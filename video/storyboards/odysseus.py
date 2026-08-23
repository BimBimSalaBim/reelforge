# ---------------------------------------------------------------
# odysseus.py -- "Odysseus" on the Ledger template. Sea blue, bronze for
# the honest row. The opening list is read as eight separate beats, so the
# ledger rows land one per beat -- the template and the recording agree.
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

NAME    = "odysseus"
AUDIO   = "odysseus.mp3"
PHRASES = "phrases/odysseus.txt"
TOTAL   = 40.4
FPS     = 30

_T = Timing(NAME); WORDS = _T.words
ws, we = _T.ws, _T.we
CH = _T.chunks()
CAPTIONS = False
# no captions -> the band they occupied is free, so the scene layer sits lower
CONTENT_DY = 150

TH = Theme(bg=(8,11,16), accent=(86,164,255), accent_hi=(150,204,255),
           pale=(222,238,255), support=(214,164,96),
           grid=(26,32,44), rule=(52,62,80))
TH.apply()
BASE = L.build_ground(TH, seed=15)

SC = [("tools",0.00,8.63), ("run",8.63,15.65), ("two",15.65,26.75),
      ("stars",26.75,29.90), ("honest",29.90,36.25), ("end",36.25,TOTAL)]
def scene_at(t):
    for i,(n,a,b) in enumerate(SC):
        if a<=t<b: return i,n,a,b
    return len(SC)-1, SC[-1][0], SC[-1][1], SC[-1][2]
CUTS = [a for _,a,_ in SC[1:]]

TOOLS=[("CHAT","local or API models, tools, MCP","Chat"),
       ("AGENTS","files, shell, skills, memory","Agents"),
       ("DEEP RESEARCH","multi-step, with report generation","research"),
       ("DOCUMENTS","writing-first editor with AI edits","Documents"),
       ("EMAIL","IMAP/SMTP triage, summaries, drafts","Email"),
       ("NOTES","reminders and todos","Notes"),
       ("TASKS","scheduled agent tasks","tasks"),
       ("CALENDAR","CalDAV sync","calendar")]

# ---------------- 1. the pile-up ----------------
def s_tools(ov,d,t,t0):
    L.heading(ov,d,"ONE SELF-HOSTED WORKSPACE",t,0.10,TH,size=44)
    for i,(nm,sub,cue) in enumerate(TOOLS):
        c=ws(cue)
        lit=eo3(lin(t,c-0.10,c+0.34))
        L.row(ov,d,t,c-0.18,TH,392+i*82,nm,sub,lit=lit,h=72,lsize=30,vsize=24)
    ka=eo3(lin(t,ws("app")-0.16,ws("app")+0.44))
    if ka>0.02:
        d.line((CX,1088,CX+(RIGHT-CX)*ka,1088),fill=rgba(TH.accent,0.9),width=4)
        text(d,(CX,1146),"one app, on your own machine",
             f(40,"bold"),WHITE,ka,2,"lm")

# ---------------- 2. how you run it ----------------
def s_run(ov,d,t,t0):
    L.heading(ov,d,"ONE COMMAND",t,t0+0.06,TH,size=46)
    L.stamp(ov,d,t,ws("docker")-0.28,TH,(CX,470),
            "docker compose up -d --build",size=30)
    L.row(ov,d,t,ws("docker")+0.10,TH,610,"then open","localhost:7000",
          lit=eo3(lin(t,ws("docker")+0.20,ws("docker")+0.60)),h=92,lsize=34)
    L.row(ov,d,t,ws("choice")-0.42,TH,724,"models","local, or any API",
          lit=eo3(lin(t,ws("choice")-0.14,ws("choice")+0.40)),h=92,lsize=34)
    L.note(ov,d,t,t0+0.5,TH,850,
           "the first admin password is printed in the logs",size=27)
    L.row(ov,d,t,t0+0.75,TH,960,"branches","dev is default, main is stabler",
          lit=0.0,h=88,lsize=32,vsize=25)
    L.note(ov,d,t,t0+0.95,TH,1074,
           "native installs, GPU notes, HTTPS: docs/setup.md",size=25)

# ---------------- 3. the two surprises ----------------
def s_two(ov,d,t,t0):
    L.heading(ov,d,"TWO THINGS I DID NOT EXPECT",t,t0+0.06,TH,size=44)
    kc=eo3(lin(t,ws("cookbook")-0.14,ws("cookbook")+0.42))
    L.row(ov,d,t,ws("cookbook")-0.24,TH,450,"COOKBOOK",
          "hardware-aware, not a generic list",lit=kc,h=96,lsize=36,vsize=25)
    kh=eo3(lin(t,ws("hardware")-0.16,ws("hardware")+0.44))
    if kh>0.02:
        text(d,(CX,552),"scan your machine  →  ranked models  →  download  →  serve",
             m(26),mix(TH.faint,TH.accent_hi,kh),kh,0,"lm")
    kp=eo3(lin(t,ws("compare")-0.14,ws("compare")+0.42))
    L.row(ov,d,t,ws("compare")-0.24,TH,700,"COMPARE",
          "blind, side by side",lit=kp,h=96,lsize=36,vsize=25)
    kb=eo3(lin(t,ws("blind")-0.16,ws("blind")+0.46))
    if kb>0.02:
        for i,lab in enumerate(("MODEL A","MODEL B")):
            x=CX+i*((RIGHT-CX)/2+10)
            d.rectangle((x,800,x+(RIGHT-CX)/2-30,884),
                        outline=rgba(TH.accent,0.85*kb),width=3)
            text(d,(x+24,842),lab,m(28,"bold"),WHITE,kb,2,"lm")
        text(d,(CX,930),"names hidden, so you judge the output",
             m(26),TH.dim,kb*0.9,0,"lm")
    ky=eo3(lin(t,ws("synthesises")-0.16,ws("synthesises")+0.44))
    if ky>0.02:
        d.line((CX,1000,CX+(RIGHT-CX)*ky,1000),fill=rgba(TH.accent,0.9),width=4)
        text(d,(CX,1056),"then synthesises the answer",
             f(36,"bold"),WHITE,ky,2,"lm")

