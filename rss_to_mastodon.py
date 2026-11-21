"""Goldman Mill: monitor outside RSS/Atom feeds and post new titles and links.

- A feed's first successful check creates a baseline and never posts old items.
- Per-feed tags, include/exclude phrases, and optional RSS-supplied article image.
- A posting_enabled switch stays false until the user deliberately turns it on.
- No secrets are kept in this public-repository script.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import feedparser
import requests

CONFIG_PATH = Path("settings.json")
STATE_PATH = Path("posted_state.json")
USER_AGENT = "GoldmanMillCuratedRSS/2.0 (+https://goldmanmill.org/)"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp"}


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def valid_http_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    parts = urlsplit(url)
    return parts.scheme in ("http", "https") and bool(parts.hostname) and not parts.username and not parts.password


def strip_markup(value) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", str(value or "")))).strip()


def ensure_list_of_strings(value, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError(f"{field} must be a list of text values")
    return [x.strip() for x in value if x.strip()]


def config_load():
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    server = str(cfg.get("mastodon_server", "")).strip().rstrip("/")
    if not server.startswith("https://") or not valid_http_url(server) or "YOUR-" in server:
        raise ValueError("Replace mastodon_server in settings.json with your Mastodon server's https:// address.")
    feeds = cfg.get("feeds")
    if not isinstance(feeds, list) or not feeds:
        raise ValueError("Add at least one outside RSS source to feeds in settings.json.")
    result = []
    for index, feed in enumerate(feeds, start=1):
        if not isinstance(feed, dict):
            raise ValueError(f"Feed {index} must be a settings object")
        url = str(feed.get("url", "")).strip()
        if not valid_http_url(url) or "YOUR-" in url:
            raise ValueError(f"Replace the sample URL for feed {index} with a real RSS/Atom URL.")
        hashtags = ensure_list_of_strings(feed.get("hashtags", []), "hashtags")
        normalized = []
        for tag in hashtags:
            tag = tag.lstrip("#")
            if not re.fullmatch(r"\w+", tag, flags=re.UNICODE):
                raise ValueError(f"Invalid hashtag in feed {index}: {tag!r} (do not use spaces or punctuation)")
            normalized.append("#" + tag)
        result.append({
            "url": url,
            "name": str(feed.get("name", url)),
            "hashtags": normalized,
            "include_any": [x.casefold() for x in ensure_list_of_strings(feed.get("include_any", []), "include_any")],
            "exclude_any": [x.casefold() for x in ensure_list_of_strings(feed.get("exclude_any", []), "exclude_any")],
            "attach_image": feed.get("attach_image", False) is True,
        })
    if len({f["url"] for f in result}) != len(result):
        raise ValueError("Each RSS URL should appear only once in feeds.")
    enabled = cfg.get("posting_enabled", False) is True
    limit = cfg.get("check_limit", 20)
    if not isinstance(limit, int) or not 1 <= limit <= 40:
        raise ValueError("check_limit must be between 1 and 40")
    token = os.environ.get("MASTODON_ACCESS_TOKEN", "").strip()
    if enabled and not token:
        raise ValueError("Add MASTODON_ACCESS_TOKEN under GitHub Settings > Secrets and variables > Actions.")
    return server, result, enabled, limit, token


def load_state():
    if not STATE_PATH.exists():
        return {"version": 2, "initialized_feeds": [], "seen": [], "ignored": []}
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if not isinstance(state.get("initialized_feeds"), list) or not isinstance(state.get("seen"), list) or not isinstance(state.get("ignored", []), list):
        raise ValueError("History file looks damaged. Stop rather than risk reposting old articles.")
    return state


def choose_image(entry):
    """Look only at explicitly supplied RSS image attachments, not web-page scraping."""
    candidates = list(entry.get("media_content", [])) + list(entry.get("media_thumbnail", [])) + list(entry.get("enclosures", []))
    for item in candidates:
        url = item.get("url") or item.get("href")
        kind = str(item.get("type", ""))
        if valid_http_url(url) and (kind.startswith("image/") or item in entry.get("media_content", []) or item in entry.get("media_thumbnail", [])):
            alt = strip_markup(item.get("description") or item.get("title") or item.get("alt"))
            return {"url": url, "alt": alt}
    return None


def parse_items(content: bytes):
    parsed = feedparser.parse(content)
    if not parsed.version and not parsed.entries:
        raise ValueError("The URL did not return a recognizable RSS/Atom feed.")
    items = []
    for entry in parsed.entries:
        title = strip_markup(entry.get("title")) or "Read the story"
        link = str(entry.get("link", "")).strip()
        if not valid_http_url(link):
            continue
        summary = strip_markup(entry.get("summary", ""))
        items.append({"key": sha(link), "title": title, "link": link, "summary": summary, "image": choose_image(entry)})
    # RSS feeds generally place the newest items first. Older first is kinder to a timeline.
    return list(reversed(items))


def meets_filter(item, feed):
    haystack = (item["title"] + " " + item["summary"]).casefold()
    if any(word in haystack for word in feed["exclude_any"]):
        return False
    return not feed["include_any"] or any(word in haystack for word in feed["include_any"])


def compose(item, hashtags):
    # Use a conservative size; Mastodon servers may have their own character limits.
    tags = " ".join(dict.fromkeys(hashtags))
    suffix = "\n" + item["link"] + ("\n" + tags if tags else "")
    budget = max(40, 460 - len(suffix))
    title = item["title"]
    if len(title) > budget:
        title = title[: budget - 1].rstrip() + "…"
    return title + suffix


def fetch_feed(url):
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
    response.raise_for_status()
    return parse_items(response.content)


def fetch_image(image_url):
    # Image attachment is optional and restricted to supported RSS media formats.
    with requests.get(image_url, headers={"User-Agent": USER_AGENT}, timeout=25, stream=True) as r:
        r.raise_for_status()
        media_type = r.headers.get("content-type", "").split(";")[0].strip().lower()
        if media_type not in IMAGE_TYPES:
            raise ValueError("RSS image is not a supported JPEG, PNG, GIF, or WebP file")
        expected = int(r.headers.get("content-length") or 0)
        if expected > MAX_IMAGE_BYTES:
            raise ValueError("RSS image exceeds the 8 MB safety limit")
        chunks, size = [], 0
        for chunk in r.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > MAX_IMAGE_BYTES:
                raise ValueError("RSS image exceeds the 8 MB safety limit")
            chunks.append(chunk)
    return b"".join(chunks), media_type


def upload_image(server, token, item):
    source = item.get("image")
    if not source:
        return None
    img_bytes, content_type = fetch_image(source["url"])
    # A source may not provide alt text: be honest rather than inventing a visual description.
    description = source["alt"] or f"Image accompanying article: {item['title']} (source provided no description)"
    response = requests.post(
        server + "/api/v2/media",
        headers={"Authorization": "Bearer " + token, "User-Agent": USER_AGENT},
        files={"file": ("feed-image." + IMAGE_TYPES[content_type], img_bytes, content_type)},
        data={"description": description[:1500]},
        timeout=35,
    )
    response.raise_for_status()
    media_id = response.json()["id"]
    # Async media processing: wait for ready metadata before attaching when supported.
    for _ in range(8):
        status = requests.get(
            server + "/api/v1/media/" + str(media_id),
            headers={"Authorization": "Bearer " + token, "User-Agent": USER_AGENT},
            timeout=20,
        )
        if status.status_code == 404:
            time.sleep(2)
            continue
        status.raise_for_status()
        if status.json().get("url"):
            return media_id
        time.sleep(2)
    raise RuntimeError("Image processing did not finish; will post a link preview instead")


def publish(server, token, item, feed):
    media_id = None
    if feed["attach_image"] and item["image"]:
        try:
            media_id = upload_image(server, token, item)
        except Exception as exc:
            print(f"Image unavailable for {item['title'][:60]} ({type(exc).__name__}). Publishing title and link only.")
    fields = [("status", compose(item, feed["hashtags"])), ("visibility", "public")]
    if media_id:
        fields.append(("media_ids[]", str(media_id)))
    response = requests.post(
        server + "/api/v1/statuses",
        headers={
            "Authorization": "Bearer " + token,
            "Idempotency-Key": item["key"],
            "User-Agent": USER_AGENT,
        },
        data=fields,
        timeout=30,
    )
    response.raise_for_status()


def main():
    server, feeds, posting_enabled, limit, token = config_load()
    state = load_state()
    initialized = set(state["initialized_feeds"])
    seen = set(state["seen"])
    ignored = set(state.get("ignored", []))
    failures, posted = 0, 0

    for feed in feeds:
        url = feed["url"]
        try:
            items = fetch_feed(url)
        except Exception as exc:
            print(f"Cannot check {feed['name']}: {type(exc).__name__}: {str(exc)[:150]}")
            failures += 1
            continue

        if url not in initialized:
            seen.update(x["key"] for x in items)
            initialized.add(url)
            print(f"First check of {feed['name']}: recognized {len(items)} existing entries; posted ZERO.")
            continue

        for item in items:
            if item["key"] in seen or sha(url + "|" + item["key"]) in ignored:
                continue
            if not meets_filter(item, feed):
                # Record exclusions per feed; do not block a matching item from a DIFFERENT feed.
                ignored.add(sha(url + "|" + item["key"]))
                continue
            if not posting_enabled:
                print(f"Posting off: new item waiting for activation: {item['title'][:75]}")
                # Do not mark eligible posts as seen: allow them when user enables posting.
                continue
            if posted >= limit:
                print("Safety cap reached. Remaining items can post on a later check.")
                break
            try:
                publish(server, token, item, feed)
            except Exception as exc:
                print(f"Could not publish {item['title'][:65]}: {type(exc).__name__}: {str(exc)[:150]}")
                failures += 1
                break
            seen.add(item["key"])
            posted += 1
            print(f"Posted: {item['title'][:95]}")
            time.sleep(1)

    state["initialized_feeds"] = sorted(initialized)
    old = [k for k in state["seen"] if k in seen]
    fresh = sorted(seen.difference(old))
    state["seen"] = (old + fresh)[-50000:]
    old_ignored = [k for k in state.get("ignored", []) if k in ignored]
    new_ignored = sorted(ignored.difference(old_ignored))
    state["ignored"] = (old_ignored + new_ignored)[-50000:]
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(f"Done. Posts published: {posted}. Errors: {failures}. Posting enabled: {posting_enabled}.")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("Setup error:", type(exc).__name__, str(exc))
        sys.exit(1)
