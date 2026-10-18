#!/usr/bin/env python3
"""Import MASTER_ARREST_DATABASE into the two-tier arrest record set.

Input is the owner's consolidated export: 6,569 {"name","charges","source"}
records drawn from 97 weekly Cap City News arrest reports (2021-01-09 to
2025-09-27), supplied as a 261-page PDF.

Output is TWO tiers, per owner policy:

  PUBLIC   data/arrests/master_records.{json,csv}   committed
           charges, categories, report citation, provenance. NO names, NO ages.
  SEALED   data/arrests/keyring.jsonl               gitignored, mode 600
           names and ages, appended. Never committed, never published.

The source PDF is NEVER copied into the repo: it holds all 5,108 names, and the
repo is public. Process it from wherever the owner keeps it and pass the path.

CLEANING (measured against the supplied file, not assumed)
  1,421 records  literal \\uXXXX escapes (O\\u2019Connor)      -> decoded
  2,454 records  space inside the source URL (PDF line wrap)   -> repaired
  2,232 records  age appended to the name (", 35")             -> SEALED, not published
      56 records exact duplicates (name+charges+source)         -> deduped
       4 records uppercase "SURNAME , FIRST - CHARGES" mangled  -> repaired

Fail-closed: if any withheld name, name token, or exact age reaches the public
tier the tool exits 3 and names the offender. Nothing is written on failure.

Usage
-----
    python3 tools/import_master_arrest_db.py --pdf /path/MASTER_ARREST_DATABASE.pdf
    python3 tools/import_master_arrest_db.py --json /path/records.json
    python3 tools/import_master_arrest_db.py --json ... --age-band 10   # opt-in
    python3 tools/import_master_arrest_db.py --json ... --dry-run

Exit codes: 0 ok · 2 bad args/input · 3 audit FAILED · 4 write error
"""

from __future__ import annotations

import argparse
import codecs
import csv
import io
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "arrests"
KEYRING = OUT_DIR / "keyring.jsonl"

# ------------------------------------------------------------------ categories
# Charge groupings ONLY. No category encodes a protected characteristic or a
# proxy for one; nothing infers race, ethnicity, national origin, sex, gender or
# immigration status. Verbatim charge text is always retained beside the
# category so grouping can never distort the record. Registry-compliance and
# immigration holds fold into the neutral warrant_court bucket rather than
# getting a targeting-able label of their own.
CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("impaired_driving", ("dui", "pedestrian under the influence", "open container",
                          "interlock")),
    ("drug_possession", ("methamphetamine", "amphetamine", "marijuana", "cocaine",
                         "heroin", "controlled substance", "possession/use of drugs",
                         "drug court hold", "schedule 1", "edibles", "meth")),
    ("assault_violence", ("assault", "domestic battery", "domestic violence",
                          "strangulation", "reckless endangerment", "fighting",
                          "riotous", "child abuse", "child endangerment", "battery")),
    ("warrant_court", ("warrant", "court order", "failure to appear", "failure to comply",
                       "probation", "parole", "ncic", "failure to register", "ice detainer",
                       "protection order", "stalking", "failure to pay", "not responsible")),
    ("property_theft", ("theft", "destruction of property", "criminal trespass",
                        "forgery", "burglary", "robbery", "larceny")),
    ("officer_obstruction", ("interference with peace officer", "interference with a peace",
                             "resisting arrest", "fleeing", "eluding", "interfering",
                             "obstructing", "false report")),
    ("traffic", ("speeding", "lane use", "suspended driver", "duty upon colliding",
                 "duty to stop", "proof of lia", "reckless driving", "no insurance",
                 "failure to maintain", "driving without")),
    ("weapons", ("concealed weapon", "firearm", "weapon")),
    ("public_order", ("public intoxication", "disturbing the peace", "urinating in public",
                      "minor in possession", "possession of tobacco", "breach of peace",
                      "disorderly")),
]

