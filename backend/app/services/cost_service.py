"""Estimated API cost tracking and budget guards for generation runs."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional


class BudgetExceededError(RuntimeError):
    """Raised before an LLM call when the configured task budget is exhausted."""


CostUpdateCallback = Callable[[dict], Awaitable[None]]


@dataclass
class CostEntry:
    provider: str
    model: str
    method: str
    api_key_id: Optional[int]
    input_tokens: int = 0
    output_tokens: int = 0
    count: int = 1
    cost_usd: float = 0.0
    pricing_known: bool = False


@dataclass
class CostTracker:
    """Best-effort cost tracker.

    Providers in this app do not expose normalized token usage yet, so text
    tokens are estimated from prompt/response characters. Image calls use a
    conservative flat price table. The summary is intentionally labelled as
    estimated.
    """

    budget_usd: Optional[float] = None
    on_update: Optional[CostUpdateCallback] = None
    entries: list[CostEntry] = field(default_factory=list)

    async def check_before_call(
        self,
        provider: str,
        model: str,
        method: str,
        kwargs: dict[str, Any],
    ) -> None:
        projected = self._estimate_cost(provider, model, method, kwargs, result=None)[0]
        if self.budget_usd is not None and self.total_usd + projected > self.budget_usd:
            raise BudgetExceededError(
                f"预算上限 ${self.budget_usd:.4f} 已不足以继续调用模型，"
                f"当前估算 ${self.total_usd:.4f}，下一次调用预计 ${projected:.4f}"
            )

    async def record_call(
        self,
        provider: str,
        model: str,
        method: str,
        kwargs: dict[str, Any],
        result: Any,
        api_key_id: Optional[int] = None,
    ) -> CostEntry:
        cost, input_tokens, output_tokens, pricing_known = self._estimate_cost(
            provider, model, method, kwargs, result=result
        )
        entry = CostEntry(
            provider=provider,
            model=model,
            method=method,
            api_key_id=api_key_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            count=1,
            cost_usd=cost,
            pricing_known=pricing_known,
        )
        self.entries.append(entry)
        if self.on_update:
            await self.on_update(self.summary())
        return entry

    @property
    def total_usd(self) -> float:
        return sum(e.cost_usd for e in self.entries)

    @property
    def is_over_budget(self) -> bool:
        return self.budget_usd is not None and self.total_usd >= self.budget_usd

    def summary(self) -> dict:
        by_agent_method: dict[str, float] = {}
        by_model: dict[str, float] = {}
        for entry in self.entries:
            by_agent_method[entry.method] = by_agent_method.get(entry.method, 0.0) + entry.cost_usd
            model_key = f"{entry.provider}:{entry.model}"
            by_model[model_key] = by_model.get(model_key, 0.0) + entry.cost_usd

        return {
            "estimated": True,
            "total_usd": round(self.total_usd, 6),
            "budget_usd": self.budget_usd,
            "budget_exceeded": self.is_over_budget,
            "pricing_complete": all(e.pricing_known for e in self.entries),
            "num_calls": len(self.entries),
            "input_tokens": sum(e.input_tokens for e in self.entries),
            "output_tokens": sum(e.output_tokens for e in self.entries),
            "by_method": {k: round(v, 6) for k, v in by_agent_method.items()},
            "by_model": {k: round(v, 6) for k, v in by_model.items()},
            "entries": [
                {
                    "provider": e.provider,
                    "model": e.model,
                    "method": e.method,
                    "api_key_id": e.api_key_id,
                    "input_tokens": e.input_tokens,
                    "output_tokens": e.output_tokens,
                    "cost_usd": round(e.cost_usd, 6),
                    "pricing_known": e.pricing_known,
                }
                for e in self.entries
            ],
        }

    def _estimate_cost(
        self,
        provider: str,
        model: str,
        method: str,
        kwargs: dict[str, Any],
        result: Any,
    ) -> tuple[float, int, int, bool]:
        input_tokens = _estimate_input_tokens(kwargs)
        output_tokens = _estimate_output_tokens(result)

        if method in ("generate_image", "generate_image_with_images", "generate_image_from_chat"):
            price = _lookup_image_price(provider, model)
            return price, input_tokens, output_tokens, price > 0

        input_rate, output_rate, known = _lookup_text_rates(provider, model)
        if result is None:
            output_tokens = max(output_tokens, 1200)
        cost = input_tokens * input_rate / 1000 + output_tokens * output_rate / 1000
        return cost, input_tokens, output_tokens, known


def _estimate_input_tokens(kwargs: dict[str, Any]) -> int:
    text = _flatten_text(kwargs)
    image_count = _count_images(kwargs)
    # A rough but stable heuristic: English/JSON-heavy prompts average ~4 chars/token.
    return max(1, math.ceil(len(text) / 4) + image_count * 1000)


def _estimate_output_tokens(result: Any) -> int:
    if isinstance(result, str):
        return max(1, math.ceil(len(result) / 4))
    if isinstance(result, (bytes, bytearray)):
        return 0
    return 0


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return ""
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            if key in {"api_key", "b64", "data"}:
                continue
            parts.append(_flatten_text(item))
        return "\n".join(parts)
    if isinstance(value, (list, tuple)):
        return "\n".join(_flatten_text(item) for item in value)
    return str(value)


def _count_images(value: Any) -> int:
    if isinstance(value, dict):
        count = 1 if value.get("type") in {"image_base64", "image_url", "image"} else 0
        if "b64" in value or "image_url" in value:
            count += 1
        return count + sum(_count_images(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return sum(_count_images(item) for item in value)
    if isinstance(value, (bytes, bytearray)):
        return 1
    return 0


def _lookup_text_rates(provider: str, model: str) -> tuple[float, float, bool]:
    name = (model or "").lower()
    provider = (provider or "").lower()

    if "gpt-4o" in name or "gpt-4.1" in name:
        return 0.005, 0.015, True
    if "gpt-5" in name:
        return 0.005, 0.015, False
    if "claude" in name or provider == "anthropic":
        return 0.003, 0.015, True
    if "gemini" in name or provider == "gemini":
        return 0.00125, 0.005, True
    # Unknown OpenRouter/relay models: keep budgets useful but mark incomplete.
    return 0.002, 0.008, False


def _lookup_image_price(provider: str, model: str) -> float:
    name = (model or "").lower()
    provider = (provider or "").lower()

    if "gpt-image" in name or provider == "openai_images":
        return 0.04
    if "gemini" in name or "nano" in name or provider in {"gemini", "openai_compat"}:
        return 0.04
    return 0.04
