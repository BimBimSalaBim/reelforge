"""Record where text lands, so collisions can be detected.

A frame can be the right size, sit inside the safe area, and carry plenty of
drawn pixels while being unreadable because two pieces of text are on top of
each other. Density checks cannot see that -- overlapping text has roughly the
density of text.

`kit.text` and `kit.grad_text` are the only ways a storyboard puts words on a
frame, so wrapping them collects every string with its box. Comparing boxes then
finds collisions exactly, with no guessing from pixels.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TextBox:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: int
    alpha: float

    @property
    def area(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)

    def intersection(self, other: "TextBox") -> float:
        width = min(self.x1, other.x1) - max(self.x0, other.x0)
        height = min(self.y1, other.y1) - max(self.y0, other.y0)
        return width * height if width > 0 and height > 0 else 0.0


@dataclass
class Recorder:
    boxes: list[TextBox] = field(default_factory=list)

    def reset(self) -> None:
        self.boxes.clear()

    def add(self, text: str, xy, font, alpha: float, track: float, anchor: str) -> None:
        text = str(text or "")
        if not text.strip() or alpha <= 0.05:
            return  # invisible text cannot collide with anything
        try:
            left, top, right, bottom = font.getbbox(text)
            width = (right - left) + track * max(0, len(text) - 1)
            height = bottom - top
            size = getattr(font, "size", int(height)) or int(height)
        except Exception:
            return

        x, y = float(xy[0]), float(xy[1])
        horizontal = (anchor or "lt")[0]
        vertical = (anchor or "lt")[1] if len(anchor or "lt") > 1 else "t"
        if horizontal == "m":
            x -= width / 2
        elif horizontal == "r":
            x -= width
        if vertical == "m":
            y -= height / 2
        elif vertical == "b":
            y -= height
        self.boxes.append(TextBox(text, x, y, x + width, y + height, int(size), alpha))


#: Two boxes count as colliding when this much of the smaller one is covered.
#: Text is drawn tight, so a genuine layout leaves clear air between lines; a
#: fifth of a box buried is already unreadable.
OVERLAP_LIMIT = 0.20


def collisions(boxes: list[TextBox], limit: float = OVERLAP_LIMIT) -> list[dict]:
    """Pairs of visible strings that sit on top of each other."""
    found: list[dict] = []
    for index, first in enumerate(boxes):
        for second in boxes[index + 1 :]:
            if first.text == second.text and abs(first.y0 - second.y0) < 1:
                continue  # the same string drawn twice for a shadow or glow
            overlap = first.intersection(second)
            if overlap <= 0:
                continue
            smaller = min(first.area, second.area)
            if smaller <= 0:
                continue
            share = overlap / smaller
            if share >= limit:
                found.append({
                    "a": first.text[:48], "b": second.text[:48],
                    "share": round(share, 2),
                    "box_a": [round(first.x0), round(first.y0),
                              round(first.x1), round(first.y1)],
                    "box_b": [round(second.x0), round(second.y0),
                              round(second.x1), round(second.y1)],
                })
    return found


def install(kit, recorder: Recorder) -> None:
    """Wrap kit's two text primitives to record every string drawn."""
    original_text = kit.text
    original_grad = kit.grad_text

    def text(d, xy, txt, font, fill, a=1.0, track=0.0, anchor="lt"):
        recorder.add(txt, xy, font, a, track, anchor)
        return original_text(d, xy, txt, font, fill, a, track, anchor)

    def grad_text(base, xy, txt, font, c_top, c_bot, a=1.0, anchor="mt", track=0.0):
        recorder.add(txt, xy, font, a, track, anchor)
        return original_grad(base, xy, txt, font, c_top, c_bot, a, anchor, track)

    kit.text = text
    kit.grad_text = grad_text
