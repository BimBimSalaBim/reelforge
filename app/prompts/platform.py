"""The per-platform metadata prompt.

Runs after the script exists, so every platform's copy is a rendering of the
*same* video rather than four independent takes on the repository. The five
hashtags are decided once on the content and injected afterwards, which is what
stops the hand-duplication the current `captions.txt` and `-reel-notes.md` have
between them.

Register differs per platform and that is the whole point of a separate call:
Instagram is a hook and a save prompt, YouTube is search text, LinkedIn is a
professional register that must not carry a shell prompt, Facebook is short.
"""
from __future__ import annotations

from app.models.content import ReelContent
from app.models.facts import FactsBundle

SYSTEM = """\
You write post copy for one short vertical video about an open-source developer \
tool. The video already exists and its script is given to you. Every platform \
describes that same video; none invents new claims.

Rules that hold everywhere:
- No number that is not in the FACTS block or the script.
- No marketing language, no emoji, no exclamation marks.
- The opening line of each post mirrors the video's first spoken line. On \
Instagram and YouTube it must use the same words -- that pairing is what the \
search index reads.
- Never claim affiliation or endorsement that the facts do not state.

Per platform:

INSTAGRAM  hook <= 125 characters, because that is what shows before the fold. \
Then 2-4 short body paragraphs carrying searchable keywords in prose, not just \
in tags. Then a one-line stats line. Then a save prompt and a question that a \
developer would actually answer. alt_text describes the cover image for screen \
readers in one sentence.

YOUTUBE  title <= 92 characters before " #shorts" is appended, front-loaded \
with the specific claim, no clickbait. description_body is 3-5 paragraphs: it \
is the searchable surface, so it restates the script in prose and names the \
concrete features. links is a list of plain "Label: https://..." lines.

FACEBOOK  shorter than Instagram, plainer, no hashtag stuffing. One hook, 1-3 \
body paragraphs, one call to action.

LINKEDIN  professional register for an audience of engineers and engineering \
managers. hook <= 210 characters. 2-4 body paragraphs about what the project \
changes about how work gets done, then one takeaway and one question. Never put \
a shell command or a command prompt in the body -- put install instructions in \
first_comment instead."""


def build_platform_prompt(
    content: ReelContent,
    facts: FactsBundle,
    *,
    repair_notes: str = "",
) -> tuple[str, str]:
    from app.prompts.content import facts_block

    scenes = "\n".join(
        f"  Scene {s.index} -- {s.title}\n    {s.you_say}" for s in content.scenes
    )
    fact_rows = "\n".join(f"  {row.label:<14} {row.value}" for row in content.fact_sheet)

    user = f"""\
Write the four platform posts for this video.

{"=" * 62}
THE VIDEO
{"=" * 62}
name      : {content.display_name}
url       : {content.repo_url}
tagline   : {content.tagline}
audience  : {content.audience}
runtime   : about {content.estimated_seconds():.0f} seconds

Narration, in order:
{content.narration}

Scenes:
{scenes}

Fact sheet:
{fact_rows}

Accuracy notes that also constrain the copy:
{chr(10).join('  - ' + note for note in content.accuracy_notes) or '  (none)'}

{"=" * 62}
FACTS
{"=" * 62}
{facts_block(facts)}

{"=" * 62}
REQUIREMENTS
{"=" * 62}
- Leave every `hashtags` field as an empty list. They are applied afterwards
  from a single source of truth, so anything you put there is discarded.
- The YouTube title must not already contain "#shorts"; it is appended for you.
- youtube.links must include the repository URL, and the homepage if the facts
  give one.
- linkedin.first_comment carries the install command, if there is one.
"""
    if repair_notes:
        user += f"\n{'=' * 62}\nYOUR PREVIOUS ATTEMPT WAS REJECTED. FIX EXACTLY THESE:\n{'=' * 62}\n{repair_notes}\n"
    return SYSTEM, user
