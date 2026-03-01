from __future__ import annotations

import json
from pathlib import Path

import pytest

from plan_dataset_builder.constants import DATASET_REFACTORBENCH_PY, DATASET_SWEBENCH_VERIFIED
from plan_dataset_builder.jsonl_io import write_jsonl
from plan_dataset_builder.models import TaskRecord
from plan_dataset_builder.sectioning import merge_sections, prepare_sections


class _FakeLoaded:
    def __init__(self, dataset: str, source: str, tasks: list[TaskRecord]) -> None:
        self.dataset = dataset
        self.source = source
        self.tasks = tasks
        self.extra_manifests: dict[str, object] = {}


class _FakeLoader:
    def __init__(self, dataset_name: str, task_ids: list[str]) -> None:
        self.dataset_name = dataset_name
        self.source = f"fake://{dataset_name}"
        self._task_ids = task_ids

    def load(self, _config):  # type: ignore[no-untyped-def]
        tasks = [
            TaskRecord(
                schema_version="1.0",
                dataset=self.dataset_name,  # type: ignore[arg-type]
                task_id=task_id,
                source=self.source,
                task_text=f"Task {task_id}",
                context_keys_included=[],
                context_keys_excluded=[],
                extras={},
            )
            for task_id in self._task_ids
        ]
        return _FakeLoaded(self.dataset_name, self.source, tasks)


def _write_minimal_config(path: Path) -> None:
    path.write_text(
        """
run:
  run_id: null
  output_root: runs
  resume: false
openai:
  model: gpt-4.1-mini
datasets:
  humaneval:
    enabled: false
  swebench_verified:
    enabled: true
    max_tasks: 100
  refactorbench_py:
    enabled: true
    local_jsonl_path: data/refactorbench_py.jsonl
    max_tasks: 100
        """.strip()
        + "\n",
        encoding="utf-8",
    )


def test_prepare_sections_writes_four_sections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "main_config.yaml"
    _write_minimal_config(config_path)

    swe_ids = [f"swe_{i:03d}" for i in range(1, 101)]
    ref_ids = [f"ref_{i:03d}" for i in range(1, 101)]

    def fake_get_enabled_loaders(*, config, config_dir):  # type: ignore[no-untyped-def]
        _ = (config, config_dir)
        return [
            _FakeLoader(DATASET_SWEBENCH_VERIFIED, swe_ids),
            _FakeLoader(DATASET_REFACTORBENCH_PY, ref_ids),
        ]

    monkeypatch.setattr("plan_dataset_builder.sectioning.get_enabled_loaders", fake_get_enabled_loaders)

    output_dir = tmp_path / "section_runs"
    summary = prepare_sections(
        config_path=config_path,
        section_size=25,
        sections=4,
        output_dir=output_dir,
        run_prefix="full_system",
    )

    assert Path(summary["sections_manifest_path"]).exists()
    for i in range(1, 5):
        section_dir = output_dir / f"section_{i:02d}"
        assert (section_dir / "swebench_verified_task_ids.json").exists()
        assert (section_dir / "refactorbench_py_task_ids.json").exists()
        section_cfg = section_dir / "section_config.yaml"
        assert section_cfg.exists()
        cfg_text = section_cfg.read_text(encoding="utf-8")
        assert "task_id_allowlist_path: swebench_verified_task_ids.json" in cfg_text
        assert "task_id_allowlist_path: refactorbench_py_task_ids.json" in cfg_text

    section1_swe = json.loads((output_dir / "section_01" / "swebench_verified_task_ids.json").read_text())
    section4_ref = json.loads((output_dir / "section_04" / "refactorbench_py_task_ids.json").read_text())
    assert section1_swe[0] == "swe_001"
    assert section1_swe[-1] == "swe_025"
    assert section4_ref[0] == "ref_076"
    assert section4_ref[-1] == "ref_100"


