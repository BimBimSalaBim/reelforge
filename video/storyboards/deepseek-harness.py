# ---------------------------------------------------------------
# deepseek-harness.py -- "dsh". Indigo. The story is the star count
# and the plugin architecture; the developer-preview warning is the beat
# that buys credibility.
# ---------------------------------------------------------------
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kit, sbkit as S
from kit import (W,H,MARGIN,f,m,clamp,lin,eo3,eo4,eob,pulse,rgba,mix,tw,text,
                 grad_text,wrap,put_glow,card,pill,hline)
from sbkit import Theme, WHITE, enter, tile, statcard, terminal, counter, endcard
from timing import Timing

NAME    = "deepseek-harness"
AUDIO   = "deepseek-harness.mp3"
PHRASES = "phrases/deepseek-harness.txt"
TOTAL   = 37.6
FPS     = 30

_T=Timing(NAME); WORDS=_T.words
ws,we = _T.ws, _T.we
CH=_T.chunks()

TH=Theme(bg=(7,9,16),accent=(93,120,254),accent_hi=(148,167,255),
         pale=(214,222,255),glow=(38,58,150),support=(96,214,255))
TH.apply()
BASE=S.build_base(TH,seed=5,bloom=0.30)

SC=[("hook",0.00,3.28),("stars",3.28,6.62),("idea",6.62,13.10),
    ("plugins",13.10,23.24),("warn",23.24,27.58),("close",27.58,35.95),
    ("end",35.95,TOTAL)]
def scene_at(t):
    for n,a,b in SC:
        if a<=t<b: return n,a,b
    return SC[-1]
CUTS=[a for _,a,_ in SC[1:]]

# ---------------- 1. hook ----------------
def s_hook(ov,d,t,t0):
    S.eyebrow(ov,d,"13 AUGUST 2026",t,0.0,TH)
    k,dy=enter(t,0.0,0.30,20)
    text(d,(MARGIN,402+dy),"DeepSeek pushed",f(88,"bold"),WHITE,k,0,"lt")
    k2,dy2=enter(t,ws("pushed")-0.10,0.34,24)
    text(d,(MARGIN,504+dy2),"a new repo.",f(88,"bold"),TH.accent,k2,0,"lt")
    k3,dy3=enter(t,0.86,0.36,20)
    if k3>0.01:
        hline(d,MARGIN,MARGIN+int(240*k3),638+dy3,TH.accent,0.85,4)
        text(d,(MARGIN,690+dy3),"deepseek-ai/deepseek-harness",m(34),TH.muted,k3,0,"lt")
        text(d,(MARGIN,748+dy3),"an official DeepSeek AI project",m(28),TH.dim,k3,0,"lt")
    k4,dy4=enter(t,ws("repo.")-0.10,0.4,18)
    if k4>0.01:
        box=(MARGIN,840+dy4,W-MARGIN,976+dy4)
        card(d,box,22,TH.card,0.85*k4,TH.border,0.9*k4,2)
        text(d,(MARGIN+36,880+dy4),"CREATED",f(25,"bold"),TH.dim,k4,4,"lt")
        text(d,(MARGIN+36,918+dy4),"13 AUG 2026",m(38,"bold"),WHITE,k4,0,"lt")
        text(d,(W-MARGIN-36,880+dy4),"AGE",f(25,"bold"),TH.dim,k4,4,"rt")
        text(d,(W-MARGIN-36,918+dy4),"6 DAYS",m(38,"bold"),TH.support,k4,0,"rt")

# ---------------- 2. the star count ----------------
def s_stars(ov,d,t,t0):
    S.eyebrow(ov,d,"AND ALREADY",t,t0,TH)
    ts=ws("hundred")-0.55
    counter(ov,d,(540,560),165399,t,ts,TH,dur=2.45,size=146,
            label="GITHUB STARS")
    k,dy=enter(t,t0+0.45,0.4,24)
    if k>0.01:
        cw=(W-2*MARGIN-32)/3
        for i,(v,l) in enumerate([("6","DAYS OLD"),("17.6K","FORKS"),("MIT","LICENCE")]):
            x=MARGIN+i*(cw+16)
            kk=eo3(lin(t,t0+0.55+i*0.16,t0+0.90+i*0.16))
            if kk<=0.01: continue
            card(d,(x,838+dy,x+cw,838+150+dy),22,TH.card,0.85*kk,TH.border,0.9*kk,2)
            grad_text(ov,(x+cw/2,838+26+dy),v,f(52,"bold"),TH.accent_hi,TH.accent,kk,"mt")
            text(d,(x+cw/2,838+118+dy),l,f(24,"bold"),TH.muted,kk,3,"mm")
    k2,_=enter(t,t0+2.25,0.4,0)
    if k2>0.01:
        text(d,(540,1064),"that is about 27,000 stars a day",m(29),TH.dim,k2,0,"mt")

