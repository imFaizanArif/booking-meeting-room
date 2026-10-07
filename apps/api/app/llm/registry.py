"""Provider registry: provider type -> adapter factory. New providers are one entry here."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from app.core.enums import ProviderType
from app.llm.adapters.anthropic import AnthropicAdapter
from app.llm.adapters.fake import FakeLLMProvider
from app.llm.adapters.gemini import GeminiAdapter
from app.llm.adapters.ollama import OllamaAdapter
from app.llm.adapters.openai import OpenAIAdapter
from app.llm.base import LLMProvider, ProviderConfig
from app.llm.types import Usage

AdapterFactory = Callable[[ProviderConfig], LLMProvider]

_FACTORIES: dict[ProviderType, AdapterFactory] = {
    ProviderType.openai: OpenAIAdapter,
    ProviderType.anthropic: AnthropicAdapter,
    ProviderType.ollama: OllamaAdapter,
    ProviderType.gemini: GeminiAdapter,
    ProviderType.fake: FakeLLMProvider,
}

# Providers that need no API key.
KEYLESS = frozenset({ProviderType.ollama, ProviderType.fake})


def register_adapter(provider_type: ProviderType, factory: AdapterFactory) -> None:
    """Override or add an adapter (tests inject scripted fakes this way)."""
    _FACTORIES[provider_type] = factory


def build_provider(config: ProviderConfig) -> LLMProvider:
    try:
        factory = _FACTORIES[ProviderType(config.provider_type)]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"No adapter registered for provider type {config.provider_type!r}") from exc
    return factory(config)


def estimate_cost(usage: Usage, input_price_per_mtok: Decimal | float | str,
                  output_price_per_mtok: Decimal | float | str) -> Decimal:
    cost = (
        Decimal(usage.input_tokens) * Decimal(str(input_price_per_mtok))
        + Decimal(usage.output_tokens) * Decimal(str(output_price_per_mtok))
    ) / Decimal(1_000_000)
    return cost.quantize(Decimal("0.000001"))