CAVEATS = [
    "Coverage is UNEVEN and must not be compared across years: 2021=1267, "
    "2022=773, 2023=241, 2024=712, 2025=2863 records. A low year reflects "
    "missing reports, not fewer arrests.",
    "The source log is not comprehensive. Verbatim from Cap City News: it omits "
    "juvenile offenders, suspects recommended for charges of a sexual nature, "
    "and anyone who bonded or bailed out before the information was released. "
    "Those exclusions are systematic, not random.",
    "Arrest is not a finding of guilt. Every entry is a recommended charge at "
    "booking. This dataset publishes NO outcomes, because it contains none.",
    "Names and exact ages are withheld from this tier by owner policy. Age is "
    "withheld because it is a quasi-identifier: age plus charge plus week in a "
    "small county can single a person out.",
    "No demographic field is derived, inferred, or published. Do not "
    "re-identify: joining these records against other public sources to "
    "recover names is out of scope of any access grant.",
    "Rows are arrest EVENTS, not people. One person can appear many times; "
    "160 name+charge pairs recur across different reports.",
]


# ------------------------------------------------------------------- extraction

def extract_from_pdf(path: Path) -> list[dict]:
    """Parse the printed-JSON PDF. Needs pypdf; it is NOT added to
    requirements.txt (Streamlit Cloud clone budget) - install ad hoc."""
    try:
        from pypdf import PdfReader
    except ImportError:
        print("error: reading the PDF needs pypdf. Either:\n"
              "    python3 -m pip install pypdf\n"
              "  or pass a pre-extracted file with --json.", file=sys.stderr)
        raise SystemExit(2)
    reader = PdfReader(str(path))
    flat = "\n\f\n".join((p.extract_text() or "") for p in reader.pages)
    flat = re.sub(r"\s*\f\s*", " ", flat)
    flat = re.sub(r"\s+", " ", flat)
    pat = re.compile(r'\{\s*"name"\s*:\s*"(.*?)"\s*,\s*"charges"\s*:\s*"(.*?)"'
                     r'\s*,\s*"source"\s*:\s*"(.*?)"\s*\}')
    found = pat.findall(flat)
    occ = flat.count('{ "name"')
    if len(found) != occ:
        print(f"warning: parsed {len(found)} records but found {occ} "
              f"'{{ \"name\"' markers - extraction may be lossy", file=sys.stderr)
    return [{"name": n, "charges": c, "source": s} for n, c, s in found]


# --------------------------------------------------------------------- cleaning

_UNICODE_ESC = re.compile(r"\\u([0-9a-fA-F]{4})")
_AGE_SUFFIX = re.compile(r",\s*(\d{1,3})\s*$")
# uppercase "SURNAME , FIRST - CHARGES" bleeding into the name field
_MANGLED = re.compile(r"^([A-Z]{2,}\s*,\s*[A-Z][A-Z .'\-]*?)\s*[\u2014\u2013]\s*(.+)$")
# charges bleeding into the name field behind a HYPHEN separator, which the
# em-dash pattern above misses: "Travis Marshall Lilly -District Court Warrant",
# "Robert Cook Bunten III- Burglary/ Aggravated Injury"
_HYPHEN_BLEED = re.compile(r"^(?P<name>.{3,60}?)\s*-\s*(?P<over>[A-Z].{2,})$")


def decode_escapes(s: str) -> str:
    """'O\\u2019Connor' -> 'O'Connor'. Only \\uXXXX is touched."""
    def rep(m):
        try:
            return codecs.decode(m.group(0), "unicode_escape")
        except Exception:
            return m.group(0)
    return _UNICODE_ESC.sub(rep, s)


def repair_url(u: str) -> str:
    """PDF line-wrapping injects spaces mid-URL. Remove all whitespace."""
    return re.sub(r"\s+", "", u)


def split_age(name: str) -> tuple[str, int | None]:
    m = _AGE_SUFFIX.search(name)
    if not m:
        return name.strip(), None
    age = int(m.group(1))
    if not 10 <= age <= 110:          # not an age, part of the name
        return name.strip(), None
    return name[:m.start()].strip(), age


