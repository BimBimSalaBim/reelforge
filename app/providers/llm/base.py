"""The LLM interface every adapter implements.

Deliberately narrow. Structured output is the only interesting part: each
backend expresses "return JSON matching this schema" differently, and the
differences are exactly what makes swapping providers painful. Adapters
normalise that here so the pipeline stages never branch on provider.
"""
from __future__ import annotations

import abc
import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)

#: Reasoning models (Qwen3, DeepSeek-R1 and friends) wrap their scratchpad in a
#: tag and emit it as ordinary content. Left in, it corrupts plain-text answers
#: and sits in front of the JSON that structured output is supposed to return.
_REASONING_RE = re.compile(
    r"<(think|thinking|reasoning|scratchpad)>.*?</\1>", re.S | re.I
)
_OPEN_REASONING_RE = re.compile(r"<(think|thinking|reasoning|scratchpad)>", re.I)


def strip_reasoning(text: str) -> str:
    """Remove reasoning blocks from a model's visible output.

    An unclosed tag means the response was truncated mid-thought; everything
    from that tag onward is scratchpad, so it goes too.
    """
    if not text:
        return text
    cleaned = _REASONING_RE.sub("", text)
    match = _OPEN_REASONING_RE.search(cleaned)
    if match:
        cleaned = cleaned[: match.start()]
    return cleaned.strip()


class LLMError(RuntimeError):
    """Anything that went wrong talking to a model."""


class TransientError(LLMError):
    """The endpoint is overloaded or rate limited. Retrying is the only fix.

    Kept distinct so callers do not respond by changing the request -- degrading
    the structured-output mode because a server said "high demand" wastes every
    mode on a problem none of them addresses.
    """


class StructuredOutputError(LLMError):
    """The model answered, but not with usable JSON."""

    def __init__(self, message: str, raw_text: str = ""):
        super().__init__(message)
        self.raw_text = raw_text


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    parsed: Any | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def as_dict(self) -> dict:
        return {
            "provider": self.provider, "model": self.model,
            "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
            "latency_ms": self.latency_ms, "chars": len(self.text),
        }


def extract_json(text: str) -> Any:
    """Recover a JSON value from a model's prose.

    Tries, in order: the whole string, a fenced block, then the outermost
    balanced braces or brackets. Local models fenced-and-prefaced far more often
    than hosted ones, so this fallback earns its keep.
    """
    text = strip_reasoning(text or "")
    if not text:
        raise StructuredOutputError("model returned an empty response")

    for candidate in _candidates(text):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise StructuredOutputError("no parseable JSON in the response", raw_text=text[:4000])


def _candidates(text: str):
    yield text
    for match in _FENCE_RE.findall(text):
        yield match.strip()
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == opener:
                depth += 1
            elif char == closer:
                depth -= 1
                if depth == 0:
                    yield text[start : index + 1]
                    break


def schema_of(model: type[BaseModel]) -> dict:
    """A JSON Schema most servers will accept.

    `$defs`/`$ref` are inlined and `additionalProperties: false` is forced,
    because strict json_schema modes reject unresolved refs and open objects.
    """
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})

    def resolve(node: Any, depth: int = 0) -> Any:
        if depth > 24:
            return node
        if isinstance(node, dict):
            if "$ref" in node and node["$ref"].startswith("#/$defs/"):
                target = defs.get(node["$ref"].split("/")[-1], {})
                merged = {k: v for k, v in node.items() if k != "$ref"}
                return resolve({**target, **merged}, depth + 1)
            out = {key: resolve(value, depth + 1) for key, value in node.items()}
            if out.get("type") == "object" and "additionalProperties" not in out:
                out["additionalProperties"] = False
            return out
        if isinstance(node, list):
            return [resolve(item, depth + 1) for item in node]
        return node

    return resolve(raw)


#: Keys that only ever appear in a JSON Schema, never in an instance of one.
SCHEMA_MARKERS = {"$schema", "$defs", "properties", "additionalProperties"}


def looks_like_schema(payload: Any) -> bool:
    """True when a model returned the specification instead of an answer."""
    if not isinstance(payload, dict):
        return False
    if SCHEMA_MARKERS & set(payload):
        return True
    return payload.get("type") == "object" and "properties" in payload


def skeleton(model: type[BaseModel], _depth: int = 0) -> Any:
    """A filled example instance, derived from the model itself.

    Shown to models that have no structured-output mode. Generated rather than
    hand-written so it cannot drift from the schema it illustrates.
    """
    if _depth > 5:
        return "..."
    out: dict[str, Any] = {}
    for name, info in model.model_fields.items():
        out[name] = _example_for(info.annotation, name, _depth,
                                 minimum=_min_items(info),
                                 bounds=_numeric_bounds(info))
    return out


def _numeric_bounds(field: Any) -> tuple[float | None, float | None]:
    """Lower and upper bounds declared on a numeric field.

    The example is a strong anchor, so it has to be a *valid* instance. A
    placeholder of 0 for a field constrained to `ge=1` was copied literally --
    every scene came back 0-indexed and failed validation.
    """
    low = high = None
    for meta in getattr(field, "metadata", []) or []:
        for attr, target in (("ge", "low"), ("gt", "low"), ("le", "high"), ("lt", "high")):
            value = getattr(meta, attr, None)
            if value is None:
                continue
            if attr == "gt":
                value = value + 1
            if attr == "lt":
                value = value - 1
            if target == "low":
                low = value if low is None else max(low, value)
            else:
                high = value if high is None else min(high, value)
    return low, high


