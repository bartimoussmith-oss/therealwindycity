"""Arrest Record Explorer — the public arrest records, with names, live.

Standalone Streamlit app. It reads ONLY the public artefacts in data/arrests/.
Owner decision 2026-11-27: the records are published WITH names and ages, as Cap
City News printed them. Legacy sealed files (if any exist locally) are never opened.

Run it:
    streamlit run tools/arrest_explorer.py --server.port 8600 --server.address 0.0.0.0

This is a read-only explorer. It writes nothing, commits nothing, and calls no
network endpoint.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
from collections import Counter
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
ARREST_DIR = ROOT / "data" / "arrests"

# Files this app is allowed to open. Anything else in data/arrests/ is sealed.
PUBLIC_FILES = ("master_records.json", "records.json")
SEALED_FILES = ("keyring.jsonl", "name_key.json", "access_ledger.json")

# When this file is embedded inside a multipage Streamlit page (see
# pages/22_Arrest_Database.py, which runs it via runpy after its own password
# gate), the host page already owns set_page_config -- calling it twice makes
# Streamlit raise. Skip it in that case.
_EMBEDDED = bool(os.environ.get("ARREST_EXPLORER_EMBEDDED"))

if not _EMBEDDED:
    st.set_page_config(page_title="Arrest Record Explorer",
                       page_icon="🗂️", layout="wide")


@st.cache_data(show_spinner=False)
def load() -> tuple[dict, dict] | None:
    """Load the master tier when present, else the single-report tier."""
    for name in PUBLIC_FILES:
        p = ARREST_DIR / name
        if p.exists():
            return json.loads(p.read_text()), {"file": name}
    return None


def guard() -> None:
    """Fail loudly rather than silently serving nothing."""
    if not ARREST_DIR.exists():
        st.error("data/arrests/ is missing. Run "
                 "`python3 tools/import_master_arrest_db.py --pdf …` first.")
        st.stop()


# --------------------------------------------------------------------- header
st.markdown(
    "<h2 style='margin-bottom:0'>🗂️ Arrest Record Explorer</h2>"
    "<div style='color:#666;margin-bottom:6px'>Laramie County weekly arrest "
    "reports · as published by Cap City News</div>",
    unsafe_allow_html=True,
)

st.info(
    "**Arrest is not a conviction.** Names and ages are shown as printed in Cap City "
    "News' weekly compilation of Laramie County arrest logs. Every row is a recommended "
    "charge at booking; this dataset contains no case outcomes. Different people can "
    "share a name.",
    icon="⚖️",
)

guard()
loaded = load()
if not loaded:
    st.error("No public tier found in data/arrests/.")
    st.stop()
payload, meta = loaded
records: list[dict] = payload["records"]

# ------------------------------------------------------------------- integrity
# Show, at render time, which public file is on screen and how complete it is.
with st.expander("✅ Integrity checks on the data being displayed", expanded=False):
    named = [r for r in records if r.get("name")]
    aged = [r for r in records if r.get("age") is not None]
    st.write(f"- Source artefact: `data/arrests/{meta['file']}` (public tier)")
    st.write(f"- Records: **{len(records):,}**")
    st.write(f"- Records carrying a name: **{len(named):,}**")
    st.write(f"- Records carrying an age (source printed one): **{len(aged):,}**")
    st.write(f"- Sealed files present but never opened by this app: "
             f"{', '.join(f for f in SEALED_FILES if (ARREST_DIR / f).exists()) or 'none'}")
    id_shape = re.compile(r"AR-[0-9]{6}|LC-[0-9-]+")
    opaque = all(id_shape.fullmatch(r["record_id"]) for r in records)
    st.write(f"- Record IDs well-formed: {'✅' if opaque else '❌'}")
    if len(named) < len(records):
        st.warning(f"{len(records) - len(named):,} record(s) have no name.")

# ------------------------------------------------------------------------ KPIs
years = sorted({r["report_date"][:4] for r in records if r.get("report_date")})
reports = {r["report_date"] for r in records if r.get("report_date")}
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Arrest events", f"{len(records):,}")
c2.metric("Weekly reports", len(reports))
c3.metric("Date span", f"{min(reports)} → {max(reports)}" if reports else "—")
c4.metric("Charge entries", f"{sum(r['charge_count'] for r in records):,}")
c5.metric("Named records", f"{sum(1 for r in records if r.get('name')):,}")

# --------------------------------------------------------------------- filters
st.sidebar.header("Filter")
cats_all = sorted({c for r in records for c in r["categories"]})
cats = st.sidebar.multiselect("Charge category", cats_all, default=[])
yrs = st.sidebar.multiselect("Report year", years, default=[])
q = st.sidebar.text_input("Name or charge contains", placeholder="e.g. Smith or methamphetamine").strip().lower()
multi = st.sidebar.checkbox("Multi-charge events only", value=False)
uncertain_only = st.sidebar.checkbox(
    "Only rows flagged name/charge-uncertain", value=False,
    help="Rows where the source's name/charge boundary could not be determined. "
         "Flagged, never guessed at.")

uncertain_ids = set(payload.get("cleaning", {}).get("uncertain_record_ids", []))


def keep(r: dict) -> bool:
    if cats and not (set(r["categories"]) & set(cats)):
        return False
    if yrs and r.get("report_date", "")[:4] not in yrs:
        return False
    if q and q not in (r.get("name") or "").lower() and not any(q in c.lower() for c in r["charges"]):
        return False
    if multi and r["charge_count"] < 2:
        return False
    if uncertain_only and r["record_id"] not in uncertain_ids:
        return False
    return True


view = [r for r in records if keep(r)]
st.caption(f"Showing **{len(view):,}** of **{len(records):,}** arrest events")

# ---------------------------------------------------------------------- charts
if view:
    a, b = st.columns(2)
    with a:
        st.subheader("By charge category")
        cc = Counter(c for r in view for c in r["categories"])
        st.bar_chart(dict(cc.most_common()))
    with b:
        st.subheader("By report year")
        yc = Counter(r["report_date"][:4] for r in view if r.get("report_date"))
        st.bar_chart({k: yc[k] for k in sorted(yc)})

    st.subheader("Charges per event")
    nc = Counter(min(r["charge_count"], 6) for r in view)
    st.bar_chart({("6+" if k == 6 else str(k)): nc[k] for k in sorted(nc)})

# ----------------------------------------------------------------------- table
st.subheader("Records")
rows = [{
    "record_id": r["record_id"],
    "name": r.get("name") or "",
    "age": r.get("age"),
    "report_date": r.get("report_date", ""),
    "window": r.get("report_window", ""),
    "charges": " · ".join(r["charges"]),
    "n": r["charge_count"],
    "categories": ", ".join(r["categories"]),
    "flag": "⚠ uncertain" if r["record_id"] in uncertain_ids else "",
} for r in view[:5000]]

st.dataframe(rows, width="stretch", hide_index=True, height=420)
if len(view) > 5000:
    st.caption(f"Table capped at 5,000 rows for rendering; the download below "
               f"has all {len(view):,}.")

buf = io.StringIO()
if rows:
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
st.download_button("⬇️ Download this filtered view (CSV)",
                   buf.getvalue(), mime="text/csv",
                   file_name="arrest_records.csv")

# ------------------------------------------------------------------------ gate
st.divider()
g1, g2 = st.columns([1, 1])
with g1:
    st.subheader("✏️ Corrections")
    st.markdown(
        "If a record is wrong, or you can show a case was dropped or dismissed, "
        "open a GitHub issue with the `record_id` and it will be corrected or "
        "annotated. Please don't use these records for employment, tenancy or "
        "credit screening."
    )
with g2:
    st.subheader("⚠️ Read before analysing")
    for cav in payload.get("caveats", []):
        st.markdown(f"- {cav}")

with st.expander("🧹 What was cleaned on the way in (measured, not assumed)"):
    cl = payload.get("cleaning", {})
    if cl:
        for k in ("records_in", "records_public", "duplicates_dropped",
                  "dropped_incomplete", "escapes_decoded", "urls_repaired",
                  "ages_sealed", "mangled_repaired", "name_uncertain",
                  "unique_names_sealed"):
            if k in cl:
                st.write(f"- **{k.replace('_', ' ')}**: {cl[k]:,}")
    st.caption("Reproduce with `python3 tools/import_master_arrest_db.py --json <extracted>` "
               "followed by `python3 tools/publish_arrest_names.py`, which refuses to write "
               "unless every record id, source URL and charge list matches.")

st.caption("Arrest is not a finding of guilt. Every row is a recommended charge "
           "at booking. This dataset publishes no outcomes, because it contains "
           "none. Source: Cap City News weekly arrest reports.")
