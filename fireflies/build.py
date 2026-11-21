"""Build the Fireflies-style ledger over every local meeting source.

Pipeline per meeting:
  1. agenda items from every source (agenda HTML > minutes > markdown > speech
     cues), merged across sources by title similarity; method tags preserved.
  2. actions/decisions (verbatim sentences, pattern-categorized), attached to
     items by source span where possible.
  3. extractive overview + keywords + entities (all method-tagged).
  4. outline chapters: Granicus deep links + ASR anchor alignment + minute
     paragraph spans.
  5. supporting docs attached (local packet files + Granicus URLs).

Then ``verify_ledger`` re-checks every stored quote is a verbatim substring of
a source text — the repo's "if it isn't quotable, it isn't asserted" rule,
enforced mechanically.
"""
from __future__ import annotations

import csv
import difflib
import json
from pathlib import Path

from . import (METHOD_ACTIONS, METHOD_ALIGNMENT, METHOD_ITEMS_AGENDA,
               METHOD_ITEMS_MINUTES, METHOD_ITEMS_SPEECH, METHOD_SUMMARY)
from .actions import attendance_quote, extract_actions
from .agenda import AgendaItem, extract_items
from .outline import build_outline
from .sources import Meeting, SourceText, load_meetings
from .summarize import entities, extractive_summary, keywords
from .textutil import clip_quote, normalize_ws, quote_body
from .topics import build_topics

PRIO = {"agenda_html": 0, "minutes": 1, "md": 2, "asr": 3}


def _title_key(t: str) -> str:
    return normalize_ws(t).lower().rstrip(".")[:200]


def _merge_items(per_source: dict) -> list:
    """Merge AgendaItem lists from several sources into one ordered list."""
    order = sorted(per_source, key=lambda k: PRIO.get(k, 9))
    merged: list = []          # list of {'item': AgendaItem, 'extras': [...], 'sources': set}
    for kind in order:
        for item in per_source[kind]:
            best, best_ratio = None, 0.0
            for entry in merged:
                if kind in entry["sources"]:
                    continue
                ratio = difflib.SequenceMatcher(
                    None, _title_key(item.title), _title_key(entry["item"].title)).ratio()
                if ratio > best_ratio:
                    best, best_ratio = entry, ratio
            if best is not None and best_ratio >= 0.72:
                primary = best["item"]
                if not primary.expected_action and item.expected_action:
                    primary.expected_action = item.expected_action
                if not primary.number and item.number:
                    primary.number = item.number
                if not primary.reading and item.reading:
                    primary.reading = item.reading
                if not primary.item_no and item.item_no:
                    primary.item_no = item.item_no
                for d in item.docs:
                    if d not in primary.docs:
                        primary.docs.append(d)
                best["extras"].append(item)
                best["sources"].add(kind)
            else:
                merged.append({"item": item, "extras": [], "sources": {kind}})
    out = []
    for i, entry in enumerate(merged, 1):
        it = entry["item"]
        it.item_id = f"itm-{i:02d}"
        quotes = [{"quote": it.quote, "locator": it.locator, "method": it.method}]
        for extra in entry["extras"]:
            quotes.append({"quote": extra.quote, "locator": extra.locator,
                           "method": extra.method})
        out.append({
            "item": it,
            "quotes": quotes,
            "sources": sorted(entry["sources"]),
        })
    return out


def _attach_actions(actions: list, merged_items: list) -> list:
    """Attach actions to items by source-span proximity; return ledger actions."""
    ledger_actions = []
    for act in actions:
        aid = ""
        for entry in merged_items:
            it = entry["item"]
            if it.locator.get("kind") != act.locator.get("kind"):
                continue
            if it.locator.get("kind") == "minutes" and it.locator.get("para"):
                # action para belongs to item when >= item para and < next item para
                pass  # handled below via ranges
        ledger_actions.append(act)
    # range attach: per (kind, ref), items sorted by para/char
    by_src = {}
    for entry in merged_items:
        it = entry["item"]
        key = (it.locator.get("kind"), it.locator.get("ref"))
        by_src.setdefault(key, []).append(it)
    for key, items in by_src.items():
        kind = key[0]
        pos_of = (lambda it: it.locator.get("para", 0)) if kind == "minutes" else \
                 (lambda it: it.locator.get("char", 0))
        items_sorted = sorted(items, key=pos_of)
        for act in ledger_actions:
            if (act.locator.get("kind"), act.locator.get("ref")) != key:
                continue
            apos = act.locator.get("para", act.locator.get("char", -1))
            if apos < 0:
                continue
            for i, it in enumerate(items_sorted):
                lo = pos_of(it)
                hi = pos_of(items_sorted[i + 1]) if i + 1 < len(items_sorted) else 10 ** 12
                if lo <= apos < hi:
                    act.item_id = it.item_id
                    break
    return ledger_actions


