# ---------------------------------------------------------------
# slab.py -- the "Slab" storyboard template.
#
# The third design language, and the one built to fix what the other two
# have in common rather than merely to look different from them.
#
#   Bloom (sbkit)      Ledger (ledger)     Slab (this file)
#   -----------------  ------------------  -----------------------------
#   near-black         near-black          full-bleed saturated FIELD
#   centred cards      left rules          one statement, set huge
#   8-15 elements      8-15 elements       at most 5 per frame
#   min type ~23px     min type ~24px      min type 34px, headline 96-150
#   glow + fade up     wipe from a spine   the type RISES into place
#   content column     content column      edge to edge, so no dead band
#   colour = accent    colour = accent     colour = the scene itself
#
# Two consequences worth stating. The field changes per scene, so the reel
# has a visible arc in a muted feed and is recognisable as a thumbnail. And
# `ink_for()` picks black or white type from the field's own luminance, so a
# legibility mistake is not possible by construction -- which is the real
# reason this reads better than a hand-tuned dark palette.
#
# Imports `kit` and nothing else: not sbkit, not ledger. ReelForge only knows
# kit/sbkit/timing, so nothing here is reachable from a generated storyboard.
# ---------------------------------------------------------------
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit
from kit import (W, H, FPS, MARGIN, f, m, clamp, lin, eo3, eo4, eob, pulse,
                 rgba, mix, tw, text, wrap)

# ---- the grid ---------------------------------------------------------
CX        = 96      # content left edge -- wider margin than the other two
CR        = 984     # content right edge
CR_LOW    = 932     # below y 1000 the platform button column starts at 960
RAIL_Y    = 128     # segmented progress, just under the top chrome
HEAD_Y    = 400     # first headline baseline
HEAD_LEAD = 118     # headline line height at the default size
BODY_Y    = 900     # the single support block starts here
FOOT_Y    = 1524    # slug and scene number

def right_edge(y):
    """Usable right edge at a height. Text below y 1000 must clear the
    platform action-button column (x 960-1080, y 1000-1700)."""
    return CR_LOW if y >= 1000 else CR

def ink_for(rgb, dark=(15,15,18), light=(255,255,255)):
    """Black or white type, chosen from the field's own relative luminance.
    This is why Slab cannot produce an illegible frame by accident."""
    def _l(c):
        c = c/255.0
        return c/12.92 if c <= 0.04045 else ((c+0.055)/1.055)**2.4
    L = 0.2126*_l(rgb[0]) + 0.7152*_l(rgb[1]) + 0.0722*_l(rgb[2])
    return dark if L > 0.42 else light


class Theme:
    """Slab's theme is a RAMP, not an accent. `fields` is one colour per
    scene; everything else is derived, including the type colour."""
    def __init__(self, fields, mark=None, dim_mix=0.42, rule_mix=0.24):
        assert len(fields) >= 2, "Slab needs at least two field colours"
        self.fields = list(fields)
        self.mark = mark or fields[-1]
        self.dim_mix = dim_mix
        self.rule_mix = rule_mix

    def field(self, i):
        return self.fields[i % len(self.fields)]

    def ink(self, i):
        return ink_for(self.field(i))

    def dim(self, i):
        """Type that recedes but stays legible -- mixed toward the field, never
        below a readable contrast because the mix is capped."""
        return mix(self.ink(i), self.field(i), self.dim_mix)

    def rule(self, i):
        return mix(self.ink(i), self.field(i), 1.0-self.rule_mix)

    def apply(self):
        fl = self.field(0)
        kit.set_palette(BG=fl, ORANGE=self.mark, ORANGE_HI=self.mark,
                        CREAM=ink_for(fl), MUTED=mix(ink_for(fl),fl,0.40),
                        DIM=mix(ink_for(fl),fl,0.55),
                        CARD=fl, BORDER=mix(ink_for(fl),fl,0.75))


# ---- the field --------------------------------------------------------
def build_field(colour, seed=5, grain=1.1, fall=0.055):
    """A flat colour field with a slight vertical settle and fine grain.

    The grain is much lower amplitude than Bloom's or Ledger's: on a light
    field, grain that size reads as noise rather than as texture. It is still
    present, because a perfectly flat field is what bands after the platform
    re-encodes it."""
    a = np.zeros((H, W, 3), np.float32)
    a[:, :] = colour
    a *= (1.0 - np.linspace(0.0, fall, H, dtype=np.float32))[:, None, None]
    rng = np.random.RandomState(seed)
    a += rng.normal(0, grain, (H, W, 1)).astype(np.float32)
    a += rng.normal(0, grain*0.45, (H, W, 3)).astype(np.float32)
    return Image.fromarray(np.clip(a,0,255).astype(np.uint8), "RGB").convert("RGBA")

