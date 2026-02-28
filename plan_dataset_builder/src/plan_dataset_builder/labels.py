from __future__ import annotations

import hashlib
import re

from plan_dataset_builder.constants import BATCH_NUMBERS, PLANS_PER_BATCH, TOTAL_PLANS_PER_TASK


def rotate_labels(task_id: str, labels: list[str]) -> list[str]:
    if len(labels) != TOTAL_PLANS_PER_TASK:
        raise ValueError(f"Expected {TOTAL_PLANS_PER_TASK} labels, found {len(labels)}")
    offset = int(hashlib.sha256(task_id.encode("utf-8")).hexdigest(), 16) % TOTAL_PLANS_PER_TASK
    return labels[offset:] + labels[:offset]


def labels_by_batch(task_id: str, labels: list[str]) -> dict[int, list[str]]:
    rotated = rotate_labels(task_id, labels)
    return {
        batch_number: rotated[index * PLANS_PER_BATCH : (index + 1) * PLANS_PER_BATCH]
        for index, batch_number in enumerate(BATCH_NUMBERS)
    }


def normalize_unique_step(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())
