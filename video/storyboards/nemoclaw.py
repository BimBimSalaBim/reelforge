# ---------------------------------------------------------------
# nemoclaw.py -- "NVIDIA NemoClaw". NVIDIA green, with red reserved
# for one meaning only: denied. The spine is a boundary that closes in
# scene 2 and is never opened again; the payoff is scene 6, where an
# allowed host turns out not to be an open door.
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

NAME    = "nemoclaw"
AUDIO   = "nemoclaw.mp3"
PHRASES = "phrases/nemoclaw.txt"
TOTAL   = 52.8
FPS     = 30

_T=Timing(NAME); WORDS=_T.words
ws,we = _T.ws, _T.we
CH=_T.chunks()

TH=Theme(bg=(6,10,6),accent=(118,185,0),accent_hi=(178,228,86),
         pale=(226,246,198),glow=(30,66,0),support=(255,110,110))
TH.apply()
BASE=S.build_base(TH,seed=11,bloom=0.30)

# Right-aligned text below y 1000 must clear the platform action-button
# column (x 960..1080, y 1000..1700 in safecheck.py). See DEVELOPMENT.md.
RIGHT_SAFE = 932

SC=[("risk",0.00,4.60),("box",4.60,7.80),("stack",7.80,13.00),
    ("agents",13.00,19.00),("deny",19.00,24.20),("binaries",24.20,33.10),
    ("tiers",33.10,40.90),("close",40.90,45.20),("alpha",45.20,49.30),
    ("end",49.30,TOTAL)]
def scene_at(t):
    for n,a,b in SC:
        if a<=t<b: return n,a,b
    return SC[-1]
CUTS=[a for _,a,_ in SC[1:]]

def chassis(ov,d,x0,y0,x1,y1,k,lit=0.0,dash=22,gap=14,label=None):
    """the sandbox boundary, dashed so it reads as a policy not a wall"""
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

SECRETS=[("~/.aws/credentials","shell"),("~/.ssh/id_ed25519","keys"),
         ("$GITHUB_TOKEN","keys"),("~/Documents/","keys")]

def secret_rows(ov,d,t,k,y0,lit=0.0,h=76,gap=10):
    for i,(path,_) in enumerate(SECRETS):
        y=y0+i*(h+gap)
        col=mix(TH.border,TH.support,lit)
        card(d,(MARGIN+30,y,W-MARGIN-30,y+h),14,TH.card,(0.62+0.24*lit)*k,
             col,(0.55+0.40*lit)*k,2)
        text(d,(MARGIN+58,y+h/2),path,m(32),mix((146,152,142),WHITE,lit),k,0,"lm")

# ---------------- 1. the blast radius ----------------
def s_risk(ov,d,t,t0):
    S.eyebrow(ov,d,"WHAT IT CAN ALREADY REACH",t,0.0,TH)
    # legible at frame 0 -- no entrance on the list itself
    pill(d,540,368,"YOUR CODING AGENT",f(32,"bold"),TH.accent,1.0,track=5)
    lit=eo3(lin(t,ws("keys")-0.12,ws("keys")+0.40))
    secret_rows(ov,d,t,1.0,432,lit)
    ksh=eo3(lin(t,ws("shell")-0.12,ws("shell")+0.36))
    if ksh>0.02:
        text(d,(540,806),"and a shell it can run anything in",
             m(30),mix(TH.dim,TH.accent_hi,ksh),ksh,0,"mm")
    # the way out
    kc=eo3(lin(t,ws("connection")-0.20,ws("connection")+0.44))
    if kc>0.02:
        y=900
        d.line((540,846,540,y),fill=rgba(TH.support,0.5*kc),width=3)
        x1=540+(W-MARGIN-540)*kc
        d.line((540,y,x1,y),fill=rgba(TH.support,0.75*kc),width=4)
        d.line((x1-18,y-12,x1,y),fill=rgba(TH.support,0.85*kc),width=4)
        d.line((x1-18,y+12,x1,y),fill=rgba(TH.support,0.85*kc),width=4)
        text(d,(540,y+52),"the open internet",m(31,"bold"),TH.support,kc,0,"mm")
        put_glow(ov,540,y,TH.glow,520,0.10*kc)

