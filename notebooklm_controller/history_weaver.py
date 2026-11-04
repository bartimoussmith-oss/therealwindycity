#!/usr/bin/env python3
"""
history_weaver.py — Weave prior-meeting context into each new artifact.

As the controller walks the YouTube archive oldest -> newest, every meeting's
transcript is indexed for entities (ordinance numbers, resolution numbers,
chapter/code cites, statutes, dollar figures, project names, proper names).
Before a new meeting's artifacts are written, the weaver looks up those
entities in everything that came before and appends a

    HISTORICAL CONTEXT — what happened in earlier meetings

section, with dates, verbatim snippets, and links to the prior artifacts. By
the last meeting on the channel, the artifacts carry the full archival history
of every matter the governing body has touched.

Index keys are casefolded so "chapter 1.28" and "Chapter 1.28" match; meetings
are keyed by ``date|body`` so same-day committees don't clobber each other.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "notebooklm_controller" / "artifacts"
INDEX_PATH = ROOT / "notebooklm_controller" / "state" / "entity_index.json"

ORDINANCE_RE = re.compile(r"\bordinance\s+(?:no\.?\s*)?#?\s*(\d{3,}[A-Z]?)", re.I)
RESOLUTION_RE = re.compile(r"\bresolution\s+(?:no\.?\s*)?#?\s*(\d{3,}[A-Z]?)", re.I)
CHAPTER_RE = re.compile(r"\bchapter\s+(\d{1,3}(?:\.\d+)?)", re.I)
STATUTE_RE = re.compile(r"\bwyoming\s+statute\s+(\d{1,2}[-–]\d{1,3}[-–]\d{1,3}[A-Z]?)", re.I)
DOLLAR_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d{2})?")
# "project" matched case-insensitively only, followed by a capitalized name
PROJECT_RE = re.compile(r"\b[Pp]roject\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?")
NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b")

NAME_STOP = {
    "City Council", "Cheyenne Wyoming", "United States", "Pledge Allegiance",
    "Roll Call", "Public Comment", "Consent Agenda", "Executive Session",
    "Cheyenne City", "Cheyenne Leads", "Mr Chair", "Madame Clerk",
}
NAME_FILLER_FIRST = {"Uh", "Um", "And"}


def meeting_key(date: str, body: str) -> str:
    return f"{date}|{body}"


def key_date(key: str) -> str:
    return key.split("|", 1)[0]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def extract_entities(transcript_text: str, limit: int = 60) -> dict[str, list[str]]:
    """Pull named entities and citations out of a transcript. Deterministic
    regexes only — no NLP dependencies."""
    found: dict[str, list[str]] = {
        "ordinances": [],
        "resolutions": [],
        "chapters": [],
        "statutes": [],
        "dollars": [],
        "projects": [],
        "names": [],
    }
    for m in ORDINANCE_RE.finditer(transcript_text):
        found["ordinances"].append(m.group(0))
    for m in RESOLUTION_RE.finditer(transcript_text):
        found["resolutions"].append(m.group(0))
    for m in CHAPTER_RE.finditer(transcript_text):
        found["chapters"].append(m.group(0))
    for m in STATUTE_RE.finditer(transcript_text):
        found["statutes"].append(m.group(0))
    for m in DOLLAR_RE.finditer(transcript_text):
        amount = m.group(0).replace("$", "").replace(",", "")
        try:
            if float(amount) >= 100:  # skip noise like $2, $3, $14
                found["dollars"].append(m.group(0))
        except ValueError:
            pass
    for m in PROJECT_RE.finditer(transcript_text):
        found["projects"].append(m.group(0))
    stop = {"City Council", "Cheyenne Wyoming", "United States", "Pledge Allegiance",
            "Roll Call", "Public Comment", "Consent Agenda", "Executive Session",
            "Cheyenne City", "Cheyenne Leads", "Mr Chair", "Madame Clerk"}
    for m in NAME_RE.finditer(transcript_text):
        phrase = m.group(0)
        if phrase in NAME_STOP:
            continue
        if phrase.split()[0] in NAME_FILLER_FIRST:
            continue
        found["names"].append(phrase)

    for key in found:
        seen, uniq = set(), []
        for v in found[key]:
            if v not in seen:
                seen.add(v)
                uniq.append(v)
        found[key] = uniq[:limit]
    return found


def load_index() -> dict:
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"entities": {}, "meetings": {}}


def save_index(index: dict) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(index, indent=1), encoding="utf-8")


def find_prior_context(entities: dict[str, list[str]], current_date: str,
                       index: dict, max_meetings: int = 6) -> list[dict]:
    """Find earlier meetings that share entities with the current meeting.

    Returns a list of prior-meeting context items, sorted oldest first, each
    with date, body, shared entities (original casing), and a verbatim snippet
    from its artifact.
    """
    scored: dict[str, dict] = {}
    for category, values in entities.items():
        cat_map = index.get("entities", {}).get(category, {})
        for value in values:
            bucket = cat_map.get(value.casefold())
            if not bucket:
                continue
            for mkey, meta in bucket.items():
                if key_date(mkey) > current_date:
                    continue  # only meetings on or before this date
                entry = scored.setdefault(mkey, {
                    "date": meta.get("date", key_date(mkey)),
                    "body": meta.get("body", ""),
                    "shared": [],
                    "snippet": meta.get("snippet", ""),
                    "artifact": meta.get("artifact", ""),
                })
                disp = value  # original casing from the current meeting
                if disp not in entry["shared"]:
                    entry["shared"].append(disp)

    ranked = sorted(scored.items(), key=lambda kv: (kv[1]["date"], kv[0]))
    return [v for _, v in ranked[:max_meetings]]


def register_meeting(date: str, body: str, clip_id: str,
                     entities: dict[str, list[str]], snippet: str,
                     artifact_rel: str) -> None:
    """Record this meeting's entities so later meetings can reference it."""
    mkey = meeting_key(date, body)
    index = load_index()
    index.setdefault("meetings", {})[mkey] = {
        "date": date,
        "body": body,
        "clip_id": clip_id,
        "artifact": artifact_rel,
        "entities": entities,
    }
    for category, values in entities.items():
        cat_map = index.setdefault("entities", {}).setdefault(category, {})
        for value in values:
            ent = cat_map.setdefault(value.casefold(), {})
            ent[mkey] = {
                "date": date,
                "body": body,
                "snippet": snippet[:220],
                "artifact": artifact_rel,
                "value": value,
            }
    save_index(index)


