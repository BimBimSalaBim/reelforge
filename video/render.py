#!/usr/bin/env python3
"""Write a storyboard's frames as raw RGBA to stdout, for piping into ffmpeg.

    python3 render.py ecc > /dev/null      # timing check
    python3 render.py ecc | ffmpeg ...     # see make.sh

Expect ~2-3 fps, so ~7-9 min for a 40s reel. Always run it in the background.
"""
import sys, os, time, argparse
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE); sys.path.insert(0,os.path.join(HERE,"storyboards"))
ap=argparse.ArgumentParser(); ap.add_argument("storyboard")
ap.add_argument("--fps",type=int,default=30)
ap.add_argument("--only",type=float,nargs=2,metavar=("T0","T1"),
                help="render just this time range (still writes from T0)")
A=ap.parse_args()
sb=__import__(A.storyboard)
fps=getattr(sb,"FPS",A.fps)
t0,t1=(A.only if A.only else (0.0,sb.TOTAL))
n0,n1=int(round(t0*fps)),int(round(t1*fps))
out=sys.stdout.buffer; start=time.time()
for i in range(n0,n1):
    out.write(sb.frame(i/fps).tobytes())
    if (i-n0)%120==0:
        el=time.time()-start
        print(f"  {i-n0}/{n1-n0}  {el:5.1f}s  ({(i-n0+1)/max(el,.01):.1f} fps)",
              file=sys.stderr,flush=True)
out.flush()
print(f"  done {n1-n0} frames in {time.time()-start:.1f}s",file=sys.stderr)
