# ---------------------------------------------------------------
# open-design.py -- "OpenDesign". Magenta/violet. Closed vs open, then the
# real payoff: DESIGN.md as a brand contract the agent reads, shown by
# reusing the same swatches in the artifacts underneath it.
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

NAME    = "open-design"
AUDIO   = "open-design.mp3"
PHRASES = "phrases/open-design.txt"
TOTAL   = 46.0
FPS     = 30

_T=Timing(NAME); WORDS=_T.words
ws,we = _T.ws, _T.we
CH=_T.chunks()

TH=Theme(bg=(12,8,16),accent=(214,92,232),accent_hi=(240,150,250),
         pale=(248,214,252),glow=(120,32,150),support=(255,178,96))
TH.apply()
BASE=S.build_base(TH,seed=14,bloom=0.32)

SC=[("closed",0.00,5.00),("what",5.00,11.85),("artifacts",11.85,17.95),
    ("exports",17.95,23.10),("designmd",23.10,32.30),("harness",32.30,38.42),
    ("close",38.42,44.55),("end",44.55,TOTAL)]
def scene_at(t):
    for n,a,b in SC:
        if a<=t<b: return n,a,b
    return SC[-1]
CUTS=[a for _,a,_ in SC[1:]]

# ---------------- 1. closed vs open ----------------
def s_closed(ov,d,t,t0):
    S.eyebrow(ov,d,"CLOSED vs OPEN",t,0.0,TH)
    # the closed one
    k=eo3(lin(t,0.05,0.44))
    shut=eo3(lin(t,ws("closed.")-0.30,ws("closed.")+0.30))
    box=(MARGIN,352,W-MARGIN,606); x0,y0,x1,y1=box
    card(d,box,22,TH.card,0.90*k,mix(TH.border,TH.bad,shut),(0.6+0.3*shut)*k,2)
    text(d,(x0+34,y0+56),"CLAUDE DESIGN",f(40,"bold"),
         mix(WHITE,(150,120,130),shut*0.6),k,2,"lm")
    text(d,(x0+34,y0+112),"the agent-native design loop",m(26),TH.dim,k,0,"lm")
    # padlock
    cx,cy=x1-84,y0+92; r=26
    d.arc((cx-r+4,cy-r-14,cx+r-4,cy+r-14),200,340,fill=rgba(mix(TH.dim,TH.bad,shut),k),width=6)
    d.rounded_rectangle((cx-r,cy-6,cx+r,cy+34),radius=8,
                        fill=rgba(mix(TH.dim,TH.bad,shut),0.9*k))
    if shut>0.4:
        text(d,(x0+34,y1-46),"CLOSED",f(30,"bold"),TH.bad,shut,5,"lm")
        d.line((x0+34,y0+72,x0+34+tw("CLAUDE DESIGN",f(40,"bold"),2),y0+72),
               fill=rgba(TH.bad,0.75*shut),width=4)
    # the open one
    ko=eo3(lin(t,ws("open")-0.32,ws("open")+0.28))
    kb=eob(lin(t,ws("open")-0.32,ws("open")+0.55),1.9)
    if ko>0.01:
        box2=(MARGIN,650,W-MARGIN,976); a0,b0,a1,b1=box2
        card(d,box2,22,(22,12,26),0.96*ko,TH.accent,0.65*ko,3)
        put_glow(ov,540,812,TH.glow,600,0.20*ko)
        grad_text(ov,(a0+34,b0+34),"OpenDesign",f(int(58*(0.94+0.06*kb)),"bold"),
                  WHITE,TH.pale,ko,"lt",-1)
        text(d,(a0+34,b0+120),"the open one",f(34,"med"),TH.accent_hi,ko,0,"lt")
        for i,ln in enumerate(["skills/","design-systems/","DESIGN.md","plugins/"]):
            kk=eo3(lin(t,ws("open")+0.10+i*0.10,ws("open")+0.46+i*0.10))
            text(d,(a0+34,b0+180+i*38),ln,m(25),TH.muted,kk*0.9,0,"lt")
        text(d,(a1-34,b1-46),"OPEN",f(30,"bold"),TH.accent_hi,ko,5,"rm")