_FIELD_CACHE = {}
def field_for(th, i, seed=5):
    key = (tuple(th.field(i)), seed)
    if key not in _FIELD_CACHE:
        _FIELD_CACHE[key] = build_field(th.field(i), seed)
    return _FIELD_CACHE[key]


# ---- motion -----------------------------------------------------------
def rk(t, t0, dur=0.42):
    return eo4(lin(t, t0, t0+dur))

def rise(ov, fn, box, k, dy=None):
    """Slab's signature entrance: content RISES into place from behind the
    bottom of its own box, hard-edged. It reads as type being set, and it is
    the reason no element needs to fade -- a fade at this size looks like a
    render bug rather than a choice."""
    if k <= 0.002: return
    x0,y0,x1,y1 = (int(v) for v in box)
    if dy is None: dy = (y1-y0)
    lay = Image.new("RGBA", (W,H), (0,0,0,0))
    fn(lay, ImageDraw.Draw(lay))
    off = int(round((1.0-k)*dy))
    if off <= 0:
        ov.alpha_composite(lay.crop((x0,y0,x1,y1)), (x0,y0)); return
    src_y0 = y0 - off
    if src_y0 + (y1-y0) <= 0: return
    piece = lay.crop((x0, max(0,src_y0), x1, max(0,src_y0)+(y1-y0)))
    ov.alpha_composite(piece, (x0, y0))


# ---- chrome -----------------------------------------------------------
def rail(ov, d, t, th, i, n, prog):
    """Segmented progress: one segment per scene, the live one filling. The
    only persistent chrome, and it doubles as the scene index.

    `prog` is progress THROUGH THE CURRENT SCENE, 0..1 -- not overall runtime.
    Three states with a real contrast step between them, because at 12px a
    two-state rail is unreadable: pending is barely there, spent is half, live
    is full ink."""
    ink, fl = th.ink(i), th.field(i)
    gap, hgt = 8, 12
    seg = (CR-CX - gap*(n-1)) / n
    for s in range(n):
        x = CX + s*(seg+gap)
        tone = 0.82 if s > i else (0.42 if s < i else 0.82)
        d.rectangle((int(x), RAIL_Y, int(x+seg), RAIL_Y+hgt),
                    fill=rgba(mix(ink, fl, tone), 1.0))
    x = CX + i*(seg+gap)
    d.rectangle((int(x), RAIL_Y, int(x+seg*clamp(prog)), RAIL_Y+hgt),
                fill=rgba(ink, 1.0))

def footer(ov, d, th, i, slug, n_total):
    ink, fl = th.ink(i), th.field(i)
    text(d, (CX, FOOT_Y), slug, m(30), mix(ink,fl,0.34), 1.0, 2, "lm")
    text(d, (CR_LOW, FOOT_Y), f"{i+1:02d}/{n_total:02d}",
         f(40,"bold"), mix(ink,fl,0.30), 1.0, 2, "rm")

def cut(ov, d, t, cuts, th, idx_at):
    """The transition: a hard-edged band of the INCOMING field sweeps down.
    A cut reads as a page turning, which is the point of a field-based
    language -- nothing crossfades.

    CALL THIS BEFORE `rail` AND `footer`. The band is opaque, so drawing it
    after the chrome makes the rail and slug blink out on every cut. 0.15s,
    not longer: the band covers the outgoing content before the incoming
    content rises, so a slow sweep is just a bare field on screen."""
    for c in cuts:
        k = lin(t, c-0.15, c)
        if 0 < k < 1:
            nxt = th.field(idx_at(c+0.01))
            y = int(H*eo4(k))
            d.rectangle((0, 0, W, y), fill=rgba(nxt, 1.0))
            d.rectangle((0, y, W, y+6), fill=rgba(ink_for(nxt), 0.55))


# ---- components -------------------------------------------------------
def statement(ov, d, lines, t, t0, th, i, y=HEAD_Y, size=104, lead=None,
              stagger=0.10, col=None, track=-1):
    """The one big thing on screen. Up to three lines, each rising in turn."""
    lead = lead or int(size*1.13)
    ink = col or th.ink(i)
    for j, ln in enumerate(lines):
        s = size; fo = f(s, "bold")
        while tw(ln, fo, track) > (CR-CX) and s > 44:
            s -= 4; fo = f(s, "bold")
        yy = y + j*lead
        k = rk(t, t0 + j*stagger, 0.44)
        # the box must clear ascenders AND descenders: text is centred on yy
        # by the "lm" anchor, so 0.98 up / 0.62 down covers both at any size.
        rise(ov, (lambda Y,F,T: (lambda L,D: text(D,(CX,Y),T,F,ink,1.0,track,"lm")))(yy,fo,ln),
             (CX-8, yy-int(s*0.98), CR+8, yy+int(s*0.62)), k)
    return rk(t, t0+(len(lines)-1)*stagger, 0.44)

