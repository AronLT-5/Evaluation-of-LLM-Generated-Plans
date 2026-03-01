from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from plan_dataset_builder.config import AppConfig, load_config
from plan_dataset_builder.constants import (
    DATASET_REFACTORBENCH_PY,
    DATASET_SWEBENCH_VERIFIED,
    TOTAL_PLANS_PER_TASK,
)
from plan_dataset_builder.datasets import get_enabled_loaders
from plan_dataset_builder.jsonl_io import iter_jsonl, sha256_file, write_json, write_jsonl
from plan_dataset_builder.run_validation import validate_run_dir

TARGET_DATASETS = (DATASET_SWEBENCH_VERIFIED, DATASET_REFACTORBENCH_PY)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve_path(base_dir: Path, raw_path: Path) -> Path:
    if raw_path.is_absolute():
        return raw_path
    return (base_dir / raw_path).resolve()


def _load_task_ids_by_dataset(config: AppConfig, config_dir: Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    task_ids_by_dataset: dict[str, list[str]] = {}
    dataset_sources: dict[str, str] = {}
    loaders = get_enabled_loaders(config=config, config_dir=config_dir)
    for loader in loaders:
        dataset = loader.dataset_name
        if dataset not in TARGET_DATASETS:
            continue
        loaded = loader.load(config)
        task_ids_by_dataset[dataset] = [task.task_id for task in loaded.tasks]
        dataset_sources[dataset] = loaded.source
    return task_ids_by_dataset, dataset_sources


def prepare_sections(
    *,
    config_path: Path,
    section_size: int,
    sections: int,
    output_dir: Path,
    run_prefix: str,
) -> dict[str, Any]:
    if section_size <= 0:
        raise ValueError("section_size must be > 0")
    if sections <= 0:
        raise ValueError("sections must be > 0")
    if not run_prefix.strip():
        raise ValueError("run_prefix must be non-empty")

    config = load_config(config_path)
    if not config.datasets.swebench_verified.enabled:
        raise ValueError("prepare-sections requires datasets.swebench_verified.enabled=true")
    if not config.datasets.refactorbench_py.enabled:
        raise ValueError("prepare-sections requires datasets.refactorbench_py.enabled=true")

    output_dir_resolved = _resolve_path(config_path.parent, output_dir)
    if output_dir_resolved.exists() and any(output_dir_resolved.iterdir()):
        raise ValueError(f"Output directory must be empty or missing: {output_dir_resolved}")
    output_dir_resolved.mkdir(parents=True, exist_ok=True)

    task_ids_by_dataset, dataset_sources = _load_task_ids_by_dataset(config=config, config_dir=config_path.parent)
    expected_total = section_size * sections

    for dataset in TARGET_DATASETS:
        if dataset not in task_ids_by_dataset:
            raise ValueError(f"Required dataset was not loaded: {dataset}")
        found = len(task_ids_by_dataset[dataset])
        if found != expected_total:
            raise ValueError(
                f"{dataset} must provide exactly {expected_total} tasks for sectioning; found {found}"
            )

    sections_payload: list[dict[str, Any]] = []
    resolved_cfg = config.resolved_dict()

    for section_index in range(sections):
        section_no = section_index + 1
        start = section_index * section_size
        end = start + section_size
        section_dir = output_dir_resolved / f"section_{section_no:02d}"
        section_dir.mkdir(parents=True, exist_ok=True)

        swe_ids = task_ids_by_dataset[DATASET_SWEBENCH_VERIFIED][start:end]
        ref_ids = task_ids_by_dataset[DATASET_REFACTORBENCH_PY][start:end]

        swe_allowlist_path = section_dir / "swebench_verified_task_ids.json"
        ref_allowlist_path = section_dir / "refactorbench_py_task_ids.json"
        write_json(swe_allowlist_path, swe_ids)
        write_json(ref_allowlist_path, ref_ids)

        section_cfg = copy.deepcopy(resolved_cfg)
        section_cfg["run"]["run_id"] = None
        section_cfg["run"]["resume"] = False
        section_cfg["datasets"]["swebench_verified"]["task_id_allowlist_path"] = swe_allowlist_path.name
        section_cfg["datasets"]["swebench_verified"]["task_id_allowlist_strict"] = True
        section_cfg["datasets"]["refactorbench_py"]["task_id_allowlist_path"] = ref_allowlist_path.name
        section_cfg["datasets"]["refactorbench_py"]["task_id_allowlist_strict"] = True
        section_cfg_path = section_dir / "section_config.yaml"
        with section_cfg_path.open("w", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(section_cfg, handle, sort_keys=False, allow_unicode=True)

        sections_payload.append(
            {
                "section": section_no,
                "range_1_based": [start + 1, end],
                "suggested_run_id": f"{run_prefix}_s{section_no:02d}_v1",
                "section_config_path": str(section_cfg_path),
                "datasets": {
                    DATASET_SWEBENCH_VERIFIED: {
                        "task_count": len(swe_ids),
                        "allowlist_path": str(swe_allowlist_path),
                        "allowlist_sha256": sha256_file(swe_allowlist_path),
                    },
                    DATASET_REFACTORBENCH_PY: {
                        "task_count": len(ref_ids),
                        "allowlist_path": str(ref_allowlist_path),
                        "allowlist_sha256": sha256_file(ref_allowlist_path),
                    },
                },
            }
        )

    manifest_path = output_dir_resolved / "sections_manifest.json"
    manifest_payload = {
        "created_at_utc": _utc_now(),
        "source_config_path": str(config_path.resolve()),
        "source_config_sha256": sha256_file(config_path.resolve()),
        "section_size": section_size,
        "sections": sections,
        "run_prefix": run_prefix,
        "expected_total_per_dataset": expected_total,
        "dataset_sources": dataset_sources,
        "datasets": {
            DATASET_SWEBENCH_VERIFIED: {
                "task_count": len(task_ids_by_dataset[DATASET_SWEBENCH_VERIFIED]),
                "task_ids": task_ids_by_dataset[DATASET_SWEBENCH_VERIFIED],
            },
            DATASET_REFACTORBENCH_PY: {
                "task_count": len(task_ids_by_dataset[DATASET_REFACTORBENCH_PY]),
                "task_ids": task_ids_by_dataset[DATASET_REFACTORBENCH_PY],
            },
        },
        "sections_payload": sections_payload,
    }
    write_json(manifest_path, manifest_payload)
    return {
        "output_dir": str(output_dir_resolved),
        "sections_manifest_path": str(manifest_path),
        "sections": sections_payload,
    }


def _parse_section_key(value: str) -> int:
    value = value.strip().lower()
    if not value.startswith("s"):
        raise ValueError(f"Invalid section key '{value}'. Expected s1..s4 format.")
    idx_text = value[1:]
    if not idx_text.isdigit():
        raise ValueError(f"Invalid section key '{value}'. Expected s1..s4 format.")
    return int(idx_text)


def _load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    return [row for row in iter_jsonl(path)]


def merge_sections(
    *,
    section_runs: dict[str, Path],
    output_run_id: str,
    output_root: Path = Path("runs"),
    expected_sections: int = 4,
    expected_section_size: int = 25,
) -> dict[str, Any]:
    if not output_run_id.strip():
        raise ValueError("output_run_id must be non-empty")
    if len(section_runs) != expected_sections:
        raise ValueError(f"Expected {expected_sections} section runs, got {len(section_runs)}")

    normalized_sections: dict[int, Path] = {}
    for key, run_path in section_runs.items():
        section_idx = _parse_section_key(key)
        if section_idx in normalized_sections:
            raise ValueError(f"Duplicate section key provided: s{section_idx}")
        normalized_sections[section_idx] = run_path.resolve()

    expected_keys = set(range(1, expected_sections + 1))
    if set(normalized_sections.keys()) != expected_keys:
        raise ValueError(
            f"Section keys must be exactly s1..s{expected_sections}; got "
            f"{sorted(normalized_sections.keys())}"
        )

    output_run_dir = output_root / output_run_id
    if output_run_dir.exists() and any(output_run_dir.iterdir()):
        raise ValueError(f"Output run directory exists and is non-empty: {output_run_dir}")
    output_run_dir.mkdir(parents=True, exist_ok=True)

    merged_tasks: dict[str, list[dict[str, Any]]] = {dataset: [] for dataset in TARGET_DATASETS}
    merged_plans: dict[str, list[dict[str, Any]]] = {dataset: [] for dataset in TARGET_DATASETS}
    seen_task_ids_by_dataset: dict[str, set[str]] = {dataset: set() for dataset in TARGET_DATASETS}
    section_info: list[dict[str, Any]] = []

    for section_idx in sorted(normalized_sections):
        run_dir = normalized_sections[section_idx]
        errors = validate_run_dir(run_dir)
        if errors:
            joined = "; ".join(errors[:5])
            raise ValueError(f"Section s{section_idx} failed validate-run checks: {joined}")

        per_dataset_counts: dict[str, int] = {}
        for dataset in TARGET_DATASETS:
            tasks_path = run_dir / "datasets" / dataset / "tasks.jsonl"
            plans_path = run_dir / "datasets" / dataset / "plans.jsonl"
            if not tasks_path.exists() or not plans_path.exists():
                raise FileNotFoundError(
                    f"Missing dataset artifacts for section s{section_idx}, dataset {dataset}"
                )
            task_rows = _load_jsonl_rows(tasks_path)
            plan_rows = _load_jsonl_rows(plans_path)

            if len(task_rows) != expected_section_size:
                raise ValueError(
                    f"Section s{section_idx}, dataset {dataset} must contain "
                    f"{expected_section_size} tasks, found {len(task_rows)}"
                )

            overlap = [row["task_id"] for row in task_rows if row["task_id"] in seen_task_ids_by_dataset[dataset]]
            if overlap:
                raise ValueError(
                    f"Section overlap detected for dataset {dataset} in section s{section_idx}: {overlap}"
                )

            for row in task_rows:
                seen_task_ids_by_dataset[dataset].add(row["task_id"])

            merged_tasks[dataset].extend(task_rows)
            merged_plans[dataset].extend(plan_rows)
            per_dataset_counts[dataset] = len(task_rows)

        section_info.append(
            {
                "section": section_idx,
                "run_dir": str(run_dir),
                "run_config_path": str(run_dir / "config" / "run_config.json"),
                "runs_jsonl_path": str(run_dir / "runs.jsonl"),
                "task_counts": per_dataset_counts,
            }
        )

    manifests_dir = output_run_dir / "manifests"
    datasets_dir = output_run_dir / "datasets"
    merge_counts: dict[str, dict[str, int]] = {}

    for dataset in TARGET_DATASETS:
        dataset_dir = datasets_dir / dataset
        dataset_dir.mkdir(parents=True, exist_ok=True)
        tasks_sorted = sorted(merged_tasks[dataset], key=lambda row: str(row["task_id"]))
        plans_sorted = sorted(
            merged_plans[dataset],
            key=lambda row: (
                str(row.get("task_id", "")),
                int(row.get("batch_number", 0)),
                int(row.get("within_batch_index", 0)),
                str(row.get("plan_id", "")),
            ),
        )
        write_jsonl(dataset_dir / "tasks.jsonl", tasks_sorted)
        write_jsonl(dataset_dir / "plans.jsonl", plans_sorted)

        task_ids = [str(row["task_id"]) for row in tasks_sorted]
        plan_count_by_task: dict[str, int] = {}
        for row in plans_sorted:
            task_id = str(row["task_id"])
            plan_count_by_task[task_id] = plan_count_by_task.get(task_id, 0) + 1

        complete_ids = sorted(
            task_id for task_id in task_ids if plan_count_by_task.get(task_id, 0) == TOTAL_PLANS_PER_TASK
        )
        incomplete_ids = sorted(
            task_id for task_id in task_ids if plan_count_by_task.get(task_id, 0) != TOTAL_PLANS_PER_TASK
        )

        write_json(manifests_dir / f"{dataset}_task_ids.json", task_ids)
        write_json(manifests_dir / f"{dataset}_complete_task_ids.json", complete_ids)
        write_json(manifests_dir / f"{dataset}_incomplete_task_ids.json", incomplete_ids)

        merge_counts[dataset] = {
            "tasks": len(task_ids),
            "plans": len(plans_sorted),
            "complete_tasks": len(complete_ids),
            "incomplete_tasks": len(incomplete_ids),
        }

    merge_info_path = output_run_dir / "merge_info.json"
    merge_info = {
        "created_at_utc": _utc_now(),
        "output_run_id": output_run_id,
        "output_run_dir": str(output_run_dir.resolve()),
        "expected_sections": expected_sections,
        "expected_section_size": expected_section_size,
        "source_sections": section_info,
        "counts": merge_counts,
        "files": {
            "datasets": {
                dataset: {
                    "tasks_jsonl": str((datasets_dir / dataset / "tasks.jsonl").resolve()),
                    "plans_jsonl": str((datasets_dir / dataset / "plans.jsonl").resolve()),
                }
                for dataset in TARGET_DATASETS
            },
            "manifests_dir": str(manifests_dir.resolve()),
        },
    }
    write_json(merge_info_path, merge_info)
    return {
        "output_run_dir": str(output_run_dir.resolve()),
        "merge_info_path": str(merge_info_path.resolve()),
        "counts": merge_counts,
    }
