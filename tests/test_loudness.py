"""Landing inside the loudness window, for any recording.

A reel failed `verify` at -1.0 dBTP against a -1.5 requirement, with its
integrated loudness perfectly on target. Single-pass `loudnorm` estimates the
input while it runs, and its true-peak control is an estimate on top of that --
so it hit the loudness and missed the ceiling.

That file is one both platforms turn down. These are the rules that stop it.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.render import encode

FIXTURES = Path(__file__).parent / "fixtures"


def test_the_reference_path_is_left_alone():
    """`single_pass_cmd` exists to be byte-for-byte make.sh, so a chunked
    result can be checked against a known-good one. Improving the audio chain
    must not touch it, or it stops being a reference."""
    assert encode.LOUDNORM == "loudnorm=I=-14:TP=-1.5:LRA=11"
    reference = encode.single_pass_cmd("ffmpeg", Path("a.mp3"), Path("o.mp4"),
                                       1080, 1920, 30)
    joined = " ".join(reference)
    assert encode.LOUDNORM in joined
    assert "alimiter" not in joined, "the reference path grew a filter make.sh lacks"


def test_the_filter_measures_first_and_limits_last():
    """Two passes for the loudness, a real limiter for the ceiling.

    loudnorm cannot guarantee a true peak; a limiter can. And nothing linear
    can put a 21.7 dB crest at both -14 LUFS and -1.5 dBTP -- one narration
    measured -22.7 integrated with peaks at -0.95 -- so something has to reduce
    the crest deliberately.
    """
    measured = {"input_i": "-22.69", "input_tp": "-0.95", "input_lra": "2.40",
                "input_thresh": "-33.05", "target_offset": "1.26"}
    chain = encode.loudnorm_filter(measured)

    assert "measured_I=-22.69" in chain and "measured_TP=-0.95" in chain
    assert "linear=false" in chain
    assert chain.index("loudnorm") < chain.index("alimiter"), "limiter runs first"
    assert f"limit={encode.LIMITER_CEILING}dB" in chain
    assert chain.endswith("aresample=48000")

    # the ceiling sits below the target, for AAC's peak reconstruction
    assert encode.LIMITER_CEILING < encode.TARGET_TP

    # with nothing measured it still produces a usable chain
    assert "alimiter" in encode.loudnorm_filter({})
    assert "measured_I" not in encode.loudnorm_filter({})


def test_the_loop_corrects_by_the_error_it_measured(monkeypatch, tmp_path):
    """The limiter costs loudness, how much depends on the recording's crest,
    and AAC adds peak back. A fixed filter cannot know where it will land, so
    the only correct approach is to look at the result."""
    out = tmp_path / "out.mp4"
    targets: list[float] = []

    def fake_run(cmd):
        out.write_bytes(b"x")
        chain = cmd[cmd.index("-filter_complex") + 1]
        targets.append(float(chain.split("loudnorm=I=")[1].split(":")[0]))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(encode, "measure_loudness", lambda *a: {})
    # first pass lands 0.8 LU quiet, the corrected pass lands on target
    results = iter([(-14.8, -4.8), (-14.1, -4.7)])
    monkeypatch.setattr(encode, "measure_output", lambda *a: next(results))

    report = encode.mux_normalised("ffmpeg", tmp_path / "v.mp4",
                                   tmp_path / "a.mp3", out, run=fake_run)

    assert report["ok"]
    assert len(report["passes"]) == 2
    assert targets[0] == pytest.approx(encode.TARGET_I)
    # aimed as far the other way as it missed
    assert targets[1] == pytest.approx(encode.TARGET_I + 0.8, abs=0.05)


def test_a_first_pass_already_inside_the_window_does_not_run_again(monkeypatch, tmp_path):
    out = tmp_path / "out.mp4"

    def fake_run(cmd):
        out.write_bytes(b"x")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(encode, "measure_loudness", lambda *a: {})
    monkeypatch.setattr(encode, "measure_output", lambda *a: (-14.2, -2.1))

    report = encode.mux_normalised("ffmpeg", tmp_path / "v.mp4",
                                   tmp_path / "a.mp3", out, run=fake_run)
    assert report["ok"] and len(report["passes"]) == 1


def test_a_correct_loudness_with_a_hot_peak_is_not_accepted(monkeypatch, tmp_path):
    """Exactly the failure this file exists for: -14.3 LUFS is on target, and
    -1.0 dBTP still fails."""
    out = tmp_path / "out.mp4"

    def fake_run(cmd):
        out.write_bytes(b"x")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(encode, "measure_loudness", lambda *a: {})
    monkeypatch.setattr(encode, "measure_output", lambda *a: (-14.3, -1.0))

    report = encode.mux_normalised("ffmpeg", tmp_path / "v.mp4",
                                   tmp_path / "a.mp3", out, run=fake_run,
                                   attempts=2)
    assert not report["ok"], "a hot peak passed because the loudness was right"


def test_the_measurement_reaches_the_job_record():
    """The correction ran and the file was correct, but the report was dropped
    between the renderer and the job -- so the progress line announcing it
    could never fire, and a file that only just cleared the window looked the
    same as one with room to spare."""
    import inspect
    from dataclasses import fields

    from app.render.chunked import RenderResult
    from app.stages import pipeline

    assert "loudness" in {f.name for f in fields(RenderResult)}
    render_source = inspect.getsource(pipeline.run_render)
    assert '"loudness": result.loudness' in render_source
    assert "dBTP after" in render_source, "the measurement is never reported"
