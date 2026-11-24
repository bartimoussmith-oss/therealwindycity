"""Extractive, method-tagged summaries, keywords and entity extraction.

Same integrity contract as engine/analyze.Summarizer: the summarizer can only
SELECT sentences from the source, never generate text. Every sentence in a
brief is a verbatim substring of a source file and carries a locator.
"""
from __future__ import annotations

import re
from collections import Counter

from .textutil import clip_quote, find_normalized, normalize_ws, split_sentences, words

_STOP = set("""
the a an and or of to in for on with by is are was were be been that this it as at
from we you they he she city council not but if then than there here all any each
which who whom whose what when where why how also into over under after before
during while about against between through its my our your their his her their
one two three four five six seven eight nine ten mr mrs ms dr professor
said says say would could should will shall may might can must do does did done
has have had having be been being am
think know just like get going gonna we're that's don't it's i'm he's she's they're
we've i've you're well okay yeah right um uh really thing things stuff kind sort
maybe actually probably definitely certainly obviously basically literally
look looked looking want wanted wants need needed needs make made makes
take took taken give gave given go went gone come came coming
""".split())

METHOD = "extractive-freq-v1"


def extractive_summary(text: str, max_sentences: int = 7, context: str = "minutes") -> list:
    """Frequency-scored sentence selection with a lead-position bonus.

    Returns [{'sentence', 'locator'}] in original document order. Sentences are
    verbatim; locators are char offsets (paragraph numbers for minutes).
    """
    # work on the raw text so we can locate sentences afterward
    sentences = split_sentences(text)
    # de-duplicate (minutes repeat boilerplate voting lines verbatim)
    seen_s = set()
    uniq = []
    for s in sentences:
        key = re.sub(r"\W+", "", s.lower())[:120]
        if key in seen_s:
            continue
        seen_s.add(key)
        uniq.append(s)
    sentences = uniq
    if len(sentences) <= max_sentences:
        picked = sentences
    else:
        freq = Counter(w for w in re.findall(r"[a-z']{3,}", text.lower()) if w not in _STOP)
        base = max(freq.values() or [1])
        scores = []
        for i, s in enumerate(sentences):
            ws = re.findall(r"[a-z']{3,}", s.lower())
            score = sum(freq.get(w, 0) for w in ws) / (len(ws) + 5)
            score += 0.35 * base / (10 + i)          # lead bonus (agendas front-load)
            if re.search(r"(?i)\b(motion carried|motion passed|approved|directed staff|"
                         r"public hearing|tabled|voting)\b", s):
                score *= 1.15                         # outcomes matter in meetings
            scores.append((score, i))
        top = sorted(sorted(scores, key=lambda x: -x[0])[:max_sentences], key=lambda x: x[1])
        picked = [sentences[i] for _, i in top]

    out = []
    for s in picked:
        idx = find_normalized(text, s)
        loc = {"char": max(idx, 0)}
        if context == "minutes":
            loc["para"] = text[:max(idx, 0)].count("\n\n") + 1
        out.append({"sentence": clip_quote(s, 320), "locator": loc})
    return out


def keywords(text: str, k: int = 12) -> list:
    """Top content terms (unigrams + bigrams), count-ranked."""
    ws = [w.lower() for w in words(text) if w.lower() not in _STOP and len(w) > 2]
    uni = Counter(ws)
    bi = Counter(f"{a} {b}" for a, b in zip(ws, ws[1:])
                 if a not in _STOP and b not in _STOP)
    merged = [(t, c * 2) for t, c in bi.most_common(k * 2)] + uni.most_common(k * 3)
    seen, out = set(), []
    for t, c in sorted(merged, key=lambda x: -x[1]):
        if t in seen:
            continue
        seen.add(t)
        out.append({"term": t, "count": int(c)})
        if len(out) >= k:
            break
    return out


_ENT_RX = {
    "ordinance": re.compile(r"(?i)\bORDINANCE(?:\s+NO\.?|\s+NUMBER)?\s*(\d{3,5})\b"),
    "resolution": re.compile(r"(?i)\bRESOLUTION(?:\s+NO\.?|\s+NUMBER)?\s*(\d{3,5})\b"),
    "statute": re.compile(r"\b(?:W\.?\s?S\.?\s?)?(\d{1,2}-\d{1,2}-\d{3,4}(?:\([a-z0-9]+\))?)\b"),
    "money": re.compile(r"\$\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?"),
}


def entities(text: str) -> list:
    """Numbered ordinances/resolutions, statute cites, dollar amounts.
    Each entity carries a verbatim example quote (± context around 1st hit)."""
    out = []
    for etype, rx in _ENT_RX.items():
        seen = {}
        for m in rx.finditer(text):
            val = m.group(1) if rx.groups else m.group(0)
            val = val.strip()
            if etype == "money":
                val = re.sub(r"\s+", "", val)
            d = seen.setdefault(val, {"type": etype, "value": val, "count": 0,
                                     "example": None})
            d["count"] += 1
            if d["example"] is None:
                lo = max(0, m.start() - 60)
                hi = min(len(text), m.end() + 60)
                d["example"] = {
                    "quote": clip_quote(text[lo:hi], 240),
                    "locator": {"char": m.start()},
                }
        out.extend(seen.values())
    return sorted(out, key=lambda e: (-e["count"], e["type"], e["value"]))
