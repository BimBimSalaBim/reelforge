"""Repoint kit.f / kit.m at bundled OSS faces.

`video/kit.py` loads Helvetica Neue and Menlo from absolute macOS paths, by
`.ttc` collection index. Neither ships in a Linux container and neither is
redistributable, so the render shim replaces `kit.f` and `kit.m` outright with
loaders over per-weight files.

Replacing the functions rather than calling `kit.set_fonts` is deliberate:
`set_fonts` keeps the one-file-plus-index model, which per-weight `.ttf` files do
not fit. Because storyboards and `sbkit` do `from kit import f, m` at import
time, the patch must be applied *before* either is imported -- which is what the
shims do.

Face choice:
  display -- Inter. The closest widely-available OSS face to Helvetica Neue.
  mono    -- DejaVu Sans Mono. Menlo descends from Bitstream Vera Sans Mono,
             which is DejaVu's direct ancestor, so this is the nearest relative
             rather than merely a substitute. It also carries every symbol the
             storyboards draw; JetBrains Mono looks sharper in terminal blocks
             but is missing the rotate and star glyphs, which render as silent
             empty boxes (DEVELOPMENT.md gotcha 3).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import get_config

#: kit's display weight names -> Inter static faces. Inter has no condensed cut,
#: so "cbold" maps to the nearest heavier upright weight.
DISPLAY_FACES = {
    "reg": "Inter-Regular.ttf",
    "bold": "Inter-Bold.ttf",
    "cbold": "Inter-ExtraBold.ttf",
    "cblack": "Inter-Black.ttf",
    "med": "Inter-Medium.ttf",
    "light": "Inter-Light.ttf",
    "thin": "Inter-Thin.ttf",
    "ultra": "Inter-ExtraBold.ttf",
}
MONO_FAMILIES = {
    "DejaVuSansMono": {"reg": "DejaVuSansMono.ttf", "bold": "DejaVuSansMono-Bold.ttf"},
    "JetBrainsMono": {"reg": "JetBrainsMono-Regular.ttf", "bold": "JetBrainsMono-Bold.ttf"},
}

#: Every non-ASCII glyph the existing storyboards, sbkit and covers actually
#: draw. A face missing one of these produces an empty box and raises nothing,
#: so the mono face is asserted against this set at startup.
SYMBOL_GLYPHS = "·—…›→↓↻★☆✓✕⚠●"


class FontsUnavailable(RuntimeError):
    pass


def font_dir() -> Path:
    return get_config().fonts.dir_path()


def mono_faces(family: str | None = None) -> dict[str, str]:
    family = family or get_config().fonts.mono_family
    if family not in MONO_FAMILIES:
        raise FontsUnavailable(
            f"unknown mono family {family!r}; known: {', '.join(MONO_FAMILIES)}"
        )
    return MONO_FAMILIES[family]


def resolve(
    directory: Path | None = None, family: str | None = None
) -> tuple[dict[str, str], dict[str, str]]:
    directory = directory or font_dir()
    mono_table = mono_faces(family)
    wanted = set(DISPLAY_FACES.values()) | set(mono_table.values())
    missing = sorted(name for name in wanted if not (directory / name).exists())
    if missing:
        raise FontsUnavailable(
            f"missing {len(missing)} font file(s) in {directory}: "
            f"{', '.join(missing[:4])}{' ...' if len(missing) > 4 else ''}. "
            "Run docker/fetch-fonts.sh"
        )
    display = {w: str(directory / n) for w, n in DISPLAY_FACES.items()}
    mono = {w: str(directory / n) for w, n in mono_table.items()}
    return display, mono


def available(directory: Path | None = None, family: str | None = None) -> bool:
    try:
        resolve(directory, family)
        return True
    except FontsUnavailable:
        return False


def patch_kit(
    kit: Any,
    directory: Path | None = None,
    family: str | None = None,
    *,
    strict: bool = True,
) -> bool:
    """Swap kit.f / kit.m for bundled-face loaders.

    Returns True if patched. With `strict=False`, a missing font directory leaves
    the macOS faces in place -- useful when running natively on the machine the
    original reels were built on.
    """
    from PIL import ImageFont

    try:
        display, mono = resolve(directory, family)
    except FontsUnavailable:
        if strict:
            raise
        return False

    cache: dict[tuple[str, str, int], Any] = {}

    def _load(table: dict[str, str], kind: str, size: int, weight: str):
        path = table.get(weight) or table["reg"]
        key = (kind, weight, int(size))
        if key not in cache:
            cache[key] = ImageFont.truetype(path, int(size))
        return cache[key]

    def f(size, w: str = "bold"):
        return _load(display, "disp", size, w)

    def m(size, w: str = "reg"):
        return _load(mono, "mono", size, w)

    kit.f = f
    kit.m = m
    kit.HN = display["reg"]
    kit.MN = mono["reg"]
    kit._fc = cache
    return True


def check_symbols(
    kit: Any, directory: Path | None = None, family: str | None = None
) -> dict[str, str]:
    """Assert the mono face carries every symbol the storyboards draw.

    Uses kit's own `probe_glyphs`, so this checks exactly what PIL will do at
    render time rather than what the font's cmap claims.
    """
    _, mono = resolve(directory, family)
    result = kit.probe_glyphs(mono["reg"], 0, SYMBOL_GLYPHS)
    missing = [ch for ch, state in result.items() if state != "OK"]
    if missing:
        raise FontsUnavailable(
            f"mono face {Path(mono['reg']).name} cannot render {''.join(missing)} -- "
            "these would draw as empty boxes with no error (DEVELOPMENT.md gotcha 3)"
        )
    return result
