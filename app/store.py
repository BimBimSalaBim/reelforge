"""The job store: a directory per job, `job.json` as its state.

Writes are atomic (temp file + `os.replace`) so a killed worker can never leave
a half-written state file. Only one process owns a job's `job.json` at a time --
render chunk workers write their own part files and report progress over Redis,
they never touch job state.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterator

from app.config import get_config
from app.models.job import Job, JobSource, ProviderChoice

SLUG_RE = re.compile(r"[^a-z0-9-]+")


def slugify(raw: str) -> str:
    slug = SLUG_RE.sub("-", raw.strip().lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return (slug or "reel")[:41]


def atomic_write(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    mode = "wb" if isinstance(data, bytes) else "w"
    with open(tmp, mode) as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


class JobPaths:
    """Every path in a job, in one place."""

    def __init__(self, root: Path, slug: str):
        self.root = root
        self.slug = slug

    # -- state and stage artifacts
    @property
    def job_json(self) -> Path: return self.root / "job.json"
    @property
    def facts_json(self) -> Path: return self.root / "facts.json"
    @property
    def content_json(self) -> Path: return self.root / "content.json"
    @property
    def platforms_json(self) -> Path: return self.root / "platforms.json"
    @property
    def verify_json(self) -> Path: return self.root / "verify.json"

    # -- the symlink farm over video/, giving this job its own build/
    @property
    def workspace(self) -> Path: return self.root / "video"
    @property
    def build(self) -> Path: return self.workspace / "build"
    @property
    def storyboards(self) -> Path: return self.workspace / "storyboards"
    @property
    def phrases(self) -> Path: return self.workspace / "phrases"
    @property
    def timing_json(self) -> Path: return self.build / f"{self.slug}.timing.json"
    @property
    def storyboard_py(self) -> Path: return self.storyboards / f"{self.slug}.py"
    @property
    def phrases_txt(self) -> Path: return self.phrases / f"{self.slug}.txt"

    # -- media.  `audio_mp3` sits at the workspace parent because a storyboard's
    #    AUDIO is declared relative to the repo root, i.e. one level above video/.
    @property
    def audio_mp3(self) -> Path: return self.root / f"{self.slug}.mp3"
    @property
    def audio_parts(self) -> Path: return self.root / "audio" / "parts"
    @property
    def uploads(self) -> Path: return self.root / "uploads"
    @property
    def images(self) -> Path: return self.uploads / "images"
    @property
    def prepared_images(self) -> Path: return self.root / "images"

    # -- render
    @property
    def render_dir(self) -> Path: return self.root / "render"
    @property
    def parts_dir(self) -> Path: return self.render_dir / "parts"
    @property
    def reel_mp4(self) -> Path: return self.root / f"{self.slug}-reel.mp4"
    @property
    def cover_png(self) -> Path: return self.root / f"{self.slug}-reel.png"
    @property
    def contact_png(self) -> Path: return self.render_dir / "contact.png"
    @property
    def smoke_dir(self) -> Path: return self.render_dir / "smoke"

    # -- delivery
    @property
    def out(self) -> Path: return self.root / "out"
    @property
    def script_txt(self) -> Path: return self.out / f"{self.slug}.txt"
    @property
    def notes_md(self) -> Path: return self.out / f"{self.slug}-reel-notes.md"
    @property
    def metadata(self) -> Path: return self.out / "metadata"
    @property
    def bundle_zip(self) -> Path: return self.out / f"{self.slug}-bundle.zip"

    def rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)


class JobStore:
    def __init__(self, jobs_dir: Path | None = None):
        self.jobs_dir = jobs_dir or get_config().paths.jobs
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    # ---- addressing ----------------------------------------------------
    def dir_for(self, job_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", job_id):
            raise ValueError(f"unsafe job id: {job_id!r}")
        return self.jobs_dir / job_id

    def paths(self, job: Job) -> JobPaths:
        return JobPaths(self.dir_for(job.id), job.slug)

    # ---- lifecycle -----------------------------------------------------
    def create(
        self,
        slug: str,
        source: JobSource,
        *,
        template: str = "cool-indigo",
        captions: bool | None = None,
        fact_check: str | None = None,
        providers: ProviderChoice | None = None,
        manual_stages: list | None = None,
    ) -> Job:
        slug = slugify(slug)
        job_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{slug[:20]}-{uuid.uuid4().hex[:6]}"
        job = Job(
            id=job_id,
            slug=slug,
            source=source,
            template=template,
            captions=(captions if captions is not None
                      else get_config().content.burn_captions),
            fact_check=fact_check or get_config().content.fact_check,
            providers=providers or ProviderChoice(),
            manual_stages=(manual_stages if manual_stages is not None
                           else get_config().approval.manual_stages),
        )
        paths = self.paths(job)
        for directory in (paths.root, paths.uploads, paths.out, paths.render_dir):
            directory.mkdir(parents=True, exist_ok=True)
        job.note(f"job created for {source.url or source.uploaded_markdown_name or slug}")
        self.save(job)
        return job

    def load(self, job_id: str) -> Job:
        path = self.dir_for(job_id) / "job.json"
        if not path.exists():
            raise FileNotFoundError(f"no such job: {job_id}")
        return Job.model_validate_json(path.read_text())

    def save(self, job: Job) -> Job:
        atomic_write(self.dir_for(job.id) / "job.json", job.model_dump_json(indent=2))
        return job

    def delete(self, job_id: str) -> None:
        shutil.rmtree(self.dir_for(job_id), ignore_errors=True)

    def list_ids(self) -> list[str]:
        if not self.jobs_dir.exists():
            return []
        ids = [p.name for p in self.jobs_dir.iterdir() if (p / "job.json").exists()]
        return sorted(ids, reverse=True)

    def iter_jobs(
        self, limit: int | None = None, *, archived: bool | None = False
    ) -> Iterator[Job]:
        """Jobs, newest first.

        `archived=False` (the default) hides archived jobs, `True` shows only
        those, and `None` shows everything. The limit counts jobs *yielded*, so
        asking for 50 current jobs returns 50 even when hundreds are archived.
        """
        count = 0
        for job_id in self.list_ids():
            if limit is not None and count >= limit:
                return
            try:
                job = self.load(job_id)
            except Exception:  # a corrupt job must not break the listing
                continue
            if archived is not None and job.archived != archived:
                continue
            count += 1
            yield job

    # ---- recovery ------------------------------------------------------
    def recover_orphans(self) -> list[tuple[str, str]]:
        """Fail any stage left `running` by a process that is gone.

        Nothing owns a stage across a restart: the inline executor runs it in a
        thread and Celery hands it to a worker, and if either dies mid-stage the
        job keeps saying `running` for ever with no way to retry it. Called at
        startup, when by definition no stage of ours is in flight.

        Marked failed rather than pending so it is visible that something was
        interrupted, and re-runnable from the UI like any other failure.
        """
        from app.models.job import STAGE_ORDER, Status

        recovered: list[tuple[str, str]] = []
        for job in self.iter_jobs(archived=None):
            touched = False
            for stage in STAGE_ORDER:
                state = job.state(stage)
                if state.status is Status.RUNNING:
                    job.mark(
                        stage, Status.FAILED,
                        error="Interrupted: the process running this stage stopped "
                              "before it finished (a restart, a crash, or a kill). "
                              "Nothing was lost except this stage's work -- retry it.",
                    )
                    job.note(f"{stage.value} was interrupted and can be retried")
                    recovered.append((job.id, stage.value))
                    touched = True
            if touched:
                self.save(job)
        return recovered

    # ---- json artifact helpers ----------------------------------------
    def write_json(self, path: Path, payload: dict | list) -> None:
        atomic_write(path, json.dumps(payload, indent=2, default=str))

    def read_json(self, path: Path) -> dict | list:
        return json.loads(path.read_text())
