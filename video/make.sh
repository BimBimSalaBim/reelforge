#!/usr/bin/env bash
# Build one reel end to end.   ./make.sh <storyboard> [outfile.mp4]
# Runs long (render is ~2-3 fps): launch it in the background and tail the log.
set -euo pipefail
cd "$(dirname "$0")"
SB="${1:?usage: ./make.sh <storyboard> [out.mp4]}"
OUT="${2:-../${SB}-reel.mp4}"
FF=./bin/ffmpeg
[ -x "$FF" ] || FF=ffmpeg

# importlib, not `import x`: storyboard names contain hyphens
META=$(python3 -c "
import sys,importlib;sys.path[:0]=['.','storyboards']
s=importlib.import_module('$SB');print(s.AUDIO);print(s.PHRASES)")
AUDIO=$(echo "$META" | sed -n 1p)
PHR=$(echo "$META" | sed -n 2p)

echo "==> align"
python3 align.py build "$SB" "../$AUDIO" "$PHR"
echo "==> audio mix"
python3 sfx.py "$SB"
echo "==> render + encode -> $OUT"
python3 render.py "$SB" 2> "build/$SB.render.log" | "$FF" -y -v warning \
  -f rawvideo -pix_fmt rgba -s 1080x1920 -r 30 -i - \
  -i "build/$SB.mix.wav" \
  -filter_complex "[1:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]" \
  -map 0:v -map "[a]" \
  -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -profile:v high -level 4.1 \
  -x264-params "keyint=60:min-keyint=60:scenecut=0:ref=4:bframes=3" \
  -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv \
  -c:a aac -b:a 192k -ar 48000 -ac 2 \
  -movflags +faststart -shortest "$OUT" 2> "build/$SB.encode.log"
tail -1 "build/$SB.render.log"
echo "==> verify"
./verify.sh "$OUT"
