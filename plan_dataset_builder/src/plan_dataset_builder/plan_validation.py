from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Sequence

from pydantic import ValidationError

from plan_dataset_builder.config import PromptBoundsConfig
from plan_dataset_builder.constants import PLACEHOLDER_TERMS, PLANS_PER_BATCH
from plan_dataset_builder.labels import normalize_unique_step
from plan_dataset_builder.models import PlanSchema, StepSchema

PLACEHOLDER_PATTERN = re.compile(
    "|".join(re.escape(term) for term in PLACEHOLDER_TERMS), flags=re.IGNORECASE
)


class PlanValidationError(Exception):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


@dataclass
class PlanValidationResult:
    plans: list[dict[str, Any]]
    warnings_by_plan: list[list[str]]


def _walk_strings(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, str):
        values.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            values.extend(_walk_strings(item))
    elif isinstance(value, list):
        for item in value:
            values.extend(_walk_strings(item))
    return values


def _contains_placeholder(value: Any) -> bool:
    for text in _walk_strings(value):
        if PLACEHOLDER_PATTERN.search(text):
            return True
    return False


def _flatten_steps(steps: Sequence[StepSchema], depth: int = 1) -> tuple[int, int, bool, list[str]]:
    total = 0
    max_depth = depth
    has_checks = False
    actions: list[str] = []

    for step in steps:
        total += 1
        actions.append(step.action)
        if step.checks:
            has_checks = True
        if step.substeps:
            child_total, child_depth, child_has_checks, child_actions = _flatten_steps(
                step.substeps, depth + 1
            )
            total += child_total
            max_depth = max(max_depth, child_depth)
            has_checks = has_checks or child_has_checks
            actions.extend(child_actions)
    return total, max_depth, has_checks, actions


def _has_near_duplicate_actions(actions: list[str]) -> bool:
    normalized = [re.sub(r"\s+", " ", a.strip().lower()) for a in actions]
    return len(normalized) != len(set(normalized))


def compute_unique_step_match(plan_obj: dict[str, Any]) -> bool:
    """Return True when unique_step exactly matches at least one step action (including nested)."""
    try:
        model = PlanSchema.model_validate(plan_obj)
    except ValidationError:
        return False
    _, _, _, actions = _flatten_steps(model.steps)
    return model.unique_step in actions


def validate_plan_object(
    plan_obj: dict[str, Any],
    *,
    allowed_labels: set[str] | None,
    schema_version: str,
    bounds: PromptBoundsConfig,
) -> tuple[dict[str, Any], list[str]]:
    try:
        model = PlanSchema.model_validate(plan_obj)
    except ValidationError as exc:
        raise PlanValidationError("Plan object failed schema validation", {"validation_errors": exc.errors()}) from exc

    if model.schema_version != schema_version:
        raise PlanValidationError(
            f"Invalid schema_version: expected {schema_version}, got {model.schema_version}"
        )
    if allowed_labels is not None and model.strategy_label not in allowed_labels:
        raise PlanValidationError(
            f"strategy_label '{model.strategy_label}' is not in allowed labels",
            {"allowed_labels": sorted(allowed_labels)},
        )
    if len(model.steps) < bounds.min_steps:
        raise PlanValidationError(
            f"Expected at least {bounds.min_steps} top-level steps, found {len(model.steps)}"
        )

    total_steps, max_depth, has_checks, actions = _flatten_steps(model.steps)
    if max_depth > bounds.max_depth:
        raise PlanValidationError(f"max depth exceeded: {max_depth} > {bounds.max_depth}")
    if total_steps > bounds.max_total_steps:
        raise PlanValidationError(f"total steps exceeded: {total_steps} > {bounds.max_total_steps}")

    payload = model.model_dump(mode="json")
    if _contains_placeholder(payload):
        raise PlanValidationError("Placeholder content detected")

    warnings: list[str] = []
    target_min = max(6, bounds.min_steps)
    target_max = 8 if target_min <= 8 else target_min
    if not (target_min <= len(model.steps) <= target_max):
        warnings.append("top_level_steps_outside_target_range")
    if not has_checks:
        warnings.append("no_checks_present")
    if _has_near_duplicate_actions(actions):
        warnings.append("near_duplicate_actions")
    if not compute_unique_step_match(payload):
        warnings.append("unique_step_no_exact_action_match")
    serialized_size = len(json.dumps(payload, ensure_ascii=False))
    if serialized_size > 12_000:
        warnings.append("verbose_plan_content")

    return payload, warnings


def validate_plan_group(
    raw_text: str,
    *,
    allowed_labels: list[str],
    schema_version: str,
    bounds: PromptBoundsConfig,
    expected_plan_count: int = PLANS_PER_BATCH,
) -> PlanValidationResult:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise PlanValidationError("Response is not valid JSON", {"error": str(exc)}) from exc

    if not isinstance(parsed, list):
        raise PlanValidationError("Response must be a single JSON array")
    if len(parsed) != expected_plan_count:
        raise PlanValidationError(
            f"Response must contain exactly {expected_plan_count} plans, found {len(parsed)}"
        )

    plans: list[dict[str, Any]] = []
    warnings_by_plan: list[list[str]] = []
    unique_steps_normalized: set[str] = set()
    allowed_set = set(allowed_labels)

    for index, plan_obj in enumerate(parsed, start=1):
        if not isinstance(plan_obj, dict):
            raise PlanValidationError(f"Plan index {index} is not a JSON object")
        plan, warnings = validate_plan_object(
            plan_obj,
            allowed_labels=allowed_set,
            schema_version=schema_version,
            bounds=bounds,
        )
        normalized_unique = normalize_unique_step(plan["unique_step"])
        if not normalized_unique:
            raise PlanValidationError(f"Plan index {index} has empty unique_step")
        if normalized_unique in unique_steps_normalized:
            raise PlanValidationError(
                "unique_step values must be unique within each plan-group response",
                {"duplicate_unique_step_normalized": normalized_unique},
            )
        unique_steps_normalized.add(normalized_unique)
        plans.append(plan)
        warnings_by_plan.append(warnings)

    return PlanValidationResult(plans=plans, warnings_by_plan=warnings_by_plan)
