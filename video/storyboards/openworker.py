# ---------------------------------------------------------------
# openworker.py -- "OpenWorker" on the SLAB template. Warm neutral and
# teal. Scene 3 is the approval gate, which is the behaviour worth the
# video; scene 5 keeps the unsigned Windows build on screen, not buried.
# ---------------------------------------------------------------
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kit, slab as S
from kit import W, H, f, m, clamp, lin, eo3, eo4, eob, rgba, mix, tw, text
from slab import Theme, CX, CR, ink_for
from timing import Timing

NAME    = "openworker"
AUDIO   = "openworker.mp3"
PHRASES = "phrases/openworker.txt"
TOTAL   = 38.3
FPS     = 30
CAPTIONS = False

_T = Timing(NAME); ws, we = _T.ws, _T.we
SLUG = "andrewyng/openworker"

TH = Theme(fields=[(246,243,236),(22,52,58),(246,243,236),(0,150,150),
                   (22,52,58),(246,243,236)],
           mark=(0,150,150))
TH.apply()

SC = [("hook",0.00,5.40),("what",5.40,14.50),("gate",14.50,23.30),
      ("models",23.30,28.50),("close",28.50,34.10),("end",34.10,TOTAL)]
def scene_at(t):
    for i,(n,a,b) in enumerate(SC):
        if a<=t<b: return i,n,a,b
    return len(SC)-1,SC[-1][0],SC[-1][1],SC[-1][2]
CUTS = [a for _,a,_ in SC[1:]]

def s_hook(ov,d,t,t0,i):
    S.statement(ov,d,["You asked","for the thing.","You got a list."],t,0.10,TH,i,size=114)
    S.rows(ov,d,[("1. Gather the data",None),("2. Review the notes",None),
                 ("3. Draft the brief",None)],
           t,ws("list")-0.30,TH,i,y=980,h=112,gap=8,stagger=0.06,lsize=40)

def s_what(ov,d,t,t0,i):
    S.statement(ov,d,["An AI coworker","on your desktop."],t,t0+0.05,TH,i,size=116)
    S.rows(ov,d,[("you give it","the outcome"),
                 ("it works across","files, terminal, apps")],
           t,ws("outcome")-0.32,TH,i,y=900,h=134,lsize=44,vsize=32,
           lit=[1.0 if t>=ws("outcome")-0.12 else 0.0,
                1.0 if t>=ws("across")-0.12 else 0.0])
    S.chip(ov,d,(CX,1440),"your keys, your machine",
           t,ws("coworker")-0.20,TH,i,size=34)

GATES=[("SEND A MESSAGE","sending"),("CHANGE A CALENDAR","changing"),
       ("RUN A COMMAND","running")]
def s_gate(ov,d,t,t0,i):
    S.statement(ov,d,["Before anything","consequential,","it asks."],t,t0+0.05,TH,i,size=104)
    lit=[1.0 if t>=ws(c)-0.10 else 0.0 for _,c in GATES]
    ok = eo3(lin(t, ws("first")-0.18, ws("first")+0.34))
    S.rows(ov,d,[(a, "APPROVED" if ok>0.5 else "waiting for you") for a,_ in GATES],
           t,ws("sending")-0.26,TH,i,y=940,h=124,gap=8,stagger=0.0,
           lsize=40,vsize=28,lit=lit)
    S.chip(ov,d,(CX,1450),"you decide, then it proceeds",
           t,ws("first")-0.16,TH,i,size=34)

def s_models(ov,d,t,t0,i):
    S.statement(ov,d,["No model","lock-in."],t,t0+0.05,TH,i,size=132)
    S.rows(ov,d,[("OpenAI",None),("Anthropic",None),("Google",None),
                 ("Ollama","local")],
           t,ws("OpenAI")-0.26,TH,i,y=880,h=116,gap=8,stagger=0.0,
           lsize=44,vsize=30,
           lit=[1.0 if t>=c-0.10 else 0.0
                for c in (ws("OpenAI"),ws("Anthropic"),ws("Google"),ws("Ollama"))])
    S.chip(ov,d,(CX,1440),"bring your own key",t,ws("local")-0.26,TH,i,size=34)

def s_close(ov,d,t,t0,i):
    S.statement(ov,d,["MIT.","Open beta."],t,t0+0.05,TH,i,size=126)
    S.rows(ov,d,[("macOS","signed & notarized"),
                 ("Windows","not signed yet")],
           t,ws("beta")-0.20,TH,i,y=860,h=132,lsize=44,vsize=30,
           lit=[0.0, 1.0 if t>=ws("signed")-0.12 else 0.0])
    S.chip(ov,d,(CX,1440),"SmartScreen will warn -- their words",
           t,ws("Windows")-0.22,TH,i,size=32)

def frame(t):
    i,n,a,b = scene_at(t)
    base = S.field_for(TH,i).copy()
    ov = Image.new("RGBA",(W,H),(0,0,0,0)); d = ImageDraw.Draw(ov)
    {"hook":s_hook,"what":s_what,"gate":s_gate,"models":s_models,
     "close":s_close}.get(n,lambda *_: None)(ov,d,t,a,i)
    if n=="end":
        S.endcard(ov,d,t,a,TH,i,"OpenWorker","an AI coworker on your desktop",
                  "github.com/andrewyng/openworker","SAVE THIS FOR YOUR DESKTOP",
                  mark_size=124)
    S.cut(ov,d,t,CUTS,TH,lambda tt: scene_at(tt)[0])
    S.rail(ov,d,t,TH,i,len(SC),(t-a)/max(b-a,0.01))
    S.footer(ov,d,TH,i,SLUG,len(SC))
    base.alpha_composite(ov)
    return base

SFX = (
 [{"t":c-0.18,"kind":"paper","amp":0.14} for c in CUTS] +
 [{"t":c,"kind":"slam","amp":0.24,"dur":0.24} for c in CUTS] +
 [{"t":ws("list")-0.30,"kind":"chime","amp":0.07,"tone":330.0},
  {"t":ws("coworker")-0.20,"kind":"chime","amp":0.08,"tone":523.0},
  {"t":ws("outcome")-0.32,"kind":"chime","amp":0.08,"tone":440.0},
  {"t":ws("first")-0.18,"kind":"riser","amp":0.11},
  {"t":ws("local")-0.26,"kind":"chime","amp":0.07,"tone":659.0},
  {"t":ws("beta")-0.20,"kind":"chime","amp":0.08,"tone":392.0},
  {"t":ws("signed")-0.12,"kind":"slam","amp":0.18,"dur":0.20}] +
 [{"t":ws(c)-0.10,"kind":"chime","amp":0.055,"tone":294.0+k*66}
    for k,(_,c) in enumerate(GATES)] +
 [{"t":ws(c)-0.10,"kind":"chime","amp":0.05,"tone":392.0+k*44}
    for k,c in enumerate(("OpenAI","Anthropic","Google","Ollama"))]
)
