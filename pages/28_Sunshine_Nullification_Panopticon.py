#!/usr/bin/env python3
"""The Real Windy City — Page 28: Wyoming 99-Town WPMA Nullification & Nationwide Sunshine Index."""
import json, os, sqlite3
from datetime import date
from pathlib import Path
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="The Real Windy City | Sunshine & Nullification Index", page_icon="🏛️", layout="wide")

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = REPO_ROOT / "data" / "sunshine_public_export.json"
WATCHDOG_DB = REPO_ROOT / "cheyenne_watchdog.db"

def resolve_api_base() -> str:
    env_url = os.environ.get("PROMETHEAN_SUNSHINE_API_URL", "").strip()
    if env_url:
        return env_url.rstrip("/")
    try:
        return str(st.secrets.get("PROMETHEAN_SUNSHINE_API_URL", "")).strip().rstrip("/")
    except Exception:
        return ""

API_BASE = resolve_api_base()

PINE_BLUFFS_BASELINE = [
    {"municipality": "Pine Bluffs", "county": "Laramie", "meeting_date": "2026-10-26", "evidence_tier": "TIER_A",
     "flags": "W.S. 15-1-105 (3 ayes / 5 present < 2/3), NO_16_4_405_CITATION, CLOSED_DOOR_ADJOURNMENT",
     "url": "https://www.pinebluffswy.gov/media/3646"},
    {"municipality": "Pine Bluffs", "county": "Laramie", "meeting_date": "2026-07-13", "evidence_tier": "TIER_A",
     "flags": "NO_16_4_405_CITATION (120-min), CLOSED_DOOR_ADJOURNMENT",
     "url": "https://www.pinebluffswy.gov/media/3526"},
    {"municipality": "Pine Bluffs", "county": "Laramie", "meeting_date": "2026-02-23", "evidence_tier": "TIER_A",
     "flags": "ZERO_VOTE_EXEC_SESSION_16_4_405C, NO_16_4_405_CITATION, COUNSEL_PRESENT",
     "url": "https://www.pinebluffswy.gov/media/3301"},
    {"municipality": "Pine Bluffs", "county": "Laramie", "meeting_date": "2026-02-09", "evidence_tier": "TIER_A",
     "flags": "ZERO_VOTE_EXEC_SESSION_16_4_405C (86-min 287(g)), UNLISTED_ON_AGENDA, COUNSEL_PRESENT",
     "url": "https://www.pinebluffswy.gov/media/3261"},
    {"municipality": "Sublette County", "county": "Sublette", "meeting_date": "2026-07-21", "evidence_tier": "TIER_A",
     "flags": "MISSING_SECOND_AND_VOTE_16_4_405C",
     "url": "https://www.sublettecountywy.gov/DocumentCenter/View/7936"},
]

@st.cache_data(ttl=180)
def load_snapshot():
    if SNAPSHOT_PATH.exists():
        try:
            return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None

@st.cache_data(ttl=120)
def fetch_live(route: str, params=None):
    if not API_BASE:
        return None
    try:
        r = requests.get(f"{API_BASE}{route}", params=params, timeout=6)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

def query_sqlite(db_path: Path, sql: str, params=()):
    if not db_path.exists():
        return []
    conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except Exception:
        return []
    finally:
        conn.close()

snap = load_snapshot()
live_health = fetch_live("/api/sunshine/health")
live_wy = fetch_live("/api/sunshine/wyoming")
live_us = fetch_live("/api/sunshine/nationwide")
live_tamper = fetch_live("/api/sunshine/tampering")

st.title("🏛️ The Real Windy City — Sunshine Nullification & Panopticon Index")
mode_badge = f"LIVE API CONNECTED ({API_BASE})" if live_health else "STATIC R2PO SNAPSHOT MODE"
st.caption(f"R2PO Publication Tier 1 (Verified Public Analytics Only) | {mode_badge}")

wy_scorecard = live_wy if live_wy is not None else (snap.get("wyoming_99_scorecard", []) if snap else [])
us_index = live_us if live_us is not None else (snap.get("nationwide_sunshine_index", []) if snap else [])
tamper_alerts = live_tamper if live_tamper is not None else (snap.get("wayback_tampering_alerts", []) if snap else [])
wy_ledger = (snap.get("wyoming_verified_wpma_ledger") if (snap and snap.get("wyoming_verified_wpma_ledger")) else PINE_BLUFFS_BASELINE)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Wyoming Towns Tracked", len(wy_scorecard) or 99)
c2.metric("Verified TIER-A/B WPMA Receipts", len(wy_ledger))
c3.metric("Wayback Silent-Edit Alerts", len(tamper_alerts))
c4.metric("Nationwide Panopticon Towns", len(us_index))

t1, t2, t3, t4, t5 = st.tabs([
    "🤠 Wyoming 99-Town Scorecard",
    "🇺🇸 Nationwide Panopticon Index",
    "🕰️ Wayback Tampering Alerts",
    "🔍 Unified Cross-Vault FTS5",
    "📜 Citizen Cure & PRA Generator",
])

