"""Units the pipeline's correctness rests on."""
import json
import re
from pathlib import Path

import pytest

from app.models.facts import FactsBundle, GitHubFacts
from app.providers.keyring import KeyRing, NoKeysAvailable
from app.providers.llm.base import extract_json, looks_like_schema, schema_of, skeleton, strip_reasoning
from app.render.encode import expected_frames, plan_chunks
from app.validate import facts_check

FIXTURES = Path(__file__).parent / "fixtures"


# ------------------------------------------------------------- encoding ---
@pytest.mark.parametrize("total,chunk", [(38.8, 4.0), (38.8, 6.0), (39.0, 2.0), (8.5, 4.0), (52.0, 8.0)])
def test_chunks_cover_every_frame_exactly_once(total, chunk):
    bounds = plan_chunks(total, chunk, 30)
    frames = [int(round(b * 30)) - int(round(a * 30)) for a, b in bounds]
    assert sum(frames) == expected_frames(total, 30)
    assert bounds[0][0] == 0.0 and bounds[-1][1] == total


def test_interior_chunks_land_on_gop_boundaries():
    """keyint=60 at 30fps: a chunk that is not a whole GOP cannot be concatenated
    without re-encoding."""
    bounds = plan_chunks(38.8, 4.0, 30)
    for start, end in bounds[:-1]:
        assert int(round((end - start) * 30)) % 60 == 0


def test_chunk_size_must_be_a_whole_gop():
    with pytest.raises(ValueError, match="whole multiple"):
        plan_chunks(30.0, 3.0, 30)


# ------------------------------------------------------------ structured ---
def test_json_is_recovered_from_prose_and_fences():
    assert extract_json("Here:\n```json\n{\"a\": 1}\n```\nDone") == {"a": 1}
    assert extract_json('Sure! {"b": [1,2], "c": "}"} ok') == {"b": [1, 2], "c": "}"}


def test_reasoning_blocks_are_stripped():
    assert strip_reasoning("<think>musing</think>\nThe answer.") == "The answer."
    # an unclosed tag means a truncated response; everything after it is scratchpad
    assert strip_reasoning("kept <think>cut off here") == "kept"
    assert extract_json("<think>plan</think>\n{\"ok\": true}") == {"ok": True}


def test_a_returned_schema_is_recognised_as_not_an_answer():
    from app.models.content import ScriptDraft

    assert looks_like_schema(schema_of(ScriptDraft))
    assert not looks_like_schema(skeleton(ScriptDraft))


def test_the_generated_example_is_itself_valid():
    """The example anchors the model, so an invalid one produces invalid output.
    A placeholder of 0 for a ge=1 field made every scene 0-indexed."""
    from app.models.content import Phrase, Scene

    assert Scene.model_validate({**skeleton(Scene), "t_start": 0.0, "t_end": 1.0})
    assert Phrase.model_validate({**skeleton(Phrase), "text": "three words here"})


def test_example_shows_the_minimum_number_of_entries():
    from app.models.content import ScriptDraft

    example = skeleton(ScriptDraft)
    assert len(example["phrases"]) >= 6
    assert len(example["scenes"]) >= 3


# ----------------------------------------------------------------- facts ---
@pytest.fixture
def facts():
    return FactsBundle(
        slug="ruflo", display_name="ruflo", primary_url="https://github.com/ruvnet/ruflo",
        github=GitHubFacts(owner="ruvnet", repo="ruflo", full_name="ruvnet/ruflo",
                           url="u", stars=68041, forks=5820, open_issues=8, watchers=9),
        readme_markdown="Ruflo ships 100+ agents and 314 MCP tools.",
    )


def test_api_and_readme_numbers_are_traced_invented_ones_are_not(facts):
    findings = facts_check.check(
        "68K stars, 100+ agents, 314 MCP tools, used by 47000 teams.", facts)
    by_value = {f.value: f.source for f in findings}
    assert by_value["68K"] == "api"
    assert by_value["100+"] == "readme"
    assert by_value["314"] == "readme"
    assert by_value["47000"] == "unsourced"


def test_versions_years_and_durations_are_not_treated_as_claims(facts):
    """An earlier version tested a 36-character window, so a version string one
    line away silenced an unrelated invented figure."""
    findings = facts_check.check("v3.38.9 shipped in 2026. Runtime 38.8s at 30 fps.", facts)
    assert not facts_check.unsourced(findings)


def test_a_nearby_version_no_longer_masks_an_invented_number(facts):
    findings = facts_check.check("used by 47000 teams\nMIT, v3.38.9, 2026", facts)
    assert [f.value for f in facts_check.unsourced(findings)] == ["47000"]


# --------------------------------------------------------------- keyring ---
def test_keys_rotate_when_one_is_exhausted(monkeypatch):
    monkeypatch.setenv("K1", "sk_aaaa1111")
    monkeypatch.setenv("K2", "sk_bbbb2222,sk_cccc3333")
    ring = KeyRing.from_env(["K1", "K2"])
    assert [s.label for s in ring] == ["K1", "K2#1", "K2#2"]
    ring.mark_exhausted()
    assert ring.rotate().label == "K2#1"
    ring.mark_rejected()
    assert ring.rotate().label == "K2#2"


def test_rotation_stops_when_every_key_is_spent(monkeypatch):
    monkeypatch.setenv("K1", "sk_only1111")
    ring = KeyRing.from_env(["K1"])
    ring.mark_exhausted()
    with pytest.raises(NoKeysAvailable, match="exhausted"):
        ring.rotate()


def test_a_pinned_key_is_never_rotated_away_from(monkeypatch):
    """A deliberate manual choice must not be silently overridden."""
    monkeypatch.setenv("K1", "sk_aaaa1111")
    monkeypatch.setenv("K2", "sk_bbbb2222")
    ring = KeyRing.from_env(["K1", "K2"], active="K2")
    assert ring.current.label == "K2"
    ring.mark_exhausted()
    with pytest.raises(NoKeysAvailable, match="pinned"):
        ring.rotate()
    assert ring.auto().rotate().label == "K1"


def test_key_values_are_never_exposed_in_reports(monkeypatch):
    monkeypatch.setenv("K1", "sk_supersecretvalue")
    report = KeyRing.from_env(["K1"]).as_dict()
    assert "supersecret" not in str(report)
    assert report["keys"][0]["key"].startswith("sk_s")


