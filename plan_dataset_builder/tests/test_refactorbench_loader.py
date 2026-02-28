from __future__ import annotations

import json
from pathlib import Path

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
