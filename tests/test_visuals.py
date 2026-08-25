"""Generated visuals: ComfyUI workflows, the planner, the stage, the render.

The render tests matter most. A clip is a new slot kind in three emitted
modules, and the lesson of test_screens.py applies: nothing short of importing
the module and looking at the pixels catches a key the template reads and the
builder never writes.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.content import ReelContent

FIXTURES = Path(__file__).parent / "fixtures"
WORKFLOWS = Path(__file__).parent.parent / "app" / "workflows"


@pytest.fixture(scope="module")
def sample() -> ReelContent:
    path = FIXTURES / "harness-content.json"
    if not path.exists():
        pytest.skip("no content fixture")
    return ReelContent.model_validate(json.loads(path.read_text()))


# ------------------------------------------------------------- workflows ---
def test_both_shipped_workflows_are_api_format_and_fully_detected():
    from app.providers.visuals import workflow as wf

    image = wf.load(WORKFLOWS / "image_qwen_image_2512.json")
    video = wf.load(WORKFLOWS / "video_ltx2_5_t2v.json")
    found = wf.detect(image, "image")
    assert {"prompt", "negative", "seed", "size", "save", "lightning"} <= set(found)
    found = wf.detect(video, "video")
    assert {"prompt", "negative", "seed", "seconds", "fps", "enhancer", "save"} <= set(found)


def test_patching_rewrites_only_the_inputs_it_is_asked_to():
    from app.providers.visuals import workflow as wf

    image = wf.load(WORKFLOWS / "image_qwen_image_2512.json")
    out = wf.patch_image(image, None, prompt="a lighthouse", negative=None, width=1152,
                         height=1536, seed=42, lightning=True, prefix="reelforge/t")
    assert out["238:227"]["inputs"]["text"] == "a lighthouse"
    assert out["238:232"]["inputs"]["width"] == 1152
    assert out["238:230"]["inputs"]["seed"] == 42
    assert out["238:229"]["inputs"]["value"] is True
    assert out["60"]["inputs"]["filename_prefix"] == "reelforge/t"
    # the source is untouched: the loader caches nothing, but a caller may
    assert image["238:227"]["inputs"]["text"] != "a lighthouse"
    # the negative prompt is the workflow author's choice unless overridden
    assert out["238:228"]["inputs"]["text"] == image["238:228"]["inputs"]["text"]


def test_the_ltx_prompt_is_found_behind_the_enhancer_switch():
    """The positive text reaches the sampler through a ComfySwitchNode whose
    true branch is a Gemma rewrite of the false branch. Both read the same
    PrimitiveStringMultiline, and that is the node to set."""
    from app.providers.visuals import workflow as wf

    video = wf.load(WORKFLOWS / "video_ltx2_5_t2v.json")
    out = wf.patch_video(video, None, prompt="slow dolly over a server room", negative=None,
                         seconds=4, fps=24, seed=9, enhancer=False, prefix="reelforge/c")
    assert out["405:376"]["inputs"]["value"] == "slow dolly over a server room"
    assert out["405:362"]["inputs"]["value"] == 4
    assert out["405:383"]["inputs"]["value"] is False
    # both noise sources, not just the first one found
    assert out["405:338"]["inputs"]["noise_seed"] == 9
    assert out["405:339"]["inputs"]["noise_seed"] == 9
    assert wf.workflow_fps(video, None) == 24


def test_a_ui_format_export_is_refused_with_a_useful_message(tmp_path):
    from app.providers.visuals import workflow as wf

    path = tmp_path / "ui.json"
    path.write_text(json.dumps({"nodes": [], "links": []}))
    with pytest.raises(wf.WorkflowError, match="Export \\(API\\)"):
        wf.load(path)


# --------------------------------------------------------------- planner ---
def test_the_plan_skips_the_hook_and_the_close_and_prefers_b_roll_for_clips(sample):
    from app.stages import visuals as V

    content = sample.model_copy(deep=True)
    for scene in content.scenes:
        scene.b_roll = ""
    content.scenes[2].b_roll = "a slow push-in on copper wires meeting at a glowing junction"
    assets = V.plan(content, job_id="j1", stills=2, clips=1, style="s", still_fit="full")
    kinds = [(a.kind, a.scene_index) for a in assets]
    clip = next(a for a in assets if a.kind == "clip")
    assert clip.scene_index == content.scenes[2].index
    assert "push-in" in clip.prompt
    assert all(idx not in (content.scenes[0].index, content.scenes[-1].index)
               for _, idx in kinds)
    # the fixture has four scenes, so two body scenes: the clip takes one and
    # a single still fits the other -- never the same scene twice
    body = len(content.scenes) - 2
    assert sum(k == "still" for k, _ in kinds) == min(2, body - 1)
    # stills and the clip never share a scene
    assert len({idx for _, idx in kinds}) == len(kinds)


def test_seeds_are_stable_for_a_prompt_and_change_with_it():
    from app.stages.visuals import seed_for

    assert seed_for("j", "still", 1, "p") == seed_for("j", "still", 1, "p")
    assert seed_for("j", "still", 1, "p") != seed_for("j", "still", 1, "q")
    assert seed_for("j", "still", 1, "p") != seed_for("j", "clip", 1, "p")


def test_typography_directions_are_stripped_from_prompts():
    from app.stages.visuals import clean_direction

    text = ("Code editor showing raw urllib code. A red line strikes through the manual "
            "encoding logic. The word 'requests' types itself in below in indigo.")
    assert clean_direction(text) == "", "a direction about code and labels must not survive"
    assert clean_direction("Slow dolly along copper wires that meet at a glowing junction") \
        == "Slow dolly along copper wires that meet at a glowing junction"
    assert clean_direction("Split screen. Left side shows requests.get(url)") == ""


# ----------------------------------------------------------------- stage ---
def test_the_stage_with_the_fake_adapter_produces_stills_clips_and_a_manifest(sample, tmp_path, monkeypatch):
    pytest.importorskip("PIL")
    monkeypatch.setenv("REELFORGE_PATHS__DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("REELFORGE_VISUALS__ACTIVE", "fake")
    monkeypatch.setenv("REELFORGE_VISUALS__PROFILES__FAKE__ADAPTER", "fake")
    monkeypatch.setenv("REELFORGE_VISUALS__CLIPS", "1")
    monkeypatch.setenv("REELFORGE_VISUALS__STILLS", "2")
    monkeypatch.setenv("REELFORGE_VISUALS__CLIP_SECONDS", "2")
    import app.config as config

    config.get_config.cache_clear()
    from app.models.job import Job, JobSource, Stage
    from app.stages.pipeline import run_visuals, stage_clips, stage_images
    from app.store import JobStore

    store = JobStore(tmp_path / "data" / "jobs")
    job = Job(id="20260101-000000-test-abc", slug=sample.slug,
              source=JobSource(kind="github", url=sample.repo_url))
    store.save(job)
    paths = store.paths(job)
    paths.content_json.parent.mkdir(parents=True, exist_ok=True)
    paths.content_json.write_text(sample.model_dump_json(), encoding="utf-8")

    # four scenes in the fixture: two body scenes, the clip takes one
    result = run_visuals(job, store, None)
    assert result["meta"]["stills"] == 1 and result["meta"]["clips"] == 1
    manifest = json.loads(paths.visuals_json.read_text())
    assert manifest["provider"] == "fake"
    assert all(a["ok"] for a in manifest["assets"])
    assert (paths.prepared_images / "gen-still-1.png").exists()
    assert len(list((paths.visuals_dir / "clip-1").glob("*.jpg"))) == 60

    paths.workspace.mkdir(parents=True, exist_ok=True)
    stills = stage_images(job, paths)
    clips = stage_clips(job, paths)
    assert [s["file"] for s in stills] == ["gen-still-1.png"]
    assert stills[0]["role"] == "generated"
    assert clips[0]["dir"] == "clip-1" and clips[0]["frames"] == 60
    assert (paths.workspace / "images" / "clip-1" / "00001.jpg").exists()

    # a second run with nothing changed regenerates nothing
    from app.providers.visuals import fake as fake_mod

    calls = []
    original = fake_mod.FakeProvider.still

    def counting(self, *a, **k):
        calls.append(1)
        return original(self, *a, **k)

    monkeypatch.setattr(fake_mod.FakeProvider, "still", counting)
    run_visuals(job, store, None)
    assert not calls, "an unchanged still was generated again"
    config.get_config.cache_clear()


def test_visuals_off_is_a_no_op_that_finishes_instantly(sample, tmp_path, monkeypatch):
    monkeypatch.setenv("REELFORGE_PATHS__DATA_DIR", str(tmp_path / "data"))
    import app.config as config

    config.get_config.cache_clear()
    from app.models.job import Job, JobSource
    from app.stages.pipeline import run_visuals, visuals_settings
    from app.store import JobStore

    store = JobStore(tmp_path / "data" / "jobs")
    job = Job(id="20260101-000000-off-abc", slug=sample.slug,
              source=JobSource(kind="github", url=sample.repo_url))
    store.save(job)
    assert visuals_settings(job)["enabled"] is False
    result = run_visuals(job, store, None)
    assert result["meta"] == {"enabled": False, "stills": 0, "clips": 0}
    config.get_config.cache_clear()


# ---------------------------------------------------------------- render ---
def _workspace_for(tmp_path, content, total):
    from app.render.workspace import build_workspace
    from tests.test_screens import _segments

    slug = content.slug
    segments = _segments(len(content.phrases), total)
    workspace = build_workspace(tmp_path / "video")
    (workspace / "build").mkdir(parents=True, exist_ok=True)
    (workspace / "storyboards").mkdir(parents=True, exist_ok=True)
    (workspace / "build" / f"{slug}.timing.json").write_text(json.dumps({
        "duration": total,
        "segments": [list(s) for s in segments],
        "phrases": [p.text for p in content.phrases],
        "words": [
            {"w": word, "s": round(start + i * 0.2, 3), "e": round(start + i * 0.2 + 0.18, 3)}
            for (start, _end), phrase in zip(segments, content.phrases)
            for i, word in enumerate(phrase.text.split())
        ],
    }))
    return workspace, segments


@pytest.mark.parametrize("family", ["bloom", "slab", "ledger"])
def test_a_clip_and_a_generated_still_render_in_every_family(sample, family, tmp_path):
    pytest.importorskip("PIL")
    from tests.test_screens import _data_of, _require_fonts

    _require_fonts()
    from app.providers.visuals.fake import FakeProvider
    from app.render.fallback_storyboard import build_source
    from app.stages.storyboard import run_smoke

    total = 34.0
    workspace, segments = _workspace_for(tmp_path, sample, total)
    images_dir = workspace / "images"
    fake = FakeProvider({})
    fake.still("x", images_dir / "gen-still-1.png", width=1080, height=1920, seed=1)
    clip = fake.clip("y", images_dir / "clip-1", seconds=2.0, fps=30, width=1080, height=1920, seed=2)

    images = [{"file": "gen-still-1.png", "fit": "full", "role": "generated", "position": "centre",
               "eyebrow": "THE MECHANISM", "caption": "", "width": 1080, "height": 1920}]
    clips = [{"dir": "clip-1", "fps": 30, "frames": clip.frames, "seconds": 2.0,
              "label": "IN MOTION"}]
    source = build_source(sample, total=total, audio_rel=f"{sample.slug}.mp3",
                          phrases_rel=f"phrases/{sample.slug}.txt", segments=segments,
                          images=images, clips=clips, family=family)
    (workspace / "storyboards" / f"{sample.slug}.py").write_text(source, encoding="utf-8")

    screens = _data_of(source)["screens"]
    kinds = [slot["kind"] for s in screens for slot in s["slots"]]
    assert "clip" in kinds, f"{family}: no screen picked the clip"
    assert "image" in kinds, f"{family}: no screen picked the still"
    clip_slot = next(slot for s in screens for slot in s["slots"] if slot["kind"] == "clip")
    assert clip_slot["dir"] == "clip-1" and clip_slot["frames"] == clip.frames

    result = run_smoke(workspace, sample.slug, tmp_path / "frames", expected_duration=total)
    if not result.get("ok"):
        # The slab family already trips the safe-area check with this
        # fixture's light palette, clip or no clip. What this test owns is
        # that the clip adds no failure of its own: same rungs as the
        # baseline render, and never a crash.
        baseline_src = build_source(sample, total=total, audio_rel=f"{sample.slug}.mp3",
                                    phrases_rel=f"phrases/{sample.slug}.txt",
                                    segments=segments, family=family)
        (workspace / "storyboards" / f"{sample.slug}.py").write_text(baseline_src)
        baseline = run_smoke(workspace, sample.slug, tmp_path / "frames-base",
                             expected_duration=total)
        rungs = {p["rung"] for p in result.get("problems", [])}
        base_rungs = {p["rung"] for p in baseline.get("problems", [])}
        assert "crash" not in rungs, result.get("problems")
        assert rungs <= base_rungs, (
            f"{family}: the clip introduced {rungs - base_rungs}: {result.get('problems')}"
        )


def test_a_reel_without_visuals_builds_the_same_source_as_before(sample):
    from app.render.fallback_storyboard import build_source
    from tests.test_screens import _segments

    kwargs = dict(total=34.0, audio_rel="a.mp3", phrases_rel="phrases/a.txt",
                  segments=_segments(len(sample.phrases), 34.0))
    assert build_source(sample, **kwargs) == build_source(sample, clips=[], **kwargs)


def test_the_art_director_feeds_prompts_and_headings_and_falls_back_cleanly(sample):
    from app.providers.llm.fake import FakeProvider
    from app.stages import visuals as V

    body = V.body_scenes(sample)
    scenes = [{"scene_index": s.index,
               "still": "a brass key on dark slate under one hard beam of light",
               "clip": "slow push-in on a brass key turning in a lock, teal glow inside",
               "heading": "One Clean Call"} for s in body]
    llm = FakeProvider({"by_schema": {"ArtDirection": {"scenes": scenes}}})
    directions = V.art_direct(sample, [s.index for s in body], llm)
    assert set(directions) == {s.index for s in body}
    assets = V.plan(sample, job_id="j", stills=2, clips=1, style="S", still_fit="full",
                    directions=directions)
    for a in assets:
        assert a.heading == "One Clean Call"
        assert "brass key" in a.prompt and sample.display_name not in a.prompt
    # the storyboard dicts carry the heading for the renderer to paint
    assert all(not V._TEXTY.search(a.prompt.split(". Vertical")[0].split(". Slow")[0]) for a in assets)

    broken = FakeProvider({"responder": lambda s, u: (_ for _ in ()).throw(RuntimeError("down"))})
    assert V.art_direct(sample, [s.index for s in body], broken) == {}
    fallback = V.plan(sample, job_id="j", stills=1, clips=0, style="S", still_fit="full")
    assert fallback and fallback[0].heading == fallback[0].scene_title


def test_the_text_negative_is_appended_to_the_workflows_own():
    from app.providers.visuals import workflow as wf
    from app.stages.visuals import TEXT_NEGATIVE

    image = wf.load(WORKFLOWS / "image_qwen_image_2512.json")
    theirs = image["238:228"]["inputs"]["text"]
    out = wf.patch_image(image, None, prompt="x", negative=TEXT_NEGATIVE, width=64, height=64,
                         seed=1, lightning=None, prefix="p")
    assert out["238:228"]["inputs"]["text"].startswith(theirs.rstrip(","))
    assert out["238:228"]["inputs"]["text"].endswith(TEXT_NEGATIVE)
    video = wf.load(WORKFLOWS / "video_ltx2_5_t2v.json")
    out = wf.patch_video(video, None, prompt="x", negative=TEXT_NEGATIVE, seconds=3, fps=24,
                         seed=1, enhancer=None, prefix="p")
    assert "cartoon" in out["405:373"]["inputs"]["text"] and "letters" in out["405:373"]["inputs"]["text"]


def test_a_long_narration_makes_a_long_reel_instead_of_failing(sample, tmp_path, monkeypatch):
    """The 36-44s window is guidance, not a gate: a 51s narration renders as a
    ~52s reel. Only the platforms' own 30-90s bounds fail the stage early."""
    monkeypatch.setenv("REELFORGE_PATHS__DATA_DIR", str(tmp_path / "data"))
    import shutil
    import subprocess

    import app.config as config

    config.get_config.cache_clear()
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not on PATH")
    from app.models.job import Job, JobSource, Stage
    from app.stages.pipeline import StageFailed, run_audio
    from app.store import JobStore

    store = JobStore(tmp_path / "data" / "jobs")
    job = Job(id="20260101-000000-lng-abc", slug=sample.slug,
              source=JobSource(kind="github", url=sample.repo_url))
    store.save(job)
    paths = store.paths(job)
    paths.content_json.parent.mkdir(parents=True, exist_ok=True)
    paths.content_json.write_text(sample.model_dump_json(), encoding="utf-8")

    def narration(seconds):
        subprocess.run([shutil.which("ffmpeg"), "-y", "-v", "error", "-f", "lavfi",
                        "-i", f"sine=frequency=200:duration={seconds}",
                        "-ac", "1", str(paths.audio_mp3)], check=True)

    narration(51.5)
    result = run_audio(job, store, None)
    assert 51 < result["meta"]["reel_seconds"] < 54, "the reel should follow the narration"
    assert "tempo" not in result["meta"], "the narration must not be altered"

    narration(95.0)
    with pytest.raises(StageFailed, match="platforms accept"):
        run_audio(job, store, None)
    config.get_config.cache_clear()


