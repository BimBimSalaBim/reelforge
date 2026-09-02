"""Celery tasks: one per stage, plus a runner that walks the whole pipeline.

Stages do the work (`app.stages.pipeline`); these only decide *where* it runs
and report progress. Rendering goes to its own queue because it is CPU-bound for
minutes at a time and would otherwise starve the short LLM and network stages.
"""
from __future__ import annotations

from celery import Celery

from app.config import get_config
# Hermes integration: optional Sentry/GlitchTip error tracking (SENTRY_DSN env).
from app.observability import init_sentry

init_sentry()

from app.models.job import Stage
from app.progress import publish, reporter
from app.stages.pipeline import run_stage
from app.store import JobStore

cfg = get_config()
celery_app = Celery("reelforge", broker=cfg.queue.broker_url,
                    backend=cfg.queue.result_backend)
celery_app.conf.update(
    task_serializer="json", result_serializer="json", accept_content=["json"],
    task_track_started=True,
    # a render is minutes of CPU; prefetching would leave workers idle behind it
    worker_prefetch_multiplier=1,
    task_routes={"reelforge.render_stage": {"queue": "render"}},
    task_time_limit=3600, task_soft_time_limit=3300,
)

RENDER_STAGES = {Stage.RENDER, Stage.VERIFY}


def queue_for(stage: Stage) -> str:
    return "render" if stage in RENDER_STAGES else "celery"


@celery_app.task(name="reelforge.run_stage", bind=True)
def run_stage_task(self, job_id: str, stage_value: str) -> dict:
    store = JobStore()
    job = store.load(job_id)
    stage = Stage(stage_value)
    publish(job_id, {"type": "stage", "stage": stage.value, "status": "running"})
    try:
        job = run_stage(job, stage, store, progress=reporter(job_id, stage.value))
    except Exception as exc:
        publish(job_id, {"type": "stage", "stage": stage.value, "status": "failed",
                         "error": str(exc)[:2000]})
        raise
    state = job.state(stage)
    publish(job_id, {"type": "stage", "stage": stage.value,
                     "status": state.status.value,
                     "artifacts": state.artifacts, "meta": _safe(state.meta)})
    return {"job": job_id, "stage": stage.value, "status": state.status.value}


@celery_app.task(name="reelforge.render_stage", bind=True)
def render_stage_task(self, job_id: str, stage_value: str) -> dict:
    """Same work, routed to the render queue."""
    return run_stage_task.run(job_id, stage_value)


@celery_app.task(name="reelforge.run_pipeline", bind=True)
def run_pipeline_task(self, job_id: str, until: str | None = None) -> dict:
    """Walk the pipeline until it finishes, stops for review, or fails.

    The walk itself is `app.stages.pipeline.walk`, shared with the inline
    executor. It used to be a second copy here, and the copies had drifted:
    this one could never publish that the *pipeline* had failed, because
    `run_stage_task` re-raises and the check for it sat after the call.
    """
    from app.stages.pipeline import walk

    outcome = walk(job_id, JobStore(), until=Stage(until) if until else None)
    return {"job": job_id, "outcome": outcome}


def _safe(meta: dict) -> dict:
    """Progress events go to a browser; keep them small and JSON-clean."""
    out = {}
    for key, value in (meta or {}).items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, (list, dict)):
            text = str(value)
            out[key] = value if len(text) < 800 else f"{text[:300]}..."
    return out
