"""Per-job symlink farm over `video/`.

`align.py` and `timing.py` both resolve their working directory from
`os.path.dirname(os.path.abspath(__file__))`, not from the cwd, and `align.py`
decodes into one fixed scratch file (`build/_align16k.wav`). Two jobs running at
once in the real `video/` would race each other and share a `build/` directory.

`os.path.abspath` normalises but does *not* resolve symlinks, so a directory of
symlinks to the real modules makes `HERE` land in the job directory instead.
Each job then gets its own `build/`, `storyboards/` and `phrases/`, and
`video/` itself is never written to.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from app.config import get_config

#: The modules a job needs on its path. `render.py` and `covers.py` are invoked
#: through shims but must still live beside the rest so their own `HERE` is right.
MODULES = (
    "kit.py",
    "sbkit.py",
    "ledger.py",
    "slab.py",
    "align.py",
    "timing.py",
    "sfx.py",
    "render.py",
    "covers.py",
    "safecheck.py",
)
WORK_DIRS = ("build", "storyboards", "phrases")


class WorkspaceError(RuntimeError):
    pass


@lru_cache(maxsize=4)
def vendored_ffmpeg_usable(video_dir: str) -> bool:
    """The checked-in `video/bin/` builds are macOS x86_64 and will not run in a
    Linux container. Probe once rather than assuming either way -- `align.py`'s
    own `tool()` prefers `bin/` over PATH, so linking a broken binary is worse
    than not linking it at all."""
    binary = Path(video_dir) / "bin" / "ffmpeg"
    if not binary.exists() or not os.access(binary, os.X_OK):
        return False
    try:
        proc = subprocess.run(
            [str(binary), "-version"], capture_output=True, timeout=20, check=False
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def system_ffmpeg() -> str:
    for name in ("ffmpeg",):
        found = shutil.which(name)
        if found:
            return found
    raise WorkspaceError(
        "ffmpeg not found on PATH and the vendored video/bin/ffmpeg is not runnable "
        "on this platform. Install ffmpeg (the container image does this for you)."
    )


#: The encode settings (see app/render/encode.py) name colour properties the
#: way ffmpeg has accepted them since 4.0. Older builds fail the chunk encoder.
MIN_FFMPEG = (4, 0)


def ffmpeg_version(binary: str) -> tuple[int, int] | None:
    """(major, minor) from `ffmpeg -version`, or None when it cannot be read.

    Git builds report `N-55702-g920046a` rather than a number; those carry a
    `libavcodec` line whose major version dates them, and anything below
    libavcodec 58 (ffmpeg 4.0) is too old.
    """
    import re

    try:
        proc = subprocess.run([binary, "-version"], capture_output=True, text=True,
                              timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    head = proc.stdout.splitlines()[0] if proc.stdout else ""
    match = re.search(r"ffmpeg version n?(\d+)\.(\d+)", head)
    if match:
        return int(match.group(1)), int(match.group(2))
    lav = re.search(r"libavcodec\s+(\d+)\.", proc.stdout)
    if lav:
        major = int(lav.group(1))
        # libavcodec 58 shipped with ffmpeg 4.0; earlier majors map below it
        return (4, 0) if major >= 58 else (major - 54, 0)
    return None


def ffmpeg_bin(video_dir: Path | None = None) -> str:
    video_dir = video_dir or get_config().paths.video
    if vendored_ffmpeg_usable(str(video_dir)):
        return str(video_dir / "bin" / "ffmpeg")
    return system_ffmpeg()


def ffprobe_bin(video_dir: Path | None = None) -> str:
    video_dir = video_dir or get_config().paths.video
    if vendored_ffmpeg_usable(str(video_dir)):
        candidate = video_dir / "bin" / "ffprobe"
        if candidate.exists():
            return str(candidate)
    found = shutil.which("ffprobe")
    if not found:
        raise WorkspaceError("ffprobe not found on PATH")
    return found


def build_workspace(workspace: Path, video_dir: Path | None = None) -> Path:
    """Create (or repair) the farm at `workspace`. Idempotent."""
    video_dir = (video_dir or get_config().paths.video).resolve()
    if not (video_dir / "kit.py").exists():
        raise WorkspaceError(f"{video_dir} does not look like the video pipeline directory")

    workspace.mkdir(parents=True, exist_ok=True)
    for module in MODULES:
        source = video_dir / module
        if not source.exists():
            raise WorkspaceError(f"missing pipeline module: {source}")
        link = workspace / module
        if link.is_symlink() or link.exists():
            if link.is_symlink() and Path(os.readlink(link)) == source:
                continue
            link.unlink()
        link.symlink_to(source)

    # Only expose the vendored binaries when they actually run here.
    bin_link = workspace / "bin"
    if vendored_ffmpeg_usable(str(video_dir)):
        if not bin_link.is_symlink():
            if bin_link.exists():
                shutil.rmtree(bin_link)
            bin_link.symlink_to(video_dir / "bin", target_is_directory=True)
    elif bin_link.is_symlink():
        bin_link.unlink()

    for name in WORK_DIRS:
        (workspace / name).mkdir(parents=True, exist_ok=True)
    return workspace


def verify_workspace(workspace: Path) -> dict[str, str]:
    """Prove `HERE` resolves inside the farm before anything depends on it."""
    probe = (
        "import os,sys;"
        "sys.path.insert(0, os.getcwd());"
        "import timing;"
        "print(os.path.dirname(os.path.abspath(timing.__file__)))"
    )
    proc = subprocess.run(
        [os.environ.get("PYTHON", "python3"), "-c", probe],
        cwd=workspace, capture_output=True, text=True, timeout=60, check=False,
    )
    if proc.returncode != 0:
        raise WorkspaceError(f"workspace probe failed: {proc.stderr.strip()}")
    resolved = proc.stdout.strip()
    if Path(resolved).resolve() != workspace.resolve():
        raise WorkspaceError(
            f"workspace isolation broken: timing.py resolved HERE to {resolved}, "
            f"expected {workspace}. Falling back to copying modules is required."
        )
    return {"here": resolved, "ffmpeg": ffmpeg_bin()}
