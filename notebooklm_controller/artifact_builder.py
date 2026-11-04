#!/usr/bin/env python3
"""
artifact_builder.py — Build one meeting's studio artifacts.

Two modes, strictly separated — minutes and verbatim transcripts are NEVER
substituted for one another:

  VERBATIM mode (2026 meetings, has_verbatim_transcript=True):
    Full pipeline with [HH:MM:SS] timestamps, verbatim quotes, audio overview.

  MINUTES mode (2008-2025 meetings, has_verbatim_transcript=False):
    Minutes are summarized official records — NOT verbatim, no timestamps.
    Artifacts are labeled accordingly. No fake timestamps, no fake quotes,
    no audio overview built on non-existent captions.

Outputs per meeting in artifacts/<date>-<body>-<clip_id>/:
  00_manifest.json     provenance + watermark scan audit + notebook spec
  01_meeting_brief.md  who, what, when, outcomes, motions, votes
  02_transcript_notes.md verbatim quotes w/ timestamps (verbatim mode only)
                         OR minutes summary (minutes mode)
  03_agenda_trace.md   agenda items -> supporting documents -> disposition
  04_historical_context.md prior meetings on the same topics (woven in)
  05_audio_overview.txt  NotebookLM-style script (verbatim mode only)
                         OR minutes-notice (minutes mode)
  06_studio_package.md   single combined deliverable

Every artifact is scrubbed of NotebookLM / Gemini watermark strings before it
hits disk, and the scrub audit is recorded in 00_manifest.json.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "notebooklm_controller" / "artifacts"

ORDINANCE_RE = re.compile(r"\bordinance\s+(?:no\.?\s*)?#?\s*(\d{3,}[A-Z]?)", re.I)
RESOLUTION_RE = re.compile(r"\bresolution\s+(?:no\.?\s*)?#?\s*(\d{3,}[A-Z]?)", re.I)
MOTION_RE = re.compile(r"(motion\s+(?:carries|passes|fails|is\s+approved|unanimous)|unanimously\s+elected|motion\s+to\s+\w+)", re.I)
ITEM_RE = re.compile(r"\b(?:item|number)\s+([\d]{1,3}[A-Z]?(?:\.\d+)?)", re.I)
DOLLAR_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d{2})?")

MAX_QUOTES = 14
MAX_QUOTE_WORDS = 40


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Verbatim transcript parsing (2026 only — [HH:MM:SS] timestamped captions)
# ---------------------------------------------------------------------------

def _parse_transcript(text: str) -> dict:
    """Split header from timed paragraphs.

    Header is one pipe-separated line:
      MEETING: planning-commission | DATE: 2026-01-05 | YT_ID: DpyCQEaEWQ0
    Body contains lines like: [HH:MM:SS] verbatim text
    """
    header, body = text, ""
    if "\n\n" in text:
        header, body = text.split("\n\n", 1)
    meta: dict[str, str] = {}
    first = header.splitlines()[0] if header.splitlines() else ""
    for part in first.split("|"):
        part = part.strip()
        if ":" in part:
            key, _, val = part.partition(":")
            meta[key.strip().lower()] = val.strip()
    paras: list[tuple[str, str]] = []
    for line in body.splitlines():
        line = line.strip()
        m = re.match(r"^\[(\d{2}:\d{2}:\d{2})\]\s*(.*)$", line)
        if m:
            paras.append((m.group(1), m.group(2)))
    return {"meta": meta, "paragraphs": paras, "raw": body}


def _parse_minutes(text: str) -> dict:
    """Parse minutes text into plain paragraphs — NO timestamps.

    Minutes are summarized official records. We split into paragraphs for
    keyword scanning only; no timestamps are invented.
    """
    header, body = text, ""
    if "\n\n" in text:
        header, body = text.split("\n\n", 1)
    meta: dict[str, str] = {}
    first = header.splitlines()[0] if header.splitlines() else ""
    for part in first.split("|"):
        part = part.strip()
        if ":" in part:
            key, _, val = part.partition(":")
            meta[key.strip().lower()] = val.strip()
    # Split body into paragraphs; no timestamps.
    paras: list[tuple[Optional[str], str]] = []
    for para in body.split("\n\n"):
        para = para.strip()
        if para:
            paras.append((None, para))
    return {"meta": meta, "paragraphs": paras, "raw": body}


def _attendees(text: str) -> list[str]:
    """Extract roll-call names from lines like ``>> Tony Leard >> here.``.

    Only meaningful in verbatim transcript mode. Minutes rarely have this
    format; returns empty list for minutes text.
    """
    found: list[str] = []
    for line in text.splitlines():
        if ">>" not in line:
            continue
        low = line.lower()
        if not (">> present" in low or ">> here" in low):
            continue
        for segment in line.split(">>"):
            seg = segment.strip(" .,:;")
            if not seg or seg[0].islower() or "[" in seg or any(ch.isdigit() for ch in seg):
                continue
            words = seg.split()
            if 1 < len(words) <= 4 and all(w[0].isalpha() for w in words):
                name = " ".join(words)
                if name.lower() in {"present", "here", "remote", "remotely", "chair", "mr chair", "madam mayor"}:
                    continue
                found.append(name)
    seen, uniq = set(), []
    for n in found:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return uniq[:24]


def _key_moments(paras: list[tuple[Optional[str], str]]) -> list[tuple[Optional[str], str]]:
    """Paragraphs that look like decisions / hearings / elections / money."""
    moments = []
    for ts, text in paras:
        low = text.lower()
        score = 0
        for tok in ("motion", "ordinance", "resolution", "public hearing",
                    "elected", "appoint", "approve", "deny", "vote",
                    "consent agenda", "executive session", "$"):
            if tok in low:
                score += 1
        if score >= 2:
            moments.append((ts, text))
    return moments[:12]


def _verbatim_quotes(paras: list[tuple[Optional[str], str]]) -> list[tuple[Optional[str], str]]:
    """Up to MAX_QUOTES short, quotable moments with timestamps (verbatim only)."""
    quotes = []
    for ts, text in paras:
        words = text.split()
        if 8 <= len(words) <= MAX_QUOTE_WORDS:
            quotes.append((ts, text))
            if len(quotes) >= MAX_QUOTES:
                break
    return quotes


# ---------------------------------------------------------------------------
# Artifact builders — minutes mode (no timestamps, no fake quotes)
# ---------------------------------------------------------------------------

def _minutes_brief(date: str, body: str, title: str, minutes_text: str,
                   yt_id: Optional[str], yt_url: Optional[str],
                   supporting: list[dict]) -> str:
    """Build meeting brief for minutes-only meetings. No YouTube claims."""
    meta = _parse_minutes(minutes_text)["meta"]
    attendees = _attendees(minutes_text)
    moments = _key_moments(_parse_minutes(minutes_text)["paragraphs"])[:8]

    lines = [
        f"# MEETING BRIEF — {title}",
        "",
        f"**Date:** {date}   **Body:** {body}",
    ]
    if yt_url:
        lines.append(f"**YouTube video:** {yt_url}  (video id `{yt_id}`)")
    else:
        lines.append("**YouTube video:** none available")
    lines.append("")
    lines.append("**Source:** Granicus summarized minutes (NOT verbatim transcript, "
                 "no timestamps).")
    lines.append("")
    lines.append("## Proceedings at a glance")
    lines.append("")
    if attendees:
        lines.append(f"**Attendees (roll call):** {', '.join(attendees)}")
        lines.append("")
    lines.append("## Key moments (from summarized minutes — no timestamps)")
    for ts, text in moments:
        short = text[:260] + ("…" if len(text) > 260 else "")
        ts_label = f"[{ts}] " if ts else ""
        lines.append(f"- {ts_label}{short}")
    if not moments:
        lines.append("- No decision-dense paragraphs auto-detected in minutes.")
    lines.append("")
    lines.append("## Supporting documents on the record")
    if supporting:
        for d in supporting:
            lines.append(_supporting_doc_line(d, date))
    else:
        lines.append("- No supporting documents harvested yet; run with network access "
                     "to fetch the Granicus agenda page and its linked staff reports "
                     "and packet documents.")
    lines.append("")
    lines.append("## Outcomes")
    lines.append("- See 02_transcript_notes.md for minutes summary.")
    lines.append("- See 04_historical_context.md for how this meeting relates to prior ones.")
    lines.append("")
    lines.append("> NOTE: This brief is built from Granicus summarized minutes, not a "
                 "> verbatim transcript. No timestamps or word-for-word quotations are "
                 "> available for this meeting.")
    return "\n".join(lines) + "\n"


def _minutes_notes(minutes_text: str, meta: dict) -> str:
    """Build transcript_notes for minutes-only meetings — no verbatim quotes."""
    paras = _parse_minutes(minutes_text)["paragraphs"]
    lines = [
        "# TRANSCRIPT NOTES — summarized minutes (NOT verbatim)",
        "",
        f"Meeting: {meta.get('meeting', '')} | {meta.get('date', '')}",
        "",
        "## Source note",
        "",
        "Granicus summarized minutes are an official record summary. They are NOT a "
        "verbatim transcript, contain no timestamps, and do not preserve word-for-word "
        "quotations. No timestamps are available for this meeting.",
        "",
        "## Minutes summary (key passages)",
        "",
    ]
    for ts, text in paras:
        short = text[:400] + ("…" if len(text) > 400 else "")
        lines.append(f"- {short}")
        lines.append("")
    lines.append("## Decision-dense passages (from minutes)")
    for ts, text in _key_moments(paras)[:10]:
        ts_label = f"[{ts}] " if ts else ""
        lines.append(f"- {ts_label}{text[:300]}{'…' if len(text) > 300 else ''}")
    lines.append("")
    return "\n".join(lines) + "\n"


def _audio_overview_minutes(date: str, body: str, title: str, minutes_text: str,
                            yt_url: Optional[str]) -> str:
    """Minutes-mode 'audio overview' — no timestamped walk-through.

    Clearly states that no verbatim transcript exists for this meeting.
    """
    meta = _parse_minutes(minutes_text)["meta"]
    moments = _key_moments(_parse_minutes(minutes_text)["paragraphs"])[:5]
    lines = [
        "# AUDIO OVERVIEW — minutes summary (no verbatim transcript available)",
        "",
        f"Meeting: {title} ({date})",
        f"YouTube: {yt_url or 'none available'}",
        "",
        "[Alex] Welcome to the Cheyenne meeting record. Today we're looking at the ",
        f"{title} from {date}.",
        "[Sam] This meeting is documented in Granicus summarized minutes only — there "
        "is no verbatim YouTube transcript available for this date, so we cannot "
        "provide timestamped quotations or a word-for-word walk-through.",
        "",
        "## What the minutes record",
        "",
    ]
    for ts, text in moments:
        short = text[:220] + ("…" if len(text) > 220 else "")
        lines.append(f"- {short}")
    if not moments:
        lines.append("- No decision-dense paragraphs auto-detected in minutes.")
    lines.append("")
    lines.append("[Both] That's the record for this meeting. Because only summarized "
                 "minutes survive, this entry is limited to what the minutes contain.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Verbatim mode builders (existing logic, adapted)
# ---------------------------------------------------------------------------

def _meeting_brief_verbatim(meta, paras, transcript_text, yt_id, yt_url, title,
                            supporting) -> str:
    date = meta.get("date", "")
    body = meta.get("meeting", "")
    yt_id_line = meta.get("yt_id", yt_id)
    attendees = _attendees(transcript_text)
    moments = _key_moments(paras)[:8]
    lines = [
        f"# MEETING BRIEF — {title}",
        "",
        f"**Date:** {date}   **Body:** {body}   **YouTube video:** {yt_url}  (video id `{yt_id_line}`)",
        f"**Source:** verbatim YouTube transcript (City of Cheyenne channel @TheCityofCheyenne)",
        "",
        "## Proceedings at a glance",
        "",
    ]
    if attendees:
        lines.append(f"**Attendees (roll call):** {', '.join(attendees)}")
        lines.append("")
    lines.append("## Key moments (timestamped)")
    for ts, text in moments:
        short = text[:260] + ("…" if len(text) > 260 else "")
        lines.append(f"- [{ts}] {short}")
    if not moments:
        lines.append("- No decision-dense paragraphs auto-detected; see transcript notes.")
    lines.append("")
    lines.append("## Supporting documents on the record")
    if supporting:
        for d in supporting:
            lines.append(_supporting_doc_line(d, date))
    else:
        lines.append("- No supporting documents harvested yet; run with network access "
                     "to fetch the Granicus agenda page and its linked staff reports "
                     "and packet documents.")
    lines.append("")
    lines.append("## Outcomes")
    lines.append("- See 02_transcript_notes.md for verbatim motions and votes.")
    lines.append("- See 04_historical_context.md for how this meeting relates to prior ones.")
    return "\n".join(lines) + "\n"


def _transcript_notes_verbatim(paras, meta) -> str:
    lines = [
        "# TRANSCRIPT NOTES — verbatim record",
        "",
        f"Meeting: {meta.get('meeting', '')} | {meta.get('date', '')}",
        f"YouTube id: {meta.get('yt_id', '')}",
        "",
        "## Verbatim quotes (timestamps from the YouTube video)",
        "",
    ]
    for ts, text in _verbatim_quotes(paras):
        lines.append(f"> [{ts}] {text}")
        lines.append("")
    lines.append("## Decision-dense passages")
    for ts, text in _key_moments(paras)[:10]:
        lines.append(f"- [{ts}] {text[:300]}{'…' if len(text) > 300 else ''}")
    lines.append("")
    return "\n".join(lines) + "\n"


def _audio_overview_verbatim(date, body, title, meta, paras, prior, yt_url) -> str:
    host1, host2 = "Alex", "Sam"
    lines = [
        "# AUDIO OVERVIEW — AI-narrated studio script",
        "",
        f"Meeting: {title} ({date})",
        f"YouTube: {yt_url}",
        "",
        f"[{host1}] Welcome to the Cheyenne meeting record. Today we're looking at the "
        f"{title} from {date}, streamed on the City of Cheyenne's YouTube channel.",
        f"[{host2}] Right. This meeting has the verbatim transcript plus the agenda "
        f"supporting documents loaded into the notebook.",
    ]
    if prior:
        lines.append(f"[{host1}] And we're not starting cold — the notebook carries "
                     f"context from {len(prior)} earlier meeting(s) that touch the "
                     f"same topics, so whatever happened before this date is right "
                     f"here with us.")
        lines.append(f"[{host2}] Exactly. If this council is revisiting an ordinance "
                     f"or a project, we can point at the exact earlier meeting where "
                     f"it was introduced.")
    else:
        lines.append(f"[{host1}] This opens the thread — no earlier archived meeting "
                     f"shares indexed topics with this one yet.")
    lines.append(f"[{host2}] Let's walk through what happened, then what it means "
                 f"in context.")
    lines.append("")
    lines.append("## Segment 1 — what happened")
    moments = _key_moments(paras)[:5]
    for ts, text in moments:
        lines.append(f"- [{ts}] {text[:220]}{'…' if len(text) > 220 else ''}")
    lines.append("")
    lines.append("## Segment 2 — why it matters")
    lines.append("- Tie to prior meetings named in 04_historical_context.md.")
    lines.append("- Watch for the same ordinance numbers and names returning.")
    lines.append("")
    lines.append("[Both] That's the record for this meeting. On to the next one — "
                 "chronologically, oldest to newest, all the way to the present.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _supporting_doc_line(d: dict, date: str) -> str:
    kind = d.get("kind", "")
    label = d.get("label") or d.get("name") or "document"
    url = d.get("url") or d.get("agenda_url") or d.get("player_url") or "n/a"
    if kind == "agenda":
        return f"- {label} — {url}" + (f"  [saved: {d['local']}]" if d.get("local") else "")
    if kind == "minutes":
        return f"- {label} (minutes) — {url}"
    if kind == "metaviewer":
        return (f"- {label} (staff report / packet) — {url}"
                + (f"  [saved: {d['local']}]" if d.get("local") else "")
                + ("  [fetch failed]" if d.get("fetched") is False else ""))
    if kind == "pdf":
        return (f"- {label} (PDF) — {url}"
                + (f"  [saved: {d['local']}]" if d.get("local") else "")
                + ("  [fetch failed]" if d.get("fetched") is False else ""))
    parts = []
    if d.get("agenda_url"):
        parts.append(f"agenda: {d['agenda_url']}")
    if d.get("minutes_url"):
        parts.append(f"minutes: {d['minutes_url']}")
    if d.get("mp4_url"):
        parts.append(f"video: {d['mp4_url']}")
    return f"- {label} ({d.get('date_display', date)}) — " + " | ".join(parts) if parts else f"- {label}"


def _agenda_trace(paras: list[tuple[Optional[str], str]], meta: dict,
                  supporting: list[dict]) -> str:
    items = []
    seen = set()
    for ts, text in paras:
        for m in ITEM_RE.finditer(text):
            item = m.group(0)
            if item not in seen:
                seen.add(item)
                items.append((ts, item, text[:200]))
    lines = ["# AGENDA TRACE — agenda items, supporting documents, dispositions",
             "",
             "Agenda items referenced in the meeting record, matched to the "
             "Granicus agenda/supporting-document catalog for this date:",
             ""]
    if items:
        for ts, item, snippet in items[:20]:
            lines.append(f"- **{item}** — raised at [{ts}]" if ts else f"- **{item}**")
            lines.append(f'  "{snippet}…"')
            doc = next((d for d in supporting if item in str(d)), None)
            lines.append(f"  Supporting doc: {doc['agenda_url'] if doc else 'not cataloged'}")
    else:
        lines.append("- No numbered agenda items detected in meeting text.")
    lines.append("")
    lines.append("## Full supporting-document list (agenda page + Granicus catalog)")
    if supporting:
        for d in supporting:
            lines.append(f"- [{d.get('label', 'document')}] ({d.get('kind', '')}) "
                         f"{d.get('url', 'n/a')}"
                         + (f"  [saved: {d['local']}]" if d.get("local") else "")
                         + (f"  [NOT FETCHED]" if d.get("fetched") is False else ""))
    else:
        lines.append("- None cataloged for this date.")
    lines.append("")
    return "\n".join(lines) + "\n"


def _historical_context(prior: list[dict]) -> str:
    if not prior:
        return ("# HISTORICAL CONTEXT — preceding meetings\n\n"
                "No earlier archived meeting shares indexed topics with this "
                "meeting; this item opens a new thread in the record.\n")
    lines = ["# HISTORICAL CONTEXT — preceding meetings",
             "",
             "Earlier Cheyenne meetings that touch the same ordinances, projects, "
             "or officials. Context is woven automatically from the entity index "
             "so each artifact builds on everything that came before it:",
             ""]
    for item in prior:
        shared = ", ".join(item["shared"][:8])
        lines.append(f"- **{item['date']} — {item['body']}** (shared: {shared})")
        if item.get("snippet"):
            lines.append(f'  > "{item["snippet"]}"')
        if item.get("artifact"):
            lines.append(f'  Artifact: `{item["artifact"]}`')
    lines.append("")
    lines.append("Reading order: start with the oldest referenced meeting and work "
                 "forward; by the time you reach this meeting, the full archival "
                 "thread is visible.")
    return "\n".join(lines) + "\n"


def _studio_package(title, date, body, out) -> str:
    order = ["01_meeting_brief.md", "02_transcript_notes.md", "03_agenda_trace.md",
             "04_historical_context.md", "05_audio_overview.txt"]
    lines = [
        f"# STUDIO PACKAGE — {title}",
        f"City of Cheyenne • {body} • {date}",
        f"Generated by notebooklm_controller (auto-run, oldest -> newest)",
        "",
        "---",
        "",
    ]
    for fname in order:
        if fname in out:
            content = out[fname][0]
            lines.append(f"## {fname}")
            lines.append("")
            lines.append(content.rstrip())
            lines.append("")
            lines.append("---")
            lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_artifacts(meeting: dict, prior_context: list[dict],
                    scrub) -> dict[str, tuple[str, dict]]:
    """Return {filename: (content, watermark_scan_result)} for one meeting.

    Branches on meeting['has_verbatim_transcript']:
      True  → verbatim transcript mode (timestamps, quotes, audio overview)
      False → minutes-only mode (no timestamps, no fake quotes, clearly labeled)
    """
    has_verbatim = meeting.get("has_verbatim_transcript", False)
    date = meeting["date"]
    body = meeting["body"]
    clip_id = meeting["clip_id"]
    yt_id = meeting.get("youtube_id")
    yt_url = meeting.get("youtube_url")
    title = meeting["title"]
    supporting = meeting.get("supporting_docs", [])

    if has_verbatim:
        transcript_text = meeting.get("transcript_text") or ""
        parsed = _parse_transcript(transcript_text)
        meta = parsed["meta"]
        paras = parsed["paragraphs"]

        brief = _meeting_brief_verbatim(meta, paras, transcript_text, yt_id, yt_url,
                                        title, supporting=supporting)
        notes = _transcript_notes_verbatim(paras, meta)
        trace = _agenda_trace(paras, meta, supporting=supporting)
        context = _historical_context(prior_context)
        audio = _audio_overview_verbatim(date, body, title, meta, paras,
                                         prior_context, yt_url)

        pieces = [
            ("01_meeting_brief.md", brief),
            ("02_transcript_notes.md", notes),
            ("03_agenda_trace.md", trace),
            ("04_historical_context.md", context),
            ("05_audio_overview.txt", audio),
        ]

        manifest_meeting = {
            "date": date,
            "body": body,
            "title": title,
            "youtube_video_id": yt_id,
            "youtube_url": yt_url,
            "transcript_file": meeting.get("transcript_path"),
            "transcript_sha256": _sha(transcript_text),
            "paragraphs": len(paras),
            "source_type": "verbatim_transcript",
        }
        manifest_sources = {
            "youtube_video": {"type": "youtube_video", "video_id": yt_id,
                              "url": yt_url, "title": title},
            "verbatim_transcript": {"type": "transcript",
                                    "path": meeting.get("transcript_path"),
                                    "source": "corpus_yt (machine mirror of YouTube captions)"},
            "supporting_documents": supporting,
        }
    else:
        # MINUTES MODE — no verbatim transcript available
        minutes_text = meeting.get("minutes_text") or ""
        parsed = _parse_minutes(minutes_text)
        meta = parsed["meta"]
        paras = parsed["paragraphs"]

        brief = _minutes_brief(date, body, title, minutes_text, yt_id, yt_url,
                               supporting)
        notes = _minutes_notes(minutes_text, meta)
        trace = _agenda_trace(paras, meta, supporting=supporting)
        context = _historical_context(prior_context)
        audio = _audio_overview_minutes(date, body, title, minutes_text, yt_url)

        pieces = [
            ("01_meeting_brief.md", brief),
            ("02_transcript_notes.md", notes),
            ("03_agenda_trace.md", trace),
            ("04_historical_context.md", context),
            ("05_audio_overview.txt", audio),
        ]

        manifest_meeting = {
            "date": date,
            "body": body,
            "title": title,
            "youtube_video_id": yt_id,
            "youtube_url": yt_url,
            "minutes_file": meeting.get("minutes_path"),
            "paragraphs": len(paras),
            "source_type": "minutes_only",
            "note": "No verbatim transcript available for this meeting; artifacts "
                    "built from Granicus summarized minutes only.",
        }
        manifest_sources = {
            "youtube_video": {"type": "youtube_video", "video_id": yt_id,
                              "url": yt_url, "title": title} if yt_url else None,
            "summarized_minutes": {"type": "minutes",
                                   "path": meeting.get("minutes_path"),
                                   "source": "granicus_minutes",
                                   "note": "Summarized official minutes — not verbatim, "
                                           "no timestamps."},
            "supporting_documents": supporting,
        }

    out: dict[str, tuple[str, dict]] = {}
    for fname, content in pieces:
        scrubbed, scan = scrub(content)
        out[fname] = (scrubbed, {"file": fname, "scan": {
            "found": scan.found, "matches": scan.matches, "lines": scan.lines}})

    package = _studio_package(title, date, body, out)
    scrubbed_pkg, pkg_scan = scrub(package)
    out["06_studio_package.md"] = (scrubbed_pkg,
                                   {"file": "06_studio_package.md", "scan": {
                                       "found": pkg_scan.found,
                                       "matches": pkg_scan.matches,
                                       "lines": pkg_scan.lines}})

    manifest = {
        "notebook": {
            "notebook_id": f"nb-{date.replace('-', '')}-{clip_id}",
            "title": f"City of Cheyenne — {title}",
            "description": (f"NotebookLM controller notebook for the {title} "
                            f"meeting ({date}). Sources: "
                            f"{', '.join(meeting.get('source_availability', []))}. "
                            f"One notebook per meeting; historical context woven "
                            f"from prior notebooks."),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "controller": "notebooklm_controller (third-party, browser-drive adapter; simulation mode unless --live)",
        },
        "meeting": manifest_meeting,
        "sources": {k: v for k, v in manifest_sources.items() if v is not None},
        "artifacts": {fname: {"sha256": _sha(content), "watermark_scan": scan}
                      for fname, (content, scan) in out.items()},
        "historical_context": {
            "prior_meetings_referenced": [p["date"] for p in prior_context],
            "shared_entities_sample": [e for p in prior_context for e in p.get("shared", [])][:12],
        },
    }
    out["00_manifest.json"] = (json.dumps(manifest, indent=1), {"file": "00_manifest.json", "scan": {"found": False, "matches": [], "lines": []}})
    return out