def figure(ov, d, value, label, t, t0, th, i, y=BODY_Y, size=190, col=None,
           note=None):
    """One enormous number. Slab's answer to a stat card."""
    ink = col or th.ink(i)
    s = size; fo = f(s,"bold")
    while tw(str(value), fo) > (CR-CX) and s > 70:
        s -= 6; fo = f(s,"bold")
    k = rk(t, t0, 0.46)
    rise(ov, lambda L,D: text(D,(CX,y),str(value),fo,ink,1.0,0,"lt"),
         (CX-8, y-12, CR+8, y+int(s*1.34)), k)
    k2 = rk(t, t0+0.14, 0.40)
    if k2 > 0.01:
        ly = y + int(s*1.16)
        d.rectangle((CX, ly, CX+int((CR-CX)*k2), ly+7), fill=rgba(ink, 0.92))
        text(d, (CX, ly+52), label, f(38,"bold"), th.dim(i), k2, 5, "lt")
    if note:
        k3 = rk(t, t0+0.28, 0.38)
        if k3 > 0.01:
            text(d, (CX, y+int(size*1.16)+124), note, m(32), th.dim(i), k3, 0, "lt")
    return k

def counter(ov, d, t, t0, th, i, y, target, label=None, dur=1.05, vsize=190,
            col=None, note=None):
    """A figure that ticks up to its target. Same layout as `figure`, so the
    two are interchangeable in a catalogue slot -- the only difference is
    whether the number arrives counted or set."""
    p = eo4(lin(t, t0, t0+dur))
    if p <= 0.0: return 0.0
    n = int(round(target*p))
    txt = f"{n:,}" if target >= 1000 else str(n)
    ink = col or th.ink(i)
    s = vsize; fo = f(s, "bold")
    while tw(txt, fo) > (CR-CX) and s > 70:
        s -= 6; fo = f(s, "bold")
    text(d, (CX, y), txt, fo, ink, 1.0, 0, "lt")
    ry = y + int(s*1.14)
    d.rectangle((CX, ry, CX + int((CR-CX)*min(1.0, p*1.4)), ry+7), fill=rgba(ink, 0.95))
    if label:
        text(d, (CX, ry+52), label, f(38, "bold"), th.dim(i), min(1.0, p*3), 5, "lt")
    if note:
        text(d, (CX, ry+124), note, m(32), th.dim(i), min(1.0, p*3), 0, "lt")
    return p


def rows(ov, d, items, t, t0, th, i, y=BODY_Y, h=118, gap=10, stagger=0.11,
         lsize=44, vsize=34, lit=None):
    """At most three or four. Big enough to read on a phone held at arm's
    length, which is the whole reason this template exists."""
    ink, fl = th.ink(i), th.field(i)
    for j,(lab,val) in enumerate(items):
        yy = y + j*(h+gap)
        k = rk(t, t0 + j*stagger, 0.40)
        if k <= 0.01: continue
        on = 0.0 if lit is None else float(lit[j])
        re = right_edge(yy+h/2)
        def draw(L,D,yy=yy,lab=lab,val=val,on=on,re=re):
            if on > 0.02:
                D.rectangle((CX, yy, re, yy+h), fill=rgba(ink, 0.10*on))
            D.rectangle((CX, yy+h-4, re, yy+h), fill=rgba(mix(ink,fl,0.62), 1.0))
            text(D,(CX+ (26 if on>0.02 else 0), yy+h*0.56), lab,
                 f(lsize,"bold"), ink, 1.0, 0, "lm")
            if val:
                text(D,(re-8, yy+h*0.56), val, m(vsize,"bold"),
                     mix(ink,fl,0.28), 1.0, 0, "rm")
        rise(ov, draw, (CX-8, yy-6, re+8, yy+h+8), k)