# ---------------- 3. one idea ----------------
def s_idea(ov,d,t,t0):
    S.eyebrow(ov,d,"ONE IDEA",t,t0,TH)
    fo=f(66,"bold")
    for i,(txt,ts) in enumerate([("It's an open-source runtime",ws("open-source")-0.30),
                                 ("for coding agents,",ws("coding")-0.10),
                                 ("built on one idea:",ws("idea:")-0.35)]):
        k,dy=enter(t,ts,0.34,20)
        text(d,(MARGIN,372+i*88+dy),txt,fo,TH.muted if i<2 else WHITE,k,0,"lt")
    kb=eob(lin(t,ws("everything")-0.22,ws("everything")+0.5),2.0)
    if kb>0.01:
        put_glow(ov,540,830,TH.glow,760,0.28*min(1,kb))
        for i,(txt,col) in enumerate([("EVERYTHING",WHITE),("IS A PLUGIN",TH.accent_hi)]):
            kk=eo3(lin(t,ws("everything")-0.20+i*0.18,ws("everything")+0.22+i*0.18))
            grad_text(ov,(540,732+i*112),txt,f(98,"bold"),
                      WHITE if i==0 else TH.accent_hi,
                      TH.pale if i==0 else TH.accent,kk,"mt",2)
    k2,_=enter(t,ws("plugin.")+0.10,0.4,0)
    if k2>0.01:
        hline(d,540-140,540+140,1000,TH.accent,0.7*k2,3)
        text(d,(540,1042),"powered by Cordis",m(30),TH.dim,k2,0,"mt")

# ---------------- 4. the plugin grid ----------------
PLUG=[("llm",ws("model,")),("sandbox",ws("sandbox,")),("mcp",ws("MCP,")),
      ("subagent",ws("subagents,")),("skill",ws("skills,")),("hooks",ws("hooks"))]
SWAP=ws("swapped")-0.55
def s_plugins(ov,d,t,t0):
    S.eyebrow(ov,d,"SWAP ANY OF THEM",t,t0,TH)
    cw=(W-2*MARGIN-28)/2; chh=150
    for i,(nm,ts) in enumerate(PLUG):
        col=i%2; row=i//2
        x=MARGIN+col*(cw+28); y=344+row*(chh+22)
        k,dy=enter(t,t0+0.10+i*0.06,0.30,20)
        lit=eo3(lin(t,ts-0.06,ts+0.26))
        # the mcp tile is the one that gets swapped out
        if i==2 and t>=SWAP:
            out=eo3(lin(t,SWAP,SWAP+0.34))
            inn=eo3(lin(t,SWAP+0.30,SWAP+0.66))
            if out<0.98:
                tile(ov,d,(x,y-out*70,x+cw,y+chh-out*70),nm,lit,TH,
                     k*(1-out),mono=True)
            if inn>0.01:
                tile(ov,d,(x,y+(1-inn)*70,x+cw,y+chh+(1-inn)*70),"your own",1.0,TH,
                     inn,sub="drop-in replacement",mono=True)
            continue
        tile(ov,d,(x,y+dy,x+cw,y+chh+dy),nm,lit,TH,k,mono=True)
    k2,dy2=enter(t,ws("forty-plus")-0.20,0.36,22)
    if k2>0.01:
        box=(MARGIN,872+dy2,W-MARGIN,1010+dy2)
        card(d,box,22,TH.card,0.85*k2,TH.border,0.9*k2,2)
        grad_text(ov,(MARGIN+40,882+dy2),"40+",f(64,"bold"),TH.accent_hi,TH.accent,k2,"lt")
        text(d,(MARGIN+180,944+dy2),"PACKAGES UNDER packages/",f(28,"bold"),
             TH.muted,k2,3,"lm")
    k3,_=enter(t,SWAP+0.45,0.4,0)
    if k3>0.01:
        text(d,(540,1072),"every one of them is just a package",
             f(34,"med"),TH.accent_hi,k3,0,"mt")

# ---------------- 5. the warning ----------------
def s_warn(ov,d,t,t0):
    S.eyebrow(ov,d,"FAIR WARNING",t,t0,TH,col=TH.warn)
    k,dy=enter(t,ws("developer")-0.30,0.34,24)
    text(d,(MARGIN,368+dy),"it's a developer preview,",f(64,"bold"),WHITE,k,0,"lt")
    kb=eob(lin(t,ws("break.")-0.30,ws("break.")+0.42),2.2)
    if kb<=0.01: return
    box=(MARGIN,478,W-MARGIN,872)
    x0,y0,x1,y1=box
    card(d,box,24,(26,20,10),0.95*min(1,kb),TH.warn,0.65*min(1,kb),3)
    put_glow(ov,540,690,(150,100,20),560,0.16*min(1,kb))
    # hazard stripes along the top edge of the panel
    for i in range(-1,26):
        xa=x0+i*38
        d.polygon([(xa,y0+8),(xa+18,y0+8),(xa+2,y0+40),(xa-16,y0+40)],
                  fill=rgba(TH.warn,0.20*min(1,kb)))
    fo=f(52,"bold")
    for i,ln in enumerate(["THERE WILL BE","COMPATIBILITY-","BREAKING CHANGES"]):
        kk=eo3(lin(t,ws("break.")-0.26+i*0.10,ws("break.")+0.16+i*0.10))
        text(d,(540,y0+86+i*66),ln,fo,TH.warn,kk,1,"mt")
    k3=eo3(lin(t,ws("break.")+0.40,ws("break.")+0.80))
    text(d,(540,y1-52),"— the README, verbatim",m(28),TH.muted,k3,0,"mm")
    k4,_=enter(t,ws("break.")+0.42,0.4,0)
    if k4>0.01:
        text(d,(540,928),"not for production. Excellent for reading.",
             f(34,"med"),TH.muted,k4,0,"mt")

