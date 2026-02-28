from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from plan_dataset_builder.config import AppConfig
from plan_dataset_builder.models import TaskRecord
from plan_dataset_builder.task_text import build_task_text


@dataclass
class DatasetLoadResult:
    dataset: str
    source: str
    tasks: list[TaskRecord]
    extra_manifests: dict[str, Any] = field(default_factory=dict)


class DatasetLoader(ABC):
    dataset_name: str
    source: str

    @abstractmethod
    def load(self, config: AppConfig) -> DatasetLoadResult:
        raise NotImplementedError


def to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        return str(value)


def build_task_record(
    *,
    dataset: str,
    source: str,
    task_id: str,
    primary_key: str,
    raw_row: dict[str, Any],
    excluded_task_text_keys: set[str],
    max_task_text_chars: int,
    max_field_chars: int,
    include_primary_in_context_fields: bool,
) -> TaskRecord:
    row = {str(k): to_jsonable(v) for k, v in raw_row.items()}
    built = build_task_text(
        dataset=dataset,
        task_id=task_id,
        primary_key=primary_key,
        row=row,
        excluded_keys=excluded_task_text_keys,
        max_task_text_chars=max_task_text_chars,
        max_field_chars=max_field_chars,
        include_primary_in_context_fields=include_primary_in_context_fields,
    )

    extras = dict(row)
    extras["__source__"] = source
    extras["__primary_field__"] = primary_key
    if built.truncation_info:
        extras["__truncation__"] = built.truncation_info

    return TaskRecord(
        schema_version="1.0",
        dataset=dataset,  # type: ignore[arg-type]
        task_id=task_id,
        source=source,
        task_text=built.task_text,
        context_keys_included=built.context_keys_included,
        context_keys_excluded=built.context_keys_excluded,
        extras=extras,
    )

