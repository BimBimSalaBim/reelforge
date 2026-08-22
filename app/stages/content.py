"""Stage 2: turn facts into a script, a cover spec and per-platform copy."""
from __future__ import annotations

import re
from typing import Callable

from app.models.content import (
    AudioNotes, CoverSpec, DesignChoices, DesignDraft, FactSheetDraft, ReelContent, ScenePhrases,
    SceneOutline, ScriptDraft, assemble, assemble_script, repair_split_numbers,
)
from app.models.facts import FactsBundle
from app.models.platform import PlatformBundle
from app.prompts.content import build_content_prompt
from app.prompts.content_parts import (
    build_design_prompt, build_factsheet_prompt, build_outline_prompt,
    build_scene_phrases_prompt, build_script_prompt,
)
from app.prompts.platform import build_platform_prompt
from app.providers.llm import LLMProvider
from app.config import get_config
from app.stages.base import (
    Attempt, GenerationOutcome, StageError, generate_with_repair,
)
from app.validate import facts_check

#: A phrase is one breath and one caption group, so only the upper bound is a
#: real constraint: past it the caption does not fit the safe area.
#:
#: There is no lower bound, and no limit on how many short phrases a script may
#: contain. Both were tried and both were wrong. Measured across the six shipped
#: scripts, phrases of under four words make up 35% to 55% of every one of them
#: -- "Ruflo", "MIT.", "which is the strange one." Short beats are the technique
#: this whole format is built on, not a defect, and a floor of four words
#: rejected the hand-written scripts the pipeline is modelled on.
#:
#: The upper bound is set above the longest phrase in those scripts (19 words,
#: in aas and open-design) rather than at a round number, which would have
#: rejected two of the six.
#:
#: What actually distinguishes a bad draft is total length, which is checked
#: separately: a model that writes headlines produces 30 words where 90 are
#: needed, and that shows up there.
PHRASE_MAX_WORDS = 22

#: The beat of silence the reel lands on after the last spoken word, which
#: `run_storyboard` adds when it sets TOTAL.
TAIL_SECONDS = 1.4

#: How far that beat may stretch to reach the platform floor. The end card
#: carries no narration -- it is a wordmark, a URL and a save prompt -- so a
#: short script does not need rewriting, it needs a longer card. Beyond this
#: the card stops reading as an ending and starts reading as dead air.
MAX_TAIL_SECONDS = 6.0


def reel_total(narration_seconds: float, floor: float | None = None) -> float:
    """The finished length: narration, plus a beat stretched to reach the floor.

    Failing a 32.8s narration for being 3.2s under a 36s floor asks for a
    rewrite of something that is not wrong. The end card holds the difference.
    """
    if floor is None:
        floor = get_config().content.target_seconds_min
    tail = min(max(TAIL_SECONDS, floor - narration_seconds), MAX_TAIL_SECONDS)
    return narration_seconds + tail


def reel_seconds(draft, floor: float | None = None) -> float:
    """How long the finished video will be, from a draft."""
    return reel_total(draft.estimated_seconds(), floor)

#: Openings that mean the model wrote the ON SCREEN column into the spoken
#: line. One reel's last phrase was "showing a model with a save prompt and a
#: deployment interface" -- a direction, read aloud, in the voice track.
DIRECTION_OPENERS = (
    "showing", "shows", "display", "displaying", "cut to", "close-up",
    "close up", "zoom", "pan ", "fade", "text appears", "on screen",
    "on-screen", "b-roll", "screenshot of", "footage of", "animation of",
    "visual", "graphic of", "title card", "overlay",
)


#: Phrases lifted from the worked example rather than written about this
#: project. A local model shown ruflo's script returned ruflo's script -- "An
#: agent is a model plus a harness", "formerly Claude Flow" -- for a Hugging
#: Face model, and every gate passed it because it is a well-formed script.
EXAMPLE_MARKERS = (
    "an agent is a model plus a harness",
    "formerly claude flow",
    "a hundred-plus specialist agents",
    "claude flow",
    "ruflo",
)


def _copied_phrases(phrases, display_name: str) -> list[str]:
    """Lines that came from the example instead of from this project."""
    name = (display_name or "").lower()
    bad = []
    for index, phrase in enumerate(phrases, 1):
        text = phrase.text.lower()
        if any(marker in text for marker in EXAMPLE_MARKERS) and name not in text:
            bad.append(f"  {index}. {phrase.text}")
    return bad


def _names_its_subject(phrases, facts: FactsBundle) -> bool:
    """Does the narration ever mention what it is about?

    The general form of the copied-example problem, and the one that does not
    depend on knowing which example was shown: a script for Qwen3.8-27B that
    never says "Qwen", or anything else specific to it, is about something else
    whatever it says.
    """
    spoken = " ".join(p.text.lower() for p in phrases)
    candidates = {(facts.display_name or "").lower(), (facts.slug or "").lower()}
    if facts.github:
        candidates |= {facts.github.repo.lower(), facts.github.owner.lower()}
    if facts.huggingface:
        model = facts.huggingface.model_id or ""
        candidates |= {part.lower() for part in model.split("/") if part}
        candidates.add((facts.huggingface.author or "").lower())

    for name in candidates:
        # match the distinctive stem, so "Qwen3.8-27B" is found in "Qwen3"
        stem = re.split(r"[^a-z0-9]", name)[0] if name else ""
        if len(stem) >= 3 and stem in spoken:
            return True
    return False


def _duplicate_phrases(phrases) -> list[str]:
    """Lines that appear more than once. Never intentional in a 40-second reel."""
    seen: dict[str, int] = {}
    bad = []
    for index, phrase in enumerate(phrases, 1):
        key = " ".join(phrase.text.lower().split())
        if key in seen:
            bad.append(f"  {index}. (same as line {seen[key]}) {phrase.text}")
        else:
            seen[key] = index
    return bad


def _direction_phrases(phrases) -> list[str]:
    """Phrases that read as a shot description rather than something spoken."""
    bad = []
    for index, phrase in enumerate(phrases, 1):
        text = phrase.text.strip().lower()
        if text.startswith(DIRECTION_OPENERS):
            bad.append(f"  {index}. {phrase.text}")
    return bad


def validate_content(
    content: ReelContent, facts: FactsBundle, *,
    target: tuple[float, float] = (30.0, 46.0),
) -> list[str]:
    """Everything pydantic cannot express. Each problem is phrased as an
    instruction, because it goes straight back to the model."""
    problems: list[str] = []

    low, high = target
    runtime = reel_seconds(content, low)
    if not low <= runtime <= high:
        direction = "shorten" if runtime > high else "lengthen"
        problems.append(
            f"Estimated runtime is {runtime:.1f}s, outside the {low:.0f}-{high:.0f}s "
            f"window. {direction.capitalize()} the narration; it is currently "
            f"{content.word_count} words."
        )

    problems.extend(_phrase_shape_problems(content.phrases))

    directions = _direction_phrases(content.phrases)
    if directions:
        problems.append(
            "These lines describe what is on screen instead of what is said. "
            "The narration is a voice track -- every line is read aloud, so a "
            "shot description would be spoken by the narrator. Rewrite each as "
            "a spoken sentence, or remove it:\n" + "\n".join(directions)
        )

    # numbers must trace to the API or to the project's own README
    surfaces = [content.narration,
                " ".join(s.on_screen for s in content.scenes),
                " ".join(f"{r.label} {r.value}" for r in content.fact_sheet),
                " ".join(f"{v} {l}" for v, l in content.cover.stats),
                " ".join(content.cover.hook)]
    # repair_hint is empty outside strict mode, so warn and off fall through
    findings = facts_check.check(" \n".join(surfaces), facts)
    hint = facts_check.repair_hint(findings, facts)
    if hint:
        problems.append(hint)

    # The narration spells its figures out, because a TTS engine reads "38K" as
    # "thirty eight kay" -- which put them beyond the digit check entirely. One
    # reel said "forty eight thousand stars" over a card reading 38K.
    spoken = facts_check.check_spoken(content.narration, facts)
    hint = facts_check.repair_hint(spoken, facts)
    if hint:
        problems.append(hint)

    # the cover's command bar takes real commands only
    if content.cover.prompt and facts.install_commands:
        if not any(content.cover.cmd.strip() in c or c in content.cover.cmd
                   for c in facts.install_commands):
            problems.append(
                f"cover.cmd is {content.cover.cmd!r}, which is not one of the real "
                f"install commands: {facts.install_commands[:4]}. Use one of those, "
                "or set cover.prompt to false and use a feature strip."
            )
    if content.cover.prompt and not facts.install_commands:
        problems.append(
            "No install command was found for this project, so cover.prompt must "
            "be false and cover.cmd must be a feature strip, not a shell command."
        )

    # the cover hook and the first spoken line must share words
    if content.phrases:
        opening = _keywords(" ".join(
            [p.text for p in content.phrases[:2]] + [content.tagline]))
        hook = _keywords(" ".join(content.cover.hook))
        if opening and hook and not (opening & hook):
            problems.append(
                f"cover.hook {content.cover.hook} shares no words with the opening "
                f"spoken line \"{content.phrases[0].text}\". They must use the same "
                "words -- that pairing is what the search index reads."
            )

    banned = _banned_words(content)
    if banned:
        problems.append(
            f"Remove this marketing language: {', '.join(sorted(banned))}."
        )
    return problems


