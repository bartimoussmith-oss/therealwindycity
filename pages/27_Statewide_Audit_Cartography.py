"""Standalone Streamlit workspace for Lineage A Statewide Forensic Auditing & Passive OSINT Cartography.

Additive page only: existing entry twins (`streamlit_app.py` / `Transparency_Index_App.py`),
databases, and source records remain untouched. All anomaly outputs are labeled
`candidate_unreviewed` and all W.S. 16-4-202 / objection templates are unsent drafts.
"""
from __future__ import annotations

import hashlib
import inspect
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from promethean.forensic_audit import (  # noqa: E402
    ANNEXATION_PREREQUISITES,
    MIRROR_LEDGERS,
    OPERATIONAL_SECTIONS,
    audit_alpr_logs,
    audit_annexation_prerequisites,
    audit_check_register_csv,
    audit_govqa_master_log,
    audit_lcrr_service_lines,
    audit_permitting_csv,
    audit_ws_16_4_202_timeline,
    build_arcgis_geojson_query_url,
    triangulate_mirror_ledgers,
)
from tools.passive_cartography import (  # noqa: E402
    generate_vendor_pra_templates,
    load_targets,
)

st.set_page_config(
    page_title="Statewide Audit & Cartography | The Real Windy City",
    page_icon="🧭",
    layout="wide",
)


def _render_df(data) -> None:
    if "width" in inspect.signature(st.dataframe).parameters:
        st.dataframe(data, width="stretch", hide_index=True)
    else:
        st.dataframe(data, use_container_width=True, hide_index=True)


st.title("🧭 Statewide Mirror Ledgers, Passive Cartography & Seven-Section Audit Lab")
st.caption(
    "Lineage A operator workspace: 8 State/Federal regulatory mirror ledgers, 23-county + wyo.gov passive "
    "infrastructure manifest, CASE/UCO SHA-256 provenance hashing, and candidate-only forensic runners."
)
st.info(
    "**Integrity & Legal Notice (`LEGAL.md`):** Statistical flags (Benford MAD / Chi-Squared, threshold clusters, "
    "elapsed clocks, and cross-ledger deltas) are `candidate_unreviewed` research leads requiring inspection of "
    "certified records — never automatic accusations. All W.S. 16-4-202 and public-comment outputs are unsent "
    "human-review drafts (`sent_by_this_tool = False`)."
)

tab_mirrors, tab_cartography, tab_benford, tab_pra, tab_sections = st.tabs([
    "1. Mirror Ledgers (8 Layers)",
    "2. 23-County Cartography & PRA Matrix",
    "3. Section 2: Benford & Check Register",
    "4. Section 7: W.S. 16-4-202 & Provenance",
    "5. Sections 1, 3, 4, 5, 6 Runners",
])

with tab_mirrors:
    st.subheader("Cross-Jurisdictional State & Federal Mirror Ledgers")
    col_s, col_k = st.columns([1, 2])
    with col_s:
        sec_choice = st.selectbox(
            "Filter by Operational Section",
            options=[0] + [s["section_id"] for s in OPERATIONAL_SECTIONS],
            format_func=lambda x: "All 7 Operational Sections" if x == 0 else f"Section {x}: {OPERATIONAL_SECTIONS[x - 1]['title']}",
        )
    with col_k:
        kw = st.text_input("Keyword filter (e.g., CAMA, EMMA, Single Audit, NPDES, Part 77, WYSOS)", value="")

    matched = triangulate_mirror_ledgers(
        section_id=None if sec_choice == 0 else sec_choice,
        keyword=kw or None,
    )
    st.metric("Matching State/Federal Mirror Layers", f"{len(matched)} / {len(MIRROR_LEDGERS)}")
    for layer in matched:
        with st.expander(f"Layer {layer['layer_id']}: {layer['name']} — {', '.join(layer['primary_endpoints'])}", expanded=True):
            st.markdown(f"**Portal Families:** {', '.join(layer['portal_families'])}")
            st.markdown(f"**Exposes Without Local Request:** {layer['exposes_without_local_pra']}")
            st.markdown(f"**Audit Synergy Across Cheyenne & 23 Counties:** {layer['statewide_synergy']}")
            st.caption(f"Supports Operational Sections: {', '.join(str(s) for s in layer['sections_supported'])}")

