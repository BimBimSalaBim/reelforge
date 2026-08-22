# ---------------------------------------------------------------
# ledger.py -- the "Ledger" storyboard template.
#
# A deliberately different design language from sbkit's "Bloom". Every axis
# is inverted, so the two read as different films rather than two palettes:
#
#   Bloom (sbkit.py)                Ledger (this file)
#   ------------------------------  ------------------------------------
#   centred column                  left-aligned, hung off a vertical rule
#   rounded cards, radial glow      hairline rules and whitespace
#   scenes replace one another      a scene index accumulates in the gutter
#   fade up + slide                 horizontal wipe out of the rule
#   a sweep line crosses on a cut   the rule flashes, the index advances
#   thump · swish · tick · sweep    click · rule · latch · shift
#
# It imports `kit` and nothing else -- in particular NOT sbkit -- so the two
# templates cannot affect each other. ReelForge only knows kit/sbkit/timing,
# so nothing in this file is reachable from a generated storyboard, which is
# exactly the intent: new work opts in, existing work is untouched.
# ---------------------------------------------------------------
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit
from kit import (W, H, FPS, MARGIN, CAP_Y, f, m, clamp, lin, eo3, eo4, eob,
                 pulse, rgba, mix, tw, text, wrap, radial)

WHITE = (255, 255, 255)

# ---- the grid ---------------------------------------------------------
GUT_X      = 118    # scene index numerals live in the left gutter
RULE_X     = 180    # the spine: one hairline, full height
CX         = 232    # content left edge, hung off the spine
RIGHT      = 996    # safe right edge
RIGHT_LOW  = 932    # below y 1000 the platform button column starts at 960
HEAD_Y     = 176    # slug + counter row
HEAD_RULE  = 228
TITLE_Y    = 292    # scene headline
STAGE_Y0   = 392    # first content row
STAGE_Y1   = 1400   # last usable row above the caption band
SPINE_Y0   = 150
SPINE_Y1   = 1440

def right_edge(y):
    """The usable right edge at a given height. Text below y 1000 must clear
    the platform action-button column (x 960-1080); rules and fills may pass
    under it. See DEVELOPMENT.md's safe-area note."""
    return RIGHT_LOW if y >= 1000 else RIGHT


class Theme:
    """Ledger's own theme. Duplicated from sbkit rather than imported: the
    whole point of this module is that it shares no state with Bloom."""
    def __init__(self, bg, accent, accent_hi, pale, support,
                 muted=(146, 150, 158), dim=(98, 103, 112), faint=(44, 48, 55),
                 grid=(30, 34, 40), rule=(58, 64, 74),
                 ok=(110, 225, 180), warn=(240, 190, 96), bad=(255, 104, 116)):
        self.bg = bg; self.accent = accent; self.accent_hi = accent_hi
        self.pale = pale; self.support = support
        self.muted = muted; self.dim = dim; self.faint = faint
        self.grid = grid; self.rule = rule
        self.ok = ok; self.warn = warn; self.bad = bad
        # kit expects these names; Ledger draws no cards, but wrap() and a few
        # kit helpers still read the palette.
        self.card = (16, 18, 22); self.border = rule
        self.glow = faint

    def apply(self):
        kit.set_palette(BG=self.bg, ORANGE=self.accent, ORANGE_HI=self.accent_hi,
                        CREAM=self.pale, MUTED=self.muted, DIM=self.dim,
                        FAINT=self.faint, CARD=self.card, BORDER=self.border,
                        GREEN=self.ok, AMBER=self.warn, RED=self.bad)


# ---- ground -----------------------------------------------------------
def build_ground(th, seed=5, grid=True, step=54):
    """Flat, not bloomed. A faint engineering grid, a slight downward
    darkening so captions sit on darker ground, and grain -- the grain is the
    one thing carried over from Bloom, because it is what stops a flat field
    banding after the platform re-encodes it."""
    a = np.zeros((H, W, 3), np.float32)
    a[:, :] = th.bg
    if grid:
        g = np.array(th.grid, np.float32)
        for x in range(0, W, step):
            a[:, x] += g * 0.55
        for y in range(0, H, step):
            a[y, :] += g * 0.55
        for x in range(0, W, step * 4):
            a[:, x] += g * 0.45
        for y in range(0, H, step * 4):
            a[y, :] += g * 0.45
    a *= np.linspace(1.06, 0.82, H, dtype=np.float32)[:, None, None]
    rng = np.random.RandomState(seed)
    a += rng.normal(0, 2.0, (H, W, 1)).astype(np.float32)
    a += rng.normal(0, 0.85, (H, W, 3)).astype(np.float32)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


