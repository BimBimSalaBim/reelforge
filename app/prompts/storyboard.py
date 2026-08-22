"""The storyboard code-generation prompt.

The model is asked to write a real Python module against `sbkit`, not to fill in
a template. What makes that work is not cleverness in the instructions -- it is
giving it the exact API (extracted from the modules, so it cannot drift), the
exact vocabulary of words it may cue off, and the specific mistakes that this
codebase has actually made before.

The gotchas below are not general advice. Every one of them is a bug that was
shipped, found by looking at frames, and written down in DEVELOPMENT.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.models.content import ReelContent
from app.prompts.api_reference import api_reference, example_storyboard

SYSTEM = """\
You write one Python module: a storyboard for a 1080x1920 vertical video. It is \
imported by a renderer that calls `frame(t)` for every frame and pipes the \
result to ffmpeg.

Output the module source and nothing else. No prose, no markdown fence, no \
explanation before or after.

THE CONTRACT. The module must define, at module level:

    NAME     str, the timing key -- use exactly the slug you are given
    AUDIO    str, path to the narration, relative to the repo root
    PHRASES  str, path to the phrase list, relative to the video directory
    TOTAL    float, the video's length in seconds -- use exactly the value given
    FPS      int, 30
    SFX      list of sound events
    frame(t) -> a PIL RGBA Image, exactly 1080x1920

HOW THESE ARE BUILT. Copy the shape of the worked example. A theme, a ground \
plate built once at import, a scene table, a dispatcher, one function per scene \
taking (ov, d, t, t0), then chrome, cut_sweep and captions applied to every \
frame.
{captions_rule}

TIME IS ALWAYS ABSOLUTE SECONDS of the finished video, and every visual beat is \
keyed off a spoken word: `ws("federation")`, `we("done.")`. Never hardcode a \
number you could look up. `ws` and `we` raise KeyError if the word was not \
spoken, so use only words from the vocabulary you are given.

THE MISTAKES THIS CODEBASE HAS ACTUALLY MADE -- do not repeat them:

1. ImageDraw does not alpha-blend, it replaces pixels. A translucent full-frame \
rectangle drawn with `d.rectangle` erases everything already in that layer. Use \
`S.scrim(ov, a)` or composite a new image. Small shapes drawn before their \
contents -- card fills, pills -- are fine.
2. Z-order is layer order, not call order. `grad_text` and `put_glow` composite \
into the image passed as their first argument, while `d.*` draws into the \
overlay. Mixing them silently puts gradients behind card fills. Draw everything \
into `ov` so call order is z-order.
3. The display face has no check, cross or arrow glyphs. They render as empty \
boxes with no error. Use `m()` for any of these characters, or draw them with \
lines.
4. Never index the word list by a scene-local index. `WORDS[0]` is the first \
word of the whole narration, not of your scene. Use `ws("word")`.
5. Cut on the narration, not on round numbers. A scene boundary that lands just \
before the line paying it off leaves text on screen for a tenth of a second. \
Take every scene boundary from a word time.
6. Reveal order follows the spoken order, not the diagram's logic. If the \
narration says "identity verified, personal data stripped", light those two up \
in that order even if the wire order is the reverse.

WHAT MAKES THESE VIDEOS WORK:

- The hook is fully on screen at t=0. No logo intro, no fade up.
- A cut every 2-4 seconds. If a layout must hold longer, give it an event every \
1-2 seconds inside the hold.
- One idea per screen, and let information accumulate rather than replacing it.
- Give the differentiating claim a physical beat -- one thing that lands hard on \
the word that matters.
- Everything meaningful stays inside y 150-1600 and x 84-996. The platform's UI \
covers the rest. Captions are drawn for you at y 1498.
- End on a save prompt.

SOUND. `SFX` is a list of plain dicts. One `swish` 0.30 s before each cut, one \
`thump` on the cut itself, a `tick` on discrete beats:

    {"t": 12.4, "kind": "swish", "amp": 0.22, "dur": 0.30}
    {"t": 12.7, "kind": "thump", "amp": 0.30, "dur": 0.55, "freq": 46.0}
    {"t": 18.1, "kind": "tick",  "amp": 0.16, "dur": 0.05, "tone": 2100.0}