with tab_cartography:
    st.subheader("Statewide Target Matrix (`wyoming/targets.json`) & Vendor PRA Draft Generator")
    targets_doc = load_targets()
    targets = targets_doc["targets"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Matrix Targets", len(targets))
    c2.metric("Counties Covered", sum(1 for t in targets if t["type"] == "county"))
    c3.metric(
        "Reviewed Official Entrypoints",
        sum(1 for t in targets if t.get("reviewed_official_urls")),
    )

    _render_df(
        [
            {
                "jurisdiction": t["jurisdiction"],
                "name": t["name"],
                "seat": t.get("county_seat_name") or "—",
                "verification": t["verification"],
                "reviewed_urls": ", ".join(t.get("reviewed_official_urls", [])) or "None yet",
                "candidate_domains": ", ".join(t.get("candidate_domains", [])),
            }
            for t in targets
        ]
    )

    db_candidate = ROOT / "cartography-results" / "wyoming_statewide_records_infrastructure.db"
    if db_candidate.is_file():
        st.markdown("#### Consolidated Cartography SQLite Bundle Found")
        with sqlite3.connect(db_candidate) as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(r) for r in conn.execute("SELECT * FROM jurisdiction_targets ORDER BY jurisdiction")]
        _render_df(rows)

    st.markdown("#### Draft W.S. 16-4-202 Request Generator by Vendor Class")
    col_j, col_v = st.columns(2)
    with col_j:
        selected_slug = st.selectbox(
            "Select Jurisdiction",
            options=[t["jurisdiction"] for t in targets],
            format_func=lambda s: next(t["name"] for t in targets if t["jurisdiction"] == s),
        )
    with col_v:
        selected_vendors = st.multiselect(
            "Detected / Assumed Vendor Stack",
            options=["govqa", "nextrequest", "tyler_itax_eagle", "greenwood_gis", "opengov_viewpoint", "smartgov", "esri_arcgis"],
            default=["tyler_itax_eagle"],
        )

    selected_target = next(t for t in targets if t["jurisdiction"] == selected_slug)
    drafts = generate_vendor_pra_templates(selected_target["name"], selected_vendors)
    for dr in drafts:
        st.text_area(
            f"Draft ({dr['template_class']} — Section {dr['section_id']})",
            value=dr["draft_text"],
            height=160,
        )

    st.markdown("#### Esri ArcGIS REST Safe GeoJSON Query URL Builder (Section 4)")
    arc_in = st.text_input(
        "HTTPS ArcGIS MapServer / FeatureServer URL",
        placeholder="https://gis.example.gov/arcgis/rest/services/Parcels/MapServer/0",
    )
    if arc_in.strip():
        try:
            st.code(build_arcgis_geojson_query_url(arc_in.strip()), language="text")
        except ValueError as exc:
            st.error(str(exc))

with tab_benford:
    st.subheader("Section 2: Check Register Benford's Law & Threshold-Splitting Detector")
    col_thr, col_amt, col_vnd = st.columns(3)
    threshold_val = col_thr.number_input("Primary Approval / Bid Threshold ($)", min_value=100.0, value=5000.0, step=500.0)
    amt_col = col_amt.text_input("Amount Column Header", value="Amount")
    vnd_col = col_vnd.text_input("Vendor Column Header", value="Vendor")

    uploaded_reg = st.file_uploader("Upload Accounts Payable Check Register CSV", type=["csv"], key="ap_csv")
    if uploaded_reg is not None:
        with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as tmp:
            tmp.write(uploaded_reg.getvalue())
            tmp_path = Path(tmp.name)
        try:
            report = audit_check_register_csv(tmp_path, amount_col=amt_col, vendor_col=vnd_col, threshold=float(threshold_val))
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Records Analyzed (> $10)", report["total_records_analyzed"])
            m2.metric("Benford MAD", f"{report['mean_absolute_deviation']:.4f}", report["conformity_band"])
            m3.metric("Chi-Squared (df=8)", f"{report['chi_squared_stat']:.2f}")
            m4.metric("Near-Threshold Invoices", report["threshold_clustering_count"])
            if report.get("benford_applicability_warning"):
                st.warning(report["benford_applicability_warning"])
            _render_df(
                [
                    {"Leading Digit": d, **vals}
                    for d, vals in report["digit_distribution"].items()
                ]
            )
            if report["vendor_split_candidates"]:
                st.markdown("##### Repeat-Vendor Near-Threshold Clusters (`candidate_unreviewed`)")
                st.json(report["vendor_split_candidates"])
        finally:
            tmp_path.unlink(missing_ok=True)
    else:
        st.caption("Upload a municipal/county check register CSV to compute first-digit Benford conformity and near-threshold clusters.")