#: Things that appear in a README but are not speech. A URL read aloud is
#: unlistenable, and it also breaks alignment: the syllable counter sees one
#: enormous "word" and stretches the phrase around it.
_UNSPEAKABLE_RE = re.compile(
    r"https?://\S+|www\.\S+|\S+/\S+/\S+|`[^`]+`|\S+\.(?:md|py|js|ts|json|ya?ml)\b",
    re.I,
)

BANNED = {
    "revolutionary", "game-changing", "gamechanging", "unlock", "unlocks",
    "empower", "empowers", "seamless", "seamlessly", "supercharge", "supercharges",
    "dive in", "cutting-edge", "state-of-the-art", "next-level", "leverage",
    "harness the power", "in today's", "look no further", "elevate",
}


def _phrase_shape_problems(phrases) -> list[str]:
    """Only the upper bound. See the note on PHRASE_MAX_WORDS."""
    return [
        f"Phrase {index + 1} is {phrase.word_count} words: \"{phrase.text}\". "
        f"Split it at a clause boundary -- no phrase may exceed "
        f"{PHRASE_MAX_WORDS} words, because each becomes one caption group and a "
        "longer one does not fit the safe area."
        for index, phrase in enumerate(phrases)
        if phrase.word_count > PHRASE_MAX_WORDS
    ]


def _keywords(text: str) -> set[str]:
    """Content words, stemmed, for judging whether two lines share a subject.

    Comparing raw words rejected a title that plainly matched: "agents" and
    "agent" are different strings, so "Mission control for your AI agents" was
    ruled to share nothing with "An agent is a model plus a harness."
    """
    return {_stem(word) for word in _words(text)}


def _words(text: str) -> list[str]:
    import re

    return [w for w in re.findall(r"[a-z0-9']+", text.lower()) if len(w) > 3]


def _banned_words(content: ReelContent) -> set[str]:
    blob = " ".join([
        content.narration, content.tagline,
        " ".join(s.on_screen for s in content.scenes),
        " ".join(content.cover.hook), content.cover.kicker,
    ]).lower()
    return {word for word in BANNED if word in blob}


def fill_platform_gaps(platforms: PlatformBundle, content: ReelContent) -> None:
    """Derive what does not need a model, in place.

    `alt_text` describes the cover for a screen reader. Every fact it needs is
    already on the cover, so asking for it was a field a whole bundle could fail
    on -- and it did, three attempts running, for being absent.
    """
    instagram = platforms.instagram
    if not (instagram.alt_text or "").strip():
        stats = ", ".join(f"{value} {label.lower()}" for value, label in content.cover.stats)
        instagram.alt_text = (
            f"Cover art for {content.display_name}: the wordmark "
            f"{content.cover.wordmark!r} over the headline "
            f"{' '.join(content.cover.hook)!r}"
            + (f", with {stats}." if stats else ".")
        )[:1000]


def validate_platforms(
    platforms: PlatformBundle, content: ReelContent, facts: FactsBundle
) -> list[str]:
    fill_platform_gaps(platforms, content)
    problems: list[str] = []

    for post in platforms.all():
        try:
            post.render_text()
        except ValueError as exc:
            problems.append(f"{post.platform}: {exc}")

    findings = facts_check.check(
        " \n".join(p.render_text() for p in platforms.all()
                   if _renderable(p)), facts
    )
    hint = facts_check.repair_hint(findings, facts)
    if hint:
        problems.append(hint)

    # Compare against the opening of the video rather than one sentence of it,
    # and against the tagline. A title that summarises the first two lines is
    # doing its job; demanding a literal echo of sentence one is not the rule,
    # it is a proxy for "the post is about the same thing as the video".
    reference = _keywords(" ".join(
        [p.text for p in content.phrases[:2]] + [content.tagline]
    ))
    for post in (platforms.instagram, platforms.youtube):
        text = post.hook if hasattr(post, "hook") else post.title
        stripped = text.replace("#shorts", "")
        if reference and not (reference & _keywords(stripped)):
            opening = content.phrases[0].text if content.phrases else content.tagline
            problems.append(
                f"{post.platform}: {stripped.strip()!r} shares no words with the "
                f"video's opening -- \"{opening}\". Reuse its words: that pairing "
                "is what the search index reads."
            )

    repo_url = content.repo_url
    if repo_url and not any(repo_url in link for link in platforms.youtube.links):
        problems.append(f"youtube.links must include the repository URL {repo_url}.")
    return problems


def _renderable(post) -> bool:
    try:
        post.render_text()
        return True
    except ValueError:
        return False


# ------------------------------------------------------- part validators ---
def validate_script(script: ScriptDraft, facts: FactsBundle, *,
                    target: tuple[float, float] = (30.0, 46.0)) -> list[str]:
    problems: list[str] = []
    low, high = target
    runtime = reel_seconds(script, low)
    if not low <= runtime <= high:
        # Hand back the draft itself rather than an instruction to try again.
        # A model expands text it can see far more reliably than it re-derives
        # a longer version from the brief, and a small local model will
        # otherwise return something the same length attempt after attempt.
        target_words = int((low + high) / 2 * 2.5)
        current = "\n".join(f"  {i + 1}. [scene {p.scene_index}] {p.text}"
                            for i, p in enumerate(script.phrases))
        if runtime > high:
            problems.append(
                f"The narration runs {runtime:.1f}s, over the {high:.0f}s limit at "
                f"{script.word_count} words. Cut it to about {target_words} words by "
                f"removing whole phrases, not by trimming words. Current draft:\n{current}"
            )
        else:
            problems.append(
                f"The narration is far too short: {script.word_count} words, about "
                f"{runtime:.1f}s of speech, against a target of {target_words} words "
                f"for a {low:.0f}-{high:.0f}s video.\n\n"
                f"Keep these phrases and EXPAND each one into a full spoken sentence, "
                f"then add more phrases until you reach {target_words} words. Say what "
                f"the project actually does, name its components, and explain the one "
                f"interesting mechanism in detail. Current draft:\n{current}"
            )
    problems.extend(_phrase_shape_problems(script.phrases))

    directions = _direction_phrases(script.phrases)
    if directions:
        problems.append(
            "These lines describe what is on screen instead of what is said. "
            "Every line here is read aloud by the narrator, so a shot "
            "description ends up in the voice track. Rewrite each as a spoken "
            "sentence, or remove it:\n" + "\n".join(directions)
        )

    duplicates = _duplicate_phrases(script.phrases)
    if duplicates:
        problems.append(
            "These lines repeat one that came earlier. Forty seconds does not "
            "have room to say anything twice -- replace each with a new point, "
            "or remove it:\n" + "\n".join(duplicates)
        )

    if script.phrases and not _names_its_subject(script.phrases, facts):
        problems.append(
            f"The narration never mentions {facts.display_name}. Every line "
            f"has to be about this project -- name it, and use the figures and "
            f"description from the FACTS block. The worked example shows the "
            f"shape to copy, not the subject."
        )

    copied = _copied_phrases(script.phrases, facts.display_name)
    if copied:
        problems.append(
            f"These lines are from the worked example, not about "
            f"{facts.display_name}. The example shows the shape to follow; the "
            f"content must come from the FACTS block. Rewrite each one about "
            f"{facts.display_name}:\n" + "\n".join(copied)
        )
    surfaces = [script.narration, " ".join(s.on_screen for s in script.scenes)]
    hint = facts_check.repair_hint(facts_check.check(" \n".join(surfaces), facts), facts)
    if hint:
        problems.append(hint)
    blob = " ".join([script.narration, script.tagline,
                     " ".join(s.on_screen for s in script.scenes)]).lower()
    banned = {w for w in BANNED if w in blob}
    if banned:
        problems.append(f"Remove this marketing language: {', '.join(sorted(banned))}.")
    return problems


