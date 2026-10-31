"""Standalone read-only review console; preserves existing application."""
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import pandas as pd
import streamlit as st
from promethean.sdk import db_path,query
st.set_page_config(page_title='Promethean evidence review',layout='wide')
st.title('Promethean evidence review')
st.caption('Research candidates only: no automatic accusations, severity scores or publication.')
p=db_path()
if not p.exists():
    st.info('Initialize and ingest an explicitly selected meeting first. No sample verdicts are supplied.');st.stop()
c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
q=st.text_input('FTS5 source search')
if q:
    try:
        for row in query(c,q,30):
            st.subheader(row['title']);st.write(row['excerpt']);st.write(row['source_url']);st.code(row['attachment_sha256'])
    except sqlite3.Error as exc:st.error(str(exc))
st.caption('No hit is not evidence of absence.')
st.subheader('Claim-review queue')
st.dataframe(pd.read_sql_query('SELECT review_id,official,role,statement_date,claim,status,created_at FROM claim_reviews ORDER BY review_id DESC',c),hide_index=True)
st.subheader('Coverage')
st.dataframe(pd.read_sql_query('SELECT committee_or_body,meeting_date,COUNT(*) documents FROM governance_items GROUP BY 1,2',c),hide_index=True)
st.caption('Dates and bodies are caller-supplied; extraction, review, publication and deployment are separate states.')
c.close()
