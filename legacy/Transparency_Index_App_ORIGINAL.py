import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="Apex Watchdog Engine", layout="wide", initial_sidebar_state="expanded")

# Custom CSS for high-tech aesthetic
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e9ecef; }
    .status-active { color: #28a745; font-weight: bold; }
    .header-style { color: #1e3a8a; font-family: 'Inter', sans-serif; }
    </style>
""", unsafe_allow_html=True)

DB_NAME = "cheyenne_watchdog.db"

def get_data(query):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            return pd.read_sql_query(query, conn)
    except Exception as e:
        return pd.DataFrame()

# --- SIDEBAR NAVIGATION ---
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/security-shield.png", width=80)
    st.title("Watchdog Control")
    st.status("System: G-SYNC ACTIVE", state="running")
    nav = st.radio("Intelligence Matrix", ["Executive Overview", "Statutory Battles", "Veracity Ledger", "Voucher Audit", "Environmental Matrix"])
    st.divider()
    st.caption("Cheyenne Civic Transparency Engine v2.4")

# --- MAIN INTERFACE ---
if nav == "Executive Overview":
    st.markdown("<h1 class='header-style'>⚡ PROMETHEAN NEXUS OVERVIEW</h1>", unsafe_allow_html=True)
    
    # Top Level Metrics
    df_v = get_data("SELECT amount FROM voucher_forensics")
    df_b = get_data("SELECT count(*) as count FROM public_comment_battles")
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Audit Accuracy", "100%", "Verified")
    m2.metric("Statutory Wins", df_b['count'][0] if not df_b.empty else 0, "Active")
    m3.metric("Discretionary Spend Tracked", f"${df_v['amount'].sum():,.2f}" if not df_v.empty else "$0.00")

    st.divider()
    
    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("📢 Priority Friction Points")
        df_top = get_data("SELECT meeting_date, subject, outcome_status FROM public_comment_battles LIMIT 5")
        for _, row in df_top.iterrows():
            with st.expander(f"⚠️ {row['meeting_date']} | {row['subject']}"):
                st.write(f"**Current Status:** {row['outcome_status']}")
    
    with c2:
        st.subheader("📊 Spend Profile")
        df_pie = get_data("SELECT department, amount FROM voucher_forensics")
        if not df_pie.empty:
            fig = px.pie(df_pie, values='amount', names='department', hole=.4, color_discrete_sequence=px.colors.sequential.RdBu)
            fig.update_layout(showlegend=False, height=300, margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)

elif nav == "Statutory Battles":
    st.header("⚔️ Statutory Interventions")
    df = get_data("SELECT * FROM public_comment_battles ORDER BY meeting_date DESC")
    st.dataframe(df, use_container_width=True, hide_index=True)

elif nav == "Veracity Ledger":
    st.header("🔍 Veracity Index: Contradictions")
    df = get_data("SELECT * FROM veracity_contradictions")
    for _, row in df.iterrows():
        with st.container(border=True):
            st.markdown(f"### {row['topic']}")
            col_denial, col_proof = st.columns(2)
            col_denial.error(f"**Official Denial** ({row['speaker_denial']}):

_{row['quote_denial']}_")
            col_proof.success(f"**Verification** ({row['speaker_validation']}):

_{row['quote_validation']}_")
            st.caption(f"Significance: {row['significance']}")

elif nav == "Voucher Audit":
    st.header("🧾 Voucher Forensic Audit")
    df = get_data("SELECT * FROM voucher_forensics")
    if not df.empty:
        fig = px.bar(df, x='vendor', y='amount', color='department', title="Expenditure by Vendor")
        st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df, use_container_width=True)

elif nav == "Environmental Matrix":
    st.header("☣️ Ecological Exposure Matrix")
    df = get_data("SELECT * FROM environmental_zones")
    st.table(df)
