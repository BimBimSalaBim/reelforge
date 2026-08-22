"""Measure cover text against the fonts that will actually draw it.

`covers.py` auto-shrinks some strings to fit and draws others at a fixed size.
The fixed ones -- the kicker, the hook lines, the footers -- simply clip when
they are too wide, with no error. Character-count limits are a poor proxy
because they depend on the typeface: the shipped covers were laid out in
Helvetica Neue, and Inter sets the same words wider, so a string that fit before
can overflow now.

This measures with the real patched fonts, so it is the same arithmetic the
renderer will do.
"""
from __future__ import annotations

W, MARGIN = 1080, 84

#: (spec key, font spec, available width, label) for every fixed-size string.
#: Sizes and positions mirror video/covers.py's layout.
FIXED_TEXTS = [
    ("kicker", ("disp", 40, "med"), W - 2 * MARGIN, "kicker"),
    ("eyebrow", ("disp", 30, "bold"), W - 2 * MARGIN - 120, "eyebrow pill"),
    ("foot_l", ("mono", 24, "reg"), (W - 2 * MARGIN) / 2 - 20, "left footer"),
    ("foot_r", ("mono", 24, "reg"), (W - 2 * MARGIN) / 2 - 20, "right footer"),
]
HOOK_FONT = ("disp", 78, "bold")
#: The wordmark is the largest thing on the cover and `covers.py` draws it
#: centred at whatever size the spec names, with no shrink-to-fit. A
#: hand-written spec chose a short name ("ecc", "ruflo"); a generated one
#: supplied "Harness Open Source" and it ran off both edges. Measuring it was
#: missing from this list entirely, which is why nothing caught that.
WORDMARK_AVAIL = W - 2 * MARGIN


def fit_mark_size(kit, wordmark: str, kind: str, start: int,
                  floor: int = 80, track: int = 0) -> int:
    """Largest size at or below `start` where the wordmark fits the safe width."""
    size = int(start)
    while size > floor:
        font = kit.m(size, "bold") if kind == "mono" else kit.f(size, "bold")
        if kit.tw(wordmark, font, track) <= WORDMARK_AVAIL:
            return size
        size -= 4
    return floor


def measure(kit, spec: dict) -> list[dict]:
    """Return one entry per string that will not fit."""
    def font(kind: str, size: int, weight: str):
        return kit.m(size, weight) if kind == "mono" else kit.f(size, weight)

    problems: list[dict] = []

    for key, (kind, size, weight), avail, label in FIXED_TEXTS:
        value = str(spec.get(key) or "")
        if not value:
            continue
        width = kit.tw(value, font(kind, size, weight), 6 if key == "eyebrow" else 0)
        if width > avail:
            problems.append({
                "field": key, "label": label, "text": value,
                "width": round(width), "available": round(avail),
                "overflow_px": round(width - avail),
                "suggest_max_chars": max(4, int(len(value) * avail / width) - 1),
            })

    for index, line in enumerate(spec.get("hook") or []):
        if not line:
            continue
        width = kit.tw(line, font(*HOOK_FONT), 0)
        avail = W - 2 * MARGIN
        if width > avail:
            problems.append({
                "field": f"hook[{index}]", "label": f"hook line {index + 1}",
                "text": line, "width": round(width), "available": round(avail),
                "overflow_px": round(width - avail),
                "suggest_max_chars": max(4, int(len(line) * avail / width) - 1),
            })

    wordmark = str(spec.get("wordmark") or "")
    if wordmark:
        kind, size = spec.get("mark_font", ("disp", 180))
        track = spec.get("mark_track", 0) or 0
        mark_font = font(kind, int(size), "bold")
        width = kit.tw(wordmark, mark_font, track)
        if width > WORDMARK_AVAIL:
            fitted = fit_mark_size(kit, wordmark, kind, int(size), track=track)
            problems.append({
                "field": "wordmark", "label": "wordmark", "text": wordmark,
                "width": round(width), "available": round(WORDMARK_AVAIL),
                "overflow_px": round(width - WORDMARK_AVAIL),
                "suggest_max_chars": max(3, int(len(wordmark) * WORDMARK_AVAIL / width)),
                "suggest_size": fitted,
            })

    # covers.py picks the stat size from the character count and then draws it,
    # with no shrink-to-fit -- so a wide value at 52px simply overflows its card.
    card_width = (W - 2 * MARGIN - 32) / 3
    stat_avail = card_width - 24
    for value, label in spec.get("stats") or []:
        size = 64 if len(value) <= 4 else 52
        width = kit.tw(value, font("disp", size, "bold"), 0)
        if width > stat_avail:
            problems.append({
                "field": "stats", "label": f"stat value {value!r}",
                "text": value, "width": round(width),
                "available": round(stat_avail),
                "overflow_px": round(width - stat_avail),
                # measured, not guessed: an earlier version hardcoded 5, which
                # would have cut "Apache-2.0" to "Apach"
                "suggest_max_chars": max(2, int(len(value) * stat_avail / width)),
            })
    return problems


