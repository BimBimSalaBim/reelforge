# ---------------------------------------------------------------
# ruflo.py -- "ruflo". Indigo + teal. Built around the equation
# AGENT = MODEL + HARNESS, then the federation pipeline, which is the
# most interesting thing in the repo and gets the most screen time.
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

NAME    = "ruflo"
AUDIO   = "ruflo.mp3"
PHRASES = "phrases/ruflo.txt"
TOTAL   = 38.8
FPS     = 30

_T=Timing(NAME); WORDS=_T.words
ws,we = _T.ws, _T.we
CH=_T.chunks()

TH=Theme(bg=(9,9,18),accent=(124,124,248),accent_hi=(168,168,255),
         pale=(222,222,255),glow=(56,48,160),support=(64,224,208))
TH.apply()
BASE=S.build_base(TH,seed=8,bloom=0.32)

SC=[("eq",0.00,7.78),("title",7.78,13.40),("cmd",13.40,19.80),
    ("fed",19.80,24.98),("pipe",24.98,34.20),("close",34.20,37.25),
    ("end",37.25,TOTAL)]
def scene_at(t):
    for n,a,b in SC:
        if a<=t<b: return n,a,b
    return SC[-1]
CUTS=[a for _,a,_ in SC[1:]]

# ---------------- 1. the equation ----------------
def s_eq(ov,d,t,t0):
    S.eyebrow(ov,d,"START HERE",t,0.0,TH)
    # AGENT = MODEL + HARNESS, assembled on the opening line
    lit_model = eo3(lin(t,ws("writes")-0.20,ws("writes")+0.30))
    lit_harn  = eo3(lin(t,ws("decides")-0.25,ws("decides")+0.30))
    ka=eo3(lin(t,0.05,0.35))
    grad_text(ov,(540,342),"AGENT",f(84,"bold"),WHITE,TH.pale,ka,"mt",8)
    keq=eo3(lin(t,0.40,0.66))
    text(d,(540,452),"=",f(46,"bold"),TH.accent,keq,0,"mt")
    fo=f(68,"bold")
    row=[("MODEL",0.72),("+",0.96),("HARNESS",1.16)]
    widths=[tw(r[0],fo,2) for r in row]
    gap=28; total=sum(widths)+gap*2
    x=540-total/2
    for (txt,ts),wq in zip(row,widths):
        k=eo3(lin(t,ts,ts+0.30))
        col=WHITE
        if txt=="MODEL":   col=mix(WHITE,TH.muted,lit_harn*0.7)
        if txt=="HARNESS": col=mix(WHITE,TH.accent_hi,lit_harn)
        if txt=="MODEL" and lit_model>0.4 and lit_harn<0.3: col=TH.support
        text(d,(x,522),txt,fo,col,k,2,"lt")
        if txt=="HARNESS" and lit_harn>0.4:
            put_glow(ov,x+wq/2,558,TH.glow,300,0.24*lit_harn)
            d.line((x,604,x+wq,604),fill=rgba(TH.accent,0.85*lit_harn),width=5)
        x+=wq+gap
    # the two annotations
    k1,dy1=enter(t,ws("writes")-0.30,0.34,22)
    if k1>0.01:
        box=(MARGIN,660+dy1,W-MARGIN,798+dy1)
        card(d,box,22,TH.card,0.88*k1,TH.border,0.9*k1,2)
        text(d,(MARGIN+34,702+dy1),"THE MODEL",f(28,"bold"),TH.support,k1,4,"lt")
        text(d,(MARGIN+34,748+dy1),"writes the code",f(38,"med"),WHITE,k1,0,"lt")
    k2,dy2=enter(t,ws("decides")-0.35,0.34,22)
    if k2>0.01:
        box=(MARGIN,826+dy2,W-MARGIN,1012+dy2)
        card(d,box,22,(16,16,32),0.94*k2,TH.accent,0.6*k2,2)
        put_glow(ov,540,918+dy2,TH.glow,520,0.16*k2)
        text(d,(MARGIN+34,872+dy2),"THE HARNESS",f(28,"bold"),TH.accent_hi,k2,4,"lt")
        for i,ln in enumerate(["decides whether any of it",
                               "actually gets done"]):
            kk=eo3(lin(t,ws("decides")-0.20+i*0.16,ws("decides")+0.22+i*0.16))
            text(d,(MARGIN+34,916+i*46+dy2),ln,f(38,"med"),WHITE,kk,0,"lt")
    k3,_=enter(t,ws("done.")+0.10,0.4,0)
    if k3>0.01:
        text(d,(540,1074),"tools · memory · loops · sandboxes · controls",
             m(28),TH.dim,k3,0,"mt")

