"""Repository-backed public evidence browser; no fabricated statutory reviews."""
import importlib.util
import json
from pathlib import Path
from urllib.parse import quote
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("civic_evidence_browser", ROOT / "tools" / "civic_evidence_browser.py")
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
st.set_page_config(page_title="Civic Evidence Review", layout="wide")
st.title("Civic Evidence Review")
st.caption("Repository evidence browser — keyword candidates, not legal findings")
st.warning("Archive text may include caption or extraction errors. Matches do not establish a violation, official position, verified speaker, or meeting date. Check the original record before relying on an excerpt.")
st.info("Challenger, defender, legal-authority verification, entity resolution and GIS review are NOT running on this page. No live model is connected. This page exposes real repository excerpts without inventing those results.")
if st.button("Refresh repository scan"):
    st.rerun()
with st.spinner("Scanning bounded repository corpus"):
    report = engine.scan(ROOT)
cols = st.columns(3)
cols[0].metric("Files scanned", report["files_scanned"])
cols[1].metric("Keyword candidates", len(report["candidates"]))
cols[2].metric("Files skipped", report["files_skipped"])
st.caption(f"Discovered {report['files_discovered']} .txt/.md files. Scans at most {report['limit']} files, at most 1 MB per file, one match per category per file. Counts are not unique meetings or total archive coverage. Source: files bundled in this app deployment; no fresh government crawl is performed.")
if report["truncated"]:
    st.warning("The file limit was reached; this is a partial corpus scan.")
for error in report["errors"]:
    st.error(error)
category = st.selectbox("Candidate category", ["All"] + list(engine.RULES))
search = st.text_input("Filter excerpt or archive filename", max_chars=200).strip().casefold()
rows = [r for r in report["candidates"] if (category == "All" or r["category"] == category) and (not search or search in (r["path"] + " " + r["quote"]).casefold())]
st.write(f"{len(rows)} candidates match the filters. Showing at most 100.")
if not rows:
    st.info("No matches in this bounded scan. This is not evidence that an issue is absent.")
for row in rows[:100]:
    with st.expander(row["category"] + " | " + row["path"]):
        st.code(row["quote"], language=None)
        st.caption(f"Matched term: {row['matched_term']} | decoded text offsets {row['start']}:{row['end']}")
        st.code("Raw file SHA-256: " + row["raw_sha256"], language=None)
        url = "https://github.com/bartimoussmith-oss/therealwindycity/blob/main/" + quote(row["path"], safe="/")
        st.link_button("Inspect archive file on GitHub", url)
        st.caption("The GitHub link follows main and may differ from this deployed copy; compare the displayed hash. It is an archive-file link, not independent source verification.")
        st.write("Review state: unreviewed. Legal authorities: not verified. Automated publication: blocked.")
export = {"schema_version": 1, "scope": "bounded repository corpus keyword scan", "report": report,
          "filtered_candidates": rows, "human_review_required": True, "publication_allowed": False,
          "live_model_connected": False, "source_freshness": "deployment checkout; government freshness unverified"}
st.download_button("Download evidence candidates and limitations", json.dumps(export, ensure_ascii=False, indent=2), file_name="evidence-candidates.json", mime="application/json")
