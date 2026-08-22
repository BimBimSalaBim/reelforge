"""Render driver: runs `video/render.py` with bundled fonts patched in.

Delegates the frame loop to the real `render.py` via `runpy` rather than
reimplementing it, so there is one source of truth for how frames are produced
and progress is reported.

Order matters. `kit.f` and `kit.m` must be replaced *before* `sbkit` or the
storyboard are imported, because both do `from kit import f, m` at import time
and would otherwise bind the macOS loaders. `runpy` runs after the patch, and
`render.py` is what triggers those imports.

One storyboard per process, always: `kit.set_palette` mutates module globals, so
a second storyboard imported into the same interpreter would inherit the first
one's palette (DEVELOPMENT.md gotcha 5). Every invocation of this shim renders
exactly one storyboard, and chunked rendering runs one process per chunk.

    python3 -m app.render.shim_render --workspace WS --storyboard slug \
        --only 0 6.0 > frames.rgba
"""
from __future__ import annotations

import argparse
import runpy
import sys
from pathlib import Path


def prepare(workspace: Path, *, strict_fonts: bool = True):
    """Put the workspace on the path and patch fonts. Returns the kit module."""
    workspace = workspace.resolve()
    for entry in (str(workspace / "storyboards"), str(workspace)):
        if entry in sys.path:
            sys.path.remove(entry)
        sys.path.insert(0, entry)

    import kit  # resolved from the workspace farm

    from app.render.fonts import check_symbols, patch_kit

    if patch_kit(kit, strict=strict_fonts):
        check_symbols(kit)
    return kit


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", required=True, type=Path)
    ap.add_argument("--storyboard", required=True)
    ap.add_argument("--only", nargs=2, type=float, metavar=("T0", "T1"))
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument(
        "--allow-system-fonts",
        action="store_true",
        help="fall back to the host's macOS faces when the bundled ones are absent",
    )
    args = ap.parse_args()

    workspace = args.workspace.resolve()
    prepare(workspace, strict_fonts=not args.allow_system_fonts)

    argv = ["render.py", args.storyboard, "--fps", str(args.fps)]
    if args.only:
        argv += ["--only", str(args.only[0]), str(args.only[1])]
    sys.argv = argv

    # render.py has no __main__ guard; run_path executes it top to bottom either
    # way, and run_name keeps its behaviour identical to the CLI.
    runpy.run_path(str(workspace / "render.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
