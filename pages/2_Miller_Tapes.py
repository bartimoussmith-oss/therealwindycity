"""Miller Tapes — standalone nav page for the shared theater.

The real implementation lives in miller_theater.py (also the app front door);
this page just boots it with its own tab title. Stdlib + streamlit only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from miller_theater import render_theater

st.set_page_config(page_title="Miller Tapes", page_icon="\U0001F3AC", layout="wide")
render_theater(embed=False)
