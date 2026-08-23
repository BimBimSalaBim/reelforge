# ---------------------------------------------------------------
# anydoc.py -- "anydoc" on the SLAB template. Firecrawl's flame against
# paper and ink. Six fields, one idea each; the whole reel is one number
# (< 5 ms) and one surprise (it reads the bytes).
# ---------------------------------------------------------------
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kit, slab as S
from kit import W, H, f, m, clamp, lin, eo3, eo4, eob, rgba, mix, tw, text
from slab import Theme, CX, CR, ink_for
from timing import Timing

NAME    = "anydoc"
AUDIO   = "anydoc.mp3"
PHRASES = "phrases/anydoc.txt"
TOTAL   = 45.2
FPS     = 30
CAPTIONS = False          # off by default, see DEVELOPMENT.md

_T = Timing(NAME); ws, we = _T.ws, _T.we
SLUG = "firecrawl/anydoc"

TH = Theme(fields=[(238,232,220),(24,24,27),(240,238,232),(232,84,42),
                   (240,238,232),(18,74,224),(24,24,27),(238,232,220)],
           mark=(232,84,42))
TH.apply()

SC = [("hook",0.00,6.00),("what",6.00,9.05),("scroll",9.05,15.00),
      ("fast",15.00,23.10),("model",23.10,30.10),("bytes",30.10,35.15),
      ("close",35.15,41.00),("end",41.00,TOTAL)]

#: The repo page, captured by app/render/reposhot.py at reel width. Panned
#: under the narration rather than inserted as a segment: the audio is
#: word-aligned, so adding time would desync every cut after it.
#:
#: This file is GENERATED and is not in the repository -- assets/ is ignored
#: along with the rest of the job output. `slab.scroll` returns False when it
#: is missing and the scene simply draws its chip on a bare field, so this
#: storyboard still imports and renders as a worked example without it.
REPO_SHOT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "assets", "anydoc-repo.png")
def scene_at(t):
    for i,(n,a,b) in enumerate(SC):
        if a<=t<b: return i,n,a,b
    return len(SC)-1,SC[-1][0],SC[-1][1],SC[-1][2]
CUTS = [a for _,a,_ in SC[1:]]

def s_hook(ov,d,t,t0,i):
    S.statement(ov,d,["Your agent hits","a .docx","and gives up."],t,0.10,TH,i,size=114)
    S.rows(ov,d,[("report.docx","unsupported"),("slides.pptx","unsupported")],
           t,ws("gives")-0.20,TH,i,y=1000,h=126,lsize=44,vsize=32,lit=[1,1])

def s_what(ov,d,t,t0,i):
    # keyed to the scene, not to "Anydoc" -- at that word it had 0.9s
    S.statement(ov,d,["Any office file","to clean Markdown."],t,t0+0.05,TH,i,size=106)


def s_scroll(ov,d,t,t0,i):
    """B-roll: the repo page panned top to bottom while the narration lists
    the formats. The page shows them better than a rendered row would."""
    S.scroll(ov,d,t,t0+0.25,(15.00-9.05)-0.25,TH,i,REPO_SHOT,
             label="firecrawl/anydoc")
    # a chip is a solid fill, so it stays legible over whatever it lands on
    S.chip(ov,d,(CX,1444),"npx @firecrawl/anydoc report.docx",
           t,ws("Markdown")-0.30,TH,i,size=30)

def s_fast(ov,d,t,t0,i):
    S.statement(ov,d,["Median: under","five milliseconds."],t,t0+0.05,TH,i,size=104)
    S.figure(ov,d,"< 5 ms","PER DOCUMENT",t,ws("milliseconds")-0.30,TH,i,y=860,size=190,
             note="pure Rust · no ML models · no external services")
    # keyed to "Rust", not "machine": at "machine" it had 0.8s before the cut
    S.chip(ov,d,(CX,1450),"nothing leaves your machine",t,ws("Rust")+0.20,TH,i,size=34)

def s_model(ov,d,t,t0,i):
    S.statement(ov,d,["One model in.","One writer out."],t,t0+0.10,TH,i,size=118)
    S.rows(ov,d,[("every format","one document model"),
                 ("every output","one Markdown writer")],
           t,ws("format")-0.24,TH,i,y=940,h=130,lsize=44,vsize=32,lit=[1,1])
    S.chip(ov,d,(CX,1430),"same shape out, whatever went in",
           t,ws("consistent")-0.26,TH,i,size=34)

def s_bytes(ov,d,t,t0,i):
    S.statement(ov,d,["It reads the bytes,","not the extension."],t,t0+0.10,TH,i,size=104)
    S.pair(ov,d,("EXTENSION SAYS",".txt",False),("BYTES SAY","%PDF-",True),
           t,ws("bytes")-0.10,TH,i,y=940,size=120)
    S.chip(ov,d,(CX,1420),"a mislabelled file still parses",
           t,ws("mislabelled")-0.26,TH,i,size=34)

def s_close(ov,d,t,t0,i):
    S.statement(ov,d,["MIT.","19 days old."],t,t0+0.10,TH,i,size=124)
    S.figure(ov,d,"17,849","STARS",t,ws("seventeen")-0.28,TH,i,y=880,size=172)
    S.chip(ov,d,(CX,1420),"npx skills add firecrawl/anydoc",
           t,ws("skill")-0.26,TH,i,size=34)

def frame(t):
    i,n,a,b = scene_at(t)
    base = S.field_for(TH,i).copy()
    ov = Image.new("RGBA",(W,H),(0,0,0,0)); d = ImageDraw.Draw(ov)
    {"hook":s_hook,"what":s_what,"scroll":s_scroll,"fast":s_fast,
     "model":s_model,"bytes":s_bytes,
     "close":s_close}.get(n,lambda *_: None)(ov,d,t,a,i)
    if n=="end":
        S.endcard(ov,d,t,a,TH,i,"anydoc","office files to Markdown",
                  "github.com/firecrawl/anydoc","SAVE THIS FOR YOUR AGENT")
    # cut BEFORE chrome -- the band is opaque and would blank the rail
    S.cut(ov,d,t,CUTS,TH,lambda tt: scene_at(tt)[0])
    S.rail(ov,d,t,TH,i,len(SC),(t-a)/max(b-a,0.01))
    S.footer(ov,d,TH,i,SLUG,len(SC))
    base.alpha_composite(ov)
    return base

SFX = (
 [{"t":c-0.18,"kind":"paper","amp":0.14} for c in CUTS] +
 [{"t":c,"kind":"slam","amp":0.24,"dur":0.24} for c in CUTS] +
 [{"t":ws("gives")-0.20,"kind":"chime","amp":0.07,"tone":392.0},
  {"t":ws("Anydoc")-0.20,"kind":"chime","amp":0.08,"tone":523.0},
  {"t":ws("milliseconds")-0.30,"kind":"riser","amp":0.10},
  {"t":ws("machine")-0.30,"kind":"chime","amp":0.07,"tone":659.0},
  {"t":ws("format")-0.24,"kind":"chime","amp":0.07,"tone":440.0},
  {"t":ws("bytes")-0.10,"kind":"riser","amp":0.11},
  {"t":ws("mislabelled")-0.26,"kind":"chime","amp":0.08,"tone":698.0},
  {"t":ws("seventeen")-0.28,"kind":"riser","amp":0.09},
  {"t":ws("skill")-0.26,"kind":"chime","amp":0.07,"tone":523.0}]
)
