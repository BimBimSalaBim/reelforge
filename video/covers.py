#!/usr/bin/env python3
"""Reel cover art (1080x1920). One spec per repo; shared skeleton, own style.

    python3 covers.py            # render all
    python3 covers.py dsh        # render one

Layout note: Instagram shows a centre-square crop of the cover in the grid, so
the wordmark and the hook both sit inside y 420-1500 and survive that crop.
The top band carries a per-repo background motif instead of dead space.
"""
import sys, os, math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import kit
from kit import (W,H,MARGIN,f,m,rgba,mix,tw,text,grad_text,wrap,radial,put_glow,
                 card,pill,hline,clamp)
OUT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ============================ specs ============================
# One entry per cover. These four are examples, one per layout, kept as the
# reference for the shape each renderer expects -- the covers actually shipped
# are job output and live in their job directory, not here.
#
# The app never edits this table: app/render/shim_cover.py injects a generated
# spec into SPECS at render time and calls the matching renderer. The mirror of
# this shape on the app side is CoverSpec in app/models/content.py, so if a
# field changes here it changes there too.
#
#   layout omitted  bloom   centred column, rounded cards, radial glow
#   layout="stack"  stack   left rail carrying the subject's own structure
#   layout="ledger" ledger  left-aligned off a spine, hairline rules, no glow
#   layout="slab"   slab    full-bleed colour field, one statement set huge
SPECS={

# -- bloom: the default. Three stat cards and a command bar.
"example":dict(
  file="example-reel.png",
  bg=(9,9,18), accent=(124,124,248), accent_hi=(168,168,255), pale=(222,222,255),
  glow=(56,48,160), support=(64,224,208), motif="flow",
  eyebrow="THE ONE-LINE PROMISE",
  wordmark="example", mark_font=("disp",210), mark_track=-4,
  sub="owner/example  ·  example.dev",
  kicker="The sentence the reel opens on.",
  hook=["Three short lines,", "each one landing", "on its own beat."],
  stats=[("12K","STARS"),("40","CONTRIBUTORS"),("MIT","LICENCE")],
  # A real, runnable command. Set prompt=False and the bar renders as a
  # feature strip instead of faking a shell prompt.
  cmd="npx example init", prompt=True,
  foot_l="OPEN SOURCE · MIT", foot_r="RUNS ANYWHERE"),

# -- stack: for a release whose structure is the story. `rail` picks what the
#    left rail draws; omit it for plain layer bars.
"example-stack":dict(
  file="example-stack-reel.png", layout="stack",
  bg=(9,7,18), accent=(150,108,255), accent_hi=(198,172,255), pale=(232,222,255),
  glow=(74,38,170), support=(94,234,212), motif="curves",
  tag="DENSE 27B · NATIVE VISION",
  band_note="16 × (3 × DeltaNet → FFN) → 1 × (Attention → FFN)",
  version="EXAMPLE3", wordmark="27B", mark_font=("disp",232), mark_track=-6,
  sub="owner/example-27b  ·  Apache-2.0",
  kicker="What the release actually is.",
  hook=["64 layers.", "16 run full", "attention."],
  stats=[("48:16","RATIO"),("262K","CONTEXT"),("90.3","BENCHMARK")],
  cmd='vllm serve "owner/example-27b"', prompt=True,
  foot_l="APACHE-2.0", foot_r="LONG CONTEXT"),

# -- ledger: rows rather than stat cards, and a slug at the top right. Note
#    `grid` and `rule` in place of `glow`; this layout draws no bloom.
"example-ledger":dict(
  file="example-ledger-reel.png", layout="ledger",
  bg=(12,11,10), accent=(232,124,48), accent_hi=(255,178,110),
  pale=(246,230,214), support=(120,190,255),
  grid=(34,30,26), rule=(64,56,48),
  slug="owner/example", tag="THE ANGLE",
  kicker="the lower-case line that sets the tone",
  wordmark="example", mark_size=150,
  sub="MIT  ·  one clause about licensing",
  hook=["69 in.", "19 out.", "Same answer."],
  rows=[("tokens saved","33.2%"),("agents supported","30+"),
        ("stars","100,244")],
  cmd="npx skills add owner/example", prompt=True,
  foot_l="MIT", foot_r="READ THE LICENCE"),

# -- slab: at most five elements. `field` is the full-bleed background colour,
#    `wordmark` is a list (one entry per line) and `figure` is the one number.
"example-slab":dict(
  file="example-slab-reel.png", layout="slab", field=(232,84,42),
  kicker="BY OWNER  ·  RUST  ·  MIT",
  wordmark=["example"], mark_size=176,
  hook=["Any input file","to clean output."],
  figure=("< 5 ms","MEDIAN, PER DOCUMENT"),
  cmd="npx skills add owner/example",
  foot_l="17,849 STARS · 19 DAYS", foot_r="NO ML. NO NETWORK."),
}

