"""OpenAI-compatible adapter -- one adapter for most of the ecosystem.

Point `base_url` at OpenAI, vLLM, LM Studio, Together, Groq, OpenRouter or an
Azure deployment and this works unchanged. That breadth is the reason it does
not use the `openai` SDK: servers differ in which structured-output mode they
implement, and raw HTTP makes falling back between them straightforward.

Structured output degrades in three steps, because support genuinely varies:
  json_schema  -> strict grammar-constrained decoding (vLLM guided decoding)
  json_object  -> valid JSON, shape unenforced
  text         -> the schema in the prompt, JSON recovered from the reply
"""
from __future__ import annotations

#: Seconds a reachability probe may take. These run when a form opens, so a
#: dead endpoint must fail fast rather than hold the page.
PROBE_TIMEOUT = 4.0

import time
from typing import Any

import httpx
from pydantic import BaseModel

from app.config import secret
from app.providers.llm.base import (
    LLMError, LLMProvider, LLMResult, StructuredOutputError, TransientError,
    extract_json, schema_of, strip_reasoning,
)


class OpenAICompatProvider(LLMProvider):
    name = "openai"

    def __init__(self, settings: dict[str, Any]):
        super().__init__(settings)
        self.base_url = str(settings.get("base_url", "https://api.openai.com/v1")).rstrip("/")
        self.json_mode = settings.get("json_mode", "json_schema")
        #: Anything the server accepts that is not in the OpenAI schema. vLLM
        #: takes `chat_template_kwargs`, which is how a Qwen3 model's thinking
        #: mode is turned off -- without that it emits a scratchpad before every
        #: answer and cannot use grammar-constrained decoding at all.
        self._window: int | None = None
        self.extra_body = dict(settings.get("extra_body") or {})
        if settings.get("disable_thinking"):
            self.extra_body.setdefault("chat_template_kwargs",
                                       {"enable_thinking": False})
        key = secret(settings.get("api_key_env", "OPENAI_API_KEY"))
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        # Self-hosted servers commonly need no key at all, so a missing one is
        # not an error here the way it is for a hosted API.
        self.request_timeout = float(settings.get("request_timeout", 180.0))
        self._client = httpx.Client(base_url=self.base_url, headers=headers,
                                    timeout=self.request_timeout)

    def supports_vision(self) -> bool:
        return bool(self.settings.get("vision", False))

    #: A context-length refusal names itself. Estimating prompt tokens can only
    #: ever approximate the server's own tokenizer, so the reliable fix is to
    #: believe the server and ask for less.
    CONTEXT_ERROR = ("maximum context length", "context_length_exceeded",
                     "reduce the length", "too many tokens", "max_model_len")

    #: Statuses that mean "try again", not "this request is wrong". Falling
    #: through the structured-output modes on one of these is exactly backwards:
    #: it spends every mode on a problem none of them can fix, and reports the
    #: cause as unsupported structured output. Google returned 503 "high demand"
    #: and all three modes were consumed in under a second.
    RETRY_STATUS = {408, 429, 500, 502, 503, 504}

    def _post_within_window(self, payload: dict) -> dict:
        """Post, and if the server says the request is too long, ask for less.

        Halving the completion budget is the one response that always helps,
        and the server's own refusal is better evidence than any estimate of
        how many tokens its tokenizer will produce.
        """
        budget = int(payload.get("max_tokens") or self.max_tokens)
        last: LLMError | None = None
        # Halve until it fits or until there is no useful budget left. Stopping
        # after a fixed number of tries reported a generic failure instead of
        # the one thing worth saying: this prompt cannot fit this model.
        while True:
            try:
                return self._post(payload)
            except LLMError as exc:
                if not any(marker in str(exc).lower() for marker in self.CONTEXT_ERROR):
                    raise
                last = exc
                if budget <= 512:
                    break
                budget = max(512, budget // 2)
                payload = {**payload, "max_tokens": budget}
        raise LLMError(
            f"{self.base_url} cannot fit this request: the prompt alone nearly "
            f"fills this model's context window, leaving no room for an answer. "
            f"Use a model with a larger window for this stage. "
            f"Server said: {str(last)[:200]}"
        ) from last

    def _post(self, payload: dict, *, attempts: int = 4) -> dict:
        import random
        import time

        last: str = ""
        for attempt in range(attempts):
            try:
                response = self._client.post("/chat/completions", json=payload)
            except httpx.HTTPError as exc:
                last = f"{self.base_url} unreachable: {exc}"
                if attempt == attempts - 1:
                    raise LLMError(last) from exc
            else:
                if response.status_code < 400:
                    return response.json()
                detail = f"{self.base_url} returned {response.status_code}: {response.text[:300]}"
                if response.status_code not in self.RETRY_STATUS:
                    raise LLMError(detail)
                last = detail
                if attempt == attempts - 1:
                    raise TransientError(detail)
                wait = response.headers.get("retry-after")
                if wait and wait.isdigit():
                    time.sleep(min(float(wait), 30.0))
                    continue
            # exponential backoff with jitter, so parallel stages do not
            # synchronise their retries against a struggling endpoint
            time.sleep(min(2 ** attempt + random.random(), 20.0))
        raise LLMError(last or "request failed")

    def context_window(self) -> int | None:
        """The model's context length, as the server reports it. Cached."""
        if self._window is not None:
            return self._window or None
        try:
            data = self._client.get("/models", timeout=PROBE_TIMEOUT).json()
            for entry in data.get("data", []):
                if entry.get("id") in (self.model, self.model.rsplit("/", 1)[-1]):
                    self._window = int(entry.get("max_model_len") or 0)
                    break
            else:
                self._window = 0
        except Exception:
            self._window = 0
        return self._window or None

    def _fit_completion(self, prompt_chars: int, wanted: int) -> int:
        """Shrink the completion budget to what the window can hold.

        Asking for 12,000 completion tokens on top of a 5,100-token prompt is a
        hard 400 from a 16,384-token model -- the request never runs. The server
        knows its own limit, so the budget is derived from it rather than being
        a constant that happens to fit some models.
        """
        window = self.context_window()
        if not window:
            return wanted
        # 3 chars per token, not 4. The usual estimate suits prose; the
        # storyboard prompt is mostly Python, which tokenizes far denser, and a
        # 4-char estimate still overshot the window by two thousand tokens.
        estimated_prompt = prompt_chars // 3 + 64
        room = window - estimated_prompt - 256      # margin for template tokens
        return max(256, min(wanted, room))

    def complete(
        self, *, system: str, user: str, schema: type[BaseModel] | None = None,
        max_tokens: int | None = None, temperature: float | None = None,
        images: list[bytes] | None = None,
    ) -> LLMResult:
        user_content: Any = user
        if images:
            import base64

            user_content = [{"type": "text", "text": user}]
            for image in images:
                encoded = base64.b64encode(image).decode()
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{encoded}"},
                })

        budget = self._fit_completion(len(system) + len(user),
                                      max_tokens or self.max_tokens)
        base_payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": budget,
            "temperature": self.temperature if temperature is None else temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            **self.extra_body,
        }

        attempts = self._modes(schema)
        errors: list[str] = []
        last_error: StructuredOutputError | None = None
        for mode in attempts:
            payload = dict(base_payload)
            if schema is not None:
                payload = self._apply_mode(payload, schema, mode)
            started = time.time()
            try:
                data = self._post_within_window(payload)
            except TransientError:
                # the endpoint is struggling, not refusing this mode -- trying
                # the next one would waste it on the same problem
                raise
            except LLMError as exc:
                # an unsupported mode usually comes back as a 400
                errors.append(f"{mode}: {exc}")
                continue
            latency = int((time.time() - started) * 1000)

            choice = (data.get("choices") or [{}])[0]
            text = (choice.get("message") or {}).get("content") or ""
            text = strip_reasoning(text)
            usage = data.get("usage") or {}
            result = LLMResult(
                text=text, provider=self.name, model=data.get("model", self.model),
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                latency_ms=latency,
                raw={"finish_reason": choice.get("finish_reason"), "json_mode": mode},
            )
            if schema is None:
                return result
            try:
                result.parsed = extract_json(text)
                return self._finish(result, schema)
            except StructuredOutputError as exc:
                last_error = exc
                errors.append(f"{mode}: {exc}")
                continue

        if last_error is not None:
            raise last_error
        raise StructuredOutputError(
            "structured output failed in every mode tried "
            f"({', '.join(attempts)}):\n" + "\n".join(errors[-3:])
        )

    def _modes(self, schema: type[BaseModel] | None) -> list[str]:
        if schema is None:
            return ["text"]
        order = ["json_schema", "json_object", "text"]
        start = order.index(self.json_mode) if self.json_mode in order else 0
        return order[start:]

    def _apply_mode(self, payload: dict, schema: type[BaseModel], mode: str) -> dict:
        if mode == "json_schema":
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__.lower(),
                    "schema": schema_of(schema),
                    "strict": True,
                },
            }
        elif mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
            payload["messages"][0]["content"] += "\n\n" + self._json_instruction(schema)
        else:
            payload["messages"][0]["content"] += "\n\n" + self._json_instruction(schema)
        return payload

    def health(self) -> dict[str, Any]:
        """Reachability and whether a key is actually in place.

        These are different questions and conflating them is misleading: an
        OpenRouter profile with no key resolved still lists 416 models, because
        `/models` is public there. A profile can be perfectly reachable and fail
        every generation with a 401.
        """
        key_env = self.settings.get("api_key_env")
        key_present = bool(secret(key_env)) if key_env else None

        out: dict[str, Any] = {
            "provider": self.name, "base_url": self.base_url, "model": self.model,
            "api_key_env": key_env, "authenticated": key_present,
        }
        try:
            response = self._client.get("/models", timeout=PROBE_TIMEOUT)
            models = [m.get("id") for m in response.json().get("data", [])]
            # Providers namespace their ids differently -- Google lists
            # "models/gemini-flash-latest" while accepting "gemini-flash-latest"
            # in a request. Comparing raw strings reported a working model as
            # missing, which is a worse signal than none.
            bare = {m.rsplit("/", 1)[-1] for m in models if m}
            out |= {"reachable": True, "available_models": models[:600],
                    "model_count": len(models),
                    "model_present": self.model in models
                                     or self.model.rsplit("/", 1)[-1] in bare}
        except Exception as exc:
            out |= {"reachable": False, "error": str(exc)[:200]}
            return out

        # A missing key only matters where the endpoint actually requires one.
        # A self-hosted vLLM or LM Studio takes no key at all, and inheriting
        # `api_key_env` from the OpenAI defaults made a perfectly working local
        # endpoint report as unreachable.
        from app.config import ProviderProfile, is_hosted

        needs_key = is_hosted(ProviderProfile(adapter="openai", base_url=self.base_url))
        window = self.context_window()
        if window and self.max_tokens >= window * 0.75:
            out["warning"] = (
                f"Max reply tokens is {self.max_tokens} against a {window}-token "
                f"context window. The prompt and the reply share that window, so "
                f"this leaves almost no room for the prompt. Try "
                f"{max(1024, window // 4)}."
            )

        if key_env and not key_present and needs_key:
            out["reachable"] = False
            out["error"] = (
                f"The endpoint responds, but no key is set for {key_env}, so every "
                "generation would fail with 401. Set it under API keys."
            )
        elif key_env and not key_present:
            # worth saying, not worth blocking on
            out["note"] = (
                f"No key set for {key_env}. This looks like a self-hosted endpoint, "
                "which usually needs none -- clear the field if so."
            )
        elif out.get("model_present") is False and out.get("model_count"):
            out["error"] = (
                f"{self.model!r} is not among the {out['model_count']} models this "
                "endpoint offers. Check the model id."
            )
        return out