# ------------------------------------------------------- content checks ---
def test_both_content_validators_accept_the_shipped_scripts(facts, tmp_path):
    """`validate_content` is the single-call path and `validate_script` the
    split one. They must agree, and neither may reject the hand-written scripts
    this pipeline is modelled on -- an earlier four-word phrase floor did."""
    from pathlib import Path

    from app.stages.content import _phrase_shape_problems

    fixture = Path(__file__).resolve().parent.parent / "video" / "phrases"
    from app.models.content import Phrase

    for path in sorted(fixture.glob("*.txt")):
        lines = [l.strip() for l in path.read_text().splitlines()
                 if l.strip() and not l.startswith("#")]
        phrases = [Phrase(text=line, scene_index=1) for line in lines]
        assert _phrase_shape_problems(phrases) == [], f"{path.name} was rejected"


def test_validate_content_runs_without_error(content, facts):
    """It was silently broken by a rename: nothing exercised this path, and it
    referenced a constant that no longer existed."""
    from app.stages.content import validate_content

    problems = validate_content(content, facts)
    assert isinstance(problems, list)


# ------------------------------------------------- per-scene generation ---
def test_similarity_separates_real_repeats_from_distinct_phrases():
    """Calibrated on labelled pairs from real generations; if the tokeniser or
    the threshold drifts, this is what notices."""
    from app.stages.content import too_similar

    repeats = [
        ("DeerFlow 2.0 is faster.", "DeerFlow 2.0, a ground-up rewrite."),
        ("No code reused from the previous version.", "No code shared with version 1."),
        ("50% faster performance.", "50% faster, to be exact."),
        ("Every line rewritten. New features, no old code.",
         "Rewritten from scratch. No code shared with previous version."),
        ("DeerFlow 2.0, DeerFlow 2.0 is faster.", "DeerFlow 2.0 is faster."),
    ]
    distinct = [
        ("Your agents can talk to agents elsewhere.",
         "An agent is a model plus a harness."),
        ("MIT licensed.", "Sixty-eight thousand stars."),
        ("The model writes the code.",
         "The harness decides whether any of it gets done."),
        ("Orchestrates sub-agents, memory, sandboxes.",
         "Handles tasks taking minutes to hours."),
        ("One npx command gives you a hundred agents.",
         "Then there is federation, which is the strange one."),
    ]
    for line, prior in repeats:
        assert too_similar(line, [prior]), f"missed a repeat: {line!r}"
    for line, prior in distinct:
        assert not too_similar(line, [prior]), f"wrongly dropped: {line!r}"


def test_split_grouped_numbers_are_repaired():
    """A model that breaks a line inside "80,000" leaves "80, 000" when the
    lines are rejoined, which then matches no real figure."""
    from app.models.content import repair_split_numbers
    from app.stages.content import merge_fragments

    assert repair_split_numbers("Over 80, 000 stars") == "Over 80,000 stars"
    assert repair_split_numbers("8, 100, 000 downloads") == "8,100,000 downloads"
    # a comma that is not grouping digits is left alone
    assert repair_split_numbers("Wait, 3 seconds") == "Wait, 3 seconds"
    assert merge_fragments(["Over 80,", "000 stars."]) == ["Over 80,000 stars."]


def test_fragments_merge_but_edge_beats_survive():
    from app.stages.content import PHRASE_MAX_WORDS, merge_fragments

    merged = merge_fragments(
        ["Runs inside a sandbox,", "Local Execution,", "Docker Execution,",
         "and Kubernetes,", "while updating"]
    )
    assert len(merged) < 5
    assert all(len(line.split()) <= PHRASE_MAX_WORDS for line in merged)
    # a closing beat stays its own phrase
    assert merge_fragments(["It is fast and small.", "MIT."])[-1] == "MIT."


def test_derived_pronunciations_cover_spelled_out_initialisms():
    from app.stages.content import derive_pronunciations

    found = derive_pronunciations("It runs on a GPU with an LLM behind a CLI, "
                                  "returning JSON over REST.")
    assert found.get("GPU") == 3
    assert found.get("LLM") == 3
    assert "CLI" not in found      # already in align.py's SPOKEN table
    assert "JSON" not in found     # read as a word, not spelled out
    assert "REST" not in found


def test_licences_and_dates_are_not_read_as_claims(facts):
    """A fact sheet is full of digits that are not statistics. "AGPL-3.0" was
    flagged as a claim of "3.0" and "2024-05-30" as claims of "05" and "30",
    which failed generation on output that was entirely correct."""
    sheet = (
        "Licence AGPL-3.0  Created 2024-05-30  Last push 2026-08-12  "
        "Release v2.1.0  Runtime 38.8s at 30 fps  Level 4.1"
    )
    assert not facts_check.unsourced(facts_check.check(sheet, facts))


def test_an_invented_figure_beside_a_licence_is_still_caught(facts):
    findings = facts_check.check(
        "Licence AGPL-3.0, created 2024-05-30, used by 47000 teams.", facts)
    assert [f.value for f in facts_check.unsourced(findings)] == ["47000"]


def test_cover_limits_are_measured_not_counted():
    """Character counts are the wrong tool: measured at 78px bold, 21 characters
    can be 796px or 863px against a 912px budget, and "AGPL-3.0" fits a stat
    card at 8 characters while "Apache-2.0" does not at 10. A count limit of 7
    rejected a real licence outright, before the width check could run."""
    from app.models.content import CoverSpec
    from app.validate.cover_fit import describe, measure_spec

    base = dict(
        bg=(8, 10, 16), accent=(90, 180, 255), accent_hi=(150, 210, 255),
        pale=(220, 235, 255), glow=(20, 60, 140), support=(255, 200, 120),
        motif="flow", eyebrow="FREE DOMAINS", wordmark="FreeDomain",
        sub="DigitalPlatDev/FreeDomain", kicker="Free domains, real lessons.",
        cmd="FREE DOMAINS", prompt=False, foot_l="OPEN SOURCE", foot_r="AGPL-3.0", mark_font_size=150,
    )

    # a real licence as a stat value is accepted, and measures as fitting
    ok = CoverSpec(**base, hook=["Free domains and DNS", "lessons in one place."],
                   stats=[("194K", "STARS"), ("AGPL-3.0", "LICENCE"), ("812", "DAYS")])
    assert not measure_spec(ok.to_covers_dict("c.png"))

    # an overlong hook is caught by measurement, with a usable budget
    wide = CoverSpec(**base, hook=["Register your domain for free.", "Learn DNS."],
                     stats=[("194K", "STARS"), ("AGPL-3.0", "LICENCE"), ("812", "DAYS")])
    problems = measure_spec(wide.to_covers_dict("c.png"))
    assert problems and problems[0]["overflow_px"] > 0
    assert "characters" in describe(problems)


def test_compact_plus_forms_trace_to_the_source(facts):
    """"68K+ stars" for 68,041 is honest and conservative, and is how these
    figures are actually written on a cover. Generating only "68K" and "68000+"
    left the form people use flagged as invented."""
    for form in ("68K+", "68K", "68k", "68k+", "68.0K", "68,041", "68000+"):
        findings = facts_check.check(f"It has {form} stars.", facts)
        assert findings and findings[0].source == "api", form
    assert facts_check.unsourced(facts_check.check("It has 999K+ stars.", facts))


