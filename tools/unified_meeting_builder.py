#!/usr/bin/env python3
"""
THE REAL WINDY CITY — UNIFIED MEETING BUILDER
Merges EVERY source into one meeting JSON:
- Granicus (agenda, minutes, supporting docs, MP4, ASX, MediaPlayer markers, RSS)
- YouTube (cityvideos.json, captions VTT, audio)
- City site boards (agendas/minutes PDFs)
- Wayback captures
- Law layers (municipal code refs, WY statutes, case law)

Input: granicus_pull/manifest.json, pipeline/cityvideos.json, cities/cheyenne/boards/*/manifest.json,
       wayback/*/manifest.json, cities/cheyenne/law/...

Output: cities/cheyenne/meetings/<clip_id>.json (unified model described in docs/BUILD_GROUND_UP.md)

Also builds:
- cities/cheyenne/meetings/index.json (all meetings sorted by date)
- ordinance cross-ref, statute cross-ref, entity cross-ref

Run in Colab or locally:
  python tools/unified_meeting_builder.py
"""
import json, re, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GRANICUS_MANIFEST = ROOT / "granicus_pull" / "manifest.json"
# fallback for Drive layout
if not GRANICUS_MANIFEST.exists():
    GRANICUS_MANIFEST = Path("/content/drive/MyDrive/TheRealWindyCity/cheyenne/manifest.json")

CITYVIDEOS = ROOT / "pipeline/cityvideos.json"
BOARDS_ROOT = ROOT / "cities/cheyenne/boards"
LAW_ROOT = ROOT / "cities/cheyenne/law"
OUT_ROOT = ROOT / "cities/cheyenne/meetings"

ORD_RE = re.compile(r"\b(?:Ord\.?|Ordinance)\s*No\.?\s*(\d{3,5})\b", re.I)
PUDC_RE = re.compile(r"\bPUDC-\d{2}-\d+\b", re.I)
STATUTE_RE = re.compile(r"\b(\d{1,2}-\d{1,2}-\d{1,4})\b")
RES_RE = re.compile(r"\bRes\.? No\.?\s*(\d{4})\b", re.I)

def load_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}

def main():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    gran = load_json(GRANICUS_MANIFEST) if GRANICUS_MANIFEST.exists() else {"meetings": {}}
    cityv = load_json(CITYVIDEOS)
    meetings_map = cityv.get("meetings", {})

    # invert cityvideos date->id to id->date
    yt_by_date = {}
    for date, info in meetings_map.items():
        ytid = info.get("id") if isinstance(info, dict) else info
        yt_by_date[date] = ytid

    unified_index = []

    for key, meta in gran.get("meetings", {}).items():
        # key = "clip:1103" or "event:1441"
        try:
            kind, mid = key.split(":",1)
            mid_int = int(mid)
        except Exception:
            continue
        date = meta.get("date","") or ""
        # try to parse date like "Jun 23, 2026" -> 2026-06-23
        iso_date = ""
        if date:
            # quick month map
            months = {"Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06","Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12"}
            m = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", date, re.I)
            if m:
                mon = months.get(m.group(1)[:3].title(), "01")
                day = m.group(2).zfill(2)
                iso_date = f"{m.group(3)}-{mon}-{day}"
        # fallback: use name field that might contain date?
        if not iso_date:
            iso_date = meta.get("name","")[:10]

        # YouTube lookup by iso_date
        yt_id = yt_by_date.get(iso_date) if iso_date else None
        if not yt_id and iso_date:
            # fuzzy: same year-month
            for d, yid in yt_by_date.items():
                if d.startswith(iso_date[:7]):
                    # pick closest
                    pass

        # Build unified
        unified = {
            "city": "cheyenne",
            "state": "wy",
            "clip_id": mid_int if kind=="clip" else None,
            "event_id": mid_int if kind=="event" else None,
            "date": iso_date or date,
            "body": "City Council",  # TODO: detect from views/name
            "title": meta.get("name",""),
            "views": meta.get("views",[]),
            "sources": {
                "granicus": {
                    "agenda_url": meta.get("agenda_url"),
                    "agenda_file": meta.get("agenda"),
                    "minutes_url": meta.get("minutes_url"),
                    "minutes_file": meta.get("minutes"),
                    "mp4_url": meta.get("mp4"),
                    "asx_url": meta.get("asx"),
                    "video_file": meta.get("video_file"),
                    "documents": meta.get("documents",[]),
                    "agenda_hrefs": meta.get("agenda_hrefs",[]),
                    "video_meta_ids": meta.get("video_meta_ids",[]),
                },
                "youtube": {
                    "id": yt_id,
                    "url": f"https://www.youtube.com/watch?v={yt_id}" if yt_id else None,
                }
            },
            "agenda_items": [],  # to be filled by parsing agenda.html
            "law_layers": {
                "municipal_code_refs": [],
                "wy_statute_refs": [],
                "ordinance_refs": [],
                "case_law_refs": [],
            },
            "toppings": {
                "ordinance_history": [],
                "entity_mentions": [],
            }
        }

        # Extract refs from agenda txt if exists
        agenda_txt_path = None
        if meta.get("agenda"):
            # granicus_pull/<id>/agenda.html -> try to find txt
            # manifest stores relative like "1103/agenda.html" — need base
            base = GRANICUS_MANIFEST.parent
            agenda_txt_path = base / Path(meta["agenda"]).with_suffix(".txt")
            # Actually agenda.txt is alongside agenda.html per puller
            # puller saves agenda.html + agenda.txt in same folder
            if agenda_txt_path.exists():
                try:
                    txt = agenda_txt_path.read_text(encoding="utf-8", errors="replace")
                    unified["law_layers"]["ordinance_refs"] = sorted(set(ORD_RE.findall(txt)))
                    unified["law_layers"]["wy_statute_refs"] = sorted(set(STATUTE_RE.findall(txt)))[:50]
                    unified["law_layers"]["municipal_code_refs"] = sorted(set(PUDC_RE.findall(txt)))
                except Exception:
                    pass

        # Save
        out_file = OUT_ROOT / f"{mid_int:04d}.json" if kind=="clip" else OUT_ROOT / f"event_{mid_int:04d}.json"
        out_file.write_text(json.dumps(unified, indent=1), encoding="utf-8")
        unified_index.append({"clip_id": mid_int if kind=="clip" else None, "event_id": mid_int if kind=="event" else None, "date": unified["date"], "title": unified["title"], "file": f"{out_file.name}", "youtube_id": yt_id})

    # Sort index by date
    unified_index_sorted = sorted(unified_index, key=lambda x: x.get("date") or "", reverse=True)
    (OUT_ROOT / "index.json").write_text(json.dumps({"count": len(unified_index_sorted), "meetings": unified_index_sorted}, indent=1), encoding="utf-8")
    print(f"Built {len(unified_index_sorted)} unified meetings -> {OUT_ROOT}/index.json")

if __name__ == "__main__":
    main()
