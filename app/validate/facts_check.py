"""Trace every number in generated copy back to a source.

DEVELOPMENT.md: "Every claim on screen is a hostage." The generation prompt says the
model may not state a number that is not in the FACTS block, and this is the
check that holds it to that -- prompts are not enforcement.

Two tiers of provenance, because the existing scripts legitimately use both:

  api     -- fetched from GitHub or Hugging Face just now. Trustworthy.
  readme  -- appears in the project's own README or model card. This is where
             "100+ agents" and "314 MCP tools" come from; the API has no such
             field. Trustworthy as *the project's own claim*, which is exactly
             how the scripts phrase them.

Anything in neither is unsourced and gets flagged for human review rather than
silently shipped.
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from app.models.facts import FactsBundle

#: 68041 | 68,041 | 68K | 68k | 8.1M | 100+ .  The unit must attach to the
#: number, and no trailing whitespace is captured -- it would corrupt
#: normalisation. The suffix is matched in either case: "194k" is as common as
#: "194K" on a cover, and matching only uppercase captured the digits alone,
#: which then matched no real figure and read as invented.
NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?(?:[KkMmBb]\b)?\+?")

#: Units that make a number a measurement of the video itself, not a claim
#: about the project.
UNIT_SUFFIX_RE = re.compile(r"^\s?(?:s|sec|secs|seconds|ms|fps|px|kbps|hz|khz)\b", re.I)

#: "1.4 million downloads" is how a caption is written; "1.4M" is how a stat
#: card is written. Both mean the same figure, and only the second was ever
#: recognised -- so every platform caption about a large number was rejected.
SCALE_WORD_RE = re.compile(r"^\s(million|thousand|billion|k|m|b)\b", re.I)
SCALE_SUFFIX = {"thousand": "K", "k": "K", "million": "M", "m": "M",
                "billion": "B", "b": "B"}

#: Words that make the following number a designation rather than a statistic.
#: "Level 4.1" and "Profile High @ 4.1" name an H.264 conformance point; "v2.1.0"
#: names a release. None of them is a claim about the project.
INDEX_PREFIX_RE = re.compile(
    r"(?:scene|step|part|chapter|phase|line|level|release|profile|tier|"
    r"v|version|#)\s?$",
    re.I,
)


def _is_structural(text: str, start: int, end: int, token: str) -> bool:
    """Decide from the token's own immediate neighbourhood, never a wide window.

    An earlier version tested a 36-character context, which meant a version
    string one line away silenced an unrelated invented figure.

    The cases here are all ones that produced false positives against real fact
    sheets: "AGPL-3.0" was read as a claim of "3.0", and "2024-05-30" as claims
    of "05" and "30". A number welded to an identifier by a hyphen, or sitting
    inside a date, is not a statistic about the project.
    """
    before = text[max(0, start - 12) : start]
    after = text[end : end + 12]

    # part of a dotted version: 3.38.9 -- a dot with a digit on the far side
    if before.endswith(".") and before[-2:-1].isdigit():
        return True
    if after.startswith(".") and after[1:2].isdigit():
        return True

    # hyphenated onto an identifier: AGPL-3.0, GPT-4, x86-64, eleven_v3
    if before.endswith(("-", "_")) and before[-2:-1].isalnum():
        return True

    # inside a hex colour: "#0a0a12" is not a claim of 0, 12 and 4
    hex_run = re.search(r"#[0-9a-fA-F]*$", before)
    if hex_run and re.match(r"^[0-9a-fA-F]*\b", text[start:end + 8]):
        prefix = before[hex_run.start():]
        following = re.match(r"^[0-9a-fA-F]*", text[end:]).group(0)
        if 3 <= len(prefix) - 1 + (end - start) + len(following) <= 8:
            return True

    # inside a hashtag: "#qwen35", "#llama3" -- a tag is a name the platform
    # will index, never a statistic, and the model is not free to change it
    if re.search(r"#[\w.-]*$", before):
        return True

    # inside a date or a range: 2024-05-30, 1-3
    if after.startswith("-") and after[1:2].isdigit():
        return True

    # a bare four-digit year, or a year immediately starting a date
    if re.fullmatch(r"(?:19|20)\d\d", token):
        return True

    # v3, version 2, scene 1, #4
    if INDEX_PREFIX_RE.search(before):
        return True

    # a duration or dimension of the reel itself
    if UNIT_SUFFIX_RE.match(after):
        return True
    return False


@dataclass
class NumberFinding:
    value: str
    context: str
    source: str  # "api" | "readme" | "unsourced"

    @property
    def ok(self) -> bool:
        return self.source != "unsourced"

    def as_dict(self) -> dict:
        return {"value": self.value, "context": self.context, "source": self.source}


# --------------------------------------------------- spoken numbers -------
#: Narration spells numbers out, because a TTS engine reads "38K" as "thirty
#: eight kay" and the six shipped scripts all write the words. That put the
#: figures beyond NUMBER_RE entirely: the harness reel says "forty eight
#: thousand stars" over a card reading 38K, and nothing caught it.
_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {"hundred": 100, "thousand": 1_000, "million": 1_000_000,
           "billion": 1_000_000_000}
#: "one point two million" is how the scripts say 1.2M, so "point" has to be
#: part of a run or the phrase parses as the two million it ends with.
_NUM_WORD = set(_UNITS) | set(_TENS) | set(_SCALES) | {"and", "a", "point"}

#: A spoken figure is a rounding of the real one -- "thirty eight thousand" for
#: 38,048 is how a person says it, and rejecting that would reject every script
#: in the repo. Two significant figures is the granularity narration works at.
def _round_sig(value: float, digits: int = 2) -> float:
    if not value:
        return 0.0
    from math import floor, log10
    exponent = digits - 1 - floor(log10(abs(value)))
    return round(value, int(exponent))


def spoken_numbers(text: str) -> list[tuple[str, int]]:
    """Every number written as words, with the value it denotes.

    Returns (phrase, value) so a finding can quote what was actually said.
    """
    words = re.findall(r"[a-z]+(?:-[a-z]+)?", (text or "").lower())
    found: list[tuple[str, int]] = []
    run: list[str] = []

    def whole(parts: list[str]) -> int:
        total = current = 0
        for word in parts:
            for part in word.split("-"):
                if part in _UNITS:
                    current += _UNITS[part]
                elif part in _TENS:
                    current += _TENS[part]
                elif part == "hundred":
                    current = max(current, 1) * 100
                elif part in _SCALES:
                    total += max(current, 1) * _SCALES[part]
                    current = 0
        return total + current

    def flush() -> None:
        if not run:
            return
        phrase = [w for w in run if w not in {"and", "a"}]
        while phrase and phrase[0] == "point":
            phrase.pop(0)
        if not phrase:
            run.clear()
            return

        if "point" in phrase:
            # "one point two million": digits after `point` are the fraction,
            # and a scale word at the end multiplies the whole thing
            head, tail = phrase[:phrase.index("point")], phrase[phrase.index("point") + 1:]
            scale = 1
            while tail and tail[-1] in _SCALES:
                scale *= _SCALES[tail.pop()]
            digits = "".join(str(_UNITS[w]) for w in tail if w in _UNITS)
            value = float(f"{whole(head)}.{digits or 0}") * scale
            total = int(round(value))
        else:
            total = whole(phrase)

        if total:
            found.append((" ".join(w for w in run if w not in {"and"}).strip(), total))
        run.clear()

    for word in words:
        if word in _NUM_WORD or all(p in _NUM_WORD for p in word.split("-")):
            run.append(word)
        else:
            flush()
    flush()
    return found


def check_spoken(text: str, facts: FactsBundle, *,
                 label: str = "") -> list[NumberFinding]:
    """The same provenance rule, applied to numbers written as words.

    Matching is at two significant figures, because narration rounds: "thirty
    eight thousand stars" is a correct way to say 38,048, while "forty eight
    thousand" is not.
    """
    sourced: set[float] = set()
    for raw in list(facts.numeric_vocabulary()) + sorted(readme_vocabulary(facts)):
        value = _as_number(str(raw))
        if value is not None:
            sourced.add(_round_sig(value))

    findings: list[NumberFinding] = []
    for phrase, value in spoken_numbers(text):
        # small numbers are counts of things in the script itself -- "three
        # scenes", "one command" -- not claims about the project
        if value < 100:
            continue
        ok = _round_sig(value) in sourced
        findings.append(NumberFinding(
            value=phrase, context=f"{label}spoken as {phrase!r} (= {value:,})",
            source="api" if ok else "unsourced"))
    return findings


def _as_number(token: str) -> float | None:
    """Read '38K', '3,352', '1.2M', '100+' as a number."""
    raw = token.replace(",", "").replace("+", "").strip().upper()
    multiplier = 1
    if raw and raw[-1] in {"K", "M", "B"}:
        multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[raw[-1]]
        raw = raw[:-1]
    try:
        return float(raw) * multiplier
    except ValueError:
        return None


def _normalise(token: str) -> str:
    return token.replace(",", "").replace(" ", "").upper().strip()


def readme_vocabulary(facts: FactsBundle) -> set[str]:
    """Numbers the project itself states, in its README or model card."""
    text = " ".join(filter(None, [facts.readme_markdown, facts.supplied_markdown]))
    return {_normalise(m.group(0)) for m in NUMBER_RE.finditer(text)}


def check(text: str, facts: FactsBundle, *, label: str = "") -> list[NumberFinding]:
    api = {_normalise(v) for v in facts.numeric_vocabulary()}
    readme = readme_vocabulary(facts)
    findings: list[NumberFinding] = []

    for match in NUMBER_RE.finditer(text or ""):
        raw = match.group(0)
        start, end = match.span()
        if _is_structural(text, start, end, raw):
            continue
        context = " ".join(text[max(0, start - 36) : end + 36].split())
        # fold a spelled scale word into the number: "1.4 million" -> "1.4M",
        # which is the form the vocabulary holds
        scale = SCALE_WORD_RE.match(text[end:])
        token = _normalise(raw + (SCALE_SUFFIX[scale.group(1).lower()] if scale else ""))
        if token in api:
            source = "api"
        elif token in readme:
            source = "readme"
        else:
            source = "unsourced"
        findings.append(NumberFinding(value=raw, context=f"{label}{context}", source=source))
    return findings


def unsourced(findings: list[NumberFinding]) -> list[NumberFinding]:
    return [f for f in findings if not f.ok]


def report(findings: list[NumberFinding]) -> dict:
    bad = unsourced(findings)
    return {
        "total": len(findings),
        "api": sum(1 for f in findings if f.source == "api"),
        "readme": sum(1 for f in findings if f.source == "readme"),
        "unsourced": [f.as_dict() for f in bad],
        "ok": not bad,
    }


#: How hard the provenance rule bites. It is one policy for a whole job, read
#: by every validator in the content stage, so it lives here rather than being
#: threaded through eight signatures that do not otherwise care.
#:
#:   strict  an unsourced number is a problem: the draft goes back to the model
#:   warn    the draft passes; `report()` still records what did not trace, and
#:           the content gate shows it
#:   off     not checked at all
_MODE: ContextVar[str] = ContextVar("fact_check_mode", default="strict")

MODES = ("strict", "warn", "off")


@contextmanager
def mode(value: str):
    """Apply a fact-checking mode to everything in this call tree."""
    if value not in MODES:
        raise ValueError(f"fact_check must be one of {MODES}, got {value!r}")
    token = _MODE.set(value)
    try:
        yield
    finally:
        _MODE.reset(token)


def current_mode() -> str:
    return _MODE.get()


def repair_hint(findings: list[NumberFinding],
                facts: FactsBundle | None = None) -> str:
    """The message fed back to the model when numbers do not trace.

    Empty outside strict mode: `warn` and `off` both let the draft through, and
    this string is precisely what turns a finding into a rejection.
    """
    if _MODE.get() != "strict":
        return ""
    bad = unsourced(findings)
    if not bad:
        return ""
    lines = [
        "These numbers appear in your output but are in neither the FACTS block "
        "nor the project's own README. Remove each one, or replace it with a "
        "real figure from the list below:",
    ]
    for finding in bad[:12]:
        lines.append(f'  {finding.value!r}  in: "...{finding.context}..."')

    # Without this the instruction was "replace them with a figure that is:"
    # followed by the wrong numbers -- the model was told what not to say and
    # never what to say, and burned three attempts writing 1.3 million for a
    # 1.4 million figure it could not see.
    figures = facts.headline_figures() if facts else []
    if figures:
        lines.append("")
        lines.append("The real figures, which are the only ones you may use:")
        for label, value in figures:
            lines.append(f"  {value} {label}")
    return "\n".join(lines)
