"""Ollama adapter.

Ollama's native `/api/chat` takes a JSON Schema directly in `format`, which is
grammar-constrained on recent versions and equivalent to guided decoding. Older
builds only understand `format: "json"`, so this degrades the same way the
OpenAI-compatible adapter does.

Ollama also exposes an OpenAI-compatible endpoint at `/v1`. This talks to the
native API instead, because `keep_alive` -- which decides whether the next call
pays the model load cost again -- has no OpenAI equivalent, and a cold reload
between pipeline stages is minutes of wall clock.
"""
from __future__ import annotations

#: Seconds a reachability probe may take. These run when a form opens, so a
#: dead endpoint must fail fast rather than hold the page.
PROBE_TIMEOUT = 4.0

import time
from typing import Any

import httpx
from pydantic import BaseModel

from app.providers.llm.base import (
    LLMError, LLMProvider, LLMResult, StructuredOutputError, extract_json,
    schema_of, strip_reasoning,
)


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, settings: dict[str, Any]):
        super().__init__(settings)
        self.base_url = str(settings.get("base_url", "http://ollama:11434")).rstrip("/")
        self.keep_alive = settings.get("keep_alive", "10m")
        self.request_timeout = float(settings.get("request_timeout", 180.0))
        self._client = httpx.Client(base_url=self.base_url, timeout=self.request_timeout)

    def supports_vision(self) -> bool:
        return bool(self.settings.get("vision", False))

    def complete(
        self, *, system: str, user: str, schema: type[BaseModel] | None = None,
        max_tokens: int | None = None, temperature: float | None = None,
        images: list[bytes] | None = None,
    ) -> LLMResult:
        message: dict[str, Any] = {"role": "user", "content": user}
        if images:
            import base64

            message["images"] = [base64.b64encode(i).decode() for i in images]

        payload: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "keep_alive": self.keep_alive,
            "messages": [{"role": "system", "content": system}, message],
            "options": {
                "temperature": self.temperature if temperature is None else temperature,
                "num_predict": max_tokens or self.max_tokens,
            },
        }

        formats: list[Any] = [None]
        if schema is not None:
            # newest first: a real schema is grammar-constrained, "json" only
            # guarantees valid JSON, and None relies on the prompt alone
            formats = [schema_of(schema), "json", None]

        errors: list[str] = []
        last_error: StructuredOutputError | None = None
        for fmt in formats:
            attempt = dict(payload)
            if fmt is not None:
                attempt["format"] = fmt
            # every mode weaker than a real schema needs the shape spelled out
            if schema is not None and not isinstance(fmt, dict):
                attempt["messages"] = [
                    {"role": "system",
                     "content": system + "\n\n" + self._json_instruction(schema)},
                    message,
                ]

            started = time.time()
            try:
                response = self._client.post("/api/chat", json=attempt)
            except httpx.HTTPError as exc:
                raise LLMError(f"{self.base_url} unreachable: {exc}") from exc
            if response.status_code >= 400:
                errors.append(f"format={_label(fmt)}: HTTP {response.status_code} "
                              f"{response.text[:200]}")
                continue

            data = response.json()
            latency = int((time.time() - started) * 1000)
            text = strip_reasoning((data.get("message") or {}).get("content") or "")
            result = LLMResult(
                text=text, provider=self.name, model=data.get("model", self.model),
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
                latency_ms=latency,
                raw={"done_reason": data.get("done_reason"), "format": _label(fmt)},
            )
            if schema is None:
                return result
            try:
                result.parsed = extract_json(text)
                return self._finish(result, schema)
            except StructuredOutputError as exc:
                last_error = exc
                errors.append(f"format={_label(fmt)}: {exc}")
                continue

        # Re-raise the last real failure rather than a summary of all of them.
        # `generate_with_repair` turns a ValidationError into instructions the
        # model can act on, and it can only do that if the cause survives; a
        # concatenated summary reaches the model as noise it cannot fix.
        if last_error is not None:
            raise last_error
        raise StructuredOutputError(
            "ollama structured output failed in every mode:\n" + "\n".join(errors[-3:])
        )

    def health(self) -> dict[str, Any]:
        try:
            response = self._client.get("/api/tags", timeout=PROBE_TIMEOUT)
            models = [m.get("name") for m in response.json().get("models", [])]
            return {"provider": self.name, "base_url": self.base_url,
                    "model": self.model, "reachable": True,
                    "available_models": models,
                    "model_present": any(
                        m == self.model or m.split(":")[0] == self.model.split(":")[0]
                        for m in models
                    )}
        except Exception as exc:
            return {"provider": self.name, "base_url": self.base_url,
                    "model": self.model, "reachable": False, "error": str(exc)[:200]}


def _label(fmt: Any) -> str:
    if fmt is None:
        return "none"
    return "json" if fmt == "json" else "schema"
