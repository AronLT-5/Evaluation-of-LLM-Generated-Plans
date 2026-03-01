from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from plan_dataset_builder.config import AppConfig
from plan_dataset_builder.datasets.swebench_verified import SWEBenchVerifiedLoader


def _install_fake_datasets_module(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, object]]) -> None:
    def fake_load_dataset(_dataset_id: str, split: str) -> list[dict[str, object]]:
        assert split == "test"
        return rows

    monkeypatch.setitem(sys.modules, "datasets", SimpleNamespace(load_dataset=fake_load_dataset))


def test_swebench_allowlist_applied_and_manifest_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [
        {"instance_id": "repo__1", "problem_statement": "one", "patch": "p", "test_patch": "t"},
        {"instance_id": "repo__2", "problem_statement": "two", "patch": "p", "test_patch": "t"},
        {"instance_id": "repo__3", "problem_statement": "three", "patch": "p", "test_patch": "t"},
    ]
    _install_fake_datasets_module(monkeypatch, rows)
    allowlist_path = tmp_path / "allow.json"
    allowlist_path.write_text(json.dumps(["repo__1", "repo__3"]), encoding="utf-8")

    cfg = AppConfig.model_validate(
        {
            "datasets": {
                "humaneval": {"enabled": False},
                "swebench_verified": {
                    "enabled": True,
                    "max_tasks": None,
                    "task_id_allowlist_path": str(allowlist_path),
                    "task_id_allowlist_strict": True,
                    "write_first100_manifest": True,
                },
                "refactorbench_py": {"enabled": False},
            }
        }
    )

    loader = SWEBenchVerifiedLoader(config_dir=tmp_path)
    loaded = loader.load(cfg)
    task_ids = [task.task_id for task in loaded.tasks]

    assert task_ids == ["repo__1", "repo__3"]
    assert loaded.extra_manifests["swebench_verified_selected_task_ids.json"] == ["repo__1", "repo__3"]
    assert "swebench_verified_first100_instance_ids.json" in loaded.extra_manifests


def test_swebench_allowlist_strict_missing_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [
        {"instance_id": "repo__1", "problem_statement": "one", "patch": "p", "test_patch": "t"},
        {"instance_id": "repo__2", "problem_statement": "two", "patch": "p", "test_patch": "t"},
    ]
    _install_fake_datasets_module(monkeypatch, rows)
    allowlist_path = tmp_path / "allow.json"
    allowlist_path.write_text(json.dumps(["repo__1", "repo__999"]), encoding="utf-8")

    cfg = AppConfig.model_validate(
        {
            "datasets": {
                "humaneval": {"enabled": False},
                "swebench_verified": {
                    "enabled": True,
                    "max_tasks": None,
                    "task_id_allowlist_path": str(allowlist_path),
                    "task_id_allowlist_strict": True,
                },
                "refactorbench_py": {"enabled": False},
            }
        }
    )

    loader = SWEBenchVerifiedLoader(config_dir=tmp_path)
    with pytest.raises(ValueError, match="allowlist contains IDs missing"):
        loader.load(cfg)