def analyze_meeting(mt: Meeting) -> dict:
    per_source = {}
    all_actions = []
    summary_src = None
    for st in sorted(mt.texts, key=lambda s: PRIO.get(s.kind, 9)):
        items = extract_items(st.text, st.kind, st.ref, st.segments)
        if items:
            per_source.setdefault(st.kind, []).extend(items)
        if st.kind in ("minutes", "md", "asr"):
            all_actions.extend(extract_actions(st.text, st.kind, st.ref, st.segments))
        if st.kind == "minutes" and (summary_src is None or st.words > summary_src.words):
            summary_src = st
    if summary_src is None:
        for st in mt.texts:
            if st.kind in ("asr", "md") and (summary_src is None or st.words > summary_src.words):
                summary_src = st

    merged_items = _merge_items(per_source)
    actions = _attach_actions(all_actions, merged_items)

    # dedupe actions across sources by normalized quote prefix
    seen = set()
    deduped = []
    for act in actions:
        key = (act.type, normalize_ws(act.quote).lower()[:150])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(act)

    segments = next((st.segments for st in mt.texts if st.kind == "asr" and st.segments), [])
    outline = build_outline([e["item"] for e in merged_items], segments or None)

    # docs: local packet files + urls from meetings.json + item-level docs
    docs = list(mt.docs)
    for e in merged_items:
        for d in e["item"].docs:
            if d not in docs:
                docs.append(d)

    overview = (extractive_summary(summary_src.text, 7, summary_src.kind)
                if summary_src else [])
    kws = keywords(summary_src.text) if summary_src else []
    # entities across ALL source texts, counts merged per (type, value)
    ent_map = {}
    for st in mt.texts:
        for e in entities(st.text):
            key = (e["type"], e["value"])
            d = ent_map.setdefault(key, {"type": e["type"], "value": e["value"],
                                         "count": 0, "example": None})
            d["count"] += e["count"]
            if d["example"] is None:
                d["example"] = e["example"]
    ents = sorted(ent_map.values(), key=lambda e: (-e["count"], e["type"], e["value"]))

    attendance = {}
    for st in mt.texts:
        attendance = attendance_quote(st.text, st.kind, st.ref)
        if attendance:
            break

    turns = None
    words_total = 0
    for st in mt.texts:
        words_total += st.words
        if st.kind == "asr":
            turns = (turns or 0) + st.text.count(">>") + 1

    return {
        "meeting_id": mt.meeting_id,
        "date": mt.date,
        "body": mt.body,
        "body_label": mt.body_label,
        "title": mt.title,
        "clip_ids": mt.clip_ids,
        "urls": mt.urls,
        "flags": sorted(set(mt.flags)),
        "sources": [{"kind": st.kind, "ref": st.ref, "sha256": st.sha256,
                     "words": st.words, "segments": len(st.segments)}
                    for st in mt.texts],
        "docs": docs,
        "stats": {
            "words": words_total,
            "texts": len(mt.texts),
            "segments": sum(len(st.segments) for st in mt.texts),
            "asr_turns_unlabeled": turns,
            "items": len(merged_items),
            "actions": len(deduped),
        },
        "attendance": attendance,
        "overview": {"method": METHOD_SUMMARY, "sentences": overview},
        "keywords": kws,
        "entities": ents,
        "outline": outline,
        "items": [{
            "item_id": e["item"].item_id,
            "title": e["item"].title,
            "title_guess": e["item"].title_guess,
            "kind": e["item"].kind,
            "reading": e["item"].reading,
            "number": e["item"].number,
            "item_no": e["item"].item_no,
            "expected_action": e["item"].expected_action,
            "sources": e["sources"],
            "quotes": e["quotes"],
            "docs": e["item"].docs,
        } for e in merged_items],
        "actions": [{
            "type": a.type,
            "quote": a.quote,
            "who": a.who,
            "locator": a.locator,
            "item_id": a.item_id,
            "method": METHOD_ACTIONS,
        } for a in deduped],
    }


# ------------------------------------------------------------------ build