# ---- per-frame chrome -------------------------------------------------
def chrome(ov, d, t, th, total, slug, scenes, idx):
    """The spine, the header row, and the accumulating scene index.

    `scenes` is the storyboard's scene table; `idx` the current index. The
    index is the structural idea of this template: past scenes stay legible
    in the gutter, so the reel visibly accumulates instead of replacing."""
    d.line((RULE_X, SPINE_Y0, RULE_X, SPINE_Y1), fill=rgba(th.rule, 0.85), width=2)
    # progress runs down the spine, not across the top
    py = SPINE_Y0 + (SPINE_Y1 - SPINE_Y0) * clamp(t / total)
    d.line((RULE_X, SPINE_Y0, RULE_X, py), fill=rgba(th.accent, 0.55), width=2)

    text(d, (CX, HEAD_Y), slug, m(25), th.dim, 1.0, 2, "lm")
    text(d, (RIGHT, HEAD_Y), f"{idx+1:02d}/{len(scenes):02d}",
         m(25, "bold"), th.muted, 1.0, 2, "rm")
    d.line((RULE_X, HEAD_RULE, RIGHT, HEAD_RULE), fill=rgba(th.rule, 0.75), width=2)

    for i, sc in enumerate(scenes):
        y = STAGE_Y0 + i * 58
        if y > SPINE_Y1 - 40:
            break
        live = (i == idx)
        past = (i < idx)
        # past must be clearly more present than future -- the index is the
        # structural idea here, and dim-vs-faint alone did not read.
        col = th.accent_hi if live else (th.muted if past else th.faint)
        text(d, (GUT_X, y), f"{i+1:02d}", m(27, "bold" if live else "reg"),
             col, 1.0, 1, "rm")
        if live:
            d.line((GUT_X + 14, y, RULE_X - 8, y), fill=rgba(th.accent_hi, 0.9), width=3)
        elif past:
            d.line((GUT_X + 20, y, RULE_X - 12, y), fill=rgba(th.rule, 0.95), width=2)


def advance(ov, d, t, cuts, th):
    """The transition. No sweep across the frame: the spine flashes and a tick
    travels down it, which is the same gesture as the index advancing."""
    for c in cuts:
        k = lin(t, c, c + 0.34)
        if 0 < k < 1:
            d.line((RULE_X, SPINE_Y0, RULE_X, SPINE_Y1),
                   fill=rgba(th.accent_hi, 0.45 * (1 - k)), width=3)
            y = int(SPINE_Y0 + eo3(k) * (SPINE_Y1 - SPINE_Y0))
            d.line((RULE_X - 16, y, RULE_X + 40, y),
                   fill=rgba(th.accent_hi, 0.85 * (1 - k)), width=4)


# ---- captions ---------------------------------------------------------
def captions(ov, d, t, chunks, th):
    """Same placement as Bloom -- bottom centre, word-synced -- because that is
    the highest-leverage thing in the pipeline and moving it would cost
    retention. Restyled only: hard corners and a left accent tick."""
    cur = None; prev = None
    for c in chunks:
        if c["s"] - 0.06 <= t <= c["e"] + 0.05:
            cur = c; break
        if c["e"] < t:
            prev = c
    a = 1.0
    if cur is None:
        if prev is None: return
        if t - prev["e"] > 0.85: return
        cur = prev; a = 1.0 - lin(t, prev["e"] + 0.45, prev["e"] + 0.85)
    fo = f(54, "bold")
    wl = [x["w"] for x in cur["ws"]]
    sp = fo.getlength(" "); wid = [fo.getlength(x) for x in wl]
    tot = sum(wid) + sp * (len(wl) - 1)
    x = 540 - tot / 2
    pad = 26; asc, _ = fo.getmetrics()
    y0 = CAP_Y - asc * 0.62 - 15; y1 = CAP_Y + asc * 0.42 + 15
    d.rectangle((int(x - pad), int(y0), int(x + tot + pad), int(y1)),
                fill=rgba((7, 8, 10), 0.74 * a))
    d.rectangle((int(x - pad), int(y0), int(x - pad + 6), int(y1)),
                fill=rgba(th.accent, 0.95 * a))
    for wd, ww, wob in zip(wl, wid, cur["ws"]):
        live = wob["s"] - 0.04 <= t <= wob["e"] + 0.04
        text(d, (x, CAP_Y), wd, fo, th.accent_hi if live else WHITE, a, 0, "lm")
        if live:
            d.rectangle((int(x), int(CAP_Y + asc * 0.40),
                         int(x + ww), int(CAP_Y + asc * 0.40) + 3),
                        fill=rgba(th.accent_hi, 0.85 * a))
        x += ww + sp


