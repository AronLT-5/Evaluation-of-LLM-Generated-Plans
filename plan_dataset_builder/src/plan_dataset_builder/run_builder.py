from __future__ import annotations

import json
import math
import os
import warnings
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from plan_dataset_builder.budget import (
    estimate_cost_from_usage,
    estimate_request_upper_cost,
    select_budget_chunk,
)
from plan_dataset_builder.config import AppConfig, load_config
from plan_dataset_builder.constants import BATCH_NUMBERS, PLANS_PER_BATCH, TOTAL_PLANS_PER_TASK
from plan_dataset_builder.datasets import get_enabled_loaders
from plan_dataset_builder.ids import make_plan_id
from plan_dataset_builder.jsonl_io import append_jsonl, iter_jsonl, sha256_file, write_json, write_jsonl
from plan_dataset_builder.labels import labels_by_batch
from plan_dataset_builder.models import FailedPlanRecord, PlanRecord, RunSummary, TaskRecord
from plan_dataset_builder.openai_api import (
    OpenAIAdapter,
    extract_response_text,
    extract_usage,
    normalize_plan_group_text,
    parse_batch_output_lines,
)
from plan_dataset_builder.plan_validation import (
    PlanValidationError,
    compute_unique_step_match,
    validate_plan_group,
)
from plan_dataset_builder.prompting import (
    compute_prompt_version_hash,
    copy_template,
    load_template,
    render_template,
)

RETRYABLE_ERROR_TERMS = {
    "rate_limit",
    "timeout",
    "temporarily_unavailable",
    "server_error",
    "internal_error",
    "api_connection_error",
    "batch_expired",
}


@dataclass
class PlannedCall:
    dataset: str
    task_id: str
    batch_number: int
    attempt_number: int
    model: str
    custom_id: str
    prompt: str
    allowed_labels: list[str]
    cost_upper: float
    input_tokens_est: int
    output_tokens_est: int


@dataclass
class CallResult:
    success: bool
    dataset: str
    task_id: str
    batch_number: int
    attempt_number: int
    model: str
    custom_id: str
    timestamp_utc: str
    raw_text: str | None
    plans: list[dict[str, Any]]
    warnings_by_plan: list[list[str]]
    request_id: str | None
    batch_id: str | None
    usage: dict[str, int] | None
    cost_estimated_request: float
    error: dict[str, Any] | None
    retryable: bool


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _generate_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _resolve_path(config_path: Path, target_path: str) -> Path:
    raw = Path(target_path)
    if raw.is_absolute():
        return raw
    candidate = (config_path.parent / raw).resolve()
    if candidate.exists():
        return candidate
    return (Path.cwd() / raw).resolve()


def _is_retryable_error(code: str | None, message: str | None) -> bool:
    code_lower = (code or "").strip().lower()
    if code_lower in {"http_429", "http_500", "http_502", "http_503", "http_504"}:
        return True
    if code_lower.startswith("http_5"):
        return True
    if any(term == code_lower or term in code_lower for term in RETRYABLE_ERROR_TERMS):
        return True

    message_lower = (message or "").lower()
    return any(term in message_lower for term in RETRYABLE_ERROR_TERMS)


def _make_custom_id(run_id: str, dataset: str, task_id: str, batch_number: int, attempt_number: int) -> str:
    return f"{run_id}:{dataset}:{task_id}:b{batch_number}:a{attempt_number}"


def _make_failed_plan_id(run_id: str, dataset: str, task_id: str, batch_number: int, attempt_number: int) -> str:
    return f"{dataset}:{task_id}:{run_id}:b{batch_number}:a{attempt_number}"


def _ensure_run_dirs(run_dir: Path) -> None:
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    (run_dir / "prompts").mkdir(parents=True, exist_ok=True)
    (run_dir / "config").mkdir(parents=True, exist_ok=True)
    (run_dir / "manifests").mkdir(parents=True, exist_ok=True)
    (run_dir / "datasets").mkdir(parents=True, exist_ok=True)


def _load_existing_tasks(tasks_path: Path) -> list[TaskRecord]:
    records: list[TaskRecord] = []
    for row in iter_jsonl(tasks_path):
        records.append(TaskRecord.model_validate(row))
    return records


def _scan_existing_plan_state(run_dir: Path, datasets: list[str]) -> tuple[
    set[str],
    dict[tuple[str, str, int], int],
    dict[tuple[str, str], int],
]:
    existing_plan_ids: set[str] = set()
    group_counts: dict[tuple[str, str, int], int] = defaultdict(int)
    task_plan_counts: dict[tuple[str, str], int] = defaultdict(int)

    for dataset in datasets:
        plans_path = run_dir / "datasets" / dataset / "plans.jsonl"
        for row in iter_jsonl(plans_path):
            plan_id = row.get("plan_id")
            if isinstance(plan_id, str):
                existing_plan_ids.add(plan_id)
            dataset_value = str(row.get("dataset", dataset))
            task_id = str(row["task_id"])
            batch_number = int(row["batch_number"])
            group_counts[(dataset_value, task_id, batch_number)] += 1
            task_plan_counts[(dataset_value, task_id)] += 1

    return existing_plan_ids, group_counts, task_plan_counts


