from __future__ import annotations

import json
import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from plan_dataset_builder.constants import TOTAL_PLANS_PER_TASK
from plan_dataset_builder.jsonl_io import iter_jsonl


def _safe_task_filename(task_id: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", task_id).strip("_")
    if not stem:
        stem = "task"
    digest = hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:8]
    return f"{stem}_{digest}.md"


def _safe_failed_attempt_filename(task_id: str, batch_number: int, attempt_number: int, custom_id: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", task_id).strip("_")
    if not stem:
        stem = "task"
    digest_source = f"{task_id}|b{batch_number}|a{attempt_number}|{custom_id}"
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:8]
    return f"{stem}_b{batch_number}_a{attempt_number}_{digest}.md"


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    keep = max_chars // 2
    return f"{text[:keep]}\n...[TRUNCATED]...\n{text[-keep:]}"


def _format_step(step: dict[str, Any], indent: int = 0) -> list[str]:
    prefix = " " * indent
    lines = [
        f"{prefix}- [{step.get('id', '?')}] {step.get('action', '')}",
        f"{prefix}  Rationale: {step.get('rationale', '')}",
    ]
    checks = step.get("checks")
    if isinstance(checks, list) and checks:
        lines.append(f"{prefix}  Checks:")
        for check in checks:
            lines.append(f"{prefix}  - {check}")
    substeps = step.get("substeps")
    if isinstance(substeps, list) and substeps:
        lines.append(f"{prefix}  Substeps:")
        for sub in substeps:
            if isinstance(sub, dict):
                lines.extend(_format_step(sub, indent=indent + 4))
    return lines


def _render_plan_section(plan_row: dict[str, Any]) -> str:
    header = (
        f"### Batch {plan_row.get('batch_number')} / Plan {plan_row.get('within_batch_index')} "
        f"({plan_row.get('plan_id')})"
    )
    lines = [
        header,
        f"- Strategy: {plan_row.get('strategy_label', '')}",
        f"- Unique Step: {plan_row.get('unique_step', '')}",
        "",
        "Steps:",
    ]
    plan_payload = plan_row.get("plan")
    if isinstance(plan_payload, dict):
        steps = plan_payload.get("steps")
    else:
        steps = None
    if isinstance(steps, list) and steps:
        for step in steps:
            if isinstance(step, dict):
                lines.extend(_format_step(step, indent=0))
    else:
        lines.append("- [No structured steps found]")
    lines.append("")
    return "\n".join(lines)


