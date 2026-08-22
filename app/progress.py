"""Progress events: worker -> Redis -> the browser.

Job state lives on disk and is the record of what happened. This is the live
commentary while a stage runs, which is a different thing: it is high-frequency,
disposable, and nobody needs it after the fact. Publishing it through Redis
keeps those two concerns apart -- a render emitting a line every 120 frames must
never rewrite `job.json`.

Degrades quietly. If Redis is not reachable the pipeline still runs; only the
live view goes away.
"""
from __future__ import annotations

import json
import time
from typing import Iterator

from app.config import get_config

_client = None


def client():
    global _client
    if _client is None:
        import redis

        cfg = get_config()
        _client = redis.Redis.from_url(cfg.queue.broker_url, decode_responses=True)
    return _client


def channel(job_id: str) -> str:
    return f"{get_config().queue.progress_channel_prefix}:{job_id}"


#: How many events to keep on disk per job.
FILE_BACKLOG = 400


def _log_path(job_id: str):
    from app.config import get_config

    return get_config().paths.jobs / job_id / "progress.jsonl"


def _append_file(job_id: str, payload: str) -> None:
    """Keep a copy on disk beside the job.

    Redis is only present under compose. Running inline -- which is the default
    for local development -- every event was silently dropped, so the activity
    panel stayed empty during exactly the stages that take longest and where a
    user most needs to know something is still happening.
    """
    try:
        path = _log_path(job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as fh:
            fh.write(payload + "\n")
        # trim occasionally rather than on every line
        if path.stat().st_size > 256_000:
            lines = path.read_text().splitlines()[-FILE_BACKLOG:]
            path.write_text("\n".join(lines) + "\n")
    except Exception:
        pass


def publish(job_id: str, event: dict) -> None:
    event.setdefault("ts", time.time())
    payload = json.dumps(event)
    _append_file(job_id, payload)
    try:
        conn = client()
        conn.publish(channel(job_id), payload)
        # a short backlog so a browser that connects mid-stage sees context
        key = f"{channel(job_id)}:log"
        conn.rpush(key, payload)
        conn.ltrim(key, -200, -1)
        conn.expire(key, 86400)
    except Exception:
        pass


def backlog(job_id: str, since: int = 0) -> list[dict]:
    """Recent events, from Redis if it is there and from disk if it is not."""
    try:
        rows = client().lrange(f"{channel(job_id)}:log", 0, -1)
        if rows:
            return [json.loads(x) for x in rows][since:]
    except Exception:
        pass
    try:
        lines = _log_path(job_id).read_text().splitlines()[-FILE_BACKLOG:]
        return [json.loads(line) for line in lines[since:] if line.strip()]
    except Exception:
        return []


def file_event_count(job_id: str) -> int:
    try:
        return sum(1 for line in _log_path(job_id).read_text().splitlines() if line.strip())
    except Exception:
        return 0


def subscribe(job_id: str, *, timeout: float = 1.0) -> Iterator[dict]:
    """Yield events as they arrive. Ends when the caller stops iterating."""
    try:
        pubsub = client().pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(channel(job_id))
    except Exception:
        return
    try:
        while True:
            message = pubsub.get_message(timeout=timeout)
            if message and message.get("data"):
                try:
                    yield json.loads(message["data"])
                except ValueError:
                    continue
            else:
                yield {"type": "heartbeat"}
    finally:
        try:
            pubsub.close()
        except Exception:
            pass


def reporter(job_id: str, stage: str):
    """A `progress(message)` callable that publishes as it goes."""
    def report(message: str) -> None:
        publish(job_id, {"type": "progress", "stage": stage, "message": message})

    return report