def _scan_existing_log_state(log_path: Path) -> tuple[
    dict[tuple[str, str, int], int],
    float,
    int,
    int,
    int,
]:
    max_attempt_by_group: dict[tuple[str, str, int], int] = defaultdict(lambda: -1)
    estimated_cost_total = 0.0
    input_tokens_total = 0
    output_tokens_total = 0
    total_tokens_total = 0

    for row in iter_jsonl(log_path):
        key = (str(row["dataset"]), str(row["task_id"]), int(row["batch_number"]))
        max_attempt_by_group[key] = max(max_attempt_by_group[key], int(row["attempt_number"]))
        estimated_cost_total += float(row.get("estimated_cost", 0.0) or 0.0)
        input_tokens_total += int(row.get("input_tokens", 0) or 0)
        output_tokens_total += int(row.get("output_tokens", 0) or 0)
        total_tokens_total += int(row.get("total_tokens", 0) or 0)

    return (
        max_attempt_by_group,
        estimated_cost_total,
        input_tokens_total,
        output_tokens_total,
        total_tokens_total,
    )


def _scan_existing_failed_artifact_state(
    run_dir: Path, datasets: list[str]
) -> tuple[set[str], set[tuple[str, str]]]:
    existing_failed_plan_ids: set[str] = set()
    existing_failed_task_keys: set[tuple[str, str]] = set()

    for dataset in datasets:
        failed_plans_path = run_dir / "failed_plans" / "datasets" / dataset / "plans.jsonl"
        for row in iter_jsonl(failed_plans_path):
            failed_plan_id = row.get("failed_plan_id")
            if isinstance(failed_plan_id, str):
                existing_failed_plan_ids.add(failed_plan_id)

        failed_tasks_path = run_dir / "failed_plans" / "datasets" / dataset / "tasks.jsonl"
        for row in iter_jsonl(failed_tasks_path):
            task_id = row.get("task_id")
            if isinstance(task_id, str):
                dataset_value = str(row.get("dataset", dataset))
                existing_failed_task_keys.add((dataset_value, task_id))

    return existing_failed_plan_ids, existing_failed_task_keys


def _best_effort_parse_json(text: str | None) -> dict[str, Any] | list[Any] | None:
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, (dict, list)):
        return parsed
    return None


def _serialize_json_preview(value: Any, max_chars: int = 12_000) -> str:
    try:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        serialized = str(value)
    if len(serialized) <= max_chars:
        return serialized
    keep = max_chars // 2
    return f"{serialized[:keep]}\n...[TRUNCATED]...\n{serialized[-keep:]}"


def _write_call_log(
    *,
    log_path: Path,
    run_id: str,
    decoding: dict[str, Any],
    prompt_version_hash: str,
    result: CallResult,
    status: str,
    budget_remaining_estimated: float,
) -> None:
    usage = result.usage or {}
    append_jsonl(
        log_path,
        {
            "dataset": result.dataset,
            "task_id": result.task_id,
            "run_id": run_id,
            "batch_number": result.batch_number,
            "attempt_number": result.attempt_number,
            "model": result.model,
            "decoding": decoding,
            "prompt_version_hash": prompt_version_hash,
            "timestamp_utc": result.timestamp_utc,
            "request_id": result.request_id,
            "batch_id": result.batch_id,
            "custom_id": result.custom_id,
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "cached_input_tokens": usage.get("cached_input_tokens"),
            "reasoning_tokens": usage.get("reasoning_tokens"),
            "usage": usage if usage else None,
            "estimated_cost": result.cost_estimated_request,
            "status": status,
            "error": result.error,
            "budget_remaining_estimated": budget_remaining_estimated,
        },
    )


def _execute_sync_call(
    *,
    adapter: OpenAIAdapter,
    call: PlannedCall,
    config: AppConfig,
) -> CallResult:
    timestamp_utc = _utc_now()
    try:
        response_body, request_id = adapter.create_response(call.prompt, model=call.model)
        request_id = request_id or response_body.get("request_id")
        usage = extract_usage(response_body)
        try:
            raw_text = extract_response_text(response_body)
            normalized_raw_text = normalize_plan_group_text(raw_text)
            validated = validate_plan_group(
                normalized_raw_text,
                allowed_labels=call.allowed_labels,
                schema_version=config.prompt.schema_version,
                bounds=config.prompt.bounds,
            )
        except PlanValidationError as exc:
            cost = estimate_cost_from_usage(usage, config.budget.pricing) if usage else call.cost_upper
            return CallResult(
                success=False,
                dataset=call.dataset,
                task_id=call.task_id,
                batch_number=call.batch_number,
                attempt_number=call.attempt_number,
                model=call.model,
                custom_id=call.custom_id,
                timestamp_utc=timestamp_utc,
                raw_text=normalized_raw_text,
                plans=[],
                warnings_by_plan=[],
                request_id=request_id,
                batch_id=None,
                usage=usage,
                cost_estimated_request=cost,
                error={
                    "code": "validation_error",
                    "message": str(exc),
                    "details": exc.details,
                },
                retryable=True,
            )
        except Exception as exc:
            code = getattr(exc, "code", None) or exc.__class__.__name__
            message = str(exc)
            cost = estimate_cost_from_usage(usage, config.budget.pricing) if usage else call.cost_upper
            response_preview = _serialize_json_preview(response_body)
            return CallResult(
                success=False,
                dataset=call.dataset,
                task_id=call.task_id,
                batch_number=call.batch_number,
                attempt_number=call.attempt_number,
                model=call.model,
                custom_id=call.custom_id,
                timestamp_utc=timestamp_utc,
                raw_text=response_preview,
                plans=[],
                warnings_by_plan=[],
                request_id=request_id,
                batch_id=None,
                usage=usage,
                cost_estimated_request=cost,
                error={
                    "code": code,
                    "message": message,
                    "details": {
                        "extract_stage": "sync_post_response_parse",
                        "response_body_preview": response_preview,
                    },
                },
                retryable=_is_retryable_error(code, message),
            )
        cost = estimate_cost_from_usage(usage, config.budget.pricing) if usage else call.cost_upper
        return CallResult(
            success=True,
            dataset=call.dataset,
            task_id=call.task_id,
            batch_number=call.batch_number,
            attempt_number=call.attempt_number,
            model=call.model,
            custom_id=call.custom_id,
            timestamp_utc=timestamp_utc,
            raw_text=normalized_raw_text,
            plans=validated.plans,
            warnings_by_plan=validated.warnings_by_plan,
            request_id=request_id,
            batch_id=None,
            usage=usage,
            cost_estimated_request=cost,
            error=None,
            retryable=False,
        )
    except Exception as exc:  # pragma: no cover - network/API path
        code = getattr(exc, "code", None) or exc.__class__.__name__
        message = str(exc)
        return CallResult(
            success=False,
            dataset=call.dataset,
            task_id=call.task_id,
            batch_number=call.batch_number,
            attempt_number=call.attempt_number,
            model=call.model,
            custom_id=call.custom_id,
            timestamp_utc=timestamp_utc,
            raw_text=None,
            plans=[],
            warnings_by_plan=[],
            request_id=None,
            batch_id=None,
            usage=None,
            cost_estimated_request=call.cost_upper,
            error={"code": code, "message": message, "details": None},
            retryable=_is_retryable_error(code, message),
        )


