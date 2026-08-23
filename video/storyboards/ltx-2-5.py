# ---------------------------------------------------------------
# ltx-2-5.py -- LTX-2.5. Video-signal cyan, magenta audio.
#
# Second model release, so it keeps the rail/square-panel language of
# qwen3-8-27b, but the rail is a FILMSTRIP of shot cells rather than layers:
# it starts as one uncut strip with no sound, gains its first cut on the word
# "cut", and ends fully cut with a magenta waveform running the whole height.
# The other recurring device is the denoise strip -- eight tiles resolving from
# noise into a frame -- which is the generation act itself, and pays off the
# "eight steps at guidance one" line.
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

# Burned-in captions removed on request. The repo's retention notes argue for
# them (most Reels views start muted), so this is kept as a one-line switch
# rather than a deletion -- flip to True and rebuild to get them back.
CAPTIONS = False

NAME    = "ltx-2-5"
AUDIO   = "ltx-2-5-reel.mp3"       # the recording arrived under this name
PHRASES = "phrases/ltx-2-5.txt"
FPS     = 30

_T=Timing(NAME); WORDS=_T.words
ws,we = _T.ws, _T.we
CH=_T.chunks()
SEG=_T.segments
def B(i): return SEG[i][0]

# whole number of frames, or the nb_frames assert in make.sh trips (gotcha 8)
TOTAL = int(round((SEG[-1][1]+2.95)*FPS))/FPS

TH=Theme(bg=(8,10,20),accent=(0,208,255),accent_hi=(150,238,255),
         pale=(214,246,255),glow=(0,84,150),support=(255,74,180),
         cardc=(15,20,32),border=(38,54,76))
TH.apply()

RX,RW,CX = 84,52,180
RIGHT    = W-MARGIN

def build_ground():
    a=np.zeros((H,W,3),np.float32); a[:,:]=TH.bg
    for cx,cy,rad,col,st,pw in [(140,560,1220,TH.glow,0.40,2.2),
                                (1000,1620,940,TH.support,0.06,2.6),
                                (560,900,1400,(20,26,40),0.22,1.6)]:
        a+=radial(W,H,cx,cy,rad,pw)[:,:,None]*np.array(col,np.float32)*st
    a*=np.linspace(1.0,0.74,H,dtype=np.float32)[:,None,None]
    rng=np.random.RandomState(11)
    a+=rng.normal(0,2.1,(H,W,1)).astype(np.float32)   # keep the grain: it is
    a+=rng.normal(0,0.9,(H,W,3)).astype(np.float32)   # what stops banding
    return Image.fromarray(np.clip(a,0,255).astype(np.uint8),"RGB").convert("RGBA")
BASE=build_ground()

# 17 phrases: 0-2 hook, 3-5 the model, 6-8 the three parts, 9-10 the cut,
# 11-13 how you run it, 14-16 the licence
SC=[("hook"   ,0.0    ,B(3)),
    ("dit"    ,B(3)   ,B(6)),
    ("vaes"   ,B(6)   ,B(9)),
    ("cut"    ,B(9)   ,B(11)),
    ("run"    ,B(11)  ,B(14)),
    ("licence",B(14)  ,SEG[-1][1]+0.55),
    ("end"    ,SEG[-1][1]+0.55,TOTAL)]
def scene_at(t):
    for n,a,b in SC:
        if a<=t<b: return n,a,b
    return SC[-1]
CUTS=[a for _,a,_ in SC[1:]]

# ---------------- the design system ----------------
_WAVE=np.array([math.sin(i*0.055)*0.55+math.sin(i*0.171)*0.30+math.sin(i*0.41)*0.15
                for i in range(2400)],np.float32)

