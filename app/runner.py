"""How stages get executed: through Celery, or inline in a thread.

Compose runs Celery workers against Redis. But a queue is infrastructure, not
architecture, and requiring it to try the app would be a bad trade -- so when
the broker is absent or unreachable, the same stage functions run in a
background thread instead. Identical behaviour, one process, no Redis.

`REELFORGE_EXECUTOR=inline|celery` forces one; the default probes and decides.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from app.config import get_config
from app.models.job import Stage
from app.stages.pipeline import run_one, walk
from app.store import JobStore

#: One worker, so one pipeline. This was `max_workers=2`, which meant two jobs
#: -- and therefore two LLM workloads -- ran at once against a single local
#: model server. The per-job lock lives in `app.stages.pipeline` now, beside the
#: walk that takes it.
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="reelforge-inline")


@lru_cache(maxsize=1)
def mode() -> str:
    forced = os.environ.get("REELFORGE_EXECUTOR", "").strip().lower()
    if forced in ("inline", "celery"):
        return forced
    try:
        import redis  # noqa: F401
        from celery import Celery  # noqa: F401

        import redis as _redis

        conn = _redis.Redis.from_url(get_config().queue.broker_url,
                                     socket_connect_timeout=1.5)
        conn.ping()
        return "celery"
    except Exception:
        return "inline"


def _run_inline(job_id: str, until: str | None = None) -> None:
    """Thin adapter: the walk itself lives in app.stages.pipeline."""
    walk(job_id, JobStore(), until=Stage(until) if until else None)


def _run_one_inline(job_id: str, stage_value: str) -> None:
    run_one(job_id, Stage(stage_value), JobStore())


def queue_enabled() -> bool:
    """Whether the one-at-a-time queue owns dispatch.

    Inline only. Under Celery the broker owns concurrency, and the honest fix
    there is a pipeline worker at --concurrency=1 rather than a second
    scheduler competing with it.
    """
    return mode() == "inline" and get_config().queue.one_at_a_time


def submit_stage(job_id: str, stage: Stage) -> str:
    """Run one stage. Returns how it was dispatched.

    Joins the queue at the front rather than bypassing it. Bypassing would
    defeat the point: a "retry content" fired while a queued job is on
    `storyboard` is exactly the second concurrent LLM call this exists to
    prevent. At the front because a single-stage run is always an interactive
    act on the reel in front of you -- and when the queue is empty, which is the
    common case, that is indistinguishable from running immediately.
    """
    if queue_enabled():
        from app import queue_store, scheduler

        queue_store.enqueue(JobStore(), job_id, intent="stage", stage=stage,
                            front=True)
        scheduler.wake()
        return "queue"
    if mode() == "celery":
        from app.tasks import RENDER_STAGES, render_stage_task, run_stage_task

        task = render_stage_task if stage in RENDER_STAGES else run_stage_task
        task.delay(job_id, stage.value)
        return "celery"
    _pool.submit(_run_one_inline, job_id, stage.value)
    return "inline"


def submit_pipeline(job_id: str, until: Stage | None = None, *,
                    front: bool = False) -> str:
    """Run stages until completion, a review gate, or a failure.

    Returns "queue" when it joined the line -- which, with an empty queue,
    starts it within a poll. `front` is for approving a gate: the reel already
    had its turn, and being told it is now fifth in line would be baffling.
    """
    if queue_enabled():
        from app import queue_store, scheduler

        queue_store.enqueue(JobStore(), job_id, intent="pipeline", until=until,
                            front=front)
        scheduler.wake()
        return "queue"
    if mode() == "celery":
        from app.tasks import run_pipeline_task

        run_pipeline_task.delay(job_id, until.value if until else None)
        return "celery"
    _pool.submit(_run_inline, job_id, until.value if until else None)
    return "inline"
