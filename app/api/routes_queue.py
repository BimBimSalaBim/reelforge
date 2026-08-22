"""The queue: what is running, what is waiting, and control over the order.

`GET /api/queue` moved here from `routes_system.py` rather than being duplicated
— two routers declaring the same path is not an error in FastAPI, the first
registered wins and the second is silently dead code.

No admin guard: the queue is state, not configuration, and the rest of the job
API is unguarded. A half-guard is worse than either.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from app import queue_store, scheduler
from app.models.job import QueueState
from app.runner import mode, queue_enabled
from app.store import JobStore

router = APIRouter(prefix="/api/queue", tags=["queue"])


def store() -> JobStore:
    return JobStore()


class PauseIn(BaseModel):
    #: Let the reel that is running finish. With False it also asks that job to
    #: stop at its next stage boundary -- because "I paused it and it kept
    #: hammering my model server for another twenty minutes" is the obvious
    #: complaint otherwise.
    finish_current: bool = True
    reason: str = ""


class OrderIn(BaseModel):
    job_ids: list[str]


class MoveIn(BaseModel):
    delta: int = -1


@router.get("")
def queue() -> dict:
    snapshot = queue_store.snapshot(store(), executor=mode())
    snapshot["enforced_by"] = "reelforge" if queue_enabled() else mode()
    snapshot["scheduler"] = scheduler.status()
    snapshot["supported"] = {
        "reorder": queue_enabled(), "pause": queue_enabled(),
        "cancel": "between stages",
    }
    return snapshot


@router.post("/pause")
def pause(payload: PauseIn = Body(default=PauseIn())) -> dict:
    settings = queue_store.set_paused(True, payload.reason or "paused by hand")
    running, _waiting = queue_store.ordered(store())
    stops_after = None
    if running is not None and not payload.finish_current:
        detail = queue_store.cancel(store(), running.id, reason="paused")
        stops_after = detail.get("stops_after_stage")
    return {"paused": True,
            "paused_at": settings.paused_at.isoformat() if settings.paused_at else None,
            "running": running.id if running else None,
            "stops_after_stage": stops_after}


@router.post("/resume")
def resume() -> dict:
    queue_store.set_paused(False)
    scheduler.wake()
    _running, waiting = queue_store.ordered(store())
    return {"paused": False, "next": waiting[0].id if waiting else None}


@router.put("/order")
def reorder(payload: OrderIn = Body(...)) -> dict:
    if not queue_enabled():
        raise HTTPException(501, "Reordering needs the built-in queue. Under the "
                                 "Celery executor the broker holds the order.")
    order = queue_store.reorder(store(), payload.job_ids)
    ignored = [jid for jid in payload.job_ids if jid not in order]
    return {"queued": order, "ignored": ignored}


@router.post("/{job_id}/move")
def move(job_id: str, payload: MoveIn = Body(default=MoveIn())) -> dict:
    try:
        return {"queued": queue_store.move(store(), job_id, delta=payload.delta)}
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/{job_id}")
def enqueue(job_id: str, front: bool = False) -> dict:
    try:
        placement = queue_store.enqueue(store(), job_id, front=front)
    except FileNotFoundError:
        raise HTTPException(404, f"no reel {job_id!r}") from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    scheduler.wake()
    return placement


@router.delete("/{job_id}")
def cancel(job_id: str) -> dict:
    try:
        job = store().load(job_id)
    except FileNotFoundError:
        raise HTTPException(404, f"no reel {job_id!r}") from None
    if job.queue.state is QueueState.IDLE:
        raise HTTPException(409, "that reel is not queued or running")
    detail = queue_store.cancel(store(), job_id, reason="cancelled")
    detail["id"] = job_id
    if detail.get("stops_after_stage"):
        detail["note"] = (
            f"{detail['stops_after_stage']} is running; it will stop when that "
            "stage finishes. Killing it mid-stage would leave a half-written "
            "artifact behind."
        )
    return detail
