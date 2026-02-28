from __future__ import annotations

from plan_dataset_builder.constants import BATCH_NUMBERS, PLANS_PER_BATCH, TOTAL_PLANS_PER_TASK
from plan_dataset_builder.labels import labels_by_batch, rotate_labels


def test_label_rotation_is_deterministic_and_complete() -> None:
    labels = [f"L{i}" for i in range(TOTAL_PLANS_PER_TASK)]
    rotated_one = rotate_labels("task-123", labels)
    rotated_two = rotate_labels("task-123", labels)
    assert rotated_one == rotated_two
    assert len(rotated_one) == TOTAL_PLANS_PER_TASK
    assert set(rotated_one) == set(labels)


def test_labels_by_batch_partition_into_3x4_without_overlap() -> None:
    labels = [f"L{i}" for i in range(TOTAL_PLANS_PER_TASK)]
    batched = labels_by_batch("task-abc", labels)
    assert set(batched.keys()) == set(BATCH_NUMBERS)
    assert all(len(batched[batch]) == PLANS_PER_BATCH for batch in BATCH_NUMBERS)

    union = [label for batch in BATCH_NUMBERS for label in batched[batch]]
    assert len(union) == TOTAL_PLANS_PER_TASK
    assert len(set(union)) == TOTAL_PLANS_PER_TASK
