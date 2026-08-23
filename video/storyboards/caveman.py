# ---------------------------------------------------------------
# caveman.py -- "Caveman". The first reel on the Ledger template.
# Stone and ember. The spine carries a token count that only ever goes
# down, and the licence split gets the last word because it has to.
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

NAME    = "caveman"
AUDIO   = "caveman.mp3"
PHRASES = "phrases/caveman.txt"
TOTAL   = 50.6
FPS     = 30

_T = Timing(NAME); WORDS = _T.words
ws, we = _T.ws, _T.we
CH = _T.chunks()
CAPTIONS = False
# no captions -> the band they occupied is free, so the scene layer sits lower
CONTENT_DY = 150

TH = Theme(bg=(12,11,10), accent=(232,124,48), accent_hi=(255,178,110),
           pale=(246,230,214), support=(120,190,255),
           grid=(34,30,26), rule=(64,56,48))
TH.apply()
BASE = L.build_ground(TH, seed=7)

SC = [("hook",0.00,7.30), ("skill",7.30,17.90), ("flip",17.90,25.00),
      ("table",25.00,32.20), ("number",32.20,38.20), ("licence",38.20,46.40),
      ("end",46.40,TOTAL)]
def scene_at(t):
    for i,(n,a,b) in enumerate(SC):
        if a<=t<b: return i,n,a,b
    return len(SC)-1, SC[-1][0], SC[-1][1], SC[-1][2]
CUTS = [a for _,a,_ in SC[1:]]

LONG = ("The reason your React component is re-rendering is likely because "
        "you're creating a new object reference on each render cycle.")
SHORT = "New object ref each render. Inline object prop = new ref = re-render."

# ---------------- 1. same answer, two sizes ----------------
def s_hook(ov,d,t,t0):
    L.heading(ov,d,"SAME ANSWER, TWO SIZES",t,0.10,TH,size=46)
    # both blocks legible at frame 0 -- the hook is the comparison itself
    for i,(body,cue,col,lab) in enumerate(
            [(LONG, ws("sixty-nine"), TH.dim, "NORMAL AGENT"),
             (SHORT, ws("nineteen"), TH.pale, "CAVEMAN AGENT")]):
        y0 = 420 + i*330
        text(d,(CX,y0),lab,f(25,"bold"),TH.muted if i else TH.faint,1.0,4,"lm")
        d.line((CX,y0+26,RIGHT,y0+26),fill=rgba(TH.rule,0.7),width=2)
        for j,ln in enumerate(wrap(body,m(29),RIGHT-CX-150)):
            text(d,(CX,y0+72+j*42),ln,m(29),col,1.0,0,"lm")
        k = eob(lin(t,cue-0.16,cue+0.52),1.5)
        if k>0.02:
            kk=min(1.0,k)
            n = "69" if i==0 else "19"
            fo = f(int(78*(0.9+0.1*k)),"bold")
            text(d,(RIGHT,y0+96),n,fo,TH.dim if i==0 else TH.accent,kk,0,"rm")
            text(d,(RIGHT,y0+152),"tokens",m(23),TH.faint if i==0 else TH.muted,kk,2,"rm")
    ka = eo3(lin(t,ws("answer")-0.14,ws("answer")+0.40))
    if ka>0.02:
        d.line((CX,1080,CX+(RIGHT-CX)*ka,1080),fill=rgba(TH.accent,0.9),width=4)
        text(d,(CX,1132),"same answer",f(40,"bold"),WHITE,ka,3,"lm")

# ---------------- 2. what the skill does ----------------
def s_skill(ov,d,t,t0):
    L.heading(ov,d,"WHAT THE SKILL DOES",t,t0+0.06,TH,size=46)
    L.note(ov,d,t,ws("Caveman")-0.10,TH,400,
           "your agent answers in tight caveman-speak")
    kx = eo3(lin(t,ws("Code")-0.16,ws("Code")+0.40))
    L.row(ov,d,t,ws("Code")-0.22,TH,540,"code · commands · errors",
          "EXACT",lit=kx,col=TH.ok,h=92,lsize=36)
    kc = eo3(lin(t,ws("crushed")-0.16,ws("crushed")+0.40))
    L.row(ov,d,t,ws("crushed")-0.24,TH,700,"the prose",
          "CRUSHED",lit=kc,col=TH.accent,h=92,lsize=36)
    if kc>0.3:
        L.meter(ov,d,TH,(CX,772,RIGHT,782),1.0-0.72*kc,col=TH.accent,bg=(30,26,22))
    L.stamp(ov,d,t,ws("skill")+0.20,TH,(CX,900),"MIT",size=30,col=TH.ok)
    L.note(ov,d,t,ws("skill")+0.40,TH,1010,
           "npx skills add JuliusBrussee/caveman",size=29,col=TH.muted)