def _make_source_section_run(
    base_dir: Path,
    section_idx: int,
    *,
    swe_start: int,
    ref_start: int,
) -> Path:
    run_dir = base_dir / f"full_s{section_idx:02d}_v1"
    (run_dir / "datasets" / DATASET_SWEBENCH_VERIFIED).mkdir(parents=True, exist_ok=True)
    (run_dir / "datasets" / DATASET_REFACTORBENCH_PY).mkdir(parents=True, exist_ok=True)
    (run_dir / "config").mkdir(parents=True, exist_ok=True)

    (run_dir / "config" / "run_config.json").write_text("{}", encoding="utf-8")
    (run_dir / "runs.jsonl").write_text("", encoding="utf-8")

    swe_tasks = [
        {
            "schema_version": "1.0",
            "dataset": DATASET_SWEBENCH_VERIFIED,
            "task_id": f"swe_{i:03d}",
            "source": "fake",
            "task_text": f"Task swe_{i:03d}",
            "context_keys_included": [],
            "context_keys_excluded": [],
            "extras": {},
        }
        for i in range(swe_start, swe_start + 25)
    ]
    ref_tasks = [
        {
            "schema_version": "1.0",
            "dataset": DATASET_REFACTORBENCH_PY,
            "task_id": f"ref_{i:03d}",
            "source": "fake",
            "task_text": f"Task ref_{i:03d}",
            "context_keys_included": [],
            "context_keys_excluded": [],
            "extras": {},
        }
        for i in range(ref_start, ref_start + 25)
    ]

    write_jsonl(run_dir / "datasets" / DATASET_SWEBENCH_VERIFIED / "tasks.jsonl", swe_tasks)
    write_jsonl(run_dir / "datasets" / DATASET_REFACTORBENCH_PY / "tasks.jsonl", ref_tasks)
    write_jsonl(run_dir / "datasets" / DATASET_SWEBENCH_VERIFIED / "plans.jsonl", [])
    write_jsonl(run_dir / "datasets" / DATASET_REFACTORBENCH_PY / "plans.jsonl", [])
    return run_dir


def test_merge_sections_happy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_root = tmp_path / "source_runs"
    source_root.mkdir(parents=True, exist_ok=True)
    runs = {
        "s1": _make_source_section_run(source_root, 1, swe_start=1, ref_start=1),
        "s2": _make_source_section_run(source_root, 2, swe_start=26, ref_start=26),
        "s3": _make_source_section_run(source_root, 3, swe_start=51, ref_start=51),
        "s4": _make_source_section_run(source_root, 4, swe_start=76, ref_start=76),
    }

    monkeypatch.setattr("plan_dataset_builder.sectioning.validate_run_dir", lambda _run_dir: [])

    output_root = tmp_path / "runs"
    summary = merge_sections(
        section_runs=runs,
        output_run_id="full_system_merged_001",
        output_root=output_root,
    )

    out_dir = Path(summary["output_run_dir"])
    swe_tasks_path = out_dir / "datasets" / DATASET_SWEBENCH_VERIFIED / "tasks.jsonl"
    ref_tasks_path = out_dir / "datasets" / DATASET_REFACTORBENCH_PY / "tasks.jsonl"
    assert swe_tasks_path.exists()
    assert ref_tasks_path.exists()
    assert len(swe_tasks_path.read_text(encoding="utf-8").splitlines()) == 100
    assert len(ref_tasks_path.read_text(encoding="utf-8").splitlines()) == 100
    assert (out_dir / "merge_info.json").exists()


def test_merge_sections_detects_overlap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_root = tmp_path / "source_runs"
    source_root.mkdir(parents=True, exist_ok=True)
    runs = {
        "s1": _make_source_section_run(source_root, 1, swe_start=1, ref_start=1),
        "s2": _make_source_section_run(source_root, 2, swe_start=1, ref_start=26),  # overlap in swe
        "s3": _make_source_section_run(source_root, 3, swe_start=51, ref_start=51),
        "s4": _make_source_section_run(source_root, 4, swe_start=76, ref_start=76),
    }

    monkeypatch.setattr("plan_dataset_builder.sectioning.validate_run_dir", lambda _run_dir: [])

    with pytest.raises(ValueError, match="Section overlap detected"):
        merge_sections(
            section_runs=runs,
            output_run_id="full_system_merged_overlap",
            output_root=tmp_path / "runs",
        )
