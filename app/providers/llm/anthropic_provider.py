"""Anthropic adapter.

Structured output goes through tool use rather than a JSON mode: the model is
given exactly one tool whose input schema is the target, and forced to call it.
That is the most reliable way to get schema-conforming output from Claude, and
it fails loudly rather than returning prose that nearly parses.
"""
from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel

from app.config import secret
from app.providers.llm.base import (
    LLMError, LLMProvider, LLMResult, schema_of, strip_reasoning,
)

TOOL_NAME = "emit_result"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, settings: dict[str, Any]):
        super().__init__(settings)
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise LLMError("the `anthropic` package is not installed") from exc

        key = secret(settings.get("api_key_env", "ANTHROPIC_API_KEY"))
        if not key:
            raise LLMError(
                f"{settings.get('api_key_env', 'ANTHROPIC_API_KEY')} is not set"
            )
        kwargs: dict[str, Any] = {"api_key": key}
        if settings.get("base_url"):
            kwargs["base_url"] = settings["base_url"]
        self._client = anthropic.Anthropic(**kwargs)

    def supports_vision(self) -> bool:
        return True

    def complete(
        self, *, system: str, user: str, schema: type[BaseModel] | None = None,
        max_tokens: int | None = None, temperature: float | None = None,
        images: list[bytes] | None = None,
    ) -> LLMResult:
        content: list[dict[str, Any]] = []
        for image in images or []:
            import base64

            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png",
                           "data": base64.b64encode(image).decode()},
            })
        content.append({"type": "text", "text": user})

        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": self.temperature if temperature is None else temperature,
            "system": system,
            "messages": [{"role": "user", "content": content}],
        }
        if schema is not None:
            request["tools"] = [{
                "name": TOOL_NAME,
                "description": f"Return the completed {schema.__name__}.",
                "input_schema": schema_of(schema),
            }]
            request["tool_choice"] = {"type": "tool", "name": TOOL_NAME}

        started = time.time()
        try:
            response = self._client.messages.create(**request)
        except Exception as exc:
            raise LLMError(f"anthropic request failed: {exc}") from exc
        latency = int((time.time() - started) * 1000)

        text_parts: list[str] = []
        parsed: Any | None = None
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use" and block.name == TOOL_NAME:
                parsed = block.input

        result = LLMResult(
            text=strip_reasoning("\n".join(text_parts)),
            provider=self.name,
            model=response.model,
            parsed=parsed,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=latency,
            raw={"stop_reason": response.stop_reason},
        )
        return self._finish(result, schema)

    def health(self) -> dict[str, Any]:
        try:
            self._client.messages.create(
                model=self.model, max_tokens=4,
                messages=[{"role": "user", "content": "hi"}],
            )
            return {"provider": self.name, "model": self.model, "reachable": True}
        except Exception as exc:
            return {"provider": self.name, "model": self.model,
                    "reachable": False, "error": str(exc)[:200]}
