"""Stage 5: align the narration to the phrase list.

`align.py build` refuses to run unless the number of voiced segments it detects
equals the number of phrase lines. That check is load-bearing -- it is what
keeps captions in sync -- and it is also the step that most often needs a human
in the current process.

Three paths, in order of preference:

1. **Synthesized audio.** The phrases were spoken separately and joined with
   known silence, so the counts match by construction and the right VAD
   threshold is known rather than guessed.
2. **Uploaded audio, swept.** Try a grid of voiced/silent thresholds and take
   the first that yields the wanted count. This is the automated form of the
   "re-read the probe output and re-split" advice in align.py's own docstring.
3. **Uploaded audio, no match.** Report the detected segments beside the phrase
   lines so a human can split or merge. This is a judgement call about where a
   sentence really ended, and guessing it silently would be worse than asking.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from app.models.content import ReelContent
from app.models.job import Job, Stage
from app.store import JobStore

Progress = Callable[[str], None]


class AlignmentUnresolved(RuntimeError):
    """Counts do not match and no parameter sweep fixed it. A human decides."""

    def __init__(self, message: str, detail: dict):
        super().__init__(message)
        self.detail = detail


def _run(args: list[str]) -> dict:
    repo_root = Path(__file__).resolve().parent.parent.parent
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    proc = subprocess.run(
        [sys.executable or "python3", "-m", "app.render.shim_align", *args],
        capture_output=True, text=True, cwd=repo_root, env=env, check=False,
    )
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise RuntimeError(
            "alignment failed:\n" + (proc.stderr.strip() or proc.stdout.strip())[-1500:]
        ) from None


def split_phrases_to_match(lines: list[str], target: int) -> list[str] | None:
    """Split phrases at their own punctuation until there are `target` of them.

    A voice pauses where the text tells it to. Sentence boundaries are tried
    first because a full stop is the longest pause, then commas and semicolons,
    which is where a long line actually gets its breath -- "Apache two zero
    license, thirty eight thousand forty eight stars." is heard as two.

    Returns None when the count cannot be reached without inventing a break the
    text does not contain, in which case a human decides.
    """
    import re as _re

    def candidates(text: str, pattern: str) -> list[str]:
        parts = [part.strip() for part in _re.split(pattern, text) if part.strip()]
        # a break is only real if both sides can stand as a spoken phrase
        return parts if len(parts) > 1 and all(len(p.split()) >= 2 for p in parts) else []

    out = list(lines)
    # strongest boundary first: a full stop, then a clause break
    for pattern in (r"(?<=[.!?])\s+", r"(?<=[,;])\s+"):
        while len(out) < target:
            splittable = [
                (index, parts) for index, text in enumerate(out)
                if (parts := candidates(text, pattern))
            ]
            if not splittable:
                break
            # split the longest line that has such a boundary
            index, parts = max(splittable, key=lambda item: len(out[item[0]].split()))
            # only take as many pieces as are still needed
            room = target - len(out) + 1
            if len(parts) > room:
                parts = parts[:room - 1] + [" ".join(parts[room - 1:])]
            out[index:index + 1] = parts
        if len(out) == target:
            return out
    return out if len(out) == target else None


def align_job(job: Job, store: JobStore, progress: Progress | None = None) -> dict:
    paths = store.paths(job)
    content = ReelContent.model_validate_json(paths.content_json.read_text(encoding="utf-8"))
    phrase_count = len(content.phrases)
    pronunciations = json.dumps(content.audio.pronunciations)

    audio_meta = job.state(Stage.AUDIO).meta or {}
    synthesized = audio_meta.get("provider") not in (None, "upload")
    known = audio_meta.get("segments")
    min_sil = int(audio_meta.get("suggested_min_sil_ms") or 220)
    drop = 32.0

    base = ["--workspace", str(paths.workspace), "--audio", str(paths.audio_mp3)]

    # Synthesized narration was assembled here from one clip per phrase, so the
    # boundaries are known exactly. Re-detecting them by silence analysis is
    # guesswork that fails the moment a voice pauses inside a phrase -- which is
    # how 11 phrases became 12 detected segments with no threshold able to
    # reconcile them.
    if known and len(known) == phrase_count:
        if progress:
            progress(f"using the {phrase_count} boundaries recorded when the "
                     "narration was assembled")
        result = _run([
            *base, "build", "--name", job.slug,
            "--phrases", str(paths.phrases_txt),
            "--segments", json.dumps(known),
            "--pronunciations", pronunciations,
        ])
        if not result.get("ok"):
            raise RuntimeError(result.get("error", "alignment build failed"))
        return {
            "artifacts": {"timing": paths.rel(paths.timing_json)},
            "meta": {"duration": result["duration"],
                     "segments": result["segment_count"],
                     "words": result["word_count"],
                     "source": "recorded at synthesis",
                     "synthesized": True,
                     "pronunciations_applied": result.get("pronunciations_applied", []),
                     "fast_phrases": result.get("fast_phrases", [])},
        }

    probe = _run([*base, "probe", "--min-sil", str(min_sil), "--drop", str(drop)])
    if progress:
        progress(f"detected {probe['count']} voiced segments for {phrase_count} phrases")

    if probe["count"] != phrase_count:
        if progress:
            progress("counts differ; sweeping the detection thresholds")
        sweep = _run([*base, "sweep", "--target", str(phrase_count)])

        if not sweep.get("matched") and probe["count"] > phrase_count:
            # The voice paused inside a phrase -- usually at a full stop in the
            # middle of one. Splitting that phrase at its own sentence boundary
            # matches what was actually said, needs no re-synthesis, and is
            # exactly what a person would do by hand.
            split = split_phrases_to_match(content.phrase_lines(), probe["count"])
            if split:
                if progress:
                    progress(f"the voice paused inside a phrase; splitting "
                             f"{phrase_count} lines into {len(split)} to match")
                from app.render import documents

                updated = content.model_copy(update={"phrases": [
                    type(content.phrases[0])(
                        text=text,
                        scene_index=content.phrases[min(i, len(content.phrases) - 1)].scene_index,
                        pause_after_ms=300)
                    for i, text in enumerate(split)
                ]})
                paths.content_json.write_text(updated.model_dump_json(indent=2), encoding="utf-8")
                paths.phrases_txt.write_text(documents.phrases_txt(updated), encoding="utf-8")
                content, phrase_count = updated, len(split)
                sweep = {"matched": True, "drop": drop, "min_sil": min_sil}

        if not sweep.get("matched"):
            detail = {
                "phrase_count": phrase_count,
                "detected": probe["count"],
                "segments": probe["segments"],
                "phrases": content.phrase_lines(),
                "reachable_counts": sweep.get("reachable_counts", []),
                "closest": sweep.get("closest"),
                "duration": probe["duration"],
            }
            raise AlignmentUnresolved(
                f"the narration splits into {probe['count']} phrases but the script has "
                f"{phrase_count}, and no detection threshold reconciles them "
                f"(reachable counts: {sweep.get('reachable_counts')}). "
                "Split or merge the phrase lines to match what was actually spoken.",
                detail,
            )
        drop, min_sil = sweep["drop"], sweep["min_sil"]
        if progress:
            progress(f"reconciled with drop={drop}dB min-sil={min_sil}ms")

    result = _run([
        *base, "build", "--name", job.slug,
        "--phrases", str(paths.phrases_txt),
        "--drop", str(drop), "--min-sil", str(min_sil),
        "--pronunciations", pronunciations,
    ])
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "alignment build failed"))

    fast = result.get("fast_phrases", [])
    if fast and progress:
        progress(f"{len(fast)} phrase(s) are unusually fast; captions may feel rushed")

    if progress:
        progress(f"aligned {result['segment_count']} phrases, {result['word_count']} words")

    return {
        "artifacts": {"timing": paths.rel(paths.timing_json)},
        "meta": {
            "duration": result["duration"],
            "segments": result["segment_count"],
            "words": result["word_count"],
            "drop": drop, "min_sil": min_sil,
            "synthesized": synthesized,
            "pronunciations_applied": result.get("pronunciations_applied", []),
            "fast_phrases": fast,
        },
    }


def reconcile_preview(job: Job, store: JobStore, *, drop: float = 32.0,
                      min_sil: int = 220) -> dict:
    """Detected segments beside the phrase lines, for the UI's split/merge view."""
    paths = store.paths(job)
    content = ReelContent.model_validate_json(paths.content_json.read_text(encoding="utf-8"))
    probe = _run(["--workspace", str(paths.workspace), "--audio", str(paths.audio_mp3),
                  "probe", "--drop", str(drop), "--min-sil", str(min_sil)])
    phrases = content.phrase_lines()
    rows = []
    for index in range(max(len(phrases), probe["count"])):
        segment = probe["segments"][index] if index < probe["count"] else None
        rows.append({
            "index": index,
            "start": segment[0] if segment else None,
            "end": segment[1] if segment else None,
            "duration": round(segment[1] - segment[0], 2) if segment else None,
            "phrase": phrases[index] if index < len(phrases) else None,
        })
    return {"detected": probe["count"], "phrases": len(phrases),
            "matched": probe["count"] == len(phrases),
            "drop": drop, "min_sil": min_sil,
            "duration": probe["duration"], "rows": rows}