def _min_items(field: Any) -> int:
    """How many list entries the field requires.

    A one-element example anchors a model to producing one element. Measured:
    a field asking for 10-18 phrases got 4, because the example showed a single
    entry. Showing the true minimum removes that pull.
    """
    for meta in getattr(field, "metadata", []) or []:
        value = getattr(meta, "min_length", None) or getattr(meta, "min_items", None)
        if isinstance(value, int) and value > 0:
            return min(value, 6)
    return 1


def _example_for(annotation: Any, name: str, depth: int, minimum: int = 1,
                 bounds: tuple[float | None, float | None] = (None, None)) -> Any:
    import typing

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    low, high = bounds

    if origin is typing.Union or str(origin) == "types.UnionType":
        real = [a for a in args if a is not type(None)]
        return _example_for(real[0], name, depth, minimum, bounds) if real else None
    if origin in (list, set, tuple):
        inner = args[0] if args else str
        return [_example_for(inner, name, depth + 1) for _ in range(max(1, minimum))]
    if origin is dict:
        value = args[1] if len(args) > 1 else str
        return {"key": _example_for(value, name, depth + 1)}
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return skeleton(annotation, depth + 1)
    if annotation is bool:
        return True
    if annotation is int:
        candidate = int(low) if low is not None else 1
        if high is not None:
            candidate = min(candidate, int(high))
        return candidate
    if annotation is float:
        candidate = float(low) if low is not None else 1.0
        if high is not None:
            candidate = min(candidate, float(high))
        return candidate
    if getattr(annotation, "__members__", None):  # Enum
        return list(annotation.__members__.values())[0].value
    return f"<{name}>"


def _count_notes(model: type[BaseModel]) -> str:
    """Spell out list minimums in words.

    Stating them separately rather than annotating the example keeps the example
    a valid instance -- a note wedged into an array of objects gets copied.
    """
    lines = []
    for name, info in model.model_fields.items():
        minimum = _min_items(info)
        if minimum > 1:
            lines.append(f"  {name}: at least {minimum} entries")
    if not lines:
        return ""
    return "\n\nMINIMUM LIST LENGTHS (a reply with fewer is rejected):\n" + "\n".join(lines)


class LLMProvider(abc.ABC):
    name: str = "base"

    def __init__(self, settings: dict[str, Any]):
        self.settings = settings
        self.model: str = settings.get("model", "")
        self.max_tokens: int = int(settings.get("max_tokens", 8192))
        self.temperature: float = float(settings.get("temperature", 0.7))

    # ---- required ------------------------------------------------------
    @abc.abstractmethod
    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: type[BaseModel] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        images: list[bytes] | None = None,
    ) -> LLMResult:
        ...

    @abc.abstractmethod
    def health(self) -> dict[str, Any]:
        """Cheap reachability probe for `GET /api/config/providers`."""

    # ---- optional ------------------------------------------------------
    def supports_vision(self) -> bool:
        return False

    # ---- shared --------------------------------------------------------
    def _finish(
        self, result: LLMResult, schema: type[BaseModel] | None
    ) -> LLMResult:
        if schema is None:
            return result
        payload = result.parsed if result.parsed is not None else extract_json(result.text)
        if looks_like_schema(payload):
            raise StructuredOutputError(
                "you returned the JSON Schema itself, not an answer shaped by it. "
                "Reply with an object whose keys are the field names "
                f"({', '.join(list(schema.model_fields)[:8])}), filled with real "
                'content. Do not include "properties", "$defs" or "type".',
                raw_text=json.dumps(payload)[:1500],
            )
        try:
            result.parsed = schema.model_validate(payload)
        except Exception as exc:
            raise StructuredOutputError(
                f"response did not match {schema.__name__}: {exc}",
                raw_text=json.dumps(payload)[:4000] if payload is not None else result.text[:4000],
            ) from exc
        return result

    @staticmethod
    def _json_instruction(schema: type[BaseModel]) -> str:
        """Belt and braces for servers with no structured-output mode.

        The schema alone is not enough. Smaller models reliably echo it back --
        returning the schema document instead of an instance of it -- so a
        filled skeleton is shown too, and the difference is stated outright.
        Models follow an example far more reliably than a specification.
        """
        return (
            "Reply with a single JSON object and nothing else: no prose, no "
            "markdown fence, no explanation.\n\n"
            "Return DATA, not a schema. Do not copy the specification below into "
            'your answer. Never include the keys "type", "properties", "$defs", '
            '"required" or "description" as structure -- those describe the '
            "shape, they are not part of it.\n\n"
            f"SHAPE SPECIFICATION:\n{json.dumps(schema_of(schema), indent=1)}\n\n"
            "A CORRECTLY SHAPED ANSWER LOOKS LIKE THIS. The values are "
            "placeholders; replace them with real content. The number of entries "
            "shown in each list is the MINIMUM, not a target:\n"
            f"{json.dumps(skeleton(schema), indent=1)}"
            + _count_notes(schema)
        )
