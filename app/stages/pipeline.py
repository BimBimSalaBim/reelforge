"""The stage runner: what each pipeline step does to a job.

One function per stage, all with the same shape -- take a job, do the work,
write artefacts into the job directory, record what happened. The Celery tasks
and the API both call these, so there is one definition of what a stage is.

Re-running a stage invalidates everything after it. Editing the script must not
leave a video rendered from the previous one.
"""
from __future__ import annotations

import json
import shutil
from typing import Callable

from app.config import get_config
from app.models.content import ReelContent
from app.models.facts import FactsBundle
from app.models.job import STAGE_ORDER, Job, Stage, Status
from app.models.platform import PlatformBundle
from app.store import JobStore, atomic_write

Progress = Callable[[str], None]


class StageFailed(RuntimeError):
    pass


def _ensure_workspace(paths) -> None:
    """Build (or repair) this job's symlink farm over `video/`.

    Idempotent, and called by every stage that touches the renderer rather than
    once at job creation: a job directory can be copied, restored from a backup
    or resumed after the `video/` path moved, and a farm of stale symlinks is
    worse than no farm at all.
    """
    from app.render.workspace import build_workspace

    build_workspace(paths.workspace)


def _note(job: Job, progress: Progress | None, message: str) -> None:
    job.note(message)
    if progress:
        progress(message)


# ------------------------------------------------------------- 1. ingest ---
def run_ingest(job: Job, store: JobStore, progress: Progress | None = None) -> dict:
    from app.ingest import ingest

    paths = store.paths(job)
    uploaded = None
    if job.source.uploaded_markdown_name:
        candidate = paths.uploads / job.source.uploaded_markdown_name
        uploaded = candidate if candidate.exists() else None

    _note(job, progress, f"fetching facts for {job.source.url or 'the uploaded file'}")
    facts = ingest(job.source.url, markdown_path=uploaded, slug=job.slug)
    atomic_write(paths.facts_json, facts.model_dump_json(indent=2))

    summary = {"slug": facts.slug, "fetched_at": facts.fetched_at.isoformat(),
               "sources": [s.api for s in facts.sources],
               "readme_chars": len(facts.readme_markdown or ""),
               "install_commands": facts.install_commands[:6]}
    if facts.github:
        summary |= {"stars": facts.github.stars, "forks": facts.github.forks,
                    "licence": facts.github.licence, "age_days": facts.github.age_days}
    if facts.huggingface:
        summary |= {"downloads": facts.huggingface.downloads,
                    "likes": facts.huggingface.likes,
                    "licence": facts.huggingface.licence}
    _note(job, progress, f"facts fetched from {', '.join(summary['sources']) or 'upload'}")
    return {"artifacts": {"facts": paths.rel(paths.facts_json)}, "meta": summary}


