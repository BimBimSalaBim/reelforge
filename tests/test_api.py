"""API surface, exercised against a temporary job store."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("REELFORGE_PATHS__DATA_DIR", str(tmp_path))
    monkeypatch.setenv("REELFORGE_EXECUTOR", "inline")
    import app.config
    import app.runner

    app.config.get_config.cache_clear()
    app.runner.mode.cache_clear()
    from app.main import app as fastapi_app

    return TestClient(fastapi_app)


def test_health_and_templates(client):
    assert client.get("/api/health").json()["ok"] is True
    names = {t["name"] for t in client.get("/api/templates").json()}
    assert {"cool-indigo", "safe-deterministic"} <= names


def test_stage_list_is_the_pipeline_order(client):
    stages = [s["stage"] for s in client.get("/api/stages").json()]
    assert stages[0] == "ingest" and stages[-1] == "package"
    assert stages.index("align") < stages.index("storyboard") < stages.index("render")


def test_a_bad_url_is_rejected_with_an_explanation(client):
    response = client.post("/api/jobs", json={"url": "https://example.com/x", "autostart": False})
    assert response.status_code == 400
    assert "github.com" in response.json()["detail"]


def test_create_and_fetch_a_job(client):
    created = client.post("/api/jobs", json={
        "url": "https://github.com/ruvnet/ruflo", "autostart": False,
        "template": "safe-deterministic"}).json()
    assert created["slug"] == "ruflo"
    assert created["next_stage"] == "ingest"

    fetched = client.get(f"/api/jobs/{created['id']}").json()
    assert fetched["id"] == created["id"]
    assert [s["stage"] for s in fetched["stages"]][0] == "ingest"
    assert client.get("/api/jobs").json()[0]["id"] == created["id"]


def test_running_a_blocked_stage_is_refused(client):
    job = client.post("/api/jobs", json={
        "url": "https://github.com/ruvnet/ruflo", "autostart": False}).json()
    response = client.post(f"/api/jobs/{job['id']}/run", json={"stage": "render"})
    assert response.status_code == 409
    assert "blocked by" in response.json()["detail"]


def test_content_is_absent_before_it_is_generated(client):
    job = client.post("/api/jobs", json={
        "url": "https://github.com/ruvnet/ruflo", "autostart": False}).json()
    assert client.get(f"/api/jobs/{job['id']}/content").status_code == 404


def test_artifact_paths_cannot_escape_the_job_directory(client, tmp_path):
    """A plain `../` is normalised away by the HTTP client before it is sent, so
    the guard is exercised with a percent-encoded traversal, which is not."""
    job = client.post("/api/jobs", json={
        "url": "https://github.com/ruvnet/ruflo", "autostart": False}).json()

    secret = tmp_path.parent / "outside.txt"
    secret.write_text("must not be served")

    encoded = "%2e%2e%2f" * 6 + "outside.txt"
    assert client.get(f"/api/jobs/{job['id']}/artifacts/{encoded}").status_code == 404
    assert client.get(f"/api/jobs/{job['id']}/artifacts/%2e%2e%2f%2e%2e%2fconfig.yaml"
                      ).status_code == 404

    # and the guard itself, called directly with a traversal the client would strip
    from fastapi import HTTPException

    from app.api.routes_jobs import artifact

    with pytest.raises(HTTPException) as raised:
        artifact(job["id"], "../../../../etc/passwd")
    assert raised.value.status_code == 404

    # a real artifact inside the job directory is still served
    from app.store import JobStore

    root = JobStore().dir_for(job["id"])
    (root / "job.json").exists()
    assert artifact(job["id"], "job.json").status_code == 200


def test_unknown_job_is_a_404(client):
    assert client.get("/api/jobs/does-not-exist").status_code == 404


def test_deleting_a_job_removes_it(client):
    job = client.post("/api/jobs", json={
        "url": "https://github.com/ruvnet/ruflo", "autostart": False}).json()
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404


# ------------------------------------------------------------- archiving --
def test_archiving_hides_a_job_without_losing_it(client):
    job = client.post("/api/jobs", json={
        "url": "https://github.com/ruvnet/ruflo", "autostart": False}).json()

    assert client.post(f"/api/jobs/{job['id']}/archive").json()["archived"] is True
    assert job["id"] not in [j["id"] for j in client.get("/api/jobs").json()]
    archived = client.get("/api/jobs?archived=true").json()
    assert job["id"] in [j["id"] for j in archived]
    # the job itself is untouched and still fetchable
    assert client.get(f"/api/jobs/{job['id']}").json()["archived"] is True


def test_restoring_returns_a_job_to_the_list(client):
    job = client.post("/api/jobs", json={
        "url": "https://github.com/ruvnet/ruflo", "autostart": False}).json()
    client.post(f"/api/jobs/{job['id']}/archive")
    client.post(f"/api/jobs/{job['id']}/unarchive")
    assert job["id"] in [j["id"] for j in client.get("/api/jobs").json()]


def test_counts_drive_the_tab_labels(client):
    first = client.post("/api/jobs", json={
        "url": "https://github.com/ruvnet/ruflo", "autostart": False}).json()
    client.post("/api/jobs", json={
        "url": "https://github.com/bytedance/deer-flow", "autostart": False})
    client.post(f"/api/jobs/{first['id']}/archive")
    counts = client.get("/api/jobs/counts").json()
    assert counts == {"current": 1, "archived": 1, "total": 2}


def test_the_limit_counts_visible_jobs_not_scanned_ones(client):
    """Asking for N current jobs must return N even when archived ones are
    interleaved -- otherwise the list silently shortens as things are archived."""
    ids = [client.post("/api/jobs", json={
        "url": "https://github.com/ruvnet/ruflo", "autostart": False}).json()["id"]
        for _ in range(4)]
    client.post(f"/api/jobs/{ids[0]}/archive")
    client.post(f"/api/jobs/{ids[2]}/archive")
    assert len(client.get("/api/jobs?limit=2").json()) == 2


# ------------------------------------------------------------- recovery ---
def test_a_stage_orphaned_by_a_restart_becomes_retryable(client):
    """Nothing owns a stage across a restart. Left as `running` the job is stuck
    for ever; marked failed it is visible and re-runnable."""
    from app.models.job import Stage, Status
    from app.store import JobStore

    job = client.post("/api/jobs", json={
        "url": "https://github.com/ruvnet/ruflo", "autostart": False}).json()
    store = JobStore()
    loaded = store.load(job["id"])
    loaded.mark(Stage.STORYBOARD, Status.RUNNING)
    store.save(loaded)

    recovered = store.recover_orphans()
    assert (job["id"], "storyboard") in recovered

    state = store.load(job["id"]).state(Stage.STORYBOARD)
    assert state.status is Status.FAILED
    assert "Interrupted" in state.error


def test_recovery_leaves_finished_stages_alone(client):
    from app.models.job import Stage, Status
    from app.store import JobStore

    job = client.post("/api/jobs", json={
        "url": "https://github.com/ruvnet/ruflo", "autostart": False}).json()
    store = JobStore()
    loaded = store.load(job["id"])
    loaded.mark(Stage.INGEST, Status.DONE)
    loaded.mark(Stage.CONTENT, Status.REVIEW)
    store.save(loaded)

    store.recover_orphans()
    after = store.load(job["id"])
    assert after.state(Stage.INGEST).status is Status.DONE
    assert after.state(Stage.CONTENT).status is Status.REVIEW


def test_a_jobs_template_can_be_changed_and_reruns_the_right_stages(client):
    job = client.post("/api/jobs", json={
        "url": "https://github.com/ruvnet/ruflo", "autostart": False,
        "template": "cool-indigo"}).json()
    body = client.patch(f"/api/jobs/{job['id']}",
                        json={"template": "safe-deterministic"}).json()
    assert body["template"] == "safe-deterministic"


def test_an_unknown_template_is_refused(client):
    job = client.post("/api/jobs", json={
        "url": "https://github.com/ruvnet/ruflo", "autostart": False}).json()
    response = client.patch(f"/api/jobs/{job['id']}", json={"template": "nope"})
    assert response.status_code == 404


def test_editing_a_job_mid_stage_is_refused_rather_than_lost(client):
    """A running stage writes its own copy back when it finishes, so an edit
    made meanwhile would vanish without a word."""
    from app.models.job import Stage, Status
    from app.store import JobStore

    job = client.post("/api/jobs", json={
        "url": "https://github.com/ruvnet/ruflo", "autostart": False}).json()
    store = JobStore()
    loaded = store.load(job["id"])
    loaded.mark(Stage.CONTENT, Status.RUNNING)
    store.save(loaded)

    response = client.patch(f"/api/jobs/{job['id']}",
                            json={"template": "safe-deterministic"})
    assert response.status_code == 409
    assert "running" in response.json()["detail"]


def test_a_job_reports_which_model_it_would_use(client):
    """Three layers decide this -- the job's override, the per-role routing and
    the active profile -- and nothing showed the answer, so a stale line in the
    activity log read as the current provider."""
    job = client.post("/api/jobs", json={
        "url": "https://github.com/ruvnet/ruflo", "autostart": False}).json()
    resolved = job["resolved"]
    assert resolved["content"]["profile"]
    assert resolved["content"]["source"] in ("active profile", "role routing",
                                             "job override")
    assert resolved["voice"]["profile"]


def test_a_per_job_model_override_is_reported_and_clearable(client):
    job = client.post("/api/jobs", json={
        "url": "https://github.com/ruvnet/ruflo", "autostart": False}).json()

    body = client.patch(f"/api/jobs/{job['id']}",
                        json={"llm_provider": "ollama"}).json()
    assert body["resolved"]["content"]["profile"] == "ollama"
    assert body["resolved"]["content"]["source"] == "job override"

    cleared = client.patch(f"/api/jobs/{job['id']}",
                           json={"llm_provider": ""}).json()
    assert cleared["providers"]["llm_provider"] is None
    assert cleared["resolved"]["content"]["source"] != "job override"


def test_captions_and_fact_checking_are_per_job_settings(client):
    """Both are decisions the pipeline cannot make for you.

    Captions: every major platform auto-captions on upload now, so burning them
    in duplicates that -- but burned-in text is what carries a muted autoplay.
    Fact checking: strict is right for a generated script and wrong for a
    hand-written one whose figures the parser cannot see.

    Each has to be settled before the stage that consumes it, so changing one
    invalidates from there.
    """
    created = client.post("/api/jobs", json={
        "url": "https://github.com/harness/harness",
        "captions": False, "fact_check": "warn", "autostart": False,
    })
    assert created.status_code == 201, created.text
    job = created.json()
    assert job["captions"] is False
    assert job["fact_check"] == "warn"

    # both survive a reload
    again = client.get(f"/api/jobs/{job['id']}").json()
    assert (again["captions"], again["fact_check"]) == (False, "warn")

    patched = client.patch(f"/api/jobs/{job['id']}",
                           json={"captions": True, "fact_check": "off"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["captions"] is True
    assert patched.json()["fact_check"] == "off"

    # an unknown mode is rejected rather than silently treated as strict
    assert client.patch(f"/api/jobs/{job['id']}",
                        json={"fact_check": "lenient"}).status_code == 422

    # and the form can read the defaults without probing any provider
    defaults = client.get("/api/config/profiles").json()
    assert defaults["fact_check"] in ("strict", "warn", "off")
    assert isinstance(defaults["burn_captions"], bool)


def _png(width: int, height: int) -> bytes:
    """A real image, because the endpoint checks that it can open one."""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (240, 240, 245)).save(buffer, "PNG")
    return buffer.getvalue()


def test_screenshots_are_optional_labelled_and_croppable(client):
    """Screenshots are the only thing on screen the pipeline did not draw, so
    they are worth having -- and a job without them must render exactly as it
    did before, which is what `needs: [images>=1]` buys.

    The label matters as much as the file: nothing in the pixels distinguishes
    a README screenshot from a terminal, and a wrong guess puts "WHAT IT
    PRINTS" over a repository page.
    """
    created = client.post("/api/jobs", json={
        "url": "https://github.com/harness/harness", "autostart": False})
    job_id = created.json()["id"]
    assert created.json()["images"] == []

    roles = client.get("/api/jobs/images/roles").json()["roles"]
    assert [r["key"] for r in roles] == ["repo", "app", "output", "other"]
    assert all(r["label"] and r["hint"] for r in roles)

    # a wide screenshot arrives as a panel, because a 9:16 crop of it would
    # keep about a third of its width
    upload = client.post(f"/api/jobs/{job_id}/images?role=repo",
                         files=[("files", ("wide.png", _png(1920, 1080), "image/png"))])
    assert upload.status_code == 201, upload.text
    image = upload.json()["added"][0]
    assert image["role"] == "repo"
    assert image["fit"] == "panel"
    assert image["prepared"], "no bitmap was prepared for the renderer"
    assert image["prepared_width"] == 1080           # the full frame width

    # a tall one is offered full-bleed
    tall = client.post(f"/api/jobs/{job_id}/images?role=output",
                       files=[("files", ("tall.png", _png(1080, 1920), "image/png"))])
    assert tall.json()["added"][0]["fit"] == "full"

    # switching fit and cropping re-cuts the bitmap
    patched = client.patch(f"/api/jobs/{job_id}/images/{image['id']}",
                           json={"fit": "full", "crop_x": 0.25, "crop_w": 0.5,
                                 "caption": "the repository"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["fit"] == "full"
    assert patched.json()["prepared_width"] == 1080
    assert patched.json()["prepared_height"] == 1920
    assert patched.json()["caption"] == "the repository"

    # an upload that is not an image is refused with a reason
    bad = client.post(f"/api/jobs/{job_id}/images?role=other",
                      files=[("files", ("notes.txt", b"hello", "text/plain"))])
    assert bad.status_code == 400
    assert "supported" in bad.json()["detail"]

    # an unknown role is refused rather than silently filed under "other"
    assert client.post(f"/api/jobs/{job_id}/images?role=nonsense",
                       files=[("files", ("x.png", _png(100, 100), "image/png"))]
                       ).status_code == 422

    listed = client.get(f"/api/jobs/{job_id}").json()["images"]
    assert len(listed) == 2

    removed = client.delete(f"/api/jobs/{job_id}/images/{image['id']}")
    assert removed.status_code == 200
    assert len(removed.json()["images"]) == 1