def build_ledger(repo: Path, out_dir: Path, limit: int = None) -> dict:
    repo, out_dir = Path(repo), Path(out_dir)
    meetings = load_meetings(repo)
    if limit:
        meetings = meetings[:limit]
    ledger = [analyze_meeting(mt) for mt in meetings]

    (out_dir / "briefs").mkdir(parents=True, exist_ok=True)
    led = out_dir / "ledger"
    led.mkdir(parents=True, exist_ok=True)

    from .render import brief_markdown  # local import to avoid cycle
    for rec in ledger:
        (out_dir / "briefs" / f"{rec['meeting_id']}.md").write_text(
            brief_markdown(rec), encoding="utf-8")

    with (led / "meetings.jsonl").open("w", encoding="utf-8") as fh:
        for rec in ledger:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    with (led / "agenda_tracker.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["meeting_id", "date", "body", "item_id", "title", "title_guess",
                    "kind", "reading", "number", "expected_action",
                    "chapter_start", "chapter_end", "deep_link",
                    "docs", "outcome_quotes", "action_types"])
        outline_by_id = {o["item_id"]: o for rec in ledger for o in rec["outline"]}
        actions_by_item = {}
        for rec in ledger:
            for a in rec["actions"]:
                if a["item_id"]:
                    actions_by_item.setdefault(
                        (rec["meeting_id"], a["item_id"]), []).append(a)
        for rec in ledger:
            for it in rec["items"]:
                o = outline_by_id.get(it["item_id"], {})
                acts = actions_by_item.get((rec["meeting_id"], it["item_id"]), [])
                w.writerow([
                    rec["meeting_id"], rec["date"], rec["body"], it["item_id"],
                    it["title"][:200], it["title_guess"], it["kind"], it["reading"],
                    it["number"], it["expected_action"][:160],
                    o.get("start", ""), o.get("end", ""), o.get("deep_link", ""),
                    " | ".join(d.get("url") or d.get("ref", "") for d in it["docs"]),
                    " || ".join(a["quote"] for a in acts[:6]),
                    ",".join(sorted({a["type"] for a in acts})),
                ])

    topics = build_topics(ledger)
    (led / "topics.json").write_text(
        json.dumps(topics, ensure_ascii=False, indent=1), encoding="utf-8")

    stats = {
        "meetings": len(ledger),
        "dated": sum(1 for r in ledger if r["date"]),
        "bodies": sorted({r["body"] for r in ledger}),
        "date_min": min((r["date"] for r in ledger if r["date"]), default=""),
        "date_max": max((r["date"] for r in ledger if r["date"]), default=""),
        "items": sum(r["stats"]["items"] for r in ledger),
        "actions": sum(r["stats"]["actions"] for r in ledger),
        "words": sum(r["stats"]["words"] for r in ledger),
        "entities": len(topics["entities"]),
        "meetings_with_asr": sum(1 for r in ledger if r["stats"]["segments"]),
        "meetings_with_docs": sum(1 for r in ledger if r["docs"]),
    }
    from .render import index_markdown
    (led / "INDEX.md").write_text(index_markdown(ledger, stats), encoding="utf-8")
    return stats


# ----------------------------------------------------------------- verify

def verify_ledger(repo: Path, ledger_path: Path) -> dict:
    """Every stored quote must be a verbatim substring of one of the meeting's
    source texts (whitespace-insensitive). Returns {checked, bad:[...]}."""
    repo = Path(repo)
    text_cache = {}
    from .textutil import strip_tags, unescape_html

    def _blobs(raw: str, kind: str) -> list:
        """Accept-quote-if-verbatim-in-any-of: raw form and unescaped form
        (older minutes text carries HTML entities like &ndash; verbatim)."""
        out = [normalize_ws(raw), normalize_ws(unescape_html(raw))]
        if kind == "agenda_html":
            out.append(normalize_ws(strip_tags(unescape_html(raw))))
        return out

    def source_texts(rec):
        out = []
        for s in rec["sources"]:
            ref = s["ref"]
            if ref not in text_cache:
                if ref.startswith("drive-import/master_db:"):
                    # reload from the master DB by record id
                    rid = ref.split(":", 1)[1]
                    text_cache[ref] = _master_db_text(repo, rid)
                else:
                    p = repo / ref
                    text_cache[ref] = (p.read_text(encoding="utf-8", errors="replace")
                                       if p.exists() else "")
            out.extend(_blobs(text_cache[ref], s["kind"]))
        return out

    checked, bad = 0, []
    with Path(ledger_path).open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            blobs = source_texts(rec)
            quotes = []
            if rec.get("attendance", {}).get("quote"):
                quotes.append(("attendance", rec["attendance"]["quote"]))
            for s in rec.get("overview", {}).get("sentences", []):
                quotes.append(("overview", s["sentence"]))
            for e in rec.get("entities", []):
                if e.get("example", {}).get("quote"):
                    quotes.append(("entity", e["example"]["quote"]))
            for it in rec.get("items", []):
                for q in it.get("quotes", []):
                    quotes.append(("item", q["quote"]))
                if it.get("expected_action"):
                    quotes.append(("expected_action", it["expected_action"]))
            for a in rec.get("actions", []):
                quotes.append(("action", a["quote"]))
            for where, q in quotes:
                body = normalize_ws(quote_body(q))
                checked += 1
                if not body:
                    continue
                if not any(body in blob for blob in blobs):
                    bad.append({"meeting_id": rec["meeting_id"], "where": where,
                                "quote": body[:120]})
    return {"checked": checked, "bad": bad, "ok": not bad}


_MASTER_CACHE = {}


def _master_db_text(repo: Path, rid: str) -> str:
    import gzip
    gp = Path(repo) / "drive-import" / "master_meetings_database_linked.json.gz"
    if gp not in _MASTER_CACHE:
        with gzip.open(gp, "rt", encoding="utf-8") as fh:
            _MASTER_CACHE[gp] = {r.get("id"): "\n".join(
                t.get("text") or "" for t in r.get("turns", []))
                for r in json.load(fh)}
    return _MASTER_CACHE[gp].get(rid, "")
