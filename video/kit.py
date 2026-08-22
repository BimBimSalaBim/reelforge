# ---------------------------------------------------------------
# kit.py -- canvas, palette, fonts, easing, drawing primitives
# ---------------------------------------------------------------
import math, numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W,H,FPS = 1080,1920,30

# ---- safe zones (IG Reels + YT Shorts UI) ----
MARGIN   = 84
TOP_SAFE = 150
BOT_SAFE = 1600          # nothing meaningful below this
CAP_Y    = 1498          # caption band centre

# ---- palette (sampled from ECC-reel.png) ----
BG        = (10,8,9)
ORANGE    = (232,129,60)
ORANGE_HI = (255,154,77)
AMBER     = (232,163,61)
WHITE     = (255,255,255)
CREAM     = (246,201,160)
MUTED     = (154,154,162)
DIM       = (106,106,114)
FAINT     = (58,55,64)
CARD      = (23,21,26)
BORDER    = (44,42,50)
GREEN     = (123,216,143)
RED       = (255,92,92)
BLUE      = (140,168,255)

HN = "/System/Library/Fonts/HelveticaNeue.ttc"
MN = "/System/Library/Fonts/Menlo.ttc"
_fc={}
_WI={"reg":0,"bold":1,"cbold":4,"cblack":9,"med":10,"light":7,"thin":12,"ultra":5}
_MI={"reg":0,"bold":1}
def f(size, w="bold"):
    """display face; see set_fonts() to swap the family"""
    idx=_WI[w]; k=("hn",size,idx)
    if k not in _fc: _fc[k]=ImageFont.truetype(HN,size,index=idx)
    return _fc[k]
def m(size, w="reg"):
    """mono face -- also the only one here with check/arrow glyphs"""
    idx=_MI[w]; k=("mn",size,idx)
    if k not in _fc: _fc[k]=ImageFont.truetype(MN,size,index=idx)
    return _fc[k]

# ---- easing ----
def clamp(x,a=0.0,b=1.0): return a if x<a else b if x>b else x
def lin(t,a,b): return clamp((t-a)/(b-a)) if b>a else (1.0 if t>=b else 0.0)
def eo3(x): x=clamp(x); return 1-(1-x)**3
def eo4(x): x=clamp(x); return 1-(1-x)**4
def ei3(x): x=clamp(x); return x*x*x
def eio(x):
    x=clamp(x)
    return 4*x**3 if x<0.5 else 1-((-2*x+2)**3)/2
def eob(x,s=1.5):
    x=clamp(x); c=s+1
    return 1+c*(x-1)**3+s*(x-1)**2
def pulse(t,period=1.0): return 0.5+0.5*math.sin(t*2*math.pi/period)

def rgba(c,a): return (c[0],c[1],c[2],int(clamp(a)*255))
def mix(c1,c2,k):
    k=clamp(k); return tuple(int(c1[i]+(c2[i]-c1[i])*k) for i in range(3))

# ---- text helpers ----
def tw(txt,font,track=0.0):
    if not txt: return 0.0
    return font.getlength(txt)+track*(len(txt)-1)

def text(d,xy,txt,font,fill,a=1.0,track=0.0,anchor="lt"):
    """anchor: l/m/r + t/m/b  (uses cap-ish baseline via PIL anchors)"""
    if a<=0.003 or not txt: return
    col=rgba(fill,a)
    if track==0.0:
        pa={"lt":"la","mt":"ma","rt":"ra","lm":"lm","mm":"mm","rm":"rm",
            "lb":"ls","mb":"ms","rb":"rs"}[anchor]
        d.text(xy,txt,font=font,fill=col,anchor=pa); return
    x,y=xy; total=tw(txt,font,track)
    if anchor[0]=="m": x-=total/2
    elif anchor[0]=="r": x-=total
    va={"t":"la","m":"lm","b":"ls"}[anchor[1]]
    for ch in txt:
        d.text((x,y),ch,font=font,fill=col,anchor=va)
        x+=font.getlength(ch)+track

def grad_text(base,xy,txt,font,c_top,c_bot,a=1.0,anchor="mt",track=0.0):
    """vertical-gradient text composited onto RGBA `base`"""
    if a<=0.003: return
    wd=int(tw(txt,font,track))+8
    asc,desc=font.getmetrics(); ht=asc+desc+8
    mask=Image.new("L",(wd,ht),0); md=ImageDraw.Draw(mask)
    x=0
    for ch in txt:
        md.text((x,0),ch,font=font,fill=255,anchor="la"); x+=font.getlength(ch)+track
    bb=mask.getbbox()
    if not bb: return
    mask=mask.crop(bb); wd,ht=mask.size
    g=np.zeros((ht,wd,3),np.float32)
    ramp=np.linspace(0,1,ht,dtype=np.float32)[:,None]
    for i in range(3): g[:,:,i]=c_top[i]+(c_bot[i]-c_top[i])*ramp
    lay=Image.fromarray(g.astype(np.uint8),"RGB").convert("RGBA")
    if a<1.0:
        mask=mask.point(lambda v:int(v*a))
    lay.putalpha(mask)
    x0,y0=xy
    if anchor[0]=="m": x0-=wd//2
    elif anchor[0]=="r": x0-=wd
    if anchor[1]=="m": y0-=ht//2
    elif anchor[1]=="b": y0-=ht
    base.alpha_composite(lay,(int(x0),int(y0)))

