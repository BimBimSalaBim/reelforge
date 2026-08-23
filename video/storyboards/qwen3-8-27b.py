# ---------------------------------------------------------------
# qwen3-8-27b.py -- Qwen3.8-27B. Violet.
#
# A different design language from the tool reels: content hangs off a
# vertical RAIL that is the model's own hidden layout -- 64 cells, every
# fourth one a lit full-attention layer -- and every panel is square with a
# lit left edge instead of a rounded card. The rail is on screen at frame 0
# and is what pays off the opening line, so it is never decoration.
#
# Scene boundaries are derived from the phrase segments rather than typed in,
# so they follow the narration when the real recording replaces the clock.
# ---------------------------------------------------------------
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kit, sbkit as S
from kit import (W,H,MARGIN,f,m,clamp,lin,eo3,eo4,eob,pulse,rgba,mix,tw,text,
                 grad_text,wrap,radial,put_glow,card,pill,hline)
from sbkit import Theme, WHITE, enter, counter
from timing import Timing

NAME    = "qwen3-8-27b"
AUDIO   = "qwen3-8-27b.mp3"
PHRASES = "phrases/qwen3-8-27b.txt"
FPS     = 30

# A provisional clock (word times estimated from the script, no recording yet)
# must never ship silently. stderr, not stdout -- stdout is the frame pipe.
import json as _json
if _json.load(open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))),"build",f"{NAME}.timing.json"))).get("provisional"):
    print(f"WARNING: {NAME} is rendering against a PROVISIONAL clock. "
          "Run align.py build against the real mp3 before shipping.",file=sys.stderr)

_T=Timing(NAME); WORDS=_T.words
ws,we = _T.ws, _T.we
CH=_T.chunks()
SEG=_T.segments
def B(i): return SEG[i][0]

# whole number of frames, or the nb_frames assert in make.sh trips (gotcha 8)
TOTAL = int(round((SEG[-1][1]+2.95)*FPS))/FPS

TH=Theme(bg=(9,7,18),accent=(150,108,255),accent_hi=(198,172,255),
         pale=(232,222,255),glow=(74,38,170),support=(94,234,212),
         cardc=(20,19,34),border=(52,46,78))
TH.apply()

RX,RW,CX = 84,52,180          # rail x, rail width, content left edge
RIGHT    = W-MARGIN

def build_ground():
    """bloom sits behind the rail, not centre-frame -- the left edge is the subject"""
    a=np.zeros((H,W,3),np.float32); a[:,:]=TH.bg
    for cx,cy,rad,col,st,pw in [(150,620,1200,TH.glow,0.34,2.2),
                                (980,1560,900,TH.support,0.07,2.6),
                                (560,900,1400,(26,24,42),0.22,1.6)]:
        a+=radial(W,H,cx,cy,rad,pw)[:,:,None]*np.array(col,np.float32)*st
    a*=np.linspace(1.0,0.74,H,dtype=np.float32)[:,None,None]
    rng=np.random.RandomState(7)
    a+=rng.normal(0,2.1,(H,W,1)).astype(np.float32)   # keep the grain: it is what
    a+=rng.normal(0,0.9,(H,W,3)).astype(np.float32)   # stops banding after re-encode
    return Image.fromarray(np.clip(a,0,255).astype(np.uint8),"RGB").convert("RGBA")
BASE=build_ground()

# indices into the 24 voiced phrases: 0-3 stack, 4-7 name+DeltaNet,
# 8-11 cost+context, 12-17 multimodal+thinking, 18-21 scores, 22-23 close
SC=[("stack" ,0.0   ,B(4)),
    ("delta" ,B(4)  ,B(8)),
    ("cost"  ,B(8)  ,B(12)),
    ("sees"  ,B(12) ,B(18)),
    ("scores",B(18) ,B(22)),
    ("close" ,B(22) ,SEG[-1][1]+0.55),
    ("end"   ,SEG[-1][1]+0.55,TOTAL)]
def scene_at(t):
    for n,a,b in SC:
        if a<=t<b: return n,a,b
    return SC[-1]
CUTS=[a for _,a,_ in SC[1:]]

