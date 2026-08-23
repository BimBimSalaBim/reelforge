# ---------------------------------------------------------------
# graphify.py -- "graphify" on the Ledger template. Indigo.
# The spine is the argument: your agent re-reads, so build the map once.
# Scene 4 is the payoff -- an edge you can tell apart from a guess.
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

NAME    = "graphify"
AUDIO   = "graphify.mp3"
PHRASES = "phrases/graphify.txt"
TOTAL   = 46.4
FPS     = 30

_T = Timing(NAME); WORDS = _T.words
ws, we = _T.ws, _T.we
CH = _T.chunks()
CAPTIONS = False
# no captions -> the band they occupied is free, so the scene layer sits lower
CONTENT_DY = 150

TH = Theme(bg=(9,10,16), accent=(124,140,255), accent_hi=(176,188,255),
           pale=(226,230,255), support=(0,220,180),
           grid=(28,30,44), rule=(56,60,80))
TH.apply()
BASE = L.build_ground(TH, seed=12)

SC = [("reread",0.00,5.95), ("graph",5.95,11.95), ("build",11.95,18.20),
      ("edges",18.20,26.40), ("notvec",26.40,34.50), ("close",34.50,42.50),
      ("end",42.50,TOTAL)]
def scene_at(t):
    for i,(n,a,b) in enumerate(SC):
        if a<=t<b: return i,n,a,b
    return len(SC)-1, SC[-1][0], SC[-1][1], SC[-1][2]
CUTS = [a for _,a,_ in SC[1:]]

def dashed(d,x0,y,x1,col,a=0.9,w=3,dash=16,gap=11):
    x=x0
    while x<x1:
        d.line((x,y,min(x+dash,x1),y),fill=rgba(col,a),width=w); x+=dash+gap

# ---------------- 1. it re-reads, every time ----------------
def s_reread(ov,d,t,t0):
    L.heading(ov,d,"EVERY SESSION, FROM SCRATCH",t,0.10,TH,size=44)
    files="read main.py   read routing.py   read models.py   read deps.py"
    for i in range(3):
        y=460+i*118
        L.row(ov,d,t,0.20+i*0.26,TH,y,f"session {i+1}",None,lit=0.0,h=92,lsize=30)
        text(d,(CX+250,y),files,m(24),TH.faint,
             0.95*L.wk(t,0.20+i*0.26,0.28),0,"lm")
    km=eo3(lin(t,ws("never")-0.16,ws("never")+0.44))
    if km>0.02:
        d.line((CX,900,CX+(RIGHT-CX)*km,900),fill=rgba(TH.support,0.9),width=4)
        text(d,(CX,956),"and it never builds a map",f(40,"bold"),WHITE,km,2,"lm")
        text(d,(CX,1016),"the map is thrown away with the context window",
             m(27),TH.dim,km*0.9,0,"lm")

# ---------------- 2. one graph instead ----------------
SRC=[("code","code",0),("docs","docs",None),("SQL schemas","SQL",None),
     ("PDFs","PDFs",None)]
def s_graph(ov,d,t,t0):
    L.heading(ov,d,"ALL OF IT, ONE GRAPH",t,t0+0.06,TH,size=46)
    for i,(lab,cue,nth) in enumerate(SRC):
        c=ws(cue,nth or 0)
        lit=eo3(lin(t,c-0.12,c+0.36))
        L.row(ov,d,t,c-0.22,TH,450+i*104,lab,"→ graph",lit=lit,h=86,lsize=32)
    kg=eo3(lin(t,ws("graph")-0.16,ws("graph")+0.44))
    if kg>0.02:
        d.line((CX,900,CX+(RIGHT-CX)*kg,900),fill=rgba(TH.accent,0.9),width=4)
        text(d,(CX,958),"one graph you query",f(44,"bold"),WHITE,kg,2,"lm")
    L.stamp(ov,d,t,t0+0.30,TH,(CX,1064),"/graphify .",size=30)
    L.note(ov,d,t,t0+0.50,TH,1160,
           "graph.html  ·  GRAPH_REPORT.md  ·  graph.json",size=26)