# ---------------- 2. the rename ----------------
def s_title(ov,d,t,t0):
    k=eo3(lin(t,ws("Ruflo")-0.22,ws("Ruflo")+0.28))
    kb=eob(lin(t,ws("Ruflo")-0.22,ws("Ruflo")+0.5),1.7)
    put_glow(ov,540,470,TH.glow,700,0.30*k+0.05*pulse(t,3.0))
    grad_text(ov,(540,468),"ruflo",f(int(208*(0.90+0.10*kb)),"bold"),WHITE,TH.pale,k,"mm",-4)
    # formerly Claude Flow -> struck through
    kr=eo3(lin(t,ws("formerly")-0.20,ws("formerly")+0.26))
    if kr>0.01:
        fo=f(42,"bold"); lab="Claude Flow"
        wq=tw(lab,fo,1); x=540-wq/2
        text(d,(x,634),lab,fo,TH.muted,kr*0.85,1,"lt")
        st=eo3(lin(t,ws("Flow")-0.05,ws("Flow")+0.42))
        if st>0.01:
            d.line((x-6,660,x-6+(wq+12)*st,660),fill=rgba(TH.bad,0.9*st),width=5)
        text(d,(540,704),"renamed. no affiliation implied.",m(27),TH.dim,
             eo3(lin(t,ws("Flow")+0.30,ws("Flow")+0.70)),0,"mt")
    k2,dy2=enter(t,ws("harness",1)-0.30 if False else ws("layer")-0.35,0.36,24)
    if k2>0.01:
        text(d,(540,790+dy2),"the harness layer for",f(44,"med"),TH.muted,k2,0,"mt")
    for i,(nm,ts) in enumerate([("CLAUDE CODE",ws("Code")-0.10),
                                ("CODEX",ws("Codex.")-0.10)]):
        cw=(W-2*MARGIN-24)/2; x=MARGIN+i*(cw+24)
        lit=eo3(lin(t,ts,ts+0.28))
        kk,dy=enter(t,ts-0.25,0.30,20)
        tile(ov,d,(x,872+dy,x+cw,996+dy),nm,lit,TH,kk)
    k3,_=enter(t,ws("Codex.")+0.25,0.4,0)
    if k3>0.01:
        text(d,(540,1058),"npm: ruflo  ·  MIT  ·  by rUv",m(28),TH.dim,k3,0,"mt")

# ---------------- 3. one command ----------------
CMD=[("npx ruflo init",ws("npx")-0.15,ws("npx")+0.70)]
LOOP=[("SWARM",ws("swarm,")),("LEARN",ws("learn")),("REMEMBER",ws("remember"))]
def s_cmd(ov,d,t,t0):
    S.eyebrow(ov,d,"ONE COMMAND",t,t0,TH)
    kt,dyt=enter(t,t0+0.06,0.30,22)
    if kt>0.01:
        terminal(ov,d,(MARGIN,336+dyt,W-MARGIN,506+dyt),CMD,t,TH,
                 title="claude code",fs=34)
    stats=[("100+","AGENTS"),("60+","COMMANDS"),("30","SKILLS"),("314","MCP TOOLS")]
    cw=(W-2*MARGIN-3*14)/4
    for i,(v,l) in enumerate(stats):
        x=MARGIN+i*(cw+14)
        k,dy=enter(t,ws("hundred-plus")-0.20+i*0.13,0.30,20)
        if k<=0.01: continue
        card(d,(x,554+dy,x+cw,554+142+dy),20,TH.card,0.88*k,TH.border,0.9*k,2)
        grad_text(ov,(x+cw/2,554+22+dy),v,f(46,"bold"),TH.accent_hi,TH.accent,k,"mt")
        text(d,(x+cw/2,554+112+dy),l,f(22,"bold"),TH.muted,k,2,"mm")
    # the learning loop
    k2,dy2=enter(t,ws("swarm,")-0.40,0.36,24)
    if k2>0.01:
        cy=832+dy2
        xs=[MARGIN+118,540,W-MARGIN-118]
        for i,(nm,ts) in enumerate(LOOP):
            lit=eo3(lin(t,ts-0.08,ts+0.26))
            r=54
            d.ellipse((xs[i]-r,cy-r,xs[i]+r,cy+r),
                      fill=rgba(mix(TH.card,TH.accent,0.30*lit),0.95*k2),
                      outline=rgba(mix(TH.border,TH.accent,lit),0.9*k2),width=3)
            if lit>0.4: put_glow(ov,xs[i],cy,TH.glow,240,0.20*lit)
            text(d,(xs[i],cy+r+40),nm,f(28,"bold"),
                 mix((96,100,120),WHITE,lit),k2,3,"mm")
            if i<2:
                x0=xs[i]+r+12; x1=xs[i+1]-r-12
                p=eo3(lin(t,LOOP[i][1]+0.10,LOOP[i+1][1]))
                d.line((x0,cy,x0+(x1-x0)*p,cy),fill=rgba(TH.accent,0.8*k2),width=4)
        # loop back arc under the row
        pb=eo3(lin(t,ws("sessions.")-0.35,ws("sessions.")+0.20))
        if pb>0.01:
            yb=cy+128
            d.line([(xs[2],cy+54),(xs[2],yb),(xs[2]-(xs[2]-xs[0])*pb,yb)],
                   fill=rgba(TH.support,0.75*pb),width=4,joint="curve")
            if pb>0.9:
                d.line((xs[0],yb,xs[0],cy+54),fill=rgba(TH.support,0.75),width=4)
                d.polygon([(xs[0],cy+52),(xs[0]-11,cy+70),(xs[0]+11,cy+70)],
                          fill=rgba(TH.support,0.9))
                text(d,(540,yb+22),"memory persists across sessions",
                     m(27),TH.support,0.9,0,"mt")