def validate_factsheet(sheet: FactSheetDraft, facts: FactsBundle) -> list[str]:
    problems: list[str] = []
    blob = " ".join(f"{r.label} {r.value}" for r in sheet.fact_sheet)
    hint = facts_check.repair_hint(facts_check.check(blob, facts), facts)
    if hint:
        problems.append(hint)
    # Every fact-sheet row is drawn on screen, so it has to be drawable.
    from app.validate.cover_fit import check_renderable, describe_unrenderable

    drawable = describe_unrenderable(check_renderable(
        {f"fact_sheet[{i}].{part}": text
         for i, row in enumerate(sheet.fact_sheet)
         for part, text in (("label", row.label), ("value", row.value))}
    ))
    if drawable:
        problems.append(drawable)

    labels = {r.label.lower().rstrip(" :") for r in sheet.fact_sheet}
    if facts.github and not any(l.startswith("repo") for l in labels):
        problems.append("The fact sheet must include a 'Repo' row with the repository path.")
    if not any("licen" in l for l in labels):
        problems.append("The fact sheet must include a 'Licence' row.")
    return problems


def validate_design(design: DesignDraft, script: ScriptDraft,
                    facts: FactsBundle) -> list[str]:
    problems: list[str] = []
    blob = " ".join([" ".join(design.cover.hook),
                     " ".join(f"{v} {l}" for v, l in design.cover.stats),
                     design.cover.kicker, design.cover.eyebrow])
    hint = facts_check.repair_hint(facts_check.check(blob, facts), facts)
    if hint:
        problems.append(hint)

    if design.cover.prompt and facts.install_commands:
        cmd = design.cover.cmd.strip()
        if not any(cmd in c or c in cmd for c in facts.install_commands):
            problems.append(
                f"cover.cmd is {cmd!r}, not one of the real install commands "
                f"{facts.install_commands[:3]}. Use one, or set cover.prompt false."
            )
    if design.cover.prompt and not facts.install_commands:
        problems.append(
            "No install command exists for this project, so cover.prompt must be "
            "false and cover.cmd must be a feature strip, not a shell command."
        )
    if script.phrases:
        opening = _keywords(" ".join(
            [p.text for p in script.phrases[:2]] + [script.tagline]))
        hook = _keywords(" ".join(design.cover.hook))
        if opening and hook and not (opening & hook):
            problems.append(
                f"cover.hook {design.cover.hook} shares no words with the opening "
                f"spoken line \"{script.phrases[0].text}\". They must share words."
            )
    if sum(design.theme.bg) > 210:
        problems.append(
            f"theme.bg {design.theme.bg} is too light. The ground is near-black; "
            "captions and glows are composited over it."
        )

    # Character limits are a poor proxy for whether text fits, because width
    # depends on the typeface. Measure with the real fonts instead.
    from app.validate.cover_fit import describe, measure_spec

    spec = design.cover.to_covers_dict("cover.png")
    overflow = describe(measure_spec(spec))
    if overflow:
        problems.append(overflow)

    from app.validate.cover_fit import check_renderable, describe_unrenderable

    drawable = describe_unrenderable(check_renderable({
        "cover.eyebrow": design.cover.eyebrow, "cover.wordmark": design.cover.wordmark,
        "cover.sub": design.cover.sub, "cover.kicker": design.cover.kicker,
        "cover.cmd": design.cover.cmd,
        **{f"cover.hook[{i}]": line for i, line in enumerate(design.cover.hook)},
        **{f"cover.stats[{i}]": f"{v} {l}" for i, (v, l) in enumerate(design.cover.stats)},
    }))
    if drawable:
        problems.append(drawable)
    return problems


# ------------------------------------------------------------- the stage ---
def generate_content(
    facts: FactsBundle, llm: LLMProvider, *,
    template_hint: str = "",
    max_attempts: int = 3,
    fact_check: str = "strict",
    progress: Callable[[str], None] | None = None,
) -> GenerationOutcome:
    """Three structured calls, assembled.

    One document-sized schema proved impractical against a locally hosted model
    under grammar-constrained decoding. These parts are independently validated
    and independently repaired, so a rejected cover costs one small call rather
    than the whole script.
    """
    with facts_check.mode(fact_check):
        return _generate_content(facts, llm, template_hint=template_hint,
                                 max_attempts=max_attempts, progress=progress)


def _generate_content(
    facts: FactsBundle, llm: LLMProvider, *, template_hint: str,
    max_attempts: int, progress: Callable[[str], None] | None,
) -> GenerationOutcome:
    def note(stage: str):
        return (lambda message: progress(f"{stage}: {message}")) if progress else None

    from app.templates import load_template

    template = None
    if template_hint:
        for candidate in load_template.__globals__["discover"]().values():
            if candidate.tone_hint == template_hint:
                template = candidate
                break
    cfg = get_config().content
    target = (cfg.target_seconds_min, cfg.target_seconds_max)
    script_out = _generate_script(
        facts, llm, mode=cfg.script_mode, template_hint=template_hint,
        target_seconds=target, max_attempts=max_attempts, progress=progress,
    )
    script: ScriptDraft = script_out.value

    sheet_out = generate_with_repair(
        llm, FactSheetDraft,
        lambda notes: build_factsheet_prompt(facts, script, repair_notes=notes),
        lambda value: validate_factsheet(value, facts),
        max_attempts=max_attempts, progress=note("fact sheet"),
    )

    # Ask only for the parts that need judgment; derive the rest. See
    # DesignChoices for why -- every model tested failed at this stage and
    # nowhere else, on fields that were never the model's to decide.
    base = derive_design(facts, script, template)
    try:
        design_out = generate_with_repair(
            llm, DesignChoices,
            lambda notes: build_design_prompt(facts, script, template_hint=template_hint,
                                              repair_notes=notes),
            lambda value: validate_choices(value, script, facts, base),
            max_attempts=max_attempts, progress=note("design"),
        )
        design = apply_choices(base, design_out.value)
        attempts_from_design = design_out.attempts
    except StageError as exc:
        # The cover is a palette, three figures and five tags -- almost all of
        # it derivable from the facts already fetched. Blocking a whole job on
        # it, after the script and fact sheet succeeded, throws away the
        # expensive work for the cheapest part. Same reasoning as the fallback
        # storyboard: never fail on something that can be derived.
        if progress:
            progress(f"design: generation gave up ({str(exc).splitlines()[-1][:80]}); "
                     "deriving the cover from the facts instead")
        design = base
        attempts_from_design = []

    content = assemble(script, sheet_out.value, design,
                       repo_url=facts.primary_url)
    attempts: list[Attempt] = []
    for part in (script_out, sheet_out):
        attempts.extend(part.attempts)
    attempts.extend(attempts_from_design)
    return GenerationOutcome(value=content, attempts=attempts)


def fact_report(content: ReelContent, facts: FactsBundle) -> dict:
    """Every number in the draft with where it traces, whatever the mode.

    `warn` is only different from `off` if the findings reach a human, so the
    report is built regardless and stored on the stage. The content gate shows
    it; strict mode has already used it to fail the draft.
    """
    surfaces = [content.narration,
                " ".join(s.on_screen for s in content.scenes),
                " ".join(f"{r.label} {r.value}" for r in content.fact_sheet),
                " ".join(f"{v} {l}" for v, l in content.cover.stats),
                " ".join(content.cover.hook)]
    written = facts_check.check(" \n".join(surfaces), facts)
    spoken = facts_check.check_spoken(content.narration, facts, label="narration: ")
    merged = facts_check.report(written + spoken)
    merged["spoken_checked"] = len(spoken)
    return merged


