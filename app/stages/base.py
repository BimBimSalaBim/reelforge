"""Shared stage machinery: the generate-validate-repair loop.

Every LLM stage has the same shape -- ask, check, and if the check fails hand
the model its own failure and ask again. Keeping it in one place means the
failure text a model sees is consistently specific, which is most of what makes
a repair attempt work rather than produce a different wrong answer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from app.providers.llm import LLMProvider, StructuredOutputError

#: Pydantic's own messages describe a constraint; a model needs an instruction.
#: "List should have at least 6 items" says nothing about what to do, and a
#: local model reliably returns the same short list again. These say what to change.
_GUIDANCE = {
    "too_short": (
        "{field}: you returned {actual} entries but at least {expected} are required. "
        "Do not stop early. Split the longer ones at clause boundaries and add more."
    ),
    "too_long": "{field}: you returned {actual} entries; at most {expected} are allowed. Merge or drop some.",
    "greater_than_equal": "{field}: {actual} is below the minimum of {expected}. Counting starts at {expected}, not 0.",
    "less_than_equal": "{field}: {actual} is above the maximum of {expected}.",
    "string_too_long": "{field}: this text is {actual} characters; keep it to {expected} or fewer.",
    "missing": "{field}: this field is required and was absent. Include it.",
    "string_pattern_mismatch": "{field}: the value does not match the required pattern.",
}


def humanise(error: ValidationError | Exception) -> str:
    """Turn a validation failure into instructions the model can act on."""
    if not isinstance(error, ValidationError):
        return str(error)
    lines: list[str] = []
    for item in error.errors():
        field = ".".join(str(p) for p in item["loc"]) or "(root)"
        kind = item.get("type", "")
        context = item.get("ctx") or {}
        expected = (context.get("min_length") or context.get("max_length")
                    or context.get("ge") or context.get("le") or "")
        actual = item.get("input")
        if isinstance(actual, (list, str)):
            actual = len(actual)
        template = _GUIDANCE.get(kind)
        if template:
            lines.append(template.format(field=field, actual=actual, expected=expected))
        else:
            lines.append(f"{field}: {item.get('msg', kind)}")
    return "\n".join(f"- {line}" for line in lines)


class StageError(RuntimeError):
    pass


@dataclass
class Attempt:
    index: int
    ok: bool
    problems: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0

    def as_dict(self) -> dict:
        return {"attempt": self.index, "ok": self.ok, "problems": self.problems,
                "tokens_in": self.tokens_in, "tokens_out": self.tokens_out,
                "latency_ms": self.latency_ms}


@dataclass
class GenerationOutcome:
    value: Any
    attempts: list[Attempt]

    @property
    def repairs(self) -> int:
        return max(0, len(self.attempts) - 1)

    @property
    def total_tokens(self) -> int:
        return sum(a.tokens_in + a.tokens_out for a in self.attempts)

    def as_dict(self) -> dict:
        return {"attempts": [a.as_dict() for a in self.attempts],
                "repairs": self.repairs, "total_tokens": self.total_tokens}


def generate_with_repair(
    llm: LLMProvider,
    schema: type[BaseModel],
    build_prompt: Callable[[str], tuple[str, str]],
    validate: Callable[[BaseModel], list[str]] | None = None,
    *,
    max_attempts: int = 3,
    progress: Callable[[str], None] | None = None,
) -> GenerationOutcome:
    """Ask until the answer validates, or give up with every failure recorded.

    `build_prompt(repair_notes)` returns (system, user); on the first attempt
    the notes are empty. `validate` returns a list of human-readable problems --
    an empty list means accept.
    """
    attempts: list[Attempt] = []
    notes = ""

    for index in range(1, max_attempts + 1):
        system, user = build_prompt(notes)
        if progress:
            progress(f"attempt {index}/{max_attempts}"
                     + (" (repair)" if notes else ""))
        try:
            result = llm.complete(system=system, user=user, schema=schema)
        except StructuredOutputError as exc:
            detail = humanise(exc.__cause__ or exc)
            attempts.append(Attempt(index, False, [f"malformed output: {detail}"]))
            notes = (
                f"Your reply was rejected. Fix exactly this:\n{detail}\n\n"
                "Return the complete corrected object as a single JSON value, with "
                "no prose and no markdown fence."
            )
            continue
        except ValidationError as exc:
            detail = humanise(exc)
            attempts.append(Attempt(index, False, [detail]))
            notes = f"Your reply failed validation. Fix exactly this:\n{detail}"
            continue

        value = result.parsed
        problems = validate(value) if validate else []
        attempts.append(Attempt(
            index, not problems, problems,
            tokens_in=result.input_tokens, tokens_out=result.output_tokens,
            latency_ms=result.latency_ms,
        ))
        if not problems:
            return GenerationOutcome(value=value, attempts=attempts)
        notes = "\n".join(f"- {p}" for p in problems)
        if progress:
            progress(f"attempt {index} rejected: {len(problems)} problem(s)")

    failures = attempts[-1].problems if attempts else ["no attempts made"]
    raise StageError(
        f"{schema.__name__} generation failed after {max_attempts} attempts. "
        "Last problems:\n" + "\n".join(f"  - {p}" for p in failures)
    )
