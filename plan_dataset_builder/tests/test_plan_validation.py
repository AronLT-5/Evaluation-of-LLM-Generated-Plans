from __future__ import annotations

import json

import pytest

from plan_dataset_builder.config import PromptBoundsConfig
from plan_dataset_builder.constants import PLANS_PER_BATCH
from plan_dataset_builder.plan_validation import (
    PlanValidationError,
    compute_unique_step_match,
    validate_plan_group,
)


def _make_plan(
    label: str,
    unique_step: str | None = None,
    first_action: str = "Inspect task statement",
) -> dict:
    resolved_unique_step = unique_step if unique_step is not None else first_action
    return {
        "schema_version": "1.0",
        "strategy_label": label,
        "unique_step": resolved_unique_step,
        "steps": [
            {"id": "1", "action": first_action, "rationale": "Understand goals"},
            {"id": "2", "action": "Identify constraints", "rationale": "Bound solution space"},
            {"id": "3", "action": "Draft approach", "rationale": "Define implementation path"},
            {"id": "4", "action": "Define checks", "rationale": "Verify expected behavior"},
        ],
    }


def test_validate_plan_group_accepts_valid_payload() -> None:
    payload = [
        _make_plan("A", first_action="Inspect task statement"),
        _make_plan("B", first_action="Map edge cases"),
        _make_plan("C", first_action="Prototype candidate flow"),
        _make_plan("D", first_action="Define verification steps"),
    ]
    result = validate_plan_group(
        json.dumps(payload),
        allowed_labels=["A", "B", "C", "D"],
        schema_version="1.0",
        bounds=PromptBoundsConfig(min_steps=4, max_depth=2, max_total_steps=25),
    )
    assert len(result.plans) == PLANS_PER_BATCH


def test_validate_plan_group_rejects_duplicate_unique_steps() -> None:
    payload = [
        _make_plan("A", unique_step="Inspect task statement", first_action="Inspect task statement"),
        _make_plan("B", unique_step="inspect   task statement", first_action="inspect   task statement"),
        _make_plan("C", unique_step="Draft approach", first_action="Draft approach"),
        _make_plan("D", unique_step="Define checks", first_action="Define checks"),
    ]
    with pytest.raises(PlanValidationError):
        validate_plan_group(
            json.dumps(payload),
            allowed_labels=["A", "B", "C", "D"],
            schema_version="1.0",
            bounds=PromptBoundsConfig(min_steps=4, max_depth=2, max_total_steps=25),
        )


def test_validate_plan_group_rejects_placeholder_content() -> None:
    payload = [
        _make_plan("A", first_action="Inspect task statement"),
        _make_plan("B", first_action="Map edge cases"),
        _make_plan("C", first_action="Draft approach"),
        _make_plan("D", unique_step="todo: finish this", first_action="todo: finish this"),
    ]
    with pytest.raises(PlanValidationError):
        validate_plan_group(
            json.dumps(payload),
            allowed_labels=["A", "B", "C", "D"],
            schema_version="1.0",
            bounds=PromptBoundsConfig(min_steps=4, max_depth=2, max_total_steps=25),
        )


def test_validate_plan_group_allows_identifier_like_unknown_tokens() -> None:
    plan_a = _make_plan("A", first_action="Inspect test_unknown_unit3 behavior")
    plan_a["steps"][0]["checks"] = ["pytest astropy/units/tests/test_units.py::test_unknown_unit3"]
    payload = [
        plan_a,
        _make_plan("B", first_action="Map edge cases"),
        _make_plan("C", first_action="Draft approach"),
        _make_plan("D", first_action="Define checks"),
    ]
    result = validate_plan_group(
        json.dumps(payload),
        allowed_labels=["A", "B", "C", "D"],
        schema_version="1.0",
        bounds=PromptBoundsConfig(min_steps=4, max_depth=2, max_total_steps=25),
    )
    assert len(result.plans) == PLANS_PER_BATCH


def test_validate_plan_group_rejects_standalone_unknown_in_natural_language() -> None:
    payload = [
        _make_plan("A", first_action="Inspect task statement"),
        _make_plan("B", first_action="Map edge cases"),
        _make_plan("C", first_action="Draft approach"),
        _make_plan("D", unique_step="Investigate unknown root cause", first_action="Define checks"),
    ]
    with pytest.raises(PlanValidationError):
        validate_plan_group(
            json.dumps(payload),
            allowed_labels=["A", "B", "C", "D"],
            schema_version="1.0",
            bounds=PromptBoundsConfig(min_steps=4, max_depth=2, max_total_steps=25),
        )


def test_validate_plan_group_allows_unknowns_plural() -> None:
    payload = [
        _make_plan("A", unique_step="Map unknowns across failing tests", first_action="Inspect task statement"),
        _make_plan("B", first_action="Map edge cases"),
        _make_plan("C", first_action="Draft approach"),
        _make_plan("D", first_action="Define checks"),
    ]
    result = validate_plan_group(
        json.dumps(payload),
        allowed_labels=["A", "B", "C", "D"],
        schema_version="1.0",
        bounds=PromptBoundsConfig(min_steps=4, max_depth=2, max_total_steps=25),
    )
    assert len(result.plans) == PLANS_PER_BATCH


def test_validate_plan_group_allows_unique_step_not_matching_action_with_warning() -> None:
    payload = [
        _make_plan("A", unique_step="This is not an action", first_action="Inspect task statement"),
        _make_plan("B", first_action="Map edge cases"),
        _make_plan("C", first_action="Draft approach"),
        _make_plan("D", first_action="Define checks"),
    ]
    result = validate_plan_group(
        json.dumps(payload),
        allowed_labels=["A", "B", "C", "D"],
        schema_version="1.0",
        bounds=PromptBoundsConfig(min_steps=4, max_depth=2, max_total_steps=25),
    )
    assert len(result.plans) == PLANS_PER_BATCH
    assert "unique_step_no_exact_action_match" in result.warnings_by_plan[0]


def test_validate_plan_group_rejects_empty_optional_fields() -> None:
    plan = _make_plan("A", first_action="Inspect task statement")
    plan["steps"][0]["checks"] = []
    payload = [
        plan,
        _make_plan("B", first_action="Map edge cases"),
        _make_plan("C", first_action="Draft approach"),
        _make_plan("D", first_action="Define checks"),
    ]
    with pytest.raises(PlanValidationError):
        validate_plan_group(
            json.dumps(payload),
            allowed_labels=["A", "B", "C", "D"],
            schema_version="1.0",
            bounds=PromptBoundsConfig(min_steps=4, max_depth=2, max_total_steps=25),
        )


def test_compute_unique_step_match_top_level_match() -> None:
    plan = _make_plan("A", unique_step="Inspect task statement", first_action="Inspect task statement")
    assert compute_unique_step_match(plan) is True


def test_compute_unique_step_match_substep_match() -> None:
    plan = _make_plan("A", unique_step="Inspect nested detail", first_action="Inspect task statement")
    plan["steps"][0]["substeps"] = [
        {"id": "1.1", "action": "Inspect nested detail", "rationale": "Nested verification"}
    ]
    assert compute_unique_step_match(plan) is True


def test_compute_unique_step_match_mismatch() -> None:
    plan = _make_plan("A", unique_step="No matching action", first_action="Inspect task statement")
    assert compute_unique_step_match(plan) is False
