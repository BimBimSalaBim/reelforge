"""Render a storyboard to a finished mp4.

The renderer is single-threaded PIL and numpy at roughly 3-9 fps, so a 40 s reel
costs 7-9 minutes in one process. `video/render.py` already accepts
`--only T0 T1`, which is the seam: split the timeline on GOP boundaries, render
the chunks concurrently, encode each with identical settings, join them without
re-encoding, then mux the audio once.

Correctness guards, in order of how much time they have cost historically:

* Every chunk boundary is a whole number of 2 s closed GOPs, so `-c copy`
  concatenation cuts on an IDR frame.
* The joined video's frame count is asserted against `round(TOTAL * fps)` before
  audio is attached. A broken pipe leaves a shorter, playable, *wrong* file and
  raises nothing (DEVELOPMENT.md gotcha 8).
* The output is written to a temp name and moved into place, so an interrupted
  rebuild never overwrites a good file with a truncated one.
* `safe_encode` runs the byte-for-byte `make.sh` command in one process instead,
  as the reference to check a chunked result against.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.config import get_config
from app.render import encode
from app.render.workspace import ffmpeg_bin, ffprobe_bin

ProgressFn = Callable[[str, float, str], None]
PROGRESS_RE = re.compile(r"^\s*(\d+)/(\d+)\s")


class RenderError(RuntimeError):
    pass


@dataclass
class RenderResult:
    output: Path
    frames: int
    expected_frames: int
    chunks: int
    seconds: float
    mode: str
    chunk_logs: dict[str, str] = field(default_factory=dict)
    #: what the loudness correction measured and how many passes it took, so a
    #: file that only just cleared the window is visible before a platform
    #: turns it down rather than after
    loudness: dict = field(default_factory=dict)


def _python() -> str:
    return os.environ.get("PYTHON", sys.executable or "python3")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    root = str(_repo_root())
    env["PYTHONPATH"] = root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def probe_frames(path: Path) -> int:
    """Count frames by decoding. `nb_frames` is absent or wrong on some muxes,
    and this check is the whole point -- it has to be the reliable one."""
    proc = subprocess.run(
        [ffprobe_bin(), "-v", "error", "-count_frames",
         "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames",
         "-of", "default=nokey=1:noprint_wrappers=1", str(path)],
        capture_output=True, text=True, check=False,
    )
    try:
        return int(proc.stdout.strip())
    except ValueError:
        raise RenderError(f"could not count frames in {path}: {proc.stderr.strip()}") from None


def run_sfx(workspace: Path, slug: str, *, allow_system_fonts: bool = False) -> Path:
    """Build `build/<slug>.mix.wav` from the narration plus the storyboard's SFX."""
    cmd = [_python(), "-m", "app.render.shim_sfx",
           "--workspace", str(workspace), "--storyboard", slug]
    if allow_system_fonts:
        cmd.append("--allow-system-fonts")
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=_repo_root(),
                          env=_child_env(), check=False)
    mix = workspace / "build" / f"{slug}.mix.wav"
    if proc.returncode != 0 or not mix.exists():
        raise RenderError(f"audio mix failed:\n{proc.stderr.strip() or proc.stdout.strip()}")
    return mix


