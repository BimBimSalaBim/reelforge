# ---------------------------------------------------------------
# sbkit.py -- shared storyboard machinery: theme, ground, chrome,
# captions, and the reusable card/terminal/counter components.
# A storyboard supplies a Theme and its scenes; everything else lives here.
# ---------------------------------------------------------------
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import kit
from kit import (W,H,FPS,MARGIN,CAP_Y,f,m,clamp,lin,eo3,eo4,eio,eob,pulse,
                 rgba,mix,tw,text,grad_text,wrap,radial,put_glow,card,pill,hline)

WHITE=(255,255,255)

class Theme:
    def __init__(self,bg,accent,accent_hi,pale,glow,support,
                 muted=(150,156,168),dim=(102,108,122),faint=(52,58,68),
                 cardc=(19,22,30),border=(43,50,62),
                 ok=(110,225,180),warn=(240,190,96),bad=(255,96,112)):
        self.bg=bg; self.accent=accent; self.accent_hi=accent_hi; self.pale=pale
        self.glow=glow; self.support=support; self.muted=muted; self.dim=dim
        self.faint=faint; self.card=cardc; self.border=border
        self.ok=ok; self.warn=warn; self.bad=bad
    def apply(self):
        """point kit's own defaults at this theme"""
        kit.set_palette(BG=self.bg,ORANGE=self.accent,ORANGE_HI=self.accent_hi,
                        CREAM=self.pale,MUTED=self.muted,DIM=self.dim,
                        FAINT=self.faint,CARD=self.card,BORDER=self.border,
                        GREEN=self.ok,AMBER=self.warn,RED=self.bad)

def build_base(th,seed=5,bloom=0.34):
    a=np.zeros((H,W,3),np.float32); a[:,:]=th.bg
    for cx,cy,rad,col,st,pw in [(200,300,1180,th.glow,bloom,2.3),
                                (960,1760,880,th.support,0.10,2.5),
                                (540,900,1420,(30,32,44),0.24,1.6)]:
        a+=radial(W,H,cx,cy,rad,pw)[:,:,None]*np.array(col,np.float32)*st
    a*=np.linspace(1.0,0.72,H,dtype=np.float32)[:,None,None]
    rng=np.random.RandomState(seed)
    a+=rng.normal(0,2.1,(H,W,1)).astype(np.float32)
    a+=rng.normal(0,0.9,(H,W,3)).astype(np.float32)
    return Image.fromarray(np.clip(a,0,255).astype(np.uint8),"RGB").convert("RGBA")

# ---- per-frame chrome -------------------------------------------------
def chrome(base,d,t,th,total,tag):
    d.rectangle((0,0,int(W*clamp(t/total)),5),fill=rgba(th.accent,0.55))
    text(d,(W-MARGIN,176),tag,m(25),(100,106,120),1.0,0,"rt")
    put_glow(base,170,270,th.glow,620,0.05+0.030*pulse(t,6.0))

def cut_sweep(ov,d,t,cuts,th):
    for c in cuts:
        k=lin(t,c,c+0.30)
        if 0<k<1:
            y=int(-40+k*(H+80))
            d.rectangle((0,y,W,y+3),fill=rgba(th.accent_hi,0.28*(1-k)))

def scrim(ov,a,col=(5,7,10)):
    """full-frame dim. MUST composite -- ImageDraw would erase the layer."""
    if a>0.01: ov.alpha_composite(Image.new("RGBA",(W,H),rgba(col,a)))

# ---- captions ---------------------------------------------------------
def captions(ov,d,t,chunks,th):
    cur=None; prev=None
    for c in chunks:
        if c["s"]-0.06<=t<=c["e"]+0.05: cur=c; break
        if c["e"]<t: prev=c
    a=1.0
    if cur is None:
        if prev is None: return
        if t-prev["e"]>0.85: return
        cur=prev; a=1.0-lin(t,prev["e"]+0.45,prev["e"]+0.85)
    fo=f(54,"bold"); wl=[x["w"] for x in cur["ws"]]
    sp=fo.getlength(" "); wid=[fo.getlength(x) for x in wl]
    total=sum(wid)+sp*(len(wl)-1); x=540-total/2
    pad=26; asc,_=fo.getmetrics()
    d.rounded_rectangle([int(v) for v in (x-pad,CAP_Y-asc*0.62-16,
                                          x+total+pad,CAP_Y+asc*0.42+16)],
        radius=20,fill=rgba((6,7,10),0.66*a),outline=rgba(WHITE,0.05*a),width=1)
    for wd,ww,wob in zip(wl,wid,cur["ws"]):
        live=wob["s"]-0.04<=t<=wob["e"]+0.04
        text(d,(x,CAP_Y),wd,fo,th.accent_hi if live else WHITE,a,0,"lm")
        if live:
            d.rectangle((int(x),int(CAP_Y+asc*0.40),int(x+ww),int(CAP_Y+asc*0.40)+4),
                        fill=rgba(th.accent_hi,0.75*a))
        x+=ww+sp

