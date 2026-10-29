#!/usr/bin/env bash
# Convert audio files of any ffmpeg-supported codec to MP3 (libmp3lame).
# For local, user-owned files only. Cannot be used on DRM-protected streams.
set -euo pipefail

BITRATE="192k"
OUTDIR=""
FORCE=0

usage() {
  echo "Usage: $(basename "$0") [-b bitrate] [-o outdir] [-f] file [file ...]"
  echo "  -b bitrate  MP3 bitrate (default: 192k)"
  echo "  -o outdir   Output directory (default: alongside input)"
  echo "  -f          Re-encode files that are already .mp3 (default: skip)"
}

while getopts ":b:o:fh" opt; do
  case "$opt" in
    b) BITRATE="$OPTARG" ;;
    o) OUTDIR="$OPTARG" ;;
    f) FORCE=1 ;;
    h) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
done
shift $((OPTIND - 1))

if [ "$#" -eq 0 ]; then usage; exit 2; fi
command -v ffmpeg >/dev/null || { echo "ffmpeg not found" >&2; exit 1; }

convert_one() {
  local src="$1"
  [ -f "$src" ] || { echo "skip (not a file): $src" >&2; return 0; }
  local ext="${src##*.}"
  if [ "$FORCE" -eq 0 ] && [ "${ext,,}" = "mp3" ]; then
    echo "skip (already mp3): $src"
    return 0
  fi
  local base="${src##*/}"
  base="${base%.*}"
  local dest
  if [ -n "$OUTDIR" ]; then
    mkdir -p "$OUTDIR"
    dest="$OUTDIR/$base.mp3"
  else
    dest="${src%.*}.mp3"
  fi
  if [ -e "$dest" ]; then
    local i=1
    while [ -e "${dest%.mp3}-$i.mp3" ]; do i=$((i + 1)); done
    dest="${dest%.mp3}-$i.mp3"
  fi
  ffmpeg -hide_banner -loglevel error -y -i "$src" -codec:a libmp3lame -b:a "$BITRATE" "$dest"
  echo "wrote: $dest"
}

for f in "$@"; do convert_one "$f"; done
