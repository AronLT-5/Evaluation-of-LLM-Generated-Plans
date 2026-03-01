from __future__ import annotations

import json
from pathlib import Path

from plan_dataset_builder.config import AppConfig
from plan_dataset_builder.constants import DATASET_SWEBENCH_VERIFIED, SWEBENCH_EXCLUDED_TASK_TEXT_KEYS
from plan_dataset_builder.datasets.base import DatasetLoadResult, DatasetLoader, build_task_record


class SWEBenchVerifiedLoader(DatasetLoader):
    dataset_name = DATASET_SWEBENCH_VERIFIED
    source = "hf://SWE-bench/SWE-bench_Verified@test"

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir

    def load(self, config: AppConfig) -> DatasetLoadResult:
        try:
            from datasets import load_dataset
        except ImportError as exc:  # pragma: no cover - dependency issue
            raise RuntimeError("datasets package is required for SWE-bench Verified loading") from exc

        hf_ds = load_dataset("SWE-bench/SWE-bench_Verified", split="test")
        rows = [dict(row) for row in hf_ds]
        rows.sort(key=lambda item: str(item.get("instance_id", "")))

        first100 = [str(row["instance_id"]) for row in rows[:100]]
        max_tasks = config.datasets.swebench_verified.max_tasks
        if max_tasks is not None:
            rows = rows[:max_tasks]

        selected_ids = [str(row["instance_id"]) for row in rows]
        allowlist = self._load_allowlist(config)
        if allowlist is not None:
            allowlist_set = set(allowlist)
            rows = [row for row in rows if str(row["instance_id"]) in allowlist_set]
            selected_ids = [str(row["instance_id"]) for row in rows]
            if config.datasets.swebench_verified.task_id_allowlist_strict:
                selected_set = set(selected_ids)
                missing = [task_id for task_id in allowlist if task_id not in selected_set]
                if missing:
                    raise ValueError(
                        "SWE-bench allowlist contains IDs missing from filtered dataset rows: "
                        f"{missing}"
                    )

        tasks = [
            build_task_record(
                dataset=self.dataset_name,
                source=self.source,
                task_id=str(row["instance_id"]),
                primary_key="problem_statement",
                raw_row=row,
                excluded_task_text_keys=set(SWEBENCH_EXCLUDED_TASK_TEXT_KEYS),
                max_task_text_chars=config.task_text.max_task_text_chars,
                max_field_chars=config.task_text.max_field_chars,
                include_primary_in_context_fields=config.task_text.include_primary_in_context_fields,
            )
            for row in rows
        ]
        extra_manifests = {}
        if config.datasets.swebench_verified.write_first100_manifest:
            extra_manifests["swebench_verified_first100_instance_ids.json"] = first100
        if allowlist is not None:
            extra_manifests["swebench_verified_selected_task_ids.json"] = selected_ids
        return DatasetLoadResult(
            dataset=self.dataset_name,
            source=self.source,
            tasks=tasks,
            extra_manifests=extra_manifests,
        )

    def _load_allowlist(self, config: AppConfig) -> list[str] | None:
        allowlist_path_raw = config.datasets.swebench_verified.task_id_allowlist_path
        if not allowlist_path_raw:
            return None
        allowlist_path = Path(allowlist_path_raw)
        if not allowlist_path.is_absolute():
            allowlist_path = (self.config_dir / allowlist_path).resolve()
        if not allowlist_path.exists():
            raise FileNotFoundError(f"SWE-bench allowlist file not found: {allowlist_path}")

        payload = json.loads(allowlist_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"SWE-bench allowlist must be a JSON array: {allowlist_path}")
        output: list[str] = []
        for index, item in enumerate(payload, start=1):
            if not isinstance(item, str) or not item.strip():
                raise ValueError(
                    f"SWE-bench allowlist entry at index {index} must be a non-empty string"
                )
            output.append(item)
        return output
