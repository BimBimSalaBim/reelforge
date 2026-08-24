"""Turn a generated picture into a cover ground the typography survives.

`covers.py`'s procedural ground is dark by construction: a near-black field,
a couple of soft blooms, a vertical falloff. A diffusion model's picture is
not -- it has a bright subject somewhere, and the wordmark at y 545 or the
hook at y 890 lands on top of it. So the picture is darkened toward the
spec's `bg` with a vertical curve that leaves the top band (where the motif
used to be) the most visible and the text bands the most covered, and the
cover's own grain goes back on so the platform re-encode does not band it.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

W, H = 1080, 1920

#: How much of the picture shows, by band. Keys are y in the frame; values
#: are the fraction of the picture kept (the rest is the spec's bg colour).
#: The wordmark sits at 545, the hook at 890-1170, the stat cards at 1216-1394.
VISIBILITY = [(0, 0.62), (300, 0.52), (520, 0.30), (700, 0.34), (860, 0.24),
              (1200, 0.26), (1420, 0.22), (1600, 0.30), (1920, 0.38)]


def _curve(height: int) -> np.ndarray:
    ys = np.array([y for y, _ in VISIBILITY], np.float32)
    vs = np.array([v for _, v in VISIBILITY], np.float32)
    return np.interp(np.arange(height, dtype=np.float32), ys, vs)


def cover_fit(image: Image.Image, width: int = W, height: int = H) -> Image.Image:
    """Scale to fill and centre-crop, never letterbox."""
    scale = max(width / image.width, height / image.height)
    resized = image.resize((max(1, round(image.width * scale)),
                            max(1, round(image.height * scale))), Image.LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def prepare_backdrop(path: Path, spec: dict, *, blur: float = 1.2, seed: int = 3) -> Image.Image:
    """An RGBA 1080x1920 ground, the shape `covers.ground()` returns."""
    with Image.open(path) as raw:
        picture = cover_fit(raw.convert("RGB"))
    if blur > 0:
        picture = picture.filter(ImageFilter.GaussianBlur(blur))
    a = np.asarray(picture, np.float32)
    bg = np.array(spec["bg"], np.float32)
    keep = _curve(H)[:, None, None]
    # slight desaturation toward bg so an off-palette picture still reads as
    # the reel's own colour
    out = a * keep + bg * (1.0 - keep)
    rng = np.random.RandomState(seed)
    out += rng.normal(0, 2.0, (H, W, 1)).astype(np.float32)
    out += rng.normal(0, 0.9, (H, W, 3)).astype(np.float32)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