def generate_content_single_call(
    facts: FactsBundle, llm: LLMProvider, *,
    template_hint: str = "", max_attempts: int = 3,
    progress: Callable[[str], None] | None = None,
) -> GenerationOutcome:
    """One call for the whole document.

    Kept for models that handle a large schema comfortably and where a single
    coherent pass is preferable to three.
    """
    return generate_with_repair(
        llm, ReelContent,
        lambda notes: build_content_prompt(facts, template_hint=template_hint,
                                           repair_notes=notes),
        lambda value: validate_content(ensure_outro(value), facts),
        max_attempts=max_attempts, progress=progress,
    )


def _generate_script(
    facts: FactsBundle, llm: LLMProvider, *, mode: str, template_hint: str,
    target_seconds: tuple[float, float], max_attempts: int,
    progress: Callable[[str], None] | None,
) -> GenerationOutcome:
    """Produce a ScriptDraft by whichever route the configuration asks for."""
    def whole() -> GenerationOutcome:
        return generate_with_repair(
            llm, ScriptDraft,
            lambda notes: build_script_prompt(
                facts, template_hint=template_hint, target_seconds=target_seconds,
                repair_notes=notes),
            lambda value: validate_script(ensure_outro(value), facts,
                                          target=target_seconds),
            max_attempts=max_attempts,
            progress=(lambda m: progress(f"script: {m}")) if progress else None,
        )

    def per_scene() -> GenerationOutcome:
        return generate_script_per_scene(
            facts, llm, template_hint=template_hint, target_seconds=target_seconds,
            max_attempts=max_attempts, progress=progress,
        )

    if mode == "whole":
        return whole()
    if mode == "per_scene":
        return per_scene()

    # auto: one honest attempt at the whole script, then change approach rather
    # than repeat it. A model that cannot hold the length will not find it on a
    # second identical ask -- measured at 30, then 44, then 44 words again.
    try:
        return generate_with_repair(
            llm, ScriptDraft,
            lambda notes: build_script_prompt(
                facts, template_hint=template_hint, target_seconds=target_seconds,
                repair_notes=notes),
            lambda value: validate_script(ensure_outro(value), facts,
                                          target=target_seconds),
            max_attempts=1,
            progress=(lambda m: progress(f"script: {m}")) if progress else None,
        )
    except StageError as exc:
        if progress:
            first = str(exc).splitlines()[-1].strip(" -")[:110]
            progress(f"script: one-pass attempt rejected ({first}); "
                     "writing it scene by scene instead")
        return per_scene()


def _repair_draft(draft: ScriptDraft, facts: FactsBundle, llm: LLMProvider, *,
                  template_hint: str, target_seconds: tuple[float, float],
                  max_attempts: int,
                  progress: Callable[[str], None] | None) -> tuple[ScriptDraft, list]:
    """Check the assembled draft as a whole, and repair it if it does not pass.

    Each scene was written and checked on its own, and nothing looked at what
    they became together. That let "On screen: a visual representation of the
    model" and "This is the close." through -- outline scaffolding read aloud
    in the voice track -- because no individual scene call is where a whole
    script is judged.

    Returns the original draft unchanged if the repair fails: a flawed script is
    a problem later stages report clearly, and losing a working draft to a
    failed retry is worse.
    """
    problems = validate_script(draft, facts, target=target_seconds)
    if not problems:
        return draft, []
    try:
        outcome = generate_with_repair(
            llm, ScriptDraft,
            lambda notes: build_script_prompt(
                facts, template_hint=template_hint, target_seconds=target_seconds,
                repair_notes=notes or "\n".join(problems)),
            lambda value: validate_script(ensure_outro(value), facts,
                                          target=target_seconds),
            max_attempts=max_attempts, progress=progress,
        )
    except StageError as exc:
        if progress:
            progress(f"expansion did not converge ({str(exc).splitlines()[-1][:80]}); "
                     "keeping the shorter draft")
        return draft, []
    # only take the rewrite if it actually passes -- a retry that trades one
    # set of problems for another is not progress
    rewritten = outcome.value
    if validate_script(rewritten, facts, target=target_seconds):
        return draft, outcome.attempts
    return rewritten, outcome.attempts


def validate_choices(choices, script: ScriptDraft, facts: FactsBundle,
                     base: DesignDraft) -> list[str]:
    """Check only what was asked for, measured against where it will be drawn."""
    from app.validate.cover_fit import describe, describe_unrenderable
    from app.validate.cover_fit import check_renderable, measure_spec

    problems: list[str] = []
    blob = " ".join(list(choices.hook) + [f"{v} {l}" for v, l in choices.stats]
                    + [choices.kicker])
    hint = facts_check.repair_hint(facts_check.check(blob, facts), facts)
    if hint:
        problems.append(hint)

    drawable = describe_unrenderable(check_renderable(
        {f"hook[{i}]": line for i, line in enumerate(choices.hook)}
        | {f"stats[{i}]": f"{v} {l}" for i, (v, l) in enumerate(choices.stats)}
        | {"kicker": choices.kicker}))
    if drawable:
        problems.append(drawable)

    # Measure what the model chose, but only complain about what cannot be
    # fixed here. The kicker and hook are trimmed deterministically by
    # `apply_choices`; rejecting them spends a repair round on something already
    # solved. A stat value that does not fit is a real choice to redo.
    trial = apply_choices(base, choices, trim=False)
    fixable = {"kicker", "eyebrow", "sub", "foot_l", "foot_r"}
    remaining = [p for p in measure_spec(trial.cover.to_covers_dict("cover.png"))
                 if p["field"] not in fixable]
    overflow = describe(remaining)
    if overflow:
        problems.append(overflow)

    if script.phrases:
        opening = _keywords(" ".join(
            [p.text for p in script.phrases[:2]] + [script.tagline]))
        hook_words = _keywords(" ".join(choices.hook))
        if opening and hook_words and not (opening & hook_words):
            problems.append(
                f"The hook {choices.hook} shares no words with the opening spoken "
                f"line \"{script.phrases[0].text}\". They must share words -- that "
                "pairing is what the search index reads.")
    return problems


def apply_choices(base: DesignDraft, choices, *, trim: bool = True) -> DesignDraft:
    """Merge the model's choices onto the derived cover."""
    data = base.cover.model_dump()
    data["hook"] = list(choices.hook)
    # a model hands back whatever it typed, so "38048 STARS" reached a cover;
    # the derived path already compacts, and this puts the two on equal footing
    data["stats"] = [(compact_stat(value), label) for value, label in choices.stats]
    data["motif"] = choices.motif
    if choices.kicker:
        data["kicker"] = choices.kicker
    cover = CoverSpec(**_clamp_to_schema(data))
    if trim:
        cover = trim_cover_to_fit(cover)
    return DesignDraft(cover=cover, hashtags=list(choices.hashtags))


def _clamp_to_schema(data: dict) -> dict:
    """Hold every string to the length CoverSpec already declares for it.

    The model's kicker was applied straight onto the derived cover, and a
    73-character one raised a ValidationError out of the *fallback* path -- the
    one whose whole purpose is that it cannot fail. Reading the limits off the
    schema means a new field is covered the day it is added, rather than the
    day it first overflows.
    """
    for name, field in CoverSpec.model_fields.items():
        limit = next((getattr(meta, "max_length", None) for meta in field.metadata
                      if getattr(meta, "max_length", None)), None)
        value = data.get(name)
        if limit and isinstance(value, str) and len(value) > limit:
            data[name] = _shorten(value, limit)
    return data