def test_a_long_url_never_crosses_the_end_cards_right_edge(sample, tmp_path):
    """The minimax-music3 failure: L.endcard draws the URL at m(38) from
    x 232 with no fitting, and a Hugging Face URL walked through x 996."""
    pytest.importorskip("PIL")
    from tests.test_screens import _require_fonts

    _require_fonts()
    from app.render.fallback_storyboard import build_source
    from app.stages.storyboard import run_smoke

    content = sample.model_copy(deep=True)
    content.repo_url = "https://huggingface.co/MiniMaxAI/MiniMax-Music3-Extended-Preview"
    for family in ("ledger", "slab", "bloom"):
        total = 20.0
        workspace, segments = _workspace_for(tmp_path / family, content, total)
        source = build_source(content, total=total, audio_rel=f"{content.slug}.mp3",
                              phrases_rel=f"phrases/{content.slug}.txt", segments=segments,
                              family=family)
        (workspace / "storyboards" / f"{content.slug}.py").write_text(source, encoding="utf-8")
        result = run_smoke(workspace, content.slug, tmp_path / family / "frames",
                           expected_duration=total)
        rungs = {p["rung"] for p in result.get("problems", [])}
        assert "crash" not in rungs, (family, result.get("problems"))
        def side_trips(report):
            return {(round(f["t"], 1), band) for f in report.get("frames", [])
                    if f["t"] > total - 4
                    for band in (f.get("outside_safe") or []) if band in ("left", "right")}

        # Slab's light palette trips the luminance bands everywhere with this
        # fixture (a pre-existing condition) -- so the assertion is relative:
        # the long URL must add no side trip the short URL did not already have.
        base_src = build_source(sample, total=total, audio_rel=f"{sample.slug}.mp3",
                                phrases_rel=f"phrases/{sample.slug}.txt", segments=segments,
                                family=family)
        (workspace / "storyboards" / f"{sample.slug}.py").write_text(base_src, encoding="utf-8")
        baseline = run_smoke(workspace, sample.slug, tmp_path / family / "frames-base",
                             expected_duration=total)
        extra = side_trips(result) - side_trips(baseline)
        assert not extra, (family, sorted(extra))