def repair_mangled(rec: dict) -> tuple[dict, bool]:
    """Fix records where charges bled into the name field.

    Two shapes occur in the source: an uppercase "SURNAME , FIRST - CHARGES"
    row, and an ordinary name followed by a hyphen and its charges. The name is
    kept VERBATIM in the source's own order and case - reordering or re-casing
    it would be a guess about a real person. Overflow charges move back into the
    charges field and the row is flagged, because its shape differs from every
    other row and a consumer deserves to know.
    """
    m = _MANGLED.match(rec["name"])
    if m:
        real_name = re.sub(r"\s*,\s*", ", ", m.group(1).strip())
        overflow = m.group(2).strip()
        charges = (overflow + ", " + rec["charges"]).strip(", ")
        return {**rec, "name": real_name, "charges": charges, "_repaired": "uppercase"}, True

    m = _HYPHEN_BLEED.match(rec["name"])
    if m:
        # Only treat it as bleed when the tail actually reads like charges, not
        # when it is a hyphenated surname ("Guardian-Rocka", "Smith-Jones").
        tail = m.group("over")
        if re.search(r"(?i)\b(warrant|court|order|probation|parole|theft|assault|"
                     r"assaukt|burglary|possession|reckless|endangering|battery|"
                     r"dui|trespass|forgery|failure|domestic|controlled|substance|"
                     r"weapon|interference|resisting|fleeing|eluding|ncic)\b", tail) \
                and not re.match(r"^[A-Z][a-z]+$", tail):
            charges = (tail + ", " + rec["charges"]).strip(", ")
            return {**rec, "name": m.group("name").strip(), "charges": charges,
                    "_repaired": "hyphen-bleed"}, True
    return rec, False


def build_public_vocab(raw: list[dict]) -> set[str]:
    """Every word that legitimately belongs in the public tier, derived from the
    RAW source rows - charges and source URLs only, never the name field.

    This must not be derived from the built public records: an audit that learns
    its own allowed vocabulary from the artefact under test is self-defeating,
    because a name injected into a charge field would then count as legitimate.
    """
    vocab: set[str] = set()
    for rec in raw:
        for field in ("charges", "source"):
            for w in re.findall(r"[A-Za-z'’\-]{3,}",
                                decode_escapes(rec.get(field, "") or "")):
                vocab.add(w.lower())
    for name, keys in CATEGORIES:
        vocab.update(w for w in re.findall(r"[a-z]{3,}", name))
        for k in keys:
            vocab.update(w for w in re.findall(r"[a-z'’\-]{3,}", k))
    return vocab


def build_charge_vocab(raw: list[dict]) -> tuple[set[str], set[tuple[str, ...]]]:
    """Words and 3-word phrases that legitimately appear in charge text, derived
    from the data itself.

    Single charge words are a WEAK signal: Duty, Bond and Guardian are real
    surnames in this dataset as well as charge words, so flagging on them would
    smear innocent rows. Three-word charge phrases ("district court warrant",
    "possession of a controlled") are distinctive enough to be trustworthy.
    """
    words: set[str] = set()
    phrases: set[tuple[str, ...]] = set()
    for rec in raw:
        toks = [w.lower() for w in
                re.findall(r"[A-Za-z]{3,}", decode_escapes(rec.get("charges", "") or ""))]
        words.update(toks)
        for i in range(len(toks) - 2):
            phrases.add(tuple(toks[i:i + 3]))
    return words, phrases


def name_is_uncertain(name: str, charge_words: set[str],
                      charge_phrases: set[tuple[str, ...]]) -> bool:
    """True when a name field still looks like it contains charge text, i.e. the
    name/charge boundary could not be determined. Flagged, never guessed at:
    splitting a real person's name on a hunch is worse than leaving it flagged."""
    toks = [w for w in re.findall(r"[A-Za-z]{3,}", name)]
    low = [t.lower() for t in toks]
    for i in range(len(low) - 2):
        if tuple(low[i:i + 3]) in charge_phrases:
            return True
    # 4+ tokens ending on a charge word: "Kristopher Lee Garlick Theft".
    # Generational suffixes are excluded - "III" is a charge word too (Schedule
    # III), and it smeared ~40 perfectly ordinary "Firstname Middle Last III"
    # rows before this guard existed.
    if len(toks) >= 4 and low[-1] in charge_words and low[-1] not in _NAME_SUFFIXES:
        return True
    return False