# ---------------- 3. how it is built ----------------
def s_build(ov,d,t,t0):
    L.heading(ov,d,"BUILT LOCALLY, NO MODEL",t,t0+0.06,TH,size=44)
    L.row(ov,d,t,ws("tree-sitter")-0.30,TH,470,"parsed with","tree-sitter AST",
          lit=eo3(lin(t,ws("tree-sitter")-0.14,ws("tree-sitter")+0.36)),h=88)
    L.row(ov,d,t,ws("locally")-0.24,TH,582,"runs","on your machine",
          lit=eo3(lin(t,ws("locally")-0.14,ws("locally")+0.36)),h=88)
    L.row(ov,d,t,ws("locally")+0.10,TH,694,"languages","~40",lit=0.0,h=88)
    L.counter(ov,d,t,ws("Zero")-0.26,TH,880,0,label="LLM CREDITS TO BUILD IT",
              dur=0.5,vsize=124,col=TH.support)
    L.note(ov,d,t,ws("Zero")+0.30,TH,1050,
           "deterministic  ·  nothing leaves the machine",size=27)

# ---------------- 4. every edge is labelled (the payoff) ----------------
def s_edges(ov,d,t,t0):
    L.heading(ov,d,"EVERY EDGE IS LABELLED",t,t0+0.06,TH,size=46)
    ke=eo3(lin(t,ws("extracted")-0.14,ws("extracted")+0.42))
    ki=eo3(lin(t,ws("inferred")-0.14,ws("inferred")+0.42))
    if ke>0.02:
        y=500
        text(d,(CX,y),"EXTRACTED",f(40,"bold"),mix(TH.dim,WHITE,ke),ke,3,"lm")
        d.line((CX,y+52,CX+(RIGHT-CX-260)*ke,y+52),fill=rgba(TH.accent_hi,0.95),width=4)
        text(d,(RIGHT,y),"explicit in the source",m(26),
             mix(TH.faint,TH.accent_hi,ke),ke,0,"rm")
    if ki>0.02:
        y=680
        text(d,(CX,y),"INFERRED",f(40,"bold"),mix(TH.dim,WHITE,ki),ki,3,"lm")
        dashed(d,CX,y+52,CX+(RIGHT-CX-260)*ki,TH.support,0.95)
        text(d,(RIGHT,y),"resolved by graphify",m(26),
             mix(TH.faint,TH.support,ki),ki,0,"rm")
    kw=eo3(lin(t,ws("inferred")+0.50,ws("inferred")+0.94))
    if kw>0.02:
        d.line((CX,860,CX+(RIGHT-CX)*kw,860),fill=rgba(TH.rule,0.9),width=2)
        text(d,(CX,918),"so you can tell what it knew",f(38,"bold"),WHITE,kw,2,"lm")
        text(d,(CX,972),"from what it guessed",f(38,"bold"),TH.accent_hi,kw,2,"lm")
    L.note(ov,d,t,ws("inferred")+0.80,TH,1080,
           "graphify explain \"APIRouter\"   →   47 connections, each tagged",size=25)

# ---------------- 5. not a vector store ----------------
HOPS=[("FastAPI",None),("DefaultPlaceholder","uses"),("ModelField","uses")]
def s_notvec(ov,d,t,t0):
    L.heading(ov,d,"NOT A VECTOR STORE",t,t0+0.06,TH,size=46)
    L.row(ov,d,t,ws("vector")-0.24,TH,460,"vector index","NONE",
          lit=eo3(lin(t,ws("vector")-0.12,ws("vector")+0.36)),
          h=86,col=TH.support)
    L.row(ov,d,t,ws("embeddings")-0.24,TH,566,"embeddings","NONE",
          lit=eo3(lin(t,ws("embeddings")-0.12,ws("embeddings")+0.36)),
          h=86,col=TH.support)
    kp=eo3(lin(t,ws("path")-0.20,ws("path")+0.50))
    if kp>0.02:
        text(d,(CX,700),"a path you can walk",m(28),TH.muted,kp,0,"lm")
        for i,(n_,edge) in enumerate(HOPS):
            kk=eo3(lin(t,ws("path")-0.10+i*0.22,ws("path")+0.24+i*0.22))
            if kk<=0.01: continue
            y=780+i*112
            d.rectangle((CX,y-30,CX+6,y+30),fill=rgba(TH.accent,0.95*kk))
            text(d,(CX+28,y),n_,m(34,"bold"),WHITE,kk,0,"lm")
            if edge:
                text(d,(RIGHT,y),f"--{edge}-->",m(25),TH.accent_hi,kk*0.9,0,"rm")
    kh=eo3(lin(t,ws("path")+1.00,ws("path")+1.44))
    if kh>0.02:
        text(d,(CX,1160),"shortest path, 3 hops",f(34,"bold"),TH.accent_hi,kh,2,"lm")

# ---------------- 6. the close ----------------
PLAT=[("Claude Code","Code",2),("Cursor","Cursor",0),("Codex","Codex",0),
      ("and 15+ more","fifteen",0)]