def derive_design(facts: FactsBundle, script: ScriptDraft, template=None) -> DesignDraft:
    """Build a cover from the facts, with no model involved.

    Every field has a defensible source: the palette comes from the chosen
    template, the wordmark from the project name, the stats from the figures
    already fetched, and the hook from the opening spoken line -- which is
    exactly the pairing the search index reads.
    """
    from app.templates import load_template

    template = template or load_template("cool-indigo")
    palette = template.palette or {}
    bg = tuple(palette.get("bg", (9, 9, 18)))
    accent = tuple(palette.get("accent", (124, 124, 248)))
    support = tuple(palette.get("support", (64, 224, 208)))
    lighter = tuple(min(255, c + 44) for c in accent)
    pale = tuple(min(255, c + 98) for c in accent)
    glow = tuple(max(0, c - 68) for c in accent)

    stats: list[tuple[str, str]] = []
    gh, hf = facts.github, facts.huggingface
    if gh:
        if gh.stars:
            stats.append((_compact(gh.stars), "STARS"))
        if gh.licence:
            stats.append((short_licence(gh.licence), "LICENCE"))
        if gh.language:
            stats.append((gh.language[:11].upper(), "LANGUAGE"))
        if len(stats) < 3 and gh.forks:
            stats.append((_compact(gh.forks), "FORKS"))
    if hf:
        if hf.downloads:
            stats.append((_compact(hf.downloads), "DOWNLOADS"))
        if hf.likes:
            stats.append((_compact(hf.likes), "LIKES"))
        if hf.licence and len(stats) < 3:
            stats.append((short_licence(hf.licence), "LICENCE"))
    while len(stats) < 3:
        stats.append(("OPEN", "SOURCE"))

    # the hook echoes the opening line, split into short display lines
    opening = script.phrases[0].text.rstrip(".") if script.phrases else script.tagline
    hook = _wrap_words(opening, 22, 3) or [script.display_name]

    command = next((clean_command(c) for c in facts.install_commands
                    if clean_command(c)), "")
    tags = _derive_hashtags(facts, script)

    cover = CoverSpec(
            bg=bg, accent=accent, accent_hi=lighter, pale=pale, glow=glow,
            support=support, motif=template.motif,
            eyebrow=(script.tagline[:40] or script.display_name).upper(),
            wordmark=_wordmark(script.display_name, facts),
            sub=(gh.full_name if gh else (hf.model_id if hf else script.display_name))[:64],
            kicker=script.tagline[:64],
            hook=hook, stats=stats[:3],
            cmd=(command[:52] if command else "OPEN SOURCE - SELF HOSTED"),
            prompt=bool(command),
            foot_l=("OPEN SOURCE" + (f" - {short_licence(gh.licence)}"
                                     if gh and gh.licence else ""))[:34],
            foot_r=(gh.language.upper() if gh and gh.language else "OPEN SOURCE")[:34],
    )
    return DesignDraft(cover=trim_cover_to_fit(cover), hashtags=tags)


def trim_cover_to_fit(cover: CoverSpec) -> CoverSpec:
    """Shorten anything that would be clipped, by measuring it.

    A derived cover must always fit -- it is the fallback, and a fallback that
    fails is worse than none. Character caps are the wrong instrument here (the
    same 21 characters can be 796px or 863px), so this measures with the real
    fonts and trims only what actually overflows.
    """
    from app.validate.cover_fit import measure_spec

    data = cover.model_dump()
    for _ in range(6):
        problems = measure_spec(CoverSpec(**data).to_covers_dict("cover.png"))
        if not problems:
            break
        for problem in problems:
            field = problem["field"]
            budget = max(4, problem["suggest_max_chars"])
            if field.startswith("hook["):
                index = int(field[5:-1])
                hook = list(data["hook"])
                hook[index] = _shorten(hook[index], budget)
                data["hook"] = hook
            elif field == "wordmark":
                # shrink the type before shortening the name: a wordmark is the
                # project's name and cutting it produces something wrong
                suggested = problem.get("suggest_size")
                if suggested and suggested < data["mark_font_size"]:
                    data["mark_font_size"] = max(80, suggested)
                else:
                    data["wordmark"] = _shorten(str(data["wordmark"]),
                                                problem["suggest_max_chars"])
            elif field in ("kicker", "eyebrow", "sub", "cmd", "foot_l", "foot_r"):
                data[field] = _shorten(str(data[field]), budget)
            elif field == "stats":
                # only the value that overflowed, trimmed to what was measured.
                # A blanket value[:7] turned "Apache-2.0" into "Apache-" across
                # every card, including the ones that fitted.
                budget = max(2, problem["suggest_max_chars"])
                data["stats"] = [
                    (short_licence(value)[:budget]
                     if value == problem["text"] else value, label)
                    for value, label in data["stats"]
                ]
    return CoverSpec(**data)


def ensure_outro(draft, outro: str | None = None):
    """End every reel on the same spoken line.

    Deterministic rather than asked for in the prompt: a model told to end with
    a fixed sentence obeys most of the time, and "most of the time" is not a
    thing you can build a channel on. Appending it here also means the runtime
    estimate and the phrase list both count it, which they must -- the aligner
    matches phrases to detected speech one for one.

    Idempotent, so a model that already ended with it does not get it twice.
    """
    from app.models.content import Phrase

    outro = get_config().content.outro if outro is None else outro
    outro = (outro or "").strip()
    if not outro or not draft.phrases:
        return draft

    def bare(text: str) -> str:
        return "".join(ch for ch in text.lower() if ch.isalnum() or ch.isspace()).strip()

    if bare(draft.phrases[-1].text) == bare(outro):
        return draft

    draft.phrases.append(Phrase(
        text=outro,
        scene_index=draft.phrases[-1].scene_index,
        # a beat before the end card, the same as any other closing line
        pause_after_ms=420,
    ))
    return draft


def _shorten(text: str, budget: int) -> str:
    """Shorten a cover string. See app/text.py for why this is shared."""
    from app.text import trim_to

    return trim_to(text, budget)

#: A stat card is 293px wide; a licence identifier has to fit it. These are the
#: spellings that read correctly when shortened, rather than being chopped.
_LICENCE_DISPLAY = {
    "Apache-2.0": "Apache", "AGPL-3.0": "AGPL", "GPL-3.0": "GPL-3",
    "GPL-2.0": "GPL-2", "LGPL-3.0": "LGPL", "BSD-3-Clause": "BSD-3",
    "BSD-2-Clause": "BSD-2", "MPL-2.0": "MPL", "EPL-2.0": "EPL",
    "CC-BY-4.0": "CC-BY", "Unlicense": "PUBLIC",
}


def short_licence(licence: str) -> str:
    if not licence:
        return ""
    if licence in _LICENCE_DISPLAY:
        return _LICENCE_DISPLAY[licence]
    if len(licence) <= 8:
        return licence
    # drop a trailing version: "Something-1.2" -> "Something"
    trimmed = re.sub(r"[-_ ]?v?\d+(\.\d+)*$", "", licence)
    return (trimmed or licence)[:8]


def clean_command(command: str) -> str:
    """A command fit to print on a cover.

    READMEs wrap long commands across lines with a trailing backslash, and the
    extractor keeps the first line -- which alone is not runnable. Shell
    continuations are dropped, and a command that is only a fragment is refused
    so the cover shows a feature strip instead of a broken instruction.
    """
    command = " ".join((command or "").split())
    command = re.sub(r"\s*\\$", "", command).strip()
    if command.endswith(("|", "&&", "&", ";")):
        command = command.rsplit(None, 1)[0] if " " in command else ""
    return command if len(command.split()) >= 2 else ""


def _wordmark(display_name: str, facts: FactsBundle) -> str:
    """The project's name, not its title.

    A wordmark is drawn very large and centred, so "Harness Open Source" runs
    off both edges however small it is shrunk. The repository name is the name
    people actually type, and it is short by construction.
    """
    name = (display_name or "").strip()
    if len(name) <= 12 and " " not in name:
        return name[:24]
    repo = facts.github.repo if facts.github else None
    if not repo and facts.huggingface:
        repo = facts.huggingface.model_id.split("/")[-1]
    if repo and len(repo) <= len(name):
        return repo[:24]
    # otherwise the first word, which is nearly always the name
    return (name.split()[0] if name.split() else name)[:24]


def _compact(n: int) -> str:
    """Match the shipped covers: 165K, 17.6K, 314.

    They carry one decimal below 100K and none above, because a stat card is
    read at a glance and "38048" is a number you parse rather than see. A
    trailing .0 is dropped, so 38048 reads 38K and 3352 reads 3.4K.
    """
    for cut, suffix in ((1_000_000, "M"), (1_000, "K")):
        if n >= cut:
            if n >= cut * 100:
                return f"{n // cut}{suffix}"
            return f"{n / cut:.1f}".removesuffix(".0") + suffix
    return str(n)


def compact_stat(value: str) -> str:
    """Compact a bare count a model handed back, and leave anything else alone.

    Derived stats go through `_compact` already; model-supplied ones arrive as
    whatever the model typed, which is how "38048 STARS" reached a cover.
    """
    raw = value.strip().replace(",", "")
    return _compact(int(raw)) if raw.isdigit() and len(raw) > 3 else value.strip()


