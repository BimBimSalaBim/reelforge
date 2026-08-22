"""The shortening rules, in one place, because they were in three.

Each copy shipped a defect the others had already fixed. These are the four
that reached rendered output or a rejected job.
"""
from __future__ import annotations

import pytest

from app.text import trim_by, trim_to

TAGLINE = "Drone's successor adds SCM, Gitspaces, and artifact registry"


def test_text_within_budget_is_returned_untouched():
    """Editing what fits is how "docker run -d" became "docker run" on an end
    card -- still a command, no longer the right one."""
    assert trim_to("docker run -d", 40) == "docker run -d"
    assert trim_to("npx create-thing@latest", 40) == "npx create-thing@latest"
    # a dangling word the author wrote is theirs to keep
    assert trim_to("built for speed and", 40) == "built for speed and"
    # only whitespace is normalised
    assert trim_to("  spaced   out  ", 40) == "spaced out"


def test_nothing_is_ever_cut_mid_word():
    """`content.tagline[:56]` put "...and artifact regi" on a rendered frame,
    and a width-fitting loop put "Gitspac" on an end card."""
    for budget in range(20, 60, 3):
        out = trim_to(TAGLINE, budget)
        assert len(out) <= budget
        assert out.split()[-1] in [w.rstrip(",.;:-") for w in TAGLINE.split()], out


def test_a_shortened_line_never_ends_on_a_word_that_points_forward():
    assert trim_to("built for speed and CD pipelines", 20) == "built for speed"
    assert trim_to("one command for the whole team", 16) == "one command"
    assert not trim_to(TAGLINE, 52).endswith(("and", "with", "the", "of"))


def test_half_a_list_item_is_dropped_rather_than_shown():
    """The opening frame read "adds SCM, Gitspaces, and artifact" -- a list
    item cut in half promises a completion that never comes."""
    assert trim_to(TAGLINE, 56) == "Drone's successor adds SCM, Gitspaces"
    assert trim_to(TAGLINE, 42) == "Drone's successor adds SCM, Gitspaces"
    assert trim_to(TAGLINE, 34) == "Drone's successor adds SCM"


def test_a_single_word_longer_than_the_budget_is_still_cut():
    """Backing up to a word boundary must not return nothing."""
    out = trim_to("supercalifragilisticexpialidocious", 10)
    assert 0 < len(out) <= 10


def test_trim_by_measures_instead_of_counting():
    """Some limits are pixels, not characters -- the same rules apply."""
    fits = lambda text: len(text) * 20 <= 900        # noqa: E731  (45 chars)

    assert trim_by("docker run -d", fits) == "docker run -d"
    out = trim_by(TAGLINE, fits)
    assert len(out) * 20 <= 900
    assert out.split()[-1] in [w.rstrip(",.;:-") for w in TAGLINE.split()]


@pytest.mark.parametrize("budget", [8, 12, 25, 40, 80, 200])
def test_the_result_always_fits_and_is_never_empty_for_real_text(budget):
    for text in (TAGLINE, "One command, a hundred agents", "MIT",
                 "Self-hosted CI/CD with Gitspaces and artifact registries"):
        out = trim_to(text, budget)
        assert len(out) <= budget
        assert out, f"{text!r} at {budget} produced nothing"