# ---- entrances --------------------------------------------------------
def wk(t, t0, dur=0.32):
    """Wipe progress. Ledger's only entrance -- no upward slide."""
    return eo4(lin(t, t0, t0 + dur))


def wipe(ov, fn, box, k):
    """Draw `fn(layer, draw)` and reveal it left to right by k.

    The mask is a rectangle, not an alpha ramp, so text arrives sharp-edged
    like a line being set rather than fading in."""
    if k <= 0.002: return
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fn(lay, ImageDraw.Draw(lay))
    if k >= 0.998:
        ov.alpha_composite(lay); return
    x0, y0, x1, y1 = (int(v) for v in box)
    xw = int(x0 + (x1 - x0) * k)
    if xw <= x0: return
    ov.alpha_composite(lay.crop((x0, y0, xw, y1)), (x0, y0))


# ---- components -------------------------------------------------------
def heading(ov, d, txt, t, t0, th, y=TITLE_Y, size=52, col=None, track=2):
    """The scene headline. Left-aligned off the spine, wiped in."""
    k = wk(t, t0, 0.30)
    wipe(ov, lambda L, D: text(D, (CX, y), txt, f(size, "bold"),
                               col or WHITE, 1.0, track, "lm"),
         (CX - 4, y - size, RIGHT + 4, y + size), k)
    return k


def rule_line(ov, d, t, t0, th, y, x0=CX, x1=RIGHT, dur=0.30, col=None, w=2, a=0.8):
    """A hairline that draws itself. Ledger's substitute for a card border."""
    k = wk(t, t0, dur)
    if k <= 0.01: return k
    d.line((x0, y, x0 + (x1 - x0) * k, y), fill=rgba(col or th.rule, a), width=w)
    return k


def row(ov, d, t, t0, th, y, label, value=None, lit=0.0, h=76,
        lsize=34, vsize=28, mono_value=True, col=None):
    """One ledger row: label left, value right, hairline underneath.

    This is the workhorse -- it replaces Bloom's `tile` and `statcard`. Rows
    are what make four different repos fit one template: token sinks, graph
    edges, memory tiers and feature lists are all ledgers."""
    k = wk(t, t0, 0.28)
    if k <= 0.01: return k
    acc = col or th.accent
    re = right_edge(y)

    def draw(L, D):
        if lit > 0.02:
            D.rectangle((CX - 22, y - h / 2, re, y + h / 2),
                        fill=rgba(acc, 0.07 * lit))
            D.rectangle((CX - 22, y - h / 2, CX - 16, y + h / 2),
                        fill=rgba(acc, 0.95 * lit))
        text(D, (CX, y), label, f(lsize, "bold"),
             mix((136, 142, 152), WHITE, max(lit, 0.62)), 1.0, 1, "lm")
        if value:
            text(D, (re, y), value, (m if mono_value else f)(vsize),
                 mix(th.dim, th.accent_hi, lit), 0.95, 0, "rm")
    wipe(ov, draw, (CX - 24, y - h / 2 - 2, re + 2, y + h / 2 + 2), k)
    d.line((CX - 22, y + h / 2, re, y + h / 2), fill=rgba(th.rule, 0.55 * k), width=2)
    return k