# ---------------- 4. the number ----------------
def s_stars(ov,d,t,t0):
    L.heading(ov,d,"THE NUMBERS",t,t0+0.06,TH,size=46)
    L.counter(ov,d,t,ws("Eighty-six")-0.26,TH,470,85923,label="STARS",
              dur=1.00,vsize=126)
    L.row(ov,d,t,t0+0.30,TH,700,"age","under 3 months",lit=0.0,h=88)
    L.row(ov,d,t,t0+0.45,TH,808,"forks","577",lit=0.0,h=88)
    L.note(ov,d,t,t0+0.65,TH,910,
           "a lot of bookmarking, not much building on it yet",size=26)

# ---------------- 5. the honest part ----------------
def s_honest(ov,d,t,t0):
    L.heading(ov,d,"READ THIS FIRST",t,t0+0.06,TH,size=46)
    L.note(ov,d,t,ws("roadmap")-0.24,TH,400,
           "ROADMAP.md, in the maintainer's own words",size=27)
    L.quote(ov,d,t,ws("words")-0.20,TH,470,
            ["It works great for me (lol),","but this ship is moving fast"],
            attrib="ROADMAP.md",col=TH.support,size=36)
    kg=eo3(lin(t,ws("great")-0.14,ws("great")+0.44))
    if kg>0.02:
        text(d,(CX,700),"that is honesty, not a warning label",
             m(27),TH.dim,kg,0,"lm")
    L.row(ov,d,t,t0+0.35,TH,830,"licence","AGPL-3.0",
          lit=0.0,h=90,lsize=34,col=TH.support)
    L.row(ov,d,t,ws("deploy")-0.34,TH,940,"before exposing it","AUTH_ENABLED=true",
          lit=eo3(lin(t,ws("deploy")-0.14,ws("deploy")+0.40)),h=90,lsize=34)
    L.note(ov,d,t,t0+0.60,TH,1050,
           "THREAT_MODEL.md ships in the repo",size=26)

# ---------------- dispatch ----------------
def frame(t):
    base = BASE.copy()
    sc = Image.new("RGBA",(W,H),(0,0,0,0)); sd = ImageDraw.Draw(sc)
    idx,n,a,b = scene_at(t)
    {"tools":s_tools,"run":s_run,"two":s_two,"stars":s_stars,
     "honest":s_honest}.get(n,lambda *_: None)(sc,sd,t,a)
    ov = Image.new("RGBA",(W,H),(0,0,0,0)); d = ImageDraw.Draw(ov)
    ov.alpha_composite(sc,(0,CONTENT_DY))
    if n=="end":
        L.endcard(ov,d,t,a,TH,"Odysseus","a self-hosted AI workspace",
                  "github.com/odysseus-dev/odysseus","docker compose up -d --build",
                  "SAVE THIS FOR YOUR NEXT SERVER",mark_size=140)
    L.chrome(ov,d,t,TH,TOTAL,"odysseus-dev/odysseus",SC,idx)
    L.advance(ov,d,t,CUTS,TH)
    # Burned-in captions are OFF by default (see DEVELOPMENT.md). Flip CAPTIONS
    # to True only when the brief asks for them.
    if CAPTIONS and n!="end": L.captions(ov,d,t,CH,TH)
    base.alpha_composite(ov)
    return base

_BIG = {15.65, 29.90, 36.25}
SFX = (
 [{"t":c-0.24,"kind":"shift","amp":0.10} for c in CUTS] +
 [{"t":c,"kind":"latch","amp":0.26 if c in _BIG else 0.19,
   "dur":0.22 if c in _BIG else 0.16} for c in CUTS] +
 [{"t":ws(c)-0.10,"kind":"click","amp":0.075,"tone":2300.0+i*95}
    for i,(_,_,c) in enumerate(TOOLS)] +
 [{"t":ws("app")-0.16,"kind":"rule","amp":0.11},
  {"t":ws("docker")-0.28,"kind":"click","amp":0.10,"tone":3000.0},
  {"t":ws("choice")-0.14,"kind":"click","amp":0.09,"tone":2700.0},
  {"t":ws("cookbook")-0.14,"kind":"click","amp":0.10,"tone":3200.0},
  {"t":ws("hardware")-0.16,"kind":"rule","amp":0.09},
  {"t":ws("compare")-0.14,"kind":"click","amp":0.10,"tone":2500.0},
  {"t":ws("blind")-0.16,"kind":"click","amp":0.09,"tone":2900.0},
  {"t":ws("synthesises")-0.16,"kind":"rule","amp":0.11},
  {"t":ws("Eighty-six")-0.26,"kind":"rule","amp":0.10},
  {"t":ws("words")-0.20,"kind":"latch","amp":0.20,"dur":0.18},
  {"t":ws("deploy")-0.14,"kind":"latch","amp":0.22,"dur":0.20}]
)
