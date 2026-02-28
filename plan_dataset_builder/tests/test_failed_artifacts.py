from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from plan_dataset_builder.cli import app
from plan_dataset_builder.jsonl_io import iter_jsonl
from plan_dataset_builder.models import TaskRecord
from plan_dataset_builder.readable_export import export_failed_run_readable
from plan_dataset_builder.run_builder import CallResult, _write_failed_plan_artifacts


def _make_task(dataset: str = "humaneval", task_id: str = "HumanEval/0") -> TaskRecord:
    return TaskRecord(
        schema_version="1.0",
        dataset=dataset,  # type: ignore[arg-type]
        task_id=task_id,
        source="test-source",
        task_text="Solve the task",
        context_keys_included=[],
        context_keys_excluded=[],
        extras={},
    )


def _make_validation_failure(
    *,
    task_id: str = "HumanEval/0",
    batch_number: int = 1,
    attempt_number: int = 0,
) -> CallResult:
    return CallResult(
        success=False,
        dataset="humaneval",
        task_id=task_id,
        batch_number=batch_number,
        attempt_number=attempt_number,
        model="gpt-4.1-mini",
        custom_id=f"run:humaneval:{task_id}:b{batch_number}:a{attempt_number}",
        timestamp_utc="2026-02-27T00:00:00Z",
        raw_text='[{"schema_version":"1.0","strategy_label":"Spec-First"}]',
        plans=[],
        warnings_by_plan=[],
        request_id="req_123",
        batch_id=None,
        usage=None,
        cost_estimated_request=0.01,
        error={"code": "validation_error", "message": "invalid payload", "details": {"x": 1}},
        retryable=True,
    )


def _make_api_failure(task_id: str = "HumanEval/0") -> CallResult:
    return CallResult(
        success=False,
        dataset="humaneval",
        task_id=task_id,
        batch_number=1,
        attempt_number=0,
        model="gpt-4.1-mini",
        custom_id=f"run:humaneval:{task_id}:b1:a0",
        timestamp_utc="2026-02-27T00:00:00Z",
        raw_text=None,
        plans=[],
        warnings_by_plan=[],
        request_id=None,
        batch_id=None,
        usage=None,
        cost_estimated_request=0.01,
        error={"code": "rate_limit", "message": "retry later", "details": None},
        retryable=True,
    )


