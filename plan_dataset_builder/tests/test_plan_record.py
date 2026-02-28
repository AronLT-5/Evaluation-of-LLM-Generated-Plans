from __future__ import annotations

import pytest

from plan_dataset_builder.models import PlanRecord, StepSchema


def test_plan_record_serialization_includes_unique_step_flag() -> None:
    record = PlanRecord(
        schema_version="1.0",
        dataset="humaneval",
        task_id="HumanEval/0",
        run_id="run-test",
        plan_id="humaneval:HumanEval/0:run-test:b1:p1",
        batch_number=1,
        within_batch_index=1,
        strategy_label="Spec-First",
        unique_step="Inspect task statement",
        plan={
            "schema_version": "1.0",
            "strategy_label": "Spec-First",
            "unique_step": "Inspect task statement",
            "steps": [
                {"id": "1", "action": "Inspect task statement", "rationale": "Understand the task"}
            ],
        },
        plan_raw="[{}]",
        gen={},
        extras={},
        unique_step_flag="pass",
    )
    dumped = record.model_dump(mode="json")
    assert dumped["unique_step_flag"] == "pass"


def test_step_schema_rejects_empty_optional_arrays() -> None:
    with pytest.raises(ValueError):
        StepSchema.model_validate(
            {"id": "1", "action": "Inspect", "rationale": "Reason", "checks": []}
        )
    with pytest.raises(ValueError):
        StepSchema.model_validate(
            {"id": "1", "action": "Inspect", "rationale": "Reason", "substeps": []}
        )