def context_sources_for(current_date: str, index: dict, limit: int = 5,
                        artifacts_root: Path | None = None) -> list[dict]:
    """Return the prior meetings' studio packages as converted text sources.

    Each source is the preceding meeting's ``06_studio_package.md`` rendered
    into a clean, citation-ready block so a downstream NotebookLM notebook can
    actually ingest prior-meeting context as a source (not just a reference).

    Returns a list of source dicts:
      {
        "kind": "context_source",
        "title": "Prior meeting context — <date> <body>",
        "date": <date>,
        "body": <body>,
        "content": "<converted plain text>",
        "local": "<abs path to studio package>",
        "note": "Converted from prior meeting's studio package; included as a "
                "source so context is grounded in the actual prior record.",
      }
    Sorted oldest -> newest, limited to ``limit`` most relevant (shared-entity)
    meetings.
    """
    if artifacts_root is None:
        artifacts_root = ROOT / "notebooklm_controller" / "artifacts"
    meetings = index.get("meetings", {})
    # candidate prior meeting keys (date <= current_date), sorted newest first
    candidates = []
    for mkey, meta in meetings.items():
        if meta["date"] > current_date:
            continue
        candidates.append((mkey, meta))
    candidates.sort(key=lambda kv: kv[1]["date"], reverse=True)

    sources: list[dict] = []
    for mkey, meta in candidates[: max(limit * 3, 12)]:
        date = meta["date"]
        body = meta["body"]
        clip_id = meta.get("clip_id") or (mkey.split("|", 1)[1] if "|" in mkey else "")
        art_dir = artifacts_root / f"{date}-{body}-{clip_id}"
        pkg = art_dir / "06_studio_package.md"
        if not pkg.exists():
            continue
        try:
            content = pkg.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Convert to optimal plain-text source: strip markdown fences but keep
        # headings/quotes so the model can cite them; cap length per source.
        text = content.replace("```", "")
        if len(text) > 4000:
            text = text[:4000] + "\n…[truncated]…"
        sources.append({
            "kind": "context_source",
            "title": f"Prior meeting context — {date} {body}",
            "date": date,
            "body": body,
            "content": text,
            "local": str(pkg),
            "note": "Converted from prior meeting's studio package (optimal "
                    "plain-text source) and added as a source to this notebook "
                    "so context is grounded in the actual prior record.",
        })
        if len(sources) >= limit:
            break
    # oldest -> newest so the model reads history in chronological order
    sources.sort(key=lambda s: s["date"])
    return sources


def context_section(prior: list[dict]) -> str:
    """Render the HISTORICAL CONTEXT markdown section."""
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
