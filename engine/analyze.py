"""Module 3 (analysis): watchlist scanner + offline summarizer.

Integrity rules:
  * scan_and_alert stores a VERBATIM snippet (no paraphrase) plus doc pointer.
  * Summarizer defaults to an extractive, no-LLM mode that can only select —
    never generate — sentences, and labels its method. Wire a real model by
    passing llm_fn (any callable str->str); outputs are still method-tagged.
"""
from __future__ import annotations

import re
from collections import Counter

from . import db

_STOP = set(("the a an and or of to in for on with by is are was were be been "
             "that this it as at from we you they he she city council not but".split()))


def scan_and_alert(conn, doc_id: int, text: str) -> int:
    hits = 0
    lowered = text.lower()
    for topic, term in db.load_watchlist():
        idx = lowered.find(term.lower())
        if idx == -1:
            continue
        start = max(0, idx - 120)
        end = min(len(text), idx + 120)
        snippet = re.sub(r"\s+", " ", text[start:end]).strip()
        db.record_alert(conn, doc_id, f"{topic}:{term}", f"…{snippet}…")
        hits += 1
    return hits


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 25]


def extractive_summary(text: str, max_sentences: int = 5) -> list[str]:
    """Frequency-scored sentence selection (TextRank-lite). Offline, safe."""
    sentences = _split_sentences(text)
    if len(sentences) <= max_sentences:
        return sentences
    freq = Counter(
        w for w in re.findall(r"[a-z']{3,}", text.lower()) if w not in _STOP
    )
    ranked = sorted(
        sentences,
        key=lambda s: -sum(freq.get(w, 0) for w in re.findall(r"[a-z']{3,}", s.lower())),
    )
    picked = ranked[:max_sentences]
    return sorted(picked, key=lambda s: sentences.index(s))  # original order


class Summarizer:
    """Provider-agnostic. Default: extractive (offline, cannot hallucinate).
    To wire an LLM: Summarizer(llm_fn=lambda prompt: your_client.complete(prompt)).
    Whatever it returns is stored verbatim with method='llm'."""

    def __init__(self, llm_fn=None):
        self.llm_fn = llm_fn

    def summarize(self, text: str) -> dict:
        if self.llm_fn is None:
            return {
                "method": "extractive-offline",
                "summary": "\n".join("• " + s for s in extractive_summary(text)),
            }
        prompt = ("Summarize the following public document in 5 bullets. Quote "
                  "figures and names exactly as written. Do not add facts.\n\n" + text[:12000])
        return {"method": "llm", "summary": self.llm_fn(prompt)}