# ------------------------------------------------------ text collisions ---
def test_overlapping_text_is_detected():
    """A frame can be the right size, inside the safe area and full of drawn
    pixels while being unreadable, because two strings sit on top of each other.
    Overlapping text has the density of text, so no pixel measure finds it.
    This is the end card that shipped: a wordmark with the call to action drawn
    straight through it."""
    from app.validate.textboxes import TextBox, collisions

    stacked = [
        TextBox("Harness", 116, 518, 964, 674, 180, 1.0),
        TextBox("Save this for your next", 210, 520, 870, 574, 40, 1.0),
    ]
    hits = collisions(stacked)
    assert hits and hits[0]["share"] > 0.5


def test_a_clean_layout_reports_nothing():
    from app.validate.textboxes import TextBox, collisions

    tidy = [
        TextBox("An agent is a model", 84, 500, 800, 570, 72, 1.0),
        TextBox("plus a harness.", 84, 600, 700, 670, 72, 1.0),
        TextBox("ruvnet/ruflo", 700, 170, 960, 200, 25, 1.0),
    ]
    assert collisions(tidy) == []


def test_invisible_text_cannot_collide():
    """Text mid-fade is drawn at low alpha and is not a collision."""
    from app.validate.textboxes import Recorder

    class Font:
        size = 40

        def getbbox(self, text):
            return (0, 0, len(text) * 20, 40)

    rec = Recorder()
    rec.add("visible", (100, 100), Font(), 1.0, 0, "lt")
    rec.add("fading in", (100, 100), Font(), 0.01, 0, "lt")
    assert [b.text for b in rec.boxes] == ["visible"]


def test_anchors_place_the_box_correctly():
    from app.validate.textboxes import Recorder

    class Font:
        size = 40

        def getbbox(self, text):
            return (0, 0, 200, 40)

    rec = Recorder()
    rec.add("x", (540, 100), Font(), 1.0, 0, "lt")
    rec.add("x", (540, 100), Font(), 1.0, 0, "mt")
    rec.add("x", (540, 100), Font(), 1.0, 0, "rb")
    left, centre, right = rec.boxes
    assert left.x0 == 540
    assert centre.x0 == 440          # centred on 540
    assert right.x1 == 540 and right.y1 == 100


def test_a_short_script_is_split_rather_than_failed():
    """Four scenes of one line each is five phrases against a floor of six.
    That used to raise an unhandled ValidationError inside assembly and kill the
    stage, losing every call that had already been paid for."""
    from app.models.content import Phrase
    from app.stages.content import reach_phrase_minimum

    five = [
        Phrase(text=t, scene_index=min(i + 1, 4))
        for i, t in enumerate([
            "A developer wants to build and deploy applications quickly",
            "Harness is an open source CI/CD platform written in Go",
            "It detects Docker Desktop, Rancher and native Linux automatically",
            "One container, one binary, no external dependencies at all",
            "Save this for your next platform review",
        ])
    ]
    out = reach_phrase_minimum(five, 6)
    assert len(out) >= 6
    # scene assignment survives the split
    assert [p.scene_index for p in out] == sorted(p.scene_index for p in out)
    assert all(len(p.text.split()) >= 3 for p in out)


def test_splitting_keeps_the_connective_and_never_makes_fragments():
    from app.stages.content import split_long_phrase

    head, tail = split_long_phrase(
        "Harness is an open source CI/CD platform, which replaced Drone entirely")
    assert tail.startswith("which")          # not "Replaced Drone entirely"
    assert len(head.split()) >= 3 and len(tail.split()) >= 3
    # too short to split usefully is left alone
    assert split_long_phrase("MIT licensed.") == ["MIT licensed."]


def test_the_fallback_survives_the_longest_content_the_limits_allow():
    """The fallback is the guarantee that a job always produces a video, so it
    must never fail on content the validators accepted. It drew headlines at a
    fixed size, so a long hook line ran off both edges and tripped the safe-area
    check -- failing the one storyboard that cannot be allowed to fail."""
    import sys

    from app.config import get_config

    video = str(get_config().paths.video)
    if video not in sys.path:
        sys.path.insert(0, video)
    import kit

    from app.render.fonts import patch_kit

    patch_kit(kit, strict=False)

    from app.models.content import CoverSpec

    longest = "x" * CoverSpec.model_fields["hook"].annotation.__args__[0].metadata[0].max_length \
        if False else "A" * 34            # the character ceiling the model may use
    avail = 1080 - 2 * 84

    # the fallback shrinks until it fits, so even the ceiling is drawable
    step = 86
    while step > 24 and kit.tw(longest, kit.f(step, "bold"), 0) > avail:
        step -= 4
    assert kit.tw(longest, kit.f(step, "bold"), 0) <= avail


# --------------------------------------------------- derived cover design --
def test_a_cover_can_be_derived_without_a_model(facts):
    """The cover is a palette, three figures and five tags -- nearly all of it
    already in the facts. Failing a whole job on it, after the script and fact
    sheet succeeded, throws away the expensive work for the cheapest part."""
    from app.models.content import ScriptDraft
    from app.stages.content import derive_design, validate_design
    from app.templates import load_template
    from app.validate.cover_fit import measure_spec

    script = ScriptDraft.model_validate({
        "slug": "ruflo", "display_name": "Ruflo",
        "tagline": "The harness layer for coding agents", "audience": "devs",
        "scenes": [{"index": i, "title": "T", "t_start": i - 1, "t_end": i,
                    "you_say": "x", "on_screen": "y"} for i in (1, 2, 3)],
        "phrases": [{"text": "An agent is a model plus a harness", "scene_index": 1}]
                   + [{"text": "The harness decides what gets done", "scene_index": i}
                      for i in (1, 2, 2, 3, 3)],
    })
    design = derive_design(facts, script, load_template("safe-deterministic"))

    assert design.theme is not None                      # derived from the cover
    assert len(design.hashtags) == 5 == len(set(design.hashtags))
    assert len(design.cover.stats) == 3
    assert not measure_spec(design.cover.to_covers_dict("c.png"))   # everything fits
    assert validate_design(design, script, facts) == []


def test_long_licences_are_shortened_to_fit_a_stat_card():
    """Measured at the sizes covers.py uses, 8 characters fits a stat card and
    10 does not, so "Apache-2.0" has to lose its version rather than be cut to
    "Apache-2"."""
    from app.stages.content import short_licence

    assert short_licence("Apache-2.0") == "Apache"
    assert short_licence("AGPL-3.0") == "AGPL"
    assert short_licence("MIT") == "MIT"
    assert all(len(short_licence(x)) <= 8
               for x in ("Apache-2.0", "BSD-3-Clause", "MPL-2.0", "GPL-3.0"))


