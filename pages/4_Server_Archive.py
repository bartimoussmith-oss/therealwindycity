"""
4_Server_Archive.py — Local Server Copy + RAG DB Status + No External Dependency

Shows:
- Local server storage layout server_data/<city>/
- Manifest with external_url + local_path + sha256
- RAG vectordb stored on server
- Verify no dependency (every external has local copy)
"""
import streamlit as st
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Server Archive — Local Copy + RAG", layout="wide")
st.title("💾 Server Archive — Local Copy + RAG DB On Your Server")
st.caption("Every document has external_url (original) + local_path (server copy) + sha256. If external site goes down, serve from local. RAG vectordb stored locally.")

try:
    from engine.local_store import LocalStore, VectorStoreLocal
    from engine.city_registry import list_cities, server_storage_layout
except Exception as e:
    st.error(f"Import failed: {e}")
    st.stop()

# Storage layout explanation
layout = server_storage_layout()
st.header("Storage Layout — No External Dependency")
st.json(layout)

st.divider()
st.header("Local Server Status")

# Check server_data
server_root = ROOT / "server_data"
if not server_root.exists():
    st.warning(f"`server_data/` not found at {server_root} — run `python tools/server_sync.py --city cheyenne --to server_data/` on your server after Colab pulls. For preview, showing expected layout.")
    # Show expected
    st.code("""
server_data/
  cheyenne/
    meetings/1103/
      agenda.html (local copy)
      agenda.txt
      minutes.pdf
      minutes.txt
      docs/staff_report.pdf
      video/meeting.mp4
      captions.vtt
      manifest.json {external_url, local_path, sha256}
    boards/
    code/municode/
    law/wy_statutes/
    law/case_law/
    wayback/
    vectordb/
      chroma.sqlite3
      chunks.jsonl
  casper/
    ...
  laramie/
    ...
    """, language="text")
else:
    cities = list_cities()
    for city in cities[:5]:  # show first 5
        slug = city["slug"]
        store = LocalStore(city=slug, root=str(server_root))
        ok, missing = store.verify_no_dependency()
        with st.expander(f"{city['name']} ({slug}) — {len(store.manifest['files'])} files, OK={ok}"):
            st.write(f"Manifest: {store.manifest_path}")
            if missing:
                st.error(f"Missing {len(missing)} local copies")
                st.write(missing[:20])
            else:
                st.success("All external URLs have local copies — no dependency")
            # List some files
            files = list(store.manifest["files"].items())[:10]
            for url, info in files:
                st.write(f"- {info['filename']} | external: {url[:60]} | local: {info['local_path']} | sha256: {info['sha256'][:12]}...")

st.divider()
st.header("RAG Vector DB — Stored On Your Server")

st.write("Existing RAG pipeline `rag/build_vector_db.py` already stores vectordb locally:")
st.code("""
# Cheyenne sample DB committed: rag/vectordb_sample/ 1687 chunks ~28MB
# Full DB (gitignored): rag/vectordb/ -> sync to server_data/cheyenne/vectordb/

pip install -r rag/requirements-rag.txt  # chromadb==1.5.9, pypdf
python rag/build_vector_db.py --all --persist server_data/cheyenne/vectordb
# Writes:
#   server_data/cheyenne/vectordb/chroma.sqlite3
#   server_data/cheyenne/vectordb/chunks.jsonl (portable, sync to R2)

# Query:
python rag/query.py "What does 15-1-402 require?" --persist server_data/cheyenne/vectordb --k 5
""", language="bash")

# Show sample vectordb
sample_db = ROOT / "rag/vectordb_sample"
if sample_db.exists():
    st.write(f"Sample DB exists at {sample_db}:")
    import os
    size = sum(f.stat().st_size for f in sample_db.rglob("*") if f.is_file()) / 1024 / 1024
    st.write(f"Size: {size:.1f} MB, files: {len(list(sample_db.rglob('*')))}")
    chunks_file = sample_db / "chunks.jsonl"
    if chunks_file.exists():
        st.write(f"chunks.jsonl: {chunks_file.stat().st_size/1024:.1f} KB")
        # preview first chunk
        with open(chunks_file) as f:
            first = f.readline()
            if first:
                st.json(json.loads(first))

st.divider()
st.header("Sync to Your Server")

st.write("After Colab pulls to Drive, sync to your own server:")
st.code("""
# On your server (Linux):
git clone https://github.com/bartimoussmith-oss/therealwindycity.git
cd therealwindycity

# 1. Pull everything in Colab first (Drive has everything)
# 2. Sync Drive -> server_data (or R2 -> server_data)
python tools/server_sync.py --city all --from-drive /path/to/Drive/TheRealWindyCity --to server_data/
python tools/server_sync.py --verify --city cheyenne

# 3. Build RAG vectordb on server
pip install -r rag/requirements-rag.txt
python rag/build_vector_db.py --all --persist server_data/cheyenne/vectordb

# 4. Backup vectordb to R2 (egress free)
# wrangler r2 object put therealwindycity/cities/cheyenne/vectordb/chroma.sqlite3 --file=server_data/cheyenne/vectordb/chroma.sqlite3

# 5. Run Streamlit on your server
streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0
# or with custom domain therealwindycity.com via Cloudflare Tunnel
""", language="bash")

st.divider()
st.header("External Link Preservation — How It Works")

st.write("""
1. **Save:** `LocalStore.save_document(url, data, meeting_id)` writes local file + manifest entry `{external_url, local_path, sha256, fetched_at}`
2. **Read:** `LocalStore.read_local(url)` serves from local even if external down
3. **Verify:** `verify_no_dependency()` checks every external_url has local copy
4. **Manifest:** `server_data/<city>/manifest.json` is the source of truth — every file has both URLs
5. **RAG:** `VectorStoreLocal` stores `chroma.sqlite3` + `chunks.jsonl` locally, backup to R2 (egress free), no external dependency for reading
6. **Viewer:** Frontend reads from `server_data/` first, falls back to external_url only if local missing (never for Cheyenne after full pull)
""")
