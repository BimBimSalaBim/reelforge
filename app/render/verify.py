"""Assert an encoded mp4 meets both platforms' requirements.

`video/verify.sh` prints a report a human reads. That is the right tool at a
terminal and the wrong one in a pipeline, so this checks the same things and
*fails* on them, returning structured findings the UI can render.

The frame-count check is the one that matters most. `make.sh` writes straight
over its target, so a killed render leaves a shorter file that plays fine and
is wrong (DEVELOPMENT.md gotcha 8). Nothing else catches that.
"""
from __future__ import annotations

import json
import re
import struct
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app.render.workspace import ffmpeg_bin, ffprobe_bin

#: Conservative UI chrome, copied from video/safecheck.py. Anything meaningful
#: under one of these boxes will be covered by the app.
REELS_CHROME = [(0, 0, 1080, 110), (0, 1600, 1080, 1920), (960, 1080, 1080, 1700)]
SHORTS_CHROME = [(0, 0, 1080, 120), (0, 1620, 1080, 1860), (960, 1000, 1080, 1700)]

TARGET_LUFS = -14.0
LUFS_TOLERANCE = 0.7
TARGET_PEAK_DBTP = -1.5
PEAK_TOLERANCE = 0.3


@dataclass
class Check:
    name: str
    ok: bool
    expected: str
    actual: str

    def as_dict(self) -> dict:
        return {"name": self.name, "ok": self.ok,
                "expected": self.expected, "actual": self.actual}


@dataclass
class VerifyReport:
    path: str
    checks: list[Check] = field(default_factory=list)
    streams: dict = field(default_factory=dict)
    loudness: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]

    def as_dict(self) -> dict:
        return {"path": self.path, "ok": self.ok,
                "checks": [c.as_dict() for c in self.checks],
                "streams": self.streams, "loudness": self.loudness}


