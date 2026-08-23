# ---------------------------------------------------------------
# ecc.py -- "ECC / Everything Claude Code". Warm-orange reel.
# ---------------------------------------------------------------
import math, os, sys, numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kit
from kit import *
from timing import Timing

# ---- storyboard contract (read by render.py / sfx.py / make.sh) ----
NAME    = "ecc"
AUDIO   = "ECC.mp3"              # relative to the repo root
PHRASES = "phrases/ecc.txt"   # relative to video/
TOTAL   = 44.0                # finished length; >= audio duration
FPS     = 30

_T = Timing(NAME)
WORDS     = _T.words
AUDIO_DUR = _T.duration
wstart, wend = _T.ws, _T.we      # look words up BY NAME, never by index
CH        = _T.chunks()          # caption chunks

S=[("hook",0.00,5.50),("title",5.50,8.50),("what",8.50,12.15),
   ("inside",12.15,15.95),("shield",15.95,20.15),("loop",20.15,32.90),
   ("proof",32.90,38.45),("install",38.45,42.30),("end",42.30,TOTAL)]
def scene_at(t):
    for n,a,b in S:
        if a<=t<b: return n,a,b
    return S[-1][0],S[-1][1],S[-1][2]
CUTS=[a for _,a,_ in S[1:]]
def fit(txt,maxw,start,minsz=28,w="bold",track=0.0):
    s=start
    while s>minsz and tw(txt,f(s,w),track)>maxw: s-=2
    return f(s,w)
# ---------------- static base ----------------
def build_base():
    a=np.zeros((H,W,3),np.float32)
    a[:,:]=BG
    # warm bloom top-left  +  faint amber bottom-right + centre lift
    for cx,cy,rad,col,st,pw in [(190,300,1150,(150,66,20),0.30,2.3),
                                (980,1780,860,(120,92,20),0.10,2.4),
                                (540,900,1400,(40,30,44),0.24,1.6)]:
        g=radial(W,H,cx,cy,rad,pw)[:,:,None]
        a+=g*np.array(col,np.float32)*st
    # vertical falloff so captions sit on darker ground
    v=np.linspace(1.0,0.72,H,dtype=np.float32)[:,None,None]
    a*=v
    # grain: kills banding after platform re-encode
    rng=np.random.RandomState(7)
    a+=rng.normal(0,2.1,(H,W,1)).astype(np.float32)
    a+=rng.normal(0,0.9,(H,W,3)).astype(np.float32)
    a=np.clip(a,0,255)
    im=Image.fromarray(a.astype(np.uint8),"RGB").convert("RGBA")
    return im
BASE=build_base()

# ---- scrolling skill-path strip (background texture for 'what'/'inside') ----
SKILLS=["skills/tdd/SKILL.md","skills/research-first/SKILL.md","agents/code-reviewer.md",
 "skills/security/agentshield/SKILL.md","rules/always/context-budget.md","agents/build-repair.md",
 "skills/frontend/design-system/SKILL.md",".ecc/memory/instincts.jsonl","commands/plan.md",
 "skills/verification/SKILL.md","agents/architecture-scout.md","skills/docs/changelog/SKILL.md",
 "hooks/pre-tool-use.sh","skills/data/schema-diff/SKILL.md","agents/security-auditor.md",
 "rules/always/no-silent-fail.md","skills/ml/eval-harness/SKILL.md","commands/verify.md",
 "agents/planner.md","skills/ops/rollback/SKILL.md",".ecc/memory/decisions.md",
 "skills/git/worktrees/SKILL.md","agents/test-writer.md","commands/remember.md"]
def build_strip():
    sh=1600
    im=Image.new("RGBA",(W,sh),(0,0,0,0)); d=ImageDraw.Draw(im)
    fo=m(25); y=0; i=0
    while y<sh:
        for col in (0,1):
            s=SKILLS[(i)%len(SKILLS)]; i+=1
            d.text((60+col*540,y),s,font=fo,fill=(255,255,255,8))
        y+=46
    return im
STRIP=build_strip()
def draw_strip(base,t,a=1.0):
    if a<=0.01: return
    off=int((t*34)%1600)
    lay=Image.new("RGBA",(W,H),(0,0,0,0))
    for k in (-1,0,1):
        lay.alpha_composite(STRIP,(0,-off+k*1600+200))
    if a<1.0:
        lay.putalpha(lay.getchannel("A").point(lambda v:int(v*a)))
    base.alpha_composite(lay)
