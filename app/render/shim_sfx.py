"""Audio-mix driver: runs `video/sfx.py` inside a job workspace.

`sfx.py` lays the narration into a buffer untouched and sums the storyboard's
`SFX` events over it, writing `build/<name>.narr48.wav` and
`build/<name>.mix.wav`. It imports the storyboard by module name, so it needs
the workspace on the path -- and one storyboard per process, as ever.

Fonts are patched first even though the mix draws nothing: importing a
storyboard executes its module body, and a storyboard is free to touch `kit.f`
there.

    python3 -m app.render.shim_sfx --workspace WS --storyboard slug

Two optional additions, both from app/render/soundbed.py and both leaving
`sfx.py` as it is: `--sfx-dir` swaps generated one-shot samples in for the
synthesized event kinds (by replacing `make_gens` on the loaded module), and
`--music` mixes a bed under the narration after the build.
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
    ap.add_argument("--sfx-dir", type=Path, default=None,
                    help="directory of <kind>.wav one-shots to use instead of synthesis")
    ap.add_argument("--music", type=Path, default=None,
                    help="48k stereo wav bed to mix under the narration")
    ap.add_argument("--music-gain-db", type=float, default=-22.0)
    ap.add_argument("--music-duck-db", type=float, default=-9.0)
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

    report = {}
    if args.sfx_dir:
        from app.render.soundbed import load_sample_gens

        samples = load_sample_gens(args.sfx_dir)
        if samples:
            original = sfx.make_gens

            def with_samples(seed=17):
                gens = original(seed)
                gens.update(samples)      # a kind without a sample keeps its synth
                return gens

            sfx.make_gens = with_samples
        report["sfx_samples"] = sorted(samples)

    sfx.build(args.storyboard)

    mix = workspace / "build" / f"{args.storyboard}.mix.wav"
    if args.music and mix.exists():
        from app.render.soundbed import mix_bed, read_wav, write_wav

        narration = workspace / "build" / f"{args.storyboard}.narr48.wav"
        try:
            mixed, bed_report = mix_bed(
                read_wav(mix), read_wav(narration), read_wav(args.music),
                gain_db=args.music_gain_db, duck_db=args.music_duck_db,
            )
            write_wav(mix, mixed)
            report["music"] = bed_report
        except Exception as exc:
            # the reel is finished without the bed rather than not at all
            report["music"] = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}

    print(json.dumps({
        "ok": mix.exists(),
        "mix_wav": str(mix),
        "bytes": mix.stat().st_size if mix.exists() else 0,
        **report,
    }))
    return 0 if mix.exists() else 1


if __name__ == "__main__":
    raise SystemExit(main())
