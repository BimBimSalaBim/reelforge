# ---------------------------------------------------------------
# muse-glimmer-30b.py -- Muse Glimmer-30B. Lime throughput, slate baseline.
#
# Third model release, so it keeps the rail + square-panel family, but the
# rail is neither a layer stack (qwen) nor a filmstrip (ltx): it is a TOKEN
# STREAM that fills over the whole runtime with a bright leading edge, so the
# spine is literally generating for the length of the video. That also gives
# every long scene continuous motion.
#
# The angle is deliberately NOT the 3-local-to-1-global attention pattern,
# even though config.json confirms it: the Qwen3.8-27B reel already built a
# whole storyboard on a 3:1 layer ratio and repeating it would make the two
# videos look like one video. The angle is speed on hardware you own.
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

NAME    = "muse-glimmer-30b"
AUDIO   = "muse-glimmer-30b.mp3"
PHRASES = "phrases/muse-glimmer-30b.txt"
FPS     = 30

_T=Timing(NAME); WORDS=_T.words
ws,we = _T.ws, _T.we
CH=_T.chunks()
SEG=_T.segments
def B(i): return SEG[i][0]

# whole number of frames, or the nb_frames assert in make.sh trips (gotcha 8)
TOTAL = int(round((SEG[-1][1]+2.95)*FPS))/FPS

TH=Theme(bg=(10,12,9),accent=(184,255,72),accent_hi=(216,255,150),
         pale=(238,255,214),glow=(60,110,20),support=(122,164,255),
         cardc=(20,24,18),border=(50,60,42))
TH.apply()

RX,RW,CX = 84,52,180
RIGHT    = W-MARGIN
# The chrome slug is right-aligned at RIGHT. A previous reel hardcoded the tag
# guard at x<740, which only held because its slug was 16 chars; this one is
# longer, so derive the limit from the slug itself.
SLUG   = "Muse-Glimmer-30B"
SLUG_X = RIGHT - tw(SLUG, m(25))

def build_ground():
    a=np.zeros((H,W,3),np.float32); a[:,:]=TH.bg
    for cx,cy,rad,col,st,pw in [(140,700,1240,TH.glow,0.42,2.2),
                                (1000,1600,940,TH.support,0.05,2.6),
                                (560,900,1400,(22,26,20),0.22,1.6)]:
        a+=radial(W,H,cx,cy,rad,pw)[:,:,None]*np.array(col,np.float32)*st
    a*=np.linspace(1.0,0.74,H,dtype=np.float32)[:,None,None]
    rng=np.random.RandomState(17)
    a+=rng.normal(0,2.1,(H,W,1)).astype(np.float32)   # keep the grain: it is
    a+=rng.normal(0,0.9,(H,W,3)).astype(np.float32)   # what stops banding
    return Image.fromarray(np.clip(a,0,255).astype(np.uint8),"RGB").convert("RGBA")
BASE=build_ground()

# 17 phrases: 0-1 hook, 2-4 the model, 5-7 in/out, 8-10 the speed,
# 11-13 the scores, 14-16 the honest close
SC=[("hook"  ,0.0    ,B(2)),
    ("name"  ,B(2)   ,B(5)),
    ("inout" ,B(5)   ,B(8)),
    ("speed" ,B(8)   ,B(11)),
    ("scores",B(11)  ,B(14)),
    ("close" ,B(14)  ,SEG[-1][1]+0.55),
    ("end"   ,SEG[-1][1]+0.55,TOTAL)]
def scene_at(t):
    for n,a,b in SC:
        if a<=t<b: return n,a,b
    return SC[-1]
CUTS=[a for _,a,_ in SC[1:]]

