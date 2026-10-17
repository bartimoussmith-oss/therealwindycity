#!/usr/bin/env python3
"""ai_record_drive.py - load the WindyCityMeetings caption-transcript database
(Google Drive: WindyCityMeetings/processed_database/master_meetings_database.json,
committed as drive-import/master_meetings_database.json.gz) and normalize it
for build_ai_record.py.

Each source record looks like:
  {"id": "meet_0704", "title": "Finance Committee 02-04-25",
   "filename": "Finance_Committee_02-04-25.md", "date": "2025-02-04" | "Unknown",
   "category": "Finance Committee", "turns": [{"speaker": "...", "text": "# Title ..."}],
   "raw_text_length": 7415}

What normalization does (nothing is reworded):
  * text = the turns joined back together.
  * A few records were split at "5:30"-style times, with the left half stored as a
    fake "speaker". Those are re-joined as "speaker:text".
  * The leading "# Title" line is removed.
  * The date is taken from the record. If it is "Unknown" or before 2008, the date
    is read from the title, e.g. "January 5, 2026, ...", "Sept. 8, 2025", "02-04-25".
    "date_source" records which of these happened.
  * The body (city-council, finance-committee, ...) comes from the category, or from
    the title when the category is "Other/Supporting".
  * Records with identical text are marked as duplicates.
"""
import gzip, hashlib, json, re
from datetime import date

CATEGORY_BODY = {
    "City Council": "city-council",
    "Finance Committee": "finance-committee",
    "Work Session": "work-sessions",
    "Public Services Committee": "public-services-committee",
    "Planning Commission": "planning-commission",
}
TITLE_BODY = [  # checked in order, case-insensitive
    (r"board of adjustment", "board-of-adjustment"),
    (r"historic preservation", "historic-preservation-board"),
    (r"urban renewal", "urban-renewal-authority"),
    (r"planning commission", "planning-commission"),
    (r"finance committee", "finance-committee"),
    (r"public services committee", "public-services-committee"),
    (r"commit+e+ of the whole|committe of the whole|work ?session|wok session|\bws\b|goal setting|zoning workshop", "work-sessions"),
    (r"city council", "city-council"),
]
MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def _valid(y, m, d):
    try:
        dt = date(y, m, d)
    except ValueError:
        return None
    return dt.isoformat() if 2008 <= y <= 2027 else None


def date_from_title(t):
    s = t.replace("_", " ")
    for mm in re.finditer(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})\b", s, re.I):
        r = _valid(int(mm.group(3)), MONTHS[mm.group(1).lower()[:3]], int(mm.group(2)))
        if r: return r
    # overlapping search so "Round 2 02-04-25" still finds 02-04-25
    for mm in re.finditer(r"(?<!\d)(?=(\d{1,2})[-/. ](\d{1,2})[-/. ](\d{4}|\d{2})(?!\d))", s):
        y = int(mm.group(3)); y = y + 2000 if y < 100 else y
        r = _valid(y, int(mm.group(1)), int(mm.group(2)))
        if r: return r
    return None


def body_for(category, title):
    for rx, b in TITLE_BODY:
        if re.search(rx, title, re.I):
            # a title naming a specific board wins over a generic category
            if category in CATEGORY_BODY and b in ("city-council", "work-sessions"):
                return CATEGORY_BODY[category]
            return b
    return CATEGORY_BODY.get(category)


def record_text(r):
    turns = r.get("turns") or []
    text = ""
    for i, t in enumerate(turns):
        sp, tx = (t.get("speaker") or "").strip(), (t.get("text") or "")
        if i == 0 or sp in ("", "Context/Agenda"):
            text = (text + " " + tx) if text else tx
        else:
            text = text.rstrip() + " " + sp + ":" + tx      # undo a split at "5:30"-style times
    title = (r.get("title") or "").strip()
    fn = re.sub(r"\.md$", "", r.get("filename") or "").replace("_", " ")
    cands = {title, re.sub(r"\s+\d+$", "", title), fn, re.sub(r"\s+\d+$", "", fn)}
    t0 = text.lstrip()
    if t0.startswith("#"):
        for c in sorted((c for c in cands if c), key=len, reverse=True):
            mm = re.match(r"#+\s*" + re.escape(c) + r"\s*", t0)
            if mm:
                return t0[mm.end():].strip()
        nl = t0.find("\n")
        if 0 < nl < 200:
            return t0[nl + 1:].strip()
        return t0.lstrip("#").strip()          # unknown header: keep its words, drop the "#"
    return text.strip()


def paragraphs(text, words_per=120):
    """Captions have no punctuation. Wrap them into readable ~120-word paragraphs,
    breaking at the next pause word near the target length when possible."""
    w = text.split()
    out, cur = [], []
    for tok in w:
        cur.append(tok)
        if len(cur) >= words_per and tok.lower() in ("okay", "thank", "thanks", "so", "and", "all", "um", "uh", "right"):
            out.append(" ".join(cur)); cur = []
        elif len(cur) >= words_per * 1.6:
            out.append(" ".join(cur)); cur = []
    if cur: out.append(" ".join(cur))
    return out


def md_safe(p):
    p = p.replace("<", "&lt;").replace("*", "\\*").replace("_", "\\_").replace("`", "\\`")
    p = re.sub(r"^([#>+\-|])", r"\\\1", p)
    p = re.sub(r"^(\d+)\. ", r"\1\\. ", p)
    return p


def load(path):
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8") as f:
        raw = json.load(f)
    recs = raw if isinstance(raw, list) else next(v for v in raw.values() if isinstance(v, list))
    out, seen = [], {}
    for r in recs:
        title = (r.get("title") or r.get("filename") or r.get("id")).strip()
        d0 = r.get("date") or "Unknown"
        dt, src = None, None
        ok = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", d0)
        if ok and _valid(*map(int, ok.groups())):
            dt, src = d0, "database"
        else:
            t = date_from_title(title)
            if t: dt, src = t, "title"
        text = record_text(r)
        h = hashlib.sha1(" ".join(text.split()).lower().encode()).hexdigest()
        rec = {"id": r.get("id"), "title": title, "filename": r.get("filename"), "category": r.get("category"),
               "date": dt, "date_source": src, "db_date": d0, "body": body_for(r.get("category") or "", title),
               "text": text, "words": len(text.split()), "hash": h, "dup_of": seen.get(h)}
        seen.setdefault(h, rec["id"])
        out.append(rec)
    return out


if __name__ == "__main__":
    import sys, collections
    rs = load(sys.argv[1])
    print(len(rs), "records;", sum(1 for r in rs if r["dup_of"]), "duplicates;",
          collections.Counter(r["date_source"] for r in rs), collections.Counter(r["body"] for r in rs))
