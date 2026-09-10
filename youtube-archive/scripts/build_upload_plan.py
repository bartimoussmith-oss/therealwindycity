#!/usr/bin/env python3
"""
build_upload_plan.py — Merge the Granicus + archive.org catalogs into one
YouTube upload plan with titles, descriptions, tags, and playlists.

Dedup policy: where the SAME City Council meeting exists in both sources
(matched by calendar date), the Granicus file wins because it is the city's
official record with linked agenda/minutes. The archive.org copy is marked
action=duplicate-skip so you can still review it in the CSV.

Outputs:
  upload_plan.csv   (one row per video: action, source, dates, titles,
                     descriptions, tags, playlist, expected local filename)
  upload_plan.json

Re-run any time after re-scraping; upload_youtube.py consumes upload_plan.csv.
"""
import csv, json, re
from datetime import datetime

GRANICUS_CSV = "catalog_granicus.csv"
ARCHIVEORG_CSV = "catalog_archiveorg.csv"

CHANNEL_DISCLAIMER = (
    "Unofficial public archive. Not affiliated with or endorsed by the "
    "City of Cheyenne."
)

PLAYLISTS = {
    "council": "City Council Meetings",
    "finance": "Finance Committee",
    "services": "Public Services Committee",
    "planning": "Planning Commission",
    "boards": "Boards & Commissions",
    "work": "Work Sessions & Special Meetings",
    "extras": "City Hall Extras & PSAs",
}