# ============================ motifs ============================
def motif_plugins(base,d,s):
    """a lattice of plugin tiles -- 'everything is a plugin'"""
    rng=np.random.RandomState(4)
    cw,ch,gap=98,98,12
    for r in range(4):
        for c in range(10):
            x=30+c*(cw+gap); y=148+r*(ch+gap)
            if x>W-30: continue
            live=rng.rand()<0.22
            a=(0.5 if live else 0.16)*max(0.0,1.0-r*0.22)
            d.rounded_rectangle((x,y,x+cw,y+ch),radius=16,
                fill=rgba(s["accent"],0.10*a) if live else None,
                outline=rgba(s["accent"] if live else (255,255,255),a*0.55),width=2)
            if live:
                d.ellipse((x+cw/2-5,y+ch/2-5,x+cw/2+5,y+ch/2+5),fill=rgba(s["accent_hi"],a))

def motif_artboards(base,d,s):
    """overlapping artboards, each a different output"""
    rng=np.random.RandomState(9)
    boards=[(60,140,420,330),(300,210,780,470),(560,120,1020,300),(120,330,560,520)]
    for i,(x0,y0,x1,y1) in enumerate(boards):
        col=s["accent"] if i%2 else s["support"]
        a=0.42-i*0.06
        d.rounded_rectangle((x0,y0,x1,y1),radius=14,fill=rgba((255,255,255),0.018),
                            outline=rgba(col,a),width=2)
        d.rectangle((x0+14,y0+14,x0+62,y0+22),fill=rgba(col,a*0.8))
        for k in range(3):
            wq=rng.randint(60,int(max(70,(x1-x0)*0.62)))
            d.rectangle((x0+14,y0+40+k*16,x0+14+wq,y0+46+k*16),
                        fill=rgba((255,255,255),0.05))

def motif_flow(base,d,s):
    """a lead node fanning into sub-agents, then converging"""
    cx,cy=540,300
    nodes=[(150,215),(150,300),(150,385),(400,258),(400,342),(690,300),(930,240),(930,360)]
    edges=[(0,3),(1,3),(1,4),(2,4),(3,5),(4,5),(5,6),(5,7)]
    for a_,b_ in edges:
        x0,y0=nodes[a_]; x1,y1=nodes[b_]
        d.line((x0,y0,x1,y1),fill=rgba(s["accent"],0.26),width=2)
    for i,(x,y) in enumerate(nodes):
        big = i in (5,)
        r=14 if big else 9
        col=s["accent_hi"] if big else s["accent"]
        d.ellipse((x-r,y-r,x+r,y+r),fill=rgba(col,0.55 if big else 0.34))
        if big: put_glow(base,x,y,s["glow"],200,0.30)

def motif_swarm(base,d,s):
    """mesh topology -- agents that find each other"""
    rng=np.random.RandomState(11)
    pts=[(int(90+rng.rand()*900),int(150+rng.rand()*300)) for _ in range(17)]
    for i,(x0,y0) in enumerate(pts):
        for x1,y1 in pts[i+1:]:
            dd=math.hypot(x1-x0,y1-y0)
            if dd<215:
                d.line((x0,y0,x1,y1),fill=rgba(s["accent"],0.30*(1-dd/215)),width=2)
    for i,(x,y) in enumerate(pts):
        r=5+ (5 if i%5==0 else 0)
        col=s["support"] if i%5==0 else s["accent"]
        d.ellipse((x-r,y-r,x+r,y+r),fill=rgba(col,0.50))
