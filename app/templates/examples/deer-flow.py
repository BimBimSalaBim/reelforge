# ---------------------------------------------------------------
# deer-flow.py -- "DeerFlow 2.0". Emerald. The arc is drift -> rewrite ->
# what it is now, and the payoff visual is progressive skill loading:
# a full catalog greyed out, one skill lit, the context bar barely moving.
# ---------------------------------------------------------------
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kit, sbkit as S
from kit import (W,H,MARGIN,f,m,clamp,lin,eo3,eo4,eob,pulse,rgba,mix,tw,text,
                 grad_text,wrap,put_glow,card,pill,hline)
from sbkit import Theme, WHITE, enter, tile, statcard, terminal, counter, endcard, bar
from timing import Timing

NAME    = "deer-flow"
AUDIO   = "deer-flow.mp3"
PHRASES = "phrases/deer-flow.txt"
TOTAL   = 39.9
FPS     = 30

_T=Timing(NAME); WORDS=_T.words
ws,we = _T.ws, _T.we
CH=_T.chunks()

TH=Theme(bg=(6,13,12),accent=(34,214,158),accent_hi=(126,240,200),
         pale=(214,250,238),glow=(16,110,90),support=(240,190,90))
TH.apply()
BASE=S.build_base(TH,seed=11,bloom=0.32)

# "Things ByteDance never planned for." (8.03-9.83) is the PAYOFF of the drift,
# so the cut belongs after it, not before.
SC=[("drift",0.00,10.00),("rewrite",10.00,15.86),("now",15.86,26.40),
    ("lean",26.40,31.34),("close",31.34,38.25),("end",38.25,TOTAL)]
def scene_at(t):
    for n,a,b in SC:
        if a<=t<b: return n,a,b
    return SC[-1]
CUTS=[a for _,a,_ in SC[1:]]

# ---------------- 1. the drift ----------------
DRIFT=[("DASHBOARDS",ws("dashboards,")),("DATA PIPELINES",ws("pipelines,")),
       ("SLIDE DECKS",ws("decks."))]
def s_drift(ov,d,t,t0):
    S.eyebrow(ov,d,"IT STARTED AS",t,0.0,TH)
    k=eo3(lin(t,0.05,0.42)); kb=eob(lin(t,0.05,0.62),1.6)
    box=(MARGIN+40,352,W-MARGIN-40,506)
    card(d,box,24,(12,26,24),0.95*k,TH.accent,0.6*k,3)
    put_glow(ov,540,429,TH.glow,540,0.18*k)
    grad_text(ov,(540,378),"DEEP RESEARCH",f(int(56*(0.94+0.06*kb)),"bold"),
              WHITE,TH.pale,k,"mt",3)
    text(d,(540,458),"a framework for one job",m(27),TH.muted,
         eo3(lin(t,0.45,0.85)),0,"mt")
    # then the jobs nobody planned for
    for i,(nm,ts) in enumerate(DRIFT):
        kk,dy=enter(t,ts-0.22,0.34,26)
        if kk<=0.01: continue
        y=580+i*136+dy
        card(d,(MARGIN,y,W-MARGIN,y+108),20,TH.card,0.90*kk,TH.support,0.45*kk,2)
        d.line((540,y-28,540,y),fill=rgba(TH.support,0.35*kk),width=3)
        text(d,(MARGIN+34,y+54),nm,f(38,"bold"),WHITE,kk,2,"lm")
        text(d,(W-MARGIN-34,y+54),"not the plan",m(25),TH.support,kk*0.85,0,"rm")
    k2,_=enter(t,ws("Things")-0.20,0.4,0)
    if k2>0.01:
        text(d,(540,1024),"things ByteDance never planned for",
             f(34,"med"),TH.muted,k2,0,"mt")