def rail(ov,d,t,ncuts=0,wave=0.0,full=0.0):
    """the spine as a filmstrip. ncuts marks 0-3 shot boundaries; wave fades in
    the magenta audio track beside it -- one clock for picture and sound."""
    y0,y1,n=150,1380,32
    put_glow(ov,RX+RW/2,660,TH.glow,540,0.14+0.04*pulse(t,5.0))
    pitch=(y1-y0)/n; ch=pitch*0.72
    cut_at=(8,16,24)[:max(0,min(3,int(ncuts)))]
    for i in range(n):
        yy=y0+i*pitch; shot=sum(1 for c in cut_at if i>=c)
        a=0.26+0.06*(shot%2)+0.40*full
        d.rounded_rectangle([int(v) for v in (RX,yy,RX+RW,yy+ch)],radius=3,
            fill=rgba(TH.accent,0.05+0.03*(shot%2)+0.45*full),
            outline=rgba(TH.accent,a),width=1)
        for sx in (RX+7,RX+RW-13):                      # sprocket holes
            d.rectangle([int(v) for v in (sx,yy+ch*0.34,sx+6,yy+ch*0.66)],
                        fill=rgba(TH.accent,0.28+0.35*full))
    for c in cut_at:
        yy=int(y0+c*pitch-pitch*0.16)
        # starts at RX, not RX-2: RX is the x=84 safe boundary
        d.rectangle((RX,yy,RX+RW+6,yy+4),fill=rgba(TH.accent_hi,0.95))
    if wave>0.01:
        pts=[(RX+RW+22+_WAVE[i]*15*wave, y0+i) for i in range(int(y1-y0))]
        d.line(pts,fill=rgba(TH.support,0.60*wave),width=2)

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
    assert CX+wd+58 < 740, f"tag {txt!r} is too wide -- it will hit the chrome slug"
    d.rounded_rectangle((CX,y-26,CX+wd+58,y+26),radius=6,outline=rgba(col,0.85*k),width=2)
    d.ellipse((CX+20,y-6,CX+32,y+6),fill=rgba(col,k))
    text(d,(CX+46,y),txt,fo,col,k,6,"lm")

def fitm(txt,sizes=(30,28,26,24,22),wide=None):
    lim=wide or (RIGHT-CX)
    fo=next((m(z) for z in sizes if tw(txt,m(z))<=lim),m(sizes[-1]))
    assert tw(txt,fo)<=lim+1, f"{txt!r} does not fit the safe area at any size"
    return fo

def wave_h(d,box,a,ph=0.0,col=None):
    """a horizontal audio track"""
    x0,y0,x1,y1=box; cy=(y0+y1)/2; amp=(y1-y0)/2
    n=int(x1-x0)
    if n<4 or a<=0.01: return
    pts=[(x0+i, cy+_WAVE[(i+int(ph))%2400]*amp) for i in range(n)]
    d.line(pts,fill=rgba(col or TH.support,0.85*a),width=3)

def shotcell(ov,d,box,t,t0,label,sub=None,lit=1.0,k=None,var=0):
    """a frame of picture: the recurring unit of this video. `var` rolls the
    plate so three shots read as three different framings of one scene."""
    if k is None: k,dy=enter(t,t0,0.30,18)
    else: dy=0.0
    if k<=0.01: return 0.0
    x0,y0,x1,y1=box; y0+=dy; y1+=dy
    card(d,(x0,y0,x1,y1),8,(12,17,28),0.92*k,mix(TH.border,TH.accent,lit),
         (0.6+0.35*lit)*k,2)
    iw,ih=int(x1-x0)-6,int(y1-y0)-6
    if iw>8 and ih>8:
        tile=_plate_rgba(iw,ih,var).copy()            # native size, not upscaled
        tile.putalpha(int(255*(0.30+0.34*lit)*k))     # composite, never d.*
        ov.alpha_composite(tile,(int(x0)+3,int(y0)+3))
    put_glow(ov,(x0+x1)/2,(y0+y1)/2,TH.glow,int((x1-x0)*0.8),0.10*lit*k)
    text(d,(x0+18,y0+16),label,m(22,"bold"),TH.accent_hi,0.95*k,1,"lt")
    if sub: text(d,((x0+x1)/2,(y0+y1)/2+10),sub,f(30,"bold"),TH.muted,k,2,"mm")
    return k