def _execute_batch_chunk(
    *,
    adapter: OpenAIAdapter,
    calls: list[PlannedCall],
    run_dir: Path,
    config: AppConfig,
    chunk_index: int,
) -> list[CallResult]:
    models = {call.model for call in calls}
    if len(models) != 1:
        raise RuntimeError("Batch API chunk cannot mix models; all calls in a batch must share one model.")

    input_path = run_dir / "logs" / f"batch_input_{chunk_index:05d}.jsonl"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    with input_path.open("w", encoding="utf-8", newline="\n") as handle:
        for call in calls:
            payload = {
                "custom_id": call.custom_id,
                "method": "POST",
                "url": "/v1/responses",
                "body": adapter.build_request_body(call.prompt, model=call.model),
            }
            handle.write(json.dumps(payload, ensure_ascii=False))
            handle.write("\n")

    batch_info = adapter.submit_batch(input_path)
    batch_id = str(batch_info.get("id"))
    finished = adapter.wait_for_batch(batch_id=batch_id)

    output_lookup: dict[str, dict[str, Any]] = {}
    error_lookup: dict[str, dict[str, Any]] = {}

    output_file_id = finished.get("output_file_id")
    if output_file_id:
        output_text = adapter.download_file_text(str(output_file_id))
        output_path = run_dir / "logs" / f"batch_output_{batch_id}.jsonl"
        output_path.write_text(output_text, encoding="utf-8", newline="\n")
        output_lookup = parse_batch_output_lines(output_text)

    error_file_id = finished.get("error_file_id")
    if error_file_id:
        error_text = adapter.download_file_text(str(error_file_id))
        error_path = run_dir / "logs" / f"batch_error_{batch_id}.jsonl"
        error_path.write_text(error_text, encoding="utf-8", newline="\n")
        error_lookup = parse_batch_output_lines(error_text)

    results: list[CallResult] = []
    for call in calls:
        timestamp_utc = _utc_now()
        line = output_lookup.get(call.custom_id) or error_lookup.get(call.custom_id)
        if line is None:
            results.append(
                CallResult(
                    success=False,
                    dataset=call.dataset,
                    task_id=call.task_id,
                    batch_number=call.batch_number,
                    attempt_number=call.attempt_number,
                    model=call.model,
                    custom_id=call.custom_id,
                    timestamp_utc=timestamp_utc,
                    raw_text=None,
                    plans=[],
                    warnings_by_plan=[],
                    request_id=None,
                    batch_id=batch_id,
                    usage=None,
                    cost_estimated_request=call.cost_upper,
                    error={
                        "code": "batch_missing_result",
                        "message": f"No batch output line for custom_id={call.custom_id}",
                        "details": {"batch_status": finished.get("status")},
                    },
                    retryable=True,
                )
            )
            continue

        response = line.get("response")
        if isinstance(response, dict) and int(response.get("status_code", 0) or 0) in range(200, 300):
            body = response.get("body") if isinstance(response.get("body"), dict) else {}
            request_id = response.get("request_id")
            try:
                raw_text = extract_response_text(body)
                normalized_raw_text = normalize_plan_group_text(raw_text)
                usage = extract_usage(body)
                validated = validate_plan_group(
                    normalized_raw_text,
                    allowed_labels=call.allowed_labels,
                    schema_version=config.prompt.schema_version,
                    bounds=config.prompt.bounds,
                )
                cost = estimate_cost_from_usage(usage, config.budget.pricing) if usage else call.cost_upper
                results.append(
                    CallResult(
                        success=True,
                        dataset=call.dataset,
                        task_id=call.task_id,
                        batch_number=call.batch_number,
                        attempt_number=call.attempt_number,
                        model=call.model,
                        custom_id=call.custom_id,
                        timestamp_utc=timestamp_utc,
                        raw_text=normalized_raw_text,
                        plans=validated.plans,
                        warnings_by_plan=validated.warnings_by_plan,
                        request_id=request_id,
                        batch_id=batch_id,
                        usage=usage,
                        cost_estimated_request=cost,
                        error=None,
                        retryable=False,
                    )
                )
            except PlanValidationError as exc:
                cost = estimate_cost_from_usage(usage, config.budget.pricing) if usage else call.cost_upper
                results.append(
                    CallResult(
                        success=False,
                        dataset=call.dataset,
                        task_id=call.task_id,
                        batch_number=call.batch_number,
                        attempt_number=call.attempt_number,
                        model=call.model,
                        custom_id=call.custom_id,
                        timestamp_utc=timestamp_utc,
                        raw_text=normalized_raw_text,
                        plans=[],
                        warnings_by_plan=[],
                        request_id=request_id,
                        batch_id=batch_id,
                        usage=usage,
                        cost_estimated_request=cost,
                        error={"code": "validation_error", "message": str(exc), "details": exc.details},
                        retryable=True,
                    )
                )
            except Exception as exc:
                code = getattr(exc, "code", None) or exc.__class__.__name__
                message = str(exc)
                usage = extract_usage(body)
                cost = estimate_cost_from_usage(usage, config.budget.pricing) if usage else call.cost_upper
                response_preview = _serialize_json_preview(body)
                results.append(
                    CallResult(
                        success=False,
                        dataset=call.dataset,
                        task_id=call.task_id,
                        batch_number=call.batch_number,
                        attempt_number=call.attempt_number,
                        model=call.model,
                        custom_id=call.custom_id,
                        timestamp_utc=timestamp_utc,
                        raw_text=response_preview,
                        plans=[],
                        warnings_by_plan=[],
                        request_id=request_id,
                        batch_id=batch_id,
                        usage=usage,
                        cost_estimated_request=cost,
                        error={
                            "code": code,
                            "message": message,
                            "details": {
                                "extract_stage": "batch_post_response_parse",
                                "response_body_preview": response_preview,
                            },
                        },
                        retryable=_is_retryable_error(code, message),
                    )
                )
        else:
            status_code = None
            if isinstance(response, dict):
                status_code = response.get("status_code")
            error_obj = line.get("error") or {}
            if isinstance(response, dict):
                response_body = response.get("body")
                if isinstance(response_body, dict):
                    body_error = response_body.get("error")
                    if isinstance(body_error, dict):
                        error_obj = body_error
            if not isinstance(error_obj, dict):
                error_obj = {"message": str(error_obj)}
            code = str(
                error_obj.get("code")
                or (f"http_{status_code}" if status_code is not None else "batch_error")
            )
            message = str(
                error_obj.get("message")
                or f"Batch request failed with status_code={status_code}"
            )
            results.append(
                CallResult(
                    success=False,
                    dataset=call.dataset,
                    task_id=call.task_id,
                    batch_number=call.batch_number,
                    attempt_number=call.attempt_number,
                    model=call.model,
                    custom_id=call.custom_id,
                    timestamp_utc=timestamp_utc,
                    raw_text=None,
                    plans=[],
                    warnings_by_plan=[],
                    request_id=response.get("request_id") if isinstance(response, dict) else None,
                    batch_id=batch_id,
                    usage=None,
                    cost_estimated_request=call.cost_upper,
                    error={"code": code, "message": message, "details": error_obj},
                    retryable=_is_retryable_error(code, message),
                )
            )

    return results


