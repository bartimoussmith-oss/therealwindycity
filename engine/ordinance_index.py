#!/usr/bin/env python3
"""Build pipeline/ordinance_history.json from the transcript record.

Scans uploads/ (Granicus-derived meeting transcripts), pipeline/corpus/
(the 17-year minutes archive) and pipeline/corpus/extra/ (full-tape
transcripts) for ordinance references, and groups them into a per-ordinance
timeline: every mention with its date, body, and reading stage where the
clerk read it aloud.

Deterministic stdlib only — no model, no guessing. Two mention kinds:
  * numbered   "Ordinance No. 4571"          -> keyed by number
  * by title   "ordinance third reading amending section 13.20.050 ..."
                                            -> keyed by the first 60
                                              normalized characters of the
                                              title the clerk read (the same
                                              title is read verbatim at each
                                              reading, which is what links
                                              the meetings together)

Run from the repo root:  python3 engine/ordinance_index.py
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "pipeline" / "ordinance_history.json"

NUM_RE = re.compile(r"(?i)\bordinance\s+no\.?\s*(\d{3,4})")
READ_RE = re.compile(r"(?i)\bordinance\s+((?:first|second|third)(?:\s+and\s+final)?)"
                     r"\s+reading[, ]+((?:amending|annexing|repealing|repealing and "
                     r"replacing|creating|establishing|vacating|changing|approving|"
                     r"adopting|authorizing|rezoning|amending and reenacting)?[^\n]{0,180})")
DATE_PATTERNS = [
    (re.compile(r"(\d{2})-(\d{2})-(\d{2})\.md$"), "%y"),   # 06-01-26
    (re.compile(r"(\d{2})-(\d{2})-(\d{4})\.md$"), "%Y"),   # 06-01-2026
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})\.md$"), "iso"),  # 2026-06-01
]
BODY_KEYWORDS = [
    ("Public Services Committee", "public services committee"),
    ("Finance Committee", "finance committee"),
    ("Planning Commission", "planning commission"),
    ("Board of Adjustment", "board of adjustment"),
    ("Urban Renewal Authority", "urban renewal"),
    ("Public Hearing", "public hearing"),
    ("Governing Body", "governing body"),
    ("Work Session", "work session"),
]
EXTRA_MEETINGS = {  # full-tape transcripts, hand-verified dates
    "mar9.txt": ("2026-03-09", "Governing Body"),
    "apr27.txt": ("2026-04-27", "Governing Body"),
    "jun22.txt": ("2026-06-22", "Governing Body"),
}


def _slug(text: str) -> str:
    norm = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    return "-".join(norm.split())[:110]


def _uploads_mentions():
    for fp in sorted((ROOT / "uploads").glob("*.md")):
        name = fp.name
        date = None
        for pat, style in DATE_PATTERNS:
            m = pat.search(name)
            if m:
                a, b, c = m.groups()
                date = (f"{c}-{a}-{b}" if style == "iso"
                        else f"20{c}-{a}-{b}" if len(c) == 2
                        else f"{c}-{a}-{b}")
                break
        body = next((label for label, kw in BODY_KEYWORDS
                     if kw in name.lower()), "Committee / meeting")
        try:
            text = fp.read_text(errors="replace")
        except OSError:
            continue
        yield date, body, f"uploads/{name}", text


def _corpus_mentions():
    for fp in sorted((ROOT / "pipeline" / "corpus").glob("*.txt")):
        head = fp.read_text(errors="replace")[:400]
        md = re.search(r"MEETING:\s*([^|]+)\|\s*DATE:\s*(\d{4}-\d{2}-\d{2})", head)
        if not md:
            continue
        body, date = md.group(1).strip(), md.group(2)
        yield date, body, f"pipeline/corpus/{fp.name}", fp.read_text(errors="replace")
    for fname, (date, body) in EXTRA_MEETINGS.items():
        fp = ROOT / "pipeline" / "corpus" / "extra" / fname
        if fp.exists():
            yield (date, body, f"pipeline/corpus/extra/{fname}",
                   fp.read_text(errors="replace"))


def _collect():
    ordinances: dict = {}

    def touch(key):
        return ordinances.setdefault(key, {"key": key, "mentions": []})

    for date, body, rel, text in list(_uploads_mentions()) + list(_corpus_mentions()):
        if not date:
            continue
        for m in NUM_RE.finditer(text):
            ctx = " ".join(text[max(0, m.start() - 70):m.end() + 130].split())
            entry = touch("no-" + m.group(1))
            entry["number"] = m.group(1)
            entry["mentions"].append(
                {"date": date, "body": body, "file": rel, "stage": "numbered",
                 "context": ctx[:220]})
        for m in READ_RE.finditer(text):
            stage = m.group(1).lower()
            title = " ".join(m.group(2).split())[:180]
            if len(title) < 15:
                continue
            entry = touch("title-" + _slug(title))
            entry.setdefault("title", title)
            entry["mentions"].append(
                {"date": date, "body": body, "file": rel, "stage": stage,
                 "context": title})
    for entry in ordinances.values():
        entry["mentions"].sort(key=lambda x: x["date"])
    return ordinances


def main() -> None:
    ordinances = _collect()
    ranked = dict(sorted(ordinances.items(),
                         key=lambda kv: (-len(kv[1]["mentions"]), kv[0])))
    OUT.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "engine/ordinance_index.py — deterministic grep of the "
                     "transcript record; no model, no inference",
        "note": "Numbered ordinances are keyed by number. Title-keyed "
                "entries rely on the clerk reading the same title verbatim "
                "at each reading — that repetition is what links meetings. "
                "Mentions carry the file they came from; verify anything "
                "load-bearing against the source.",
        "stats": {"ordinances": len(ranked),
                  "mentions": sum(len(e["mentions"]) for e in ranked.values())},
        "ordinances": ranked,
    }, indent=1))
    print(f"ordinance_history.json: {len(ranked)} ordinances, "
          f"{sum(len(e['mentions']) for e in ranked.values())} mentions -> {OUT}")


if __name__ == "__main__":
    main()
