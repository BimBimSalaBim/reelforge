"""Generate the kit/sbkit API reference the code-writing model is given.

Extracted with `inspect` from the modules themselves rather than written by
hand, so it cannot drift from the code the generated storyboard will actually
run against. A stale API reference is the most expensive kind of prompt bug:
the model writes something plausible, it fails at render time, and the repair
loop spends its whole budget rediscovering the real signature.
"""
from __future__ import annotations

import inspect
from functools import lru_cache
from pathlib import Path

from app.config import get_config

#: Ordered so the model reads the canvas constants before anything positional.
KIT_GROUPS = [
    ("canvas and safe areas", ["W", "H", "FPS", "MARGIN", "TOP_SAFE", "BOT_SAFE", "CAP_Y"]),
    ("fonts", ["f", "m", "set_fonts", "probe_glyphs"]),
    ("palette", ["set_palette", "rgba", "mix"]),
    ("easing", ["clamp", "lin", "eo3", "eo4", "ei3", "eio", "eob", "pulse"]),
    ("text", ["tw", "text", "grad_text", "wrap"]),
    ("shapes", ["card", "pill", "hline"]),
    ("glow", ["radial", "glow", "put_glow"]),
]
SBKIT_ORDER = [
    "Theme", "build_base", "chrome", "cut_sweep", "scrim", "captions",
    "enter", "eyebrow", "statcard", "tile", "terminal", "counter", "bar", "endcard",
]


def _load_modules():
    import sys

    video = str(get_config().paths.video)
    if video not in sys.path:
        sys.path.insert(0, video)
    import kit
    import sbkit

    return kit, sbkit


def _signature(name: str, obj) -> str:
    try:
        return f"{name}{inspect.signature(obj)}"
    except (TypeError, ValueError):
        return name


def _first_doc_line(obj) -> str:
    doc = inspect.getdoc(obj) or ""
    return " ".join(doc.split("\n")[0].split())[:150]


def _render_callable(name: str, obj) -> str:
    line = _signature(name, obj)
    doc = _first_doc_line(obj)
    return f"  {line}" + (f"\n      {doc}" if doc else "")


@lru_cache(maxsize=1)
def api_reference() -> str:
    kit, sbkit = _load_modules()
    out: list[str] = ["MODULE kit -- canvas, palette, fonts, easing, drawing primitives", ""]

    for title, names in KIT_GROUPS:
        out.append(f"  # {title}")
        for name in names:
            obj = getattr(kit, name, None)
            if obj is None:
                continue
            if callable(obj):
                out.append(_render_callable(name, obj))
            else:
                out.append(f"  {name} = {obj!r}")
        out.append("")

    out += ["", "MODULE sbkit -- the component library. Import as `import sbkit as S`.", ""]
    for name in SBKIT_ORDER:
        obj = getattr(sbkit, name, None)
        if obj is None:
            continue
        if inspect.isclass(obj):
            signature = _signature(name, obj.__init__).replace("__init__", name, 1)
            out.append("  " + signature.replace("(self, ", "(").replace("(self)", "()"))
            # the class docstring, not __init__'s "Initialize self" boilerplate
            doc = _first_doc_line(obj)
            if doc and not doc.startswith("Initialize self"):
                out.append(f"      {doc}")
            methods = [n for n, _ in inspect.getmembers(obj, inspect.isfunction)
                       if not n.startswith("_")]
            if methods:
                out.append(f"      methods: {', '.join(methods)}")
            if name == "Theme":
                out.append(f"      attributes after construction: {theme_attributes()}")
                out.append("      note: the constructor parameter is `cardc` but the "
                           "attribute is `TH.card`")
        else:
            out.append(_render_callable(name, obj))
    return "\n".join(out)


@lru_cache(maxsize=1)
def theme_attributes() -> str:
    _, sbkit = _load_modules()
    theme = sbkit.Theme(bg=(0, 0, 0), accent=(1, 1, 1), accent_hi=(2, 2, 2),
                        pale=(3, 3, 3), glow=(4, 4, 4), support=(5, 5, 5))
    names = sorted(k for k in vars(theme) if not k.startswith("_"))
    return ", ".join(f"TH.{n}" for n in names)


#: Worked examples ship with the app. They are read as text and pasted into the
#: prompt, never imported -- so they are application assets, not reel output.
EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "templates" / "examples"


def example_storyboard(name: str = "ruflo") -> str:
    path = EXAMPLE_DIR / f"{name}.py"
    if path.exists():
        return path.read_text(encoding="utf-8")
    # A working copy that still has the original renderer's storyboards.
    legacy = get_config().paths.video / "storyboards" / f"{name}.py"
    return legacy.read_text(encoding="utf-8") if legacy.exists() else ""