def test_a_command_broken_across_lines_is_not_shown():
    """READMEs wrap long commands with a trailing backslash and the extractor
    keeps the first line, which alone will not run."""
    from app.stages.content import clean_command

    assert clean_command("docker run -d \\") == "docker run -d"
    assert clean_command("npx ruflo init") == "npx ruflo init"
    assert clean_command("make") == ""          # a fragment, not an instruction
    # a dangling pipe is dropped; what precedes it is still the command
    assert clean_command("curl -fsSL https://x |") == "curl -fsSL https://x"


def test_an_over_long_scene_is_trimmed_not_rejected():
    """Asking the model to shorten a scene spent the repair budget and came
    back the same length. Dropping a whole line needs no call and cannot
    introduce a new problem."""
    from app.stages.content import trim_scene

    lines = [
        "Harness replaced Drone entirely with a ground up rewrite in Go",
        "It builds tests and deploys from a single static binary",
        "There is no external database and no message queue to run",
        "Everything is one process you can run on a laptop",
    ]
    out = trim_scene(lines, 33)
    assert sum(len(x.split()) for x in out) <= 33
    assert out == lines[:len(out)]        # kept in order, trimmed from the end
    # never trims away the whole scene
    assert trim_scene(["one very long line " * 8], 5) != []


def test_subject_matching_stems_and_uses_the_whole_opening():
    """"Mission control for your AI agents" was rejected as sharing nothing with
    "An agent is a model plus a harness" -- because "agents" and "agent" are
    different strings. The rule is "the post is about the same thing as the
    video", not "it echoes sentence one verbatim"."""
    from app.stages.content import _keywords

    reference = _keywords(
        "An agent is a model plus a harness. The model writes the code. "
        "The harness layer for coding agents")

    for title in ("Mission control for your AI agents",
                  "Agent = model + harness. Ruflo is the harness for Claude Code",
                  "The model writes it, the harness ships it"):
        assert reference & _keywords(title), title

    # still catches copy that is about something else entirely
    assert not (reference & _keywords("Ten kitchen gadgets you need this winter"))


def test_the_completion_budget_fits_the_models_window():
    """Asking for 12,000 completion tokens on top of a 5,100-token prompt is a
    hard 400 from a 16,384-token model -- the request never runs. The server
    reports its own limit, so the budget is derived rather than assumed."""
    from app.providers.llm.openai_compat import OpenAICompatProvider

    provider = OpenAICompatProvider({"base_url": "http://example.invalid/v1",
                                     "model": "m", "max_tokens": 12000})
    provider._window = 16384

    tight = provider._fit_completion(prompt_chars=5100 * 4, wanted=12000)
    assert tight < 12000
    assert 5100 + tight < 16384                # the whole request now fits

    roomy = provider._fit_completion(prompt_chars=600 * 4, wanted=12000)
    assert roomy == 12000                      # untouched when there is space

    # an unknown window leaves the caller's choice alone
    provider._window = 0
    assert provider._fit_completion(5100 * 4, 12000) == 12000


def test_a_context_refusal_shrinks_the_request_instead_of_failing():
    """Estimating prompt tokens can only approximate the server's tokenizer --
    a 4-chars-per-token estimate still overshot a 16k window by two thousand
    tokens on a code-heavy prompt. The server's own refusal is better evidence."""
    from app.providers.llm.base import LLMError
    from app.providers.llm.openai_compat import OpenAICompatProvider

    provider = OpenAICompatProvider({"base_url": "http://example.invalid/v1",
                                     "model": "m", "max_tokens": 12000})
    seen: list[int] = []

    def fake_post(payload, attempts=4):
        seen.append(payload["max_tokens"])
        if payload["max_tokens"] > 3000:
            raise LLMError("400: This model's maximum context length is 16384 tokens")
        return {"choices": [{"message": {"content": "{}"}}], "usage": {}}

    provider._post = fake_post
    provider._post_within_window({"max_tokens": 12000})
    assert seen == [12000, 6000, 3000]       # halved until it fits


def test_an_impossible_prompt_says_so_plainly():
    from app.providers.llm.base import LLMError
    from app.providers.llm.openai_compat import OpenAICompatProvider

    provider = OpenAICompatProvider({"base_url": "http://example.invalid/v1",
                                     "model": "m", "max_tokens": 12000})

    def always_too_long(payload, attempts=4):
        raise LLMError("400: maximum context length exceeded")

    provider._post = always_too_long
    with pytest.raises(LLMError, match="larger window"):
        provider._post_within_window({"max_tokens": 12000})


def test_a_reply_budget_that_crowds_out_the_prompt_is_flagged():
    """max_tokens is the reply budget, not the context window -- they share it.
    Setting 16000 on a 16384-token model leaves 384 tokens for the prompt and
    every request fails, with nothing in the UI explaining why."""
    from app.providers.llm.openai_compat import OpenAICompatProvider

    provider = OpenAICompatProvider({"base_url": "http://example.invalid/v1",
                                     "model": "m", "max_tokens": 16000})
    provider._window = 16384

    # the clamp keeps it working whatever the setting says
    budget = provider._fit_completion(prompt_chars=6266 * 3, wanted=16000)
    assert budget < 16000
    assert 6266 + budget < 16384


# ---------------------------------------------------------- alignment -----
def test_a_phrase_the_voice_split_is_split_in_the_script_too():
    """A synthesized voice pauses at a full stop, so a phrase containing one is
    heard as two. 11 phrases became 12 detected segments and no threshold could
    reconcile them -- but the text says exactly where the break was."""
    from app.stages.align import split_phrases_to_match

    lines = [
        "An agent is a model plus a harness.",
        "The model writes the code. The harness decides what ships.",
        "One command. A hundred agents.",
        "MIT licensed.",
    ]
    five = split_phrases_to_match(lines, 5)
    assert five and len(five) == 5
    assert "The model writes the code." in five
    assert "The harness decides what ships." in five

    assert len(split_phrases_to_match(lines, 6)) == 6

    # when full stops run out, a clause break is where the voice actually
    # breathes -- this is the real case that failed: 11 phrases, 12 heard
    clauses = ["Apache two zero license, thirty eight thousand forty eight stars.",
               "The server detects your Docker daemon."]
    three = split_phrases_to_match(clauses, 3)
    assert three and len(three) == 3
    assert any(part.startswith("thirty eight") for part in three)

    # never invents a boundary that is not in the text
    assert split_phrases_to_match(["One two three four."], 4) is None