# ------------------------------------------------------------ 2. content ---
def run_content(job: Job, store: JobStore, progress: Progress | None = None) -> dict:
    from app.providers.llm import build_llm
    from app.render import documents
    from app.stages.content import fact_report, generate_content, generate_platforms
    from app.templates import load_template

    cfg = get_config()
    paths = store.paths(job)
    facts = FactsBundle.model_validate_json(paths.facts_json.read_text())
    template = load_template(job.template)

    overrides = {"provider": job.providers.llm_provider, "model": job.providers.llm_model}
    llm = build_llm("content", cfg, overrides)
    _note(job, progress, f"writing the script with {llm.name}/{llm.model}")

    content_out = generate_content(
        facts, llm, template_hint=template.tone_hint,
        max_attempts=cfg.storyboard.max_repair_attempts,
        fact_check=job.fact_check, progress=progress,
    )
    content: ReelContent = content_out.value

    facts_report = fact_report(content, facts)
    if not facts_report["ok"]:
        _note(job, progress,
              f"{len(facts_report['unsourced'])} number(s) do not trace to the "
              f"facts block or the project's README -- check them on the gate")

    _note(job, progress, "writing the per-platform copy")
    platform_llm = build_llm("content", cfg, overrides)
    platforms_out = generate_platforms(
        content, facts, platform_llm,
        max_attempts=cfg.storyboard.max_repair_attempts, progress=progress,
    )
    platforms: PlatformBundle = platforms_out.value

    atomic_write(paths.content_json, content.model_dump_json(indent=2))
    atomic_write(paths.platforms_json, platforms.model_dump_json(indent=2))

    _ensure_workspace(paths)
    paths.out.mkdir(parents=True, exist_ok=True)
    atomic_write(paths.script_txt, documents.script_txt(content, facts))
    atomic_write(paths.out / "captions.txt",
                 documents.caption_block(content, platforms))
    paths.phrases.mkdir(parents=True, exist_ok=True)
    atomic_write(paths.phrases_txt, documents.phrases_txt(content))

    metadata = documents.metadata_files(content, platforms)
    paths.metadata.mkdir(parents=True, exist_ok=True)
    for name, body in metadata.items():
        atomic_write(paths.metadata / name, body)

    _note(job, progress,
          f"script: {content.word_count} words, {len(content.phrases)} phrases, "
          f"~{content.estimated_seconds():.0f}s")
    return {
        "artifacts": {
            "content": paths.rel(paths.content_json),
            "platforms": paths.rel(paths.platforms_json),
            "script": paths.rel(paths.script_txt),
            "phrases": paths.rel(paths.phrases_txt),
        },
        "meta": {
            "words": content.word_count, "phrases": len(content.phrases),
            "estimated_seconds": content.estimated_seconds(),
            "hashtags": content.hashtags,
            "content_generation": content_out.as_dict(),
            "platform_generation": platforms_out.as_dict(),
            "youtube_title": platforms.youtube.title,
            "facts": facts_report,
            "fact_check": job.fact_check,
        },
    }


# -------------------------------------------------------------- 3. cover ---
def run_cover(job: Job, store: JobStore, progress: Progress | None = None) -> dict:
    from app.render.cover import render_cover

    paths = store.paths(job)
    _ensure_workspace(paths)
    content = ReelContent.model_validate_json(paths.content_json.read_text())
    _note(job, progress, "rendering the cover")
    out, fit_problems = render_cover(content, paths.workspace, paths.cover_png)
    if fit_problems:
        _note(job, progress,
              f"{len(fit_problems)} cover string(s) are clipped: "
              + ", ".join(p["label"] for p in fit_problems))
    return {"artifacts": {"cover": paths.rel(out)},
            "meta": {"motif": content.cover.motif, "bytes": out.stat().st_size,
                     "fit_problems": fit_problems}}