# ---------------- 2. the box ----------------
def s_box(ov,d,t,t0):
    S.eyebrow(ov,d,"NVIDIA OPEN-SOURCED THE BOX",t,t0,TH)
    kb=eob(lin(t,ws("box")-0.16,ws("box")+0.52),1.7)
    k=min(1.0,max(kb,0.0))
    # chassis FIRST -- its fill is drawn with d.rounded_rectangle, which replaces
    # pixels rather than blending (gotcha 1). After the rows, it erases them.
    chassis(ov,d,MARGIN,404,W-MARGIN,872,k,min(1.0,k),label="OPENSHELL SANDBOX")
    secret_rows(ov,d,t,1.0,470,0.0)
    if k>0.3:
        put_glow(ov,540,640,TH.glow,900,0.22*k)
        text(d,(540,940),"the same files, now behind a policy",
             m(31),TH.accent,k,0,"mm")

# ---------------- 3. the stack ----------------
def s_stack(ov,d,t,t0):
    S.eyebrow(ov,d,"THE STACK",t,t0,TH)
    rows=[("NemoClaw","the reference stack  ·  TypeScript",ws("NemoClaw")-0.20,500),
          ("OpenShell","the sandbox runtime  ·  Rust",ws("OpenShell")-0.20,700)]
    for nm,sub,cue,y in rows:
        k,dy=enter(t,cue,0.38,30)
        if k<=0.01: continue
        card(d,(MARGIN,y+dy,W-MARGIN,y+164+dy),22,TH.card,0.92*k,TH.accent,0.5*k,2)
        put_glow(ov,540,y+82+dy,TH.glow,760,0.14*k)
        text(d,(540,y+58+dy),nm,f(56,"bold"),WHITE,k,1,"mm")
        text(d,(540,y+118+dy),sub,m(27),TH.muted,k*0.95,0,"mm")
    kf=eo3(lin(t,ws("OpenShell")+0.55,ws("OpenShell")+0.95))
    if kf>0.02:
        text(d,(540,940),"two repos, both NVIDIA, both Apache-2.0",
             m(30),TH.accent,kf,0,"mm")

# ---------------- 4. three agents, one box ----------------
AGENTS=[("OPENCLAW","default  ·  openclaw.ai","OpenClaw"),
        ("HERMES","get-hermes.ai","Hermes"),
        ("LANGCHAIN","Deep Agents Code","LangChain")]
def s_agents(ov,d,t,t0):
    S.eyebrow(ov,d,"WHAT RUNS INSIDE IT",t,t0,TH)
    lit=eo3(lin(t,ws("hardened")-0.14,ws("hardened")+0.42))
    chassis(ov,d,MARGIN,430,W-MARGIN,1010,1.0,lit,label="ONE HARDENED SANDBOX")
    for i,(nm,sub,cue) in enumerate(AGENTS):
        k,dy=enter(t,ws(cue)-0.22,0.32,26)
        if k<=0.01: continue
        y=486+i*168+dy
        card(d,(MARGIN+40,y,W-MARGIN-40,y+140),18,TH.card,(0.62+0.26*lit)*k,
             mix(TH.border,TH.accent,lit),(0.6+0.4*lit)*k,2)
        text(d,(540,y+56),nm,f(42,"bold"),mix((140,148,136),WHITE,max(lit,0.7)),k,2,"mm")
        text(d,(540,y+104),sub,m(25),mix(TH.dim,TH.accent_hi,lit*0.7),k*0.9,0,"mm")
    kp=eo3(lin(t,ws("Deep")-0.10,ws("Deep")+0.36))
    if kp>0.02:
        text(d,(540,1078),"same policy, whichever one you pick",
             m(30),TH.accent,kp,0,"mm")

