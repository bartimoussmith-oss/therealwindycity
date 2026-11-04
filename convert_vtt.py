#!/usr/bin/env python3
"""
convert_vtt.py — Convert Google Drive VTT caption files to corpus_yt format.

Reads VTT files from google_drive/, converts to plain text with [HH:MM:SS]
timestamps, adds the required MEETING/DATE/YT_ID/VIDEO header, and saves to
pipeline/corpus_yt/drive_transcripts/.

Matching strategy:
  1. If filename has YouTube ID (pattern YYYY-MM-DD_VIDEOID), look up date
     in harvest_state.json, then match to queue by date+body.
  2. Otherwise, fuzzy-match by date (±3 days) + body type hint.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GDRIVE = ROOT / "google_drive"
OUTDIR = ROOT / "pipeline" / "corpus_yt"
QUEUE_PATH = ROOT / "notebooklm_controller" / "state" / "queue.json"
HARVEST_PATH = GDRIVE / ".harvest_state.json"

OUTDIR.mkdir(parents=True, exist_ok=True)

# ── Load harvest state ─────────────────────────────────────────────────────
harvest: dict[str, dict] = {}
if HARVEST_PATH.exists():
    harvest = json.loads(HARVEST_PATH.read_text(encoding="utf-8"))

# Build: youtube_id → date (for has_transcript=true entries)
ytid_to_date: dict[str, str] = {}
# Build: date → list of youtube_ids with has_transcript
date_to_youtube_ids: dict[str, list[str]] = {}
for vid, info in harvest.items():
    if info.get("has_transcript"):
        d = info["date"]
        ytid_to_date[vid] = d
        date_to_youtube_ids.setdefault(d, []).append(vid)

# ── Load queue ─────────────────────────────────────────────────────────────
queue: list[dict] = []
if QUEUE_PATH.exists():
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))

# Index queue by (date, body) and by date
queue_by_date_body: dict[tuple[str, str], dict] = {}
queue_by_date: dict[str, list[dict]] = {}
for m in queue:
    queue_by_date_body[(m["date"], m["body"])] = m
    queue_by_date.setdefault(m["date"], []).append(m)

# Parse all queue dates for fuzzy matching
queue_dates = sorted(set(m["date"] for m in queue))


def slugify_body(name: str) -> str:
    n = name.lower().strip()
    n = re.sub(r"\s*\(\d{1,2}/\d{1,2}/\d{2}\)", "", n)
    n = re.sub(r"\|\s*regular meeting\s*\|", " ", n, flags=re.IGNORECASE)
    n = re.sub(r"\bregular meeting\b", "", n, flags=re.IGNORECASE)
    BODY_MAP = [
        ("city council", "city-council"),
        ("committee of the whole", "committee-of-the-whole"),
        ("public services", "public-services-committee"),
        ("finance committee", "finance-committee"),
        ("planning commission", "planning-commission"),
        ("board of adjustment", "board-of-adjustment"),
        ("historic preservation", "historic-preservation"),
        ("urban renewal", "urban-renewal"),
        ("goal setting", "goal-setting"),
        ("work session", "work-session"),
        ("special meeting", "special-city-council"),
        ("council update", "city-council"),
    ]
    for k, v in BODY_MAP:
        n = n.replace(k, v)
    n = re.sub(r"[^a-z0-9]+", "-", n).strip("-")
    return n or "meeting"


def vtt_to_plain(vtt_text: str) -> list[tuple[str, str]]:
    """Convert VTT text to list of (timestamp, text) tuples."""
    cues: list[tuple[str, str]] = []
    lines = vtt_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:") or not line:
            i += 1
            continue
        m = re.match(r"^(\d{2}):(\d{2}):(\d{2})\.\d+\s*-->", line)
        if m:
            hh, mm, ss = m.group(1), m.group(2), m.group(3)
            ts = f"{hh}:{mm}:{ss}"
            i += 1
            text_parts: list[str] = []
            while i < len(lines):
                t = lines[i].strip()
                if not t:
                    break
                if re.match(r"^\d{2}:\d{2}:\d{2}\.\d+\s*-->", t):
                    break
                t = re.sub(r"<\d{2}:\d{2}:\d{2}\.\d+>", "", t)
                t = re.sub(r"</?c>", "", t)
                t = re.sub(r"</?v[^>]*>", "", t)
                t = re.sub(r"<[^>]+>", "", t)
                t = t.replace("&gt;&gt;", ">>").replace("&amp;", "&")
                t = unicodedata.normalize("NFKC", t).strip()
                if t:
                    text_parts.append(t)
                i += 1
            if text_parts:
                cues.append((ts, " ".join(text_parts)))
        else:
            i += 1
    return cues


def parse_filename(name: str) -> dict | None:
    """Extract date, youtube_id, and body hint from VTT filename."""
    stem = Path(name).stem
    stem = re.sub(r"\.en(-orig)?$", "", stem)

    # Pattern 1: YYYY-MM-DD_VIDEOID (e.g., 2026-06-01_AEKufmR2Dc0)
    m = re.match(r"^(\d{4}-\d{2}-\d{2})_([A-Za-z0-9_-]+)$", stem)
    if m:
        return {"date": m.group(1), "youtube_id": m.group(2), "body_hint": None}

    # Pattern 2: YYYYMMDD - Meeting Name (M/D/YY) (e.g., 20180109 - City Council meeting (01⧸09⧸18))
    # The YYYYMMDD prefix is the UPLOAD date; the (M/D/YY) in parens is the MEETING date.
    # Use the meeting date from parens since inventory matches against queue dates.
    # Filenames may use regular "/" or Unicode fraction slash "⧸" (U+29F8).
    m = re.match(r"^(\d{8})\s*-\s*(.+?)(?:\s*\((\d{1,2})[/\u29f8](\d{1,2})[/\u29f8](\d{2})\))?$", stem)
    if m:
        name_part = m.group(2).strip()
        # Prefer meeting date from parentheses
        if m.group(3):
            month, day, year = m.group(3), m.group(4), m.group(5)
            yy = int(year)
            full_year = 2000 + yy if yy < 50 else 1900 + yy
            date_val = f"{full_year:04d}-{int(month):02d}-{int(day):02d}"
        else:
            # Fallback: use YYYYMMDD prefix (upload date)
            date_str = m.group(1)
            date_val = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        return {"date": date_val, "youtube_id": None, "body_hint": name_part}

    # Pattern 3: YYYY-MM-DD - Meeting Name (e.g., 2025-09-16 - Finance Committee - 09-15-2025)
    m = re.match(r"^(\d{4}-\d{2}-\d{2})\s*-\s*(.+)$", stem)
    if m:
        return {"date": m.group(1), "youtube_id": None, "body_hint": m.group(2).strip()}

    return None


def find_best_match(vtt_date: str, body_hint: str | None, filename_youtube_id: str | None) -> tuple[str | None, str | None, str | None]:
    """
    Find best matching queue entry.
    Returns (youtube_id, body_slug, match_reason, matched_date).
    matched_date is the queue entry's date (may differ from vtt_date due to upload vs meeting date).
    """
    # ── Step 1: If we have a YouTube ID from filename, use harvest to get correct date ──
    if filename_youtube_id and filename_youtube_id in ytid_to_date:
        correct_date = ytid_to_date[filename_youtube_id]
        # Try to find body for this date
        if correct_date in queue_by_date:
            bodies = [m["body"] for m in queue_by_date[correct_date]]
            if body_hint:
                slug = slugify_body(body_hint)
                if slug in bodies:
                    return filename_youtube_id, slug, "ytid-direct", correct_date
            if len(bodies) == 1:
                return filename_youtube_id, bodies[0], "ytid-single", correct_date
            # Try fuzzy body match
            if body_hint:
                hint_lower = body_hint.lower()
                for b in bodies:
                    if b.replace("-", " ") in hint_lower or hint_lower in b.replace("-", " "):
                        return filename_youtube_id, b, "ytid-fuzzy", correct_date
            return filename_youtube_id, bodies[0], "ytid-first", correct_date

    # ── Step 2: Fuzzy date matching ±3 days ──
    try:
        vtt_d = date.fromisoformat(vtt_date)
    except ValueError:
        return None, None, "no-date", None

    candidates = []
    for offset in range(0, 4):
        for sign in (1, -1):
            target = vtt_d + timedelta(days=sign * offset)
            target_str = target.isoformat()
            if target_str in queue_by_date:
                for m in queue_by_date[target_str]:
                    candidates.append((abs(sign * offset), m))

    if not candidates:
        return None, None, "no-date-match", None

    # Sort by date offset, then try body match
    candidates.sort(key=lambda x: x[0])

    # First pass: exact body match
    if body_hint:
        slug = slugify_body(body_hint)
        for _, m in candidates:
            if m["body"] == slug:
                yt = m.get("youtube_id") or filename_youtube_id
                return yt, m["body"], "fuzzy-date-body", m["date"]

    # Second pass: fuzzy body match
    if body_hint:
        hint_lower = body_hint.lower()
        for _, m in candidates:
            if m["body"].replace("-", " ") in hint_lower or hint_lower in m["body"].replace("-", " "):
                yt = m.get("youtube_id") or filename_youtube_id
                return yt, m["body"], "fuzzy-date-hint", m["date"]

    # Third pass: first candidate (closest date)
    _, m = candidates[0]
    yt = m.get("youtube_id") or filename_youtube_id
    return yt, m["body"], "fuzzy-date-first", m["date"]


def main() -> None:
    vtt_files = sorted(GDRIVE.glob("*.vtt"))
    print(f"Found {len(vtt_files)} VTT files in google_drive/")

    converted = 0
    skipped = 0
    matched = 0
    unmatched = []

    for vtt_path in vtt_files:
        info = parse_filename(vtt_path.name)
        if not info:
            print(f"  SKIP (unrecognized name): {vtt_path.name}")
            skipped += 1
            continue

        vtt_date = info["date"]
        yt_id = info["youtube_id"]
        body_hint = info["body_hint"]

        # Find best match
        yt_id, body, reason, match_date = find_best_match(vtt_date, body_hint, yt_id)

        # Read and convert VTT
        try:
            vtt_text = vtt_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"  SKIP (read error): {vtt_path.name}: {exc}")
            skipped += 1
            continue

        cues = vtt_to_plain(vtt_text)
        if not cues:
            print(f"  SKIP (no cues): {vtt_path.name}")
            skipped += 1
            continue

        # Build output filename — use matched queue date if available
        yt_part = yt_id if yt_id else "no-ytid"
        body_part = body if body else "unknown"
        if not match_date:
            match_date = vtt_date

        out_name = f"{match_date}-{body_part}-{yt_part}.txt"
        out_path = OUTDIR / out_name

        # Build header
        video_url = f"https://www.youtube.com/watch?v={yt_id}" if yt_id else ""
        header_lines = [
            f"MEETING: {body_part} | DATE: {match_date} | YT_ID: {yt_id or ''}",
            "SOURCE: verbatim YouTube captions via Google Drive (bartimoussmith-oss)",
        ]
        if video_url:
            header_lines.append(f"VIDEO: {video_url}")
        header_lines.append("")
        header_lines.append("")

        # Build body with timestamps
        body_lines = []
        for ts, text in cues:
            body_lines.append(f"[{ts}] {text}")

        output = "\n".join(header_lines + body_lines) + "\n"
        out_path.write_text(output, encoding="utf-8")
        converted += 1
        if reason != "no-match" and reason != "no-date-match":
            matched += 1
            print(f"  {reason.upper()}: {vtt_path.name} → {out_name} ({len(cues)} cues)")
        else:
            unmatched.append((vtt_path.name, out_name, vtt_date, body_hint, reason))
            print(f"  {reason.upper()}: {vtt_path.name} → {out_name} ({len(cues)} cues)")

    print(f"\nConverted: {converted}, Skipped: {skipped}, Matched: {matched}, Unmatched: {len(unmatched)}")


if __name__ == "__main__":
    main()
