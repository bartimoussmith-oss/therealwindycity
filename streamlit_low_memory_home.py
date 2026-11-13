"""Low-memory landing page and bounded, read-only evidence explorer."""
from __future__ import annotations
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parent
PAGE_SIZE = 50

def query_rows(path, sql, params=()):
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError("Evidence database is not installed at the configured path.")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return [dict(row) for row in conn.execute(sql, params).fetchmany(PAGE_SIZE)]

def navigation():
    st.title("The Real Windy City")
    st.caption("Heroes of the Public Record | Cheyenne and Laramie County")
    st.info("Low-memory home: open a feature to load its data. No corpus scan, verification rebuild, or local video is loaded here.")
    manifest = ROOT / "pages" / "_features.json"
    features = []
    try:
        if manifest.is_file() and manifest.stat().st_size <= 65536:
            features = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(features, list):
                features = []
    except (OSError, ValueError):
        st.warning("Feature descriptions are unavailable; use the sidebar.")
    linked = set()
    for item in features:
        if not isinstance(item, dict):
            continue
        page = str(item.get("page", ""))
        target = ROOT / "pages" / (page + ".py")
        if Path(page).name != page or not target.is_file():
            continue
        label = "Transparency Index" if item.get("key") == "__INDEX__" else str(item.get("key") or page)
        st.page_link("pages/" + target.name, label=label)
        if item.get("blurb"):
            st.caption(str(item["blurb"]))
        linked.add(target.name)
    for name, label in (
        ("16a_Miller_Tapes.py", "Miller Tapes"),
        ("16b_Screening_Room.py", "Screening Room"),
        ("23_Estoppel_Effect.py", "Estoppel-Effect Review"),
        ("24_Unified_Records.py", "Unified Public Records"),
        ("24_Scanner_Live.py", "Scanner Live"),
        ("25_Civic_Atlas.py", "Civic Atlas and Dais Lens"),
        ("26_Gods_Eye_View.py", "County Map"),
        ("27_Statewide_Audit_Cartography.py", "Statewide Audit Cartography"),
    ):
        if name not in linked and (ROOT / "pages" / name).is_file():
            st.page_link("pages/" + name, label=label)


def explorer():
    st.subheader("Municipal Evidence Database")
    st.caption("Read-only queries; at most 50 rows returned per page. A changed hash is not by itself proof of tampering.")
    configured = Path(os.environ.get("PROMETHEAN_DB", "database/promethean_evidence.db")).expanduser()
    path = configured if configured.is_absolute() else ROOT / configured
    view = st.selectbox("View", ("Latest records", "Observed document changes", "Full-text search"))
    if view == "Full-text search":
        with st.form("evidence_search"):
            term = st.text_input("Full-text query", max_chars=300)
            submitted = st.form_submit_button("Search")
        if not submitted or not term.strip():
            return
        sql = "SELECT primary_actor, title_or_claim, snippet(fts_forensic_archive, 2, '[', ']', '...', 35) AS Excerpt FROM fts_forensic_archive WHERE fts_forensic_archive MATCH ? LIMIT ?"
        params = (term, PAGE_SIZE)
    else:
        page = int(st.number_input("Page", min_value=1, max_value=100000, value=1, step=1))
        if not st.button("Load selected page"):
            return
        if view == "Latest records":
            sql = "SELECT g.item_id, g.meeting_date, g.committee_or_body, g.title, g.source_url, EXISTS(SELECT 1 FROM document_tamper_log t WHERE t.item_id=g.item_id) AS has_observed_change FROM governance_items g ORDER BY g.item_id DESC LIMIT ? OFFSET ?"
        else:
            sql = "SELECT tamper_id, detected_at, source_url, original_hash, new_hash FROM document_tamper_log ORDER BY tamper_id DESC LIMIT ? OFFSET ?"
        params = (PAGE_SIZE, (page - 1) * PAGE_SIZE)
    try:
        rows = query_rows(path, sql, params)
    except FileNotFoundError as exc:
        st.warning(str(exc))
        return
    except sqlite3.Error:
        st.error("Query failed: the database schema, search syntax, or database availability needs checking. No replacement database was created.")
        return
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
        st.caption("Showing at most 50 rows. No full-table export is held in memory.")
    else:
        st.info("No rows matched this query; this does not establish complete coverage or absence of changes.")


def main():
    st.set_page_config(page_title="The Real Windy City", layout="wide")
    mode = st.radio("Home view", ("Feature directory", "Municipal evidence explorer"), horizontal=True)
    if mode == "Feature directory":
        navigation()
    else:
        explorer()

if __name__ == "__main__":
    main()
