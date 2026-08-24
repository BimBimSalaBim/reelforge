"""A music bed under the narration, and generated one-shots for the cuts.

`video/sfx.py` owns the mix: narration written in untouched, the storyboard's
sound-design events summed over it. Two things are added here without
touching that file, both applied by `shim_sfx.py`:

* **Samples for the event kinds.** `sfx.make_gens()` returns a dict of kind ->
  function returning a float32 signal at 48 kHz, and every storyboard's `SFX`
  list names a kind and an `amp`. A generated one-shot becomes one more such
  function: loaded once, trimmed, peak-normalised so `amp` means what it
  always meant, faded at the event's own `dur` when it gives one. A kind with
  no sample keeps its synthesized generator, so a half-generated library
  still mixes.

* **The bed.** Mixed in after `sfx.build()` has written the mix: gain, then
  ducked under the narration by an envelope follower (fast attack, slow
  release, so a pause between phrases lets the music breathe without it
  pumping on every word), faded in at the top and out across the end card.
  The narration is never touched, and the peak guard is the same 0.985 that
  sfx.py uses, so loudnorm downstream sees the same kind of material.

Keep it quiet. DEVELOPMENT.md's rule is that narration stays dominant; a bed
anyone notices is too loud. -22 dB with -9 dB of duck is where it sits under
a level voice without vanishing in the gaps.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 48000
PEAK_GUARD = 0.985
#: a one-shot longer than this is a texture, not a hit; trimmed hard
MAX_SAMPLE_SECONDS = 2.5
#: leading silence a generator tends to leave before the transient
TRIM_THRESHOLD = 0.02


# ------------------------------------------------------------------ wav ---
def read_wav(path: Path) -> np.ndarray:
    """Stereo float32 at 48 kHz. Anything else is the caller's bug -- the
    adapters convert on the way in, and the test fixtures are written so."""
    with wave.open(str(path)) as w:
        if w.getframerate() != SR:
            raise ValueError(f"{path.name}: expected {SR} Hz, got {w.getframerate()}")
        width = w.getsampwidth()
        raw = w.readframes(w.getnframes())
        channels = w.getnchannels()
    if width != 2:
        raise ValueError(f"{path.name}: expected 16-bit samples")
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    data = data.reshape(-1, channels)
    if channels == 1:
        data = np.repeat(data, 2, axis=1)
    return data[:, :2]


def write_wav(path: Path, data: np.ndarray) -> None:
    clipped = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(clipped.tobytes())


# ---------------------------------------------------------------- samples ---
def prepare_sample(data: np.ndarray, *, max_seconds: float = MAX_SAMPLE_SECONDS) -> np.ndarray:
    """Mono float32, leading silence trimmed, peak at 1.0, capped in length."""
    mono = data.mean(axis=1) if data.ndim == 2 else data.astype(np.float32)
    peak = float(np.abs(mono).max()) if mono.size else 0.0
    if peak <= 0:
        return mono[:1].astype(np.float32)
    mono = mono / peak
    above = np.flatnonzero(np.abs(mono) > TRIM_THRESHOLD)
    if above.size:
        start = max(0, int(above[0]) - int(0.003 * SR))
        mono = mono[start:]
    mono = mono[: int(max_seconds * SR)]
    # a short tail so a hard cut at the cap never clicks
    tail = min(len(mono), int(0.02 * SR))
    if tail > 1:
        mono[-tail:] *= np.linspace(1.0, 0.0, tail, dtype=np.float32)
    return mono.astype(np.float32)


def sample_generator(sample: np.ndarray):
    """A drop-in for one of `sfx.make_gens()`'s functions.

    Accepts the same keyword arguments the synthesized kinds take (`dur`,
    `freq`, `tone`...) and honours `dur` by fading the sample out there, so
    a storyboard that asks for a 2 s sweep gets 2 s of it and one that asks
    for a 0.05 s tick gets a blip. Everything else is ignored -- a recorded
    sample has no `freq` to change.
    """
    def gen(dur: float | None = None, **_):
        out = sample
        if dur:
            n = max(1, int(float(dur) * SR))
            if n < len(out):
                out = out[:n].copy()
                fade = min(n, int(0.012 * SR))
                if fade > 1:
                    out[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
        return out.astype(np.float32)

    return gen


def load_sample_gens(directory: Path) -> dict:
    """`kind -> generator` for every `<kind>.wav` in the library directory."""
    gens = {}
    if not directory or not Path(directory).is_dir():
        return gens
    for path in sorted(Path(directory).glob("*.wav")):
        try:
            gens[path.stem] = sample_generator(prepare_sample(read_wav(path)))
        except Exception:
            continue    # one bad file is not a reason to lose the others
    return gens


# -------------------------------------------------------------------- bed ---
def envelope(narration: np.ndarray, *, window: float = 0.03, attack: float = 0.02,
             release: float = 0.45) -> np.ndarray:
    """How loud the voice is right now, 0..1, smoothed the way a sidechain
    compressor hears it: almost instant onset, slow decay."""
    mono = np.abs(narration).mean(axis=1) if narration.ndim == 2 else np.abs(narration)
    total = len(mono)
    if total == 0:
        return np.zeros(0, np.float32)
    # RMS in 1 ms blocks: a 45 s reel is 2.2M samples, and the follower below
    # is a Python loop, so it runs over 45k blocks instead
    hop = SR // 1000
    padded = np.concatenate([mono, np.zeros((-len(mono)) % hop, np.float32)])
    blocks = np.sqrt((padded.reshape(-1, hop) ** 2).mean(axis=1))
    n = max(1, int(window * SR / hop))
    kernel = np.ones(n, dtype=np.float32) / n
    rms = np.convolve(blocks, kernel, mode="same")
    # one-pole follower with separate attack and release coefficients
    a_att = float(np.exp(-hop / (attack * SR)))
    a_rel = float(np.exp(-hop / (release * SR)))
    out = np.empty_like(rms)
    level = 0.0
    for i, x in enumerate(rms):
        coeff = a_att if x > level else a_rel
        level = coeff * level + (1.0 - coeff) * x
        out[i] = level
    peak = float(out.max()) if out.size else 0.0
    if peak > 0:
        out = out / peak
    return np.repeat(out, hop)[:total].astype(np.float32)


def place_bed(bed: np.ndarray, total_seconds: float, *, fade_in: float = 0.8,
              fade_out: float = 2.5) -> np.ndarray:
    """The bed cut (or tiled, with a crossfade) to the reel's length, with the
    fades that make it arrive with the hook and leave under the end card."""
    n = int(total_seconds * SR)
    if len(bed) == 0:
        return np.zeros((n, 2), np.float32)
    if len(bed) < n:
        # tile with a short equal-power crossfade at each seam
        xf = min(int(1.0 * SR), len(bed) // 4)
        pieces = [bed]
        while sum(len(p) for p in pieces) - xf * (len(pieces) - 1) < n:
            pieces.append(bed)
        out = pieces[0].copy()
        for piece in pieces[1:]:
            if xf > 0:
                ramp = np.linspace(0.0, 1.0, xf, dtype=np.float32)[:, None]
                seam = out[-xf:] * np.sqrt(1.0 - ramp) + piece[:xf] * np.sqrt(ramp)
                out = np.concatenate([out[:-xf], seam, piece[xf:]])
            else:
                out = np.concatenate([out, piece])
        bed = out
    bed = bed[:n].copy()
    fi = min(n, int(fade_in * SR))
    fo = min(n, int(fade_out * SR))
    if fi > 1:
        bed[:fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)[:, None] ** 2
    if fo > 1:
        bed[-fo:] *= np.linspace(1.0, 0.0, fo, dtype=np.float32)[:, None] ** 1.5
    return bed


def mix_bed(mix: np.ndarray, narration: np.ndarray, bed: np.ndarray, *,
            gain_db: float = -22.0, duck_db: float = -9.0,
            total_seconds: float | None = None) -> tuple[np.ndarray, dict]:
    """`mix` plus the bed, ducked under `narration`. Returns the new mix and a
    few numbers worth logging."""
    n = len(mix)
    total = total_seconds if total_seconds is not None else n / SR
    placed = place_bed(bed, total)[:n]
    if len(placed) < n:
        placed = np.concatenate([placed, np.zeros((n - len(placed), 2), np.float32)])
    narr = narration[:n]
    if len(narr) < n:
        narr = np.concatenate([narr, np.zeros((n - len(narr), 2), np.float32)])
    env = envelope(narr)
    base = 10 ** (gain_db / 20.0)
    duck = 10 ** (duck_db / 20.0)
    # full gain in silence, `duck` under the loudest speech, smooth between
    gain = base * (1.0 - (1.0 - duck) * env)
    # the bed's own level varies; normalise so gain_db means "below full scale"
    bed_peak = float(np.abs(placed).max()) if placed.size else 0.0
    if bed_peak > 0:
        placed = placed / bed_peak
    out = mix + placed * gain[:, None]
    peak = float(np.abs(out).max()) if out.size else 0.0
    if peak > PEAK_GUARD:
        out *= PEAK_GUARD / peak
    voiced = env > 0.2
    report = {
        "gain_db": gain_db, "duck_db": duck_db, "peak": round(peak, 3),
        "bed_seconds": round(len(bed) / SR, 2),
        "mean_gain_db_under_voice": round(float(20 * np.log10(gain[voiced].mean())), 1)
        if voiced.any() else None,
    }
    return out.astype(np.float32), report
