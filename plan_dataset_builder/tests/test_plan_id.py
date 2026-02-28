from __future__ import annotations

from plan_dataset_builder.constants import BATCH_NUMBERS, PLANS_PER_BATCH, TOTAL_PLANS_PER_TASK
from plan_dataset_builder.ids import make_plan_id


def test_plan_id_format() -> None:
    plan_id = make_plan_id(
        dataset="humaneval",
        task_id="HumanEval/0",
        run_id="run-123",
        batch_number=2,
        within_batch_index=4,
    )
    assert plan_id == "humaneval:HumanEval/0:run-123:b2:p4"


def test_plan_id_uniqueness_across_batch_and_position() -> None:
    ids = {
        make_plan_id("humaneval", "HumanEval/0", "run-123", batch_number, within_batch_index)
        for batch_number in BATCH_NUMBERS
        for within_batch_index in range(1, PLANS_PER_BATCH + 1)
    }
    assert len(ids) == TOTAL_PLANS_PER_TASK