# ---------------- the design system ----------------
def rail(ov,d,t,n=34):
    """the spine as a token stream. It fills across the whole runtime, so the
    rail is generating continuously -- which is also what keeps the long
    scenes moving between their scripted beats."""
    y0,y1=150,1380
    pitch=(y1-y0)/n; ch=pitch*0.66
    lead=clamp(t/TOTAL)*n
    put_glow(ov,RX+RW/2,660,TH.glow,540,0.13+0.04*pulse(t,5.0))
    for i in range(n):
        yy=y0+i*pitch
        box=[int(v) for v in (RX,yy,RX+RW,yy+ch)]
        frac=clamp(lead-i)
        if frac>=0.999:
            d.rounded_rectangle(box,radius=3,fill=rgba(TH.accent,0.48))
        elif frac>0.02:
            # The leading cell gets no halo. The rail centre sits at x=110,
            # only 26px inside the x=84 safe edge, so any halo big enough to
            # read also bleeds out of frame -- and the bright fill plus the
            # rail's own bloom already carry the leading edge.
            d.rounded_rectangle(box,radius=3,fill=rgba(TH.accent_hi,0.98*frac),
                                outline=rgba(TH.pale,0.85*frac),width=2)
        else:
            d.rounded_rectangle(box,radius=3,fill=rgba(TH.accent,0.05),
                                outline=rgba(TH.accent,0.20),width=1)

def panel(ov,d,box,t,t0,edge=None,fa=0.90,dur=0.32,dyv=24):
    k,dy=enter(t,t0,dur,dyv)
    if k<=0.01: return 0.0,0.0
    x0,y0,x1,y1=box; y0+=dy; y1+=dy
    card(d,(x0,y0,x1,y1),6,TH.card,fa*k,TH.border,0.95*k,2)
    d.rectangle((int(x0),int(y0),int(x0)+4,int(y1)),fill=rgba(edge or TH.accent,0.95*k))
    return k,dy

def tag(d,txt,t,t0,y=206,col=None):
    k=eo3(lin(t,t0,t0+0.32))
    if k<=0.01: return
    col=col or TH.accent
    fo=f(28,"bold"); wd=tw(txt,fo,6)
    assert CX+wd+58 < SLUG_X-16, \
        f"tag {txt!r} is too wide -- it would hit the chrome slug at x={SLUG_X}"
    d.rounded_rectangle((CX,y-26,CX+wd+58,y+26),radius=6,outline=rgba(col,0.85*k),width=2)
    d.ellipse((CX+20,y-6,CX+32,y+6),fill=rgba(col,k))
    text(d,(CX+46,y),txt,fo,col,k,6,"lm")

def fitm(txt,sizes=(30,28,26,24,22),wide=None):
    lim=wide or (RIGHT-CX)
    fo=next((m(z) for z in sizes if tw(txt,m(z))<=lim),m(sizes[-1]))
    assert tw(txt,fo)<=lim+1, f"{txt!r} does not fit the safe area at any size"
    return fo

def chip(ov,d,box,label,t,t0,col=None,mono=True,fs=28):
    k,dy=enter(t,t0,0.28,16)
    if k<=0.01: return 0.0
    x0,y0,x1,y1=box; y0+=dy; y1+=dy
    col=col or TH.accent
    d.rounded_rectangle((int(x0),int(y0),int(x1),int(y1)),radius=6,
        fill=rgba(col,0.13*k),outline=rgba(col,0.85*k),width=2)
    text(d,((x0+x1)/2,(y0+y1)/2),label,(m if mono else f)(fs,"bold"),col,k,1,"mm")
    return k

MAXTPS=233.4
def lane(ov,d,y0,label,tps,t,col,k=1.0,h=92,stream=True):
    """one throughput lane: a bar, the tok/s figure, and tokens streaming out"""
    if k<=0.01: return
    card(d,(CX,y0,RIGHT,y0+h),6,TH.card,0.88*k,TH.border,0.92*k,2)
    d.rectangle((int(CX),int(y0),int(CX)+4,int(y0+h)),fill=rgba(col,0.95*k))
    text(d,(CX+28,y0+26),label,m(24,"bold"),col,0.95*k,2,"lt")
    bw=(RIGHT-CX-330)*(tps/MAXTPS)
    d.rounded_rectangle((int(CX+28),int(y0+52),int(CX+28+bw),int(y0+74)),radius=5,
                        fill=rgba(col,0.34*k),outline=rgba(col,0.85*k),width=2)
    text(d,(RIGHT-28,y0+46),f"{tps}",m(44,"bold"),col,k,0,"rt")
    text(d,(RIGHT-28,y0+h-22),"tok/s",m(22),TH.dim,0.9*k,1,"rb")
    if stream:                      # tokens leaving the lane, paced by tok/s
        sp=tps/MAXTPS*260.0
        for j in range(7):
            x=CX+28+((t*sp+j*46)%max(bw,1))
            d.rounded_rectangle((int(x),int(y0+56),int(x)+12,int(y0+70)),radius=3,
                                fill=rgba(TH.pale if col is TH.accent else col,0.55*k))

