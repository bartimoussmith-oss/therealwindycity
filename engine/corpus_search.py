"""corpus_search.py — shared loader/searcher for the minutes transcript archive.

Used by the site's Minutes Archive tab and by verify_vault.py. Pure stdlib.
The corpus lives at pipeline/corpus/*.txt in the repo (meeting minutes,
2008-present, pushed from the Colab pipeline). Dates come from filenames
like 1091_2026-04-13.txt.

A second corpus lives at pipeline/corpus_yt/*.txt: verbatim YouTube
transcripts mirrored from therealwindycity/The-Real-Windy-City- by
pipeline/sync_yt_corpus.py (council, committees, work sessions, boards).
Each loaded document carries a "source" field: "minutes" or "verbatim-yt".
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def norm(s: str) -> str:
    """Lowercase, strip accents/punct, collapse whitespace — for matching."""
    s = unicodedata.normalize("NFKD", s).lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_corpus(root: Path) -> list[dict]:
    """All minutes transcripts under root/'pipeline'/'corpus' (+/*.txt),
    plus verbatim YouTube transcripts under root/'pipeline'/'corpus_yt'."""
    out = []
    for dirname, source in (("corpus", "minutes"), ("corpus_yt", "verbatim-yt")):
        cdir = Path(root) / "pipeline" / dirname
        if not cdir.is_dir():
            continue
        for fp in sorted(cdir.glob("*.txt")):
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            m = _DATE.search(fp.name)
            out.append({"name": fp.name,
                        "date": m.group(1) if m else "",
                        "source": source,
                        "text": text,
                        "norm": norm(text)})
    return out


def search(corpus: list[dict], query: str, context: int = 220,
           limit: int = 60) -> list[dict]:
    """Every-term match: a file matches when all query terms appear in it.
    Snippet is centered on the first term."""
    terms = [norm(t) for t in query.split() if len(norm(t)) >= 3]
    if not terms:
        return []
    hits = []
    for doc in corpus:
        if all(t in doc["norm"] for t in terms):
            i = doc["norm"].find(terms[0])
            lo, hi = max(0, i - context), i + len(terms[0]) + context
            hits.append({"file": doc["name"], "date": doc["date"],
                         "source": doc.get("source", "minutes"),
                         "snippet": doc["norm"][lo:hi]})
        if len(hits) >= limit:
            break
    return hits
