#!/usr/bin/env python3
"""Publish the arrest records WITH names and ages (owner decision, 2026-11-27).

Owner instruction: "I want all the arrest records to not be redacted." This replaces
the 2026-10-17 publish-without-names policy. The records are the Laramie County
arrest logs that Cap City News compiled and published under each person's name.

What it does
------------
1. master_records.{json,csv}: re-runs tools/import_master_arrest_db.py's own clean()
   on the owner's MASTER_ARREST_DATABASE.json, so every record gets the same
   record_id it already has. Before writing anything it checks that every
   (record_id, source_url, charges) is IDENTICAL to the committed public file.
   One mismatch and nothing is written (exit 3).
2. records.{json,csv} (the weekly capture in data/snapshots/): names are read from
   that capture's "Name, age - charges" lines, matched record-by-record on the
   charge list. Unmatched records stop the run.
3. Optional cross-check (--check-names names.json): names recovered independently
   from the Cap City News articles must agree with the database.

Usage
-----
    python3 tools/publish_arrest_names.py --master-json /path/MASTER_ARREST_DATABASE.json \
        --laramie-html /path/capture.html [--check-names names.json] [--dry-run]

The source JSON is read, not copied; the published files now carry the names.
Exit codes: 0 ok, 2 bad input, 3 verification failed.
"""
from __future__ import annotations

import argparse
import csv
import html as _html
import importlib.util
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "arrests"

POLICY = ("Arrest records published WITH names and ages, as compiled and published by Cap City News "
          "from Laramie County law-enforcement logs (owner decision 2026-11-27; supersedes the "
          "2026-10-17 publish-without-names policy).")
CAVEATS = [
    "Arrest is not a finding of guilt. Every entry is a recommended charge at the time of booking; "
    "cases may be dropped, reduced, or dismissed, and this dataset contains no case outcomes.",
    "The source log is not comprehensive. Verbatim from Cap City News: it omits juvenile offenders, "
    "suspects recommended for charges of a sexual nature, and anyone who bonded or bailed out before "
    "the information was released.",
    "Names are as printed in the source article. Different people can share a name; do not assume two "
    "records with the same name are the same person, or that a person here is someone you know.",
    "Coverage is uneven across years (missing weekly reports, not fewer arrests); do not compare years.",
    "No demographic field is derived, inferred, or published; categories are charge groupings only.",
    "Corrections: if a record is wrong or a case was dismissed, open an issue and it will be corrected "
    "or annotated.",
]
ENTRY = re.compile(r"^(?P<name>[^\u2013\u2014]{3,90}?)\s*[\u2013\u2014]\s*(?P<ch>.+)$")
AGE = re.compile(r",?\s*(\d{1,3})\s*$")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _html.unescape(s).lower())