def bar_row(ov,d,y0,name,sub,val,t,t0,h=118,vmax=100.0):
    """a benchmark row whose bar fills just after the number lands"""
    k,dy=panel(ov,d,(CX,y0,RIGHT,y0+h),t,t0)
    if k<=0.01: return
    yy=y0+dy
    text(d,(CX+30,yy+30),name,f(38,"bold"),WHITE,k,0,"lt")
    text(d,(CX+30,yy+76),sub,m(24),TH.dim,k,0,"lt")
    grad_text(ov,(RIGHT-30,yy+24),val,f(62,"bold"),TH.accent_hi,TH.accent,k,"rt")
    S.bar(ov,d,(CX+30,yy+h-22,RIGHT-30,yy+h-12),
          float(val)/vmax*eo4(lin(t,t0+0.34,t0+1.30)),TH,r=5)

def draft_verify(ov,d,y0,t,t0,k,h=104):
    """the drafter proposes a run, the verifier accepts most and rejects one --
    which is the whole of speculative decoding"""
    if k<=0.01: return
    card(d,(CX,y0,RIGHT,y0+h),6,TH.card,0.88*k,TH.border,0.92*k,2)
    d.rectangle((int(CX),int(y0),int(CX)+4,int(y0+h)),fill=rgba(TH.support,0.95*k))
    text(d,(CX+26,y0+22),"DRAFTER",m(21,"bold"),TH.support,0.9*k,2,"lt")
    text(d,(CX+26,y0+62),"VERIFY",m(21,"bold"),TH.accent,0.9*k,2,"lt")
    n=10; x0=CX+168; cw=(RIGHT-30-x0)/n
    ph=(t-t0)*2.2
    for i in range(n):
        a=clamp(ph-i*0.16)*k
        if a<=0.02: continue
        bx=x0+i*cw
        d.rounded_rectangle((int(bx),int(y0+18),int(bx+cw-8),int(y0+42)),radius=4,
                            fill=rgba(TH.support,0.30*a),outline=rgba(TH.support,0.75*a),width=2)
        rej=(i==7)
        mk="✕" if rej else "✓"
        col=TH.bad if rej else TH.accent
        a2=clamp(ph-i*0.16-0.5)*k
        if a2>0.02:
            text(d,(bx+(cw-8)/2,y0+72),mk,m(30,"bold"),col,a2,0,"mm")

# ---------------- 1. the hook ----------------
def s_hook(ov,d,t,t0):
    rail(ov,d,t)
    tag(d,"THROUGHPUT",t,-0.40)
    # legible at frame 0, and the qualifier is on screen with the number --
    # 233.4 tok/s is an RTX 5090 with DFlash, never a bare figure
    text(d,(CX,282),"233 tokens a second.",f(62,"bold"),WHITE,1.0,0,"lt")
    lane(ov,d,372,"BASELINE",74.9,t,TH.support,1.0)
    lane(ov,d,486,"DFLASH",233.4,t,TH.accent,1.0)
    q="RTX 5090 · with DFlash · Meta's reported figures"
    text(d,(CX,614),q,fitm(q,(26,24,22)),TH.muted,1.0,0,"lt")
    k=chip(ov,d,(CX,672,CX+330,742),"ONE CONSUMER GPU",t,ws("consumer")-0.12)
    if k>0.01:
        text(d,(CX+352,707),"3.1× over baseline",m(28,"bold"),TH.accent_hi,k,0,"lm")

