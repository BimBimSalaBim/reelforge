"""The content-generation prompt.

Everything the model needs to write a reel script for one repository, and
nothing it could use to invent a number.

The retention rules embedded here are not generic advice -- they are the ones
DEVELOPMENT.md records as what makes the existing six reels work, and they are stated
as constraints rather than suggestions because that is how they survive
contact with a model that would rather write a trailer.
"""
from __future__ import annotations

import re

from app.models.facts import FactsBundle

SYSTEM = """\
You write 30-45 second vertical video scripts about open-source developer tools \
for Instagram Reels and YouTube Shorts. Your audience is working developers who \
are technically literate and allergic to marketing language.

How these scripts work, and these are constraints, not preferences:

1. THE HOOK IS THE FIRST SENTENCE. It must be fully meaningful on its own, land \
in under three seconds, and state a specific technical fact or a real tension. \
Never open with a question, a greeting, "imagine", or the project's name.
2. ONE IDEA PER SCENE. Four scenes: the hook, what it actually is, the one \
genuinely interesting thing, and the close.
3. THE THIRD SCENE CARRIES THE VIDEO. Pick the single most technically \
surprising thing in the project and spend the most time on it. If nothing is \
surprising, pick the most concrete.
4. THE CLOSE ENDS ON A SAVE PROMPT. Saves and shares outrank likes.
5. PLAIN SPOKEN ENGLISH. Short declarative sentences. No "revolutionary", \
"game-changing", "unlock", "empower", "seamless", "supercharge", "dive in", \
"in today's fast-paced world". No exclamation marks. No emoji anywhere.
6. NUMBERS ARE HOSTAGES. State a number only if it appears in the FACTS block \
or verbatim in the README supplied below. If you are unsure, omit it. Never \
estimate, round up, or infer a figure.
7. NEVER CLAIM AFFILIATION, ENDORSEMENT, AUDIT OR CERTIFICATION that the \
sources do not state. Describe what a feature does; do not vouch for it.

The narration is delivered as a list of phrases. Each phrase is one breath -- \
one clause or one short sentence, 3 to 18 words. They are synthesized \
separately and joined with real silence, and each phrase becomes one caption \
group in the finished video, so a phrase that runs long is a caption that does \
not fit. Assign every phrase to its scene.

You also choose the palette. Sample it from the project's own branding where \
the README makes that obvious, otherwise choose something that fits its \
subject. The cover art and the video share this palette, and that pairing is \
what the platform search index reads, so the cover's hook lines and the \
opening spoken line must use the same words."""


def condense_readme(text: str, budget: int = 9000) -> str:
    """Fit a README into a prompt without losing its shape.

    Takes the opening, then section headings with the first lines beneath them.
    A plain head-truncation loses the feature list, which is where the concrete
    detail that makes a script specific actually lives.
    """
    text = (text or "").strip()
    if not text:
        return ""
    # badge soup and HTML carry no information for this purpose
    text = re.sub(r"^\s*(?:\[!\[.*?\]\(.*?\)\]\(.*?\)\s*)+$", "", text, flags=re.M)
    text = re.sub(r"<[^>]{1,200}>", " ", text)
    if len(text) <= budget:
        return text

    lines = text.splitlines()
    head_budget = budget // 3
    head, used = [], 0
    for line in lines:
        if used + len(line) > head_budget:
            break
        head.append(line)
        used += len(line) + 1

    body, remaining = [], budget - used
    index = len(head)
    while index < len(lines) and remaining > 0:
        line = lines[index]
        if re.match(r"^#{1,4}\s+\S", line):
            block = [line]
            cost = len(line)
            for follow in lines[index + 1 : index + 7]:
                if re.match(r"^#{1,4}\s+\S", follow):
                    break
                if follow.strip():
                    block.append(follow)
                    cost += len(follow)
            if cost < remaining:
                body.extend(block + [""])
                remaining -= cost
        index += 1

    return "\n".join(head + ["", "[... README condensed to section headings ...]", ""] + body)