def _write_plan_rows(
    *,
    run_id: str,
    run_dir: Path,
    config: AppConfig,
    call: PlannedCall,
    result: CallResult,
    existing_plan_ids: set[str],
    group_counts: dict[tuple[str, str, int], int],
    task_plan_counts: dict[tuple[str, str], int],
    prompt_version_hash: str,
) -> int:
    if not result.success or result.raw_text is None:
        return 0

    plans_path = run_dir / "datasets" / call.dataset / "plans.jsonl"
    plans_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    for index, plan in enumerate(result.plans, start=1):
        plan_id = make_plan_id(
            dataset=call.dataset,
            task_id=call.task_id,
            run_id=run_id,
            batch_number=call.batch_number,
            within_batch_index=index,
        )
        if plan_id in existing_plan_ids:
            continue

        record = PlanRecord(
            schema_version="1.0",
            dataset=call.dataset,  # type: ignore[arg-type]
            task_id=call.task_id,
            run_id=run_id,
            plan_id=plan_id,
            batch_number=call.batch_number,
            within_batch_index=index,
            strategy_label=str(plan["strategy_label"]),
            unique_step=str(plan["unique_step"]),
            plan=plan,
            plan_raw=result.raw_text,
            gen={
                "model": call.model,
                "decoding": {
                    "temperature": config.openai.temperature,
                    "top_p": config.openai.top_p,
                    "max_output_tokens": config.openai.max_output_tokens,
                    "seed": config.openai.seed,
                },
                "prompt_version_hash": prompt_version_hash,
                "timestamp_utc": result.timestamp_utc,
                "request_id": result.request_id,
                "batch_id": result.batch_id,
                "custom_id": call.custom_id,
                "attempt_number": call.attempt_number,
                "token_usage": result.usage or {},
                "cost_estimated_request": result.cost_estimated_request,
                "warnings": result.warnings_by_plan[index - 1] if index - 1 < len(result.warnings_by_plan) else [],
            },
            extras={},
            unique_step_flag="pass" if compute_unique_step_match(plan) else "fail",
        ).model_dump(mode="json")

        append_jsonl(plans_path, record)
        existing_plan_ids.add(plan_id)
        group_counts[(call.dataset, call.task_id, call.batch_number)] += 1
        task_plan_counts[(call.dataset, call.task_id)] += 1
        written += 1

    return written