# ---------------- 2. what it is ----------------
def s_what(ov,d,t,t0):
    S.eyebrow(ov,d,"WHAT IT IS",t,t0,TH)
    for i,(txt,ts) in enumerate([("a local-first",ws("local-first")-0.30),
                                 ("desktop app",ws("desktop")-0.10)]):
        k,dy=enter(t,ts,0.34,22)
        text(d,(MARGIN,342+i*86+dy),txt,f(74,"bold"),
             WHITE if i==0 else TH.accent,k,0,"lt")
    # the machine boundary -- nothing leaves it
    kb,dyb=enter(t,ws("coding")-0.45,0.4,26)
    if kb<=0.01: return
    box=(MARGIN,532+dyb,W-MARGIN,1052+dyb); x0,y0,x1,y1=box
    card(d,box,26,(18,12,22),0.55*kb,TH.border,0.0,0)
    for xx in range(int(x0),int(x1),26):          # dashed boundary
        d.line((xx,y0,min(xx+13,x1),y0),fill=rgba(TH.border,0.9*kb),width=3)
        d.line((xx,y1,min(xx+13,x1),y1),fill=rgba(TH.border,0.9*kb),width=3)
    for yy in range(int(y0),int(y1),26):
        d.line((x0,yy,x0,min(yy+13,y1)),fill=rgba(TH.border,0.9*kb),width=3)
        d.line((x1,yy,x1,min(yy+13,y1)),fill=rgba(TH.border,0.9*kb),width=3)
    text(d,(540,y0+34),"YOUR LAPTOP",f(27,"bold"),TH.dim,kb,5,"mm")
    lit1=eo3(lin(t,ws("agent")-0.10,ws("agent")+0.30))
    lit2=eo3(lin(t,ws("engine.")-0.45,ws("engine.")+0.15))
    tile(ov,d,(x0+46,y0+82,x1-46,y0+232),"THE CODING AGENT",lit1,TH,kb,
         sub="already on your machine")
    p=eo3(lin(t,ws("agent")+0.35,ws("engine.")-0.30))
    d.line((540,y0+248,540,y0+248+72*p),fill=rgba(TH.accent,0.8*kb),width=4)
    if p>0.9:
        d.polygon([(540,y0+326),(528,y0+308),(552,y0+308)],fill=rgba(TH.accent,0.9))
    if lit2>0.01:
        b2=(x0+46,y0+344,x1-46,y0+494)
        card(d,b2,20,(28,14,32),0.96*lit2,TH.accent,0.7*lit2,3)
        put_glow(ov,540,y0+419,TH.glow,520,0.20*lit2)
        grad_text(ov,(540,y0+372),"THE DESIGN ENGINE",f(38,"bold"),
                  WHITE,TH.pale,lit2,"mt",2)
        text(d,(540,y0+444),"same laptop. same CLI.",m(26),TH.accent_hi,lit2,0,"mt")

# ---------------- 3. artifacts ----------------
ART=[("PROTOTYPES","web · desktop · mobile",ws("Prototypes,")),
     ("DASHBOARDS","live artifacts",ws("dashboards,")),
     ("DECKS","magazine, pitch, weekly",ws("decks,")),
     ("IMAGES","gpt-image-2, ImageRouter",ws("images,")),
     ("VIDEO","HyperFrames motion",ws("video"))]
def s_artifacts(ov,d,t,t0):
    S.eyebrow(ov,d,"WHAT IT MAKES",t,t0,TH)
    for i,(nm,sub,ts) in enumerate(ART):
        k,dy=enter(t,ts-0.26,0.32,24)
        if k<=0.01: continue
        lit=eo3(lin(t,ts-0.06,ts+0.26))
        y=344+i*126+dy
        col=mix(TH.border,TH.accent,lit)
        card(d,(MARGIN,y,W-MARGIN,y+108),20,TH.card,(0.55+0.35*lit)*k,col,
             (0.55+0.4*lit)*k,2)
        if lit>0.4: put_glow(ov,540,y+54,TH.glow,560,0.11*lit)
        text(d,(MARGIN+32,y+40),nm,f(36,"bold"),mix((110,96,116),WHITE,lit),k,2,"lm")
        text(d,(MARGIN+32,y+80),sub,m(24),TH.dim,k*0.9,0,"lm")
        d.ellipse((W-MARGIN-56,y+44,W-MARGIN-34,y+66),
                  fill=rgba(mix(TH.border,TH.accent_hi,lit),0.9*k))
    k2,_=enter(t,ws("exports")-0.35,0.4,0)
    if k2>0.01:
        text(d,(540,1030),"and it exports real files",f(40,"med"),TH.accent_hi,k2,0,"mt")