# ---------------- the design system ----------------
def rail(ov,d,t,ign=0.0,dn=0.0,full=0.0):
    """the spine. ign lights the 16 attention layers in order; dn tints the 48
    DeltaNet layers teal; full lights everything (end card)."""
    y0,y1,n,ev=150,1380,64,4
    put_glow(ov,RX+RW/2,700,TH.glow,540,0.13+0.04*pulse(t,5.0))
    pitch=(y1-y0)/n; ch=pitch*0.60; li=0
    for i in range(n):
        yy=y0+i*pitch
        box=[int(v) for v in (RX,yy,RX+RW,yy+ch)]
        if i%ev==ev-1:
            k=max(clamp(ign*16-li),full); li+=1
            if k>0.02:
                d.rounded_rectangle(box,radius=3,fill=rgba(TH.accent,0.92*k)); continue
        col=mix(TH.accent,TH.support,dn)
        d.rounded_rectangle(box,radius=3,fill=rgba(col,0.10+0.14*dn+0.70*full),
                            outline=rgba(col,0.32+0.30*dn),width=1)

def panel(ov,d,box,t,t0,edge=None,fa=0.90,dur=0.32,dyv=24):
    """square panel, lit left edge. returns (alpha, dy) so contents can follow."""
    k,dy=enter(t,t0,dur,dyv)
    if k<=0.01: return 0.0,0.0
    x0,y0,x1,y1=box; y0+=dy; y1+=dy
    card(d,(x0,y0,x1,y1),6,TH.card,fa*k,TH.border,0.95*k,2)
    d.rectangle((int(x0),int(y0),int(x0)+4,int(y1)),fill=rgba(edge or TH.accent,0.95*k))
    return k,dy

def fitm(txt,sizes=(30,28,26,24,22),wide=None):
    """largest mono size that stays inside the x 84-996 safe area"""
    lim=wide or (RIGHT-CX)
    fo=next((m(z) for z in sizes if tw(txt,m(z))<=lim),m(sizes[-1]))
    assert tw(txt,fo)<=lim+1, f"{txt!r} does not fit the safe area at any size"
    return fo

def tag(d,txt,t,t0,y=206,col=None):
    """left-aligned square tag -- the counterpart to sbkit's centred pill"""
    k=eo3(lin(t,t0,t0+0.32))
    if k<=0.01: return
    col=col or TH.accent
    fo=f(28,"bold"); wd=tw(txt,fo,6)
    # the chrome slug is right-aligned at y 176; a long tag runs under it
    assert CX+wd+58 < 740, f"tag {txt!r} is too wide -- it will hit the chrome slug"
    d.rounded_rectangle((CX,y-26,CX+wd+58,y+26),radius=6,outline=rgba(col,0.85*k),width=2)
    d.ellipse((CX+20,y-6,CX+32,y+6),fill=rgba(col,k))
    text(d,(CX+46,y),txt,fo,col,k,6,"lm")

def cmdbar(ov,d,box,cmd,t,t0,dur=1.1):
    """the cover's command bar, typed"""
    k,dy=panel(ov,d,box,t,t0)
    if k<=0.01: return
    x0,y0,x1,y1=box; y0+=dy; y1+=dy; cy=(y0+y1)/2
    fo=m(30)
    n=int(len(cmd)*clamp((t-t0-0.12)/dur))
    show=cmd if t>=t0+0.12+dur else cmd[:n]
    text(d,(x0+30,cy),"›",m(34,"bold"),TH.accent,k,0,"lm")
    text(d,(x0+68,cy),show,fo,WHITE,k,0,"lm")
    if t<t0+0.12+dur and int(t*8)%2==0:
        cx=x0+68+fo.getlength(show)
        d.rectangle((int(cx)+2,int(cy)-16,int(cx)+15,int(cy)+14),
                    fill=rgba(TH.accent_hi,0.85))

