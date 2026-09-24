#!/usr/bin/env bash
set -euo pipefail

VOICE_URL="https://storage.googleapis.com/adm--audio-playback--7d--public/mcp-preview/f458a192-51d5-4c15-bfbe-41fe0b1ab773.mp3"
OUT="videos/thor-bride-short.mp4"
FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

mkdir -p videos tmp
curl -L --fail --retry 3 "$VOICE_URL" -o tmp/voice.mp3

ffmpeg -y \
  -f lavfi -i "color=c=0x0c1424:s=1080x1920:r=30" \
  -i tmp/voice.mp3 \
  -filter_complex "
    [0:v]
    drawbox=x=0:y=0:w=1080:h=1920:color=0x07101f@0.45:t=fill,
    drawbox=x=260:y=280:w=560:h=190:color=0x7f8ea3@0.95:t=fill,
    drawbox=x=500:y=470:w=80:h=390:color=0x74563a@0.95:t=fill,
    drawbox=x=485:y=850:w=110:h=35:color=0x9b7449@0.95:t=fill,
    drawbox=x=0:y=0:w=1080:h=1920:color=white@0.13:t=fill:enable='between(t,18.0,18.18)+between(t,19.0,19.12)',
    drawtext=fontfile=${FONT}:text='THOR... AS A BRIDE?!':fontcolor=white:fontsize=78:borderw=5:bordercolor=black@0.75:x=(w-text_w)/2:y=95,
    drawtext=fontfile=${FONT}:text='He dressed as a bride to steal back Mjolnir.':fontcolor=white:fontsize=58:borderw=5:bordercolor=black@0.78:x=(w-text_w)/2:y=1110:enable='between(t,0,4.4)',
    drawtext=fontfile=${FONT}:text='A giant demanded Freyja — so Thor wore the veil.':fontcolor=white:fontsize=50:borderw=5:bordercolor=black@0.78:x=(w-text_w)/2:y=1110:enable='between(t,4.4,9.0)',
    drawtext=fontfile=${FONT}:text='At the wedding, his appetite nearly ruined everything.':fontcolor=white:fontsize=47:borderw=5:bordercolor=black@0.78:x=(w-text_w)/2:y=1110:enable='between(t,9.0,14.2)',
    drawtext=fontfile=${FONT}:text='Then the hammer appeared.':fontcolor=white:fontsize=60:borderw=5:bordercolor=black@0.78:x=(w-text_w)/2:y=1110:enable='between(t,14.2,17.2)',
    drawtext=fontfile=${FONT}:text='Thor grabbed it — and the wedding ended in THUNDER.':fontcolor=white:fontsize=47:borderw=5:bordercolor=black@0.78:x=(w-text_w)/2:y=1110:enable='gte(t,17.2)',
    drawtext=fontfile=${FONT}:text='MYTH IN 20 SECONDS':fontcolor=0xf1c75b:fontsize=44:borderw=3:bordercolor=black@0.7:x=(w-text_w)/2:y=1765
    [v]
  " \
  -map "[v]" -map 1:a \
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
  -c:a aac -b:a 192k \
  -movflags +faststart -shortest "$OUT"

echo "Rendered $OUT"
