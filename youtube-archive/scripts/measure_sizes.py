#!/usr/bin/env python3
"""measure_sizes.py — Measure exact archive.org payload (no downloads).

Fetches metadata for every cataloged IA item, replicates the
download_archiveorg.py picker, and sums the bytes that a full run would
pull. Writes youtube-archive/size_audit.json.
"""
import json, time, urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "Mozilla/5.0 CheyenneArchiveResearch/1.0 (size audit)"}
VIDEO_PREFS = (".mp4", ".mpeg4", ".mov", ".webm", ".ogv")
SKIP_FORMATS = {"Thumbnail", "Item Tile", "Metadata", "Archive BitTorrent",
                "DjVuTXT", "Text", "Single Page Processed JP2 ZIP"}
ROOT = Path(__file__).resolve().parents[1]  # youtube-archive/


def metadata(identifier):
    req = urllib.request.Request(f"https://archive.org/metadata/{identifier}",
                                 headers=UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def pick_video(meta):
    files = [f for f in meta.get("files", [])
             if f.get("format") not in SKIP_FORMATS and not f.get("private", False)]
    videos = [f for f in files if f.get("name", "").lower().endswith(VIDEO_PREFS)]

    def rank(f):
        low = f["name"].lower()
        ext = next((i for i, e in enumerate(VIDEO_PREFS) if low.endswith(e)), 9)
        fmt = (f.get("format") or "").lower()
        fr = 0 if "h.264" in fmt else (1 if "mpeg4" in fmt else 2)
        return (ext, fr, int(f.get("size", 0) or 0))

    videos.sort(key=rank)
    return videos[0] if videos else None


def one(ident):
    for attempt in range(3):
        try:
            m = metadata(ident)
            v = pick_video(m)
            if not v:
                return {"id": ident, "video": None}
            return {"id": ident, "video": v["name"],
                    "format": v.get("format"), "size": int(v.get("size", 0) or 0),
                    "length": v.get("length")}
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                return {"id": ident, "error": str(e)[:100]}
            time.sleep(2)


def main():
    cat = json.load(open(f"{ROOT}/catalog_archiveorg.json"))
    plan = json.load(open(f"{ROOT}/upload_plan.json"))
    skip = {r["source_id"] for r in plan
            if r["source"] == "archiveorg" and r["action"] != "upload"}
    idents = [r["identifier"] for r in cat]
    print(f"{len(idents)} items, {len(skip)} skipped by plan")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=20) as ex:
        results = list(ex.map(one, idents))
    errs = [r for r in results if "error" in r]
    oks = [r for r in results if r.get("size")]
    kept = [r for r in oks if r["id"] not in skip]
    print(f"done in {time.time()-t0:.0f}s: {len(oks)} sized, {len(errs)} errors")
    for r in errs[:10]:
        print("  ERR", r["id"], r["error"])
    json.dump(results, open(f"{ROOT}/size_audit.json", "w"), indent=1)
    gb = lambda b: b / 1e9
    print(f"ALL {len(oks)} IA videos: {gb(sum(r['size'] for r in oks)):.1f} GB")
    print(f"unique-to-plan {len(kept)} IA videos: {gb(sum(r['size'] for r in kept)):.1f} GB")
    lens = [float(r["length"]) for r in kept if r.get("length")]
    print(f"IA hours (kept, with length): {sum(lens)/3600:.0f}h over {len(lens)} items")


if __name__ == "__main__":
    main()
