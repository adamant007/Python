#!/usr/bin/env python3
"""Upload the current rendered Short directly to YouTube.

Credentials are read only from environment variables supplied by GitHub Actions:
  YOUTUBE_CLIENT_ID
  YOUTUBE_CLIENT_SECRET
  YOUTUBE_REFRESH_TOKEN

The upload uses the YouTube Data API's resumable videos.insert endpoint. It
uploads the video as private and sets publishAt for the next configured
Tue/Thu/Sat 6 PM Pacific slot. Public scheduling will work once the Google API
project has YouTube upload-publication restrictions lifted by Google's audit.
"""

import json
import mimetypes
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
JOB_PATH = ROOT / "video-job.json"
CONFIG_PATH = ROOT / "series-config.json"
MARKER_DIR = ROOT / "published-youtube"

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"

DAY_MAP = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


def post_form(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.load(res)


def refresh_access_token() -> str:
    payload = post_form(
        TOKEN_URL,
        {
            "client_id": required_env("YOUTUBE_CLIENT_ID"),
            "client_secret": required_env("YOUTUBE_CLIENT_SECRET"),
            "refresh_token": required_env("YOUTUBE_REFRESH_TOKEN"),
            "grant_type": "refresh_token",
        },
    )
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("Google OAuth refresh returned no access token")
    return token


def next_slot(config: dict) -> datetime:
    tz = ZoneInfo(config.get("timezone", "America/Los_Angeles"))
    now = datetime.now(tz)
    hour, minute = map(int, config.get("publish_time", "18:00").split(":"))
    allowed = {DAY_MAP[d] for d in config.get("cadence", ["TU", "TH", "SA"])}

    for offset in range(15):
        day = now.date() + timedelta(days=offset)
        if day.weekday() not in allowed:
            continue
        candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)
        # Give YouTube enough time to process a minute-plus Short.
        if candidate > now + timedelta(minutes=30):
            return candidate
    raise RuntimeError("Could not find a valid publishing slot")


def infer_tags(job: dict, config: dict) -> list[str]:
    tags = job.get("youtube_tags") or job.get("tags") or []
    if isinstance(tags, str):
        tags = [x.strip() for x in tags.split(",") if x.strip()]
    if tags:
        return tags[:30]

    headline = job.get("headline", "")
    base = ["Shorts"]
    if "BIBLE" in headline.upper() or job.get("series") == "bible":
        base += ["Bible Stories", "Bible", "Genesis"]
    else:
        base += ["Mythology", "Mythology Shorts"]
    return base


def upload(video_path: Path, job: dict, config: dict) -> dict:
    token = refresh_access_token()
    publish_at = next_slot(config).astimezone(timezone.utc)
    publish_at_iso = publish_at.isoformat(timespec="seconds").replace("+00:00", "Z")

    title = (
        job.get("youtube_title")
        or job.get("title")
        or job.get("headline")
        or video_path.stem.replace("-", " ").title()
    ).strip()[:100]

    description = (
        job.get("youtube_description")
        or job.get("description")
        or f"{title}\n\n#Shorts"
    ).strip()

    category_id = str(job.get("youtube_category_id") or "27")  # Education
    metadata = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": infer_tags(job, config),
            "categoryId": category_id,
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_at_iso,
            "selfDeclaredMadeForKids": bool(config.get("made_for_kids", False)),
            "containsSyntheticMedia": bool(config.get("is_ai_generated_content", True)),
            "embeddable": True,
            "publicStatsViewable": True,
        },
    }

    query = urllib.parse.urlencode(
        {
            "uploadType": "resumable",
            "part": "snippet,status",
            "notifySubscribers": "false",
        }
    )
    endpoint = f"{UPLOAD_URL}?{query}"
    size = video_path.stat().st_size
    mime = mimetypes.guess_type(video_path.name)[0] or "video/mp4"
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(metadata).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(size),
            "X-Upload-Content-Type": mime,
        },
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        location = res.headers.get("Location")
    if not location:
        raise RuntimeError("YouTube did not return a resumable upload URL")

    data = video_path.read_bytes()
    put = urllib.request.Request(
        location,
        data=data,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": mime,
            "Content-Length": str(len(data)),
        },
    )
    with urllib.request.urlopen(put, timeout=900) as res:
        result = json.load(res)

    result["_scheduled_for"] = publish_at_iso
    result["_title"] = title
    return result


def main() -> None:
    job = json.loads(JOB_PATH.read_text(encoding="utf-8"))
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    slug = job["slug"].strip()
    video_path = ROOT / "videos" / f"{slug}.mp4"
    marker = MARKER_DIR / f"{slug}.json"

    if marker.exists():
        print(f"Already uploaded: {marker}")
        return
    if not video_path.is_file():
        raise RuntimeError(f"Rendered video not found: {video_path}")

    result = upload(video_path, job, config)
    video_id = result.get("id")
    if not video_id:
        raise RuntimeError("YouTube upload completed without a video ID")

    MARKER_DIR.mkdir(exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "slug": slug,
                "youtube_video_id": video_id,
                "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
                "scheduled_for_utc": result["_scheduled_for"],
                "title": result["_title"],
                "uploaded_at_utc": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Uploaded {slug} to YouTube as private and requested scheduled publication "
        f"for {result['_scheduled_for']}. Video ID: {video_id}"
    )


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"YouTube HTTP {exc.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