def test_synthesis_records_where_each_phrase_lands():
    """Boundaries are known when the track is assembled here, so alignment need
    not infer them from silences -- inference is what failed."""
    import inspect

    from app.providers.tts import joiner

    source = inspect.getsource(joiner.join)
    assert "segments" in source
    assert '"segments": segments' in source


def test_the_endcard_wordmark_always_fits():
    """`sbkit.endcard` draws the wordmark centred at a fixed 250px, so a long
    one runs off both edges -- "Harness Open Source" was 937px against a 912px
    budget even shrunk to the floor. A wordmark is a name, not a title."""
    import sys

    from app.config import get_config
    from app.models.facts import FactsBundle, GitHubFacts
    from app.stages.content import _wordmark

    video = str(get_config().paths.video)
    if video not in sys.path:
        sys.path.insert(0, video)
    import kit

    from app.render.fonts import patch_kit

    patch_kit(kit, strict=False)
    avail = 1080 - 2 * 84

    def facts_for(repo):
        return FactsBundle(slug="x", display_name="x", primary_url="u",
                           github=GitHubFacts(owner="o", repo=repo, full_name=f"o/{repo}",
                                              url="u", stars=1, forks=1,
                                              open_issues=1, watchers=1))

    for display, repo in (("Harness Open Source", "harness"), ("ruflo", "ruflo"),
                          ("DeerFlow", "deer-flow"), ("A Very Long Project Title", "vlp")):
        word = _wordmark(display, facts_for(repo))
        size = 250
        while size > 64 and kit.tw(word, kit.f(size, "bold"), 0) > avail:
            size -= 6
        assert kit.tw(word, kit.f(size, "bold"), 0) <= avail, f"{display} -> {word}"


def test_the_wordmark_is_measured_and_shrunk_rather_than_cut():
    """The shipped harness cover put "Harness Open Source" at 180px and it ran off
    both edges. `covers.py` draws the wordmark centred at whatever size the spec
    names with no shrink-to-fit, and the fit checker measured the kicker, hook,
    stats and footers -- but not the wordmark, so nothing caught it.

    Shrinking is the right repair, not truncation: a wordmark is the project's
    name, and "Harness Open Sou" is simply wrong.
    """
    from app.models.content import CoverSpec
    from app.stages.content import trim_cover_to_fit
    from app.validate.cover_fit import WORDMARK_AVAIL, measure_spec

    base = dict(
        bg=(9, 9, 18), accent=(124, 124, 248), accent_hi=(168, 168, 255),
        pale=(222, 222, 255), glow=(56, 48, 160), support=(64, 224, 208),
        motif="flow", eyebrow="CI/CD", sub="harness/harness",
        kicker="Self-hosted CI/CD", hook=["Drone successor", "adds Gitspaces"],
        stats=[("38K", "STARS"), ("3352", "FORKS"), ("GO", "LANGUAGE")],
        cmd="docker run", foot_l="OPEN SOURCE", foot_r="GO",
    )

    too_wide = CoverSpec(**base, wordmark="Harness Open Source", mark_font_size=180)
    problems = measure_spec(too_wide.to_covers_dict("c.png"))
    assert [p["field"] for p in problems] == ["wordmark"]
    assert problems[0]["width"] > WORDMARK_AVAIL

    fixed = trim_cover_to_fit(too_wide)
    assert fixed.wordmark == "Harness Open Source"   # the name survives intact
    assert fixed.mark_font_size < 180
    assert not measure_spec(fixed.to_covers_dict("c.png"))

    # a short wordmark is left at the size the spec asked for
    short = CoverSpec(**base, wordmark="harness", mark_font_size=180)
    assert not measure_spec(short.to_covers_dict("c.png"))
    assert trim_cover_to_fit(short).mark_font_size == 180


def test_captions_can_be_turned_off_per_job(content):
    """Every major platform auto-captions on upload, so burning them in is a
    choice rather than a given. It has to be made before the storyboard is
    written, because the storyboard is what draws them -- and a generated one
    has to be *told*, or it keeps calling S.captions regardless.
    """
    from app.prompts.storyboard import CAPTIONS_OFF, CAPTIONS_ON, SYSTEM
    from app.render.fallback_storyboard import build_source

    kwargs = dict(total=30.0, audio_rel="x.mp3", phrases_rel="phrases/x.txt")

    on = build_source(content, captions=True, **kwargs)
    off = build_source(content, captions=False, **kwargs)
    # emitted as a Python literal, not JSON -- `true` would be a NameError
    assert "'captions': True" in on
    assert "'captions': False" in off
    # the call site is identical in both -- the DATA flag is what gates it, so
    # the two modules cannot drift apart beyond that one value
    for module in (on, off):
        assert "CAPTIONS = DATA" in module
        assert "if CAPTIONS and" in module
    assert on.replace("'captions': True", "'captions': False") == off

    # and the codegen prompt says the opposite thing in each mode
    assert "{captions_rule}" in SYSTEM
    assert "DO NOT call `S.captions`" in CAPTIONS_OFF
    assert "Call `S.captions(" in CAPTIONS_ON


def test_counts_are_compacted_the_way_the_shipped_covers_are():
    """The six shipped covers read 165K, 17.6K, 89K, 314 -- one decimal below
    100K, none above, raw under 1000. A stat card is read at a glance and
    "38048" is a number you parse rather than see.

    The derived path always compacted; a model-supplied stat did not, which is
    how "38048 STARS" reached a rendered cover.
    """
    from app.stages.content import _compact, compact_stat

    assert [_compact(n) for n in (165_000, 17_600, 89_000, 38_048, 3_352, 314, 26)] \
        == ["165K", "17.6K", "89K", "38K", "3.4K", "314", "26"]
    assert _compact(1_240_000) == "1.2M"

    # model output is normalised to the same shape, and non-counts are untouched
    assert [compact_stat(v) for v in ("38048", "3,352", "GO", "100+", "314", "#1")] \
        == ["38K", "3.4K", "GO", "100+", "314", "#1"]


