import streamlit as st
st.set_page_config(page_title="Unified Public Records", page_icon="📂", layout="wide")
from remediation_runtime import render_records_page
render_records_page()

# provenance: where the indexed numbers on this page come from
try:
    from rwc_provenance import show as _prov_show
    _prov_show('Unified Public Records', families=['engine', 'meeting_calendar'])
except Exception:
    pass