# ---------------- 3. the other direction ----------------
def s_flip(ov,d,t,t0):
    L.heading(ov,d,"VERSION TWO GOES THE OTHER WAY",t,t0+0.06,TH,size=42)
    lit_out = 1.0
    lit_in = eo3(lin(t,ws("proxy")-0.16,ws("proxy")+0.44))
    L.row(ov,d,t,t0+0.20,TH,520,"v1  ·  OUTPUT","what it says",
          lit=lit_out*0.35,h=96,lsize=36)
    L.note(ov,d,t,t0+0.34,TH,596,"the skill, MIT",size=25,col=TH.faint)
    L.row(ov,d,t,ws("proxy")-0.24,TH,730,"v2  ·  INPUT","what it reads",
          lit=lit_in,h=96,lsize=36,col=TH.accent)
    L.note(ov,d,t,ws("proxy")+0.10,TH,806,"a local proxy, BSL-1.1",size=25,col=TH.dim)
    kr = eo3(lin(t,ws("reads")-0.14,ws("reads")+0.46))
    if kr>0.02:
        L.meter(ov,d,TH,(CX,900,RIGHT,914),kr,col=TH.accent,bg=(30,26,22))
        text(d,(CX,968),"shrunk before every provider call",m(29),TH.muted,kr,0,"lm")
    L.stamp(ov,d,t,ws("reads")+0.30,TH,(CX,1076),"caveman claude",size=30)

# ---------------- 4. what it shrinks ----------------
ROWS = [("log","85-95%","Logs"),("search-result","80-95%","Search"),
        ("json","70-90%",None),("diff","60-80%",None),
        ("text / HTML","50-80%",None),("code","40-70%",None)]
def s_table(ov,d,t,t0):
    L.heading(ov,d,"WHAT THE PROXY SHRINKS",t,t0+0.06,TH,size=46)
    for i,(lab,val,cue) in enumerate(ROWS):
        t_in = ws(cue)-0.24 if cue else t0+0.30+i*0.13
        lit  = eo3(lin(t,ws(cue)-0.14,ws(cue)+0.40)) if cue else 0.0
        L.row(ov,d,t,t_in,TH,470+i*104,lab,val,lit=lit,h=86)
    L.note(ov,d,t,t0+0.5,TH,1118,
           "detect() types the payload, then routes it",size=27)
    kb = eo3(lin(t,ws("recoverable")-0.20,ws("recoverable")+0.40))
    if kb>0.02:
        text(d,(CX,1196),"byte-exact recovery",f(32,"bold"),TH.accent_hi,kb,2,"lm")
        text(d,(CX,1250),"copies stay on your disk",m(26),TH.dim,kb*0.9,0,"lm")

# ---------------- 5. the measured number ----------------
def s_number(ov,d,t,t0):
    L.heading(ov,d,"MEASURED",t,t0+0.06,TH,size=46)
    p = L.counter(ov,d,t,ws("Thirty-three")-0.26,TH,500,33,
                  label="PERCENT FEWER INPUT TOKENS",dur=1.05,vsize=136)
    if p>0.05:
        L.meter(ov,d,TH,(CX,640,RIGHT,660),0.332*min(1.0,p*1.3),bg=(30,26,22))
    L.note(ov,d,t,ws("benchmark")-0.30,TH,760,
           "provider-reported, pinned 54-run Claude Code benchmark")
    L.stamp(ov,d,t,ws("benchmark")-0.10,TH,(CX,850),"benchmark_counterfactual",size=27)
    # keyed to the scene, not to "benchmark": at +0.35/+0.55 these were on
    # screen 0.65s and 0.45s before the cut. Neither is a narration beat.
    L.row(ov,d,t,t0+0.85,TH,1010,"caveman learn",
          "local, read-only",lit=0.0,h=84)
    L.note(ov,d,t,t0+1.05,TH,1104,
           "scores months of your own agent history",size=26)

