#!/usr/bin/env python3
"""Tile frames with each platform's UI chrome drawn on top.

    python3 safecheck.py 'build/_frames/f*.png' out.png

Anything meaningful under a coloured box will be covered by the app. Boxes are
deliberately conservative -- real chrome is a little smaller.
"""
import sys, glob
from PIL import Image, ImageDraw
REELS  = [(0,0,1080,110),(0,1600,1080,1920),(960,1080,1080,1700)]
SHORTS = [(0,0,1080,120),(0,1620,1080,1860),(960,1000,1080,1700)]
outs=[]
for p in sorted(glob.glob(sys.argv[1])):
    im=Image.open(p).convert("RGBA")
    ov=Image.new("RGBA",im.size,(0,0,0,0)); d=ImageDraw.Draw(ov)
    for b in REELS:  d.rectangle(b,fill=(255,0,80,58),outline=(255,0,80,150),width=3)
    for b in SHORTS: d.rectangle(b,fill=(0,140,255,50),outline=(0,140,255,150),width=3)
    im=Image.alpha_composite(im,ov).convert("RGB")
    im.thumbnail((300,534)); outs.append(im)
if not outs: sys.exit("no frames matched")
sh=Image.new("RGB",(len(outs)*306+6,540),(20,20,22))
for i,im in enumerate(outs): sh.paste(im,(6+i*306,3))
sh.save(sys.argv[2]); print("wrote",sys.argv[2])
