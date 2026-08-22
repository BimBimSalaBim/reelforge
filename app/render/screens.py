"""A catalogue of screen layouts, and the picker that assigns one per scene.

The deterministic renderer used to carry four layouts in a list and cycle them.
With five or six scenes that means the third screen is the first one again --
the harness reel showed the same headline at 2s and at 25s, and DEVELOPMENT.md's
"one idea per screen, let information accumulate" is exactly what that breaks.

So layouts are data. Each declares what content it needs and what it draws, the
picker scores the catalogue against the scene and takes the best unused one, and
adding a layout is appending to a YAML file. The generated storyboard receives
fully-resolved screens -- every string already measured, fitted and trimmed here,
where the fonts are -- so the module it executes has no layout logic at all.

Slot kinds map onto sbkit components, which is the whole point: this adds
arrangement, not drawing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

SCREEN_DIR = Path(__file__).resolve().parent / "screens"

#: How much weight each extra appearance of a repeating layout gives up.
REPEAT_DECAY = 12

#: What a layout can ask for, and how to count it in the content bundle.
CAPABILITIES = {
    "hook_lines": lambda c: len(c.get("hook_lines") or []),
    "stats": lambda c: len(c.get("stats") or []),
    "facts": lambda c: len(c.get("facts") or []),
    "commands": lambda c: len(c.get("commands") or []),
    "points": lambda c: len(c.get("point_lines") or []),
    "tagline": lambda c: 1 if c.get("tagline") else 0,
    "quote": lambda c: 1 if c.get("quote") else 0,
    "counter": lambda c: 1 if c.get("counter") else 0,
    "images": lambda c: len(c.get("images") or []),
}


@dataclass
class Slot:
    kind: str
    options: dict = field(default_factory=dict)


@dataclass
class Layout:
    id: str
    slots: list[Slot]
    eyebrow: str = ""
    #: "stats>=3" -- the content must supply at least three stats
    needs: list[str] = field(default_factory=list)
    #: higher wins when several layouts fit. Openers and closers are pinned.
    weight: int = 10
    #: a capability this layout consumes one of per appearance. Three uploaded
    #: screenshots should be three screens, not the same screen three times, so
    #: the layout enters the rotation once per item and each appearance takes
    #: the next one via its variant index.
    repeat_with: str = ""
    role: str = "body"          # opener | body | closer

    def satisfied_by(self, content: dict) -> bool:
        return all(_meets(rule, content) for rule in self.needs)


def _meets(rule: str, content: dict) -> bool:
    for operator in (">=", "=="):
        if operator in rule:
            name, _, count = rule.partition(operator)
            have = CAPABILITIES.get(name.strip(), lambda _c: 0)(content)
            want = int(count)
            return have >= want if operator == ">=" else have == want
    return CAPABILITIES.get(rule.strip(), lambda _c: 0)(content) > 0


@lru_cache(maxsize=8)
def catalogue(name: str = "default") -> list[Layout]:
    """Load a catalogue by name, falling back to the shared default."""
    path = SCREEN_DIR / f"{name}.yaml"
    if not path.exists():
        path = SCREEN_DIR / "default.yaml"
    raw = yaml.safe_load(path.read_text()) or []
    return [
        Layout(
            id=entry["id"],
            eyebrow=entry.get("eyebrow", ""),
            needs=list(entry.get("needs") or []),
            weight=int(entry.get("weight", 10)),
            repeat_with=entry.get("repeat_with", ""),
            role=entry.get("role", "body"),
            slots=[Slot(kind=s.pop("kind"), options=s) for s in
                   (dict(x) for x in entry.get("slots") or [])],
        )
        for entry in raw
    ]


def pick(scene_count: int, content: dict,
         name: str = "default") -> list[tuple[Layout, int]]:
    """Assign (layout, variant) to each scene, not repeating while it can help.

    The opener is pinned -- the hook must be fully legible at frame 0, which is
    the first retention rule in DEVELOPMENT.md -- and so is the closer, because every
    reel ends on a save prompt. The middle is filled by weight from whatever the
    content can actually support: a repo with no install command never gets the
    terminal screen rather than getting an empty one.

    When the catalogue runs out before the scenes do, a layout comes back with a
    higher variant index, and the slot renderers use it to show the *next* slice
    of the same list. Repeating a layout is acceptable; repeating a screenful of
    text is what made the old cycle look broken.
    """
    usable = [layout for layout in catalogue(name) if layout.satisfied_by(content)]
    by_role: dict[str, list[Layout]] = {"opener": [], "body": [], "closer": []}
    for layout in usable:
        by_role[layout.role].append(layout)
    for group in by_role.values():
        group.sort(key=lambda item: (-item.weight, item.id))

    if not by_role["opener"] or not by_role["closer"]:
        raise ValueError(
            "the screen catalogue must contain at least one opener and one "
            "closer that this content satisfies"
        )

    if not scene_count:
        return []

    chosen: list[tuple[Layout, int]] = [(by_role["opener"][0], 0)]

    # Each appearance of a repeating layout is worth a little less than the
    # last, so repeats compete with other layouts instead of always winning
    # (three screenshots in a row, reading as one long screen) or always losing
    # (two of your three uploads never shown). A second screenshot at 95 still
    # outranks a fact column at 55; a fourth does not.
    scored: list[tuple[float, str, Layout]] = []
    for layout in by_role["body"] or by_role["opener"]:
        available = (CAPABILITIES.get(layout.repeat_with, lambda _c: 1)(content)
                     if layout.repeat_with else 1)
        for appearance in range(max(1, available)):
            scored.append((-(layout.weight - appearance * REPEAT_DECAY),
                           layout.id, layout))
    scored.sort()
    body: list[Layout] = [layout for _score, _id, layout in scored]
    seen: dict[str, int] = {}
    for index in range(max(0, scene_count - 2)):
        layout = body[index % len(body)]
        variant = seen.get(layout.id, -1) + 1
        seen[layout.id] = variant
        chosen.append((layout, variant))
    if scene_count > 1:
        chosen.append((by_role["closer"][0], 0))
    return chosen[:scene_count]