def wrap(txt,font,maxw,track=0.0):
    out=[];cur=""
    for word in txt.split():
        t=(cur+" "+word).strip()
        if tw(t,font,track)<=maxw or not cur: cur=t
        else: out.append(cur); cur=word
    if cur: out.append(cur)
    return out

# ---- shapes ----
def card(d,box,r=26,fill=None,fa=1.0,outline=None,oa=1.0,wdt=2):
    if fill is None: fill=CARD
    if outline is None: outline=BORDER
    x0,y0,x1,y1=[int(v) for v in box]
    if x1<=x0 or y1<=y0: return
    d.rounded_rectangle((x0,y0,x1,y1),radius=r,
        fill=rgba(fill,fa) if fa>0 else None,
        outline=rgba(outline,oa) if oa>0 else None, width=wdt)

def pill(d,cx,cy,txt,font,col=None,a=1.0,track=6,padx=30,pady=17,dot=True,
         fill=None,fa=0.0,txtcol=None):
    if col is None: col=ORANGE
    twd=tw(txt,font,track)
    dw=26 if dot else 0
    bw=twd+dw+padx*2; asc,desc=font.getmetrics()
    bh=asc+pady*2
    x0=cx-bw/2; y0=cy-bh/2
    d.rounded_rectangle((x0,y0,x0+bw,y0+bh),radius=bh/2,
        fill=rgba(fill or col,fa) if fa>0 else None,
        outline=rgba(col,a*0.85),width=2)
    tx=x0+padx
    if dot:
        rr=6; d.ellipse((tx,cy-rr,tx+2*rr,cy+rr),fill=rgba(col,a)); tx+=dw
    text(d,(tx,cy),txt,font,txtcol or col,a,track,"lm")
    return (x0,y0,x0+bw,y0+bh)

def hline(d,x0,x1,y,col=None,a=1.0,wdt=2):
    if col is None: col=BORDER
    if x1>x0: d.line((x0,y,x1,y),fill=rgba(col,a),width=wdt)

# ---- glow sprites (pre-blurred, reused every frame) ----
def radial(w,h,cx,cy,rad,power=2.0):
    yy,xx=np.mgrid[0:h,0:w]
    dd=np.sqrt(((xx-cx)/rad)**2+((yy-cy)/rad)**2)
    return np.clip(1-dd,0,1)**power

_gl={}
def glow(color,rad,strength=1.0):
    """small RGBA sprite, cached: soft round light"""
    k=(color,rad,round(strength,3))
    if k in _gl: return _gl[k]
    s=int(rad*2)
    al=(radial(s,s,rad,rad,rad,2.4)*255*strength).astype(np.uint8)
    im=Image.new("RGBA",(s,s),(color[0],color[1],color[2],0))
    im.putalpha(Image.fromarray(al,"L"))
    _gl[k]=im; return im

def put_glow(base,cx,cy,color,rad,strength=1.0):
    if strength<=0.004: return
    sp=glow(color,int(rad),1.0)
    if strength<1.0:
        sp=sp.copy(); a=sp.getchannel("A").point(lambda v:int(v*strength)); sp.putalpha(a)
    base.alpha_composite(sp,(int(cx-rad),int(cy-rad)))

def set_palette(**kw):
    """Rebind palette globals so a sibling video can reuse this kit."""
    g=globals()
    for k,v in kw.items():
        assert k in g, k
        g[k]=v

def set_fonts(display=None, mono=None, weight_index=None, mono_index=None):
    """Swap typefaces. weight_index maps our weight names -> .ttc face index.

    Probe a new family first -- Helvetica Neue, for instance, has no check or
    arrow glyphs and silently renders .notdef boxes:
        python3 -c "import kit; print(kit.probe_glyphs(kit.HN,1))"
    """
    global HN,MN,_WI,_MI
    if display is not None: HN=display
    if mono is not None:    MN=mono
    if weight_index is not None: _WI=dict(weight_index)
    if mono_index  is not None: _MI=dict(mono_index)
    _fc.clear()

def probe_glyphs(path,index=0,chars="✓✕→↓↻·—●⚠"):
    """-> {char: 'OK'|'NOTDEF'|'EMPTY'}. NOTDEF renders as a tofu box."""
    import numpy as _np
    fo=ImageFont.truetype(path,56,index=index)
    def r(ch):
        im=Image.new("L",(90,90),0); ImageDraw.Draw(im).text((10,10),ch,font=fo,fill=255)
        return _np.array(im)
    ref=r("￿"); out={}
    for ch in chars:
        a=r(ch)
        out[ch]="EMPTY" if a.max()==0 else ("NOTDEF" if _np.array_equal(a,ref) else "OK")
    return out
