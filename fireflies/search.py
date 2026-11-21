"""Cross-meeting search over every local source text.

Whitespace-flexible phrase matching (words may wrap across caption lines),
word-boundary aware. Hits carry source kind, locator (timestamp for ASR,
paragraph for minutes, char offset otherwise) and a verbatim snippet with the
match offsets marked — the snippet is always copy-of-source text.
"""
from __future__ import annotations

import re

from .textutil import clip_quote, normalize_ws


def _phrase_rx(query: str) -> re.Pattern:
    words = [w for w in re.split(r"\s+", query.strip()) if w]
    if not words:
        return re.compile(r"(?!x)x")
    body = r"\s+".join(re.escape(w) for w in words)
    return re.compile(r"(?<![A-Za-z0-9])" + body + r"(?![A-Za-z0-9])", re.I)


def _locate(st, idx: int) -> dict:
    loc = {"kind": st.kind, "ref": st.ref, "char": idx}
    if st.kind == "asr" and st.segments:
        ts = ""
        for s in st.segments:
            if s["start"] <= idx:
                ts = f"{s['t']//3600:02d}:{(s['t']%3600)//60:02d}:{s['t']%60:02d}"
            else:
                break
        loc["ts"] = ts
    elif st.kind == "minutes":
        loc["para"] = st.text[:idx].count("\n\n") + 1
    return loc


def search(query: str, meetings: list, *, body: str = None, year: str = None,
           kinds: tuple = ("minutes", "asr", "md", "agenda_html"),
           max_hits: int = 25, window: int = 110) -> list:
    """Return [{meeting_id, date, body, title, locator, snippet, start, end}].
    ``snippet`` is verbatim source text; start/end index the match inside it."""
    rx = _phrase_rx(query)
    hits = []
    for mt in meetings:
        if body and mt.body != body:
            continue
        if year and not (mt.date or "").startswith(year):
            continue
        for st in mt.texts:
            if st.kind not in kinds:
                continue
            for m in rx.finditer(st.text):
                lo = max(0, m.start() - window)
                hi = min(len(st.text), m.end() + window)
                raw = st.text[lo:hi].replace("\n", " ")
                shift = 0
                if lo > 0:
                    raw = "…" + raw
                    shift = 1
                if hi < len(st.text):
                    raw = raw + "…"
                hits.append({
                    "meeting_id": mt.meeting_id,
                    "date": mt.date,
                    "body": mt.body,
                    "title": mt.title,
                    "locator": _locate(st, m.start()),
                    "snippet": normalize_ws(raw),
                    "match_start": m.start() - lo + shift,
                    "match_end": m.end() - lo + shift,
                })
                if len(hits) >= max_hits * 4:
                    break
    hits.sort(key=lambda h: (h["date"] or "", h["body"]), reverse=True)
    return hits[:max_hits]
