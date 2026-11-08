# Statewide Cross-Jurisdictional Audit Engine & Passive OSINT Cartography

- **Date:** 2026-11-07 (America/Denver)
- **Scope:** `promethean/forensic_audit.py`, `wyoming/targets.json`, `tools/passive_cartography.py`,
  `.github/workflows/passive_cartography.yml`, `tools/colab_statewide_cartography.ipynb`,
  `pages/27_Statewide_Audit_Cartography.py`, and `tools/test_statewide_audit_cartography.py`.

## Overview

This additive subsystem connects the repository's 126-jurisdiction Wyoming registry (`wyoming/registry.json`)
and Promethean evidence SDK (`promethean/`) to two capabilities:

1. **Lineage A Statewide Forensic Audit Engine (`promethean/forensic_audit.py`)**
   - **Eight State & Federal Mirror Ledgers (`MIRROR_LEDGERS`)**: Triangulates municipal/county records
     against statutory state and federal repositories (WY DOR CAMA, MSRB EMMA, GSA Federal Audit
     Clearinghouse / USASpending, EPA ECHO / SDWIS / WDEQ, State Engineer SEO / WOGCC, FAA Part 77
     OE/AAA, FCC ULS / BDC, and WYSOS Business Center / County UCC indices).
   - **Cryptographic Provenance Packager (`package_osint_artifact` & `verify_osint_provenance`)**:
     Streams 64 KiB SHA-256 digests and emits CASE/UCO JSON-LD `.provenance.json` sidecar manifests
     with sanitized response headers so post-capture alterations are mathematically verifiable.
   - **Seven Operational Section Runners**:
     - *Section 1 (Legislative / Annexations)*: `audit_annexation_prerequisites` — evaluates W.S.
       15-1-402 through 15-1-405 packet prerequisites and drafts a human-reviewable Notice of Gap +
       `<= 350`-word three-beat comment script (`sent_by_this_tool = False`).
     - *Section 2 (Finance / Check Registers)*: `audit_check_register_csv` — first-digit Benford's Law
       conformity (MAD + Pearson Chi-Squared, df=8), multi-threshold invoice-clustering scanner, and
       optional WYSOS entity good-standing cross-check.
     - *Section 3 (Permitting / Development)*: `audit_permitting_csv` — compares permit issue dates
       against external FAA Part 77 / grading anchors and declared valuation against CAMA deltas.
     - *Section 4 (GIS / Assessor / Tax)*: `build_arcgis_geojson_query_url` +
       `audit_gis_tax_classifications` — bounded HTTPS Esri ArcGIS GeoJSON query builder and
       agricultural-assessment cross-reference runner.
     - *Section 5 (Utilities / Environmental Health)*: `audit_lcrr_service_lines` +
       `audit_water_advisory_timeline` — flags pre-1986 structures marked `Non-Lead` without recorded
       verification and checks 40 CFR Part 141 public-notice clocks.
     - *Section 6 (Public Safety / ALPR)*: `audit_alpr_logs` — inspects ALPR audit CSVs for blank or
       placeholder reason strings and bulk device sweeps lacking a structured CAD/case reference,
       hashing operator IDs (`SHA-256` prefix) so personal names never appear in output.
     - *Section 7 (Public Records / Custodians)*: `audit_ws_16_4_202_timeline` +
       `audit_govqa_master_log` — calculates both Wyoming business days (`W.S. 8-4-101` holiday
       calendar, 7-business-day acknowledgment rule) and calendar days (30-day release clock).

2. **Hybrid "GitHub Actions Matrix → Colab / Streamlit" Passive Cartography Pipeline (`tools/passive_cartography.py`)**
   - **Target Matrix (`wyoming/targets.json`)**: 24 bounded targets (`wyo-gov` state portal + all 23
     Wyoming counties), reconciled 1-to-1 with `wyoming/registry.json` county slugs and seats, and
     preserving `reviewed_official_urls` from `wyoming/source-reviews.json` separately from
     unverified `candidate_domains`.
   - **GitHub Actions Matrix Workflow (`.github/workflows/passive_cartography.yml`)**:
     - Runs offline unit tests on push/PR to relevant paths.
     - On manual `workflow_dispatch`, fans out up to 20 concurrent Ubuntu runners (`fail-fast: false`)
       across `wyo-gov` + 23 counties, writes SHA-256 provenance-wrapped JSON per target, and runs a
       `consolidate` job that builds `wyoming_statewide_records_infrastructure.db` +
       `consolidated_cartography.json` + `vendor_pra_matrix.md` as a downloadable artifact bundle.
   - **Colab & Streamlit Post-Processing**:
     - `tools/colab_statewide_cartography.ipynb`: loads the consolidated SQLite bundle in Google Colab
       for cross-county SQLite/pandas querying and section audits.
     - `pages/27_Statewide_Audit_Cartography.py`: standalone interactive Streamlit workspace.

