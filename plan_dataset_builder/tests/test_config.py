from __future__ import annotations

import pytest

from plan_dataset_builder.config import AppConfig


def test_multi_model_requires_all_three_batch_models() -> None:
    with pytest.raises(ValueError):
        AppConfig.model_validate(
            {
                "openai": {
                    "model": "gpt-4.1-mini",
                    "multi_model": True,
                    "model1": "gpt-4.1-mini",
                    "model2": "gpt-4.1",
                }
            }
        )


def test_model_map_by_batch_uses_single_model_when_multi_model_disabled() -> None:
    cfg = AppConfig.model_validate({"openai": {"model": "gpt-4.1-mini", "multi_model": False}})
    assert cfg.openai.model_map_by_batch() == {
        1: "gpt-4.1-mini",
        2: "gpt-4.1-mini",
        3: "gpt-4.1-mini",
    }


def test_model_map_by_batch_uses_per_batch_models_when_multi_model_enabled() -> None:
    cfg = AppConfig.model_validate(
        {
            "openai": {
                "model": "unused-default",
                "multi_model": True,
                "model1": "gpt-4.1-mini",
                "model2": "gpt-4.1",
                "model3": "gpt-4o-mini",
            }
        }
    )
    assert cfg.openai.model_map_by_batch() == {
        1: "gpt-4.1-mini",
        2: "gpt-4.1",
        3: "gpt-4o-mini",
    }


def test_multi_model_hyphenated_key_is_accepted() -> None:
    cfg = AppConfig.model_validate(
        {
            "openai": {
                "model": "unused-default",
                "multi-model": True,
                "model1": "gpt-4.1-mini",
                "model2": "gpt-4.1",
                "model3": "gpt-4o-mini",
            }
        }
    )
    assert cfg.openai.multi_model is True


def test_config_prompt_cache_fields_valid() -> None:
    cfg = AppConfig.model_validate(
        {
            "openai": {
                "prompt_cache_enabled": True,
                "prompt_cache_key_prefix": "plan-dataset-builder-main",
                "prompt_cache_retention": "24h",
            }
        }
    )
    assert cfg.openai.prompt_cache_enabled is True
    assert cfg.openai.prompt_cache_key_prefix == "plan-dataset-builder-main"
    assert cfg.openai.prompt_cache_retention == "24h"


def test_config_prompt_cache_retention_in_memory_valid() -> None:
    cfg = AppConfig.model_validate({"openai": {"prompt_cache_retention": "in_memory"}})
    assert cfg.openai.prompt_cache_retention == "in_memory"


def test_config_prompt_cache_retention_invalid() -> None:
    with pytest.raises(ValueError):
        AppConfig.model_validate({"openai": {"prompt_cache_retention": "7d"}})


def test_dataset_allowlist_paths_accept_none_or_non_empty() -> None:
    cfg = AppConfig.model_validate(
        {
            "datasets": {
                "humaneval": {"enabled": False},
                "swebench_verified": {
                    "enabled": True,
                    "task_id_allowlist_path": None,
                    "task_id_allowlist_strict": True,
                },
                "refactorbench_py": {
                    "enabled": True,
                    "local_jsonl_path": "data/refactorbench_py.jsonl",
                    "task_id_allowlist_path": "manifests/ref_allowlist.json",
                    "task_id_allowlist_strict": False,
                },
            }
        }
    )
    assert cfg.datasets.swebench_verified.task_id_allowlist_path is None
    assert cfg.datasets.refactorbench_py.task_id_allowlist_path == "manifests/ref_allowlist.json"
    assert cfg.datasets.refactorbench_py.task_id_allowlist_strict is False


def test_dataset_allowlist_paths_reject_empty_string() -> None:
    with pytest.raises(ValueError):
        AppConfig.model_validate(
            {
                "datasets": {
                    "humaneval": {"enabled": False},
                    "swebench_verified": {"enabled": True, "task_id_allowlist_path": "   "},
                    "refactorbench_py": {"enabled": False},
                }
            }
        )