def _write_failed_plan_artifacts(
    *,
    run_id: str,
    run_dir: Path,
    task: TaskRecord,
    result: CallResult,
    existing_failed_plan_ids: set[str],
    existing_failed_task_keys: set[tuple[str, str]],
) -> tuple[int, int]:
    error = result.error or {}
    if str(error.get("code", "")).strip() != "validation_error":
        return 0, 0

    failed_plans_root = run_dir / "failed_plans" / "datasets" / result.dataset
    failed_plans_path = failed_plans_root / "plans.jsonl"
    failed_tasks_path = failed_plans_root / "tasks.jsonl"

    task_key = (result.dataset, result.task_id)
    tasks_written = 0
    if task_key not in existing_failed_task_keys:
        append_jsonl(failed_tasks_path, task.model_dump(mode="json"))
        existing_failed_task_keys.add(task_key)
        tasks_written = 1

    failed_plan_id = _make_failed_plan_id(
        run_id=run_id,
        dataset=result.dataset,
        task_id=result.task_id,
        batch_number=result.batch_number,
        attempt_number=result.attempt_number,
    )
    if failed_plan_id in existing_failed_plan_ids:
        return 0, tasks_written

    details = error.get("details")
    error_payload = {
        "code": str(error.get("code", "validation_error")),
        "message": str(error.get("message", "Local validation failed")),
        "details": details if isinstance(details, (dict, list, str, int, float, bool)) or details is None else str(details),
    }

    failed_record = FailedPlanRecord(
        schema_version="1.0",
        dataset=result.dataset,  # type: ignore[arg-type]
        task_id=result.task_id,
        run_id=run_id,
        failed_plan_id=failed_plan_id,
        batch_number=result.batch_number,
        attempt_number=result.attempt_number,
        model=result.model,
        custom_id=result.custom_id,
        timestamp_utc=result.timestamp_utc,
        error=error_payload,
        raw_response_text=result.raw_text or "",
        parsed_response=_best_effort_parse_json(result.raw_text),
        request_id=result.request_id,
        batch_id=result.batch_id,
        extras={},
    ).model_dump(mode="json")
    append_jsonl(failed_plans_path, failed_record)
    existing_failed_plan_ids.add(failed_plan_id)
    return 1, tasks_written