with t1:
    st.subheader("Wyoming 99-Municipality WPMA Compliance Scorecard")
    st.info("W.S. § 16-4-403(a): nonconforming actions are null and void and not merely voidable | W.S. § 15-1-105: municipal closed sessions require 2/3 of members present | W.S. § 16-4-408(a): up to $750 civil penalty | Gronberg v. Teton County Housing Authority, 2011 WY 13.")
    if wy_scorecard:
        df_wy = pd.DataFrame(wy_scorecard)
        counties = ["All Counties"] + sorted(df_wy["county"].dropna().unique().tolist()) if "county" in df_wy else ["All Counties"]
        sel = st.selectbox("Filter by County", counties)
        if sel != "All Counties":
            df_wy = df_wy[df_wy["county"] == sel]
        st.dataframe(df_wy, use_container_width=True, hide_index=True)
    st.markdown("### Verified Primary-Source WPMA Audit Ledger")
    st.dataframe(pd.DataFrame(wy_ledger), use_container_width=True, hide_index=True)

with t2:
    st.subheader("Nationwide Municipal Transparency & High-Leverage Sunshine States")
    if us_index:
        df_us = pd.DataFrame(us_index)
        states = ["All States"] + sorted(df_us["state"].dropna().unique().tolist()) if "state" in df_us else ["All States"]
        sel_st = st.selectbox("Filter by State", states)
        if sel_st != "All States":
            df_us = df_us[df_us["state"] == sel_st]
        st.dataframe(df_us, use_container_width=True, hide_index=True)
    else:
        st.info("Nationwide batch harvesting in progress on micro-worker-2.")

with t3:
    st.subheader("Wayback Machine CDX Multi-Digest Silent-Tampering Alerts")
    if tamper_alerts:
        st.dataframe(pd.DataFrame(tamper_alerts), use_container_width=True, hide_index=True)
    else:
        st.success("Zero multi-digest silent tampering alerts recorded yet.")

with t4:
    st.subheader("Unified Forensic Search (Cheyenne Watchdog + Wyoming WPMA + Nationwide Panopticon)")
    q = st.text_input("Search keywords (e.g., executive, 287, 16-4-405, consent, data center)")
    if q:
        live_hits = fetch_live("/api/sunshine/fts", params={"q": q})
        if live_hits:
            st.markdown("**Live Sunshine API Hits — Wyoming**")
            st.dataframe(pd.DataFrame(live_hits.get("wyoming_hits", [])), use_container_width=True, hide_index=True)
            st.markdown("**Live Sunshine API Hits — Nationwide**")
            st.dataframe(pd.DataFrame(live_hits.get("nationwide_hits", [])), use_container_width=True, hide_index=True)
        wc_hits = query_sqlite(WATCHDOG_DB, "SELECT * FROM veracity_contradictions WHERE topic LIKE ? OR official_denial LIKE ? OR contradiction LIKE ? LIMIT 25", (f"%{q}%", f"%{q}%", f"%{q}%"))
        if wc_hits:
            st.markdown("**Cheyenne Watchdog Veracity Contradictions**")
            st.dataframe(pd.DataFrame(wc_hits), use_container_width=True, hide_index=True)

with t5:
    st.subheader("Neutral Citizen Cure-and-Correct & Open Records Request Generator")
    col1, col2 = st.columns(2)
    st_pick = col1.selectbox("State Statute", ["Wyoming (WPMA W.S. § 16-4-403 / Gronberg + WPRA)", "California (Brown Act § 54960.1 + SB 707 + CPRA)", "Iowa (Code Ch. 21 + Ch. 22)", "Colorado (C.R.S. § 24-6-402 + CORA)", "Illinois (5 ILCS 120 OMA + FOIA)"])
    muni = col2.text_input("Municipality", value="Town of Pine Bluffs")
    mdate = col1.text_input("Meeting Date", value="October 26, 2026")
    defect = col2.text_input("Documented Defect", value="Executive session entered on 3-aye vote (5 present; < 2/3 under W.S. 15-1-105) with no W.S. 16-4-405(a) citation")
    sender = col1.text_input("Your Name", value="[Your Name]")
    email = col2.text_input("Your Email", value="[Your Email]")
    body = f"Subject: Statutory Sunshine Notice & Public Records Request ({muni} - {mdate})\nDate: {date.today().isoformat()}\nTo: Clerk, Governing Body & Municipal Attorney - {muni}\nFrom: {sender} ({email})\n\nFramework: {st_pick}\nDocumented Record Issue: {defect}\n\nPlease confirm whether the governing body will conduct a de novo open-session cure proceeding and provide electronic copies of open-session audio/video recordings, posted notices/agendas, and enacted public-comment/procedural rules for {mdate}.\n\nRespectfully,\n{sender}"
    st.text_area("Generated Notice / Records Request (Educational Template — Review Before Sending)", value=body, height=240)
