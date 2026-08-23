# ---------------------------------------------------------------
# career-ops.py -- "career-ops" on the SLAB template. Navy and lime. The
# hook is the author's own inversion, and scene 4 is the one that must not
# be cut: this is a filter, not a spray-and-pray tool.
# ---------------------------------------------------------------
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kit, slab as S
from kit import W, H, f, m, clamp, lin, eo3, eo4, eob, rgba, mix, tw, text
from slab import Theme, CX, CR, ink_for
from timing import Timing

NAME    = "career-ops"
AUDIO   = "career-ops.mp3"
PHRASES = "phrases/career-ops.txt"
TOTAL   = 38.0
FPS     = 30
CAPTIONS = False

_T = Timing(NAME); ws, we = _T.ws, _T.we
SLUG = "santifer/career-ops"

TH = Theme(fields=[(240,240,236),(16,34,70),(198,232,72),(16,34,70),
                   (240,240,236),(16,34,70)],
           mark=(198,232,72))
TH.apply()

SC = [("hook",0.00,5.00),("what",5.00,14.20),("output",14.20,21.40),
      ("filter",21.40,28.50),("close",28.50,33.80),("end",33.80,TOTAL)]
def scene_at(t):
    for i,(n,a,b) in enumerate(SC):
        if a<=t<b: return i,n,a,b
    return len(SC)-1,SC[-1][0],SC[-1][1],SC[-1][2]
CUTS = [a for _,a,_ in SC[1:]]

def s_hook(ov,d,t,t0,i):
    S.statement(ov,d,["They screen you","with AI.","Screen them back."],t,0.10,TH,i,size=112)
    S.pair(ov,d,("THEY SCREEN","you",False),("YOU SCREEN","them",True),
           t,ws("gives")-0.26,TH,i,y=1000,size=112)

def s_what(ov,d,t,t0,i):
    S.statement(ov,d,["Any coding CLI,","into a job search."],t,t0+0.05,TH,i,size=104)
    S.rows(ov,d,[("SCANS","Greenhouse · Ashby · Lever"),
                 ("SCORES","each listing, against you")],
           t,ws("scans")-0.28,TH,i,y=920,h=134,lsize=44,vsize=30,
           lit=[1.0 if t>=ws("scans")-0.12 else 0.0,
                1.0 if t>=ws("scores")-0.12 else 0.0])
    S.chip(ov,d,(CX,1440),"blocks A through H, one 1-5 score",
           t,ws("system")-0.30,TH,i,size=32)

def s_output(ov,d,t,t0,i):
    S.statement(ov,d,["For the few","worth it."],t,t0+0.05,TH,i,size=128)
    S.rows(ov,d,[("A TAILORED CV","as a PDF, ATS-optimised"),
                 ("THE COMPANY","researched, not guessed"),
                 ("A CONTACT","a person, not an inbox")],
           t,ws("writes")-0.28,TH,i,y=880,h=132,stagger=0.0,lsize=42,vsize=28,
           lit=[1.0 if t>=ws("CV")-0.12 else 0.0,
                1.0 if t>=ws("researches")-0.12 else 0.0,
                1.0 if t>=ws("contact")-0.20 else 0.0])
    S.chip(ov,d,(CX,1440),"10+ evaluated in parallel with sub-agents",
           t,ws("company")-0.24,TH,i,size=30)

def s_filter(ov,d,t,t0,i):
    S.statement(ov,d,["Not a","spray-and-pray tool."],t,t0+0.05,TH,i,size=108)
    S.band(ov,d,["It is a filter."],t,ws("filter")-0.28,TH,i,y=800,size=64,
           col=(198,232,72),attrib="the README, verbatim")
    S.rows(ov,d,[("find","the few worth real effort")],
           t,ws("effort")-0.34,TH,i,y=1060,h=132,lsize=44,vsize=30,lit=[1])
    S.chip(ov,d,(CX,1440),"and the first evaluations won't be great -- their words",
           t,ws("worth",1)-0.20,TH,i,size=28)

def s_close(ov,d,t,t0,i):
    S.statement(ov,d,["MIT."],t,t0+0.05,TH,i,size=132)
    S.figure(ov,d,"740+","OFFERS HE EVALUATED",t,ws("seven")-0.30,TH,i,
             y=700,size=180,note="the author's own account")
    S.rows(ov,d,[("roles taken","1")],
           t,ws("took")-0.26,TH,i,y=1180,h=132,lsize=44,vsize=34,lit=[1])

def frame(t):
    i,n,a,b = scene_at(t)
    base = S.field_for(TH,i).copy()
    ov = Image.new("RGBA",(W,H),(0,0,0,0)); d = ImageDraw.Draw(ov)
    {"hook":s_hook,"what":s_what,"output":s_output,"filter":s_filter,
     "close":s_close}.get(n,lambda *_: None)(ov,d,t,a,i)
    if n=="end":
        S.endcard(ov,d,t,a,TH,i,"career-ops","a filter, not a firehose",
                  "github.com/santifer/career-ops","SAVE THIS FOR YOUR NEXT SEARCH",
                  mark_size=126)
    S.cut(ov,d,t,CUTS,TH,lambda tt: scene_at(tt)[0])
    S.rail(ov,d,t,TH,i,len(SC),(t-a)/max(b-a,0.01))
    S.footer(ov,d,TH,i,SLUG,len(SC))
    base.alpha_composite(ov)
    return base

SFX = (
 [{"t":c-0.18,"kind":"paper","amp":0.14} for c in CUTS] +
 [{"t":c,"kind":"slam","amp":0.24,"dur":0.24} for c in CUTS] +
 [{"t":ws("gives")-0.26,"kind":"riser","amp":0.11},
  {"t":ws("scans")-0.12,"kind":"chime","amp":0.07,"tone":392.0},
  {"t":ws("scores")-0.12,"kind":"chime","amp":0.07,"tone":494.0},
  {"t":ws("system")-0.30,"kind":"chime","amp":0.07,"tone":587.0},
  {"t":ws("CV")-0.12,"kind":"chime","amp":0.06,"tone":330.0},
  {"t":ws("researches")-0.12,"kind":"chime","amp":0.06,"tone":392.0},
  {"t":ws("contact")-0.20,"kind":"chime","amp":0.06,"tone":494.0},
  {"t":ws("filter")-0.28,"kind":"slam","amp":0.22,"dur":0.22},
  {"t":ws("effort")-0.34,"kind":"chime","amp":0.07,"tone":523.0},
  {"t":ws("seven")-0.30,"kind":"riser","amp":0.10},
  {"t":ws("took")-0.26,"kind":"chime","amp":0.08,"tone":659.0}]
)
