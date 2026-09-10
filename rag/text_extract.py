#!/usr/bin/env python3
"""text_extract.py — shared text extraction (stdlib + pypdf/pdfplumber).

Handles the repo's real-world quirks:
  * pipeline/docs/** stores PDF bytes under .html extensions (sniff magic, not ext)
  * corpus minutes carry a MEETING/DATE/CLIP_ID header line
  * extra/*.txt transcripts are rolling-caption windows (heavy duplication)
"""
from __future__ import annotations

import hashlib
import html as _html
import json
import re
from pathlib import Path

MINUTES_HDR = re.compile(
    r"MEETING:\s*(?P<meeting>.*?)\s*\|\s*DATE:\s*(?P<date>\d{4}-\d{2}-\d{2})"
    r"\s*\|\s*CLIP_ID:\s*(?P<clip>\d+)"
)
TS_LINE = re.compile(r"^(?P<ts>\d{1,2}:\d{2}(?::\d{2})?)\s+(?P<text>.*)$")
ROLLCALL = re.compile(
    r"Present were:\s*(?P<present>.*?)(?:Absent:\s*(?P<absent>.*?))?(?:Also present:\s*(?P<also>.*?))?\.\s+(?:The pledge|Consent Agenda|CALL)",
    re.S | re.I,
)
ORDINANCE = re.compile(r"Ordinance\s*(?:No\.\s*)?(?P<num>\d{3,5}[A-Z]?)", re.I)
RESOLUTION = re.compile(r"Resolution\s*(?:No\.\s*)?(?P<num>\d{3,5}[A-Z]?)", re.I)


def is_pdf(path: Path) -> bool:
    with open(path, "rb") as f:
        return f.read(4) == b"%PDF"


def pdf_to_text(path: Path) -> dict:
    """Return {'pages': [str...], 'full_text': str}. Prefers pdfplumber."""
    pages: list[str] = []
    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(path) as pdf:
            pages = [(p.extract_text() or "") for p in pdf.pages]
    except Exception:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = [(p.extract_text() or "") for p in reader.pages]
    return {"pages": pages, "full_text": "\n".join(pages)}


def file_to_text(path: Path) -> str:
    """Best-effort text for any doc file (PDF bytes, HTML, or plain text)."""
    raw = path.read_bytes()
    if raw[:4] == b"%PDF":
        return pdf_to_text(path)["full_text"]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("iso-8859-1", errors="replace")
    if "<html" in text[:2000].lower() or "<table" in text[:2000].lower():
        text = re.sub(r"<script.*?</script>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = _html.unescape(text)
    return re.sub(r"[ \t\xa0]+", " ", text)


def agenda_items(agenda_html: str) -> list[dict]:
    """Parse Granicus agenda HTML into [{no, title}] (best effort)."""
    items = []
    for m in re.finditer(
        r"<td width=40>\s*([^<]*?)</td>\s*<td>(.*?)</td>", agenda_html, re.S | re.I
    ):
        no = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))).strip().rstrip(".")
        title_full = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", m.group(2)))).strip()
        title = re.split(r"\bACTION\s*:", title_full, maxsplit=1)[0].strip(" ;\t")
        if no or title:
            items.append({"no": no, "title": title[:300]})
    return items


def parse_minutes_header(text: str) -> dict:
    m = MINUTES_HDR.search(text[:600])
    if not m:
        return {}
    return {"meeting": m.group("meeting").strip(), "date": m.group("date"),
            "clip_id": m.group("clip")}


def ts_to_seconds(ts: str) -> int:
    parts = [int(p) for p in ts.split(":")]
    while len(parts) < 3:
        parts = [0] + parts
    h, m, s = parts[-3:]
    return h * 3600 + m * 60 + s


def seconds_to_ts(sec: int) -> str:
    return f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"


def parse_rolling_transcript(path: Path, max_overlap: int = 60) -> dict:
    """Dedup rolling-caption transcript -> {words, times, raw_lines, segments}.

    words: reconstructed word list; times[i]: first-seen timestamp (sec) of words[i].
    segments: sentence-grouped [{t_start, t_end, text}].
    """
    lines = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        m = TS_LINE.match(raw)
        if m:
            lines.append((ts_to_seconds(m.group("ts")), _html.unescape(m.group("text"))))
        elif lines:  # continuation of previous caption line
            prev_t, prev_text = lines[-1]
            lines[-1] = (prev_t, prev_text + " " + _html.unescape(raw))

    words: list[str] = []
    times: list[int] = []
    for t, text in lines:
        toks = text.split()
        if not toks:
            continue
        # longest overlap: tail of committed == head of new line
        best = 0
        limit = min(len(words), len(toks), max_overlap)
        for k in range(limit, 0, -1):
            if words[-k:] == toks[:k]:
                best = k
                break
        for w in toks[best:]:
            words.append(w)
            times.append(t)

    # sentence segmentation, then group to ~60s / ~600-char segments
    sentences, cur, cur_t0 = [], [], None
    for w, t in zip(words, times):
        if cur_t0 is None:
            cur_t0 = t
        cur.append((w, t))
        if re.search(r"[.?!]['\")\]]?$", w):
            sentences.append((cur_t0, t, " ".join(x[0] for x in cur)))
            cur, cur_t0 = [], None
    if cur:
        sentences.append((cur_t0, cur[-1][1], " ".join(x[0] for x in cur)))

    segments = []
    buf: list[tuple[int, int, str]] = []
    for s in sentences:
        buf.append(s)
        span = s[1] - buf[0][0]
        chars = sum(len(x[2]) for x in buf)
        if span >= 45 or chars >= 700:
            segments.append({"t_start": buf[0][0], "t_end": buf[-1][1],
                             "text": " ".join(x[2] for x in buf)})
            buf = []
    if buf:
        segments.append({"t_start": buf[0][0], "t_end": buf[-1][1],
                         "text": " ".join(x[2] for x in buf)})
    return {"words": words, "times": times, "raw_lines": len(lines),
            "segments": segments}


def norm_token(tok: str) -> str:
    t = tok.lower()
    t = re.sub(r"'s$", "", t)  # possessives normalize to the base form
    return re.sub(r"[^a-z0-9]", "", t)


def _cache_key(path: Path) -> str:
    st = path.stat()
    h = hashlib.sha1(
        f"{path.resolve()}|{st.st_size}|{st.st_mtime}".encode()).hexdigest()
    return f"{h[:16]}_{path.parent.name}_{path.name}"[:120]


def cached_text(path: Path, cache_dir: Path) -> str:
    """file_to_text with a persistent cache (keyed by path+size+mtime)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    fp = cache_dir / (_cache_key(path) + ".txt")
    if fp.exists():
        return fp.read_text(encoding="utf-8", errors="replace")
    text = file_to_text(path)
    fp.write_text(text, encoding="utf-8")
    return text


def cached_pdf_pages(path: Path, cache_dir: Path) -> list[str]:
    """pdf_to_text pages with a persistent cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    fp = cache_dir / (_cache_key(path) + ".pages.json")
    if fp.exists():
        return json.loads(fp.read_text(encoding="utf-8"))
    pages = pdf_to_text(path)["pages"]
    fp.write_text(json.dumps(pages), encoding="utf-8")
    return pages
