from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from plan_dataset_builder.config import AppConfig
from plan_dataset_builder.constants import DATASET_REFACTORBENCH_PY, REFACTORBENCH_EXCLUDED_PATTERNS
from plan_dataset_builder.datasets.base import DatasetLoadResult, DatasetLoader, build_task_record

PRIMARY_FIELD_CANDIDATES = (
    "instruction",
    "prompt",
    "problem_statement",
    "task",
    "task_text",
    "description",
)


class RefactorBenchPyLoader(DatasetLoader):
    dataset_name = DATASET_REFACTORBENCH_PY

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir
        self.source = ""

    def load(self, config: AppConfig) -> DatasetLoadResult:
        local_path_raw = config.datasets.refactorbench_py.local_jsonl_path
        if not local_path_raw:
            raise ValueError("refactorbench_py.local_jsonl_path is required when refactorbench_py is enabled")

        local_path = Path(local_path_raw)
        if not local_path.is_absolute():
            local_path = (self.config_dir / local_path).resolve()
        self.source = str(local_path)

        rows = list(self._read_jsonl(local_path))
        rows.sort(key=lambda item: str(item["task_id"]))
        max_tasks = config.datasets.refactorbench_py.max_tasks
        if max_tasks is not None:
            rows = rows[:max_tasks]

        selected_ids = [str(row["task_id"]) for row in rows]
        allowlist = self._load_allowlist(config)
        if allowlist is not None:
            allowlist_set = set(allowlist)
            rows = [row for row in rows if str(row["task_id"]) in allowlist_set]
            selected_ids = [str(row["task_id"]) for row in rows]
            if config.datasets.refactorbench_py.task_id_allowlist_strict:
                selected_set = set(selected_ids)
                missing = [task_id for task_id in allowlist if task_id not in selected_set]
                if missing:
                    raise ValueError(
                        "RefactorBench allowlist contains IDs missing from filtered dataset rows: "
                        f"{missing}"
                    )

        tasks = []
        for row in rows:
            task_id = str(row["task_id"])
            excluded_keys = {key for key in row.keys() if self._is_excluded_key(key)}
            primary_key = self._choose_primary_field(row, excluded_keys)
            if primary_key is None:
                raise ValueError(f"Could not infer primary instruction field for task_id={task_id}")

            tasks.append(
                build_task_record(
                    dataset=self.dataset_name,
                    source=self.source,
                    task_id=task_id,
                    primary_key=primary_key,
                    raw_row=row,
                    excluded_task_text_keys=excluded_keys,
                    max_task_text_chars=config.task_text.max_task_text_chars,
                    max_field_chars=config.task_text.max_field_chars,
                    include_primary_in_context_fields=config.task_text.include_primary_in_context_fields,
                )
            )

        extra_manifests: dict[str, Any] = {}
        if allowlist is not None:
            extra_manifests["refactorbench_py_selected_task_ids.json"] = selected_ids
        return DatasetLoadResult(
            dataset=self.dataset_name,
            source=self.source,
            tasks=tasks,
            extra_manifests=extra_manifests,
        )

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            raise FileNotFoundError(f"RefactorBench JSONL not found: {path}")
        output: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                text = line.strip()
                if not text:
                    continue
                row = json.loads(text)
                if "task_id" not in row:
                    raise ValueError(f"Missing task_id at line {line_number} in {path}")
                output.append(dict(row))
        return output

    def _load_allowlist(self, config: AppConfig) -> list[str] | None:
        allowlist_path_raw = config.datasets.refactorbench_py.task_id_allowlist_path
        if not allowlist_path_raw:
            return None
        allowlist_path = Path(allowlist_path_raw)
        if not allowlist_path.is_absolute():
            allowlist_path = (self.config_dir / allowlist_path).resolve()
        if not allowlist_path.exists():
            raise FileNotFoundError(f"RefactorBench allowlist file not found: {allowlist_path}")

        payload = json.loads(allowlist_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"RefactorBench allowlist must be a JSON array: {allowlist_path}")
        output: list[str] = []
        for index, item in enumerate(payload, start=1):
            if not isinstance(item, str) or not item.strip():
                raise ValueError(
                    f"RefactorBench allowlist entry at index {index} must be a non-empty string"
                )
            output.append(item)
        return output

    @staticmethod
    def _is_excluded_key(key: str) -> bool:
        key_lower = key.lower()
        return any(pattern in key_lower for pattern in REFACTORBENCH_EXCLUDED_PATTERNS)

    @staticmethod
    def _choose_primary_field(row: dict[str, Any], excluded_keys: set[str]) -> str | None:
        for candidate in PRIMARY_FIELD_CANDIDATES:
            if candidate in row and candidate not in excluded_keys:
                value = row[candidate]
                if isinstance(value, str) and value.strip():
                    return candidate
                if value is not None:
                    return candidate
        for key in row.keys():
            if key == "task_id" or key in excluded_keys:
                continue
            return key
        return None
