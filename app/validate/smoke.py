"""Render a handful of frames from a generated storyboard, under limits.

Runs as its own process for three reasons, in order of importance:

1. `kit.set_palette` mutates module globals and a storyboard applies its theme
   at import time, so a second storyboard in the same interpreter inherits the
   first one's palette (DEVELOPMENT.md gotcha 5).
2. Generated code can loop forever or allocate without bound. A subprocess can
   be capped and killed; a thread cannot.
3. A crash in generated code must not take the worker with it.

The limits here contain *buggy* code, which is the actual threat model -- the
model writing this storyboard is one the operator configured. They are not a
boundary against hostile code, and the static import allowlist is not either.
For that, run the renderer container with no network and a read-only root.

    python3 -m app.validate.smoke --workspace WS --storyboard slug \
        --out DIR --frames 16
"""
from __future__ import annotations

import argparse
import json
import traceback

try:
    import resource
except ImportError:  # Windows: no rlimits; apply_limits becomes a no-op
    resource = None
from pathlib import Path

#: Content outside these bounds is covered by platform UI, per video/kit.py.
TOP_SAFE, BOT_SAFE, MARGIN = 150, 1600, 84
#: A pixel must differ from the untouched ground by more than this to count as
#: drawn content rather than grain or a bloom edge.
DIFF_THRESHOLD = 26
#: Luminance above which drawn content is legible rather than decorative.
#:
#: Mere difference from the ground is the wrong test for the safe area. These
#: storyboards use full-bleed decorative layers -- aas opens on a scrolling wall
#: of skill tags that runs edge to edge by design -- and those moved pixels are
#: not information anyone loses when the platform UI covers them. Measured on
#: that frame: the top band peaks at luminance 17 and the left band at 72, while
#: the headline sits at 192 and foreground text reaches 255. Anything a viewer
#: would actually read is far above this line.
LEGIBLE_LUMA = 150
#: Share of a band that must carry legible content before it is reported.
BAND_TRIP = 0.004
#: `sbkit.chrome` draws a progress bar across y 0-5 on every frame, deliberately.
#: It is decoration, not information, so it is meant to sit under the platform
#: UI -- excluding it stops every frame of a correct storyboard being reported.
CHROME_ROWS = 8
#: Below this share of drawn pixels a frame carries nothing. Calibrated against
#: the shipped storyboards, whose lightest real frame measures about 0.003.
BLANK_INK = 0.0015
#: A frame with less legible content than this is nearly bare -- an eyebrow and
#: empty space. The shipped storyboards run 0.0015 to 0.03 legible; a generated
#: one came back with a scene showing only its heading.
SPARSE_LEGIBLE = 0.0012
#: Longest mean gap between cuts before it is worth mentioning. DEVELOPMENT.md asks
#: for a cut every 2-4 s, but explicitly allows a longer hold that has events
#: inside it -- which a static check cannot see. This only catches the extreme.
MAX_MEAN_CUT_GAP = 8.0


def apply_limits(memory_mb: int, cpu_seconds: int) -> None:
    if resource is None:
        return
    soft = memory_mb * 1024 * 1024
    for limit, value in (
        (resource.RLIMIT_AS, soft),
        (resource.RLIMIT_CPU, cpu_seconds),
        (resource.RLIMIT_NOFILE, 256),
        (resource.RLIMIT_NPROC, 64),
    ):
        try:
            resource.setrlimit(limit, (value, value))
        except (ValueError, OSError):
            pass  # a platform that will not take the limit is not a reason to stop


