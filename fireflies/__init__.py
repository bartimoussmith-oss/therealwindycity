"""Fireflies-style meeting intelligence for the local civic meeting corpus.

Mirrors the core fireflies.ai loop — transcript in, intelligence out — over the
corpus this repo already holds:

  * meeting summaries + outline chapters linked to transcript timestamps,
  * agenda items linked to supporting documents and video deep links,
  * action items & decisions (motions, votes, directives) with verbatim quotes,
  * cross-meeting search and topic/entity tracking.

Integrity rules (same as engine/analyze.py): analysis is extractive and
pattern-based only — it can select and categorize sentences, never generate
them. Every derived claim carries a verbatim quote plus a source locator, and
``python3 -m fireflies verify`` re-checks every stored quote against its source
file. Method tags are stored on every generated field.

All corpora under pipeline/, uploads/, drive-import/ and rag/ are READ-ONLY
inputs; everything this package writes goes to fireflies/briefs/ and
fireflies/ledger/ (or an explicit --out directory).
"""

__version__ = "1.0.0"

METHOD_SUMMARY = "extractive-freq-v1"
METHOD_ITEMS_MINUTES = "minutes-item-patterns-v1"
METHOD_ITEMS_AGENDA = "granicus-agenda-html-v1"
METHOD_ITEMS_SPEECH = "speech-item-cues-v1"
METHOD_ACTIONS = "verbatim-pattern-v1"
METHOD_ALIGNMENT = "anchor-alignment-v1"
METHOD_ALIGNMENT_DEEP = "granicus-mediaplayer-link-v1"
