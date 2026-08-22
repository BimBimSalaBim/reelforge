"""Audio-mix driver: runs `video/sfx.py` inside a job workspace.

`sfx.py` lays the narration into a buffer untouched and sums the storyboard's
`SFX` events over it, writing `build/<name>.narr48.wav` and
`build/<name>.mix.wav`. It imports the storyboard by module name, so it needs
the workspace on the path -- and one storyboard per process, as ever.

Fonts are patched first even though the mix draws nothing: importing a
storyboard executes its module body, and a storyboard is free to touch `kit.f`
there.

    python3 -m app.render.shim_sfx --workspace WS --storyboard slug
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", required=True, type=Path)
    ap.add_argument("--storyboard", required=True)
    ap.add_argument("--allow-system-fonts", action="store_true")
    args = ap.parse_args()

    workspace = args.workspace.resolve()

    from app.render.shim_render import prepare

    prepare(workspace, strict_fonts=not args.allow_system_fonts)

    spec = importlib.util.spec_from_file_location(
        f"_sfx_{os.getpid()}", workspace / "sfx.py"
    )
    sfx = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = sfx
    spec.loader.exec_module(sfx)

    sfx.build(args.storyboard)

    mix = workspace / "build" / f"{args.storyboard}.mix.wav"
    print(json.dumps({
        "ok": mix.exists(),
        "mix_wav": str(mix),
        "bytes": mix.stat().st_size if mix.exists() else 0,
    }))
    return 0 if mix.exists() else 1


if __name__ == "__main__":
    raise SystemExit(main())
