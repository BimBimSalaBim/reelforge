"""Templates: a directory, not code.

A template carries the visual direction for a reel -- palette hints, tone, a
cover motif, and a worked example storyboard the code-writing model is shown.
Adding one is dropping in a directory; nothing here needs to change.

`safe-deterministic` is special: it skips code generation entirely and renders
from the content data, so it always produces a video.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

TEMPLATE_DIR = Path(__file__).resolve().parent


@dataclass
class Template:
    name: str
    title: str
    description: str = ""
    tone_hint: str = ""
    #: the storyboard shown to the model as a worked example
    example: str = "ruflo"
    deterministic: bool = False
    palette: dict = field(default_factory=dict)
    motif: str = "flow"
    directory: Path | None = None

    @property
    def example_source(self) -> str:
        """The example storyboard's source, from the template or from video/."""
        if self.directory:
            local = self.directory / "example.py"
            if local.exists():
                return local.read_text()
        from app.prompts.api_reference import example_storyboard

        return example_storyboard(self.example)

    def as_dict(self) -> dict:
        return {"name": self.name, "title": self.title,
                "description": self.description, "motif": self.motif,
                "deterministic": self.deterministic, "palette": self.palette}


#: Shipped templates, derived from the storyboards that already work. Each names
#: an existing storyboard as its worked example rather than duplicating one.
BUILTIN: dict[str, Template] = {
    "cool-indigo": Template(
        name="cool-indigo", title="Cool indigo",
        description="Indigo and teal on near-black. Equation opener, pipeline "
                    "diagram, hard-landing end card.",
        tone_hint="Cool and technical. Lead with a definition or an equation, "
                  "then the mechanism. Indigo accent, teal support.",
        example="ruflo", motif="swarm",
        palette={"bg": [9, 9, 18], "accent": [124, 124, 248], "support": [64, 224, 208]},
    ),
    "warm-amber": Template(
        name="warm-amber", title="Warm amber",
        description="Amber on warm black. Urgency and momentum; good for a "
                    "project whose story is speed or scale.",
        tone_hint="Warm and urgent. Lead with the number that makes people look "
                  "twice. Amber accent, cream support.",
        example="deepseek-harness", motif="plugins",
        palette={"bg": [10, 8, 9], "accent": [232, 129, 60], "support": [246, 201, 160]},
    ),
    "editorial": Template(
        name="editorial", title="Editorial",
        description="Restrained, typographic, lots of air. Good for design and "
                    "documentation tools.",
        tone_hint="Editorial and calm. Large type, generous space, few elements "
                  "per screen. Let one idea land before the next.",
        example="open-design", motif="artboards",
        palette={"bg": [8, 9, 12], "accent": [120, 190, 255], "support": [255, 200, 120]},
    ),
    "research": Template(
        name="research", title="Research",
        description="Green on deep green-black. Flow diagrams and stage "
                    "pipelines; good for agent and workflow systems.",
        tone_hint="Systems-focused. Show the flow: stages, hand-offs, what runs "
                  "where. Green accent, amber support.",
        example="deer-flow", motif="flow",
        palette={"bg": [6, 13, 12], "accent": [34, 214, 158], "support": [240, 190, 90]},
    ),
    "safe-deterministic": Template(
        name="safe-deterministic", title="Safe (no code generation)",
        description="Renders from the content data with five fixed archetypes. "
                    "No model-written drawing code, so it always produces a video.",
        tone_hint="", example="ruflo", motif="flow", deterministic=True,
        palette={"bg": [9, 9, 18], "accent": [124, 124, 248], "support": [64, 224, 208]},
    ),
}


@lru_cache(maxsize=1)
def discover() -> dict[str, Template]:
    """Built-ins plus any directory dropped into app/templates/."""
    found = dict(BUILTIN)
    for entry in sorted(TEMPLATE_DIR.iterdir()):
        manifest = entry / "template.yaml"
        if not entry.is_dir() or not manifest.exists():
            continue
        data = yaml.safe_load(manifest.read_text()) or {}
        name = data.get("name", entry.name)
        found[name] = Template(
            name=name,
            title=data.get("title", name),
            description=data.get("description", ""),
            tone_hint=data.get("tone_hint", ""),
            example=data.get("example", "ruflo"),
            deterministic=bool(data.get("deterministic", False)),
            palette=data.get("palette", {}),
            motif=data.get("motif", "flow"),
            directory=entry,
        )
    return found


def load_template(name: str) -> Template:
    templates = discover()
    if name in templates:
        return templates[name]
    raise KeyError(f"unknown template {name!r}; available: {', '.join(sorted(templates))}")


def list_templates() -> list[dict]:
    return [t.as_dict() for t in discover().values()]