# ---- entrances -------------------------------------------------------
def enter(t,t0,dur=0.34,dy=32):
    k=eo3(lin(t,t0,t0+dur)); return k,(1-k)*dy
def eyebrow(ov,d,txt,t,t0,th,y=252,col=None):
    k=eo3(lin(t,t0,t0+0.34))
    if k>0.01: pill(d,540,y+(1-k)*-14,txt,f(31,"bold"),col or th.accent,k,track=6)

# ---- components ------------------------------------------------------
def statcard(ov,d,box,value,label,t,t0,th,count=None,vsize=76,lsize=26):
    """count: int target to tick up to; otherwise `value` is drawn as-is"""
    k,dy=enter(t,t0,0.32,26)
    if k<=0.01: return k
    x0,y0,x1,y1=box; y0+=dy; y1+=dy
    card(d,(x0,y0,x1,y1),24,th.card,0.92*k,th.border,0.92*k,2)
    put_glow(ov,(x0+x1)/2,(y0+y1)/2-14,th.glow,int((x1-x0)*0.72),0.14*k)
    if count is not None:
        p=eo4(lin(t,t0,t0+1.0)); n=int(round(count*p))
        s=f"{n:,}" if count>=1000 else str(n)
    else: s=value
    fo=f(vsize,"bold")
    while tw(s,fo)>(x1-x0)-40 and vsize>28:
        vsize-=4; fo=f(vsize,"bold")
    grad_text(ov,((x0+x1)/2,y0+34),s,fo,th.accent_hi,th.accent,k,"mt")
    text(d,((x0+x1)/2,y1-34),label,f(lsize,"bold"),th.muted,k,3,"mm")
    return k

def tile(ov,d,box,label,lit,th,k=1.0,sub=None,mono=False,glow=True):
    """a capability / plugin tile that lights up on cue"""
    if k<=0.01: return
    x0,y0,x1,y1=box
    col=mix(th.border,th.accent,lit)
    card(d,(x0,y0,x1,y1),20,th.card,(0.55+0.35*lit)*k,col,(0.55+0.40*lit)*k,2)
    if glow and lit>0.4: put_glow(ov,(x0+x1)/2,(y0+y1)/2,th.glow,int((x1-x0)*0.95),0.14*lit*k)
    fo=(m if mono else f)(34,"bold")
    cy=(y0+y1)/2 - (16 if sub else 0)
    text(d,((x0+x1)/2,cy),label,fo,mix((96,102,116),WHITE,lit),k,0 if mono else 1,"mm")
    if sub: text(d,((x0+x1)/2,cy+40),sub,m(24),th.dim,k*0.9,0,"mm")

def terminal(ov,d,box,lines,t,th,title="",fs=31,lead=52,foot=None,foot_t=None):
    """lines: [(text, t_start, t_end)] typed in; indented lines get no prompt"""
    x0,y0,x1,y1=box
    card(d,(x0,y0,x1,y1),24,(13,15,21),0.95,th.border,0.9,2)
    for i,c in enumerate([(255,95,86),(255,189,46),(39,201,63)]):
        d.ellipse((x0+30+i*30,y0+25,x0+44+i*30,y0+39),fill=rgba(c,0.5))
    if title: text(d,(x1-28,y0+32),title,m(24),th.dim,1.0,0,"rm")
    hline(d,x0,x1,y0+62,th.border,0.8,2)
    fo=m(fs); yy=y0+104
    for txt,a,b in lines:
        if t<a-0.02: break
        n=int(len(txt)*clamp((t-a)/max(b-a,0.05)))
        show=txt if t>=b else txt[:n]
        if not txt.startswith(" "):
            text(d,(x0+30,yy),"›",m(fs,"bold"),th.accent,1.0,0,"lt")
        text(d,(x0+58,yy),show,fo,WHITE,1.0,0,"lt")
        if t<b and int(t*8)%2==0:
            cx=x0+58+fo.getlength(show)
            d.rectangle((cx+2,yy+3,cx+15,yy+31),fill=rgba(th.accent_hi,0.85))
        yy+=lead
    if foot and foot_t is not None:
        k=eo3(lin(t,foot_t,foot_t+0.28))
        if k>0.01:
            text(d,(x0+30,y1-52),foot,m(26,"bold"),th.ok,k,0,"lm")

