"""Prompts for the three content calls.

Split from one document-sized request because grammar-constrained decoding cost
scales badly with schema size: the combined schema did not return inside five
minutes on a locally hosted 32B model, while each part below returns in seconds.
The split also means a rejected cover no longer forces the script to be rewritten.
"""
from __future__ import annotations

from app.models.content import ScriptDraft
from app.models.facts import FactsBundle
from app.prompts.content import SYSTEM as SCRIPT_SYSTEM
from app.prompts.content import condense_readme, facts_block

FACTSHEET_SYSTEM = """\
You extract dense, checkable technical detail about an open-source project and \
write the accuracy notes that guard it.

The fact sheet is what fills the screen behind the narration, so every row must \
be concrete: counts, names, licences, versions, protocols, architecture terms. \
No adjectives, no marketing, no vague capability claims. Labels are 14 \
characters or fewer.

State a number only if it is in the FACTS block or verbatim in the README. \
Never estimate or infer one.

The accuracy notes are for the person about to post the video. Each note names \
a claim a careful reader could challenge and says how to hold it honestly: \
where two sources disagree, which figure to use; what a feature is and is not \
(a project's own zero-trust design is not an audit); any affiliation that must \
not be implied; and which figures go stale and how to re-check them."""

DESIGN_SYSTEM = """\
You choose the palette, cover art and hashtags for a short vertical video about \
an open-source developer tool.

The cover and the video share one palette. Sample it from the project's own \
branding where the README makes that obvious; otherwise choose colours that fit \
the subject. Dark ground, one accent, one support colour. The background is \
near-black, not mid-grey.

The cover is seen as a small square crop in a grid, so the wordmark and hook \
must be short and high-contrast. The hook lines must use the same words as the \
video's opening spoken line -- that pairing is what the search index reads.

The command bar takes a real, runnable command only. If the project has no \
short one, set prompt to false and use a feature strip instead, such as \
"SUB-AGENTS - MEMORY - SANDBOX".

Hashtags: exactly five, lowercase, no punctuation, distinct. One or two broad \
(#opensource, #devtools), three or four specific to what this project is."""