#: Pairs that must not be split across a line break, because half of one reads
#: as a different claim: "A model with 27" / "billion parameters" invites the
#: eye to stop at 27.
_UNSPLITTABLE_NEXT = {"billion", "million", "thousand", "hundred", "percent",
                      "k", "m", "b", "x", "plus"}


def _wrap_words(text: str, width: int, limit: int) -> list[str]:
    """Break into at most `limit` lines, without stranding half a figure.

    A hook is read at a glance, so where it breaks changes what it says.
    """
    words = text.split()
    lines: list[str] = []
    current = ""
    for index, word in enumerate(words):
        candidate = f"{current} {word}".strip()
        over = len(candidate) > width and current
        # never end a line on a number whose unit is the next word
        if over and word.lower() in _UNSPLITTABLE_NEXT and current.split():
            previous = current.rsplit(" ", 1)
            if previous[-1].rstrip(",.").replace(".", "").isdigit():
                current = (previous[0] if len(previous) > 1 else "").strip()
                if current:
                    lines.append(current)
                current = f"{previous[-1]} {word}"
                if len(lines) == limit:
                    break
                continue
        if over:
            lines.append(current)
            current = word
            if len(lines) == limit:
                break
        else:
            current = candidate
    if current and len(lines) < limit:
        lines.append(current)

    # a hook that ran out of room mid-clause promises a line that never comes
    while lines and lines[-1].split() and lines[-1].split()[-1].lower() in _DANGLING_WORDS:
        words_left = lines[-1].split()[:-1]
        if not words_left:
            lines.pop()
        else:
            lines[-1] = " ".join(words_left)
            break
    return lines[:limit] if len(lines) >= 2 else (lines or [])


#: Words that cannot end a hook line, because they point at something after them.
_DANGLING_WORDS = {"and", "or", "but", "with", "for", "the", "a", "an", "of",
                   "to", "in", "on", "at", "from", "that", "which", "into"}


def _derive_hashtags(facts: FactsBundle, script: ScriptDraft) -> list[str]:
    """Five distinct, lowercase tags: two broad, the rest from the project."""
    import re as _re

    tags: list[str] = ["#opensource", "#devtools"]
    topics = list(facts.github.topics) if facts.github else []
    if facts.huggingface:
        topics += list(facts.huggingface.tags)
    for topic in topics:
        cleaned = "#" + _re.sub(r"[^a-z0-9]", "", topic.lower())
        if len(cleaned) > 2 and cleaned not in tags:
            tags.append(cleaned)
        if len(tags) == 5:
            break
    for extra in ("#coding", "#software", "#developer", "#programming"):
        if len(tags) == 5:
            break
        if extra not in tags:
            tags.append(extra)
    return tags[:5]


def generate_platforms(
    content: ReelContent, facts: FactsBundle, llm: LLMProvider, *,
    max_attempts: int = 3,
    progress: Callable[[str], None] | None = None,
) -> GenerationOutcome:
    outcome = generate_with_repair(
        llm, PlatformBundle,
        lambda notes: build_platform_prompt(content, facts, repair_notes=notes),
        lambda value: validate_platforms(
            value.apply_hashtags(content.hashtags), content, facts
        ),
        max_attempts=max_attempts, progress=progress,
    )
    outcome.value.apply_hashtags(content.hashtags)
    return outcome


# ------------------------------------------------- per-scene generation ----
#: Initialisms `align.py`'s SPOKEN table already knows about.
_KNOWN_SPOKEN = {
    "MCP", "AAS", "ECC", "npx", "MIT", "CLI", "API", "AI", "TDD", "URL", "SDK", "IDE",
}
#: Short all-caps words that are read as words, not spelled out.
_SAID_AS_WORDS = {"AWS", "SQL", "JSON", "YAML", "REST", "HTTP", "HTTPS", "GNU"}


def derive_pronunciations(narration: str) -> dict[str, int]:
    """Find initialisms the syllable counter will get wrong.

    `align.py` counts vowel runs, so "GPU" reads as one syllable when it is
    spoken as three, and the whole phrase containing it drifts by about 200 ms
    (DEVELOPMENT.md gotcha 7). Its SPOKEN table covers the ones seen so far; this
    catches the rest without needing the model to remember to declare them.

    Only letters-spelled-out initialisms are inferred. Anything read as a word
    ("JSON", "REST") is left alone, because guessing its syllables would be
    worse than the counter's own estimate.
    """
    found: dict[str, int] = {}
    for token in re.findall(r"\b[A-Za-z][A-Za-z0-9.\-]*\b", narration or ""):
        core = token.strip(".,:;!?")
        if core in _KNOWN_SPOKEN or core.upper() in _SAID_AS_WORDS:
            continue
        letters = core.replace(".", "")
        if 2 <= len(letters) <= 5 and letters.isalpha() and letters.isupper():
            found[core] = len(letters)
    return found


def validate_outline(outline: SceneOutline, facts: FactsBundle) -> list[str]:
    problems: list[str] = []
    if len(outline.scenes) != 4:
        problems.append(
            f"There are {len(outline.scenes)} scenes; there must be exactly 4: "
            "the hook, what it is, the surprising thing, the close."
        )
    for previous, following in zip(outline.scenes, outline.scenes[1:]):
        if abs(previous.t_end - following.t_start) > 0.01:
            problems.append(
                f"scene {previous.index} ends at {previous.t_end}s but scene "
                f"{following.index} starts at {following.t_start}s. They must meet."
            )
    blob = " ".join(f"{s.title} {s.you_say} {s.on_screen}" for s in outline.scenes)
    banned = {w for w in BANNED if w in blob.lower()}
    if banned:
        problems.append(f"Remove this marketing language: {', '.join(sorted(banned))}.")
    hint = facts_check.repair_hint(facts_check.check(blob, facts), facts)
    if hint:
        problems.append(hint)
    return problems


def validate_scene_phrases(
    spoken: ScenePhrases, target_words: int, facts: FactsBundle, scene_index: int,
    *, check_length: bool = True,
) -> list[str]:
    """Shape always; length only when the caller has no other way to reach it.

    `_write_scene` passes `check_length=False` for the opening call, because a
    short first answer is not a failure there -- it is topped up by asking for
    more lines, which works where asking for a longer answer does not. Failing
    the opening call on length meant the repair budget was spent before the
    accumulation loop was ever reached.
    """
    problems: list[str] = []
    low, high = int(target_words * 0.7), int(target_words * 1.5)
    if not check_length:
        # `_write_scene` owns length on the opening call: short is topped up by
        # asking for more lines, long is trimmed by dropping one. Both are
        # deterministic and cost no call, so failing here would spend the repair
        # budget on something already solved.
        pass
    elif spoken.word_count < low:
        problems.append(
            f"Scene {scene_index} is {spoken.word_count} words; it needs at least "
            f"{low} and should be about {target_words}. Expand each line into a "
            "full spoken sentence and add another if you need to. You wrote:\n"
            + "\n".join(f"  {line}" for line in spoken.phrases)
        )
    elif spoken.word_count > high:
        problems.append(
            f"Scene {scene_index} is {spoken.word_count} words, over the {high} "
            f"limit. Cut it to about {target_words} by dropping a whole line."
        )

    for position, line in enumerate(spoken.phrases, start=1):
        if len(line.split()) > PHRASE_MAX_WORDS:
            problems.append(
                f"Line {position} is {len(line.split())} words: \"{line}\". Split it "
                f"at a clause boundary; no phrase may exceed {PHRASE_MAX_WORDS}."
            )
        unspeakable = _UNSPEAKABLE_RE.search(line)
        if unspeakable:
            problems.append(
                f"Line {position} contains {unspeakable.group(0)!r}, which nobody "
                "says out loud. This is narration that will be read by a voice: no "
                "URLs, no file paths, no code. Say what it does instead, and leave "
                "the address to the description box."
            )
    blob = " ".join(spoken.phrases)
    banned = {w for w in BANNED if w in blob.lower()}
    if banned:
        problems.append(f"Remove this marketing language: {', '.join(sorted(banned))}.")
    hint = facts_check.repair_hint(facts_check.check(blob, facts), facts)
    if hint:
        problems.append(hint)
    return problems