# ---------------- 6. the close ----------------
CMD=[("npx @deepseek-ai/dsh web",ws("npx")-0.20,ws("npx")+0.95)]
def s_close(ov,d,t,t0):
    S.eyebrow(ov,d,"AND YET",t,t0,TH)
    kb=eob(lin(t,ws("MIT,")-0.16,ws("MIT,")+0.46),2.0)
    if kb>0.01:
        pill(d,540,348,"MIT LICENSED",f(32,"bold"),TH.ok,kb,track=5)
    chips=[("PYTHON SDK",ws("Python")-0.10),("WEB UI",ws("UI,")-0.30),
           ("MCP + ACP",ws("UI,")+0.20),("SANDBOXES",ws("UI,")+0.55)]
    cw=(W-2*MARGIN-24)/2
    for i,(nm,ts) in enumerate(chips):
        x=MARGIN+(i%2)*(cw+24); y=436+(i//2)*116
        lit=eo3(lin(t,ts,ts+0.28))
        k,dy=enter(t,ts-0.12,0.30,18)
        tile(ov,d,(x,y+dy,x+cw,y+92+dy),nm,lit,TH,k)
    kt,dyt=enter(t,ws("npx")-0.45,0.34,24)
    if kt>0.01:
        terminal(ov,d,(MARGIN,712+dyt,W-MARGIN,912+dyt),CMD,t,TH,
                 title="your machine",fs=32)
    ko=eo3(lin(t,ws("machine.")-0.35,ws("machine.")+0.10))
    if ko>0.01:
        box=(MARGIN,948,W-MARGIN,1064)
        card(d,box,20,TH.card,0.85*ko,TH.border,0.9*ko,2)
        d.ellipse((MARGIN+34,996,MARGIN+56,1018),fill=rgba(TH.ok,ko))
        text(d,(MARGIN+80,1006),"127.0.0.1:3080",m(36,"bold"),WHITE,ko,0,"lm")
        text(d,(W-MARGIN-30,1006),"LOCAL WEB UI",f(25,"bold"),TH.muted,ko,3,"rm")

# ---------------- dispatch ----------------
def frame(t):
    base=BASE.copy()
    ov=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(ov)
    n,a,b=scene_at(t)
    {"hook":s_hook,"stars":s_stars,"idea":s_idea,"plugins":s_plugins,
     "warn":s_warn,"close":s_close}.get(n,lambda *_: None)(ov,d,t,a)
    if n=="end":
        endcard(ov,d,t,a,TH,"dsh","DeepSeek Harness",
                "deepseek-ai/deepseek-harness","deepseek.com/harness",
                "SAVE THIS FOR LATER",mark_size=240,mono_mark=True)
    S.chrome(base,d,t,TH,TOTAL,"deepseek-ai/dsh")
    S.cut_sweep(ov,d,t,CUTS,TH)
    if n!="end": S.captions(ov,d,t,CH,TH)
    base.alpha_composite(ov)
    return base

_BIG={35.95}
SFX=(
 [{"t":c-0.30,"kind":"swish","amp":0.15} for c in CUTS] +
 [{"t":c,"kind":"thump","amp":0.29 if c in _BIG else 0.20,
   "dur":0.55 if c in _BIG else 0.34,"freq":46.0 if c in _BIG else 58.0}
    for c in CUTS] +
 [{"t":ts,"kind":"tick","amp":0.08,"tone":2600.0} for _,ts in PLUG] +
 [{"t":ws("hundred")-0.55,"kind":"tick","amp":0.075,"tone":3000.0},
  {"t":SWAP,"kind":"thump","amp":0.15,"dur":0.30,"freq":62.0},
  {"t":ws("break.")-0.30,"kind":"thump","amp":0.24,"dur":0.45,"freq":50.0},
  {"t":ws("npx")-0.20,"kind":"tick","amp":0.07,"tone":3000.0},
  {"t":ws("machine.")-0.35,"kind":"tick","amp":0.09,"tone":3200.0}]
)
