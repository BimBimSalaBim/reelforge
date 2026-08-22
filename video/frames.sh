#!/usr/bin/env bash
# Pull frames out of an encoded mp4 and tile them, with the platform UI chrome
# overlaid so you can see what the app will cover.
#   ./frames.sh out.mp4 6 150 400 700        (frame numbers)
set -euo pipefail
cd "$(dirname "$0")"
F="${1:?usage: ./frames.sh <file.mp4> <frame> [frame ...]}"; shift
FF=./bin/ffmpeg; [ -x "$FF" ] || FF=ffmpeg
rm -rf build/_frames; mkdir -p build/_frames
for n in "$@"; do
  "$FF" -y -v error -i "$F" -vf "select=eq(n\,$n)" -frames:v 1 -vsync 0 \
        "build/_frames/f$(printf %05d "$n").png"
done
python3 safecheck.py 'build/_frames/f*.png' build/_frames/contact.png
echo "open build/_frames/contact.png   (magenta = Reels chrome, blue = Shorts chrome)"