# ---------------- 6. the licence is split ----------------
def s_licence(ov,d,t,t0):
    L.heading(ov,d,"BEFORE YOU SHIP IT",t,t0+0.06,TH,size=46)
    L.counter(ov,d,t,ws("hundred")-0.26,TH,430,100244,label="STARS",
              dur=1.05,vsize=112)
    ks = eo3(lin(t,ws("MIT")-0.14,ws("MIT")+0.40))
    L.row(ov,d,t,ws("skill",1)-0.22,TH,700,"the skill","MIT",
          lit=ks,col=TH.ok,h=88,lsize=34)
    ke = eo3(lin(t,ws("engine")-0.14,ws("engine")+0.40))
    L.row(ov,d,t,ws("engine")-0.22,TH,812,"engine · proxy · rewriter","BSL-1.1",
          lit=ke,col=TH.warn,h=88,lsize=34)
    L.quote(ov,d,t,ws("licence")-0.20,TH,950,
            ["BSL is source-available,","not open source."],
            attrib="LICENSING.md",col=TH.warn,size=34)

# ---------------- dispatch ----------------
def frame(t):
    base = BASE.copy()
    sc = Image.new("RGBA",(W,H),(0,0,0,0)); sd = ImageDraw.Draw(sc)
    idx,n,a,b = scene_at(t)
    {"hook":s_hook,"skill":s_skill,"flip":s_flip,"table":s_table,
     "number":s_number,"licence":s_licence}.get(n,lambda *_: None)(sc,sd,t,a)
    ov = Image.new("RGBA",(W,H),(0,0,0,0)); d = ImageDraw.Draw(ov)
    ov.alpha_composite(sc,(0,CONTENT_DY))
    if n=="end":
        L.endcard(ov,d,t,a,TH,"caveman","few token do trick",
                  "github.com/JuliusBrussee/caveman","npx skills add …/caveman",
                  "SAVE THIS BEFORE YOUR NEXT RUN",mark_size=150)
    L.chrome(ov,d,t,TH,TOTAL,"JuliusBrussee/caveman",SC,idx)
    L.advance(ov,d,t,CUTS,TH)
    # Burned-in captions are OFF by default (see DEVELOPMENT.md). Flip CAPTIONS
    # to True only when the brief asks for them.
    if CAPTIONS and n!="end": L.captions(ov,d,t,CH,TH)
    base.alpha_composite(ov)
    return base

_BIG = {17.90, 32.20, 46.40}
SFX = (
 [{"t":c-0.24,"kind":"shift","amp":0.10} for c in CUTS] +
 [{"t":c,"kind":"latch","amp":0.26 if c in _BIG else 0.19,
   "dur":0.22 if c in _BIG else 0.16} for c in CUTS] +
 [{"t":ws("sixty-nine")-0.16,"kind":"click","amp":0.10,"tone":2600.0},
  {"t":ws("nineteen")-0.16,"kind":"click","amp":0.11,"tone":3300.0},
  {"t":ws("answer")-0.14,"kind":"rule","amp":0.10},
  {"t":ws("Code")-0.16,"kind":"click","amp":0.09,"tone":3000.0},
  {"t":ws("crushed")-0.16,"kind":"latch","amp":0.18,"dur":0.16},
  {"t":ws("proxy")-0.16,"kind":"click","amp":0.10,"tone":2800.0},
  {"t":ws("reads")-0.14,"kind":"rule","amp":0.11},
  {"t":ws("recoverable")-0.20,"kind":"click","amp":0.09,"tone":3400.0},
  {"t":ws("Thirty-three")-0.26,"kind":"rule","amp":0.10},
  {"t":ws("hundred")-0.26,"kind":"rule","amp":0.09},
  {"t":ws("MIT")-0.14,"kind":"click","amp":0.09,"tone":3100.0},
  {"t":ws("engine")-0.14,"kind":"click","amp":0.10,"tone":2200.0},
  {"t":ws("licence")-0.20,"kind":"latch","amp":0.20,"dur":0.18}] +
 [{"t":ws(c)-0.14,"kind":"click","amp":0.085,"tone":2700.0}
    for _,_,c in ROWS if c] +
 [{"t":25.00+0.30+i*0.13,"kind":"click","amp":0.06,"tone":2400.0+i*90}
    for i in range(6)]
)