def pair(ov, d, left, right, t, t0, th, i, y=BODY_Y, size=120, gap=44):
    """A two-column comparison at display size -- before/after, them/us."""
    ink, fl = th.ink(i), th.field(i)
    cw = (CR-CX-gap)/2
    for j,(head,body,strong) in enumerate((left,right)):
        x = CX + j*(cw+gap)
        k = rk(t, t0 + j*0.14, 0.44)
        if k <= 0.01: continue
        def draw(L,D,x=x,head=head,body=body,strong=strong):
            D.rectangle((x, y, x+cw, y+8), fill=rgba(ink if strong else mix(ink,fl,0.6), 1.0))
            text(D,(x, y+64), head, f(34,"bold"),
                 ink if strong else th.dim(i), 1.0, 4, "lt")
            s=size; fo=f(s,"bold")
            while tw(body,fo) > cw and s>52: s-=4; fo=f(s,"bold")
            text(D,(x, y+118), body, fo, ink if strong else th.dim(i), 1.0, 0, "lt")
        rise(ov, draw, (x-6, y-6, x+cw+6, y+150+int(size*1.42)), k)

def chip(ov, d, xy, txt, t, t0, th, i, size=36, solid=True, col=None):
    """A solid tag. Slab has no outlines anywhere -- fills only."""
    k = rk(t, t0, 0.34)
    if k <= 0.01: return k
    ink, fl = th.ink(i), th.field(i)
    c = col or ink
    x,y = xy
    fo = f(size,"bold"); wd = tw(txt,fo,4)
    def draw(L,D):
        if solid:
            D.rectangle((x, y-size*0.86, x+wd+52, y+size*0.62), fill=rgba(c,1.0))
            text(D,(x+26, y-size*0.12), txt, fo, ink_for(c), 1.0, 4, "lm")
        else:
            D.rectangle((x, y+size*0.5, x+wd, y+size*0.5+6), fill=rgba(c,1.0))
            text(D,(x, y-size*0.12), txt, fo, c, 1.0, 4, "lm")
    rise(ov, draw, (x-6, int(y-size*1.1), int(x+wd+60), int(y+size*0.9)), k)
    return k

def band(ov, d, lines, t, t0, th, i, y, size=52, col=None, attrib=None):
    """A full-bleed band for a quote or a caution -- the one element allowed
    to break the margin, so it lands like a stop sign."""
    k = rk(t, t0, 0.44)
    if k <= 0.01: return k
    fl = th.field(i)
    c = col or th.ink(i)
    on = ink_for(c)
    lead = int(size*1.26)
    # 96 of padding put the attribution hard against the last line's
    # descenders; 150 clears it at every size the band is used at.
    h = lead*len(lines) + (150 if attrib else 96)
    def draw(L,D):
        D.rectangle((0, y, W, y+h), fill=rgba(c,1.0))
        for j,ln in enumerate(lines):
            s=size; fo=f(s,"bold")
            while tw(ln,fo) > (CR-CX): s-=3; fo=f(s,"bold")
            text(D,(CX, y+56+j*lead), ln, fo, on, 1.0, 0, "lt")
        if attrib:
            text(D,(CX, y+h-46), attrib, m(28), mix(on,c,0.32), 1.0, 2, "lm")
    rise(ov, draw, (0, y-4, W, y+h+6), k, dy=h)
    return k

def command(ov, d, txt, t, t0, th, i, y):
    """The runnable line. Mono, but at 40px -- not the 24px both other
    templates use, which is where they lose a phone viewer."""
    k = rk(t, t0, 0.38)
    if k <= 0.01: return k
    ink, fl = th.ink(i), th.field(i)
    s=40; fo=m(s,"bold")
    while tw(txt,fo) > (CR-CX-70) and s>26: s-=2; fo=m(s,"bold")
    def draw(L,D):
        D.rectangle((CX, y-52, CX+12, y+30), fill=rgba(ink,1.0))
        text(D,(CX+38, y-12), txt, fo, ink, 1.0, 0, "lm")
    rise(ov, draw, (CX-8, y-64, CR+8, y+44), k)
    return k

_SCROLL_CACHE = {}


def load_scroll(path):
    """A tall page capture, scaled to frame width. Cached: the renderer calls
    frame() a thousand times and this must not be a thousand decodes."""
    if path not in _SCROLL_CACHE:
        if not os.path.exists(path):
            _SCROLL_CACHE[path] = None
        else:
            try:
                img = Image.open(path).convert("RGB")
                if img.width != W:
                    img = img.resize((W, int(img.height * W / img.width)),
                                     Image.LANCZOS)
                _SCROLL_CACHE[path] = img
            except Exception:
                _SCROLL_CACHE[path] = None
    return _SCROLL_CACHE[path]