def _render_one_chunk(
    workspace: Path, slug: str, index: int, t0: float, t1: float,
    out: Path, fps: int, width: int, height: int,
    allow_system_fonts: bool, progress: ProgressFn | None, lock: threading.Lock,
) -> tuple[int, str]:
    """One chunk: shim_render's raw RGBA piped straight into its own encoder."""
    render_cmd = [_python(), "-m", "app.render.shim_render",
                  "--workspace", str(workspace), "--storyboard", slug,
                  "--fps", str(fps), "--only", str(t0), str(t1)]
    if allow_system_fonts:
        render_cmd.append("--allow-system-fonts")

    ff = subprocess.Popen(
        encode.chunk_cmd(ffmpeg_bin(), out, width, height, fps),
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    rd = subprocess.Popen(
        render_cmd, stdout=ff.stdin, stderr=subprocess.PIPE, text=False,
        cwd=_repo_root(), env=_child_env(),
    )
    # the encoder owns the pipe now; this process must let go or it never sees EOF
    ff.stdin.close()

    tail: list[str] = []
    total_frames = int(round((t1 - t0) * fps))
    for raw in rd.stderr:
        line = raw.decode("utf-8", "replace").rstrip()
        tail.append(line)
        del tail[:-40]
        match = PROGRESS_RE.match(line)
        if match and progress:
            done = int(match.group(1))
            with lock:
                progress(f"chunk{index:03d}", done / max(total_frames, 1), line.strip())
    rd.stderr.close()
    render_rc = rd.wait()
    ff_err = ff.stderr.read().decode("utf-8", "replace")
    ff.stderr.close()
    ff_rc = ff.wait()

    log = "\n".join(tail)
    if render_rc != 0:
        raise RenderError(f"chunk {index} render failed (rc={render_rc}):\n{log}")
    if ff_rc != 0 or not out.exists():
        raise RenderError(f"chunk {index} encode failed (rc={ff_rc}):\n{ff_err.strip()}")
    return index, log


def render(
    workspace: Path,
    slug: str,
    total: float,
    out: Path,
    *,
    progress: ProgressFn | None = None,
    allow_system_fonts: bool = False,
) -> RenderResult:
    """Render `slug` in `workspace` to `out`. Chunked unless config says otherwise."""
    import time

    cfg = get_config()
    fps, width, height = cfg.render.fps, cfg.render.width, cfg.render.height
    started = time.time()

    mix = run_sfx(workspace, slug, allow_system_fonts=allow_system_fonts)
    if progress:
        progress("mix", 1.0, f"narration + SFX mixed ({mix.stat().st_size // 1024} KiB)")

    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f"render-{slug}-", dir=str(out.parent)))
    try:
        if cfg.render.safe_encode:
            result = _render_single(workspace, slug, total, mix, staging, fps, width,
                                    height, allow_system_fonts, progress)
        else:
            result = _render_chunked(workspace, slug, total, mix, staging, fps, width,
                                     height, allow_system_fonts, progress)

        expected = encode.expected_frames(total, fps)
        frames = probe_frames(result["video"])
        if frames != expected:
            raise RenderError(
                f"frame count mismatch: {frames} rendered, {expected} expected "
                f"({total}s x {fps}fps). The render pipe broke and the tail of the "
                "video is missing."
            )
        # temp name then move: an interrupted rebuild must never overwrite a good file
        shutil.move(str(result["video"]), str(out))
        return RenderResult(
            output=out, frames=frames, expected_frames=expected,
            chunks=result["chunks"], seconds=round(time.time() - started, 1),
            mode=result["mode"], chunk_logs=result.get("logs", {}),
            loudness=result.get("loudness", {}),
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _render_single(workspace, slug, total, mix, staging, fps, width, height,
                   allow_system_fonts, progress) -> dict:
    """The reference path: exactly `make.sh`, one process, frames on a pipe."""
    out = staging / "single.mp4"
    render_cmd = [_python(), "-m", "app.render.shim_render",
                  "--workspace", str(workspace), "--storyboard", slug, "--fps", str(fps)]
    if allow_system_fonts:
        render_cmd.append("--allow-system-fonts")

    ff = subprocess.Popen(
        encode.single_pass_cmd(ffmpeg_bin(), mix, out, width, height, fps),
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    rd = subprocess.Popen(render_cmd, stdout=ff.stdin, stderr=subprocess.PIPE,
                          cwd=_repo_root(), env=_child_env())
    ff.stdin.close()
    expected = encode.expected_frames(total, fps)
    tail: list[str] = []
    for raw in rd.stderr:
        line = raw.decode("utf-8", "replace").rstrip()
        tail.append(line); del tail[:-40]
        match = PROGRESS_RE.match(line)
        if match and progress:
            progress("render", int(match.group(1)) / max(expected, 1), line.strip())
    rd.stderr.close()
    if rd.wait() != 0:
        raise RenderError("render failed:\n" + "\n".join(tail))
    err = ff.stderr.read().decode("utf-8", "replace"); ff.stderr.close()
    if ff.wait() != 0:
        raise RenderError(f"encode failed:\n{err.strip()}")
    return {"video": out, "chunks": 1, "mode": "single", "logs": {"render": "\n".join(tail)}}


def _render_chunked(workspace, slug, total, mix, staging, fps, width, height,
                    allow_system_fonts, progress) -> dict:
    cfg = get_config()
    bounds = encode.plan_chunks(total, cfg.render.chunk_seconds, fps)
    parts_dir = staging / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    done = 0
    logs: dict[str, str] = {}

    def report(tag: str, fraction: float, message: str) -> None:
        if progress:
            progress(tag, (done + fraction) / len(bounds), message)

    workers = max(1, min(cfg.render.resolved_workers(), len(bounds)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _render_one_chunk, workspace, slug, i, t0, t1,
                parts_dir / f"part{i:03d}.mp4", fps, width, height,
                allow_system_fonts, report, lock,
            ): i
            for i, (t0, t1) in enumerate(bounds)
        }
        for future in as_completed(futures):
            index, log = future.result()  # re-raises RenderError with its chunk log
            logs[f"chunk{index:03d}"] = log
            with lock:
                done += 1
            if progress:
                progress("chunk", done / len(bounds), f"chunk {index} of {len(bounds)} done")

    # The concat demuxer resolves each entry relative to the list file, so the
    # paths must be absolute or they get joined onto the list file's directory.
    list_file = staging / "parts.txt"
    list_file.write_text(
        "".join(
            f"file '{(parts_dir / f'part{i:03d}.mp4').resolve()}'\n"
            for i in range(len(bounds))
        )
    )
    joined = staging / "joined.mp4"
    proc = subprocess.run(encode.concat_cmd(ffmpeg_bin(), list_file, joined),
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not joined.exists():
        raise RenderError(f"concat failed:\n{proc.stderr.strip()}")

    final = staging / "final.mp4"
    loudness = encode.mux_normalised(
        ffmpeg_bin(), joined, mix, final,
        run=lambda cmd: subprocess.run(cmd, capture_output=True, text=True,
                                       check=False),
    )
    if progress and len(loudness["passes"]) > 1:
        progress(f"loudness corrected over {len(loudness['passes'])} passes "
                 f"to {loudness['loudness']:.1f} LUFS / "
                 f"{loudness['true_peak']:.1f} dBTP")

    return {"video": final, "chunks": len(bounds), "mode": "chunked",
            "logs": logs, "loudness": loudness}