kind is one of thump, swish, tick, sweep. Nothing else is accepted."""


def build_storyboard_prompt(
    content: ReelContent,
    timing_json: Path,
    *,
    total: float,
    audio_rel: str,
    phrases_rel: str,
    template_example: str = "",
    repair_notes: str = "",
    max_example_lines: int = 300,
    captions: bool = True,
) -> tuple[str, str]:
    timing = json.loads(timing_json.read_text())
    phrases = timing["phrases"]
    segments = timing["segments"]

    phrase_table = "\n".join(
        f"  {start:6.2f} - {end:6.2f}   {text}"
        for (start, end), text in zip(segments, phrases)
    )
    word_table = "\n".join(
        "  " + "  ".join(f"{w['w']}@{w['s']:.2f}" for w in timing["words"][i:i + 6])
        for i in range(0, len(timing["words"]), 6)
    )
    scene_plan = "\n".join(
        f"  Scene {s.index} -- {s.title}\n"
        f"    says    : {s.you_say}\n"
        f"    onscreen: {s.on_screen}"
        for s in content.scenes
    )
    facts = "\n".join(f"  {r.label:<14} {r.value}" for r in content.fact_sheet)

    # The worked example dominates this prompt -- ruflo.py is 276 lines, around
    # 3,000 tokens of the ~6,000 total. On a small-context model that is the
    # difference between fitting and not, so the caller can ask for less of it.
    example = template_example or example_storyboard("ruflo")
    example_lines = example.splitlines()
    if len(example_lines) > max_example_lines:
        head = max_example_lines * 2 // 3
        tail = max_example_lines - head
        example = ("\n".join(example_lines[:head])
                   + "\n\n# ... middle of the file omitted ...\n\n"
                   + "\n".join(example_lines[-tail:]))

    theme = content.theme
    user = f"""\
Write the storyboard for "{content.display_name}".

{"=" * 68}
THE CONTRACT VALUES -- use these exactly
{"=" * 68}
NAME    = {content.slug!r}
AUDIO   = {audio_rel!r}
PHRASES = {phrases_rel!r}
TOTAL   = {total}
FPS     = 30

{"=" * 68}
THE PALETTE -- already chosen, matching the cover art
{"=" * 68}
TH = S.Theme(bg={tuple(theme.bg)}, accent={tuple(theme.accent)},
             accent_hi={tuple(theme.accent_hi)}, pale={tuple(theme.pale)},
             glow={tuple(theme.glow)}, support={tuple(theme.support)})
TH.apply()
BASE = S.build_base(TH, seed={theme.base_seed}, bloom={theme.base_bloom})

{"=" * 68}
THE NARRATION, ALIGNED -- scene boundaries must come from these times
{"=" * 68}
{phrase_table}

{"=" * 68}
EVERY WORD YOU MAY CUE OFF, with its start time
  ws()/we() raise KeyError on anything not in this list.
{"=" * 68}
{word_table}

{"=" * 68}
THE SCENE PLAN
{"=" * 68}
{scene_plan}

{"=" * 68}
FACTS AVAILABLE FOR ON-SCREEN TEXT
  Do not put a number on screen that is not here.
{"=" * 68}
{facts}

{"=" * 68}
THE API YOU ARE WRITING AGAINST
{"=" * 68}
{api_reference()}

{"=" * 68}
A COMPLETE WORKED EXAMPLE -- follow this structure
{"=" * 68}
{example}
"""
    if repair_notes:
        user += f"""
{"=" * 68}
YOUR PREVIOUS ATTEMPT WAS REJECTED. FIX EXACTLY THESE PROBLEMS.
Return the complete corrected module, not a patch.
{"=" * 68}
{repair_notes}
"""
    system = SYSTEM.replace("{captions_rule}", CAPTIONS_ON if captions else CAPTIONS_OFF)
    return system, user


#: Burned-in captions carry a muted autoplay, which is how most reels are first
#: watched -- but every major platform now auto-captions on upload, so a job can
#: reasonably decline them. The renderer must be told either way: `S.captions`
#: draws over the lower third, and a storyboard that assumes it is there will
#: leave that band empty when it is not.
CAPTIONS_ON = """\
Call `S.captions(ov, d, t, CH, TH)` on every frame. Captions occupy the lower \
third, so keep scene content above y 1500."""

CAPTIONS_OFF = """\
DO NOT call `S.captions`. This video ships without burned-in captions, so the \
lower third is yours -- but nothing may rely on caption text to make sense, and \
every claim must be legible on screen without it."""

VISION_SYSTEM = """\
You are reviewing frames from a vertical video for defects a renderer cannot \
detect. Be specific and concrete; say which frame and what is wrong.

Report only real problems:
- text that overlaps other text, or is clipped by the frame edge
- text too small or too low-contrast to read on a phone
- a frame that is empty or nearly empty when it should carry a scene
- elements that collide or sit on top of each other
- anything important close to the top or bottom edges, where the app's own UI sits

Do not comment on taste, colour preference, or wording. If the frames look \
correct, say so plainly."""


def build_vision_prompt(times: list[float]) -> str:
    listing = ", ".join(f"{t:.2f}s" for t in times)
    return (
        f"These are frames at {listing} from a 1080x1920 vertical video, in order.\n"
        "Identify any rendering defect from the list you were given. If there is "
        "none, reply exactly: NO DEFECTS."
    )
