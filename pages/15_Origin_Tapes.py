"""🔥 Origin Tapes — feature page (auto-split from the single-file console)."""
from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
st.set_page_config(page_title="🔥 Origin Tapes", page_icon="🔥", layout="wide")
import rwc_views as V
V.render_ledger_header()
V.render_section('🔥 Origin Tapes')
V.footer()
