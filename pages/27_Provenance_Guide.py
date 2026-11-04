"""The provenance guide — the master page for the whole archive.

Everything this project holds, the films that show how each part of it was collected,
the ledger that ties every printed figure to a source and a second of footage, and how
to check any of it yourself. Generated from the checkout by `provenance/guide.py`, so it
restates whatever is actually there rather than what somebody once wrote down.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Provenance Guide", page_icon="🧭", layout="wide")

import rwc_provenance as P  # noqa: E402

st.title("🧭 Provenance Guide")
P.show_guide()
