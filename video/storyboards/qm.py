# ---------------------------------------------------------------
# qm.py -- "QM" on the SLAB template. Plum and green: one field for the
# personal scope, one for the shared. Scene 3 is the scoped-resource list,
# which is the claim other shared agents cannot make.
# ---------------------------------------------------------------
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kit, slab as S
from kit import W, H, f, m, clamp, lin, eo3, eo4, eob, rgba, mix, tw, text
from slab import Theme, CX, CR, ink_for
from timing import Timing

NAME    = "qm"
AUDIO   = "qm.mp3"
PHRASES = "phrases/qm.txt"
TOTAL   = 43.1
FPS     = 30
CAPTIONS = False

_T = Timing(NAME); ws, we = _T.ws, _T.we
SLUG = "yc-software/qm"

TH = Theme(fields=[(244,242,238),(58,42,120),(244,242,238),(28,168,120),
                   (58,42,120),(244,242,238)],
           mark=(28,168,120))
TH.apply()

SC = [("hook",0.00,6.40),("what",6.40,15.90),("scoped",15.90,26.30),
      ("vendor",26.30,35.60),("close",35.60,38.90),("end",38.90,TOTAL)]
def scene_at(t):
    for i,(n,a,b) in enumerate(SC):
        if a<=t<b: return i,n,a,b
    return len(SC)-1,SC[-1][0],SC[-1][1],SC[-1][2]
CUTS = [a for _,a,_ in SC[1:]]

def s_hook(ov,d,t,t0,i):
    S.statement(ov,d,["Your agent","knows you.","Not your company."],t,0.10,TH,i,size=112)
    S.rows(ov,d,[("one agent, one memory","whose files?"),
                 ("a whole team in it","whose keys?")],
           t,ws("Slack")-0.30,TH,i,y=1000,h=126,lsize=40,vsize=32,lit=[1,1])

def s_what(ov,d,t,t0,i):
    S.statement(ov,d,["A multiplayer","agent harness."],t,t0+0.05,TH,i,size=122)
    S.rows(ov,d,[("each person","their own workspace"),
                 ("each channel","a shared one")],
           t,ws("Everyone")-0.26,TH,i,y=900,h=134,lsize=44,vsize=32,
           lit=[1.0 if t>=ws("Everyone")-0.10 else 0.0,
                1.0 if t>=ws("channels")-0.10 else 0.0])
    S.chip(ov,d,(CX,1440),"Slack and web, same identity",
           t,ws("projects")-0.34,TH,i,size=34)

SCOPED=[("MEMORY","per person, per room","memory"),
        ("FILES","per scope","files"),
        ("PERMISSIONS","per scope","permissions"),
        ("KEYCHAIN","a view, not the keys","keychain"),
        ("CRONS + SANDBOX","durable, per scope","cron")]
def s_scoped(ov,d,t,t0,i):
    S.statement(ov,d,["Every person.","Every room."],t,t0+0.05,TH,i,size=118)
    S.rows(ov,d,[(a,b) for a,b,_ in SCOPED],
           t,ws("memory")-0.26,TH,i,y=800,h=112,gap=8,stagger=0.0,
           lsize=40,vsize=28,
           lit=[1.0 if t>=ws(c)-0.10 else 0.0 for _,_,c in SCOPED])
    S.chip(ov,d,(CX,1470),"the part most shared agents skip",
           t,ws("skip")-0.36,TH,i,size=32)

def s_vendor(ov,d,t,t0,i):
    S.statement(ov,d,["Not tied to","one vendor."],t,t0+0.05,TH,i,size=124)
    S.rows(ov,d,[("Pi",None),("OpenCode",None),("Codex",None),("Claude Code",None)],
           t,ws("Pi")-0.26,TH,i,y=880,h=118,gap=8,stagger=0.0,lsize=44,
           lit=[1.0 if t>=c-0.10 else 0.0
                for c in (ws("Pi"),ws("OpenCode"),ws("Codex"),ws("Claude"))])
    S.chip(ov,d,(CX,1440),"all drive the same core",
           t,ws("core")-0.30,TH,i,size=34)

def s_close(ov,d,t,t0,i):
    S.statement(ov,d,["MIT."],t,t0+0.05,TH,i,size=132)
    S.figure(ov,d,"14,064","STARS IN THREE WEEKS",t,ws("Fourteen")-0.28,TH,i,
             y=740,size=176)

def frame(t):
    i,n,a,b = scene_at(t)
    base = S.field_for(TH,i).copy()
    ov = Image.new("RGBA",(W,H),(0,0,0,0)); d = ImageDraw.Draw(ov)
    {"hook":s_hook,"what":s_what,"scoped":s_scoped,"vendor":s_vendor,
     "close":s_close}.get(n,lambda *_: None)(ov,d,t,a,i)
    if n=="end":
        S.endcard(ov,d,t,a,TH,i,"QM","a multiplayer agent harness",
                  "github.com/yc-software/qm","SAVE THIS FOR YOUR TEAM")
    S.cut(ov,d,t,CUTS,TH,lambda tt: scene_at(tt)[0])
    S.rail(ov,d,t,TH,i,len(SC),(t-a)/max(b-a,0.01))
    S.footer(ov,d,TH,i,SLUG,len(SC))
    base.alpha_composite(ov)
    return base

SFX = (
 [{"t":c-0.18,"kind":"paper","amp":0.14} for c in CUTS] +
 [{"t":c,"kind":"slam","amp":0.24,"dur":0.24} for c in CUTS] +
 [{"t":ws("Slack")-0.30,"kind":"chime","amp":0.08,"tone":392.0},
  {"t":ws("Everyone")-0.26,"kind":"chime","amp":0.08,"tone":523.0},
  {"t":ws("projects")-0.34,"kind":"chime","amp":0.07,"tone":659.0},
  {"t":ws("skip")-0.36,"kind":"riser","amp":0.10},
  {"t":ws("core")-0.30,"kind":"chime","amp":0.08,"tone":587.0},
  {"t":ws("Fourteen")-0.28,"kind":"riser","amp":0.10}] +
 [{"t":ws(c)-0.10,"kind":"chime","amp":0.05,"tone":294.0+k*44}
    for k,(_,_,c) in enumerate(SCOPED)] +
 [{"t":ws(c)-0.10,"kind":"chime","amp":0.055,"tone":392.0+k*49}
    for k,c in enumerate(("Pi","OpenCode","Codex","Claude"))]
)
