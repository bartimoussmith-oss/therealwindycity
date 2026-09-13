"""
engine/city_registry.py — Wyoming cities factory + recent 6 months real data

Loads cities/wyoming_cities.json, provides registry + recent meetings from
pipeline/meetings.json + pipeline/cityvideos.json (real data, no external fetch needed).

For each city, config lives in cities/<slug>/config.yaml (seeded via tools/seed-city.py).
Cheyenne is fully live with real meetings; other cities are seeded placeholders that will
be populated when their pullers run in Colab (tools/*_pull.py).

Used by Streamlit region preview to show last 6 months real data per city.
"""
from __future__ import annotations
import json, os
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "cities/wyoming_cities.json"
MEETINGS_INDEX = ROOT / "pipeline/meetings.json"
CITYVIDEOS = ROOT / "pipeline/cityvideos.json"

def load_registry():
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {"cities": []}

def list_cities(state="wy"):
    reg = load_registry()
    return [c for c in reg.get("cities", []) if c.get("state", "wy") == state or state=="wy"]

def get_city(slug: str):
    for c in list_cities():
        if c["slug"] == slug:
            return c
    return None

def recent_meetings(city_slug="cheyenne", months=6):
    """
    Returns meetings from last N months for a city.
    For Cheyenne: uses pipeline/meetings.json (real Granicus index 479 meetings) + cityvideos.json (260 YouTube)
    For other cities: returns seeded placeholder count + instructions to run pullers.
    """
    cutoff = datetime.utcnow() - timedelta(days=months*30)
    # Cheyenne live
    if city_slug == "cheyenne":
        meetings = []
        # meetings.json
        if MEETINGS_INDEX.exists():
            data = json.loads(MEETINGS_INDEX.read_text(encoding="utf-8"))
            for clip_id, info in data.get("meetings", {}).items():
                date_str = info.get("date","")
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                except Exception:
                    continue
                if dt >= cutoff:
                    meetings.append({
                        "clip_id": int(clip_id),
                        "date": date_str,
                        "title": info.get("name","City Council"),
                        "agenda_url": info.get("agenda_url"),
                        "minutes_url": info.get("minutes_url"),
                        "mp4_url": info.get("mp4_url"),
                        "source": "granicus",
                        "external_url": info.get("agenda_url"),
                        "local_path": f"server_data/cheyenne/meetings/{clip_id}/agenda.html",
                    })
        # cityvideos.json for video + captions
        if CITYVIDEOS.exists():
            cv = json.loads(CITYVIDEOS.read_text(encoding="utf-8"))
            for date_str, info in cv.get("meetings", {}).items():
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                except Exception:
                    continue
                if dt >= cutoff:
                    ytid = info.get("id") if isinstance(info, dict) else info
                    title = info.get("title") if isinstance(info, dict) else f"Meeting {date_str}"
                    # merge if not already
                    if not any(m["date"]==date_str for m in meetings):
                        meetings.append({
                            "clip_id": None,
                            "date": date_str,
                            "title": title,
                            "youtube_id": ytid,
                            "youtube_url": f"https://www.youtube.com/watch?v={ytid}" if ytid else None,
                            "source": "youtube",
                            "external_url": f"https://www.youtube.com/watch?v={ytid}",
                            "local_path": f"server_data/cheyenne/captions/{date_str}.vtt",
                        })
        meetings_sorted = sorted(meetings, key=lambda x: x["date"], reverse=True)
        return meetings_sorted
    else:
        # Other cities: placeholder — real pullers will populate cities/<slug>/meetings/
        city = get_city(city_slug)
        # Check if local index exists
        local_index = ROOT / f"cities/{city_slug}/meetings/index.json"
        if local_index.exists():
            try:
                data = json.loads(local_index.read_text())
                return [m for m in data.get("meetings", []) if datetime.strptime(m.get("date","2000-01-01"), "%Y-%m-%d") >= cutoff]
            except Exception:
                pass
        # Return seeded info with instructions
        return [{
            "city": city_slug,
            "status": "seeded",
            "note": f"Run tools for {city_slug}: python tools/seed-city.py {city_slug} wy --granicus {city.get('granicus_domain') if city else ''} then Colab pullers",
            "external_url": city.get("city_site") if city else "",
            "local_path": f"server_data/{city_slug}/ (to be populated)",
        }]

def server_storage_layout():
    """
    Returns the local server storage layout that guarantees no external dependency.
    Every file saved has both external_url and local_path.
    """
    return {
        "root": "server_data/",
        "structure": {
            "cheyenne": {
                "meetings/{clip_id}/": ["agenda.html (local copy) + external_url Granicus", "minutes.pdf + external_url", "docs/*.pdf + external_url MetaViewer", "video/meeting.mp4 + external_url archive-video", "captions.vtt + external_url YouTube", "manifest.json with sha256 + external URLs"],
                "boards/{board}/": ["agendas/*.pdf + external_url city site", "minutes/*.pdf + external_url"],
                "code/municode/": ["Title/*.html + txt + external_url Municode", "previous_versions/"],
                "law/wy_statutes/": ["pdf/*.pdf + external_url wyoleg.gov", "txt/*.txt (local text)", "sections/*.txt"],
                "law/case_law/": ["{cite}/opinion.txt + metadata.json + external_url CourtListener"],
                "wayback/": ["{host}/{timestamp}_{url}.html + original URL"],
                "vectordb/": ["chroma.sqlite3 + chunks.jsonl (local vector DB)"],
                "law_layers/": ["municipal_code.json, statutes.json, case_law.json"]
            }
        },
        "principle": "Every file has external_url preserved in manifest, but local_path is served if external down. RAG vectordb stored locally in server_data/<city>/vectordb/ + synced to R2 for backup. No dependency on external sites for reading.",
        "sync": "tools/server_sync.py syncs Drive/R2 -> server_data/ + verifies sha256",
    }