#: Pan rate in frame-pixels per second. This is the control that matters.
#: The first version had no rate at all -- it fitted the whole capture into
#: whatever time the scene had, which for an 8768px GitHub page in a 6s scene
#: meant ~1600 px/s and read as a blur. A page going past at this rate is
#: legible as a page; raise it for a faster flick, lower it to let someone
#: actually read a line. 520 was the first setting; 400 on request.
SCROLL_SPEED = 400


def scroll(ov, d, t, t0, dur, th, i, path, speed=SCROLL_SPEED, hold=0.12,
           label=None):
    """Pan a tall page capture downward at a FIXED rate, full bleed.

    Distance is `speed x time`, not "the whole page however long that takes",
    so how fast it reads never depends on how tall the repo's README happens
    to be. If the page is short enough to finish inside the scene it stops at
    the bottom and holds there; if it is not, it simply gets as far as it gets,
    which is the right trade -- the screen is establishing the repo, not asking
    anyone to read it.

    Holds at the top for `hold` of the scene first, so the repo's name and
    header are readable rather than smearing past, and eases in and out of the
    travel: a linear pan starts and stops with a visible jerk at this size.
    """
    img = load_scroll(path)
    if img is None:
        return False
    p = clamp((t - t0) / max(dur, 0.01))
    travel_secs = max(dur * (1.0 - hold), 0.01)
    travel = min(max(0, img.height - H), speed * travel_secs)
    q = clamp((p - hold) / max(1.0 - hold, 0.05))
    q = q * q * (3.0 - 2.0 * q)                      # smoothstep, eased both ends
    y = int(q * travel)
    ov.paste(img.crop((0, y, W, min(y + H, img.height))), (0, 0))

    # The capture is a white page, so the rail and the footer would otherwise
    # sit on it at whatever contrast the page happens to give them. Each scrim
    # is SOLID field colour across the band the chrome actually occupies, then
    # a gradient out of it. Getting this wrong is easy to miss: a first pass
    # faded to 0 by y 250 and started again at y 1600, which left the rail at
    # 128 half-covered and the footer at 1524 not covered at all.
    solid_top, fade_top = 176, 340          # rail sits at RAIL_Y 128
    fade_bot, solid_bot = 1330, FOOT_Y - 40  # footer sits at FOOT_Y 1524
    fill = th.field(i)
    top = Image.new("RGBA", (W, fade_top), (0, 0, 0, 0))
    td = ImageDraw.Draw(top)
    for row in range(fade_top):
        a = 1.0 if row < solid_top else 1.0 - (row - solid_top) / max(
            1, fade_top - solid_top)
        td.line((0, row, W, row), fill=rgba(fill, a))
    ov.alpha_composite(top, (0, 0))

    bot = Image.new("RGBA", (W, H - fade_bot), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bot)
    for row in range(H - fade_bot):
        y_abs = fade_bot + row
        a = 1.0 if y_abs >= solid_bot else (y_abs - fade_bot) / max(
            1, solid_bot - fade_bot)
        bd.line((0, row, W, row), fill=rgba(fill, a))
    ov.alpha_composite(bot, (0, fade_bot))
    if label:
        chip(ov, d, (CX, 236), label, t, t0 + 0.10, th, i, size=32)
    return True


def endcard(ov, d, t, t0, th, i, wordmark, sub, url, cta,
            mark_size=170, follow="Follow for more"):
    ink, fl = th.ink(i), th.field(i)
    k = statement(ov, d, [wordmark], t, t0, th, i, y=470, size=mark_size)
    k2 = rk(t, t0+0.16, 0.40)
    if k2 > 0.01:
        d.rectangle((CX, 540, CX+int((CR-CX)*k2), 550), fill=rgba(ink,0.95))
        text(d, (CX, 612), sub, f(40,"med"), th.dim(i), k2, 0, "lt")
    k3 = rk(t, t0+0.30, 0.40)
    if k3 > 0.01:
        text(d, (CX, 736), url, m(36,"bold"), ink, k3, 0, "lt")
    chip(ov, d, (CX, 900), cta, t, t0+0.44, th, i, size=38)
    k5 = rk(t, t0+0.62, 0.44)
    if k5 > 0.01:
        rise(ov, lambda L,D: text(D,(CX,1060),follow,f(70,"bold"),ink,1.0,-1,"lt"),
             (CX-8, 1040, CR+8, 1150), k5)
    k6 = rk(t, t0+0.80, 0.38)
    if k6 > 0.01:
        text(d, (CX, 1230), "REPLAY", f(32,"bold"), th.dim(i), k6, 6, "lt")