# ---------------- 4. exports ----------------
FMT=[("HTML","live page",18.30),("PDF","print-ready",19.45),
     ("PPTX","PowerPoint",ws("PowerPoint,")-0.10),("MP4","video",ws("MP4.")-0.10)]
def s_exports(ov,d,t,t0):
    S.eyebrow(ov,d,"REAL FILES OUT",t,t0,TH)
    cw=(W-2*MARGIN-24)/2
    for i,(nm,sub,ts) in enumerate(FMT):
        kb=eob(lin(t,ts,ts+0.46),2.4)
        if kb<=0.01: continue
        k=min(1.0,kb)
        x=MARGIN+(i%2)*(cw+24); y=380+(i//2)*260
        sc=0.90+0.10*k
        bw,bh=cw*sc,236*sc
        bx=x+(cw-bw)/2; by=y+(236-bh)/2
        card(d,(bx,by,bx+bw,by+bh),24,(26,14,30),0.95*k,TH.accent,0.65*k,3)
        put_glow(ov,x+cw/2,y+118,TH.glow,int(cw*0.9),0.16*k)
        grad_text(ov,(x+cw/2,y+56),nm,f(72,"bold"),WHITE,TH.pale,k,"mt",2)
        text(d,(x+cw/2,y+180),sub,m(26),TH.accent_hi,k,0,"mt")
    k2,_=enter(t,ws("PowerPoint,")+0.20,0.4,0)   # was after MP4: only 0.8s on screen
    if k2>0.01:
        text(d,(540,930),"not screenshots. not a canvas. files.",
             f(36,"med"),WHITE,k2,0,"mt")
        text(d,(540,990),"sandboxed iframe preview before you ship",
             m(27),TH.dim,k2,0,"mt")

# ---------------- 5. DESIGN.md ----------------
SW=[(214,92,232),(255,178,96),(120,220,240),(140,240,180),(244,244,250)]
def s_designmd(ov,d,t,t0):
    S.eyebrow(ov,d,"THE CLEVER PART",t,t0,TH)
    k=eo3(lin(t,ws("DESIGN.md.")-0.34,ws("DESIGN.md.")+0.22))
    kb=eob(lin(t,ws("DESIGN.md.")-0.34,ws("DESIGN.md.")+0.5),1.9)
    grad_text(ov,(540,336),"DESIGN.md",m(int(76*(0.93+0.07*min(1,kb))),"bold"),
              WHITE,TH.pale,k,"mt",2)
    # the file itself
    kf,dyf=enter(t,ws("system")-0.40,0.4,26)
    if kf>0.01:
        box=(MARGIN,452+dyf,W-MARGIN,768+dyf); x0,y0,x1,y1=box
        card(d,box,22,(15,10,19),0.96*kf,TH.border,0.9*kf,2)
        text(d,(x0+28,y0+40),"DESIGN.md",m(27,"bold"),TH.accent_hi,kf,0,"lm")
        text(d,(x1-28,y0+40),"your brand, as a file",m(24),TH.dim,kf,0,"rm")
        hline(d,x0+28,x1-28,y0+70,TH.border,0.8*kf,2)
        # swatches
        ksw=eo3(lin(t,ws("becomes")-0.20,ws("becomes")+0.40))
        for i,c in enumerate(SW):
            xx=x0+30+i*70
            d.rounded_rectangle((xx,y0+96,xx+56,y0+152),radius=10,
                                fill=rgba(c,0.95*ksw))
        text(d,(x0+30,y0+176),"type: Helvetica Neue / Menlo",m(24),TH.muted,
             eo3(lin(t,ws("file")-0.10,ws("file")+0.35)),0,"lt")
        text(d,(x0+30,y0+212),"scale: 24 · 34 · 48 · 74",m(24),TH.muted,
             eo3(lin(t,ws("file")+0.10,ws("file")+0.55)),0,"lt")
        text(d,(x0+30,y0+248),"radius: 20 · spacing: 8pt grid",m(24),TH.muted,
             eo3(lin(t,ws("agent")-0.05,ws("agent")+0.40)),0,"lt")
    # ... and everything it makes inherits it
    ka=eo3(lin(t,ws("everything")-0.40,ws("everything")+0.10))
    if ka>0.01:
        d.line((540,786,540,834),fill=rgba(TH.accent,0.8*ka),width=4)
        if ka>0.9:
            d.polygon([(540,846),(528,828),(552,828)],fill=rgba(TH.accent,0.9))
        cw=(W-2*MARGIN-32)/3
        for i,lab in enumerate(["deck","dashboard","landing"]):
            kk=eo3(lin(t,ws("everything")-0.10+i*0.16,ws("everything")+0.30+i*0.16))
            if kk<=0.01: continue
            x=MARGIN+i*(cw+16); y=866
            card(d,(x,y,x+cw,y+188),18,TH.card,0.92*kk,TH.border,0.9*kk,2)
            d.rounded_rectangle((x+16,y+16,x+cw-16,y+30),radius=6,
                                fill=rgba(SW[0],0.9*kk))
            for r_ in range(3):
                d.rounded_rectangle((x+16,y+46+r_*18,x+cw-16-r_*22,y+56+r_*18),
                                    radius=4,fill=rgba((255,255,255),0.10*kk))
            d.rounded_rectangle((x+16,y+112,x+16+34,y+128),radius=5,
                                fill=rgba(SW[1],0.85*kk))
            text(d,(x+cw/2,y+156),lab,m(25),TH.muted,kk,0,"mm")
        kt=eo3(lin(t,ws("brand.")-0.30,ws("brand.")+0.20))
        text(d,(540,1088),"already on brand, before you look at it",
             f(32,"med"),TH.accent_hi,kt,0,"mt")

# ---------------- 6. harnesses ----------------
CLIS=["Claude Code","Codex","Cursor","dsh","OpenCode","Copilot",
      "Qwen","Hermes","Kimi","Antigravity","Amp","OpenClaw"]
def s_harness(ov,d,t,t0):
    S.eyebrow(ov,d,"WHERE IT RUNS",t,t0,TH)
    ts=ws("twenty-six")-0.35
    counter(ov,d,(540,404),26,t,ts,TH,dur=0.85,size=110,
            label="DISTINCT AGENT CLIs")
    cw=(W-2*MARGIN-2*12)/3
    for i,nm in enumerate(CLIS):
        c=i%3; r=i//3
        x=MARGIN+c*(cw+12); y=524+r*96
        k=eo3(lin(t,ts+0.35+i*0.075,ts+0.62+i*0.075))
        if k<=0.01: continue
        card(d,(x,y,x+cw,y+80),16,TH.card,0.55+0.35*k,
             mix(TH.border,TH.accent,k),0.5+0.4*k,2)
        if k>0.7: put_glow(ov,x+cw/2,y+40,TH.glow,int(cw*0.8),0.10*k)
        fo=m(24) if len(nm)>9 else m(27)
        text(d,(x+cw/2,y+40),nm,fo,mix((110,96,116),WHITE,k),1.0,0,"mm")
    kb,dyb=enter(t,ws("OpenAI-compatible")-0.40,0.4,22)
    if kb>0.01:
        box=(MARGIN,932+dyb,W-MARGIN,1064+dyb)
        card(d,box,20,(26,14,30),0.94*kb,TH.support,0.55*kb,2)
        text(d,(540,972+dyb),"+ ANY OPENAI-COMPATIBLE ENDPOINT",
             f(30,"bold"),TH.support,kb,3,"mt")
        text(d,(540,1018+dyb),"bring your own key",m(26),TH.dim,kb,0,"mt")

# ---------------- 7. close ----------------
def s_close(ov,d,t,t0):
    S.eyebrow(ov,d,"THE NUMBERS",t,t0,TH)
    kb=eob(lin(t,ws("Apache-two")-0.16,ws("Apache-two")+0.46),2.0)
    if kb>0.01:
        pill(d,540,352,"APACHE-2.0 LICENSED",f(32,"bold"),TH.support,kb,track=5)
    counter(ov,d,(540,540),89210,t,ws("eighty-nine")-0.30,TH,dur=1.30,size=132,
            label="GITHUB STARS")
    k,dy=enter(t,ws("Figma")-0.45,0.4,24)
    if k>0.01:
        for i,(ln,col) in enumerate([("the Figma alternative",WHITE),
                                     ("for the agent era",TH.accent_hi)]):
            kk=eo3(lin(t,ws("Figma")-0.40+i*0.20,ws("Figma")+0.02+i*0.20))
            text(d,(540,720+i*74+dy),ln,f(60,"bold"),col,kk,0,"mt")
    k2,_=enter(t,ws("era.")-0.30,0.4,0)
    if k2>0.01:
        cw=(W-2*MARGIN-32)/3
        for i,(v,l) in enumerate([("14","LANGUAGES"),("60","PLUGINS"),
                                  ("2","PLATFORMS")]):
            kk=eo3(lin(t,ws("era.")-0.26+i*0.13,ws("era.")+0.06+i*0.13))
            if kk<=0.01: continue
            x=MARGIN+i*(cw+16)
            card(d,(x,920,x+cw,1050),20,TH.card,0.85*kk,TH.border,0.9*kk,2)
            grad_text(ov,(x+cw/2,938),v,f(44,"bold"),TH.accent_hi,TH.accent,kk,"mt")
            text(d,(x+cw/2,1020),l,f(22,"bold"),TH.muted,kk,3,"mm")

# ---------------- dispatch ----------------
def frame(t):
    base=BASE.copy()
    ov=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(ov)
    n,a,b=scene_at(t)
    {"closed":s_closed,"what":s_what,"artifacts":s_artifacts,"exports":s_exports,
     "designmd":s_designmd,"harness":s_harness,"close":s_close
     }.get(n,lambda *_: None)(ov,d,t,a)
    if n=="end":
        endcard(ov,d,t,a,TH,"OpenDesign","local-first design for agents",
                "nexu-io/open-design","open-design.ai",
                "SAVE THIS FOR YOUR NEXT BUILD",mark_size=126)
    S.chrome(base,d,t,TH,TOTAL,"nexu-io/open-design")
    S.cut_sweep(ov,d,t,CUTS,TH)
    if n!="end": S.captions(ov,d,t,CH,TH)
    base.alpha_composite(ov)
    return base

_BIG={44.55}
SFX=(
 [{"t":c-0.30,"kind":"swish","amp":0.15} for c in CUTS] +
 [{"t":c,"kind":"thump","amp":0.29 if c in _BIG else 0.20,
   "dur":0.55 if c in _BIG else 0.34,"freq":46.0 if c in _BIG else 58.0}
    for c in CUTS] +
 [{"t":ts,"kind":"tick","amp":0.075,"tone":2600.0} for _,_,ts in ART] +
 [{"t":ts,"kind":"thump","amp":0.14,"dur":0.26,"freq":66.0} for _,_,ts in FMT] +
 [{"t":ws("closed.")-0.30,"kind":"thump","amp":0.19,"dur":0.36,"freq":52.0},
  {"t":ws("open")-0.32,"kind":"thump","amp":0.22,"dur":0.42,"freq":50.0},
  {"t":ws("becomes")-0.20,"kind":"tick","amp":0.08,"tone":3000.0},
  {"t":ws("twenty-six")-0.35,"kind":"tick","amp":0.075,"tone":3200.0},
  {"t":ws("eighty-nine")-0.30,"kind":"tick","amp":0.075,"tone":3200.0}]
)
