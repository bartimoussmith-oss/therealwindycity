#!/usr/bin/env python3
"""Build the de-identified public arrest-record tier from captured arrest logs.

Policy this implements (owner directive, 2026-10-17):

  * PUBLIC  - arrest records WITHOUT names: date window, verbatim charges,
              coarse research categories, counts, provenance.
  * SEALED  - names, released only on request, for public-safety and
              non-discriminatory research purposes only.

Read the honesty note in data/arrests/README.md before relying on this: the
underlying capcity.news article is itself public and already names people, and
this repo already holds that raw capture in data/snapshots/ plus its text in
data/engine.db. This tool controls what THIS PROJECT publishes and surfaces.
It does not, and cannot, make the names secret. Run --report-leaks to see
exactly where names currently sit in the committed tree.

Usage
-----
    python3 tools/build_arrest_records.py                 # build + self-audit
    python3 tools/build_arrest_records.py --audit         # audit only
    python3 tools/build_arrest_records.py --report-leaks  # where names already are
    python3 tools/build_arrest_records.py --source FILE   # add a capture not in
                                                          # data/snapshots/

Exit codes: 0 ok · 2 bad args/input · 3 audit FAILED (a name leaked) · 4 write error
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAP_DIR = ROOT / "data" / "snapshots"
OUT_DIR = ROOT / "data" / "arrests"
DB_PATH = ROOT / "data" / "engine.db"

# ---------------------------------------------------------------- source shape

# A section header is a bare date range: 8/28/26-8/31/26
DATE_RANGE = re.compile(
    r"^(\d{1,2})/(\d{1,2})/(\d{2,4})\s*[\u2013\u2014-]\s*(\d{1,2})/(\d{1,2})/(\d{2,4})$"
)
# An entry is: Name <en-dash> charge, charge, charge
ENTRY = re.compile(r"^(?P<name>.+?)\s*[\u2013\u2014]\s*(?P<charges>.+)$")
# The article line that opens the log body
BODY_START = re.compile(r"compiled arrest logs", re.I)
# Lines that end the body
BODY_END = re.compile(r"^(Related|More by|Popular|Search for:|Search|Tags?)$", re.I)

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
PUBTIME_RE = re.compile(
    r'<meta property="article:published_time" content="([^"]+)"'
)
CANONICAL_RE = re.compile(r'<link rel="canonical" href="([^"]+)"')

ARREST_URL_HINT = re.compile(r"arrest-report", re.I)

# ------------------------------------------------------------ charge categories
# Coarse buckets for research aggregation only.
#
# RULE: no category encodes a protected characteristic or a proxy for one.
# Nothing here infers race, ethnicity, national origin, sex, gender, age or
# immigration status, and no category exists to let a consumer filter people by
# any of those. Verbatim charge text is ALWAYS retained alongside the category,
# so categorisation can never hide or distort what the record actually says.
# Charges that touch registry compliance or immigration holds are folded into
# the neutral warrant/court bucket rather than given a targeting-able label of
# their own.
CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("impaired_driving", (
        "dui", "pedestrian under the influence", "open container",
    )),
    ("drug_possession", (
        "methamphetamine", "amphetamine", "marijuana", "controlled substance",
        "possession/use of drugs", "drug court hold",
    )),
    ("assault_violence", (
        "assault", "domestic battery", "domestic violence", "strangulation",
        "reckless endangerment", "fighting/riotous", "child endangerment",
    )),
    ("warrant_court", (
        "warrant", "court order", "failure to appear", "failure to comply",
        "probation", "parole", "ncic", "failure to register", "ice detainer",
        "protection order", "stalking", "failure to pay",
    )),
    ("property_theft", (
        "theft", "destruction of property", "criminal trespass", "forgery",
    )),
    ("officer_obstruction", (
        "interference with a peace officer", "resisting arrest",
        "fleeing/eluding", "interfering/obstructing",
    )),
    ("traffic", (
        "speeding", "lane use", "suspended driver", "duty upon colliding",
        "duty to stop", "proof of lia",
    )),
    ("weapons", ("concealed weapon",)),
    ("public_order", (
        "public intoxication", "disturbing the peace", "urinating in public",
        "minor in possession", "possession of tobacco", "breach of peace",
    )),
]

# Caveats lifted verbatim from the source article. These are load-bearing for
# any non-discriminatory research use: the exclusions are SYSTEMATIC, so the
# dataset must never be read as a complete picture of who was arrested.
CAVEATS = [
    "The arrest log is not a comprehensive document and may not represent all "
    "of the arrests made in a given time period.",
    "The log does not contain information for juvenile offenders, suspects "
    "recommended for charges of a sexual nature, or information for persons "
    "arrested in Laramie County who have bonded or bailed out of the detention "
    "center before law enforcement releases the information.",
    "Arrest is not a finding of guilt. Every entry is a recommended charge at "
    "the time of booking; cases may be dropped, reduced, or dismissed.",
    "Names are withheld from this tier by owner policy. No demographic field "
    "is derived, inferred, or published: the categories above are charge "
    "groupings only and encode no protected characteristic or proxy for one.",
]


def categorise(charges: list[str]) -> list[str]:
    """Map verbatim charges onto coarse research categories."""
    joined = " | ".join(charges).lower()
    hits = [name for name, keys in CATEGORIES if any(k in joined for k in keys)]
    return hits or ["other"]


# --------------------------------------------------------------------- parsing

def strip_to_text(raw: str) -> list[str]:
    """HTML -> non-empty visible lines, scripts/styles/nav removed."""
    body = re.sub(
        r"<script.*?</script>|<style.*?</style>|<nav.*?</nav>"
        r"|<header.*?</header>|<footer.*?</footer>",
        "", raw, flags=re.S | re.I,
    )
    text = html.unescape(re.sub(r"<[^>]+>", "\n", body))
    return [ln.strip() for ln in text.split("\n") if ln.strip()]


def find_arrest_captures(extra: list[Path]) -> list[Path]:
    """Every captured arrest-report page we know about, deterministically sorted."""
    found: list[Path] = []
    if SNAP_DIR.is_dir():
        for p in sorted(SNAP_DIR.iterdir()):
            if not p.is_file():
                continue
            if ARREST_URL_HINT.search(p.name):
                found.append(p)
    for p in extra:
        if p.is_file() and p not in found:
            found.append(p)
    return found


def parse_capture(path: Path) -> dict:
    """One capture -> report metadata + a list of (date_window, name, charges)."""
    raw = path.read_text(errors="replace")
    is_html = raw.lstrip()[:200].lower().startswith("<!doctype") or "<html" in raw[:2000].lower()

    if is_html:
        lines = strip_to_text(raw)
        tm = TITLE_RE.search(raw)
        title = html.unescape(tm.group(1)).strip() if tm else path.name
        pm = PUBTIME_RE.search(raw)
        published = pm.group(1) if pm else None
        cm = CANONICAL_RE.search(raw)
        url = cm.group(1) if cm else None
    else:
        # A plain-text capture (e.g. a saved page-source .txt): no tags to strip.
        lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
        title = path.name
        published = None
        url = None

    # locate the body
    start = next((i for i, ln in enumerate(lines) if BODY_START.search(ln)), None)
    if start is None:
        raise ValueError(f"{path.name}: no 'compiled arrest logs' lede - not an arrest log?")

    entries: list[dict] = []
    window = None
    multi_dash = 0
    for ln in lines[start + 1:]:
        if BODY_END.match(ln):
            break
        if DATE_RANGE.match(ln):
            window = ln
            continue
        m = ENTRY.match(ln)
        if not m:
            continue
        name, charges_raw = m.group("name").strip(), m.group("charges").strip()
        if len(name) < 3 or len(name) > 80:
            continue
        if "\u2013" in charges_raw or "\u2014" in charges_raw:
            multi_dash += 1  # a charge itself carries a dash - flag, do not guess
        charges = [c.strip() for c in charges_raw.split(",") if c.strip()]
        entries.append({
            "window": window,
            "name": name,
            "charges": charges,
        })

    if not entries:
        raise ValueError(f"{path.name}: parsed 0 entries")

    return {
        "path": path,
        "title": title,
        "published": published,
        "url": url,
        "entries": entries,
        "multi_dash_warnings": multi_dash,
        "raw_sha256": hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest(),
    }


# ------------------------------------------------------------------ de-identify

def build(source: Path, extra: list[Path]) -> tuple[list[dict], list[dict]]:
    """-> (public_records, sealed_name_key). Opaque IDs, not name hashes."""
    public: list[dict] = []
    sealed: list[dict] = []

    for cap in find_arrest_captures(extra):
        parsed = parse_capture(cap)
        # Report slug from the published date when we have it, else the filename.
        slug_src = (parsed["published"] or "")[:10].replace("-", "") or \
            hashlib.sha256(str(cap).encode()).hexdigest()[:8]
        for n, e in enumerate(parsed["entries"], start=1):
            # Opaque, sequential, NOT derived from the name: nothing to brute-force.
            rid = f"LC-{slug_src}-{n:03d}"
            cats = categorise(e["charges"])
            public.append({
                "record_id": rid,
                "report": parsed["title"],
                "report_published": parsed["published"],
                "source_url": parsed["url"],
                "source_capture": cap.name,
                "source_sha256": parsed["raw_sha256"],
                "arrest_window": e["window"],
                "charges": e["charges"],
                "charge_count": len(e["charges"]),
                "categories": cats,
                "name": None,          # withheld by policy
                "name_withheld": True,
            })
            sealed.append({
                "record_id": rid,
                "name": e["name"],
                "arrest_window": e["window"],
                "source_capture": cap.name,
            })
    return public, sealed


# ------------------------------------------------------------------ name audit

def audit(public_records: list[dict], sealed: list[dict], out_files: list[Path]) -> list[str]:
    """Prove no withheld name appears in any public artefact. Returns failures."""
    names = {s["name"] for s in sealed}
    # Every token of every name: given, middle, surname, suffix-stripped.
    tokens: set[str] = set()
    for nm in names:
        for tok in re.split(r"[\s.]+", nm):
            tok = tok.strip(".,'")
            if len(tok) >= 4 and not re.fullmatch(r"(?i)jr|sr|ii|iii|iv|st|mrs|mr|ms", tok):
                tokens.add(tok)

    failures: list[str] = []
    for f in out_files:
        if not f.exists():
            continue
        text = f.read_text(errors="replace")
        for nm in sorted(names):
            if nm in text:
                failures.append(f"{f.relative_to(ROOT)}: contains full name {nm!r}")
        for tok in sorted(tokens):
            # Word-boundary match: catches a withheld token standing alone in
            # prose, but not as a substring of an unrelated longer word.
            # No example token is written here on purpose - this file is
            # committed and public, and a surname used as an illustration can
            # collide with a real one in the data and trip the auditor.
            if re.search(rf"\b{re.escape(tok)}\b", text):
                failures.append(f"{f.relative_to(ROOT)}: contains name token {tok!r}")
    return failures


def report_leaks(names: set[str]) -> None:
    """Show where withheld names ALREADY sit in the committed tree."""
    print("\n=== where names already are (committed, public) ===")

    snaps = sorted(SNAP_DIR.glob("*arrest-report*")) if SNAP_DIR.is_dir() else []
    for p in snaps:
        text = p.read_text(errors="replace")
        hit = sum(1 for n in names if n in text)
        flag = "TRACKED by git" if _tracked(p) else "untracked"
        print(f"  {p.relative_to(ROOT)}  [{flag}]  {hit}/{len(names)} names present")

    if DB_PATH.exists():
        try:
            con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            hit = 0
            for n in names:
                try:
                    row = con.execute(
                        "select count(*) from text_index where text_index match ?",
                        (n.split()[0],),
                    ).fetchone()
                    hit += 1 if row and row[0] else 0
                except sqlite3.Error:
                    pass
            tracked = "TRACKED by git" if _tracked(DB_PATH) else "untracked"
            print(f"  data/engine.db  [{tracked}]  FTS5 text_index matches "
                  f"{hit}/{len(names)} given names -> full text is searchable")
            con.close()
        except sqlite3.Error as e:
            print(f"  data/engine.db  probe failed: {e}")

    print("\n  => Redacting a derived CSV is NOT redaction while these stay public.")
    print("     Removing them from the current tree also does not remove them from")
    print("     git history, and repo protocol forbids rewriting the remote.")
    print("     Owner decision required - see data/arrests/README.md §Honesty.\n")


def _tracked(p: Path) -> bool:
    import subprocess
    r = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(p.relative_to(ROOT))],
        cwd=ROOT, capture_output=True, text=True,
    )
    return r.returncode == 0


# ----------------------------------------------------------------------- output

CSV_FIELDS = [
    "record_id", "report_published", "arrest_window", "charge_count",
    "categories", "charges", "source_url", "source_capture",
]


def write_outputs(public: list[dict], sealed: list[dict], source_captures: list[Path]) -> list[Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # ---- public JSON (the research artefact)
    payload = {
        "tier": "public-deidentified",
        "policy": "Arrest records published WITHOUT names. Names are released "
                  "only on request, for public-safety and non-discriminatory "
                  "research purposes only.",
        "generated_by": "tools/build_arrest_records.py",
        "record_count": len(public),
        "report_count": len(source_captures),
        "reports": [
            {"capture": p.name, "sha256": hashlib.sha256(
                p.read_bytes()).hexdigest()} for p in source_captures
        ],
        "caveats": CAVEATS,
        "category_rule": "Categories are charge groupings only. No category "
                         "encodes a protected characteristic or a proxy for one, "
                         "and no demographic field is derived or inferred.",
        "records": public,
    }
    jp = OUT_DIR / "records.json"
    jp.write_text(json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    written.append(jp)

    # ---- public CSV (spreadsheet / notebook friendly)
    cp = OUT_DIR / "records.csv"
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS, extrasaction="ignore",
                       lineterminator="\n")
    w.writeheader()
    for r in public:
        row = dict(r)
        row["charges"] = " | ".join(r["charges"])
        row["categories"] = " | ".join(r["categories"])
        w.writerow(row)
    cp.write_text(buf.getvalue())
    written.append(cp)

    # ---- SEALED name key: never committed, 0600, gitignored
    kp = OUT_DIR / "name_key.json"
    kp.write_text(json.dumps({
        "tier": "SEALED - DO NOT COMMIT, DO NOT PUBLISH",
        "policy": "Released only on request for public-safety and "
                  "non-discriminatory research. See .github/ISSUE_TEMPLATE/"
                  "arrest-name-request.md.",
        "count": len(sealed),
        "records": sealed,
    }, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    os.chmod(kp, 0o600)
    written.append(kp)

    return written


# ------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", action="append", default=[], type=Path,
                    help="extra capture to include (e.g. a Drive export)")
    ap.add_argument("--audit", action="store_true",
                    help="audit existing data/arrests/ output and exit")
    ap.add_argument("--report-leaks", action="store_true",
                    help="show where withheld names already sit in the repo")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    for p in args.source:
        if not p.is_file():
            print(f"error: --source not a file: {p}", file=sys.stderr)
            return 2

    if args.audit:
        if not (OUT_DIR / "records.json").exists():
            print("error: data/arrests/records.json does not exist - build first",
                  file=sys.stderr)
            return 2
        payload = json.loads((OUT_DIR / "records.json").read_text())
        sealed = json.loads((OUT_DIR / "name_key.json").read_text())["records"] \
            if (OUT_DIR / "name_key.json").exists() else []
        if not sealed:
            print("error: no sealed name key to audit against", file=sys.stderr)
            return 2
        files = [OUT_DIR / n for n in ("records.json", "records.csv", "README.md")]
        fails = audit(payload["records"], sealed, files)
        if fails:
            print(f"AUDIT FAILED - {len(fails)} leak(s):")
            for f in fails[:20]:
                print("  " + f)
            return 3
        print(f"AUDIT PASS - {len(payload['records'])} public records, "
              f"{len(sealed)} sealed names, 0 name tokens in public output.")
        return 0

    caps = find_arrest_captures(args.source)
    if not caps:
        print("error: no arrest-report captures found in data/snapshots/ "
              "and no --source given", file=sys.stderr)
        return 2

    try:
        public, sealed = build(None, args.source)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    try:
        written = write_outputs(public, sealed, caps)
    except OSError as e:
        print(f"error: could not write output: {e}", file=sys.stderr)
        return 4

    names = {s["name"] for s in sealed}
    files = [OUT_DIR / n for n in ("records.json", "records.csv", "README.md")]
    fails = audit(public, sealed, files)

    if not args.quiet:
        print(f"parsed {len(caps)} capture(s) -> {len(public)} de-identified records")
        for c in caps:
            print(f"  - {c.relative_to(ROOT)}")
        windows = sorted({r["arrest_window"] for r in public if r["arrest_window"]})
        print(f"arrest windows: {', '.join(windows)}")
        print(f"public tier : {written[0].relative_to(ROOT)}")
        print(f"              {written[1].relative_to(ROOT)}")
        print(f"sealed tier : {written[2].relative_to(ROOT)}  (mode 600, gitignored)")
        cats: dict[str, int] = {}
        for r in public:
            for c in r["categories"]:
                cats[c] = cats.get(c, 0) + 1
        print("categories  : " + ", ".join(f"{k}={v}" for k, v in sorted(
            cats.items(), key=lambda kv: -kv[1])))

    if args.report_leaks:
        report_leaks(names)

    if fails:
        print(f"\nAUDIT FAILED - {len(fails)} leak(s):", file=sys.stderr)
        for f in fails[:20]:
            print("  " + f, file=sys.stderr)
        return 3

    print(f"\nAUDIT PASS - 0 of {len(names)} names and 0 name tokens appear in "
          f"the public tier ({len(public)} records).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