# ---------------- chrome ----------------
def chrome(base,d,t):
    # progress bar
    p=clamp(t/TOTAL)
    d.rectangle((0,0,int(W*p),5),fill=rgba(ORANGE,0.55))
    # persistent repo tag
    text(d,(W-MARGIN,176),"affaan-m/ECC",m(25),(96,92,104),1.0,0,"rt")
    # breathing bloom keeps every frame alive
    put_glow(base,150,260,(180,80,26),620,0.05+0.030*pulse(t,6.0))
def cut_sweep(base,d,t):
    for c in CUTS:
        k=lin(t,c,c+0.30)
        if 0<k<1:
            y=int(-40+k*(H+80))
            d.rectangle((0,y,W,y+3),fill=rgba(ORANGE_HI,0.30*(1-k)))
# ---------------- captions ----------------
def captions(base,d,t):
    cur=None;prev=None
    for c in CH:
        if c["s"]-0.06<=t<=c["e"]+0.05: cur=c;break
        if c["e"]<t: prev=c
    a=1.0
    if cur is None:
        if prev is None: return
        gap=t-prev["e"]
        if gap>0.85: return
        cur=prev; a=1.0-lin(t,prev["e"]+0.45,prev["e"]+0.85)
    fo=f(54,"bold")
    words=[x["w"] for x in cur["ws"]]
    sp=fo.getlength(" ")
    widths=[fo.getlength(x) for x in words]
    total=sum(widths)+sp*(len(words)-1)
    x=540-total/2
    pad=26; asc,desc=fo.getmetrics()
    box=(x-pad,CAP_Y-asc*0.62-16,x+total+pad,CAP_Y+asc*0.42+16)
    d.rounded_rectangle([int(v) for v in box],radius=20,
                        fill=rgba((8,7,10),0.62*a),outline=rgba((255,255,255),0.05*a),width=1)
    for wd,ww,wob in zip(words,widths,cur["ws"]):
        live = wob["s"]-0.04<=t<=wob["e"]+0.04
        col=ORANGE_HI if live else WHITE
        text(d,(x,CAP_Y),wd,fo,col,a,0,"lm")
        if live:
            d.rectangle((int(x),int(CAP_Y+asc*0.40),int(x+ww),int(CAP_Y+asc*0.40)+4),
                        fill=rgba(ORANGE_HI,0.75*a))
        x+=ww+sp
# ---------------- shared bits ----------------
def eyebrow(base,d,txt,t,t0,y=252):
    k=eo3(lin(t,t0,t0+0.34))
    if k<=0.01: return
    pill(d,540,y+ (1-k)*-14,txt,f(31,"bold"),ORANGE,k,track=6)
def enter(t,t0,dur=0.34,dy=34):
    k=eo3(lin(t,t0,t0+dur))
    return k,(1-k)*dy

# ================= SCENE 1 : HOOK =================
HOOK=[("WRITES THE CODE",      wstart("writes"), 1.14, True ),
      ("REVIEWS ITS OWN CODE", wstart("reviews"),2.58, False),
      ("FORGETS EVERYTHING",   wstart("forgets"),4.08, False)]
