"""Cross-meeting topic / entity tracking.

Entities (ordinance numbers, resolution numbers, statute cites) are followed
across every meeting in the ledger: when an ordinance was first mentioned,
every meeting it surfaced in, and a verbatim example quote per meeting. The
same walk powers ``python3 -m fireflies topics <term>`` for free-text terms.
"""
from __future__ import annotations

import re
from collections import defaultdict


def build_topics(meetings: list) -> dict:
    """meetings: ledger meeting dicts (already analyzed). -> topics.json payload."""
    topics = defaultdict(lambda: {"type": "", "value": "", "meetings": [], "mentions": 0})
    for mt in meetings:
        for ent in mt.get("entities", []):
            if ent["type"] not in ("ordinance", "resolution", "statute"):
                continue
            key = f"{ent['type']}:{ent['value']}"
            t = topics[key]
            t["type"], t["value"] = ent["type"], ent["value"]
            t["mentions"] += ent.get("count", 0)
            t["meetings"].append({
                "meeting_id": mt["meeting_id"],
                "date": mt["date"],
                "body": mt["body"],
                "count": ent.get("count", 0),
                "example": ent.get("example"),
            })
    out = {"entities": [], "generated_by": "fireflies.topics"}
    for key in sorted(topics, key=lambda k: (-topics[k]["mentions"], k)):
        t = dict(topics[key])
        t["key"] = key
        t["meetings"].sort(key=lambda m: m["date"])
        t["first_seen"] = t["meetings"][0]["date"] if t["meetings"] else ""
        t["last_seen"] = t["meetings"][-1]["date"] if t["meetings"] else ""
        out["entities"].append(t)
    return out


def term_timeline(term: str, meetings: list, corpus_texts) -> list:
    """Timeline of a free-text term across the corpus.

    corpus_texts: callable meeting_dict -> iterable of (SourceText-like) to scan.
    Returns one row per (meeting, source) hit: date, body, meeting_id, count,
    first verbatim example quote + locator.
    """
    rx = re.compile(re.escape(term), re.I)
    rows = []
    for mt in meetings:
        total = 0
        example = None
        for st in corpus_texts(mt):
            for m in rx.finditer(st.text):
                total += 1
                if example is None:
                    lo = max(0, m.start() - 70)
                    hi = min(len(st.text), m.end() + 70)
                    from .textutil import clip_quote
                    loc = {"kind": st.kind, "ref": st.ref, "char": m.start()}
                    if st.kind == "asr" and st.segments:
                        ts = ""
                        for s in st.segments:
                            if s["start"] <= m.start():
                                ts = f"{s['t']//3600:02d}:{(s['t']%3600)//60:02d}:{s['t']%60:02d}"
                            else:
                                break
                        loc["ts"] = ts
                    example = {"quote": clip_quote(st.text[lo:hi], 240), "locator": loc}
        if total:
            rows.append({
                "meeting_id": mt.meeting_id, "date": mt.date,
                "body": mt.body, "count": total, "example": example,
            })
    rows.sort(key=lambda r: r["date"])
    return rows
