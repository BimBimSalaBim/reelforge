"""How long a reel still has to run, from how long reels have actually taken.

Measured across the jobs on disk rather than guessed: ingest 1.4s, content 207s,
cover 3.5s, audio 15s, align 0.5s, storyboard 309s, render 117s, verify 25s,
package 0.8s — about 11.3 minutes, of which the two LLM stages are 8.6. Those
medians improve on their own as more reels are run.
"""
from __future__ import annotations

from datetime import datetime
from statistics import median

from app.models.job import STAGE_ORDER, Job, Stage, Status
from app.store import JobStore

#: Used until a stage has been run enough times to have a median of its own.
#: Taken from the measurements above, so a first-ever estimate is still close.
FALLBACK_SECONDS: dict[str, float] = {
    "ingest": 2.0, "content": 207.0, "cover": 4.0, "audio": 15.0, "align": 1.0,
    "storyboard": 309.0, "render": 117.0, "verify": 25.0, "package": 1.0,
}

#: Below this a median is one job's luck rather than a pattern.
MIN_SAMPLES = 2


def parse_time(value: str | datetime | None) -> datetime | None:
    """Read a stored timestamp.

    Stage timestamps are written with a `Z` suffix, which Python 3.10's
    `fromisoformat` cannot parse — it returns nothing and the caller silently
    computes an empty table. That happened while measuring the numbers above.
    """
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def stage_medians(store: JobStore) -> dict[str, float]:
    """Median duration per stage, from every completed run on disk."""
    samples: dict[str, list[float]] = {stage.value: [] for stage in STAGE_ORDER}
    for job in store.iter_jobs(archived=None):
        for stage, state in job.stages.items():
            if state.status is not Status.DONE:
                continue
            started, finished = parse_time(state.started_at), parse_time(state.finished_at)
            if started and finished:
                samples[stage.value].append((finished - started).total_seconds())

    out = dict(FALLBACK_SECONDS)
    for name, values in samples.items():
        if len(values) >= MIN_SAMPLES:
            out[name] = round(median(values), 1)
    return out


def estimate_seconds(job: Job, medians: dict[str, float] | None = None) -> float:
    """How much longer this job has, counting only what it has left to do."""
    medians = medians or dict(FALLBACK_SECONDS)
    remaining = 0.0
    for stage in STAGE_ORDER:
        state = job.stages.get(stage)
        if state is None or state.status in (Status.DONE, Status.SKIPPED):
            continue
        remaining += medians.get(stage.value, FALLBACK_SECONDS.get(stage.value, 0.0))

    # A stage already under way has burnt some of its own estimate.
    for stage, state in job.stages.items():
        if state.status is Status.RUNNING:
            started = parse_time(state.started_at)
            if started:
                spent = (datetime.now(started.tzinfo) - started).total_seconds()
                remaining -= min(spent, medians.get(stage.value, 0.0))
    return round(max(remaining, 0.0), 1)


def humanise(seconds: float) -> str:
    if seconds < 90:
        return f"{round(seconds)}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{round(minutes)} min"
    return f"{minutes / 60:.1f} h"


__all__ = ["stage_medians", "estimate_seconds", "humanise", "parse_time",
           "FALLBACK_SECONDS", "Stage"]
