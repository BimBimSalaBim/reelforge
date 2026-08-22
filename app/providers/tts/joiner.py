"""Join per-phrase audio into one narration track with controlled silence.

The gaps are the contract with `align.py`. Its default VAD merges anything
quieter than 32 dB below peak that lasts under 220 ms, so a gap must clear that
comfortably to register as a phrase boundary -- and the scene breaks want the
"about one second" pause the existing scripts ask the narrator for.

Everything is normalised to 48 kHz mono via ffmpeg before joining, then written
as a single mp3, because that is what the storyboards declare as `AUDIO` and
what `align.py` decodes.
"""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

from app.models.content import Phrase
from app.providers.tts.base import SpokenPhrase, TTSError
from app.render.workspace import ffmpeg_bin

SAMPLE_RATE = 48000
#: Must clear not just align.py's 220 ms merge threshold but every pause the
#: engine itself inserts *inside* a phrase. TTS engines pause 150-350 ms at
#: commas, and at 320 ms those internal pauses split too -- measured: 18
#: segments detected for 14 phrases. 520 ms separates the two populations
#: cleanly, so a min-silence anywhere in 380-500 ms cuts only at phrase joins.
MIN_GAP_MS = 520
SCENE_GAP_MS = 1000

#: What the align stage should use for audio joined by this module. Sits below
#: MIN_GAP_MS and above any credible intra-phrase pause.
SUGGESTED_MIN_SIL_MS = 420
LEAD_IN_MS = 60
TAIL_MS = 700


def _decode_to_mono(data: bytes, out_wav: Path) -> np.ndarray:
    proc = subprocess.run(
        [ffmpeg_bin(), "-y", "-v", "error", "-i", "pipe:0",
         "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "wav", str(out_wav)],
        input=data, capture_output=True, check=False,
    )
    if proc.returncode != 0 or not out_wav.exists():
        raise TTSError(f"could not decode synthesized audio: {proc.stderr.decode()[:300]}")
    with wave.open(str(out_wav)) as handle:
        frames = handle.readframes(handle.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def _silence(ms: int) -> np.ndarray:
    return np.zeros(int(SAMPLE_RATE * ms / 1000.0), dtype=np.float32)


def join(
    spoken: list[SpokenPhrase], phrases: list[Phrase], out_mp3: Path,
    *, scratch: Path | None = None,
) -> dict:
    """Write one mp3 and report the gaps used, so alignment can be checked."""
    if len(spoken) != len(phrases):
        raise TTSError(f"{len(spoken)} audio clips for {len(phrases)} phrases")

    scratch = scratch or out_mp3.parent / "_tts_scratch"
    scratch.mkdir(parents=True, exist_ok=True)

    pieces: list[np.ndarray] = [_silence(LEAD_IN_MS)]
    gaps: list[int] = []
    # Where each phrase actually lands. This is ground truth -- we are building
    # the track -- so alignment need not re-detect it from silences, which is
    # guesswork that fails whenever a voice pauses inside a phrase.
    segments: list[tuple[float, float]] = []
    cursor = LEAD_IN_MS / 1000.0

    for index, (clip, phrase) in enumerate(zip(spoken, phrases)):
        samples = _decode_to_mono(clip.audio, scratch / f"p{index:03d}.wav")
        samples = _trim_silence(samples)
        pieces.append(samples)
        span = len(samples) / SAMPLE_RATE
        segments.append((round(cursor, 3), round(cursor + span, 3)))
        cursor += span
        if index == len(spoken) - 1:
            continue
        scene_change = phrases[index + 1].scene_index != phrase.scene_index
        gap = SCENE_GAP_MS if scene_change else max(phrase.pause_after_ms, MIN_GAP_MS)
        gaps.append(gap)
        pieces.append(_silence(gap))
        cursor += gap / 1000.0
    pieces.append(_silence(TAIL_MS))

    track = np.concatenate(pieces)
    peak = float(np.max(np.abs(track))) or 1.0
    track = track * (0.89 / peak)  # headroom; loudnorm does the real levelling

    raw_wav = scratch / "narration.wav"
    with wave.open(str(raw_wav), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes((track * 32767.0).astype(np.int16).tobytes())

    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [ffmpeg_bin(), "-y", "-v", "error", "-i", str(raw_wav),
         "-codec:a", "libmp3lame", "-q:a", "2", "-ar", str(SAMPLE_RATE), str(out_mp3)],
        capture_output=True, check=False,
    )
    if proc.returncode != 0:
        raise TTSError(f"mp3 encode failed: {proc.stderr.decode()[:300]}")

    return {
        "mp3": str(out_mp3),
        "duration_seconds": round(len(track) / SAMPLE_RATE, 3),
        "phrase_count": len(spoken),
        "gaps_ms": gaps,
        # exact per-phrase boundaries, in seconds
        "segments": segments,
        "scene_gap_ms": SCENE_GAP_MS,
        "min_gap_ms": MIN_GAP_MS,
        # the align stage seeds its VAD from this instead of guessing
        "suggested_min_sil_ms": SUGGESTED_MIN_SIL_MS,
    }


def _trim_silence(samples: np.ndarray, floor_db: float = -45.0) -> np.ndarray:
    """Trim engine-added lead-in/out so the gaps we insert are the only gaps."""
    if samples.size == 0:
        return samples
    window = 480  # 10 ms
    frames = samples[: len(samples) - len(samples) % window].reshape(-1, window)
    if frames.size == 0:
        return samples
    rms = np.sqrt(np.mean(frames**2, axis=1))
    db = 20 * np.log10(np.maximum(rms, 1e-8))
    voiced = np.flatnonzero(db > floor_db)
    if voiced.size == 0:
        return samples
    start = max(0, (voiced[0] - 2) * window)
    end = min(len(samples), (voiced[-1] + 3) * window)
    return samples[start:end]
