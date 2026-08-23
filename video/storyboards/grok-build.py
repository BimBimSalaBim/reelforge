# ---------------------------------------------------------------
# grok-build.py -- "Grok Build" on the SLAB template. Stark black/white
# with one signal blue, because the story is that real source exists, not
# that it is colourful. Scene 4 is the mirror, which is the unusual part.
# ---------------------------------------------------------------
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kit, slab as S
from kit import W, H, f, m, clamp, lin, eo3, eo4, eob, rgba, mix, tw, text
from slab import Theme, CX, CR, ink_for
from timing import Timing

NAME    = "grok-build"
AUDIO   = "grok-build.mp3"
PHRASES = "phrases/grok-build.txt"
TOTAL   = 39.6
FPS     = 30
CAPTIONS = False

_T = Timing(NAME); ws, we = _T.ws, _T.we
SLUG = "xai-org/grok-build"

TH = Theme(fields=[(18,18,20),(240,240,242),(18,18,20),(64,132,255),
                   (240,240,242),(18,18,20)],
           mark=(64,132,255))
TH.apply()

SC = [("hook",0.00,5.30),("what",5.30,15.10),("modes",15.10,22.60),
      ("mirror",22.60,30.30),("close",30.30,35.30),("end",35.30,TOTAL)]
def scene_at(t):
    for i,(n,a,b) in enumerate(SC):
        if a<=t<b: return i,n,a,b
    return len(SC)-1,SC[-1][0],SC[-1][1],SC[-1][2]
CUTS = [a for _,a,_ in SC[1:]]

def s_hook(ov,d,t,t0,i):
    S.statement(ov,d,["The actual","Rust source.","Not a wrapper."],t,0.10,TH,i,size=118)
    S.rows(ov,d,[("xai-org/grok-build","Apache-2.0")],
           t,ws("GitHub")-0.24,TH,i,y=1080,h=134,lsize=42,vsize=34,lit=[1])

def s_what(ov,d,t,t0,i):
    S.statement(ov,d,["A full-screen","terminal agent."],t,t0+0.05,TH,i,size=116)
    caps=[("reads","your codebase"),("edits","files"),
          ("runs","shell commands"),("searches","the web")]
    cues=["reads","edits","runs","searches"]
    S.rows(ov,d,caps,t,ws("reads")-0.24,TH,i,y=860,h=116,gap=8,stagger=0.0,
           lsize=42,vsize=32,
           lit=[1.0 if t>=ws(c)-0.10 else 0.0 for c in cues])
    S.chip(ov,d,(CX,1440),"and holds long-running tasks",
           t,ws("holds")-0.24,TH,i,size=34)

def s_modes(ov,d,t,t0,i):
    S.statement(ov,d,["Three ways","to run it."],t,t0+0.05,TH,i,size=120)
    S.rows(ov,d,[("INTERACTIVE","you, at a terminal"),
                 ("HEADLESS","scripting and CI"),
                 ("EMBEDDED","your editor, over ACP")],
           t,ws("interactive")-0.24,TH,i,y=900,h=132,stagger=0.0,
           lsize=44,vsize=30,
           lit=[1.0 if t>=c-0.10 else 0.0
                for c in (ws("interactive"),ws("headless"),ws("embedded"))])
    S.chip(ov,d,(CX,1440),"a protocol, so not only one editor",
           t,ws("Protocol")-0.30,TH,i,size=32)

def s_mirror(ov,d,t,t0,i):
    S.statement(ov,d,["This repo","is a mirror."],t,t0+0.05,TH,i,size=124)
    S.rows(ov,d,[("syncs from","their internal monorepo")],
           t,ws("syncs")-0.24,TH,i,y=880,h=136,lsize=44,vsize=32,lit=[1])
    S.figure(ov,d,"SOURCE_REV","THE EXACT COMMIT YOU ARE READING",
             t,ws("records")-0.30,TH,i,y=1060,size=92,
             note="so you can tell which snapshot this is")

def s_close(ov,d,t,t0,i):
    S.statement(ov,d,["Apache 2.0.","One install line."],t,t0+0.05,TH,i,size=112)
    S.command(ov,d,"curl -fsSL https://x.ai/cli/install.sh | bash",
              t,ws("install")-0.26,TH,i,900)
    S.rows(ov,d,[("platforms","macOS · Linux · Windows")],
           t,ws("Mac")-0.24,TH,i,y=1040,h=132,lsize=42,vsize=32,lit=[1])

def frame(t):
    i,n,a,b = scene_at(t)
    base = S.field_for(TH,i).copy()
    ov = Image.new("RGBA",(W,H),(0,0,0,0)); d = ImageDraw.Draw(ov)
    {"hook":s_hook,"what":s_what,"modes":s_modes,"mirror":s_mirror,
     "close":s_close}.get(n,lambda *_: None)(ov,d,t,a,i)
    if n=="end":
        S.endcard(ov,d,t,a,TH,i,"grok","a terminal coding agent",
                  "github.com/xai-org/grok-build","SAVE THIS BEFORE YOU PICK ONE")
    S.cut(ov,d,t,CUTS,TH,lambda tt: scene_at(tt)[0])
    S.rail(ov,d,t,TH,i,len(SC),(t-a)/max(b-a,0.01))
    S.footer(ov,d,TH,i,SLUG,len(SC))
    base.alpha_composite(ov)
    return base

SFX = (
 [{"t":c-0.18,"kind":"paper","amp":0.14} for c in CUTS] +
 [{"t":c,"kind":"slam","amp":0.24,"dur":0.24} for c in CUTS] +
 [{"t":ws("GitHub")-0.24,"kind":"chime","amp":0.08,"tone":392.0},
  {"t":ws("holds")-0.24,"kind":"chime","amp":0.07,"tone":523.0},
  {"t":ws("Protocol")-0.30,"kind":"chime","amp":0.07,"tone":659.0},
  {"t":ws("syncs")-0.24,"kind":"chime","amp":0.08,"tone":440.0},
  {"t":ws("records")-0.30,"kind":"riser","amp":0.11},
  {"t":ws("install")-0.26,"kind":"chime","amp":0.08,"tone":523.0},
  {"t":ws("Mac")-0.24,"kind":"chime","amp":0.07,"tone":698.0}] +
 [{"t":ws(c)-0.10,"kind":"chime","amp":0.055,"tone":330.0+k*55}
    for k,c in enumerate(("reads","edits","runs","searches"))] +
 [{"t":ws(c)-0.10,"kind":"chime","amp":0.06,"tone":392.0+k*66}
    for k,c in enumerate(("interactive","headless","embedded"))]
)
