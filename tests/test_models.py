"""The model layer's invariants -- the ones that protect the pipeline below."""
import pytest
from pydantic import ValidationError

from app.models.content import ReelContent
from app.models.facts import FactsBundle, GitHubFacts
from app.models.job import Job, JobSource, Stage, Status
from app.models.platform import InstagramPost, LinkedInPost, YouTubePost


def test_out_of_order_phrases_are_sorted_not_rejected(content):
    """Phrases are spoken in sequence, so scene order matters -- but a list that
    is merely emitted out of order is recoverable without another round trip.
    The sort is stable, so order within a scene, which nothing else can
    reconstruct, is preserved."""
    payload = content.model_dump()
    phrases = payload["phrases"]
    payload["phrases"] = [phrases[-1]] + phrases[:-1]

    result = ReelContent.model_validate(payload)
    indices = [p.scene_index for p in result.phrases]
    assert indices == sorted(indices)

    scene_one = [p.text for p in result.phrases if p.scene_index == 1]
    assert scene_one[0] == "An agent is a model plus a harness."


def test_every_scene_needs_narration(content):
    """Keep enough phrases to clear the length floor, but leave scene 4 silent."""
    payload = content.model_dump()
    payload["phrases"] = [p.model_dump() for p in content.phrases
                          if p.scene_index != 4]
    assert len(payload["phrases"]) >= 6
    with pytest.raises(ValidationError, match="no narration phrases"):
        ReelContent.model_validate(payload)


def test_narration_groups_by_scene(content):
    paragraphs = content.narration.split("\n\n")
    assert len(paragraphs) == 4
    assert paragraphs[0].startswith("An agent is a model")


def test_phrase_lines_match_phrase_count(content):
    """align.py refuses to build unless these counts agree."""
    assert len(content.phrase_lines()) == len(content.phrases)


def test_hashtags_must_be_five_and_distinct(content):
    payload = content.model_dump()
    payload["hashtags"] = ["#a2", "#a2", "#b2", "#c2", "#d2"]
    with pytest.raises(ValidationError, match="distinct"):
        ReelContent.model_validate(payload)


def test_youtube_title_gets_shorts_suffix():
    post = YouTubePost(title="A specific claim about a tool",
                       description_body=["body"])
    assert post.title.endswith("#shorts")


def test_youtube_title_length_is_enforced():
    with pytest.raises(ValidationError, match="max 100"):
        YouTubePost(title="x" * 120, description_body=["body"])


def test_instagram_hook_must_survive_the_fold():
    """Instagram hides everything past 125 characters behind "... more".

    A hook slightly over is trimmed to the fold rather than failing the whole
    bundle: it is a formatting limit, not a judgment, and one job lost three
    generations to a 131-character hook. A hook far over means the model wrote
    a paragraph where a line was asked for, and that does go back.
    """
    def post(hook):
        return InstagramPost(hook=hook, body=["b"], stats_line="s",
                             save_prompt="p", question="q", alt_text="a",
                             hashtags=["#a", "#b", "#c", "#d", "#e"])

    fits = "Ship a self-hosted CI pipeline in one command"
    assert post(fits).hook == fits                      # untouched

    slightly_over = ("Qwen3 is a dense twenty seven billion parameter model with a "
                     "vision encoder, thinking mode on by default, and low "
                     "latency inference")
    assert len(slightly_over) > 125
    trimmed = post(slightly_over).hook
    assert len(trimmed) <= 125
    assert slightly_over.startswith(trimmed)
    assert trimmed.split()[-1] in slightly_over.split()          # no mid-word cut
    assert trimmed.split()[-1].lower() not in {"and", "with", "a"}   # no dangling

    with pytest.raises(ValidationError, match="125"):
        post("x " * 130)


def test_linkedin_rejects_a_shell_prompt_in_the_body():
    """A command prompt reads wrong in that feed; it belongs in a comment."""
    with pytest.raises(ValidationError, match="shell prompt"):
        LinkedInPost(hook="h", body=["intro", "$ npm install thing"],
                     takeaway="t", question="q")


def test_numeric_vocabulary_allows_real_figures_and_rejects_invention():
    facts = FactsBundle(
        slug="x", display_name="x", primary_url="u",
        github=GitHubFacts(owner="o", repo="r", full_name="o/r", url="u",
                           stars=68041, forks=5820, open_issues=1, watchers=2),
    )
    vocabulary = facts.numeric_vocabulary()
    assert "68041" in vocabulary and "68K" in vocabulary and "68,041" in vocabulary
    assert "47000" not in vocabulary


def test_rerunning_a_stage_invalidates_everything_after_it():
    """Editing the script must not leave a video rendered from the old one."""
    job = Job(id="j", slug="s", source=JobSource(url="u"))
    for stage in (Stage.INGEST, Stage.CONTENT, Stage.RENDER):
        job.mark(stage, Status.DONE)
    cleared = job.invalidate_from(Stage.CONTENT)
    assert Stage.RENDER in cleared
    assert job.state(Stage.RENDER).status is Status.PENDING
    assert job.state(Stage.INGEST).status is Status.DONE


def test_stage_blockers_are_reported():
    job = Job(id="j", slug="s", source=JobSource(url="u"))
    assert job.blockers(Stage.RENDER)
    assert Stage.INGEST in job.blockers(Stage.RENDER)


def test_colours_accept_the_forms_models_actually_write():
    """Hex is at least as common as a triple in model output. Rejecting it cost
    a whole repair round to relearn what the prompt already said, and a
    two-element array reported three separate missing fields rather than the
    one real problem."""
    from app.models.content import ThemeSpec

    base = dict(accent=[124, 124, 248], accent_hi=[168, 168, 255],
                pale=[222, 222, 255], glow=[56, 48, 160], support=[64, 224, 208])
    for form in ("#0a0a12", "0a0a12", "rgb(10, 10, 18)", [10, 10, 18], (10, 10, 18),
                 [10, 10, 18, 255]):
        assert ThemeSpec(bg=form, **base).bg == (10, 10, 18), form
    assert ThemeSpec(bg="#abc", **base).bg == (170, 187, 204)

    with pytest.raises(ValidationError, match="exactly three numbers"):
        ThemeSpec(bg=[10, 10], **base)
    with pytest.raises(ValidationError, match="not a colour"):
        ThemeSpec(bg="dark blue", **base)
