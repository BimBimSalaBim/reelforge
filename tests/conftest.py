import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

from app.models.content import ReelContent


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def ruflo_timing(repo_root) -> Path:
    """The real narration's word timing.

    `video/build/` is generated and not tracked, so a fresh clone does not have
    this. Skip rather than fail: the tests that use it are checking the cue-word
    ladder against real timing, and absent timing is a missing prerequisite, not
    a broken check. Rebuild with `cd video && ./make.sh ruflo`.
    """
    path = repo_root / "video" / "build" / "ruflo.timing.json"
    if not path.exists():
        pytest.skip(f"{path.relative_to(repo_root)} is generated; run video/make.sh to build it")
    return path


@pytest.fixture
def content() -> ReelContent:
    """A complete, valid ReelContent keyed to ruflo's real narration."""
    lines = [
        "An agent is a model plus a harness.",
        "The model writes the code.",
        "The harness decides whether any of it gets done.",
        "Ruflo is the harness layer for Claude Code.",
        "One npx command gives you a hundred agents.",
        "They swarm, learn, and remember across sessions.",
        "Then there's federation, which is the strange one.",
        "Your agents can talk to agents on another machine.",
        "MIT licensed.",
        "Sixty-eight thousand stars.",
    ]
    scenes = [1, 1, 1, 2, 2, 2, 3, 3, 4, 4]
    return ReelContent.model_validate({
        "slug": "ruflo", "display_name": "ruflo",
        "repo_url": "https://github.com/ruvnet/ruflo",
        "tagline": "The harness layer for coding agents",
        "audience": "developers using coding agents",
        "scenes": [
            {"index": i, "title": t, "t_start": (i - 1) * 9.0, "t_end": i * 9.0,
             "you_say": "spoken", "on_screen": "drawn"}
            for i, t in enumerate(["Hook", "What", "Twist", "Close"], start=1)
        ],
        "phrases": [{"text": t, "scene_index": s, "pause_after_ms": 300}
                    for t, s in zip(lines, scenes)],
        "fact_sheet": [{"label": "Repo", "value": "ruvnet/ruflo"},
                       {"label": "Licence", "value": "MIT"},
                       {"label": "Author", "value": "rUv"},
                       {"label": "Stars", "value": "68K"},
                       {"label": "Agents", "value": "100+"},
                       {"label": "Created", "value": "2 June 2025"}],
        "accuracy_notes": ["Star counts drift; re-check before recording."],
        "cover": {"bg": [9, 9, 18], "accent": [124, 124, 248],
                  "accent_hi": [168, 168, 255], "pale": [222, 222, 255],
                  "glow": [56, 48, 160], "support": [64, 224, 208],
                  "motif": "swarm", "eyebrow": "AGENT = MODEL + HARNESS",
                  "wordmark": "ruflo", "sub": "ruvnet/ruflo",
                  "kicker": "One command, a hundred agents.",
                  "hook": ["An agent is a model", "plus a harness."],
                  "stats": [["68K", "STARS"], ["100+", "AGENTS"], ["314", "TOOLS"]],
                  "cmd": "npx ruflo init", "prompt": True,
                  "foot_l": "OPEN SOURCE - MIT", "foot_r": "FEDERATION"},
        "theme": {"bg": [9, 9, 18], "accent": [124, 124, 248],
                  "accent_hi": [168, 168, 255], "pale": [222, 222, 255],
                  "glow": [56, 48, 160], "support": [64, 224, 208]},
        "hashtags": ["#aiagents", "#claudecode", "#opensource", "#devtools", "#mcp"],
    })
