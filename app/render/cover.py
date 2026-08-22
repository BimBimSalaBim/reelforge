"""Render the cover image.

`video/covers.py` is already declarative -- a dict per repo -- so this needs no
code generation at all. The generated spec is injected into that module's SPECS
table and its own `render()` does the drawing, which keeps one implementation of
the cover layout rather than a second that drifts.

Instagram shows a centre-square crop of the cover in the grid, so the wordmark
and hook have to survive it. That is checked here rather than assumed.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.models.content import ReelContent

#: The centre square Instagram crops to, in a 1080x1920 cover.
CROP_TOP, CROP_BOTTOM = 420, 1500


class CoverError(RuntimeError):
    pass


def render_cover(
    content: ReelContent, workspace: Path, out_png: Path
) -> tuple[Path, list[dict]]:
    """Render via a subprocess: covers.py calls kit.set_palette, which mutates
    module globals, and the worker must not inherit that."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    spec_json = out_png.parent / f".{content.slug}.cover.json"
    spec_json.parent.mkdir(parents=True, exist_ok=True)
    spec_json.write_text(
        __import__("json").dumps(content.cover.to_covers_dict(out_png.name))
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    proc = subprocess.run(
        [sys.executable or "python3", "-m", "app.render.shim_cover",
         "--workspace", str(workspace), "--spec", str(spec_json),
         "--key", content.slug, "--out", str(out_png)],
        capture_output=True, text=True, cwd=repo_root, env=env, check=False,
    )
    spec_json.unlink(missing_ok=True)
    if proc.returncode != 0 or not out_png.exists():
        raise CoverError(
            "cover render failed:\n" + (proc.stderr.strip() or proc.stdout.strip())
        )
    try:
        result = __import__("json").loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        result = {}
    return out_png, result.get("fit_problems", [])


def crop_preview(cover_png: Path, out_png: Path) -> Path:
    """What Instagram's grid actually shows."""
    from PIL import Image

    image = Image.open(cover_png)
    image.crop((0, CROP_TOP, image.width, CROP_BOTTOM)).save(out_png)
    return out_png
