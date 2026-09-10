#!/usr/bin/env python3
"""
scrape_granicus.py — Build a catalog of all City of Cheyenne Granicus meeting videos.

Fetches https://cheyenne.granicus.com/ViewPublisher.php?view_id=2 (the City Council /
Governing Body archive) and parses the archive table into CSV + JSON.

Outputs (in the project root):
  catalog_granicus.csv
  catalog_granicus.json

Safe to re-run: it overwrites the catalog files with a fresh scrape.
"""
import csv, json, re, sys, urllib.request
from html import unescape
from datetime import datetime, timezone

VIEW_ID = 2
ARCHIVE_URL = f"https://cheyenne.granicus.com/ViewPublisher.php?view_id={VIEW_ID}"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CheyenneArchiveResearch/1.0"}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    # Granicus pages declare iso-8859-1; decode leniently
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("iso-8859-1", errors="replace")


def clean(text: str) -> str:
    text = unescape(re.sub(r"<.*?>", "", text or "")).strip()
    return re.sub(r"\s+", " ", text)


def parse(html: str):
    m = re.search(r'<table class="listingTable" id="archive".*?</table>', html, re.S)
    if not m:
        raise SystemExit("Archive table not found — page layout may have changed.")
    rows = re.findall(r'<tr class="(?:odd|even)".*?</tr>', m.group(0), re.S)
    items = []
    for r in rows:
        name_m = re.search(r'<td class="listItem" headers="Name".*?>(.*?)</td>', r, re.S)
        name = clean(name_m.group(1)) if name_m else ""
        date_m = re.search(r'<span style="display:none;">(\d+)</span>([^<]+)', r)
        ts = date_m.group(1) if date_m else ""
        date_disp = date_m.group(2).strip() if date_m else ""
        date_iso = ""
        if ts:
            try:
                date_iso = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
            except ValueError:
                pass
        dur_m = re.search(r'headers="Duration[^"]*">(.*?)</td>', r, re.S)
        duration = clean(dur_m.group(1)).replace("\xa0", " ") if dur_m else ""
        clip_m = re.search(r"clip_id=(\d+)", r)
        clip_id = clip_m.group(1) if clip_m else ""
        ag_m = re.search(r'href="([^"]*AgendaViewer[^"]*)"', r)
        agenda = ("https:" + ag_m.group(1)) if ag_m and ag_m.group(1).startswith("//") else (ag_m.group(1) if ag_m else "")
        min_m = re.search(r'href="([^"]*MinutesViewer[^"]*)"', r)
        minutes = ("https:" + min_m.group(1)) if min_m and min_m.group(1).startswith("//") else (min_m.group(1) if min_m else "")
        mp4_m = re.search(r'href="(https://archive-video[^"]+\.mp4)"', r)
        mp4 = mp4_m.group(1) if mp4_m else ""
        # HLS stream URL follows the same file id as the MP4 on archive-stream host
        stream = ""
        if mp4:
            file_id = mp4.rsplit("/", 1)[-1]  # cheyenne_<guid>.mp4
            stream = f"https://archive-stream.granicus.com/OnDemand/_definst_/mp4:archive/cheyenne/{file_id}/playlist.m3u8"
        player = f"https://cheyenne.granicus.com/player/clip/{clip_id}?view_id={VIEW_ID}&redirect=true" if clip_id else ""
        items.append({
            "clip_id": clip_id,
            "name": name,
            "date_display": date_disp,
            "date_iso": date_iso,
            "timestamp": ts,
            "duration": duration,
            "mp4_url": mp4,
            "stream_url": stream,
            "player_url": player,
            "agenda_url": agenda,
            "minutes_url": minutes,
        })
    return items


def main():
    if len(sys.argv) > 1:  # allow passing a saved HTML file for offline parsing
        with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
            html = f.read()
    else:
        print(f"Fetching {ARCHIVE_URL} ...")
        html = fetch(ARCHIVE_URL)
    items = parse(html)
    print(f"Parsed {len(items)} archive rows "
          f"({sum(1 for i in items if i['mp4_url'])} with MP4 links).")

    with open("catalog_granicus.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["clip_id", "name", "date_display", "date_iso",
                                          "timestamp", "duration", "mp4_url", "stream_url",
                                          "player_url", "agenda_url", "minutes_url"])
        w.writeheader()
        w.writerows(items)

    with open("catalog_granicus.json", "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)

    print("Wrote catalog_granicus.csv and catalog_granicus.json")


if __name__ == "__main__":
    main()
