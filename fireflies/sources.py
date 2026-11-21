"""Read-only enumeration and parsing of every local meeting text corpus.

Sources (nothing here ever writes to them):
  * pipeline/corpus/<clip_id>_<date>.txt          Granicus minutes text (2008-2026)
  * pipeline/corpus_yt/<date>-<body>.txt          timestamped YouTube ASR captions (2026)
  * drive-import/master_meetings_database_linked.json.gz   markdown transcripts (2004-2026)
  * uploads/*.md                                  markdown transcripts (master-db source files)
  * pipeline/meetings.json                        clip_id -> agenda/minutes/mp4 URLs
  * pipeline/docs/<clip_id>/                      agenda/minutes/packet HTML (local sample)

Canonical meetings are keyed by (date, body-slug); texts from different sources
about the same meeting are kept side by side (kind-tagged) rather than merged,
because minutes and captions are different evidence.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ASR_TS = re.compile(r"^\[(\d{1,2}):(\d{2}):(\d{2})\]\s*(.*)$")
HEADER = re.compile(
    r"^MEETING:\s*(?P<meeting>[^|]*?)\s*\|\s*DATE:\s*(?P<date>[^|]*?)\s*"
    r"(?:\|\s*CLIP_ID:\s*(?P<clip>[^|]*?)\s*)?(?:\|\s*SOURCE:\s*(?P<source>.*))?$"
)

BODY_MAP = {
    "city council": "city-council",
    "city council meeting": "city-council",
    "cheyenne city council": "city-council",
    "governing body": "city-council",
    "first regular meeting of the governing body": "city-council",
    "first regular meeting": "city-council",
    "special meeting of the governing body": "city-council",
    "special city council meeting": "city-council",
    "special city council": "city-council",
    "sine die": "city-council",
    "sine die meeting": "city-council",
    "budget hearing special session of the governing body": "city-council",
    "finance committee": "finance-committee",
    "public services committee": "public-services-committee",
    "planning commission": "planning-commission",
    "historic preservation board": "historic-preservation-board",
    "board of adjustment": "board-of-adjustment",
    "committee of the whole": "committee-of-the-whole",
    "work session": "work-session",
    "goal setting": "goal-setting",
    "urban renewal authority": "urban-renewal-authority",
    "public hearing": "public-hearing",
    "other supporting": "other-supporting",
    "other": "other-supporting",
}

_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}


@dataclass
class SourceText:
    kind: str                 # minutes | asr | md | agenda_html | minutes_html
    ref: str                  # repo-relative path or record id
    text: str
    sha256: str = ""
    words: int = 0
    segments: list = None     # ASR only: [{'t': seconds, 'start': char, 'end': char, 'text': str}]

    def __post_init__(self):
        self.sha256 = hashlib.sha256(self.text.encode("utf-8", "replace")).hexdigest()
        self.words = len(self.text.split())
        if self.segments is None:
            self.segments = []

    @property
    def norm_hash(self) -> str:
        """Whitespace/case-insensitive hash for cross-source dedupe."""
        norm = re.sub(r"\s+", " ", self.text).strip().lower()
        return hashlib.sha256(norm.encode("utf-8", "replace")).hexdigest()


@dataclass
class Meeting:
    meeting_id: str
    date: str                 # ISO date or '' when undated
    body: str                 # body slug
    body_label: str = ""
    title: str = ""
    clip_ids: list = field(default_factory=list)
    urls: dict = field(default_factory=dict)     # agenda/minutes/mp4/youtube
    texts: list = field(default_factory=list)    # SourceText
    docs: list = field(default_factory=list)     # supporting docs: {kind,title,ref,url}
    flags: list = field(default_factory=list)


# ---------------------------------------------------------------- helpers

def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "unknown"


def _body_key(label: str) -> str:
    key = re.sub(r"[^a-z0-9]+", " ", (label or "").lower())
    key = re.sub(r"\b(agenda only|no video available)\b", "", key)
    key = re.sub(r"\s+", " ", key).strip()
    key = key.removeprefix("cheyenne ").strip()
    return key


def map_body(label: str):
    """Known-body slug for a label/title, or None when no mapping exists."""
    key = _body_key(label)
    for cand in (key, key.removesuffix(" meeting").strip(),
                 key + " meeting"):
        if cand in BODY_MAP:
            return BODY_MAP[cand]
    for k, v in sorted(BODY_MAP.items(), key=lambda kv: -len(kv[0])):
        if key.startswith(k):
            return v
    return None


def body_slug(label: str) -> str:
    mapped = map_body(label)
    if mapped:
        return mapped
    key = _body_key(label)
    return slugify(" ".join(key.split()[:3])) or "unknown"


def ts_to_seconds(h: str, m: str, s: str) -> int:
    return int(h) * 3600 + int(m) * 60 + int(s)


def fmt_ts(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse_asr_segments(text: str) -> list:
    """Split timestamped caption text into [{'t','start','end','text'}] segments."""
    segments = []
    cur = None
    pos = 0
    for line in text.splitlines(keepends=True):
        m = ASR_TS.match(line)
        if m:
            if cur:
                cur["end"] = pos
                segments.append(cur)
            body = m.group(4).strip()
            cur = {
                "t": ts_to_seconds(*m.groups()[:3]),
                "start": pos + line.find(m.group(4)) if body else pos,
                "end": 0,
                "text": body,
            }
        elif cur is not None:
            frag = line.strip()
            if frag:
                cur["text"] += (" " if cur["text"] else "") + frag
        pos += len(line)
    if cur:
        cur["end"] = pos
        segments.append(cur)
    return segments


def guess_date_from_filename(name: str) -> str:
    """Best-effort ISO date from titles/filenames like '..._01-06-25.md' or 'May_18,_2026,...'."""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"([A-Z][a-z]+)_(\d{1,2}),_(\d{4})", name)
    if m and m.group(1).lower() in _MONTHS:
        return f"{m.group(3)}-{_MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    m = re.search(r"(\d{2})-(\d{2})-(\d{2})(?:\.md)?$", name)
    if m:
        return f"20{m.group(3)}-{m.group(1)}-{m.group(2)}"
    m = re.search(r"(\d{1,2})-(\d{1,2})-(\d{2})(?:\.md)?$", name)
    if m:
        return f"20{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    m = re.search(r"(\d{2})\s(\d{2})\s(\d{2})", name)
    if m:
        return f"20{m.group(3)}-{m.group(1)}-{m.group(2)}"
    return ""


def meeting_id_for(date: str, body: str, fallback: str = "") -> str:
    if date:
        return f"{date}-{body}"
    return f"undated-{body}-{fallback}" if fallback else f"undated-{body}"


# ---------------------------------------------------------------- loaders

def load_minutes_corpus(repo: Path) -> list:
    """pipeline/corpus/<clip_id>_<date>.txt -> raw meeting dicts."""
    out = []
    corpus = repo / "pipeline" / "corpus"
    for fp in sorted(corpus.iterdir()):
        if fp.suffix != ".txt" or not fp.stat().st_size:
            continue
        text = fp.read_text(encoding="utf-8", errors="replace")
        m = HEADER.match(text.splitlines()[0]) if text else None
        date = clip = label = ""
        if m:
            date = (m.group("date") or "").strip()
            clip = (m.group("clip") or "").strip()
            label = (m.group("meeting") or "").strip()
        if not date:
            date = guess_date_from_filename(fp.name)
        if not label:
            label = "City Council Meeting" if clip else "Meeting"
        out.append({
            "date": date, "body": body_slug(label), "body_label": label,
            "title": f"{label} {date}".strip(),
            "clip_ids": [clip] if clip.isdigit() else [],
            "kind": "minutes", "ref": f"pipeline/corpus/{fp.name}", "text": text,
        })
    return out


def load_asr_corpus(repo: Path) -> list:
    """pipeline/corpus_yt/<date>-<body>.txt -> raw meeting dicts with segments."""
    out = []
    corpus = repo / "pipeline" / "corpus_yt"
    for fp in sorted(corpus.glob("*.txt")):
        if not fp.stat().st_size:
            continue
        text = fp.read_text(encoding="utf-8", errors="replace")
        first = text.splitlines()[0] if text else ""
        m = HEADER.match(first)
        date = (m.group("date") or "").strip() if m else ""
        label = (m.group("meeting") or "").strip() if m else ""
        stem = fp.stem
        if not date and re.match(r"\d{4}-\d{2}-\d{2}", stem):
            date = stem[:10]
        body = body_slug(label) if label and label not in ("",) else slugify(re.sub(r"^\d{4}-\d{2}-\d{2}-?", "", stem))
        yt = ""
        for line in text.splitlines()[:5]:
            mm = re.search(r"YT_ID:\s*(\S+)", line)
            if mm:
                yt = mm.group(1)
                break
        urls = {"youtube": f"https://www.youtube.com/watch?v={yt}"} if yt else {}
        out.append({
            "date": date, "body": body, "body_label": label.replace("-", " ").title() or body.replace("-", " ").title(),
            "title": f"{label or body} {date}".strip(),
            "clip_ids": [], "urls": urls,
            "kind": "asr", "ref": f"pipeline/corpus_yt/{fp.name}", "text": text,
        })
    return out


def load_master_db(repo: Path) -> list:
    """drive-import master DB -> raw meeting dicts (markdown transcripts)."""
    out = []
    gp = repo / "drive-import" / "master_meetings_database_linked.json.gz"
    if not gp.exists():
        return out
    with gzip.open(gp, "rt", encoding="utf-8") as fh:
        records = json.load(fh)
    for rec in records:
        parts = [(t.get("text") or "") for t in rec.get("turns", [])]
        text = "\n".join(p for p in parts if p.strip())
        if not text.strip():
            continue
        title = (rec.get("title") or "").strip()
        label = (rec.get("category") or "Meeting").strip()
        flags = []
        date_field = (rec.get("date") or "").strip()
        guess = (guess_date_from_filename(rec.get("filename") or "")
                 or guess_date_from_filename(title))
        if not date_field or date_field.lower() == "unknown":
            date = guess or ""
            if guess:
                flags.append(f"date-source:filename")
        elif guess and guess != date_field:
            # the record's date column disagrees with the filename/title date;
            # the filename is the closer artifact — keep BOTH values on record
            date = guess
            flags.append(f"date-conflict:record-field={date_field};used={guess}")
        else:
            date = date_field
        body = map_body(title) or map_body(label) or body_slug(label)
        out.append({
            "date": date, "body": body,
            "body_label": (title or label).strip(),
            "title": title or label, "clip_ids": [], "flags": flags,
            "kind": "md", "ref": f"drive-import/master_db:{rec.get('id', '')}", "text": text,
        })
    return out


def load_uploads(repo: Path) -> list:
    """uploads/*.md -> raw meeting dicts (markdown transcripts)."""
    out = []
    updir = repo / "uploads"
    if not updir.exists():
        return out
    for fp in sorted(updir.glob("*.md")):
        if not fp.stat().st_size:
            continue
        text = fp.read_text(encoding="utf-8", errors="replace")
        first = ""
        for line in text.splitlines():
            if line.strip():
                first = line.strip().lstrip("# ").strip()
                break
        date = guess_date_from_filename(fp.name)
        label = first or fp.stem.replace("_", " ")
        out.append({
            "date": date, "body": body_slug(label), "body_label": label,
            "title": label, "clip_ids": [],
            "kind": "md", "ref": f"uploads/{fp.name}", "text": text,
        })
    return out


def load_meetings_index(repo: Path) -> dict:
    """pipeline/meetings.json -> clip_id -> urls/name/date."""
    fp = repo / "pipeline" / "meetings.json"
    if not fp.exists():
        return {}
    data = json.loads(fp.read_text(encoding="utf-8"))
    return {str(k): v for k, v in data.get("meetings", {}).items()}


def load_local_docs(repo: Path) -> dict:
    """pipeline/docs/<clip_id>/ -> per-clip local agenda/minutes/packet files."""
    out = {}
    docs = repo / "pipeline" / "docs"
    if not docs.exists():
        return out
    for d in sorted(docs.iterdir()):
        if not d.is_dir():
            continue
        entries = []
        for fp in sorted(d.iterdir()):
            if fp.suffix not in (".html", ".vtt", ".txt"):
                continue
            name = fp.name.lower()
            kind = ("agenda_html" if "agenda" in name else
                    "minutes_html" if "minutes" in name else
                    "packet" if "meta" in name else "other")
            entries.append({"kind": kind, "title": fp.name,
                            "ref": f"pipeline/docs/{d.name}/{fp.name}"})
        if entries:
            out[d.name] = entries
    return out


# ---------------------------------------------------------------- assembly

def load_meetings(repo: Path) -> list:
    """Build the canonical merged meeting list from every local source."""
    repo = Path(repo)
    index = load_meetings_index(repo)
    local_docs = load_local_docs(repo)

    raw = []
    raw += load_minutes_corpus(repo)
    raw += load_asr_corpus(repo)
    raw += load_master_db(repo)
    raw += load_uploads(repo)

    merged: dict = {}
    seen_text: dict = {}

    def bucket(rec):
        date, body = rec["date"], rec["body"]
        mid = meeting_id_for(date, body, fallback=slugify(Path(rec["ref"]).name))
        return merged.setdefault(mid, {
            "meeting_id": mid, "date": date, "body": body,
            "body_label": rec.get("body_label") or body, "title": rec.get("title") or mid,
            "clip_ids": [], "urls": {}, "texts": [], "docs": [], "flags": [],
        })

    for rec in raw:
        st = SourceText(kind=rec["kind"], ref=rec["ref"], text=rec["text"])
        key = (rec["date"] or rec["title"], st.norm_hash)
        if key in seen_text:
            continue  # same text already attached (uploads vs master db)
        seen_text[key] = rec["ref"]
        mt = bucket(rec)
        mt["flags"].extend(rec.get("flags", []))
        if rec.get("body_label") and rec["body_label"] not in mt["body_label"]:
            mt["flags"].append(f"also-labeled:{rec['body_label']}")
        if rec.get("title") and len(rec["title"]) > len(mt["title"]):
            mt["title"] = rec["title"]
        if rec["kind"] == "asr":
            st.segments = parse_asr_segments(st.text)
            mt["urls"].update(rec.get("urls", {}))
        mt["texts"].append(st)
        for cid in rec.get("clip_ids", []):
            if cid not in mt["clip_ids"]:
                mt["clip_ids"].append(cid)

    # attach URLs from meetings.json + local docs via clip_id, and index-only meetings
    for clip, meta in index.items():
        date, name = meta.get("date") or "", meta.get("name") or "Meeting"
        body = body_slug(name)
        mid = meeting_id_for(date, body, fallback=f"clip{clip}")
        mt = merged.get(mid)
        if mt is None:
            mt = merged.setdefault(mid, {
                "meeting_id": mid, "date": date, "body": body, "body_label": name,
                "title": f"{name} {date}".strip(), "clip_ids": [clip], "urls": {},
                "texts": [], "docs": [], "flags": ["links-only:no-local-text"],
            })
        if clip not in mt["clip_ids"]:
            mt["clip_ids"].append(clip)
        for k_src, k_dst in (("agenda_url", "agenda"), ("minutes_url", "minutes"),
                             ("mp4_url", "mp4")):
            if meta.get(k_src):
                mt["urls"].setdefault(k_dst, meta[k_src])
        if "agenda only" in name.lower():
            mt["flags"].append("agenda-only")

    for clip, entries in local_docs.items():
        target = None
        for mt in merged.values():
            if clip in mt["clip_ids"]:
                target = mt
                break
        if target is None:
            continue
        for e in entries:
            if e["kind"] in ("agenda_html", "minutes_html", "packet"):
                target["docs"].append({
                    "kind": e["kind"], "title": e["title"], "ref": e["ref"], "url": "",
                })
                if e["kind"] == "agenda_html":
                    target["texts"].append(SourceText(
                        kind="agenda_html", ref=e["ref"],
                        text=(repo / e["ref"]).read_text(encoding="utf-8", errors="replace")))

    meetings = [Meeting(
        meeting_id=m["meeting_id"], date=m["date"], body=m["body"],
        body_label=m["body_label"], title=m["title"],
        clip_ids=m["clip_ids"], urls=m["urls"], texts=m["texts"],
        docs=m["docs"], flags=m["flags"],
    ) for m in sorted(merged.values(),
                     key=lambda m: (m["date"] or "9999", m["body"], m["meeting_id"]))]
    return meetings
