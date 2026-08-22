"""ReelForge: FastAPI app.

Serves the REST API and the built single-page UI from one process. The worker
runs the same code from `app.tasks`; nothing about a stage differs between them.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_jobs import router as jobs_router
from app.api.routes_queue import router as queue_router
from app.api.routes_settings import router as settings_router
from app.api.routes_system import router as system_router
from app.config import get_config

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s")

UI_DIST = Path(__file__).resolve().parent / "ui" / "dist"
UI_V2 = Path(__file__).resolve().parent / "ui_v2"

@asynccontextmanager
async def lifespan(_app: FastAPI):
    cfg = get_config()
    cfg.paths.jobs.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("reelforge")

    from app.runner import mode
    from app.store import JobStore

    # A stage left `running` belongs to a process that no longer exists -- this
    # runs before anything of ours starts, so any such stage was orphaned.
    try:
        for job_id, stage in JobStore().recover_orphans():
            log.warning("recovered orphaned stage %s in job %s", stage, job_id)
    except Exception as exc:
        log.warning("orphan recovery skipped: %s", exc)

    # Order matters: `recover_orphans` has just marked any interrupted stage as
    # failed, and `scheduler.recover` then takes the job out of the queue.
    # Reversed, a job would be re-queued straight back into the stage that just
    # died, and across a crash loop it would do that for ever.
    from app import scheduler

    try:
        for job_id in scheduler.recover(JobStore()):
            log.warning("job %s was running when the process stopped; "
                        "it left the queue", job_id)
    except Exception as exc:
        log.warning("queue recovery skipped: %s", exc)

    if cfg.queue.start_scheduler and mode() == "inline" and cfg.queue.one_at_a_time:
        scheduler.start()
        log.info("queue: one reel at a time")

    log.info("ready: executor=%s llm=%s tts=%s jobs=%s",
             mode(), cfg.llm.active, cfg.tts.active, cfg.paths.jobs)
    yield
    scheduler.stop()


app = FastAPI(
    title="ReelForge",
    description="Turn a repository URL into a finished vertical reel and the "
                "per-platform copy that ships with it.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
app.include_router(system_router)
app.include_router(jobs_router)
app.include_router(settings_router)
app.include_router(queue_router)


# ------------------------------------------------------------------- ui_v2 --
# Registered BEFORE the single-page block below, and that ordering is the whole
# point: `GET /{path:path}` at the end of this file matches every path there is,
# and Starlette tries routes in the order they were added. Anything registered
# after it is unreachable -- `/v2` would quietly return the old UI, which reads
# as "the new UI failed to load" rather than as a routing mistake.
if UI_V2.is_dir():
    fonts_dir = get_config().fonts.dir_path()
    if fonts_dir.is_dir():
        # The renderer's own Inter and DejaVu faces. The reel-frame preview
        # draws the eyebrow pill and the caption band at the renderer's sizes,
        # so it has to draw them in the renderer's typeface or it lies about how
        # much room the text takes. Mounted before /v2: mounts match by prefix in
        # order, and /v2 would otherwise claim /v2/fonts and look for the file
        # inside app/ui_v2/fonts/.
        app.mount("/v2/fonts", StaticFiles(directory=fonts_dir), name="ui-v2-fonts")

    class RevalidatingStatic(StaticFiles):
        """Always revalidate. Costs a 304; saves an afternoon.

        Without an explicit `Cache-Control`, browsers apply a heuristic freshness
        lifetime and may serve a cached script *without asking* -- which is
        exactly what happened here: a page reload after an edit ran the previous
        version of the file, and the UI looked broken in a way the served bytes
        did not explain.
        """

        def file_response(self, *args, **kwargs):
            response = super().file_response(*args, **kwargs)
            response.headers["cache-control"] = "no-cache, must-revalidate"
            return response

    # html=True serves index.html for "/v2/" and a real 404 for a missing page.
    # A missing v2 page must not fall through to the old UI: these are separate
    # documents, and serving the old one for a broken link hides the break.
    app.mount("/v2", RevalidatingStatic(directory=UI_V2, html=True), name="ui-v2")

    @app.get("/v2", include_in_schema=False)
    def ui_v2_root() -> RedirectResponse:
        """A mount at "/v2" only matches "/v2/...", never the bare path.

        Without this, `GET /v2` falls past the mount to the catch-all below and
        serves the old UI with a 200 -- the single most confusing way this could
        fail, so there is a test for it.
        """
        return RedirectResponse("/v2/", status_code=307)


if UI_DIST.exists():
    # The UI is a single file with no build step, so an assets directory only
    # exists if one was added. Mounting a missing directory is a startup error.
    if (UI_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(UI_DIST / "index.html")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        candidate = UI_DIST / path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(UI_DIST / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def placeholder() -> dict:
        return {"service": "reelforge",
                "note": "the UI has not been built; run `npm run build` in app/ui",
                "docs": "/docs"}