def sample_times(scenes: list[tuple[str, float, float]], total: float, count: int) -> list[float]:
    """One frame inside every scene, plus both sides of every cut.

    Boundaries are where storyboards break: a scene that ends just before the
    line paying it off leaves text on screen for a tenth of a second.
    """
    times: list[float] = [0.0]
    for _, start, end in scenes:
        times.append(round(start + (end - start) * 0.5, 3))
        if start > 0:
            times.append(round(max(0.0, start - 0.05), 3))
            times.append(round(start + 0.05, 3))
    times.append(round(max(0.0, total - 0.1), 3))

    unique = sorted({min(max(t, 0.0), max(total - 0.001, 0.0)) for t in times})
    if len(unique) <= count:
        return unique
    step = len(unique) / count
    return [unique[int(i * step)] for i in range(count)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", required=True, type=Path)
    ap.add_argument("--storyboard", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--frames", type=int, default=16)
    ap.add_argument("--memory-mb", type=int, default=3072)
    ap.add_argument("--cpu-seconds", type=int, default=90)
    ap.add_argument("--expected-duration", type=float)
    ap.add_argument("--allow-system-fonts", action="store_true")
    args = ap.parse_args()

    apply_limits(args.memory_mb, args.cpu_seconds)
    args.out.mkdir(parents=True, exist_ok=True)
    report: dict = {"ok": False, "problems": [], "frames": []}

    def fail(rung: str, message: str) -> int:
        report["problems"].append({"rung": rung, "message": message})
        print(json.dumps(report))
        return 1

    try:
        from app.render.shim_render import prepare

        kit = prepare(args.workspace, strict_fonts=not args.allow_system_fonts)
    except Exception as exc:
        return fail("environment", f"could not prepare the render environment: {exc}")

    # Record where every string lands. Overlapping text has the density of
    # text, so no pixel measurement finds it -- but the draw calls do.
    from app.validate.textboxes import Recorder, collisions, install

    recorder = Recorder()
    install(kit, recorder)

    try:
        sb = __import__(args.storyboard)
    except Exception:
        return fail("import", "the storyboard raised while being imported:\n"
                              + traceback.format_exc(limit=6))

    # ---- rung 3 continued: values, not just presence --------------------
    total = float(getattr(sb, "TOTAL", 0.0))
    fps = int(getattr(sb, "FPS", 0))
    if fps != 30:
        report["problems"].append({"rung": "contract",
                                   "message": f"FPS is {fps}; it must be 30."})
    if total <= 0:
        return fail("contract", f"TOTAL is {total}; it must be the video's length in seconds.")
    if args.expected_duration and abs(total - args.expected_duration) > 0.15:
        report["problems"].append({"rung": "contract", "message":
            f"TOTAL is {total}s but the narration is {args.expected_duration:.2f}s. "
            "They must agree within 0.15s or the video ends early or hangs on black."})

    # ---- rung 5: the scene table ----------------------------------------
    scenes = list(getattr(sb, "SC", None) or getattr(sb, "S", None) or [])
    scenes = [(str(n), float(a), float(b)) for n, a, b in scenes] if scenes else []
    report["scenes"] = scenes
    if scenes:
        problems = check_scene_table(scenes, total)
        report["problems"].extend({"rung": "scenes", "message": m} for m in problems)

    # ---- rungs 6 and 7: render, then look at what was drawn -------------
    times = sample_times(scenes or [("all", 0.0, total)], total, args.frames)
    base = None
    try:
        base = getattr(sb, "BASE", None)
    except Exception:
        base = None

    for index, t in enumerate(times):
        recorder.reset()
        try:
            image = sb.frame(t)
        except Exception:
            return fail("render", f"frame({t}) raised:\n" + traceback.format_exc(limit=6))
        if image is None:
            return fail("render", f"frame({t}) returned None; it must return a PIL image.")
        if image.size != (1080, 1920):
            return fail("render", f"frame({t}) is {image.size}; it must be 1080x1920.")
        if image.mode != "RGBA":
            return fail("render", f"frame({t}) is mode {image.mode}; it must be RGBA.")
        raw = image.tobytes()
        if len(raw) != 1080 * 1920 * 4:
            return fail("render",
                        f"frame({t}) produced {len(raw)} bytes, expected {1080 * 1920 * 4}.")

        path = args.out / f"smoke_{index:02d}_t{t:07.3f}.png"
        image.convert("RGB").save(path)
        entry = {"t": t, "path": str(path)}
        entry.update(inspect_frame(image, base))
        entry["collisions"] = collisions(recorder.boxes)
        entry["strings"] = len(recorder.boxes)
        report["frames"].append(entry)

    outside = [f for f in report["frames"] if f.get("outside_safe")]
    if outside:
        detail = ", ".join(f"t={f['t']} ({'/'.join(f['outside_safe'])})" for f in outside[:6])
        report["problems"].append({"rung": "safe-area", "message":
            "Content is drawn outside the safe area at: " + detail +
            f". Keep everything inside y {TOP_SAFE}-{BOT_SAFE} and x {MARGIN}-{1080 - MARGIN}; "
            "the platform UI covers the rest."})

    blank = [f["t"] for f in report["frames"] if f.get("ink", 1.0) < BLANK_INK]
    if blank:
        report["problems"].append({"rung": "blank", "message":
            f"These frames are effectively empty: {blank}. Every frame should carry "
            "the scene it belongs to."})

    sparse = [f["t"] for f in report["frames"]
              if f["t"] not in blank and f.get("legible", 1.0) < SPARSE_LEGIBLE
              and f.get("strings", 0) <= 2]
    if sparse:
        report["problems"].append({"rung": "sparse", "message":
            f"These frames are nearly bare -- a heading and little else: {sparse}. "
            "Give every scene something to look at for its whole length: the "
            "figures, the labels, the component it is describing."})

    collided = [f for f in report["frames"] if f.get("collisions")]
    if collided:
        lines = []
        for frame in collided[:5]:
            for hit in frame["collisions"][:3]:
                lines.append(
                    f"  t={frame['t']}: \"{hit['a']}\" and \"{hit['b']}\" overlap by "
                    f"{int(hit['share'] * 100)}% (boxes {hit['box_a']} and {hit['box_b']})"
                )
        report["problems"].append({"rung": "overlap", "message":
            "Text is drawn on top of other text and neither can be read:\n"
            + "\n".join(lines)
            + "\nGive each element its own vertical band. Nothing that is on "
              "screen at the same moment may share space."})

    report["ok"] = not report["problems"]
    print(json.dumps(report))
    return 0 if report["ok"] else 1


def check_scene_table(scenes: list[tuple[str, float, float]], total: float) -> list[str]:
    problems: list[str] = []
    if scenes[0][1] > 0.001:
        problems.append(f"the scene table starts at {scenes[0][1]}s; it must start at 0.")
    if abs(scenes[-1][2] - total) > 0.001:
        problems.append(
            f"the scene table ends at {scenes[-1][2]}s but TOTAL is {total}s; they must match."
        )
    for (name_a, _, end_a), (name_b, start_b, _) in zip(scenes, scenes[1:]):
        if abs(end_a - start_b) > 0.001:
            problems.append(
                f"scenes {name_a!r} and {name_b!r} do not meet: {end_a}s then {start_b}s. "
                "Scenes must be contiguous."
            )
    for name, start, end in scenes:
        if end - start < 1.2:
            problems.append(
                f"scene {name!r} lasts {end - start:.2f}s. Nothing reads in under 1.2s."
            )
    if total > 0:
        cuts = max(1, len(scenes) - 1)
        if total / cuts > MAX_MEAN_CUT_GAP:
            problems.append(
                f"only {cuts} cut(s) in {total:.1f}s. A cut every 2-4 seconds holds "
                "attention; if a layout must hold longer, give it an event inside the hold."
            )
    return problems


def inspect_frame(image, base) -> dict:
    """How much was drawn, and whether anything *legible* is under the platform UI.

    Two different questions, two different measurements:

    `ink` is how much of the frame differs from the storyboard's own untouched
    ground plate. Comparing against that plate rather than a flat colour isolates
    drawn content from the background's blooms and grain, which otherwise read as
    content everywhere. It answers "is this frame carrying anything at all".

    `outside_safe` is about legibility, not difference. A full-bleed decorative
    layer moving behind the content is not information a viewer loses when the
    app's UI covers it, so the band test looks for bright pixels -- text and
    accents -- rather than merely changed ones.
    """
    import numpy as np

    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    if base is not None:
        try:
            ground = np.asarray(base.convert("RGB"), dtype=np.float32)
            delta = np.abs(rgb - ground).max(axis=2)
        except Exception:
            delta = np.abs(rgb - rgb[0, 0]).max(axis=2)
    else:
        delta = np.abs(rgb - rgb[0, 0]).max(axis=2)
    drawn = delta > DIFF_THRESHOLD

    luma = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    legible = luma > LEGIBLE_LUMA
    width = legible.shape[1]
    bands = {
        # the progress bar across y 0-5 is deliberate decoration, not information
        "top": legible[CHROME_ROWS:TOP_SAFE, :],
        "bottom": legible[BOT_SAFE:, :],
        "left": legible[TOP_SAFE:BOT_SAFE, :MARGIN],
        "right": legible[TOP_SAFE:BOT_SAFE, width - MARGIN:],
    }
    outside = [name for name, band in bands.items()
               if band.size and float(band.mean()) > BAND_TRIP]
    return {"ink": round(float(drawn.mean()), 5),
            "legible": round(float(legible.mean()), 5),
            "outside_safe": outside}


if __name__ == "__main__":
    raise SystemExit(main())