def export_run_readable(
    run_dir: Path,
    output_dir: Path | None = None,
    *,
    include_task_text: bool = True,
    max_task_text_chars: int = 6000,
) -> dict[str, Any]:
    if not run_dir.exists():
        raise FileNotFoundError(f"Run directory does not exist: {run_dir}")

    datasets_root = run_dir / "datasets"
    if not datasets_root.exists():
        raise FileNotFoundError(f"Missing datasets directory: {datasets_root}")

    target_root = output_dir or (run_dir / "readable")
    target_root.mkdir(parents=True, exist_ok=True)

    task_rows: dict[tuple[str, str], dict[str, Any]] = {}
    plan_rows: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    datasets_seen: set[str] = set()

    for dataset_dir in sorted(datasets_root.iterdir()):
        if not dataset_dir.is_dir():
            continue
        dataset = dataset_dir.name
        datasets_seen.add(dataset)

        tasks_path = dataset_dir / "tasks.jsonl"
        plans_path = dataset_dir / "plans.jsonl"

        for row in iter_jsonl(tasks_path):
            task_id = str(row.get("task_id"))
            task_rows[(dataset, task_id)] = row

        for row in iter_jsonl(plans_path):
            task_id = str(row.get("task_id"))
            plan_rows[(dataset, task_id)].append(row)

    index_lines = [
        f"# Human Readable Plans for Run `{run_dir.name}`",
        "",
    ]
    summary: dict[str, Any] = {
        "run_dir": str(run_dir),
        "output_dir": str(target_root),
        "datasets": {},
        "tasks_written": 0,
        "plans_written": 0,
    }

    for dataset in sorted(datasets_seen):
        dataset_target = target_root / dataset
        dataset_target.mkdir(parents=True, exist_ok=True)

        keys = sorted(
            key for key in set(task_rows.keys()) | set(plan_rows.keys()) if key[0] == dataset
        )
        index_lines.append(f"## Dataset `{dataset}`")
        index_lines.append("")

        dataset_task_count = 0
        dataset_plan_count = 0

        for _, task_id in keys:
            task = task_rows.get((dataset, task_id), {})
            plans = sorted(
                plan_rows.get((dataset, task_id), []),
                key=lambda row: (
                    int(row.get("batch_number", 0) or 0),
                    int(row.get("within_batch_index", 0) or 0),
                    str(row.get("plan_id", "")),
                ),
            )

            filename = _safe_task_filename(task_id)
            task_path = dataset_target / filename
            dataset_task_count += 1
            dataset_plan_count += len(plans)

            content: list[str] = [
                f"# Run `{run_dir.name}` - `{dataset}` / `{task_id}`",
                "",
                f"- Plans found: {len(plans)}",
                f"- Expected for complete task: {TOTAL_PLANS_PER_TASK}",
                "",
            ]

            if include_task_text:
                task_text = str(task.get("task_text", ""))
                content.extend(
                    [
                        "## Task Text",
                        "",
                        "```text",
                        _truncate(task_text, max_task_text_chars),
                        "```",
                        "",
                    ]
                )

            content.append("## Plans")
            content.append("")
            if plans:
                for plan_row in plans:
                    content.append(_render_plan_section(plan_row))
            else:
                content.append("No plans were written for this task.")
                content.append("")

            task_path.write_text("\n".join(content), encoding="utf-8", newline="\n")
            index_lines.append(
                f"- `{task_id}`: [{filename}]({dataset}/{filename}) ({len(plans)} plans)"
            )

        index_lines.append("")
        summary["datasets"][dataset] = {
            "tasks_written": dataset_task_count,
            "plans_written": dataset_plan_count,
        }
        summary["tasks_written"] += dataset_task_count
        summary["plans_written"] += dataset_plan_count

    index_path = target_root / "index.md"
    index_path.write_text("\n".join(index_lines), encoding="utf-8", newline="\n")
    summary["index_path"] = str(index_path)
    return summary


