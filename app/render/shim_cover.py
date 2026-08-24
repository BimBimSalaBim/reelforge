"""Cover driver: runs `video/covers.py` with a generated spec and bundled fonts.

`covers.py` renders from a module-level SPECS dict and writes to the repo root.
Injecting one entry and overriding its output directory reuses that layout code
exactly, rather than reimplementing it here where it would drift.
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
    ap.add_argument("--spec", required=True, type=Path)
    ap.add_argument("--key", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--allow-system-fonts", action="store_true")
    ap.add_argument("--backdrop", type=Path, default=None,
                    help="a generated 1080x1920 image to paint under the typography")
    args = ap.parse_args()

    workspace = args.workspace.resolve()
    sys.path.insert(0, str(workspace))

    import kit

    from app.render.fonts import check_symbols, patch_kit

    if patch_kit(kit, strict=not args.allow_system_fonts):
        check_symbols(kit)

    spec = importlib.util.spec_from_file_location(
        f"_covers_{os.getpid()}", workspace / "covers.py"
    )
    covers = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = covers
    spec.loader.exec_module(covers)

    payload = json.loads(args.spec.read_text(encoding="utf-8"))
    payload["file"] = args.out.name
    payload["mark_font"] = tuple(payload["mark_font"])
    payload["stats"] = [tuple(s) for s in payload["stats"]]
    for key in ("bg", "accent", "accent_hi", "pale", "glow", "support"):
        payload[key] = tuple(payload[key])

    # Measure before drawing: covers.py draws the kicker, hook and footers at a
    # fixed size with no shrink-to-fit, so an overlong string clips silently.
    from app.validate.cover_fit import measure

    fit_problems = measure(kit, payload)

    covers.SPECS[args.key] = payload
    args.out.parent.mkdir(parents=True, exist_ok=True)
    covers.OUT = str(args.out.parent)   # covers.py writes into OUT

    if args.backdrop:
        # Same injection idea as SPECS: covers.render() calls ground() for
        # its base and MOTIFS[...] for the top band, both module attributes,
        # so a generated picture replaces the procedural ground here without
        # covers.py learning anything about it.
        from app.render.backdrop import prepare_backdrop

        base = prepare_backdrop(args.backdrop, payload)
        covers.ground = lambda _s: base.copy()
        covers.MOTIFS[payload["motif"]] = lambda *_a, **_k: None

    produced = covers.render(args.key)
    print(json.dumps({"ok": True, "path": str(produced or args.out),
                      "fit_problems": fit_problems}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
