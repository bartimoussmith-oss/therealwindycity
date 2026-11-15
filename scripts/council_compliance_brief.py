#!/usr/bin/env python3
"""Cheyenne City Council public-record compliance brief (offline, local records only).

Scope gate (enforced in code, not by convention):

* Queries must match an allowed civic scope: City Council meetings, agendas,
  minutes, ordinances, resolutions, Laramie County ArcGIS / parcel telemetry,
  government contracts, or Wyoming Public Records Act references
  (W.S. 16-4-201 et seq.).
* Queries matching a profiling pattern (personal names, addresses, phone
  numbers, family, personal-contact terms) are refused before any lookup.
* Only documents already collected by the engine are searched. No network
  request is made. Granicus (cheyenne.granicus.com) is never fetched because its
  robots.txt disallows automated access (see LEGAL.md and config/sources.json).

Usage:
    python3 scripts/council_compliance_brief.py "Ordinance 4687" --db data/engine.db
    python3 scripts/council_compliance_brief.py "Laramie County parcel" --out brief.md
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Civic scope: at least one term must appear in the query.
ALLOWED_SCOPE = re.compile(
    r"\b(city council|council|meeting|agenda|minutes|ordinance|resolution|"
    r"laramie county|arcgis|parcel|contract|procurement|award|"
    r"public records|records act|w\.?\s?s\.?\s*16-4-2\d\d|"
    r"16-4-20\d|cheyenne|moratorium|annexation|referendum)\b",
    re.IGNORECASE,
)

# Profiling patterns: refused regardless of scope terms.
DENIED_PATTERNS = [
    re.compile(r"\b(home|personal|private|family|spouse|wife|husband|son|daughter)\b", re.I),
    re.compile(r"\b(address|phone|email|e-mail|ssn|social security|dob|date of birth)\b", re.I),
    re.compile(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b"),           # phone number
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),                 # email address
    # Two or more consecutive capitalised words that are not known civic phrases
    # are treated as a possible personal name and refused.
    re.compile(r"\b(?!City\b|County\b|Council\b|Laramie\b|Cheyenne\b|Wyoming\b|Ordinance\b|"
               r"Resolution\b|Public\b|Records\b|Act\b|Project\b|Board\b|Commission\b|"
               r"Department\b|Planning\b|Zoning\b|Water\b|Utilities\b|Finance\b|"
               r"Annexation\b|Moratorium\b|Referendum\b|Agenda\b|Minutes\b)"
               r"[A-Z][a-z]+\s+[A-Za-z][a-z]+\b"),
]


# Sentence terminators, excluding common abbreviations such as "No." and "Mr."
SENT_END = re.compile(r"(?<!\bNo)(?<!\bMr)(?<!\bMs)(?<!\bDr)(?<!\bSt)[.!?](?=\s+[A-Z0-9\"']|$)")


class QueryRefused(ValueError):
    """Raised when a query falls outside the permitted public-record scope."""


def check_scope(query: str) -> str:
    q = " ".join(query.split())
    if not q or len(q) > 200:
        raise QueryRefused("query must be 1-200 characters")
    for pat in DENIED_PATTERNS:
        m = pat.search(q)
        if m:
            raise QueryRefused(f"refused: possible individual-profiling term {m.group(0)!r}")
    if not ALLOWED_SCOPE.search(q):
        raise QueryRefused("refused: query is outside permitted public-record scope")
    return q


@dataclass
class Hit:
    doc_id: int
    source: str
    url: str
    title: str
    published_at: str | None
    fetched_at: str | None
    sha256: str | None
    status: str | None
    quote: str | None = None


@dataclass
class Brief:
    query: str
    generated_at: str
    hits: list[Hit] = field(default_factory=list)
    method: str = "offline-sqlite-like-search (no LLM, verbatim quotes only)"


def search(db_path: Path, query: str, limit: int = 25) -> list[Hit]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    terms = [t for t in re.findall(r"[A-Za-z0-9-]+", query) if len(t) > 2]
    if not terms:
        terms = [query]
    clauses = " AND ".join(["(title LIKE ? OR url LIKE ?)"] * len(terms))
    params: list[str] = []
    for t in terms:
        params += [f"%{t}%", f"%{t}%"]
    rows = con.execute(
        f"""SELECT id, source, url, title, published_at, last_checked, local_path, sha256, status
            FROM documents
            WHERE {clauses} AND url NOT LIKE '%granicus.com%'
            ORDER BY COALESCE(published_at, first_seen) DESC LIMIT ?""",
        (*params, limit),
    ).fetchall()
    hits: list[Hit] = []
    for r in rows:
        quote = find_quote(r["local_path"], terms)
        hits.append(Hit(r["id"], r["source"], r["url"], r["title"] or "",
                        r["published_at"], r["last_checked"], r["sha256"], r["status"], quote))
    con.close()
    return hits


def find_quote(local_path: str | None, terms: list[str]) -> str | None:
    """Return one verbatim sentence containing the first matching term, if the text exists."""
    if not local_path:
        return None
    p = Path(local_path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8", errors="replace")
    for t in terms:
        m = re.search(re.escape(t), text, re.IGNORECASE)
        if m:
            start = 0
            for b in SENT_END.finditer(text, 0, m.start()):
                start = b.end()
            end_m = SENT_END.search(text, m.end())
            end = end_m.end() if end_m else min(len(text), m.end() + 200)
            return " ".join(text[start:end].split())[:400]
    return None


def render(brief: Brief) -> str:
    out = [
        "# Public-record compliance brief",
        "",
        f"- Query: `{brief.query}`",
        f"- Generated (UTC): {brief.generated_at}",
        f"- Method: {brief.method}",
        f"- Scope: Cheyenne City Council records, Laramie County public records, "
        "government contracts, Wyoming PRA references (W.S. 16-4-201 et seq.).",
        "- Excluded by design: personal-name or individual-profiling queries; "
        "Granicus (robots-disallowed); any non-public data.",
        "",
        f"## Results ({len(brief.hits)})",
        "",
    ]
    if not brief.hits:
        out.append("No matching public records in the local vault. Nothing has been inferred.")
    for i, h in enumerate(brief.hits, 1):
        out += [
            f"### {i}. {h.title or '(untitled)'}",
            f"- Source: {h.source}",
            f"- URL: {h.url}",
            f"- Published: {h.published_at or 'unknown'}",
            f"- Fetched/checked: {h.fetched_at or 'unknown'}",
            f"- SHA-256: {h.sha256 or 'unknown'}",
            f"- Status: {h.status or 'unknown'}",
        ]
        if h.quote:
            out.append(f"- Verbatim: \"{h.quote}\"")
        else:
            out.append("- Verbatim: not available locally; listed as unverified text.")
        out.append("")
    return "\n".join(out)


def build_brief(db_path: Path, query: str) -> Brief:
    q = check_scope(query)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return Brief(query=q, generated_at=now, hits=search(db_path, q))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query")
    ap.add_argument("--db", default=str(ROOT / "data" / "engine.db"))
    ap.add_argument("--out", help="write the brief to this path instead of stdout")
    args = ap.parse_args(argv)
    try:
        brief = build_brief(Path(args.db), args.query)
    except QueryRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    text = render(brief)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out} ({len(brief.hits)} hits)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
