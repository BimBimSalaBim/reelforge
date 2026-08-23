# ---------------------------------------------------------------
# colibri.py -- "Colibrì" on the Ledger template. Teal, with amber kept
# for the one honest row: no SLA on speed. The rows ARE the memory
# hierarchy, which is the whole reason this repo fits this template.
# ---------------------------------------------------------------
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kit, ledger as L
from kit import (W, H, MARGIN, f, m, clamp, lin, eo3, eo4, eob, pulse, rgba,
                 mix, tw, text, wrap)
from ledger import Theme, WHITE, CX, RIGHT, RULE_X, right_edge
from timing import Timing

NAME    = "colibri"
AUDIO   = "colibri.mp3"
PHRASES = "phrases/colibri.txt"
TOTAL   = 40.2
FPS     = 30

_T = Timing(NAME); WORDS = _T.words
ws, we = _T.ws, _T.we
CH = _T.chunks()
CAPTIONS = False
# no captions -> the band they occupied is free, so the scene layer sits lower
CONTENT_DY = 150

TH = Theme(bg=(7,12,12), accent=(0,206,178), accent_hi=(128,240,220),
           pale=(214,250,242), support=(255,168,86),
           grid=(24,34,32), rule=(48,64,60))
TH.apply()
BASE = L.build_ground(TH, seed=9)

SC = [("scale",0.00,6.10), ("tiers",6.10,16.30), ("number",16.30,23.15),
      ("brain",23.15,29.30), ("contract",29.30,36.15), ("end",36.15,TOTAL)]
def scene_at(t):
    for i,(n,a,b) in enumerate(SC):
        if a<=t<b: return i,n,a,b
    return len(SC)-1, SC[-1][0], SC[-1][1], SC[-1][2]
CUTS = [a for _,a,_ in SC[1:]]

# ---------------- 1. the scale ----------------
def s_scale(ov,d,t,t0):
    L.heading(ov,d,"TINY ENGINE, IMMENSE MODEL",t,0.10,TH,size=44)
    # legible at frame 0
    text(d,(CX,470),"2.8T",f(150,"bold"),WHITE,1.0,0,"lm")
    text(d,(CX,584),"PARAMETERS  ·  KIMI K3",f(26,"bold"),TH.muted,1.0,4,"lm")
    d.line((CX,620,RIGHT,620),fill=rgba(TH.accent,0.9),width=4)
    kt=eo3(lin(t,ws("trillion")-0.14,ws("trillion")+0.40))
    if kt>0.02:
        text(d,(RIGHT,470),"on hardware you own",m(28),
             mix(TH.faint,TH.accent_hi,kt),kt,0,"rm")
    L.row(ov,d,t,ws("dependencies")-0.70,TH,760,"written in","pure C",
          lit=eo3(lin(t,ws("dependencies")-0.60,ws("dependencies")-0.20)),h=88)
    L.row(ov,d,t,ws("dependencies")-0.40,TH,872,"engine dependencies","0",
          lit=eo3(lin(t,ws("dependencies")-0.14,ws("dependencies")+0.36)),h=88)
    L.note(ov,d,t,ws("dependencies")+0.10,TH,984,
           "one C file per model family, six of them",size=27)

# ---------------- 2. one memory hierarchy ----------------
TIERS=[("VRAM","fastest, smallest","VRAM"),
       ("RAM","the middle tier","RAM"),
       ("STORAGE","slowest, largest","disk")]