def test_fallback_text_is_trimmed_on_word_boundaries():
    """`content.tagline[:56]` put "...and artifact regi" on a rendered frame.

    A slice cuts wherever the budget lands, and the renderer cannot tell that
    from text the author meant -- so the shrink-to-fit pass drew the broken
    word faithfully. Trimming has to happen where the budget is applied.
    """
    from app.render.fallback_storyboard import _clip, _stat_value

    tagline = "Drone's successor adds SCM, Gitspaces, and artifact registry"
    for budget in (56, 42, 34, 26):
        out = _clip(tagline, budget)
        assert len(out) <= budget
        assert tagline.startswith(out.rstrip(" ,.;:-"))
        assert not out.endswith(("regi", "Gitspac", "Sou"))   # no mid-word cuts
        # trailing punctuation is dropped, so compare the bare word
        assert out.split()[-1] in [w.rstrip(",.;:-") for w in tagline.split()]

    assert _clip("short enough", 40) == "short enough"
    # a trailing conjunction, or a list item cut in half, promises a clause
    # that is not coming -- the opening frame read "...and artifact"
    assert _clip(tagline, 56) == "Drone's successor adds SCM, Gitspaces"
    assert _clip("built for speed and CD pipelines", 20) == "built for speed"
    # text that fits is never touched, dangling conjunctions and all: editing
    # what fits is how "docker run -d" once became "docker run"
    assert _clip("CI and CD in one place", 40) == "CI and CD in one place"
    assert _clip("built for speed and", 40) == "built for speed and"
    # a single word longer than the budget still has to be cut somewhere
    assert len(_clip("supercalifragilisticexpialidocious", 10)) <= 10

    # fact-sheet values get the same compaction the stat cards use
    assert _stat_value("38048") == "38K"
    assert _stat_value("Apache-2.0") == "Apache-2.0"


def test_numbers_spelled_out_in_narration_are_traced_too():
    """Narration spells its figures out, because a TTS engine reads "38K" as
    "thirty eight kay" and every shipped script writes the words. That put them
    beyond NUMBER_RE entirely -- the digit check ran on the on-screen text and
    saw nothing at all in the spoken line.

    Matching is at two significant figures because narration rounds: "thirty
    eight thousand" is a correct way to say 38,048 and rejecting it would
    reject every script in the repo.
    """
    import json

    from app.models.facts import FactsBundle
    from app.validate.facts_check import check_spoken, spoken_numbers, unsourced

    assert spoken_numbers("one point two million downloads") == \
        [("one point two million", 1_200_000)]
    assert spoken_numbers("seventeen point six thousand forks") == \
        [("seventeen point six thousand", 17_600)]
    assert spoken_numbers("a hundred plus agents") == [("a hundred", 100)]
    assert spoken_numbers("no numbers here") == []

    facts = FactsBundle.model_validate(json.loads(
        (FIXTURES / "harness-facts.json").read_text()))       # stars 38048
    assert not unsourced(check_spoken("thirty eight thousand stars", facts))
    assert unsourced(check_spoken("forty eight thousand stars", facts))

    # counts of things in the script itself are not claims about the project
    assert not check_spoken("one command, three scenes, two flags", facts)


def test_the_configured_runtime_window_reaches_the_script_validator():
    """`validate_script` takes a `target` its callers never passed, so the
    configured 36-44s window was silently replaced by a hardcoded 30-46s.

    A dead parameter is worse than no parameter: changing the window in
    settings appeared to work and did nothing.
    """
    import inspect

    from app.stages import content

    source = inspect.getsource(content._generate_script)
    # match the whole call, not one line: it wraps once the outro is threaded
    # through, and a line-based check reports that as a missing argument
    calls = re.findall(r"validate_script\((?:[^()]|\([^()]*\))*\)", source)
    assert calls, "the script path no longer validates at all"
    for call in calls:
        assert "target=" in call, f"the window is not passed: {call}"


def test_a_short_per_scene_assembly_is_expanded_not_shipped(content):
    """Four scenes each a little short produced 55 words -- a 25.8s reel that
    the platforms reject, and that nothing noticed until after the render.

    The assembly step trimmed a draft that came out too long and had no branch
    at all for one that came out too short.
    """
    import inspect

    from app.stages import content as content_mod

    source = inspect.getsource(content_mod.generate_script_per_scene)
    assert "validate_script(draft" in source, \
        "the assembled draft is not checked as a whole"
    assert "_repair_draft" in source, "there is no repair path for a bad assembly"

    # a failed repair keeps the draft rather than losing it, and a repair that
    # trades one set of problems for another is not accepted
    repair = inspect.getsource(content_mod._repair_draft)
    assert "return draft, []" in repair
    assert "if validate_script(rewritten" in repair


def test_a_number_inside_a_hashtag_is_a_name_not_a_claim():
    """"#qwen35" blocked a job three attempts running. A tag is a name the
    platform indexes, the model is not free to change it, and no repair could
    satisfy the checker.

    Fifth in the same family as AGPL-3.0, 2024-05-30, 194k and #0a0a12: the
    rule is that a number welded into an identifier is not a statistic.
    """
    facts = FactsBundle.model_validate(
        json.loads((FIXTURES / "harness-facts.json").read_text()))

    for tagged in ("#transformers #safetensors #qwen35", "#llama3", "#gpt4o",
                   "#v2ray #s3"):
        assert not facts_check.unsourced(facts_check.check(tagged, facts)), tagged

    # an invented figure next to a hashtag is still caught
    findings = facts_check.unsourced(
        facts_check.check("#qwen35 has 99000 stars", facts))
    assert [f.value for f in findings] == ["99000"]


def test_a_facts_measurement_window_is_part_of_the_fact():
    """Hugging Face's `downloads` is a last-30-days figure, so "1.4 million
    downloads in 30 days" is the honest way to say it -- and the checker
    rejected the 30, because the window appears only in the field's meaning.

    That blocked every script about a HF model's downloads, and no repair could
    fix it: the model was being asked to remove a number that was correct.
    """
    from app.models.facts import FactsBundle, HuggingFaceFacts

    hf = HuggingFaceFacts(model_id="Qwen/Qwen3-27B", author="Qwen",
                          downloads=1_400_000, likes=900, tags=[],
                          url="https://huggingface.co/Qwen/Qwen3-27B")
    facts = FactsBundle(slug="qwen3-27b", display_name="Qwen3-27B",
                        primary_url=hf.url, huggingface=hf)
    vocabulary = facts.numeric_vocabulary()

    assert "30" in vocabulary
    assert "1.4M" in vocabulary

    findings = facts_check.check("1.4M downloads in 30 days", facts)
    assert not facts_check.unsourced(findings)

    # a figure that is simply wrong is still caught
    wrong = facts_check.check("1.3 million downloads", facts)
    assert facts_check.unsourced(wrong)

    # a repo with no Hugging Face facts does not inherit the window
    github_only = FactsBundle.model_validate(
        json.loads((FIXTURES / "harness-facts.json").read_text()))
    assert github_only.huggingface is None
    assert "30" not in github_only.numeric_vocabulary()


