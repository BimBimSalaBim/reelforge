"""Uploaded screenshots, prepared for a 1080x1920 frame.

A repo screenshot is wide and a reel is very tall. A full-bleed 9:16 crop of a
1920x1080 screenshot keeps about 608 of its 1920 pixels, which is right for
zooming into a terminal block and wrong for a dashboard nobody can then read.
So an image carries how it wants to be shown:

  panel  the whole image inside a rounded card on the reel's own ground, the
         way the shipped storyboards present a terminal. Nothing is lost, and
         the crop is for trimming chrome -- a browser bar, a desktop background.
  full   edge to edge, the viewer picks which 9:16 slice. Highest impact, and
         the one that throws information away.

The crop is stored normalised (0-1 of the original) rather than in pixels, so it
survives the source being re-uploaded at a different size, and so the browser
that drew it and the renderer that applies it agree without sharing a unit.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: The frame the reel is rendered at.
FRAME_W, FRAME_H = 1080, 1920

#: A panel image spans the full frame width. Insetting it to the safe width
#: left margins down both sides and made a wide screenshot smaller than it
#: needed to be; edge to edge is what a screenshot in a reel should do.
PANEL_W = FRAME_W

#: And it is capped in height, because a screenshot is not always wide. A
#: 1600x4200 README capture scaled to the frame width is 2835px tall -- taller
#: than the whole 1920 frame, which is exactly how one ended up overflowing off
#: the top of a rendered reel. Anything past this is cropped, and the cropper is
#: where that choice is made rather than left to the renderer.
#:
#: 1060 rather than 1120 so that a panel of the maximum height still fits the
#: band above the burned-in captions (380..1440). At 1120 the tallest panels
#: overlapped the captions no matter where they were placed, which is the one
#: case the position control could not fix.
PANEL_MAX_H = 1060
PANEL_MIN_H = 280

#: Anything larger is downscaled on upload. A 6000px screenshot costs memory in
#: every one of the render's parallel chunk processes and cannot show more than
#: the frame can resolve.
MAX_SOURCE_EDGE = 3000

#: What a browser will actually hand us, and what PIL will actually open.
ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MAX_BYTES = 12 * 1024 * 1024

#: Wider than this and a full-bleed crop would discard most of the image, so
#: the cropper opens on `panel` instead. 1.2 is past square, not merely
#: landscape -- a nearly-square screenshot survives a 9:16 crop.
WIDE_RATIO = 1.2


#: What an uploaded image is of. The label is what the form asks for, the
#: eyebrow is what the screen says above it, and the order is where it belongs
#: in the arc -- the repo before what it prints, because that is the order the
#: script explains them in.
#:
#: Asking on the form is worth more than inferring later: nothing in the pixels
#: distinguishes a README screenshot from a terminal, and a wrong guess puts
#: "WHAT IT PRINTS" over a repository page.
ROLES: dict[str, dict] = {
    "repo": {"label": "Repository screenshot",
             "hint": "The GitHub or Hugging Face page, a README, the file tree",
             "eyebrow": "THE REPO", "order": 1},
    "app": {"label": "The app running",
            "hint": "The interface, a dashboard, the UI in use",
            "eyebrow": "THE INTERFACE", "order": 2},
    "output": {"label": "Output screenshot",
               "hint": "A terminal, logs, the result of running it",
               "eyebrow": "WHAT IT PRINTS", "order": 3},
    "other": {"label": "Something else",
              "hint": "A diagram, a benchmark chart, anything worth showing",
              "eyebrow": "A LOOK", "order": 4},
}

DEFAULT_ROLE = "other"


def role_order(role: str) -> int:
    return ROLES.get(role, ROLES[DEFAULT_ROLE])["order"]


def role_eyebrow(role: str) -> str:
    return ROLES.get(role, ROLES[DEFAULT_ROLE])["eyebrow"]


class ImageError(ValueError):
    """An upload that cannot be used, with a reason worth showing."""


@dataclass(frozen=True)
class Crop:
    """A rectangle in fractions of the source image."""

    x: float = 0.0
    y: float = 0.0
    w: float = 1.0
    h: float = 1.0

    def clamped(self) -> "Crop":
        """Inside the image, and never zero-sized."""
        w = min(max(self.w, 0.02), 1.0)
        h = min(max(self.h, 0.02), 1.0)
        return Crop(x=min(max(self.x, 0.0), 1.0 - w),
                    y=min(max(self.y, 0.0), 1.0 - h), w=w, h=h)

    def pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        crop = self.clamped()
        left, top = round(crop.x * width), round(crop.y * height)
        return (left, top,
                max(left + 1, round((crop.x + crop.w) * width)),
                max(top + 1, round((crop.y + crop.h) * height)))


def default_fit(width: int, height: int) -> str:
    """`panel` for anything meaningfully wider than it is tall."""
    return "panel" if height and width / height >= WIDE_RATIO else "full"


def panel_aspect_limits() -> tuple[float, float]:
    """The band a panel image must land inside, as width/height ratios."""
    return FRAME_W / PANEL_MAX_H, FRAME_W / PANEL_MIN_H


def default_crop(width: int, height: int, fit: str) -> Crop:
    """The largest centred rectangle of the right shape.

    Opening the cropper on something already correct means an upload that needs
    no attention needs no attention.
    """
    if not width or not height:
        return Crop()
    if fit == "panel":
        # a wide screenshot is kept whole; a tall one is cropped to the deepest
        # band the frame can show, centred, and the cropper moves it from there
        widest = FRAME_W / PANEL_MAX_H
        if width / height >= widest:
            return Crop()
        h = (width / widest) / height
        return Crop(x=0.0, y=max(0.0, (1 - h) / 2), w=1.0, h=min(h, 1.0))
    target = FRAME_W / FRAME_H             # 9:16
    source = width / height
    if source > target:                    # too wide: keep full height
        w = target / source
        return Crop(x=(1 - w) / 2, y=0.0, w=w, h=1.0)
    h = source / target                    # too tall: keep full width
    return Crop(x=0.0, y=(1 - h) / 2, w=1.0, h=h)


def inspect(path: Path) -> tuple[int, int]:
    """Size of an upload, and the check that it is an image at all."""
    from PIL import Image, UnidentifiedImageError

    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ImageError(
            f"{path.name}: only {', '.join(sorted(ALLOWED_SUFFIXES))} are supported"
        )
    if path.stat().st_size > MAX_BYTES:
        raise ImageError(
            f"{path.name} is {path.stat().st_size / 1e6:.1f} MB; the limit is "
            f"{MAX_BYTES / 1e6:.0f} MB"
        )
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            return image.size
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageError(f"{path.name} is not an image the renderer can open") from exc


def shrink_source(path: Path) -> tuple[int, int]:
    """Downscale a very large upload in place, and return the new size.

    Every parallel chunk process opens this file, so a 6000px screenshot is paid
    for once per chunk, and it cannot show more than 1080 pixels of detail.
    """
    from PIL import Image

    with Image.open(path) as image:
        image = image.convert("RGBA")
        if max(image.size) <= MAX_SOURCE_EDGE:
            return image.size
        scale = MAX_SOURCE_EDGE / max(image.size)
        resized = image.resize(
            (round(image.width * scale), round(image.height * scale)),
            Image.Resampling.LANCZOS)
        resized.save(path.with_suffix(".png"), "PNG")
    if path.suffix.lower() != ".png":
        path.unlink(missing_ok=True)
    return resized.size


def prepare(source: Path, target: Path, *, fit: str, crop: Crop) -> tuple[int, int]:
    """Apply the crop and scale to what the frame will draw, once.

    Doing this at upload time rather than at render time means the renderer
    pastes a correctly-sized bitmap instead of resampling a large source in
    every chunk process, and it means what you approved in the cropper is
    exactly the file that gets drawn.
    """
    from PIL import Image

    with Image.open(source) as image:
        image = image.convert("RGBA")
        cropped = image.crop(crop.pixels(*image.size))

        if fit == "full":
            out = _cover(cropped, FRAME_W, FRAME_H)
        else:
            # Uniform scale to the full frame width, then the height is capped.
            # Stretching non-uniformly would fill the frame too, and would make
            # every letter in a screenshot the wrong shape.
            scale = PANEL_W / cropped.width
            tall = cropped.resize(
                (PANEL_W, max(1, round(cropped.height * scale))),
                Image.Resampling.LANCZOS)
            if tall.height > PANEL_MAX_H:
                top = (tall.height - PANEL_MAX_H) // 2
                tall = tall.crop((0, top, PANEL_W, top + PANEL_MAX_H))
            out = tall

        target.parent.mkdir(parents=True, exist_ok=True)
        out.save(target, "PNG")
        return out.size


def _cover(image, width: int, height: int):
    """Scale to fill and centre-crop the overflow.

    The stored crop already chose the region; this only absorbs the rounding
    between its aspect and the frame's, so nothing is letterboxed.
    """
    from PIL import Image

    scale = max(width / image.width, height / image.height)
    scaled = image.resize((max(width, round(image.width * scale)),
                           max(height, round(image.height * scale))), Image.Resampling.LANCZOS)
    left = (scaled.width - width) // 2
    top = (scaled.height - height) // 2
    return scaled.crop((left, top, left + width, top + height))
