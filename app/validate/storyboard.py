"""Static checks on a generated storyboard, before anything executes.

These run on the AST alone. They are cheap, they never run the code, and rung 4
in particular catches the failure this design is most exposed to.

`Timing.ws(word)` raises `KeyError` when a word is not in the narration, and it
does so deliberately -- a typo would otherwise be a silent mistiming. A model
writing a storyboard binds visual beats to literal words from the script
(`ws("auditable.")`), and the single most likely thing it gets wrong is naming a
word that was never spoken. Finding that statically costs milliseconds; finding
it at render time costs a chunk render and a full repair round.
"""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path

#: Modules a storyboard legitimately needs. Anything else is either a mistake or
#: something that has no business in a drawing routine.
ALLOWED_IMPORTS = {
    "math", "os", "sys", "random", "colorsys", "itertools", "functools",
    "numpy", "PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFilter", "PIL.ImageFont",
    "kit", "sbkit", "ledger", "slab", "timing",
}
#: Names that make a drawing routine something other than a drawing routine.
FORBIDDEN_NAMES = {
    "eval", "exec", "compile", "__import__", "globals", "locals", "vars",
    "getattr", "setattr", "delattr", "input", "breakpoint", "memoryview",
}
FORBIDDEN_ATTRS = {"system", "popen", "spawn", "fork", "execv", "remove", "unlink",
                   "rmdir", "rmtree", "chmod", "kill"}
REQUIRED_NAMES = {"NAME", "AUDIO", "PHRASES", "TOTAL", "FPS", "SFX", "frame"}
#: Functions whose string arguments must be words that were actually spoken.
CUE_FUNCS = {"ws", "we", "wstart", "wend", "index"}


@dataclass
class Problem:
    rung: str
    message: str

    def __str__(self) -> str:
        return f"[{self.rung}] {self.message}"


@dataclass
class StaticReport:
    problems: list[Problem] = field(default_factory=list)
    cue_words: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def messages(self) -> list[str]:
        return [str(p) for p in self.problems]

    def as_dict(self) -> dict:
        return {"ok": self.ok, "problems": self.messages(),
                "cue_words": self.cue_words, "imports": self.imports}


def _module_root(node: ast.AST) -> str:
    if isinstance(node, ast.Import):
        return ""
    return ""


def check_source(source: str, timing_json: Path | None = None) -> StaticReport:
    report = StaticReport()

    # ---- rung 1: it must parse -----------------------------------------
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        report.problems.append(Problem(
            "syntax",
            f"line {exc.lineno}: {exc.msg}\n"
            f"    {(exc.text or '').rstrip()}"
        ))
        return report

    # ---- rung 2: imports and dangerous names ---------------------------
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                report.imports.append(alias.name)
                if root not in ALLOWED_IMPORTS and alias.name not in ALLOWED_IMPORTS:
                    report.problems.append(Problem(
                        "imports",
                        f"line {node.lineno}: `import {alias.name}` is not allowed. "
                        f"A storyboard may import only: {', '.join(sorted(ALLOWED_IMPORTS))}."
                    ))
        elif isinstance(node, ast.ImportFrom):
            name = node.module or ""
            root = name.split(".")[0]
            report.imports.append(name)
            if root and root not in ALLOWED_IMPORTS and name not in ALLOWED_IMPORTS:
                report.problems.append(Problem(
                    "imports",
                    f"line {node.lineno}: `from {name} import ...` is not allowed. "
                    f"A storyboard may import only: {', '.join(sorted(ALLOWED_IMPORTS))}."
                ))
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            report.problems.append(Problem(
                "unsafe", f"line {node.lineno}: `{node.id}` is not allowed in a storyboard."
            ))
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRS:
            report.problems.append(Problem(
                "unsafe", f"line {node.lineno}: `.{node.attr}(...)` is not allowed."
            ))
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open":
                report.problems.append(Problem(
                    "unsafe",
                    f"line {node.lineno}: a storyboard must not open files. "
                    "Everything it needs is already imported."
                ))

    # ---- rung 3: the module contract -----------------------------------
    assigned = {
        target.id
        for node in tree.body if isinstance(node, ast.Assign)
        for target in node.targets if isinstance(target, ast.Name)
    }
    defined = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    missing = REQUIRED_NAMES - assigned - defined
    if missing:
        report.problems.append(Problem(
            "contract",
            f"module is missing {sorted(missing)}. Every storyboard must define "
            "NAME, AUDIO, PHRASES, TOTAL, FPS, SFX and frame(t)."
        ))
    if "frame" in defined:
        func = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "frame")
        args = [a.arg for a in func.args.args]
        if args != ["t"]:
            report.problems.append(Problem(
                "contract",
                f"frame() takes {args}, but the renderer calls frame(t) with a single "
                "float: seconds from the start of the video."
            ))

    # ---- rung 4: every cue word must have been spoken -------------------
    cues = collect_cue_words(tree)
    report.cue_words = sorted({c for c, _ in cues})
    if timing_json and timing_json.exists():
        spoken = spoken_words(timing_json)
        for word, lineno in cues:
            if _normalise(word) not in spoken:
                near = _closest(_normalise(word), spoken)
                hint = f" Did you mean {near!r}?" if near else ""
                report.problems.append(Problem(
                    "cue-word",
                    f"line {lineno}: ws()/we() was given {word!r}, which is not a word "
                    f"in the narration. Timing lookups raise KeyError on a miss, so "
                    f"this would crash at render time.{hint}"
                ))
    return report


