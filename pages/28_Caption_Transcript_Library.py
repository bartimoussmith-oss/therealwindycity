"""Browser-hosted transcript navigation without loading the corpus into Streamlit RAM."""
import streamlit as st
import streamlit.components.v1 as components

URL = "https://bartimoussmith-oss.github.io/therealwindycity/transcripts-master/index.html"
st.set_page_config(page_title="Caption Transcript Library", layout="wide")
st.title("Caption Transcript Library")
st.caption("Existing public caption text. Not official minutes; dates, names, attribution and recording completeness require verification.")
st.link_button("Open searchable transcript library", URL)
if st.checkbox("Show the transcript library here", value=False):
    components.iframe(URL, height=900, scrolling=True)