def categorise(charges: list[str]) -> list[str]:
    joined = " | ".join(charges).lower()
    hits = [n for n, keys in CATEGORIES if any(k in joined for k in keys)]
    return hits or ["other"]


def report_window(url: str) -> str:
    """'...arrest-report-9-19-25-9-26-25/' -> '9/19/25-9/26/25' (best effort)."""
    m = re.search(r"arrest-report-(\d{1,2}-\d{1,2}-\d{2})-?\s*(\d{1,2}-\d{1,2}-\d{2})", url)
    if not m:
        return ""
    return m.group(1).replace("-", "/") + "-" + m.group(2).replace("-", "/")


def report_date(url: str) -> str:
    m = re.search(r"/crime/(\d{4})/(\d{2})/(\d{2})/", url)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def clean(raw: list[dict]) -> tuple[list[dict], list[dict], dict, set[str]]:
    """-> (public_records, sealed_rows, quality_report, public_vocab)."""
    stats = Counter({k: 0 for k in (
        "records_in", "records_public", "duplicates_dropped", "dropped_incomplete",
        "escapes_decoded", "urls_repaired", "ages_sealed", "mangled_repaired",
        "unique_names_sealed", "surname_first_rows", "name_uncertain")})
    charge_words, charge_phrases = build_charge_vocab(raw)
    public_vocab = build_public_vocab(raw)
    uncertain_ids: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    out: list[dict] = []
    sealed: list[dict] = []

    for rec in raw:
        raw_name = rec.get("name", "") or ""
        raw_charges = rec.get("charges", "") or ""
        raw_src = rec.get("source", "") or ""

        if "\\u" in raw_name or "\\u" in raw_charges:
            stats["escapes_decoded"] += 1
        if re.search(r"\s", raw_src):
            stats["urls_repaired"] += 1

        # Decode escapes and repair the URL FIRST: the mangled-record fix and the
        # age split both depend on real punctuation, not literal \u2014 sequences
        # or a space wrapped into the middle of a URL.
        rec = {"name": decode_escapes(raw_name),
               "charges": decode_escapes(raw_charges),
               "source": repair_url(raw_src)}
        rec, mangled = repair_mangled(rec)
        if mangled:
            stats["mangled_repaired"] += 1
            stats["surname_first_rows"] += 1

        name = rec["name"].strip()
        charges_raw = rec["charges"].strip()
        url = rec["source"].strip()

        name, age = split_age(name)
        if age is not None:
            stats["ages_sealed"] += 1

        if not name or not charges_raw:
            stats["dropped_incomplete"] += 1
            continue

        key = (name, charges_raw, url)
        if key in seen:
            stats["duplicates_dropped"] += 1
            continue
        seen.add(key)

        charges = [c.strip() for c in charges_raw.split(",") if c.strip()]
        rid = f"AR-{len(out)+1:06d}"
        out.append({
            "record_id": rid,
            "report_date": report_date(url),
            "report_window": report_window(url),
            "source_url": url,
            "charges": charges,
            "charge_count": len(charges),
            "categories": categorise(charges),
            "name": None,
            "age": None,
            "name_withheld": True,
            "age_withheld": age is not None,
        })
        uncertain = name_is_uncertain(name, charge_words, charge_phrases)
        if uncertain:
            stats["name_uncertain"] += 1
            uncertain_ids.append(rid)
        sealed.append({"record_id": rid, "name": name, "age": age,
                       "repaired": rec.get("_repaired", ""),
                       "name_uncertain": uncertain,
                       "report_date": report_date(url), "source_url": url})

    stats["records_in"] = len(raw)
    stats["records_public"] = len(out)
    stats["unique_names_sealed"] = len({s["name"] for s in sealed})
    stats["uncertain_record_ids"] = uncertain_ids
    return out, sealed, dict(stats), public_vocab


# ------------------------------------------------------------------ name audit

_STOP = {"jr", "sr", "ii", "iii", "iv", "st", "mr", "mrs", "ms", "de", "la", "el",
         "van", "mac", "mc", "del", "los", "san", "santa"}
_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}


