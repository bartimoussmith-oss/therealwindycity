"""Shared initialization and safe source reader for the multipage dashboard."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VAULT_TABLES = ("public_comment_battles", "veracity_contradictions", "voucher_forensics", "environmental_zones")


def initialize_databases():
    from engine import db
    if not (ROOT / "data/engine.db").exists():
        db.init_db()
    vault = ROOT / "cheyenne_watchdog.db"
    tables = set()
    if vault.exists():
        with sqlite3.connect(vault) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not set(VAULT_TABLES).issubset(tables):
        import cheyenne_watchdog_vault
        cheyenne_watchdog_vault.init_db()


def _allowed(path):
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT.resolve()):
        return False
    lower = str(resolved.relative_to(ROOT.resolve())).lower()
    return not any(part in lower for part in ("arrest", "name_key", "keyring", "secrets", "access_ledger"))


def read_raw_document(fname, doc_meta=None):
    name = str(fname)
    if Path(name).is_absolute() or ".." in Path(name).parts:
        return "Source path is outside the public document reader."
    if not _allowed(ROOT / "Entity_Database" / (name + ".json")):
        return "This record is outside the public document reader; use its access-controlled page."
    candidates = []
    directories = ("data/text", "data/snapshots", "uploads", "pipeline/corpus", "pipeline/corpus_yt", "Video_Transcripts", "Cheyenne_Extracted_Documents", "city of cheyenne gov files")
    variants = {name, name + ".txt", name + ".md", name + ".html", name + ".pdf"}
    for directory in directories:
        base = ROOT / directory
        if base.is_dir():
            candidates.extend(base / variant for variant in sorted(variants))
            candidates.extend(p for p in sorted(base.rglob("*")) if p.name in variants)
    candidates.extend(p for p in sorted(ROOT.glob("*.md")) if p.name in variants)
    for target in dict.fromkeys(candidates):
        if not target.is_file() or not _allowed(target):
            continue
        try:
            suffix = target.suffix.lower()
            if suffix == ".pdf":
                from pypdf import PdfReader
                text = "\n".join(page.extract_text() or "" for page in PdfReader(target).pages)
            elif suffix in (".html", ".htm"):
                from bs4 import BeautifulSoup
                text = BeautifulSoup(target.read_text(encoding="utf-8", errors="replace"), "html.parser").get_text(" ")
            elif suffix in (".txt", ".md", ".json", ""):
                text = target.read_text(encoding="utf-8", errors="replace")
            else:
                continue
            from engine import redact
            if redact.is_arrest_document(title=target.name) or "arrest" in text.lower():
                continue
            if text.strip():
                return text
        except (OSError, ValueError, ImportError):
            continue
        except Exception:
            continue
    if not isinstance(doc_meta, dict):
        for filename in (name + ".json", Path(name).stem + ".json"):
            metadata_path = ROOT / "Entity_Database" / filename
            if metadata_path.is_file() and _allowed(metadata_path):
                try:
                    candidate = json.loads(metadata_path.read_text(encoding="utf-8"))
                    if isinstance(candidate, dict):
                        doc_meta = candidate
                        break
                except (OSError, ValueError):
                    pass
    if isinstance(doc_meta, dict):
        return "Raw source unavailable; indexed metadata follows. This is not the original document or independent verification.\n\n" + json.dumps(doc_meta, ensure_ascii=False, indent=2)
    return "Raw source and indexed metadata are currently unavailable."


def render_records_page():
    import streamlit as st
    initialize_databases()
    st.title("Unified Public Records")
    st.caption("The existing ledger, alerts, silent edits, search, paperwork, and other chapters remain in the sidebar.")
    vault_tab, entity_tab = st.tabs(["Forensic Vault", "Entity Dossiers"])
    with vault_tab:
        st.warning("Seeded vault entries are research leads, not independently verified facts. Consult the existing Case Files pages for corpus-verification context.")
        for table in VAULT_TABLES:
            with st.expander(table.replace("_", " ").title()):
                with sqlite3.connect(ROOT / "cheyenne_watchdog.db") as conn:
                    conn.row_factory = sqlite3.Row
                    rows = [dict(row) for row in conn.execute('SELECT * FROM "' + table + '"')]
                st.dataframe(rows, use_container_width=True)
    with entity_tab:
        paths = [p for p in sorted((ROOT / "Entity_Database").glob("*.json")) if _allowed(p)]
        st.metric("Indexed dossier files", len(paths))
        if paths:
            selected = st.selectbox("Document dossier", paths, format_func=lambda p: p.stem)
            try:
                metadata = json.loads(selected.read_text(encoding="utf-8"))
                st.json(metadata)
                st.text_area("Source text or metadata fallback", read_raw_document(selected.stem, metadata), height=500)
            except (OSError, ValueError) as exc:
                st.error("Unable to read dossier: " + str(exc))
        else:
            st.info("No entity dossier JSON files are present yet.")
