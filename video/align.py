#!/usr/bin/env python3
"""Force-align a known narration script to its recorded audio.

Two modes:

  probe   python3 align.py probe ../ECC.mp3
          Prints the voiced phrases ffmpeg-free VAD found, with durations.
          Use this to WRITE the phrases file: one line per detected segment.

  build   python3 align.py build ecc ../ECC.mp3 phrases/ecc.txt
          Requires len(phrases) == len(segments). Distributes each phrase's
          words across its segment by syllable weight and writes
          build/ecc.timing.json  ->  {duration, segments, phrases, words[]}

Why this and not an ASR model: the transcript is already known exactly, so the
only unknown is *when*. Anchoring each phrase to a real silence boundary is
more accurate than word timestamps from a small ASR model, and has no deps.

If the counts do not match, adjust in this order:
  1. re-read the probe output and re-split the phrases file (most common fix --
     the narrator paused where you did not expect)
  2. --min-sil (default 220ms): lower it to split more, raise it to merge
  3. --drop (default 32dB below peak): the voiced/silent threshold
Sanity check before rendering: every phrase boundary should land on a real
clause or sentence boundary. If it does not, the split is wrong.
"""
import sys, os, re, json, wave, subprocess, argparse
import numpy as np

HERE=os.path.dirname(os.path.abspath(__file__))
def ffmpeg():
    return tool("ffmpeg")
def tool(name):
    p=os.path.join(HERE,"bin",name)
    if os.path.exists(p): return p
    from shutil import which
    w=which(name)
    if w: return w
    sys.exit(f"{name} not found. Expected video/bin/{name} (vendored) or on PATH.\n"
             f"Restore with:  brew install ffmpeg\n"
             f"           or: npm i ffmpeg-static ffprobe-static && cp the binaries into video/bin/")

def decode16k(src):
    out=os.path.join(HERE,"build","_align16k.wav")
    subprocess.run([ffmpeg(),"-y","-v","error","-i",src,"-ac","1","-ar","16000",
                    "-f","wav",out],check=True)
    w=wave.open(out); n=w.getnframes(); sr=w.getframerate()
    a=np.frombuffer(w.readframes(n),dtype=np.int16).astype(np.float32)/32768.0
    return a,sr,n/sr

def segments(a,sr,drop=32.0,min_sil_ms=220,min_dur_ms=120):
    hop=int(0.010*sr); win=int(0.025*sr)
    rms=np.array([np.sqrt(np.mean(a[i:i+win]**2)) for i in range(0,len(a)-win,hop)])
    db=20*np.log10(np.maximum(rms,1e-8))
    voiced=db>(db.max()-drop); minsil=int(min_sil_ms/10)
    segs=[];i=0
    while i<len(voiced):
        if voiced[i]:
            j=i
            while j<len(voiced):
                if not voiced[j]:
                    k=j
                    while k<len(voiced) and not voiced[k]: k+=1
                    if k-j>=minsil: break
                    j=k
                else: j+=1
            segs.append((round(i*hop/sr,3),round(j*hop/sr,3))); i=j
        else: i+=1
    # Drop runs too short to be a spoken phrase. colibri.mp3 has a 0.02s click
    # at 16.16 that survived every --drop threshold and would otherwise have to
    # be assigned a word. No shipped reel has a segment under 0.20s, so 120ms
    # is a no-op for all of them -- verified before this was added.
    return [(a_,b_) for a_,b_ in segs if (b_-a_)*1000.0 >= min_dur_ms]

# ---- spoken-length model: seconds of phonation per word ----------------
VOWELS="aeiouy"
# initialisms and oddities the syllable counter gets wrong
SPOKEN={"MCP":3,"AAS":3,"ECC":3,"npx":3,"MIT":3,"CLI":3,"API":3,"AI":2,
        "read-only":3,"open-source":3,"TDD":3,"URL":3,"SDK":3,"IDE":3,
        # the syllable counter reads these wrong: GPQA is spoken as four
        # letters, OSWorld as three, and it hears five vowel groups in
        # "LiveCodeBench" and four in "natively".
        "GPQA":4,"OSWorld":3,"LiveCodeBench":3,"natively":3,
        # LTX-2.5: initialisms, plus four the counter mis-reads. Adding
        # "Apache" also changes qwen3-8-27b, which speaks it -- the shipped
        # mp4 stays valid, but a rebuild shifts that phrase ~0.1s (more
        # accurately: Apache is a-PATCH-ee, three syllables, not two).
        "LTX":3,"VAE":3,"NVFP":4,"ComfyUI":4,"Apache":3,
        "visual":3,"revenue":3,"distilled":2,
        # Muse Glimmer-30B. None of these appear in an already-shipped
        # phrases file, so no existing reel's timing moves.
        "DFlash":2,"RTX":3,"AIME":4,"quantized":2,"Ninety-four":3,
        # AgenticSeek. "APIs" is ay-pee-eye-ess and "G-P-L" is three letters,
        # both of which the counter reads as one or two. "decides" is de-CIDES,
        # two syllables, not the three the vowel-group rule finds -- that word
        # also appears in ruflo's phrases, so a ruflo REBUILD shifts one phrase
        # by ~0.1s. The shipped ruflo mp4 stays valid.
        "APIs":4,"GPU":3,"G-P-L":3,"classifier":4,"gigabytes":3,"decides":2,
        # NemoClaw. "NVIDIA" is en-VID-ee-uh and "2.0" is two-point-oh, both of
        # which the vowel-group rule under-counts; the -ed and -ure words it
        # over-counts. "filesystem" also appears in phrases/deer-flow.txt, so a
        # DEER-FLOW REBUILD shifts that phrase ~0.1s. Its shipped mp4 is fine.
        "NVIDIA":4,"2.0":3,"postures":2,"balanced":2,"enforced":2,
        "hardened":2,"reference":3,"filesystem":3,"open-sourced":3,
        # The Ledger set: caveman, graphify, colibri, odysseus. Initialisms
        # the counter reads as one (SQL, LLM, PDFs, VRAM), and -ed/-ly words
        # it over-counts. "ninety" also appears in qwen3-8-27b and
        # muse-glimmer-30b, so a REBUILD of either shifts one phrase ~0.1s;
        # both shipped mp4s are unaffected.
        "SQL":3,"LLM":3,"PDFs":4,"VRAM":2,"Odysseus":4,
        "caveman-speak":3,"nineteen":2,"ninety":2,"recoverable":5,
        "labelled":2,"inferred":2,"hierarchy":4,"quietly":3,
        # syllables() strips non-a-z, so the accent vanishes and "Colibrì"
        # reads as two. It is co-lee-BREE.
        "Colibrì":3,
        # The Slab set: anydoc, grok-build, qm, openworker, mempalace,
        # career-ops. Mostly initialisms with no vowels for the counter to
        # find. "PDF" also appears in phrases/open-design.txt, so an
        # OPEN-DESIGN REBUILD shifts that one phrase ~0.1s; its shipped mp4 is
        # unaffected. ("OpenAI" does NOT collide -- open-design says
        # "OpenAI-compatible", which weight() sees as a different token.)
        "dot-docx":3,"mislabelled":3,"ML":2,"CI":2,"QM":2,
        "OpenAI":4,"Ninety-six":3,"CV":2,"PDF":3}
