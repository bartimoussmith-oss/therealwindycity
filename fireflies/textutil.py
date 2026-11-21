"""Small shared text utilities. Verbatim-quote discipline starts here: anything
stored as evidence keeps its original wording; helpers only clip with an
explicit ellipsis marker and never rewrite."""
from __future__ import annotations

import re
import unicodedata

SENT_SPLIT = re.compile(
    r"(?<!Mr\.)(?<!Mrs\.)(?<!Ms\.)(?<!Dr\.)(?<!Prof\.)(?<!Sr\.)(?<!Jr\.)"
    r"(?<!St\.)(?<!No\.)(?<!vs\.)(?<!etc\.)(?<!Rep\.)(?<!Sen\.)(?<=[.!?])"
    r"\s+(?=[A-Z\[\"'“(])")

# single-letter word splits from older PDF text extraction ("M otion", "a nd")
_OCR_JOINED = set("""
motion the and that this with they them than then submitted supported seconded
moved approved carried present minutes ordinance resolution public hearing upon
after all our you for are were was not but his her had has have been will would
could should there their what when where which who whom whose also only very
more most some such into over under again further once here now own same too
just about against between during before below above to in on at of by off out
up down in out if or as
""".split())


def ocr_join(text: str) -> str:
    """Matching-view only: rejoin single-letter OCR splits when the joined form
    is a known word. Stored quotes always keep the raw wording."""

    def fix(m):
        joined = (m.group(1) + m.group(2))
        return joined if joined.lower() in _OCR_JOINED else m.group(0)

    return re.sub(r"\b([A-Za-z]) ([a-z]{2,})\b", fix, text)


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def strip_tags(html: str) -> str:
    txt = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    txt = re.sub(r"<style.*?</style>", " ", txt, flags=re.S | re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = unicodedata.normalize("NFKC", txt)
    return normalize_ws(txt)


def unescape_html(html: str) -> str:
    import html as _h
    return _h.unescape(html)


def split_sentences(text: str) -> list:
    """Sentence split tuned for minutes prose and caption run-ons."""
    text = normalize_ws(text)
    if not text:
        return []
    parts = SENT_SPLIT.split(text)
    return [p.strip() for p in parts if len(p.strip()) > 2]


def first_sentence(text: str, max_len: int = 700) -> str:
    """First sentence only (abbreviation-aware), for titles and attendance."""
    text = normalize_ws(text)
    if not text:
        return ""
    m = SENT_SPLIT.split(text, maxsplit=1)
    return m[0][:max_len].strip()


def clip_quote(text: str, limit: int = 300) -> str:
    """Hard cap for stored evidence quotes. The trailing '…' marks the cut, and
    verifiers strip it before substring checks."""
    text = normalize_ws(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def quote_body(quote: str) -> str:
    """The verifiable part of a stored quote (ellipsis tail removed)."""
    return quote.rstrip("…").rstrip()


def words(text: str) -> list:
    return re.findall(r"[A-Za-z][A-Za-z'’\-]{1,}", text or "")


def find_normalized(text: str, snippet: str, start: int = 0) -> int:
    """Char index of a whitespace-normalized snippet inside raw text.
    Exact find first; then whitespace-flexible word match."""
    if not snippet:
        return -1
    idx = text.find(snippet[:60], start)
    if idx >= 0:
        return idx
    ws = snippet.split()[:12]
    if not ws:
        return -1
    rx = re.compile(r"\s+".join(re.escape(w) for w in ws))
    m = rx.search(text, start)
    return m.start() if m else -1