def facts_block(facts: FactsBundle) -> str:
    """The only numbers the model is allowed to use."""
    lines: list[str] = [
        f"fetched_at        : {facts.fetched_at.isoformat()}",
        f"name              : {facts.display_name}",
        f"url               : {facts.primary_url}",
    ]
    gh = facts.github
    if gh:
        lines += [
            f"full_name         : {gh.full_name}",
            f"description       : {gh.description or '(none)'}",
            f"stars             : {gh.stars}",
            f"forks             : {gh.forks}",
            f"watchers          : {gh.watchers}",
            f"open_issues       : {gh.open_issues}",
            f"licence           : {gh.licence or 'unstated'}",
            f"primary_language  : {gh.language or 'unstated'}",
            f"languages         : {', '.join(list(gh.languages)[:6]) or 'unstated'}",
            f"topics            : {', '.join(gh.topics[:12]) or 'none'}",
            f"created_at        : {gh.created_at.date() if gh.created_at else 'unknown'}",
            f"age_days          : {gh.age_days if gh.age_days is not None else 'unknown'}",
            f"last_push         : {gh.pushed_at.date() if gh.pushed_at else 'unknown'}",
            f"days_since_push   : {gh.days_since_push if gh.days_since_push is not None else 'unknown'}",
            f"latest_release    : {gh.latest_release or 'none published'}",
            f"homepage          : {gh.homepage or 'none'}",
            f"archived          : {gh.archived}",
        ]
    hf = facts.huggingface
    if hf:
        lines += [
            f"model_id          : {hf.model_id}",
            f"author            : {hf.author or 'unstated'}",
            f"downloads_30d     : {hf.downloads if hf.downloads is not None else 'unstated'}",
            f"downloads_total   : {hf.downloads_all_time if hf.downloads_all_time is not None else 'unstated'}",
            f"likes             : {hf.likes if hf.likes is not None else 'unstated'}",
            f"pipeline_tag      : {hf.pipeline_tag or 'unstated'}",
            f"library           : {hf.library_name or 'unstated'}",
            f"base_model        : {hf.base_model or 'none stated'}",
            f"licence           : {hf.licence or 'unstated'}",
            f"created_at        : {hf.created_at.date() if hf.created_at else 'unknown'}",
            f"tags              : {', '.join(hf.tags[:12]) or 'none'}",
        ]
    lines.append("")
    lines.append("Every figure you may state is above. Do not calculate a new one "
                 "from them -- no ages, no differences between dates, no totals, "
                 "no percentages. If a number you want is not listed, leave it out.")
    if facts.install_commands:
        lines.append("install_commands  :")
        lines += [f"    {c}" for c in facts.install_commands[:6]]
    else:
        lines.append("install_commands  : none found -- set cover.prompt to false")
    return "\n".join(lines)


def build_content_prompt(
    facts: FactsBundle,
    *,
    template_hint: str = "",
    target_seconds: tuple[float, float] = (36.0, 44.0),
    readme_budget: int = 9000,
    repair_notes: str = "",
) -> tuple[str, str]:
    """Return (system, user)."""
    low, high = target_seconds
    words_low, words_high = int(low * 2.35), int(high * 2.6)

    parts = [
        "Write the reel for this project.",
        "",
        "=" * 62,
        "FACTS  -- the only numbers you may state, besides any that appear",
        "          verbatim in the README below",
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
            "",
            "=" * 62,
            f"ALSO SUPPLIED BY THE USER: {facts.supplied_markdown_name or 'notes.md'}",
            "  Treat this as authoritative about intent and framing.",
            "  It is still not a source for numbers.",
            "=" * 62,
            condense_readme(facts.supplied_markdown, readme_budget // 2),
        ]

    parts += [
        "",
        "=" * 62,
        "REQUIREMENTS",
        "=" * 62,
        f"- Runtime {low:.0f}-{high:.0f} seconds, which is {words_low}-{words_high} "
        "words of narration in total.",
        "- Exactly 4 scenes, indexed 1 to 4.",
        "- 10 to 18 narration phrases, each 3-18 words, in scene order, every "
        "scene covered.",
        "- pause_after_ms: 280 within a thought, 420 at the end of a sentence. "
        "Scene changes get their own longer pause automatically -- do not add it.",
        "- fact_sheet: 8-16 rows of dense, specific, checkable detail. This is "
        "what fills the screen, so prefer concrete nouns and figures over "
        "adjectives. Labels 14 characters or fewer.",
        "- accuracy_notes: every claim a careful reader could challenge, plus how "
        "to re-check the volatile ones before posting.",
        "- audio.pronunciations: spoken syllable counts for initialisms and odd "
        'words, e.g. {"MCP": 3, "npx": 3, "MIT": 3}. Without these the caption '
        "timing drifts. Include every initialism you use.",
        "- hashtags: exactly 5, lowercase, no punctuation. One or two broad, "
        "three or four niche.",
        "- cover.hook: 2-4 lines, 26 characters or fewer each. Its words must "
        "match the opening spoken line.",
        "- cover.stats: exactly 3 pairs of (value, label). Values 7 characters "
        "or fewer, labels 13 or fewer, uppercase labels.",
        "- cover.cmd: a real runnable command from install_commands. If there is "
        "none, set cover.prompt to false and use a short feature strip instead, "
        'such as "SUB-AGENTS - MEMORY - SANDBOX".',
        "- cover.motif: one of plugins, artboards, flow, swarm.",
        "- theme: the same palette as the cover, as RGB triples.",
        f"- slug: lowercase, hyphenated. Use {facts.slug!r} unless it is wrong.",
    ]
    if template_hint:
        parts += ["", "STYLE DIRECTION FOR THIS TEMPLATE", template_hint]
    if repair_notes:
        parts += ["", "=" * 62,
                  "YOUR PREVIOUS ATTEMPT WAS REJECTED. FIX EXACTLY THESE PROBLEMS:",
                  "=" * 62, repair_notes]

    return SYSTEM, "\n".join(parts)
