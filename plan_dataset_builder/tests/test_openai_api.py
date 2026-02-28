from __future__ import annotations

from plan_dataset_builder.config import AppConfig
from plan_dataset_builder.openai_api import OpenAIAdapter, extract_usage


def _make_adapter_like(cfg: AppConfig) -> OpenAIAdapter:
    adapter = OpenAIAdapter.__new__(OpenAIAdapter)
    adapter.cfg = cfg.openai
    adapter.group_schema = {"type": "object"}
    return adapter


def test_build_request_body_includes_cache_fields_when_enabled() -> None:
    cfg = AppConfig.model_validate(
        {
            "openai": {
                "model": "gpt-4.1",
                "prompt_cache_enabled": True,
                "prompt_cache_key_prefix": "plan-dataset-builder-main",
                "prompt_cache_retention": "24h",
            }
        }
    )
    adapter = _make_adapter_like(cfg)

    body = OpenAIAdapter.build_request_body(adapter, "prompt", model="gpt-4.1-mini")
    assert body["prompt_cache_key"] == "plan-dataset-builder-main:gpt-4.1-mini:plan_group_v1"
    assert body["prompt_cache_retention"] == "24h"


def test_build_request_body_omits_cache_fields_when_disabled() -> None:
    cfg = AppConfig.model_validate({"openai": {"model": "gpt-4.1", "prompt_cache_enabled": False}})
    adapter = _make_adapter_like(cfg)

    body = OpenAIAdapter.build_request_body(adapter, "prompt")
    assert "prompt_cache_key" not in body
    assert "prompt_cache_retention" not in body


def test_extract_usage_includes_cached_and_reasoning_tokens() -> None:
    usage = extract_usage(
        {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
                "input_tokens_details": {"cached_tokens": 25},
                "output_tokens_details": {"reasoning_tokens": 30},
            }
        }
    )
    assert usage is not None
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 50
    assert usage["total_tokens"] == 150
    assert usage["cached_input_tokens"] == 25
    assert usage["reasoning_tokens"] == 30