def s_tiers(ov,d,t,t0):
    L.heading(ov,d,"ONE MEMORY HIERARCHY",t,t0+0.06,TH,size=46)
    for i,(nm,sub,cue) in enumerate(TIERS):
        c=ws(cue)
        lit=eo3(lin(t,c-0.12,c+0.40))
        L.row(ov,d,t,c-0.22,TH,470+i*116,nm,sub,lit=lit,h=96,lsize=38)
    kh=eo3(lin(t,ws("hierarchy")-0.16,ws("hierarchy")+0.44))
    if kh>0.02:
        d.rectangle((CX-40,440,CX-34,700),fill=rgba(TH.accent,0.9*kh))
        text(d,(CX,868),"placement tiers for the same weights",
             m(28),TH.muted,kh,0,"lm")
    # the expert climbing out of storage on the word
    ke=eo3(lin(t,ws("Experts")-0.16,ws("Experts")+0.60))
    if ke>0.02:
        y=700-260*eo4(ke)
        d.rectangle((RIGHT-190,y-13,RIGHT-160,y+13),fill=rgba(TH.accent_hi,0.95))
        text(d,(RIGHT-140,y),"expert",m(24),TH.accent_hi,1.0,0,"lm")
    ks=eo3(lin(t,ws("storage")-0.16,ws("storage")+0.44))
    if ks>0.02:
        text(d,(CX,952),"streamed up as the router asks for them",
             f(34,"bold"),WHITE,ks,2,"lm")
    kj=eo3(lin(t,ws("loading")-0.16,ws("loading")+0.44))
    if kj>0.02:
        text(d,(CX,1024),"not the whole model, every time",
             m(28),TH.dim,kj,0,"lm")
    L.note(ov,d,t,t0+0.5,TH,1140,
           "per-layer LRU  ·  pinned hot-store  ·  one-layer-ahead prefetch",size=25)

# ---------------- 3. the measured run ----------------
def s_number(ov,d,t,t0):
    L.heading(ov,d,"ONE MEASURED RUN",t,t0+0.06,TH,size=46)
    L.note(ov,d,t,t0+0.25,TH,400,"GLM-5.2  ·  744B MoE  ·  int4  ·  streaming CPU")
    kb=eob(lin(t,ws("billion")-0.16,ws("billion")+0.52),1.5)
    if kb>0.02:
        kk=min(1.0,kb)
        text(d,(CX,530),"744B",f(int(132*(0.92+0.08*kb)),"bold"),WHITE,kk,0,"lm")
        text(d,(CX,626),"PARAMETERS",f(26,"bold"),TH.muted,kk,4,"lm")
        d.line((CX,660,CX+(RIGHT-CX)*kk,660),fill=rgba(TH.accent,0.9),width=4)
    L.row(ov,d,t,ws("gigabytes")-0.30,TH,780,"resident","9.9 GB",
          lit=eo3(lin(t,ws("gigabytes")-0.14,ws("gigabytes")+0.40)),h=94,lsize=36)
    L.row(ov,d,t,ws("Ready")-0.24,TH,894,"ready in","32 s",
          lit=eo3(lin(t,ws("seconds")-0.14,ws("seconds")+0.40)),h=94,lsize=36)
    L.note(ov,d,t,t0+0.60,TH,1010,
           "the dashboard run is 4 tok/s, TTFT 1.6s, on 6x RTX 5090",
           size=26,col=TH.support)

# ---------------- 4. it shows you the inside ----------------
def s_brain(ov,d,t,t0):
    L.heading(ov,d,"IT SHOWS YOU THE INSIDE",t,t0+0.06,TH,size=46)
    kn=eo3(lin(t,ws("Nineteen")-0.24,ws("Nineteen")+0.40))
    L.counter(ov,d,t,ws("Nineteen")-0.24,TH,450,19456,label="EXPERTS, LIVE",
              dur=0.95,vsize=104)
    # the cortex, abstracted: colour is tier, brightness is routing heat
    kf=eo3(lin(t,ws("cortex")-0.30,ws("cortex")+0.30))
    if kf>0.02:
        rng=np.random.RandomState(3)
        cols,rows=26,9
        for r in range(rows):
            for c in range(cols):
                x=CX+c*28; y=640+r*28
                tier=rng.rand()
                base=TH.accent if tier<0.45 else (TH.accent_hi if tier<0.7 else TH.rule)
                a=0.20+0.55*rng.rand()
                flash=eo3(lin(t,ws("route")-0.20+ (c*7+r)%13*0.02,
                                ws("route")+0.10+(c*7+r)%13*0.02))
                if rng.rand()<0.16 and flash>0.1:
                    d.rectangle((x,y,x+15,y+15),fill=rgba((255,255,255),0.95*flash))
                else:
                    d.rectangle((x,y,x+15,y+15),fill=rgba(base,a*kf))
    kr=eo3(lin(t,ws("cortex")+0.40,ws("cortex")+0.84))
    if kr>0.02:
        text(d,(CX,960),"every expert routed this turn flashes white",
             m(28),TH.accent_hi,kr,0,"lm")
        text(d,(CX,1012),"colour is the storage tier, brightness is routing heat",
             m(25),TH.dim,kr*0.9,0,"lm")

