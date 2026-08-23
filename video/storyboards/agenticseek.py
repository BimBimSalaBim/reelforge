# ---------------------------------------------------------------
# agenticseek.py -- "AgenticSeek". Steel blue sampled from the repo's
# robotic-whale logo, amber as the one warm counterweight. The spine is
# the enclosure: a machine outline that appears empty, fills up, then
# seals. The router scene is the payoff and gets the most screen time.
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

NAME    = "agenticseek"
AUDIO   = "agenticseek.mp3"
PHRASES = "phrases/agenticseek.txt"
TOTAL   = 51.5
FPS     = 30

_T=Timing(NAME); WORDS=_T.words
ws,we = _T.ws, _T.we
CH=_T.chunks()

TH=Theme(bg=(6,10,15),accent=(92,170,214),accent_hi=(160,214,244),
         pale=(214,236,250),glow=(26,70,110),support=(255,190,90))
TH.apply()
BASE=S.build_base(TH,seed=6,bloom=0.33)

# The repo screenshot, if one has been dropped in. Full frame width and
# capped in height -- app/images.py explains why 1060: a taller panel
# collides with the burned-in captions no matter where it is placed.
REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_PATH=os.path.join(REPO_ROOT,"assets","agenticseek-repo.png")
PANEL_TOP, PANEL_MAX_H = 380, 1060
# Where the "100% local alternative to Manus AI" line sits in the source
# image, as a fraction of its height. Measured, not guessed -- see notes.
TAGLINE_F0, TAGLINE_F1 = 0.478, 0.552

def _load_shot():
    if not os.path.exists(SHOT_PATH): return None,0.0,0.0
    im=Image.open(SHOT_PATH).convert("RGB")
    sw,sh=im.size
    nh=int(round(sh*W/sw))
    im=im.resize((W,nh),Image.LANCZOS)
    y0,y1=TAGLINE_F0*nh, TAGLINE_F1*nh
    if nh>PANEL_MAX_H: im=im.crop((0,0,W,PANEL_MAX_H))
    return im.convert("RGBA"),y0,y1
SHOT,TAG_Y0,TAG_Y1=_load_shot()

SC=[("bill",0.00,5.95),("iron",5.95,8.55),("repo",8.55,12.20),
    ("caps",12.20,19.90),("sealed",19.90,22.40),("agents",22.40,25.20),
    ("router",25.20,34.15),("search",34.15,36.40),("close",36.40,40.75),
    ("human",40.75,44.50),("gpu",44.50,48.55),("end",48.55,TOTAL)]
def scene_at(t):
    for n,a,b in SC:
        if a<=t<b: return n,a,b
    return SC[-1]
CUTS=[a for _,a,_ in SC[1:]]

AGENTS=[("CASUAL","conversation"),
        ("CODER","writes · runs · debugs"),
        ("FILE","finds and edits your files"),
        ("BROWSER","drives a real Chrome"),
        ("PLANNER","splits the job into steps")]
BAR_Y0, BAR_H, BAR_GAP = 656, 76, 12
# Right-aligned text below y 1000 must clear the platform action-button column
# (x 960..1080, y 1000..1700 in safecheck.py) -- tighter than the x<=996 rule
# that applies higher up. The bar/card EDGES may run under it; the text may not.
RIGHT_SAFE = 932

def agent_bars(ov,d,t,starts,lit_i=-1,lit_k=0.0):
    """the five specialists. starts[i] is when bar i lands."""
    for i,(nm,role) in enumerate(AGENTS):
        k,dy=enter(t,starts[i],0.30,20)
        if k<=0.01: continue
        y0=BAR_Y0+i*(BAR_H+BAR_GAP)+dy; y1=y0+BAR_H
        on = lit_k if i==lit_i else 0.0
        col=mix(TH.border,TH.accent,on)
        card(d,(MARGIN,y0,W-MARGIN,y1),16,TH.card,(0.62+0.30*on)*k,col,(0.6+0.4*on)*k,2)
        if on>0.35:
            put_glow(ov,540,(y0+y1)/2,TH.glow,760,0.16*on)
            d.rectangle((MARGIN,y0,MARGIN+6,y1),fill=rgba(TH.accent_hi,0.95*on))
        text(d,(MARGIN+34,(y0+y1)/2),nm,f(36,"bold"),
             mix((132,140,156),WHITE,max(on,0.55)),k,2,"lm")
        text(d,(RIGHT_SAFE,(y0+y1)/2),role,m(25),
             mix(TH.dim,TH.accent_hi,on),k*0.95,0,"rm")