def counter(ov,d,xy,target,t,t0,th,dur=1.4,size=128,label=None,lsize=30):
    p=eo4(lin(t,t0,t0+dur))
    if p<=0.0: return
    x,y=xy
    put_glow(ov,x,y,th.glow,470,0.16*min(1,p*3))
    grad_text(ov,(x,y),f"{int(target*p):,}",f(size,"bold"),
              th.accent_hi,th.accent,min(1,p*4),"mm")
    if label:
        text(d,(x,y+size*0.66),label,f(lsize,"bold"),th.muted,min(1,p*4),5,"mm")

def bar(ov,d,box,frac,th,col=None,bg=(22,26,34),r=8):
    x0,y0,x1,y1=box
    d.rounded_rectangle((int(x0),int(y0),int(x1),int(y1)),radius=r,fill=rgba(bg,0.9))
    wq=(x1-x0)*clamp(frac)
    if wq>2:
        d.rounded_rectangle((int(x0),int(y0),int(x0+max(r*2,wq)),int(y1)),
                            radius=r,fill=rgba(col or th.accent,0.9))

def endcard(ov,d,t,t0,th,wordmark,sub,url,url2,cta,mark_size=250,mono_mark=False):
    k=eo3(lin(t,t0,t0+0.34)); kb=eob(lin(t,t0,t0+0.55),1.4)
    put_glow(ov,540,600,th.glow,820,0.30*k+0.04*pulse(t,2.5))
    fo=(m if mono_mark else f)(int(mark_size*(0.92+0.08*kb)),"bold")
    grad_text(ov,(540,596),wordmark,fo,WHITE,th.pale,k,"mm",6 if mono_mark else 0)
    text(d,(540,772),sub,m(38),th.muted,k,3,"mm")
    k2=eo3(lin(t,t0+0.22,t0+0.56))
    hline(d,540-int(140*k2),540+int(140*k2),846,th.accent,0.9*k2,4)
    text(d,(540,906),url,m(40,"bold"),WHITE,k2,0,"mt")
    if url2: text(d,(540,964),url2,m(34),th.accent,k2,0,"mt")
    k3=eo3(lin(t,t0+0.44,t0+0.80))
    if k3>0.01:
        fo2=f(35,"bold"); wd=tw(cta,fo2,4)+72; x0=540-wd/2
        d.rounded_rectangle((int(x0),1098,int(x0+wd),1180),radius=41,
                            fill=rgba(th.accent,0.94*k3))
        text(d,(540,1140),cta,fo2,(8,8,14),k3,4,"mm")
        put_glow(ov,540,1139,th.glow,320,0.16*k3)
    # The standing CTA for the account. It lands after the save prompt and is
    # also the last spoken line of every narration -- keep the two in step.
    k4=eo3(lin(t,t0+0.66,t0+1.00))
    if k4>0.01:
        put_glow(ov,540,1256,th.glow,420,0.13*k4)
        grad_text(ov,(540,1256),"Follow for more",f(46,"bold"),
                  WHITE,th.pale,k4,"mm",2)
    k5=eo3(lin(t,t0+0.88,t0+1.24))
    if k5>0.01:
        lab="WATCH AGAIN"; fl=f(28,"bold"); wd=tw(lab,fl,5)
        text(d,(540-wd/2-38,1350),"↻",m(30),th.dim,k5,0,"lm")
        text(d,(540+18,1350),lab,fl,th.dim,k5,5,"mm")
