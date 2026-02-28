from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from plan_dataset_builder.config import OpenAIConfig, PromptBoundsConfig
from plan_dataset_builder.constants import PLANS_PER_BATCH

TERMINAL_BATCH_STATUSES = {"completed", "failed", "cancelled", "expired"}


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    raise TypeError(f"Cannot convert value to dict: {type(value)!r}")


def build_group_json_schema(schema_version: str, bounds: PromptBoundsConfig) -> dict[str, Any]:
    return {
        # Responses API json_schema format requires an object schema at the root.
        "type": "object",
        "additionalProperties": False,
        "required": ["plans"],
        "properties": {
            "plans": {
                "type": "array",
                "minItems": PLANS_PER_BATCH,
                "maxItems": PLANS_PER_BATCH,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["schema_version", "strategy_label", "unique_step", "steps"],
                    "properties": {
                        "schema_version": {"type": "string", "const": schema_version},
                        "strategy_label": {"type": "string", "minLength": 1},
                        "unique_step": {"type": "string", "minLength": 1},
                        "steps": {
                            "type": "array",
                            "items": {"$ref": "#/$defs/step"},
                            "minItems": bounds.min_steps,
                        },
                    },
                },
            },
        },
        "$defs": {
            "step": {
                "anyOf": [
                    {"$ref": "#/$defs/step_base"},
                    {"$ref": "#/$defs/step_with_checks"},
                    {"$ref": "#/$defs/step_with_substeps"},
                    {"$ref": "#/$defs/step_with_checks_and_substeps"},
                ]
            },
            "step_base": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "action", "rationale"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "action": {"type": "string", "minLength": 1},
                    "rationale": {"type": "string", "minLength": 1},
                },
            },
            "step_with_checks": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "action", "rationale", "checks"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "action": {"type": "string", "minLength": 1},
                    "rationale": {"type": "string", "minLength": 1},
                    "checks": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "minItems": 1,
                    },
                },
            },
            "step_with_substeps": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "action", "rationale", "substeps"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "action": {"type": "string", "minLength": 1},
                    "rationale": {"type": "string", "minLength": 1},
                    "substeps": {
                        "type": "array",
                        "items": {"$ref": "#/$defs/step"},
                        "minItems": 1,
                    },
                },
            },
            "step_with_checks_and_substeps": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "action", "rationale", "checks", "substeps"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "action": {"type": "string", "minLength": 1},
                    "rationale": {"type": "string", "minLength": 1},
                    "checks": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "minItems": 1,
                    },
                    "substeps": {
                        "type": "array",
                        "items": {"$ref": "#/$defs/step"},
                        "minItems": 1,
                    },
                },
            }
        },
    }


class OpenAIAdapter:
    def __init__(
        self,
        *,
        api_key: str,
        openai_config: OpenAIConfig,
        schema_version: str,
        bounds: PromptBoundsConfig,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - dependency issue
            raise RuntimeError("openai package is required for generation") from exc

        self.client = OpenAI(api_key=api_key)
        self.cfg = openai_config
        self.schema_version = schema_version
        self.bounds = bounds
        self.group_schema = build_group_json_schema(schema_version=schema_version, bounds=bounds)

    def build_request_body(self, prompt: str, *, model: str | None = None) -> dict[str, Any]:
        resolved_model = model or self.cfg.model
        body: dict[str, Any] = {
            "model": resolved_model,
            "input": prompt,
            "max_output_tokens": self.cfg.max_output_tokens,
        }

        body["text"] = {
            "format": {
                "type": "json_schema",
                "name": "plan_group",
                "schema": self.group_schema,
                "strict": True,
            }
        }

        if self.cfg.prompt_cache_enabled:
            prefix = self.cfg.prompt_cache_key_prefix or "plan-dataset-builder"
            body["prompt_cache_key"] = f"{prefix}:{resolved_model}:plan_group_v1"
            if self.cfg.prompt_cache_retention:
                body["prompt_cache_retention"] = self.cfg.prompt_cache_retention
        return body

    def create_response(self, prompt: str, *, model: str | None = None) -> tuple[dict[str, Any], str | None]:
        body = self.build_request_body(prompt, model=model)
        response = self.client.responses.create(**body)
        request_id = getattr(response, "_request_id", None) or getattr(response, "request_id", None)
        return _to_dict(response), request_id

    def submit_batch(self, input_jsonl_path: Path) -> dict[str, Any]:
        with input_jsonl_path.open("rb") as handle:
            uploaded = self.client.files.create(file=handle, purpose="batch")
        batch = self.client.batches.create(
            input_file_id=uploaded.id,
            endpoint="/v1/responses",
            completion_window="24h",
        )
        return _to_dict(batch)

    def wait_for_batch(self, batch_id: str, poll_interval_seconds: int = 10) -> dict[str, Any]:
        while True:
            batch = _to_dict(self.client.batches.retrieve(batch_id))
            status = batch.get("status")
            if status in TERMINAL_BATCH_STATUSES:
                return batch
            time.sleep(poll_interval_seconds)

    def download_file_text(self, file_id: str) -> str:
        content = self.client.files.content(file_id)
        if hasattr(content, "text"):
            return content.text  # type: ignore[no-any-return]
        if isinstance(content, (bytes, bytearray)):
            return content.decode("utf-8")
        if hasattr(content, "read"):
            raw = content.read()
            if isinstance(raw, (bytes, bytearray)):
                return raw.decode("utf-8")
            return str(raw)
        return str(content)


def extract_response_text(response_body: dict[str, Any]) -> str:
    output_text = response_body.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = response_body.get("output")
    fragments: list[str] = []
    if isinstance(output, list):
        for message in output:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    text = part.get("text")
                    if isinstance(text, str):
                        fragments.append(text)
                    elif isinstance(text, dict) and isinstance(text.get("value"), str):
                        fragments.append(text["value"])
    joined = "".join(fragments).strip()
    if joined:
        return joined
    raise ValueError("Could not extract output text from Responses API payload")


def extract_usage(response_body: dict[str, Any]) -> dict[str, int] | None:
    usage = response_body.get("usage")
    if not isinstance(usage, dict):
        return None
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens) or 0)
    payload = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }
    input_tokens_details = usage.get("input_tokens_details")
    if isinstance(input_tokens_details, dict):
        cached_tokens = input_tokens_details.get("cached_tokens")
        if isinstance(cached_tokens, int):
            payload["cached_input_tokens"] = cached_tokens

    output_tokens_details = usage.get("output_tokens_details")
    if isinstance(output_tokens_details, dict):
        reasoning_tokens = output_tokens_details.get("reasoning_tokens")
        if isinstance(reasoning_tokens, int):
            payload["reasoning_tokens"] = reasoning_tokens

    for key, value in usage.items():
        if key not in payload and isinstance(value, int):
            payload[key] = value
    return payload


def parse_batch_output_lines(content: str) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parsed = json.loads(line)
        custom_id = parsed.get("custom_id")
        if isinstance(custom_id, str):
            output[custom_id] = parsed
    return output


def normalize_plan_group_text(raw_text: str) -> str:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return raw_text
    if isinstance(parsed, list):
        return json.dumps(parsed, ensure_ascii=False)
    if isinstance(parsed, dict):
        plans = parsed.get("plans")
        if isinstance(plans, list):
            return json.dumps(plans, ensure_ascii=False)
    return raw_text
