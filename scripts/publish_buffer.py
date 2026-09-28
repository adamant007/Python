#!/usr/bin/env python3
"""Publish the freshly rendered Short to YouTube through Buffer.

Requirements:
  - BUFFER_API_KEY secret
  - Buffer account with exactly one connected, unlocked YouTube channel

The script auto-discovers the Buffer organization/channel, schedules the
current video-job.json slug for the next configured Tue/Thu/Sat 6 PM Pacific
slot, and writes a local marker so reruns do not double-publish.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
JOB_PATH = ROOT / "video-job.json"
CONFIG_PATH = ROOT / "series-config.json"
PUBLISHED_DIR = ROOT / "published"
API = "https://api.buffer.com"

DAY_MAP = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def gql(query, variables=None):
    key = os.environ.get("BUFFER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("BUFFER_API_KEY is not configured")
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        data = json.load(res)
    if data.get("errors"):
        raise RuntimeError("Buffer GraphQL error: " + json.dumps(data["errors"]))
    return data.get("data") or {}


def next_slot(config):
    tz = ZoneInfo(config.get("timezone", "America/Los_Angeles"))
    now = datetime.now(tz)
    hour, minute = map(int, config.get("publish_time", "18:00").split(":"))
    allowed = {DAY_MAP[d] for d in config.get("cadence", ["TU", "TH", "SA"])}

    for offset in range(0, 15):
        day = now.date() + timedelta(days=offset)
        if day.weekday() not in allowed:
            continue
        candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)
        # Leave Buffer at least ten minutes to ingest the public video asset.
        if candidate > now + timedelta(minutes=10):
            return candidate
    raise RuntimeError("Could not find the next publishing slot")


def main():
    job = json.loads(JOB_PATH.read_text(encoding="utf-8"))
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    slug = job["slug"].strip()
    marker = PUBLISHED_DIR / f"{slug}.json"
    if marker.exists():
        print(f"Already scheduled: {marker}")
        return

    account = gql("""
      query Account {
        account {
          organizations { id name }
        }
      }
    """)
    orgs = account["account"]["organizations"]
    requested_org = os.environ.get("BUFFER_ORGANIZATION_ID", "").strip()
    if requested_org:
        org = next((o for o in orgs if o["id"] == requested_org), None)
        if not org:
            raise RuntimeError("BUFFER_ORGANIZATION_ID is not available to this API key")
    elif len(orgs) == 1:
        org = orgs[0]
    else:
        raise RuntimeError(
            "Multiple Buffer organizations found. Set BUFFER_ORGANIZATION_ID once: "
            + ", ".join(f"{o['name']}={o['id']}" for o in orgs)
        )

    channels = gql("""
      query Channels($organizationId: OrganizationId!) {
        channels(input: { organizationId: $organizationId, filter: { isLocked: false } }) {
          id
          name
          displayName
          service
        }
      }
    """, {"organizationId": org["id"]})["channels"]
    yt = [c for c in channels if c.get("service") == "youtube"]
    if len(yt) != 1:
        raise RuntimeError(
            "Expected exactly one unlocked YouTube channel in Buffer; found "
            + str(len(yt))
        )
    channel = yt[0]

    repo = os.environ.get("GITHUB_REPOSITORY", "adamant007/Python")
    video_url = f"https://raw.githubusercontent.com/{repo}/main/videos/{slug}.mp4"
    due = next_slot(config)

    title = (
        job.get("youtube_title")
        or job.get("title")
        or job.get("headline")
        or slug.replace("-", " ").title()
    )[:100]
    description = job.get("youtube_description") or job.get("description") or ""
    if not description:
        description = f"{title} #Shorts"

    mutation = """
      mutation CreatePost($input: CreatePostInput!) {
        createPost(input: $input) {
          ... on PostActionSuccess {
            post { id status dueAt text }
          }
          ... on MutationError { message }
        }
      }
    """
    variables = {
        "input": {
            "text": description,
            "channelId": channel["id"],
            "schedulingType": "automatic",
            "mode": "customScheduled",
            "dueAt": due.isoformat(),
            "aiAssisted": True,
            "assets": [{"video": {"url": video_url}}],
            "metadata": {
                "youtube": {
                    "title": title,
                    "categoryId": str(job.get("youtube_category_id", "27")),
                    "madeForKids": bool(job.get("made_for_kids", False)),
                    "isAiGenerated": bool(job.get("is_ai_generated_content", True)),
                    "privacy": "public",
                    "embeddable": True,
                    "notifySubscribers": True,
                }
            },
        }
    }
    result = gql(mutation, variables)["createPost"]
    if "message" in result and "post" not in result:
        raise RuntimeError("Buffer rejected the post: " + result["message"])
    post = result["post"]

    PUBLISHED_DIR.mkdir(exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "slug": slug,
                "buffer_post_id": post["id"],
                "channel": channel.get("displayName") or channel.get("name"),
                "video_url": video_url,
                "scheduled_for": due.isoformat(),
                "title": title,
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"Scheduled {slug} on YouTube for {due.isoformat()} via Buffer")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