def s_close(ov,d,t,t0):
    L.heading(ov,d,"WHERE IT RUNS",t,t0+0.06,TH,size=46)
    L.stamp(ov,d,t,ws("Apache")-0.16,TH,(CX,420),"APACHE-2.0",size=30,col=TH.ok)
    L.counter(ov,d,t,ws("hundred")-0.26,TH,560,109387,label="STARS",
              dur=1.05,vsize=112)
    for i,(lab,cue,nth) in enumerate(PLAT):
        c=ws(cue,nth)
        L.row(ov,d,t,c-0.22,TH,780+i*98,lab,None,
              lit=eo3(lin(t,c-0.12,c+0.36)),h=82,lsize=32)
    L.note(ov,d,t,ws("hundred")+1.20,TH,1210,
           "uv tool install graphifyy   ·   graphify install",size=26)

# ---------------- dispatch ----------------
def frame(t):
    base = BASE.copy()
    sc = Image.new("RGBA",(W,H),(0,0,0,0)); sd = ImageDraw.Draw(sc)
    idx,n,a,b = scene_at(t)
    {"reread":s_reread,"graph":s_graph,"build":s_build,"edges":s_edges,
     "notvec":s_notvec,"close":s_close}.get(n,lambda *_: None)(sc,sd,t,a)
    ov = Image.new("RGBA",(W,H),(0,0,0,0)); d = ImageDraw.Draw(ov)
    ov.alpha_composite(sc,(0,CONTENT_DY))
    if n=="end":
        L.endcard(ov,d,t,a,TH,"graphify","your codebase as a graph",
                  "github.com/Graphify-Labs/graphify","uv tool install graphifyy",
                  "SAVE THIS FOR YOUR NEXT REPO",mark_size=150)
    L.chrome(ov,d,t,TH,TOTAL,"Graphify-Labs/graphify",SC,idx)
    L.advance(ov,d,t,CUTS,TH)
    # Burned-in captions are OFF by default (see DEVELOPMENT.md). Flip CAPTIONS
    # to True only when the brief asks for them.
    if CAPTIONS and n!="end": L.captions(ov,d,t,CH,TH)
    base.alpha_composite(ov)
    return base

_BIG = {18.20, 26.40, 42.50}
SFX = (
 [{"t":c-0.24,"kind":"shift","amp":0.10} for c in CUTS] +
 [{"t":c,"kind":"latch","amp":0.26 if c in _BIG else 0.19,
   "dur":0.22 if c in _BIG else 0.16} for c in CUTS] +
 [{"t":0.20+i*0.26,"kind":"click","amp":0.07,"tone":2300.0+i*120} for i in range(3)] +
 [{"t":ws("map")-0.16,"kind":"latch","amp":0.19,"dur":0.18},
  {"t":ws("graph")-0.16,"kind":"rule","amp":0.11},
  {"t":ws("tree-sitter")-0.14,"kind":"click","amp":0.09,"tone":3000.0},
  {"t":ws("locally")-0.14,"kind":"click","amp":0.09,"tone":2700.0},
  {"t":ws("Zero")-0.26,"kind":"rule","amp":0.10},
  {"t":ws("extracted")-0.14,"kind":"click","amp":0.10,"tone":3300.0},
  {"t":ws("inferred")-0.14,"kind":"click","amp":0.10,"tone":2500.0},
  {"t":ws("out")-0.16,"kind":"latch","amp":0.20,"dur":0.18},
  {"t":ws("vector")-0.12,"kind":"click","amp":0.09,"tone":2200.0},
  {"t":ws("embeddings")-0.12,"kind":"click","amp":0.09,"tone":2200.0},
  {"t":ws("hops")-0.16,"kind":"rule","amp":0.10},
  {"t":ws("Apache")-0.16,"kind":"click","amp":0.09,"tone":2900.0},
  {"t":ws("hundred")-0.26,"kind":"rule","amp":0.09}] +
 [{"t":ws(c,nth)-0.12,"kind":"click","amp":0.08,"tone":2600.0+i*130}
    for i,(_,c,nth) in enumerate(PLAT)] +
 [{"t":ws(c,nth or 0)-0.12,"kind":"click","amp":0.08,"tone":2400.0+i*140}
    for i,(_,c,nth) in enumerate(SRC)] +
 [{"t":ws("path")-0.10+i*0.22,"kind":"click","amp":0.075,"tone":2800.0+i*160}
    for i in range(3)]
)
