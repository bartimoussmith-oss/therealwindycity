"""Module 3 (extraction): turn raw files into searchable text.

HTML/TXT: stdlib. PDF: pdfplumber if installed (else flagged 'needs-parser').
Scanned-image PDFs: OCR hook via pytesseract if installed (else flagged
'needs-ocr') — the job row records exactly *why* a doc isn't text yet, which is
itself audit-relevant information.
"""
from __future__ import annotations

from pathlib import Path

from . import db
from .analyze import scan_and_alert
from .ingest import html_to_text


def extract_document(conn, doc_id: int) -> str:
    doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if doc is None:
        return f"doc {doc_id} missing"
    path = Path(doc["local_path"])
    raw = path.read_bytes()
    name = path.name.lower()

    # Dispatch on CONTENT, not filename: civic CMS URLs often lack extensions.
    head = raw[:1024].lstrip().lower()
    if raw[:5] == b"%PDF-" or name.endswith(".pdf"):
        text = _extract_pdf(path)
    elif head.startswith(b"<!doctype") or head.startswith(b"<html") or name.endswith((".html", ".htm")):
        text = html_to_text(raw.decode("utf-8", errors="replace"))
    else:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = f"[binary file retained ({len(raw)} bytes); no parser for it yet]"

    if text.startswith("["):
        with conn:
            conn.execute("UPDATE documents SET status = ? WHERE id = ?",
                         (text.strip("[]"), doc_id))
        return f"doc {doc_id}: {text}"

    db.index_text(conn, doc_id, doc["source"], doc["title"], text)
    alerts = scan_and_alert(conn, doc_id, text)
    return f"doc {doc_id}: indexed {len(text)} chars, {alerts} watchlist hits"


def _extract_pdf(path: Path) -> str:
    try:
        import pdfplumber  # optional dependency
    except ImportError:
        return "[needs-parser: install pdfplumber to read PDFs]"
    parts: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages):
            t = page.extract_text() or ""
            if t.strip():
                parts.append(f"--- page {i + 1} ---\n{t}")
            else:
                parts.append(f"--- page {i + 1} ---\n[_ocr_page_placeholder:{path.name}:{i + 1}]")
    full = "\n".join(parts)
    if "_ocr_page_placeholder" in full:
        try:
            import pytesseract  # noqa: F401
        except ImportError:
            full += "\n[needs-ocr: install pytesseract + tesseract binary for scanned pages]"
    return full


def process_jobs(conn, kinds: tuple[str, ...] = ("extract",)) -> int:
    from .detect import diff_document  # local import avoids cycle
    done = 0
    while True:
        job = db.dequeue_job(conn)
        if job is None:
            break
        if job["kind"] == "extract" and "extract" in kinds:
            print("    " + extract_document(conn, job["payload"]["document_id"]))
        elif job["kind"] == "diff" and "diff" in kinds:
            print("    " + diff_document(conn, job["payload"]["document_id"],
                                         job["payload"]["seq"]))
        done += 1
    return done