def entry(ov, d, t, t0, th, y, value, label=None, note=None, vsize=104, col=None):
    """A display figure with a rule under it and a mono annotation. Ledger's
    counter: no glow, no gradient -- the size is the emphasis."""
    k = wk(t, t0, 0.34)
    if k <= 0.01: return k

    def draw(L, D):
        text(D, (CX, y), str(value), f(vsize, "bold"), col or WHITE, 1.0, 0, "lm")
        if label:
            text(D, (CX, y + vsize * 0.62), label, f(26, "bold"),
                 th.muted, 1.0, 4, "lm")
    wipe(ov, draw, (CX - 4, y - vsize, RIGHT, y + vsize), k)
    d.line((CX, y + vsize * 0.42, CX + (RIGHT - CX) * k, y + vsize * 0.42),
           fill=rgba(col or th.accent, 0.85), width=3)
    if note:
        text(d, (RIGHT, y - vsize * 0.30), note, m(26), th.dim, 0.9 * k, 0, "rt")
    return k


def counter(ov, d, t, t0, th, y, target, label=None, dur=1.15, vsize=112, col=None):
    """A figure that ticks up, set as a ledger entry."""
    p = eo4(lin(t, t0, t0 + dur))
    if p <= 0.0: return 0.0
    n = int(round(target * p))
    s = f"{n:,}" if target >= 1000 else str(n)
    text(d, (CX, y), s, f(vsize, "bold"), col or WHITE, 1.0, 0, "lm")
    d.line((CX, y + vsize * 0.42, CX + (RIGHT - CX) * min(1.0, p * 1.4),
            y + vsize * 0.42), fill=rgba(col or th.accent, 0.85), width=3)
    if label:
        text(d, (CX, y + vsize * 0.62), label, f(26, "bold"), th.muted, 1.0, 4, "lm")
    return p


def meter(ov, d, th, box, frac, col=None, bg=None, h=None):
    """A flat bar. Square ends -- Ledger has no rounded geometry anywhere."""
    x0, y0, x1, y1 = box
    d.rectangle((int(x0), int(y0), int(x1), int(y1)),
                fill=rgba(bg or (26, 30, 36), 0.9))
    w = (x1 - x0) * clamp(frac)
    if w > 1:
        d.rectangle((int(x0), int(y0), int(x0 + w), int(y1)),
                    fill=rgba(col or th.accent, 0.92))


def stamp(ov, d, t, t0, th, xy, txt, size=32, col=None, track=4, pad=(20, 12)):
    """A hard-cornered box. Replaces Bloom's pill; corners are the tell."""
    k = wk(t, t0, 0.26)
    if k <= 0.01: return k
    x, y = xy
    fo = f(size, "bold"); wd = tw(txt, fo, track)
    c = col or th.accent

    def draw(L, D):
        D.rectangle((x, y - size / 2 - pad[1], x + wd + pad[0] * 2, y + size / 2 + pad[1]),
                    outline=rgba(c, 0.9), width=3)
        text(D, (x + pad[0], y), txt, fo, c, 1.0, track, "lm")
    wipe(ov, draw, (x - 2, y - size, x + wd + pad[0] * 2 + 4, y + size), k)
    return k


def quote(ov, d, t, t0, th, y, lines, attrib=None, size=32, col=None):
    """A pulled quote, marked by a rule down its left edge rather than marks."""
    k = wk(t, t0, 0.34)
    if k <= 0.01: return k
    lh = size + 16
    h = lh * len(lines)

    def draw(L, D):
        D.rectangle((CX, y, CX + 5, y + h), fill=rgba(col or th.accent, 0.9))
        for i, ln in enumerate(lines):
            text(D, (CX + 30, y + i * lh + lh / 2), ln, f(size, "med"),
                 col or th.pale, 1.0, 0, "lm")
        if attrib:
            text(D, (CX + 30, y + h + 30), attrib, m(25), th.dim, 0.9, 0, "lm")
    wipe(ov, draw, (CX - 2, y - 8, RIGHT, y + h + 56), k)
    return k


def note(ov, d, t, t0, th, y, txt, size=27, col=None, right=False):
    """A mono annotation. Ledger's small print."""
    k = wk(t, t0, 0.28)
    if k <= 0.01: return k
    re = right_edge(y)
    if right:
        text(d, (re, y), txt, m(size), col or th.dim, 0.95 * k, 0, "rm")
    else:
        wipe(ov, lambda L, D: text(D, (CX, y), txt, m(size),
                                   col or th.dim, 0.95, 0, "lm"),
             (CX - 2, y - size, re, y + size), k)
    return k


