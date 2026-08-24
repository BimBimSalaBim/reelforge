"""The second UI is served, and the first one still is.

`app/main.py` ends with `GET /{path:path}`, which matches every path there is and
returns the old single-page app. Starlette tries routes in registration order, so
anything added after it is unreachable — and the failure is silent: `/v2` returns
the *old* UI with a 200, which reads as "the new UI failed to load" rather than as
a routing mistake. Every test here exists because of that one hazard.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

UI_V2 = Path(__file__).resolve().parent.parent / "app" / "ui_v2"
PAGES = sorted(UI_V2.glob("*.html"))
SCRIPTS = sorted((UI_V2 / "static").glob("*.js"))
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_the_v2_index_is_served(client):
    response = client.get("/v2/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "ReelForge" in response.text


def test_bare_v2_redirects_and_does_not_serve_the_old_ui(client):
    """The regression test for the catch-all.

    A mount at "/v2" matches "/v2/..." and never the bare "/v2". Without the
    explicit redirect the request falls past it to `GET /{path:path}` and is
    answered, with a 200, by the old single-page app.
    """
    response = client.get("/v2", follow_redirects=False)
    assert response.status_code == 307, (
        "bare /v2 was not redirected — it fell through to the SPA catch-all"
    )
    assert response.headers["location"].endswith("/v2/")
    assert 'class="layout"' not in response.text


def test_a_missing_v2_page_is_a_404_not_the_old_ui(client):
    """A broken link inside v2 must look broken, not like a working page."""
    response = client.get("/v2/nope.html")
    assert response.status_code == 404
    assert 'class="layout"' not in response.text


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_v2_page_is_served(client, page):
    response = client.get(f"/v2/{page.name}")
    assert response.status_code == 200
    assert response.text.strip()


def test_v2_assets_are_served_with_usable_types(client):
    for asset in SCRIPTS:
        response = client.get(f"/v2/static/{asset.name}")
        assert response.status_code == 200, f"{asset.name} is referenced but not served"
        assert "javascript" in response.headers["content-type"], asset.name
    if (UI_V2 / "static" / "app.css").exists():
        assert client.get("/v2/static/app.css").headers["content-type"].startswith("text/css")


def test_v2_does_not_shadow_the_api(client):
    """The API routers are registered first; this proves it stayed that way."""
    for path in ("/api/health", "/api/jobs", "/api/jobs/images/roles"):
        assert client.get(path).status_code == 200, path


def test_the_classic_ui_is_untouched(client):
    """v1 keeps working the whole time -- that is the point of building beside it."""
    response = client.get("/")
    assert response.status_code == 200
    assert 'class="layout"' in response.text, "the old single-page UI stopped being served"


def test_pages_only_reference_assets_that_exist():
    """A typo in a <script src> fails silently in a browser: the page loads, the
    script does not, and half the UI is inert with nothing in the console but a
    404 nobody was watching for."""
    missing: list[str] = []
    for page in PAGES:
        for ref in re.findall(r'(?:src|href)="/v2/(static/[^"]+)"', page.read_text()):
            if not (UI_V2 / ref).is_file():
                missing.append(f"{page.name} -> {ref}")
    assert not missing, "referenced but absent: " + ", ".join(missing)


def test_pages_carry_no_inline_styles():
    """The design system is only a system if nothing opts out of it.

    JS may set computed geometry (the frame scale, a panel height); markup may
    not carry a style attribute. Mechanical enforcement, because "we agreed not
    to" is how the old stylesheet ended up with 14 colours outside its tokens.
    """
    offenders = [p.name for p in PAGES if 'style="' in p.read_text()]
    assert not offenders, f"inline styles in {offenders}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_the_javascript_parses(script):
    """`node --check` with no flags, which is why these are classic scripts and
    not ES modules: checking a `.js` module needs an experimental flag, and
    `.mjs` is served as text/plain on some hosts. This is the only JavaScript
    verification the repo has, so it must not be behind a flag.
    """
    result = subprocess.run(["node", "--check", str(script)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, f"{script.name}:\n{result.stderr}"


def test_the_board_notices_a_reorder():
    """`JobStore.save` does not touch `updated_at`, so a fingerprint built only
    from job timestamps and counts cannot see a reorder — the board kept showing
    the old order while the API had already moved on. Whatever the page draws,
    the fingerprint has to cover."""
    source = (UI_V2 / "static" / "jobs.js").read_text()
    fingerprint = source[source.index("var next ="):source.index("var changed =")]
    assert "position" in fingerprint and "state" in fingerprint, \
        "the queue's order is not part of the change check"
    assert "paused" in fingerprint, "pausing the queue would not repaint the board"


def test_every_stage_has_a_pane():
    """A stage with no pane falls back to a bare meta table, which for `audio`
    and `align` meant the v2 UI could not take a reel end to end on its own --
    you had to go back to the classic UI for exactly two steps."""
    source = (UI_V2 / "static" / "job.js").read_text()
    for stage in ("content", "cover", "visuals", "audio", "align", "storyboard",
                  "render", "verify", "package"):
        assert f"panes.{stage} = " in source, f"no pane for {stage}"


def test_the_reel_length_is_read_not_recomputed():
    """The finished reel is the narration plus a beat stretched to reach the
    platform floor. `run_audio` already computes it and stores `reel_seconds`;
    reimplementing that arithmetic in JavaScript is the drift this project has
    already paid for once with the frame constants."""
    source = (UI_V2 / "static" / "job.js").read_text()
    assert "reel_seconds" in source
    assert "36" not in source.split("panes.audio")[1].split("panes.align")[0], \
        "the audio pane hardcodes a platform floor instead of reading the stage's value"


def test_the_header_offers_new_reel_once():
    """It appeared twice -- as a nav link and as the primary button -- which
    reads as two different things that do the same thing."""
    source = (UI_V2 / "static" / "shell.js").read_text()
    nav = source[source.index("var NAV = ["):source.index("];", source.index("var NAV = ["))]
    assert "new.html" not in nav, "New reel is in the nav as well as the button"
    assert source.count('href: "/v2/new.html"') == 1


CSS = (UI_V2 / "static" / "app.css").read_text()


def _token_block(selector: str) -> dict[str, str]:
    start = CSS.index(selector)
    body = CSS[CSS.index("{", start) + 1:CSS.index("\n}", start)]
    out = {}
    for line in body.splitlines():
        line = line.split("/*")[0]
        for decl in line.split(";"):
            if ":" in decl and decl.strip().startswith("--"):
                name, _, value = decl.partition(":")
                out[name.strip()] = value.strip()
    return out


def test_the_light_theme_defines_every_colour_the_dark_one_does():
    """A semantic token missing from the light block keeps its dark value, which
    on a white page is invisible text or an invisible border -- and only on the
    one screen that happens to use it.

    Only the semantic layer is checked: the neutral ramp and the hues are shared
    on purpose, which is what keeps this a theme rather than a second stylesheet.
    """
    dark = _token_block(":root {")
    light = _token_block(':root[data-theme="light"] {')

    semantic = [name for name in dark if name.startswith(
        ("--surface", "--border", "--text", "--accent", "--focus", "--st-", "--shadow"))]
    assert semantic, "the token naming changed; this test is now checking nothing"

    missing = [name for name in semantic if name not in light]
    assert not missing, f"the light theme leaves these at their dark values: {missing}"


def test_the_theme_is_resolved_before_first_paint():
    """A deferred theme script runs after the first paint, so a light-preferring
    viewer gets a black flash -- and in a multi-page app that is every click."""
    for page in PAGES:
        html = page.read_text()
        assert '<script src="/v2/static/theme.js"></script>' in html, page.name
        assert 'defer src="/v2/static/theme.js"' not in html, (
            f"{page.name} defers the theme script, which reintroduces the flash"
        )
        # and it must come before the stylesheet, so the attribute is set first
        assert html.index("theme.js") < html.index("app.css"), page.name


def test_colour_only_lives_in_the_token_blocks():
    """The v1 stylesheet had fourteen hexes outside its token set, which is why
    nothing in it could be re-themed. Both token blocks may hold raw colour;
    nothing below them may."""
    after = CSS[CSS.index("/* -------------------------------------------------------------------- BASE"):]
    # rgb(...) with an alpha is a shade of an existing colour, not a new one
    strays = re.findall(r"#[0-9a-fA-F]{3,8}\b", after)
    assert not strays, f"raw colours outside the token blocks: {sorted(set(strays))}"


def test_v2_can_edit_what_v1_can_edit():
    """v2 shipped read-only in three places -- the narration, the storyboard and
    the provider profiles -- which meant finishing a reel still meant going back
    to the classic UI. Displaying a thing is not the same as offering it."""
    job = (UI_V2 / "static" / "job.js").read_text()
    settings = (UI_V2 / "static" / "settings.js").read_text()

    # nothing that is meant to be edited may be marked readonly
    assert 'readonly: "readonly"' not in job, "a pane is still read-only"
    assert "PUT" in job or "RF.api.put" in job

    for call, where in (('/content"', job), ('/storyboard"', job),
                        ('"/api/settings/" + kind + "/profiles/"', settings)):
        assert call in where, f"nothing writes to {call}"

    assert "removeProfile" in settings and "editProfile" in settings


def test_the_active_profile_is_set_through_the_body():
    """`POST /{kind}/active` declares `name` as an embedded Body field. Sending
    it in the query string returns "name: Field required", which reads like the
    UI failed to pass a name rather than passing it in the wrong place."""
    settings = (UI_V2 / "static" / "settings.js").read_text()
    call = settings[settings.index("function activate("):]
    call = call[:call.index("\n  }")]
    assert "/active\", { name: name }" in call, "the active profile is set via the query"
    assert "?name=" not in call


def test_the_profile_test_button_reads_the_fields_the_probe_returns():
    """`POST /profiles/{name}/test` answers `reachable` and, separately,
    `authenticated`. Reading a non-existent `ok` reported every provider as
    unreachable -- including the ones that answered.

    They are separate questions on purpose: a local vLLM needs no key, and a
    hosted provider can be up and still refuse yours.
    """
    settings = (UI_V2 / "static" / "settings.js").read_text()
    body = settings[settings.index("function test("):]
    body = body[:body.index("\n  }")]
    assert "result.reachable" in body, "the test button does not read `reachable`"
    assert "result.authenticated" in body, "a refused key is reported as unreachable"
    assert "result.ok" not in body, "reading a field the probe does not return"
    assert "result.error" in body, "the reason a provider is down is discarded"


def test_profile_fields_render_as_their_declared_type():
    """The field schema says select, bool, keyname, voice, number or text.
    Rendering all of them as a text box throws that away -- "Structured output"
    is three fixed values, and typing one is a way to get it wrong."""
    settings = (UI_V2 / "static" / "settings.js").read_text()
    control = settings[settings.index("function buildControl("):]
    control = control[:control.index("\n  function ")]
    for kind in ("select", "bool", "voice", "number", "keyname"):
        assert f'"{kind}"' in control, f"{kind} fields fall through to a text box"
    assert "field.options" in control, "a select does not use its declared options"


def test_v2_settings_covers_what_v1_settings_covers():
    """Everything the classic settings screen can do, or v2 is not a replacement."""
    settings = (UI_V2 / "static" / "settings.js").read_text()
    for endpoint, what in [
        ('"/active"', "activate a profile"),
        ('/profiles/"', "add, edit or delete a profile"),
        ("/test", "test a profile"),
        ("/voices", "list voices"),
        ("/llm/roles", "route roles"),
        ("/roles/preset/", "apply a role preset"),
        ("/approval", "set review gates"),
        ("/secrets", "set and clear API keys"),
        ("/config/tts/key", "pin or rotate a TTS key"),
    ]:
        assert endpoint in settings, f"v2 settings cannot {what}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("page_script", ["settings.js", "job.js", "jobs.js"])
def test_pages_render_against_real_api_payloads(page_script):
    """`node --check` proves a file parses; it cannot prove a page works.

    Two bugs shipped that this catches and `node --check` cannot: the settings
    page called `.map` on an object, and the job page treated a 404 from a
    stage that had not finished writing its artifact as a failure -- "no
    storyboard yet" rendered as "Could not load this stage" while the pipeline
    was working perfectly well.

    The fixture pins the storyboard stage as `running` for exactly that reason.
    This renders the page under a DOM stub against captured API responses and
    fails if it paints an error callout, which is the same signal a person gets
    from looking at it.

    The stub has to satisfy `child instanceof Node`, or `el()` stringifies every
    element and a page full of "[object Object]" reports as fine.
    """
    result = subprocess.run(
        ["node", str(FIXTURES / "render_page.js"),
         str(UI_V2 / "static" / page_script), str(FIXTURES)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr.strip() or result.stdout.strip()


V1 = Path(__file__).resolve().parent.parent / "app" / "ui" / "dist" / "index.html"


def test_each_ui_links_to_the_other():
    """Getting from the classic UI to v2 meant typing the URL, which is not a
    migration path -- nobody discovers a new interface they cannot see.

    Both directions are needed while the two run side by side.
    """
    assert 'href="/v2/"' in V1.read_text(), "the classic UI cannot reach v2"
    shell = (UI_V2 / "static" / "shell.js").read_text()
    assert 'href: "/"' in shell, "v2 cannot get back to the classic UI"


def test_the_classic_ui_does_not_depend_on_v2_assets():
    """It is the fallback. If it loaded v2's stylesheet or scripts, one broken
    v2 asset would take down the thing you fall back to -- so the handful of
    icon paths it needs are duplicated into it deliberately."""
    html = V1.read_text()
    # references, not prose: the file explains in a comment why it does *not*
    # load from /v2/static, and a substring check reads that as a dependency
    refs = re.findall(r'(?:src|href)="([^"]+)"', html)
    borrowed = [r for r in refs if r.startswith("/v2/static") or r.startswith("/v2/fonts")]
    assert not borrowed, f"the fallback UI loads v2 assets: {borrowed}"