# ---------------- 2. what it is ----------------
def s_name(ov,d,t,t0):
    rail(ov,d,t)
    tag(d,"THE MODEL",t,t0)
    k,dy=enter(t,ws("Glimmer")-0.16,0.34,20)
    if k>0.01:
        text(d,(CX+4,286+dy),"MUSE",m(52,"bold"),TH.pale,0.95*k,10,"lt")
        grad_text(ov,(CX,344+dy),"GLIMMER",f(112,"bold"),WHITE,TH.pale,k,"lt",-3)
    k1,dy1=panel(ov,d,(CX,486,RIGHT,600),t,ws("parameters,")-0.20)
    if k1>0.01:
        text(d,(CX+30,516+dy1),"~29.6B",f(44,"bold"),TH.accent,k1,0,"lt")
        text(d,(CX+30,566+dy1),"dense + ViT-G/14 vision tower",m(26),TH.muted,k1,0,"lt")
    k2=eo3(lin(t,ws("Meta",0)-0.12,ws("Meta",0)+0.30))
    if k2>0.01:
        text(d,(CX,646),"META SUPERINTELLIGENCE LAB",f(34,"bold"),TH.support,k2,4,"lt")
    chip(ov,d,(CX,708,CX+286,782),"APACHE-2.0",t,ws("Apache")-0.14,fs=32)
    k3=eo3(lin(t,ws("Apache")+0.30,ws("Apache")+0.70))
    if k3>0.01:
        text(d,(CX+310,745),"not the Llama licence",m(27),TH.dim,k3,0,"lm")

# ---------------- 3. in, out, and where ----------------
def s_inout(ov,d,t,t0):
    rail(ov,d,t)
    tag(d,"IN AND OUT",t,t0)
    k,dy=enter(t,t0,0.32,18)
    if k>0.01:
        text(d,(CX,282+dy),"Text and images in.",f(58,"bold"),TH.muted,k,0,"lt")
    cw=(RIGHT-CX-16)/2
    chip(ov,d,(CX,374,CX+cw,452),"TEXT",t,ws("Text")-0.14,fs=30)
    chip(ov,d,(CX+cw+16,374,RIGHT,452),"IMAGE",t,ws("images")-0.14,
         col=TH.support,fs=30)
    k2=eo3(lin(t,ws("in,")-0.05,ws("in,")+0.34))
    if k2>0.01:
        text(d,(CX,492),"→  text out  ·  4,096 visual tokens per image",
             fitm("→  text out  ·  4,096 visual tokens per image",(28,26,24,22)),
             TH.dim,k2,0,"lt")
    # "machine." is its own 0.6s phrase -- give it the hard beat of the scene
    kb=eob(lin(t,ws("machine.")-0.18,ws("machine.")+0.42),1.9)
    km,dym=panel(ov,d,(CX,566,RIGHT,712),t,ws("machine.")-0.18,fa=0.94)
    if km>0.01:
        grad_text(ov,(CX+30,596+dym),"ON YOUR OWN MACHINE",
                  f(int(46*(0.94+0.06*kb)),"bold"),WHITE,TH.pale,km,"lt",1)
        text(d,(CX+30,664+dym),"no cloud in the loop",m(28),TH.muted,km,0,"lt")

# ---------------- 4. where the speed comes from ----------------
SPEEDUP=[("RTX 5090","74.9","233.4","3.1×",TH.accent),
         ("M5 Max","26.6","50.2","1.8×",TH.support),
         ("M4 Max","23.7","37.8","1.5×",TH.support)]
