"""Job state. A job *is* a directory; `job.json` is its state.

There is no database. Every artifact is a file you can open, which is how the
rest of this repo already works, and it makes jobs inspectable, resumable and
trivially backed up. Redis carries the queue and progress events only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Stage(str, Enum):
    INGEST = "ingest"
    CONTENT = "content"
    COVER = "cover"
    AUDIO = "audio"
    ALIGN = "align"
    STORYBOARD = "storyboard"
    RENDER = "render"
    VERIFY = "verify"
    PACKAGE = "package"


#: Pipeline order. A stage may only run when every stage before it is DONE.
STAGE_ORDER: list[Stage] = [
    Stage.INGEST,
    Stage.CONTENT,
    Stage.COVER,
    Stage.AUDIO,
    Stage.ALIGN,
    Stage.STORYBOARD,
    Stage.RENDER,
    Stage.VERIFY,
    Stage.PACKAGE,
]


class Status(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    #: finished, but waiting for the user to approve the artifact
    REVIEW = "review"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class QueueState(str, Enum):
    """A job's relationship to the one-at-a-time queue.

    Deliberately separate from `Status`, which is stage-level: a job can be
    QUEUED while every one of its stages is PENDING, and RUNNING while the stage
    it is on is also RUNNING. They answer different questions.
    """

    IDLE = "idle"          # not scheduled; may still have work left to do
    QUEUED = "queued"      # waiting its turn
    RUNNING = "running"    # holding the single slot right now


class JobQueue(BaseModel):
    """Where a job sits in the line, stored with the job.

    In `job.json` rather than a separate index because a second file can
    reference a deleted job, or omit one that thinks it is queued, and then two
    sources disagree with no way to tell which is right. Keeping it here means
    the queue is rebuilt by scanning jobs -- which is what `/api/queue` already
    does -- and survives a restart without any recovery code.
    """

    state: QueueState = QueueState.IDLE
    #: Sort key, low first. A float, not an integer, so moving a job between two
    #: others is one write of the midpoint rather than renumbering every row.
    seq: float = 0.0
    #: "pipeline" walks to the next gate; "stage" runs exactly one stage.
    intent: Literal["pipeline", "stage"] = "pipeline"
    stage: Stage | None = None
    until: Stage | None = None
    queued_at: datetime | None = None
    started_at: datetime | None = None
    #: Honoured between stages only. A render killed mid-flight leaves a
    #: shorter, playable, wrong file (DEVELOPMENT.md gotcha 8), and a killed content
    #: stage leaves half a content.json -- a stage boundary is the only place
    #: the job's state is coherent.
    cancel_requested: bool = False
    #: Which process holds the slot, so a stale RUNNING can be told from a live
    #: one after a crash.
    owner_pid: int | None = None
    #: Why it last left the queue: "complete", "review:content",
    #: "failed:storyboard", "cancelled before it started", ...
    reason: str = ""

    @field_validator("state", mode="before")
    @classmethod
    def _unknown_state_is_idle(cls, value: Any) -> Any:
        """An unrecognised state must not make a job disappear.

        `JobStore.iter_jobs` swallows load errors so one corrupt file cannot
        break the listing -- which means a `job.json` written by a newer build,
        with a state this one has never heard of, would silently vanish from the
        job list rather than fail loudly. Falling back to idle costs a queue
        place and keeps the job.
        """
        known = {member.value for member in QueueState}
        if isinstance(value, QueueState) or value in known:
            return value
        return QueueState.IDLE.value


class StageState(BaseModel):
    status: Status = Status.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    #: named artifact paths, relative to the job directory
    artifacts: dict[str, str] = Field(default_factory=dict)
    #: stage-specific detail surfaced in the UI (token usage, repair attempts,
    #: alignment parameters, verify report summary, ...)
    meta: dict[str, Any] = Field(default_factory=dict)
    #: how many times this stage has been run
    attempts: int = 0

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.finished_at:
            return round((self.finished_at - self.started_at).total_seconds(), 2)
        return None


class JobSource(BaseModel):
    kind: Literal["github", "huggingface", "markdown"] = "github"
    url: str | None = None
    uploaded_markdown_name: str | None = None


class ProviderChoice(BaseModel):
    """Per-job override of the configured providers. Empty means "use config"."""

    llm_provider: str | None = None
    llm_model: str | None = None
    tts_provider: str | None = None
    tts_voice: str | None = None


class JobImage(BaseModel):
    """One uploaded screenshot and how it should be shown.

    The crop is normalised (0-1 of the source) rather than in pixels, so the
    browser that drew it and the renderer that applies it agree without sharing
    a coordinate system, and it survives a re-upload at a different size.
    """

    id: str
    filename: str
    #: what it is a picture of; drives the eyebrow and the order in the reel
    role: Literal["repo", "app", "output", "other"] = "other"
    #: panel spans the full width at its own height; full fills the frame
    fit: Literal["panel", "full"] = "panel"
    #: where a panel sits vertically. Bottom by default: the eyebrow lives at
    #: the top and a panel placed there covers it, which is what one rendered
    #: reel did.
    position: Literal["top", "centre", "bottom"] = "bottom"
    crop_x: float = 0.0
    crop_y: float = 0.0
    crop_w: float = 1.0
    crop_h: float = 1.0
    source_width: int = 0
    source_height: int = 0
    #: the prepared bitmap the renderer pastes, relative to the job root
    prepared: str = ""
    prepared_width: int = 0
    prepared_height: int = 0
    caption: str = ""


class Job(BaseModel):
    id: str
    slug: str
    source: JobSource
    template: str = "cool-indigo"
    #: Burn word-synced captions into the video. Instagram, YouTube and Facebook
    #: all auto-caption on upload now, so burning them in duplicates that -- but
    #: only for viewers who leave the platform's captions on, and burned-in text
    #: is what carries a muted autoplay. Per job because the answer differs by
    #: where the reel is going.
    captions: bool = True
    #: How hard the "every claim on screen is a hostage" rule bites. Strict
    #: sends an unsourced figure back to the model; warn lets the draft through
    #: and shows the findings on the content gate; off skips the check. Off is
    #: a real choice -- a hand-written script, or a repo whose only source for
    #: its headline number is its own README in a form the parser misses.
    fact_check: Literal["strict", "warn", "off"] = "strict"
    #: Optional. With none, the screen catalogue simply never picks a layout
    #: that needs one, and the reel is exactly what it was before.
    images: list[JobImage] = Field(default_factory=list)
    #: Where this job sits in the one-at-a-time queue. Additive with a default,
    #: so every `job.json` already on disk loads unchanged -- no migration
    #: validator needed, unlike `_migrate_review_gates` below, which exists
    #: because a field was reshaped rather than added.
    queue: JobQueue = Field(default_factory=JobQueue)
    providers: ProviderChoice = Field(default_factory=ProviderChoice)
    #: stages that stop for a human instead of flowing into the next one.
    #: Replaces a single on/off switch: all-manual is tedious once the pipeline
    #: is trusted, all-auto spends a render on a script nobody read.
    manual_stages: list[Stage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    #: When set, the job is kept but out of the main list. Archiving rather than
    #: deleting matters here: a finished job holds the rendered video, the cover
    #: and the platform copy, and a failed one holds the error that explains why
    #: -- both are worth keeping long after they stop being current work.
    archived_at: datetime | None = None
    stages: dict[Stage, StageState] = Field(
        default_factory=lambda: {s: StageState() for s in STAGE_ORDER}
    )
    log: list[str] = Field(default_factory=list)

    # ---- queries -------------------------------------------------------
    @model_validator(mode="before")
    @classmethod
    def _migrate_review_gates(cls, data: Any) -> Any:
        """Accept jobs written before gating became per-stage.

        `review_gates: true` meant "pause everywhere", `false` meant "never", so
        each maps cleanly onto the new list. Jobs already on disk load unchanged.
        """
        if not isinstance(data, dict) or "manual_stages" in data:
            return data
        if "review_gates" in data:
            data = dict(data)
            gates = data.pop("review_gates")
            data["manual_stages"] = [s.value for s in STAGE_ORDER] if gates else []
        return data

    @property
    def review_gates(self) -> bool:
        """Whether this job pauses anywhere. Kept for callers that ask."""
        return bool(self.manual_stages)

    def pauses_at(self, stage: Stage) -> bool:
        return stage in self.manual_stages

    def state(self, stage: Stage) -> StageState:
        return self.stages.setdefault(stage, StageState())

    def is_done(self, stage: Stage) -> bool:
        return self.state(stage).status in (Status.DONE, Status.SKIPPED)

    def blockers(self, stage: Stage) -> list[Stage]:
        """Stages that must finish before `stage` may run."""
        idx = STAGE_ORDER.index(stage)
        return [s for s in STAGE_ORDER[:idx] if not self.is_done(s)]

    def next_stage(self) -> Stage | None:
        for stage in STAGE_ORDER:
            if not self.is_done(stage):
                return stage
        return None

    @property
    def progress(self) -> float:
        done = sum(1 for s in STAGE_ORDER if self.is_done(s))
        return round(done / len(STAGE_ORDER), 3)

    @property
    def failed_stage(self) -> Stage | None:
        for stage in STAGE_ORDER:
            if self.state(stage).status is Status.FAILED:
                return stage
        return None

    # ---- mutations -----------------------------------------------------
    def mark(
        self,
        stage: Stage,
        status: Status,
        *,
        error: str | None = None,
        artifacts: dict[str, str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> StageState:
        state = self.state(stage)
        if status is Status.RUNNING:
            state.started_at = _now()
            state.finished_at = None
            state.error = None
            state.attempts += 1
        elif status in (Status.DONE, Status.REVIEW, Status.FAILED, Status.SKIPPED):
            state.finished_at = _now()
        state.status = status
        if error is not None:
            state.error = error
        if artifacts:
            state.artifacts.update(artifacts)
        if meta:
            state.meta.update(meta)
        self.updated_at = _now()
        return state

    def invalidate_from(self, stage: Stage) -> list[Stage]:
        """Re-running a stage invalidates everything downstream of it.

        Editing the script must not leave a video rendered from the old one.
        """
        idx = STAGE_ORDER.index(stage)
        cleared: list[Stage] = []
        for later in STAGE_ORDER[idx + 1 :]:
            state = self.state(later)
            if state.status is not Status.PENDING:
                self.stages[later] = StageState()
                cleared.append(later)
        self.updated_at = _now()
        return cleared

    @property
    def archived(self) -> bool:
        return self.archived_at is not None

    def archive(self) -> "Job":
        self.archived_at = _now()
        self.note("archived")
        return self

    def unarchive(self) -> "Job":
        self.archived_at = None
        self.note("restored from the archive")
        return self

    def note(self, message: str) -> None:
        stamp = _now().strftime("%H:%M:%S")
        self.log.append(f"{stamp}  {message}")
        del self.log[:-500]
        self.updated_at = _now()
