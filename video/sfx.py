#!/usr/bin/env python3
"""Mix narration + the storyboard's sound-design events into one 48k stereo wav.

    python3 sfx.py ecc

Reads the storyboard's AUDIO, TOTAL and SFX. SFX is plain data so storyboards
need no import:

    SFX = [{"t": 5.50, "kind": "thump", "amp": 0.30, "dur": 0.55, "freq": 46.0},
           {"t": 22.03, "kind": "tick", "amp": 0.085}, ...]

kinds, Bloom set (sbkit storyboards):
       thump (low impact) · swish (short air, put it BEFORE a cut) ·
       tick (UI blip; `tone` to pitch it) · sweep (long riser, `dur`)

kinds, Ledger set (ledger.py storyboards) -- dry and mechanical, no sub-bass,
so a Ledger reel reads as a different film rather than a reskin:
       click (damped transient, one per row) · rule (pen-stroke noise, `dur`) ·
       latch (two-tone mechanical seat, replaces thump on a cut) ·
       shift (short pitched slide, for the index advancing)

kinds, Slab set (slab.py storyboards) -- mid-focused and musical. Slab cuts are
page turns, so they get body without Bloom's sub-bass and without Ledger's dry
click: slam (tight mid impact, the field landing) · paper (broadband page turn,
put it BEFORE a cut) · chime (soft two-note reveal) · riser (short upsweep)

Keep this subtle. Narration is written in untouched and must stay dominant:
totals here peak around 0.45 of full scale, leaving loudnorm room to work.
Anything that draws attention to itself is too loud.
"""
import sys, os, wave, argparse
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE); sys.path.insert(0,os.path.join(HERE,"storyboards"))
from align import tool
import subprocess
SR=48000

def _lp(x,cut):
    al=1.0-np.exp(-2*np.pi*cut/SR); y=np.empty_like(x); acc=0.0
    for i,v in enumerate(x): acc+=al*(v-acc); y[i]=acc
    return y
def _hp(x,cut): return x-_lp(x,cut)

def make_gens(seed=17):
    rng=np.random.RandomState(seed)
    def thump(dur=0.34,freq=58.0,**_):
        t=np.arange(int(dur*SR))/SR; env=np.exp(-t/0.085)
        body=(np.sin(2*np.pi*freq*t*(1-0.25*t/dur))+0.45*np.sin(2*np.pi*freq*1.5*t))*env
        click=_hp(rng.normal(0,1,len(t)),1800)*np.exp(-t/0.006)*0.25
        return (body*0.85+click).astype(np.float32)
    def swish(dur=0.30,**_):
        t=np.arange(int(dur*SR))/SR
        env=(t/dur)**2.2*np.exp(-((t/dur-0.92)**2)/0.06)
        return (_lp(rng.normal(0,1,len(t)),2600)*env*1.5).astype(np.float32)
    def tick(dur=0.05,tone=2100.0,**_):
        t=np.arange(int(dur*SR))/SR; env=np.exp(-t/0.009)
        return ((_hp(rng.normal(0,1,len(t)),1200)*0.55
                 +np.sin(2*np.pi*tone*t)*0.45)*env).astype(np.float32)
    def sweep(dur=2.0,**_):
        t=np.arange(int(dur*SR))/SR
        band=_hp(_lp(rng.normal(0,1,len(t)),5200),420)
        return (band*(t/dur)**1.7*0.9).astype(np.float32)
    # ---- Ledger set --------------------------------------------------
    # Deliberately no energy below ~180 Hz: the Bloom set owns the low end,
    # and keeping it out is most of what makes these two read as different.
    def click(dur=0.035,tone=3200.0,**_):
        t=np.arange(int(dur*SR))/SR; env=np.exp(-t/0.0045)
        body=_hp(rng.normal(0,1,len(t)),2400)*0.7+np.sin(2*np.pi*tone*t)*0.3
        return (_hp(body*env,320)).astype(np.float32)
    def rule(dur=0.10,**_):
        # a pen stroke: band-limited noise that opens and shuts quickly
        t=np.arange(int(dur*SR))/SR; n=len(t)
        env=np.sin(np.pi*np.clip(t/dur,0,1))**1.6
        band=_hp(_lp(rng.normal(0,1,n),7200),1500)
        return (band*env*0.55).astype(np.float32)
    def latch(dur=0.18,freq=240.0,**_):
        # two-tone mechanical seat: a damped body, then a smaller click after
        t=np.arange(int(dur*SR))/SR; n=len(t)
        body=np.sin(2*np.pi*freq*t*(1-0.18*t/dur))*np.exp(-t/0.022)
        out=_hp(body,180)*0.8
        off=int(0.030*SR)
        if n>off:
            t2=t[:n-off]
            out[off:]+=(_hp(rng.normal(0,1,n-off),2600)
                        *np.exp(-t2/0.0035)*0.5).astype(np.float32)
        return out.astype(np.float32)
    def shift(dur=0.12,tone=1500.0,rise=1.7,**_):
        t=np.arange(int(dur*SR))/SR
        env=np.sin(np.pi*np.clip(t/dur,0,1))**1.2
        ph=2*np.pi*tone*(t+0.5*(rise-1.0)*t*t/dur)
        return (_hp(np.sin(ph)*env*1.05,400)).astype(np.float32)
    # ---- Slab set ----------------------------------------------------
    # Energy sits in the 110-400 Hz band: enough body for a full-frame field
    # to feel like it lands, without occupying the sub-bass that Bloom uses or
    # the dry 2-4 kHz click band that Ledger uses. Three distinct registers,
    # so the three templates never sound like each other.
    def slam(dur=0.26,freq=138.0,**_):
        t=np.arange(int(dur*SR))/SR
        body=np.sin(2*np.pi*freq*t*(1-0.22*t/dur))*np.exp(-t/0.048)
        body+=0.35*np.sin(2*np.pi*freq*2.02*t)*np.exp(-t/0.020)
        edge=_hp(rng.normal(0,1,len(t)),1400)*np.exp(-t/0.008)*0.30
        return (_hp(body*0.9+edge,95)).astype(np.float32)
    def paper(dur=0.22,**_):
        t=np.arange(int(dur*SR))/SR; n=len(t)
        env=(t/dur)**1.4*np.exp(-((t/dur-0.80)**2)/0.10)
        band=_hp(_lp(rng.normal(0,1,n),4200),700)
        return (band*env*1.7).astype(np.float32)
    def chime(dur=0.42,tone=523.0,ratio=1.5,**_):
        t=np.arange(int(dur*SR))/SR
        a=np.sin(2*np.pi*tone*t)*np.exp(-t/0.115)
        b=np.sin(2*np.pi*tone*ratio*t)*np.exp(-t/0.085)*0.55
        return (_hp((a+b)*0.42,180)).astype(np.float32)
    def riser(dur=0.30,lo=180.0,hi=900.0,**_):
        t=np.arange(int(dur*SR))/SR; n=len(t)
        env=(t/dur)**2.0
        band=_hp(_lp(rng.normal(0,1,n),int(hi)),int(lo))
        return (band*env*1.2).astype(np.float32)
    return {"thump":thump,"swish":swish,"tick":tick,"sweep":sweep,
            "click":click,"rule":rule,"latch":latch,"shift":shift,
            "slam":slam,"paper":paper,"chime":chime,"riser":riser}