#: A scene asking for more than this in one go runs into the same ceiling the
#: whole-script call does, so the remainder is gathered in continuation rounds.
SCENE_CHUNK_WORDS = 30
#: How many times to ask for more before accepting what is there.
MAX_CONTINUATIONS = 3


#: Above this content-word overlap, two phrases are saying the same thing.
#:
#: Accumulating a scene in rounds invites repetition -- a scene came back with
#: "DeerFlow 2.0, DeerFlow 2.0 is faster", and a closing scene restated the
#: previous one. The prompt asks the model not to repeat itself and it does
#: anyway, so the filter has to be mechanical.
#:
#: Calibrated on 11 labelled pairs from real generations: genuine repeats scored
#: 0.20-1.00 and legitimately distinct phrases 0.00-0.17. That is a small sample
#: and the boundary is narrow, so the threshold sits just above the observed
#: keeps rather than midway. Erring toward dropping is the cheaper mistake: a
#: line wrongly dropped leaves the scene short and the accumulation loop simply
#: asks for another, while a repeat that slips through ships.
SIMILARITY_LIMIT = 0.19
#: Words too common to count as evidence that two phrases match.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be",
    "been", "it", "its", "this", "that", "these", "those", "to", "of", "in",
    "on", "for", "with", "from", "by", "as", "at", "you", "your", "can", "has",
    "have", "had", "not", "no", "so", "then", "than", "into", "over", "every",
}


#: Suffixes stripped so "rewritten", "rewrite" and "rewrites" compare equal.
#: Crude, but the alternative is a stemmer dependency for one similarity check.
_SUFFIXES = ("ing", "edly", "ted", "ed", "es", "s", "en", "ly")


def _stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _content_tokens(line: str) -> set[str]:
    """Content words, punctuation stripped and lightly stemmed.

    Keeping the trailing period made "rewritten." and "rewritten" different
    tokens, so two phrases saying the same thing scored zero overlap. Digits and
    version numbers are kept whole -- "2.0" is a token, not a "2" and a "0".
    """
    out: set[str] = set()
    for raw in re.findall(r"[a-z0-9]+(?:[.%][a-z0-9]+)*%?", line.lower()):
        word = raw.strip(".")
        if not word or word in _STOPWORDS or len(word) < 2:
            continue
        out.add(word if any(ch.isdigit() for ch in word) else _stem(word))
    return out


def too_similar(line: str, existing: list[str], limit: float = SIMILARITY_LIMIT) -> bool:
    """True when `line` restates something already said.

    Jaccard overlap on content words, which catches a reworded repeat that an
    exact-match check misses, without flagging two phrases that merely share a
    subject.
    """
    tokens = _content_tokens(line)
    if not tokens:
        return True  # nothing but filler
    for other in existing:
        other_tokens = _content_tokens(other)
        if not other_tokens:
            continue
        overlap = len(tokens & other_tokens) / len(tokens | other_tokens)
        if overlap > limit:
            return True
        # a line wholly contained in one already said adds nothing
        if tokens <= other_tokens:
            return True
    return False


#: Where a long phrase may be broken into two. Ordered longest-first so a break
#: lands on the strongest boundary available.
_SPLIT_MARKERS = (
    ", and ", ", but ", ", which ", ", so ", ", then ", "; ",
    " -- ", " and ", " but ", " which ", " so that ", " because ", ", ",
)


