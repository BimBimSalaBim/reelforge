"""Fetch a Hugging Face model (or dataset) card and its counters."""
from __future__ import annotations

import re
from datetime import datetime, timezone

import httpx

from app.config import get_config, secret
from app.models.facts import HuggingFaceFacts, SourceRef

API = "https://huggingface.co"
URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?huggingface\.co/"
    r"(?:(?P<kind>models|datasets)/)?"
    r"(?P<id>[^/\s#?]+(?:/[^/\s#?]+)?)",
    re.I,
)
#: paths that are site chrome, not a model id
RESERVED = {"docs", "blog", "spaces", "pricing", "login", "join", "settings", "papers"}


def matches(url: str) -> bool:
    match = URL_RE.match(url.strip())
    return bool(match and match["id"].split("/")[0].lower() not in RESERVED)


def parse(url: str) -> tuple[str, str]:
    match = URL_RE.match(url.strip())
    if not match:
        raise ValueError(f"not a Hugging Face URL: {url!r}")
    return (match["kind"] or "models"), match["id"]


def _client() -> httpx.Client:
    cfg = get_config()
    headers = {"Accept": "application/json"}
    token = secret(cfg.ingest.hf_token_env)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=API, headers=headers,
                        timeout=cfg.ingest.timeout_seconds, follow_redirects=True,
                        transport=httpx.HTTPTransport(retries=2))


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch(url: str) -> tuple[HuggingFaceFacts, str | None, list[SourceRef]]:
    kind, model_id = parse(url)
    now = datetime.now(timezone.utc)
    sources: list[SourceRef] = []

    with _client() as client:
        endpoint = "/api/models/" if kind == "models" else "/api/datasets/"
        from app.ingest.github import get_with_retry

        response = get_with_retry(client, f"{endpoint}{model_id}")
        if response.status_code == 404:
            raise LookupError(f"huggingface.co/{model_id} not found (or gated)")
        response.raise_for_status()
        data = response.json()
        sources.append(SourceRef(api=f"hf.{kind}", url=str(response.url), fetched_at=now))

        card = None
        for branch in (data.get("sha") and "main" or "main",):
            raw = client.get(f"/{model_id}/raw/{branch}/README.md")
            if raw.status_code == 200:
                card = raw.text
                sources.append(SourceRef(api="hf.card", url=str(raw.url), fetched_at=now))
                break

    card_data = data.get("cardData") or {}
    base_model = card_data.get("base_model")
    if isinstance(base_model, list):
        base_model = base_model[0] if base_model else None

    facts = HuggingFaceFacts(
        model_id=data.get("id", model_id),
        url=f"{API}/{model_id}",
        author=data.get("author") or (model_id.split("/")[0] if "/" in model_id else None),
        downloads=data.get("downloads"),
        downloads_all_time=data.get("downloadsAllTime"),
        likes=data.get("likes"),
        pipeline_tag=data.get("pipeline_tag"),
        library_name=data.get("library_name"),
        tags=data.get("tags", []),
        licence=card_data.get("license") or _licence_from_tags(data.get("tags", [])),
        base_model=base_model,
        created_at=_dt(data.get("createdAt")),
        last_modified=_dt(data.get("lastModified")),
        gated=bool(data.get("gated")),
        card_data=card_data,
    )
    cfg = get_config()
    if card and len(card) > cfg.ingest.readme_max_chars:
        card = card[: cfg.ingest.readme_max_chars] + "\n\n[... model card truncated ...]"
    return facts, card, sources


def _licence_from_tags(tags: list[str]) -> str | None:
    for tag in tags:
        if tag.startswith("license:"):
            return tag.split(":", 1)[1]
    return None
