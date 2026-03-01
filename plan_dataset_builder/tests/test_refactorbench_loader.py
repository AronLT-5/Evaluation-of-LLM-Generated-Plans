from __future__ import annotations

import json
from pathlib import Path
import pytest

from plan_dataset_builder.config import AppConfig
from plan_dataset_builder.datasets.refactorbench_py import RefactorBenchPyLoader


def test_refactorbench_max_tasks_applied(tmp_path: Path) -> None:
    input_path = tmp_path / "refactorbench_sample.jsonl"
    rows = [
        {"task_id": "rb_002", "instruction": "second"},
        {"task_id": "rb_001", "instruction": "first"},
        {"task_id": "rb_003", "instruction": "third"},
    ]
    with input_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")

    cfg = AppConfig.model_validate(
        {
            "datasets": {
                "humaneval": {"enabled": False},
                "swebench_verified": {"enabled": False},
                "refactorbench_py": {
                    "enabled": True,
                    "local_jsonl_path": str(input_path),
                    "max_tasks": 2,
                },
            }
        }
    )

    loader = RefactorBenchPyLoader(config_dir=tmp_path)
    loaded = loader.load(cfg)
    task_ids = [task.task_id for task in loaded.tasks]

    assert len(task_ids) == 2
    assert task_ids == ["rb_001", "rb_002"]


def test_refactorbench_allowlist_applied_with_manifest(tmp_path: Path) -> None:
    input_path = tmp_path / "refactorbench_sample.jsonl"
    allowlist_path = tmp_path / "allowlist.json"
    rows = [
        {"task_id": "rb_003", "instruction": "third"},
        {"task_id": "rb_001", "instruction": "first"},
        {"task_id": "rb_002", "instruction": "second"},
    ]
    with input_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")
    allowlist_path.write_text(json.dumps(["rb_001", "rb_003"]), encoding="utf-8")

    cfg = AppConfig.model_validate(
        {
            "datasets": {
                "humaneval": {"enabled": False},
                "swebench_verified": {"enabled": False},
                "refactorbench_py": {
                    "enabled": True,
                    "local_jsonl_path": str(input_path),
                    "max_tasks": None,
                    "task_id_allowlist_path": str(allowlist_path),
                    "task_id_allowlist_strict": True,
                },
            }
        }
    )

    loader = RefactorBenchPyLoader(config_dir=tmp_path)
    loaded = loader.load(cfg)
    task_ids = [task.task_id for task in loaded.tasks]

    assert task_ids == ["rb_001", "rb_003"]
    assert loaded.extra_manifests["refactorbench_py_selected_task_ids.json"] == ["rb_001", "rb_003"]


def test_refactorbench_allowlist_strict_missing_raises(tmp_path: Path) -> None:
    input_path = tmp_path / "refactorbench_sample.jsonl"
    allowlist_path = tmp_path / "allowlist.json"
    rows = [
        {"task_id": "rb_001", "instruction": "first"},
        {"task_id": "rb_002", "instruction": "second"},
    ]
    with input_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")
    allowlist_path.write_text(json.dumps(["rb_001", "rb_999"]), encoding="utf-8")

    cfg = AppConfig.model_validate(
        {
            "datasets": {
                "humaneval": {"enabled": False},
                "swebench_verified": {"enabled": False},
                "refactorbench_py": {
                    "enabled": True,
                    "local_jsonl_path": str(input_path),
                    "task_id_allowlist_path": str(allowlist_path),
                    "task_id_allowlist_strict": True,
                },
            }
        }
    )

    loader = RefactorBenchPyLoader(config_dir=tmp_path)
    with pytest.raises(ValueError, match="allowlist contains IDs missing"):
        loader.load(cfg)
