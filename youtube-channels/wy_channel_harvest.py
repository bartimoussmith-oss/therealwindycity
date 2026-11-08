#!/usr/bin/env python3
"""
Wyoming official YouTube channel + video inventory (metadata only).

For each target entity (state/county/city bodies + Wyoming towns):
  1. search YouTube for the entity's channel (YouTube Data API v3, search.list)
  2. take the top candidate and mark it for human review if the title
     does not clearly match the entity name
  3. list every upload on that channel (channels.list + playlistItems.list)
  4. write CSV spreadsheets (open in Excel or Google Sheets)

It does NOT download any video files.

Requirements: Python 3.8+, standard library only.

Usage (run on your own computer):
  export YOUTUBE_API_KEY=your_key_here      # Windows PowerShell: $env:YOUTUBE_API_KEY="..."
  python3 wy_channel_harvest.py                  # full run
  python3 wy_channel_harvest.py --limit 5        # test on first 5 targets
  python3 wy_channel_harvest.py --core-only      # only the 13 state/county/city bodies

Quota: each search.list call costs 100 units; the default daily quota is
10,000 units. A full run needs roughly 11,500 units across all targets, so it
may take two days. Progress is saved to cache.json in the output folder, and a
re-run skips finished work.
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://www.googleapis.com/youtube/v3"

CORE_ENTITIES = [
    "Wyoming Legislature", "Cheyenne City Council", "Laramie County Commissioners",
    "Casper City Council", "Laramie City Council", "Sheridan City Council",
    "Gillette City Council", "Jackson Town Council", "Teton County Commissioners",
    "Sweetwater County Commissioners", "Natrona County Commissioners",
    "Wyoming Supreme Court", "Wyoming Department of Transportation",
]

WY_TOWNS = [
    "Afton", "Albin", "Alpine", "Baggs", "Bairoil", "Bar Nunn", "Basin", "Bear River",
    "Big Piney", "Buffalo", "Burlington", "Burns", "Byron", "Chugwater", "Clearmont",
    "Cody", "Cokeville", "Cowley", "Dayton", "Deaver", "Diamondville", "Dixon",
    "Douglas", "Dubois", "East Thermopolis", "Edgerton", "Elk Mountain", "Encampment",
    "Evanston", "Evansville", "Fort Laramie", "Frannie", "Glendo", "Glenrock", "Granger",
    "Green River", "Greybull", "Guernsey", "Hanna", "Hartville", "Hudson", "Hulett",
    "Kaycee", "Kemmerer", "Kirby", "La Barge", "La Grange", "Lander", "Lingle",
    "Lost Springs", "Lovell", "Lusk", "Lyman", "Manderson", "Manville", "Marbleton",
    "Medicine Bow", "Meeteetse", "Midwest", "Mills", "Moorcroft", "Mountain View",
    "Newcastle", "Opal", "Pavillion", "Pine Bluffs", "Pine Haven", "Pinedale", "Powell",
    "Ranchester", "Rawlins", "Riverside", "Riverton", "Rock River", "Rock Springs",
    "Rolling Hills", "Saratoga", "Shoshoni", "Sinclair", "Star Valley Ranch", "Sundance",
    "Superior", "Ten Sleep", "Thayne", "Thermopolis", "Torrington", "Upton",
    "Van Tassell", "Wamsutter", "Wheatland", "Worland", "Wright", "Yoder",
]

STOPWORDS = {"of", "the", "and", "for", "city", "town", "county"}


class QuotaExceeded(Exception):
    pass


def build_targets(core_only=False):
    """Return [(label, search_name, kind)] for every target."""
    targets = [(name, name, "core") for name in CORE_ENTITIES]
    if not core_only:
        targets += [(town, f"{town} Wyoming", "town") for town in WY_TOWNS]
    return targets


def api_get(endpoint, key, **params):
    """Call one YouTube Data API v3 endpoint and return the parsed JSON."""
    params["key"] = key
    url = f"{API}/{endpoint}?{urllib.parse.urlencode(params)}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", errors="ignore")
            if err.code in (403, 429) and "quota" in body.lower():
                raise QuotaExceeded(body[:300])
            if err.code >= 500 and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"HTTP {err.code} on {endpoint}: {body[:300]}")
        except urllib.error.URLError:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise
    raise RuntimeError(f"gave up on {endpoint}")


def match_score(search_name, channel_title):
    """Share of the entity's significant words that appear in the channel title (0-1)."""
    words = [w for w in re.findall(r"[a-z']+", search_name.lower()) if w not in STOPWORDS]
    if not words:
        return 0.0
    title = channel_title.lower()
    hits = sum(1 for w in words if w in title)
    return round(hits / len(words), 2)


def find_candidates(search_name, key, call=api_get):
    """Return up to 5 channel candidates for a search name, best match first."""
    data = call("search", key, part="snippet", type="channel",
                q=f"{search_name} official", maxResults=5)
    cands = []
    for item in data.get("items", []):
        channel_id = item["id"]["channelId"]
        title = item["snippet"]["channelTitle"]
        cands.append({
            "channel_id": channel_id,
            "title": title,
            "score": match_score(search_name, title),
        })
    cands.sort(key=lambda c: c["score"], reverse=True)
    return cands


def fetch_channel_info(channel_id, key, call=api_get):
    """Return (custom_url, uploads_playlist_id, video_count) for a channel."""
    data = call("channels", key, part="snippet,contentDetails,statistics", id=channel_id)
    items = data.get("items", [])
    if not items:
        return "", "", 0
    item = items[0]
    custom = item["snippet"].get("customUrl", "")
    uploads = item["contentDetails"]["relatedPlaylists"].get("uploads", "")
    count = int(item.get("statistics", {}).get("videoCount", 0) or 0)
    return custom, uploads, count