# ---------------- 4. federation ----------------
def s_fed(ov,d,t,t0):
    S.eyebrow(ov,d,"THE STRANGE PART",t,t0,TH,col=TH.support)
    k,dy=enter(t,ws("federation,")-0.30,0.36,26)
    grad_text(ov,(540,392+dy),"FEDERATION",f(92,"bold"),WHITE,TH.pale,k,"mt",3)
    k2,dy2=enter(t,ws("federation,")+0.42,0.36,22)
    if k2>0.01:
        text(d,(540,530+dy2),"Slack, but for agents.",f(46,"med"),TH.accent_hi,k2,0,"mt")
    k3,dy3=enter(t,ws("strange")-0.20,0.4,22)
    if k3>0.01:
        box=(MARGIN,646+dy3,W-MARGIN,900+dy3)
        card(d,box,24,TH.card,0.90*k3,TH.border,0.9*k3,2)
        for i,ln in enumerate(["your agents can talk to agents",
                               "on someone else's machine"]):
            kk=eo3(lin(t,ws("strange")-0.14+i*0.18,ws("strange")+0.28+i*0.18))
            text(d,(540,700+i*58+dy3),ln,f(40,"med"),WHITE,kk,0,"mt")
        k4=eo3(lin(t,ws("one.")+0.05,ws("one.")+0.45))
        text(d,(540,838+dy3),"mTLS + ed25519 · zero trust",m(28),TH.dim,k4,0,"mt")

# ---------------- 5. the pipeline ----------------
# order follows the NARRATION ("identity verified, personal data stripped,
# ... every message auditable"), not the wire order.
GATES=[("VERIFY IDENTITY", "signed; forgeries rejected", ws("identity")-0.30),
       ("STRIP PII",       "emails, keys, SSNs removed", ws("stripped")-0.30),
       ("AUDIT TRAIL",     "every message, both sides",  ws("auditable.")-0.55)]
def s_pipe(ov,d,t,t0):
    S.eyebrow(ov,d,"WHAT LEAVES YOUR NODE",t,t0,TH,col=TH.support)
    k,dy=enter(t,t0+0.06,0.34,22)
    # your node
    if k>0.01:
        box=(MARGIN,332+dy,W-MARGIN,438+dy)
        card(d,box,20,(14,20,30),0.94*k,TH.support,0.55*k,2)
        text(d,(MARGIN+32,385+dy),"YOUR NODE",f(32,"bold"),TH.support,k,4,"lm")
        text(d,(W-MARGIN-32,385+dy),"agents · memory",m(26),TH.dim,k,0,"rm")
    # gates
    for i,(title,sub,ts) in enumerate(GATES):
        kk,dyk=enter(t,ts,0.34,22)
        if kk<=0.01: continue
        y=482+i*172+dyk
        lit=eo3(lin(t,ts+0.10,ts+0.42))
        col=mix(TH.border,TH.accent,lit)
        card(d,(MARGIN+52,y,W-MARGIN-52,y+126),20,(16,16,30),0.95*kk,col,0.75*kk,2)
        if lit>0.4: put_glow(ov,540,y+63,TH.glow,440,0.14*lit)
        text(d,(MARGIN+86,y+46),title,f(34,"bold"),WHITE,kk,3,"lm")
        text(d,(MARGIN+86,y+90),sub,m(26),TH.muted,kk*0.9,0,"lm")
        rr=13; cx=W-MARGIN-92
        d.ellipse((cx-rr,y+63-rr,cx+rr,y+63+rr),outline=rgba(col,0.85*kk),width=2)
        if lit>0.5:
            d.line([(cx-6,y+64),(cx-1,y+69),(cx+7,y+57)],
                   fill=rgba(TH.ok,lit),width=4,joint="curve")
        if i<2:
            pa=eo3(lin(t,ts+0.30,GATES[i+1][2]))
            d.line((540,y+126,540,y+126+46*pa),fill=rgba(TH.accent,0.7),width=4)
    # their node
    kt,dyt=enter(t,ws("auditable.")-0.05,0.36,22)
    if kt>0.01:
        box=(MARGIN,1006+dyt,W-MARGIN,1112+dyt)
        card(d,box,20,TH.card,0.92*kt,TH.border,0.9*kt,2)
        text(d,(MARGIN+32,1059+dyt),"THEIR NODE",f(32,"bold"),TH.muted,kt,4,"lm")
        text(d,(W-MARGIN-32,1059+dyt),"trust: earned, revocable",m(26),TH.dim,kt,0,"rm")

