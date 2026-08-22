"""The FACTS bundle: everything fetched deterministically from an upstream API.

This is the ground truth for the whole pipeline. `DEVELOPMENT.md` is emphatic that
every claim on screen is a hostage -- star counts and ages go stale -- so no
number reaches the screen unless it can be traced back to a field in here.
"""
from __future__ import annotations

import math

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SourceRef(BaseModel):
    """Where one fact came from, so the UI can show provenance."""

    api: str
    url: str
    fetched_at: datetime


class GitHubFacts(BaseModel):
    kind: Literal["github"] = "github"
    owner: str
    repo: str
    full_name: str
    url: str
    homepage: str | None = None
    description: str | None = None
    stars: int
    forks: int
    open_issues: int
    watchers: int
    licence: str | None = None
    language: str | None = None
    languages: dict[str, int] = Field(default_factory=dict)
    topics: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    pushed_at: datetime | None = None
    latest_release: str | None = None
    latest_release_at: datetime | None = None
    default_branch: str = "main"
    archived: bool = False
    age_days: int | None = None
    #: derived and supplied so the model never has to compute them. It computed
    #: "332 days ago" for a repo pushed eight days earlier -- an invented figure
    #: that was also wrong, and each repair round produced a different one.
    days_since_push: int | None = None
    days_since_release: int | None = None


class HuggingFaceFacts(BaseModel):
    kind: Literal["huggingface"] = "huggingface"
    model_id: str
    url: str
    author: str | None = None
    downloads: int | None = None
    downloads_all_time: int | None = None
    likes: int | None = None
    pipeline_tag: str | None = None
    library_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    licence: str | None = None
    base_model: str | None = None
    created_at: datetime | None = None
    last_modified: datetime | None = None
    gated: bool = False
    card_data: dict[str, Any] = Field(default_factory=dict)


class FactsBundle(BaseModel):
    """What `ingest` writes. Consumed by `content` as the only permitted source
    of numbers, names, licences and install commands."""

    slug: str
    display_name: str
    primary_url: str
    fetched_at: datetime = Field(default_factory=_now)
    github: GitHubFacts | None = None
    huggingface: HuggingFaceFacts | None = None
    readme_markdown: str | None = None
    readme_source: str | None = None
    supplied_markdown: str | None = None
    supplied_markdown_name: str | None = None
    install_commands: list[str] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)

    def headline_figures(self) -> list[tuple[str, str]]:
        """The few real figures, labelled, for showing back to a model.

        `numeric_vocabulary` holds hundreds of accepted spellings and round-downs
        -- useful for checking, useless for instructing. This is the short list
        a repair prompt can name.
        """
        def compact(n: int) -> str:
            for cut, suffix in ((1_000_000, "M"), (1_000, "K")):
                if n >= cut:
                    return (f"{n // cut}{suffix}" if n >= cut * 100
                            else f"{n / cut:.1f}".removesuffix(".0") + suffix)
            return str(n)

        out: list[tuple[str, str]] = []
        if self.github:
            for label, value in (("stars", self.github.stars),
                                 ("forks", self.github.forks),
                                 ("open issues", self.github.open_issues),
                                 ("days old", self.github.age_days)):
                if value:
                    out.append((label, f"{value:,} ({compact(value)})"))
        if self.huggingface:
            for label, value in (("downloads in the last 30 days",
                                  self.huggingface.downloads),
                                 ("downloads all time",
                                  self.huggingface.downloads_all_time),
                                 ("likes", self.huggingface.likes)):
                if value:
                    out.append((label, f"{value:,} ({compact(value)})"))
        return out

    def numeric_vocabulary(self) -> set[str]:
        """Every number a downstream claim may legitimately use.

        Includes the raw integer, a comma-grouped form and the compact forms the
        scripts actually use on screen ("68K", "8.1M"), plus small round-downs
        such as "100+" so an LLM can honestly write "100+ agents" for 118.
        """
        out: set[str] = set()

        def add(n: int | None) -> None:
            if n is None:
                return
            out.add(str(n))
            out.add(f"{n:,}")
            for unit, size in (("K", 1_000), ("M", 1_000_000), ("B", 1_000_000_000)):
                if n >= size:
                    # "194K", "194.5K", and the "+" forms -- "194K+ stars" for
                    # 194,467 is honest and conservative, and is how these
                    # figures are actually written on screen
                    out.add(f"{n // size}{unit}")
                    out.add(f"{n // size}{unit}+")
                    out.add(f"{n / size:.1f}{unit}")
                    out.add(f"{n / size:.1f}{unit}+")
                    # the truncated form as well as the rounded one: 1,373,584
                    # is "1.4M" rounded and "1.3M" truncated, and there really
                    # are 1.3 million of them. Understating is honest --
                    # overstating is the thing this table exists to prevent --
                    # and a model told to pick one figure should not lose a
                    # generation for picking the conservative one.
                    truncated = math.floor(n / size * 10) / 10
                    out.add(f"{truncated:.1f}{unit}")
                    out.add(f"{truncated:.1f}{unit}+")
            # honest round-downs: 118 -> "100+", 68041 -> "68000+"
            for digits in range(1, len(str(n))):
                floor = int(str(n)[: len(str(n)) - digits] + "0" * digits)
                if floor:
                    out.add(f"{floor}+")
                    out.add(f"{floor}")

        if self.github:
            for value in (
                self.github.stars,
                self.github.forks,
                self.github.open_issues,
                self.github.watchers,
                self.github.age_days,
            ):
                add(value)
        if self.huggingface:
            for value in (
                self.huggingface.downloads,
                self.huggingface.downloads_all_time,
                self.huggingface.likes,
            ):
                add(value)
            if self.huggingface.downloads is not None:
                # `downloads` is Hugging Face's last-30-days figure, so any
                # honest sentence about it says "in 30 days" -- and the window
                # is part of the fact, not a number the model invented. Without
                # this, every script describing HF downloads is rejected for
                # stating the period the figure is measured over.
                out.add("30")
        return out
