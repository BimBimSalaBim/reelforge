"""Alignment driver: runs `video/align.py` inside a job workspace.

Adds two things the bare CLI cannot do:

1. **Pronunciation injection.** `align.SPOKEN` is a module-global table of
   initialisms the syllable counter gets wrong ("MCP" is one vowel run but three
   spoken syllables). Without an entry, the whole phrase containing it drifts by
   about 200 ms (DEVELOPMENT.md gotcha 7). The generated content carries its own
   pronunciation map, which is merged in here.

2. **Parameter sweep.** `align.py build` refuses to run unless the phrase count
   equals the detected segment count. For synthesized audio the counts match by
   construction, because each phrase is spoken separately with real silence
   between. For uploaded human audio they often do not, so this sweeps the
   voiced/silent thresholds looking for a pair that yields the wanted count --
   the automated form of the "re-read the probe output" advice in align.py's
   own docstring.

Runs as a subprocess: `align` binds its working directory from its own
`__file__`, so it must be imported from the workspace, and two workspaces cannot
share one interpreter.

    python3 -m app.render.shim_align probe  --workspace WS --audio A.mp3
    python3 -m app.render.shim_align sweep  --workspace WS --audio A.mp3 --target 14
    python3 -m app.render.shim_align build  --workspace WS --audio A.mp3 \
        --name slug --phrases phrases/slug.txt --pronunciations '{"npx":3}'

Every mode prints a single JSON object on stdout.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

#: (drop dB below peak, minimum silence ms) pairs, tried in this order.
#: Defaults first, then progressively more and less eager splitting.
SWEEP_GRID: list[tuple[float, int]] = [
    (drop, sil)
    for sil in (220, 260, 300, 180, 340, 150, 400, 120, 500)
    for drop in (32.0, 30.0, 34.0, 28.0, 36.0, 26.0, 40.0)
]


def load_align(workspace: Path):
    """Import the workspace's `align.py` under a private module name.

    A plain `import align` would cache one instance in `sys.modules` and every
    later workspace would inherit the first one's `HERE`.
    """
    path = workspace / "align.py"
    if not path.exists():
        raise SystemExit(f"no align.py in workspace {workspace}")
    spec = importlib.util.spec_from_file_location(f"_align_{os.getpid()}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_phrases(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["probe", "sweep", "build"])
    ap.add_argument("--workspace", required=True, type=Path)
    ap.add_argument("--audio", required=True, type=Path)
    ap.add_argument("--name")
    ap.add_argument("--phrases", type=Path)
    ap.add_argument("--target", type=int, help="wanted segment count for sweep")
    ap.add_argument("--drop", type=float, default=32.0)
    ap.add_argument("--min-sil", type=int, default=220)
    ap.add_argument("--pronunciations", default="{}")
    ap.add_argument("--segments", default="",
                    help="JSON [[start,end],...] to use instead of detecting them. "
                         "Synthesized narration is assembled from known clips, so "
                         "its boundaries are facts rather than something to infer.")
    args = ap.parse_args()

    workspace = args.workspace.resolve()
    align = load_align(workspace)

    pronunciations = json.loads(args.pronunciations or "{}")
    if pronunciations:
        align.SPOKEN.update({str(k): int(v) for k, v in pronunciations.items()})

    samples, rate, duration = align.decode16k(str(args.audio))

    if args.mode == "probe":
        segments = align.segments(samples, rate, args.drop, args.min_sil)
        print(json.dumps({
            "duration": round(duration, 3),
            "drop": args.drop,
            "min_sil": args.min_sil,
            "count": len(segments),
            "segments": [[float(s), float(e)] for s, e in segments],
        }))
        return 0

    if args.mode == "sweep":
        if args.target is None:
            raise SystemExit("--target is required for sweep")
        tried: list[dict] = []
        for drop, min_sil in SWEEP_GRID:
            segments = align.segments(samples, rate, drop, min_sil)
            tried.append({"drop": drop, "min_sil": min_sil, "count": len(segments)})
            if len(segments) == args.target:
                print(json.dumps({
                    "matched": True, "drop": drop, "min_sil": min_sil,
                    "duration": round(duration, 3), "count": len(segments),
                    "segments": [[float(s), float(e)] for s, e in segments],
                    "attempts": len(tried),
                }))
                return 0
        counts = sorted({entry["count"] for entry in tried})
        print(json.dumps({
            "matched": False, "target": args.target,
            "duration": round(duration, 3),
            "reachable_counts": counts,
            "attempts": len(tried),
            "closest": min(tried, key=lambda e: abs(e["count"] - args.target)),
        }))
        return 0

    # build
    if not args.name or not args.phrases:
        raise SystemExit("--name and --phrases are required for build")
    phrase_path = args.phrases if args.phrases.is_absolute() else workspace / args.phrases
    phrases = read_phrases(phrase_path)
    if args.segments:
        segments = [(float(a), float(b)) for a, b in json.loads(args.segments)]
        detected = False
    else:
        segments = align.segments(samples, rate, args.drop, args.min_sil)
        detected = True
    if len(phrases) != len(segments):
        print(json.dumps({
            "ok": False,
            "error": (
                f"{len(segments)} voiced phrases in audio, {len(phrases)} lines in "
                f"{phrase_path.name}"
            ),
            "segment_count": len(segments),
            "phrase_count": len(phrases),
            "segments": [[float(s), float(e)] for s, e in segments],
            "phrases": phrases,
        }))
        return 1

    words = []
    for (start, end), phrase in zip(segments, phrases):
        tokens = phrase.split()
        weights = [align.weight(tok) for tok in tokens]
        total = sum(weights)
        cursor = start
        for token, w in zip(tokens, weights):
            span = (end - start) * w / total
            words.append({"w": token, "s": round(cursor, 3), "e": round(cursor + span, 3)})
            cursor += span

    out_path = workspace / "build" / f"{args.name}.timing.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "duration": duration,
        "segments": [list(seg) for seg in segments],
        "phrases": phrases,
        "words": words,
    }
    out_path.write_text(json.dumps(payload, indent=1))

    rates = [
        {"phrase": phrase, "start": seg[0], "end": seg[1],
         "words_per_second": round(len(phrase.split()) / max(seg[1] - seg[0], 1e-3), 2)}
        for seg, phrase in zip(segments, phrases)
    ]
    print(json.dumps({
        "ok": True,
        "detected": detected,
        "timing_json": str(out_path),
        "duration": round(duration, 3),
        "segment_count": len(segments),
        "word_count": len(words),
        "drop": args.drop,
        "min_sil": args.min_sil,
        "pronunciations_applied": sorted(pronunciations),
        # align.py flags anything above 4.4 w/s as suspiciously fast
        "fast_phrases": [r for r in rates if r["words_per_second"] > 4.4],
        "rates": rates,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
