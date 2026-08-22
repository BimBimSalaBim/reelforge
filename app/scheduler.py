"""One thread that drains the queue, one job at a time.

The interesting function is `tick()`, and it is deliberately synchronous: it
claims one job, runs it to its natural stop, and returns. Every ordering,
cancellation and pause test drives `tick()` directly with no thread and no
sleeps, so none of them can be flaky. The thread below only decides *when* to
call it.
"""
from __future__ import annotations

import threading
import time
import traceback

from app import queue_store
from app.config import get_config
from app.models.job import QueueState, Stage, Status
from app.progress import publish
from app.stages.pipeline import run_one, walk
from app.store import JobStore

_thread: threading.Thread | None = None
_wake = threading.Event()
_stop = threading.Event()
_state = {"last_tick": 0.0, "last_error": "", "running": None}


def status() -> dict:
    """Enough to tell a dead scheduler from an idle one.

    Worth having: if this thread dies, nothing ever runs again and there is no
    error anywhere — jobs simply sit at "queued" for ever. `GET /api/queue`
    surfaces this so that failure is visible rather than mysterious.
    """
    return {
        "alive": bool(_thread and _thread.is_alive()),
        "last_tick": _state["last_tick"],
        "last_error": _state["last_error"],
        "running": _state["running"],
    }


def wake() -> None:
    """Ask the loop to look now rather than at its next poll."""
    _wake.set()


def recover(store: JobStore | None = None) -> list[str]:
    """A job holding the slot when the process died no longer holds anything.

    Must run *after* `JobStore.recover_orphans`, which has just marked the stage
    it was on as FAILED. That ordering is why the job leaves the queue rather
    than going back into it: re-queueing would send it straight back to the
    stage that just died, and across a crash loop it would do that for ever.
    Failed and visible is the same choice `recover_orphans` already makes.

    Jobs that were merely QUEUED need no recovery at all — they are still queued
    in their own `job.json`, and the first tick finds them in the same order.
    """
    store = store or JobStore()
    recovered = []
    for job in store.iter_jobs(archived=None):
        if job.queue.state is QueueState.RUNNING:
            job.queue.state = QueueState.IDLE
            job.queue.reason = "interrupted: the process running it stopped"
            job.queue.owner_pid = None
            job.queue.cancel_requested = False
            job.note("left the queue: the process running it stopped")
            store.save(job)
            recovered.append(job.id)
    return recovered


def _cancelled(job) -> bool:
    return job.queue.cancel_requested


def tick(store: JobStore | None = None) -> str | None:
    """Claim one job and run it to its natural stop. Returns its id, or None."""
    store = store or JobStore()
    job = queue_store.claim_next(store)
    if job is None:
        return None

    _state["running"] = job.id
    publish(job.id, {"type": "queue", "status": "started"})
    try:
        if job.queue.intent == "stage" and job.queue.stage:
            outcome = run_one(job.id, job.queue.stage, store)
        else:
            outcome = walk(job.id, store, until=job.queue.until,
                           should_stop=_cancelled)
    except Exception as exc:
        # One job must never take the queue down with it.
        outcome = f"failed: {type(exc).__name__}: {exc}"
        _state["last_error"] = outcome
        traceback.print_exc()
    finally:
        _state["running"] = None

    queue_store.release(store, job.id, reason=outcome)
    queue_store.record_outcome(outcome)
    publish(job.id, {"type": "queue", "status": "finished", "outcome": outcome})
    return job.id


def _loop() -> None:
    poll = get_config().queue.poll_seconds
    while not _stop.is_set():
        try:
            ran = tick() is not None
        except Exception as exc:
            _state["last_error"] = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
            ran = False
        _state["last_tick"] = time.time()
        if not ran:
            # A poll as well as an event, so a missed wakeup self-heals and
            # anything that writes a queued job.json -- the CLI, a hand edit --
            # joins the queue without having to know this module exists.
            _wake.wait(timeout=poll)
            _wake.clear()


def start() -> None:
    """Idempotent: a second call while the thread is alive does nothing."""
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="reelforge-queue", daemon=True)
    _thread.start()


def stop(timeout: float = 5.0) -> None:
    _stop.set()
    _wake.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=timeout)


__all__ = ["start", "stop", "wake", "tick", "recover", "status",
           "Stage", "Status"]
