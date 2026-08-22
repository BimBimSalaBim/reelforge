"""A provider that returns canned responses.

Lets the whole pipeline run in CI with no API key, no network and no GPU, and
lets tests drive specific failure modes -- a malformed payload, a schema
violation, a repair that succeeds on the second attempt.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from pydantic import BaseModel

from app.providers.llm.base import LLMProvider, LLMResult

Responder = Callable[[str, str], Any]


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, settings: dict[str, Any] | None = None):
        super().__init__(settings or {"model": "fake-1"})
        #: queue of responses; each is a str, a dict, a BaseModel, or an Exception
        self.queue: list[Any] = list((settings or {}).get("queue", []))
        #: responses keyed by the schema name they answer. Preferred over the
        #: queue for anything that retries: a repair attempt would otherwise
        #: consume the next stage's canned answer and fail for the wrong reason.
        self.by_schema: dict[str, Any] = dict((settings or {}).get("by_schema", {}))
        self.responder: Responder | None = (settings or {}).get("responder")
        self.calls: list[dict[str, Any]] = []

    def push(self, *responses: Any) -> "FakeProvider":
        self.queue.extend(responses)
        return self

    def answer(self, schema: type[BaseModel] | str, response: Any) -> "FakeProvider":
        """Answer every request for this schema with the same value."""
        name = schema if isinstance(schema, str) else schema.__name__
        self.by_schema[name] = response
        return self

    def complete(
        self, *, system: str, user: str, schema: type[BaseModel] | None = None,
        max_tokens: int | None = None, temperature: float | None = None,
        images: list[bytes] | None = None,
    ) -> LLMResult:
        self.calls.append({"system": system, "user": user,
                           "schema": schema.__name__ if schema else None,
                           "images": len(images or [])})

        name = schema.__name__ if schema else None
        if name and name in self.by_schema:
            response = self.by_schema[name]
        elif self.queue:
            response = self.queue.pop(0)
        elif self.responder:
            response = self.responder(system, user)
        else:
            raise AssertionError(
                f"FakeProvider has no answer for {name or 'a plain completion'}. "
                f"Registered schemas: {sorted(self.by_schema) or 'none'}; "
                f"queue depth: {len(self.queue)}."
            )

        if isinstance(response, Exception):
            raise response
        if isinstance(response, BaseModel):
            response = response.model_dump(mode="json")

        text = response if isinstance(response, str) else json.dumps(response)
        result = LLMResult(text=text, provider=self.name, model=self.model,
                           input_tokens=len(user) // 4, output_tokens=len(text) // 4,
                           latency_ms=1)
        if schema is not None and not isinstance(response, str):
            result.parsed = response
        return self._finish(result, schema)

    def health(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "reachable": True,
                "queued": len(self.queue), "schemas": sorted(self.by_schema)}
