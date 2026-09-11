#!/usr/bin/env python3
"""
download_granicus.py — Download City of Cheyenne meeting MP4s from Granicus.

Reads catalog_granicus.csv (built by scrape_granicus.py) and downloads each MP4
with resume + retries. Be polite: default is sequential with a short delay.

IMPORTANT — run this on your HOME internet connection (your own PC in Cheyenne,
a laptop, etc.), NOT on a cloud server / VPS / datacenter machine:
Granicus serves video through CloudFront with bot protection that returns
HTTP 403 to most datacenter/VPN IP ranges. From a normal residential IP the
exact same MP4 links download fine.

Usage examples:
  pip install -r requirements.txt
  python scripts/download_granicus.py --limit 3            # test with 3 newest
  python scripts/download_granicus.py                      # download everything
  python scripts/download_granicus.py --from-date 2024-01-01
  python scripts/download_granicus.py --only 1126 1124 1122
  python scripts/download_granicus.py --workers 2 --delay 2

Storage: council meetings run ~1-4 hours each. Expect roughly 0.3-1.5 GB per
video, i.e. on the order of 200-500 GB for the full 474-video back catalog.
Point --out at a drive with room (external USB drive works fine).
"""
import argparse, csv, os, re, sys, time
import requests
from tqdm import tqdm

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Referer": "https://cheyenne.granicus.com/",
}


def slug(text: str, maxlen: int = 60) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return text[:maxlen] or "meeting"


def expected_filename(row: dict) -> str:
    return f"granicus_clip{row['clip_id']}_{row['date_iso'] or 'nodate'}_{slug(row['name'])}.mp4"


def download(url: str, dest: str, delay: float) -> str:
    """Download with resume + retries. Returns 'ok' | 'skipped' | raises."""
    tmp = dest + ".part"
    existing = os.path.getsize(tmp) if os.path.exists(tmp) else 0
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return "skipped"
    last_err = None
    for attempt in range(1, 4):
        try:
            headers = dict(HEADERS)
            if existing:
                headers["Range"] = f"bytes={existing}-"
            with requests.get(url, headers=headers, stream=True, timeout=60) as r:
                if r.status_code == 403:
                    raise RuntimeError(
                        "HTTP 403 from Granicus CloudFront. This almost always means "
                        "your IP is a datacenter/VPN range. Re-run this script from a "
                        "normal home internet connection.")
                if r.status_code == 416:  # range past EOF: part file is complete
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
            if delay:
                time.sleep(delay)
            return "ok"
        except Exception as e:  # noqa: BLE001 - retry then report
            last_err = e
            if "403" in str(e):
                raise
            print(f"  attempt {attempt}/3 failed: {e}")
            time.sleep(5 * attempt)
    raise RuntimeError(f"failed after 3 attempts: {last_err}")


def main():
    ap = argparse.ArgumentParser(description="Download Cheyenne Granicus meeting videos.")
    ap.add_argument("--catalog", default="catalog_granicus.csv")
    ap.add_argument("--out", default="videos/granicus")
    ap.add_argument("--limit", type=int, default=0, help="only first N rows (newest first)")
    ap.add_argument("--only", nargs="*", default=[], help="only these clip_id values")
    ap.add_argument("--from-date", default="", help="only videos on/after YYYY-MM-DD")
    ap.add_argument("--to-date", default="", help="only videos on/before YYYY-MM-DD")
    ap.add_argument("--delay", type=float, default=3.0, help="seconds between downloads")
    ap.add_argument("--newest-first", action="store_true", default=True)
    ap.add_argument("--oldest-first", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    with open(args.catalog, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    only = set(args.only)
    if only:
        rows = [r for r in rows if r["clip_id"] in only]
    if args.from_date:
        rows = [r for r in rows if r["date_iso"] >= args.from_date]
    if args.to_date:
        rows = [r for r in rows if r["date_iso"] and r["date_iso"] <= args.to_date]
    rows = [r for r in rows if r["mp4_url"]]  # skip agenda-only entries
    rows.sort(key=lambda r: r["date_iso"] or "", reverse=not args.oldest_first)
    if args.limit:
        rows = rows[:args.limit]

    print(f"{len(rows)} videos queued -> {args.out}/")
    ok = skipped = failed = 0
    failures = []
    for i, row in enumerate(rows, 1):
        dest = os.path.join(args.out, expected_filename(row))
        print(f"\n[{i}/{len(rows)}] clip {row['clip_id']} | {row['name']} | "
              f"{row['date_display']} | {row['duration']}")
        try:
            res = download(row["mp4_url"], dest, args.delay)
            if res == "skipped":
                print("  already downloaded, skipping")
                skipped += 1
            else:
                ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED: {e}")
            failures.append((row["clip_id"], str(e)))
            failed += 1
            if "403" in str(e):
                print("\nStopping: fix the network/IP issue, then re-run "
                      "(completed files are skipped).")
                break

    print(f"\nDone: {ok} downloaded, {skipped} already present, {failed} failed.")
    if failures:
        print("Failures:")
        for clip, err in failures:
            print(f"  clip {clip}: {err[:160]}")


if __name__ == "__main__":
    main()