def export_failed_run_readable(
    run_dir: Path,
    output_dir: Path | None = None,
    *,
    include_task_text: bool = True,
    max_task_text_chars: int = 6000,
    max_raw_response_chars: int = 12000,
    max_parsed_preview_chars: int = 12000,
) -> dict[str, Any]:
    if not run_dir.exists():
        raise FileNotFoundError(f"Run directory does not exist: {run_dir}")

    failed_datasets_root = run_dir / "failed_plans" / "datasets"
    if not failed_datasets_root.exists():
        raise FileNotFoundError(f"Missing failed_plans datasets directory: {failed_datasets_root}")

    target_root = output_dir or (run_dir / "failed_plans" / "readable")
    target_root.mkdir(parents=True, exist_ok=True)

    task_rows: dict[tuple[str, str], dict[str, Any]] = {}
    failed_rows_by_dataset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    datasets_seen: set[str] = set()

    for dataset_dir in sorted(failed_datasets_root.iterdir()):
        if not dataset_dir.is_dir():
            continue
        dataset = dataset_dir.name
        datasets_seen.add(dataset)

        tasks_path = dataset_dir / "tasks.jsonl"
        failed_plans_path = dataset_dir / "plans.jsonl"

        for row in iter_jsonl(tasks_path):
            task_id = str(row.get("task_id"))
            task_rows[(dataset, task_id)] = row

        for row in iter_jsonl(failed_plans_path):
            failed_rows_by_dataset[dataset].append(row)

    index_lines = [
        f"# Failed Validation Attempts for Run `{run_dir.name}`",
        "",
    ]
    summary: dict[str, Any] = {
        "run_dir": str(run_dir),
        "output_dir": str(target_root),
        "datasets": {},
        "tasks_written": 0,
        "failed_attempts_written": 0,
    }

    for dataset in sorted(datasets_seen):
        rows = sorted(
            failed_rows_by_dataset.get(dataset, []),
            key=lambda row: (
                str(row.get("task_id", "")),
                int(row.get("batch_number", 0) or 0),
                int(row.get("attempt_number", 0) or 0),
                str(row.get("failed_plan_id", "")),
            ),
        )
        if not rows:
            continue

        dataset_target = target_root / dataset
        dataset_target.mkdir(parents=True, exist_ok=True)

        task_ids_seen: set[str] = set()
        index_lines.append(f"## Dataset `{dataset}`")
        index_lines.append("")

        for row in rows:
            task_id = str(row.get("task_id", ""))
            batch_number = int(row.get("batch_number", 0) or 0)
            attempt_number = int(row.get("attempt_number", 0) or 0)
            custom_id = str(row.get("custom_id", ""))

            filename = _safe_failed_attempt_filename(
                task_id=task_id,
                batch_number=batch_number,
                attempt_number=attempt_number,
                custom_id=custom_id,
            )
            output_path = dataset_target / filename
            task_ids_seen.add(task_id)

            task = task_rows.get((dataset, task_id), {})
            error = row.get("error")
            if not isinstance(error, dict):
                error = {"message": str(error)}
            parsed_response = row.get("parsed_response")

            body_lines: list[str] = [
                f"# Failed Plan Attempt - `{dataset}` / `{task_id}`",
                "",
                f"- Failed Plan ID: {row.get('failed_plan_id', '')}",
                f"- Batch: {batch_number}",
                f"- Attempt: {attempt_number}",
                f"- Model: {row.get('model', '')}",
                f"- Request ID: {row.get('request_id', '')}",
                f"- Batch ID: {row.get('batch_id', '')}",
                f"- Custom ID: {custom_id}",
                f"- Timestamp (UTC): {row.get('timestamp_utc', '')}",
                "",
                "## Validation Error",
                "",
                f"- Code: {error.get('code', '')}",
                f"- Message: {error.get('message', '')}",
            ]
            if error.get("details") is not None:
                body_lines.extend(
                    [
                        "- Details:",
                        "```json",
                        _truncate(
                            json.dumps(error.get("details"), ensure_ascii=False, indent=2, sort_keys=True),
                            max_parsed_preview_chars,
                        ),
                        "```",
                    ]
                )

            if include_task_text:
                task_text = str(task.get("task_text", ""))
                body_lines.extend(
                    [
                        "",
                        "## Task Text",
                        "",
                        "```text",
                        _truncate(task_text, max_task_text_chars),
                        "```",
                    ]
                )

            raw_response_text = str(row.get("raw_response_text", ""))
            body_lines.extend(
                [
                    "",
                    "## Raw Response Text",
                    "",
                    "```text",
                    _truncate(raw_response_text, max_raw_response_chars),
                    "```",
                ]
            )

            if parsed_response is not None:
                body_lines.extend(
                    [
                        "",
                        "## Parsed Response Preview",
                        "",
                        "```json",
                        _truncate(
                            json.dumps(parsed_response, ensure_ascii=False, indent=2, sort_keys=True),
                            max_parsed_preview_chars,
                        ),
                        "```",
                    ]
                )

            output_path.write_text("\n".join(body_lines) + "\n", encoding="utf-8", newline="\n")
            index_lines.append(
                f"- `{task_id}` b{batch_number} a{attempt_number}: [{filename}]({dataset}/{filename})"
            )

        index_lines.append("")
        summary["datasets"][dataset] = {
            "tasks_written": len(task_ids_seen),
            "failed_attempts_written": len(rows),
        }
        summary["tasks_written"] += len(task_ids_seen)
        summary["failed_attempts_written"] += len(rows)

    index_path = target_root / "index.md"
    index_path.write_text("\n".join(index_lines), encoding="utf-8", newline="\n")
    summary["index_path"] = str(index_path)
    return summary