# ---------------- 2. the rewrite ----------------
def s_rewrite(ov,d,t,t0):
    S.eyebrow(ov,d,"SO THEY STARTED OVER",t,t0,TH)
    kv=eo3(lin(t,ws("threw")-0.25,ws("threw")+0.55))     # v1 crumbling
    ka=eo3(lin(t,ws("rebuilt")-0.10,ws("rebuilt")+0.70)) # v2 assembling
    cw=(W-2*MARGIN-32)/2
    # v1
    x0=MARGIN
    card(d,(x0,368,x0+cw,712),22,TH.card,0.85*(1-0.55*kv),TH.border,0.85*(1-0.5*kv),2)
    text(d,(x0+cw/2,404),"1.x",m(66,"bold"),mix(WHITE,(70,80,78),kv),1-0.45*kv,4,"mt")
    text(d,(x0+cw/2,500),"deep research",m(25),TH.dim,1-0.5*kv,0,"mt")
    for i in range(5):        # rows falling away
        p=clamp((kv-i*0.10)/0.5)
        yy=540+i*30+p*90
        d.rectangle((x0+34,yy,x0+cw-34-p*120,yy+10),
                    fill=rgba((60,72,70),0.9*(1-p)))
    text(d,(x0+cw/2,690),"maintained on main-1.x",m(22),TH.dim,0.7*(1-0.4*kv),0,"mb")
    # v2
    x1=MARGIN+cw+32
    card(d,(x1,368,x1+cw,712),22,(10,26,23),0.95*ka,TH.accent,0.6*ka,3)
    if ka>0.3: put_glow(ov,x1+cw/2,540,TH.glow,420,0.16*ka)
    grad_text(ov,(x1+cw/2,404),"2.0",m(66,"bold"),TH.accent_hi,TH.accent,ka,"mt",4)
    text(d,(x1+cw/2,500),"super agent harness",m(25),TH.accent_hi,ka,0,"mt")
    for i in range(5):
        p=eo3(lin(t,ws("rebuilt")+0.05+i*0.10,ws("rebuilt")+0.42+i*0.10))
        d.rectangle((x1+34,540+i*30,x1+34+(cw-68)*p,540+i*30+10),
                    fill=rgba(TH.accent,0.75*p))
    # 0% shared
    kb=eob(lin(t,ws("shares")-0.25,ws("shares")+0.5),2.1)
    if kb>0.01:
        box=(MARGIN,762,W-MARGIN,946)
        card(d,box,24,(10,24,22),0.95*min(1,kb),TH.accent,0.55*min(1,kb),2)
        grad_text(ov,(540,790),"0%",f(int(92*(0.9+0.1*min(1,kb))),"bold"),
                  TH.accent_hi,TH.accent,min(1,kb),"mt")
        text(d,(540,900),"SHARED CODE WITH VERSION ONE",f(28,"bold"),
             TH.muted,min(1,kb),4,"mm")
    k3,_=enter(t,ws("one.")+0.10,0.4,0)
    if k3>0.01:
        text(d,(540,1000),"a ground-up rewrite, not a refactor",
             m(28),TH.dim,k3,0,"mt")

# ---------------- 3. what it is now ----------------
CAPS=[("SUB-AGENTS",ws("sub-agents,")),("LONG-TERM MEMORY",ws("memory,")),
      ("SANDBOXED EXECUTION",ws("execution,")),("FILESYSTEM",ws("filesystem"))]
