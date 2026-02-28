from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from plan_dataset_builder.constants import TRUNCATION_MARKER


@dataclass
class TaskTextBuildResult:
    task_text: str
    context_keys_included: list[str]
    context_keys_excluded: list[str]
    truncation_info: dict[str, Any]


def format_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def truncate_text(value: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0:
        return "", bool(value)
    if len(value) <= max_chars:
        return value, False
    left = max_chars // 2
    right = max_chars - left
    truncated = f"{value[:left]}{TRUNCATION_MARKER}{value[-right:]}"
    return truncated, True


def build_task_text(
    dataset: str,
    task_id: str,
    primary_key: str,
    row: dict[str, Any],
    excluded_keys: set[str],
    max_task_text_chars: int,
    max_field_chars: int,
    include_primary_in_context_fields: bool = False,
) -> TaskTextBuildResult:
    truncation_info: dict[str, Any] = {}

    primary_value = format_value(row.get(primary_key, ""))
    primary_value, was_primary_truncated = truncate_text(primary_value, max_field_chars)
    if was_primary_truncated:
        truncation_info[primary_key] = {
            "reason": "max_field_chars",
            "original_chars": len(format_value(row.get(primary_key, ""))),
            "kept_chars": len(primary_value),
        }

    context_keys_candidates = [
        key
        for key in row.keys()
        if key not in excluded_keys and (include_primary_in_context_fields or key != primary_key)
    ]
    context_keys_included = sorted(context_keys_candidates)
    context_keys_excluded = sorted(key for key in row.keys() if key in excluded_keys)

    context_lines: list[str] = []
    for key in context_keys_included:
        rendered = format_value(row[key])
        rendered, was_truncated = truncate_text(rendered, max_field_chars)
        if was_truncated:
            truncation_info[key] = {
                "reason": "max_field_chars",
                "original_chars": len(format_value(row[key])),
                "kept_chars": len(rendered),
            }
        context_lines.append(f"{key}:")
        context_lines.append(rendered)
        context_lines.append("")

    parts: list[str] = [
        f"[DATASET] {dataset}",
        f"[TASK_ID] {task_id}",
        "",
        "[PRIMARY_TASK]",
        primary_value,
        "",
        "[CONTEXT_FIELDS]",
        *context_lines,
    ]
    task_text = "\n".join(parts).rstrip()

    task_text, was_task_text_truncated = truncate_text(task_text, max_task_text_chars)
    if was_task_text_truncated:
        truncation_info["__task_text__"] = {
            "reason": "max_task_text_chars",
            "original_chars": len("\n".join(parts).rstrip()),
            "kept_chars": len(task_text),
        }

    return TaskTextBuildResult(
        task_text=task_text,
        context_keys_included=context_keys_included,
        context_keys_excluded=context_keys_excluded,
        truncation_info=truncation_info,
    )