def describe(problems: list[dict]) -> str:
    """The message handed back to the model, in its own terms."""
    if not problems:
        return ""
    lines = ["These cover strings are too wide for their space and would be "
             "clipped. Shorten them:"]
    for problem in problems:
        lines.append(
            f"  {problem['label']}: {problem['text']!r} is {problem['overflow_px']}px "
            f"too wide. Keep it to about {problem['suggest_max_chars']} characters."
        )
    return "\n".join(lines)


def measure_spec(spec: dict) -> list[dict]:
    """Measure without a subprocess.

    Safe to call from a worker: this imports `kit` and patches its font loaders,
    but never imports a storyboard, so the one-storyboard-per-process rule that
    `kit.set_palette` imposes is not in play.
    """
    import sys

    from app.config import get_config

    video = str(get_config().paths.video)
    if video not in sys.path:
        sys.path.insert(0, video)
    try:
        import kit

        from app.render.fonts import patch_kit

        patch_kit(kit, strict=False)
        return measure(kit, spec)
    except Exception:
        # measurement is a refinement; never fail generation because of it
        return []


def unrenderable(kit, strings: dict[str, str]) -> list[dict]:
    """Find text the display font cannot draw.

    A quantised model leaked a CJK character into a fact-sheet label -- the row
    read "Programming语言". Inter has no CJK coverage, so that draws as empty
    boxes with no error, which is exactly the failure DEVELOPMENT.md's gotcha 3 is
    about. Latin-1 plus the symbol set the storyboards use is what the bundled
    faces actually cover.
    """
    problems: list[dict] = []
    cache: dict[str, bool] = {}

    for label, value in strings.items():
        if not value:
            continue
        bad = []
        for char in dict.fromkeys(value):
            if char.isascii() or char in SYMBOL_SET:
                continue
            if char not in cache:
                probe = kit.probe_glyphs(kit.HN, 0, char)
                cache[char] = probe.get(char) == "OK"
            if not cache[char]:
                bad.append(char)
        if bad:
            problems.append({"field": label, "text": value,
                             "characters": "".join(bad)})
    return problems


#: Non-ASCII the bundled faces are known to carry.
SYMBOL_SET = set("·—…›→↓↻★☆✓✕⚠●–‘’“”")


def describe_unrenderable(problems: list[dict]) -> str:
    if not problems:
        return ""
    lines = ["This text contains characters the display font cannot draw. They "
             "would appear as empty boxes on screen. Use ASCII only:"]
    for problem in problems:
        lines.append(f"  {problem['field']}: {problem['text']!r} contains "
                     f"{problem['characters']!r}")
    return "\n".join(lines)


def check_renderable(strings: dict[str, str]) -> list[dict]:
    """As `unrenderable`, importing and patching kit lazily."""
    import sys

    from app.config import get_config

    video = str(get_config().paths.video)
    if video not in sys.path:
        sys.path.insert(0, video)
    try:
        import kit

        from app.render.fonts import patch_kit

        patch_kit(kit, strict=False)
        return unrenderable(kit, strings)
    except Exception:
        return []