def parse_date_iso(s: str) -> str:
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(s[:19] if "T" in s and fmt == "%Y-%m-%d" else s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else ""


def long_date(iso: str) -> str:
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        try:
            return datetime.strptime(iso, "%Y-%m-%d").strftime("%B %d, %Y").replace(" 0", " ")
        except ValueError:
            return iso


def slug(text: str, maxlen: int = 60) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return text[:maxlen] or "meeting"


def classify_ia(title: str) -> str:
    t = title.lower()
    if "planning commission" in t or "planning  commission" in t:
        return "planning"
    if "finance committee" in t:
        return "finance"
    if "public services committee" in t:
        return "services"
    if "board of adjustment" in t or "historic preservation" in t or "board" in t or "commission" in t:
        return "boards"
    if "work session" in t or "special meeting" in t or "committee of the whole" in t:
        return "work"
    if "city council" in t or "council" in t or "governing body" in t or "sine die" in t:
        return "council"
    return "extras"


def main():
    plan = []

    # ---- Granicus rows (City Council / Governing Body, 2008-2026) ----
    with open(GRANICUS_CSV, newline="", encoding="utf-8") as f:
        granicus = list(csv.DictReader(f))
    council_dates = set()
    for r in granicus:
        iso = r["date_iso"]
        if iso:
            council_dates.add(iso)
        if not r["mp4_url"]:
            plan.append({
                "action": "no-video", "source": "granicus",
                "source_id": r["clip_id"], "date_iso": iso,
                "youtube_title": "", "description": "", "tags": "",
                "playlist": PLAYLISTS["council"],
                "expected_file": "",
                "source_url": r["player_url"],
                "agenda_url": r["agenda_url"], "minutes_url": r["minutes_url"],
                "note": f"Granicus entry has no MP4 ({r['name']}). Agenda/minutes link preserved.",
            })
            continue
        title = f"Cheyenne City Council Meeting \u2014 {long_date(iso)}" if iso else \
            f"Cheyenne City Council Meeting (Granicus clip {r['clip_id']})"
        desc = (
            f"{r['name']} \u2014 City of Cheyenne, Wyoming \u2014 {long_date(iso)}.\n"
            f"Duration (Granicus): {r['duration']}.\n\n"
            f"Source: City of Cheyenne Granicus archive ({r['player_url']}).\n"
            + (f"Agenda: {r['agenda_url']}\n" if r["agenda_url"] else "")
            + (f"Minutes: {r['minutes_url']}\n" if r["minutes_url"] else "")
            + f"\nThis is a recording of a public meeting posted as a public record. {CHANNEL_DISCLAIMER}"
        )
        plan.append({
            "action": "upload", "source": "granicus",
            "source_id": r["clip_id"], "date_iso": iso,
            "youtube_title": title[:100], "description": desc,
            "tags": "Cheyenne Wyoming, City Council, public meeting, Granicus, governing body",
            "playlist": PLAYLISTS["council"],
            "expected_file": f"videos/granicus/granicus_clip{r['clip_id']}_{iso or 'nodate'}_{slug(r['name'])}.mp4",
            "source_url": r["player_url"],
            "agenda_url": r["agenda_url"], "minutes_url": r["minutes_url"],
            "note": "",
        })

    # ---- archive.org rows ----
    with open(ARCHIVEORG_CSV, newline="", encoding="utf-8") as f:
        ia_rows = list(csv.DictReader(f))
    for r in ia_rows:
        iso = parse_date_iso(r["date"])
        bucket = classify_ia(r["title"] or "")
        ident = r["identifier"]
        base_title = (r["title"] or ident).strip()
        if iso and iso not in base_title and re.search(r"\d{1,2}-\d{1,2}-\d{2,4}", base_title) is None:
            yt_title = f"{base_title} \u2014 {long_date(iso)}"
        else:
            yt_title = base_title
        yt_title = yt_title[:100]
        desc = (
            f"{base_title} \u2014 City of Cheyenne, Wyoming"
            + (f" \u2014 {long_date(iso)}" if iso else "") + ".\n\n"
            f"Source: Internet Archive community collection ({r['item_url']}).\n"
            f"Original publisher materials courtesy of the City of Cheyenne.\n\n"
            f"This is a recording of a public meeting posted as a public record. {CHANNEL_DISCLAIMER}"
        )
        tags = {"council": "Cheyenne Wyoming, City Council, public meeting, governing body",
                "finance": "Cheyenne Wyoming, Finance Committee, public meeting",
                "services": "Cheyenne Wyoming, Public Services Committee, public meeting",
                "planning": "Cheyenne Wyoming, Planning Commission, public meeting, zoning",
                "boards": "Cheyenne Wyoming, public meeting, board, commission",
                "work": "Cheyenne Wyoming, work session, public meeting",
                "extras": "Cheyenne Wyoming, city hall, PSA"}[bucket]
        action, note = "upload", ""
        if bucket == "council" and iso and iso in council_dates:
            action = "duplicate-skip"
            note = "Same-date City Council meeting already covered by Granicus (official record)."
        elif bucket == "council" and iso:
            # archive.org item dates are often the *upload* date, 1-3 days after
            # the meeting, so flag near-matches for human review.
            try:
                base = datetime.strptime(iso, "%Y-%m-%d").date()
                near = []
                for delta in (-4, -3, -2, -1, 1, 2, 3, 4):
                    cand = (base.fromordinal(base.toordinal() + delta)).strftime("%Y-%m-%d")
                    if cand in council_dates:
                        near.append(cand)
                if near:
                    note = ("Possible duplicate: Granicus has council video(s) within days: "
                            + ", ".join(near) + ". Verify before uploading.")
            except ValueError:
                pass
        plan.append({
            "action": action, "source": "archiveorg",
            "source_id": ident, "date_iso": iso,
            "youtube_title": yt_title, "description": desc, "tags": tags,
            "playlist": PLAYLISTS[bucket],
            "expected_file": f"videos/archiveorg/ia_{ident}.mp4",
            "source_url": r["item_url"], "agenda_url": "", "minutes_url": "",
            "note": note,
        })

    plan.sort(key=lambda p: (p["date_iso"] or "9999", p["source"], p["source_id"]))

    with open("upload_plan.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["action", "source", "source_id", "date_iso",
                                          "youtube_title", "description", "tags",
                                          "playlist", "expected_file", "source_url",
                                          "agenda_url", "minutes_url", "note"])
        w.writeheader()
        w.writerows(plan)
    with open("upload_plan.json", "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)

    from collections import Counter
    print(f"Wrote upload_plan.csv / .json with {len(plan)} rows.")
    print("By action:", dict(Counter(p["action"] for p in plan)))
    print("Uploads by playlist:",
          dict(Counter(p["playlist"] for p in plan if p["action"] == "upload")))


if __name__ == "__main__":
    main()
