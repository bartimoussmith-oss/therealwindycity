#!/usr/bin/env python3
"""build_glossary.py — canonical entity glossary from minutes + agendas + docs.

The transcript cleaner trusts THIS file for spelling. Sources, in priority order:
  1. rag/glossary_manual.json (curated; always wins — edit this for fixes)
  2. Minutes roll calls ("Present were: MAYOR – X COUNCIL MEMBERS – ...")
  3. Ordinance/Resolution numbers + titles from minutes/agendas/supporting docs
  4. Frequent capitalized phrases from doc text (candidates, need review)

Usage (repo root):
  python rag/build_glossary.py --clips 1124 1103 1093 1071   # sample
  python rag/build_glossary.py --all                          # full corpus (slow)
  python rag/build_glossary.py --all --docs-dir documents     # + youtube-archive docs

Reads minutes from pipeline/corpus/{clip}_*.txt and docs from pipeline/docs/
(or --docs-dir in youtube-archive layout documents/clipNNN_*/).
Writes rag/glossary.json (+ merges rag/glossary_manual.json).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

from text_extract import (MINUTES_HDR, ORDINANCE, RESOLUTION, ROLLCALL,
                          cached_text)

ROOT = Path(__file__).resolve().parent.parent
RAG = ROOT / "rag"
TEXT_CACHE = RAG / "text_cache"

TITLE_STRIP = re.compile(r"^(mayor|dr\.?|mr\.?|ms\.?|mrs\.?)\s+", re.I)
PAREN_STRIP = re.compile(r"\s*\([^)]*\)\s*")
CAP_PHRASE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b")
STOP_PHRASES = {"City Council", "City Of Cheyenne", "Governing Body", "Consent Agenda",
                "Public Hearing", "City Clerk", "Mayor Collins", "Council Chambers"}


ROLE_WORDS = {"city", "clerk", "mayor", "also", "present", "absent", "council",
              "members", "member", "the", "and", "office", "of", "recited"}


def people_from_minutes(text: str) -> list[str]:
    people: list[str] = []
    m = ROLLCALL.search(text)
    if not m:
        return people
    for group in (m.group("present"), m.group("absent"), m.group("also")):
        if not group:
            continue
        blob = re.sub(r"\s+", " ", group)
        blob = re.sub(r"(MAYOR|COUNCIL MEMBERS|MEMBERS)\s*[\u2013\u2014:\-]\s*",
                      "", blob, flags=re.I)
        for chunk in re.split(r"[;.]|\band\b", blob):
            for part in chunk.split(","):
                part = PAREN_STRIP.sub(" ", part).strip()
                part = TITLE_STRIP.sub("", part).strip(" .")
                toks = part.split()
                if not (2 <= len(toks) <= 3):
                    continue
                if any(t.lower().strip(".") in ROLE_WORDS for t in toks):
                    continue
                if toks[-1].lower().strip(".") in {"dr", "mr", "ms", "mrs"}:
                    continue  # dangling title stub ("... Collins Dr")
                if not all(re.match(r"^[A-Z][a-z'.-]+$", t) for t in toks):
                    continue
                people.append(" ".join(toks))
    return people


def seed_manual() -> dict:
    fp = RAG / "glossary_manual.json"
    if fp.exists():
        return json.loads(fp.read_text(encoding="utf-8"))
    return {"people": [], "places": [], "terms": [], "ordinances": [], "confusions": []}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", nargs="*", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--docs-dir", default="", help="extra docs root (youtube-archive layout)")
    ap.add_argument("--max-pdf-mb", type=float, default=0,
                    help="skip PDFs larger than this (0 = no cap). Sample runs: 8")
    ap.add_argument("--min-phrase-count", type=int, default=4)
    args = ap.parse_args()

    corpus = sorted((ROOT / "pipeline" / "corpus").glob("*.txt"))
    if args.clips:
        want = set(args.clips)
        corpus = [p for p in corpus if p.stem.split("_")[0] in want]
    elif not args.all:
        ap.error("pass --clips ... or --all")

    people: Counter = Counter()
    ordinances: dict[str, str] = {}
    resolutions: dict[str, str] = {}
    phrases: Counter = Counter()
    files_read = 0

    for minutes_fp in corpus:
        text = minutes_fp.read_text(encoding="utf-8", errors="replace")
        hdr = MINUTES_HDR.search(text[:600])
        clip = hdr.group("clip") if hdr else minutes_fp.stem.split("_")[0]
        for p in people_from_minutes(text):
            people[p] += 1
        for num in ORDINANCE.findall(text):
            ordinances.setdefault(f"Ordinance {num}", f"clip {clip}")
        for num in RESOLUTION.findall(text):
            resolutions.setdefault(f"Resolution {num}", f"clip {clip}")
        files_read += 1

    # supporting-doc text: repo layout pipeline/docs/<clip>/ + optional extra root
    doc_roots = [ROOT / "pipeline" / "docs"]
    if args.docs_dir:
        doc_roots.append(Path(args.docs_dir))
    for doc_root in doc_roots:
        if not doc_root.is_dir():
            continue
        for fp in sorted(doc_root.rglob("*")):
            if not fp.is_file() or fp.suffix.lower() not in (".pdf", ".html", ".htm", ".txt", ""):
                continue
            if fp.stat().st_size > 60_000_000:
                continue
            if args.max_pdf_mb and fp.stat().st_size > args.max_pdf_mb * 1e6:
                continue
            try:
                text = cached_text(fp, TEXT_CACHE)
            except Exception:
                continue
            for num in ORDINANCE.findall(text):
                ordinances.setdefault(f"Ordinance {num}", fp.name)
            for num in RESOLUTION.findall(text):
                resolutions.setdefault(f"Resolution {num}", fp.name)
            for ph in CAP_PHRASE.findall(text):
                if ph not in STOP_PHRASES and len(ph) > 6:
                    phrases[ph] += 1
            files_read += 1

    manual = seed_manual()
    glossary = {
        "people": sorted(set(manual.get("people", [])) | {p for p, c in people.items() if c >= 1}),
        "ordinances": sorted(set(manual.get("ordinances", [])) | set(ordinances)),
        "resolutions": sorted(set(resolutions)),
        "places": sorted(set(manual.get("places", []))),
        "terms": sorted(set(manual.get("terms", []))),
        "people_titles": manual.get("people_titles", {}),
        "phrase_candidates": [{"phrase": p, "count": c}
                              for p, c in phrases.most_common(400)
                              if c >= args.min_phrase_count],
        "confusions": manual.get("confusions", []),
        "regex_confusions": manual.get("regex_confusions", []),
        "meta": {"files_read": files_read,
                 "note": "Move vetted phrase_candidates into places/terms (or glossary_manual.json)."},
    }
    out = RAG / "glossary.json"
    out.write_text(json.dumps(glossary, indent=1), encoding="utf-8")
    print(f"minutes+docs read: {files_read}")
    print(f"people: {len(glossary['people'])}  ordinances: {len(glossary['ordinances'])}  "
          f"resolutions: {len(glossary['resolutions'])}  candidates: {len(glossary['phrase_candidates'])}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