# ---------------- 1. the stack ----------------
def s_stack(ov,d,t,t0):
    ign=eo3(lin(t,ws("Sixteen")-0.05,we("attention",0)+0.15))
    dnp=0.30*eo3(lin(t,ws("forty-eight")-0.10,ws("forty-eight")+0.60))
    rail(ov,d,t,ign=ign,dn=dnp)

    # the hook is fully legible at frame 0: no fade up, no logo intro, and the
    # model is named in the first frame because most views start muted
    tag(d,"HIDDEN LAYOUT",t,-0.40)
    text(d,(CX,292),"64 layers.",f(84,"bold"),WHITE,1.0,0,"lt")
    sub="Qwen3.8-27B · 27B dense · native vision"
    text(d,(CX,400),sub,fitm(sub),TH.muted,1.0,0,"lt")

    k,dy=enter(t,ws("Sixteen")-0.12,0.32,22)
    if k>0.01:
        text(d,(CX,486+dy),"16 run full",f(84,"bold"),TH.accent,k,0,"lt")
        text(d,(CX,582+dy),"attention.",f(84,"bold"),TH.accent,k,0,"lt")

    k2=eo3(lin(t,we("attention",0)-0.10,we("attention",0)+0.26))
    if k2>0.01:
        text(d,(CX,700),"16 × GATED ATTENTION",m(32,"bold"),TH.accent_hi,k2,2,"lt")

    k3,dy3=panel(ov,d,(CX,790,RIGHT,950),t,ws("forty-eight")-0.14,edge=TH.support)
    if k3>0.01:
        text(d,(CX+34,838+dy3),"THE OTHER 48",f(30,"bold"),TH.muted,k3,4,"lt")
        text(d,(CX+34,884+dy3),"SOMETHING ELSE",m(42,"bold"),TH.support,k3,0,"lt")
        kq=eob(lin(t,ws("else.")-0.20,ws("else.")+0.40),2.2)
        grad_text(ov,(RIGHT-46,814+dy3),"?",f(int(104*(0.86+0.14*kq)),"bold"),
                  TH.support,TH.accent,k3,"rt")

# ---------------- 2. what the 48 are ----------------
def s_delta(ov,d,t,t0):
    dnp=eo3(lin(t,ws("DeltaNet")-0.18,ws("DeltaNet")+0.65))
    rail(ov,d,t,ign=1.0,dn=dnp)
    tag(d,"THE OTHER 48",t,t0,col=TH.support)

    # where the model gets named -- version small, size as the hero (cover echo)
    k,dy=enter(t,ws("Qwen")-0.14,0.34,20)
    if k>0.01:
        text(d,(CX+4,304+dy),"QWEN3.8",m(52,"bold"),TH.pale,0.95*k,9,"lt")
        grad_text(ov,(CX,362+dy),"27B",f(146,"bold"),WHITE,TH.pale,k,"lt",-4)
    k1=eo3(lin(t,ws("twenty-seven")-0.05,ws("twenty-seven")+0.34))
    if k1>0.01:
        sub="27B dense · all parameters active"
        text(d,(CX,536),sub,fitm(sub),TH.muted,k1,0,"lt")

    # "three of every four" -- bracket one repeating unit on the rail itself,
    # so the claim is made by the spine rather than by a caption
    ku=eo3(lin(t,ws("four")-0.15,ws("four")+0.38))
    if ku>0.01:
        pitch=(1380-150)/64.0; i0=48
        by0=150+i0*pitch-5; by1=150+(i0+4)*pitch-pitch*0.40+5
        cy=(by0+by1)/2
        # hugs the rail's own left edge: RX is the x=84 safe boundary
        d.rounded_rectangle((RX+2,by0,RX+RW+14,by1),radius=5,
                            outline=rgba(TH.accent_hi,0.85*ku),width=3)
        d.line((RX+RW+18,cy,CX-14,cy),fill=rgba(TH.accent_hi,0.50*ku),width=2)
        text(d,(CX,cy),"3 of every 4",m(31,"bold"),TH.accent_hi,ku,0,"lm")

    k2,dy2=panel(ov,d,(CX,606,RIGHT,772),t,ws("DeltaNet")-0.16,edge=TH.support)
    if k2>0.01:
        text(d,(CX+34,652+dy2),"GATED DELTANET",f(46,"bold"),TH.support,k2,1,"lt")
        text(d,(CX+34,714+dy2),"48 of 64 layers",m(30),TH.muted,k2,0,"lt")
        text(d,(RIGHT-34,652+dy2),"48",m(52,"bold"),TH.support,k2,0,"rt")

    k3=eo3(lin(t,ws("linear")-0.12,ws("linear")+0.30))
    if k3>0.01:
        fo=f(34,"bold"); lab="LINEAR ATTENTION"
        wd=tw(lab,fo,5)+64
        d.rounded_rectangle((CX,812,CX+wd,878),radius=6,
                            fill=rgba(TH.support,0.13*k3),outline=rgba(TH.support,0.85*k3),width=2)
        text(d,(CX+32,846),lab,fo,TH.support,k3,5,"lm")
    k4=eo3(lin(t,ws("linear")+0.28,ws("linear")+0.70))
    if k4>0.01:
        lay="16 × (3 × DeltaNet → FFN) → 1 × (Attention → FFN)"
        text(d,(CX,936),lay,fitm(lay,(28,26,24,22)),TH.dim,k4,0,"lt")