# eight stable noise fields -- fixed seed so the strip reads as denoising
# rather than as television static, and so chunked renders stay identical
_NT_W,_NT_H=88,120
_NOISE=np.random.RandomState(5).rand(8,_NT_H,_NT_W,1).astype(np.float32)*255.0
def _plate(w,h):
    """the picture the strip is resolving towards"""
    img=np.zeros((h,w,3),np.float32)
    hz=int(h*0.62)
    img[:hz]=np.array(TH.glow,np.float32)*1.25
    img[hz:]=np.array((12,17,28),np.float32)
    yy,xx=np.mgrid[0:h,0:w]
    cy,cx,r=int(h*0.40),int(w*0.52),int(h*0.18)
    img[((xx-cx)**2+(yy-cy)**2)<r*r]=np.array(TH.accent,np.float32)*0.88
    return img
_PLATE=_plate(_NT_W,_NT_H)

_PCACHE={}
def _plate_rgba(w,h,var=0):
    """the plate at its final size -- generated, not upscaled, so a shot cell
    reads as a frame rather than a blurred thumbnail. Cached per (w,h,var)."""
    key=(w,h,var)
    if key not in _PCACHE:
        pl=np.roll(_plate(w,h),int(var*w*0.31),axis=1)
        _PCACHE[key]=Image.fromarray(np.clip(pl,0,255).astype(np.uint8),
                                     "RGB").convert("RGBA")
    return _PCACHE[key]

def denoise_strip(ov,d,box,p,t):
    """eight steps, noise -> frame. p in 0..1 sweeps the resolve left to right."""
    x0,y0,x1,y1=box; n=8; gap=8
    twd=((x1-x0)-gap*(n-1))/n
    for i in range(n):
        bx=x0+i*(twd+gap)
        reveal=clamp(p*n-i)                       # this tile's own progress
        if reveal<=0.01: continue
        lvl=(1.0-i/(n-1))                          # its target noise level
        lvl=1.0-(1.0-lvl)*eo3(reveal)              # ...eased in
        img=_PLATE*(1-lvl)+_NOISE[i]*lvl
        tile=Image.fromarray(np.clip(img,0,255).astype(np.uint8),"RGB").convert("RGBA")
        tile=tile.resize((int(twd),int(y1-y0)))
        tile.putalpha(int(235*clamp(reveal*2)))
        ov.alpha_composite(tile,(int(bx),int(y0)))
        d.rounded_rectangle((int(bx),int(y0),int(bx+twd),int(y1)),radius=4,
            outline=rgba(TH.accent,(0.90 if i==n-1 else 0.26)*clamp(reveal*2)),width=2)
        text(d,(bx+twd/2,y1+14),str(i+1),m(19,"bold"),
             TH.accent if i==n-1 else TH.dim,0.9*clamp(reveal*2),0,"mt")

def chip(ov,d,box,label,t,t0,col=None,mono=True):
    k,dy=enter(t,t0,0.28,16)
    if k<=0.01: return
    x0,y0,x1,y1=box; y0+=dy; y1+=dy
    col=col or TH.accent
    d.rounded_rectangle((int(x0),int(y0),int(x1),int(y1)),radius=6,
        fill=rgba(col,0.12*k),outline=rgba(col,0.85*k),width=2)
    fo=(m if mono else f)(28,"bold")
    text(d,((x0+x1)/2,(y0+y1)/2),label,fo,col,k,1,"mm")

def lockrow(ov,d,y0,label,t,t0,h=68):
    """one of the four things held across the cuts"""
    k,dy=enter(t,t0,0.30,14)
    if k<=0.01: return
    yy=y0+dy
    d.rounded_rectangle((int(CX),int(yy),int(RIGHT),int(yy+h)),radius=6,
        fill=rgba(TH.accent,0.09*k),outline=rgba(TH.accent,0.60*k),width=2)
    text(d,(CX+26,yy+h/2),label,f(34,"bold"),WHITE,k,3,"lm")
    kb=eob(lin(t,t0,t0+0.46),2.0)
    text(d,(RIGHT-30,yy+h/2),"HELD",m(int(26*(0.9+0.1*kb)),"bold"),
         TH.accent_hi,k,2,"rm")