def s_hook(base,d,t):
    eyebrow(base,d,"YOUR CODING AGENT",t,0.0)
    fo=fit("REVIEWS ITS OWN CODE",790,72,44)
    for i,(txt,tl,tv,good) in enumerate(HOOK):
        y=470+i*182
        lit=lin(t,tl,tl+0.26)                    # word being spoken
        vk =eo3(lin(t,tv,tv+0.34))               # verdict lands
        col=mix(mix((132,127,140),WHITE,lit), GREEN if good else (140,132,138), vk)
        # marker
        bx=MARGIN; bs=62
        mc=mix(BORDER, GREEN if good else RED, vk)
        d.rounded_rectangle((bx,y-bs//2,bx+bs,y+bs//2),radius=16,
            fill=rgba(mc,0.14*vk),outline=rgba(mix(BORDER,mc,max(lit*0.5,vk)),0.9),width=3)
        cx,cy=bx+bs/2,y+1
        if vk>0.02:
            if good:
                pts=[(cx-14,cy+1),(cx-4,cy+11),(cx+15,cy-11)]
                n=1+int(vk*2)
                d.line(pts[:max(2,n)] if vk<0.6 else pts,fill=rgba(GREEN,vk),width=6,joint="curve")
            else:
                r=13*vk
                d.line((cx-r,cy-r,cx+r,cy+r),fill=rgba(RED,vk),width=6)
                d.line((cx-r,cy+r,cx+r,cy-r),fill=rgba(RED,vk),width=6)
        # label
        text(d,(bx+bs+38,y),txt,fo,col,1.0,0,"lm")
        if not good and vk>0.01:
            x0=bx+bs+34; x1=x0+tw(txt,fo)+10
            d.line((x0,y+2,x0+(x1-x0)*eo3(vk),y+2),fill=rgba(RED,0.9*vk),width=6)
        if good and vk>0.4: put_glow(base,cx,cy,GREEN,90,0.16*vk)
    # bridge to the title
    k,dy=enter(t,4.62,0.36,20)
    if k>0.01:
        text(d,(MARGIN,1024+dy),"FIX ALL THREE",f(46,"bold"),ORANGE,k,5,"lt")
        xw=tw("FIX ALL THREE",f(46,"bold"),5)
        text(d,(MARGIN+xw+30,1024+dy),"↓",m(46,"bold"),ORANGE,k*(0.55+0.45*pulse(t,0.9)),0,"lt")
        hline(d,MARGIN,MARGIN+int(300*k),1096+dy,ORANGE,0.5*k,3)

# ================= SCENE 2 : TITLE =================
def s_title(base,d,t,t0=5.50):
    k=eo3(lin(t,t0,t0+0.42)); kb=eob(lin(t,t0,t0+0.62),1.6)
    put_glow(base,540,600,(210,96,34),760,0.30*k+0.05*pulse(t,3.0))
    sz=int(300*(0.90+0.10*kb))
    grad_text(base,(540,600),"ECC",f(sz,"bold"),WHITE,CREAM,k,"mm")
    k2=eo3(lin(t,t0+0.34,t0+0.72))
    text(d,(540,796),"Everything Claude Code",m(42),MUTED,k2,3,"mm")
    k3=eo3(lin(t,t0+0.52,t0+0.86))
    hline(d,540-int(150*k3),540+int(150*k3),884,ORANGE,0.9*k3,4)
    k4,dy=enter(t,wstart("fixes")-0.18,0.36,26)
    if k4>0.01:
        text(d,(540,978+dy),"FIXES ALL THREE",f(80,"bold"),WHITE,k4,0,"mt")
    k5,dy5=enter(t,t0+1.30,0.36,18)
    if k5>0.01:
        pill(d,540,1180+dy5,"OPEN SOURCE · MIT · v2.2.0",f(30,"bold"),MUTED,k5,track=5,dot=False)

# ================= SCENE 3 : WHAT IT IS =================
WHAT=[("It's",WHITE),("an",WHITE),("open-source",ORANGE),("operating",ORANGE),
      ("system",ORANGE),("for",WHITE),("agent",WHITE),("harnesses",WHITE)]
W0=next(i for i,x in enumerate(WORDS) if x["w"]=="It's")   # offset of this phrase
def s_what(base,d,t,t0=8.50):
    draw_strip(base,t,0.9*eo3(lin(t,t0,t0+0.6)))
    eyebrow(base,d,"WHAT IT IS",t,t0)
    fo=f(84,"bold")
    lines=[[0,1,2],[3,4],[5,6,7]]              # word indices per line
    for li,idx in enumerate(lines):
        y=430+li*116
        parts=[(WHAT[i][0],WHAT[i][1],WORDS[W0+i]["s"]) for i in idx]
        x=MARGIN
        for txt,col,ts in parts:
            k=eo3(lin(t,ts-0.10,ts+0.24))
            text(d,(x,y+(1-k)*18),txt,fo,col,k,0,"lt")
            x+=fo.getlength(txt)+fo.getlength(" ")
    k,dy=enter(t,t0+1.05,0.4,22)
    if k>0.01:
        hline(d,MARGIN,MARGIN+int(220*k),800,ORANGE,0.8,4)
        for i,(lab,val) in enumerate([("harnesses","14 supported"),
                                      ("licence","MIT"),("author","Affaan M · ships weekly")]):
            kk=eo3(lin(t,t0+1.15+i*0.16,t0+1.50+i*0.16))
            y=870+i*70
            text(d,(MARGIN,y),lab,m(30),DIM,kk,0,"lt")
            text(d,(MARGIN+300,y),val,m(30),WHITE,kk*0.9,0,"lt")

# ================= SCENE 4 : WHAT'S INSIDE =================
def statcard(base,d,box,num,label,t,t0,target):
    k,dy=enter(t,t0,0.34,26)
    if k<=0.01: return
    x0,y0,x1,y1=box; y0+=dy; y1+=dy
    card(d,(x0,y0,x1,y1),28,CARD,0.90*k,BORDER,0.9*k,2)
    put_glow(base,(x0+x1)/2,(y0+y1)/2-24,(200,92,34),250,0.15*k)
    p=eo4(lin(t,t0,t0+1.05)); cur=int(round(target*p))
    s=f"{cur:,}" if target>=1000 else str(cur)
    grad_text(base,((x0+x1)/2,y0+46),s,f(116,"bold"),ORANGE_HI,ORANGE,k,"mt")
    text(d,((x0+x1)/2,y1-42),label,f(29,"bold"),MUTED,k,5,"mm")

def s_inside(base,d,t,t0=12.15):
    draw_strip(base,t,0.55)
    eyebrow(base,d,"WHAT'S INSIDE",t,t0)
    statcard(base,d,(MARGIN,376,528,632),68,"SPECIALIST AGENTS",t,wstart("68")-0.12,68)
    statcard(base,d,(552,376,W-MARGIN,632),285,"SKILLS",t,wstart("285")-0.12,285)
    rows=[("94","COMMANDS"),("23","RULE PACKS"),("12","LANGUAGES"),("5","LAYERS")]
    for i,(n,l) in enumerate(rows):
        k,dy=enter(t,t0+1.55+i*0.13,0.3,18)
        if k<=0.01: continue
        cx=MARGIN+(i%2)*468; cy=696+(i//2)*104
        card(d,(cx,cy+dy,cx+444,cy+86+dy),18,CARD,0.7*k,BORDER,0.7*k,2)
        text(d,(cx+26,cy+43+dy),n,f(44,"bold"),ORANGE,k,0,"lm")
        text(d,(cx+26+tw(n,f(44,'bold'))+20,cy+46+dy),l,f(27,"bold"),MUTED,k,4,"lm")
    LAY=[("SKILLS","loaded on demand"),("AGENTS","own context + tools"),
         ("RULES","always loaded"),("HOOKS","run outside the model"),
         ("INSTINCTS","learned, confidence-scored")]
    k,_=enter(t,t0+2.05,0.4,0)
    if k>0.01:
        hline(d,MARGIN,W-MARGIN,952,BORDER,0.8*k,2)
        for i,(a,b) in enumerate(LAY):
            kk=eo3(lin(t,t0+2.10+i*0.11,t0+2.42+i*0.11))
            y=998+i*66
            d.ellipse((MARGIN,y-5,MARGIN+10,y+5),fill=rgba(ORANGE,kk))
            text(d,(MARGIN+30,y),a,f(31,"bold"),WHITE,kk,3,"lm")
            text(d,(MARGIN+322,y),b,m(28),DIM,kk,0,"lm")

# ================= SCENE 5 : AGENTSHIELD =================
SCAN=[("prompts","CLEAN"),("hooks","CLEAN"),("mcp config","1 FINDING"),
      ("permissions","CLEAN"),("secrets","CLEAN"),("agent files","CLEAN")]
def s_shield(base,d,t,t0=15.95):
    eyebrow(base,d,"SECURITY",t,t0)
    k,dy=enter(t,t0+0.10,0.36,26)
    text(d,(MARGIN,352+dy),"your agent config",f(76,"bold"),WHITE,k,0,"lt")
    k2,dy2=enter(t,t0+0.30,0.36,26)
    text(d,(MARGIN,444+dy2),"is an attack surface",f(76,"bold"),ORANGE,k2,0,"lt")
    kp,dyp=enter(t,t0+0.55,0.4,30)
    if kp<=0.01: return
    box=(MARGIN,594+dyp,W-MARGIN,1198+dyp)
    card(d,box,26,(18,16,21),0.92*kp,BORDER,0.9*kp,2)
    x0,y0,x1,y1=box
    text(d,(x0+34,y0+46),"AgentShield",f(46,"bold"),WHITE,kp,0,"lm")
    scanning = t<t0+3.3
    text(d,(x1-34,y0+46),"SCANNING…" if scanning else "SCAN COMPLETE",
         m(28,"bold"),ORANGE if scanning else GREEN,kp,2,"rm")
    hline(d,x0+34,x1-34,y0+90,BORDER,0.9*kp,2)
    fo=m(34); fb=m(28,"bold")
    for i,(name,verdict) in enumerate(SCAN):
        ts=t0+0.62+i*0.40
        kk=eo3(lin(t,ts,ts+0.22))
        if kk<=0.01: continue
        y=y0+146+i*80
        bad = verdict!="CLEAN"
        col=RED if bad else GREEN
        cx=x0+52
        d.ellipse((cx-13,y-13,cx+13,y+13),outline=rgba(col,0.55*kk),width=2)
        if bad:
            r=7; d.line((cx-r,y-r,cx+r,y+r),fill=rgba(col,kk),width=4)
            d.line((cx-r,y+r,cx+r,y-r),fill=rgba(col,kk),width=4)
        else:
            d.line([(cx-6,y+1),(cx-1,y+6),(cx+7,y-6)],fill=rgba(col,kk),width=4,joint="curve")
        text(d,(x0+96,y),name,fo,WHITE if not bad else RED,0.92*kk,0,"lm")
        text(d,(x1-34,y),verdict,fb,col,kk,2,"rm")
        if bad and kk>0.9: put_glow(base,cx,y,RED,110,0.20)
    ks=lin(t,t0+0.62,t0+3.2)
    if 0<ks<1:
        ly=y0+120+ks*(y1-y0-150)
        d.rectangle((x0+8,ly,x1-8,ly+3),fill=rgba(ORANGE_HI,0.35*(1-ks*0.5)))
    k3,_=enter(t,t0+3.4,0.36,0)
    if k3>0.01:
        text(d,(540,1262),"scans prompts · hooks · MCP · permissions · secrets · agent files",
             m(27),DIM,k3,0,"mt")

# ================= SCENE 6 : THE LOOP =================
STAGES=["PLAN","TEST","IMPLEMENT","REVIEW","VERIFY","REMEMBER","IMPROVE"]
ST_T=[wstart("plan"),wstart("test"),wstart("implement"),wstart("review"),
      wstart("verify"),wstart("remember"),wstart("improve")]
RAIL=142; ROW0=440; DROW=122
CALL_R=(wstart("fresh-context")-0.30, 30.95)
CALL_M=(wstart("and",2)-0.05, 32.84)   # 'and what it learns becomes memory'

def s_loop(base,d,t,t0=20.15):
    eyebrow(base,d,"EVERYTHING RUNS ONE LOOP",t,t0)
    kp,dyp=enter(t,t0+0.20,0.4,30)
    if kp<=0.01: return
    ytop=ROW0+dyp; ybot=ROW0+6*DROW+dyp
    railk=eo3(lin(t,t0+0.22,t0+1.20))
    d.line((RAIL,ytop,RAIL,ytop+(ybot-ytop)*railk),fill=rgba(BORDER,0.95*kp),width=4)
    # focus dimming during callouts
    foc=-1
    if CALL_R[0]<=t<CALL_R[1]: foc=3
    elif CALL_M[0]<=t<CALL_M[1]: foc=5
    # filled rail
    prog=0.0
    for i,ts in enumerate(ST_T):
        if t>=ts: prog=i+ (0 if i==6 else min(1.0,(t-ts)/max(0.18,(ST_T[i+1]-ts))))
    if prog>0:
        d.line((RAIL,ytop,RAIL,ytop+min(6,prog)*DROW),fill=rgba(ORANGE,0.85),width=4)
    fo=f(46,"bold")
    for i,(name,ts) in enumerate(zip(STAGES,ST_T)):
        y=ROW0+i*DROW+dyp
        lit=eo3(lin(t,ts,ts+0.22))
        app=eo3(lin(t,t0+0.28+i*0.10,t0+0.62+i*0.10))
        base_a = (1.0 if foc<0 else (1.0 if i==foc else 0.30))*app
        # dot
        rr=14
        dc=mix(BORDER,ORANGE,lit)
        d.ellipse((RAIL-rr,y-rr,RAIL+rr,y+rr),fill=rgba((10,8,9),1.0))
        d.ellipse((RAIL-rr,y-rr,RAIL+rr,y+rr),
                  fill=rgba(dc,lit*0.95*base_a),outline=rgba(dc,0.9*base_a),width=3)
        if lit>0.5:
            gl=0.20*base_a*(1.0 if i!=foc else 0.34+0.20*pulse(t,1.1))
            put_glow(base,RAIL,y,ORANGE,120,gl)
        text(d,(RAIL+52,y-2),f"{i+1}",m(27,"bold"),mix(FAINT,ORANGE,lit),base_a,0,"lm")
        col=mix((104,99,112),WHITE,lit)
        text(d,(RAIL+96,y),name,fo,col,base_a,1,"lm")
        if lit>0.98 and i<6 and foc<0:
            text(d,(RAIL+96+tw(name,fo,1)+24,y+1),"✓",m(30,"bold"),ORANGE,0.55,0,"lm")
    # loop closes
    kl=eo3(lin(t,wend("improve.")+0.06,wend("improve.")+0.62))
    aa=1.0 if foc<0 else 0.34
    if kl>0.01:
        xo=RAIL-64
        seg=[(RAIL,ybot),(xo,ybot+2),(xo,ytop-2),(RAIL,ytop)]
        n=int(kl*3)+1; pl=seg[:max(2,min(4,n+1))]
        if kl>0.34: pl=[(RAIL,ybot),(xo,ybot+2),(xo, ybot+2-(ybot-ytop+4)*min(1,(kl-0.30)/0.55))]
        if kl>0.86: pl=seg
        d.line(pl,fill=rgba(ORANGE,0.9*kl*aa),width=4,joint="curve")
        if kl>0.9:
            d.polygon([(RAIL-4,ytop),(RAIL-22,ytop-11),(RAIL-22,ytop+11)],fill=rgba(ORANGE,aa))
            put_glow(base,RAIL,ytop,ORANGE,150,0.22*pulse(t,1.0)*aa)
    # callouts
    def callout(y,title,body,tstart,tend,mono=False,extra=None):
        k=eo3(lin(t,tstart,tstart+0.30))*(1-lin(t,tend-0.16,tend))
        if k<=0.01: return
        x0,x1=560,966
        fb=f(28,"med")
        lines=wrap(body,fb,x1-x0-52)
        h=104+36*len(lines)+(32 if extra else 0)
        b=(x0,y-h/2,x1,y+h/2)
        card(d,b,22,(20,17,24),0.96*k,ORANGE,0.55*k,2)
        d.line((RAIL+96+312,y,x0-6,y),fill=rgba(ORANGE,0.45*k),width=3)
        tf=m(33,"bold") if mono else f(34,"bold")
        text(d,(x0+26,y-h/2+42),title,tf,ORANGE_HI if mono else WHITE,k,0 if mono else 3,"lm")
        yy=y-h/2+76
        for ln in lines:
            text(d,(x0+26,yy),ln,fb,MUTED,k,0,"lt"); yy+=36
        if extra:
            text(d,(x0+26,yy+6),extra,m(24),GREEN,k*0.95,0,"lt")
    callout(ROW0+3*DROW+dyp,"FRESH CONTEXT",
            "a reviewer that never wrote the code grades it",
            CALL_R[0],CALL_R[1])
    callout(ROW0+5*DROW+dyp,".ecc/memory/",
            "what it learns survives the session",
            CALL_M[0],CALL_M[1],mono=True,
            extra="› instinct saved  0.82")

# ================= SCENE 7 : PROOF =================
SPTS=[(0,0),(1,3200),(2,12500),(3,31000),(4,68000),(5,122000),(6,186000),(7,240818)]
def star_pts(box):
    x0,y0,x1,y1=box
    out=[]
    N=180
    for i in range(N+1):
        u=i/N*7.0
        j=min(6,int(u)); fr=u-j
        fr=fr*fr*(3-2*fr)
        v=SPTS[j][1]+(SPTS[j+1][1]-SPTS[j][1])*fr
        out.append((x0+(x1-x0)*u/7.0, y1-(y1-y0)*(v/240818.0)))
    return out
_CHG=None
def chart_grad(box):
    global _CHG
    if _CHG: return _CHG
    x0,y0,x1,y1=[int(v) for v in box]
    w,h=x1-x0,y1-y0
    a=np.zeros((h,w,4),np.uint8)
    ramp=np.linspace(0,1,h)[:,None]
    a[:,:,0]=int(ORANGE[0]);a[:,:,1]=int(ORANGE[1]);a[:,:,2]=int(ORANGE[2])
    a[:,:,3]=(ramp*118).astype(np.uint8)
    _CHG=Image.fromarray(a,"RGBA"); return _CHG

def s_proof(base,d,t,t0=32.90):
    eyebrow(base,d,"TRACTION",t,t0)
    kb=eob(lin(t,wstart("MIT-licensed,")-0.10,wstart("MIT-licensed,")+0.5),2.0)
    if kb>0.01:
        pill(d,540,352,"MIT LICENSED · FREE FOREVER",f(32,"bold"),GREEN,kb,track=5,dot=True)
    tgt=240818
    ts=wstart("quarter-million")-0.55
    p=eo4(lin(t,ts,ts+2.15))
    if p>0.0:
        cur=int(tgt*p)
        put_glow(base,540,505,(210,96,34),480,0.16*min(1,p*3))
        grad_text(base,(540,505),f"{cur:,}",f(132,"bold"),ORANGE_HI,ORANGE,min(1,p*4),"mm")
        text(d,(540,596),"GITHUB STARS IN SEVEN MONTHS",f(30,"bold"),MUTED,min(1,p*4),5,"mm")
    box=(MARGIN+8,690,W-MARGIN-8,1176)
    kc,dyc=enter(t,t0+0.55,0.4,26)
    if kc>0.01:
        x0,y0,x1,y1=box
        for i in range(1,4):
            hline(d,x0,x1,y0+(y1-y0)*i/4,BORDER,0.45*kc,1)
        pts=star_pts(box)
        cp=eo3(lin(t,t0+0.75,t0+3.3))
        n=max(2,int(cp*len(pts)))
        sub=pts[:n]
        if cp>0.01:
            mask=Image.new("L",(int(x1-x0),int(y1-y0)),0)
            md=ImageDraw.Draw(mask)
            poly=[(px-x0,py-y0) for px,py in sub]+[(sub[-1][0]-x0,y1-y0),(0,y1-y0)]
            md.polygon(poly,fill=int(200*kc))
            g=chart_grad(box).copy(); g.putalpha(Image.composite(g.getchannel("A"),
                Image.new("L",mask.size,0),mask))
            base.alpha_composite(g,(int(x0),int(y0)))
            d.line(sub,fill=rgba(ORANGE_HI,0.98*kc),width=7,joint="curve")
            if cp>0.05:
                hx,hy=sub[-1]
                put_glow(base,hx,hy,ORANGE_HI,180,0.42)
                d.ellipse((hx-11,hy-11,hx+11,hy+11),fill=rgba(WHITE,1.0))
        text(d,(x0,y1+26),"18 JAN 2026",m(27),DIM,kc,0,"lt")
        text(d,(x1,y1+26),"AUG 2026",m(27),DIM,kc,0,"rt")
    for i,txt in enumerate(["v2.2.0","36,528 FORKS","SHIPS WEEKLY"]):
        k,dy=enter(t,t0+2.9+i*0.14,0.3,16)
        if k<=0.01: continue
        cw=(W-2*MARGIN-32)/3
        x=MARGIN+i*(cw+16)
        card(d,(x,1276+dy,x+cw,1352+dy),16,CARD,0.7*k,BORDER,0.7*k,2)
        text(d,(x+cw/2,1316+dy),txt,f(28,"bold"),MUTED,k,3,"mm")

# ================= SCENE 8 : INSTALL =================
CMD=[("/plugin marketplace add",38.66,39.22),
     ("  https://github.com/affaan-m/ECC",39.22,39.86),
     ("/plugin install ecc@ecc",39.90,40.34)]
HARN=[("CLAUDE CODE",wstart("Claude")),("CODEX",wstart("Codex,")),("CURSOR",wstart("Cursor"))]
def s_install(base,d,t,t0=38.45):
    eyebrow(base,d,"TWO COMMANDS",t,t0)
    k,dy=enter(t,t0+0.06,0.3,24)
    if k<=0.01: return
    box=(MARGIN,340+dy,W-MARGIN,676+dy); x0,y0,x1,y1=box
    card(d,box,24,(15,13,18),0.95*k,BORDER,0.9*k,2)
    hline(d,x0,x1,y0+62,BORDER,0.8*k,2)
    for i,c in enumerate([(255,95,86),(255,189,46),(39,201,63)]):
        d.ellipse((x0+30+i*30,y0+25,x0+44+i*30,y0+39),fill=rgba(c,0.55*k))
    text(d,(x1-28,y0+32),"claude code",m(25),DIM,k,0,"rm")
    fo=m(31); yy=y0+108
    for txt,a,b in CMD:
        if t<a-0.02: break
        n=int(len(txt)*clamp((t-a)/(b-a)))
        show=txt[:n] if t<b else txt
        lead = not txt.startswith(" ")
        if lead: text(d,(x0+30,yy),"›",m(31,"bold"),ORANGE,1.0,0,"lt")
        text(d,(x0+60,yy),show,fo,WHITE,1.0,0,"lt")
        if t<b and int(t*8)%2==0:
            cx=x0+60+fo.getlength(show)
            d.rectangle((cx+2,yy+4,cx+16,yy+34),fill=rgba(ORANGE_HI,0.85))
        yy+=52
    ok=eo3(lin(t,40.42,40.70))
    if ok>0.01:
        text(d,(x0+30,y1-56),"✓  68 agents · 285 skills · 94 commands loaded",
             m(27,"bold"),GREEN,ok,0,"lm")
    for i,(name,ts) in enumerate(HARN):
        kk=eo3(lin(t,ts-0.08,ts+0.26))
        cw=(W-2*MARGIN-32)/3; x=MARGIN+i*(cw+16); y=744
        card(d,(x,y,x+cw,y+124),20,CARD,0.55+0.40*kk,mix(BORDER,ORANGE,kk),0.55+0.4*kk,2)
        if kk>0.5: put_glow(base,x+cw/2,y+62,ORANGE,190,0.15*kk)
        text(d,(x+cw/2,y+50),name,f(33,"bold"),mix((90,86,96),WHITE,kk),1.0,2,"mm")
        text(d,(x+cw/2,y+92),"SUPPORTED" if kk>0.6 else "",f(23,"bold"),GREEN,kk,3,"mm")
    k2,_=enter(t,t0+3.05,0.4,0)
    if k2>0.01:
        text(d,(540,918),"+ 11 MORE HARNESSES",f(27,"bold"),DIM,k2,5,"mt")
        body=("OpenCode · Gemini · Zed · GitHub Copilot · Antigravity · Qwen · "
              "Kimi · CodeBuddy · JoyCode · Hermes · OpenClaw")
        yy=974
        for ln in wrap(body,m(27),W-2*MARGIN-40):
            text(d,(540,yy),ln,m(27),(84,80,92),k2,0,"mt"); yy+=42

# ================= SCENE 9 : END CARD =================
def s_end(base,d,t,t0=42.30):
    k=eo3(lin(t,t0,t0+0.34)); kb=eob(lin(t,t0,t0+0.55),1.4)
    put_glow(base,540,620,(210,96,34),820,0.30*k+0.04*pulse(t,2.5))
    grad_text(base,(540,600),"ECC",f(int(268*(0.92+0.08*kb)),"bold"),WHITE,CREAM,k,"mm")
    text(d,(540,784),"Everything Claude Code",m(38),MUTED,k,3,"mm")
    k2=eo3(lin(t,t0+0.22,t0+0.56))
    hline(d,540-int(140*k2),540+int(140*k2),862,ORANGE,0.9*k2,4)
    text(d,(540,930),"github.com/affaan-m/ECC",m(42,"bold"),WHITE,k2,0,"mt")
    text(d,(540,992),"ecc.tools",m(38),ORANGE,k2,0,"mt")
    k3=eo3(lin(t,t0+0.44,t0+0.80))
    if k3>0.01:
        fo=f(35,"bold"); txt="SAVE THIS FOR YOUR NEXT BUILD"
        wd=tw(txt,fo,4)+72
        x0=540-wd/2
        d.rounded_rectangle((int(x0),1128,int(x0+wd),1210),radius=41,
                            fill=rgba(ORANGE,0.94*k3))
        text(d,(540,1170),txt,fo,(18,10,6),k3,4,"mm")
        put_glow(base,540,1169,ORANGE,320,0.16*k3)
    k4=eo3(lin(t,t0+0.70,t0+1.05))
    if k4>0.01:
        lab="WATCH AGAIN"; fl=f(28,"bold"); wd=tw(lab,fl,5)
        text(d,(540-wd/2-38,1296),"↻",m(30),DIM,k4,0,"lm")
        text(d,(540+18,1296),lab,fl,DIM,k4,5,"mm")

# ================= dispatch =================
def frame(t):
    base=BASE.copy()
    ov=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(ov)
    n,a,b=scene_at(t)
    # NB: scenes draw into `ov` (not `base`) so call order == z-order.
    if   n=="hook":   s_hook(ov,d,t)
    elif n=="title":  s_title(ov,d,t,a)
    elif n=="what":   s_what(ov,d,t,a)
    elif n=="inside": s_inside(ov,d,t,a)
    elif n=="shield": s_shield(ov,d,t,a)
    elif n=="loop":   s_loop(ov,d,t,a)
    elif n=="proof":  s_proof(ov,d,t,a)
    elif n=="install":s_install(ov,d,t,a)
    else:             s_end(ov,d,t,a)
    chrome(base,d,t)
    cut_sweep(ov,d,t)
    if n!="end": captions(base,d,t)
    base.alpha_composite(ov)
    return base

# ---- sound design (read by sfx.py; plain data, keep it subtle) ------------
_BIG={5.50,42.30}                                   # title card, end card
SFX=(
  [{"t":c-0.30,"kind":"swish","amp":0.16} for c in CUTS] +
  [{"t":c,"kind":"thump","amp":0.30 if c in _BIG else 0.21,
    "dur":0.55 if c in _BIG else 0.34,
    "freq":46.0 if c in _BIG else 58.0} for c in CUTS] +
  [{"t":ts,"kind":"tick","amp":0.085} for ts in ST_T] +          # the 7 stages
  [{"t":ts,"kind":"tick","amp":0.075,"tone":3000.0}              # counters spin up
     for ts in (wstart("68")-0.12, wstart("285")-0.12,
                wstart("quarter-million")-0.55)] +
  [{"t":ts,"kind":"tick","amp":0.070,"tone":3000.0}              # harness chips
     for ts in (wstart("Claude"), wstart("Codex,"), wstart("Cursor"))] +
  [{"t":wend("improve.")+0.10,"kind":"thump","amp":0.16},        # the loop closes
   {"t":40.44,"kind":"tick","amp":0.09,"tone":3000.0}]           # install check
)