# ---------------- 3. why it scales ----------------
def curves(ov,d,box,p):
    x0,y0,x1,y1=box
    for i in range(5):
        yy=y0+i*(y1-y0)/4
        d.line((x0+20,yy,x1-20,yy),fill=rgba(WHITE,0.045),width=1)
    ax0,ax1,ay0,ay1=x0+40,x1-40,y0+30,y1-32
    npts=max(2,int(120*clamp(p)))
    quad,linr=[],[]
    for i in range(npts):
        u=i/119.0
        quad.append((ax0+u*(ax1-ax0), ay1-(u**2.6)*(ay1-ay0)*2.7))
        linr.append((ax0+u*(ax1-ax0), ay1-u*(ay1-ay0)*0.30))
    quad=[q for q in quad if q[1]>=ay0-6]
    if len(linr)>1: d.line(linr,fill=rgba(TH.accent,0.92),width=4)
    if len(quad)>1: d.line(quad,fill=rgba(TH.support,0.78),width=4)
    text(d,(x1-26,y0+22),"O(n^2)",m(26,"bold"),TH.support,0.90,0,"rt")
    text(d,(x1-26,ay1-(ay1-ay0)*0.30-40),"O(n)",m(26,"bold"),TH.accent,0.95,0,"rt")

def s_cost(ov,d,t,t0):
    rail(ov,d,t,ign=1.0,dn=1.0)
    tag(d,"WHY IT SCALES",t,t0)
    k,dy=enter(t,ws("Cost")-0.14,0.32,20)
    if k>0.01:
        text(d,(CX,296+dy),"Cost grows with length,",f(62,"bold"),TH.muted,k,0,"lt")
    k1,dy1=enter(t,ws("squared.")-0.30,0.32,20)
    if k1>0.01:
        text(d,(CX,376+dy1),"not length squared.",f(62,"bold"),WHITE,k1,0,"lt")

    kp,dyp=panel(ov,d,(CX,462,RIGHT,846),t,ws("Cost")+0.10,fa=0.72)
    if kp>0.01:
        curves(ov,d,(CX,462+dyp,RIGHT,846+dyp),
               lin(t,ws("Cost")+0.30,ws("squared.")+0.45))

    # one counter that jumps rather than two competing for the eye
    jump=ws("million")-0.12
    if t>=jump:
        counter(ov,d,(588,962),1000000,t,jump,TH,dur=0.55,size=112,
                label="EXTENSIBLE WITH YaRN")
    else:
        counter(ov,d,(588,962),262144,t,ws("quarter-million")-0.20,TH,
                dur=1.15,size=112,label="NATIVE CONTEXT")
    k3=eo3(lin(t,ws("YaRN.")-0.10,ws("YaRN.")+0.34))
    if k3>0.01:
        text(d,(588,1120),"262,144 native · 1,000,000 only with YaRN",
             m(28),TH.dim,k3,0,"mt")

# ---------------- 4. and it sees ----------------
IN=[("IMAGE","STEM diagrams","images,"),
    ("DOCUMENT","OmniDocBench 91.1","documents,"),
    ("HOUR-SCALE VIDEO","up to an hour","video.")]
def s_sees(ov,d,t,t0):
    rail(ov,d,t,ign=1.0,dn=1.0)
    tag(d,"AND IT SEES",t,t0)
    k,dy=enter(t,ws("multimodal")-0.30,0.32,20)
    if k>0.01:
        text(d,(CX,294+dy),"Natively multimodal.",f(70,"bold"),WHITE,k,0,"lt")

    # three inputs feeding the same stack -- the lines run into the rail
    for i,(lab,sub,cue) in enumerate(IN):
        y0=392+i*104; t1=ws(cue)-0.16
        kk,dyk=panel(ov,d,(CX,y0,RIGHT,y0+84),t,t1,edge=TH.support,dyv=0)
        if kk<=0.01: continue
        cy=y0+42+dyk
        text(d,(CX+30,cy),lab,f(34,"bold"),WHITE,kk,1,"lm")
        text(d,(RIGHT-30,cy),sub,m(25),TH.dim,kk,0,"rm")
        kl=eo3(lin(t,t1+0.10,t1+0.40))
        if kl>0.01:
            d.line((RX+10,cy,CX-6,cy),fill=rgba(TH.support,0.60*kl),width=2)

    kt,dyt=panel(ov,d,(CX,724,RIGHT,904),t,ws("Thinking")-0.16)
    if kt>0.01:
        yy=724+dyt
        text(d,(CX+30,yy+42),"<think>",m(32,"bold"),TH.accent,kt,0,"lm")
        text(d,(CX+62,yy+92),"reasoning_effort: xhigh",m(30),TH.pale,kt,0,"lm")
        text(d,(CX+30,yy+142),"</think>",m(32,"bold"),TH.accent,kt,0,"lm")
        text(d,(RIGHT-30,yy+42),"ON BY DEFAULT",f(25,"bold"),TH.muted,kt,3,"rm")
    k4=eo3(lin(t,ws("default.")-0.05,ws("default.")+0.34))
    if k4>0.01:
        text(d,(CX,952),"xhigh  ·  medium  ·  low",m(30,"bold"),TH.dim,k4,2,"lt")