# ---------------- 1. the hook ----------------
def s_hook(ov,d,t,t0):
    tc=ws("cut.")
    kcut=eo3(lin(t,tc-0.12,tc+0.34))
    rail(ov,d,t,ncuts=1 if t>=tc-0.12 else 0,wave=kcut)
    tag(d,"AUDIO + VIDEO MODEL",t,-0.40)

    # legible at frame 0: no fade up, no logo intro
    text(d,(CX,286),"Most open video models",f(64,"bold"),TH.muted,1.0,0,"lt")
    text(d,(CX,362),"give you one shot.",f(64,"bold"),WHITE,1.0,0,"lt")

    # one lonely silent frame, which then splits on the word "cut"
    if kcut<0.02:
        shotcell(ov,d,(CX,470,RIGHT,742),t,0.0,"SHOT 1",k=1.0,lit=0.5,var=0)
        text(d,(RIGHT-22,716),"NO AUDIO",m(24,"bold"),TH.dim,1.0,2,"rb")
    else:
        gapx=10; midp=CX+(RIGHT-CX)/2
        shotcell(ov,d,(CX,470,midp-gapx,742),t,0.0,"SHOT 1",k=1.0,lit=1.0,var=0)
        shotcell(ov,d,(midp+gapx,470,RIGHT,742),t,0.0,"SHOT 2",k=kcut,lit=1.0,var=1)
        d.rectangle((int(midp-4),int(470),int(midp+4),int(742)),
                    fill=rgba(TH.accent_hi,0.95*kcut))
        wave_h(d,(CX,776,RIGHT,836),kcut)
        text(d,(CX,862),"one cut · one waveform · one pass",
             fitm("one cut · one waveform · one pass"),TH.support,kcut,0,"lt")

    k2,dy2=enter(t,ws("LTX")-0.12,0.34,20)
    if k2>0.01:
        grad_text(ov,(CX,936+dy2),"LTX-2.5",m(96,"bold"),WHITE,TH.pale,k2,"lt",4)

# ---------------- 2. one model ----------------
def s_dit(ov,d,t,t0):
    rail(ov,d,t,ncuts=1,wave=1.0)
    tag(d,"ONE MODEL",t,t0)
    k,dy=enter(t,ws("Twenty-two")-0.14,0.34,20)
    if k>0.01:
        grad_text(ov,(CX,282+dy),"22B",f(132,"bold"),WHITE,TH.pale,k,"lt",-4)
        text(d,(CX+322,318+dy),"DiT",m(52,"bold"),TH.accent,k,4,"lt")
        text(d,(CX+322,388+dy),"one transformer",m(26),TH.dim,k,0,"lt")

    kb,dyb=panel(ov,d,(CX,470,RIGHT,584),t,ws("diffusion")-0.16)
    if kb>0.01:
        text(d,(CX+30,527+dyb),"DIFFUSION TRANSFORMER",f(40,"bold"),WHITE,kb,2,"lm")

    # two lanes leaving the same block, locked to the same clock
    for i,(lab,col,cue) in enumerate([("VIDEO",TH.accent,ws("generating")-0.14),
                                      ("AUDIO",TH.support,ws("generating")+0.16)]):
        y0=634+i*112
        kk,dyk=panel(ov,d,(CX,y0,RIGHT,y0+92),t,cue,edge=col,dyv=0)
        if kk<=0.01: continue
        cy=y0+46+dyk
        text(d,(CX+28,cy),lab,f(34,"bold"),col,kk,3,"lm")
        if i==0:
            for j in range(5):
                bx=CX+150+j*74
                d.rounded_rectangle((int(bx),int(cy-26),int(bx+62),int(cy+26)),
                                    radius=4,fill=rgba(col,0.16*kk),
                                    outline=rgba(col,0.55*kk),width=2)
        else:
            wave_h(d,(CX+150,cy-26,RIGHT-30,cy+26),kk,ph=40,col=col)

    k3=eo3(lin(t,ws("together.")-0.12,ws("together.")+0.34))
    if k3>0.01:
        text(d,(CX,890),"generated together, in the same pass",
             fitm("generated together, in the same pass"),TH.accent_hi,k3,0,"lt")

