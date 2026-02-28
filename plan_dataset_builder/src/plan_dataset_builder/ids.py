from __future__ import annotations


def make_plan_id(
    dataset: str,
    task_id: str,
    run_id: str,
    batch_number: int,
    within_batch_index: int,
) -> str:
    return f"{dataset}:{task_id}:{run_id}:b{batch_number}:p{within_batch_index}"

