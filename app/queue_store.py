"""The queue: who is next, and who is holding the slot.

All state, no threads. Everything here is a pure function over `JobStore` plus
one small settings file, which is what lets the ordering, cancellation and pause
tests run with no timing in them at all — the scheduler thread in
`app/scheduler.py` only decides *when* to call `claim_next`.

Why one job at a time: a reel spends about 8.6 of its 11.3 minutes inside the
`content` and `storyboard` stages, both of which are LLM calls. Two concurrent
jobs are, in practice, two concurrent LLM workloads against one GPU — and the
executor used to run exactly that, `ThreadPoolExecutor(max_workers=2)`.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from app.config import get_config
from app.models.job import Job, QueueState, Stage, Status
from app.store import JobStore, atomic_write

QUEUE_FILE = "queue.json"
LOCK_FILE = "queue.lock"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class QueueSettings(BaseModel):
    """The one piece of state that belongs to no particular job."""

    paused: bool = False
    paused_at: datetime | None = None
    paused_reason: str = ""
    #: A run of failures usually means the model server is down, not that five
    #: separate reels are individually broken. Counting them here rather than in
    #: memory means the count survives a restart.
    consecutive_failures: int = 0


def path() -> Path:
    return get_config().paths.data / QUEUE_FILE


def read() -> QueueSettings:
    """Settings, or the safe default.

    A missing or corrupt file means "not paused", matching how the config
    overlay treats unreadable YAML: the queue running is the state that needs no
    explanation.
    """
    try:
        return QueueSettings.model_validate_json(path().read_text())
    except (OSError, ValueError):
        return QueueSettings()


def write(settings: QueueSettings) -> QueueSettings:
    path().parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path(), settings.model_dump_json(indent=2))
    return settings


def set_paused(paused: bool, reason: str = "") -> QueueSettings:
    settings = read()
    settings.paused = paused
    settings.paused_at = _now() if paused else None
    settings.paused_reason = reason if paused else ""
    if not paused:
        settings.consecutive_failures = 0
    return write(settings)


@contextmanager
def locked(timeout: float = 10.0):
    """An advisory lock around claiming the slot.

    The app assumes one API process — `runner`'s pool and `mode()`'s cache
    already do — but this makes the assumption survive a second one starting by
    accident rather than silently running two jobs.
    """
    import fcntl
    import time

    path().parent.mkdir(parents=True, exist_ok=True)
    handle = open(path().parent / LOCK_FILE, "w")
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise TimeoutError("the queue lock is held by another process")
                time.sleep(0.05)
        yield
    finally:
        try:
            fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            handle.close()


# ------------------------------------------------------------------ reading --
def order_key(job: Job) -> tuple:
    """Total and stable even if two jobs somehow share a seq."""
    queued = job.queue.queued_at
    return (job.queue.seq, queued.timestamp() if queued else 0.0, job.id)


def ordered(store: JobStore) -> tuple[Job | None, list[Job]]:
    """(the job holding the slot, the jobs waiting) in the order they will run."""
    running, waiting = None, []
    for job in store.iter_jobs(archived=False):
        if job.queue.state is QueueState.RUNNING:
            running = job
        elif job.queue.state is QueueState.QUEUED:
            waiting.append(job)
    waiting.sort(key=order_key)
    return running, waiting


def next_seq(store: JobStore) -> float:
    _running, waiting = ordered(store)
    return (max((j.queue.seq for j in waiting), default=0.0)) + 1.0


def front_seq(store: JobStore) -> float:
    """Ahead of everything waiting. May go negative; it is a sort key."""
    _running, waiting = ordered(store)
    return (min((j.queue.seq for j in waiting), default=0.0)) - 1.0


def placement(store: JobStore, job_id: str) -> dict:
    running, waiting = ordered(store)
    if running is not None and running.id == job_id:
        return {"state": "running", "position": 0, "ahead": 0}
    for index, job in enumerate(waiting):
        if job.id == job_id:
            return {"state": "queued", "position": index + 1,
                    "ahead": index + (1 if running else 0)}
    return {"state": "idle", "position": None, "ahead": None}


# ------------------------------------------------------------------ writing --
def enqueue(store: JobStore, job_id: str, *, intent: str = "pipeline",
            stage: Stage | None = None, until: Stage | None = None,
            front: bool = False) -> dict:
    """Put a job in the line, or update the entry it already has.

    Idempotent by design: a job occupies at most one slot, so enqueuing one that
    is already queued rewrites its intent in place rather than adding a second
    entry. Two entries would make "cancel this job" ambiguous and the positions
    wrong.
    """
    job = store.load(job_id)
    if job.next_stage() is None and intent == "pipeline":
        raise ValueError("this reel is already finished; there is nothing to run")

    if job.queue.state is QueueState.RUNNING:
        return placement(store, job_id)

    already = job.queue.state is QueueState.QUEUED
    job.queue.state = QueueState.QUEUED
    job.queue.intent = intent
    job.queue.stage = stage
    job.queue.until = until
    job.queue.cancel_requested = False
    job.queue.reason = ""
    if not already or front:
        job.queue.seq = front_seq(store) if front else next_seq(store)
        job.queue.queued_at = _now()
    job.note("queued" + (" at the front" if front else ""))
    store.save(job)
    return placement(store, job_id)


def cancel(store: JobStore, job_id: str, *, reason: str = "cancelled") -> dict:
    """Take a job out of the line, or ask a running one to stop.

    A waiting job leaves immediately. A running one cannot be interrupted
    mid-stage, so it is flagged and the walk stops at the next stage boundary --
    see `JobQueue.cancel_requested` for why that is the only coherent moment.
    """
    job = store.load(job_id)
    was = job.queue.state

    if was is QueueState.RUNNING:
        job.queue.cancel_requested = True
        job.note("cancel requested; it will stop after the current stage")
        store.save(job)
        current = next((s.value for s, state in job.stages.items()
                        if state.status is Status.RUNNING), None)
        return {"was": "running", "cancelled": True, "stops_after_stage": current}

    if was is QueueState.QUEUED:
        job.queue.state = QueueState.IDLE
        job.queue.reason = reason
        job.queue.queued_at = None
        job.note("removed from the queue: " + reason)
        store.save(job)
        return {"was": "queued", "cancelled": True, "stops_after_stage": None}

    return {"was": "idle", "cancelled": False, "stops_after_stage": None}


def reorder(store: JobStore, job_ids: list[str]) -> list[str]:
    """Apply an order to the waiting jobs.

    Accepts a partial list rather than demanding a permutation: a client whose
    list went stale because something was enqueued between its GET and its PUT
    gets a sane result instead of a rejection. Listed jobs go first in the order
    given, everything else keeps its relative order behind them.
    """
    running, waiting = ordered(store)
    by_id = {job.id: job for job in waiting}
    listed = [by_id[jid] for jid in job_ids if jid in by_id]
    rest = [job for job in waiting if job.id not in set(job_ids)]

    for index, job in enumerate(listed + rest, start=1):
        if job.queue.seq != float(index):
            job.queue.seq = float(index)
            store.save(job)
    return [job.id for job in listed + rest]


def move(store: JobStore, job_id: str, *, delta: int) -> list[str]:
    """Nudge one job up or down, which is what an arrow button needs."""
    _running, waiting = ordered(store)
    ids = [job.id for job in waiting]
    if job_id not in ids:
        raise ValueError("that reel is not waiting in the queue")
    index = ids.index(job_id)
    target = min(max(index + delta, 0), len(ids) - 1)
    ids.insert(target, ids.pop(index))
    return reorder(store, ids)


def claim_next(store: JobStore) -> Job | None:
    """Take the single slot, or return None.

    The whole concurrency invariant lives here and nowhere else: at most one job
    may be RUNNING. Everything else in this module is deciding which job gets
    offered to this function.
    """
    with locked():
        if read().paused:
            return None
        running, waiting = ordered(store)
        if running is not None:
            return None

        for candidate in waiting:
            try:
                job = store.load(candidate.id)     # re-read inside the lock
            except FileNotFoundError:
                continue                            # deleted since the scan
            if job.queue.state is not QueueState.QUEUED:
                continue                            # cancelled since the scan
            if job.queue.cancel_requested:
                job.queue.state = QueueState.IDLE
                job.queue.reason = "cancelled before it started"
                store.save(job)
                continue

            job.queue.state = QueueState.RUNNING
            job.queue.started_at = _now()
            job.queue.owner_pid = os.getpid()
            job.note("started from the queue")
            store.save(job)
            return job
    return None


def release(store: JobStore, job_id: str, *, reason: str) -> None:
    """Give the slot back, recording why the job stopped."""
    try:
        job = store.load(job_id)
    except FileNotFoundError:
        return
    job.queue.state = QueueState.IDLE
    job.queue.reason = reason
    job.queue.cancel_requested = False
    job.queue.owner_pid = None
    job.queue.queued_at = None
    job.note("left the queue: " + reason)
    store.save(job)


def record_outcome(reason: str) -> QueueSettings:
    """Pause the queue when it is clearly the server and not the reels.

    Five jobs failing in ninety seconds is not a queue working correctly. The
    counter resets on any success, so an occasional failure never accumulates.
    """
    settings = read()
    limit = get_config().queue.pause_after_consecutive_failures
    if reason.startswith("failed:"):
        settings.consecutive_failures += 1
        if limit and settings.consecutive_failures >= limit:
            settings.paused = True
            settings.paused_at = _now()
            settings.paused_reason = (
                f"{settings.consecutive_failures} reels failed in a row — "
                "check the model server before resuming"
            )
    else:
        settings.consecutive_failures = 0
    return write(settings)


# ----------------------------------------------------------------- snapshot --
def _entry(job: Job, state: str, position: int | None) -> dict:
    stage = job.next_stage()
    running_stage = next((s.value for s, st in job.stages.items()
                          if st.status is Status.RUNNING), None)
    return {
        "id": job.id, "job_id": job.id, "slug": job.slug,
        "state": state, "position": position,
        "stage": running_stage or (stage.value if stage else None),
        "next_stage": stage.value if stage else None,
        "failed_stage": job.failed_stage.value if job.failed_stage else None,
        "progress": job.progress,
        "queued_at": job.queue.queued_at.isoformat() if job.queue.queued_at else None,
        "started_at": job.queue.started_at.isoformat() if job.queue.started_at else None,
        "updated_at": job.updated_at.isoformat(),
        "reason": job.queue.reason or None,
        "cancel_requested": job.queue.cancel_requested,
        "eta_seconds": None,
    }


def snapshot(store: JobStore, *, executor: str = "inline") -> dict:
    """What `GET /api/queue` returns.

    `waiting` is kept as an alias of `queued`, and `counts.waiting` with it,
    because the existing UI reads exactly `counts.running` and `counts.waiting`
    — renaming either blanks its header pill with no error. The *meaning*
    legitimately changes here (queued now means actually scheduled, not merely
    unfinished), so `idle` and `blocked` are added rather than letting anything
    disappear from that UI's view of the world.
    """
    from app.eta import estimate_seconds, stage_medians

    settings = read()
    medians = stage_medians(store)
    running, waiting = ordered(store)

    entries: list[dict] = []
    if running is not None:
        entry = _entry(running, "running", 0)
        entry["eta_seconds"] = estimate_seconds(running, medians)
        entries.append(entry)

    ahead = entries[0]["eta_seconds"] if entries else 0.0
    for index, job in enumerate(waiting, start=1):
        entry = _entry(job, "queued", index)
        own = estimate_seconds(job, medians)
        entry["eta_seconds"] = round((ahead or 0.0) + own, 1)
        ahead = entry["eta_seconds"]
        entries.append(entry)

    blocked, idle, done, failed = [], [], [], []
    for job in store.iter_jobs(archived=False):
        if job.queue.state in (QueueState.RUNNING, QueueState.QUEUED):
            continue
        if job.failed_stage:
            failed.append(_entry(job, "failed", None))
        elif job.next_stage() is None:
            done.append(_entry(job, "done", None))
        elif any(state.status is Status.REVIEW for state in job.stages.values()):
            blocked.append(_entry(job, "blocked", None))
        else:
            idle.append(_entry(job, "idle", None))

    queued = [e for e in entries if e["state"] == "queued"]
    running_entries = [e for e in entries if e["state"] == "running"]

    return {
        "executor": executor,
        "concurrency": 1,
        "paused": settings.paused,
        "paused_at": settings.paused_at.isoformat() if settings.paused_at else None,
        "paused_reason": settings.paused_reason,
        "entries": entries,
        "running": running_entries,
        "queued": queued,
        "waiting": queued,          # alias; see the docstring
        "blocked": blocked,
        "idle": idle,
        "done": done,
        "failed": failed,
        # The gates in force, because a job that stops at every one of them
        # looks like a queue that is not working.
        # config stores these as plain strings; the Job model uses the enum
        "gated": [getattr(s, "value", s) for s in get_config().approval.manual_stages],
        "counts": {
            "running": len(running_entries), "queued": len(queued),
            "waiting": len(queued), "blocked": len(blocked),
            "idle": len(idle), "done": len(done), "failed": len(failed),
        },
    }