# -------------------------------------------------------------- 4. audio ---
def run_audio(job: Job, store: JobStore, progress: Progress | None = None) -> dict:
    from app.providers.tts import UploadRequired, build_tts, join

    cfg = get_config()
    paths = store.paths(job)
    content = ReelContent.model_validate_json(paths.content_json.read_text())

    provider_name = job.providers.tts_provider or cfg.tts.active
    adapter, _ = cfg.tts.for_profile(provider_name)
    if adapter == "upload":
        if not paths.audio_mp3.exists():
            raise StageFailed(
                "the audio provider is 'upload' but no narration file has been "
                "supplied. Upload one, or choose a TTS provider."
            )
        _note(job, progress, f"using the uploaded narration ({paths.audio_mp3.name})")
        info = {"provider": "upload", "mp3": str(paths.audio_mp3)}
    else:
        engine = build_tts(cfg, {"provider": provider_name,
                                 "voice": job.providers.tts_voice})
        estimate = getattr(engine, "estimate", lambda _t: {})(content.phrase_lines())
        _note(job, progress,
              f"synthesizing {len(content.phrases)} phrases with {provider_name}"
              + (f" ({estimate.get('characters')} characters)" if estimate else ""))
        try:
            spoken = engine.speak_all(
                content.phrases, hints=content.audio.pronunciations,
                progress=lambda frac, msg: progress(msg) if progress else None,
            )
        except UploadRequired as exc:
            raise StageFailed(str(exc)) from None
        info = join(spoken.phrases, content.phrases, paths.audio_mp3,
                    scratch=paths.audio_parts)
        info["provider"] = provider_name
        info["voice"] = spoken.voice
        rotations = getattr(engine, "rotations", [])
        if rotations:
            info["key_rotations"] = rotations
            _note(job, progress, f"rotated API key {len(rotations)} time(s)")

    from app.render.workspace import ffprobe_bin
    import subprocess

    proc = subprocess.run(
        [ffprobe_bin(), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nokey=1:noprint_wrappers=1", str(paths.audio_mp3)],
        capture_output=True, text=True, check=False)
    duration = float(proc.stdout.strip() or 0.0)
    info["duration_seconds"] = round(duration, 3)
    _note(job, progress, f"narration is {duration:.2f}s")

    # The finished video is the narration plus a beat, and verify holds it to
    # the platform window. Every fact needed to know that is available here, so
    # checking it now costs a second instead of a full render -- one job spent
    # 90s rendering 773 frames to be told the reel was 25.77s.
    from app.stages.content import reel_total

    low, high = cfg.content.target_seconds_min, cfg.content.target_seconds_max
    runtime = reel_total(duration, low)
    info["reel_seconds"] = round(runtime, 3)
    if runtime > duration + 1.5:
        _note(job, progress,
              f"holding the end card for {runtime - duration:.1f}s so the reel "
              f"reaches the {low:.0f}s floor")
    if not low <= runtime <= high:
        raise StageFailed(
            f"the narration is {duration:.2f}s, which makes a {runtime:.2f}s reel -- "
            f"outside the {low:.0f}-{high:.0f}s window the platforms want, and "
            f"verify will reject it after the render.\n"
            + ("Re-run content asking for a shorter script, or trim the recording."
               if runtime > high else
               "Even holding the end card for the maximum, this is short. Re-run "
               "content asking for a longer script, or upload a longer recording.")
        )

    return {"artifacts": {"audio": paths.rel(paths.audio_mp3)}, "meta": info}


# -------------------------------------------------------------- 5. align ---
def run_align(job: Job, store: JobStore, progress: Progress | None = None) -> dict:
    from app.stages.align import align_job

    _ensure_workspace(store.paths(job))
    return align_job(job, store, progress)


def stage_images(job: Job, paths) -> list[dict]:
    """Prepared screenshots, copied where the storyboard can open them.

    The storyboard resolves paths from its own `__file__`, which the symlink
    farm puts inside the job directory -- so the bitmaps go beside it rather
    than being referenced from anywhere else, and a chunk process running with
    a different cwd still finds them.
    """
    import shutil

    from app.images import role_eyebrow, role_order

    if not job.images:
        return []

    # the storyboard sits in workspace/storyboards/, and resolves ../images
    destination = paths.workspace / "images"
    destination.mkdir(parents=True, exist_ok=True)

    out = []
    for image in sorted(job.images, key=lambda i: (role_order(i.role), i.id)):
        prepared = paths.root / image.prepared if image.prepared else None
        if not prepared or not prepared.exists():
            continue
        target = destination / prepared.name
        if not target.exists() or target.stat().st_mtime < prepared.stat().st_mtime:
            shutil.copy2(prepared, target)
        out.append({
            "file": prepared.name, "fit": image.fit, "role": image.role,
            "position": image.position,
            "eyebrow": role_eyebrow(image.role), "caption": image.caption,
            "width": image.prepared_width, "height": image.prepared_height,
        })
    return out


# --------------------------------------------------------- 6. storyboard ---
def run_storyboard(job: Job, store: JobStore, progress: Progress | None = None) -> dict:
    from app.providers.llm import build_llm
    from app.stages.storyboard import generate_storyboard, write_fallback
    from app.templates import load_template

    cfg = get_config()
    paths = store.paths(job)
    _ensure_workspace(paths)
    content = ReelContent.model_validate_json(paths.content_json.read_text())
    timing = json.loads(paths.timing_json.read_text())
    from app.stages.content import reel_total

    total = round(reel_total(float(timing["duration"]),
                             cfg.content.target_seconds_min), 2)
    template = load_template(job.template)

    if template.deterministic:
        _note(job, progress, f"template {template.name!r} renders from data, no codegen")
        write_fallback(content, paths.workspace, total,
                       f"{content.slug}.mp3", f"phrases/{content.slug}.txt",
                       captions=job.captions, timing_json=paths.timing_json,
                       images=stage_images(job, paths))
        from app.stages.storyboard import run_smoke

        smoke = run_smoke(paths.workspace, content.slug, paths.smoke_dir,
                          expected_duration=total)
        if not smoke.get("ok"):
            raise StageFailed("the deterministic template failed to render:\n" +
                              "\n".join(p["message"] for p in smoke.get("problems", [])))
        return {"artifacts": {"storyboard": paths.rel(paths.storyboard_py)},
                "meta": {"used_fallback": True, "total": total,
                         "frames": [f["path"] for f in smoke.get("frames", [])]}}

    overrides = {"provider": job.providers.llm_provider, "model": job.providers.llm_model}
    llm = build_llm("storyboard", cfg, overrides)
    vision = build_llm("review", cfg) if cfg.storyboard.vision_review else None
    _note(job, progress, f"writing the storyboard with {llm.name}/{llm.model}")

    result = generate_storyboard(
        content, paths.workspace, paths.timing_json, llm=llm, total=total,
        audio_rel=f"{content.slug}.mp3", phrases_rel=f"phrases/{content.slug}.txt",
        smoke_dir=paths.smoke_dir, template_example=template.example_source,
        vision_llm=vision, captions=job.captions,
        images=stage_images(job, paths), progress=progress,
    )
    meta = result.as_dict() | {"total": total}
    _note(job, progress,
          f"storyboard ready after {len(result.attempts)} attempt(s)"
          + (" (fallback)" if result.used_fallback else ""))
    return {"artifacts": {"storyboard": paths.rel(result.path)}, "meta": meta}


# ------------------------------------------------------------- 7. render ---
def run_render(job: Job, store: JobStore, progress: Progress | None = None) -> dict:
    from app.render.chunked import render

    paths = store.paths(job)
    _ensure_workspace(paths)
    total = float(job.state(Stage.STORYBOARD).meta.get("total") or 0.0)
    if not total:
        from app.stages.content import reel_total

        timing = json.loads(paths.timing_json.read_text())
        total = round(reel_total(float(timing["duration"]),
                                 get_config().content.target_seconds_min), 2)

    _note(job, progress, f"rendering {total:.2f}s")
    result = render(
        paths.workspace, job.slug, total, paths.reel_mp4,
        progress=lambda tag, frac, msg: progress(f"{tag} {frac * 100:.0f}%")
        if progress else None,
    )
    _note(job, progress,
          f"rendered {result.frames} frames in {result.seconds}s "
          f"({result.mode}, {result.chunks} chunk(s))")
    if result.loudness:
        _note(job, progress,
              f"audio at {result.loudness['loudness']:.1f} LUFS / "
              f"{result.loudness['true_peak']:.1f} dBTP after "
              f"{len(result.loudness['passes'])} normalisation pass(es)")
    return {"artifacts": {"video": paths.rel(paths.reel_mp4)},
            "meta": {"frames": result.frames, "expected_frames": result.expected_frames,
                     "seconds": result.seconds, "mode": result.mode,
                     "chunks": result.chunks, "total": total,
                     "loudness": result.loudness}}


# ------------------------------------------------------------- 8. verify ---
def run_verify(job: Job, store: JobStore, progress: Progress | None = None) -> dict:
    from app.render.verify import contact_sheet, verify

    paths = store.paths(job)
    meta = job.state(Stage.RENDER).meta
    expected_frames = meta.get("expected_frames")
    total = meta.get("total")

    _note(job, progress, "verifying the encoded file")
    report = verify(paths.reel_mp4, expected_frames=expected_frames,
                    expected_duration=total)
    atomic_write(paths.verify_json, json.dumps(report.as_dict(), indent=2))

    frames = [6, int((expected_frames or 1164) * 0.2), int((expected_frames or 1164) * 0.4),
              int((expected_frames or 1164) * 0.6), int((expected_frames or 1164) * 0.8),
              max(0, (expected_frames or 1164) - 14)]
    try:
        contact_sheet(paths.reel_mp4, paths.contact_png, frames)
    except Exception as exc:
        _note(job, progress, f"contact sheet could not be built: {exc}")

    if not report.ok:
        raise StageFailed(
            "the encoded file does not meet platform requirements:\n"
            + "\n".join(f"  {c.name}: expected {c.expected}, got {c.actual}"
                        for c in report.failures)
        )
    _note(job, progress, f"verified: {len(report.checks)} checks passed")
    return {"artifacts": {"verify": paths.rel(paths.verify_json),
                          "contact": paths.rel(paths.contact_png)},
            "meta": {"checks": len(report.checks), "loudness": report.loudness,
                     "ok": True}}


# ------------------------------------------------------------ 9. package ---
def run_package(job: Job, store: JobStore, progress: Progress | None = None) -> dict:
    import zipfile

    from app.render import documents

    paths = store.paths(job)
    content = ReelContent.model_validate_json(paths.content_json.read_text())
    platforms = PlatformBundle.model_validate_json(paths.platforms_json.read_text())
    facts = FactsBundle.model_validate_json(paths.facts_json.read_text())
    report = json.loads(paths.verify_json.read_text()) if paths.verify_json.exists() else {}

    streams = report.get("streams", {}) or {}
    video = streams.get("video") or {}
    spec = {
        "duration_seconds": float((streams.get("format") or {}).get("duration", 0.0)),
        "frames": job.state(Stage.RENDER).meta.get("frames"),
        "fps": 30,
        "integrated_lufs": (report.get("loudness") or {}).get("integrated_lufs"),
        "width": video.get("width"), "height": video.get("height"),
    }
    atomic_write(paths.notes_md,
                 documents.notes_md(content, platforms, spec=spec, facts=facts))

    paths.out.mkdir(parents=True, exist_ok=True)
    for source, name in ((paths.reel_mp4, f"{job.slug}-reel.mp4"),
                         (paths.cover_png, f"{job.slug}-reel.png"),
                         (paths.facts_json, "facts.json"),
                         (paths.content_json, "content.json"),
                         (paths.verify_json, "verify.json"),
                         (paths.contact_png, "contact.png")):
        if source.exists():
            shutil.copy2(source, paths.out / name)

    with zipfile.ZipFile(paths.bundle_zip, "w", zipfile.ZIP_DEFLATED) as bundle:
        for item in sorted(paths.out.rglob("*")):
            if item.is_file() and item != paths.bundle_zip:
                bundle.write(item, item.relative_to(paths.out))

    _note(job, progress, f"packaged {paths.bundle_zip.name}")
    return {"artifacts": {"notes": paths.rel(paths.notes_md),
                          "bundle": paths.rel(paths.bundle_zip),
                          "out_dir": paths.rel(paths.out)},
            "meta": {"spec": spec, "bytes": paths.bundle_zip.stat().st_size}}


RUNNERS: dict[Stage, Callable[[Job, JobStore, Progress | None], dict]] = {
    Stage.INGEST: run_ingest,
    Stage.CONTENT: run_content,
    Stage.COVER: run_cover,
    Stage.AUDIO: run_audio,
    Stage.ALIGN: run_align,
    Stage.STORYBOARD: run_storyboard,
    Stage.RENDER: run_render,
    Stage.VERIFY: run_verify,
    Stage.PACKAGE: run_package,
}


def run_stage(job: Job, stage: Stage, store: JobStore,
              progress: Progress | None = None) -> Job:
    """Run one stage, recording its outcome on the job either way."""
    blockers = job.blockers(stage)
    if blockers:
        raise StageFailed(
            f"{stage.value} cannot run yet: {', '.join(b.value for b in blockers)} "
            "must finish first."
        )
    job.mark(stage, Status.RUNNING)
    job.invalidate_from(stage)
    store.save(job)
    try:
        outcome = RUNNERS[stage](job, store, progress)
    except Exception as exc:
        job.mark(stage, Status.FAILED, error=f"{type(exc).__name__}: {exc}")
        job.note(f"{stage.value} failed: {exc}")
        store.save(job)
        raise
    status = Status.REVIEW if job.pauses_at(stage) else Status.DONE
    job.mark(stage, status, artifacts=outcome.get("artifacts"), meta=outcome.get("meta"))
    store.save(job)
    return job


# ---------------------------------------------------------------- walking ---
# `runner._run_inline` and `tasks.run_pipeline_task` were near-identical copies
# of the loop below, and they had already drifted: the Celery one could never
# publish `{"type": "pipeline", "status": "failed"}`, because `run_stage_task`
# re-raises and the FAILED check after it was unreachable. A browser watching a
# Celery run was told the stage failed and never that the pipeline had stopped.
#
# So the walk lives here, next to `run_stage`, which is already the one
# definition of what a stage is.
import threading  # noqa: E402  (deliberately local to this section)
import traceback  # noqa: E402

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def job_lock(job_id: str) -> threading.Lock:
    """One stage at a time per job -- `job.json` has a single writer."""
    with _locks_guard:
        return _locks.setdefault(job_id, threading.Lock())


def run_one(job_id: str, stage: Stage, store: JobStore | None = None) -> str:
    """Run exactly one stage. Returns "done" | "review" | "failed:<stage>"."""
    from app.progress import publish, reporter

    store = store or JobStore()
    with job_lock(job_id):
        job = store.load(job_id)
        publish(job_id, {"type": "stage", "stage": stage.value, "status": "running"})
        try:
            job = run_stage(job, stage, store, progress=reporter(job_id, stage.value))
        except Exception as exc:
            publish(job_id, {"type": "stage", "stage": stage.value, "status": "failed",
                             "error": str(exc)[:2000]})
            traceback.print_exc()
            return "failed:" + stage.value
        state = job.state(stage)
        publish(job_id, {"type": "stage", "stage": stage.value,
                         "status": state.status.value, "artifacts": state.artifacts})
        return "review" if state.status is Status.REVIEW else "done"


def walk(job_id: str, store: JobStore | None = None, *,
         until: Stage | None = None,
         should_stop: Callable[[Job], bool] | None = None) -> str:
    """Run stages until the pipeline ends, a gate stops it, or something fails.

    Returns why it stopped, which is what the queue records as the job's reason:
    "complete" | "review:<stage>" | "failed:<stage>" | "until:<stage>" |
    "cancelled" | "gone".

    `should_stop` is checked against the freshly-loaded job at the top of each
    iteration, which is free -- the job is loaded there anyway -- and is how a
    cancel takes effect at a stage boundary rather than mid-stage. Mid-stage is
    not an option: DEVELOPMENT.md gotcha 8 is that a killed render leaves a shorter,
    playable, wrong file, and a killed content stage leaves half a content.json.
    """
    from app.progress import publish, reporter

    store = store or JobStore()
    with job_lock(job_id):
        while True:
            try:
                job = store.load(job_id)
            except FileNotFoundError:
                return "gone"

            if should_stop and should_stop(job):
                publish(job_id, {"type": "pipeline", "status": "cancelled"})
                return "cancelled"

            stage = job.next_stage()
            if stage is None:
                publish(job_id, {"type": "pipeline", "status": "complete"})
                return "complete"
            if until and STAGE_ORDER.index(stage) > STAGE_ORDER.index(until):
                return "until:" + until.value

            publish(job_id, {"type": "stage", "stage": stage.value, "status": "running"})
            try:
                job = run_stage(job, stage, store, progress=reporter(job_id, stage.value))
            except Exception as exc:
                publish(job_id, {"type": "stage", "stage": stage.value,
                                 "status": "failed", "error": str(exc)[:2000]})
                publish(job_id, {"type": "pipeline", "status": "failed",
                                 "stage": stage.value})
                traceback.print_exc()
                return "failed:" + stage.value

            state = job.state(stage)
            publish(job_id, {"type": "stage", "stage": stage.value,
                             "status": state.status.value,
                             "artifacts": state.artifacts})
            if state.status is Status.REVIEW:
                publish(job_id, {"type": "pipeline", "status": "awaiting_review",
                                 "stage": stage.value})
                return "review:" + stage.value
            if state.status is Status.FAILED:
                # reachable here, unlike in the Celery copy this replaced
                publish(job_id, {"type": "pipeline", "status": "failed",
                                 "stage": stage.value})
                return "failed:" + stage.value
