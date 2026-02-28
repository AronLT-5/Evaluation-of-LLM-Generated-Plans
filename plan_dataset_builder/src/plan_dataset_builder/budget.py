from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Sequence, TypeVar

from plan_dataset_builder.config import PricingConfig

try:
    tiktoken = importlib.import_module("tiktoken")
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    tiktoken = None


@dataclass
class CostEstimate:
    input_tokens_est: int
    output_tokens_est: int
    cost_upper: float


def estimate_input_tokens(text: str, model: str) -> int:
    if tiktoken is None:
        return max(1, len(text) // 4)
    try:
        encoding = tiktoken.encoding_for_model(model)
    except Exception:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


def estimate_request_upper_cost(
    prompt_text: str,
    model: str,
    max_output_tokens: int,
    pricing: PricingConfig,
) -> CostEstimate:
    input_tokens_est = estimate_input_tokens(prompt_text, model)
    output_tokens_est = max_output_tokens
    cost_upper = (
        (input_tokens_est / 1_000_000) * pricing.input_per_1m_tokens
        + (output_tokens_est / 1_000_000) * pricing.output_per_1m_tokens
    )
    return CostEstimate(
        input_tokens_est=input_tokens_est,
        output_tokens_est=output_tokens_est,
        cost_upper=cost_upper,
    )


def estimate_cost_from_usage(usage: dict[str, int] | None, pricing: PricingConfig) -> float:
    if not usage:
        return 0.0
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    return (
        (input_tokens / 1_000_000) * pricing.input_per_1m_tokens
        + (output_tokens / 1_000_000) * pricing.output_per_1m_tokens
    )


T = TypeVar("T")


def select_budget_chunk(items: Sequence[T], costs: Sequence[float], allowed_total: float) -> list[T]:
    if len(items) != len(costs):
        raise ValueError("items and costs length mismatch")
    if not items:
        return []

    chunk: list[T] = []
    running = 0.0
    for item, cost in zip(items, costs):
        if chunk and running + cost > allowed_total:
            break
        chunk.append(item)
        running += cost

    if not chunk:
        chunk.append(items[0])
    return chunk
