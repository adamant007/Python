#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "video-job.json"
TMP = ROOT / "tmp"
VIDEOS = ROOT / "videos"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def ff_escape_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:")

with JOB.open("r", encoding="utf-8") as f:
    job = json.load(f)

slug = job["slug"]
voice_url = job.get("voice_url")
voice_urls = job.get("voice_urls") or ([voice_url] if voice_url else [])
if not voice_urls:
    raise ValueError("video-job.json must include voice_url or voice_urls")
headline = job["headline"]
footer = job.get("footer", "STORY IN 20 SECONDS")
bg = job.get("background", "0x0c1424")
accent = job.get("accent", "0xf1c75b")
captions = job["captions"]

TMP.mkdir(exist_ok=True)
VIDEOS.mkdir(exist_ok=True)

voice = TMP / f"{slug}-voice.mp3"
parts = []
for i, url in enumerate(voice_urls):
    part = TMP / f"{slug}-voice-{i}.mp3"
    subprocess.run(["curl", "-L", "--fail", "--retry", "3", url, "-o", str(part)], check=True)
    parts.append(part)

if len(parts) == 1:
    subprocess.run(["cp", str(parts[0]), str(voice)], check=True)
else:
    concat_file = TMP / f"{slug}-concat.txt"
    concat_file.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts) + "\n", encoding="utf-8")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:a", "libmp3lame", "-b:a", "192k", str(voice)
    ], check=True)

headline_file = TMP / f"{slug}-headline.txt"
footer_file = TMP / f"{slug}-footer.txt"
headline_file.write_text(headline, encoding="utf-8")
footer_file.write_text(footer, encoding="utf-8")

filters = [
    f"drawbox=x=0:y=0:w=1080:h=1920:color=0x07101f@0.38:t=fill",
    f"drawbox=x=85:y=75:w=910:h=6:color={accent}@0.85:t=fill",
    f"drawbox=x=85:y=1710:w=910:h=6:color={accent}@0.85:t=fill",
    f"drawbox=x=180:y=330:w=720:h=500:color={accent}@0.07:t=fill",
    f"drawbox=x=245:y=405:w=590:h=350:color=white@0.035:t=fill",
    f"drawbox=x=0:y=0:w=1080:h=1920:color=white@0.10:t=fill:enable='between(t,18.0,18.14)+between(t,19.0,19.10)'",
    f"drawtext=fontfile={FONT}:textfile={ff_escape_path(headline_file)}:fontcolor=white:fontsize=72:borderw=5:bordercolor=black@0.75:x=(w-text_w)/2:y=115",
]
for i, cap in enumerate(captions):
    p = TMP / f"{slug}-caption-{i}.txt"
    p.write_text(cap["text"], encoding="utf-8")
    size = int(cap.get("font_size", 52))
    filters.append(
        f"drawtext=fontfile={FONT}:textfile={ff_escape_path(p)}:fontcolor=white:fontsize={size}:"
        f"borderw=5:bordercolor=black@0.78:x=(w-text_w)/2:y=1100:"
        f"enable='between(t,{float(cap['start'])},{float(cap['end'])})'"
    )
filters.append(
    f"drawtext=fontfile={FONT}:textfile={ff_escape_path(footer_file)}:fontcolor={accent}:fontsize=42:"
    f"borderw=3:bordercolor=black@0.7:x=(w-text_w)/2:y=1770"
)

filter_chain = ",".join(filters)
out = VIDEOS / f"{slug}.mp4"

cmd = [
    "ffmpeg", "-y",
    "-f", "lavfi", "-i", f"color=c={bg}:s=1080x1920:r=30",
    "-i", str(voice),
    "-filter_complex", f"[0:v]{filter_chain}[v]",
    "-map", "[v]", "-map", "1:a",
    "-c:v", "libx264", "-preset", "medium", "-crf", "20",
    "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "192k",
    "-movflags", "+faststart", "-shortest",
    str(out),
]
subprocess.run(cmd, check=True)
print(out)