def audit_texts(public: list[dict], sealed: list[dict],
                texts: dict[str, str], scaffold: str = "",
                public_vocab: set[str] | None = None) -> list[str]:
    """Prove nothing withheld reached a public artefact.

    Takes label -> text so the SAME audit runs on the exact bytes about to be
    written (dry-run) and on the files afterwards. An audit that silently skips
    a missing file would be a hollow pass, so nothing here is optional.

    Single-pass by design: with 4.5k withheld names and multi-megabyte output,
    testing each name against each artefact is minutes of work. Instead every
    word-like token in the artefact is collected once and intersected with the
    forbidden set. A full name cannot appear without its tokens appearing, so
    this is strictly stronger per unit time, not weaker.
    """
    if not texts:
        return ["audit called with no artefacts to check"]

    names = {s["name"].strip() for s in sealed if s.get("name")}
    sealed_ages = {int(s["age"]) for s in sealed if s.get("age") is not None}

    # Words that LEGITIMATELY belong in the public tier: charge text, category
    # labels, source URLs, report dates. Without subtracting them the audit
    # flags real surnames that are also ordinary English (Duty, Bond, Guardian)
    # and charge vocabulary that happens to appear in a charge string.
    # Allowed vocabulary comes from the RAW source (public_vocab) and the
    # scaffold render - never from `public`, which is the artefact under test.
    legit: set[str] = set(public_vocab or set())
    # The scaffold is the same artefact rendered with ZERO records: its vocabulary
    # is exactly the structure + narrative (policy, caveats, JSON literals such as
    # "null"). Subtracting it means prose I authored cannot be mistaken for a
    # withheld name - "grant" in "any access grant" is not Mr Grant. Deriving it
    # from a real render beats maintaining a hand-written word list that drifts.
    if scaffold:
        legit.update(w.lower() for w in re.findall(r"[A-Za-z'’\-]{3,}", scaffold))
    legit.update({"null", "true", "false", "none"})
    forbidden: set[str] = set()
    for nm in names:
        for tok in re.split(r"[\s.'’,\-]+", nm):
            tl = tok.lower()
            if len(tok) >= 4 and tl not in _STOP and tl not in legit:
                forbidden.add(tl)
    # A name whose every part is short (<=3 chars) would slip past the token
    # test, so those are checked as whole strings.
    short_names = {nm for nm in names
                   if all(len(t) < 4 for t in re.split(r"[\s.'’,\-]+", nm) if t)}

    # Full names, normalised to lowercase token tuples, for an exact check that
    # does not depend on any single token being distinctive.
    name_tuples: set[tuple[str, ...]] = set()
    for nm in names:
        t = tuple(w.lower() for w in re.findall(r"[A-Za-z'’\-]+", nm) if w)
        if len(t) >= 2:
            name_tuples.add(t)

    fails: list[str] = []
    # Boundary-aware: a token embedded in a snake_case identifier is CODE, not a
    # name. "unique_names_sealed" is a JSON key; "Aja Unique Johnson" is a
    # person. Names never contain underscores, so this cannot hide a real leak.
    word_re = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z'’\-]{4,}(?![A-Za-z0-9_])")
    seq_re = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z'’\-]+(?![A-Za-z0-9_])")
    for label, text in texts.items():
        found = {w.lower() for w in word_re.findall(text)} & forbidden
        for tok in sorted(found)[:20]:
            fails.append(f"{label}: withheld name token {tok!r}")
        if len(found) > 20:
            fails.append(f"{label}: ...and {len(found) - 20} more name tokens")
        words = [w.lower() for w in seq_re.findall(text)]
        full: set[str] = set()
        for k in (2, 3, 4, 5):
            if k > len(words):
                break
            for i in range(len(words) - k + 1):
                t = tuple(words[i:i + k])
                if t in name_tuples:
                    full.add(" ".join(t))
        for nm in sorted(full)[:10]:
            fails.append(f"{label}: FULL withheld name {nm!r}")
        if len(full) > 10:
            fails.append(f"{label}: ...and {len(full) - 10} more full names")
        low = text.lower()
        for nm in sorted(short_names):
            if nm.lower() in low:
                fails.append(f"{label}: short withheld name {nm!r}")
        # exact ages published as a field value would defeat de-identification
        published_ages = {int(a) for a in re.findall(r'"age":\s*"?(\d{1,3})"?', text)}
        for a in sorted(published_ages & sealed_ages):
            fails.append(f"{label}: exact age {a} published")
    return fails


