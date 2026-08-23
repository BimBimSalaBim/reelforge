# ---------------------------------------------------------------
# aas.py -- "Agentic Awesome Skills". Cyan sibling of ecc.py.
# ---------------------------------------------------------------
import math, os, sys, numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kit
from kit import *
from timing import Timing

# ---- storyboard contract (read by render.py / sfx.py / make.sh) ----
NAME    = "aas"
AUDIO   = "agentic-awesome-skills.mp3"              # relative to the repo root
PHRASES = "phrases/aas.txt"   # relative to video/
TOTAL   = 39.0                # finished length; >= audio duration
FPS     = 30

_T = Timing(NAME)
WORDS     = _T.words
AUDIO_DUR = _T.duration
wstart, wend = _T.ws, _T.we      # look words up BY NAME, never by index
CH        = _T.chunks()          # caption chunks

BG=(7,9,12); CYAN=(93,216,240); CYAN_HI=(155,236,250); PALE=(206,240,248)
DEEP=(26,92,116); MINT=(110,225,180); WHITE=(255,255,255)
MUTED=(150,156,166); DIM=(100,108,120); FAINT=(50,57,66)
CARD=(18,22,28); BORDER=(41,51,60); RED=(255,96,112); AMBER=(240,192,96)
kit.set_palette(BG=BG,ORANGE=CYAN,ORANGE_HI=CYAN_HI,CREAM=PALE,MUTED=MUTED,
                DIM=DIM,FAINT=FAINT,CARD=CARD,BORDER=BORDER,GREEN=MINT,RED=RED,
                AMBER=AMBER)
def ws(word,nth=0):
    h=[x for x in WORDS if x["w"].lower().strip('.,:;')==word.lower().strip('.,:;')]
    return h[nth]["s"]
def we(word,nth=0):
    h=[x for x in WORDS if x["w"].lower().strip('.,:;')==word.lower().strip('.,:;')]
    return h[nth]["e"]
S=[("hook",0.00,5.60),("title",5.60,9.30),("mcp",9.30,16.20),
   ("ranks",16.20,20.72),("chain",20.72,25.05),("harness",25.05,31.50),
   ("proof",31.50,34.58),("install",34.58,37.30),("end",37.30,TOTAL)]
def scene_at(t):
    for n,a,b in S:
        if a<=t<b: return n,a,b
    return S[-1]
CUTS=[a for _,a,_ in S[1:]]
# ---------------- ground ----------------
def build_base():
    a=np.zeros((H,W,3),np.float32); a[:,:]=BG
    for cx,cy,rad,col,st,pw in [(210,300,1180,(28,104,132),0.34,2.3),
                                (960,1760,880,(30,110,86),0.11,2.4),
                                (540,900,1400,(30,34,46),0.24,1.6)]:
        a+=radial(W,H,cx,cy,rad,pw)[:,:,None]*np.array(col,np.float32)*st
    a*=np.linspace(1.0,0.72,H,dtype=np.float32)[:,None,None]
    rng=np.random.RandomState(19)
    a+=rng.normal(0,2.1,(H,W,1)).astype(np.float32)
    a+=rng.normal(0,0.9,(H,W,3)).astype(np.float32)
    return Image.fromarray(np.clip(a,0,255).astype(np.uint8),"RGB").convert("RGBA")
BASE=build_base()
# ---------------- the wall of 2,019 skills ----------------
CATS=["development","cloud","ai-ml","security","business","content","web-dev",
      "workflow","marketing","data","devops","qa","docs","mobile","payments"]
LEAF=["code-review","tdd","brainstorming","threat-model","terraform-modules",
 "eval-harness","schema-diff","rollback","changelog","design-system","a11y-audit",
 "load-test","secret-scan","openapi-spec","dockerfile-lint","k8s-probes","rag-eval",
 "prompt-eval","cost-guard","sbom","canary-deploy","feature-flags","dep-upgrade",
 "flaky-tests","perf-budget","seo-audit","copy-review","email-drip","churn-model",
 "invoice-sync","webhook-retry","idempotency","rate-limit","oauth-pkce","csp-header",
 "log-redaction","trace-spans","slo-alerts","blue-green","db-migrate","index-tuning",
 "cache-warm","queue-drain","backfill-job","data-contract","pii-scan","model-card",
 "drift-monitor","ab-test","onboarding-flow","paywall-copy","press-kit","roadmap-brief"]