def _probe(path: Path) -> dict:
    proc = subprocess.run(
        [ffprobe_bin(), "-v", "error", "-show_streams", "-show_format",
         "-count_frames", "-of", "json", str(path)],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def _loudness(path: Path) -> dict:
    """Integrated loudness and true peak, via the same ebur128 filter verify.sh uses."""
    proc = subprocess.run(
        [ffmpeg_bin(), "-nostats", "-i", str(path), "-filter:a",
         "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True, check=False,
    )
    tail = proc.stderr[-4000:]
    out: dict[str, float] = {}
    for key, pattern in (
        ("integrated_lufs", r"I:\s*(-?\d+\.?\d*)\s*LUFS"),
        ("lra", r"LRA:\s*(-?\d+\.?\d*)\s*LU"),
        ("true_peak_dbtp", r"Peak:\s*(-?\d+\.?\d*)\s*dBFS"),
    ):
        found = re.findall(pattern, tail)
        if found:
            out[key] = float(found[-1])
    return out


def _atom_order(path: Path) -> list[str]:
    order: list[str] = []
    with open(path, "rb") as fh:
        offset = 0
        for _ in range(64):
            fh.seek(offset)
            header = fh.read(8)
            if len(header) < 8:
                break
            size = struct.unpack(">I", header[:4])[0]
            order.append(header[4:8].decode("latin1", "replace"))
            if size < 8:
                break
            offset += size
    return order


def verify(path: Path, *, expected_frames: int | None = None,
           expected_duration: float | None = None) -> VerifyReport:
    report = VerifyReport(path=str(path))
    add = report.checks.append

    if not path.exists():
        add(Check("file exists", False, "a file", "missing"))
        return report

    data = _probe(path)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    fmt = data.get("format", {})
    report.streams = {"video": video, "audio": audio, "format": fmt}

    if not video:
        add(Check("video stream", False, "one H.264 stream", "none"))
        return report
    if not audio:
        add(Check("audio stream", False, "one AAC stream", "none"))

    add(Check("dimensions", (video["width"], video["height"]) == (1080, 1920),
              "1080x1920", f'{video["width"]}x{video["height"]}'))
    add(Check("frame rate", video.get("r_frame_rate") == "30/1",
              "30/1", str(video.get("r_frame_rate"))))
    add(Check("video codec", video.get("codec_name") == "h264",
              "h264", str(video.get("codec_name"))))
    add(Check("profile", str(video.get("profile", "")).lower() == "high",
              "High", str(video.get("profile"))))
    add(Check("level", str(video.get("level")) == "41", "4.1 (41)", str(video.get("level"))))
    add(Check("pixel format", video.get("pix_fmt") == "yuv420p",
              "yuv420p", str(video.get("pix_fmt"))))
    # untagged, both platforms render the colours washed out
    for key in ("color_space", "color_primaries", "color_transfer"):
        add(Check(f"colour tag {key}", video.get(key) == "bt709",
                  "bt709", str(video.get(key))))

    frames = video.get("nb_read_frames") or video.get("nb_frames")
    frames = int(frames) if frames not in (None, "N/A") else None
    if expected_frames is not None:
        add(Check("frame count", frames == expected_frames,
                  str(expected_frames),
                  str(frames) + (" -- the render pipe broke, the tail is missing"
                                 if frames and frames < expected_frames else "")))

    duration = float(fmt.get("duration", 0.0))
    if expected_duration is not None:
        add(Check("duration", abs(duration - expected_duration) <= 0.15,
                  f"{expected_duration:.2f}s +/- 0.15", f"{duration:.2f}s"))
    add(Check("runtime 30-90s", 30.0 <= duration <= 90.0,
              "30-90s (Reels limit is 90s)", f"{duration:.2f}s"))

    if audio:
        add(Check("audio codec", audio.get("codec_name") == "aac",
                  "aac", str(audio.get("codec_name"))))
        add(Check("sample rate", str(audio.get("sample_rate")) == "48000",
                  "48000", str(audio.get("sample_rate"))))
        add(Check("channels", audio.get("channels") == 2, "2", str(audio.get("channels"))))

        report.loudness = _loudness(path)
        lufs = report.loudness.get("integrated_lufs")
        peak = report.loudness.get("true_peak_dbtp")
        if lufs is not None:
            add(Check("integrated loudness", abs(lufs - TARGET_LUFS) <= LUFS_TOLERANCE,
                      f"{TARGET_LUFS} +/- {LUFS_TOLERANCE} LUFS", f"{lufs} LUFS"))
        if peak is not None:
            add(Check("true peak", peak <= TARGET_PEAK_DBTP + PEAK_TOLERANCE,
                      f"<= {TARGET_PEAK_DBTP} dBTP", f"{peak} dBTP"))

    order = _atom_order(path)
    faststart = "moov" in order and "mdat" in order and order.index("moov") < order.index("mdat")
    add(Check("faststart", faststart, "moov before mdat", " -> ".join(order[:6])))
    return report


def contact_sheet(video: Path, out: Path, frame_numbers: list[int],
                  *, columns: int = 3) -> Path:
    """Frames from the *encoded* file, with both platforms' chrome drawn on top.

    The renderer is not the deliverable. Every bug in DEVELOPMENT.md's gotchas was
    found by looking at frames like these, and none of them raised an error.
    """
    from PIL import Image, ImageDraw

    out.parent.mkdir(parents=True, exist_ok=True)
    tiles = []
    for number in frame_numbers:
        raw = out.parent / f"_f{number:06d}.png"
        proc = subprocess.run(
            [ffmpeg_bin(), "-y", "-v", "error", "-i", str(video),
             "-vf", f"select=eq(n\\,{number})", "-vsync", "0", "-frames:v", "1", str(raw)],
            capture_output=True, text=True, check=False,
        )
        if proc.returncode != 0 or not raw.exists():
            continue
        image = Image.open(raw).convert("RGBA")
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for box in REELS_CHROME:
            draw.rectangle(box, fill=(255, 0, 80, 58), outline=(255, 0, 80, 150), width=3)
        for box in SHORTS_CHROME:
            draw.rectangle(box, fill=(0, 140, 255, 50), outline=(0, 140, 255, 150), width=3)
        tile = Image.alpha_composite(image, overlay).convert("RGB")
        tile.thumbnail((300, 534))
        tiles.append(tile)
        raw.unlink(missing_ok=True)

    if not tiles:
        raise RuntimeError(f"no frames extracted from {video}")

    rows = (len(tiles) + columns - 1) // columns
    width, height = tiles[0].size
    sheet = Image.new("RGB", (columns * (width + 6) + 6, rows * (height + 6) + 6), (20, 20, 22))
    for index, tile in enumerate(tiles):
        x = 6 + (index % columns) * (width + 6)
        y = 6 + (index // columns) * (height + 6)
        sheet.paste(tile, (x, y))
    sheet.save(out)
    return out