def execute_run(
    *,
    config_path: Path,
    run_id_override: str | None,
    resume_override: bool | None,
    dry_run: bool,
) -> Path:
    config = load_config(config_path)
    if (
        config.openai.temperature is not None
        or config.openai.top_p is not None
        or config.openai.seed is not None
    ):
        warnings.warn(
            "openai.temperature/top_p/seed are ignored for compatibility; remove from config.",
            stacklevel=2,
        )
    if not config.openai.structured_outputs:
        warnings.warn(
            "openai.structured_outputs=false is ignored; structured outputs are always enabled for plan generation.",
            stacklevel=2,
        )
        config.openai.structured_outputs = True
    models_by_batch = config.openai.model_map_by_batch()

    run_id = run_id_override or config.run.run_id or _generate_run_id()
    resume = config.run.resume if resume_override is None else resume_override

    output_root = Path(config.run.output_root)
    if not output_root.is_absolute():
        output_root = (Path.cwd() / output_root).resolve()
    run_dir = output_root / run_id

    if run_dir.exists() and not resume and any(run_dir.iterdir()):
        raise RuntimeError(f"Run directory already exists and is non-empty: {run_dir}")

    _ensure_run_dirs(run_dir)
    batch_call_log_path = run_dir / "logs" / "batch_calls.jsonl"
    if not batch_call_log_path.exists():
        batch_call_log_path.write_text("", encoding="utf-8", newline="\n")

    started_at_utc = _utc_now()

    template_path = _resolve_path(config_path=config_path, target_path=config.prompt.template_path)
    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")
    template_text = load_template(template_path)
    template_bytes = template_path.read_bytes()

    prompt_render_config = {
        "schema_version": config.prompt.schema_version,
        "bounds": config.prompt.bounds.model_dump(mode="json"),
        "task_text": config.task_text.model_dump(mode="json"),
        "enforce_unique_labels_across_12": config.diversity.enforce_unique_labels_across_12,
        "openai_multi_model": config.openai.multi_model,
        "models_by_batch": {f"batch_{batch}": model for batch, model in sorted(models_by_batch.items())},
    }
    prompt_version_hash = compute_prompt_version_hash(template_bytes, prompt_render_config)
    used_template_path = run_dir / "prompts" / "plan_prompt_template.txt"
    copy_template(template_path, used_template_path)

    run_config_path = run_dir / "config" / "run_config.json"
    write_json(run_config_path, config.resolved_dict())

    dataset_tasks: dict[str, list[TaskRecord]] = {}
    dataset_sources: dict[str, str] = {}
    manifest_path_lookup: dict[str, Path] = {}

    loaders = get_enabled_loaders(config=config, config_dir=config_path.parent)
    for loader in loaders:
        dataset = loader.dataset_name
        dataset_dir = run_dir / "datasets" / dataset
        tasks_path = dataset_dir / "tasks.jsonl"
        plans_path = dataset_dir / "plans.jsonl"
        dataset_dir.mkdir(parents=True, exist_ok=True)

        if resume and tasks_path.exists():
            tasks = _load_existing_tasks(tasks_path)
            source = tasks[0].source if tasks else getattr(loader, "source", "unknown")
            extra_manifests = {}
        else:
            loaded = loader.load(config)
            tasks = loaded.tasks
            source = loaded.source
            extra_manifests = loaded.extra_manifests
            write_jsonl(tasks_path, (task.model_dump(mode="json") for task in tasks))
        if not plans_path.exists():
            plans_path.write_text("", encoding="utf-8", newline="\n")

        dataset_tasks[dataset] = tasks
        dataset_sources[dataset] = source

        task_ids = [task.task_id for task in tasks]
        task_manifest_path = run_dir / "manifests" / f"{dataset}_task_ids.json"
        write_json(task_manifest_path, task_ids)
        manifest_path_lookup[task_manifest_path.name] = task_manifest_path

        if dataset == "swebench_verified" and config.datasets.swebench_verified.write_first100_manifest:
            first100 = task_ids[:100]
            first100_path = run_dir / "manifests" / "swebench_verified_first100_instance_ids.json"
            write_json(first100_path, first100)
            manifest_path_lookup[first100_path.name] = first100_path

        for filename, payload in extra_manifests.items():
            manifest_path = run_dir / "manifests" / filename
            write_json(manifest_path, payload)
            manifest_path_lookup[manifest_path.name] = manifest_path

    dataset_names = sorted(dataset_tasks.keys())
    task_lookup: dict[tuple[str, str], TaskRecord] = {}
    for dataset in dataset_names:
        for task in dataset_tasks[dataset]:
            task_lookup[(dataset, task.task_id)] = task

    existing_plan_ids, group_counts, task_plan_counts = _scan_existing_plan_state(run_dir, dataset_names)
    (
        existing_failed_plan_ids,
        existing_failed_task_keys,
    ) = _scan_existing_failed_artifact_state(run_dir, dataset_names)
    (
        max_attempt_by_group,
        estimated_cost_spent,
        input_tokens_total,
        output_tokens_total,
        total_tokens_total,
    ) = _scan_existing_log_state(batch_call_log_path)

    pending_calls: list[PlannedCall] = []
    permanently_failed_groups: set[tuple[str, str, int]] = set()
    failed_validation_attempts_written = 0
    failed_validation_tasks_written = 0

    for dataset in dataset_names:
        label_set = config.diversity.label_sets[dataset]
        for task in dataset_tasks[dataset]:
            batch_labels = labels_by_batch(task.task_id, label_set)
            if config.diversity.enforce_unique_labels_across_12:
                labels_all = [label for batch in BATCH_NUMBERS for label in batch_labels[batch]]
                if len(set(labels_all)) != TOTAL_PLANS_PER_TASK:
                    raise RuntimeError(f"Label uniqueness violation for task {dataset}:{task.task_id}")

            for batch_number in BATCH_NUMBERS:
                group_key = (dataset, task.task_id, batch_number)
                if group_counts.get(group_key, 0) >= PLANS_PER_BATCH:
                    continue

                next_attempt = max_attempt_by_group.get(group_key, -1) + 1
                if next_attempt > config.retries.max_retries_per_batch_call:
                    permanently_failed_groups.add(group_key)
                    continue

                model_for_call = models_by_batch[batch_number]
                values = {
                    "dataset": dataset,
                    "task_id": task.task_id,
                    "task_text": task.task_text,
                    "batch_number": str(batch_number),
                    "allowed_labels_json": json.dumps(batch_labels[batch_number], ensure_ascii=False),
                    "schema_version": config.prompt.schema_version,
                    "bounds_json": json.dumps(
                        config.prompt.bounds.model_dump(mode="json"),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                }
                prompt = render_template(template_text, values)
                estimate = estimate_request_upper_cost(
                    prompt_text=prompt,
                    model=model_for_call,
                    max_output_tokens=config.openai.max_output_tokens,
                    pricing=config.budget.pricing,
                )
                pending_calls.append(
                    PlannedCall(
                        dataset=dataset,
                        task_id=task.task_id,
                        batch_number=batch_number,
                        attempt_number=next_attempt,
                        model=model_for_call,
                        custom_id=_make_custom_id(
                            run_id=run_id,
                            dataset=dataset,
                            task_id=task.task_id,
                            batch_number=batch_number,
                            attempt_number=next_attempt,
                        ),
                        prompt=prompt,
                        allowed_labels=batch_labels[batch_number],
                        cost_upper=estimate.cost_upper,
                        input_tokens_est=estimate.input_tokens_est,
                        output_tokens_est=estimate.output_tokens_est,
                    )
                )

    pending_calls.sort(key=lambda call: (call.model, call.dataset, call.task_id, call.batch_number, call.attempt_number))
    pending_upper_cost = sum(call.cost_upper for call in pending_calls)

    projected_total_cost = estimated_cost_spent + pending_upper_cost
    if (
        not dry_run
        and projected_total_cost > config.budget.budget_total
        and not config.budget.allow_over_budget
    ):
        raise RuntimeError(
            "Preflight budget check failed: "
            f"estimated_spent={estimated_cost_spent:.6f}, pending_upper={pending_upper_cost:.6f}, "
            f"budget_total={config.budget.budget_total:.6f}. "
            "Set budget.allow_over_budget=true to override."
        )

    plans_written_new = 0
    actual_cost_total_from_usage = estimate_cost_from_usage(
        {"input_tokens": input_tokens_total, "output_tokens": output_tokens_total},
        config.budget.pricing,
    )
    batch_chunk_index = 0

    if not dry_run and pending_calls:
        api_key = os.environ.get(config.openai.api_key_env_var)
        if not api_key:
            raise RuntimeError(
                f"Missing API key environment variable: {config.openai.api_key_env_var}"
            )

        adapter = OpenAIAdapter(
            api_key=api_key,
            openai_config=config.openai,
            schema_version=config.prompt.schema_version,
            bounds=config.prompt.bounds,
        )

        queue = list(pending_calls)
        while queue:
            queue.sort(key=lambda call: (call.model, call.dataset, call.task_id, call.batch_number, call.attempt_number))
            budget_remaining = config.budget.budget_total - estimated_cost_spent
            budget_limit = math.inf if config.budget.allow_over_budget else budget_remaining * config.budget.safety_margin
            if not config.budget.allow_over_budget and budget_limit <= 0:
                raise RuntimeError("Budget exhausted before completing all pending requests.")

            if config.openai.use_batch_api:
                selected_model = queue[0].model
                model_queue = [call for call in queue if call.model == selected_model]
                chunk = select_budget_chunk(model_queue, [call.cost_upper for call in model_queue], budget_limit)
                if not config.budget.allow_over_budget and chunk and chunk[0].cost_upper > budget_limit:
                    raise RuntimeError(
                        f"Single call upper-bound cost {chunk[0].cost_upper:.6f} exceeds allowed chunk budget "
                        f"{budget_limit:.6f}. Increase budget or allow_over_budget."
                    )
                chunk_ids = {call.custom_id for call in chunk}
                queue = [call for call in queue if call.custom_id not in chunk_ids]
                batch_chunk_index += 1
                processed_calls = chunk
                results = _execute_batch_chunk(
                    adapter=adapter,
                    calls=chunk,
                    run_dir=run_dir,
                    config=config,
                    chunk_index=batch_chunk_index,
                )
            else:
                call = queue.pop(0)
                if not config.budget.allow_over_budget and call.cost_upper > budget_limit:
                    raise RuntimeError(
                        f"Call upper-bound cost {call.cost_upper:.6f} exceeds allowed request budget "
                        f"{budget_limit:.6f}. Increase budget or allow_over_budget."
                    )
                processed_calls = [call]
                results = [_execute_sync_call(adapter=adapter, call=call, config=config)]

            processed_call_map = {call.custom_id: call for call in processed_calls}
            for result in results:
                estimated_cost_spent += result.cost_estimated_request
                usage = result.usage or {}
                input_tokens_total += int(usage.get("input_tokens", 0) or 0)
                output_tokens_total += int(usage.get("output_tokens", 0) or 0)
                total_tokens_total += int(usage.get("total_tokens", 0) or 0)
                if usage:
                    actual_cost_total_from_usage += estimate_cost_from_usage(usage, config.budget.pricing)

                will_retry = result.retryable and result.attempt_number < config.retries.max_retries_per_batch_call
                status = "ok" if result.success else ("retry" if will_retry else "failed")
                budget_remaining_estimated = config.budget.budget_total - estimated_cost_spent

                _write_call_log(
                    log_path=batch_call_log_path,
                    run_id=run_id,
                    decoding={
                        "temperature": config.openai.temperature,
                        "top_p": config.openai.top_p,
                        "max_output_tokens": config.openai.max_output_tokens,
                        "seed": config.openai.seed,
                    },
                    prompt_version_hash=prompt_version_hash,
                    result=result,
                    status=status,
                    budget_remaining_estimated=budget_remaining_estimated,
                )

                matched = processed_call_map.get(result.custom_id)
                if matched is None:
                    continue

                if result.success:
                    plans_written_new += _write_plan_rows(
                        run_id=run_id,
                        run_dir=run_dir,
                        config=config,
                        call=matched,
                        result=result,
                        existing_plan_ids=existing_plan_ids,
                        group_counts=group_counts,
                        task_plan_counts=task_plan_counts,
                        prompt_version_hash=prompt_version_hash,
                    )
                else:
                    task_key = (result.dataset, result.task_id)
                    failed_task = task_lookup.get(task_key)
                    if failed_task is not None:
                        written_attempts, written_tasks = _write_failed_plan_artifacts(
                            run_id=run_id,
                            run_dir=run_dir,
                            task=failed_task,
                            result=result,
                            existing_failed_plan_ids=existing_failed_plan_ids,
                            existing_failed_task_keys=existing_failed_task_keys,
                        )
                        failed_validation_attempts_written += written_attempts
                        failed_validation_tasks_written += written_tasks

                    group_key = (result.dataset, result.task_id, result.batch_number)
                    if will_retry:
                        next_attempt = result.attempt_number + 1
                        if failed_task is None:
                            raise RuntimeError(
                                f"Task lookup failed for retry scheduling: {result.dataset}:{result.task_id}"
                            )
                        labels = labels_by_batch(result.task_id, config.diversity.label_sets[result.dataset])[
                            result.batch_number
                        ]
                        values = {
                            "dataset": result.dataset,
                            "task_id": result.task_id,
                            "task_text": failed_task.task_text,
                            "batch_number": str(result.batch_number),
                            "allowed_labels_json": json.dumps(labels, ensure_ascii=False),
                            "schema_version": config.prompt.schema_version,
                            "bounds_json": json.dumps(
                                config.prompt.bounds.model_dump(mode="json"),
                                ensure_ascii=False,
                                sort_keys=True,
                            ),
                        }
                        prompt = render_template(template_text, values)
                        estimate = estimate_request_upper_cost(
                            prompt_text=prompt,
                            model=result.model,
                            max_output_tokens=config.openai.max_output_tokens,
                            pricing=config.budget.pricing,
                        )
                        queue.append(
                            PlannedCall(
                                dataset=result.dataset,
                                task_id=result.task_id,
                                batch_number=result.batch_number,
                                attempt_number=next_attempt,
                                model=result.model,
                                custom_id=_make_custom_id(
                                    run_id=run_id,
                                    dataset=result.dataset,
                                    task_id=result.task_id,
                                    batch_number=result.batch_number,
                                    attempt_number=next_attempt,
                                ),
                                prompt=prompt,
                                allowed_labels=labels,
                                cost_upper=estimate.cost_upper,
                                input_tokens_est=estimate.input_tokens_est,
                                output_tokens_est=estimate.output_tokens_est,
                            )
                        )
                    else:
                        permanently_failed_groups.add(group_key)

    complete_by_dataset: dict[str, list[str]] = {}
    incomplete_by_dataset: dict[str, list[str]] = {}
    for dataset in dataset_names:
        complete: list[str] = []
        incomplete: list[str] = []
        for task in dataset_tasks[dataset]:
            group_ok = all(
                group_counts.get((dataset, task.task_id, batch), 0) >= PLANS_PER_BATCH
                for batch in BATCH_NUMBERS
            )
            if group_ok:
                complete.append(task.task_id)
            else:
                incomplete.append(task.task_id)
        complete.sort()
        incomplete.sort()
        complete_by_dataset[dataset] = complete
        incomplete_by_dataset[dataset] = incomplete

        complete_path = run_dir / "manifests" / f"{dataset}_complete_task_ids.json"
        incomplete_path = run_dir / "manifests" / f"{dataset}_incomplete_task_ids.json"
        write_json(complete_path, complete)
        write_json(incomplete_path, incomplete)
        manifest_path_lookup[complete_path.name] = complete_path
        manifest_path_lookup[incomplete_path.name] = incomplete_path

    manifest_metadata: dict[str, dict[str, Any]] = {}
    for filename, path in sorted(manifest_path_lookup.items()):
        if path.exists():
            manifest_metadata[filename] = {"path": str(path), "sha256": sha256_file(path)}

    plans_written_total = 0
    for dataset in dataset_names:
        plans_path = run_dir / "datasets" / dataset / "plans.jsonl"
        plans_written_total += sum(1 for _ in iter_jsonl(plans_path))

    failed_validation_attempts_total = 0
    failed_validation_task_keys_total: set[tuple[str, str]] = set()
    for dataset in dataset_names:
        failed_plans_path = run_dir / "failed_plans" / "datasets" / dataset / "plans.jsonl"
        failed_tasks_path = run_dir / "failed_plans" / "datasets" / dataset / "tasks.jsonl"
        failed_validation_attempts_total += sum(1 for _ in iter_jsonl(failed_plans_path))
        for row in iter_jsonl(failed_tasks_path):
            task_id = row.get("task_id")
            if isinstance(task_id, str):
                dataset_value = str(row.get("dataset", dataset))
                failed_validation_task_keys_total.add((dataset_value, task_id))

    tasks_total = sum(len(dataset_tasks[dataset]) for dataset in dataset_names)
    tasks_complete = sum(len(complete_by_dataset[dataset]) for dataset in dataset_names)
    tasks_incomplete = sum(len(incomplete_by_dataset[dataset]) for dataset in dataset_names)
    plans_expected = tasks_total * TOTAL_PLANS_PER_TASK

    run_model: str | dict[str, str]
    if config.openai.multi_model:
        run_model = {f"batch_{batch}": model for batch, model in sorted(models_by_batch.items())}
    else:
        run_model = config.openai.model

    finished_at_utc = _utc_now()
    run_summary = RunSummary(
        run_id=run_id,
        started_at_utc=started_at_utc,
        finished_at_utc=finished_at_utc,
        config={
            "resolved_config_path": str(run_config_path),
            "resolved": config.resolved_dict(),
            "failed_validation_artifacts_path": str(run_dir / "failed_plans"),
        },
        dataset_sources=dataset_sources,
        task_selection_manifests=manifest_metadata,
        prompt_version_hash=prompt_version_hash,
        prompt_template_path=str(used_template_path),
        model=run_model,
        decoding_defaults={
            "temperature": config.openai.temperature,
            "top_p": config.openai.top_p,
            "max_output_tokens": config.openai.max_output_tokens,
            "seed": config.openai.seed,
        },
        budget_total=config.budget.budget_total,
        pricing_table=config.budget.pricing.model_dump(mode="json"),
        budget_enforcement={
            "safety_margin": config.budget.safety_margin,
            "allow_over_budget": config.budget.allow_over_budget,
            "budget_remaining_estimated": config.budget.budget_total - estimated_cost_spent,
        },
        counts={
            "tasks_total": tasks_total,
            "tasks_complete": tasks_complete,
            "tasks_incomplete": tasks_incomplete,
            "plans_expected": plans_expected,
            "plans_written": plans_written_total,
            "plans_written_new": plans_written_new,
            "failed_groups": len(permanently_failed_groups),
            "failed_validation_attempts_written": failed_validation_attempts_total,
            "failed_validation_attempts_written_new": failed_validation_attempts_written,
            "failed_validation_tasks": len(failed_validation_task_keys_total),
            "failed_validation_tasks_new": failed_validation_tasks_written,
        },
        token_cost_totals={
            "input_tokens": input_tokens_total,
            "output_tokens": output_tokens_total,
            "total_tokens": total_tokens_total,
            "estimated_cost_total": estimated_cost_spent,
            "actual_cost_total_from_usage": actual_cost_total_from_usage,
            "currency": config.budget.pricing.currency,
        },
    ).model_dump(mode="json")

    append_jsonl(run_dir / "runs.jsonl", run_summary)
    return run_dir
