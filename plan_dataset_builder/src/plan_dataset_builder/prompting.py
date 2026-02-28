from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from plan_dataset_builder.jsonl_io import sha256_bytes


TOKENS = (
    "{{dataset}}",
    "{{task_id}}",
    "{{task_text}}",
    "{{batch_number}}",
    "{{allowed_labels_json}}",
    "{{schema_version}}",
    "{{bounds_json}}",
)


def load_template(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def render_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for token in TOKENS:
        key = token[2:-2]
        if key not in values:
            raise ValueError(f"Missing prompt value for token {token}")
        rendered = rendered.replace(token, values[key])
    return rendered


def compute_prompt_version_hash(template_bytes: bytes, prompt_render_config: dict[str, Any]) -> str:
    blob = template_bytes + json.dumps(prompt_render_config, sort_keys=True).encode("utf-8")
    return sha256_bytes(blob)


def copy_template(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")

