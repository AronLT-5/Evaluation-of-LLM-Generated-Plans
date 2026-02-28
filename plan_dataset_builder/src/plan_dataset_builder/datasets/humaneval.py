from __future__ import annotations

from plan_dataset_builder.config import AppConfig
from plan_dataset_builder.constants import DATASET_HUMANEVAL, HUMANEVAL_EXCLUDED_TASK_TEXT_KEYS
from plan_dataset_builder.datasets.base import DatasetLoadResult, DatasetLoader, build_task_record


class HumanEvalLoader(DatasetLoader):
    dataset_name = DATASET_HUMANEVAL
    source = "hf://openai/openai_humaneval@test"

    def load(self, config: AppConfig) -> DatasetLoadResult:
        try:
            from datasets import load_dataset
        except ImportError as exc:  # pragma: no cover - dependency issue
            raise RuntimeError("datasets package is required for HumanEval loading") from exc

        hf_ds = load_dataset("openai/openai_humaneval", split="test")
        rows = [dict(row) for row in hf_ds]
        rows.sort(key=lambda item: str(item.get("task_id", "")))
        rows = rows[: config.datasets.humaneval.max_tasks]

        tasks = [
            build_task_record(
                dataset=self.dataset_name,
                source=self.source,
                task_id=str(row["task_id"]),
                primary_key="prompt",
                raw_row=row,
                excluded_task_text_keys=set(HUMANEVAL_EXCLUDED_TASK_TEXT_KEYS),
                max_task_text_chars=config.task_text.max_task_text_chars,
                max_field_chars=config.task_text.max_field_chars,
                include_primary_in_context_fields=config.task_text.include_primary_in_context_fields,
            )
            for row in rows
        ]
        return DatasetLoadResult(dataset=self.dataset_name, source=self.source, tasks=tasks)