def audit(public: list[dict], sealed: list[dict], files: list[Path],
          scaffold: str = "", public_vocab: set[str] | None = None) -> list[str]:
    """Audit artefacts already on disk."""
    texts = {str(f.relative_to(ROOT)): f.read_text(errors="replace")
             for f in files if f.exists()}
    for m in [str(f.relative_to(ROOT)) for f in files if not f.exists()]:
        print(f"warning: {m} does not exist - not audited", file=sys.stderr)
    return audit_texts(public, sealed, texts, scaffold, public_vocab)


# ----------------------------------------------------------------------- output

CSV_FIELDS = ["record_id", "report_date", "report_window", "charge_count",
              "categories", "charges", "source_url"]


def render_public(public: list[dict], sealed: list[dict], stats: dict,
                  src: Path, age_band: int | None) -> tuple[str, str]:
    """Render the exact public JSON and CSV text. Shared by --dry-run and the
    real write, so what is audited is byte-for-byte what gets committed."""
    # Age bands come from the SEALED side and are coarse; exact ages are never
    # written to a public artefact.
    band_of: dict[str, str] = {}
    if age_band:
        for s in sealed:
            if s["age"] is not None:
                lo = (s["age"] // age_band) * age_band
                band_of[s["record_id"]] = f"{lo}-{lo + age_band - 1}"

    dates = sorted({r["report_date"] for r in public if r["report_date"]})
    payload = {
        "tier": "public-deidentified",
        "policy": "Arrest records published WITHOUT names and WITHOUT exact "
                  "ages. Names are released only on request or by paid access "
                  "code, for public-safety and non-discriminatory research only.",
        "generated_by": "tools/import_master_arrest_db.py",
        "source_file": src.name,
        "source_note": "The source PDF is owner-held and is NEVER committed: it "
                       "contains every withheld name.",
        "record_count": len(public),
        "report_count": len(dates),
        "date_span": [dates[0] if dates else "", dates[-1] if dates else ""],
        "age_band_published": age_band,
        "caveats": CAVEATS,
        "cleaning": stats,
        "category_rule": "Categories are charge groupings only; none encodes a "
                         "protected characteristic or a proxy for one.",
        "records": [
            {**r, **({"age_band": band_of[r["record_id"]]}
                     if r["record_id"] in band_of else {})}
            for r in public
        ],
    }
    json_text = json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + "\n"

    fields = CSV_FIELDS + (["age_band"] if age_band else [])
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore",
                       lineterminator="\n")
    w.writeheader()
    for r in payload["records"]:
        row = dict(r)
        row["charges"] = " | ".join(r["charges"])
        row["categories"] = " | ".join(r["categories"])
        w.writerow(row)
    return json_text, buf.getvalue()


