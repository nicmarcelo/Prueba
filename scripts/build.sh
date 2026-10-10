#!/usr/bin/env bash
# Builds the finished video: frames (Playwright) -> silent mp4, timeline -> audio, then mux.
#   scripts/build.sh                 -> output/squishies_asmr_pizarra.mp4
#   scripts/build.sh --fps 15        -> quicker draft
set -euo pipefail
cd "$(dirname "$0")/.."

BUILD=${BUILD_DIR:-build}
OUT=${OUT:-output/squishies_asmr_pizarra.mp4}
mkdir -p "$BUILD" "$(dirname "$OUT")"

echo "== 1/3 rendering frames"
node scripts/render.mjs --out "$BUILD/video_noaudio.mp4" --timeline "$BUILD/timeline.json" "$@"

echo "== 2/3 synthesising audio"
python3 scripts/make_audio.py "$BUILD/timeline.json" "$BUILD/audio.wav"

echo "== 3/3 muxing"
ffmpeg -y -loglevel error -i "$BUILD/video_noaudio.mp4" -i "$BUILD/audio.wav" \
  -c:v copy -c:a aac -b:a 192k -ar 48000 -shortest -movflags +faststart "$OUT"
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height,r_frame_rate -of default=nw=1 "$OUT"
echo "done: $OUT"
