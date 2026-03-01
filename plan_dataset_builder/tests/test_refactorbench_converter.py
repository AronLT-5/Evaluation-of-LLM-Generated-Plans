from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_converter_module():
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "convert_refactorbench_to_jsonl.py"
    spec = importlib.util.spec_from_file_location("rb_converter", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_refactorbench_fixture(tmp_path: Path, mapping_text: str) -> Path:
    root = tmp_path / "RefactorBench"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)

    _write(scripts / "descriptive_mapping.py", mapping_text)
    _write(
        root / "tests" / "foo_refactor" / "alpha-test.py",
        "def test_alpha():\n    assert True\n",
    )
    _write(
        root / "tests" / "bar_refactor" / "beta-test.py",
        "def test_beta():\n    assert True\n",
    )
    _write(
        root / "problems" / "descriptive_problems" / "foo_refactor" / "alpha-task.txt",
        "Refactor alpha task.",
    )
    _write(
        root / "problems" / "descriptive_problems" / "bar_refactor" / "beta-task.txt",
        "Refactor beta task.",
    )

    return root


def test_build_rows_descriptive_shape_and_sort(tmp_path: Path) -> None:
    mod = _load_converter_module()
    root = _build_refactorbench_fixture(
        tmp_path,
        (
            "file_mapping = {\n"
            "  '../tests/bar_refactor/beta-test.py': '../problems/descriptive_problems/bar_refactor/beta-task.txt',\n"
            "  '../tests/foo_refactor/alpha-test.py': '../problems/descriptive_problems/foo_refactor/alpha-task.txt',\n"
            "}\n"
        ),
    )

    rows = mod.build_rows(root, "descriptive", include_test_source=False)
    assert len(rows) == 2

    assert rows[0]["task_id"] == "descriptive__bar_refactor__beta"
    assert rows[1]["task_id"] == "descriptive__foo_refactor__alpha"

    for row in rows:
        assert row["instance_id"] == row["task_id"]
        assert isinstance(row["problem_statement"], str)
        assert row["base_commit"] is None
        assert row["environment_setup_commit"] is None
        assert row["hints_text"] == ""
        assert isinstance(row["FAIL_TO_PASS"], list)
        assert isinstance(row["PASS_TO_PASS"], list)
        assert row["difficulty"] == "unknown"
        assert row["created_at"] is None
        assert row["variant"] == "descriptive"
        assert row["source"] == "refactorbench_local_clone"
        assert "test_source" not in row


def test_write_jsonl_limit_applied(tmp_path: Path) -> None:
    mod = _load_converter_module()
    output_path = tmp_path / "data" / "refactorbench_py.jsonl"
    rows = [
        {"task_id": "a"},
        {"task_id": "b"},
        {"task_id": "c"},
    ]
    written = mod.write_jsonl(rows, output_path, limit=2)
    assert written == 2
    lines = output_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_build_rows_missing_task_file_raises(tmp_path: Path) -> None:
    mod = _load_converter_module()
    root = tmp_path / "RefactorBench"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    _write(
        scripts / "descriptive_mapping.py",
        (
            "file_mapping = {\n"
            "  '../tests/foo_refactor/alpha-test.py': '../problems/descriptive_problems/foo_refactor/missing-task.txt',\n"
            "}\n"
        ),
    )
    _write(root / "tests" / "foo_refactor" / "alpha-test.py", "pass\n")

    with pytest.raises(FileNotFoundError):
        mod.build_rows(root, "descriptive", include_test_source=False)


def test_build_rows_duplicate_task_id_raises(tmp_path: Path) -> None:
    mod = _load_converter_module()
    root = _build_refactorbench_fixture(
        tmp_path,
        (
            "file_mapping = {\n"
            "  '../tests/foo_refactor/alpha-test.py': '../problems/descriptive_problems/foo_refactor/alpha-task.txt',\n"
            "  '../tests/bar_refactor/alpha-test.py': '../problems/descriptive_problems/foo_refactor/alpha-task.txt',\n"
            "}\n"
        ),
    )
    _write(
        root / "tests" / "bar_refactor" / "alpha-test.py",
        "def test_alpha():\n    assert True\n",
    )

    with pytest.raises(ValueError, match="Duplicate task_id generated"):
        mod.build_rows(root, "descriptive", include_test_source=False)
