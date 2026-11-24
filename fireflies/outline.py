"""Outline / chapter building — agenda items -> transcript time spans.

Three alignment grades, each stored with a method tag and hit counts:
  * granicus-mediaplayer-link-v1 — agenda HTML items carry MediaPlayer deep
    links (the system of record's own per-item jump-to-moment).
  * anchor-alignment-v1 — timestamped ASR: item anchors (ordinance numbers,
    item numbers like 20D, reading phrases, title content words) are matched
    against caption segments; the contiguous hit run is the chapter. Confidence
    is reported (high/medium/low) from hit counts, never assumed.
  * minutes-paragraph-span-v1 — minutes prose: the item paragraph runs until
    the next item paragraph.

Ends are exclusive-ish: a chapter ends where the next chapter begins.
"""
from __future__ import annotations

import re

from .textutil import ocr_join, words

_STOP = set("""
the a an and or of to in for on with by is are was were be been that this it as at
from we you they he she city council not but then than there this that all any
which what when where also into over under after before about against between
""".split())


def _anchor_terms(item) -> tuple:
    """(strong anchors, weak terms) for one agenda item."""
    strong = []
    if item.number:
        strong.append(item.number)
    if item.item_no:
        strong.append(item.item_no.lower())
    m = re.search(r"(\d(?:st|nd|rd|th))\s*READING", item.title, re.I)
    if m:
        strong.append(m.group(1).lower() + " reading")
    m = re.findall(r"\b(ordinance|resolution)\s*(?:no\.?|number)?\s*(\d{3,5})\b",
                   item.title, re.I)
    for _, num in m:
        strong.append(num)
    weak = [w.lower() for w in words(item.title)
            if w.lower() not in _STOP and len(w) > 3]
    return strong, weak


def align_asr(item, segments: list, after_s: int = 0) -> dict:
    """Match one item against timestamped segments -> chapter span.
    ``after_s``: prefer hits at/after this second (agenda order is mostly
    chronological; a 60 s tolerance allows for out-of-order mentions)."""
    strong, weak = _anchor_terms(item)
    if not segments:
        return {}
    hits = []
    for i, seg in enumerate(segments):
        if seg["t"] < after_s - 60:
            continue
        text = ocr_join(seg["text"]).lower()
        score = 0
        matched = []
        for a in strong:
            if re.search(r"(?<![a-z0-9])" + re.escape(a.lower()) + r"(?![a-z0-9])", text):
                score += 3
                matched.append(a)
        weak_hits = [w for w in dict.fromkeys(weak)
                     if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", text)]
        score += len(weak_hits)
        matched += weak_hits[:6]
        if score >= 2:
            hits.append((i, score, matched))
    if not hits:
        return {}

    # group contiguous-ish runs (gap tolerance of 2 segments)
    runs = []
    run = [hits[0]]
    for h in hits[1:]:
        if h[0] - run[-1][0] <= 3:
            run.append(h)
        else:
            runs.append(run)
            run = [h]
    runs.append(run)
    run = max(runs, key=lambda r: sum(h[1] for h in r))

    i0, i1 = run[0][0], run[-1][0]
    total_hits = sum(h[1] for h in run)
    strong_hit = any(h[1] >= 3 for h in run)
    confidence = ("high" if strong_hit and total_hits >= 6 else
                  "medium" if total_hits >= 6 else
                  "low")
    start = segments[i0]["t"]
    end = segments[min(i1 + 1, len(segments) - 1)]["t"]
    if i1 + 1 < len(segments):
        end = segments[i1 + 1]["t"]
    return {
        "start": f"{start//3600:02d}:{(start%3600)//60:02d}:{start%60:02d}",
        "end": f"{end//3600:02d}:{(end%3600)//60:02d}:{end%60:02d}",
        "start_s": start, "end_s": end,
        "method": "anchor-alignment-v1",
        "confidence": confidence,
        "hits": [{"seg": h[0], "score": h[1], "terms": h[2][:6]} for h in run[:12]],
    }


def build_outline(items: list, segments: list = None) -> list:
    """Outline chapters for an ordered item list."""
    outline = []
    cursor = 0
    for item in items:
        entry = {
            "item_id": item.item_id,
            "title": item.title[:160],
            "method": "",
            "confidence": "",
            "start": "", "end": "",
            "deep_link": "",
        }
        link = next((d.get("url") for d in item.docs
                     if d.get("kind") == "video-link" and d.get("url")), "")
        if link:
            entry["method"] = "granicus-mediaplayer-link-v1"
            entry["confidence"] = "high"
            entry["deep_link"] = link
        if segments:
            span = align_asr(item, segments, after_s=cursor)
            if span:
                entry.update({
                    "start": span["start"], "end": span["end"],
                    "method": span["method"],
                    "confidence": span["confidence"],
                    "hits": span["hits"][:6],
                })
                cursor = span.get("start_s", cursor)
        elif item.locator.get("para") and item.method.startswith("minutes"):
            entry["method"] = "minutes-paragraph-span-v1"
            entry["confidence"] = "high"
            entry["start"] = f"¶{item.locator['para']}"
            entry["end"] = ""
        outline.append(entry)
    return outline
