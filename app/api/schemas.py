"""Request and response shapes for the HTTP API."""
from __future__ import annotations

from typing import Any

from typing import Literal

from pydantic import BaseModel, Field

from app.models.job import STAGE_ORDER, Job


class VisualsChoiceIn(BaseModel):
    enabled: bool | None = None
    stills: int | None = Field(default=None, ge=0, le=6)
    clips: int | None = Field(default=None, ge=0, le=3)
    cover: bool | None = None
    music: bool | None = None
    profile: str | None = None


class CreateJobRequest(BaseModel):
    url: str | None = Field(
        default=None,
        description="a github.com/<owner>/<repo> or huggingface.co/<model> URL",
    )
    slug: str | None = None
    template: str = "cool-indigo"
    captions: bool = True
    fact_check: Literal["strict", "warn", "off"] = "strict"
    #: stages that pause for review. None uses the saved default from settings.
    manual_stages: list[str] | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    tts_provider: str | None = None
    tts_voice: str | None = None
    #: generated stills/clips/cover backdrop. Each None means the saved default.
    visuals: VisualsChoiceIn | None = None
    #: start the pipeline immediately rather than waiting for an explicit run
    autostart: bool = True


class StageView(BaseModel):
    stage: str
    status: str
    attempts: int
    error: str | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)
    duration_seconds: float | None = None
    blocked_by: list[str] = Field(default_factory=list)


class JobView(BaseModel):
    id: str
    slug: str
    template: str
    captions: bool = True
    fact_check: str = "strict"
    images: list[dict] = Field(default_factory=list)
    source: dict[str, Any]
    providers: dict[str, Any]
    visuals: dict[str, Any] = Field(default_factory=dict)
    manual_stages: list[str]
    created_at: str
    updated_at: str
    archived: bool = False
    #: what this job will actually use if run now, resolved through the job's
    #: own overrides, the per-role routing and the active profile
    resolved: dict[str, Any] = Field(default_factory=dict)
    progress: float
    next_stage: str | None
    failed_stage: str | None
    stages: list[StageView]
    log: list[str] = Field(default_factory=list)

    @classmethod
    def of(cls, job: Job) -> "JobView":
        return cls(
            id=job.id, slug=job.slug, template=job.template,
            captions=job.captions, fact_check=job.fact_check,
            images=[i.model_dump() for i in job.images],
            source=job.source.model_dump(mode="json"),
            providers=job.providers.model_dump(mode="json"),
            visuals=job.visuals.model_dump(mode="json"),
            manual_stages=[s.value for s in job.manual_stages],
            created_at=job.created_at.isoformat(),
            updated_at=job.updated_at.isoformat(),
            archived=job.archived,
            resolved=_resolve(job),
            progress=job.progress,
            next_stage=job.next_stage().value if job.next_stage() else None,
            failed_stage=job.failed_stage.value if job.failed_stage else None,
            # STAGE_ORDER, not the dict: the UI renders the pipeline in order,
            # and a job created before a stage existed would otherwise omit it
            stages=[
                StageView(
                    stage=stage.value, status=job.state(stage).status.value,
                    attempts=job.state(stage).attempts,
                    error=job.state(stage).error,
                    artifacts=job.state(stage).artifacts,
                    meta=job.state(stage).meta,
                    duration_seconds=job.state(stage).duration_seconds,
                    blocked_by=[b.value for b in job.blockers(stage)],
                )
                for stage in STAGE_ORDER
            ],
            log=job.log[-120:],
        )


def _resolve(job: Job) -> dict[str, Any]:
    """Which model and voice this job would use right now.

    A job carries optional overrides, the settings carry per-role routing, and
    the active profile is the fallback -- three layers, and nothing showed the
    answer. A stale line in the activity log then reads as the current provider.
    """
    from app.config import get_config

    cfg = get_config()
    out: dict[str, Any] = {}
    for role in ("content", "storyboard"):
        override = job.providers.llm_provider
        if override and override in cfg.llm.profiles:
            profile = cfg.llm.profiles[override]
            out[role] = {"profile": override, "model": profile.model,
                         "source": "job override"}
            continue
        name, profile, binding = cfg.llm.profile_for(role)
        out[role] = {
            "profile": name, "model": binding.model or profile.model,
            "source": "role routing" if binding.target() else "active profile",
        }
    from app.stages.pipeline import visuals_settings

    visuals = visuals_settings(job)
    visuals_profile = cfg.visuals.profiles.get(visuals["profile"])
    out["visuals"] = visuals | {
        "adapter": visuals_profile.adapter if visuals_profile else "none",
        "source": "job override" if job.visuals.enabled is not None or job.visuals.profile
                  else "active profile",
    }
    tts_name = job.providers.tts_provider or cfg.tts.active
    tts_profile = cfg.tts.profiles.get(tts_name)
    out["voice"] = {
        "profile": tts_name,
        "adapter": tts_profile.adapter if tts_profile else None,
        "voice": job.providers.tts_voice or (
            (tts_profile.settings().get("voice_id")
             or tts_profile.settings().get("voice")) if tts_profile else None),
        "source": "job override" if job.providers.tts_provider else "active profile",
    }
    return out


class ApproveRequest(BaseModel):
    """Accept a stage's artifact and let the pipeline continue."""

    advance: bool = True


class RunRequest(BaseModel):
    stage: str | None = Field(
        default=None, description="a single stage; omit to run to the next gate"
    )
    until: str | None = None