STACK=["development/tdd","development/code-review","workflow/brainstorming",
       "security/threat-model","qa/flaky-tests","docs/changelog",
       "devops/canary-deploy","data/schema-diff","ai-ml/eval-harness",
       "security/secret-scan"]
ROWH=52; COLS=2; NROW=44
WH_=NROW*ROWH                       # 2288 px of list per tile
# The freeze offset is a whole number of tiles, so a frozen row sits at
# y = 52*row + 8 exactly. Slots are then chosen inside the visible band.
FINAL_OFF=6*WH_
SLOTS=[8,53,11,56,14,59,17,62,20,65]        # interleaved across the 2 columns
def build_wall():
    rows=[f"{CATS[i%len(CATS)]}/{LEAF[(i*7)%len(LEAF)]}" for i in range(NROW*COLS)]
    picks=set()
    for sl,name in zip(SLOTS,STACK):
        rows[sl]=name; picks.add(sl)
    im=Image.new("RGBA",(W,WH_),(0,0,0,0)); d=ImageDraw.Draw(im)
    fo=m(30)
    for i,r in enumerate(rows):
        x=70+(i//NROW)*520; y=(i%NROW)*ROWH+8
        d.text((x,y),r,font=fo,fill=(255,255,255,56 if i in picks else 44))
    return im,rows,picks
WALL,WROWS,WPICK=build_wall()
WALL_BLUR=WALL.resize((W,max(1,WH_//16)),Image.BILINEAR).resize((W,WH_),Image.BILINEAR)
def wall(base,off,sharp,a=1.0):
    o=int(off)%WH_
    lay=Image.new("RGBA",(W,H),(0,0,0,0))
    for src,aa in ((WALL_BLUR,1.0-sharp),(WALL,sharp)):
        if aa<=0.01: continue
        sub=Image.new("RGBA",(W,H),(0,0,0,0))
        for k in (0,1):
            sub.alpha_composite(src,(0,-o+k*WH_))
        if aa<1.0: sub.putalpha(sub.getchannel("A").point(lambda v:int(v*aa)))
        lay.alpha_composite(sub)
    if a<1.0: lay.putalpha(lay.getchannel("A").point(lambda v:int(v*a)))
    base.alpha_composite(lay)
def row_xy(idx,off):
    return 70+(idx//NROW)*520, ((idx%NROW)*ROWH+8-int(off))%WH_
# ---------------- chrome ----------------
def chrome(base,d,t):
    d.rectangle((0,0,int(W*clamp(t/TOTAL)),5),fill=rgba(CYAN,0.55))
    text(d,(W-MARGIN,176),"sickn33/aas",m(25),(104,112,124),1.0,0,"rt")
    put_glow(base,170,270,(34,116,148),620,0.05+0.030*pulse(t,6.0))
def cut_sweep(base,d,t):
    for c in CUTS:
        k=lin(t,c,c+0.30)
        if 0<k<1:
            y=int(-40+k*(H+80)); d.rectangle((0,y,W,y+3),fill=rgba(CYAN_HI,0.28*(1-k)))
# ---------------- captions ----------------
def captions(base,d,t):
    cur=None;prev=None
    for c in CH:
        if c["s"]-0.06<=t<=c["e"]+0.05: cur=c;break
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
    d.rounded_rectangle([int(v) for v in (x-pad,CAP_Y-asc*0.62-16,x+total+pad,CAP_Y+asc*0.42+16)],
        radius=20,fill=rgba((6,9,12),0.66*a),outline=rgba(WHITE,0.05*a),width=1)
    for wd,ww,wob in zip(wl,wid,cur["ws"]):
        live=wob["s"]-0.04<=t<=wob["e"]+0.04
        text(d,(x,CAP_Y),wd,fo,CYAN_HI if live else WHITE,a,0,"lm")
        if live: d.rectangle((int(x),int(CAP_Y+asc*0.40),int(x+ww),int(CAP_Y+asc*0.40)+4),
                             fill=rgba(CYAN_HI,0.75*a))
        x+=ww+sp
def eyebrow(base,d,txt,t,t0,y=252,col=None):
    k=eo3(lin(t,t0,t0+0.34))
    if k>0.01: pill(d,540,y+(1-k)*-14,txt,f(31,"bold"),col or CYAN,k,track=6)
def enter(t,t0,dur=0.34,dy=34):
    k=eo3(lin(t,t0,t0+dur)); return k,(1-k)*dy

# ================= 1. HOOK : the wall ==================
FREEZE=2.14
def s_hook(base,d,t):
    p=clamp(t/FREEZE)
    OFF=FINAL_OFF*(1-(1-p)**1.8)                # fast, then brakes to a stop
    sharp=eo3(lin(p,0.80,0.96))
    wall(base,OFF,sharp,0.95)
    sc=eo3(lin(t,ws("Picking")-0.34,ws("Picking")+0.20))
    if sc>0.01:
        # must alpha_composite: ImageDraw writes pixels, it does not blend,
        # so a full-frame draw would erase the wall underneath.
        base.alpha_composite(Image.new("RGBA",(W,H),rgba((5,7,10),0.84*sc)))
    if t>=FREEZE-0.02:
        for j,idx in enumerate(SLOTS):
            ts=FREEZE+0.02+j*0.055
            k=eo3(lin(t,ts,ts+0.20))
            if k<=0.01: continue
            x,y=row_xy(idx,FINAL_OFF)
            nm=WROWS[idx]; fo=m(30); wd=fo.getlength(nm)
            aa=k*(1.0-0.80*sc)                  # sinks to texture behind the headline
            d.rounded_rectangle((int(x-16),int(y-9),int(x+wd+16),int(y+40)),radius=10,
                fill=rgba(DEEP,0.42*aa),outline=rgba(CYAN,0.65*aa),width=2)
            text(d,(x,y),nm,fo,CYAN_HI,aa,0,"lt")
    eyebrow(base,d,"2,019 AGENT SKILLS",t,0.0)
    kc=eo3(lin(t,FREEZE+0.10,FREEZE+0.5))
    if kc>0.01 and sc<0.6:
        pill(d,540,1414,"10 SELECTED",f(30,"bold"),MINT,kc*(1-sc),track=5)
    if sc>0.02:
        fo=f(86,"bold")
        for i,(ln,col) in enumerate([("PICKING THE",WHITE),("RIGHT TEN",CYAN),
                                     ("IS THE HARD PART",WHITE)]):
            kk=eo3(lin(t,ws("Picking")-0.20+i*0.14,ws("Picking")+0.18+i*0.14))
            text(d,(MARGIN,560+i*112+(1-kk)*18),ln,fo,col,kk*sc,0,"lt")
        k2=eo3(lin(t,ws("hard")-0.10,ws("hard")+0.3))
        if k2>0.01:
            hline(d,MARGIN,MARGIN+int(240*k2),952,CYAN,0.8*k2*sc,4)
            text(d,(MARGIN,1006),"2,019 in the catalog · 101 categories",
                 m(31),MUTED,k2*sc,0,"lt")

# ================= 2. TITLE + CATALOG ==================
def s_title(base,d,t,t0=5.60):
    k=eo3(lin(t,t0,t0+0.42)); kb=eob(lin(t,t0,t0+0.62),1.6)
    put_glow(base,540,470,(36,132,166),700,0.30*k+0.05*pulse(t,3.0))
    grad_text(base,(540,468),"AAS",f(int(224*(0.90+0.10*kb)),"bold"),WHITE,PALE,k,"mm")
    k2=eo3(lin(t,t0+0.30,t0+0.68))
    text(d,(540,614),"Agentic Awesome Skills",m(40),MUTED,k2,3,"mm")
    k3=eo3(lin(t,t0+0.46,t0+0.80))
    hline(d,540-int(140*k3),540+int(140*k3),690,MINT,0.9*k3,4)
    STATS=[(2019,"SKILLS",ws("catalog")-0.10),(101,"CATEGORIES",ws("catalog")+0.42),
           (60,"PLUGINS",ws("catalog")+0.84)]
    cw=(W-2*MARGIN-32)/3
    for i,(tgt,lab,ts) in enumerate(STATS):
        kk,dy=enter(t,ts,0.32,26)
        if kk<=0.01: continue
        x=MARGIN+i*(cw+16); y0=782+dy
        card(d,(x,y0,x+cw,y0+202),24,CARD,0.92*kk,BORDER,0.9*kk,2)
        put_glow(base,x+cw/2,y0+84,(36,132,166),200,0.14*kk)
        p=eo4(lin(t,ts,ts+0.95)); cur=int(round(tgt*p))
        s=f"{cur:,}" if tgt>=1000 else str(cur)
        grad_text(base,(x+cw/2,y0+38),s,f(72,"bold"),CYAN_HI,CYAN,kk,"mt")
        text(d,(x+cw/2,y0+160),lab,f(26,"bold"),MUTED,kk,4,"mm")
    k4,dy4=enter(t,t0+2.05,0.36,18)
    if k4>0.01:
        pill(d,540,1088+dy4,"MIT · npm: agentic-awesome-skills · v15.15.0",
             f(28,"bold"),MUTED,k4,track=4,dot=False)
        text(d,(540,1176+dy4),"2,019 SKILL.md playbooks · 101 categories · 60 plugin packs",
             m(27),DIM,k4,0,"mt")

# ================= 3. LOCAL, READ-ONLY MCP ==================
TERM=[("aas-mcp search \"tdd\"",            10.15,10.95,"cmd"),
      ("2,019 skills indexed · 101 categories",11.05,11.75,"ok"),
      ("development/tdd",                    11.85,12.30,"hit"),
      ("qa/flaky-tests",                     12.36,12.78,"hit"),
      ("security/threat-model",              12.84,13.34,"hit")]
def s_mcp(base,d,t,t0=9.30):
    eyebrow(base,d,"LOCAL · READ-ONLY",t,t0)
    k,dy=enter(t,t0+0.06,0.36,26)
    text(d,(MARGIN,344+dy),"a local, read-only",f(74,"bold"),WHITE,k,0,"lt")
    k2,dy2=enter(t,ws("MCP")-0.20,0.36,26)
    text(d,(MARGIN,434+dy2),"MCP server",f(74,"bold"),CYAN,k2,0,"lt")
    kp,dyp=enter(t,t0+0.55,0.4,30)
    if kp>0.01:
        box=(MARGIN,566+dyp,W-MARGIN,952+dyp); x0,y0,x1,y1=box
        card(d,box,24,(13,17,22),0.95*kp,BORDER,0.9*kp,2)
        for i,c in enumerate([(255,95,86),(255,189,46),(39,201,63)]):
            d.ellipse((x0+30+i*30,y0+25,x0+44+i*30,y0+39),fill=rgba(c,0.5*kp))
        text(d,(x1-28,y0+32),"localhost · no network",m(24),MINT,kp,0,"rm")
        hline(d,x0,x1,y0+62,BORDER,0.8*kp,2)
        fo=m(30); yy=y0+104
        for txt,a,b,kind in TERM:
            if t<a-0.02: break
            n=int(len(txt)*clamp((t-a)/(b-a))); show=txt if t>=b else txt[:n]
            if kind=="cmd":
                text(d,(x0+30,yy),"›",m(30,"bold"),CYAN,1.0,0,"lt")
                text(d,(x0+58,yy),show,fo,WHITE,1.0,0,"lt")
            elif kind=="ok":
                text(d,(x0+30,yy),"✓",m(28,"bold"),MINT,1.0,0,"lt")
                text(d,(x0+62,yy),show,m(27),MUTED,1.0,0,"lt")
            else:
                text(d,(x0+30,yy),"→",m(28),CYAN,0.8,0,"lt")
                text(d,(x0+62,yy),show,m(28),CYAN_HI,0.95,0,"lt")
            if t<b and int(t*8)%2==0:
                cx=x0+(58 if kind=="cmd" else 62)+ (fo if kind=="cmd" else m(28)).getlength(show)
                d.rectangle((cx+2,yy+3,cx+15,yy+31),fill=rgba(CYAN_HI,0.85))
            yy+=54 if kind=="cmd" else 50
    # the promise
    kb=eob(lin(t,ws("never")-0.22,ws("never")+0.42),1.9)
    if kb>0.01:
        box=(MARGIN,1012,W-MARGIN,1268)
        card(d,box,26,(12,26,26),0.94*kb,MINT,0.55*kb,2)
        put_glow(base,540,1140,(30,120,96),520,0.16*kb)
        cx=MARGIN+92; cy=1094
        r=34
        d.ellipse((cx-r,cy-r,cx+r,cy+r),outline=rgba(MINT,0.9*kb),width=4)
        d.line((cx-r*0.62,cy+r*0.62,cx+r*0.62,cy-r*0.62),fill=rgba(MINT,0.9*kb),width=4)
        text(d,(cx+64,cy),"NOTHING UPLOADED",f(42,"bold"),MINT,kb,3,"lm")
        text(d,(MARGIN+40,1178),"your code never leaves your machine",
             f(34,"med"),WHITE,kb*0.92,0,"lt")
        text(d,(MARGIN+40,1222),"read-only MCP · runs on localhost · no telemetry",
             m(26),MUTED,kb*0.9,0,"lt")

# ================= 4. IT NEVER RANKS ==================
FAKE=[("★★★★★","best-practices-pro"),("★★★★☆","ultimate-ai-toolkit"),
      ("★★★★☆","top-10-skills-2026")]
def s_ranks(base,d,t,t0=16.20):
    eyebrow(base,d,"THE UNUSUAL PART",t,t0)
    k,dy=enter(t,t0+0.06,0.36,26)
    text(d,(MARGIN,340+dy),"it never ranks.",f(78,"bold"),WHITE,k,0,"lt")
    k2,dy2=enter(t,ws("recommends.")-0.28,0.36,26)
    text(d,(MARGIN,434+dy2),"it never recommends.",f(78,"bold"),CYAN,k2,0,"lt")
    # the thing it refuses to be
    kp,dyp=enter(t,t0+0.62,0.4,26)
    if kp>0.01:
        box=(MARGIN,584+dyp,W-MARGIN,916+dyp); x0,y0,x1,y1=box
        strike=eo3(lin(t,ws("recommends.")+0.10,ws("recommends.")+0.66))
        oc=mix(BORDER,RED,strike)
        card(d,box,22,(20,17,20),0.9*kp,oc,0.75*kp,2)
        text(d,(x0+30,y0+46),"RECOMMENDED FOR YOU",f(32,"bold"),
             mix(MUTED,RED,strike*0.7),kp,3,"lm")
        hline(d,x0+30,x1-30,y0+84,BORDER,0.8*kp,2)
        for i,(st,nm) in enumerate(FAKE):
            yy=y0+128+i*62
            text(d,(x0+30,yy),st,m(28),mix(AMBER,(90,70,60),strike),kp*0.9,2,"lm")
            text(d,(x0+180,yy),nm,m(29),mix(MUTED,(96,80,84),strike),kp*0.9,0,"lm")
        if strike>0.01:
            for i in range(3):
                yy=y0+128+i*62
                d.line((x0+30,yy,x0+30+(x1-x0-60)*eo3(min(1,strike*1.4-i*0.18)),yy),
                       fill=rgba(RED,0.85*strike),width=4)
            r=44; cx,cy=x1-84,y0+46
            d.line((cx-r*0.5,cy-r*0.5,cx+r*0.5,cy+r*0.5),fill=rgba(RED,strike),width=7)
            d.line((cx-r*0.5,cy+r*0.5,cx+r*0.5,cy-r*0.5),fill=rgba(RED,strike),width=7)
    kk,dyk=enter(t,ws("picks;")-0.34,0.36,24)
    if kk>0.01:
        box=(MARGIN,986+dyk,W-MARGIN,1150+dyk); x0,y0,x1,y1=box
        card(d,box,22,(12,26,30),0.95*kk,CYAN,0.6*kk,2)
        put_glow(base,540,1068+dyk,(36,132,166),470,0.16*kk)
        text(d,(540,y0+58),"YOUR AGENT PICKS",f(46,"bold"),CYAN_HI,kk,3,"mm")
        text(d,(540,y0+118),"it inspects the project, then chooses exact skill IDs",
             m(26),MUTED,kk,0,"mm")

# ================= 5. THE CHAIN ==================
CHAIN=[("YOUR AGENT PICKS","exact skill IDs, chosen from the full catalog",20.90),
       ("aas-stack.json","validated in memory, plus an evidence sidecar",ws("stack")-0.10),
       ("IMMUTABLE PLAN","aas stack validate · aas stack plan",ws("immutable")+0.10)]
def s_chain(base,d,t,t0=20.72):
    eyebrow(base,d,"WHAT AAS ACTUALLY DOES",t,t0)
    BH=176; GAP=64; y0=364
    for i,(title,sub,ts) in enumerate(CHAIN):
        k,dy=enter(t,ts,0.34,28)
        if k<=0.01: continue
        yy=y0+i*(BH+GAP)+dy
        mono = i==1
        col=CYAN if i<2 else MINT
        card(d,(MARGIN,yy,W-MARGIN,yy+BH),24,(14,20,25),0.95*k,col,0.55*k,2)
        put_glow(base,540,yy+BH/2,(30,110,140) if i<2 else (30,120,96),520,0.10*k)
        tf=m(48,"bold") if mono else f(48,"bold")
        text(d,(540,yy+62),title,tf,WHITE if not mono else CYAN_HI,k,0 if mono else 2,"mm")
        text(d,(540,yy+124),sub,m(26),MUTED,k*0.92,0,"mm")
        if i<2:
            ka=eo3(lin(t,ts+0.20,ts+0.52))
            if ka>0.01:
                ay=yy+BH; h=GAP*ka
                d.line((540,ay+8,540,ay+8+h),fill=rgba(CYAN,0.8*ka),width=4)
                if ka>0.85:
                    d.polygon([(540,ay+GAP+2),(528,ay+GAP-14),(552,ay+GAP-14)],
                              fill=rgba(CYAN,0.9))
    # the stamp
    kst=eob(lin(t,ws("written.")-0.42,ws("written.")+0.34),2.2)
    if kst>0.01:
        yy=y0+2*(BH+GAP)+BH
        fo=f(52,"bold"); txt="NOTHING WRITTEN YET"
        wd=tw(txt,fo,4)+64
        st=Image.new("RGBA",(int(wd)+40,140),(0,0,0,0)); sd=ImageDraw.Draw(st)
        sd.rounded_rectangle((20,34,20+wd,106),radius=12,
                             fill=rgba((12,26,26),0.90),outline=rgba(MINT,0.95),width=4)
        text(sd,(20+wd/2,70),txt,fo,MINT,1.0,4,"mm")
        st=st.rotate(-7,resample=Image.BICUBIC,expand=False)
        if kst<1.0:
            st.putalpha(st.getchannel("A").point(lambda v:int(v*min(1,kst))))
        base.alpha_composite(st,(int(540-st.width/2),int(yy-st.height/2)))
    k4,_=enter(t,ws("audit")+0.10,0.4,0)
    if k4>0.01:
        text(d,(540,1310),"audit it before a single file changes",
             m(28),MUTED,k4,0,"mt")

# ================= 6. HARNESSES ==================
HARN=[("CLAUDE CODE",ws("Claude")),("CODEX",ws("Codex,")),("CURSOR",ws("Cursor,")),
      ("GEMINI",ws("Gemini,")),("COPILOT",ws("Copilot."))]
def s_harness(base,d,t,t0=25.05):
    eyebrow(base,d,"WORKS WITH",t,t0)
    for i,(nm,ts) in enumerate(HARN):
        k,dy=enter(t,t0+0.16+i*0.09,0.30,24)
        if k<=0.01: continue
        lit=eo3(lin(t,ts-0.10,ts+0.26))
        y=376+i*140+dy
        card(d,(MARGIN,y,W-MARGIN,y+116),22,CARD,(0.5+0.45*lit)*k,
             mix(BORDER,CYAN,lit),(0.55+0.4*lit)*k,2)
        if lit>0.4: put_glow(base,540,y+58,(36,132,166),430,0.13*lit)
        text(d,(MARGIN+40,y+58),nm,f(44,"bold"),mix((96,104,116),WHITE,lit),k,2,"lm")
        rr=13; cx=W-MARGIN-46
        d.ellipse((cx-rr,y+58-rr,cx+rr,y+58+rr),outline=rgba(mix(BORDER,MINT,lit),0.8*k),width=2)
        if lit>0.5:
            d.line([(cx-6,y+59),(cx-1,y+64),(cx+7,y+52)],fill=rgba(MINT,lit),width=4,joint="curve")
    k2,_=enter(t,ws("Gemini,"),0.4,0)
    if k2>0.01:
        text(d,(540,1122),"+ ANTIGRAVITY · KIRO · OPENCODE · AUTOHAND CODE",
             f(27,"bold"),DIM,k2,4,"mt")

# ================= 7. PROOF ==================
BARS=[("development",175),("cloud",146),("ai-ml",130),("security",81),("business",69)]
def s_proof(base,d,t,t0=31.50):
    eyebrow(base,d,"THE NUMBERS",t,t0)
    kb=eob(lin(t,ws("MIT,")-0.12,ws("MIT,")+0.48),2.0)
    if kb>0.01: pill(d,540,346,"MIT · FREE · OPEN CATALOG",f(31,"bold"),MINT,kb,track=5)
    ts=ws("forty-five")-0.18
    p=eo4(lin(t,ts,ts+1.35))
    if p>0.0:
        put_glow(base,540,486,(36,132,166),470,0.16*min(1,p*3))
        grad_text(base,(540,486),f"{int(45083*p):,}",f(128,"bold"),CYAN_HI,CYAN,min(1,p*4),"mm")
        text(d,(540,572),"GITHUB STARS",f(30,"bold"),MUTED,min(1,p*4),5,"mm")
    k,dy=enter(t,t0+0.55,0.4,24)
    if k>0.01:
        text(d,(MARGIN,660+dy),"101 CATEGORIES · BIGGEST FIVE",f(27,"bold"),DIM,k,4,"lt")
        mx=175.0; x0=MARGIN; x1=W-MARGIN-140
        for i,(nm,v) in enumerate(BARS):
            kk=eo3(lin(t,t0+0.72+i*0.16,t0+1.12+i*0.16))
            if kk<=0.01: continue
            y=724+i*84
            text(d,(x0,y+18),nm,m(29),MUTED,kk,0,"lm")
            bx=x0+310
            d.rounded_rectangle((bx,y,x1,y+36),radius=8,fill=rgba((22,27,33),0.9*kk))
            w2=(x1-bx)*(v/mx)*eo3(kk)
            d.rounded_rectangle((bx,y,bx+max(10,w2),y+36),radius=8,fill=rgba(CYAN,0.85*kk))
            text(d,(W-MARGIN,y+18),str(v),m(29,"bold"),CYAN_HI,kk,0,"rm")
        k3=eo3(lin(t,t0+1.9,t0+2.3))
        text(d,(MARGIN,1196),"2,019 playbooks · 60 plugin packs · v15.15.0 · created 14 Jan 2026",
             m(26),DIM,k3,0,"lt")

# ================= 8. INSTALL ==================
CMD=[("npx agentic-awesome-skills \\",       34.72,35.40),
     ("  --skills brainstorming \\",         35.42,35.92),
     ("  --dry-run",                         35.94,36.30)]
def s_install(base,d,t,t0=34.58):
    eyebrow(base,d,"ONE COMMAND",t,t0)
    k,dy=enter(t,t0+0.06,0.30,24)
    if k<=0.01: return
    box=(MARGIN,346+dy,W-MARGIN,714+dy); x0,y0,x1,y1=box
    card(d,box,24,(13,17,22),0.95*k,BORDER,0.9*k,2)
    for i,c in enumerate([(255,95,86),(255,189,46),(39,201,63)]):
        d.ellipse((x0+30+i*30,y0+25,x0+44+i*30,y0+39),fill=rgba(c,0.5*k))
    text(d,(x1-28,y0+32),"any harness",m(24),DIM,k,0,"rm")
    hline(d,x0,x1,y0+62,BORDER,0.8*k,2)
    fo=m(31); yy=y0+108
    for txt,a,b in CMD:
        if t<a-0.02: break
        n=int(len(txt)*clamp((t-a)/(b-a))); show=txt if t>=b else txt[:n]
        if not txt.startswith(" "): text(d,(x0+30,yy),"›",m(31,"bold"),CYAN,1.0,0,"lt")
        dry = txt.strip().startswith("--dry-run")
        text(d,(x0+58,yy),show,fo,MINT if dry else WHITE,1.0,0,"lt")
        if t<b and int(t*8)%2==0:
            cx=x0+58+fo.getlength(show)
            d.rectangle((cx+2,yy+3,cx+15,yy+31),fill=rgba(CYAN_HI,0.85))
        yy+=54
    ok=eo3(lin(t,36.36,36.66))
    if ok>0.01:
        text(d,(x0+30,y1-58),"✓  shows what WOULD change · writes nothing",
             m(27,"bold"),MINT,ok,0,"lm")
    k2,dy2=enter(t,t0+0.9,0.36,20)
    if k2>0.01:
        for i,(a_,b_) in enumerate([("dry run first","always"),
                                    ("then review","aas-stack.json"),
                                    ("then apply","only if you agree")]):
            kk=eo3(lin(t,t0+0.95+i*0.15,t0+1.30+i*0.15))
            y=800+i*76
            d.ellipse((MARGIN,y-5,MARGIN+10,y+5),fill=rgba(CYAN,kk))
            text(d,(MARGIN+30,y),a_,f(32,"bold"),WHITE,kk,2,"lm")
            text(d,(MARGIN+330,y),b_,m(27),DIM,kk,0,"lm")

# ================= 9. END ==================
def s_end(base,d,t,t0=37.30):
    k=eo3(lin(t,t0,t0+0.34)); kb=eob(lin(t,t0,t0+0.55),1.4)
    put_glow(base,540,600,(36,132,166),820,0.30*k+0.04*pulse(t,2.5))
    grad_text(base,(540,596),"AAS",f(int(236*(0.92+0.08*kb)),"bold"),WHITE,PALE,k,"mm")
    text(d,(540,760),"Agentic Awesome Skills",m(38),MUTED,k,3,"mm")
    k2=eo3(lin(t,t0+0.22,t0+0.56))
    hline(d,540-int(140*k2),540+int(140*k2),838,MINT,0.9*k2,4)
    text(d,(540,900),"github.com/sickn33",m(42,"bold"),WHITE,k2,0,"mt")
    text(d,(540,958),"agentic-awesome-skills",m(36),CYAN,k2,0,"mt")
    k3=eo3(lin(t,t0+0.44,t0+0.80))
    if k3>0.01:
        fo=f(35,"bold"); txt="SAVE THIS FOR YOUR NEXT SETUP"
        wd=tw(txt,fo,4)+72; x0=540-wd/2
        d.rounded_rectangle((int(x0),1094,int(x0+wd),1176),radius=41,fill=rgba(CYAN,0.94*k3))
        text(d,(540,1136),txt,fo,(6,18,22),k3,4,"mm")
        put_glow(base,540,1135,(36,132,166),320,0.16*k3)
    k4=eo3(lin(t,t0+0.70,t0+1.05))
    if k4>0.01:
        lab="WATCH AGAIN"; fl=f(28,"bold"); wd=tw(lab,fl,5)
        text(d,(540-wd/2-38,1250),"↻",m(30),DIM,k4,0,"lm")
        text(d,(540+18,1250),lab,fl,DIM,k4,5,"mm")

# ================= dispatch ==================
def frame(t):
    base=BASE.copy()
    ov=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(ov)
    n,a,b=scene_at(t)
    if   n=="hook":    s_hook(ov,d,t)
    elif n=="title":   s_title(ov,d,t,a)
    elif n=="mcp":     s_mcp(ov,d,t,a)
    elif n=="ranks":   s_ranks(ov,d,t,a)
    elif n=="chain":   s_chain(ov,d,t,a)
    elif n=="harness": s_harness(ov,d,t,a)
    elif n=="proof":   s_proof(ov,d,t,a)
    elif n=="install": s_install(ov,d,t,a)
    else:              s_end(ov,d,t,a)
    chrome(base,d,t)
    cut_sweep(ov,d,t)
    if n!="end": captions(ov,d,t)
    base.alpha_composite(ov)
    return base

# ---- sound design (read by sfx.py; plain data, keep it subtle) ------------
_BIG={5.60,37.30}
SFX=(
  [{"t":0.0,"kind":"sweep","amp":0.19,"dur":FREEZE},             # the fast scroll
   {"t":FREEZE,"kind":"thump","amp":0.26,"dur":0.5,"freq":50.0}] +  # ...slams stop
  [{"t":FREEZE+0.02+j*0.055,"kind":"tick","amp":0.055,"tone":3200.0}
     for j in range(len(SLOTS))] +                               # ten picks land
  [{"t":c-0.30,"kind":"swish","amp":0.15} for c in CUTS] +
  [{"t":c,"kind":"thump","amp":0.29 if c in _BIG else 0.20,
    "dur":0.55 if c in _BIG else 0.34,
    "freq":46.0 if c in _BIG else 58.0} for c in CUTS] +
  [{"t":ts,"kind":"tick","amp":0.07,"tone":3200.0}
     for ts in (ws("catalog")-0.10, ws("catalog")+0.42, ws("catalog")+0.84)] +
  [{"t":ts,"kind":"tick","amp":0.085} for _,_,ts in CHAIN] +
  [{"t":ws("written.")-0.34,"kind":"thump","amp":0.20,"dur":0.4,"freq":54.0}] +
  [{"t":ts,"kind":"tick","amp":0.065,"tone":3200.0} for _,ts in HARN] +
  [{"t":ws("forty-five")-0.18,"kind":"tick","amp":0.075,"tone":3200.0},
   {"t":36.36,"kind":"tick","amp":0.09,"tone":3200.0}]
)