def test_failed_plan_capture_validation_only(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_a"
    task = _make_task()
    existing_failed_plan_ids: set[str] = set()
    existing_failed_task_keys: set[tuple[str, str]] = set()

    validation_result = _make_validation_failure()
    api_result = _make_api_failure()

    _write_failed_plan_artifacts(
        run_id="run_a",
        run_dir=run_dir,
        task=task,
        result=validation_result,
        existing_failed_plan_ids=existing_failed_plan_ids,
        existing_failed_task_keys=existing_failed_task_keys,
    )
    _write_failed_plan_artifacts(
        run_id="run_a",
        run_dir=run_dir,
        task=task,
        result=api_result,
        existing_failed_plan_ids=existing_failed_plan_ids,
        existing_failed_task_keys=existing_failed_task_keys,
    )

    failed_plans_path = run_dir / "failed_plans" / "datasets" / "humaneval" / "plans.jsonl"
    rows = list(iter_jsonl(failed_plans_path))
    assert len(rows) == 1
    assert rows[0]["error"]["code"] == "validation_error"


def test_failed_plan_capture_every_attempt(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_b"
    task = _make_task()
    existing_failed_plan_ids: set[str] = set()
    existing_failed_task_keys: set[tuple[str, str]] = set()

    for attempt in (0, 1):
        _write_failed_plan_artifacts(
            run_id="run_b",
            run_dir=run_dir,
            task=task,
            result=_make_validation_failure(attempt_number=attempt),
            existing_failed_plan_ids=existing_failed_plan_ids,
            existing_failed_task_keys=existing_failed_task_keys,
        )

    failed_plans_path = run_dir / "failed_plans" / "datasets" / "humaneval" / "plans.jsonl"
    rows = list(iter_jsonl(failed_plans_path))
    assert len(rows) == 2
    assert {row["attempt_number"] for row in rows} == {0, 1}


def test_failed_tasks_association_dedup(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_c"
    task = _make_task()
    existing_failed_plan_ids: set[str] = set()
    existing_failed_task_keys: set[tuple[str, str]] = set()

    for attempt in (0, 1):
        _write_failed_plan_artifacts(
            run_id="run_c",
            run_dir=run_dir,
            task=task,
            result=_make_validation_failure(attempt_number=attempt),
            existing_failed_plan_ids=existing_failed_plan_ids,
            existing_failed_task_keys=existing_failed_task_keys,
        )

    failed_tasks_path = run_dir / "failed_plans" / "datasets" / "humaneval" / "tasks.jsonl"
    task_rows = list(iter_jsonl(failed_tasks_path))
    assert len(task_rows) == 1
    assert task_rows[0]["task_id"] == "HumanEval/0"


def test_failed_readable_export_generation(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_d"
    failed_dataset_dir = run_dir / "failed_plans" / "datasets" / "humaneval"
    failed_dataset_dir.mkdir(parents=True, exist_ok=True)

    task = _make_task().model_dump(mode="json")
    failed_plan: dict[str, Any] = {
        "schema_version": "1.0",
        "dataset": "humaneval",
        "task_id": "HumanEval/0",
        "run_id": "run_d",
        "failed_plan_id": "humaneval:HumanEval/0:run_d:b1:a0",
        "batch_number": 1,
        "attempt_number": 0,
        "model": "gpt-4.1-mini",
        "custom_id": "run_d:humaneval:HumanEval/0:b1:a0",
        "timestamp_utc": "2026-02-27T00:00:00Z",
        "error": {"code": "validation_error", "message": "invalid", "details": {"k": "v"}},
        "raw_response_text": '[{"oops":true}]',
        "parsed_response": [{"oops": True}],
        "request_id": "req_123",
        "batch_id": None,
        "extras": {},
    }

    (failed_dataset_dir / "tasks.jsonl").write_text(
        f"{json.dumps(task, ensure_ascii=False)}\n",
        encoding="utf-8",
        newline="\n",
    )
    (failed_dataset_dir / "plans.jsonl").write_text(
        f"{json.dumps(failed_plan, ensure_ascii=False)}\n",
        encoding="utf-8",
        newline="\n",
    )

    summary = export_failed_run_readable(run_dir=run_dir)
    assert summary["tasks_written"] == 1
    assert summary["failed_attempts_written"] == 1
    index_path = Path(summary["index_path"])
    assert index_path.exists()
    assert "Failed Validation Attempts" in index_path.read_text(encoding="utf-8")


def test_run_auto_readable_non_blocking(tmp_path: Path, monkeypatch: Any) -> None:
    from plan_dataset_builder import cli

    run_dir = tmp_path / "run_e"
    run_dir.mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}", encoding="utf-8", newline="\n")

    def _fake_execute_run(**_: Any) -> Path:
        return run_dir

    def _boom_export(**_: Any) -> dict[str, Any]:
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "execute_run", _fake_execute_run)
    monkeypatch.setattr(cli, "export_run_readable", _boom_export)
    monkeypatch.setattr(cli, "_has_failed_plan_artifacts", lambda _: False)

    runner = CliRunner()
    result = runner.invoke(app, ["run", "--config", str(config_path), "--run-id", "run_e"])
    combined_output = result.stdout + getattr(result, "stderr", "")
    assert result.exit_code == 0
    assert "Run complete:" in result.stdout
    assert "Warning: readable export failed: boom" in combined_output


def test_render_readable_includes_failed_when_present(tmp_path: Path, monkeypatch: Any) -> None:
    from plan_dataset_builder import cli

    run_dir = tmp_path / "run_f"
    run_dir.mkdir(parents=True, exist_ok=True)
    calls: dict[str, int] = {"normal": 0, "failed": 0}

    def _fake_normal_export(**_: Any) -> dict[str, Any]:
        calls["normal"] += 1
        return {
            "output_dir": str(run_dir / "readable"),
            "index_path": str(run_dir / "readable" / "index.md"),
            "tasks_written": 1,
            "plans_written": 1,
        }

    def _fake_failed_export(**_: Any) -> dict[str, Any]:
        calls["failed"] += 1
        return {
            "output_dir": str(run_dir / "failed_plans" / "readable"),
            "index_path": str(run_dir / "failed_plans" / "readable" / "index.md"),
            "tasks_written": 1,
            "failed_attempts_written": 2,
        }

    monkeypatch.setattr(cli, "export_run_readable", _fake_normal_export)
    monkeypatch.setattr(cli, "export_failed_run_readable", _fake_failed_export)
    monkeypatch.setattr(cli, "_has_failed_plan_artifacts", lambda _: True)

    runner = CliRunner()
    result = runner.invoke(app, ["render-readable", "--run-dir", str(run_dir)])
    assert result.exit_code == 0
    assert calls["normal"] == 1
    assert calls["failed"] == 1
    assert "Failed readable export written to:" in result.stdout
