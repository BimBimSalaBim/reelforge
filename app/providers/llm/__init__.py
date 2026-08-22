"""LLM provider factory."""
from __future__ import annotations

from typing import Any

from app.config import Config, get_config
from app.providers.llm.base import (
    LLMError, LLMProvider, LLMResult, StructuredOutputError, extract_json,
    schema_of, strip_reasoning,
)

__all__ = [
    "LLMError", "LLMProvider", "LLMResult", "StructuredOutputError",
    "extract_json", "schema_of", "strip_reasoning", "build_llm", "PROVIDERS",
]

PROVIDERS = ("anthropic", "openai", "ollama", "fake")


def build_llm(
    role: str = "content",
    cfg: Config | None = None,
    overrides: dict[str, Any] | None = None,
) -> LLMProvider:
    """Resolve the provider for a pipeline stage.

    Precedence: explicit overrides > the stage's `roles` entry > the top-level
    provider block. Adapters are imported lazily so a missing optional SDK only
    matters when that provider is actually selected.
    """
    cfg = cfg or get_config()
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}

    # a caller may name either a profile ("my-vllm") or an adapter ("ollama")
    requested = overrides.pop("provider", None) or overrides.pop("profile", None)
    if requested and requested in cfg.llm.profiles:
        profile = cfg.llm.profiles[requested]
        name, settings = profile.adapter, profile.settings()
    elif requested:
        from app.config import LLM_DEFAULTS

        match = next((p for p in cfg.llm.profiles.values() if p.adapter == requested), None)
        name = requested
        settings = match.settings() if match else dict(LLM_DEFAULTS.get(requested, {}))
    else:
        name, settings = cfg.llm.for_role(role)
    settings = {**settings, **overrides}

    if name == "anthropic":
        from app.providers.llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider(settings)
    if name == "openai":
        from app.providers.llm.openai_compat import OpenAICompatProvider
        return OpenAICompatProvider(settings)
    if name == "ollama":
        from app.providers.llm.ollama_provider import OllamaProvider
        return OllamaProvider(settings)
    if name == "fake":
        from app.providers.llm.fake import FakeProvider
        return FakeProvider(settings)
    raise LLMError(f"unknown llm provider {name!r}; known: {', '.join(PROVIDERS)}")