def s_now(ov,d,t,t0):
    S.eyebrow(ov,d,"WHAT IT IS NOW",t,t0,TH)
    k,dy=enter(t,ws("super")-0.30,0.36,24)
    grad_text(ov,(540,338+dy),"SUPER AGENT HARNESS",f(58,"bold"),WHITE,TH.pale,k,"mt",2)
    cw=(W-2*MARGIN-24)/2
    for i,(nm,ts) in enumerate(CAPS):
        x=MARGIN+(i%2)*(cw+24); y=444+(i//2)*130
        lit=eo3(lin(t,ts-0.08,ts+0.28))
        kk,dyk=enter(t,ts-0.30,0.30,20)
        fo=f(30,"bold") if len(nm)>14 else f(34,"bold")
        if kk<=0.01: continue
        col=mix(TH.border,TH.accent,lit)
        card(d,(x,y+dyk,x+cw,y+108+dyk),20,TH.card,(0.55+0.35*lit)*kk,col,
             (0.55+0.40*lit)*kk,2)
        if lit>0.4: put_glow(ov,x+cw/2,y+54+dyk,TH.glow,int(cw*0.9),0.13*lit)
        text(d,(x+cw/2,y+54+dyk),nm,fo,mix((92,104,100),WHITE,lit),kk,1,"mm")
    # all driven by SKILL.md
    kt,dyt=enter(t,ws("driven")-0.35,0.36,24)
    if kt>0.01:
        box=(MARGIN,724+dyt,W-MARGIN,1050+dyt); x0,y0,x1,y1=box
        card(d,box,22,(9,17,16),0.95*kt,TH.border,0.9*kt,2)
        text(d,(x0+30,y0+42),"SKILL.md",m(34,"bold"),TH.accent_hi,kt,0,"lm")
        text(d,(x1-30,y0+42),"plain markdown",m(25),TH.dim,kt,0,"rm")
        hline(d,x0+30,x1-30,y0+76,TH.border,0.8*kt,2)
        lines=["---","name: data-analysis","allowed-tools: [read_file, shell]",
               "---","## Workflow","1. inspect the schema"]
        for i,ln in enumerate(lines):
            kk=eo3(lin(t,ws("driven")-0.20+i*0.10,ws("driven")+0.16+i*0.10))
            col=TH.accent_hi if ln.startswith(("name","allowed")) else TH.muted
            text(d,(x0+30,y0+104+i*36),ln,m(25),col,kk*0.92,0,"lt")

# ---------------- 4. progressive loading ----------------
SKILLS=["research","report","slides","web-page","image-gen","video-gen",
        "data-analysis","schema-diff","crawl","summarise","translate","chart",
        "podcast","deck-review","brand-voice","seo","qa-sweep","refactor",
        "benchmark","migrate","classify","extract","cite-check","outline"]
ACTIVE={6}
def s_lean(ov,d,t,t0):
    S.eyebrow(ov,d,"WHY IT STAYS FAST",t,t0,TH)
    k,dy=enter(t,t0+0.06,0.34,22)
    text(d,(540,332+dy),"skills load only when the task needs them",
         f(36,"med"),TH.muted,k,0,"mt")
    # the whole catalog, mostly dormant
    cols,cw,chh,gap=4,(W-2*MARGIN-3*12)/4,58,12
    for i,nm in enumerate(SKILLS):
        c=i%cols; r=i//cols
        x=MARGIN+c*(cw+12); y=406+r*(chh+gap)
        kk=eo3(lin(t,t0+0.20+i*0.012,t0+0.48+i*0.012))
        if kk<=0.01: continue
        live = i in ACTIVE and t>=ws("needs")-0.30
        lv=eo3(lin(t,ws("needs")-0.30,ws("needs")+0.10)) if i in ACTIVE else 0.0
        col=mix(TH.border,TH.accent,lv)
        card(d,(x,y,x+cw,y+chh),12,TH.card,(0.40+0.5*lv)*kk,col,(0.4+0.5*lv)*kk,2)
        text(d,(x+cw/2,y+chh/2),nm,m(21),
             mix((72,84,80),WHITE,lv),kk,0,"mm")
        if lv>0.5: put_glow(ov,x+cw/2,y+chh/2,TH.glow,150,0.20*lv)
    # context meter
    km,dym=enter(t,ws("context")-0.35,0.36,22)
    if km>0.01:
        y=828+dym
        text(d,(MARGIN,y),"CONTEXT WINDOW",f(26,"bold"),TH.muted,km,4,"lt")
        p=eo3(lin(t,ws("context")-0.20,ws("context")+0.55))
        bar(ov,d,(MARGIN,y+44,W-MARGIN,y+92),0.14*p,TH,col=TH.accent)
        text(d,(MARGIN,y+118),"1 skill loaded, 23 dormant",m(26),TH.accent_hi,
             eo3(lin(t,ws("context")+0.10,ws("context")+0.5)),0,"lt")
        kx=eo3(lin(t,ws("lean.")-0.25,ws("lean.")+0.20))
        if kx>0.01:
            text(d,(MARGIN,y+178),"load everything up front and this bar is full",
                 m(25),TH.dim,kx,0,"lt")
            bar(ov,d,(MARGIN,y+212,W-MARGIN,y+248),0.97*kx,TH,col=(90,74,74))

# ---------------- 5. close ----------------
MARKS=[("1 min",0.10),("10 min",0.34),("1 hour",0.62),("hours",0.95)]
def s_close(ov,d,t,t0):
    S.eyebrow(ov,d,"LONG-HORIZON",t,t0,TH)
    k,dy=enter(t,t0+0.06,0.34,22)
    text(d,(540,336+dy),"it handles jobs that run for hours",
         f(40,"med"),WHITE,k,0,"mt")
    # timeline
    km,dym=enter(t,t0+0.30,0.4,20)
    if km>0.01:
        y=470+dym
        p=eo3(lin(t,t0+0.40,t0+1.85))
        bar(ov,d,(MARGIN,y,W-MARGIN,y+40),p,TH,col=TH.accent)
        for lab,fr in MARKS:
            x=MARGIN+(W-2*MARGIN)*fr
            on = p>=fr-0.02
            d.line((x,y-14,x,y+54),fill=rgba(TH.accent if on else TH.border,0.8),width=3)
            text(d,(x,y+70),lab,m(24),TH.accent_hi if on else TH.dim,km,0,"mt")
    kb=eob(lin(t,ws("number")-0.30,ws("number")+0.5),2.1)
    if kb>0.01:
        box=(MARGIN,620,W-MARGIN,830)
        card(d,box,24,(10,24,22),0.95*min(1,kb),TH.accent,0.55*min(1,kb),2)
        put_glow(ov,540,724,TH.glow,540,0.18*min(1,kb))
        grad_text(ov,(540,648),"#1",f(int(86*(0.9+0.1*min(1,kb))),"bold"),
                  TH.accent_hi,TH.accent,min(1,kb),"mt")
        text(d,(540,772),"ON GITHUB TRENDING · 28 FEB 2026",f(27,"bold"),
             TH.muted,min(1,kb),3,"mm")
    kp=eob(lin(t,ws("MIT")-0.14,ws("MIT")+0.46),2.0)
    if kp>0.01:
        pill(d,540,900,"MIT LICENSED",f(32,"bold"),TH.accent_hi,kp,track=5)
    k3,_=enter(t,ws("MIT")+0.30,0.4,0)
    if k3>0.01:
        cw=(W-2*MARGIN-32)/3
        for i,(v,l) in enumerate([("80K","STARS"),("11K","FORKS"),("5","LANGUAGES")]):
            kk=eo3(lin(t,ws("MIT")+0.34+i*0.13,ws("MIT")+0.66+i*0.13))
            if kk<=0.01: continue
            x=MARGIN+i*(cw+16)
            card(d,(x,966,x+cw,1090),20,TH.card,0.85*kk,TH.border,0.9*kk,2)
            grad_text(ov,(x+cw/2,982),v,f(42,"bold"),TH.accent_hi,TH.accent,kk,"mt")
            text(d,(x+cw/2,1058),l,f(22,"bold"),TH.muted,kk,3,"mm")

# ---------------- dispatch ----------------
def frame(t):
    base=BASE.copy()
    ov=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(ov)
    n,a,b=scene_at(t)
    {"drift":s_drift,"rewrite":s_rewrite,"now":s_now,"lean":s_lean,
     "close":s_close}.get(n,lambda *_: None)(ov,d,t,a)
    if n=="end":
        endcard(ov,d,t,a,TH,"DeerFlow","by ByteDance",
                "bytedance/deer-flow","deerflow.tech",
                "SAVE THIS FOR YOUR NEXT BUILD",mark_size=150)
    S.chrome(base,d,t,TH,TOTAL,"bytedance/deer-flow")
    S.cut_sweep(ov,d,t,CUTS,TH)
    if n!="end": S.captions(ov,d,t,CH,TH)
    base.alpha_composite(ov)
    return base

_BIG={38.25}
SFX=(
 [{"t":c-0.30,"kind":"swish","amp":0.15} for c in CUTS] +
 [{"t":c,"kind":"thump","amp":0.29 if c in _BIG else 0.20,
   "dur":0.55 if c in _BIG else 0.34,"freq":46.0 if c in _BIG else 58.0}
    for c in CUTS] +
 [{"t":ts,"kind":"tick","amp":0.075,"tone":2500.0} for _,ts in DRIFT] +
 [{"t":ts,"kind":"tick","amp":0.08,"tone":2800.0} for _,ts in CAPS] +
 [{"t":ws("threw")-0.25,"kind":"thump","amp":0.20,"dur":0.40,"freq":52.0},
  {"t":ws("shares")-0.25,"kind":"thump","amp":0.18,"dur":0.34,"freq":56.0},
  {"t":ws("needs")-0.30,"kind":"tick","amp":0.09,"tone":3200.0},
  {"t":ws("number")-0.30,"kind":"thump","amp":0.20,"dur":0.38,"freq":54.0}]
)
