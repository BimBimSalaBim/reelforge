"""Shortening text so it still reads as text.

Three places needed the same thing and each grew its own version: the cover
trimmer, the deterministic renderer, and the Instagram hook. Every one of them
shipped a defect that the others had already fixed --

  "...and artifact regi"          a slice, cutting mid-word
  "Drone's successor adds SCM, Gitspac"   a width fit, cutting mid-word
  "...on by default, and low latency"     a word boundary, stranding a list item
  "docker run"                    a trim that ran when nothing needed trimming

so the rules live here once: never cut a word in half, never end on a word that
points at the next one, never leave half a list item, and never touch text that
already fits.
"""
from __future__ import annotations

#: Words that cannot end a shortened line, because they promise what follows.
DANGLING = frozenset({
    "and", "or", "but", "with", "for", "the", "a", "an", "of", "to", "in", "on",
    "at", "from", "that", "which", "plus", "into", "by", "as", "via", "per",
})

#: Conjunctions that, one word back, mean a list item was cut in half.
LIST_JOINERS = frozenset({"and", "or", "plus"})

#: Below this fraction of the budget, backing up to a word boundary would throw
#: away most of the text -- better to cut the single long word.
MIN_KEEP = 0.55


def trim_to(text: str, budget: int) -> str:
    """Shorten to at most `budget` characters, on a boundary that reads.

    Text already within budget is returned untouched, whitespace-normalised and
    nothing else: editing what fits is how "docker run -d" became "docker run",
    which is a different command.
    """
    text = " ".join(str(text).split())
    if len(text) <= budget:
        return text
    return _tidy(text[:budget].rstrip(), budget)


def trim_by(text: str, fits, floor: int = 0) -> str:
    """Shorten until `fits(candidate)` is true, on a boundary that reads.

    For the places where the limit is a measured pixel width rather than a
    character count -- `fits` is called with the candidate string.
    """
    text = " ".join(str(text).split())
    if fits(text):
        return text
    cut = text
    while len(cut) > floor and not fits(cut):
        cut = cut[:-1]
    return _tidy(cut.rstrip(), len(cut))


def _tidy(cut: str, budget: int) -> str:
    """Back up to a word boundary, then off anything that dangles."""
    space = cut.rfind(" ")
    out = (cut[:space] if space > budget * MIN_KEEP else cut).rstrip(" ,.;:-")

    words = out.split()
    while len(words) > 2 and words[-1].lower() in DANGLING:
        words.pop()
    if len(words) > 3 and words[-2].lower() in LIST_JOINERS:
        del words[-2:]
    return " ".join(words).rstrip(" ,.;:-")
