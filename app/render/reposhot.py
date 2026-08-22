"""Capture a repository page as one tall image, for use as scrolling B-roll.

Why a single full-page screenshot rather than a screen recording: the reel is
drawn frame by frame in PIL, so a video would have to be decoded back into
frames anyway. One tall PNG is ~200x fewer captures, pans at sub-pixel
smoothness with any easing the storyboard likes, costs one file instead of a
few hundred, and decouples capture time from scene duration entirely. A repo
page is static, so nothing is lost by not recording motion.

The capture is deliberately conservative: it declines rather than guesses.
A page that will not load, a viewport-height page with nothing to scroll, or a
missing browser all return None, and the caller simply does not get a B-roll
screen. A reel without one is fine; a reel with a broken one is not.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

#: The reel's own width, so the capture needs no horizontal rescale later.
WIDTH = 1080
#: Viewport height used while capturing. Taller than the reel frame so lazy
#: content below the fold has been laid out before the full-page shot.
VIEWPORT_H = 1920
#: Past this the page is trimmed. A very long README would otherwise pan far
#: too fast to read, or far too slowly to be worth the screen.
MAX_HEIGHT = 14000
#: Below this there is nothing to scroll and a static screenshot would be the
#: honest choice -- so the scroll screen is declined.
MIN_HEIGHT = 2600
#: Selectors hidden before the shot: sticky chrome smears when panned, and a
#: cookie banner is not what anyone wants eight seconds into a reel.
HIDE = (
    ".js-notice, .flash-full, .js-cookie-consent-banner, "
    "[data-testid='cookie-consent-banner'], .Popover, .js-header-wrapper "
    ".AppHeader, header.AppHeader, .js-sticky, .sticky-content"
)


#: Where to look for a browser when Playwright's own managed download is not
#: usable. On this machine `playwright install` refuses ("does not support
#: chromium on mac12") while an older Chromium from a previous install sits in
#: the cache and drives fine, so discovery beats assuming.
def _executable() -> str | None:
    """A Chromium that actually exists, or None to use Playwright's own."""
    import glob
    import os

    cache = Path(os.path.expanduser("~/Library/Caches/ms-playwright"))
    patterns = [
        str(cache / "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"),
        str(cache / "chromium-*/chrome-linux/chrome"),
        str(cache / "chromium_headless_shell-*/chrome-mac/headless_shell"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/chromium",
        "/usr/bin/google-chrome",
    ]
    found: list[str] = []
    for pattern in patterns:
        found.extend(sorted(glob.glob(pattern), reverse=True))
    for candidate in found:
        if os.access(candidate, os.X_OK):
            return candidate
    return None


@dataclass
class RepoShot:
    path: Path
    width: int
    height: int

    @property
    def pans(self) -> bool:
        return self.height > VIEWPORT_H


def capture(url: str, target: Path, *, timeout_ms: int = 45_000,
            settle_ms: int = 1_800) -> RepoShot | None:
    """Screenshot `url` full-page at reel width. None if it cannot be done."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.info("playwright is not installed; skipping the repo scroll")
        return None

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as pw:
            launch: dict = {"args": ["--force-color-profile=srgb"]}
            try:
                browser = pw.chromium.launch(**launch)
            except Exception:
                # Playwright's managed browser is missing or unsupported here;
                # fall back to any Chromium already on the machine.
                exe = _executable()
                if not exe:
                    log.info("no usable chromium found; skipping the repo scroll")
                    return None
                log.info("using chromium at %s", exe)
                browser = pw.chromium.launch(executable_path=exe, **launch)
            try:
                page = browser.new_context(
                    viewport={"width": WIDTH, "height": VIEWPORT_H},
                    device_scale_factor=1,
                    reduced_motion="reduce",
                ).new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                # walk the page once so lazy images and syntax highlighting
                # have rendered before the full-page shot is taken
                page.evaluate(
                    "async () => {"
                    "  const step = window.innerHeight * 0.9;"
                    "  for (let y = 0; y < document.body.scrollHeight; y += step) {"
                    "    window.scrollTo(0, y);"
                    "    await new Promise(r => setTimeout(r, 90));"
                    "  }"
                    "  window.scrollTo(0, 0);"
                    "}"
                )
                page.add_style_tag(content=f"{HIDE} {{ display: none !important; }} "
                                           "* { animation: none !important; "
                                           "transition: none !important; }")
                page.wait_for_timeout(settle_ms)
                page.screenshot(path=str(target), full_page=True, type="png")
            finally:
                browser.close()
    except Exception as exc:                     # capture is best-effort
        log.warning("repo capture failed for %s: %s", url, exc)
        return None

    if not target.exists():
        return None

    from PIL import Image

    with Image.open(target) as img:
        w, h = img.size
        if h > MAX_HEIGHT:
            img.crop((0, 0, w, MAX_HEIGHT)).save(target)
            h = MAX_HEIGHT
    if h < MIN_HEIGHT:
        log.info("repo page is only %dpx tall; not worth a scroll screen", h)
        target.unlink(missing_ok=True)
        return None
    return RepoShot(path=target, width=w, height=h)
