"""Arrest Record Explorer — the PUBLIC, de-identified tier, live.

Standalone Streamlit app. It reads ONLY the public artefacts in data/arrests/
and refuses by construction to open the sealed ones: names and exact ages are
withheld by owner policy, and this viewer is the proof that the public surface
carries no identifiers.

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
    st.set_page_config(page_title="Arrest Record Explorer — de-identified",
                       page_icon="🔒", layout="wide")


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
    "<h2 style='margin-bottom:0'>🔒 Arrest Record Explorer</h2>"
    "<div style='color:#666;margin-bottom:6px'>Laramie County weekly arrest "
    "reports · de-identified public tier</div>",
    unsafe_allow_html=True,
)

st.info(
    "**Names and exact ages are withheld from this dataset by owner policy.** "
    "Records are published as arrest *events* — charge, date, reporting source — "
    "under opaque sequential IDs (`AR-000123`) that are **not** derived from any "
    "name, so there is nothing to reverse. Names are released only on request or "
    "by paid access code, for **public-safety and non-discriminatory research "
    "only**.",
    icon="🔐",
)

guard()
loaded = load()
if not loaded:
    st.error("No public tier found in data/arrests/.")
    st.stop()
payload, meta = loaded
records: list[dict] = payload["records"]

# ------------------------------------------------------------------- integrity
# Prove, at render time, that what is on screen came from a public file and
# carries no identifiers.
with st.expander("✅ Integrity checks on the data being displayed", expanded=False):
    named = [r for r in records if r.get("name")]
    aged = [r for r in records if r.get("age") is not None]
    st.write(f"- Source artefact: `data/arrests/{meta['file']}` (public tier)")
    st.write(f"- Records: **{len(records):,}**")
    st.write(f"- Records carrying a name: **{len(named)}** "
             f"{'✅' if not named else '❌ POLICY VIOLATION'}")
    st.write(f"- Records carrying an exact age: **{len(aged)}** "
             f"{'✅' if not aged else '❌ POLICY VIOLATION'}")
    st.write(f"- Sealed files present but never opened by this app: "
             f"{', '.join(f for f in SEALED_FILES if (ARREST_DIR / f).exists()) or 'none'}")
    id_shape = re.compile(r"AR-[0-9]{6}|LC-[0-9-]+")
    opaque = all(id_shape.fullmatch(r["record_id"]) for r in records)
    st.write(f"- Record IDs opaque (no name hash): {'✅' if opaque else '❌'}")
    if named or aged:
        st.error("This tier contains identifiers. Do not publish it.")

# ------------------------------------------------------------------------ KPIs
years = sorted({r["report_date"][:4] for r in records if r.get("report_date")})
reports = {r["report_date"] for r in records if r.get("report_date")}
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Arrest events", f"{len(records):,}")
c2.metric("Weekly reports", len(reports))
c3.metric("Date span", f"{min(reports)} → {max(reports)}" if reports else "—")
c4.metric("Charge entries", f"{sum(r['charge_count'] for r in records):,}")
c5.metric("Names published", "0")

# --------------------------------------------------------------------- filters
st.sidebar.header("Filter")
cats_all = sorted({c for r in records for c in r["categories"]})
cats = st.sidebar.multiselect("Charge category", cats_all, default=[])
yrs = st.sidebar.multiselect("Report year", years, default=[])
q = st.sidebar.text_input("Charge contains", placeholder="e.g. methamphetamine").strip().lower()
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
    if q and not any(q in c.lower() for c in r["charges"]):
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
    "report_date": r.get("report_date", ""),
    "window": r.get("report_window", ""),
    "charges": " · ".join(r["charges"]),
    "n": r["charge_count"],
    "categories": ", ".join(r["categories"]),
    "name": "— withheld —",
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
st.download_button("⬇️ Download this filtered view (CSV, de-identified)",
                   buf.getvalue(), mime="text/csv",
                   file_name="arrest_records_deidentified.csv")

# ------------------------------------------------------------------------ gate
st.divider()
g1, g2 = st.columns([1, 1])
with g1:
    st.subheader("🔑 Getting names")
    st.markdown(
        "Names and exact ages are sealed. Two routes, both owner-reviewed:\n\n"
        "1. **Request** — open a GitHub issue with the *Arrest record name "
        "request* template. State the purpose and the `record_id`s.\n"
        "2. **Paid access code** — purchase a code, then enter it in the gated "
        "full version.\n\n"
        "Both are limited to **public safety** and **non-discriminatory "
        "research**. Denied: targeting, screening, employment/tenancy/credit "
        "decisions, resale, and any use that ranks people by a protected "
        "characteristic."
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
    st.caption("Reproduce with `python3 tools/import_master_arrest_db.py "
               "--json <extracted> --dry-run`. The build fails closed (exit 3) "
               "if any withheld name, name token, or exact age reaches the "
               "public tier.")

st.caption("Arrest is not a finding of guilt. Every row is a recommended charge "
           "at booking. This dataset publishes no outcomes, because it contains "
           "none. Source: Cap City News weekly arrest reports.")