def chassis(ov,d,x0,y0,x1,y1,k,lit=0.0,dash=22,gap=14,label=None):
    """the enclosure -- your machine, drawn dashed so it reads as a boundary"""
    if k<=0.01: return
    col=mix(TH.accent,TH.accent_hi,lit)
    d.rounded_rectangle((x0,y0,x1,y1),radius=26,fill=rgba((255,255,255),0.016*k))
    r=26
    for ax,ay,bx,by in ((x0+r,y0,x1-r,y0),(x1,y0+r,x1,y1-r),
                        (x1-r,y1,x0+r,y1),(x0,y1-r,x0,y0+r)):
        L=math.hypot(bx-ax,by-ay)
        for i in range(int(L//(dash+gap))+1):
            t0=i*(dash+gap)/L
            if t0>=1.0: break
            t1=min(1.0,(i*(dash+gap)+dash)/L)
            d.line((ax+(bx-ax)*t0,ay+(by-ay)*t0,ax+(bx-ax)*t1,ay+(by-ay)*t1),
                   fill=rgba(col,(0.34+0.5*lit)*k),width=3)
    if label:
        text(d,(x0+8,y0-34),label,f(25,"bold"),mix(TH.dim,TH.accent,lit),k,5,"lt")

# ---------------- 1. the bill ----------------
def s_bill(ov,d,t,t0):
    S.eyebrow(ov,d,"WHAT A CLOUD AGENT COSTS",t,0.0,TH)
    # on screen at frame 0: an invoice with both line items already legible
    card(d,(MARGIN,392,W-MARGIN,860),26,TH.card,0.92,TH.border,0.92,2)
    text(d,(MARGIN+38,432),"MONTHLY",f(27,"bold"),TH.dim,1.0,5,"lt")
    hline(d,MARGIN+38,W-MARGIN-38,500,TH.border,0.9,2)
    rows=[("API ACCESS","required",ws("APIs")),
          ("SUBSCRIPTION","$200",ws("bills"))]
    for i,(lab,val,cue) in enumerate(rows):
        y=548+i*104
        struck=eo3(lin(t,cue-0.10,cue+0.34))
        col=mix(WHITE,TH.dim,struck)
        text(d,(MARGIN+38,y),lab,f(40,"med"),col,1.0,0,"lm")
        fo=f(52,"bold") if i else f(40,"med")
        text(d,(W-MARGIN-38,y),val,fo,col,1.0,0,"rm")
        if struck>0.02:
            x1=MARGIN+30+(W-2*MARGIN-60)*eo3(struck)
            d.line((MARGIN+30,y,x1,y),fill=rgba(TH.bad,0.92),width=5)
    # the replacement lands on "bills"
    kb=eob(lin(t,ws("bills")+0.18,ws("bills")+0.78),1.6)
    if kb>0.01:
        put_glow(ov,540,772,TH.glow,540,0.24*kb)
        text(d,(540,772),"~ ELECTRICITY",f(int(60*(0.9+0.1*kb)),"bold"),
             TH.support,min(1,kb*1.6),4,"mm")
    # attribution once the line is spoken
    k,dy=enter(t,ws("promise")-0.20,0.34,18)
    if k>0.01:
        text(d,(540,916+dy),"the project's own front page",m(30),TH.muted,k,0,"mm")

# ---------------- 2. your own hardware ----------------
def s_iron(ov,d,t,t0):
    S.eyebrow(ov,d,"WHERE IT RUNS",t,t0,TH)
    k,dy=enter(t,t0+0.06,0.36,26)
    lit=eo3(lin(t,ws("hardware")-0.12,ws("hardware")+0.40))
    chassis(ov,d,MARGIN,480+dy,W-MARGIN,980+dy,k,lit,label="YOUR MACHINE")
    prov=[("OLLAMA",0.30),("LM STUDIO",0.44),("llama.cpp",0.58)]
    for i,(nm,ts) in enumerate(prov):
        kk=eo3(lin(t,t0+ts,t0+ts+0.30))
        if kk<=0.01: continue
        y=560+i*140+dy
        card(d,(MARGIN+56,y,W-MARGIN-56,y+112),18,TH.card,0.80*kk,TH.border,0.85*kk,2)
        text(d,(540,y+56),nm,m(40,"bold"),mix(TH.muted,WHITE,lit),kk,1,"mm")
    if lit>0.3:
        put_glow(ov,540,730+dy,TH.glow,900,0.20*lit)
        text(d,(540,1046+dy),"no cloud · no API key required",
             m(30),TH.accent,lit,0,"mm")

# ---------------- 3. the repo ----------------
def s_repo(ov,d,t,t0):
    S.eyebrow(ov,d,"THE REPO",t,t0,TH)
    k,dy=enter(t,t0+0.04,0.40,26)
    if k<=0.01: return
    y=int(PANEL_TOP+dy)
    if SHOT is not None:
        msk=Image.new("L",SHOT.size,0)
        ImageDraw.Draw(msk).rounded_rectangle((0,0,SHOT.width-1,SHOT.height-1),
                                              radius=22,fill=int(255*k))
        ov.paste(SHOT,(0,y),msk)
        d.rounded_rectangle((0,y,W-1,y+SHOT.height-1),radius=22,
                            outline=rgba(TH.border,0.9*k),width=2)
        # underline the line the narration is speaking
        hl=eo3(lin(t,ws("local")-0.14,ws("Manus")+0.30))
        if hl>0.02 and TAG_Y1>0:
            ty0,ty1=y+int(TAG_Y0),y+int(TAG_Y1)
            if ty1<y+SHOT.height:
                d.rectangle((MARGIN-24,ty0,MARGIN-24+int((W-2*MARGIN+48)*hl),ty1),
                            outline=rgba(TH.support,0.85*hl),width=4)
                put_glow(ov,540,(ty0+ty1)/2,TH.glow,780,0.14*hl)
    else:
        card(d,(MARGIN,PANEL_TOP+dy,W-MARGIN,PANEL_TOP+520+dy),24,TH.card,
             0.92*k,TH.border,0.92*k,2)
        text(d,(540,PANEL_TOP+120+dy),"AgenticSeek",f(76,"bold"),WHITE,k,0,"mm")
        for i,ln in enumerate(wrap("A 100% local alternative to Manus AI",
                                   f(38,"med"),W-2*MARGIN-80)):
            text(d,(540,PANEL_TOP+240+i*54+dy),ln,f(38,"med"),TH.muted,k,0,"mm")
        text(d,(540,PANEL_TOP+430+dy),"github.com/Fosowl/agenticSeek",
             m(32),TH.accent,k,0,"mm")

# ---------------- 4. what it does ----------------
CAPS=[("BROWSES","search · read · fill forms","browses"),
      ("CODES","Python  Go  Java  C  Bash","code"),
      ("PLANS","splits the job, runs it","plans"),
      ("SPEAKS","text-to-speech + speech-to-text","speaks")]
def s_caps(ov,d,t,t0):
    S.eyebrow(ov,d,"ONE ASSISTANT, FOUR JOBS",t,t0,TH)
    cw=(W-2*MARGIN-24)/2
    for i,(nm,sub,cue) in enumerate(CAPS):
        c=ws(cue)
        k,dy=enter(t,c-0.24,0.32,24)
        if k<=0.01: continue
        lit=eo3(lin(t,c-0.08,c+0.36))
        x=MARGIN+(i%2)*(cw+24); y=470+(i//2)*352+dy
        col=mix(TH.border,TH.accent,lit)
        card(d,(x,y,x+cw,y+320),22,TH.card,(0.58+0.34*lit)*k,col,(0.6+0.4*lit)*k,2)
        if lit>0.35: put_glow(ov,x+cw/2,y+150,TH.glow,int(cw*0.95),0.16*lit)
        text(d,(x+cw/2,y+118),nm,f(44,"bold"),mix((120,128,144),WHITE,lit),k,2,"mm")
        for j,ln in enumerate(wrap(sub,m(26),cw-56)):
            text(d,(x+cw/2,y+186+j*38),ln,m(26),
                 mix(TH.dim,TH.accent_hi,lit*0.8),k*0.95,0,"mm")
    # the language list gets its own tick
    kl=eo3(lin(t,ws("languages")-0.10,ws("languages")+0.34))
    if kl>0.02:
        text(d,(540,1230),"five interpreters, all local",m(29),TH.accent,kl,0,"mm")

# ---------------- 5. nothing leaves ----------------
def s_sealed(ov,d,t,t0):
    S.eyebrow(ov,d,"AND STAYS THERE",t,t0,TH)
    k,dy=enter(t,t0+0.04,0.34,22)
    lit=eo3(lin(t,ws("machine")-0.12,ws("machine")+0.42))
    x0,y0,x1,y1=MARGIN,460+dy,W-MARGIN,1160+dy
    chassis(ov,d,x0,y0,x1,y1,k,lit,label="YOUR MACHINE")
    hx,hy=540,(y0+y1)/2
    ring=[(hx+int(300*math.cos(math.radians(v))),hy+int(190*math.sin(math.radians(v))))
          for v in (200,262,318,20,110)]
    for x,y in ring:
        d.line((hx,hy,x,y),fill=rgba(TH.accent,0.30*k),width=2)
        d.ellipse((x-10,y-10,x+10,y+10),fill=rgba(TH.accent,0.46*k))
    put_glow(ov,hx,hy,TH.glow,300,0.30*k)
    d.ellipse((hx-18,hy-18,hx+18,hy+18),fill=rgba(TH.accent_hi,0.62*k))
    # three attempts to leave, sealed on the word
    kb=eob(lin(t,ws("leaving")-0.10,ws("leaving")+0.50),1.5)
    for i,side in ((0,"l"),(3,"r"),(4,"d")):
        nx,ny=ring[i]
        if side=="l":   ex,ey,bar=x0+34,ny,(x0+3,ny-38,x0+3,ny+38)
        elif side=="r": ex,ey,bar=x1-34,ny,(x1-3,ny-38,x1-3,ny+38)
        else:           ex,ey,bar=nx,y1-30,(nx-38,y1-3,nx+38,y1-3)
        kk=eo3(lin(t,ws("nothing")-0.10,ws("nothing")+0.40))
        if kk<=0.02: continue
        d.line((nx,ny,nx+(ex-nx)*kk,ny+(ey-ny)*kk),fill=rgba(TH.accent,0.36*kk),width=2)
        if kb>0.02:
            d.line(bar,fill=rgba(TH.support,0.88*min(1,kb)),width=7)
    if lit>0.3:
        text(d,(540,1232+dy),"nothing crosses the edge",m(31),TH.support,lit,0,"mm")

# ---------------- 6. the specialists ----------------
def s_agents(ov,d,t,t0):
    S.eyebrow(ov,d,"WHO DOES WHAT",t,t0,TH)
    k,dy=enter(t,t0+0.05,0.34,20)
    if k>0.01:
        grad_text(ov,(540,470+dy),"FIVE SPECIALISTS",f(64,"bold"),
                  WHITE,TH.pale,k,"mt",4)
        hline(d,540-130,540+130,566+dy,TH.accent,0.9*k,4)
    c=ws("specialist")
    agent_bars(ov,d,t,[c-0.10+i*0.20 for i in range(5)])

# ---------------- 7. the router ----------------
def s_router(ov,d,t,t0):
    S.eyebrow(ov,d,"HOW IT PICKS",t,t0,TH)
    agent_bars(ov,d,t,[t0-1.0]*5,
               lit_i=3,lit_k=eo3(lin(t,ws("picks")-0.08,ws("picks")+0.40)))
    # the classifier
    kc,dy=enter(t,ws("classifier")-0.26,0.34,24)
    if kc>0.01:
        y0,y1=366+dy,640+dy
        card(d,(MARGIN,y0,W-MARGIN,y1),22,TH.card,0.92*kc,TH.accent,0.55*kc,2)
        put_glow(ov,540,(y0+y1)/2,TH.glow,720,0.16*kc)
        text(d,(540,y0+54),"llm_router/",m(38,"bold"),WHITE,kc,0,"mm")
        text(d,(540,y0+106),"adaptive-classifier + BART, on your machine",
             m(26),TH.muted,kc*0.95,0,"mm")
        # "not an API call" -- a claim, so it gets a pill, never a strike
        kn=eo3(lin(t,ws("API")-0.20,ws("API")+0.34))
        if kn>0.02:
            pill(d,540,y0+172,"NO API CALL",f(31,"bold"),TH.support,kn,track=4)
            text(d,(540,y0+222),"0 tokens · no network",m(25),TH.dim,kn,0,"mm")
    # the routing arrow into BROWSER
    kp=eo3(lin(t,ws("picks")-0.06,ws("picks")+0.42))
    if kp>0.02:
        by=BAR_Y0+3*(BAR_H+BAR_GAP)+BAR_H/2
        d.line((540,648,540,648+(by-648)*kp),fill=rgba(TH.accent_hi,0.55*kp),width=3)
    # complexity gate -> the planner
    kg,gdy=enter(t,ws("decides")-0.22,0.34,20)
    if kg>0.01:
        y=1130+gdy
        text(d,(MARGIN,y),"COMPLEXITY",f(25,"bold"),TH.dim,kg,5,"lt")
        S.bar(ov,d,(MARGIN,y+42,RIGHT_SAFE,y+70),1.0,TH,col=(30,36,46))
        p=eo4(lin(t,ws("planner")-0.44,ws("planner")+0.14))
        S.bar(ov,d,(MARGIN,y+42,MARGIN+(RIGHT_SAFE-MARGIN)*(0.18+0.82*p),y+70),1.0,
              TH,col=mix(TH.accent,TH.support,p))
        text(d,(MARGIN,y+96),"LOW",f(24,"bold"),TH.dim,kg,4,"lt")
        text(d,(RIGHT_SAFE,y+96),"HIGH",f(24,"bold"),
             mix(TH.dim,TH.support,p),kg,4,"rt")
    # the planner lights hard on the word
    kpl=eob(lin(t,ws("planner")-0.10,ws("planner")+0.50),1.8)
    if kpl>0.02:
        y0=BAR_Y0+4*(BAR_H+BAR_GAP); y1=y0+BAR_H
        d.rounded_rectangle((MARGIN,y0,W-MARGIN,y1),radius=16,
                            outline=rgba(TH.support,0.95*min(1,kpl)),width=4)
        put_glow(ov,540,(y0+y1)/2,TH.glow,820,0.24*min(1,kpl))

# ---------------- 8. the search engine ----------------
def s_search(ov,d,t,t0):
    S.eyebrow(ov,d,"EVEN THE SEARCH",t,t0,TH)
    k,dy=enter(t,t0+0.04,0.34,22)
    x0,y0,x1,y1=MARGIN,480+dy,W-MARGIN,880+dy
    chassis(ov,d,x0,y0,x1,y1,k,eo3(lin(t,ws("yours")-0.14,ws("yours")+0.36)),
            label="YOUR DOCKER")
    for i,(nm,sub) in enumerate([("SearxNG","your own metasearch"),
                                 ("Redis","its cache")]):
        kk=eo3(lin(t,t0+0.22+i*0.16,t0+0.54+i*0.16))
        if kk<=0.01: continue
        cw=(x1-x0-160)/2
        x=x0+56+i*(cw+48)
        card(d,(x,y0+70,x+cw,y0+320),18,TH.card,0.86*kk,TH.border,0.9*kk,2)
        text(d,(x+cw/2,y0+158),nm,m(36,"bold"),WHITE,kk,0,"mm")
        text(d,(x+cw/2,y0+220),sub,m(24),TH.dim,kk*0.9,0,"mm")
    ky=eo3(lin(t,t0+0.85,t0+1.19))
    if ky>0.02:
        text(d,(540,962+dy),"no search API key, no query log",
             m(30),TH.support,ky,0,"mm")

# ---------------- 9. licence + stars ----------------
def s_close(ov,d,t,t0):
    S.eyebrow(ov,d,"THE NUMBERS",t,t0,TH)
    kb=eob(lin(t,ws("G-P-L")-0.14,ws("G-P-L")+0.46),2.0)
    if kb>0.01: pill(d,540,412,"GPL-3.0",f(38,"bold"),TH.ok,min(1,kb),track=5)
    cw=(W-2*MARGIN-32)/3
    for i,(v,l) in enumerate([("3.0K","FORKS"),("18","MONTHS OLD"),
                              ("8","README LANGS")]):
        kk,dy=enter(t,t0+0.55+i*0.14,0.34,20)
        if kk<=0.01: continue
        x=MARGIN+i*(cw+16)
        card(d,(x,500+dy,x+cw,640+dy),20,TH.card,0.85*kk,TH.border,0.9*kk,2)
        grad_text(ov,(x+cw/2,522+dy),v,f(44,"bold"),TH.accent_hi,TH.accent,kk,"mt")
        text(d,(x+cw/2,612+dy),l,f(23,"bold"),TH.muted,kk,3,"mm")
    counter(ov,d,(540,900),26949,t,ws("Twenty-seven")-0.30,TH,dur=1.20,
            size=144,label="GITHUB STARS")

# ---------------- 10. a side project ----------------
def s_human(ov,d,t,t0):
    S.eyebrow(ov,d,"WHO BUILT IT",t,t0,TH)
    for i,(lab,cue) in enumerate([("NO COMPANY","side"),("NO FUNDING","funding"),
                                  ("NO ROADMAP","roadmap")]):
        c=ws(cue)
        k,dy=enter(t,c-0.22,0.32,22)
        if k<=0.01: continue
        y=470+i*168+dy
        lit=eo3(lin(t,c-0.06,c+0.36))
        card(d,(MARGIN,y,W-MARGIN,y+140),20,TH.card,(0.62+0.28*lit)*k,
             mix(TH.border,TH.accent,lit),(0.6+0.4*lit)*k,2)
        text(d,(540,y+70),lab,f(48,"bold"),mix((124,132,148),WHITE,lit),k,4,"mm")
    kq,qdy=enter(t,ws("project")+0.30,0.36,20)
    if kq>0.01:
        text(d,(540,1032+qdy),"one maintainer in Paris, plus two friends",
             m(29),TH.muted,kq,0,"mm")
        text(d,(540,1082+qdy),"Fosowl · GitHub Trending, Feb 2025",
             m(27),TH.accent,kq*0.9,0,"mm")

# ---------------- 11. bring a real GPU ----------------
TIERS=[("7B","8 GB","not recommended",False),
       ("14B","12 GB","simple tasks",False),
       ("32B","24 GB","most tasks",True),
       ("70B+","48 GB","excellent",False)]
def s_gpu(ov,d,t,t0):
    S.eyebrow(ov,d,"THE HONEST PART",t,t0,TH)
    hi=eo3(lin(t,ws("gigabytes")-0.16,ws("gigabytes")+0.40))
    for i,(sz,vram,note,mark) in enumerate(TIERS):
        k,dy=enter(t,ws("GPU")-0.16+i*0.14,0.30,22)
        if k<=0.01: continue
        y=486+i*170+dy
        lit=hi if mark else 0.0
        card(d,(MARGIN,y,W-MARGIN,y+142),18,TH.card,(0.60+0.30*lit)*k,
             mix(TH.border,TH.support,lit),(0.6+0.4*lit)*k,2)
        if lit>0.35:
            put_glow(ov,540,y+71,TH.glow,820,0.18*lit)
            d.rectangle((MARGIN,y,MARGIN+6,y+142),fill=rgba(TH.support,0.95*lit))
        text(d,(MARGIN+34,y+71),sz,f(44,"bold"),
             mix((132,140,156),WHITE,max(lit,0.6)),k,1,"lm")
        text(d,(540,y+71),vram,m(40,"bold"),
             mix(TH.muted,TH.support,lit),k,0,"mm")
        text(d,(RIGHT_SAFE,y+71),note,m(26),
             mix(TH.dim,TH.accent_hi,lit),k*0.95,0,"rm")
    if hi>0.3:
        text(d,(540,1216),"their own FAQ, not ours",m(27),TH.dim,hi,0,"mm")

# ---------------- dispatch ----------------
def frame(t):
    base=BASE.copy()
    ov=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(ov)
    n,a,b=scene_at(t)
    {"bill":s_bill,"iron":s_iron,"repo":s_repo,"caps":s_caps,
     "sealed":s_sealed,"agents":s_agents,"router":s_router,"search":s_search,
     "close":s_close,"human":s_human,"gpu":s_gpu}.get(n,lambda *_: None)(ov,d,t,a)
    if n=="end":
        endcard(ov,d,t,a,TH,"agenticSeek","fully local Manus alternative",
                "github.com/Fosowl/agenticSeek","./start_services.sh full",
                "SAVE THIS FOR YOUR NEXT BUILD",mark_size=150)
    S.chrome(base,d,t,TH,TOTAL,"Fosowl/agenticSeek")
    S.cut_sweep(ov,d,t,CUTS,TH)
    if n!="end": S.captions(ov,d,t,CH,TH)
    base.alpha_composite(ov)
    return base

_BIG={8.55,25.20,48.55}
SFX=(
 [{"t":c-0.30,"kind":"swish","amp":0.15} for c in CUTS] +
 [{"t":c,"kind":"thump","amp":0.29 if c in _BIG else 0.20,
   "dur":0.55 if c in _BIG else 0.34,"freq":46.0 if c in _BIG else 58.0}
    for c in CUTS] +
 [{"t":ws("APIs")-0.10,"kind":"tick","amp":0.085,"tone":2400.0},
  {"t":ws("bills")-0.10,"kind":"thump","amp":0.22,"dur":0.40,"freq":52.0},
  {"t":ws("bills")+0.18,"kind":"tick","amp":0.09,"tone":1900.0},
  {"t":ws("hardware")-0.12,"kind":"tick","amp":0.08,"tone":3000.0}] +
 [{"t":ws(c)-0.08,"kind":"tick","amp":0.075,"tone":2800.0}
    for _,_,c in CAPS] +
 [{"t":ws("nothing")-0.10,"kind":"swish","amp":0.12},
  {"t":ws("leaving")-0.10,"kind":"thump","amp":0.24,"dur":0.42,"freq":50.0},
  {"t":ws("classifier")-0.26,"kind":"tick","amp":0.08,"tone":3100.0},
  {"t":ws("API")-0.20,"kind":"tick","amp":0.085,"tone":2200.0},
  {"t":ws("picks")-0.06,"kind":"tick","amp":0.09,"tone":3300.0},
  {"t":ws("planner")-0.10,"kind":"thump","amp":0.26,"dur":0.48,"freq":48.0},
  {"t":ws("yours")-0.14,"kind":"tick","amp":0.08,"tone":2900.0},
  {"t":ws("G-P-L")-0.14,"kind":"tick","amp":0.085,"tone":2600.0},
  {"t":ws("Twenty-seven")-0.30,"kind":"tick","amp":0.075,"tone":3200.0},
  {"t":ws("gigabytes")-0.16,"kind":"thump","amp":0.20,"dur":0.36,"freq":54.0}] +
 [{"t":ws(c)-0.22,"kind":"tick","amp":0.07,"tone":2500.0}
    for c in ("side","funding","roadmap")] +
 [{"t":ws("specialist")-0.10+i*0.20,"kind":"tick","amp":0.07,"tone":2700.0+i*120}
    for i in range(5)]
)
