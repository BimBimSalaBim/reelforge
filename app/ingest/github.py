"""Fetch a GitHub repository's facts.

Deterministic on purpose. DEVELOPMENT.md is blunt about this: "Star counts and ages
go stale. Every claim on screen is a hostage." Letting a model read a number out
of a README reintroduces exactly that problem, so every number the pipeline is
allowed to say comes from here, stamped with when it was fetched.
"""
from __future__ import annotations

import base64
import re
from datetime import datetime, timezone

import httpx

from app.config import get_config, secret
from app.models.facts import GitHubFacts, SourceRef

API = "https://api.github.com"
URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s#?]+)",
    re.I,
)
#: install lines worth lifting out of a README for the command bar
INSTALL_RE = re.compile(
    r"^\s*(?:\$|>|›)?\s*((?:npx|npm i|npm install|pnpm|yarn|pip install|uv|uvx|"
    r"brew install|cargo install|go install|docker run|curl -[a-zA-Z]+)\s+[^\n`]{2,72})",
    re.M,
)


def matches(url: str) -> bool:
    return bool(URL_RE.match(url.strip()))


def parse(url: str) -> tuple[str, str]:
    match = URL_RE.match(url.strip())
    if not match:
        raise ValueError(f"not a GitHub repository URL: {url!r}")
    return match["owner"], match["repo"].removesuffix(".git")


def _client() -> httpx.Client:
    cfg = get_config()
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    token = secret(cfg.ingest.github_token_env)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(
        base_url=API, headers=headers, timeout=cfg.ingest.timeout_seconds,
        follow_redirects=True,
        # connection-level retries; status-level ones are handled by get_with_retry
        transport=httpx.HTTPTransport(retries=2),
    )


#: Statuses worth trying again. The GitHub API returns a 5xx often enough that a
#: single one should not fail a job at its very first stage.
RETRY_STATUS = {502, 503, 504, 429}


def get_with_retry(client: httpx.Client, path: str, *, attempts: int = 4,
                   backoff: float = 1.5) -> httpx.Response:
    import time

    last: httpx.Response | None = None
    for attempt in range(attempts):
        try:
            response = client.get(path)
        except httpx.HTTPError:
            if attempt == attempts - 1:
                raise
            time.sleep(backoff ** attempt)
            continue
        if response.status_code not in RETRY_STATUS:
            return response
        last = response
        if attempt < attempts - 1:
            # honour Retry-After when the server sends one
            wait = response.headers.get("retry-after")
            time.sleep(float(wait) if wait and wait.isdigit() else backoff ** attempt)
    return last  # type: ignore[return-value]


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def fetch(url: str) -> tuple[GitHubFacts, str | None, list[SourceRef], list[str]]:
    owner, repo = parse(url)
    now = datetime.now(timezone.utc)
    sources: list[SourceRef] = []

    with _client() as client:
        response = get_with_retry(client, f"/repos/{owner}/{repo}")
        if response.status_code == 404:
            raise LookupError(f"github.com/{owner}/{repo} not found (or private)")
        if response.status_code == 403 and "rate limit" in response.text.lower():
            raise RuntimeError(
                "GitHub API rate limit reached. Set GITHUB_TOKEN to raise it from "
                "60 to 5000 requests an hour."
            )
        response.raise_for_status()
        data = response.json()
        sources.append(SourceRef(api="github.repos", url=str(response.url), fetched_at=now))

        languages: dict[str, int] = {}
        latest_release = latest_release_at = None
        readme = None

        langs = get_with_retry(client, f"/repos/{owner}/{repo}/languages", attempts=2)
        if langs.status_code == 200:
            languages = langs.json()
            sources.append(SourceRef(api="github.languages", url=str(langs.url), fetched_at=now))

        release = get_with_retry(client, f"/repos/{owner}/{repo}/releases/latest", attempts=2)
        if release.status_code == 200:
            payload = release.json()
            latest_release = payload.get("tag_name")
            latest_release_at = _dt(payload.get("published_at"))
            sources.append(SourceRef(api="github.releases", url=str(release.url), fetched_at=now))

        readme_response = get_with_retry(client, f"/repos/{owner}/{repo}/readme", attempts=2)
        if readme_response.status_code == 200:
            payload = readme_response.json()
            if payload.get("encoding") == "base64":
                readme = base64.b64decode(payload["content"]).decode("utf-8", "replace")
            sources.append(
                SourceRef(api="github.readme", url=str(readme_response.url), fetched_at=now)
            )

    created = _dt(data.get("created_at"))
    facts = GitHubFacts(
        owner=owner, repo=repo, full_name=data.get("full_name", f"{owner}/{repo}"),
        url=data.get("html_url", f"https://github.com/{owner}/{repo}"),
        homepage=data.get("homepage") or None,
        description=data.get("description") or None,
        stars=data.get("stargazers_count", 0),
        forks=data.get("forks_count", 0),
        open_issues=data.get("open_issues_count", 0),
        watchers=data.get("subscribers_count", data.get("watchers_count", 0)),
        licence=(data.get("license") or {}).get("spdx_id") or None,
        language=data.get("language"),
        languages=languages,
        topics=data.get("topics", []),
        created_at=created,
        pushed_at=_dt(data.get("pushed_at")),
        latest_release=latest_release,
        latest_release_at=latest_release_at,
        default_branch=data.get("default_branch", "main"),
        archived=bool(data.get("archived")),
        age_days=(now - created).days if created else None,
        days_since_push=((now - _dt(data.get("pushed_at"))).days
                         if data.get("pushed_at") else None),
        days_since_release=((now - latest_release_at).days
                            if latest_release_at else None),
    )
    cfg = get_config()
    if readme and len(readme) > cfg.ingest.readme_max_chars:
        readme = readme[: cfg.ingest.readme_max_chars] + "\n\n[... README truncated ...]"
    return facts, readme, sources, install_commands(readme or "")


def install_commands(readme: str, limit: int = 6) -> list[str]:
    """Pull runnable install lines out of a README.

    The command bar takes real commands only -- `covers.py` renders a fake shell
    prompt otherwise, which is worse than showing none.
    """
    seen: list[str] = []
    for match in INSTALL_RE.finditer(readme):
        command = " ".join(match.group(1).split())
        if command not in seen:
            seen.append(command)
        if len(seen) >= limit:
            break
    return seen
