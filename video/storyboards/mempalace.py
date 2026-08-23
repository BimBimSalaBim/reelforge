# ---------------------------------------------------------------
# mempalace.py -- "MemPalace" on the SLAB template. Plum and gold. The
# hook is a lost detail, so scene 1 shows the same fact twice and strikes
# the summary. Scene 5 carries their impostor-site warning as a band.
# ---------------------------------------------------------------
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kit, slab as S
from kit import W, H, f, m, clamp, lin, eo3, eo4, eob, rgba, mix, tw, text, wrap
from slab import Theme, CX, CR, ink_for
from timing import Timing

NAME    = "mempalace"
AUDIO   = "mempalace.mp3"
PHRASES = "phrases/mempalace.txt"
TOTAL   = 41.7
FPS     = 30
CAPTIONS = False

_T = Timing(NAME); ws, we = _T.ws, _T.we
SLUG = "MemPalace/mempalace"

TH = Theme(fields=[(242,238,232),(46,26,60),(214,166,74),(242,238,232),
                   (46,26,60),(242,238,232)],
           mark=(214,166,74))
TH.apply()

SC = [("hook",0.00,5.00),("what",5.00,12.90),("palace",12.90,22.90),
      ("number",22.90,30.10),("close",30.10,37.50),("end",37.50,TOTAL)]
def scene_at(t):
    for i,(n,a,b) in enumerate(SC):
        if a<=t<b: return i,n,a,b
    return len(SC)-1,SC[-1][0],SC[-1][1],SC[-1][2]
CUTS = [a for _,a,_ in SC[1:]]

def s_hook(ov,d,t,t0,i):
    S.statement(ov,d,["Summaries lose","the detail","you needed."],t,0.10,TH,i,size=112)
    S.pair(ov,d,("YOU SAID","port 8081",True),
                ("STORED","“port config”",False),
           t,ws("detail")-0.30,TH,i,y=1000,size=104)

def s_what(ov,d,t,t0,i):
    S.statement(ov,d,["Verbatim.","Nothing rewritten."],t,t0+0.05,TH,i,size=118)
    S.rows(ov,d,[("summarise","no"),("extract","no"),("paraphrase","no")],
           t,ws("summarise")-0.26,TH,i,y=880,h=120,gap=8,stagger=0.0,
           lsize=44,vsize=32,
           lit=[1.0 if t>=ws(c)-0.10 else 0.0
                for c in ("summarise","extract","paraphrase")])
    S.chip(ov,d,(CX,1420),"semantic search finds it; storage never edits it",
           t,ws("retrieves")-0.28,TH,i,size=30)

def s_palace(ov,d,t,t0,i):
    S.statement(ov,d,["Structured,","not flat."],t,t0+0.05,TH,i,size=132)
    S.rows(ov,d,[("WINGS","people and projects"),
                 ("ROOMS","topics"),
                 ("DRAWERS","the original text")],
           t,ws("wings")-0.30,TH,i,y=880,h=134,stagger=0.0,lsize=46,vsize=30,
           lit=[1.0 if t>=ws(c)-0.10 else 0.0
                for c in ("wings","rooms","drawers")])
    S.chip(ov,d,(CX,1440),"so a search is scoped, not run flat",
           t,ws("scoped")-0.30,TH,i,size=32)

def s_number(ov,d,t,t0,i):
    S.statement(ov,d,["96.6% recall","at five."],t,t0+0.05,TH,i,size=118)
    S.rows(ov,d,[("LongMemEval","their reported figure"),
                 ("API calls","zero")],
           t,ws("LongMemEval")-0.30,TH,i,y=880,h=132,lsize=44,vsize=30,
           lit=[0.0, 1.0 if t>=ws("zero")-0.12 else 0.0])
    S.chip(ov,d,(CX,1440),"local by default",t,ws("local")-0.24,TH,i,size=34)

def s_close(ov,d,t,t0,i):
    S.statement(ov,d,["MIT.","58,543 stars."],t,t0+0.05,TH,i,size=118)
    S.band(ov,d,["MemPalace has no other","official websites."],
           t,ws("warning")-0.32,TH,i,y=760,size=56,
           col=(214,166,74),attrib="the README's own CAUTION")
    S.rows(ov,d,[("only","this repo + mempalaceofficial.com")],
           t,ws("fake")-0.24,TH,i,y=1080,h=126,lsize=40,vsize=28,lit=[1])
    S.chip(ov,d,(CX,1440),"uv tool install mempalace",
           t,ws("install")-0.28,TH,i,size=34)

def frame(t):
    i,n,a,b = scene_at(t)
    base = S.field_for(TH,i).copy()
    ov = Image.new("RGBA",(W,H),(0,0,0,0)); d = ImageDraw.Draw(ov)
    {"hook":s_hook,"what":s_what,"palace":s_palace,"number":s_number,
     "close":s_close}.get(n,lambda *_: None)(ov,d,t,a,i)
    if n=="end":
        S.endcard(ov,d,t,a,TH,i,"MemPalace","verbatim local memory",
                  "github.com/MemPalace/mempalace","SAVE THIS FOR YOUR AGENT",
                  mark_size=132)
    S.cut(ov,d,t,CUTS,TH,lambda tt: scene_at(tt)[0])
    S.rail(ov,d,t,TH,i,len(SC),(t-a)/max(b-a,0.01))
    S.footer(ov,d,TH,i,SLUG,len(SC))
    base.alpha_composite(ov)
    return base

SFX = (
 [{"t":c-0.18,"kind":"paper","amp":0.14} for c in CUTS] +
 [{"t":c,"kind":"slam","amp":0.24,"dur":0.24} for c in CUTS] +
 [{"t":ws("detail")-0.30,"kind":"chime","amp":0.08,"tone":392.0},
  {"t":ws("retrieves")-0.28,"kind":"chime","amp":0.07,"tone":523.0},
  {"t":ws("scoped")-0.30,"kind":"chime","amp":0.08,"tone":659.0},
  {"t":ws("LongMemEval")-0.30,"kind":"riser","amp":0.10},
  {"t":ws("local")-0.24,"kind":"chime","amp":0.07,"tone":587.0},
  {"t":ws("warning")-0.32,"kind":"slam","amp":0.22,"dur":0.22},
  {"t":ws("install")-0.28,"kind":"chime","amp":0.07,"tone":440.0}] +
 [{"t":ws(c)-0.10,"kind":"chime","amp":0.05,"tone":330.0+k*49}
    for k,c in enumerate(("summarise","extract","paraphrase"))] +
 [{"t":ws(c)-0.10,"kind":"chime","amp":0.055,"tone":392.0+k*66}
    for k,c in enumerate(("wings","rooms","drawers"))]
)