def s_speed(ov,d,t,t0):
    rail(ov,d,t)
    tag(d,"SPECULATIVE DECODING",t,t0)
    k,dy=enter(t,ws("speed")-0.14,0.32,18)
    if k>0.01:
        fo=f(62,"bold")
        text(d,(CX,278+dy),"DFlash.",fo,WHITE,k,0,"lt")
        text(d,(CX+tw("DFlash.",fo)+30,300+dy),"a drafter that guesses ahead",
             m(27),TH.muted,k,0,"lt")
    kd=eo3(lin(t,ws("drafter.")-0.30,ws("drafter.")+0.20))
    draft_verify(ov,d,368,t,ws("drafter.")-0.30,kd)
    for i,(dev,a,b,x,col) in enumerate(SPEEDUP):
        y0=512+i*94
        kk,dyk=panel(ov,d,(CX,y0,RIGHT,y0+80),t,ws("Three")+i*0.42,edge=col,dyv=0)
        if kk<=0.01: continue
        cy=y0+40+dyk
        text(d,(CX+28,cy),dev,f(30,"bold"),WHITE,kk,1,"lm")
        text(d,(CX+250,cy),f"{a}  →  {b}",m(28),TH.muted,kk,0,"lm")
        text(d,(RIGHT-28,cy),x,m(34,"bold"),col,kk,0,"rm")
    k2=eo3(lin(t,ws("twenty-four")-0.14,ws("twenty-four")+0.30))
    if k2>0.01:
        text(d,(CX,806),"4-bit builds target 24GB and 32GB cards",
             fitm("4-bit builds target 24GB and 32GB cards",(28,26,24)),TH.accent_hi,k2,0,"lt")
    k3=eo3(lin(t,ws("quantized.")-0.10,ws("quantized.")+0.34))
    if k3>0.01:
        text(d,(CX,856),"K-Quant-17GB · GGUF · llama.cpp · Ollama · LM Studio",
             fitm("K-Quant-17GB · GGUF · llama.cpp · Ollama · LM Studio",(26,24,22,20)),
             TH.dim,k3,0,"lt")

# ---------------- 5. the scores ----------------
def s_scores(ov,d,t,t0):
    rail(ov,d,t)
    tag(d,"ON THE MODEL CARD",t,t0)
    bar_row(ov,d,300,"AIME 2026","competition maths","94.7",t,B(11)-0.14)
    bar_row(ov,d,442,"SWE-bench Verified","real GitHub issues","76.0",t,B(12)-0.14)
    bar_row(ov,d,584,"GPQA Diamond","graduate science","83.5",t,B(13)-0.14)
    k=eo3(lin(t,ws("Verified.")+0.40,ws("Verified.")+0.80))
    if k>0.01:
        nt="card compares against Gemma4-31B and Qwen3.6-27B, both thinking"
        text(d,(CX,742),nt,fitm(nt,(26,24,22,20)),TH.dim,k,0,"lt")
    k2=eo3(lin(t,ws("Diamond.")+0.24,ws("Diamond.")+0.64))
    if k2>0.01:
        text(d,(CX,790),"Meta's own reported figures",
             fitm("Meta's own reported figures"),TH.muted,k2,0,"lt")

# ---------------- 6. the honest close ----------------
def s_close(ov,d,t,t0):
    rail(ov,d,t)
    tag(d,"META'S OWN WORDS",t,t0,col=TH.support)
    k,dy=enter(t,ws("plainly.")-0.20,0.32,18)
    if k>0.01:
        text(d,(CX,278+dy),"Meta says it plainly.",f(56,"bold"),TH.muted,k,0,"lt")
    kq,dyq=panel(ov,d,(CX,352,RIGHT,530),t,ws("frontier")-0.20,edge=TH.support,fa=0.94)
    if kq>0.01:
        yy=352+dyq
        text(d,(CX+30,yy+34),"PREPAREDNESS DESIGNATION",f(24,"bold"),TH.dim,kq,4,"lt")
        q1="\"does not fall under the definition"
        q2="of 'Frontier AI'\""
        text(d,(CX+30,yy+80),q1,fitm(q1,(30,28,26),wide=RIGHT-CX-60),WHITE,kq,0,"lt")
        text(d,(CX+30,yy+124),q2,fitm(q2,(30,28,26),wide=RIGHT-CX-60),WHITE,kq,0,"lt")
    k2=eo3(lin(t,ws("distilled")-0.14,ws("distilled")+0.32))
    if k2>0.01:
        text(d,(CX,568),"moderate-or-lower risk · distilled from Muse Spark",
             fitm("moderate-or-lower risk · distilled from Muse Spark",(26,24,22)),
             TH.muted,k2,0,"lt")
    kc,dyc=panel(ov,d,(CX,630,RIGHT,738),t,ws("run.")-0.34)
    if kc>0.01:
        cmd='vllm serve "meta-models/Muse-Glimmer-30B"'
        cy=630+dyc+54
        text(d,(CX+28,cy),"›",m(32,"bold"),TH.accent,kc,0,"lm")
        text(d,(CX+64,cy),cmd,fitm(cmd,(28,26,24,22),wide=RIGHT-CX-110),WHITE,kc,0,"lm")