# ---------------- 5. deny by default ----------------
ROPATHS=["/usr","/lib","/etc","/proc","/app","/var/log"]
def s_deny(ov,d,t,t0):
    S.eyebrow(ov,d,"THE DEFAULT",t,t0,TH)
    kb=eob(lin(t,ws("deny")-0.16,ws("deny")+0.50),1.9)
    if kb>0.01:
        k=min(1.0,kb)
        put_glow(ov,540,452,TH.glow,700,0.24*k)
        grad_text(ov,(540,452),"DENY BY DEFAULT",f(int(66*(0.92+0.08*kb)),"bold"),
                  WHITE,TH.pale,k,"mm",4)
        text(d,(540,528),"“allow only what’s needed for core functionality”",
             m(27),TH.muted,k,0,"mm")
    # the read-only set
    kr,dy=enter(t,ws("filesystem")-0.24,0.34,24)
    if kr>0.01:
        cw=(W-2*MARGIN-2*16)/3
        for i,p in enumerate(ROPATHS):
            kk=eo3(lin(t,ws("filesystem")-0.20+i*0.08,ws("filesystem")+0.16+i*0.08))
            if kk<=0.01: continue
            x=MARGIN+(i%3)*(cw+16); y=620+(i//3)*128+dy
            card(d,(x,y,x+cw,y+110),16,TH.card,0.86*kk,TH.border,0.9*kk,2)
            text(d,(x+cw/2,y+40),p,m(34,"bold"),WHITE,kk,0,"mm")
            text(d,(x+cw/2,y+80),"READ-ONLY",f(21,"bold"),TH.accent,kk,3,"mm")
    kl=eo3(lin(t,ws("enforced")-0.14,ws("enforced")+0.40))
    if kl>0.02:
        pill(d,540,924,"enforced by landlock",m(31,"bold"),TH.accent,kl,track=1)
        text(d,(540,988),"a Linux kernel LSM, not a wrapper",
             m(27),TH.dim,kl*0.9,0,"mm")

# ---------------- 6. bound to binaries (the payoff) ----------------
PASS=[("npm","/usr/local/bin/npm*"),("npx","/usr/local/bin/npx*"),
      ("node","/usr/local/bin/node*"),("yarn","/usr/local/bin/yarn*")]
def s_binaries(ov,d,t,t0):
    S.eyebrow(ov,d,"THE PART THAT IS DIFFERENT",t,t0,TH)
    # every policy entry needs three fields, and the third is the story
    kf,dy=enter(t,ws("rules")-0.22,0.32,22)
    if kf>0.01:
        lit=eo3(lin(t,ws("binaries")-0.14,ws("binaries")+0.42))
        cw=(W-2*MARGIN-2*14)/3
        for i,fld in enumerate(["name","endpoints","binaries"]):
            on=lit if i==2 else 0.0
            x=MARGIN+i*(cw+14); y=352+dy
            card(d,(x,y,x+cw,y+86),14,TH.card,(0.6+0.3*on)*kf,
                 mix(TH.border,TH.accent,on),(0.6+0.4*on)*kf,2)
            text(d,(x+cw/2,y+43),fld,m(30,"bold"),
                 mix((140,148,136),WHITE,max(on,0.6)),kf,0,"mm")
        if lit>0.3: put_glow(ov,MARGIN+2*(cw+14)+cw/2,395+dy,TH.glow,340,0.20*lit)
    kh=eo3(lin(t,ws("hosts")-0.14,ws("hosts")+0.40))
    if kh>0.02:
        text(d,(540,486),"not just the host  —  the binary that dials out",
             m(28),mix(TH.dim,TH.accent_hi,kh),kh,0,"mm")
    # the endpoint everything is measured against
    ke,edy=enter(t,ws("npm")-0.22,0.32,22)
    if ke>0.01:
        pill(d,540,568+edy,"registry.npmjs.org:443",m(33,"bold"),TH.accent,ke,track=0)
    # who gets through, and who does not
    kr=eo3(lin(t,ws("registry")-0.20,ws("registry")+0.30))
    for i,(nm,path) in enumerate(PASS):
        kk=eo3(lin(t,ws("registry")-0.16+i*0.10,ws("registry")+0.18+i*0.10))
        if kk<=0.01: continue
        y=650+i*76
        card(d,(MARGIN,y,W-MARGIN,y+64),12,TH.card,0.80*kk,TH.accent,0.55*kk,2)
        text(d,(MARGIN+26,y+32),"✓",m(32,"bold"),TH.ok,kk,0,"lm")
        text(d,(MARGIN+72,y+32),nm,m(31,"bold"),WHITE,kk,0,"lm")
        text(d,(RIGHT_SAFE,y+32),path,m(24),TH.dim,kk*0.9,0,"rm")
    kn=eob(lin(t,ws("nothing")-0.12,ws("nothing")+0.52),1.7)
    if kn>0.02:
        k=min(1.0,kn); y=650+4*76
        card(d,(MARGIN,y,W-MARGIN,y+64),12,TH.card,0.80*k,TH.support,0.75*k,2)
        text(d,(MARGIN+26,y+32),"✕",m(32,"bold"),TH.support,k,0,"lm")
        text(d,(MARGIN+72,y+32),"curl",m(31,"bold"),TH.support,k,0,"lm")
        text(d,(RIGHT_SAFE,y+32),"same host, not on the list",m(24),TH.support,k*0.9,0,"rm")
        put_glow(ov,540,y+32,TH.glow,760,0.16*k)
        text(d,(540,1064),"an allowed host is not an open door",
             m(30,"bold"),TH.accent_hi,k,0,"mm")

# ---------------- 7. pick the blast radius ----------------
TIERS=[("RESTRICTED","inference and core tooling only","restricted"),
       ("BALANCED","npm · PyPI · Hugging Face · brew · search","balanced"),
       ("OPEN","plus messaging and productivity","open"),
       ("PERSONAL","every binary, ports 80 and 443","personal")]
def s_tiers(ov,d,t,t0):
    S.eyebrow(ov,d,"FOUR POSTURES",t,t0,TH)
    for i,(nm,sub,cue) in enumerate(TIERS):
        c=ws(cue)
        k,dy=enter(t,c-0.20,0.30,22)
        if k<=0.01: continue
        lit=eo3(lin(t,c-0.06,c+0.34))
        risky=(i==3)
        col=TH.support if risky else TH.accent
        y=450+i*130+dy
        card(d,(MARGIN,y,W-MARGIN,y+118),16,TH.card,(0.60+0.28*lit)*k,
             mix(TH.border,col,lit),(0.6+0.4*lit)*k,2)
        if lit>0.35:
            d.rectangle((MARGIN,y,MARGIN+6,y+118),fill=rgba(col,0.95*lit))
        text(d,(MARGIN+34,y+44),nm,f(38,"bold"),
             mix((140,148,136),WHITE,max(lit,0.6)),k,3,"lm")
        text(d,(MARGIN+34,y+88),sub,m(24),
             mix(TH.dim,col if risky else TH.accent_hi,lit),k*0.9,0,"lm")
    kw=eo3(lin(t,ws("personal")-0.06,ws("personal")+0.40))
    if kw>0.02:
        text(d,(540,1016),"“Do not use with untrusted prompts or data.”",
             m(28,"bold"),TH.support,kw,0,"mm")
        text(d,(540,1064),"tiers.yaml, on the personal preset",m(24),TH.dim,kw*0.85,0,"mm")

# ---------------- 8. licence + stars ----------------
def s_close(ov,d,t,t0):
    S.eyebrow(ov,d,"THE NUMBERS",t,t0,TH)
    kb=eob(lin(t,ws("Apache")-0.14,ws("Apache")+0.46),2.0)
    if kb>0.01: pill(d,540,412,"APACHE-2.0",f(38,"bold"),TH.ok,min(1,kb),track=5)
    cw=(W-2*MARGIN-32)/3
    for i,(v,l) in enumerate([("3.0K","FORKS"),("5","MONTHS OLD"),
                              ("8.3K","OPENSHELL STARS")]):
        kk,dy=enter(t,t0+0.45+i*0.14,0.34,20)
        if kk<=0.01: continue
        x=MARGIN+i*(cw+16)
        card(d,(x,500+dy,x+cw,640+dy),20,TH.card,0.85*kk,TH.border,0.9*kk,2)
        grad_text(ov,(x+cw/2,522+dy),v,f(44,"bold"),TH.accent_hi,TH.accent,kk,"mt")
        text(d,(x+cw/2,612+dy),l,f(22,"bold"),TH.muted,kk,2,"mm")
    counter(ov,d,(540,880),22238,t,ws("Twenty-two")-0.28,TH,dur=1.15,
            size=140,label="GITHUB STARS")

# ---------------- 9. and it's alpha ----------------
def s_alpha(ov,d,t,t0):
    S.eyebrow(ov,d,"BEFORE YOU INSTALL IT",t,t0,TH)
    kb=eob(lin(t,ws("alpha")-0.16,ws("alpha")+0.54),1.8)
    if kb>0.01:
        k=min(1.0,kb)
        put_glow(ov,540,500,TH.glow,700,0.20*k)
        fo=f(int(132*(0.92+0.08*kb)),"bold")
        grad_text(ov,(540,500),"ALPHA",fo,WHITE,TH.warn,k,"mm",10)
        text(d,(540,600),"the README’s own word",m(29),TH.muted,k,0,"mm")
    ks,dy=enter(t,t0+0.30,0.36,22)
    if ks>0.01:
        card(d,(MARGIN,690+dy,W-MARGIN,960+dy),22,TH.card,0.90*ks,TH.border,0.9*ks,2)
        for i,ln in enumerate(["issues and PRs reviewed best-effort,",
                               "with no guaranteed response times",
                               "",
                               "vulnerabilities: NVIDIA PSIRT, privately"]):
            if not ln: continue
            text(d,(540,736+i*54+dy),ln,m(28),
                 TH.warn if i==3 else TH.muted,ks,0,"mm")
    kt=eo3(lin(t,ws("security")-0.06,ws("security")+0.36))
    if kt>0.02:
        text(d,(540,1030),"read SECURITY.md first",f(32,"bold"),WHITE,kt,3,"mm")

# ---------------- dispatch ----------------
def frame(t):
    base=BASE.copy()
    ov=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(ov)
    n,a,b=scene_at(t)
    {"risk":s_risk,"box":s_box,"stack":s_stack,"agents":s_agents,
     "deny":s_deny,"binaries":s_binaries,"tiers":s_tiers,"close":s_close,
     "alpha":s_alpha}.get(n,lambda *_: None)(ov,d,t,a)
    if n=="end":
        endcard(ov,d,t,a,TH,"NemoClaw","sandboxed agents, by NVIDIA",
                "github.com/NVIDIA/NemoClaw","docs.nvidia.com/nemoclaw",
                "SAVE THIS BEFORE YOUR NEXT RUN",mark_size=165)
    S.chrome(base,d,t,TH,TOTAL,"NVIDIA/NemoClaw")
    S.cut_sweep(ov,d,t,CUTS,TH)
    if n!="end": S.captions(ov,d,t,CH,TH)
    base.alpha_composite(ov)
    return base

_BIG={4.60,24.20,49.30}
SFX=(
 [{"t":c-0.30,"kind":"swish","amp":0.15} for c in CUTS] +
 [{"t":c,"kind":"thump","amp":0.29 if c in _BIG else 0.20,
   "dur":0.55 if c in _BIG else 0.34,"freq":46.0 if c in _BIG else 58.0}
    for c in CUTS] +
 [{"t":ws("shell")-0.12,"kind":"tick","amp":0.08,"tone":2500.0},
  {"t":ws("keys")-0.12,"kind":"tick","amp":0.085,"tone":2300.0},
  {"t":ws("connection")-0.20,"kind":"swish","amp":0.13},
  {"t":ws("box")-0.16,"kind":"thump","amp":0.27,"dur":0.50,"freq":48.0},
  {"t":ws("NemoClaw")-0.20,"kind":"tick","amp":0.08,"tone":3000.0},
  {"t":ws("OpenShell")-0.20,"kind":"tick","amp":0.08,"tone":2700.0},
  {"t":ws("hardened")-0.14,"kind":"thump","amp":0.20,"dur":0.36,"freq":54.0},
  {"t":ws("deny")-0.16,"kind":"thump","amp":0.28,"dur":0.52,"freq":46.0},
  {"t":ws("Landlock")-0.14,"kind":"tick","amp":0.085,"tone":2900.0},
  {"t":ws("binaries")-0.14,"kind":"tick","amp":0.09,"tone":3300.0},
  {"t":ws("npm")-0.22,"kind":"tick","amp":0.08,"tone":2600.0},
  {"t":ws("nothing")-0.12,"kind":"thump","amp":0.26,"dur":0.48,"freq":50.0},
  {"t":ws("radius")-0.16,"kind":"tick","amp":0.08,"tone":3100.0},
  {"t":ws("Apache")-0.14,"kind":"tick","amp":0.085,"tone":2600.0},
  {"t":ws("Twenty-two")-0.28,"kind":"tick","amp":0.075,"tone":3200.0},
  {"t":ws("alpha")-0.16,"kind":"thump","amp":0.24,"dur":0.44,"freq":52.0}] +
 [{"t":ws("registry")-0.16+i*0.10,"kind":"tick","amp":0.07,"tone":2700.0+i*100}
    for i in range(4)] +
 [{"t":ws(c)-0.20,"kind":"tick","amp":0.075,"tone":2600.0+i*140}
    for i,(_,_,c) in enumerate(TIERS)] +
 [{"t":ws(c)-0.22,"kind":"tick","amp":0.07,"tone":2800.0}
    for _,_,c in AGENTS]
)
