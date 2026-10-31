import os, sqlite3, pandas as pd, streamlit as st
st.set_page_config(page_title="Promethean CivicWatch", layout="wide")

DB_PATH = os.environ.get("PROMETHEAN_DB", "database/promethean_evidence.db")
conn = sqlite3.connect(DB_PATH, check_same_thread=False)

st.title("⚖️ The Real Windy City — Municipal Archive")
tab1, tab2, tab3 = st.tabs(["📅 Latest Records", "⚠️ Silent Edit Tamper Log", "🔍 FTS5 Forensic Search"])

with tab1:
    st.subheader("Recently Ingested Municipal Documents")
    # Chain of Custody Query: Flags tampered documents in the main view
    query = """
        SELECT g.meeting_date AS Date, g.committee_or_body AS Body, g.title AS Document, 
               CASE WHEN t.tamper_id IS NOT NULL THEN '⚠️ ALTERED (See Tamper Log)' ELSE g.source_url END AS Link_Status
        FROM governance_items g
        LEFT JOIN document_tamper_log t ON g.item_id = t.item_id
        ORDER BY g.item_id DESC LIMIT 50
    """
    df_recent = pd.read_sql_query(query, conn)
    st.dataframe(df_recent, use_container_width=True)

with tab2:
    st.subheader("Cryptographic Tamper Detections (SHA-512)")
    df_tamper = pd.read_sql_query("SELECT detected_at AS Detected, source_url AS URL, original_hash AS Old_SHA512, new_hash AS New_SHA512 FROM document_tamper_log ORDER BY tamper_id DESC", conn)
    if df_tamper.empty:
        st.success("No silent edits detected in the historical archive.")
    else:
        st.error("Warning: Cryptographic mismatches detected on historically published URLs. Rely on external storage shards for original binaries.")
        st.dataframe(df_tamper, use_container_width=True)

with tab3:
    search = st.text_input("Query FTS5 Statutory Archive (Full Text Search):")
    if search:
        try:
            df_fts = pd.read_sql_query("SELECT primary_actor, title_or_claim, snippet(fts_forensic_archive, 2, ' **[', ']** ', '...', 35) AS Excerpt FROM fts_forensic_archive WHERE fts_forensic_archive MATCH ? LIMIT 30", conn, params=(search,))
            st.dataframe(df_fts, use_container_width=True)
        except Exception:
            st.error("Invalid query syntax.")
