"""Stage 6: write the storyboard module, then prove it renders.

The generation itself is one LLM call. Everything else here is the ladder that
decides whether what came back is worth spending eight minutes of rendering on,
and -- when it is not -- turns the failure into a specific instruction.

Rungs, cheapest first:

  1-4  static, on the AST alone: syntax, imports, the module contract, and every
       cue word checked against the words actually spoken
  5-7  in a limited subprocess: scene table, sample frames, safe-area legibility
  8    optional, a multimodal model looking at the frames

Anything that fails becomes the repair prompt. If the budget runs out, the
fallback storyboard renders the same content from data, so a job always produces
a video.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.config import get_config
from app.models.content import ReelContent
from app.prompts.storyboard import build_storyboard_prompt, build_vision_prompt, VISION_SYSTEM
from app.providers.llm import LLMProvider
from app.stages.base import StageError
from app.validate.storyboard import autofix, check_source

FENCE_RE = re.compile(r"```(?:python|py)?\s*(.*?)```", re.S)


@dataclass
class StoryboardResult:
    source: str
    path: Path
    attempts: list[dict] = field(default_factory=list)
    smoke: dict = field(default_factory=dict)
    used_fallback: bool = False

    @property
    def repairs(self) -> int:
        return max(0, len(self.attempts) - 1)

    def as_dict(self) -> dict:
        return {"path": str(self.path), "attempts": self.attempts,
                "repairs": self.repairs, "used_fallback": self.used_fallback,
                "smoke_ok": self.smoke.get("ok"),
                "frames": [f["path"] for f in self.smoke.get("frames", [])]}


def strip_fence(text: str) -> str:
    """Models fence code even when told not to. Take the block if there is one."""
    text = (text or "").strip()
    blocks = FENCE_RE.findall(text)
    if blocks:
        return max(blocks, key=len).strip() + "\n"
    return text + "\n"


def run_smoke(
    workspace: Path, slug: str, out_dir: Path, *,
    expected_duration: float | None = None,
) -> dict:
    """Import and render sample frames in a limited subprocess."""
    cfg = get_config()
    repo_root = Path(__file__).resolve().parent.parent.parent
    cmd = [
        sys.executable or "python3", "-m", "app.validate.smoke",
        "--workspace", str(workspace), "--storyboard", slug,
        "--out", str(out_dir),
        "--frames", str(cfg.storyboard.smoke_frames),
        "--memory-mb", str(cfg.storyboard.memory_limit_mb),
        "--cpu-seconds", str(cfg.storyboard.smoke_timeout_seconds),
    ]
    if expected_duration:
        cmd += ["--expected-duration", str(expected_duration)]

    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, cwd=repo_root, env=env,
            timeout=cfg.storyboard.smoke_timeout_seconds + 60,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "problems": [{
            "rung": "timeout",
            "message": (
                f"rendering sample frames did not finish within "
                f"{cfg.storyboard.smoke_timeout_seconds}s. frame(t) must return in well "
                "under a second; check for an unbounded loop or a per-frame allocation "
                "that should be done once at import."
            )}], "frames": []}

    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        detail = (proc.stderr or proc.stdout or "")[-1200:]
        return {"ok": False, "problems": [{
            "rung": "crash",
            "message": "the storyboard could not be loaded or rendered:\n" + detail,
        }], "frames": []}


def vision_review(llm: LLMProvider, frames: list[dict], limit: int = 6) -> list[str]:
    """Ask a multimodal model to look at the frames. Advisory only."""
    chosen = frames[:: max(1, len(frames) // limit)][:limit]
    images = []
    for entry in chosen:
        path = Path(entry["path"])
        if path.exists():
            images.append(path.read_bytes())
    if not images:
        return []
    result = llm.complete(
        system=VISION_SYSTEM,
        user=build_vision_prompt([f["t"] for f in chosen]),
        images=images, max_tokens=900, temperature=0.2,
    )
    text = result.text.strip()
    if not text or "NO DEFECTS" in text.upper():
        return []
    return [f"A reviewer looking at the rendered frames reported:\n{text}"]


def generate_storyboard(
    content: ReelContent,
    workspace: Path,
    timing_json: Path,
    *,
    llm: LLMProvider,
    total: float,
    audio_rel: str,
    phrases_rel: str,
    smoke_dir: Path,
    template_example: str = "",
    vision_llm: LLMProvider | None = None,
    captions: bool = True,
    images: list[dict] | None = None,
    progress: Callable[[str], None] | None = None,
) -> StoryboardResult:
    cfg = get_config()
    target = workspace / "storyboards" / f"{content.slug}.py"
    target.parent.mkdir(parents=True, exist_ok=True)

    attempts: list[dict] = []
    notes = ""

    for index in range(1, cfg.storyboard.max_repair_attempts + 1):
        if progress:
            progress(f"writing storyboard, attempt {index}"
                     + (" (repair)" if notes else ""))
        # A small-context model cannot hold a 276-line example and still have
        # room to write 250 lines of its own.
        window = getattr(llm, "context_window", lambda: None)() or 128_000
        example_lines = 300 if window >= 32_000 else (140 if window >= 16_000 else 80)
        system, user = build_storyboard_prompt(
            content, timing_json, total=total, audio_rel=audio_rel,
            phrases_rel=phrases_rel, template_example=template_example,
            repair_notes=notes, max_example_lines=example_lines,
            captions=captions,
        )
        try:
            result = llm.complete(system=system, user=user, max_tokens=12000,
                                  temperature=0.4)
        except Exception as exc:
            # An unreachable endpoint, an auth failure, a model that will not
            # produce text -- none of these say anything about this job, and a
            # deterministic renderer is sitting right there. Record it as a
            # failed attempt so the loop exhausts into the fallback rather than
            # taking the whole stage down with the provider.
            reason = f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"
            attempts.append({"attempt": index, "ok": False, "stage": "provider",
                             "problems": [reason]})
            if progress:
                progress(f"attempt {index}: the model could not be reached ({reason})")
            notes = ""
            continue
        source = strip_fence(result.text)

        # Repair what needs no judgment before judging it: a forgotten `SFX`
        # constant and a cue word one letter off are not worth a generation.
        source, repairs = autofix(source, timing_json)
        if repairs and progress:
            progress("auto-repaired: " + "; ".join(repairs))

        # --- rungs 1-4: static, no execution -----------------------------
        static = check_source(source, timing_json)
        if not static.ok:
            attempts.append({"attempt": index, "ok": False, "stage": "static",
                             "problems": static.messages(),
                             "tokens_out": result.output_tokens})
            notes = "\n".join(static.messages())
            if progress:
                progress(f"attempt {index} rejected by static checks "
                         f"({len(static.problems)} problem(s))")
            continue

        # --- rungs 5-7: render sample frames ------------------------------
        target.write_text(source)
        if progress:
            progress(f"attempt {index} passed static checks, rendering sample frames")
        smoke = run_smoke(workspace, content.slug, smoke_dir, expected_duration=total)
        problems = [p["message"] for p in smoke.get("problems", [])]

        # --- rung 8: a look at the frames ---------------------------------
        if not problems and vision_llm is not None and cfg.storyboard.vision_review:
            if progress:
                progress("reviewing rendered frames")
            try:
                problems += vision_review(vision_llm, smoke.get("frames", []))
            except Exception as exc:  # advisory only, never fatal
                if progress:
                    progress(f"vision review skipped: {exc}")

        attempts.append({"attempt": index, "ok": not problems, "stage": "smoke",
                         "problems": problems, "tokens_out": result.output_tokens,
                         "cue_words": static.cue_words})
        if not problems:
            if progress:
                progress(f"storyboard accepted after {index} attempt(s)")
            return StoryboardResult(source=source, path=target,
                                    attempts=attempts, smoke=smoke)
        notes = "\n".join(problems)
        if progress:
            progress(f"attempt {index} rejected: {len(problems)} problem(s)")

    if not cfg.storyboard.fallback_to_template:
        raise StageError(
            f"storyboard generation failed after {cfg.storyboard.max_repair_attempts} "
            "attempts and fallback is disabled. Last problems:\n"
            + "\n".join(f"  - {p}" for p in attempts[-1]["problems"])
        )

    if progress:
        progress("generation exhausted its attempts; using the data-driven fallback")
    source = write_fallback(content, workspace, total, audio_rel, phrases_rel,
                            captions=captions, timing_json=timing_json,
                            images=images)
    smoke = run_smoke(workspace, content.slug, smoke_dir, expected_duration=total)
    if not smoke.get("ok"):
        raise StageError(
            "the fallback storyboard failed to render, which should not happen:\n"
            + "\n".join(p["message"] for p in smoke.get("problems", []))
        )
    attempts.append({"attempt": len(attempts) + 1, "ok": True, "stage": "fallback",
                     "problems": []})
    return StoryboardResult(source=source, path=workspace / "storyboards" / f"{content.slug}.py",
                            attempts=attempts, smoke=smoke, used_fallback=True)


def capture_repo_scroll(repo_url: str, workspace: Path) -> dict | None:
    """Screenshot the repo page for use as scrolling B-roll, or return None.

    Best-effort by design: no browser, a page that will not load, or a page too
    short to be worth scrolling all return None, and the reel is simply built
    without that screen. A missing B-roll costs nothing; a broken one is on
    screen for eight seconds.
    """
    if not repo_url:
        return None
    from app.render.reposhot import capture

    target = workspace / "images" / "repo-scroll.png"
    if target.exists():                       # a re-run reuses the capture
        from PIL import Image
        with Image.open(target) as img:
            if img.height >= 2600:
                return {"file": target.name,
                        "label": _repo_label(repo_url), "height": img.height}
    shot = capture(repo_url, target)
    if not shot:
        return None
    return {"file": target.name, "label": _repo_label(repo_url),
            "height": shot.height}


def _repo_label(repo_url: str) -> str:
    parts = repo_url.rstrip("/").split("/")
    return "/".join(parts[-2:]) if len(parts) >= 2 else repo_url


def write_fallback(
    content: ReelContent, workspace: Path, total: float,
    audio_rel: str, phrases_rel: str, captions: bool = True,
    timing_json: Path | None = None, images: list[dict] | None = None,
    family: str = "bloom", repo_url: str | None = None,
) -> str:
    """Render the same content from data, with no generated code involved.

    Guarantees a job always produces a video, and doubles as the 'safe' template
    a user can pick deliberately.
    """
    from app.render.fallback_storyboard import build_source

    segments = None
    if timing_json and timing_json.exists():
        segments = [tuple(seg) for seg in json.loads(timing_json.read_text())["segments"]]

    scroll = capture_repo_scroll(repo_url or content.repo_url, workspace)
    source = build_source(content, total=total, audio_rel=audio_rel,
                          phrases_rel=phrases_rel, captions=captions,
                          segments=segments, images=images, family=family,
                          scroll=scroll)
    target = workspace / "storyboards" / f"{content.slug}.py"
    target.write_text(source)
    return source
