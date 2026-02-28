from __future__ import annotations

from plan_dataset_builder.config import AppConfig
from plan_dataset_builder.constants import DATASET_SWEBENCH_VERIFIED, SWEBENCH_EXCLUDED_TASK_TEXT_KEYS
from plan_dataset_builder.datasets.base import DatasetLoadResult, DatasetLoader, build_task_record


class SWEBenchVerifiedLoader(DatasetLoader):
    dataset_name = DATASET_SWEBENCH_VERIFIED
    source = "hf://SWE-bench/SWE-bench_Verified@test"

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
        return DatasetLoadResult(
            dataset=self.dataset_name,
            source=self.source,
            tasks=tasks,
            extra_manifests=extra_manifests,
        )