# ---------------- 5. the contract ----------------
def s_contract(ov,d,t,t0):
    L.heading(ov,d,"WHAT IT WILL AND WILL NOT PROMISE",t,t0+0.06,TH,size=40)
    ksp=eo3(lin(t,ws("speed")-0.14,ws("speed")+0.42))
    L.row(ov,d,t,ws("speed")-0.24,TH,490,"SPEED","NO SLA",
          lit=ksp,h=104,lsize=40,col=TH.support)
    ksem=eo3(lin(t,ws("guarantee")-0.14,ws("guarantee")+0.42))
    L.row(ov,d,t,ws("guarantee")-0.26,TH,624,"SEMANTICS","HARD GUARANTEE",
          lit=ksem,h=104,lsize=40)
    L.quote(ov,d,t,ws("quietly")-0.30,TH,790,
            ["Insufficient fast memory may","reduce speed; it must not","quietly redefine the model."],
            attrib="README, on the default policy",size=32)
    L.note(ov,d,t,t0+0.50,TH,1150,
           "Apache-2.0  ·  25,736 stars  ·  a research platform, openly",size=26)

# ---------------- dispatch ----------------
def frame(t):
    base = BASE.copy()
    sc = Image.new("RGBA",(W,H),(0,0,0,0)); sd = ImageDraw.Draw(sc)
    idx,n,a,b = scene_at(t)
    {"scale":s_scale,"tiers":s_tiers,"number":s_number,"brain":s_brain,
     "contract":s_contract}.get(n,lambda *_: None)(sc,sd,t,a)
    ov = Image.new("RGBA",(W,H),(0,0,0,0)); d = ImageDraw.Draw(ov)
    ov.alpha_composite(sc,(0,CONTENT_DY))
    if n=="end":
        L.endcard(ov,d,t,a,TH,"Colibrì","frontier MoE, your hardware",
                  "github.com/JustVugg/colibri","./coli chat",
                  "SAVE THIS FOR YOUR NEXT BUILD",mark_size=150)
    L.chrome(ov,d,t,TH,TOTAL,"JustVugg/colibri",SC,idx)
    L.advance(ov,d,t,CUTS,TH)
    # Burned-in captions are OFF by default (see DEVELOPMENT.md). Flip CAPTIONS
    # to True only when the brief asks for them.
    if CAPTIONS and n!="end": L.captions(ov,d,t,CH,TH)
    base.alpha_composite(ov)
    return base

_BIG = {16.30, 29.30, 36.15}
SFX = (
 [{"t":c-0.24,"kind":"shift","amp":0.10} for c in CUTS] +
 [{"t":c,"kind":"latch","amp":0.26 if c in _BIG else 0.19,
   "dur":0.22 if c in _BIG else 0.16} for c in CUTS] +
 [{"t":ws("trillion")-0.14,"kind":"rule","amp":0.11},
  {"t":ws("dependencies")-0.14,"kind":"click","amp":0.10,"tone":3200.0},
  {"t":ws("hierarchy")-0.16,"kind":"rule","amp":0.10},
  {"t":ws("Experts")-0.16,"kind":"shift","amp":0.12},
  {"t":ws("storage")-0.16,"kind":"click","amp":0.09,"tone":2900.0},
  {"t":ws("billion")-0.16,"kind":"latch","amp":0.24,"dur":0.20},
  {"t":ws("gigabytes")-0.14,"kind":"click","amp":0.10,"tone":3300.0},
  {"t":ws("seconds")-0.14,"kind":"click","amp":0.09,"tone":2600.0},
  {"t":ws("Nineteen")-0.24,"kind":"rule","amp":0.10},
  {"t":ws("route")-0.16,"kind":"rule","amp":0.12},
  {"t":ws("speed")-0.14,"kind":"click","amp":0.09,"tone":2200.0},
  {"t":ws("guarantee")-0.14,"kind":"latch","amp":0.22,"dur":0.20},
  {"t":ws("quietly")-0.30,"kind":"click","amp":0.085,"tone":2800.0}] +
 [{"t":ws(c)-0.12,"kind":"click","amp":0.085,"tone":2400.0+i*180}
    for i,(_,_,c) in enumerate(TIERS)]
)