# ---------------- 3. the three parts ----------------
PARTS=[("VIDEO VAE","frames out",6),
       ("AUDIO VAE","sound out",7),
       ("VOCODER","waveform out",8)]
def s_vaes(ov,d,t,t0):
    rail(ov,d,t,ncuts=1,wave=1.0)
    tag(d,"WHAT IS INSIDE",t,t0)
    k,dy=enter(t,t0,0.32,18)
    if k>0.01:
        text(d,(CX,282+dy),"Three parts, one",f(62,"bold"),TH.muted,k,0,"lt")
        text(d,(CX,356+dy),"checkpoint.",f(62,"bold"),WHITE,k,0,"lt")
    for i,(lab,sub,seg) in enumerate(PARTS):
        y0=452+i*152
        col=TH.accent if i==0 else TH.support
        kk,dyk=panel(ov,d,(CX,y0,RIGHT,y0+124),t,B(seg)-0.10,edge=col)
        if kk<=0.01: continue
        text(d,(CX+32,y0+40+dyk),lab,f(40,"bold"),WHITE,kk,1,"lt")
        text(d,(CX+32,y0+92+dyk),sub,m(26),TH.dim,kk,0,"lt")
        if i==2: wave_h(d,(RIGHT-260,y0+42+dyk,RIGHT-32,y0+96+dyk),kk,ph=90)
        else:    text(d,(RIGHT-32,y0+62+dyk),("▦" if i==0 else "♪"),
                      m(54,"bold"),col,0.85*kk,0,"rm")
    k2=eo3(lin(t,ws("vocoder")+0.30,ws("vocoder")+0.70))
    if k2>0.01:
        text(d,(CX,932),"text encoder: Gemma 4 · 12B",
             fitm("text encoder: Gemma 4 · 12B"),TH.dim,k2,0,"lt")

# ---------------- 4. the cut ----------------
LOCKS=[("CHARACTER IDENTITY","identity,"),("LIGHTING","lighting,"),
       ("VOICE","voice,"),("VISUAL STYLE","visual")]
def s_cut(ov,d,t,t0):
    n=1+int(t>=ws("single")-0.10)+int(t>=ws("pass.")-0.10)
    rail(ov,d,t,ncuts=n,wave=1.0)
    tag(d,"THE ONE THAT MATTERS",t,t0)
    k,dy=enter(t,ws("cuts")-0.16,0.32,20)
    if k>0.01:
        text(d,(CX,278+dy),"It cuts in a",f(62,"bold"),TH.muted,k,0,"lt")
        text(d,(CX,352+dy),"single pass.",f(62,"bold"),WHITE,k,0,"lt")

    # three shots, hard cuts between them
    gapx=12; wq=((RIGHT-CX)-2*gapx)/3
    for i in range(3):
        bx=CX+i*(wq+gapx)
        cue=[ws("cuts")-0.10,ws("single")-0.10,ws("pass.")-0.10][i]
        kk=shotcell(ov,d,(bx,436,bx+wq,592),t,cue,f"SHOT {i+1}",var=i)
        if i and kk>0.01:
            d.rectangle((int(bx-gapx/2-3),436,int(bx-gapx/2+3),592),
                        fill=rgba(TH.accent_hi,0.90*kk))
    for i,(lab,cue) in enumerate(LOCKS):
        lockrow(ov,d,634+i*80,lab,t,ws(cue)-0.14)
    k2=eo3(lin(t,ws("visual")+0.55,ws("visual")+0.95))
    if k2>0.01:
        text(d,(CX,972),"one pass · not three generations stitched",
             fitm("one pass · not three generations stitched"),TH.accent_hi,k2,0,"lt")