def _sources(facts: FactsBundle, readme_budget: int) -> str:
    parts = [
        "=" * 62,
        "FACTS -- the only numbers you may state, besides any appearing",
        "         verbatim in the README below",
        "=" * 62,
        facts_block(facts),
        "",
        "=" * 62,
        "README / MODEL CARD",
        "=" * 62,
        condense_readme(facts.readme_markdown or "", readme_budget) or "(none available)",
    ]
    if facts.supplied_markdown:
        parts += [
            "", "=" * 62,
            f"ALSO SUPPLIED: {facts.supplied_markdown_name or 'notes.md'}"
            " -- authoritative about intent, not about numbers",
            "=" * 62,
            condense_readme(facts.supplied_markdown, readme_budget // 2),
        ]
    return "\n".join(parts)


def build_script_prompt(
    facts: FactsBundle, *, template_hint: str = "",
    target_seconds: tuple[float, float] = (36.0, 44.0),
    readme_budget: int = 8000, repair_notes: str = "",
) -> tuple[str, str]:
    low, high = target_seconds
    words_low, words_high = int(low * 2.35), int(high * 2.6)
    user = "\n".join([
        f"Write the narration and scene plan for {facts.display_name}.",
        "",
        _sources(facts, readme_budget),
        "",
        "=" * 62,
        "WHAT GOOD NARRATION SOUNDS LIKE",
        "=" * 62,
        "This is the opening of a finished script for a different project. Note "
        "that every phrase is a complete spoken clause, not a headline or a "
        "bullet, and that the whole thing runs to about 90 words:",
        "",
        '  "An agent is a model plus a harness."',
        '  "The model writes the code."',
        '  "The harness decides whether any of it gets done."',
        '  "Ruflo -- formerly Claude Flow -- is the harness layer for Claude Code '
        'and Codex."',
        '  "One npx command gives you a hundred-plus specialist agents that swarm, '
        'learn from every task, and remember across sessions."',
        '  "Then there is federation, which is the strange one."',
        '  "Your agents can talk to agents on someone else\'s machine."',
        "",
        "Write at that length and in that register. Do not write headlines.",
        "",
        "=" * 62,
        "REQUIREMENTS",
        "=" * 62,
        f"- LENGTH IS A HARD REQUIREMENT: {words_low}-{words_high} words of "
        f"narration in total, across all phrases, for a {low:.0f}-{high:.0f} "
        "second video. Count them. A shorter script is rejected.",
        "- Each phrase is one breath: a clause or a short sentence, at most 22 "
        "words. Short beats of one to three words are good and normal -- a name, "
        "a licence, a figure. What matters is that the TOTAL reaches the word "
        "count above.",
        "- Exactly 4 scenes, indexed 1-4: the hook, what it is, the one genuinely "
        "interesting thing, the close.",
        "- 10-18 phrases, each 3-18 words, in scene order, covering every scene.",
        "- Each phrase is one breath and becomes one caption group.",
        "- pause_after_ms: 280 mid-thought, 420 at a sentence end. Scene changes "
        "get a longer pause automatically -- do not add one.",
        "- on_screen describes what is drawn, concretely: which numbers, which "
        "labels, what animates and on which spoken word.",
        "- audio.pronunciations: spoken syllable counts for every initialism you "
        'use, e.g. {"MCP": 3, "npx": 3, "MIT": 3}. Caption timing drifts without them.',
        f"- slug: use {facts.slug!r} unless it is wrong.",
    ])
    if template_hint:
        user += f"\n\nSTYLE DIRECTION\n{template_hint}"
    if repair_notes:
        user += ("\n\n" + "=" * 62 +
                 "\nYOUR PREVIOUS ATTEMPT WAS REJECTED. FIX EXACTLY THESE:\n" +
                 "=" * 62 + f"\n{repair_notes}\n")
    return SCRIPT_SYSTEM, user


def build_factsheet_prompt(
    facts: FactsBundle, script: ScriptDraft, *,
    readme_budget: int = 8000, repair_notes: str = "",
) -> tuple[str, str]:
    user = "\n".join([
        f"Write the fact sheet and accuracy notes for {facts.display_name}.",
        "",
        "The video says this:",
        script.narration,
        "",
        _sources(facts, readme_budget),
        "",
        "=" * 62,
        "REQUIREMENTS",
        "=" * 62,
        "- fact_sheet: 8-16 rows. Labels 14 characters or fewer. Always include "
        "the repository, the author or maintainer, the licence and the created "
        "date when the facts give them.",
        "- accuracy_notes: 3-8 notes. Include one that names the figures which go "
        "stale and how to re-check them before posting.",
    ])
    if repair_notes:
        user += ("\n\n" + "=" * 62 +
                 "\nYOUR PREVIOUS ATTEMPT WAS REJECTED. FIX EXACTLY THESE:\n" +
                 "=" * 62 + f"\n{repair_notes}\n")
    return FACTSHEET_SYSTEM, user


def build_design_prompt(
    facts: FactsBundle, script, *, template_hint: str = "", repair_notes: str = "",
) -> tuple[str, str]:
    """Ask only for the parts of the cover that need judgment.

    The palette, wordmark, sub, footers and command are derived from the facts
    and the template, so they are not asked for at all. Every model tested
    failed at this stage while it demanded all twenty fields.
    """
    opening = script.phrases[0].text if script.phrases else ""
    figures: list[str] = []
    gh, hf = facts.github, facts.huggingface
    if gh:
        figures += [f"{gh.stars} stars", f"{gh.forks} forks"]
        if gh.licence:
            figures.append(f"licence {gh.licence}")
        if gh.language:
            figures.append(f"written in {gh.language}")
        if gh.latest_release:
            figures.append(f"release {gh.latest_release}")
    if hf:
        if hf.downloads:
            figures.append(f"{hf.downloads} downloads")
        if hf.likes:
            figures.append(f"{hf.likes} likes")
        if hf.licence:
            figures.append(f"licence {hf.licence}")

    user = "\n".join([
        f"Choose the cover copy for {facts.display_name}.",
        "",
        f"The video opens with: \"{opening}\"",
        f"It is about: {script.tagline}",
        "",
        "Narration:",
        script.narration,
        "",
        "FIGURES YOU MAY USE -- no others, and do not calculate new ones:",
        *[f"  {figure}" for figure in figures],
        "",
        "=" * 62,
        "WHAT TO WRITE",
        "=" * 62,
        "hook -- two or three lines that appear large on the cover. Each at most "
        "20 characters. They must reuse words from the opening spoken line above, "
        "because that pairing is what the search index reads.",
        '    example: ["An agent is a model", "plus a harness."]',
        "",
        "stats -- exactly three [value, label] pairs. The VALUE is a figure from "
        "the list above; the LABEL says what it counts, uppercase.",
        '    good: [["68K", "STARS"], ["MIT", "LICENCE"], ["Go", "LANGUAGE"]]',
        '    bad:  [["Specialist agents", "AGENTS"]]  -- that is not a figure',
        "    Values are at most 7 characters.",
        "",
        "hashtags -- exactly five, lowercase, no punctuation, all different. One "
        "or two broad, the rest specific to this project.",
        '    example: ["#opensource", "#devtools", "#cicd", "#golang", "#devops"]',
        "",
        "motif -- the background pattern: plugins, artboards, flow or swarm.",
        "",
        "kicker -- one short line under the wordmark, at most 40 characters.",
        "",
        "Nothing else is needed. The colours, the wordmark and the install "
        "command are already set.",
    ])
    if template_hint:
        user += f"\n\nSTYLE DIRECTION\n{template_hint}"
    if repair_notes:
        user += ("\n\n" + "=" * 62 +
                 "\nYOUR PREVIOUS ATTEMPT WAS REJECTED. FIX EXACTLY THESE:\n" +
                 "=" * 62 + f"\n{repair_notes}\n")
    return DESIGN_SYSTEM, user


# ------------------------------------------------- per-scene generation ----
OUTLINE_SYSTEM = SCRIPT_SYSTEM + """

You are writing only the PLAN right now, not the narration. For each scene give
one sentence of what is said in it and a concrete description of what is drawn.
The spoken lines themselves come later, one scene at a time."""

SCENE_SYSTEM = """\
You write the spoken narration for ONE scene of a short vertical video about an \
open-source developer tool, for an audience of working developers.

Write only that scene's lines. Not a summary, not a heading, not a bullet list: \
the words a person says out loud, in order.

Constraints, all of them hard:
- Plain spoken English. Short declarative sentences. No marketing language, no \
"revolutionary", "seamless", "unlock", "empower", "supercharge". No exclamation \
marks, no emoji.
- State a number only if it appears in the facts you are given. Never estimate \
or infer one.
- Each phrase is one breath: a clause or a short sentence, at most 22 words. A \
one- or two-word beat is good where it lands -- a name, a licence, a figure.
- Do not repeat what an earlier scene already said.
- Hit the word count you are given. It is what makes the video the right length."""


def build_outline_prompt(
    facts: FactsBundle, *, template_hint: str = "",
    target_seconds: tuple[float, float] = (36.0, 44.0),
    readme_budget: int = 8000, repair_notes: str = "",
) -> tuple[str, str]:
    low, high = target_seconds
    user = "\n".join([
        f"Plan the four scenes for a video about {facts.display_name}.",
        "",
        _sources(facts, readme_budget),
        "",
        "=" * 62,
        "REQUIREMENTS",
        "=" * 62,
        "- Exactly 4 scenes, indexed 1, 2, 3, 4 in order.",
        "  1: the hook -- a specific technical fact or a real tension, stated flat.",
        "  2: what it actually is.",
        "  3: the one genuinely surprising thing in the project. This scene "
        "carries the video and gets the most time.",
        "  4: the close, ending on a reason to save it.",
        f"- t_start and t_end should divide roughly {low:.0f}-{high:.0f} seconds, "
        "with scene 3 the longest.",
        "- you_say: one sentence summarising what is spoken in that scene. The "
        "actual lines are written later.",
        "- on_screen: concretely what is drawn -- which numbers, which labels, "
        "what animates.",
        f"- slug: use {facts.slug!r} unless it is wrong.",
    ])
    if template_hint:
        user += f"\n\nSTYLE DIRECTION\n{template_hint}"
    if repair_notes:
        user += ("\n\n" + "=" * 62 +
                 "\nYOUR PREVIOUS ATTEMPT WAS REJECTED. FIX EXACTLY THESE:\n" +
                 "=" * 62 + f"\n{repair_notes}\n")
    return OUTLINE_SYSTEM, user


def build_scene_phrases_prompt(
    facts: FactsBundle,
    outline,
    scene,
    *,
    already_said: list[str] | None = None,
    target_words: int = 24,
    repair_notes: str = "",
) -> tuple[str, str]:
    """One scene's lines.

    The whole outline is included so the scene stays coherent with the rest, and
    everything already spoken so it does not repeat itself -- but the model is
    only ever asked to write this one scene's worth of words.
    """
    plan = "\n".join(
        f"  Scene {s.index}{' <- THIS ONE' if s.index == scene.index else ''}: "
        f"{s.title} -- {s.you_say}"
        for s in outline.scenes
    )
    facts_lines = [f"  {facts.display_name} -- {facts.primary_url}"]
    gh = facts.github
    if gh:
        facts_lines += [
            f"  stars {gh.stars}, forks {gh.forks}, licence {gh.licence or 'unstated'}",
            f"  language {gh.language or 'unstated'}, created "
            f"{gh.created_at.date() if gh.created_at else 'unknown'}",
            f"  description: {gh.description or '(none)'}",
        ]
    hf = facts.huggingface
    if hf:
        facts_lines += [
            f"  downloads {hf.downloads}, likes {hf.likes}, "
            f"licence {hf.licence or 'unstated'}",
            f"  pipeline {hf.pipeline_tag or 'unstated'}, "
            f"library {hf.library_name or 'unstated'}",
        ]
    if facts.install_commands:
        facts_lines.append(f"  install: {facts.install_commands[0]}")

    said = already_said or []
    user = "\n".join([
        f"Write the spoken lines for scene {scene.index} of {len(outline.scenes)}: "
        f"{scene.title}.",
        "",
        "THE PLAN FOR THE WHOLE VIDEO",
        plan,
        "",
        "WHAT THIS SCENE COVERS",
        f"  {scene.you_say}",
        f"  On screen: {scene.on_screen}",
        "",
        "FACTS YOU MAY USE",
        *facts_lines,
        "",
        "ALREADY SPOKEN IN EARLIER SCENES -- do not repeat any of it:",
        *([f"  {line}" for line in said] or ["  (nothing yet, this is the opening)"]),
        "",
        "=" * 62,
        f"WRITE ABOUT {target_words} WORDS, split into 2 to 5 phrases.",
        "=" * 62,
        f"Count them. Fewer than {int(target_words * 0.7)} words is rejected and "
        f"more than {int(target_words * 1.5)} is rejected.",
        "Return the phrases in the order they are spoken.",
    ])
    if scene.index == 1:
        user += ("\n\nThis is the opening. The first phrase must work as a hook on "
                 "its own: a specific fact or a real tension, in under three "
                 "seconds. Do not open with a question, a greeting, or the "
                 "project's name.")
    if scene.index == len(outline.scenes):
        user += "\n\nThis is the close. End on a reason to save the video."
    if repair_notes:
        user += ("\n\n" + "=" * 62 +
                 "\nYOUR PREVIOUS ATTEMPT WAS REJECTED. FIX EXACTLY THESE:\n" +
                 "=" * 62 + f"\n{repair_notes}\n")
    return SCENE_SYSTEM, user


def build_scene_continuation_prompt(
    facts: FactsBundle,
    outline,
    scene,
    written: list[str],
    *,
    already_said: list[str] | None = None,
    more_words: int = 20,
) -> tuple[str, str]:
    """Ask for additional lines to append to a scene, not a longer rewrite.

    "Expand this" and "write three more lines that continue it" are very
    different asks. A small model answers the second reliably and ignores the
    first -- measured: told a 22-word scene needed 37, it returned 22 again
    three times running. Accumulating short answers reaches the target that
    asking for a long answer never does.
    """
    system, base = build_scene_phrases_prompt(
        facts, outline, scene, already_said=already_said, target_words=more_words,
    )
    user = "\n".join([
        f"Scene {scene.index} ({scene.title}) already has these lines:",
        *[f"  {line}" for line in written],
        "",
        f"That is {sum(len(w.split()) for w in written)} words and the scene needs "
        f"about {more_words} more.",
        "",
        "Write ONLY the additional lines that come next in this same scene. Do not "
        "repeat or rewrite the lines above -- they are already written. Continue "
        "from where they stop, still on this scene's subject:",
        f"  {scene.you_say}",
        "",
        "Return just the new lines, in the order they are spoken.",
        "",
        "=" * 62,
        "CONTEXT (the same facts as before, for reference)",
        "=" * 62,
        base.split("FACTS YOU MAY USE", 1)[-1].split("=" * 62, 1)[0].strip(),
    ])
    return system, user