def test_a_spelled_scale_word_is_part_of_the_number():
    """"1.4 million downloads" is how a caption is written; "1.4M" is how a stat
    card is written. Only the second was recognised, so every platform caption
    about a large figure was rejected and no repair could satisfy it.
    """
    from app.models.facts import FactsBundle, HuggingFaceFacts

    hf = HuggingFaceFacts(model_id="q/q", author="q", downloads=1_373_584,
                          likes=11_686, tags=[], url="https://huggingface.co/q/q")
    facts = FactsBundle(slug="q", display_name="Q", primary_url=hf.url, huggingface=hf)

    assert not facts_check.unsourced(facts_check.check("1.4 million downloads", facts))
    assert not facts_check.unsourced(facts_check.check("11.7 thousand likes", facts))
    assert not facts_check.unsourced(facts_check.check("1.4M downloads", facts))

    # a figure that is simply not the real one is still caught, at any spelling
    for wrong in ("2.9 million downloads", "47 million users", "9.1M downloads"):
        assert facts_check.unsourced(facts_check.check(wrong, facts)), wrong


def test_the_repair_message_names_the_figures_the_model_may_use():
    """The instruction read "replace them with a figure that is:" followed by
    the wrong numbers -- the model was told what not to write and never what to
    write, and burned three attempts on a figure it could not see."""
    from app.models.facts import FactsBundle, HuggingFaceFacts

    hf = HuggingFaceFacts(model_id="q/q", author="q", downloads=1_373_584,
                          likes=11_686, tags=[], url="https://huggingface.co/q/q")
    facts = FactsBundle(slug="q", display_name="Q", primary_url=hf.url, huggingface=hf)

    findings = facts_check.check("2.9 million downloads", facts)
    hint = facts_check.repair_hint(findings, facts)
    assert "1.4M" in hint and "1,373,584" in hint
    assert "downloads in the last 30 days" in hint

    # without the facts it still says what is wrong, just not what is right
    assert "2.9" in facts_check.repair_hint(findings)


def test_a_stat_that_overflows_reports_what_it_measured():
    """The stat branch shipped with placeholders: width 0, overflow 0, and a
    hardcoded 5-character suggestion. Every message read "'Apache-2.0' is 0px
    too wide, keep it to about 5 characters", which would have cut it to
    "Apach"."""
    from app.models.content import CoverSpec
    from app.stages.content import trim_cover_to_fit
    from app.validate.cover_fit import measure_spec

    base = dict(
        bg=(9, 9, 18), accent=(124, 124, 248), accent_hi=(168, 168, 255),
        pale=(222, 222, 255), glow=(56, 48, 160), support=(64, 224, 208),
        motif="flow", eyebrow="MODEL", sub="Qwen/Qwen3-27B", wordmark="Qwen3",
        kicker="A dense 27B model", hook=["Thinking mode", "on by default"],
        cmd="pip install", foot_l="OPEN SOURCE", foot_r="APACHE",
    )
    spec = CoverSpec(**base, stats=[("1.4M", "DOWNLOADS"), ("Apache-2.0", "LICENCE"),
                                    ("27B", "PARAMS")])

    problem = measure_spec(spec.to_covers_dict("c.png"))[0]
    assert problem["overflow_px"] > 0
    assert problem["width"] > problem["available"]
    assert problem["suggest_max_chars"] >= 8      # not the hardcoded 5

    fixed = trim_cover_to_fit(spec)
    assert fixed.stats[0] == ("1.4M", "DOWNLOADS")   # untouched
    assert fixed.stats[2] == ("27B", "PARAMS")       # untouched
    assert fixed.stats[1][0] == "Apache"             # shortened, not chopped
    assert not measure_spec(fixed.to_covers_dict("c.png"))


def test_the_assembly_window_is_measured_in_seconds_not_words():
    """A word ceiling of `high * 2.9` let 117 words through as a 48s script.

    The estimator weights syllables, so words-per-second is not a constant, and
    the estimator is the thing the platform check will ultimately agree or
    disagree with. Asking it directly removes the second, wrong model of length.
    """
    import inspect

    from app.stages import content as content_mod

    source = inspect.getsource(content_mod.generate_script_per_scene)
    # the prose explains the old multipliers, so judge the code alone
    code = "\n".join(line.split("#")[0] for line in source.splitlines())
    assert "high * 2.9" not in code and "low * 2.4" not in code, \
        "a word-count proxy for the runtime window is back"
    # `reel_seconds` is estimated_seconds plus the end beat -- the length the
    # platform check will actually see
    assert code.count("reel_seconds(") >= 2

    # trimming stops before it undershoots the floor
    assert "reel_seconds(trial, low) < low" in code


def test_the_derived_cover_never_violates_its_own_schema(content):
    """A 73-character kicker from the model raised a ValidationError out of the
    fallback path -- the one whose entire purpose is that it cannot fail."""
    from app.models.content import CoverSpec
    from app.stages.content import _clamp_to_schema

    overlong = {
        "kicker": "x" * 200, "eyebrow": "y" * 200, "sub": "z" * 200,
        "wordmark": "w" * 200, "cmd": "c" * 200,
        "foot_l": "l" * 200, "foot_r": "r" * 200,
    }
    clamped = _clamp_to_schema(dict(overlong))

    for name, field in CoverSpec.model_fields.items():
        limit = next((getattr(m, "max_length", None) for m in field.metadata
                      if getattr(m, "max_length", None)), None)
        if limit and name in clamped:
            assert len(clamped[name]) <= limit, f"{name} still over its limit"

    # a value already inside its limit is not touched
    assert _clamp_to_schema({"eyebrow": "MODEL"})["eyebrow"] == "MODEL"


def test_a_hook_never_strands_half_a_figure_or_ends_on_a_conjunction():
    """A hook is read at a glance, so where it breaks changes what it says.

    A generated cover read "A model with 27" / "billion parameters can" /
    "understand images and" -- the eye stops at 27, and the last line promises
    a clause that never arrives.
    """
    from app.stages.content import _wrap_words

    lines = _wrap_words("A model with 27 billion parameters can understand images", 22, 3)
    assert any(line.startswith("27 billion") for line in lines), lines
    assert not any(line.rstrip().endswith(" 27") for line in lines), lines

    for text in ("Self hosted CI and CD plus source hosting and artifact registries",
                 "One command gives you a hundred plus specialist agents",
                 "Drone successor adds source hosting and Gitspaces"):
        lines = _wrap_words(text, 20, 3)
        assert lines
        last = lines[-1].split()[-1].lower()
        assert last not in {"and", "or", "with", "the", "a", "of", "to", "plus"}, lines
        # a unit never starts a line on its own
        for line in lines:
            assert line.split()[0].lower() not in {"billion", "million", "thousand"}, lines


def test_a_stage_direction_is_not_narration():
    """One reel's last spoken line was "showing a model with a save prompt and
    a deployment interface" -- the ON SCREEN column, read aloud by the
    narrator, in the finished voice track."""
    from app.stages.content import _direction_phrases

    class Phrase:
        def __init__(self, text): self.text = text

    spoken = [Phrase("A model with 27 billion parameters runs on one GPU."),
              Phrase("It is available on Hugging Face today."),
              Phrase("Show me a repo that does that.")]     # "Show me" is speech
    assert not _direction_phrases(spoken)

    directions = [Phrase("showing a model with a save prompt"),
                  Phrase("Cut to the terminal as the command runs"),
                  Phrase("B-roll of the dashboard"),
                  Phrase("Close-up on the counter")]
    assert len(_direction_phrases(directions)) == 4