# ---------------- 6. close ----------------
def s_close(ov,d,t,t0):
    S.eyebrow(ov,d,"THE NUMBERS",t,t0,TH)
    kb=eob(lin(t,ws("MIT.")-0.14,ws("MIT.")+0.46),2.0)
    if kb>0.01: pill(d,540,368,"MIT LICENSED",f(34,"bold"),TH.ok,kb,track=5)
    counter(ov,d,(540,560),68295,t,ws("Sixty-eight")-0.30,TH,dur=1.25,size=132,
            label="GITHUB STARS")
    k,dy=enter(t,t0+1.20,0.4,20)
    if k>0.01:
        cw=(W-2*MARGIN-32)/3
        for i,(v,l) in enumerate([("8.1M+","DOWNLOADS"),("33","CC PLUGINS"),
                                  ("12","BG WORKERS")]):
            kk=eo3(lin(t,t0+1.25+i*0.14,t0+1.58+i*0.14))
            if kk<=0.01: continue
            x=MARGIN+i*(cw+16)
            card(d,(x,720+dy,x+cw,860+dy),20,TH.card,0.85*kk,TH.border,0.9*kk,2)
            grad_text(ov,(x+cw/2,720+22+dy),v,f(44,"bold"),TH.accent_hi,TH.accent,kk,"mt")
            text(d,(x+cw/2,720+112+dy),l,f(23,"bold"),TH.muted,kk,3,"mm")

# ---------------- dispatch ----------------
def frame(t):
    base=BASE.copy()
    ov=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(ov)
    n,a,b=scene_at(t)
    {"eq":s_eq,"title":s_title,"cmd":s_cmd,"fed":s_fed,"pipe":s_pipe,
     "close":s_close}.get(n,lambda *_: None)(ov,d,t,a)
    if n=="end":
        endcard(ov,d,t,a,TH,"ruflo","agent meta-harness",
                "github.com/ruvnet/ruflo","npx ruflo init",
                "SAVE THIS FOR YOUR NEXT SETUP",mark_size=232)
    S.chrome(base,d,t,TH,TOTAL,"ruvnet/ruflo")
    S.cut_sweep(ov,d,t,CUTS,TH)
    if n!="end": S.captions(ov,d,t,CH,TH)
    base.alpha_composite(ov)
    return base

_BIG={7.78,37.25}
SFX=(
 [{"t":c-0.30,"kind":"swish","amp":0.15} for c in CUTS] +
 [{"t":c,"kind":"thump","amp":0.29 if c in _BIG else 0.20,
   "dur":0.55 if c in _BIG else 0.34,"freq":46.0 if c in _BIG else 58.0}
    for c in CUTS] +
 [{"t":ts,"kind":"tick","amp":0.08,"tone":2600.0} for _,ts in LOOP] +
 [{"t":ts,"kind":"tick","amp":0.075,"tone":3000.0} for _,_,ts in GATES] +
 [{"t":ws("decides")-0.25,"kind":"thump","amp":0.18,"dur":0.34,"freq":54.0},
  {"t":ws("Flow")-0.05,"kind":"tick","amp":0.09,"tone":1800.0},
  {"t":ws("npx")-0.15,"kind":"tick","amp":0.07,"tone":3000.0},
  {"t":ws("Sixty-eight")-0.30,"kind":"tick","amp":0.075,"tone":3200.0}]
)
