#!/usr/bin/env python3
"""
download_archiveorg.py — Download City of Cheyenne meeting videos from archive.org.

The Internet Archive hosts a community 'cochwy' collection (773 items as of
Sep 2026): City Council, Finance Committee, Public Services Committee, Planning
Commission, work sessions, PSAs. Unlike Granicus, archive.org allows downloads
from anywhere, so this script works on any connection.

For each item it picks the best upload-ready video file (prefers the .mp4
derivative, falls back to .mpeg4/.mov) and also grabs captions (.vtt/.srt)
when present so you can attach them to the YouTube upload.

Usage examples:
  pip install -r requirements.txt
  python scripts/download_archiveorg.py --limit 3 --contains Finance
  python scripts/download_archiveorg.py --contains "Planning Commission"
  python scripts/download_archiveorg.py --identifiers cochwy-City_Council_-_11-24-25
  python scripts/download_archiveorg.py --from-date 2024-01-01
"""
import argparse, csv, json, os, time, urllib.parse, urllib.request
import requests
from tqdm import tqdm

UA = {"User-Agent": "Mozilla/5.0 CheyenneArchiveResearch/1.0 (bulk civic archiving)"}
VIDEO_PREFS = (".mp4", ".mpeg4", ".mov", ".webm", ".ogv")
SKIP_FORMATS = {"Thumbnail", "Item Tile", "Metadata", "Archive BitTorrent",
                "DjVuTXT", "Text", "Single Page Processed JP2 ZIP"}


def metadata(identifier: str) -> dict:
    url = f"https://archive.org/metadata/{identifier}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def pick_files(meta: dict):
    """Return (video_file_dict|None, [caption_file_dicts])."""
    files = [f for f in meta.get("files", [])
             if f.get("format") not in SKIP_FORMATS and not f.get("private", False)]
    videos, captions = [], []
    for f in files:
        name = f.get("name", "")
        low = name.lower()
        if low.endswith((".vtt", ".srt")):
            captions.append(f)
        elif low.endswith(VIDEO_PREFS):
            videos.append(f)
    def rank(f):
        low = f["name"].lower()
        # prefer .mp4, prefer h.264 derivative over huge originals
        ext_rank = next((i for i, ext in enumerate(VIDEO_PREFS) if low.endswith(ext)), 9)
        fmt = (f.get("format") or "").lower()
        fmt_rank = 0 if "h.264" in fmt else (1 if "mpeg4" in fmt else 2)
        return (ext_rank, fmt_rank, int(f.get("size", 0) or 0))
    videos.sort(key=rank)
    return (videos[0] if videos else None, captions)


def file_url(identifier: str, name: str) -> str:
    return ("https://archive.org/download/" + identifier + "/"
            + urllib.parse.quote(name))


def download(url: str, dest: str) -> str:
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return "skipped"
    tmp = dest + ".part"
    existing = os.path.getsize(tmp) if os.path.exists(tmp) else 0
    for attempt in range(1, 4):
        try:
            headers = dict(UA)
            if existing:
                headers["Range"] = f"bytes={existing}-"
            with requests.get(url, headers=headers, stream=True, timeout=60) as r:
                if r.status_code == 416:
                    os.rename(tmp, dest)
                    return "ok"
                r.raise_for_status()
                total = r.headers.get("Content-Length")
                total = (int(total) + existing) if total else None
                mode = "ab" if (existing and r.status_code == 206) else "wb"
                if mode == "wb":
                    existing = 0
                with open(tmp, mode) as f, tqdm(
                        total=total, initial=existing, unit="B",
                        unit_scale=True, desc=os.path.basename(dest)) as bar:
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)
                            bar.update(len(chunk))
            os.rename(tmp, dest)
            return "ok"
        except Exception as e:  # noqa: BLE001
            print(f"  attempt {attempt}/3 failed: {e}")
            time.sleep(5 * attempt)
    raise RuntimeError("failed after 3 attempts")


def main():
    ap = argparse.ArgumentParser(description="Download Cheyenne videos from archive.org.")
    ap.add_argument("--catalog", default="catalog_archiveorg.csv")
    ap.add_argument("--out", default="videos/archiveorg")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--contains", default="", help="only items whose title contains this (case-insensitive)")
    ap.add_argument("--identifiers", nargs="*", default=[])
    ap.add_argument("--from-date", default="")
    ap.add_argument("--no-captions", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    with open(args.catalog, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.identifiers:
        want = set(args.identifiers)
        rows = [r for r in rows if r["identifier"] in want]
    if args.contains:
        rows = [r for r in rows if args.contains.lower() in r["title"].lower()]
    if args.from_date:
        rows = [r for r in rows if r["date"][:10] >= args.from_date]
    rows.sort(key=lambda r: r["date"])
    if args.limit:
        rows = rows[:args.limit]

    print(f"{len(rows)} items queued -> {args.out}/")
    ok = skipped = failed = 0
    for i, row in enumerate(rows, 1):
        ident = row["identifier"]
        print(f"\n[{i}/{len(rows)}] {ident} | {(row['title'] or '')[:80]}")
        try:
            meta = metadata(ident)
            video, captions = pick_files(meta)
            if not video:
                print("  no video file found, skipping")
                failed += 1
                continue
            ext = os.path.splitext(video["name"])[1].lower() or ".mp4"
            dest = os.path.join(args.out, f"ia_{ident}{ext}")
            size_mb = int(video.get("size", 0) or 0) / 1e6
            print(f"  file: {video['name']} ({size_mb:.0f} MB)")
            res = download(file_url(ident, video["name"]), dest)
            print("  already downloaded, skipping" if res == "skipped" else "  downloaded")
            if res == "skipped":
                skipped += 1
            else:
                ok += 1
            if not args.no_captions:
                for cap in captions[:2]:  # usually .vtt + .srt of same track
                    cap_ext = os.path.splitext(cap["name"])[1].lower()
                    cap_dest = os.path.splitext(dest)[0] + cap_ext
                    try:
                        download(file_url(ident, cap["name"]), cap_dest)
                        print(f"  caption: {os.path.basename(cap_dest)}")
                    except Exception as e:  # noqa: BLE001
                        print(f"  caption failed (non-fatal): {e}")
            time.sleep(2)  # be polite to archive.org
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED: {e}")
            failed += 1
    print(f"\nDone: {ok} downloaded, {skipped} already present, {failed} failed/skipped.")


if __name__ == "__main__":
    main()