def fetch_all_uploads(uploads_playlist_id, key, call=api_get):
    """Return every video on the uploads playlist as a list of dicts."""
    videos, page_token = [], None
    while True:
        params = dict(part="snippet,contentDetails", playlistId=uploads_playlist_id, maxResults=50)
        if page_token:
            params["pageToken"] = page_token
        data = call("playlistItems", key, **params)
        for item in data.get("items", []):
            vid = item["contentDetails"]["videoId"]
            videos.append({
                "video_id": vid,
                "title": item["snippet"].get("title", ""),
                "published": item["contentDetails"].get("videoPublishedAt",
                                                        item["snippet"].get("publishedAt", "")),
                "url": f"https://www.youtube.com/watch?v={vid}",
            })
        page_token = data.get("nextPageToken")
        if not page_token:
            return videos


def load_cache(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"targets": {}, "channels": {}}


def save_cache(path, cache):
    path.write_text(json.dumps(cache, indent=1), encoding="utf-8")


def write_csv(path, rows, fieldnames):
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run(out_dir, key, targets, call=api_get, sleep=0.2):
    """Process targets, saving progress after each one. Returns True if finished cleanly."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_path = out_dir / "cache.json"
    cache = load_cache(cache_path)
    finished = True

    try:
        for label, search_name, kind in targets:
            if label in cache["targets"]:
                continue
            cands = find_candidates(search_name, key, call=call)
            time.sleep(sleep)
            cache["targets"][label] = {"kind": kind, "search_name": search_name, "candidates": cands}

            if cands and cands[0]["channel_id"] not in cache["channels"]:
                cid = cands[0]["channel_id"]
                custom, uploads, count = fetch_channel_info(cid, key, call=call)
                time.sleep(sleep)
                videos = fetch_all_uploads(uploads, key, call=call) if uploads else []
                time.sleep(sleep)
                cache["channels"][cid] = {"custom_url": custom, "video_count": count,
                                          "videos": videos}
            save_cache(cache_path, cache)
            print(f"[ok] {label}: {cands[0]['title'] if cands else 'no channel found'}")
    except QuotaExceeded as err:
        finished = False
        save_cache(cache_path, cache)
        print(f"\n[!] YouTube daily quota reached. Progress saved. Re-run tomorrow to resume.\n{err}")

    write_outputs(out_dir, cache, targets)
    return finished


def write_outputs(out_dir, cache, targets):
    channel_rows, cand_rows, video_rows = [], [], []
    for label, search_name, kind in targets:
        entry = cache["targets"].get(label)
        if entry is None:
            channel_rows.append({"entity": label, "type": kind, "status": "not yet searched",
                                 "channel_title": "", "channel_url": "", "channel_id": "",
                                 "match_score": "", "needs_review": "", "video_count": "",
                                 "videos_listed": ""})
            continue
        cands = entry["candidates"]
        for rank, c in enumerate(cands, 1):
            cand_rows.append({"entity": label, "rank": rank, "channel_title": c["title"],
                              "channel_id": c["channel_id"], "match_score": c["score"],
                              "channel_url": f"https://www.youtube.com/channel/{c['channel_id']}"})
        if not cands:
            channel_rows.append({"entity": label, "type": kind, "status": "no channel found",
                                 "channel_title": "", "channel_url": "", "channel_id": "",
                                 "match_score": "", "needs_review": "yes", "video_count": 0,
                                 "videos_listed": 0})
            continue
        top = cands[0]
        info = cache["channels"].get(top["channel_id"], {})
        custom = info.get("custom_url", "")
        url = f"https://www.youtube.com/{custom}" if custom else \
            f"https://www.youtube.com/channel/{top['channel_id']}"
        videos = info.get("videos", [])
        channel_rows.append({
            "entity": label, "type": kind, "status": "found",
            "channel_title": top["title"], "channel_url": url,
            "channel_id": top["channel_id"], "match_score": top["score"],
            "needs_review": "yes" if top["score"] < 1 else "no",
            "video_count": info.get("video_count", ""), "videos_listed": len(videos),
        })
        for v in videos:
            video_rows.append({"entity": label, "channel_title": top["title"],
                               "published": v["published"][:10], "title": v["title"],
                               "video_id": v["video_id"], "url": v["url"]})

    write_csv(out_dir / "channels.csv", channel_rows,
              ["entity", "type", "status", "channel_title", "channel_url", "channel_id",
               "match_score", "needs_review", "video_count", "videos_listed"])
    write_csv(out_dir / "channel_candidates.csv", cand_rows,
              ["entity", "rank", "channel_title", "channel_id", "match_score", "channel_url"])
    write_csv(out_dir / "videos.csv", video_rows,
              ["entity", "channel_title", "published", "title", "video_id", "url"])
    print(f"\nWrote {len(channel_rows)} entities, {len(video_rows)} videos to {out_dir}/")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="wy_youtube_out", help="output folder")
    parser.add_argument("--limit", type=int, default=0, help="only the first N targets")
    parser.add_argument("--core-only", action="store_true", help="only the 13 core bodies")
    args = parser.parse_args(argv)

    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not key:
        print("Set YOUTUBE_API_KEY first (see the usage notes at the top of this file).")
        return 2

    targets = build_targets(core_only=args.core_only)
    if args.limit:
        targets = targets[:args.limit]
    print(f"[*] {len(targets)} targets")
    run(Path(args.out), key, targets)
    return 0


if __name__ == "__main__":
    sys.exit(main())