# ---------------- 7. end card ----------------
def s_end(ov,d,t,t0):
    rail(ov,d,t)
    k=eo3(lin(t,t0,t0+0.34)); kb=eob(lin(t,t0,t0+0.55),1.4)
    put_glow(ov,588,560,TH.glow,780,0.30*k+0.04*pulse(t,2.5))
    grad_text(ov,(588,548),"MUSE GLIMMER",f(int(84*(0.94+0.06*kb)),"bold"),
              WHITE,TH.pale,k,"mm",1)
    text(d,(588,640),"30B · text + image · Apache-2.0",m(30),TH.muted,k,2,"mm")
    k2=eo3(lin(t,t0+0.22,t0+0.56))
    hline(d,588-int(150*k2),588+int(150*k2),716,TH.accent,0.9*k2,4)
    text(d,(588,776),"huggingface.co",m(38,"bold"),WHITE,k2,0,"mt")
    text(d,(588,830),"/meta-models/Muse-Glimmer-30B",m(28),TH.accent,k2,0,"mt")
    k3=eo3(lin(t,t0+0.44,t0+0.80))
    if k3>0.01:
        lab="SAVE THIS FOR LATER"; fo=f(35,"bold"); wd=tw(lab,fo,4)+72
        d.rounded_rectangle((int(588-wd/2),960,int(588+wd/2),1042),radius=8,
                            fill=rgba(TH.accent,0.94*k3))
        text(d,(588,1002),lab,fo,(8,12,6),k3,4,"mm")
        put_glow(ov,588,1001,TH.glow,320,0.16*k3)
    k4=eo3(lin(t,t0+0.70,t0+1.05))
    if k4>0.01:
        lab="WATCH AGAIN"; fl=f(28,"bold"); wd=tw(lab,fl,5)
        text(d,(588-wd/2-38,1120),"↻",m(30),TH.dim,k4,0,"lm")
        text(d,(588+18,1120),lab,fl,TH.dim,k4,5,"mm")

# ---------------- dispatch ----------------
def frame(t):
    base=BASE.copy()
    ov=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(ov)
    n,a,b=scene_at(t)
    {"hook":s_hook,"name":s_name,"inout":s_inout,"speed":s_speed,
     "scores":s_scores,"close":s_close,"end":s_end}.get(n,lambda *_:None)(ov,d,t,a)
    S.chrome(base,d,t,TH,TOTAL,SLUG)
    S.cut_sweep(ov,d,t,CUTS,TH)
    if n!="end": S.captions(ov,d,t,CH,TH)
    base.alpha_composite(ov)
    return base

# ---------------- sound design ----------------
SFX=(
 [{"t":c-0.28,"kind":"swish","amp":0.14} for c in CUTS] +
 [{"t":c,"kind":"thump","amp":0.20,"dur":0.34,"freq":58.0} for c in CUTS] +
 [{"t":ws("Three")+i*0.42,"kind":"tick","amp":0.075,"tone":2600.0+i*220}
    for i in range(3)] +
 [{"t":B(i)-0.14,"kind":"tick","amp":0.085,"tone":2800.0} for i in (11,12,13)] +
 [{"t":ws("consumer")-0.12,"kind":"tick","amp":0.08,"tone":3000.0},
  {"t":ws("Glimmer")-0.16,"kind":"thump","amp":0.18,"dur":0.34,"freq":60.0},
  {"t":ws("Apache")-0.14,"kind":"tick","amp":0.075,"tone":2400.0},
  {"t":ws("machine.")-0.18,"kind":"thump","amp":0.28,"dur":0.50,"freq":47.0},
  {"t":ws("machine.")-0.18,"kind":"swish","amp":0.16},
  {"t":ws("drafter.")-0.30,"kind":"tick","amp":0.07,"tone":2200.0},
  {"t":ws("twenty-four")-0.14,"kind":"tick","amp":0.07,"tone":3200.0},
  {"t":ws("frontier")-0.20,"kind":"thump","amp":0.22,"dur":0.42,"freq":50.0},
  {"t":ws("run.")-0.34,"kind":"tick","amp":0.08,"tone":3000.0},
  {"t":SC[-1][1],"kind":"sweep","amp":0.10}]
)