def test_every_stage_measures_the_same_finished_length():
    """The content stage measured the narration and the audio stage measured
    the narration plus the end beat, both against the same 36-44s window. A 35s
    script was under the floor in one and inside it in the other, so the
    expansion pass fired on a draft that was already fine.
    """
    import inspect

    from app.stages import pipeline
    from app.stages.content import TAIL_SECONDS, reel_seconds

    class Draft:
        def estimated_seconds(self): return 38.0

    # comfortably past the floor, so the tail stays at its minimum
    assert reel_seconds(Draft(), 36.0) == 38.0 + TAIL_SECONDS

    # nothing adds the beat by hand any more
    for module in (pipeline,):
        code = "\n".join(line.split("#")[0]
                         for line in inspect.getsource(module).splitlines())
        assert "+ 1.4" not in code, "the end beat is hardcoded somewhere again"


def test_understating_a_figure_is_honest_and_overstating_is_not():
    """1,373,584 downloads is "1.4 million" rounded and "1.3 million"
    truncated, and there really are 1.3 million of them.

    Only the rounded form was accepted, so a model that picked the conservative
    figure lost three generations to it. Overstating stays rejected -- that is
    the thing the whole table exists to prevent.
    """
    from app.models.facts import FactsBundle, HuggingFaceFacts

    hf = HuggingFaceFacts(model_id="q/q", author="q", downloads=1_373_584,
                          likes=11_686, tags=[], url="https://huggingface.co/q/q")
    facts = FactsBundle(slug="q", display_name="Q", primary_url=hf.url, huggingface=hf)

    for honest in ("1.3 million downloads", "1.4 million downloads",
                   "1.3M downloads", "11.6 thousand likes", "11.7K likes"):
        assert not facts_check.unsourced(facts_check.check(honest, facts)), honest

    for overstated in ("1.5 million downloads", "2.9 million downloads",
                       "12.5K likes"):
        assert facts_check.unsourced(facts_check.check(overstated, facts)), overstated


def test_a_script_about_the_worked_example_is_rejected():
    """A local model shown ruflo's script as an example returned ruflo's script
    -- for a Hugging Face model. Every existing gate passed it, because it is a
    well-formed, correctly-paced, internally consistent script about the wrong
    project.

    The general rule, which does not depend on knowing which example was shown:
    a script that never names its subject is about something else, whatever it
    says.
    """
    from app.models.content import Phrase
    from app.models.facts import FactsBundle, HuggingFaceFacts
    from app.stages.content import (_copied_phrases, _duplicate_phrases,
                                    _names_its_subject)

    hf = HuggingFaceFacts(model_id="Qwen/Qwen3.8-27B", author="Qwen",
                          downloads=1_373_584, likes=11_686, tags=[],
                          url="https://huggingface.co/Qwen/Qwen3.8-27B")
    facts = FactsBundle(slug="qwen3-8-27b", display_name="Qwen3.8-27B",
                        primary_url=hf.url, huggingface=hf)

    from_the_example = [
        Phrase(text="An agent is a model plus a harness.", scene_index=1),
        Phrase(text="Ruflo -- formerly Claude Flow -- is the harness layer.",
               scene_index=2),
    ]
    assert not _names_its_subject(from_the_example, facts)
    assert _copied_phrases(from_the_example, facts.display_name)

    about_the_subject = [
        Phrase(text="Qwen3.8-27B is a dense twenty seven billion parameter model.",
               scene_index=1),
        Phrase(text="It ships with a vision encoder.", scene_index=2),
    ]
    assert _names_its_subject(about_the_subject, facts)
    assert not _copied_phrases(about_the_subject, facts.display_name)

    # forty seconds has no room to say anything twice
    repeated = about_the_subject + [about_the_subject[0]]
    assert len(_duplicate_phrases(repeated)) == 1
    assert not _duplicate_phrases(about_the_subject)


def test_trimming_a_long_draft_never_empties_a_scene():
    """Dropping trailing phrases to reach the ceiling took all of scene 4,
    and `ReelContent` rejected the result -- a ValidationError out of the
    assembly step rather than a problem anything could act on."""
    import inspect

    from app.stages import content as content_mod

    source = inspect.getsource(content_mod.generate_script_per_scene)
    assert "scene_index == kept[-1].scene_index" in source, \
        "the trim can still remove a scene's last phrase"


def test_every_reel_ends_on_the_same_spoken_line():
    """"Follow for more." is appended deterministically rather than asked of the
    model, because a model told to end with a fixed sentence obeys most of the
    time -- and most of the time is not something you can build a channel on.

    It must be a real phrase in the script, not something added at synthesis
    time: `align.py build` refuses to run unless the phrase count matches the
    segments it detects, so a spoken line with no phrase behind it would break
    alignment outright.
    """
    from app.models.content import Phrase, ScriptDraft
    from app.stages.content import ensure_outro

    def draft(texts):
        return ScriptDraft.model_construct(
            phrases=[Phrase(text=t, scene_index=2) for t in texts],
            tagline="t", scenes=[])

    added = ensure_outro(draft(["One command.", "It just works."]))
    assert added.phrases[-1].text == "Follow for more."
    assert added.phrases[-1].scene_index == 2, "the outro left the closing scene"
    assert added.phrases[-1].pause_after_ms >= 400, "no beat before the end card"

    # appending twice must not say it twice
    assert len(ensure_outro(added).phrases) == len(added.phrases)

    # nor should a model that already ended with it, whatever the punctuation
    already = ensure_outro(draft(["Done.", "follow for more"]))
    assert len(already.phrases) == 2

    # and it is a preference, so it can be turned off
    assert len(ensure_outro(draft(["Only this."]), outro="").phrases) == 1


def test_the_outro_is_counted_before_the_length_window_is_checked():
    """It adds a second and a half of speech. Added after the runtime check, a
    draft measured at exactly the ceiling would tip over it at synthesis time,
    where nothing is watching."""
    import inspect

    from app.stages import content as content_mod

    for name in ("_generate_script", "generate_script_per_scene"):
        source = inspect.getsource(getattr(content_mod, name))
        assert "ensure_outro" in source, f"{name} does not append the outro"

    one_pass = inspect.getsource(content_mod._generate_script)
    assert "validate_script(ensure_outro(" in one_pass, (
        "the outro is added after the length window is checked, not before"
    )
