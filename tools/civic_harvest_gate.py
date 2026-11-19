"""Fail-closed audit of legacy harvest summaries and preserved evidence.
This is not a seven-stage collector or a legal-analysis engine.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile

FIELDS = ("endpoints_listed", "endpoints_crawled", "endpoints_remaining", "new",
          "unchanged", "aliases", "changed", "errors", "known_not_refetched")

def summaries(log, expected_roots):
    expected = set(expected_roots)
    if not expected or len(expected) != len(expected_roots):
        raise ValueError("expected roots must be nonempty and unique")
    found = {}
    for line in log.splitlines():
        if not line.startswith("[summary] "):
            continue
        item = json.loads(line[len("[summary] "):])
        source = item.get("root")
        if source not in expected or source in found:
            raise ValueError("unexpected or duplicate source summary")
        if item.get("reachable") is not True:
            raise ValueError("source unreachable")
        if item.get("budget_exhausted") is not False:
            raise ValueError("partial or missing budget status")
        for field in FIELDS:
            if type(item.get(field)) is not int or item[field] < 0:
                raise ValueError("invalid counter: " + field)
        if item["errors"] or item["endpoints_remaining"]:
            raise ValueError("collection errors or incomplete queue")
        if item["endpoints_listed"] < 1 or item["endpoints_crawled"] < 1:
            raise ValueError("no validated crawl")
        if item["endpoints_crawled"] > item["endpoints_listed"]:
            raise ValueError("inconsistent crawl counters")
        # The legacy parser cannot prove that an empty result is legitimate.
        if not sum(item[k] for k in ("new", "unchanged", "aliases", "changed", "known_not_refetched")):
            raise ValueError("unverified empty result")
        found[source] = item
    if set(found) != expected:
        raise ValueError("missing source summaries")
    return found

def audit_database(database, evidence_root):
    database = Path(database).resolve(strict=True)
    evidence_root = Path(evidence_root).resolve(strict=True)
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as conn:
        conn.execute("PRAGMA query_only=ON")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("database integrity check failed")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("database foreign-key check failed")
        rows = conn.execute("SELECT item_id, attachment_sha256, local_pdf_path FROM governance_items").fetchall()
    if not rows:
        raise ValueError("empty evidence database")
    for identifier, claimed, relative in rows:
        if not isinstance(claimed, str) or len(claimed) not in (64, 128):
            raise ValueError("invalid digest on item " + str(identifier))
        try:
            int(claimed, 16)
        except ValueError:
            raise ValueError("nonhex digest on item " + str(identifier))
        if not isinstance(relative, str) or not relative:
            raise ValueError("missing raw path on item " + str(identifier))
        path = (evidence_root / relative).resolve(strict=True)
        if not path.is_relative_to(evidence_root):
            raise ValueError("raw evidence path escapes approved root")
        algorithm = hashlib.sha256 if len(claimed) == 64 else hashlib.sha512
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, algorithm).hexdigest()
        if actual != claimed.lower():
            raise ValueError("raw evidence digest mismatch on item " + str(identifier))
    return {"records_verified": len(rows), "database_integrity": "ok"}

def verified_snapshot(database, target, evidence_root):
    target = Path(target)
    source = Path(database).resolve(strict=True)
    if target.resolve() == source:
        raise ValueError("snapshot cannot overwrite source")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=target.parent, suffix=".sqlite")
    os.close(fd)
    try:
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src:
            with sqlite3.connect(temporary) as dst:
                src.backup(dst)
        result = audit_database(temporary, evidence_root)
        os.replace(temporary, target)
        return result
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True)
    parser.add_argument("--expected-root", action="append", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--snapshot", required=True)
    args = parser.parse_args()
    try:
        checked = summaries(Path(args.log).read_text(encoding="utf-8"), args.expected_root)
        result = verified_snapshot(args.database, args.snapshot, args.evidence_root)
    except (ValueError, OSError, sqlite3.Error, TypeError) as exc:
        print(json.dumps({"status": "rejected", "error": str(exc)}))
        return 2
    print(json.dumps({"status": "verified_snapshot", "sources_checked": len(checked), **result,
                      "publication_authorized": False}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
