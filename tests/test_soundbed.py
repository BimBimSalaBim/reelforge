"""Generated audio: the music bed, the one-shot library, and the mix.

Stable Audio makes music and sound effects, not speech, so nothing here
touches narration -- the assertions are that the voice comes through the
mixer untouched and the bed sits underneath it.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from app.render import soundbed as B

WORKFLOWS = Path(__file__).parent.parent / "app" / "workflows"
FIXTURES = Path(__file__).parent / "fixtures"
SR = B.SR


def _db(x: np.ndarray) -> float:
    return float(20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9))


def _voice(seconds: float, *, on: float = 3.0, period: float = 5.0, level: float = 0.08) -> np.ndarray:
    """Bursts of noise with silence between, the shape of phrases and pauses."""
    t = np.arange(int(seconds * SR)) / SR
    mono = (np.random.RandomState(1).normal(0, level, len(t)) * ((t % period) < on)).astype(np.float32)
    return np.stack([mono, mono], 1)


# ------------------------------------------------------------- workflows ---
def test_both_audio_workflows_are_detected_and_patched():
    from app.providers.visuals import workflow as wf

    sa3 = wf.load(WORKFLOWS / "audio_stable_audio_3_medium_base.json")
    found = wf.detect(sa3, "audio")
    assert {"prompt", "seed", "seconds", "category", "enhancer", "save"} <= set(found)
    out = wf.patch_audio(sa3, None, prompt="soft pad", negative=None, seconds=60, seed=4,
                         category="One-shot", enhancer=True, prefix="reelforge/a")
    assert out["52:31"]["inputs"]["value"] == "soft pad"          # behind the reprompt switch
    assert out["52:36"]["inputs"]["value"] == 60
    assert out["52:43"]["inputs"]["choice"] == "One-shot" and out["52:43"]["inputs"]["index"] == 3
    assert out["52:3"]["inputs"]["seed"] == 4
    assert out["19"]["inputs"]["filename_prefix"] == "reelforge/a"

    open_ = wf.load(WORKFLOWS / "audio_stable_audio_open.json")
    found = wf.detect(open_, "audio")
    assert found["prompt"] == "6" and found["seconds"] == "11" and found["save"] == "19"
    out = wf.patch_audio(open_, None, prompt="rain", negative=None, seconds=12.5, seed=1,
                         category="Music", enhancer=None, prefix="x")
    assert out["11"]["inputs"]["seconds"] == 12.5 and out["6"]["inputs"]["text"] == "rain"


# --------------------------------------------------------------- mixing ---
def test_the_bed_sits_under_the_voice_and_rises_in_the_gaps():
    narr = _voice(40)
    t = np.arange(20 * SR) / SR
    bed = np.stack([np.sin(2 * np.pi * 220 * t) * 0.8] * 2, 1).astype(np.float32)   # shorter: tiles
    out, report = B.mix_bed(narr.copy(), narr, bed, gain_db=-22, duck_db=-9, total_seconds=40)
    bed_only = out - narr

    assert np.allclose(out - bed_only, narr, atol=1e-6), "the narration was altered"
    under = _db(bed_only[int(1.0 * SR):int(2.5 * SR)])
    gap = _db(bed_only[int(3.9 * SR):int(4.9 * SR)])
    voice = _db(narr[int(1.0 * SR):int(2.5 * SR)])
    assert under < voice - 10, f"bed at {under:.1f} dB is not clearly under a {voice:.1f} dB voice"
    assert gap > under + 5, f"bed did not come up in the pause ({gap:.1f} vs {under:.1f})"
    assert float(np.abs(bed_only[-SR // 10:]).max()) < 0.01, "no fade-out under the end card"
    assert report["bed_seconds"] == 20.0 and report["peak"] <= B.PEAK_GUARD + 1e-6


def test_a_tiled_bed_has_no_seam_click():
    t = np.arange(3 * SR) / SR
    bed = np.stack([np.sin(2 * np.pi * 110 * t) * 0.5] * 2, 1).astype(np.float32)
    placed = B.place_bed(bed, 10.0)
    assert len(placed) == 10 * SR
    # the largest sample-to-sample jump must be what a 110 Hz sine can do, not a discontinuity
    jump = float(np.abs(np.diff(placed[:, 0])).max())
    assert jump < 0.02, f"seam jump {jump:.3f}"


def test_samples_keep_amp_semantics_and_honour_dur():
    t = np.arange(int(1.5 * SR)) / SR
    raw = np.concatenate([np.zeros(int(0.2 * SR)), np.sin(2 * np.pi * 60 * t) * np.exp(-t / 0.3) * 0.3])
    prepared = B.prepare_sample(np.stack([raw, raw], 1).astype(np.float32))
    assert abs(float(np.abs(prepared).max()) - 1.0) < 1e-5, "not peak-normalised"
    assert int(np.flatnonzero(np.abs(prepared) > 0.02)[0]) < int(0.01 * SR), "leading silence kept"
    gen = B.sample_generator(prepared)
    short = gen(dur=0.05, freq=58.0)
    assert len(short) == int(0.05 * SR) and abs(float(short[-1])) < 1e-3
    assert len(gen()) == len(prepared)


# ----------------------------------------------------------------- stage ---
@pytest.fixture
def sample():
    from app.models.content import ReelContent

    path = FIXTURES / "harness-content.json"
    if not path.exists():
        pytest.skip("no content fixture")
    return ReelContent.model_validate(json.loads(path.read_text()))


def test_the_stage_makes_a_bed_and_the_one_shot_library_with_the_fake(sample, tmp_path, monkeypatch):
    monkeypatch.setenv("REELFORGE_PATHS__DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("REELFORGE_VISUALS__ACTIVE", "fake")
    monkeypatch.setenv("REELFORGE_VISUALS__PROFILES__FAKE__ADAPTER", "fake")
    monkeypatch.setenv("REELFORGE_VISUALS__STILLS", "0")
    monkeypatch.setenv("REELFORGE_VISUALS__CLIPS", "0")
    monkeypatch.setenv("REELFORGE_VISUALS__MUSIC", "true")
    monkeypatch.setenv("REELFORGE_VISUALS__SFX_SAMPLES", "true")
    import app.config as config

    config.get_config.cache_clear()
    from app.models.job import Job, JobSource
    from app.stages import visuals as V
    from app.stages.pipeline import render_audio, run_visuals, sfx_library_dir
    from app.store import JobStore

    store = JobStore(tmp_path / "data" / "jobs")
    job = Job(id="20260101-000000-snd-abc", slug=sample.slug,
              source=JobSource(kind="github", url=sample.repo_url), template="warm-amber")
    store.save(job)
    paths = store.paths(job)
    paths.content_json.parent.mkdir(parents=True, exist_ok=True)
    paths.content_json.write_text(sample.model_dump_json(), encoding="utf-8")

    result = run_visuals(job, store, None)
    assert result["meta"]["music"] is True and result["meta"]["sfx_samples"] is True
    manifest = json.loads(paths.visuals_json.read_text())
    bed = next(a for a in manifest["assets"] if a["kind"] == "music")
    assert bed["ok"] and "lo-fi hip hop" in bed["prompt"] and "no vocals" in bed["prompt"]
    assert (paths.root / bed["file"]).exists() and abs(bed["seconds"] - V.MUSIC_SECONDS) < 0.1

    library = sfx_library_dir("fake")
    assert sorted(p.stem for p in library.glob("*.wav")) == sorted(V.SFX_KINDS)

    audio = render_audio(job, paths)
    assert audio["music"] == paths.root / bed["file"]
    assert audio["sfx_dir"] == library and audio["music_gain_db"] == -22.0
    config.get_config.cache_clear()


def test_music_off_leaves_the_render_audio_empty(sample, tmp_path, monkeypatch):
    monkeypatch.setenv("REELFORGE_PATHS__DATA_DIR", str(tmp_path / "data"))
    import app.config as config

    config.get_config.cache_clear()
    from app.models.job import Job, JobSource
    from app.stages.pipeline import render_audio
    from app.store import JobStore

    store = JobStore(tmp_path / "data" / "jobs")
    job = Job(id="20260101-000000-off-abc", slug=sample.slug,
              source=JobSource(kind="github", url=sample.repo_url))
    store.save(job)
    assert render_audio(job, store.paths(job)) == {}
    config.get_config.cache_clear()


# ------------------------------------------------------------------ shim ---
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not on PATH")
def test_the_sfx_shim_swaps_samples_in_and_mixes_the_bed(sample, tmp_path):
    """The real path: a storyboard module in a workspace, run_sfx with the
    extras, and the mix that comes out."""
    from tests.test_screens import _require_fonts

    _require_fonts()
    from app.providers.visuals.fake import FakeProvider
    from app.render.chunked import LAST_MIX_REPORT, run_sfx
    from app.render.fallback_storyboard import build_source
    from tests.test_visuals import _workspace_for

    total = 20.0
    workspace, segments = _workspace_for(tmp_path, sample, total)
    # narration: bursts with pauses, written where the storyboard's AUDIO points
    narr = _voice(total - 2.0, level=0.12)
    B.write_wav(workspace / f"{sample.slug}.mp3", narr)   # sfx.py decodes via ffmpeg; wav content is fine
    source = build_source(sample, total=total, audio_rel=f"video/{sample.slug}.mp3",
                          phrases_rel=f"phrases/{sample.slug}.txt", segments=segments)
    (workspace / "storyboards" / f"{sample.slug}.py").write_text(source, encoding="utf-8")

    fake = FakeProvider({})
    library = tmp_path / "sfx"
    for kind in ("thump", "swish", "tick", "sweep"):
        fake.audio(kind, library / f"{kind}.wav", seconds=1.0, seed=3, category="One-shot")
    bed = tmp_path / "bed.wav"
    fake.audio("pad", bed, seconds=30.0, seed=4, category="Music")

    plain = run_sfx(workspace, sample.slug)
    plain_mix = B.read_wav(plain).copy()
    assert "music" not in LAST_MIX_REPORT and "sfx_samples" not in LAST_MIX_REPORT

    # the bed alone: same events, same narration, plus music
    with_bed = B.read_wav(run_sfx(workspace, sample.slug, audio={
        "music": bed, "music_gain_db": -22.0, "music_duck_db": -9.0}))
    assert "error" not in LAST_MIX_REPORT["music"]
    assert len(with_bed) == len(plain_mix)
    bed_only = with_bed - plain_mix
    under = _db(bed_only[int(1.0 * SR):int(2.5 * SR)])     # the voice is on 0-3 s
    gap = _db(bed_only[int(3.9 * SR):int(4.9 * SR)])       # and off 3-5 s
    assert gap > under + 4, f"bed did not duck: {under:.1f} dB under voice, {gap:.1f} dB in the gap"
    assert under < _db(plain_mix[int(1.0 * SR):int(2.5 * SR)]) - 8

    # the samples: the report names what was swapped in, and the mix still builds
    with_samples = B.read_wav(run_sfx(workspace, sample.slug, audio={"sfx_dir": library}))
    assert set(LAST_MIX_REPORT["sfx_samples"]) == {"thump", "swish", "tick", "sweep"}
    assert len(with_samples) == len(plain_mix)
    assert not np.array_equal(with_samples, plain_mix), "the samples were not used"