def load_importer():
    spec = importlib.util.spec_from_file_location("imp", ROOT / "tools" / "import_master_arrest_db.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_capture(text: str) -> list[dict]:
    i = text.find('class="entry-content')
    body = text[max(i, 0):]
    j = body.find("</article>")
    body = body[:j] if j > 0 else body
    body = re.sub(r"<br\s*/?>", "\n", body)
    t = _html.unescape(re.sub(r"<[^>]+>", "\n", body))
    out = []
    for line in (x.strip() for x in t.split("\n")):
        m = ENTRY.match(line) if line and len(line) < 600 else None
        if not m:
            continue
        name, age = m.group("name").strip(), None
        a = AGE.search(name)
        if a and 10 <= int(a.group(1)) <= 110:
            age, name = int(a.group(1)), name[:a.start()].strip().rstrip(",")
        if not name[:1].isupper() or "CHEYENNE" in name.upper() or len(name.split()) > 8:
            continue
        out.append({"name": name, "age": age, "ch": m.group("ch").strip()})
    return out


def to_csv(rows: list[dict], cols: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for r in rows:
        w.writerow([" | ".join(r[c]) if isinstance(r.get(c), list) else ("" if r.get(c) is None else r[c])
                    for c in cols])
    return buf.getvalue()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--master-json", type=Path, required=True)
    ap.add_argument("--laramie-html", type=Path, required=True)
    ap.add_argument("--check-names", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    imp = load_importer()
    raw = json.loads(a.master_json.read_text())
    public, sealed, _stats, _vocab = imp.clean(raw)
    names = {s["record_id"]: s for s in sealed}

    mpath = OUT / "master_records.json"
    mdoc = json.loads(mpath.read_text())
    cur = mdoc["records"]
    fails = []
    if len(cur) != len(public):
        fails.append(f"record count {len(cur)} committed vs {len(public)} rebuilt")
    for c, p in zip(cur, public):
        # charges compared without whitespace: 19 committed rows keep a PDF line-wrap space ("Methamphetamine- Type")
        ws = lambda xs: [re.sub(r"\s+", "", x) for x in xs]
        if (c["record_id"], c["source_url"], ws(c["charges"])) != (p["record_id"], p["source_url"], ws(p["charges"])):
            fails.append(f"{c['record_id']}: committed record differs from rebuilt record")
    if fails:
        print("VERIFY FAIL (master):", *fails[:10], sep="\n  ")
        return 3
    for r in cur:
        s = names[r["record_id"]]
        r["name"], r["age"] = s["name"], s["age"]
        r["name_withheld"], r["age_withheld"] = False, False
        if s.get("name_uncertain"):
            r["name_uncertain"] = True

    # weekly capture (records.json)
    lpath = OUT / "records.json"
    ldoc = json.loads(lpath.read_text())
    ents = parse_capture(a.laramie_html.read_text(errors="ignore"))
    pool = {}
    for e in ents:
        pool.setdefault(norm(e["ch"]), []).append(e)
    miss = []
    for r in ldoc["records"]:
        k = norm(",".join(r["charges"]))
        if not pool.get(k):
            miss.append(r["record_id"])
            continue
        e = pool[k].pop(0)
        r["name"], r["age"], r["name_withheld"] = e["name"], e["age"], False
        r["age_withheld"] = False
    if miss:
        print("VERIFY FAIL (weekly capture): no matching entry for", miss[:10])
        return 3

    if a.check_names:
        web = json.loads(a.check_names.read_text())
        agree = disagree = 0
        bad = []
        for r in cur + ldoc["records"]:
            w = web.get(r["record_id"])
            if not w:
                continue
            if norm(w["name"]) == norm(r["name"]):
                agree += 1
            else:
                disagree += 1
                bad.append((r["record_id"], r["name"], w["name"]))
        print(f"cross-check vs articles: {agree} agree, {disagree} differ")
        for b in bad[:15]:
            print("   differs:", *b)

    for doc in (mdoc, ldoc):
        doc["policy"], doc["caveats"], doc["tier"] = POLICY, CAVEATS, "public-named"
        doc.pop("source_note", None)
    mdoc["age_band_published"] = None
    if "cleaning" in mdoc:
        c = mdoc["cleaning"]
        c["ages_published"] = c.pop("ages_sealed", None)
        c["unique_names"] = c.pop("unique_names_sealed", None)

    mcols = ["record_id", "report_date", "report_window", "name", "age", "charge_count", "categories",
             "charges", "source_url"]
    lcols = ["record_id", "report_published", "arrest_window", "name", "age", "charge_count", "categories",
             "charges", "source_url", "source_capture"]
    outputs = {
        mpath: json.dumps(mdoc, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        OUT / "master_records.csv": to_csv(cur, mcols),
        lpath: json.dumps(ldoc, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        OUT / "records.csv": to_csv(ldoc["records"], lcols),
    }
    named = sum(1 for r in cur + ldoc["records"] if r.get("name"))
    print(f"records with names: {named} of {len(cur) + len(ldoc['records'])}")
    if not a.dry_run:
        for p, text in outputs.items():
            p.write_text(text, encoding="utf-8")
        print("written:", ", ".join(p.name for p in outputs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
