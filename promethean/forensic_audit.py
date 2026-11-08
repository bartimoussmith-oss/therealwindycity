"""Lineage A: Statewide Cross-Jurisdictional Mirror Ledger & Seven-Section Forensic Audit Engine.

Implements:
  - Part I: Eight Cross-Jurisdictional State & Federal Mirror Ledgers (Triangulated Verification Matrix)
  - Part II: Deterministic Audit Runners for all Seven Municipal/County Operational Sections
  - Part III: Automated Cryptographic Provenance Packager (SHA-256 + CASE/UCO JSON-LD)
              Benford's Law & Threshold-Splitting Detector (MAD + Chi-Squared + WYSOS check)
              Veracity Timeline Auditor (W.S. 16-4-202 7-business-day & 30-calendar-day clocks)

Integrity & Legal Guardrails (LEGAL.md, promethean/README.md, docs/ARCHITECTURE-TIERS.md):
  - Pure Python 3.11+ standard library; zero import-time network calls or filesystem writes.
  - All analytical flags carry status="candidate_unreviewed". Statistical anomalies, missing fields,
    and elapsed-clock counts are research/audit leads requiring human verification of primary records,
    never automatic accusations or legal determinations.
  - Notice of Statutory Defect and 3-minute podium scripts are human-reviewed DRAFTS only
    (sent_by_this_tool=False; never auto-submitted).
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shlex
import sys
from typing import Any, Iterable, Mapping
from urllib.parse import urlencode, urlsplit

SENSITIVE_HTTP_HEADERS = frozenset({
    "authorization",
    "cookie",
    "set-cookie",
    "proxy-authorization",
    "x-api-key",
    "x-auth-token",
    "x-amz-security-token",
})

# Chi-squared critical values for 8 degrees of freedom (first digits 1..9)
CHI_SQ_CRIT_DF8_P05 = 15.5073
CHI_SQ_CRIT_DF8_P01 = 20.0902

CANDIDATE_WARNING = (
    "All outputs are candidate_unreviewed audit leads derived from supplied inputs. "
    "Verify original certified records and statutory exceptions before asserting any defect."
)


# ---------------------------------------------------------------------------
# PART I: Eight Cross-Jurisdictional State & Federal Mirror Ledgers
# ---------------------------------------------------------------------------

MIRROR_LEDGERS: tuple[dict[str, Any], ...] = (
    {
        "layer_id": 1,
        "slug": "state_cama_backbone",
        "name": "State CAMA Mass Appraisal Backbone",
        "primary_endpoints": [
            "https://wyo-prop-div.wyo.gov",
        ],
        "portal_families": ["County iTax", "Greenwood Mapping", "Esri ArcGIS MapServer", "WY DOR Property Tax Division"],
        "exposes_without_local_pra": (
            "All 23 Wyoming counties use a state-supported Computer-Assisted Mass Appraisal (CAMA) "
            "database maintained with the WY Dept. of Revenue Property Tax Division Technical Services Group."
        ),
        "statewide_synergy": (
            "Standardized underlying CAMA schema allows a single structured W.S. 16-4-202 parcel/valuation "
            "export query pattern to apply across all 23 County Assessors."
        ),
        "sections_supported": [3, 4, 5],
    },
    {
        "layer_id": 2,
        "slug": "msrb_emma_disclosures",
        "name": "Municipal Bond & Continuing Disclosures (MSRB EMMA)",
        "primary_endpoints": [
            "https://emma.msrb.org",
        ],
        "portal_families": ["MSRB EMMA", "SEC Rule 15c2-12 Continuing Disclosures"],
        "exposes_without_local_pra": (
            "Audited financial statements (ACFRs), utility/BOPU water and sewer revenue bond covenants, "
            "special improvement districts (SIDs), and mandatory Material Event Notices."
        ),
        "statewide_synergy": (
            "Cross-checks local infrastructure liability disclosures, debt-service coverage ratios, "
            "and material litigation against federal municipal-securities filings."
        ),
        "sections_supported": [2, 5],
    },
    {
        "layer_id": 3,
        "slug": "federal_audit_clearinghouse",
        "name": "Federal Audit Clearinghouse (Single Audits) & USASpending",
        "primary_endpoints": [
            "https://fac.gov",
            "https://www.usaspending.gov",
        ],
        "portal_families": ["GSA FAC API (Form SF-SAC)", "USASpending Sub-Awards", "SAM.gov Exclusions"],
        "exposes_without_local_pra": (
            "Annual Single Audit filings (Form SF-SAC) for municipalities, counties, school districts, "
            "and special districts expending above the 2 CFR Part 200 threshold ($750k/$1M) in federal awards."
        ),
        "statewide_synergy": (
            "Surfaces auditor-reported Internal Control Material Weaknesses, Significant Deficiencies, "
            "unspent grant clawback risks, and downloadable JSON/CSV SEFA schedules."
        ),
        "sections_supported": [2],
    },
    {
        "layer_id": 4,
        "slug": "epa_echo_sdwis_wdeq",
        "name": "EPA ECHO, SDWIS & WDEQ Environmental Portals",
        "primary_endpoints": [
            "https://echo.epa.gov",
            "https://deq.wyoming.gov",
        ],
        "portal_families": ["EPA ECHO API", "EPA SDWIS Drinking Water", "WDEQ Title V / WYPDES / NPDES / UST"],
        "exposes_without_local_pra": (
            "Wastewater discharge monitoring reports (DMRs) and exceedances, lead/copper action-level "
            "reports, underground storage tank (UST) leaks, stormwater grading permits, and industrial air permits."
        ),
        "statewide_synergy": (
            "Cross-checks municipal utility and BOPU water-quality claims against federal lab submissions "
            "and 40 CFR Part 141 public-notification clocks."
        ),
        "sections_supported": [3, 5],
    },
    {
        "layer_id": 5,
        "slug": "seo_wogcc_water",
        "name": "Wyoming State Engineer's Office (SEO) & WOGCC",
        "primary_endpoints": [
            "https://seoweb.wyo.gov",
            "https://wogcc.wyo.gov",
        ],
        "portal_families": ["SEO e-Permit", "WOGCC Well & Surface-Use Records"],
        "exposes_without_local_pra": (
            "Priority-date water rights, commercial groundwater well permits, produced-water volumes, "
            "surface-use agreements, and industrial/data-center water transfers."
        ),
        "statewide_synergy": (
            "Documents water consumption and well-drawdown footprints for commercial annexations and "
            "industrial sites prior to or alongside local governing-body agendas."
        ),
        "sections_supported": [1, 4, 5],
    },
    {
        "layer_id": 6,
        "slug": "faa_part77_oeaaa",
        "name": "FAA Part 77 Obstruction Evaluation (OE/AAA)",
        "primary_endpoints": [
            "https://oeaaa.faa.gov",
        ],
        "portal_families": ["FAA OE/AAA Form 7460-1 Filings"],
        "exposes_without_local_pra": (
            "Mandatory federal airspace filings for construction cranes, communications towers, wind turbines, "
            "and tall commercial structures near regional airports (e.g., CYS, CPR, JAC, GCC, RKS, SHR)."
        ),
        "statewide_synergy": (
            "Provides a 60-to-120-day lead indicator and independent work-schedule anchor for major "
            "commercial, telecom, and data-center construction relative to local building permit dates."
        ),
        "sections_supported": [3],
    },
    {
        "layer_id": 7,
        "slug": "fcc_uls_bdc",
        "name": "FCC Universal Licensing System (ULS) & Broadband Map",
        "primary_endpoints": [
            "https://wireless2.fcc.gov",
            "https://broadbandmap.fcc.gov",
        ],
        "portal_families": ["FCC ULS", "FCC BDC"],
        "exposes_without_local_pra": (
            "Public-safety, sheriff, fire, municipal, utility SCADA, and private industrial VHF/UHF/microwave "
            "transmitter coordinates, frequencies, call signs, and license expiration dates."
        ),
        "statewide_synergy": (
            "Maps public-safety and utility telemetry topology and flags expired public/private repeater "
            "authorizations without filing a local records request."
        ),
        "sections_supported": [5, 6],
    },
    {
        "layer_id": 8,
        "slug": "wysos_ucc_liens",
        "name": "Wyoming Secretary of State (WYSOS) & County Clerk UCC/Recording Indices",
        "primary_endpoints": [
            "https://wyobiz.wyo.gov",
        ],
        "portal_families": ["WYSOS Business Center", "UCC Financing Statements", "County Clerk Land/Deed Indices"],
        "exposes_without_local_pra": (
            "Corporate good-standing status, registered agents, formation dates, administrative dissolutions, "
            "tax/annual-report delinquencies, and UCC equipment financing statements."
        ),
        "statewide_synergy": (
            "Flags public-contract vendors, franchisees, or annexation applicant LLCs that are administratively "
            "dissolved or not in good standing at the time of bid, disbursement, or application."
        ),
        "sections_supported": [1, 2, 4],
    },
)

OPERATIONAL_SECTIONS: tuple[dict[str, Any], ...] = (
    {
        "section_id": 1,
        "slug": "legislative_agendas_annexations",
        "title": "Legislative, Agendas & Annexations (City Council / County Commissioners)",
        "target_stack": ["Granicus", "CivicPlus AgendaCenter", "BoardDocs", "Municode", "YouTube Live"],
        "statutory_anchors": ["W.S. 15-1-402 through 15-1-405 (Annexation)", "W.S. 16-4-401 et seq. (Public Meetings Act)"],
        "frameworks": ["Systemic Resonance Mapper", "Agenda Objection Dossier Builder"],
        "mirror_ledger_ids": [5, 8],
        "runner": "audit_annexation_prerequisites",
    },
    {
        "section_id": 2,
        "slug": "finance_treasurer_purchasing",
        "title": "Finance, Treasurer, Purchasing & Check Registers",
        "target_stack": ["Tyler Technologies ERP", "wyopen.gov", "Socrata", "OpenGov", "Monthly Warrant Lists"],
        "statutory_anchors": ["W.S. 15-1-113 (Competitive Bidding)", "W.S. 16-4-101 et seq. (Uniform Municipal Fiscal Procedures)"],
        "frameworks": ["Benford Ledger Anomaly Detector", "Threshold-Splitting Scanner", "WYSOS Entity Verifier"],
        "mirror_ledger_ids": [2, 3, 8],
        "runner": "audit_check_register_csv",
    },
    {
        "section_id": 3,
        "slug": "permitting_code_development",
        "title": "Permitting, Code Enforcement & Development Services",
        "target_stack": ["OpenGov / ViewPoint Cloud", "SmartGov", "Tyler EnerGov"],
        "statutory_anchors": ["Local Building Codes", "FAA 14 CFR Part 77", "WDEQ WYPDES Stormwater Construction Permits"],
        "frameworks": ["Veracity Timeline Auditor", "Valuation Arbitrage Cross-Check"],
        "mirror_ledger_ids": [1, 4, 6],
        "runner": "audit_permitting_csv",
    },
    {
        "section_id": 4,
        "slug": "gis_land_assessor_tax",
        "title": "GIS, Land Records, Assessor & Tax Rolls",
        "target_stack": ["Esri ArcGIS Server REST", "State DOR CAMA", "Tyler iTax", "Greenwood Mapping"],
        "statutory_anchors": ["W.S. 39-13-101 et seq. (Ad Valorem Taxation)", "W.S. 39-13-103(b)(x) (Agricultural Land Assessment)"],
        "frameworks": ["Spatial & Tax Classification Audit", "Direct GeoJSON Query Builder"],
        "mirror_ledger_ids": [1, 5, 8],
        "runner": "audit_gis_tax_classifications",
    },
    {
        "section_id": 5,
        "slug": "public_works_utilities_env_health",
        "title": "Public Works, Utilities (BOPU) & Environmental Health",
        "target_stack": ["Utility Billing / SCADA Registries", "ArcGIS Utility Network", "HSGovTech (HealthSpace)"],
        "statutory_anchors": ["40 CFR Part 141 (Safe Drinking Water Act / LCRR & Public Notification)", "Clean Water Act NPDES"],
        "frameworks": ["Infrastructure & Contaminant Delta Audit", "Veracity Timeline Auditor"],
        "mirror_ledger_ids": [1, 2, 4, 5, 7],
        "runner": "audit_lcrr_service_lines",
    },
    {
        "section_id": 6,
        "slug": "public_safety_law_enforcement_courts",
        "title": "Public Safety, Law Enforcement & Municipal Courts",
        "target_stack": ["Flock Safety ALPR Portals", "Citizen Connect / Motorola CAD", "Municipal & Circuit Court Dockets"],
        "statutory_anchors": ["Wyoming Constitution Art. 1, Sec. 4", "W.S. 7-17-101 et seq.", "CJIS / POST Audit Rules"],
        "frameworks": ["ALPR Audit-Log Reason Inspector", "Statutory Warrant Alignment Check"],
        "mirror_ledger_ids": [7],
        "runner": "audit_alpr_logs",
    },
    {
        "section_id": 7,
        "slug": "public_records_intake_it_governance",
        "title": "Public Records Intake & IT Governance (Meta-Auditing Custodians)",
        "target_stack": ["Granicus GovQA", "NextRequest", "Mimecast SMTP Gateways", "Cloudflare / IIS Headers"],
        "statutory_anchors": ["W.S. 16-4-201 through 16-4-205 (Wyoming Public Records Act; 7-business-day ack / 30-calendar-day clock)"],
        "frameworks": ["Veracity Timeline Auditor", "Cryptographic Provenance Packager (CASE/UCO)"],
        "mirror_ledger_ids": [1, 2, 3, 4, 5, 6, 7, 8],
        "runner": "audit_ws_16_4_202_timeline",
    },
)


def triangulate_mirror_ledgers(section_id: int | None = None, keyword: str | None = None) -> list[dict[str, Any]]:
    """Return external State/Federal mirror ledgers matching an operational section or keyword."""
    results: list[dict[str, Any]] = []
    kw = (keyword or "").strip().lower()
    for layer in MIRROR_LEDGERS:
        if section_id is not None and section_id not in layer["sections_supported"]:
            continue
        if kw:
            haystack = " ".join([
                layer["slug"],
                layer["name"],
                " ".join(layer["primary_endpoints"]),
                " ".join(layer["portal_families"]),
                layer["exposes_without_local_pra"],
                layer["statewide_synergy"],
            ]).lower()
            if kw not in haystack:
                continue
        results.append(dict(layer))
    return results


# ---------------------------------------------------------------------------
# 1. CRYPTOGRAPHIC PROVENANCE PACKAGER (SHA-256 + CASE/UCO Manifest)
# ---------------------------------------------------------------------------

def _sanitize_http_headers(headers: Mapping[str, Any] | None) -> dict[str, str]:
    if not headers:
        return {}
    cleaned: dict[str, str] = {}
    for k, v in headers.items():
        key = str(k).strip()
        if not key or key.lower() in SENSITIVE_HTTP_HEADERS:
            continue
        if any(tok in key.lower() for tok in ("secret", "token", "password", "cookie", "auth")):
            continue
        cleaned[key] = str(v).strip()[:512]
    return cleaned


def package_osint_artifact(
    filepath: str | Path,
    source_url: str,
    section_tag: str,
    http_headers: Mapping[str, Any] | None = None,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Hash an ingested OSINT/public-record file (SHA-256) and emit a CASE/UCO JSON-LD sidecar manifest."""
    target = Path(filepath)
    if not target.is_file():
        raise FileNotFoundError(f"Artifact not found: {filepath}")

    sha256 = hashlib.sha256()
    size_bytes = 0
    with target.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
            size_bytes += len(chunk)
    digest = sha256.hexdigest()

    filepath_str = str(filepath)
    quoted_path = shlex.quote(filepath_str)
    manifest: dict[str, Any] = {
        "@context": "https://ontology.caseontology.org/case/case.jsonld",
        "@type": "uco-observable:ObservableObject",
        "section_audited": section_tag,
        "file_path": filepath_str,
        "file_size_bytes": size_bytes,
        "source_url": str(source_url),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "sha256_hash": digest,
        "verification_cmd": f"sha256sum {quoted_path} # Expected: {digest}",
    }
    safe_headers = _sanitize_http_headers(http_headers)
    if safe_headers:
        manifest["http_response_headers"] = safe_headers

    out_path = Path(manifest_path) if manifest_path is not None else Path(f"{filepath_str}.provenance.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as out:
        json.dump(manifest, out, indent=2)
    return manifest


def verify_osint_provenance(manifest_path: str | Path, artifact_path: str | Path | None = None) -> dict[str, Any]:
    """Re-compute SHA-256 against a `.provenance.json` manifest to prove post-capture integrity."""
    mpath = Path(manifest_path)
    if not mpath.is_file():
        raise FileNotFoundError(f"Provenance manifest not found: {manifest_path}")
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    expected = str(manifest.get("sha256_hash", "")).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Manifest lacks a valid 64-hex-character sha256_hash")

    target = Path(artifact_path) if artifact_path is not None else Path(manifest["file_path"])
    if not target.is_file():
        sibling = mpath.with_name(mpath.name.removesuffix(".provenance.json"))
        if sibling.is_file():
            target = sibling
        else:
            return {
                "verified": False,
                "status": "missing_artifact",
                "manifest_path": str(mpath),
                "expected_sha256": expected,
                "actual_sha256": None,
            }

    sha256 = hashlib.sha256()
    actual_bytes = 0
    with target.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
            actual_bytes += len(chunk)
    actual = sha256.hexdigest()
    expected_bytes = manifest.get("file_size_bytes")
    bytes_match = expected_bytes is None or int(expected_bytes) == actual_bytes
    matched = (actual == expected) and bytes_match
    return {
        "verified": matched,
        "status": "intact" if matched else "altered_after_capture",
        "manifest_path": str(mpath),
        "artifact_path": str(target),
        "source_url": manifest.get("source_url"),
        "retrieved_at_utc": manifest.get("retrieved_at_utc"),
        "expected_sha256": expected,
        "actual_sha256": actual,
        "bytes_match": bytes_match,
    }


# ---------------------------------------------------------------------------
# 2. SECTION 2: BENFORD LEDGER ANOMALY, THRESHOLD-SPLITTING & ENTITY CHECK
# ---------------------------------------------------------------------------

def _first_significant_digit(value: float) -> int:
    """Return leading digit 1..9 for any positive finite float without scientific-notation string bugs."""
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError("Value must be positive and finite")
    sci = f"{value:.12e}"
    return int(sci[0])


def _normalize_entity_name(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


def _parse_currency(raw: Any) -> float | None:
    s = str(raw if raw is not None else "").strip()
    if not s:
        return None
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    s = s.replace("$", "").replace(",", "").strip()
    try:
        val = float(s)
    except ValueError:
        return None
    if not math.isfinite(val):
        return None
    return -val if negative else val


def audit_check_register_csv(
    csv_path: str | Path,
    amount_col: str = "Amount",
    vendor_col: str = "Vendor",
    threshold: float = 5000.0,
    secondary_thresholds: Iterable[float] = (25000.0,),
    date_col: str = "Check Date",
    invoice_col: str = "Invoice Number",
    min_amount: float = 10.0,
    wysos_entities: Mapping[str, Mapping[str, Any] | str] | None = None,
) -> dict[str, Any]:
    """Audit an Accounts Payable check register CSV for Benford's Law deviations,
    threshold-proximity clustering (potential invoice splitting), and inactive WYSOS vendors.
    """
    if threshold <= 0:
        raise ValueError("threshold must be positive")

    all_thresholds = sorted({float(threshold), *(float(t) for t in secondary_thresholds if float(t) > 0)})
    normalized_wysos: dict[str, dict[str, Any]] = {}
    if wysos_entities:
        for name, meta in wysos_entities.items():
            key = _normalize_entity_name(name)
            if not key:
                continue
            if isinstance(meta, Mapping):
                normalized_wysos[key] = dict(meta)
            else:
                normalized_wysos[key] = {"status": str(meta)}

    amounts: list[float] = []
    near_primary_threshold: list[tuple[str, float]] = []
    vendor_threshold_buckets: dict[tuple[str, float], list[dict[str, Any]]] = defaultdict(list)
    entity_flags: list[dict[str, Any]] = []
    skipped_rows = 0
    total_rows_read = 0

    with Path(csv_path).open("r", encoding="utf-8-sig", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_rows_read += 1
            val = _parse_currency(row.get(amount_col, ""))
            if val is None or val <= min_amount:
                skipped_rows += 1
                continue

            vendor = (row.get(vendor_col) or row.get("Vendor Name") or "Unknown").strip() or "Unknown"
            check_date = (row.get(date_col) or "").strip()
            invoice_no = (row.get(invoice_col) or "").strip()
            amounts.append(val)

            if (threshold * 0.90) <= val < threshold:
                near_primary_threshold.append((vendor, round(val, 2)))

            for t in all_thresholds:
                if (t * 0.90) <= val < t:
                    vendor_threshold_buckets[(vendor, t)].append({
                        "amount": round(val, 2),
                        "date": check_date,
                        "invoice": invoice_no,
                    })

            if normalized_wysos:
                vkey = _normalize_entity_name(vendor)
                meta = normalized_wysos.get(vkey)
                if meta:
                    st_text = str(meta.get("status", "")).strip()
                    low_st = st_text.lower()
                    has_bad_marker = any(
                        bad in low_st
                        for bad in ("inactive", "dissolv", "delinquent", "revok", "forfeit", "suspend", "withdraw", "not found")
                    )
                    is_good_standing = (
                        not has_bad_marker
                        and bool(re.search(r"\b(?:active|good\s+standing)\b", low_st))
                    )
                    if st_text and not is_good_standing:
                        entity_flags.append({
                            "vendor": vendor,
                            "amount": round(val, 2),
                            "date": check_date,
                            "invoice": invoice_no,
                            "wysos_status": st_text,
                            "filing_id": meta.get("filing_id"),
                            "status": "candidate_unreviewed",
                        })

    first_digits = [_first_significant_digit(a) for a in amounts if a > 0]
    counts = Counter(first_digits)
    total = len(first_digits)
    mad_sum = 0.0
    chi_sq = 0.0
    benford_report: dict[str, dict[str, Any]] = {}

    for d in range(1, 10):
        expected = math.log10(1 + 1 / d)
        obs_count = counts.get(d, 0)
        observed = obs_count / total if total else 0.0
        mad_sum += abs(observed - expected)
        if total:
            exp_count = expected * total
            chi_sq += ((obs_count - exp_count) ** 2) / exp_count
        benford_report[str(d)] = {
            "count": obs_count,
            "expected_pct": round(expected * 100, 2),
            "observed_pct": round(observed * 100, 2),
        }

    mad = mad_sum / 9.0 if total else 0.0
    if total == 0:
        conformity_band = "insufficient_sample"
    elif mad <= 0.006:
        conformity_band = "close_conformity"
    elif mad <= 0.012:
        conformity_band = "acceptable_conformity"
    elif mad <= 0.015:
        conformity_band = "marginally_acceptable"
    else:
        conformity_band = "nonconformity"

    magnitude_span = round(math.log10(max(amounts) / min(amounts)), 2) if len(amounts) >= 2 and min(amounts) > 0 else 0.0
    applicability_warning = None
    if 0 < total < 100:
        applicability_warning = "Sample has fewer than 100 positive disbursements (> min_amount); interpret Benford statistics cautiously."
    elif total >= 100 and magnitude_span < 2.0:
        applicability_warning = "Amounts span fewer than 2 orders of magnitude; Benford's Law conformity may be distorted by narrow price bands."

    vendor_split_candidates: list[dict[str, Any]] = []
    for (vendor, t), items in sorted(vendor_threshold_buckets.items(), key=lambda kv: (-len(kv[1]), kv[0][0])):
        total_cluster = round(sum(x["amount"] for x in items), 2)
        if len(items) >= 2 and total_cluster >= t:
            vendor_split_candidates.append({
                "vendor": vendor,
                "threshold_tested": t,
                "near_threshold_invoice_count": len(items),
                "combined_amount": total_cluster,
                "invoices": items[:10],
                "status": "candidate_unreviewed",
            })

    return {
        "status": "candidate_unreviewed",
        "total_rows_read": total_rows_read,
        "skipped_rows_lte_min_or_non_numeric": skipped_rows,
        "total_records_analyzed": total,
        "orders_of_magnitude_span": magnitude_span,
        "mean_absolute_deviation": round(mad, 4),
        "conformity_band": conformity_band,
        "nonconformity_flag": bool(total > 0 and mad > 0.015),
        "chi_squared_stat": round(chi_sq, 4),
        "chi_squared_critical_p05": CHI_SQ_CRIT_DF8_P05,
        "chi_squared_critical_p01": CHI_SQ_CRIT_DF8_P01,
        "chi_squared_p05_flag": bool(total >= 50 and chi_sq > CHI_SQ_CRIT_DF8_P05),
        "benford_applicability_warning": applicability_warning,
        "threshold_tested": threshold,
        "threshold_clustering_count": len(near_primary_threshold),
        "top_threshold_clusters": near_primary_threshold[:10],
        "vendor_split_candidates": vendor_split_candidates,
        "wysos_entity_flags": entity_flags,
        "digit_distribution": benford_report,
        "warning": CANDIDATE_WARNING,
    }


# ---------------------------------------------------------------------------
# 3. SECTION 7: VERACITY TIMELINE AUDITOR (W.S. 16-4-202 Clocks & GovQA Logs)
# ---------------------------------------------------------------------------

def _parse_iso_utc(raw: str | None, fallback: datetime | None = None) -> datetime:
    if not raw or not str(raw).strip():
        if fallback is not None:
            return fallback
        return datetime.now(timezone.utc)
    s = str(raw).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # Support common US slash dates in CSV exports (MM/DD/YYYY or YYYY/MM/DD)
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", s):
        m, d, y = (int(p) for p in s.split("/"))
        return datetime(y, m, d, tzinfo=timezone.utc)
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    offset = (last.weekday() - weekday) % 7
    return last - timedelta(days=offset)


def wyoming_state_holidays(year: int) -> set[date]:
    """Legal holidays in Wyoming per W.S. 8-4-101 (with Sat->Fri, Sun->Mon observance)."""
    fixed = [
        date(year, 1, 1),    # New Year's Day
        date(year, 6, 19),   # Juneteenth
        date(year, 7, 4),    # Independence Day
        date(year, 11, 11),  # Veterans Day
        date(year, 12, 25),  # Christmas Day
    ]
    floating = {
        _nth_weekday(year, 1, 0, 3),   # MLK / Wyoming Equality Day (3rd Mon Jan)
        _nth_weekday(year, 2, 0, 3),   # Presidents' Day (3rd Mon Feb)
        _last_weekday(year, 5, 0),     # Memorial Day (last Mon May)
        _nth_weekday(year, 9, 0, 1),   # Labor Day (1st Mon Sep)
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving Day (4th Thu Nov)
    }
    observed = set(floating)
    for h in fixed:
        observed.add(h)
        if h.weekday() == 5:  # Saturday -> preceding Friday
            observed.add(h - timedelta(days=1))
        elif h.weekday() == 6:  # Sunday -> following Monday
            observed.add(h + timedelta(days=1))
    return observed


def count_wyoming_business_days(start_date: date, end_date: date) -> int:
    """Count elapsed business days after start_date through end_date (excluding weekends & WY holidays)."""
    if end_date <= start_date:
        return 0
    holidays: set[date] = set()
    for y in range(start_date.year, end_date.year + 1):
        holidays.update(wyoming_state_holidays(y))
    count = 0
    cur = start_date + timedelta(days=1)
    while cur <= end_date:
        if cur.weekday() < 5 and cur not in holidays:
            count += 1
        cur += timedelta(days=1)
    return count


def audit_ws_16_4_202_timeline(
    submitted_iso: str,
    ack_iso: str | None = None,
    fulfilled_iso: str | None = None,
    reference_now_iso: str | None = None,
) -> dict[str, Any]:
    """Evaluate W.S. 16-4-202 acknowledgment (7 business days) and release (30 calendar days) clocks."""
    now_utc = _parse_iso_utc(reference_now_iso) if reference_now_iso else datetime.now(timezone.utc)
    t_sub = _parse_iso_utc(submitted_iso, fallback=now_utc)
    t_ack = _parse_iso_utc(ack_iso, fallback=now_utc)
    t_ful = _parse_iso_utc(fulfilled_iso, fallback=now_utc)

    ack_calendar_days = (t_ack - t_sub).days
    fulfill_calendar_days = (t_ful - t_sub).days
    ack_business_days = count_wyoming_business_days(t_sub.date(), t_ack.date())

    return {
        "status": "candidate_unreviewed",
        "submitted_date": submitted_iso,
        "acknowledged_recorded": bool(ack_iso and str(ack_iso).strip()),
        "fulfilled_recorded": bool(fulfilled_iso and str(fulfilled_iso).strip()),
        "ack_elapsed_days": ack_calendar_days,
        "ack_business_days": ack_business_days,
        "fulfill_elapsed_days": fulfill_calendar_days,
        "ws_16_4_202_7bday_ack_violation": ack_business_days > 7,
        "ws_16_4_202_30day_violation": fulfill_calendar_days > 30,
        "statutory_caveat": (
            "W.S. 16-4-202(b)-(c) sets a 7-business-day acknowledgment rule and a 30-calendar-day "
            "release deadline from acknowledgment unless good cause is communicated and mutually "
            "extended or determined; verify written custodian notices before asserting noncompliance."
        ),
    }


def audit_govqa_master_log(
    csv_path: str | Path,
    ref_col: str = "Reference #",
    submitted_col: str = "Date Submitted",
    ack_col: str = "Date Acknowledged",
    closed_col: str = "Date Closed",
    dept_col: str = "Department",
    fee_col: str = "Fees Charged",
    reference_now_iso: str | None = None,
) -> dict[str, Any]:
    """Batch-audit a GovQA / NextRequest CSV export by department for W.S. 16-4-202 clock compliance."""
    dept_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "tickets": 0,
        "ack_gt_7_business_days": 0,
        "fulfill_gt_30_calendar_days": 0,
        "total_fees_charged": 0.0,
    })
    flagged_tickets: list[dict[str, Any]] = []
    total_tickets = 0

    with Path(csv_path).open("r", encoding="utf-8-sig", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sub_raw = (row.get(submitted_col) or "").strip()
            if not sub_raw:
                continue
            total_tickets += 1
            ref_id = (row.get(ref_col) or f"row-{total_tickets}").strip()
            dept = (row.get(dept_col) or "Unspecified").strip() or "Unspecified"
            ack_raw = (row.get(ack_col) or "").strip() or None
            closed_raw = (row.get(closed_col) or "").strip() or None
            fee = _parse_currency(row.get(fee_col, "")) or 0.0

            res = audit_ws_16_4_202_timeline(
                submitted_iso=sub_raw,
                ack_iso=ack_raw,
                fulfilled_iso=closed_raw,
                reference_now_iso=reference_now_iso,
            )
            bucket = dept_stats[dept]
            bucket["tickets"] += 1
            bucket["total_fees_charged"] = round(bucket["total_fees_charged"] + max(fee, 0.0), 2)
            if res["ws_16_4_202_7bday_ack_violation"]:
                bucket["ack_gt_7_business_days"] += 1
            if res["ws_16_4_202_30day_violation"]:
                bucket["fulfill_gt_30_calendar_days"] += 1
            if res["ws_16_4_202_7bday_ack_violation"] or res["ws_16_4_202_30day_violation"]:
                flagged_tickets.append({
                    "reference_id": ref_id,
                    "department": dept,
                    "fee_charged": round(fee, 2),
                    **res,
                })

    departments_out: dict[str, Any] = {}
    for dept, st in sorted(dept_stats.items()):
        n = st["tickets"]
        compliant_30d = n - st["fulfill_gt_30_calendar_days"]
        departments_out[dept] = {
            **st,
            "within_30d_rate_pct": round((compliant_30d / n) * 100.0, 2) if n else 100.0,
        }

    return {
        "status": "candidate_unreviewed",
        "total_tickets_analyzed": total_tickets,
        "flagged_ticket_count": len(flagged_tickets),
        "departments": departments_out,
        "flagged_tickets": flagged_tickets[:50],
        "warning": CANDIDATE_WARNING,
    }


# ---------------------------------------------------------------------------
# 4. SECTION 1: LEGISLATIVE / ANNEXATION DEPENDENCY GRAPH & OBJECTION DOSSIER
# ---------------------------------------------------------------------------

ANNEXATION_PREREQUISITES: tuple[tuple[str, str, str], ...] = (
    (
        "contiguous_boundary_verified",
        "W.S. 15-1-402(a)(iv)",
        "Contiguous perimeter boundary geometry documented in annexation map/legal description",
    ),
    (
        "infrastructure_cost_estimate_present",
        "W.S. 15-1-402(c)(iii)",
        "Written annexation report containing estimated cost of infrastructure/utility extensions",
    ),
    (
        "certified_mailing_radius_verified",
        "W.S. 15-1-405(b)",
        "Certified-mail notice to landowners + utilities within statutory timeline prior to public hearing",
    ),
    (
        "newspaper_publication_intervals_verified",
        "W.S. 15-1-405(a)",
        "Public hearing notice published at least twice in a newspaper of general circulation (>=15 days before hearing)",
    ),
    (
        "applicant_wysos_good_standing",
        "W.S. 17-29-208 / wyobiz.wyo.gov",
        "Applicant business entity verified active and in good standing with Wyoming Secretary of State",
    ),
    (
        "seo_water_rights_verified",
        "W.S. 41-3-101 / seoweb.wyo.gov",
        "Water supply / State Engineer's Office water-right or municipal utility allocation documented",
    ),
)


def audit_annexation_prerequisites(
    packet: Mapping[str, Any],
    agenda_item: str = "[AGENDA ITEM / ORDINANCE #]",
    governing_body: str = "Governing Body",
    meeting_date: str = "[YYYY-MM-DD]",
) -> dict[str, Any]:
    """Evaluate mandatory statutory prerequisites for an annexation/land-use packet and draft
    a human-reviewed Notice of Defect + <=350-word 3-beat public comment script when items are absent.
    """
    missing: list[dict[str, str]] = []
    present: list[str] = []
    for key, statute, desc in ANNEXATION_PREREQUISITES:
        if bool(packet.get(key)):
            present.append(key)
        else:
            missing.append({
                "field": key,
                "statute_or_mirror": statute,
                "requirement": desc,
                "status": "candidate_unreviewed",
            })

    # Construct 3-beat podium script strictly bounded under 350 words (target ~180-260 words)
    if missing:
        primary = missing[0]
        other_cites = ", ".join(m["statute_or_mirror"] for m in missing[1:4])
        extra_clause = f" Additional unverified prerequisites in the packet include {other_cites}." if other_cites else ""
        script = (
            f"[DRAFT FOR HUMAN REVIEW — NOT AUTO-SENT; NOT LEGAL ADVICE]\n\n"
            f"Members of the {governing_body}, for the record on {agenda_item} ({meeting_date}):\n\n"
            f"Beat 1 — Statutory Prerequisite: Under {primary['statute_or_mirror']}, prior to final "
            f"annexation action, the record must contain: {primary['requirement'].lower()}.{extra_clause}\n\n"
            f"Beat 2 — Packet Inspection Finding: A review of the published agenda packet for {agenda_item} "
            f"did not locate {primary['requirement'].lower()} ({len(missing)} of "
            f"{len(ANNEXATION_PREREQUISITES)} checklist prerequisites unverified in the packet).\n\n"
            f"Beat 3 — Record Preservation Request: Because statutory prerequisites govern municipal "
            f"annexation procedure under W.S. 15-1-402 through 15-1-405, I respectfully request that "
            f"this written objection be entered into the administrative record and that third-reading "
            f"or final action on {agenda_item} be deferred until the complete statutory documentation "
            f"is published and noticed for public inspection."
        )
        notice_draft = (
            f"DRAFT WRITTEN NOTICE OF PROCEDURAL / STATUTORY RECORD GAP\n"
            f"[Review, verify against the official clerk packet, sign, and submit manually — LEGAL.md §4]\n\n"
            f"To: Clerk of the {governing_body}\n"
            f"Re: {agenda_item} — Meeting of {meeting_date}\n\n"
            f"Please include this notice in the official public record prior to the vote on {agenda_item}.\n"
            f"Unverified / missing items identified in the published agenda packet:\n"
            + "\n".join(f"  - [{m['statute_or_mirror']}] {m['requirement']}" for m in missing)
            + "\n\nRespectfully,\n[YOUR NAME / CONTACT]\n"
        )
    else:
        script = "[All six checklist prerequisites marked verified in input; no objection script drafted.]"
        notice_draft = ""

    word_count = len(re.findall(r"\S+", script))
    return {
        "status": "candidate_unreviewed",
        "sent_by_this_tool": False,
        "agenda_item": agenda_item,
        "governing_body": governing_body,
        "meeting_date": meeting_date,
        "verified_prerequisites_count": len(present),
        "missing_prerequisites_count": len(missing),
        "missing_prerequisites": missing,
        "podium_script_word_count": word_count,
        "podium_script_within_350_words": word_count <= 350,
        "draft_podium_script": script,
        "draft_written_notice": notice_draft,
        "warning": CANDIDATE_WARNING,
    }


# ---------------------------------------------------------------------------
# 5. SECTION 3: PERMITTING TIMELINE & CAMA VALUATION ARBITRAGE AUDITOR
# ---------------------------------------------------------------------------

def audit_permitting_csv(
    csv_path: str | Path,
    record_col: str = "Record ID",
    issued_col: str = "Date Issued",
    external_work_col: str = "External Work Date",
    valuation_col: str = "Valuation",
    cama_delta_col: str = "CAMA Value Delta",
) -> dict[str, Any]:
    """Cross-check OpenGov/ViewPoint/SmartGov permit dates against FAA Part 77 / grading observation
    dates and declared permit valuation against Assessor CAMA market-value additions.
    """
    pre_permit_candidates: list[dict[str, Any]] = []
    valuation_arbitrage_candidates: list[dict[str, Any]] = []
    rows_analyzed = 0

    with Path(csv_path).open("r", encoding="utf-8-sig", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows_analyzed += 1
            rec_id = (row.get(record_col) or f"permit-{rows_analyzed}").strip()
            issued_raw = (row.get(issued_col) or "").strip()
            ext_raw = (row.get(external_work_col) or "").strip()
            if issued_raw and ext_raw:
                try:
                    t_issued = _parse_iso_utc(issued_raw)
                    t_ext = _parse_iso_utc(ext_raw)
                    lead_days = (t_issued - t_ext).days
                    if lead_days > 0:
                        pre_permit_candidates.append({
                            "record_id": rec_id,
                            "date_issued": issued_raw,
                            "external_work_date": ext_raw,
                            "days_prior_to_permit_issuance": lead_days,
                            "status": "candidate_unreviewed",
                        })
                except ValueError:
                    pass

            declared_val = _parse_currency(row.get(valuation_col, ""))
            cama_delta = _parse_currency(row.get(cama_delta_col, ""))
            if declared_val is not None and cama_delta is not None and (declared_val > 0 or cama_delta > 0):
                diff = round(cama_delta - declared_val, 2)
                # Flag >35% divergence where either permit under-declared vs CAMA or CAMA roll omitted permit
                if declared_val > 25000 and cama_delta < (declared_val * 0.50):
                    valuation_arbitrage_candidates.append({
                        "record_id": rec_id,
                        "anomaly_class": "cama_roll_addition_below_50pct_of_permit_valuation",
                        "declared_permit_valuation": round(declared_val, 2),
                        "cama_value_delta": round(cama_delta, 2),
                        "delta_difference": diff,
                        "status": "candidate_unreviewed",
                    })
                elif cama_delta > 50000 and declared_val < (cama_delta * 0.50):
                    valuation_arbitrage_candidates.append({
                        "record_id": rec_id,
                        "anomaly_class": "permit_valuation_below_50pct_of_cama_addition",
                        "declared_permit_valuation": round(declared_val, 2),
                        "cama_value_delta": round(cama_delta, 2),
                        "delta_difference": diff,
                        "status": "candidate_unreviewed",
                    })

    return {
        "status": "candidate_unreviewed",
        "rows_analyzed": rows_analyzed,
        "pre_permit_work_candidate_count": len(pre_permit_candidates),
        "pre_permit_work_candidates": pre_permit_candidates[:50],
        "valuation_arbitrage_candidate_count": len(valuation_arbitrage_candidates),
        "valuation_arbitrage_candidates": valuation_arbitrage_candidates[:50],
        "warning": CANDIDATE_WARNING,
    }


# ---------------------------------------------------------------------------
# 6. SECTION 4: GIS ARCGIS QUERY BUILDER & AGRICULTURAL TAX AUDIT
# ---------------------------------------------------------------------------

def build_arcgis_geojson_query_url(
    service_layer_url: str,
    where: str = "1=1",
    out_fields: str = "*",
    result_record_count: int = 1000,
) -> str:
    """Validate an HTTPS Esri ArcGIS MapServer/FeatureServer layer URL and build a bounded GeoJSON query."""
    parsed = urlsplit((service_layer_url or "").strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("ArcGIS service URL must be credential-free HTTPS")
    if not re.search(r"/(MapServer|FeatureServer)(/\d+)?/?$", parsed.path, re.IGNORECASE):
        raise ValueError("URL path must end at .../MapServer[/<layerId>] or .../FeatureServer[/<layerId>]")
    if not 1 <= int(result_record_count) <= 5000:
        raise ValueError("result_record_count must be between 1 and 5000")

    base = service_layer_url.rstrip("/")
    if re.search(r"/(MapServer|FeatureServer)$", base, re.IGNORECASE):
        base = base + "/0"
    params = urlencode({
        "where": where,
        "outFields": out_fields,
        "resultRecordCount": int(result_record_count),
        "f": "geojson",
    })
    return f"{base}/query?{params}"


def audit_gis_tax_classifications(parcels: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Cross-reference parcels with preferential agricultural tax assessment against commercial
    zoning filings, WOGCC industrial surface activity, or multi-year low NDVI indicators.
    """
    candidates: list[dict[str, Any]] = []
    analyzed = 0
    for row in parcels:
        analyzed += 1
        tax_class = str(row.get("tax_class", "")).strip().lower()
        if "ag" not in tax_class:
            continue
        parcel_id = str(row.get("parcel_id") or row.get("pidn") or f"parcel-{analyzed}").strip()
        active_commercial = str(row.get("active_zoning_application", "")).strip().lower() in (
            "commercial", "industrial", "pud-commercial", "data-center", "true", "1", "yes",
        )
        wogcc_industrial = bool(row.get("wogcc_industrial_surface_use"))
        ndvi_raw = row.get("ndvi_5yr_max")
        ndvi_val = float(ndvi_raw) if ndvi_raw is not None and str(ndvi_raw).strip() != "" else None
        grazing_documented = bool(row.get("grazing_or_crop_documented"))

        triggers: list[str] = []
        if active_commercial:
            triggers.append("active_commercial_or_industrial_zoning_filing")
        if wogcc_industrial:
            triggers.append("wogcc_industrial_surface_use_recorded")
        if ndvi_val is not None and ndvi_val < 0.20 and not grazing_documented:
            triggers.append(f"low_5yr_ndvi_{ndvi_val:.2f}_without_documented_grazing")

        if triggers:
            candidates.append({
                "parcel_id": parcel_id,
                "tax_class": row.get("tax_class"),
                "triggers": triggers,
                "status": "candidate_unreviewed",
            })

    return {
        "status": "candidate_unreviewed",
        "parcels_analyzed": analyzed,
        "ag_classification_candidate_count": len(candidates),
        "ag_classification_candidates": candidates[:100],
        "statutory_note": "Verify W.S. 39-13-103(b)(x) statutory agricultural eligibility criteria (contiguous/non-contiguous production, gross revenue, and lease affidavits) with the County Assessor.",
        "warning": CANDIDATE_WARNING,
    }


# ---------------------------------------------------------------------------
# 7. SECTION 5: LCRR SERVICE-LINE & 40 CFR PART 141 WATER TIMELINE AUDIT
# ---------------------------------------------------------------------------

def audit_lcrr_service_lines(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Flag pre-1986 parcels marked 'Non-Lead' in a Lead & Copper Rule Revisions (LCRR) inventory
    that lack an excavation, hydro-vac, or plumbing-permit verification record.
    """
    candidates: list[dict[str, Any]] = []
    analyzed = 0
    for row in records:
        analyzed += 1
        try:
            year_built = int(str(row.get("year_built", "")).strip())
        except ValueError:
            continue
        material = str(row.get("reported_material", "")).strip().lower()
        verified_date = str(row.get("verification_date") or row.get("excavation_verified_date") or "").strip()
        verification_method = str(row.get("verification_method") or "").strip()

        is_claimed_non_lead = ("non-lead" in material or "non_lead" in material or material in ("copper", "plastic", "pex", "hdpe"))
        if 0 < year_built < 1986 and is_claimed_non_lead and not verified_date and not verification_method:
            candidates.append({
                "service_id": str(row.get("service_id") or row.get("parcel_id") or f"line-{analyzed}"),
                "year_built": year_built,
                "reported_material": row.get("reported_material"),
                "reason": "pre_1986_structure_marked_non_lead_without_recorded_verification",
                "status": "candidate_unreviewed",
            })

    return {
        "status": "candidate_unreviewed",
        "service_lines_analyzed": analyzed,
        "unverified_pre1986_non_lead_count": len(candidates),
        "candidates": candidates[:100],
        "warning": CANDIDATE_WARNING,
    }


def audit_water_advisory_timeline(
    lab_result_iso: str,
    wdeq_notified_iso: str | None,
    public_notice_iso: str | None,
    tier: int = 1,
    reference_now_iso: str | None = None,
) -> dict[str, Any]:
    """Evaluate drinking-water public notification elapsed hours/days against 40 CFR Part 141 Subparts Q."""
    if tier not in (1, 2, 3):
        raise ValueError("40 CFR Part 141 public notice tier must be 1, 2, or 3")
    now_utc = _parse_iso_utc(reference_now_iso) if reference_now_iso else datetime.now(timezone.utc)
    t_lab = _parse_iso_utc(lab_result_iso, fallback=now_utc)
    t_wdeq = _parse_iso_utc(wdeq_notified_iso, fallback=now_utc)
    t_pub = _parse_iso_utc(public_notice_iso, fallback=now_utc)

    hours_to_wdeq = round((t_wdeq - t_lab).total_seconds() / 3600.0, 2)
    hours_to_public = round((t_pub - t_lab).total_seconds() / 3600.0, 2)
    limit_hours = {1: 24.0, 2: 720.0, 3: 8760.0}[tier]

    return {
        "status": "candidate_unreviewed",
        "tier": tier,
        "cfr_limit_hours": limit_hours,
        "hours_lab_to_wdeq_consultation": hours_to_wdeq,
        "hours_lab_to_public_notice": hours_to_public,
        "exceeds_40_cfr_141_public_notice_window": hours_to_public > limit_hours,
        "warning": CANDIDATE_WARNING,
    }


# ---------------------------------------------------------------------------
# 8. SECTION 6: ALPR AUDIT-LOG REASON & CAD-REFERENCE INSPECTOR
# ---------------------------------------------------------------------------

PLACEHOLDER_ALPR_REASONS = frozenset({
    "", "na", "n/a", "none", "null", "test", "testing", "check", "checking",
    "inv", "investigation", "patrol", "traffic", "lookup", "info", ".", "-", "123", "1234",
})
CAD_OR_CASE_PATTERN = re.compile(r"(?:\b\d{2,4}[-_ ]?\d{3,10}\b|\b(?:case|cad|cfs|inc|warrant)[-_ #:]*[a-z0-9]{3,}\b)", re.I)


def audit_alpr_logs(
    csv_path: str | Path,
    timestamp_col: str = "Timestamp",
    user_col: str = "Anonymized User ID",
    reason_col: str = "Reason",
    devices_col: str = "Devices Queried",
    bulk_device_threshold: int = 25,
) -> dict[str, Any]:
    """Audit an ALPR search-log CSV for blank/placeholder reason strings or bulk network queries
    lacking a structured CAD/case reference. User identifiers are SHA-256 hashed so no names leak.
    """
    flagged: list[dict[str, Any]] = []
    total_queries = 0
    blank_or_placeholder = 0
    bulk_without_case = 0

    with Path(csv_path).open("r", encoding="utf-8-sig", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_queries += 1
            raw_reason = str(row.get(reason_col) or row.get("Case/Reason String") or "").strip()
            norm_reason = raw_reason.lower()
            raw_user = str(row.get(user_col) or row.get("User ID") or "unknown").strip()
            anon_user = "op-" + hashlib.sha256(raw_user.encode("utf-8")).hexdigest()[:10]
            dev_raw = str(row.get(devices_col) or "0").strip()
            try:
                devices = int(float(dev_raw))
            except ValueError:
                devices = 0

            has_case_ref = bool(CAD_OR_CASE_PATTERN.search(raw_reason))
            is_placeholder = (norm_reason in PLACEHOLDER_ALPR_REASONS) or (len(norm_reason) < 3)
            is_bulk_no_case = (devices >= bulk_device_threshold) and not has_case_ref

            reasons: list[str] = []
            if is_placeholder:
                blank_or_placeholder += 1
                reasons.append("blank_or_placeholder_reason_string")
            if is_bulk_no_case:
                bulk_without_case += 1
                reasons.append(f"bulk_query_{devices}_devices_without_case_or_cad_id")

            if reasons:
                flagged.append({
                    "row": total_queries,
                    "timestamp": (row.get(timestamp_col) or "").strip(),
                    "operator_hash": anon_user,
                    "devices_queried": devices,
                    "reason_length": len(raw_reason),
                    "has_structured_case_or_cad_ref": has_case_ref,
                    "flags": reasons,
                    "status": "candidate_unreviewed",
                })

    return {
        "status": "candidate_unreviewed",
        "total_queries_analyzed": total_queries,
        "blank_or_placeholder_reason_count": blank_or_placeholder,
        "bulk_queries_without_case_ref_count": bulk_without_case,
        "flagged_query_count": len(flagged),
        "flagged_queries": flagged[:100],
        "privacy_note": "Operator identifiers are one-way hashed (SHA-256 prefix); raw query strings and plates are never emitted.",
        "warning": CANDIDATE_WARNING,
    }


# ---------------------------------------------------------------------------
# CLI ENTRYPOINT
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    m = sub.add_parser("mirror-ledgers", help="List the 8 State & Federal OSINT mirror ledgers")
    m.add_argument("--section", type=int, choices=range(1, 8))
    m.add_argument("--keyword")

    sub.add_parser("sections", help="List the 7 operational municipal/county audit sections")

    p = sub.add_parser("package-provenance", help="SHA-256 hash a file and write CASE/UCO .provenance.json")
    p.add_argument("--file", required=True)
    p.add_argument("--source-url", required=True)
    p.add_argument("--section-tag", required=True)

    vp = sub.add_parser("verify-provenance", help="Verify an artifact against its .provenance.json sidecar")
    vp.add_argument("--manifest", required=True)
    vp.add_argument("--file")

    b = sub.add_parser("audit-check-register", help="Section 2: Benford + threshold-splitting check register audit")
    b.add_argument("--csv", required=True)
    b.add_argument("--amount-col", default="Amount")
    b.add_argument("--vendor-col", default="Vendor")
    b.add_argument("--threshold", type=float, default=5000.0)

    t = sub.add_parser("audit-pra-timeline", help="Section 7: W.S. 16-4-202 statutory clock check")
    t.add_argument("--submitted", required=True)
    t.add_argument("--ack")
    t.add_argument("--fulfilled")
    t.add_argument("--now")

    g = sub.add_parser("audit-govqa-log", help="Section 7: GovQA/NextRequest master CSV compliance audit")
    g.add_argument("--csv", required=True)
    g.add_argument("--now")

    pe = sub.add_parser("audit-permits", help="Section 3: Permitting timeline & CAMA valuation delta audit")
    pe.add_argument("--csv", required=True)

    al = sub.add_parser("audit-alpr", help="Section 6: ALPR search audit-log reason & CAD reference check")
    al.add_argument("--csv", required=True)

    args = ap.parse_args(argv)
    if args.command == "mirror-ledgers":
        out: Any = {"mirror_ledgers": triangulate_mirror_ledgers(args.section, args.keyword)}
    elif args.command == "sections":
        out = {"operational_sections": list(OPERATIONAL_SECTIONS)}
    elif args.command == "package-provenance":
        out = package_osint_artifact(args.file, args.source_url, args.section_tag)
    elif args.command == "verify-provenance":
        out = verify_osint_provenance(args.manifest, args.file)
        print(json.dumps(out, indent=2))
        return 0 if out["verified"] else 3
    elif args.command == "audit-check-register":
        out = audit_check_register_csv(args.csv, args.amount_col, args.vendor_col, args.threshold)
    elif args.command == "audit-pra-timeline":
        out = audit_ws_16_4_202_timeline(args.submitted, args.ack, args.fulfilled, args.now)
    elif args.command == "audit-govqa-log":
        out = audit_govqa_master_log(args.csv, reference_now_iso=args.now)
    elif args.command == "audit-permits":
        out = audit_permitting_csv(args.csv)
    elif args.command == "audit-alpr":
        out = audit_alpr_logs(args.csv)
    else:
        ap.error(f"Unknown command: {args.command}")
        return 2

    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
