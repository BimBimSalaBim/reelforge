"""System endpoints: provider health, templates, queue state, progress stream."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.config import get_config
from app.models.job import STAGE_ORDER
from app.progress import backlog, subscribe
from app.runner import mode
from app.store import JobStore
from app.templates import list_templates

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health() -> dict:
    return {"ok": True, "executor": mode()}


@router.get("/templates")
def templates() -> list[dict]:
    return list_templates()


@router.get("/stages")
def stages() -> list[dict]:
    descriptions = {
        "ingest": "Fetch the facts from GitHub or Hugging Face",
        "content": "Write the script, fact sheet, cover spec and platform copy",
        "cover": "Render the cover image",
        "audio": "Synthesize or accept the narration",
        "align": "Align the narration to the phrase list",
        "storyboard": "Write the storyboard and prove it renders",
        "render": "Render and encode the video",
        "verify": "Check the encoded file against platform requirements",
        "package": "Assemble the delivery bundle",
    }
    return [{"stage": s.value, "description": descriptions.get(s.value, "")}
            for s in STAGE_ORDER]


#: Health probes are network calls to third parties, and one unreachable
#: endpoint used to stall the whole response: measured at 16.3 s with a stopped
#: vLLM in the list, against 8 ms for every other endpoint. That delay landed on
#: the "New reel" form, which waits for this.
PROBE_TIMEOUT = 4.0
#: Reachability does not change second to second, and the form is opened
#: repeatedly. Cached against the configuration fingerprint so a settings change
#: invalidates it immediately.
PROBE_TTL = 30.0

_probe_cache: dict[str, Any] = {}


def _probe_all(cfg) -> dict:
    """Probe every profile at once, with a short deadline on each.

    Concurrently, because these are independent network calls and the slowest
    one should set the total, not the sum.
    """
    from concurrent.futures import ThreadPoolExecutor

    from app.providers.llm import build_llm
    from app.providers.tts import list_voices

    def llm_probe(item):
        name, profile = item
        entry = {"provider": name, "adapter": profile.adapter,
                 "label": profile.display(), "model": profile.model,
                 "configured": name == cfg.llm.active}
        try:
            entry |= build_llm("content", cfg, {"profile": name}).health()
        except Exception as exc:
            entry |= {"reachable": False, "error": str(exc)[:200]}
        entry["provider"] = name
        return entry

    def tts_probe(item):
        name, profile = item
        entry = {"provider": name, "adapter": profile.adapter,
                 "label": profile.display(), "configured": name == cfg.tts.active}
        try:
            entry |= list_voices(cfg, name)
        except Exception as exc:
            entry |= {"reachable": False, "error": str(exc)[:200]}
        entry["provider"] = name
        return entry

    llm_items = list(cfg.llm.profiles.items())
    tts_items = list(cfg.tts.profiles.items())
    workers = max(2, min(12, len(llm_items) + len(tts_items)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        llm_futures = [pool.submit(llm_probe, item) for item in llm_items]
        tts_futures = [pool.submit(tts_probe, item) for item in tts_items]
        llm = [f.result() for f in llm_futures]
        tts = [f.result() for f in tts_futures]
    return {"llm": llm, "tts": tts}


@router.get("/config/providers")
def providers(refresh: bool = False) -> dict:
    """What is reachable right now, so the UI can grey out what is not.

    Reports configured *profiles* rather than adapter types: several profiles
    can share an adapter, and which one is reachable is a question about the
    endpoint and its key, not about the code that talks to it.

    Every probe is free -- model listings and subscription reads, never a
    generation or a synthesis.
    """
    import time

    from app.settings_store import fingerprint

    cfg = get_config()
    stamp = (fingerprint(), )
    cached = _probe_cache.get("value")
    if (not refresh and cached and _probe_cache.get("stamp") == stamp
            and time.monotonic() - _probe_cache.get("at", 0) < PROBE_TTL):
        probed = cached
    else:
        probed = _probe_all(cfg)
        _probe_cache.update({"value": probed, "stamp": stamp, "at": time.monotonic()})

    return {
        "llm": {"selected": cfg.llm.active, "providers": probed["llm"],
                "roles": {k: v.model_dump(exclude_none=True)
                          for k, v in cfg.llm.roles.items()}},
        "tts": {"selected": cfg.tts.active, "providers": probed["tts"]},
        "render": cfg.render.model_dump(),
        "approval": cfg.approval.model_dump(),
        "executor": mode(),
        "burn_captions": cfg.content.burn_captions,
        "fact_check": cfg.content.fact_check,
    }


@router.get("/images/frame")
def image_frame() -> dict:
    """The geometry the reel-frame preview draws against.

    These constants live in three modules -- app/images.py, the deterministic
    renderer, and video/sbkit.py, which this project may not edit -- and three
    of them moved in a single afternoon while fixing a screenshot that ran off
    the top of a frame. Retyping them into JavaScript would mean a preview that
    silently stops agreeing with the renderer, which is worse than no preview.
    So they are served.
    """
    from app import images
    from app.render import fallback_storyboard as fb

    # SAFE_* and the full-bleed treatments are declared inside the emitted
    # storyboard, which is the only place they exist; read them from there
    # rather than keeping a second copy that can disagree.
    tc = fb.template_constants()

    return {
        "frame": {"w": images.FRAME_W, "h": images.FRAME_H},
        "panel": {"w": images.PANEL_W, "max_h": images.PANEL_MAX_H,
                  "min_h": images.PANEL_MIN_H,
                  "top": fb.PANEL_TOP, "bottom": fb.PANEL_BOTTOM},
        "safe": {"top": tc["SAFE_TOP"], "bottom": tc["SAFE_BOTTOM"],
                 "side": tc["SAFE_SIDE"]},
        "full_bleed": {"edge_at_safe": tc["EDGE_AT_SAFE"], "dim": tc["FULL_BLEED_DIM"],
                       "scrim_top": tc["BOTTOM_SCRIM_TOP"],
                       "scrim_max": tc["BOTTOM_SCRIM_MAX"]},
        # The eyebrow sits at y=252 and the burned-in captions occupy roughly
        # 1450-1535. Note that PANEL_BOTTOM (1470) is already inside that band:
        # a bottom-placed panel overlaps the captions by 20px, which is a real
        # defect the preview is meant to make visible.
        "eyebrow": {"y": 252, "font_px": 31, "track": 6, "pad_x": 30, "pad_y": 17},
        "captions": {"top": 1450, "bottom": 1535},
        "upload": {"max_bytes": images.MAX_BYTES,
                   "max_edge": images.MAX_SOURCE_EDGE,
                   "wide_ratio": images.WIDE_RATIO,
                   "allowed": sorted(images.ALLOWED_SUFFIXES)},
        "roles": {key: value["eyebrow"] for key, value in images.ROLES.items()},
    }


@router.get("/config/profiles")
def profiles_only() -> dict:
    """Names and models with no network probing at all.

    What a form needs to render. Reachability arrives separately so opening a
    form never waits on a third party.
    """
    cfg = get_config()
    return {
        "llm": {"selected": cfg.llm.active,
                "providers": [{"provider": n, "adapter": p.adapter,
                               "label": p.display(), "model": p.model}
                              for n, p in cfg.llm.profiles.items()]},
        "tts": {"selected": cfg.tts.active,
                "providers": [{"provider": n, "adapter": p.adapter,
                               "label": p.display()}
                              for n, p in cfg.tts.profiles.items()]},
        "executor": mode(),
        # the new-reel form defaults its captions box and fact-check menu here
        "burn_captions": cfg.content.burn_captions,
        "fact_check": cfg.content.fact_check,
    }


@router.post("/config/tts/key")
def select_tts_key(label: str | int | None = None) -> dict:
    """Pin an ElevenLabs key, or clear the pin to rotate automatically.

    Rotation already happens on its own when a key runs out of credit; this is
    for choosing one deliberately.
    """
    from app.providers.tts import build_tts

    cfg = get_config()
    engine = build_tts(cfg, {"provider": "elevenlabs"})
    if not hasattr(engine, "keys"):
        raise HTTPException(400, "the selected TTS provider does not use API keys")
    if label is None:
        return {"pinned": False, "keys": engine.use_any_key()}
    try:
        engine.select_key(label)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from None
    return {"pinned": True, "keys": engine.keys.as_dict()}


# `GET /api/queue` lives in app/api/routes_queue.py now. It was moved rather
# than duplicated: two routers declaring the same path is not an error in
# FastAPI -- the first registered wins and the second is silently dead.


@router.get("/jobs/{job_id}/events")
async def events(job_id: str):
    """Live progress over server-sent events."""
    store = JobStore()
    try:
        store.load(job_id)
    except FileNotFoundError:
        raise HTTPException(404, f"no such job: {job_id}") from None

    async def stream():
        seen = 0
        for event in backlog(job_id):
            seen += 1
            yield {"event": "progress", "data": json.dumps(event)}

        loop = asyncio.get_event_loop()
        iterator = subscribe(job_id)
        live = True
        while True:
            event = await loop.run_in_executor(None, lambda: next(iterator, None))
            if event is not None and event.get("type") != "heartbeat":
                yield {"event": "progress", "data": json.dumps(event)}
                continue
            if event is None:
                live = False
            # No broker, or a quiet moment: tail the on-disk log so the browser
            # still sees progress. Without this the panel was blank for the
            # whole of a long stage whenever Redis was absent.
            await asyncio.sleep(0.0 if live else 1.0)
            fresh = backlog(job_id, since=seen)
            for item in fresh:
                seen += 1
                yield {"event": "progress", "data": json.dumps(item)}
            if not live and not fresh:
                await asyncio.sleep(1.0)

    return EventSourceResponse(stream())