## Guardrails & Honesty Boundaries

1. **Passive OSINT only (`validate_spiderfoot_modules`)**: Active port scanning (`sfp_portscan_tcp`,
   `sfp_nmap`), vulnerability probing (`sfp_nuclei`, `sfp_vuln`), and brute-forcing are hard-blocked
   in code (`ValueError`) to comply with `LEGAL.md` and GitHub/Google Cloud Acceptable Use Policies.
2. **Personal-data redaction (`LEGAL.md` §5)**: `filter_institutional_contacts` drops personal
   individual email addresses and retains only generic institutional role mailboxes (`clerk@`,
   `records@`, `assessor@`, `treasurer@`, `gis@`, `info@`, `publicrecords@`).
3. **Human-in-the-loop drafts (`LEGAL.md` §4)**: Every W.S. 16-4-202 request, Notice of Gap, and
   podium script is a draft (`sent_by_this_tool: false`). No SMTP, portal submission, or automated
   outbound messaging exists.
4. **Candidate-only analytical leads (`docs/ARCHITECTURE-TIERS.md` §6)**: Every statistical or
   timeline flag carries `status: "candidate_unreviewed"`. Benford nonconformity (`MAD > 0.015`),
   near-threshold invoice clusters, and >30-day open tickets are triage leads, not proof of
   wrongdoing or statutory violation (e.g., W.S. 16-4-202 permits documented good-cause extensions).
5. **Tier-4 binary hygiene (`docs/ARCHITECTURE-TIERS.md`)**: `.github/workflows/passive_cartography.yml`
   runs with `permissions: contents: read` and uploads `wyoming_statewide_records_infrastructure.db`
   as a workflow artifact rather than committing binary SQLite blobs onto `main`.
6. **Verification boundary**: From this sandbox, outbound internet is restricted to GitHub/PyPI/npm
   hosts, so live county DNS/CT/HTTPS scans were **not** executed here. Offline manifest generation,
   end-to-end 24-target SQLite consolidation, provenance tamper rejection, all 7 section runners,
   notebook structure, and Streamlit `AppTest` rendering are verified offline by
   `tools/test_statewide_audit_cartography.py`.

## Commands

```bash
# Run offline unit & integration test suite
python3 -m unittest discover -s tools -p 'test_statewide_audit_cartography.py' -v

# List the 8 State & Federal OSINT mirror ledgers
python3 -m promethean.forensic_audit mirror-ledgers

# Hash an ingested PDF/CSV/JSON with SHA-256 + CASE/UCO provenance sidecar
python3 -m promethean.forensic_audit package-provenance \
  --file path/to/packet.pdf \
  --source-url 'https://cheyenne.granicus.com/...' \
  --section-tag 'Section 1: Council Packet'

# Verify artifact integrity against its .provenance.json sidecar
python3 -m promethean.forensic_audit verify-provenance --manifest path/to/packet.pdf.provenance.json

# Audit an Accounts Payable check register CSV (Section 2)
python3 -m promethean.forensic_audit audit-check-register --csv check_register.csv --threshold 5000

# Audit W.S. 16-4-202 statutory clocks (Section 7)
python3 -m promethean.forensic_audit audit-pra-timeline --submitted 2026-09-01 --ack 2026-09-04 --fulfilled 2026-10-08

# Build an offline 24-target cartography baseline & consolidate into SQLite + PRA Matrix
python3 tools/passive_cartography.py scan-all --offline --output-dir /tmp/carto/raw
python3 tools/passive_cartography.py consolidate --input-dir /tmp/carto/raw --db /tmp/carto/wyoming_statewide_records_infrastructure.db
```