with tab_pra:
    st.subheader("Section 7: W.S. 16-4-202 Statutory Clock Calculator & CASE/UCO Provenance Hasher")
    p1, p2, p3 = st.columns(3)
    sub_dt = p1.text_input("Date Submitted (ISO YYYY-MM-DD)", value="2026-09-01")
    ack_dt = p2.text_input("Date Acknowledged (blank = unacknowledged)", value="2026-09-09")
    ful_dt = p3.text_input("Date Fulfilled / Closed (blank = still open)", value="2026-10-05")
    try:
        clock_res = audit_ws_16_4_202_timeline(
            submitted_iso=sub_dt,
            ack_iso=ack_dt or None,
            fulfilled_iso=ful_dt or None,
            reference_now_iso="2026-11-07T00:00:00+00:00",
        )
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Ack Business Days (WY)", clock_res["ack_business_days"])
        k2.metric("> 7 Business-Day Ack Flag", str(clock_res["ws_16_4_202_7bday_ack_violation"]))
        k3.metric("Fulfillment Calendar Days", clock_res["fulfill_elapsed_days"])
        k4.metric("> 30 Calendar-Day Flag", str(clock_res["ws_16_4_202_30day_violation"]))
        st.caption(clock_res["statutory_caveat"])
    except ValueError as exc:
        st.error(f"Invalid date format: {exc}")

    st.markdown("#### GovQA / NextRequest Master Ticket Log CSV Batch Audit")
    govqa_csv = st.file_uploader("Upload GovQA / NextRequest Ticket CSV", type=["csv"], key="govqa_csv")
    if govqa_csv is not None:
        with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as tmp:
            tmp.write(govqa_csv.getvalue())
            gpath = Path(tmp.name)
        try:
            st.json(audit_govqa_master_log(gpath))
        finally:
            gpath.unlink(missing_ok=True)

    st.markdown("#### Cryptographic Provenance Manifest Generator (SHA-256 + CASE/UCO JSON-LD)")
    prov_file = st.file_uploader("Select local PDF/CSV/JSON artifact to hash in memory (not stored on server)", key="prov_up")
    prov_url = st.text_input("Source URL of captured record", value="https://example.gov/agenda.pdf")
    if prov_file is not None:
        raw_bytes = prov_file.getvalue()
        digest = hashlib.sha256(raw_bytes).hexdigest()
        manifest_preview = {
            "@context": "https://ontology.caseontology.org/case/case.jsonld",
            "@type": "uco-observable:ObservableObject",
            "section_audited": "Section 7: Browser Provenance Hash",
            "file_path": prov_file.name,
            "file_size_bytes": len(raw_bytes),
            "source_url": prov_url,
            "sha256_hash": digest,
            "verification_cmd": f"sha256sum '{prov_file.name}' # Expected: {digest}",
        }
        st.code(json.dumps(manifest_preview, indent=2), language="json")
        st.download_button(
            "Download .provenance.json sidecar",
            data=json.dumps(manifest_preview, indent=2),
            file_name=f"{prov_file.name}.provenance.json",
            mime="application/json",
        )

with tab_sections:
    st.subheader("Section 1: Annexation Statutory Prerequisite Checklist & Draft 3-Beat Script")
    a_col1, a_col2, a_col3 = st.columns(3)
    ag_item = a_col1.text_input("Agenda Item / Ordinance #", value="Ordinance [NUMBER]")
    ag_body = a_col2.text_input("Governing Body", value="City Council")
    ag_date = a_col3.text_input("Meeting Date", value="2026-11-09")

    pkt_state = {}
    chk_cols = st.columns(2)
    for idx, (key, statute, desc) in enumerate(ANNEXATION_PREREQUISITES):
        pkt_state[key] = chk_cols[idx % 2].checkbox(f"[{statute}] {desc}", value=True)

    annex_res = audit_annexation_prerequisites(pkt_state, agenda_item=ag_item, governing_body=ag_body, meeting_date=ag_date)
    st.caption(
        f"Verified prerequisites: {annex_res['verified_prerequisites_count']} / {len(ANNEXATION_PREREQUISITES)} "
        f"| Script word count: {annex_res['podium_script_word_count']} words (<= 350 limit: {annex_res['podium_script_within_350_words']})"
    )
    if annex_res["missing_prerequisites_count"] > 0:
        st.text_area("Draft 3-Beat Podium Script (Human Review Required)", value=annex_res["draft_podium_script"], height=210)
        st.text_area("Draft Written Notice of Record Gap (Human Review Required)", value=annex_res["draft_written_notice"], height=180)

    st.markdown("---")
    st.subheader("Sections 3, 5, 6 CSV Audit Runners")
    c_perm, c_lcrr, c_alpr = st.columns(3)
    with c_perm:
        p_up = st.file_uploader("Section 3: OpenGov Permits CSV", type=["csv"], key="sec3_csv")
        if p_up is not None:
            with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as tmp:
                tmp.write(p_up.getvalue())
                pp = Path(tmp.name)
            try:
                st.json(audit_permitting_csv(pp))
            finally:
                pp.unlink(missing_ok=True)
    with c_lcrr:
        l_up = st.file_uploader("Section 5: LCRR Service-Line CSV", type=["csv"], key="sec5_csv")
        if l_up is not None:
            import csv as _csv
            rows_l = list(_csv.DictReader(io.StringIO(l_up.getvalue().decode("utf-8-sig", errors="replace"))))
            st.json(audit_lcrr_service_lines(rows_l))
    with c_alpr:
        al_up = st.file_uploader("Section 6: ALPR Audit Log CSV", type=["csv"], key="sec6_csv")
        if al_up is not None:
            with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as tmp:
                tmp.write(al_up.getvalue())
                ap = Path(tmp.name)
            try:
                st.json(audit_alpr_logs(ap))
            finally:
                ap.unlink(missing_ok=True)