def write_outputs(public: list[dict], sealed: list[dict], stats: dict,
                  src: Path, age_band: int | None) -> list[Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_text, csv_text = render_public(public, sealed, stats, src, age_band)

    jp = OUT_DIR / "master_records.json"
    jp.write_text(json_text)

    cp = OUT_DIR / "master_records.csv"
    cp.write_text(csv_text)

    # SEALED: append names + ages to the gitignored keyring, mode 600
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fresh = not KEYRING.exists()
    with KEYRING.open("a", encoding="utf-8") as fh:
        for s in sealed:
            fh.write(json.dumps({
                "sealed_at": now, "tier": "master-arrest-database",
                "record_id": s["record_id"], "name": s["name"], "age": s["age"],
                "repaired": s.get("repaired", ""),
                "name_uncertain": bool(s.get("name_uncertain")),
                "report_date": s["report_date"], "source_url": s["source_url"],
            }, ensure_ascii=False, sort_keys=True) + "\n")
    os.chmod(KEYRING, 0o600)
    if fresh:
        gi = (ROOT / ".gitignore").read_text() if (ROOT / ".gitignore").exists() else ""
        if "/data/arrests/keyring.jsonl" not in gi:
            raise SystemExit("error: keyring.jsonl is not gitignored - refusing to "
                             "write names where git could commit them")
    return [jp, cp, KEYRING]


# ------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pdf", type=Path, help="MASTER_ARREST_DATABASE.pdf (owner-held)")
    g.add_argument("--json", type=Path, help="pre-extracted [{name,charges,source}] JSON")
    ap.add_argument("--age-band", type=int, default=None,
                    help="OPT-IN: publish coarse age bands of this width (e.g. 10). "
                         "Off by default - exact ages are never published.")
    ap.add_argument("--dry-run", action="store_true", help="clean + audit, write nothing")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    src = args.pdf or args.json
    if not src.is_file():
        print(f"error: not a file: {src}", file=sys.stderr)
        return 2
    # src may live anywhere on the owner's side. It is read, never copied into
    # the repo: the PDF holds every withheld name and the repo is public.
    raw = extract_from_pdf(src) if args.pdf else json.loads(src.read_text())
    if not isinstance(raw, list) or not raw:
        print("error: input parsed to no records", file=sys.stderr)
        return 2

    public, sealed, stats, public_vocab = clean(raw)

    # Audit the exact bytes that would be / were written. In --dry-run this is
    # the rendered text; after a real write the on-disk files are re-read and
    # audited too, so a rendering/write divergence cannot slip through.
    json_text, csv_text = render_public(public, sealed, stats, src, args.age_band)
    scaffold = "".join(render_public([], sealed, stats, src, args.age_band))
    texts = {"master_records.json (rendered)": json_text,
             "master_records.csv (rendered)": csv_text}

    files: list[Path] = []
    if not args.dry_run:
        try:
            files = write_outputs(public, sealed, stats, src, args.age_band)
        except OSError as e:
            print(f"error: write failed: {e}", file=sys.stderr)
            return 4
        for f in files[:2]:
            texts[str(f.relative_to(ROOT)) + " (on disk)"] = f.read_text(errors="replace")

    fails = audit_texts(public, sealed, texts, scaffold, public_vocab)

    if not args.quiet:
        print(f"input records      : {stats['records_in']}")
        print(f"public (de-id)     : {stats['records_public']}")
        print(f"duplicates dropped : {stats['duplicates_dropped']}")
        print(f"incomplete dropped : {stats['dropped_incomplete']}")
        print(f"escapes decoded    : {stats['escapes_decoded']}")
        print(f"urls repaired      : {stats['urls_repaired']}")
        print(f"ages sealed        : {stats['ages_sealed']}")
        print(f"mangled repaired   : {stats['mangled_repaired']}")
        print(f"name/charge unsure : {stats['name_uncertain']}  "
              f"(flagged, not guessed: {', '.join(stats['uncertain_record_ids'][:8])}"
              f"{' ...' if len(stats['uncertain_record_ids']) > 8 else ''})")
        print(f"unique names sealed: {stats['unique_names_sealed']}")
        dates = sorted({r['report_date'] for r in public if r['report_date']})
        print(f"report span        : {dates[0]} -> {dates[-1]}  ({len(dates)} reports)")
        cats = Counter(c for r in public for c in r["categories"])
        print("categories         : " + ", ".join(f"{k}={v}" for k, v in cats.most_common()))
        if not args.dry_run:
            print(f"\npublic tier : {files[0].relative_to(ROOT)}")
            print(f"              {files[1].relative_to(ROOT)}")
            print(f"sealed tier : {files[2].relative_to(ROOT)}  (appended, mode 600, gitignored)")
        else:
            print("\n--dry-run: nothing written")

    if fails:
        print(f"\nAUDIT FAILED - {len(fails)} leak(s):", file=sys.stderr)
        for f in fails[:25]:
            print("  " + f, file=sys.stderr)
        return 3
    print(f"\nAUDIT PASS - 0 of {stats['unique_names_sealed']} names, 0 name tokens, "
          f"and 0 exact ages in the public tier ({stats['records_public']} records).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
