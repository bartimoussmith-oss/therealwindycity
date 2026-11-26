#!/usr/bin/env python3
"""Keep database/promethean_evidence.db in git as a gzip file.

GitHub rejects any file over 100 MB. The SQLite database passed that limit (102.67 MB) and every
harvest push was refused, so no harvest progress was saved. It compresses about 3x, so git now
stores database/promethean_evidence.db.gz and the working .db is ignored.

    python3 tools/evidence_db.py unpack   # .db.gz -> .db (before reading or writing the database)
    python3 tools/evidence_db.py pack     # checkpoint WAL, .db -> .db.gz (before `git add`)

Packing is deterministic (no timestamp or name in the gzip header), so an unchanged database
produces a byte-identical .gz and therefore no commit.
"""
from __future__ import annotations

import gzip
import os
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "database" / "promethean_evidence.db"
GITHUB_LIMIT = 100 * 1024 * 1024


def gz_path(db: Path) -> Path:
    return db.with_name(db.name + ".gz")


def ensure_unpacked(db: Path | str = DEFAULT_DB) -> Path:
    """Return the .db path, decompressing the committed .gz first when the .db is missing or older."""
    db = Path(db)
    gz = gz_path(db)
    if gz.exists() and (not db.exists() or gz.stat().st_mtime > db.stat().st_mtime + 1):
        db.parent.mkdir(parents=True, exist_ok=True)
        tmp = db.with_name(db.name + ".unpacking")
        with gzip.open(gz, "rb") as src, open(tmp, "wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
        os.replace(tmp, db)
    return db


def pack(db: Path | str = DEFAULT_DB) -> Path:
    db = Path(db)
    if not db.exists():
        raise SystemExit(f"{db} does not exist; nothing to pack")
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    gz = gz_path(db)
    tmp = gz.with_name(gz.name + ".tmp")
    with open(db, "rb") as src, open(tmp, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
    size = tmp.stat().st_size
    if size >= GITHUB_LIMIT:
        tmp.unlink()
        raise SystemExit(f"Compressed database is {size / 1e6:.1f} MB, over GitHub's 100 MB file limit")
    os.replace(tmp, gz)
    # Keep the .db newer than the .gz so ensure_unpacked() does not overwrite it in this checkout.
    os.utime(db, None)
    print(f"[evidence-db] packed {db.stat().st_size / 1e6:.1f} MB -> {gz.name} {size / 1e6:.1f} MB")
    return gz


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_DB
    if cmd == "unpack":
        print(f"[evidence-db] using {ensure_unpacked(target)}")
    elif cmd == "pack":
        pack(target)
    else:
        raise SystemExit(__doc__)