# ---------------- 5. the scores ----------------
# (name, sub, value, row cue, sub cue) -- the sub cue gives the row a second
# beat so an 11s hold is not three events with 3.5s of nothing between them
BM=[("GPQA Diamond","graduate science","89.2","Eighty-nine",None),
    ("LiveCodeBench v6","code","90.3","ninety",None),
    ("OSWorld-Verified","driving a real desktop","84.3","eighty-four","driving")]
def s_scores(ov,d,t,t0):
    rail(ov,d,t,ign=1.0,dn=1.0)
    tag(d,"ON THE MODEL CARD",t,t0)
    for i,(name,sub,val,cue,scue) in enumerate(BM):
        y0=320+i*182; tc=ws(cue)-0.18
        kk,dy=panel(ov,d,(CX,y0,RIGHT,y0+152),t,tc)
        if kk<=0.01: continue
        text(d,(CX+34,y0+52+dy),name,f(40,"bold"),WHITE,kk,0,"lt")
        ks=kk if scue is None else eo3(lin(t,ws(scue)-0.14,ws(scue)+0.28))
        text(d,(CX+34,y0+108+dy),sub,m(26),TH.dim,ks,0,"lt")
        grad_text(ov,(RIGHT-34,y0+44+dy),val,f(72,"bold"),
                  TH.accent_hi,TH.accent,kk,"rt")
        # the score as a share of 100, filling just after the number lands
        S.bar(ov,d,(CX+34,y0+132+dy,RIGHT-34,y0+142+dy),
              float(val)/100.0*eo4(lin(t,tc+0.34,tc+1.25)),TH,r=5)
    k=eo3(lin(t,ws("OSWorld.")+0.20,ws("OSWorld.")+0.60))
    if k>0.01:
        text(d,(CX,904),"Qwen's own reported figures",m(27),TH.dim,k,0,"lt")

# ---------------- 6. the close ----------------
def s_close(ov,d,t,t0):
    rail(ov,d,t,ign=1.0,dn=1.0)
    k,dy=enter(t,ws("Apache")-0.14,0.32,20)
    if k>0.01:
        grad_text(ov,(CX,286+dy),"APACHE-2.0",f(92,"bold"),WHITE,TH.accent_hi,k,"lt",-2)
        text(d,(CX+6,412+dy),"weights, code, and the right to ship it",
             m(29),TH.muted,k,0,"lt")
    cmdbar(ov,d,(CX,492,RIGHT,600),'vllm serve "Qwen/Qwen3.8-27B"',
           t,ws("command")-0.20)
    counter(ov,d,(588,748),677,t,ws("Six")-0.15,TH,dur=1.0,size=124,
            label="QUANTIZATIONS ALREADY")
    k3=eo3(lin(t,ws("quantizations")+0.10,ws("quantizations")+0.52))
    if k3>0.01:
        text(d,(588,912),"llama.cpp  ·  LM Studio  ·  Jan  ·  Ollama",
             m(30,"bold"),TH.dim,k3,1,"mt")

