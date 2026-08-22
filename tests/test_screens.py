"""Render every screen layout, for real, before any of them can ship.

Written after four failures that all had the same shape: a change to the
deterministic renderer looked right, passed the unit tests, and only broke when
a job reached the render stage.

  * `DATA` emitted as JSON, so a boolean came out `true` -- NameError on import
  * the template read `DATA["screens"]` while `build_source` still wrote
    `archetypes` -- KeyError on import
  * the frame-0 lead applied to the eyebrow but not the slots -- a blank opener
  * `sub: tagline` passed the key name through as literal text

Every one is caught by importing the generated module and looking at the pixels.
None is caught by inspecting the source. So this renders each layout against
thin, ordinary and rich content: thin proves a layout degrades instead of
drawing an empty box, rich proves nothing overflows, and importing at all proves
the emitted module and the data it carries agree.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.content import ReelContent
from app.render import screens as screens_mod
from app.render.fallback_storyboard import build_source, scene_spans

FIXTURES = Path(__file__).parent / "fixtures"

#: A frame with almost nothing lit is the failure the smoke check calls
#: "sparse", and it never raises on its own.
MIN_INK = 0.008

#: Entrances pre-roll into their cut (see PRE_ROLL), so a frame just after a cut
#: is already part-way in rather than blank. The pipeline's own smoke check
#: fails a job over bare frames here, so the test holds the same line: only the
#: first instant of the very first screen is exempt.
ENTRANCE_SECONDS = 0.04


def _require_fonts() -> None:
    """The bundled faces are fetched at build time, not vendored -- they carry
    their own licences. Without them nothing renders, which is a setup step
    missing rather than a regression."""
    from app.render.fonts import available, font_dir

    if not available():
        pytest.skip(f"bundled faces missing from {font_dir()}; "
                    "run docker/fetch-fonts.sh")


def _content_shapes(base: ReelContent) -> dict[str, ReelContent]:
    """The same reel with the fact bundle a real repo might actually have."""
    rich = base.model_copy(deep=True)

    thin = base.model_copy(deep=True)
    thin.fact_sheet = thin.fact_sheet[:1]
    thin.cover.stats = thin.cover.stats[:1]
    thin.cover.hook = thin.cover.hook[:1]
    thin.cover.prompt = False

    ordinary = base.model_copy(deep=True)
    ordinary.fact_sheet = ordinary.fact_sheet[:4]

    return {"thin": thin, "ordinary": ordinary, "rich": rich}


def _segments(count: int, total: float) -> list[tuple[float, float]]:
    step = total / max(count, 1)
    return [(i * step + 0.05, (i + 1) * step - 0.05) for i in range(count)]


def _data_of(source: str) -> dict:
    """Read DATA out of the emitted module without executing its imports."""
    import ast

    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "DATA":
            return ast.literal_eval(node.value)
    raise AssertionError("the generated module has no DATA assignment")


@pytest.fixture(scope="module")
def sample() -> ReelContent:
    path = FIXTURES / "harness-content.json"
    if not path.exists():
        pytest.skip("no content fixture")
    return ReelContent.model_validate(json.loads(path.read_text()))


def test_every_catalogue_layout_declares_slots_it_can_draw():
    """A layout naming a slot kind the renderer does not implement fails at the
    only moment it is ever used, which is inside a job."""
    from app.render.fallback_storyboard import TEMPLATE

    # read the implemented kinds off the renderer rather than listing them
    # here, so adding a slot cannot leave this test quietly out of date
    import re

    known = set(re.findall(r'"(\w+)": sl_\w+', TEMPLATE))
    assert known, "the SLOTS table could not be read from the template"
    catalogue = screens_mod.catalogue()
    assert catalogue, "the default catalogue is empty"

    for layout in catalogue:
        assert layout.slots, f"{layout.id} draws nothing"
        for slot in layout.slots:
            assert slot.kind in known, f"{layout.id} names unknown slot {slot.kind!r}"
            assert f'"{slot.kind}": sl_' in TEMPLATE, \
                f"{slot.kind} is in the catalogue but not in the SLOTS table"
        assert layout.role in ("opener", "body", "closer")

    roles = {layout.role for layout in catalogue}
    assert {"opener", "closer"} <= roles

    # at least one body layout must need nothing, or thin content falls back to
    # repeating the opener -- which is the defect this catalogue replaced
    assert any(not layout.needs and layout.role == "body" for layout in catalogue)


@pytest.mark.parametrize("shape", ["thin", "ordinary", "rich"])
def test_generated_module_imports_and_draws(sample, shape, tmp_path):
    """The whole point: emit, import, render, look at the pixels.

    An emitted module is only correct if the data it carries and the code that
    reads it agree, and the only way to know that is to run it.
    """
    pytest.importorskip("PIL")
    _require_fonts()

    content = _content_shapes(sample)[shape]
    total = 34.0
    segments = _segments(len(content.phrases), total)
    source = build_source(content, total=total, audio_rel="x.mp3",
                          phrases_rel="phrases/x.txt", segments=segments)

    data = _data_of(source)
    assert data["screens"], "no screens were resolved"

    spans = scene_spans(segments, [p.scene_index for p in content.phrases], total, 3.2)
    assert len(data["screens"]) == len(spans)
    assert data["screens"][0]["start"] == 0.0
    assert data["screens"][-1]["end"] == pytest.approx(total)
    assert data["screens"][-1]["is_end"]

    # contiguous, in order, and nothing left on screen after its own scene
    for previous, following in zip(data["screens"], data["screens"][1:]):
        assert previous["end"] == following["start"]

    for screen in data["screens"]:
        for slot in screen["slots"]:
            # every slot carries resolved values, never a key name to look up
            assert "source" not in slot, f"{screen['id']}/{slot['kind']} unresolved"
            if slot["kind"] == "headline":
                assert slot["lines"] and all(line.strip() for line in slot["lines"])


def test_thin_content_degrades_instead_of_drawing_empty_boxes(sample):
    """A repo with one stat and no install command must not get a terminal
    screen with nothing in it, or a stat trio with two blanks."""
    thin = _content_shapes(sample)["thin"]
    bundle = {"hook_lines": ["only one"], "point_lines": ["a point"],
              "stats": [["38K", "STARS"]], "facts": [["LICENCE", "MIT"]],
              "commands": [], "tagline": thin.tagline}

    chosen = screens_mod.pick(6, bundle)
    assert len(chosen) == 6
    ids = [layout.id for layout, _ in chosen]
    assert ids[0] != ids[-1], "the opener was reused as the closer"
    assert "terminal" not in ids, "a terminal screen was picked with no commands"
    assert "stat-trio" not in ids, "a three-card screen was picked with one stat"

    # a layout that must repeat gets a new variant, so the content differs
    repeats = [(layout.id, variant) for layout, variant in chosen]
    assert len(set(repeats)) == len(repeats), f"identical screen twice: {repeats}"


def test_rich_content_uses_a_different_layout_for_every_scene(sample):
    """The defect this replaced: four archetypes cycled, so scene five was
    scene one again -- the harness reel showed the same headline at 2s and 25s."""
    bundle = {"hook_lines": ["a", "b"], "point_lines": ["x", "y"],
              "stats": [["38K", "STARS"], ["3.4K", "FORKS"], ["GO", "LANG"]],
              "facts": [[f"L{i}", f"V{i}"] for i in range(8)],
              "commands": ["docker run -d"], "tagline": "a tagline",
              "quote": "one memorable line"}

    ids = [layout.id for layout, _ in screens_mod.pick(7, bundle)]
    assert len(set(ids)) == len(ids), f"a layout repeated with content to spare: {ids}"


@pytest.mark.parametrize("shape", ["thin", "ordinary", "rich"])
def test_the_emitted_module_actually_renders(sample, shape, tmp_path):
    """Import it and look at the pixels. Nothing else catches these.

    A JSON `true`, a key the template reads and the builder never writes, an
    entrance delay that leaves frame 0 blank -- all four regressions this file
    exists for are import-time or pixel-level, and invisible to source
    inspection. Every screen is sampled at its start, just after its start (the
    boundary that DEVELOPMENT.md warns about) and at its midpoint.
    """
    pytest.importorskip("PIL")
    _require_fonts()
    from app.render.workspace import build_workspace
    from app.stages.storyboard import run_smoke

    content = _content_shapes(sample)[shape]
    # NAME in the emitted module is content.slug, and Timing resolves the
    # timing file from it -- so the workspace has to be keyed the same way
    slug, total = content.slug, 34.0
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

    source = build_source(content, total=total, audio_rel=f"{slug}.mp3",
                          phrases_rel=f"phrases/{slug}.txt", segments=segments)
    (workspace / "storyboards" / f"{slug}.py").write_text(source)

    result = run_smoke(workspace, slug, tmp_path / "frames",
                       expected_duration=total)
    assert result.get("ok"), (
        f"{shape} content did not render: {result.get('error') or result.get('problems')}"
    )

    frames = result.get("frames") or []
    assert frames, "the smoke run produced no frames"
    starts = [screen["start"] for screen in _data_of(source)["screens"]]
    settled = [f for f in frames
               if all(not (start <= f["t"] < start + ENTRANCE_SECONDS)
                      for start in starts)]
    bare = [f["t"] for f in settled if f.get("ink", 0) < MIN_INK]
    assert not bare, f"{shape}: frames with almost nothing drawn at t={bare}"
    outside = {f["t"]: f["outside_safe"] for f in frames if f.get("outside_safe")}
    assert not outside, f"{shape}: content outside the safe area at {outside}"


def test_a_missing_alignment_never_produces_zero_length_scenes():
    """The deterministic branch of the pipeline called build_source without the
    timing, so every group ended at the same instant and every span after the
    first was 0.00s -- six screens nobody would ever see.

    The caller is fixed, but the arithmetic should not be able to emit that
    table at all: an even split is wrong about where the cuts belong and right
    about there being cuts, which is the better failure.
    """
    total = 38.83
    phrase_scene = [0, 1, 2, 3, 4, 5]

    spans = scene_spans([(0.0, total)], phrase_scene, total, 3.2)
    assert len(spans) >= 2
    assert all(end - start >= 1.2 for start, end in spans), spans
    assert spans[0][0] == 0.0
    assert spans[-1][1] == pytest.approx(total)
    for previous, following in zip(spans, spans[1:]):
        assert previous[1] == following[0]


def test_every_pipeline_path_passes_the_alignment_and_the_caption_flag():
    """Two branches write the deterministic storyboard -- the chosen template
    and the codegen fallback -- and only one of them was passing the timing.
    Both take the same keywords, so neither can quietly drop one.
    """
    import inspect

    from app.stages import pipeline
    from app.stages.storyboard import write_fallback

    signature = inspect.signature(write_fallback)
    assert {"captions", "timing_json"} <= set(signature.parameters)

    for module in (pipeline, __import__("app.stages.storyboard", fromlist=["x"])):
        source = inspect.getsource(module)
        for call in _calls_of("write_fallback", source):
            assert "captions=" in call, f"a write_fallback call drops captions: {call}"
            assert "timing_json=" in call, f"a write_fallback call drops timing: {call}"


def _calls_of(name: str, source: str) -> list[str]:
    """Every call to `name` in the source, excluding its definition."""
    calls, index = [], 0
    while (index := source.find(f"{name}(", index)) != -1:
        if source[max(0, index - 4):index] == "def ":
            index += 1
            continue
        depth, cursor = 0, index + len(name)
        while cursor < len(source):
            depth += source[cursor] == "("
            depth -= source[cursor] == ")"
            cursor += 1
            if depth == 0:
                break
        calls.append(source[index:cursor])
        index = cursor
    return calls


def test_text_that_fits_is_left_exactly_as_written():
    """A trim that runs when nothing needs trimming is a silent edit.

    Backing off to a word boundary unconditionally turned the end card's
    "docker run -d" into "docker run" -- still a command, no longer the right
    one. Anything the renderer puts on screen has to be what the content said,
    unless it genuinely does not fit.
    """
    fit_mono = _helper_from_template("_fit_mono")

    assert fit_mono("docker run -d", 34, 912) == "docker run -d"
    assert fit_mono("npx create-thing@latest", 34, 912) == "npx create-thing@latest"

    long = "an extremely long tagline that will not fit inside the space given"
    trimmed = fit_mono(long, 34, 912)
    assert len(trimmed) < len(long)
    assert long.startswith(trimmed)
    assert trimmed.split()[-1] in long.split()          # no mid-word cut


def _helper_from_template(name: str):
    """Pull one helper out of the emitted template and make it callable.

    These live in the generated module, not in the builder, so this is the only
    way to exercise the code that actually runs -- reimplementing it in the test
    would only prove the copy works.
    """
    import textwrap

    from app.render.fallback_storyboard import TEMPLATE

    source = TEMPLATE.replace("{{", "{").replace("}}", "}")
    start = source.index(f"def {name}(")
    lines = source[start:].splitlines(keepends=True)
    body = [lines[0]]
    for line in lines[1:]:
        if line.strip() and not line[:1].isspace():
            break                    # back to column 0: the function ended
        body.append(line)
    end = start + len("".join(body))
    namespace = {
        # 20px a character against a 912px budget: about 45 characters fit
        "tw": lambda text, _font, track=0: len(text) * 20,
        "m": lambda *a, **k: None,
    }
    exec(textwrap.dedent(source[start:end]), namespace)  # noqa: S102
    return namespace[name]


def test_an_unreachable_model_falls_through_to_the_deterministic_renderer(tmp_path):
    """A dead endpoint says nothing about the job.

    The vLLM box went down mid-run and took the storyboard stage with it, even
    though `fallback_to_template` was on and a renderer that cannot fail was
    sitting right there. Provider errors have to count as failed attempts, not
    as stage failures.
    """
    import inspect

    from app.stages import storyboard

    source = inspect.getsource(storyboard.generate_storyboard)
    call = source[source.index("llm.complete("):]
    assert "try:" in source[:source.index("llm.complete(")][-400:], \
        "llm.complete is not inside a try block"
    assert '"stage": "provider"' in source, \
        "a provider error is not recorded as an attempt"
    # and the loop continues rather than raising
    assert "continue" in call[:call.index("strip_fence")]


def test_a_short_narration_stretches_the_end_card_instead_of_failing():
    """One job rendered 773 frames over 90 seconds to be told its reel was
    25.77s against a 30s floor, and the answer was "rewrite the script".

    But the end card carries no narration -- it is a wordmark, a URL and a save
    prompt -- so a script a few seconds short does not need rewriting, it needs
    a longer card. The stage only fails when even the longest card cannot
    reach the floor.
    """
    import inspect

    from app.stages import pipeline
    from app.stages.content import MAX_TAIL_SECONDS, TAIL_SECONDS, reel_total

    # a few seconds short: the card holds the difference
    assert reel_total(32.78, 36.0) == pytest.approx(36.0)
    assert reel_total(35.0, 36.0) == pytest.approx(36.0 + 0.4, abs=0.5)

    # comfortably long enough: the card stays at its minimum beat
    assert reel_total(40.0, 36.0) == pytest.approx(40.0 + TAIL_SECONDS)

    # far too short: the card stops at its limit rather than becoming dead air
    assert reel_total(20.0, 36.0) == pytest.approx(20.0 + MAX_TAIL_SECONDS)

    audio = inspect.getsource(pipeline.run_audio)
    assert "reel_total" in audio, "the audio stage does not stretch the tail"
    assert "StageFailed" in audio, "it no longer fails when nothing can help"
    assert "holding the end card" in audio, "the stretch is not reported"


def test_a_reel_with_no_screenshots_is_unchanged(sample):
    """The whole point of gating the layout on `needs`: adding this feature must
    not alter a single job that does not use it."""
    from app.render.fallback_storyboard import build_source

    kwargs = dict(total=34.0, audio_rel="a.mp3", phrases_rel="phrases/a.txt",
                  segments=_segments(len(sample.phrases), 34.0))
    assert build_source(sample, **kwargs) == build_source(sample, images=[], **kwargs)

    ids = [layout.id for layout, _ in screens_mod.pick(7, {
        "hook_lines": ["a", "b"], "point_lines": ["x", "y"], "facts": [("l", "v")] * 6,
        "stats": [("38K", "S")] * 3, "commands": ["x"], "tagline": "t", "images": []})]
    assert "screenshot" not in ids


def test_each_screenshot_gets_its_own_screen_and_its_own_heading(sample):
    """Three uploads should be three screens, not the same screen three times,
    and a repository page must not be captioned "WHAT IT PRINTS"."""
    from app.render.fallback_storyboard import build_source

    images = [
        {"file": "a.png", "fit": "panel", "role": "repo", "eyebrow": "THE REPO",
         "caption": "", "width": 896, "height": 504},
        {"file": "b.png", "fit": "full", "role": "output",
         "eyebrow": "WHAT IT PRINTS", "caption": "", "width": 1080, "height": 1920},
    ]
    source = build_source(sample, total=40.0, audio_rel="a.mp3",
                          phrases_rel="phrases/a.txt", images=images,
                          segments=_segments(len(sample.phrases), 40.0))
    screens = [s for s in _data_of(source)["screens"] if s["id"] == "screenshot"]
    assert len(screens) == 2, "the second upload never got a screen"
    assert [s["eyebrow"] for s in screens] == ["THE REPO", "WHAT IT PRINTS"]
    assert [s["slots"][0]["file"] for s in screens] == ["a.png", "b.png"]
    assert [s["slots"][0]["fit"] for s in screens] == ["panel", "full"]

    # repeats are interleaved, never adjacent
    ids = [s["id"] for s in _data_of(source)["screens"]]
    assert not any(a == b == "screenshot" for a, b in zip(ids, ids[1:]))


def test_a_panel_fills_the_width_and_fits_the_frame():
    """A rendered reel showed a screenshot running off the top of the frame with
    the eyebrow printed across it.

    Two causes: panels were inset to the safe width, so a wide screenshot was
    smaller than it needed to be; and the height was whatever the aspect gave,
    so a 1600x4200 README capture became 896x2352 -- taller than the whole
    1920 frame.
    """
    from app.images import (FRAME_W, PANEL_MAX_H, PANEL_W, Crop, default_crop,
                            prepare)

    assert PANEL_W == FRAME_W, "a panel no longer spans the frame"

    from PIL import Image

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for width, height in ((1600, 4200), (1920, 1080), (1400, 3000), (900, 900)):
            source = tmp / f"{width}x{height}.png"
            Image.new("RGB", (width, height), (250, 250, 250)).save(source)
            crop = default_crop(width, height, "panel")
            out_w, out_h = prepare(source, tmp / "out.png", fit="panel", crop=crop)
            assert out_w == FRAME_W, f"{width}x{height} did not fill the width"
            assert out_h <= PANEL_MAX_H, f"{width}x{height} came out {out_h} tall"

        # an explicit crop is honoured, and still fills the width
        source = tmp / "1600x4200.png"
        out_w, out_h = prepare(source, tmp / "out.png", fit="panel",
                               crop=Crop(x=0.0, y=0.1, w=1.0, h=0.15))
        assert out_w == FRAME_W and out_h <= PANEL_MAX_H


def test_a_panel_sits_where_it_was_asked_to_and_never_over_the_eyebrow():
    """The default is the bottom because the eyebrow lives at the top, and a
    panel placed there covers it -- which is what the rendered reel did."""
    from app.render.fallback_storyboard import PANEL_BOTTOM, PANEL_TOP, _panel_y

    for height in (608, 400, 900):
        placements = {p: _panel_y(height, p) for p in ("top", "centre", "bottom")}
        assert placements["top"] == PANEL_TOP
        assert placements["bottom"] + height == PANEL_BOTTOM
        assert placements["top"] <= placements["centre"] <= placements["bottom"]
        # never above the eyebrow band, never into the burned-in captions
        for y in placements.values():
            assert y >= PANEL_TOP and y + height <= PANEL_BOTTOM

    # a panel too tall to move is pinned rather than pushed out of the band
    tall = PANEL_BOTTOM - PANEL_TOP + 200
    assert _panel_y(tall, "bottom") == PANEL_TOP


def test_a_bottom_placed_panel_never_sits_under_the_captions():
    """`PANEL_BOTTOM` was 1470 and the burned-in captions start at 1450, so
    *every* bottom-placed screenshot overlapped them by 20px.

    The live preview built to warn about collisions reported this on the very
    first screenshot anyone placed in it -- the tool found a defect in the
    renderer it was built to preview, which is the argument for building it.

    A maximum-height panel was the case position could not fix: at 1120px tall
    it did not fit the band above the captions wherever it was put, so the cap
    came down to match the band.
    """
    from app.images import PANEL_MAX_H, PANEL_MIN_H
    from app.render.fallback_storyboard import (CAPTION_TOP, PANEL_TOP, _panel_y,
                                                panel_floor)

    assert panel_floor(True) < CAPTION_TOP, "the panel band reaches into the captions"
    assert PANEL_MAX_H <= panel_floor(True) - PANEL_TOP, (
        "the tallest panel does not fit the band above the captions"
    )

    for height in (PANEL_MIN_H, 608, 900, PANEL_MAX_H):
        for position in ("top", "centre", "bottom"):
            y = _panel_y(height, position, True)
            assert y >= PANEL_TOP, f"{height}px at {position} rides over the eyebrow"
            assert y + height <= CAPTION_TOP, (
                f"{height}px at {position} ends at {y + height}, "
                f"under the captions at {CAPTION_TOP}"
            )

    # with captions off there is nothing to collide with, so a screenshot gets
    # the extra room rather than being held to a limit that no longer applies
    assert panel_floor(False) > panel_floor(True)
    assert _panel_y(608, "bottom", False) > _panel_y(608, "bottom", True)
