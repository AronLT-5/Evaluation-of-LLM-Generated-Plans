from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml
from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

from plan_dataset_builder.constants import DATASET_NAMES, DEFAULT_LABEL_SETS, TOTAL_PLANS_PER_TASK


class RunConfig(BaseModel):
    run_id: str | None = None
    output_root: str = "runs"
    resume: bool = False


class OpenAIConfig(BaseModel):
    api_key_env_var: str = "OPENAI_API_KEY"
    model: str = "gpt-4.1-mini"
    multi_model: bool = Field(
        default=False,
        validation_alias=AliasChoices("multi_model", "multi-model"),
        serialization_alias="multi_model",
    )
    model1: str | None = None
    model2: str | None = None
    model3: str | None = None
    use_batch_api: bool = True
    # Deprecated and ignored at runtime for compatibility across models.
    temperature: float | None = None
    # Deprecated and ignored at runtime for compatibility across models.
    top_p: float | None = None
    max_output_tokens: int = 2500
    # Deprecated and ignored at runtime for compatibility across models.
    seed: int | None = None
    # Kept for backward compatibility; plan generation always enforces structured outputs.
    structured_outputs: bool = True
    prompt_cache_enabled: bool = False
    prompt_cache_key_prefix: str | None = None
    prompt_cache_retention: str | None = None

    @field_validator("model", "model1", "model2", "model3")
    @classmethod
    def validate_model_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("model names must be non-empty strings")
        return cleaned

    @field_validator("prompt_cache_retention")
    @classmethod
    def validate_prompt_cache_retention(cls, value: str | None) -> str | None:
        if value is None:
            return value
        allowed = {"24h", "in_memory"}
        if value not in allowed:
            allowed_text = ", ".join(sorted(allowed))
            raise ValueError(f"prompt_cache_retention must be one of: {allowed_text}")
        return value

    @model_validator(mode="after")
    def validate_multi_model(self) -> "OpenAIConfig":
        if not self.multi_model:
            return self
        missing: list[str] = []
        if not self.model1:
            missing.append("model1")
        if not self.model2:
            missing.append("model2")
        if not self.model3:
            missing.append("model3")
        if missing:
            missing_str = ", ".join(missing)
            raise ValueError(f"openai.multi_model=true requires values for: {missing_str}")
        return self

    def model_for_batch(self, batch_number: int) -> str:
        if not self.multi_model:
            return self.model
        if batch_number == 1 and self.model1:
            return self.model1
        if batch_number == 2 and self.model2:
            return self.model2
        if batch_number == 3 and self.model3:
            return self.model3
        raise ValueError(f"No configured model for batch_number={batch_number}")

    def model_map_by_batch(self) -> dict[int, str]:
        return {
            1: self.model_for_batch(1),
            2: self.model_for_batch(2),
            3: self.model_for_batch(3),
        }


class HumanEvalDatasetConfig(BaseModel):
    enabled: bool = True
    max_tasks: int = 50


class SWEBenchVerifiedDatasetConfig(BaseModel):
    enabled: bool = True
    max_tasks: int | None = 500
    write_first100_manifest: bool = True
    task_id_allowlist_path: str | None = None
    task_id_allowlist_strict: bool = True

    @field_validator("task_id_allowlist_path")
    @classmethod
    def validate_task_id_allowlist_path(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("task_id_allowlist_path must be a non-empty string when provided")
        return cleaned


class RefactorBenchPyDatasetConfig(BaseModel):
    enabled: bool = False
    local_jsonl_path: str | None = None
    max_tasks: int | None = None
    task_id_allowlist_path: str | None = None
    task_id_allowlist_strict: bool = True

    @field_validator("task_id_allowlist_path")
    @classmethod
    def validate_task_id_allowlist_path(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("task_id_allowlist_path must be a non-empty string when provided")
        return cleaned

    @model_validator(mode="after")
    def ensure_path_if_enabled(self) -> "RefactorBenchPyDatasetConfig":
        if self.enabled and not self.local_jsonl_path:
            raise ValueError("refactorbench_py.local_jsonl_path is required when enabled=true")
        return self


class DatasetsConfig(BaseModel):
    humaneval: HumanEvalDatasetConfig = Field(default_factory=HumanEvalDatasetConfig)
    swebench_verified: SWEBenchVerifiedDatasetConfig = Field(default_factory=SWEBenchVerifiedDatasetConfig)
    refactorbench_py: RefactorBenchPyDatasetConfig = Field(default_factory=RefactorBenchPyDatasetConfig)


class TaskTextConfig(BaseModel):
    max_task_text_chars: int = 200_000
    max_field_chars: int = 80_000
    include_primary_in_context_fields: bool = False


class PromptBoundsConfig(BaseModel):
    min_steps: int = 4
    max_depth: int = 2
    max_total_steps: int = 25


class PromptConfig(BaseModel):
    template_path: str = "prompts/plan_prompt_template.txt"
    schema_version: str = "1.0"
    bounds: PromptBoundsConfig = Field(default_factory=PromptBoundsConfig)


class DiversityConfig(BaseModel):
    label_sets: dict[str, list[str]] = Field(default_factory=lambda: copy.deepcopy(DEFAULT_LABEL_SETS))
    enforce_unique_labels_across_12: bool = True

    @field_validator("label_sets")
    @classmethod
    def validate_label_sets(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        missing = [name for name in DATASET_NAMES if name not in value]
        if missing:
            raise ValueError(f"Missing label sets for datasets: {missing}")

        for dataset in DATASET_NAMES:
            labels = value[dataset]
            if len(labels) != TOTAL_PLANS_PER_TASK:
                raise ValueError(
                    f"{dataset} must define exactly {TOTAL_PLANS_PER_TASK} labels, found {len(labels)}"
                )
            if len(set(labels)) != TOTAL_PLANS_PER_TASK:
                raise ValueError(f"{dataset} labels must be unique")
        return value


class RetriesConfig(BaseModel):
    max_retries_per_batch_call: int = 3


class PricingConfig(BaseModel):
    input_per_1m_tokens: float = 0.30
    output_per_1m_tokens: float = 1.20
    currency: str = "USD"


class BudgetConfig(BaseModel):
    budget_total: float = 50.0
    pricing: PricingConfig = Field(default_factory=PricingConfig)
    safety_margin: float = 0.9
    allow_over_budget: bool = False

    @field_validator("safety_margin")
    @classmethod
    def validate_safety_margin(cls, value: float) -> float:
        if value <= 0 or value > 1:
            raise ValueError("safety_margin must be in (0, 1]")
        return value


class AppConfig(BaseModel):
    run: RunConfig = Field(default_factory=RunConfig)
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    datasets: DatasetsConfig = Field(default_factory=DatasetsConfig)
    task_text: TaskTextConfig = Field(default_factory=TaskTextConfig)
    prompt: PromptConfig = Field(default_factory=PromptConfig)
    diversity: DiversityConfig = Field(default_factory=DiversityConfig)
    retries: RetriesConfig = Field(default_factory=RetriesConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)

    def resolved_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def load_config(path: Path) -> AppConfig:
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return AppConfig.model_validate(raw)


def write_sample_config(path: Path) -> None:
    cfg = AppConfig()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(cfg.resolved_dict(), handle, sort_keys=False, allow_unicode=True)