# ---------------- 5. how you run it ----------------
def s_run(ov,d,t,t0):
    rail(ov,d,t,ncuts=3,wave=1.0)
    tag(d,"HOW YOU RUN IT",t,t0)
    k,dy=enter(t,ws("distilled")-0.16,0.32,20)
    if k>0.01:
        text(d,(CX,278+dy),"The distilled build.",f(62,"bold"),WHITE,k,0,"lt")
    denoise_strip(ov,d,(CX,376,RIGHT,520),
                  lin(t,ws("distilled")+0.05,ws("steps")+0.55),t)
    k1=eo3(lin(t,ws("guidance")-0.12,ws("guidance")+0.34))
    if k1>0.01:
        text(d,(CX,584),"8 STEPS · CFG 1",m(52,"bold"),TH.accent_hi,k1,3,"lt")
    cw=((RIGHT-CX)-2*14)/3
    for i,(lab,cue) in enumerate([("BF16",B(12)-0.10),("INT8",B(12)+0.30),
                                  ("NVFP4",ws("NVFP")-0.10)]):
        bx=CX+i*(cw+14)
        chip(ov,d,(bx,668,bx+cw,742),lab,t,cue)
    cw2=((RIGHT-CX)-14)/2
    for i,(lab,cue) in enumerate([("ComfyUI",ws("ComfyUI")-0.14),
                                  ("diffusers",ws("diffusers.")-0.14)]):
        bx=CX+i*(cw2+14)
        chip(ov,d,(bx,772,bx+cw2,846),lab,t,cue,col=TH.support)
    k3=eo3(lin(t,ws("diffusers.")+0.24,ws("diffusers.")+0.62))
    if k3>0.01:
        nt="544×960 · 121 frames · 24 fps — the card's example"
        text(d,(CX,898),nt,fitm(nt,(26,24,22,20)),TH.dim,k3,0,"lt")

# ---------------- 6. the licence ----------------
def s_licence(ov,d,t,t0):
    rail(ov,d,t,ncuts=3,wave=1.0)
    tag(d,"THE CATCH",t,t0,col=TH.support)
    k,dy=enter(t,ws("Apache")-0.14,0.32,18)
    if k>0.01:
        text(d,(CX,278+dy),"APACHE-2.0",f(78,"bold"),TH.dim,k,0,"lt")
        ks=eo3(lin(t,ws("Apache")+0.22,ws("Apache")+0.62))
        if ks>0.01:
            wd=tw("APACHE-2.0",f(78,"bold"))
            d.rectangle((int(CX),int(320+dy),int(CX+wd*ks),int(328+dy)),
                        fill=rgba(TH.support,0.95))
    k1,dy1=enter(t,B(15)-0.10,0.34,20)
    if k1>0.01:
        text(d,(CX,392+dy1),"LTX-2.x",m(58,"bold"),WHITE,k1,4,"lt")
        text(d,(CX,462+dy1),"COMMUNITY LICENCE",m(44,"bold"),TH.accent,k1,3,"lt")

    # the threshold, both sides of it -- the number is the point
    rows=[("under $10M revenue","commercial use, no cost",TH.accent,ws("ten")-0.14),
          ("$10M and above","paid agreement",TH.support,ws("revenue.")-0.30)]
    for i,(l,r,col,cue) in enumerate(rows):
        y0=576+i*136
        kk,dyk=panel(ov,d,(CX,y0,RIGHT,y0+112),t,cue,edge=col)
        if kk<=0.01: continue
        text(d,(CX+30,y0+38+dyk),l,m(30,"bold"),col,kk,0,"lt")
        text(d,(CX+30,y0+76+dyk),r,f(30,"bold"),WHITE,kk,0,"lt")
    k3=eo3(lin(t,B(16)+0.55,B(16)+0.95))
    if k3>0.01:
        nt="gated repo · accept the licence, then it pulls"
        text(d,(CX,868),nt,fitm(nt,(28,26,24,22)),TH.dim,k3,0,"lt")

