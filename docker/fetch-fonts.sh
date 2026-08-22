#!/usr/bin/env bash
# Fetch the bundled OSS faces. Run once locally; the renderer image runs it at
# build time. Idempotent -- already-present files are left alone.
#
# Helvetica Neue and Menlo are macOS-only and not redistributable, so kit.f and
# kit.m are repointed at these instead.
#
#   Inter            display face, closest widely-available match to Helvetica Neue
#   DejaVu Sans Mono mono face and the default. Menlo descends from Bitstream Vera
#                    Sans Mono, DejaVu's ancestor, and it carries every symbol the
#                    storyboards draw.
#   JetBrains Mono   optional alternative. Sharper in terminal blocks, but missing
#                    the rotate and star glyphs, which render as empty boxes with
#                    no error -- so it is not the default.
set -euo pipefail

DEST="$(cd "$(dirname "$0")" && pwd)/fonts"
mkdir -p "$DEST"
cd "$DEST"

INTER_VER=4.1
JBM_VER=2.304
DEJAVU_VER=2.37

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fetch() { curl -fsSL --retry 3 --retry-delay 2 -o "$2" "$1"; }

# copy every matching file found anywhere under a directory, flat into $DEST
collect() {
  local root="$1"; shift
  local found=0
  local file
  while IFS= read -r file; do
    cp "$file" "$DEST/"
    found=1
  done < <(find "$root" -type f "$@" -print)
  [ "$found" = 1 ] || { echo "no files matched under $root" >&2; return 1; }
}

if [ ! -f Inter-Regular.ttf ]; then
  echo "==> Inter $INTER_VER"
  fetch "https://github.com/rsms/inter/releases/download/v${INTER_VER}/Inter-${INTER_VER}.zip" "$TMP/inter.zip"
  unzip -qo "$TMP/inter.zip" -d "$TMP/inter"
  collect "$TMP/inter" -name 'Inter-*.ttf' ! -name '*Italic*'
fi

if [ ! -f DejaVuSansMono.ttf ]; then
  echo "==> DejaVu Sans Mono $DEJAVU_VER"
  fetch "https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-${DEJAVU_VER}.zip" "$TMP/dejavu.zip"
  unzip -qo "$TMP/dejavu.zip" -d "$TMP/dejavu"
  collect "$TMP/dejavu" \( -name 'DejaVuSansMono.ttf' -o -name 'DejaVuSansMono-Bold.ttf' \)
fi

if [ ! -f JetBrainsMono-Regular.ttf ]; then
  echo "==> JetBrains Mono $JBM_VER (optional alternative)"
  fetch "https://github.com/JetBrains/JetBrainsMono/releases/download/v${JBM_VER}/JetBrainsMono-${JBM_VER}.zip" "$TMP/jbm.zip"
  unzip -qo "$TMP/jbm.zip" -d "$TMP/jbm"
  collect "$TMP/jbm" \( -name 'JetBrainsMono-Regular.ttf' -o -name 'JetBrainsMono-Bold.ttf' \)
fi

echo "==> fonts in $DEST:"
ls -1 *.ttf | sed 's/^/    /'

# Required by app/render/fonts.py; a missing one is a render-time surprise.
for required in Inter-Regular.ttf Inter-Bold.ttf Inter-Medium.ttf Inter-Black.ttf \
                Inter-Light.ttf Inter-Thin.ttf Inter-ExtraBold.ttf \
                DejaVuSansMono.ttf DejaVuSansMono-Bold.ttf; do
  [ -f "$required" ] || { echo "MISSING: $required" >&2; exit 1; }
done
echo "==> all required faces present"