# ---------------- 7. end card ----------------
def s_end(ov,d,t,t0):
    rail(ov,d,t,ign=1.0,dn=0.0,full=eo3(lin(t,t0,t0+0.55)))
    k=eo3(lin(t,t0,t0+0.34)); kb=eob(lin(t,t0,t0+0.55),1.4)
    put_glow(ov,588,560,TH.glow,780,0.28*k+0.04*pulse(t,2.5))
    grad_text(ov,(588,556),"Qwen3.8-27B",m(int(92*(0.94+0.06*kb)),"bold"),
              WHITE,TH.pale,k,"mm",4)
    text(d,(588,676),"27B dense · native vision · Apache-2.0",m(30),TH.muted,k,2,"mm")
    k2=eo3(lin(t,t0+0.22,t0+0.56))
    hline(d,588-int(150*k2),588+int(150*k2),742,TH.accent,0.9*k2,4)
    text(d,(588,802),"huggingface.co",m(38,"bold"),WHITE,k2,0,"mt")
    text(d,(588,856),"/Qwen/Qwen3.8-27B",m(34),TH.accent,k2,0,"mt")
    k3=eo3(lin(t,t0+0.44,t0+0.80))
    if k3>0.01:
        lab="SAVE THIS FOR LATER"; fo=f(35,"bold"); wd=tw(lab,fo,4)+72
        d.rounded_rectangle((int(588-wd/2),986,int(588+wd/2),1068),radius=8,
                            fill=rgba(TH.accent,0.94*k3))
        text(d,(588,1028),lab,fo,(8,8,14),k3,4,"mm")
        put_glow(ov,588,1027,TH.glow,320,0.16*k3)
    k4=eo3(lin(t,t0+0.70,t0+1.05))
    if k4>0.01:
        lab="WATCH AGAIN"; fl=f(28,"bold"); wd=tw(lab,fl,5)
        text(d,(588-wd/2-38,1146),"↻",m(30),TH.dim,k4,0,"lm")
        text(d,(588+18,1146),lab,fl,TH.dim,k4,5,"mm")

# ---------------- dispatch ----------------
def frame(t):
    base=BASE.copy()
    ov=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(ov)
    n,a,b=scene_at(t)
    {"stack":s_stack,"delta":s_delta,"cost":s_cost,"sees":s_sees,
     "scores":s_scores,"close":s_close,"end":s_end}.get(n,lambda *_:None)(ov,d,t,a)
    S.chrome(base,d,t,TH,TOTAL,"Qwen/Qwen3.8-27B")
    S.cut_sweep(ov,d,t,CUTS,TH)
    if n!="end": S.captions(ov,d,t,CH,TH)
    base.alpha_composite(ov)
    return base

# ---------------- sound design ----------------
# subtle: soft impact on cuts, tick on discrete reveals. Narration stays dominant.
# a tick every other attention layer, spread across the real ignition window
_I0,_I1=ws("Sixteen")-0.05,we("attention",0)+0.15
_IGN=[_I0+(_I1-_I0)*(i/7.0) for i in range(8)]
SFX=(
 [{"t":c-0.28,"kind":"swish","amp":0.14} for c in CUTS] +
 [{"t":c,"kind":"thump","amp":0.20,"dur":0.34,"freq":58.0} for c in CUTS] +
 [{"t":x,"kind":"tick","amp":0.055,"tone":3200.0} for x in _IGN] +
 [{"t":ws(cue)-0.16,"kind":"tick","amp":0.075,"tone":2600.0} for _,_,cue in IN] +
 [{"t":ws(b[3])-0.18,"kind":"tick","amp":0.085,"tone":2800.0} for b in BM] +
 [{"t":ws("else.")-0.20,"kind":"thump","amp":0.17,"dur":0.32,"freq":64.0},
  {"t":ws("four")-0.15,"kind":"tick","amp":0.07,"tone":2000.0},
  {"t":ws("DeltaNet")-0.18,"kind":"tick","amp":0.09,"tone":2400.0},
  {"t":ws("squared.")+0.10,"kind":"thump","amp":0.26,"dur":0.48,"freq":48.0},
  {"t":ws("quarter-million")-0.20,"kind":"tick","amp":0.07,"tone":3000.0},
  {"t":ws("million")-0.12,"kind":"thump","amp":0.16,"dur":0.30,"freq":62.0},
  {"t":ws("Thinking")-0.16,"kind":"tick","amp":0.07,"tone":2200.0},
  {"t":ws("Apache")-0.14,"kind":"thump","amp":0.18,"dur":0.36,"freq":56.0},
  {"t":ws("Six")-0.15,"kind":"tick","amp":0.075,"tone":3000.0},
  {"t":SC[-1][1],"kind":"sweep","amp":0.10}]          # into the end card
)
