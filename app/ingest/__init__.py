"""Ingest dispatcher: a URL and/or an uploaded markdown file -> FactsBundle."""
from __future__ import annotations

import re
from pathlib import Path

from app.models.facts import FactsBundle
from app.store import slugify


class IngestError(RuntimeError):
    pass


def detect(url: str) -> str:
    from app.ingest import github, huggingface

    url = (url or "").strip()
    if github.matches(url):
        return "github"
    if huggingface.matches(url):
        return "huggingface"
    raise IngestError(
        f"cannot tell what {url!r} is. Give a github.com/<owner>/<repo> or "
        "huggingface.co/<model> URL."
    )


def ingest(
    url: str | None = None,
    *,
    markdown_path: Path | None = None,
    markdown_text: str | None = None,
    slug: str | None = None,
) -> FactsBundle:
    """Build the facts bundle.

    A URL alone is the common case. An uploaded `.md` is merged in alongside it
    -- the URL still gets fetched, because the upload carries prose and the API
    carries the numbers, and only the numbers are trustworthy.
    """
    from app.ingest import github, huggingface

    if not url and not (markdown_path or markdown_text):
        raise IngestError("give a URL, an uploaded markdown file, or both")

    supplied = markdown_text
    supplied_name = None
    if markdown_path:
        supplied = markdown_path.read_text(encoding="utf-8", errors="replace")
        supplied_name = markdown_path.name

    if not url:
        title = _title_from_markdown(supplied or "") or "untitled"
        return FactsBundle(
            slug=slugify(slug or title), display_name=title,
            primary_url="", supplied_markdown=supplied,
            supplied_markdown_name=supplied_name,
            install_commands=github.install_commands(supplied or ""),
        )

    kind = detect(url)
    if kind == "github":
        facts, readme, sources, installs = github.fetch(url)
        return FactsBundle(
            slug=slugify(slug or facts.repo), display_name=facts.repo,
            primary_url=facts.url, github=facts,
            readme_markdown=readme, readme_source="github.readme",
            supplied_markdown=supplied, supplied_markdown_name=supplied_name,
            install_commands=installs or github.install_commands(supplied or ""),
            sources=sources,
        )

    facts, card, sources = huggingface.fetch(url)
    name = facts.model_id.split("/")[-1]
    return FactsBundle(
        slug=slugify(slug or name), display_name=name,
        primary_url=facts.url, huggingface=facts,
        readme_markdown=card, readme_source="hf.card",
        supplied_markdown=supplied, supplied_markdown_name=supplied_name,
        install_commands=github.install_commands((card or "") + "\n" + (supplied or "")),
        sources=sources,
    )


def _title_from_markdown(text: str) -> str | None:
    match = re.search(r"^#\s+(.+)$", text, re.M)
    return match.group(1).strip() if match else None