def motif_boundary(base,d,s):
    """a sealed enclosure -- the agents work inside, nothing crosses out"""
    x0,y0,x1,y1,r=44,150,W-44,458,24
    def dashed(ax,ay,bx,by,col,a,w=3,dash=24,gap=15):
        L=math.hypot(bx-ax,by-ay)
        for i in range(int(L//(dash+gap))+1):
            t0=i*(dash+gap)/L
            if t0>=1.0: break
            t1=min(1.0,(i*(dash+gap)+dash)/L)
            d.line((ax+(bx-ax)*t0,ay+(by-ay)*t0,ax+(bx-ax)*t1,ay+(by-ay)*t1),
                   fill=rgba(col,a),width=w)
    d.rounded_rectangle((x0,y0,x1,y1),radius=r,fill=rgba((255,255,255),0.015))
    for seg in ((x0+r,y0,x1-r,y0),(x1,y0+r,x1,y1-r),
                (x1-r,y1,x0+r,y1),(x0,y1-r,x0,y0+r)):
        dashed(*seg,s["accent"],0.34)
    # the agents, kept clear of the eyebrow pill that sits inside the box
    hx,hy=540,368
    ring=[(hx+int(255*math.cos(math.radians(v))),hy+int(62*math.sin(math.radians(v))))
          for v in (200,255,310,20,120)]
    for x,y in ring:
        d.line((hx,hy,x,y),fill=rgba(s["accent"],0.30),width=2)
        d.ellipse((x-9,y-9,x+9,y+9),fill=rgba(s["accent"],0.44))
    put_glow(base,hx,hy,s["glow"],250,0.32)
    d.ellipse((hx-16,hy-16,hx+16,hy+16),fill=rgba(s["accent_hi"],0.60))
    # three attempts to leave, each stopped and sealed at the wall
    for i,side in ((0,"l"),(3,"r"),(4,"d")):
        nx,ny=ring[i]
        if side=="l":   ex,ey,bar=x0+30,ny,(x0+3,ny-32,x0+3,ny+32)
        elif side=="r": ex,ey,bar=x1-30,ny,(x1-3,ny-32,x1-3,ny+32)
        else:           ex,ey,bar=nx,y1-26,(nx-32,y1-3,nx+32,y1-3)
        d.line((nx,ny,ex,ey),fill=rgba(s["accent"],0.34),width=2)
        d.ellipse((ex-4,ey-4,ex+4,ey+4),fill=rgba(s["support"],0.55))
        d.line(bar,fill=rgba(s["support"],0.80),width=6)

def motif_egress(base,d,s):
    """lanes meeting one wall -- only the named binary is let through"""
    wx=742
    ys=[288,316,344,372,400,428]
    through=2
    d.line((wx,274,wx,452),fill=rgba(s["accent"],0.36),width=3)
    for i,y in enumerate(ys):
        if i==through:
            d.line((56,y,W-46,y),fill=rgba(s["accent"],0.52),width=3)
            d.ellipse((wx-10,y-10,wx+10,y+10),fill=rgba(s["accent_hi"],0.72))
        else:
            d.line((56,y,wx-18,y),fill=rgba((255,255,255),0.13),width=2)
            for a,b,c,e in ((-9,-9,9,9),(-9,9,9,-9)):
                d.line((wx+a,y+b,wx+c,y+e),fill=rgba(s["support"],0.50),width=4)
    put_glow(base,wx,ys[through],s["glow"],440,0.22)

MOTIFS={"plugins":motif_plugins,"artboards":motif_artboards,
        "flow":motif_flow,"swarm":motif_swarm,
        "boundary":motif_boundary,"egress":motif_egress}

# ============================ renderer ============================
def ground(s):
    a=np.zeros((H,W,3),np.float32); a[:,:]=s["bg"]
    g=s["glow"]
    for cx,cy,rad,col,st,pw in [(200,300,1180,g,0.60,2.2),
                                (960,1700,900,s["support"],0.10,2.5),
                                (540,900,1420,(28,28,40),0.26,1.6)]:
        a+=radial(W,H,cx,cy,rad,pw)[:,:,None]*np.array(col,np.float32)*st
    a*=np.linspace(1.0,0.70,H,dtype=np.float32)[:,None,None]
    rng=np.random.RandomState(3)
    a+=rng.normal(0,2.0,(H,W,1)).astype(np.float32)
    a+=rng.normal(0,0.9,(H,W,3)).astype(np.float32)
    return Image.fromarray(np.clip(a,0,255).astype(np.uint8),"RGB").convert("RGBA")

def render(key):
    s=SPECS[key]
    WHITE=(255,255,255); MUTED=(152,156,170); DIM=(104,110,126)
    CARD=(20,22,32); BORDER=(46,50,66)
    kit.set_palette(BG=s["bg"],ORANGE=s["accent"],ORANGE_HI=s["accent_hi"],
                    CREAM=s["pale"],MUTED=MUTED,DIM=DIM,CARD=CARD,BORDER=BORDER)
    base=ground(s)
    ov=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(ov)
    MOTIFS[s["motif"]](ov,d,s)

    pill(d,540,238,s["eyebrow"],f(30,"bold"),s["accent"],1.0,track=6)

    kind,size=s["mark_font"]
    fo = m(size,"bold") if kind=="mono" else f(size,"bold")
    grad_text(ov,(540,545),s["wordmark"],fo,WHITE,s["pale"],1.0,"mm",s["mark_track"])
    put_glow(ov,540,545,s["glow"],620,0.24)

    avail=W-2*MARGIN
    sf=next((m(z) for z in (31,29,27,25,23) if tw(s["sub"],m(z),2)<=avail),m(23))
    text(d,(540,690),s["sub"],sf,MUTED,1.0,2,"mm")
    hline(d,540-150,540+150,748,s["accent"],0.95,4)

    text(d,(MARGIN,822),s["kicker"],f(40,"med"),MUTED,1.0,0,"lt")
    y=890
    for ln in s["hook"]:
        text(d,(MARGIN,y),ln,f(78,"bold"),WHITE,1.0,0,"lt"); y+=92

    cw=(W-2*MARGIN-32)/3
    for i,(n,lab) in enumerate(s["stats"]):
        x=MARGIN+i*(cw+16); y0=1216
        card(d,(x,y0,x+cw,y0+178),24,CARD,0.88,BORDER,0.95,2)
        put_glow(ov,x+cw/2,y0+70,s["glow"],210,0.13)
        nf=f(64,"bold") if len(n)<=4 else f(52,"bold")
        grad_text(ov,(x+cw/2,y0+34),n,nf,s["accent_hi"],s["accent"],1.0,"mt")
        text(d,(x+cw/2,y0+140),lab,f(24,"bold"),MUTED,1.0,3,"mm")

    box=(MARGIN,1428,W-MARGIN,1528)
    card(d,box,20,CARD,0.80,BORDER,0.9,2)
    if s.get("prompt",True):
        text(d,(MARGIN+34,1478),"›",m(34,"bold"),s["accent"],1.0,0,"lm")
        avail=W-2*MARGIN-110
        # fail soft: shrink as far as needed rather than raising on a long command
        cf=next((m(z) for z in (32,30,28,26,24,22,20) if tw(s["cmd"],m(z))<=avail),m(20))
        text(d,(MARGIN+72,1478),s["cmd"],cf,WHITE,0.95,0,"lm")
    else:
        text(d,(540,1478),s["cmd"],f(28,"bold"),s["accent_hi"],0.95,4,"mm")

    text(d,(MARGIN,1586),s["foot_l"],f(26,"bold"),DIM,1.0,4,"lt")
    text(d,(W-MARGIN,1586),s["foot_r"],f(26,"bold"),s["accent"],1.0,4,"rt")

    base.alpha_composite(ov)
    p=os.path.join(OUT,s["file"])
    base.convert("RGB").save(p)
    print("wrote",p)
    return p

# ================= stack layout (model releases) =================
# A different design language from the tool covers: content hangs off a
# vertical rail that is the model's own hidden layout, and every panel is
# square-cornered with a lit left edge instead of a rounded card.
RAIL_X, RAIL_W = 84, 52
CONTENT_X      = 180

def motif_curves(base,d,s):
    """cost against context length -- n^2 leaves the frame, n does not"""
    x0,y0,x1,y1 = CONTENT_X+16, 190, 1040, 400
    for i in range(5):
        yy=y0+i*(y1-y0)/4
        d.line((x0,yy,x1,yy),fill=rgba((255,255,255),0.035),width=1)
    quad,linr=[],[]
    for i in range(120):
        u=i/119.0
        quad.append((x0+u*(x1-x0), y1-(u**2.3)*(y1-y0)*1.9))
        linr.append((x0+u*(x1-x0), y1-u*(y1-y0)*0.30))
    quad=[pt for pt in quad if pt[1]>=y0-4] or quad[:2]
    d.line(quad,fill=rgba(s["support"],0.34),width=3)
    d.line(linr,fill=rgba(s["accent"],0.62),width=3)
    text(d,(quad[-1][0]+14,y0+4),"O(n^2)",m(24),s["support"],0.55,0,"lt")
    text(d,(x1-6,linr[-1][1]-30),"O(n)",m(24),s["accent"],0.75,0,"rt")

MOTIFS["curves"]=motif_curves

def layer_rail(base,d,s,y0=168,y1=1544,n=64,every=4):
    """the spine: 16 lit full-attention layers, 48 dim Gated DeltaNet ones"""
    put_glow(base,RAIL_X+RAIL_W/2,900,s["glow"],620,0.22)
    pitch=(y1-y0)/n; ch=pitch*0.62
    for i in range(n):
        yy=y0+i*pitch
        box=[int(v) for v in (RAIL_X,yy,RAIL_X+RAIL_W,yy+ch)]
        if (i%every)==every-1:
            d.rounded_rectangle(box,radius=3,fill=rgba(s["accent"],0.90))
        else:
            d.rounded_rectangle(box,radius=3,fill=rgba(s["accent"],0.07),
                                outline=rgba(s["accent"],0.22),width=1)

def filmstrip_rail(base,d,s,y0=168,y1=1544,n=32,cuts=(11,22)):
    """the spine as a strip of shot frames: the cuts are marked, and one
    continuous waveform runs beside it -- picture and sound on the same clock"""
    put_glow(base,RAIL_X+RAIL_W/2,900,s["glow"],620,0.22)
    pitch=(y1-y0)/n; ch=pitch*0.72
    for i in range(n):
        yy=y0+i*pitch; shot=sum(1 for c in cuts if i>=c)
        d.rounded_rectangle([int(v) for v in (RAIL_X,yy,RAIL_X+RAIL_W,yy+ch)],
            radius=3,fill=rgba(s["accent"],0.06+0.04*shot),
            outline=rgba(s["accent"],(0.32,0.22,0.32)[shot]),width=1)
        for sx in (RAIL_X+7,RAIL_X+RAIL_W-13):     # sprocket holes
            d.rectangle([int(v) for v in (sx,yy+ch*0.34,sx+6,yy+ch*0.66)],
                        fill=rgba(s["accent"],0.30))
    for c in cuts:                                  # the cuts themselves
        yy=int(y0+c*pitch-pitch*0.16)
        d.rectangle((RAIL_X-2,yy,RAIL_X+RAIL_W+2,yy+4),fill=rgba(s["accent"],0.95))
    pts=[]
    for i in range(int(y1-y0)):
        a=(math.sin(i*0.055)*0.55+math.sin(i*0.171)*0.30+math.sin(i*0.41)*0.15)
        pts.append((RAIL_X+RAIL_W+22+a*15, y0+i))
    d.line(pts,fill=rgba(s["support"],0.55),width=2)

def motif_shots(base,d,s):
    """three shots, hard cuts between them, one waveform under all of them"""
    x0,x1,y0,y1 = CONTENT_X+16, 1040, 196, 326
    wq=(x1-x0-24)/3
    for i in range(3):
        bx=x0+i*(wq+12)
        d.rounded_rectangle((bx,y0,bx+wq,y1),radius=8,
            fill=rgba((255,255,255),0.020),outline=rgba(s["accent"],0.34),width=2)
        text(d,(bx+14,y0+14),f"SHOT {i+1}",m(20,"bold"),s["accent"],0.55,1,"lt")
        if i: d.rectangle((int(bx-8),int(y0),int(bx-4),int(y1)),
                          fill=rgba(s["accent"],0.85))
    pts=[]
    for i in range(int(x1-x0)):
        a=(math.sin(i*0.05)*0.5+math.sin(i*0.13)*0.32+math.sin(i*0.31)*0.18)
        pts.append((x0+i, y1+42+a*20))
    d.line(pts,fill=rgba(s["support"],0.70),width=3)

def motif_denoise(base,d,s):
    """eight denoise steps: noise resolving into a frame -- the generation act.
    Composites RGBA tiles rather than drawing them: ImageDraw replaces pixels
    instead of blending, so noise over a picture has to go through
    alpha_composite (gotcha 1)."""
    rng=np.random.RandomState(7)
    x0,y0,n,gap = CONTENT_X+16, 196, 8, 8
    twd=(1040-x0-gap*(n-1))/n; thd=118
    for i in range(n):
        bx=x0+i*(twd+gap); lvl=1.0-i/(n-1)      # 1.0 pure noise -> 0.0 clean
        w_,h_=int(twd),int(thd)
        img=np.zeros((h_,w_,3),np.float32)
        hz=int(h_*0.62)
        img[:hz]=np.array(s["glow"],np.float32)*1.10
        img[hz:]=np.array((12,16,28),np.float32)
        yy,xx=np.mgrid[0:h_,0:w_]
        cy,cx,r=int(h_*0.40),int(w_*0.52),int(h_*0.17)
        img[((xx-cx)**2+(yy-cy)**2)<r*r]=np.array(s["accent"],np.float32)*0.85
        img=img*(1-lvl)+rng.rand(h_,w_,1)*255.0*lvl
        tile=Image.fromarray(np.clip(img,0,255).astype(np.uint8),"RGB").convert("RGBA")
        tile.putalpha(230)
        base.alpha_composite(tile,(int(bx),int(y0)))
        d.rounded_rectangle((int(bx),int(y0),int(bx)+w_,int(y0)+h_),radius=4,
                            outline=rgba(s["accent"],0.85 if i==n-1 else 0.28),width=2)
        text(d,(bx+w_/2,y0+h_+16),str(i+1),m(19,"bold"),
             s["accent"] if i==n-1 else (108,116,138),0.85,0,"mt")

def motif_speed(base,d,s):
    """the whole argument in the top band: baseline against DFlash"""
    x0 = CONTENT_X+16; MAXW = 560; mx = 233.4
    for i,(lab,v,col,fill) in enumerate([("BASELINE",74.9,s["support"],0.26),
                                         ("DFLASH",233.4,s["accent"],0.55)]):
        y=206+i*86
        text(d,(x0,y),lab,m(22,"bold"),col,0.85,2,"lt")
        bw=MAXW*(v/mx)
        d.rounded_rectangle((x0,y+34,x0+bw,y+66),radius=6,
                            fill=rgba(col,fill),outline=rgba(col,0.85),width=2)
        text(d,(x0+bw+16,y+50),f"{v} tok/s",m(24,"bold"),col,0.95,0,"lm")

def token_rail(base,d,s,y0=168,y1=1544,n=34,done=21):
    """the spine as a token stream: emitted, a bright leading edge, pending"""
    put_glow(base,RAIL_X+RAIL_W/2,900,s["glow"],620,0.22)
    pitch=(y1-y0)/n; ch=pitch*0.66
    for i in range(n):
        yy=y0+i*pitch
        box=[int(v) for v in (RAIL_X,yy,RAIL_X+RAIL_W,yy+ch)]
        if i<done:
            d.rounded_rectangle(box,radius=3,fill=rgba(s["accent"],0.50))
        elif i==done:
            d.rounded_rectangle(box,radius=3,fill=rgba(s["accent_hi"],0.95))
            put_glow(base,RAIL_X+RAIL_W/2,yy+ch/2,s["accent"],240,0.34)
        else:
            d.rounded_rectangle(box,radius=3,fill=rgba(s["accent"],0.05),
                                outline=rgba(s["accent"],0.20),width=1)

MOTIFS["shots"]=motif_shots
MOTIFS["denoise"]=motif_denoise
MOTIFS["speed"]=motif_speed
RAILS={"layers":layer_rail,"filmstrip":filmstrip_rail,"tokens":token_rail}

def _fit(txt,mk,sizes,maxw,track=0.0):
    """largest size in `sizes` whose rendered width fits, else the smallest"""
    return next((mk(z) for z in sizes if tw(txt,mk(z),track)<=maxw),mk(sizes[-1]))

def render_stack(key):
    s=SPECS[key]
    WHITE=(255,255,255); MUTED=(152,156,170); DIM=(104,110,126)
    CARD=s.get("cardc",(20,19,34)); BORDER=s.get("borderc",(52,46,78))
    kit.set_palette(BG=s["bg"],ORANGE=s["accent"],ORANGE_HI=s["accent_hi"],
                    CREAM=s["pale"],MUTED=MUTED,DIM=DIM,CARD=CARD,BORDER=BORDER)
    base=ground(s)
    ov=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(ov)
    MOTIFS[s["motif"]](ov,d,s)
    RAILS[s.get("rail","layers")](ov,d,s)

    avail=W-CONTENT_X-MARGIN
    if s.get("band_note"):
        text(d,(CONTENT_X,410),s["band_note"],
             _fit(s["band_note"],m,(26,24,22,20),avail),(120,126,146),0.95,0,"lt")

    # left-aligned square tag instead of the centred pill
    tf=f(28,"bold"); twd=tw(s["tag"],tf,6)
    d.rounded_rectangle((CONTENT_X,464,CONTENT_X+twd+58,516),radius=6,
                        outline=rgba(s["accent"],0.85),width=2)
    d.ellipse((CONTENT_X+20,484,CONTENT_X+32,496),fill=rgba(s["accent"],1.0))
    text(d,(CONTENT_X+46,490),s["tag"],tf,s["accent"],1.0,6,"lm")

    # version small on top, size as the hero -- "3.8" is a version, "27B" a size
    text(d,(CONTENT_X+4,546),s["version"],m(60,"bold"),s["pale"],0.95,10,"lt")
    kind,size=s["mark_font"]
    fo=(m if kind=="mono" else f)(size,"bold")
    grad_text(ov,(CONTENT_X,608),s["wordmark"],fo,WHITE,s["pale"],1.0,"lt",
              s["mark_track"])

    sf=_fit(s["sub"],m,(31,29,27,25,23),avail,2)
    text(d,(CONTENT_X,806),s["sub"],sf,MUTED,1.0,2,"lt")
    hline(d,CONTENT_X,CONTENT_X+300,856,s["accent"],0.95,4)

    text(d,(CONTENT_X,896),s["kicker"],f(38,"med"),MUTED,1.0,0,"lt")
    y=948
    for ln in s["hook"]:
        text(d,(CONTENT_X,y),ln,f(76,"bold"),WHITE,1.0,0,"lt"); y+=90

    # square panels with a lit left edge
    gap=18; cw=(avail-2*gap)/3
    for i,(n,lab) in enumerate(s["stats"]):
        x=CONTENT_X+i*(cw+gap); y0=1226
        card(d,(x,y0,x+cw,y0+164),6,CARD,0.90,BORDER,0.95,2)
        d.rectangle((int(x),int(y0),int(x)+4,int(y0+164)),fill=rgba(s["accent"],0.95))
        nf=_fit(n,f,(58,52,46,40),cw-44)
        grad_text(ov,(x+22,y0+28),n,nf,s["accent_hi"],s["accent"],1.0,"lt")
        lf=_fit(lab,f,(22,21,20,19,18),cw-40,2)
        text(d,(x+22,y0+134),lab,lf,MUTED,1.0,2,"lt")

    box=(CONTENT_X,1428,W-MARGIN,1528)
    card(d,box,6,CARD,0.82,BORDER,0.9,2)
    if s.get("prompt",True):
        text(d,(CONTENT_X+30,1478),"›",m(34,"bold"),s["accent"],1.0,0,"lm")
        cf=_fit(s["cmd"],m,(32,30,28,26,24,22,20),avail-104)
        text(d,(CONTENT_X+68,1478),s["cmd"],cf,WHITE,0.95,0,"lm")
    else:
        text(d,(CONTENT_X,1478),s["cmd"],f(28,"bold"),s["accent_hi"],0.95,4,"lm")

    ff=f(26,"bold")
    assert tw(s["foot_l"],ff,4)+tw(s["foot_r"],ff,4)+40 <= W-2*MARGIN, \
        "cover footers would overlap"
    text(d,(MARGIN,1600),s["foot_l"],ff,DIM,1.0,4,"lt")
    text(d,(W-MARGIN,1600),s["foot_r"],ff,s["accent"],1.0,4,"rt")

    base.alpha_composite(ov)
    p=os.path.join(OUT,s["file"])
    base.convert("RGB").save(p)
    print("wrote",p)
    return p


# ================= ledger layout (the Ledger template) =================
# Matches video/ledger.py so a reel and its cover read as one object: a
# vertical spine at x 180, everything hung off it left-aligned, hairline
# rules instead of cards, and no glow anywhere. `render` and `render_stack`
# above are untouched -- a spec opts in with layout="ledger".
LG_GUT, LG_RULE_X, LG_CX, LG_RIGHT = 118, 180, 232, 996

def ledger_ground(s, step=54):
    a=np.zeros((H,W,3),np.float32); a[:,:]=s["bg"]
    g=np.array(s.get("grid",(30,34,40)),np.float32)
    for x in range(0,W,step):      a[:,x]+=g*0.55
    for y in range(0,H,step):      a[y,:]+=g*0.55
    for x in range(0,W,step*4):    a[:,x]+=g*0.45
    for y in range(0,H,step*4):    a[y,:]+=g*0.45
    a*=np.linspace(1.06,0.82,H,dtype=np.float32)[:,None,None]
    rng=np.random.RandomState(4)
    a+=rng.normal(0,2.0,(H,W,1)).astype(np.float32)
    a+=rng.normal(0,0.85,(H,W,3)).astype(np.float32)
    return Image.fromarray(np.clip(a,0,255).astype(np.uint8),"RGB").convert("RGBA")

def render_ledger(key):
    s=SPECS[key]
    WHITE=(255,255,255); MUTED=(146,150,158); DIM=(98,103,112)
    RULE=s.get("rule",(58,64,74))
    kit.set_palette(BG=s["bg"],ORANGE=s["accent"],ORANGE_HI=s["accent_hi"],
                    CREAM=s["pale"],MUTED=MUTED,DIM=DIM,CARD=(16,18,22),BORDER=RULE)
    base=ledger_ground(s)
    ov=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(ov)

    d.line((LG_RULE_X,150,LG_RULE_X,1660),fill=rgba(RULE,0.85),width=2)
    text(d,(LG_CX,176),s["slug"],m(25),DIM,1.0,2,"lm")
    text(d,(LG_RIGHT,176),s["tag"],m(25,"bold"),s["accent"],1.0,2,"rm")
    d.line((LG_RULE_X,228,LG_RIGHT,228),fill=rgba(RULE,0.75),width=2)

    text(d,(LG_CX,306),s["kicker"],f(34,"med"),MUTED,1.0,0,"lm")

    mk=s.get("mark_size",132)
    fo=f(mk,"bold")
    while tw(s["wordmark"],fo,-1)>LG_RIGHT-LG_CX and mk>60:
        mk-=6; fo=f(mk,"bold")
    text(d,(LG_CX,486),s["wordmark"],fo,WHITE,1.0,-1,"lm")
    d.line((LG_CX,584,LG_RIGHT,584),fill=rgba(s["accent"],0.9),width=4)
    sf=next((m(z) for z in (30,28,26,24,22) if tw(s["sub"],m(z),2)<=LG_RIGHT-LG_CX),m(22))
    text(d,(LG_CX,632),s["sub"],sf,MUTED,1.0,2,"lm")

    y=740
    for ln in s["hook"]:
        hs=76; hf=f(hs,"bold")
        while tw(ln,hf)>LG_RIGHT-LG_CX+40 and hs>44:
            hs-=4; hf=f(hs,"bold")
        text(d,(LG_CX,y),ln,hf,WHITE,1.0,0,"lm"); y+=92

    ry=1096
    for i,(lab,val) in enumerate(s["rows"]):
        yy=ry+i*96
        text(d,(LG_CX,yy),lab,f(33,"bold"),mix((136,142,152),WHITE,0.55),1.0,1,"lm")
        text(d,(LG_RIGHT,yy),val,m(31,"bold"),s["accent_hi"],1.0,0,"rm")
        d.line((LG_CX-22,yy+40,LG_RIGHT,yy+40),fill=rgba(RULE,0.6),width=2)

    cy=1444
    d.rectangle((LG_CX-22,cy-34,LG_CX-16,cy+34),fill=rgba(s["accent"],0.95))
    if s.get("prompt",True):
        text(d,(LG_CX,cy),"›",m(32,"bold"),s["accent"],1.0,0,"lm")
        avail=LG_RIGHT-LG_CX-46
        cf=next((m(z) for z in (32,30,28,26,24,22,20) if tw(s["cmd"],m(z))<=avail),m(20))
        text(d,(LG_CX+40,cy),s["cmd"],cf,WHITE,0.95,0,"lm")
    else:
        cf=next((m(z) for z in (30,28,26,24,22) if tw(s["cmd"],m(z),2)<=LG_RIGHT-LG_CX),m(22))
        text(d,(LG_CX,cy),s["cmd"],cf,s["accent_hi"],0.95,2,"lm")

    ff=f(26,"bold")
    assert tw(s["foot_l"],ff,4)+tw(s["foot_r"],ff,4)+40 <= LG_RIGHT-LG_CX+60, \
        f"ledger cover footers would overlap for {key!r}"
    text(d,(LG_CX,1600),s["foot_l"],ff,DIM,1.0,4,"lt")
    text(d,(LG_RIGHT,1600),s["foot_r"],ff,s["accent"],1.0,4,"rt")

    base.alpha_composite(ov)
    p=os.path.join(OUT,s["file"])
    base.convert("RGB").save(p)
    print("wrote",p)
    return p


# ================= slab layout (the Slab template) =================
# Full-bleed colour field, one enormous wordmark, one figure. Matches
# video/slab.py so a reel and its cover are the same object, and so a grid
# of these reads as a set of posters rather than a set of dark cards.
# `render`, `render_stack` and `render_ledger` above are untouched.
SL_CX, SL_CR = 96, 984

def _slab_ink(rgb):
    def _l(c):
        c=c/255.0
        return c/12.92 if c<=0.04045 else ((c+0.055)/1.055)**2.4
    L=0.2126*_l(rgb[0])+0.7152*_l(rgb[1])+0.0722*_l(rgb[2])
    return (15,15,18) if L>0.42 else (255,255,255)

def render_slab(key):
    s=SPECS[key]
    fl=s["field"]; ink=_slab_ink(fl)
    dim=mix(ink,fl,0.34); rule=mix(ink,fl,0.58)
    kit.set_palette(BG=fl,ORANGE=ink,ORANGE_HI=ink,CREAM=ink,
                    MUTED=dim,DIM=dim,CARD=fl,BORDER=rule)
    a=np.zeros((H,W,3),np.float32); a[:,:]=fl
    a*=(1.0-np.linspace(0.0,0.055,H,dtype=np.float32))[:,None,None]
    rng=np.random.RandomState(4)
    a+=rng.normal(0,1.1,(H,W,1)).astype(np.float32)
    a+=rng.normal(0,0.5,(H,W,3)).astype(np.float32)
    base=Image.fromarray(np.clip(a,0,255).astype(np.uint8),"RGB").convert("RGBA")
    ov=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(ov)

    text(d,(SL_CX,206),s["kicker"],m(30,"bold"),dim,1.0,4,"lm")

    y=430
    for ln in s["wordmark"]:
        sz=s.get("mark_size",148); fo=f(sz,"bold")
        while tw(ln,fo,-1)>(SL_CR-SL_CX) and sz>60:
            sz-=6; fo=f(sz,"bold")
        text(d,(SL_CX,y),ln,fo,ink,1.0,-1,"lm"); y+=int(sz*1.06)
    d.rectangle((SL_CX,y+18,SL_CR,y+30),fill=rgba(ink,1.0))

    hy=y+110
    for ln in s["hook"]:
        hs=80; hf=f(hs,"bold")
        while tw(ln,hf)>(SL_CR-SL_CX) and hs>46:
            hs-=4; hf=f(hs,"bold")
        text(d,(SL_CX,hy),ln,hf,ink,1.0,0,"lm"); hy+=94

    # Everything above here is variable height -- a two-line wordmark pushes
    # the figure down. So the figure sizes itself to the space that is left and
    # the command follows it, rather than sitting at a fixed y and colliding
    # (which is exactly what qm and openworker did).
    val,lab=s["figure"]
    fy=hy+60
    FOOT_TOP=1500
    fs=176
    while fs>76:
        ffo=f(fs,"bold")
        if tw(str(val),ffo)<=(SL_CR-SL_CX) and fy+int(fs*1.14)+50+96+30<=FOOT_TOP:
            break
        fs-=8
    ffo=f(fs,"bold")
    text(d,(SL_CX,fy),str(val),ffo,ink,1.0,0,"lt")
    ry=fy+int(fs*1.14)
    d.rectangle((SL_CX,ry,SL_CR,ry+7),fill=rgba(ink,1.0))
    text(d,(SL_CX,ry+50),lab,f(34,"bold"),dim,1.0,5,"lt")

    cy=ry+50+96
    assert cy+30<=FOOT_TOP, f"slab cover command would hit the footer for {key!r}"
    cs=38; cfo=m(cs,"bold")
    while tw(s["cmd"],cfo)>(SL_CR-SL_CX-60) and cs>24:
        cs-=2; cfo=m(cs,"bold")
    d.rectangle((SL_CX,cy-46,SL_CX+12,cy+26),fill=rgba(ink,1.0))
    text(d,(SL_CX+38,cy-10),s["cmd"],cfo,ink,1.0,0,"lm")

    ff=f(28,"bold")
    assert tw(s["foot_l"],ff,4)+tw(s["foot_r"],ff,4)+40 <= SL_CR-SL_CX, \
        f"slab cover footers would overlap for {key!r}"
    text(d,(SL_CX,1556),s["foot_l"],ff,dim,1.0,4,"lt")
    text(d,(SL_CR,1556),s["foot_r"],ff,ink,1.0,4,"rt")

    base.alpha_composite(ov)
    p=os.path.join(OUT,s["file"])
    base.convert("RGB").save(p)
    print("wrote",p)
    return p

RENDERERS={"stack":render_stack,"ledger":render_ledger,
            "slab":render_slab}

if __name__=="__main__":
    keys=sys.argv[1:] or list(SPECS)
    for k in keys:
        RENDERERS.get(SPECS[k].get("layout"), render)(k)
