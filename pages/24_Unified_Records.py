import streamlit as st
st.set_page_config(page_title="Unified Public Records", page_icon="📂", layout="wide")
from remediation_runtime import render_records_page
render_records_page()
