"""entity_index.py — heuristic entity auto-indexer for the Transparency Index face.

Builds the Entity_Database structure the entity face expects
({speakers_or_authors, policies_mentioned, locations_mentioned} per document)
straight from the repo's Markdown dossiers — no LLM, no network, deterministic:

  * people/orgs: gazetteer (borrowed from intake.py's keyword battery) + every
    speaker/vendor already named in the recovered vault DB
  * policies: gazetteer phrases + regexes for Chapter/Section/Ordinance/Resolution
  * locations: gazetteer + street/park/ranch surface-pattern regex

main(): writes Entity_Database/<docname>.json per root dossier so the entity
face can also run from committed JSONs; the app calls build() live as a
fallback when that directory is absent (so the face lights up on first boot).
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

SKIP = {"README.md", "LEGAL.md", "PERSISTENCE.md", "DEPLOY.md"}

PEOPLE_ORGS = [
    "Charles Miller", "BOPU", "Board of Public Utilities", "DDA",
    "Downtown Development Authority", "NextEra", "Microsoft", "WY Fresh",
    "Metagold", "Kniseley", "Granicus", "City Council", "Planning Commission",
    "City Attorney", "Mayor", "Flock", "County Clerk",
]
POLICY_PHRASES = [
    "sixth penny", "6th penny", "Food Freedom", "administrative warrant",
    "public record", "passenger rail", "historic horse racing", "data center",
    "SRF", "lead service", "rate increase", "annexation", "UDC",
    "Unified Development Code", "storm sewer interceptor", "SRO MOU",
    "gag order", "referendum", "petition", "franchise", "2% assessment",
    "reserves", "compliance", "abatement", "encampment", "TCE",
]
LOCATION_TERMS = [
    "Reed Avenue", "Reed Ave", "MLK Park", "Martin Luther King Park",
    "Cox Ranch", "Belvoir", "Highlands", "West Edge", "Downtown Cheyenne",
    "Downtown", "Laramie County", "Cheyenne", "Municipal Building",
]
POLICY_RX = re.compile(
    r"\b(?:Chapter|Section|Sec\.)\s+\d+(?:\.\d+)+\b|"
    r"\b(?:Resolution|Ordinance)\s+(?:No\.?\s*)?\d{3,5}\b")
PLACE_RX = re.compile(
    r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+"
    r"(?:Avenue|Ave\.?|Street|St\.?|Road|Rd\.?|Park|Ranch|Ridge|Trail)\b")


def _vault_terms(root: Path) -> list[str]:
    """Speakers + vendors already named in the recovered vault = proven terms."""
    terms = []
    vault = Path(root) / "cheyenne_watchdog.db"
    if not vault.exists():
        return terms
    try:
        conn = sqlite3.connect(str(vault))
        for q in ("SELECT speaker_denial x FROM veracity_contradictions "
                  "UNION SELECT speaker_validation FROM veracity_contradictions "
                  "UNION SELECT vendor FROM voucher_forensics "
                  "UNION SELECT department FROM voucher_forensics"):
            for (t,) in conn.execute(q):
                if t and 3 < len(t) < 60:
                    terms.append(t)
        conn.close()
    except Exception:
        pass
    return terms


def build(root: Path, max_bytes: int = 2_000_000) -> dict:
    """{doc_name: {speakers_or_authors, policies_mentioned, locations_mentioned}}"""
    root = Path(root)
    people = sorted(set(PEOPLE_ORGS) | set(_vault_terms(root)), key=str.lower)
    index: dict[str, dict] = {}
    for fp in sorted(root.glob("*.md")):
        if fp.name in SKIP or fp.stat().st_size > max_bytes:
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        low, hit = text.lower(), {}
        hit["speakers_or_authors"] = sorted(
            {p for p in people if p.lower() in low})[:30]
        pol = {m.group(0) for m in POLICY_RX.finditer(text)}
        pol |= {ph for ph in POLICY_PHRASES if ph.lower() in low}
        hit["policies_mentioned"] = sorted(pol)[:40]
        loc = {m.group(0) for m in PLACE_RX.finditer(text)}
        loc |= {t for t in LOCATION_TERMS if t.lower() in low}
        hit["locations_mentioned"] = sorted(loc)[:40]
        hit["source_path"] = fp.name
        hit["auto_generated"] = True
        if any(hit[k] for k in ("speakers_or_authors", "policies_mentioned",
                                "locations_mentioned")):
            index[fp.name] = hit
    return index


def main():
    root = Path(__file__).resolve().parent.parent
    outdir = root / "Entity_Database"
    outdir.mkdir(exist_ok=True)
    index = build(root)
    for name, data in index.items():
        (outdir / (name.rsplit(".md", 1)[0] + ".json")).write_text(
            json.dumps(data, indent=1))
    print(f"entity index: {len(index)} dossiers -> {outdir}/")


if __name__ == "__main__":
    main()