def syllables(word):
    s=re.sub(r'[^a-z]','',word.lower())
    if not s: return 1
    c=0;prev=False
    for ch in s:
        v=ch in VOWELS
        if v and not prev: c+=1
        prev=v
    if s.endswith('e') and c>1: c-=1
    return max(1,c)
def weight(word):
    core=word.strip('.,:;"\'!?')
    if core in SPOKEN:       b=SPOKEN[core]
    elif core.isdigit():     b={1:1,2:3,3:4}.get(len(core),5)
    else:                    b=syllables(core)
    w=0.16+0.115*b
    if word.endswith(('.',':',';','!','?')): w+=0.06
    elif word.endswith(','):                 w+=0.035
    return w

def main():
    ap=argparse.ArgumentParser(add_help=False)
    ap.add_argument("mode",choices=["probe","build"])
    ap.add_argument("rest",nargs="*")
    ap.add_argument("--drop",type=float,default=32.0)
    ap.add_argument("--min-sil",type=int,default=220)
    A=ap.parse_args()
    if A.mode=="probe":
        src=A.rest[0]
        a,sr,dur=decode16k(src)
        segs=segments(a,sr,A.drop,A.min_sil)
        print(f"# {os.path.basename(src)}  {dur:.2f}s  {len(segs)} voiced phrases")
        print(f"# drop={A.drop}dB min-sil={A.min_sil}ms")
        print("# write phrases/<name>.txt with exactly this many non-comment lines")
        for k,(s,e) in enumerate(segs):
            print(f"[{k:2d}] {s:6.2f}-{e:6.2f}  ({e-s:4.2f}s)")
        return
    name,src,phrfile=A.rest[0],A.rest[1],A.rest[2]
    a,sr,dur=decode16k(src)
    segs=segments(a,sr,A.drop,A.min_sil)
    phrases=[l.strip() for l in open(phrfile) if l.strip() and not l.lstrip().startswith("#")]
    if len(phrases)!=len(segs):
        print(f"MISMATCH: {len(segs)} voiced phrases in audio, {len(phrases)} lines in "
              f"{phrfile}\n",file=sys.stderr)
        for k in range(max(len(segs),len(phrases))):
            s=f"{segs[k][0]:6.2f}-{segs[k][1]:6.2f} ({segs[k][1]-segs[k][0]:4.2f}s)" if k<len(segs) else " "*22
            p=phrases[k] if k<len(phrases) else "<missing>"
            print(f"  [{k:2d}] {s}  {p}",file=sys.stderr)
        sys.exit(1)
    words=[]
    for (s,e),ph in zip(segs,phrases):
        ws=ph.split(); cs=[weight(x) for x in ws]; tot=sum(cs); t=s
        for x,c in zip(ws,cs):
            d=(e-s)*c/tot
            words.append({"w":x,"s":round(t,3),"e":round(t+d,3)}); t+=d
    out=os.path.join(HERE,"build",f"{name}.timing.json")
    json.dump({"duration":dur,"segments":[list(x) for x in segs],
               "phrases":phrases,"words":words},open(out,"w"),indent=1)
    print(f"wrote {out}: {dur:.2f}s, {len(segs)} phrases, {len(words)} words")
    for (s,e),ph in zip(segs,phrases):
        rate=len(ph.split())/(e-s)
        flag="  <-- check: unusually fast" if rate>4.4 else ""
        print(f"  {s:6.2f}-{e:6.2f}  {rate:4.1f} w/s  {ph}{flag}")
if __name__=="__main__": main()