def split_long_phrase(text: str) -> list[str]:
    """Break one phrase at its best internal clause boundary.

    Used to reach the caption-pacing minimum without another model call. Splits
    only at a real boundary and only when both halves are substantial, so this
    never manufactures a fragment to satisfy a count.
    """
    words = text.split()
    if len(words) < 8:
        return [text]
    best: tuple[int, str] | None = None
    for marker in _SPLIT_MARKERS:
        index = text.find(marker, len(text) // 4, (len(text) * 3) // 4)
        if index == -1:
            continue
        head = text[:index].strip(" ,;")
        tail = text[index + len(marker):].strip()
        if len(head.split()) >= 3 and len(tail.split()) >= 3:
            distance = abs(index - len(text) // 2)
            if best is None or distance < best[0]:
                best = (distance, marker)
    if best is None:
        return [text]

    marker = best[1]
    index = text.find(marker, len(text) // 4, (len(text) * 3) // 4)
    head = text[:index].strip(" ,;")
    tail = text[index + len(marker):].strip()

    # Keep the connective on the second half -- "which replaced Drone" reads as
    # a continuation, while dropping it leaves "Replaced Drone" hanging. And
    # leave that half lowercase, because it continues a sentence rather than
    # starting one.
    connective = marker.strip(" ,;")
    if connective:
        tail = f"{connective} {tail}".strip()
    elif tail:
        tail = tail[0].upper() + tail[1:]

    if not head.endswith((".", "!", "?", ",")):
        head += ","
    return [head, tail]


def reach_phrase_minimum(phrases: list, minimum: int) -> list:
    """Split the longest phrases until there are enough of them.

    The per-scene path can legitimately return fewer phrases than the caption
    minimum -- four scenes of one line each is five phrases against a floor of
    six. That used to raise an unhandled ValidationError and kill the stage.
    Splitting a long phrase at a clause boundary is deterministic, costs no
    model call, and improves caption pacing rather than merely satisfying a
    count.
    """
    from app.models.content import Phrase

    out = list(phrases)
    guard = 0
    while len(out) < minimum and guard < minimum * 3:
        guard += 1
        # Longest first, but try every candidate: the longest phrase may have no
        # clause boundary at all ("Harness is an open source CI/CD platform
        # written in Go"), and giving up on it used to abandon the whole attempt
        # while shorter, splittable phrases sat untouched.
        order = sorted(range(len(out)), key=lambda i: -out[i].word_count)
        for index in order:
            pieces = split_long_phrase(out[index].text)
            if len(pieces) < 2:
                continue
            source = out[index]
            out[index:index + 1] = [
                Phrase(text=piece, scene_index=source.scene_index,
                       pause_after_ms=source.pause_after_ms if position else 280)
                for position, piece in enumerate(pieces)
            ]
            break
        else:
            break  # nothing left that can be split
    return out


#: A phrase shorter than this, sitting next to another, is a fragment rather
#: than a beat and reads better joined to its neighbour.
FRAGMENT_WORDS = 4
#: Comfortable length for one spoken phrase and one caption group.
PHRASE_TARGET_WORDS = 12


def merge_fragments(lines: list[str]) -> list[str]:
    """Join runs of very short lines into breath-sized phrases.

    Accumulating a scene across rounds produces fragments -- measured, 14 lines
    for 31 words, including "while updating" on its own. Each phrase becomes one
    caption group and one aligned segment, so two-word slivers make the captions
    stutter and give the aligner more boundaries than the narration really has.

    A short line survives on its own only at the very start or end of a scene
    and only when it ends a sentence -- enough to keep a closing "MIT." intact.
    It is not enough to preserve every deliberate beat: ruflo's opening runs
    "Ruflo" / "formerly Claude Flow" / "is the harness layer...", and this would
    join those three into one.

    That is an acceptable trade because it is applied only to *generated*
    accumulated output, where short lines are an artifact of asking for more in
    rounds. A phrase list a person wrote, or edited in the UI, is never passed
    through here.
    """
    if not lines:
        return lines

    out: list[str] = []
    buffer = ""

    def flush() -> None:
        nonlocal buffer
        if buffer:
            out.append(buffer.strip())
            buffer = ""

    for index, raw in enumerate(lines):
        line = " ".join(raw.split())
        if not line:
            continue
        last = index == len(lines) - 1
        words = len(line.split())
        buffered = len(buffer.split()) if buffer else 0

        # a deliberate beat: short, self-contained, and at an edge of the scene
        if words < FRAGMENT_WORDS and not buffer and (index == 0 or last) \
                and line.endswith((".", "!", "?")):
            out.append(line)
            continue

        if buffered and buffered + words > PHRASE_MAX_WORDS:
            flush()
            buffered = 0

        buffer = f"{buffer} {line}".strip() if buffer else line
        buffered = len(buffer.split())

        # close the phrase at a sentence end, or once it is long enough
        if buffered >= PHRASE_TARGET_WORDS or (
            line.endswith((".", "!", "?")) and buffered >= FRAGMENT_WORDS
        ):
            flush()

    flush()
    # joining lines is exactly what splits a grouped number, so repair here
    # rather than at the call site
    return [repair_split_numbers(line) for line in out] or lines


def trim_scene(lines: list[str], limit: int, progress=None) -> list[str]:
    """Drop whole lines from the end until the scene is under its word limit.

    A scene that runs long is fixed by removing a line, which needs no model
    call and cannot introduce a new problem. Asking the model to shorten it
    spent the repair budget and came back the same length.
    """
    def total(items: list[str]) -> int:
        return sum(len(item.split()) for item in items)

    out = list(lines)
    while len(out) > 1 and total(out) > limit:
        dropped = out.pop()
        if progress:
            progress(f"{total(out) + len(dropped.split())} words, over {limit}: "
                     f"dropped the last line")
    return out


def _write_scene(
    facts: FactsBundle, llm: LLMProvider, outline, scene, *,
    target_words: int, already_said: list[str], max_attempts: int,
    progress: Callable[[str], None] | None,
) -> tuple[ScenePhrases, list]:
    """One scene's lines, gathered in rounds if the target is large.

    The first call asks for at most SCENE_CHUNK_WORDS. If the scene needs more,
    later calls ask for additional lines to append rather than for a longer
    version of the same thing.
    """
    from app.prompts.content_parts import build_scene_continuation_prompt

    first_target = min(target_words, SCENE_CHUNK_WORDS)
    attempts: list = []

    out = generate_with_repair(
        llm, ScenePhrases,
        lambda notes, tw=first_target: build_scene_phrases_prompt(
            facts, outline, scene, already_said=already_said, target_words=tw,
            repair_notes=notes),
        # shape only: a short opening answer is topped up below, not rejected
        lambda value, tw=first_target: validate_scene_phrases(
            value, tw, facts, scene.index, check_length=False),
        max_attempts=max_attempts, progress=progress,
    )
    written = trim_scene(list(out.value.phrases), int(target_words * 1.5), progress)
    attempts.extend(out.attempts)

    low = int(target_words * 0.7)
    for round_number in range(MAX_CONTINUATIONS):
        have = sum(len(line.split()) for line in written)
        if have >= low:
            break
        wanted = min(target_words - have, SCENE_CHUNK_WORDS)
        if progress:
            progress(f"{have}/{target_words} words, asking for about {wanted} more")
        try:
            more = generate_with_repair(
                llm, ScenePhrases,
                lambda notes, w=wanted, wr=list(written): build_scene_continuation_prompt(
                    facts, outline, scene, wr, already_said=already_said,
                    more_words=w),
                # every check except the length target, which the loop owns.
                # An earlier version validated shape only here, and unchecked
                # continuation text shipped banned words and a raw URL.
                lambda value, tw=wanted: validate_scene_phrases(
                    value, tw, facts, scene.index, check_length=False),
                max_attempts=2, progress=progress,
            )
        except StageError:
            break  # take what we have rather than fail the whole scene
        attempts.extend(more.attempts)
        fresh: list[str] = []
        for line in more.value.phrases:
            if too_similar(line, written + already_said + fresh):
                continue
            fresh.append(line)
        if not fresh:
            break  # it is repeating itself; more rounds will not help
        written.extend(fresh)

    deduped: list[str] = []
    for line in written:
        if not too_similar(line, deduped + already_said):
            deduped.append(line)
    written = merge_fragments(deduped or written)
    if progress:
        total = sum(len(line.split()) for line in written)
        progress(f"scene done: {total} words in {len(written)} lines")
    return ScenePhrases(phrases=written), attempts


def generate_script_per_scene(
    facts: FactsBundle, llm: LLMProvider, *,
    template_hint: str = "",
    target_seconds: tuple[float, float] = (36.0, 44.0),
    max_attempts: int = 3,
    progress: Callable[[str], None] | None = None,
) -> GenerationOutcome:
    """Plan the scenes, then write them one at a time.

    A model that returns 40 words when asked for 95 will return 25 when asked
    for 25. Splitting the ask is what makes a small local model usable here; it
    costs one extra call and each one is a fifth of the size.
    """
    low, high = target_seconds
    total_words = int((low + high) / 2 * 2.5)

    def note(stage: str):
        return (lambda message: progress(f"{stage}: {message}")) if progress else None

    outline_out = generate_with_repair(
        llm, SceneOutline,
        lambda notes: build_outline_prompt(
            facts, template_hint=template_hint, target_seconds=target_seconds,
            repair_notes=notes),
        lambda value: validate_outline(value, facts),
        max_attempts=max_attempts, progress=note("outline"),
    )
    outline: SceneOutline = outline_out.value
    attempts = list(outline_out.attempts)

    span = sum(max(s.t_end - s.t_start, 0.1) for s in outline.scenes) or 1.0
    per_scene: dict[int, ScenePhrases] = {}
    said: list[str] = []

    for scene in outline.scenes:
        share = max(scene.t_end - scene.t_start, 0.1) / span
        target = max(12, round(total_words * share))
        if progress:
            progress(f"scene {scene.index}/{len(outline.scenes)} "
                     f"({scene.title}) -- about {target} words")

        spoken, scene_attempts = _write_scene(
            facts, llm, outline, scene, target_words=target,
            already_said=list(said), max_attempts=max_attempts,
            progress=note(f"scene {scene.index}"),
        )
        per_scene[scene.index] = spoken
        said.extend(spoken.phrases)
        attempts.extend(scene_attempts)

    draft = assemble_script(outline, per_scene)
    ensure_outro(draft)

    # Each scene was checked against its own share, but nothing checked the
    # whole -- in either direction. Four scenes each a little long produced 143
    # words for a 36-44s video; four each a little short produced 55, which
    # became a 25.8s reel that the platforms reject and that nothing noticed
    # until after the render. Trimming from the end keeps the hook and drops the
    # tail; growing hands the draft back and asks for it to be expanded.
    # Measure in seconds, not words. A word ceiling of `high * 2.9` let 117
    # words through as a 48s script, because the estimator does not run at
    # 2.9 words a second -- it weights syllables. The estimator is the thing
    # verify will ultimately agree or disagree with, so ask it directly.
    if reel_seconds(draft, low) > high:
        if progress:
            progress(f"assembled {draft.word_count} words "
                     f"(~{reel_seconds(draft, low):.0f}s of video), over {high:.0f}s; "
                     "dropping trailing phrases")
        kept = list(draft.phrases)
        while len(kept) > 6:
            # never empty a scene: every scene must have something spoken over
            # it, and dropping the tail took all of scene 4 once, which raised
            # a ValidationError out of the assembly rather than a clean problem
            if sum(1 for p in kept if p.scene_index == kept[-1].scene_index) == 1:
                break
            trial = draft.model_copy(update={"phrases": kept[:-1]})
            if reel_seconds(trial, low) < low:
                break            # dropping another would overshoot the floor
            kept = kept[:-1]
            if reel_seconds(trial, low) <= high:
                break
        draft.phrases = kept
    # The whole draft, checked as a whole: length, stage directions, repeats,
    # and whether it is about this project at all. None of these are visible
    # from inside a single scene call.
    final_problems = validate_script(draft, facts, target=target_seconds)
    if final_problems:
        if progress:
            first = final_problems[0].splitlines()[0][:90]
            progress(f"assembled draft rejected ({first}); asking for a rewrite")
        draft, repair_attempts = _repair_draft(
            draft, facts, llm, template_hint=template_hint,
            target_seconds=target_seconds, max_attempts=max_attempts,
            progress=note("rewrite"),
        )
        attempts.extend(repair_attempts)

    draft.audio = AudioNotes(
        delivery=[
            "Measured, level delivery. No hype, no upspeak.",
            "Leave a clear pause of about one second at every blank line.",
            "No background music. Voice only.",
        ],
        pronunciations=derive_pronunciations(draft.narration),
        target_seconds_min=low, target_seconds_max=high,
    )
    if progress:
        progress(f"assembled {draft.word_count} words in {len(draft.phrases)} phrases "
                 f"(~{reel_seconds(draft, low):.0f}s of video)")
    return GenerationOutcome(value=draft, attempts=attempts)
