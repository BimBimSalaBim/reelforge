"""Everything the LLM produces for one reel, as validated structure.

The shape mirrors the Gen-2 script format already in the repo (`ruflo.txt`,
`deer-flow.txt`): header, four scenes, a read-through, audio-model notes, a fact
sheet and accuracy notes -- plus the cover spec and per-platform metadata that
were previously written by hand into separate files.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel, BeforeValidator, Field, field_validator, model_validator,
)

MOTIFS = ("plugins", "artboards", "flow", "swarm")


def _to_rgb(value: Any) -> Any:
    """Accept the several ways a model writes a colour.

    Hex is at least as common as a triple in model output, and rejecting it
    costs a whole repair round to relearn something the prompt already said.
    A wrong-length array is a real mistake and still fails, but with a message
    that names the problem rather than reporting three missing fields.
    """
    if isinstance(value, str):
        text = value.strip().lstrip("#")
        if text.lower().startswith("rgb"):
            parts = re.findall(r"\d+", text)
            if len(parts) >= 3:
                return tuple(int(p) for p in parts[:3])
        if len(text) == 3 and all(c in "0123456789abcdefABCDEF" for c in text):
            return tuple(int(c * 2, 16) for c in text)
        if len(text) == 6 and all(c in "0123456789abcdefABCDEF" for c in text):
            return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
        raise ValueError(
            f"{value!r} is not a colour. Use three numbers 0-255, like "
            "[10, 10, 18], or a hex string like \"#0a0a12\"."
        )
    if isinstance(value, (list, tuple)):
        if len(value) == 4:
            return tuple(int(v) for v in value[:3])   # drop an alpha channel
        if len(value) != 3:
            raise ValueError(
                f"a colour needs exactly three numbers (red, green, blue); got "
                f"{len(value)}: {list(value)!r}"
            )
        return tuple(int(v) for v in value)
    return value


RGB = Annotated[tuple[int, int, int], BeforeValidator(_to_rgb)]

#: "80, 000" -> "80,000". A model that puts a line break inside a grouped number
#: leaves a stray space when the lines are rejoined, and the result is wrong
#: three ways over: it fails the sourced-number check (the digits no longer
#: match any real figure), a caption shows "80," on its own, and the narration
#: reads it aloud as two numbers.
_SPLIT_NUMBER_RE = re.compile(r"(\d),\s+(\d{3})\b")


def repair_split_numbers(text: str) -> str:
    previous = None
    while previous != text:
        previous = text
        text = _SPLIT_NUMBER_RE.sub(r"\1,\2", text)
    return text


# ------------------------------------------------------------- script ------
class Scene(BaseModel):
    """One of the four scene blocks. `t_start`/`t_end` are the script's own
    intent; the real cut times come from alignment, not from these."""

    index: int = Field(ge=1, le=8)
    title: str
    t_start: float = Field(ge=0)
    t_end: float = Field(gt=0)
    you_say: str
    on_screen: str
    b_roll: str = ""

    @model_validator(mode="after")
    def _ordered(self) -> "Scene":
        if self.t_end <= self.t_start:
            raise ValueError(f"scene {self.index}: t_end must be after t_start")
        return self


class Phrase(BaseModel):
    """One voiced phrase.

    This is the pivot of the whole pipeline. `align.py` splits audio on silence
    and refuses to build unless the phrase count matches the segment count, so
    generating narration as a phrase *list* -- and synthesizing it phrase by
    phrase with `pause_after_ms` of real silence between -- makes alignment
    deterministic instead of a manual reconciliation.
    """

    text: str
    scene_index: int = Field(ge=1)
    pause_after_ms: int = Field(default=280, ge=0, le=2000)

    @field_validator("text")
    @classmethod
    def _single_line(cls, v: str) -> str:
        v = repair_split_numbers(" ".join(v.split()))
        if not v:
            raise ValueError("phrase text cannot be empty")
        return v

    @property
    def word_count(self) -> int:
        return len(self.text.split())


class AudioNotes(BaseModel):
    delivery: list[str] = Field(default_factory=list)
    # word -> spoken syllable count. Feeds both the TTS hint and align.SPOKEN,
    # without which an initialism drifts its whole phrase by ~200 ms.
    pronunciations: dict[str, int] = Field(default_factory=dict)
    target_seconds_min: float = 30.0
    target_seconds_max: float = 45.0

    @field_validator("pronunciations")
    @classmethod
    def _sane_syllables(cls, v: dict[str, int]) -> dict[str, int]:
        for word, syllables in v.items():
            if not 1 <= syllables <= 12:
                raise ValueError(f"pronunciation {word!r}: {syllables} syllables is implausible")
        return v


class FactRow(BaseModel):
    label: str = Field(max_length=14)
    value: str


# -------------------------------------------------------------- cover ------
class CoverSpec(BaseModel):
    """Mirrors one entry of `video/covers.py` SPECS.

    Cover art needs no code generation -- `covers.py` is already declarative --
    so the LLM fills this in and the render is deterministic.
    """

    bg: RGB
    accent: RGB
    accent_hi: RGB
    pale: RGB
    glow: RGB
    support: RGB
    motif: Literal["plugins", "artboards", "flow", "swarm"]
    eyebrow: str = Field(max_length=42)
    wordmark: str = Field(max_length=24)
    mark_font_kind: Literal["disp", "mono"] = "disp"
    mark_font_size: int = Field(default=180, ge=80, le=260)
    mark_track: int = Field(default=-2, ge=-12, le=16)
    sub: str = Field(max_length=64)
    kicker: str = Field(max_length=72)
    hook: list[str] = Field(min_length=2, max_length=4)
    stats: list[tuple[str, str]] = Field(min_length=3, max_length=3)
    cmd: str = Field(max_length=52)
    prompt: bool = True
    foot_l: str = Field(max_length=34)
    foot_r: str = Field(max_length=34)

    #: Loose ceilings. Whether a line fits depends on which letters it uses --
    #: measured at 78px bold, 21 characters can be 796px or 863px against a
    #: 912px budget -- so the authoritative check is `cover_fit.measure`, which
    #: measures with the real font and reports a precise character budget.
    #: These exist only to reject the absurd before it reaches that.
    @field_validator("hook")
    @classmethod
    def _hook_lines(cls, v: list[str]) -> list[str]:
        for line in v:
            if len(line) > 34:
                raise ValueError(
                    f"cover hook line is {len(line)} characters: {line!r}. Keep hook "
                    "lines short -- around 20 characters each, three at most."
                )
        return v

    @field_validator("stats")
    @classmethod
    def _stat_shape(cls, v: list[tuple[str, str]]) -> list[tuple[str, str]]:
        for value, label in v:
            # measured: "AGPL-3.0" is 8 characters and fits (251px of 269px),
            # "Apache-2.0" is 10 and does not. The width check decides; this
            # only stops something wildly wrong.
            if len(value) > 11:
                raise ValueError(
                    f"stat value is {len(value)} characters: {value!r}. A stat value "
                    "is a short figure like '68K', '100+' or 'MIT'."
                )
            if len(label) > 13:
                raise ValueError(f"stat label too long: {label!r}")
        return v

    def to_covers_dict(self, filename: str) -> dict:
        """The literal dict shape `video/covers.py` expects in SPECS."""
        return dict(
            file=filename,
            bg=tuple(self.bg), accent=tuple(self.accent), accent_hi=tuple(self.accent_hi),
            pale=tuple(self.pale), glow=tuple(self.glow), support=tuple(self.support),
            motif=self.motif, eyebrow=self.eyebrow, wordmark=self.wordmark,
            mark_font=(self.mark_font_kind, self.mark_font_size),
            mark_track=self.mark_track, sub=self.sub, kicker=self.kicker,
            hook=list(self.hook), stats=[tuple(s) for s in self.stats],
            cmd=self.cmd, prompt=self.prompt,
            foot_l=self.foot_l, foot_r=self.foot_r,
        )


# ------------------------------------------------------------- theme -------
class ThemeSpec(BaseModel):
    """Palette for the storyboard, sampled from the cover so reel and cover
    match -- that pairing is what the platform search index reads."""

    bg: RGB
    accent: RGB
    accent_hi: RGB
    pale: RGB
    glow: RGB
    support: RGB
    base_seed: int = Field(default=5, ge=0, le=99)
    base_bloom: float = Field(default=0.34, ge=0.10, le=0.60)


# ------------------------------------------------------------ content ------
class ReelContent(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,40}$")
    display_name: str
    repo_url: str
    tagline: str
    audience: str
    facts_checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    scenes: list[Scene] = Field(min_length=3, max_length=8)
    phrases: list[Phrase] = Field(min_length=6, max_length=40)
    audio: AudioNotes = Field(default_factory=AudioNotes)
    fact_sheet: list[FactRow] = Field(min_length=6)
    accuracy_notes: list[str] = Field(default_factory=list)

    cover: CoverSpec
    theme: ThemeSpec
    hashtags: list[str] = Field(min_length=5, max_length=5)

    @field_validator("hashtags")
    @classmethod
    def _hashtag_shape(cls, v: list[str]) -> list[str]:
        out = []
        for tag in v:
            tag = tag if tag.startswith("#") else f"#{tag}"
            if not re.fullmatch(r"#[a-z0-9]{2,30}", tag):
                raise ValueError(f"hashtag {tag!r} must be lowercase alphanumeric, 2-30 chars")
            out.append(tag)
        if len(set(out)) != 5:
            raise ValueError("the five hashtags must be distinct")
        return out

    @model_validator(mode="after")
    def _phrases_cover_scenes(self) -> "ReelContent":
        scene_ids = {s.index for s in self.scenes}
        used = {p.scene_index for p in self.phrases}
        missing = scene_ids - used
        if missing:
            raise ValueError(f"no narration phrases for scene(s) {sorted(missing)}")
        unknown = used - scene_ids
        if unknown:
            raise ValueError(f"phrases reference nonexistent scene(s) {sorted(unknown)}")
        # Phrases are spoken in sequence, so they must be in scene order -- but
        # a list grouped correctly and merely emitted out of order is
        # recoverable without asking again. A stable sort preserves the order
        # within each scene, which is the part no one else can reconstruct.
        order = [p.scene_index for p in self.phrases]
        if order != sorted(order):
            self.phrases = sorted(self.phrases, key=lambda p: p.scene_index)
        return self

    # ---- derived views -------------------------------------------------
    @property
    def narration(self) -> str:
        """The read-through: scene paragraphs separated by blank lines."""
        paragraphs: list[str] = []
        for scene in self.scenes:
            said = [p.text for p in self.phrases if p.scene_index == scene.index]
            if said:
                paragraphs.append(" ".join(said))
        return "\n\n".join(paragraphs)

    @property
    def word_count(self) -> int:
        return sum(p.word_count for p in self.phrases)

    def phrase_lines(self) -> list[str]:
        """Exactly what `video/phrases/<slug>.txt` must contain."""
        return [p.text for p in self.phrases]

    def estimated_seconds(self) -> float:
        """Rough runtime: ~2.6 words/sec of speech plus the declared pauses."""
        speech = self.word_count / 2.6
        pauses = sum(p.pause_after_ms for p in self.phrases[:-1]) / 1000.0
        return round(speech + pauses, 2)


# ------------------------------------------------- split generation --------
# One structured call per concern rather than one for the whole document.
#
# Measured on a locally hosted 32B model with grammar-constrained decoding, the
# full ReelContent schema did not return inside five minutes; the pieces below
# each return in seconds. The split is better regardless of backend: a rejected
# cover no longer forces the script to be rewritten, the two later calls can run
# concurrently, and each schema fits comfortably in a small context window.


class ScriptDraft(BaseModel):
    """Call 1 -- the creative core: what is said, and what is on screen."""

    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,40}$")
    display_name: str
    tagline: str
    audience: str
    scenes: list[Scene] = Field(min_length=3, max_length=8)
    phrases: list[Phrase] = Field(min_length=6, max_length=40)
    audio: AudioNotes = Field(default_factory=AudioNotes)

    @model_validator(mode="after")
    def _phrases_cover_scenes(self) -> "ScriptDraft":
        scene_ids = {s.index for s in self.scenes}
        used = {p.scene_index for p in self.phrases}
        if scene_ids - used:
            raise ValueError(f"no narration phrases for scene(s) {sorted(scene_ids - used)}")
        if used - scene_ids:
            raise ValueError(f"phrases reference nonexistent scene(s) {sorted(used - scene_ids)}")
        # Phrases are spoken in sequence, so they must be in scene order -- but
        # a list grouped correctly and merely emitted out of order is
        # recoverable without asking again. A stable sort preserves the order
        # within each scene, which is the part no one else can reconstruct.
        order = [p.scene_index for p in self.phrases]
        if order != sorted(order):
            self.phrases = sorted(self.phrases, key=lambda p: p.scene_index)
        return self

    @property
    def narration(self) -> str:
        paragraphs = []
        for scene in self.scenes:
            said = [p.text for p in self.phrases if p.scene_index == scene.index]
            if said:
                paragraphs.append(" ".join(said))
        return "\n\n".join(paragraphs)

    @property
    def word_count(self) -> int:
        return sum(p.word_count for p in self.phrases)

    def estimated_seconds(self) -> float:
        speech = self.word_count / 2.6
        pauses = sum(p.pause_after_ms for p in self.phrases[:-1]) / 1000.0
        return round(speech + pauses, 2)


class FactSheetDraft(BaseModel):
    """Call 2 -- the dense on-screen detail and the claims that need guarding."""

    fact_sheet: list[FactRow] = Field(min_length=6, max_length=20)
    accuracy_notes: list[str] = Field(default_factory=list, max_length=12)


class DesignDraft(BaseModel):
    """Call 3 -- palette, cover art and the five hashtags.

    `theme` is optional and derived from the cover when absent. The two are
    required to be the same palette -- that pairing is what the search index
    reads -- so asking for both meant twelve colour triples per call, all of
    which had to agree. A small model reliably lost one, and the whole call
    failed over a redundant field.
    """

    cover: CoverSpec
    theme: ThemeSpec | None = None
    hashtags: list[str] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def _theme_from_cover(self) -> "DesignDraft":
        if self.theme is None:
            self.theme = ThemeSpec(
                bg=self.cover.bg, accent=self.cover.accent,
                accent_hi=self.cover.accent_hi, pale=self.cover.pale,
                glow=self.cover.glow, support=self.cover.support,
            )
        return self

    @field_validator("hashtags")
    @classmethod
    def _hashtag_shape(cls, v: list[str]) -> list[str]:
        out = []
        for tag in v:
            tag = tag if tag.startswith("#") else f"#{tag}"
            if not re.fullmatch(r"#[a-z0-9]{2,30}", tag):
                raise ValueError(f"hashtag {tag!r} must be lowercase alphanumeric, 2-30 chars")
            out.append(tag)
        if len(set(out)) != 5:
            raise ValueError("the five hashtags must be distinct")
        return out


def assemble(
    script: ScriptDraft, sheet: FactSheetDraft, design: DesignDraft, *, repo_url: str
) -> ReelContent:
    """Join the three drafts into the document the rest of the pipeline uses."""
    return ReelContent(
        slug=script.slug, display_name=script.display_name, repo_url=repo_url,
        tagline=script.tagline, audience=script.audience,
        scenes=script.scenes, phrases=script.phrases, audio=script.audio,
        fact_sheet=sheet.fact_sheet, accuracy_notes=sheet.accuracy_notes,
        cover=design.cover, theme=design.theme, hashtags=design.hashtags,
    )


# ------------------------------------------------- per-scene generation ----
# A second way to produce a ScriptDraft, for models that cannot sustain a whole
# script in one answer.
#
# Measured with qwen2.5:7b-instruct: asked for 95 words in one call it returns
# 30-44, attempt after attempt, however the instruction is phrased -- it writes
# headlines and stops. Asked for one scene at a time it writes the ~24 words
# that scene needs, because that is a length it can hold. The outline call fixes
# what each scene is about, so the four phrase calls stay coherent with each
# other without any of them seeing the others' output.


class SceneOutline(BaseModel):
    """Call 1 of the per-scene path: what the video is and what each scene does."""

    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,40}$")
    display_name: str
    tagline: str
    audience: str
    scenes: list[Scene] = Field(min_length=3, max_length=6)

    @model_validator(mode="after")
    def _sequential(self) -> "SceneOutline":
        for position, scene in enumerate(self.scenes, start=1):
            if scene.index != position:
                raise ValueError(
                    f"scenes must be numbered 1..{len(self.scenes)} in order; "
                    f"scene at position {position} has index {scene.index}"
                )
        return self


class ScenePhrases(BaseModel):
    """One of calls 2..N: the spoken lines for a single scene.

    The upper bound is generous because this is also the container for lines
    accumulated across several continuation rounds, not only for one answer.
    """

    phrases: list[str] = Field(min_length=1, max_length=30)

    @field_validator("phrases")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        out = [repair_split_numbers(" ".join(line.split())) for line in v]
        out = [line for line in out if line]
        if not out:
            raise ValueError("a scene needs at least one spoken phrase")
        return out

    @property
    def word_count(self) -> int:
        return sum(len(p.split()) for p in self.phrases)


def assemble_script(
    outline: SceneOutline,
    per_scene: dict[int, ScenePhrases],
    *,
    audio: AudioNotes | None = None,
    top_up: bool = True,
) -> ScriptDraft:
    """Join an outline and its per-scene phrase lists into one draft.

    With `top_up`, a draft that falls short of the phrase minimum has its
    longest phrases split at clause boundaries rather than failing validation --
    four scenes of one line each is five phrases against a floor of six, which
    is a normal outcome and not an error worth losing the work over.
    """
    phrases: list[Phrase] = []
    for scene in outline.scenes:
        spoken = per_scene.get(scene.index)
        if not spoken:
            continue
        for position, text in enumerate(spoken.phrases):
            last = position == len(spoken.phrases) - 1
            phrases.append(Phrase(
                text=text,
                scene_index=scene.index,
                # a longer beat at the end of a thought, which is also where a
                # scene boundary lands
                pause_after_ms=420 if last or text.endswith((".", "?", "!")) else 280,
            ))
    minimum = ScriptDraft.model_fields["phrases"].metadata[0].min_length
    if top_up and len(phrases) < minimum:
        from app.stages.content import reach_phrase_minimum

        phrases = reach_phrase_minimum(phrases, minimum)
    return ScriptDraft(
        slug=outline.slug, display_name=outline.display_name,
        tagline=outline.tagline, audience=outline.audience,
        scenes=outline.scenes, phrases=phrases,
        audio=audio or AudioNotes(),
    )


class DesignChoices(BaseModel):
    """What a model is actually asked for when designing the cover.

    The full CoverSpec has twenty fields -- six colours, a wordmark, a sub, a
    kicker, an eyebrow, hook lines, three stat pairs, a command, two footers, a
    motif -- and asking for all of it was the single most reliable way to fail a
    job. Measured across four models (Nemotron via OpenRouter, qwen2.5:7b via
    Ollama, Qwen3-1.7B via vLLM, Mistral), every one failed here and nowhere
    else.

    Nearly all of it is derivable: the palette belongs to the template, and the
    wordmark, sub, footers and command come from facts already fetched. What
    genuinely needs judgment is the hook, which three figures to show, and the
    tags. So that is all this asks for.
    """

    hook: list[str] = Field(min_length=2, max_length=3)
    stats: list[tuple[str, str]] = Field(min_length=3, max_length=3)
    hashtags: list[str] = Field(min_length=5, max_length=5)
    motif: Literal["plugins", "artboards", "flow", "swarm"] = "flow"
    kicker: str = ""

    @field_validator("hook")
    @classmethod
    def _hook_lines(cls, v: list[str]) -> list[str]:
        out = [" ".join(line.split()) for line in v if line.strip()]
        if len(out) < 2:
            raise ValueError("give two or three short hook lines")
        return out

    @field_validator("hashtags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        out = []
        for tag in v:
            tag = tag if tag.startswith("#") else f"#{tag}"
            tag = "#" + re.sub(r"[^a-z0-9]", "", tag[1:].lower())
            if len(tag) > 2 and tag not in out:
                out.append(tag)
        if len(out) != 5:
            raise ValueError(
                f"exactly 5 distinct lowercase hashtags are needed, got {len(out)}")
        return out