def build(name):
    sb=__import__(name)
    src=os.path.join(HERE,"..",sb.AUDIO)
    narr_wav=os.path.join(HERE,"build",f"{name}.narr48.wav")
    subprocess.run([tool("ffmpeg"),"-y","-v","error","-i",src,"-ac","2","-ar",str(SR),
                    "-c:a","pcm_s16le",narr_wav],check=True)
    w=wave.open(narr_wav)
    a=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768.0
    narr=a.reshape(-1,2)
    N=int(sb.TOTAL*SR)
    buf=np.zeros((N+SR,2),np.float32)
    buf[:len(narr)]+=narr                      # narration, unmodified
    gens=make_gens(getattr(sb,"SFX_SEED",17))
    used={}
    for ev in getattr(sb,"SFX",[]):
        kind=ev["kind"]
        if kind not in gens: sys.exit(f"unknown sfx kind {kind!r}")
        sig=gens[kind](**{k:v for k,v in ev.items() if k not in ("t","kind","amp")})
        i0=int(ev["t"]*SR)
        if i0<0 or i0>=N: continue
        sig=sig[:min(len(sig),len(buf)-i0)]
        buf[i0:i0+len(sig),0]+=sig*ev["amp"]; buf[i0:i0+len(sig),1]+=sig*ev["amp"]
        used[kind]=used.get(kind,0)+1
    pk=float(np.abs(buf).max())
    if pk>0.985: buf*=0.985/pk
    out=os.path.join(HERE,"build",f"{name}.mix.wav")
    o=(np.clip(buf[:N],-1,1)*32767).astype(np.int16)
    wo=wave.open(out,"wb"); wo.setnchannels(2); wo.setsampwidth(2)
    wo.setframerate(SR); wo.writeframes(o.tobytes()); wo.close()
    print(f"wrote {out}  {N/SR:.2f}s  peak={pk:.3f}  events={used}")
    if pk>0.9: print("  warning: peak is high -- sfx amps are probably too hot")
if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("storyboard"); A=ap.parse_args()
    build(A.storyboard)
