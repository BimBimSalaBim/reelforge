"""Command line access to the same pipeline the UI drives.

    python -m app.cli new https://github.com/owner/repo --template research
    python -m app.cli run <job-id> --stage content
    python -m app.cli list
    python -m app.cli show <job-id>
    python -m app.cli providers
    python -m app.cli doctor

Useful headlessly, in CI, and inside the container when something needs poking
at without a browser.
"""
from __future__ import annotations

import argparse
import json
import sys

from app.config import get_config
from app.models.job import STAGE_ORDER, JobSource, ProviderChoice, Stage, Status
from app.store import JobStore


def _print(payload) -> None:
    print(json.dumps(payload, indent=2, default=str))


def cmd_new(args) -> int:
    from app.ingest import IngestError, detect

    try:
        kind = detect(args.url)
    except IngestError as exc:
        print(exc, file=sys.stderr)
        return 2
    store = JobStore()
    job = store.create(
        args.slug or args.url.rstrip("/").split("/")[-1],
        JobSource(kind=kind, url=args.url),
        template=args.template,
        providers=ProviderChoice(llm_provider=args.llm, tts_provider=args.tts),
        manual_stages=[] if args.no_gates else None,
    )
    print(job.id)
    if args.run:
        return cmd_run(argparse.Namespace(job=job.id, stage=None, until=None))
    return 0


def cmd_run(args) -> int:
    from app.stages.pipeline import run_stage

    store = JobStore()
    job = store.load(args.job)
    stages = [Stage(args.stage)] if args.stage else list(STAGE_ORDER)
    stop_at = Stage(args.until) if getattr(args, "until", None) else None

    for stage in stages:
        if job.is_done(stage):
            continue
        if stop_at and STAGE_ORDER.index(stage) > STAGE_ORDER.index(stop_at):
            break
        print(f"==> {stage.value}", flush=True)
        try:
            job = run_stage(job, stage, store,
                            progress=lambda m: print(f"    {m}", flush=True))
        except Exception as exc:
            print(f"    FAILED: {exc}", file=sys.stderr)
            return 1
        if job.state(stage).status is Status.REVIEW and not args.stage:
            print(f"    awaiting review; approve with: "
                  f"python -m app.cli approve {job.id} {stage.value}")
            break
    return 0


def cmd_approve(args) -> int:
    store = JobStore()
    job = store.load(args.job)
    job.mark(Stage(args.stage), Status.DONE)
    store.save(job)
    print(f"{args.stage} approved")
    return 0


def cmd_list(args) -> int:
    for job in JobStore().iter_jobs(limit=args.limit):
        marker = ("failed at " + job.failed_stage.value) if job.failed_stage else (
            job.next_stage().value if job.next_stage() else "complete")
        print(f"{job.id}  {job.slug:<22} {job.progress * 100:3.0f}%  {marker}")
    return 0


def cmd_show(args) -> int:
    job = JobStore().load(args.job)
    _print(json.loads(job.model_dump_json()))
    return 0


def cmd_providers(args) -> int:
    from app.api.routes_system import providers

    _print(providers())
    return 0


def cmd_doctor(args) -> int:
    """Check that everything the pipeline depends on is actually present."""
    import shutil

    from app.render.fonts import available as fonts_available
    from app.render.workspace import ffmpeg_bin, vendored_ffmpeg_usable
    from app.runner import mode

    cfg = get_config()
    checks: list[tuple[str, bool, str]] = []

    # What matters is that *an* ffmpeg runs here, not which one. The vendored
    # video/bin builds are macOS x86_64 and are used when they work; otherwise
    # align.py's own tool() falls back to PATH, which is the container's case.
    on_path = shutil.which("ffmpeg")
    vendored = vendored_ffmpeg_usable(str(cfg.paths.video))
    try:
        resolved = ffmpeg_bin()
    except Exception:
        resolved = ""
    checks.append(("ffmpeg available", bool(resolved),
                   resolved or "neither video/bin nor PATH has a runnable ffmpeg"))
    checks.append(("  from", True,
                   "vendored video/bin" if vendored else
                   ("PATH" if on_path else "nowhere")))
    checks.append(("video pipeline present", (cfg.paths.video / "kit.py").exists(),
                   str(cfg.paths.video)))
    checks.append(("bundled fonts", fonts_available(),
                   str(cfg.fonts.dir_path())))
    checks.append(("job directory writable", cfg.paths.jobs.exists(),
                   str(cfg.paths.jobs)))
    checks.append((f"executor ({mode()})", True, "celery if redis is reachable"))

    ok = True
    for name, passed, detail in checks:
        ok = ok and passed
        print(f"  {'ok  ' if passed else 'FAIL'}  {name:34} {detail}")

    if fonts_available():
        try:
            sys.path.insert(0, str(cfg.paths.video))
            import kit

            from app.render.fonts import check_symbols, patch_kit

            patch_kit(kit)
            check_symbols(kit)
            print(f"  ok    {'mono face has every symbol':34} {kit.MN.split('/')[-1]}")
        except Exception as exc:
            ok = False
            print(f"  FAIL  {'mono face symbols':34} {exc}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reelforge", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("new", help="create a job")
    p.add_argument("url")
    p.add_argument("--slug")
    p.add_argument("--template", default="cool-indigo")
    p.add_argument("--llm")
    p.add_argument("--tts")
    p.add_argument("--no-gates", action="store_true",
                   help="run straight through without pausing for review")
    p.add_argument("--run", action="store_true")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("run", help="run a job, or one stage of it")
    p.add_argument("job")
    p.add_argument("--stage", choices=[s.value for s in STAGE_ORDER])
    p.add_argument("--until", choices=[s.value for s in STAGE_ORDER])
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("approve", help="accept a stage awaiting review")
    p.add_argument("job")
    p.add_argument("stage", choices=[s.value for s in STAGE_ORDER])
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser("list", help="list jobs")
    p.add_argument("--limit", type=int, default=40)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="print a job's full state")
    p.add_argument("job")
    p.set_defaults(func=cmd_show)

    sub.add_parser("providers", help="what is reachable right now").set_defaults(
        func=cmd_providers)
    sub.add_parser("doctor", help="check the environment").set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
