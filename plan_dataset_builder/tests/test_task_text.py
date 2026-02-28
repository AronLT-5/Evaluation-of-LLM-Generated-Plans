from __future__ import annotations

from plan_dataset_builder.task_text import build_task_text


def test_task_text_excludes_gold_keys_and_sorts_context() -> None:
    row = {
        "task_id": "HumanEval/0",
        "prompt": "Implement add(a, b).",
        "entry_point": "add",
        "canonical_solution": "return a + b",
        "test": "assert add(1, 2) == 3",
        "metadata": {"difficulty": "easy", "tags": ["math", "intro"]},
    }

    built = build_task_text(
        dataset="humaneval",
        task_id="HumanEval/0",
        primary_key="prompt",
        row=row,
        excluded_keys={"canonical_solution", "test"},
        max_task_text_chars=200_000,
        max_field_chars=80_000,
        include_primary_in_context_fields=False,
    )

    assert "[DATASET] humaneval" in built.task_text
    assert "[TASK_ID] HumanEval/0" in built.task_text
    assert "[PRIMARY_TASK]" in built.task_text
    assert "Implement add(a, b)." in built.task_text
    assert "canonical_solution" not in built.task_text
    assert "assert add(1, 2) == 3" not in built.task_text
    assert built.context_keys_excluded == ["canonical_solution", "test"]
    assert built.context_keys_included == ["entry_point", "metadata", "task_id"]

