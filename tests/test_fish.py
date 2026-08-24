"""The Fish-Speech voice adapter, with its Gradio client replaced by a fake."""
from __future__ import annotations

import shutil
import wave
from pathlib import Path

import numpy as np
import pytest


def _wav(path: Path, seconds: float = 1.0, freq: float = 220.0) -> Path:
    sr = 44100
    t = np.arange(int(seconds * sr)) / sr
    data = (np.sin(2 * np.pi * freq * t) * 0.3 * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())
    return path


class FakeGradio:
    """Records every predict() and answers with a wav whose pitch encodes the
    reference it was given, so the test can tell the calls apart."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.calls: list[dict] = []

    def predict(self, **kwargs):
        self.calls.append(kwargs)
        ref = kwargs.get("reference_audio")
        freq = 440.0 if ref else 220.0
        return (str(_wav(self.tmp / f"out-{len(self.calls)}.wav", 0.5, freq)), None)


@pytest.fixture
def fish(tmp_path, monkeypatch):
    monkeypatch.setenv("REELFORGE_PATHS__DATA_DIR", str(tmp_path / "data"))
    import app.config as config

    config.get_config.cache_clear()
    from app.providers.tts import fish as fish_mod

    fake = FakeGradio(tmp_path / "gradio")
    monkeypatch.setattr(fish_mod.FishSpeechProvider, "client", lambda self: fake)
    monkeypatch.setattr(fish_mod, "handle_file", lambda p: {"path": p}, raising=False)
    import sys
    import types

    # handle_file is imported inside _predict; give it something to import
    stub = types.ModuleType("gradio_client")
    stub.handle_file = lambda p: {"path": p}
    stub.Client = object
    monkeypatch.setitem(sys.modules, "gradio_client", stub)
    yield fake, fish_mod
    config.get_config.cache_clear()


def test_without_a_reference_the_voice_is_fixed_by_one_calibration_call(fish, tmp_path):
    fake, fish_mod = fish
    provider = fish_mod.FishSpeechProvider({"base_url": "http://fish.test:7860", "seed": 3})

    first = provider.speak("Requests is a Python library.")
    second = provider.speak("It wraps HTTP verbs in readable method calls.")

    assert len(fake.calls) == 3, "calibration once, then one call per phrase"
    assert fake.calls[0]["text"] == fish_mod.CALIBRATION and fake.calls[0]["reference_audio"] is None
    for call in fake.calls[1:]:
        assert call["reference_audio"] is not None, "phrases must carry the reference"
        assert call["reference_text"] == fish_mod.CALIBRATION
        assert call["seed"] == 3
    assert first[:4] == b"RIFF" and second[:4] == b"RIFF"

    # the calibration clip is kept, so a second provider (next job) reuses it
    kept = list((tmp_path / "data" / "tts" / "fish").glob("reference-3-*.wav"))
    assert len(kept) == 1
    again = fish_mod.FishSpeechProvider({"base_url": "http://fish.test:7860", "seed": 3})
    again.speak("Sessions keep a cookie jar.")
    assert len(fake.calls) == 4 and fake.calls[-1]["reference_audio"] is not None


def test_a_configured_reference_is_used_as_is(fish, tmp_path):
    fake, fish_mod = fish
    ref = _wav(tmp_path / "voice.wav", 2.0)
    provider = fish_mod.FishSpeechProvider({"base_url": "http://fish.test:7860",
                                            "reference_audio": str(ref),
                                            "reference_text": "hello there"})
    provider.speak("one line")
    assert len(fake.calls) == 1
    assert fake.calls[0]["reference_audio"] == {"path": str(ref)}
    assert fake.calls[0]["reference_text"] == "hello there"
    assert provider.voice == "voice"


def test_a_server_error_message_is_surfaced(fish):
    fake, fish_mod = fish
    fake.predict = lambda **kw: (None, "CUDA out of memory")
    provider = fish_mod.FishSpeechProvider({"base_url": "http://fish.test:7860", "reference_id": "narrator"})
    with pytest.raises(fish_mod.TTSError, match="CUDA out of memory"):
        provider.speak("x")


def test_the_profile_is_buildable_and_its_voice_field_is_the_reference_id(tmp_path, monkeypatch):
    monkeypatch.setenv("REELFORGE_PATHS__DATA_DIR", str(tmp_path / "data"))
    import app.config as config

    config.get_config.cache_clear()
    from app.providers.tts import build_tts, voice_field

    engine = build_tts(config.get_config(), {"provider": "fish", "voice": "narrator"})
    assert engine.name == "fish" and engine.reference_id == "narrator"
    assert voice_field("fish") == "reference_id"
    config.get_config.cache_clear()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not on PATH")
def test_retime_shortens_narration_by_the_factor(tmp_path):
    from app.render.encode import retime

    src = _wav(tmp_path / "n.wav", 4.0)
    new = retime(src, 1.25)
    assert abs(new - 3.2) < 0.1


def test_a_sample_voice_can_be_uploaded_played_and_removed(tmp_path, monkeypatch):
    monkeypatch.setenv("REELFORGE_PATHS__DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("REELFORGE_EXECUTOR", "inline")
    import app.config as config
    import app.runner as runner

    config.get_config.cache_clear()
    runner.mode.cache_clear()
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    client.put("/api/settings/tts/profiles/narrator",
               json={"adapter": "fish", "settings": {"base_url": "http://fish.test:7860"}})
    sample = _wav(tmp_path / "me.wav", 2.0)

    # the wrong kind of profile takes no sample
    bad = client.post("/api/settings/tts/profiles/upload/reference",
                      files={"file": ("me.wav", sample.read_bytes(), "audio/wav")})
    assert bad.status_code == 422

    with sample.open("rb") as handle:
        up = client.post("/api/settings/tts/profiles/narrator/reference",
                         files={"file": ("me.wav", handle, "audio/wav")},
                         data={"transcript": "hello there"})
    assert up.status_code == 200, up.text
    stored = [p for p in up.json()["tts"]["profiles"] if p["name"] == "narrator"][0]["settings"]
    assert stored["reference_audio"].endswith("narrator.wav") and stored["reference_text"] == "hello there"
    assert (tmp_path / "data" / "tts" / "references" / "narrator.wav").exists()

    play = client.get("/api/settings/tts/profiles/narrator/reference")
    assert play.status_code == 200 and play.content[:4] == b"RIFF"

    # the adapter built from the profile points at the stored file
    from app.providers.tts import build_tts

    engine = build_tts(config.get_config(), {"provider": "narrator"})
    assert engine.reference_audio == stored["reference_audio"]

    gone = client.delete("/api/settings/tts/profiles/narrator/reference")
    assert gone.status_code == 200
    assert not (tmp_path / "data" / "tts" / "references" / "narrator.wav").exists()
    assert client.get("/api/settings/tts/profiles/narrator/reference").status_code == 404
    config.get_config.cache_clear()


def test_saving_the_profile_form_never_clears_an_uploaded_sample(tmp_path, monkeypatch):
    """The bug as it happened: upload a sample, then press Save on the editor
    that was opened before the upload. Its blank field must not win."""
    monkeypatch.setenv("REELFORGE_PATHS__DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("REELFORGE_EXECUTOR", "inline")
    import app.config as config
    import app.runner as runner

    config.get_config.cache_clear()
    runner.mode.cache_clear()
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    client.put("/api/settings/tts/profiles/narrator",
               json={"adapter": "fish", "settings": {"base_url": "http://fish.test:7860"}})
    sample = _wav(tmp_path / "me.wav", 1.0)
    with sample.open("rb") as handle:
        client.post("/api/settings/tts/profiles/narrator/reference",
                    files={"file": ("me.wav", handle, "audio/wav")})
    saved = client.put("/api/settings/tts/profiles/narrator",
                       json={"adapter": "fish", "settings": {"base_url": "http://fish.test:7860",
                                                             "reference_audio": "", "seed": 4}})
    stored = [p for p in saved.json()["tts"]["profiles"] if p["name"] == "narrator"][0]["settings"]
    assert stored["reference_audio"].endswith("narrator.wav"), "a blank form value cleared the sample"
    assert stored["seed"] == 4
    assert client.get("/api/settings/tts/profiles/narrator/reference").status_code == 200
    config.get_config.cache_clear()
