"""Module 3 (verification): the silent-edit detector.

Ingest already fingerprints every capture with SHA-256 and appends a new
`versions` row on change. This module turns that raw signal into evidence:
a unified diff of the extracted text (old vs new), stored as an alert and on
the version row. Hash shows *that* a file changed; the diff shows *what*.
"""
from __future__ import annotations

import difflib
from pathlib import Path

from . import db
from .ingest import html_to_text


def _text_of(local_path: str) -> str:
    raw = Path(local_path).read_bytes()
    if local_path.lower().endswith((".html", ".htm")):
        return html_to_text(raw.decode("utf-8", errors="replace"))
    try:
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return ""


def diff_document(conn, doc_id: int, new_seq: int) -> str:
    vers = conn.execute(
        "SELECT * FROM versions WHERE document_id = ? ORDER BY seq",
        (doc_id,),
    ).fetchall()
    if len(vers) < 2:
        return f"doc {doc_id}: only one version"
    prev, cur = vers[-2], vers[-1]
    old = _find_capture(doc_id, prev["sha256"])
    new = _find_capture(doc_id, cur["sha256"])
    if old is None or new is None:
        return f"doc {doc_id}: snapshot missing for diff"
    old_lines = _text_of(str(old)).splitlines()
    new_lines = _text_of(str(new)).splitlines()
    diff = list(difflib.unified_diff(
        old_lines, new_lines, lineterm="",
        fromfile=f"seq{prev['seq']} ({prev['captured_at']})",
        tofile=f"seq{cur['seq']} ({cur['captured_at']})",
    ))
    added = [l[1:] for l in diff if l.startswith("+") and not l.startswith("+++")]
    removed = [l[1:] for l in diff if l.startswith("-") and not l.startswith("---")]
    summary = f"{len(added)} lines added, {len(removed)} removed"
    detail = "\n".join(diff[:400])
    with conn:
        conn.execute(
            "UPDATE versions SET change_summary = ? WHERE id = ?",
            (summary, cur["id"]),
        )
    db.record_alert(conn, doc_id, "SILENT-EDIT",
                    f"Document changed after publication: {summary}. "
                    f"Removed: {removed[:5]} Added: {added[:5]}")
    out = db.OUT_DIR / f"silent-edit-doc{doc_id}-seq{new_seq}.diff.txt"
    out.write_text(detail)
    return f"doc {doc_id}: SILENT EDIT -> {summary} (diff: {out.name})"


def _find_capture(doc_id: int, sha256: str) -> Path | None:
    doc = conn_less_doc(doc_id)
    for fp in db.SNAP_DIR.iterdir():
        if fp.name.startswith(sha256[:12] + "_"):
            return fp
    return Path(doc["local_path"]) if doc and doc["sha256"] == sha256 else None


def conn_less_doc(doc_id: int):
    conn = db.connect()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    return row
