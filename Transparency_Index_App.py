import streamlit as st
import os
import json
import glob
import re
import pandas as pd
from bs4 import BeautifulSoup
from pypdf import PdfReader

# --- UI & BRANDING ---
st.set_page_config(layout="wide", page_title="The Cheyenne Transparency Index", page_icon="🏛️")
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #ffffff; }
    .stMetric { background-color: #1e2130; padding: 15px; border-radius: 5px; border: 1px solid #30363d; }
    .object-header { font-size: 28px; font-weight: bold; color: #e6edf3; border-bottom: 1px solid #30363d; padding-bottom: 10px; margin-bottom: 20px;}
    a { color: #58a6ff !important; text-decoration: none; font-weight: 500; }
    a:hover { text-decoration: underline; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏛️ The Cheyenne Transparency Index")
st.markdown("*An independent, document-backed forensic database of Cheyenne Municipal Operations.*")
st.markdown("---")

# --- FORENSIC DATA ENGINE ---
@st.cache_data(show_spinner=False)
def load_index():
    index = {"Entities": {}, "Documents": {}}
    json_files = glob.glob("Entity_Database/*.json")
    
    for jf in json_files:
        try:
            with open(jf, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            fname = os.path.basename(jf).replace(".json", "")
            index["Documents"][fname] = data
            
            # Map all entities (Speakers, Policies, Locations) to the document
            all_entities = data.get("speakers_or_authors", []) + data.get("policies_mentioned", []) + data.get("locations_mentioned", [])
            for entity in set(all_entities):
                if not entity or len(entity) < 4: continue
                if entity not in index["Entities"]: 
                    index["Entities"][entity] = []
                index["Entities"][entity].append(fname)
        except: pass
    return index

with st.spinner("Initializing Forensic Database..."):
    index = load_index()

# Extract just the policies for the sidebar
all_policies = set()
for doc in index["Documents"].values():
    all_policies.update(doc.get("policies_mentioned", []))

# --- UNIVERSAL FILE READER ---
def read_raw_document(fname):
    paths = [
        os.path.join("Video_Transcripts", fname),
        os.path.join("Cheyenne_Extracted_Documents", fname),
        os.path.join("city of cheyenne gov files", fname)
    ]
    target = next((p for p in paths if os.path.exists(p)), None)
    if not target: return "Source file currently archived or unavailable."
    
    ext = target.lower().split('.')[-1]
    try:
        if ext in ['htm', 'html']: return BeautifulSoup(open(target, "r", encoding="utf-8", errors="ignore").read(), 'html.parser').get_text(' ')
        elif ext == 'pdf': return "\n".join([p.extract_text() or "" for p in PdfReader(target).pages])
        elif ext == 'txt': return open(target, "r", encoding="utf-8", errors="ignore").read()
    except: return "Error extracting raw text."
    return "Format unsupported."

# --- NAVIGATION ---
st.sidebar.markdown("### 🔍 Index Navigation")
nav_mode = st.sidebar.radio("Select View:", ["Global Dashboard", "Entity Dossier", "Document Viewer"])

if nav_mode == "Global Dashboard":
    st.markdown("<div class='object-header'>System Overview</div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("Indexed Municipal Records", len(index["Documents"]))
    c2.metric("Tracked Entities & Policies", len(index["Entities"]))
    c3.metric("Status", "ACTIVE - UNREDACTED")
    
    st.subheader("High-Frequency Targets (Recent)")
    df_entities = pd.DataFrame([{"Entity": k, "Record Count": len(v)} for k, v in index["Entities"].items()])
    if not df_entities.empty:
        st.dataframe(df_entities.sort_values("Record Count", ascending=False).head(15), use_container_width=True)

elif nav_mode == "Entity Dossier":
    selected_entity = st.sidebar.selectbox("Select Target Entity/Policy:", sorted(list(index["Entities"].keys())))
    if selected_entity:
        st.markdown(f"<div class='object-header'>Dossier: {selected_entity}</div>", unsafe_allow_html=True)
        linked_docs = index["Entities"][selected_entity]
        st.info(f"Target identified in {len(linked_docs)} official records.")
        
        for doc in linked_docs:
            with st.expander(f"📄 View record: {doc}"):
                raw_text = read_raw_document(doc)
                # Highlight the entity in the text
                highlighted = re.sub(rf"(?i)({re.escape(selected_entity)})", r"**:red[\1]**", raw_text)
                st.markdown(highlighted[:3000] + "...\n\n*[Text truncated for display]*")

elif nav_mode == "Document Viewer":
    selected_doc = st.sidebar.selectbox("Select Official Record:", sorted(list(index["Documents"].keys())))
    if selected_doc:
        st.markdown(f"<div class='object-header'>Record: {selected_doc}</div>", unsafe_allow_html=True)
        t1, t2 = st.tabs(["Raw Source Text", "Extracted Metadata"])
        with t1:
            st.markdown(read_raw_document(selected_doc))
        with t2:
            st.json(index["Documents"][selected_doc])