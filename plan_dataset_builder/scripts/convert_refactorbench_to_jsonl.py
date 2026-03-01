#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

VARIANT_TO_MAPPING = {
    "base": "base_mapping.py",
    "descriptive": "descriptive_mapping.py",
    "lazy": "lazy_mapping.py",
}

REPO_CANONICAL = {
    "ansible_refactor": "ansible/ansible",
    "celery_refactor": "celery/celery",
    "django_refactor": "django/django",
    "fastapi_refactor": "tiangolo/fastapi",
    "flask_refactor": "pallets/flask",
    "requests_refactor": "psf/requests",
    "salt_refactor": "saltstack/salt",
    "scrapy_refactor": "scrapy/scrapy",
    "tornado_refactor": "tornadoweb/tornado",
}


def load_mapping(mapping_file: Path) -> dict[str, str]:
    module = ast.parse(mapping_file.read_text(encoding="utf-8"), filename=str(mapping_file))
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "file_mapping":
                    value = ast.literal_eval(node.value)
                    if not isinstance(value, dict):
                        raise ValueError(f"{mapping_file} file_mapping is not a dict")
                    return {str(k): str(v) for k, v in value.items()}
    raise ValueError(f"{mapping_file} does not define file_mapping")


def to_posix_rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def build_rows(
    refactorbench_root: Path,
    variant: str,
    include_test_source: bool,
) -> list[dict[str, Any]]:
    scripts_dir = refactorbench_root / "scripts"
    mapping_path = scripts_dir / VARIANT_TO_MAPPING[variant]
    mapping = load_mapping(mapping_path)

    rows: list[dict[str, Any]] = []
    seen_task_ids: set[str] = set()

    for test_rel, task_rel in mapping.items():
        test_path = (scripts_dir / test_rel).resolve()
        task_path = (scripts_dir / task_rel).resolve()

        if not test_path.exists():
            raise FileNotFoundError(f"Missing test file: {test_path}")
        if not task_path.exists():
            raise FileNotFoundError(f"Missing task file: {task_path}")

        repo_dir = task_path.parent.name
        stem = task_path.stem
        problem_id = stem[:-5] if stem.endswith("-task") else stem

        task_id = f"{variant}__{repo_dir}__{problem_id}"
        if task_id in seen_task_ids:
            raise ValueError(f"Duplicate task_id generated: {task_id}")
        seen_task_ids.add(task_id)

        problem_statement = task_path.read_text(encoding="utf-8").strip()
        repo = REPO_CANONICAL.get(repo_dir, repo_dir)

        row: dict[str, Any] = {
            "task_id": task_id,
            "instance_id": task_id,
            "problem_statement": problem_statement,
            "repo": repo,
            "base_commit": None,
            "environment_setup_commit": None,
            "hints_text": "",
            "FAIL_TO_PASS": [to_posix_rel(test_path, refactorbench_root)],
            "PASS_TO_PASS": [],
            "difficulty": "unknown",
            "created_at": None,
            "variant": variant,
            "problem_id": problem_id,
            "task_file": to_posix_rel(task_path, refactorbench_root),
            "test_file": to_posix_rel(test_path, refactorbench_root),
            "source": "refactorbench_local_clone",
        }

        if include_test_source:
            row["test_source"] = test_path.read_text(encoding="utf-8", errors="replace")

        rows.append(row)

    rows.sort(key=lambda x: x["task_id"])
    return rows


def write_jsonl(rows: list[dict[str, Any]], output_path: Path, limit: int | None) -> int:
    if limit is not None:
        rows = rows[:limit]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")
    return len(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert RefactorBench tasks into a JSONL format aligned with SWE-bench-style fields."
    )
    parser.add_argument(
        "--refactorbench-root",
        type=Path,
        default=Path("../RefactorBench"),
        help="Path to cloned RefactorBench root.",
    )
    parser.add_argument(
        "--variant",
        choices=("base", "descriptive", "lazy"),
        default="descriptive",
        help="Task variant to export.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/refactorbench_py.jsonl"),
        help="Output JSONL file path.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap after deterministic sort by task_id.",
    )
    parser.add_argument(
        "--include-test-source",
        action="store_true",
        help="Include full test source in each row (larger prompts/cost).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.refactorbench_root.resolve()
    if not root.exists():
        raise FileNotFoundError(f"RefactorBench root not found: {root}")

    rows = build_rows(
        refactorbench_root=root,
        variant=args.variant,
        include_test_source=args.include_test_source,
    )
    written = write_jsonl(rows, args.output.resolve(), args.limit)
    print(f"Wrote {written} rows to {args.output.resolve()}")


if __name__ == "__main__":
    main()
