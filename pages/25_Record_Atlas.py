"""Additive Streamlit page; does not change existing entrypoints."""
import json
import os
import subprocess
import sys
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.record_atlas import manifest, build_index, related

st.set_page_config(page_title="Record Atlas", page_icon="◈", layout="wide")
st.title("◈ Record Atlas")
st.caption("THE REAL WINDY CITY / SOURCE-FIRST RELATIONSHIP EXPLORER")
st.info("Shared identifiers are research leads, not proof of coordination, causation, or legal effect. Repository records are not automatically authenticated official records.")
try:
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=5).strip()
except (OSError, subprocess.SubprocessError):
    revision = os.environ.get("GITHUB_SHA", "main")

@st.cache_data(max_entries=2, show_spinner=False)
def load(root, inventory, rev):
    return build_index(root, inventory, rev)

inventory = manifest(ROOT)
with st.spinner("Indexing local allowlisted archive text…"):
    report = load(str(ROOT), inventory, revision)
records = report["records"]
a, b, c = st.columns(3)
a.metric("Indexed documents", len(records))
b.metric("Discovered eligible text files", report["discovered"])
c.metric("Skipped / duplicate files", len(report["skipped"]))
with st.expander("Coverage and provenance"):
    st.write("Local source folders: " + ", ".join(report["allowlist"]))
    st.code("Revision: " + revision)
    st.write("PDFs, JSON databases, compressed transcripts, private repositories, and Git history are not indexed by this first adapter. Dates are filename-derived. Text-cache invalidation uses file size and modification time; text SHA-256 is stored per record.")
    st.json(report["skipped"])
if not records:
    st.warning("No eligible local text corpus found in this checkout.")
    st.stop()
query = st.text_input("Search all indexed text", placeholder="Agenda, ordinance, parcel, phrase…").casefold()
choices = sorted([r for r in records if not query or query in (r["id"] + " " + r["text"]).casefold()], key=lambda r: (r["date"], r["id"]), reverse=True)
if not choices:
    st.info("No matching indexed documents.")
    st.stop()
selected = st.selectbox("Focus record", range(len(choices)), format_func=lambda i: choices[i]["id"])
focus = choices[selected]
links = related(records, focus)
st.caption(f"{len(choices)} search matches · {len(links)} historical records share an identifier with this focus. Historical links search the whole indexed corpus, not just the search results.")
keys = sorted(focus["identifiers"])
if keys:
    key = st.selectbox("Trace identifier", keys)
    matches = [(r, shared) for r, shared in links if key in shared]
else:
    key, matches = "No extracted identifier", []
limit = st.slider("Historical records displayed", 5, 100, 25)
shown = matches[:limit]
nodes = [{"title": focus["title"], "url": focus["url"], "text": focus["identifiers"].get(key, {}).get("excerpt", "No supported identifier extracted."), "type": "focus"}]
nodes += [{"title": r["title"], "url": r["url"], "text": r["identifiers"][key]["excerpt"], "type": "record"} for r, _ in shown]
payload = json.dumps({"nodes": nodes, "key": key}).replace("<", "\\u003c")
template = (ROOT / "record_atlas" / "graph.html").read_text(encoding="utf-8")
components.html(template.replace("/*DATA*/", payload), height=620, scrolling=False)
st.caption(f"Showing {len(shown)} of {len(matches)} matching historical records. Solid lines show extracted mentions, not substantive relationships. Click a graph node for its excerpt and source link.")
left, right = st.columns([2, 1])
with left:
    st.subheader("Focus source text")
    st.code(focus["text"][:40000], language=None)
    if len(focus["text"]) > 40000:
        st.caption("Preview capped at 40,000 characters; download includes the full text.")
with right:
    st.link_button("Open focus source", focus["url"])
    st.caption("SHA-256 of UTF-8 text")
    st.code(focus["sha256"])
    st.download_button("Download full focus text", focus["text"], file_name=focus["title"], mime="text/plain")
    st.download_button("Download matching evidence", json.dumps({"revision": revision, "focus": focus, "identifier": key, "matches": [r for r, _ in matches]}, indent=2), file_name="record-atlas-evidence.json", mime="application/json")
