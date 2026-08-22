#!/usr/bin/env bash
# Check a finished file against Reels / Shorts requirements.  ./verify.sh out.mp4
set -uo pipefail
cd "$(dirname "$0")"
F="${1:?usage: ./verify.sh <file.mp4>}"
FF=./bin/ffmpeg;   [ -x "$FF" ] || FF=ffmpeg
FP=./bin/ffprobe;  [ -x "$FP" ] || FP=ffprobe
echo "--- streams ---"
"$FP" -v error -of default=noprint_wrappers=1 -show_entries \
 stream=codec_name,codec_type,width,height,r_frame_rate,pix_fmt,profile,level,nb_frames,sample_rate,channels,color_space \
 -show_entries format=duration,size,bit_rate "$F"
echo "--- decode check (the header can lie; this actually decodes every frame) ---"
# Two renders racing on one output left a file whose container said 51.5s while
# the stream stopped decoding a third of the way in. It passed every other check
# in this script, because nothing here decoded the video. So: decode it.
#
# This compares decoded frames against the CONTAINER's duration, so it catches
# corruption and a stream that dies mid-file. It does NOT catch a cleanly
# truncated render -- agentic-awesome-skills-reel.mp4 is 2.4s short of its
# storyboard and passes this, because 36.57s and 1097 frames agree with each
# other. For that, compare nb_frames to the storyboard's TOTAL*FPS (gotcha 8).
DUR=$("$FP" -v error -show_entries format=duration -of csv=p=0 "$F")
RATE=$("$FP" -v error -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 "$F")
DEC=$("$FP" -v error -select_streams v:0 -count_frames -show_entries stream=nb_read_frames \
      -of csv=p=0 "$F" 2>/dev/null | tail -1)
EXP=$(python3 -c "print(round(float('$DUR')*($RATE)))")
ERR=$("$FF" -v error -i "$F" -map 0:v -f null - 2>&1 | head -3)
if [ "$DEC" = "$EXP" ] && [ -z "$ERR" ]; then
  echo "  OK: decoded $DEC frames, matches ${EXP} expected"
else
  echo "  FAIL: decoded $DEC frames, expected $EXP -- the render did not finish cleanly"
  [ -n "$ERR" ] && echo "$ERR" | sed 's/^/  /'
fi
echo "--- loudness (both platforms normalise to about -14 LUFS) ---"
"$FF" -hide_banner -nostats -i "$F" -map 0:a -filter:a ebur128=peak=true \
  -f null /dev/null 2>&1 | grep -A11 "Summary:" | grep -E "I:|LRA:|Peak"
echo "--- top-level atoms (moov must precede mdat) ---"
python3 - "$F" <<'EOF'
import struct,sys
f=open(sys.argv[1],"rb"); off=0; order=[]
while len(order)<12:
    f.seek(off); h=f.read(8)
    if len(h)<8: break
    sz=struct.unpack(">I",h[:4])[0]; t=h[4:8].decode("latin1","replace")
    order.append(t)
    if sz<8: break
    off+=sz
print("  "+" -> ".join(order))
if "moov" in order and "mdat" in order and order.index("moov")<order.index("mdat"):
    print("  OK: faststart")
else:
    print("  FAIL: re-encode with -movflags +faststart")
EOF
echo
echo "Now LOOK at it -- extract frames from this encoded file, not the renderer:"
echo "  ./frames.sh $F 6 150 400 700 1000 1300"