def collect_cue_words(tree: ast.AST) -> list[tuple[str, int]]:
    """Every literal string handed to a timing lookup, with its line number."""
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (func.id if isinstance(func, ast.Name)
                else func.attr if isinstance(func, ast.Attribute) else None)
        if name not in CUE_FUNCS:
            continue
        for arg in node.args[:1]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                found.append((arg.value, node.lineno))
    return found


def spoken_words(timing_json: Path) -> set[str]:
    data = json.loads(timing_json.read_text())
    return {_normalise(w["w"]) for w in data.get("words", [])}


def _normalise(word: str) -> str:
    """Match Timing._hits: lowercase, strip surrounding punctuation."""
    return word.lower().strip('.,:;!?')


def _closest(word: str, options: set[str]) -> str | None:
    import difflib

    matches = difflib.get_close_matches(word, sorted(options), n=1, cutoff=0.72)
    return matches[0] if matches else None


# --------------------------------------------------------------- repair ----
#: Contract names with an obvious default. A storyboard that forgot `SFX`
#: is not broken -- it simply has no sound design, which is a valid video.
#: Rejecting it spends a whole generation on a line anyone can write.
_DEFAULTS = {
    "SFX": "SFX = []",
    "FPS": "FPS = 30",
}


def autofix(source: str, timing_json: Path | None = None) -> tuple[str, list[str]]:
    """Repair what can be repaired without asking the model again.

    Two classes are worth fixing here rather than in a repair round:

    * a missing contract constant that has one sensible value
    * a cue word that is close to a word which *was* spoken -- the model heard
      the narration correctly and mistyped the lookup, and the nearest match is
      already computed for the error message

    Anything requiring judgment, a syntax error above all, is left alone.
    Returns the repaired source and a note of what changed.
    """
    notes: list[str] = []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source, notes          # nothing safe to do with unparseable code

    assigned = {
        target.id
        for node in tree.body if isinstance(node, ast.Assign)
        for target in node.targets if isinstance(target, ast.Name)
    }
    additions = [line for name, line in _DEFAULTS.items() if name not in assigned]
    if additions:
        source = source.rstrip() + "\n\n" + "\n".join(additions) + "\n"
        notes.append("added " + ", ".join(a.split(" =")[0] for a in additions))

    if timing_json and timing_json.exists():
        spoken = spoken_words(timing_json)
        replaced: list[str] = []
        for word, _lineno in collect_cue_words(ast.parse(source)):
            if _normalise(word) in spoken:
                continue
            near = _closest(_normalise(word), spoken)
            if not near:
                continue
            # keep the original trailing punctuation: ws("done.") and ws("done")
            # are equivalent to Timing, and the script reads better with it
            for quote in ('"', "'"):
                source = source.replace(f"{quote}{word}{quote}",
                                        f"{quote}{near}{quote}")
            replaced.append(f"{word!r}->{near!r}")
        if replaced:
            notes.append("corrected cue word(s) " + ", ".join(replaced))

    return source, notes