_SCROLL_CACHE = {}


def load_scroll(path):
    """A tall page capture at frame width, decoded once per process."""
    if path not in _SCROLL_CACHE:
        try:
            img = Image.open(path).convert("RGB")
            if img.width != W:
                img = img.resize((W, int(img.height * W / img.width)),
                                 Image.LANCZOS)
            _SCROLL_CACHE[path] = img
        except Exception:
            _SCROLL_CACHE[path] = None
    return _SCROLL_CACHE[path]


#: Frame-pixels per second. Matches slab.SCROLL_SPEED so the same repo pans at
#: the same rate whichever template a reel is built on.
SCROLL_SPEED = 400


def scroll(ov, d, t, t0, dur, th, path, y=STAGE_Y0, height=None,
           speed=SCROLL_SPEED, hold=0.12, label=None):
    """Pan a page capture inside the stage band, hung off the spine.

    Ledger keeps its margins, so this is a framed panel rather than Slab's
    full bleed -- the spine and the gutter index stay visible beside it, which
    is the whole silhouette of this template.
    """
    img = load_scroll(path)
    if img is None:
        return False
    band = height or (STAGE_Y1 - y)
    p = clamp((t - t0) / max(dur, 0.01))
    travel = min(max(0, img.height - band), speed * max(dur * (1.0 - hold), 0.01))
    q = clamp((p - hold) / max(1.0 - hold, 0.05))
    q = q * q * (3.0 - 2.0 * q)
    top = int(q * travel)
    crop = img.crop((0, top, W, min(top + band, img.height)))
    x0, x1 = CX - 22, RIGHT
    ov.paste(crop.resize((int(x1 - x0), band)), (int(x0), int(y)))
    d.rectangle((x0, y, x0 + 6, y + band), fill=rgba(th.accent, 0.95))
    if label:
        text(d, (CX, y - 34), label, m(27, "bold"), th.accent, 1.0, 2, "lt")
    return True


def endcard(ov, d, t, t0, th, wordmark, sub, url, url2, cta,
            mark_size=140, follow="Follow for more"):
    """Ledger's end card. Left-aligned like everything else, and it keeps the
    standing sign-off -- see DEVELOPMENT.md."""
    k = wk(t, t0, 0.36)
    wipe(ov, lambda L, D: text(D, (CX, 470), wordmark, f(mark_size, "bold"),
                               WHITE, 1.0, 0, "lm"),
         (CX - 4, 470 - mark_size, W, 470 + mark_size), k)
    k2 = wk(t, t0 + 0.18, 0.32)
    if k2 > 0.01:
        d.line((CX, 566, CX + (RIGHT - CX) * k2, 566), fill=rgba(th.accent, 0.9), width=4)
        text(d, (CX, 618), sub, m(34), th.muted, k2, 2, "lm")
    k3 = wk(t, t0 + 0.34, 0.32)
    if k3 > 0.01:
        text(d, (CX, 716), url, m(38, "bold"), WHITE, k3, 0, "lm")
        if url2:
            text(d, (CX, 774), url2, m(30), th.accent, k3, 0, "lm")
    k4 = wk(t, t0 + 0.52, 0.32)
    if k4 > 0.01:
        fo = f(34, "bold"); wd = tw(cta, fo, 4)
        d.rectangle((CX, 880, CX + wd + 56, 962), fill=rgba(th.accent, 0.94 * k4))
        text(d, (CX + 28, 921), cta, fo, (8, 9, 10), k4, 4, "lm")
    k5 = wk(t, t0 + 0.70, 0.34)
    if k5 > 0.01:
        text(d, (CX, 1064), follow, f(46, "bold"), WHITE, k5, 2, "lm")
        d.line((CX, 1104, CX + tw(follow, f(46, "bold"), 2) * k5, 1104),
               fill=rgba(th.accent, 0.8), width=3)
    k6 = wk(t, t0 + 0.88, 0.34)
    if k6 > 0.01:
        text(d, (CX, 1168), "↻  WATCH AGAIN", m(27), th.dim, k6, 3, "lm")
