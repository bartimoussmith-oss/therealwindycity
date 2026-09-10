"""verify_vault.py — the auto-verification bridge.

Every recovered vault row carries claims and quotes with no source URL (the
Sept-7 squash orphan-recovery caveat). This module greps each claim against
the transcript corpus (pipeline/corpus/*.txt) AND the root dossier corpus
(*.md), so a row can graduate from "lead" to "found in the record" with the
exact file + meeting date + matched context attached.

Matching strategy (deterministic, no LLM):
  1. normalized full-substring probe (whole claim text vs normalized corpus)
  2. if that misses, three 8-word shingles (start/middle/end of the claim);
     >=2 shingles hitting the SAME file counts as a hit
Both steps are pure substring matches after the same normalization, so every
verdict is itself verifiable by hand with ctrl-F.

Row keys are "<table>:<ordinal>" using the SAME ordering the app displays
(app: battles ORDER BY meeting_date DESC, veracity natural rowid order,
vouchers ORDER BY amount DESC) — keep in sync if those queries change.

main(): writes data/vault_verification.json so the site can load verdicts
instead of re-grepping the corpus on every boot (the app also verifies live
when the JSON is absent).
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

try:
    from engine import corpus_search as cs
except ImportError:  # running as `python3 engine/verify_vault.py` from repo root
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from engine import corpus_search as cs

TABLES = {
    "public_comment_battles":  "SELECT * FROM public_comment_battles ORDER BY meeting_date DESC",
    "veracity_contradictions": "SELECT * FROM veracity_contradictions",
    "voucher_forensics":       "SELECT * FROM voucher_forensics ORDER BY amount DESC",
    "environmental_zones":     "SELECT * FROM environmental_zones",
}

MIN_PROBE = 40          # ignore quote fields shorter than this
SHINGLE = 8             # words per fallback shingle
MIN_SHINGLE_HITS = 2    # shingles that must land in one file


def _shingles(words: list[str]) -> list[str]:
    if len(words) <= SHINGLE:
        return []
    pts = [0, max(0, (len(words) - SHINGLE) // 2), max(0, len(words) - SHINGLE)]
    return [" ".join(words[p:p + SHINGLE]) for p in sorted(set(pts))]


def _probes_for_row(row: dict) -> list[str]:
    out = []
    for v in row.values():
        if isinstance(v, str):
            n = cs.norm(v)
            if len(n) >= MIN_PROBE:
                out.append(n)
    return out


def verify(root: Path) -> dict:
    root = Path(root)
    vault = root / "cheyenne_watchdog.db"
    corpus = cs.load_corpus(root)          # transcripts
    for fp in sorted(root.glob("*.md")):   # dossier corpus as second source
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        corpus.append({"name": fp.name, "date": "",
                       "text": text, "norm": cs.norm(text)})

    result = {"generated_at": datetime.now(timezone.utc)
                     .strftime("%Y-%m-%dT%H:%M:%SZ"),
              "corpus_files": len(corpus), "rows": {}}
    if not vault.exists() or not corpus:
        return result

    conn = sqlite3.connect(str(vault))
    conn.row_factory = sqlite3.Row
    for table, query in TABLES.items():
        try:
            rows = [dict(r) for r in conn.execute(query)]
        except sqlite3.OperationalError:
            continue
        for i, row in enumerate(rows):
            key = f"{table}:{i}"
            probes = _probes_for_row(row)
            hits = []
            for doc in corpus:
                matched = None
                for p in probes:
                    if p in doc["norm"]:
                        matched = p
                        break
                    sh = [s for s in _shingles(p.split()) if s in doc["norm"]]
                    if len(sh) >= MIN_SHINGLE_HITS:
                        matched = " ".join(sh[0].split()[:6]) + " …"
                        break
                if matched:
                    j = doc["norm"].find(cs.norm(matched.split(" …")[0][:40]))
                    lo, hi = max(0, j - 140), j + 260
                    hits.append({"file": doc["name"], "date": doc["date"],
                                 "context": doc["norm"][lo:hi]})
                    if len(hits) >= 5:
                        break
            result["rows"][key] = {
                "status": "found-in-record" if hits else "unverified",
                "hits": hits}
    conn.close()
    return result


def main():
    root = Path(__file__).resolve().parent.parent
    out = root / "data" / "vault_verification.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    result = verify(root)
    found = sum(1 for r in result["rows"].values()
                if r["status"] == "found-in-record")
    out.write_text(json.dumps(result, indent=1))
    print(f"vault verification: {found}/{len(result['rows'])} rows matched "
          f"against {result['corpus_files']} corpus files -> {out}")


if __name__ == "__main__":
    main()