# ---------------- 7. end card ----------------
def s_end(ov,d,t,t0):
    rail(ov,d,t,ncuts=3,wave=1.0,full=eo3(lin(t,t0,t0+0.55)))
    k=eo3(lin(t,t0,t0+0.34)); kb=eob(lin(t,t0,t0+0.55),1.4)
    put_glow(ov,588,560,TH.glow,780,0.30*k+0.04*pulse(t,2.5))
    grad_text(ov,(588,556),"LTX-2.5",m(int(120*(0.94+0.06*kb)),"bold"),
              WHITE,TH.pale,k,"mm",5)
    text(d,(588,676),"22B · audio + video · multishot",m(30),TH.muted,k,2,"mm")
    k2=eo3(lin(t,t0+0.22,t0+0.56))
    hline(d,588-int(150*k2),588+int(150*k2),742,TH.accent,0.9*k2,4)
    text(d,(588,802),"huggingface.co",m(38,"bold"),WHITE,k2,0,"mt")
    text(d,(588,856),"/Lightricks/LTX-2.5",m(34),TH.accent,k2,0,"mt")
    k3=eo3(lin(t,t0+0.44,t0+0.80))
    if k3>0.01:
        lab="SAVE THIS FOR LATER"; fo=f(35,"bold"); wd=tw(lab,fo,4)+72
        d.rounded_rectangle((int(588-wd/2),986,int(588+wd/2),1068),radius=8,
                            fill=rgba(TH.accent,0.94*k3))
        text(d,(588,1028),lab,fo,(6,10,16),k3,4,"mm")
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
    {"hook":s_hook,"dit":s_dit,"vaes":s_vaes,"cut":s_cut,
     "run":s_run,"licence":s_licence,"end":s_end}.get(n,lambda *_:None)(ov,d,t,a)
    S.chrome(base,d,t,TH,TOTAL,"Lightricks/LTX-2.5")
    S.cut_sweep(ov,d,t,CUTS,TH)
    if CAPTIONS and n!="end": S.captions(ov,d,t,CH,TH)
    base.alpha_composite(ov)
    return base

# ---------------- sound design ----------------
# subtle. The one hard beat is the cut itself.
SFX=(
 [{"t":c-0.28,"kind":"swish","amp":0.14} for c in CUTS] +
 [{"t":c,"kind":"thump","amp":0.20,"dur":0.34,"freq":58.0} for c in CUTS] +
 [{"t":ws(cue)-0.14,"kind":"tick","amp":0.075,"tone":2800.0} for _,cue in LOCKS] +
 [{"t":B(s)-0.10,"kind":"tick","amp":0.07,"tone":2500.0} for _,_,s in PARTS] +
 [{"t":ws("cut.")-0.12,"kind":"thump","amp":0.30,"dur":0.52,"freq":46.0},
  {"t":ws("cut.")-0.12,"kind":"swish","amp":0.18},
  {"t":ws("single")-0.10,"kind":"tick","amp":0.08,"tone":3000.0},
  {"t":ws("pass.")-0.10,"kind":"tick","amp":0.08,"tone":3000.0},
  {"t":ws("diffusion")-0.16,"kind":"tick","amp":0.08,"tone":2200.0},
  {"t":ws("guidance")-0.12,"kind":"thump","amp":0.16,"dur":0.30,"freq":62.0},
  {"t":ws("Apache")+0.22,"kind":"thump","amp":0.20,"dur":0.38,"freq":52.0},
  {"t":ws("ten")-0.14,"kind":"tick","amp":0.085,"tone":3200.0},
  {"t":SC[-1][1],"kind":"sweep","amp":0.10}]
)
