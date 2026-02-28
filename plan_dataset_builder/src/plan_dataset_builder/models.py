from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from plan_dataset_builder.constants import BATCH_NUMBERS, PLANS_PER_BATCH

DatasetName = Literal["humaneval", "swebench_verified", "refactorbench_py"]


class StepSchema(BaseModel):
    id: str
    action: str
    rationale: str
    checks: list[str] | None = None
    substeps: list["StepSchema"] | None = None

    @field_validator("id", "action", "rationale")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must be a non-empty string")
        return value

    @field_validator("checks")
    @classmethod
    def validate_checks(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        if not value:
            raise ValueError("checks must be omitted or contain at least one item")
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("checks must contain non-empty strings")
        return value

    @field_validator("substeps")
    @classmethod
    def validate_substeps(cls, value: list["StepSchema"] | None) -> list["StepSchema"] | None:
        if value is None:
            return value
        if not value:
            raise ValueError("substeps must be omitted or contain at least one item")
        return value


StepSchema.model_rebuild()


class PlanSchema(BaseModel):
    schema_version: str
    strategy_label: str
    unique_step: str
    steps: list[StepSchema]

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != "1.0":
            raise ValueError("schema_version must be '1.0'")
        return value

    @field_validator("strategy_label", "unique_step")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must be a non-empty string")
        return value


class TaskRecord(BaseModel):
    schema_version: str = "1.0"
    dataset: DatasetName
    task_id: str
    source: str
    task_text: str
    context_keys_included: list[str]
    context_keys_excluded: list[str]
    extras: dict[str, Any] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != "1.0":
            raise ValueError("schema_version must be '1.0'")
        return value


class PlanRecord(BaseModel):
    schema_version: str = "1.0"
    dataset: DatasetName
    task_id: str
    run_id: str
    plan_id: str
    batch_number: int
    within_batch_index: int
    strategy_label: str
    unique_step: str
    plan: dict[str, Any]
    plan_raw: str
    gen: dict[str, Any]
    extras: dict[str, Any] = Field(default_factory=dict)
    unique_step_flag: Literal["pass", "fail"]

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != "1.0":
            raise ValueError("schema_version must be '1.0'")
        return value

    @field_validator("batch_number")
    @classmethod
    def validate_batch_number(cls, value: int) -> int:
        if value not in BATCH_NUMBERS:
            allowed = ",".join(str(number) for number in BATCH_NUMBERS)
            raise ValueError(f"batch_number must be in {{{allowed}}}")
        return value

    @field_validator("within_batch_index")
    @classmethod
    def validate_within_batch_index(cls, value: int) -> int:
        if not (1 <= value <= PLANS_PER_BATCH):
            raise ValueError(f"within_batch_index must be in [1,{PLANS_PER_BATCH}]")
        return value


class FailedPlanRecord(BaseModel):
    schema_version: str = "1.0"
    dataset: DatasetName
    task_id: str
    run_id: str
    failed_plan_id: str
    batch_number: int
    attempt_number: int
    model: str
    custom_id: str
    timestamp_utc: str
    error: dict[str, Any]
    raw_response_text: str = ""
    parsed_response: dict[str, Any] | list[Any] | None = None
    request_id: str | None = None
    batch_id: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != "1.0":
            raise ValueError("schema_version must be '1.0'")
        return value

    @field_validator("batch_number")
    @classmethod
    def validate_batch_number(cls, value: int) -> int:
        if value not in BATCH_NUMBERS:
            allowed = ",".join(str(number) for number in BATCH_NUMBERS)
            raise ValueError(f"batch_number must be in {{{allowed}}}")
        return value


class RunSummary(BaseModel):
    run_id: str
    started_at_utc: str
    finished_at_utc: str
    config: dict[str, Any]
    dataset_sources: dict[str, str]
    task_selection_manifests: dict[str, dict[str, Any]]
    prompt_version_hash: str
    prompt_template_path: str
    model: str | dict[str, str]
    decoding_defaults: dict[str, Any]
    budget_total: float
    pricing_table: dict[str, Any]
    budget_enforcement: dict[str, Any]
    counts: dict[str, int]
    token_cost_totals: dict[str, Any]
