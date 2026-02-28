from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from plan_dataset_builder.config import AppConfig
from plan_dataset_builder.constants import BATCH_NUMBERS, PLANS_PER_BATCH, TOTAL_PLANS_PER_TASK
from plan_dataset_builder.ids import make_plan_id
from plan_dataset_builder.jsonl_io import iter_jsonl
from plan_dataset_builder.models import PlanRecord, TaskRecord
from plan_dataset_builder.plan_validation import (
    PlanValidationError,
    compute_unique_step_match,
    validate_plan_object,
)


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_run_dir(run_dir: Path) -> list[str]:
    errors: list[str] = []

    if not run_dir.exists():
        return [f"Run directory does not exist: {run_dir}"]

    config_path = run_dir / "config" / "run_config.json"
    if not config_path.exists():
        return [f"Missing config snapshot: {config_path}"]
    config = AppConfig.model_validate(_read_json(config_path))

    all_plan_ids: set[str] = set()
    all_task_ids_by_dataset: dict[str, set[str]] = {}
    task_counts_by_dataset: dict[str, dict[str, int]] = {}
    batch_counts_by_dataset: dict[str, dict[tuple[str, int], int]] = {}
    within_index_tracker: dict[str, dict[tuple[str, int], set[int]]] = {}

    datasets_dir = run_dir / "datasets"
    for dataset_dir in sorted(datasets_dir.glob("*")):
        if not dataset_dir.is_dir():
            continue
        dataset = dataset_dir.name
        tasks_path = dataset_dir / "tasks.jsonl"
        plans_path = dataset_dir / "plans.jsonl"

        task_ids: set[str] = set()
        for row in iter_jsonl(tasks_path):
            task = TaskRecord.model_validate(row)
            if task.task_id in task_ids:
                errors.append(f"Duplicate task_id in tasks.jsonl: {dataset}:{task.task_id}")
            task_ids.add(task.task_id)
        all_task_ids_by_dataset[dataset] = task_ids

        task_counts: dict[str, int] = defaultdict(int)
        batch_counts: dict[tuple[str, int], int] = defaultdict(int)
        within_seen: dict[tuple[str, int], set[int]] = defaultdict(set)

        for row in iter_jsonl(plans_path):
            row_for_model = dict(row)
            if row_for_model.get("unique_step_flag") not in {"pass", "fail"}:
                plan_payload = row_for_model.get("plan")
                if isinstance(plan_payload, dict):
                    row_for_model["unique_step_flag"] = (
                        "pass" if compute_unique_step_match(plan_payload) else "fail"
                    )
                else:
                    row_for_model["unique_step_flag"] = "fail"

            plan = PlanRecord.model_validate(row_for_model)
            expected_plan_id = make_plan_id(
                dataset=plan.dataset,
                task_id=plan.task_id,
                run_id=plan.run_id,
                batch_number=plan.batch_number,
                within_batch_index=plan.within_batch_index,
            )
            if plan.plan_id != expected_plan_id:
                errors.append(
                    f"Invalid plan_id format for {plan.dataset}:{plan.task_id}: "
                    f"expected {expected_plan_id}, got {plan.plan_id}"
                )
            if plan.plan_id in all_plan_ids:
                errors.append(f"Duplicate plan_id detected: {plan.plan_id}")
            all_plan_ids.add(plan.plan_id)

            if plan.task_id not in task_ids:
                errors.append(f"Plan references missing task: {dataset}:{plan.task_id}")

            allowed_labels = set(config.diversity.label_sets.get(dataset, []))
            try:
                validate_plan_object(
                    plan.plan,
                    allowed_labels=allowed_labels if allowed_labels else None,
                    schema_version=config.prompt.schema_version,
                    bounds=config.prompt.bounds,
                )
            except PlanValidationError as exc:
                errors.append(
                    f"Invalid plan payload for {dataset}:{plan.task_id}:{plan.plan_id}: {exc}"
                )

            task_counts[plan.task_id] += 1
            batch_counts[(plan.task_id, plan.batch_number)] += 1
            key = (plan.task_id, plan.batch_number)
            if plan.within_batch_index in within_seen[key]:
                errors.append(
                    f"Duplicate within_batch_index for {dataset}:{plan.task_id}:"
                    f"b{plan.batch_number}:p{plan.within_batch_index}"
                )
            within_seen[key].add(plan.within_batch_index)

        task_counts_by_dataset[dataset] = task_counts
        batch_counts_by_dataset[dataset] = batch_counts
        within_index_tracker[dataset] = within_seen

    manifests_dir = run_dir / "manifests"
    for dataset, task_ids in all_task_ids_by_dataset.items():
        complete_path = manifests_dir / f"{dataset}_complete_task_ids.json"
        incomplete_path = manifests_dir / f"{dataset}_incomplete_task_ids.json"
        if not complete_path.exists():
            errors.append(f"Missing complete manifest: {complete_path}")
            continue
        if not incomplete_path.exists():
            errors.append(f"Missing incomplete manifest: {incomplete_path}")
            continue

        complete_ids = set(_read_json(complete_path))
        incomplete_ids = set(_read_json(incomplete_path))

        if complete_ids & incomplete_ids:
            errors.append(f"Manifest overlap for {dataset}: complete and incomplete sets intersect")

        if complete_ids | incomplete_ids != task_ids:
            errors.append(f"Manifest coverage mismatch for {dataset}: complete+incomplete != all tasks")

        task_counts = task_counts_by_dataset.get(dataset, {})
        batch_counts = batch_counts_by_dataset.get(dataset, {})
        for task_id in complete_ids:
            if task_counts.get(task_id, 0) != TOTAL_PLANS_PER_TASK:
                errors.append(
                    f"Complete task {dataset}:{task_id} does not have exactly {TOTAL_PLANS_PER_TASK} plans"
                )
            for batch_number in BATCH_NUMBERS:
                if batch_counts.get((task_id, batch_number), 0) != PLANS_PER_BATCH:
                    errors.append(
                        "Complete task "
                        f"{dataset}:{task_id} missing full batch b{batch_number} "
                        f"(expected {PLANS_PER_BATCH} plans)"
                    )

    return errors
