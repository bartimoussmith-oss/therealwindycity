#!/usr/bin/env python3
"""Offline unit and integration tests for Lineage A Forensic Audit & Passive Cartography."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import random
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import promethean  # noqa: E402
from promethean.forensic_audit import (  # noqa: E402
    MIRROR_LEDGERS,
    OPERATIONAL_SECTIONS,
    audit_alpr_logs,
    audit_annexation_prerequisites,
    audit_check_register_csv,
    audit_gis_tax_classifications,
    audit_govqa_master_log,
    audit_lcrr_service_lines,
    audit_permitting_csv,
    audit_water_advisory_timeline,
    audit_ws_16_4_202_timeline,
    build_arcgis_geojson_query_url,
    count_wyoming_business_days,
    package_osint_artifact,
    triangulate_mirror_ledgers,
    verify_osint_provenance,
)
from tools.passive_cartography import (  # noqa: E402
    consolidate_results,
    filter_institutional_contacts,
    fingerprint_saas_vendors,
    load_targets,
    scan_jurisdiction,
    validate_spiderfoot_modules,
)


class ForensicAuditTests(unittest.TestCase):
    def test_mirror_ledgers_and_sections_catalog(self):
        self.assertEqual(len(MIRROR_LEDGERS), 8)
        self.assertEqual([m["layer_id"] for m in MIRROR_LEDGERS], list(range(1, 9)))
        self.assertEqual(len(OPERATIONAL_SECTIONS), 7)
        for layer in MIRROR_LEDGERS:
            for ep in layer["primary_endpoints"]:
                self.assertTrue(ep.startswith("https://"), ep)
        sec2_layers = triangulate_mirror_ledgers(section_id=2)
        self.assertEqual({m["slug"] for m in sec2_layers}, {
            "msrb_emma_disclosures",
            "federal_audit_clearinghouse",
            "wysos_ucc_liens",
        })
        cama_hits = triangulate_mirror_ledgers(keyword="cama")
        self.assertEqual(len(cama_hits), 1)
        self.assertEqual(cama_hits[0]["slug"], "state_cama_backbone")

    def test_provenance_packager_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            art = Path(tmp) / "agenda packet 'draft'.pdf"
            payload = b"%PDF-1.7\n" + (b"Cheyenne civic test payload\n" * 6000)
            art.write_bytes(payload)

            manifest = package_osint_artifact(
                filepath=art,
                source_url="https://cheyenne.granicus.com/DocumentViewer.php?file=test.pdf",
                section_tag="Section 1: Legislative Packet",
                http_headers={
                    "Content-Type": "application/pdf",
                    "ETag": '"abc-123"',
                    "Set-Cookie": "secret_session=do_not_record",
                    "Authorization": "Bearer topsecret",
                },
            )
            self.assertEqual(manifest["@type"], "uco-observable:ObservableObject")
            self.assertIn("http_response_headers", manifest)
            self.assertIn("ETag", manifest["http_response_headers"])
            self.assertNotIn("Set-Cookie", manifest["http_response_headers"])
            self.assertNotIn("Authorization", manifest["http_response_headers"])

            mpath = Path(f"{art}.provenance.json")
            self.assertTrue(mpath.is_file())
            ver_ok = verify_osint_provenance(mpath)
            self.assertTrue(ver_ok["verified"])
            self.assertEqual(ver_ok["status"], "intact")

            # Silently alter a single byte and confirm fail-closed detection
            art.write_bytes(payload + b" ")
            ver_bad = verify_osint_provenance(mpath)
            self.assertFalse(ver_bad["verified"])
            self.assertEqual(ver_bad["status"], "altered_after_capture")

    def test_benford_and_threshold_splitting_detector(self):
        rng = random.Random(20261107)
        with tempfile.TemporaryDirectory() as tmp:
            natural_csv = Path(tmp) / "natural_ap.csv"
            with natural_csv.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Vendor", "Check Date", "Invoice Number", "Amount"])
                for i in range(600):
                    # Power-law / log-uniform across 4 orders of magnitude -> natural Benford distribution
                    amt = 10 ** rng.uniform(1.2, 5.2)
                    w.writerow([f"Vendor {i % 40}", "2026-08-15", f"INV-{i}", f"${amt:,.2f}"])

            nat_res = audit_check_register_csv(natural_csv, threshold=5000.0)
            self.assertEqual(nat_res["total_records_analyzed"], 600)
            self.assertFalse(nat_res["nonconformity_flag"])
            self.assertLessEqual(nat_res["mean_absolute_deviation"], 0.015)

            # Construct synthetic split-invoice register clustered at $4,850-$4,995 + dissolved LLC
            split_csv = Path(tmp) / "split_ap.csv"
            with split_csv.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Vendor", "Check Date", "Invoice Number", "Amount"])
                for i in range(120):
                    w.writerow(["Shadow Creek Paving LLC", "2026-09-01", f"SC-{i}", "$4,925.00"])
                w.writerow(["Refund Entry", "2026-09-02", "REF-1", "($150.00)"])
                w.writerow(["Small Fee", "2026-09-02", "FEE-1", "$5.00"])

            split_res = audit_check_register_csv(
                split_csv,
                threshold=5000.0,
                wysos_entities={"Shadow Creek Paving LLC": {"status": "Inactive - Administratively Dissolved", "filing_id": "2021-00099"}},
            )
            self.assertEqual(split_res["total_records_analyzed"], 120)
            self.assertTrue(split_res["nonconformity_flag"])
            self.assertTrue(split_res["chi_squared_p05_flag"])
            self.assertEqual(split_res["threshold_clustering_count"], 120)
            self.assertEqual(len(split_res["vendor_split_candidates"]), 1)
            self.assertEqual(split_res["vendor_split_candidates"][0]["vendor"], "Shadow Creek Paving LLC")
            self.assertEqual(len(split_res["wysos_entity_flags"]), 120)

    def test_ws_16_4_202_clocks_and_govqa_log(self):
        # 2026-09-07 is Labor Day (Monday). Submitted Fri 2026-09-04 -> Tue 2026-09-15 is 6 business days
        from datetime import date
        self.assertEqual(count_wyoming_business_days(date(2026, 9, 4), date(2026, 9, 15)), 6)
        ok = audit_ws_16_4_202_timeline("2026-09-04", "2026-09-15", "2026-09-28")
        self.assertFalse(ok["ws_16_4_202_7bday_ack_violation"])
        self.assertFalse(ok["ws_16_4_202_30day_violation"])

        # Open ticket with None ack/fulfilled + naive submitted date must not raise naive/aware TypeError
        late = audit_ws_16_4_202_timeline(
            submitted_iso="2026-09-01",
            ack_iso=None,
            fulfilled_iso=None,
            reference_now_iso="2026-10-20T12:00:00Z",
        )
        self.assertTrue(late["ws_16_4_202_7bday_ack_violation"])
        self.assertTrue(late["ws_16_4_202_30day_violation"])
        self.assertEqual(late["fulfill_elapsed_days"], 49)

        with tempfile.TemporaryDirectory() as tmp:
            gcsv = Path(tmp) / "govqa.csv"
            with gcsv.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Reference #", "Date Submitted", "Date Acknowledged", "Department", "Date Closed", "Fees Charged"])
                w.writerow(["R-101", "2026-08-01", "2026-08-04", "Clerk", "2026-08-12", "$0.00"])
                w.writerow(["R-102", "2026-08-01", "2026-08-20", "Planning", "2026-09-15", "$45.00"])
            gres = audit_govqa_master_log(gcsv, reference_now_iso="2026-10-01T00:00:00Z")
            self.assertEqual(gres["total_tickets_analyzed"], 2)
            self.assertEqual(gres["flagged_ticket_count"], 1)
            self.assertEqual(gres["departments"]["Clerk"]["within_30d_rate_pct"], 100.0)
            self.assertEqual(gres["departments"]["Planning"]["within_30d_rate_pct"], 0.0)

    def test_sections_1_3_4_5_6_runners(self):
        # Section 1: Annexation prerequisites + <=350-word draft script
        annex = audit_annexation_prerequisites(
            {"contiguous_boundary_verified": True, "infrastructure_cost_estimate_present": False},
            agenda_item="Ordinance 4701",
            governing_body="Cheyenne City Council",
            meeting_date="2026-11-09",
        )
        self.assertFalse(annex["sent_by_this_tool"])
        self.assertEqual(annex["missing_prerequisites_count"], 5)
        self.assertTrue(annex["podium_script_within_350_words"])
        self.assertIn("W.S. 15-1-402(c)(iii)", annex["draft_podium_script"])

        # Section 3: Permitting pre-issuance work & CAMA arbitrage
        with tempfile.TemporaryDirectory() as tmp:
            pcsv = Path(tmp) / "permits.csv"
            with pcsv.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Record ID", "Date Issued", "External Work Date", "Valuation", "CAMA Value Delta"])
                w.writerow(["BP-2026-01", "2026-07-15", "2026-06-01", "$2,000,000", "$200,000"])
            pres = audit_permitting_csv(pcsv)
            self.assertEqual(pres["pre_permit_work_candidate_count"], 1)
            self.assertEqual(pres["valuation_arbitrage_candidate_count"], 1)

            # Section 6: ALPR audit log anonymization & reason checks
            acsv = Path(tmp) / "alpr.csv"
            with acsv.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Timestamp", "Anonymized User ID", "Reason", "Devices Queried"])
                w.writerow(["2026-10-01T01:00:00Z", "officer.personal.name@agency.gov", "test", "40"])
                w.writerow(["2026-10-01T02:00:00Z", "unit42", "CAD 26-099812 stolen vehicle", "50"])
            ares = audit_alpr_logs(acsv, bulk_device_threshold=25)
            self.assertEqual(ares["flagged_query_count"], 1)
            raw_dump = json.dumps(ares)
            self.assertNotIn("officer.personal.name", raw_dump)

        # Section 4: ArcGIS GeoJSON URL + Ag classification
        qurl = build_arcgis_geojson_query_url("https://gis.laramiecountywy.gov/arcgis/rest/services/Parcels/MapServer")
        self.assertIn("/MapServer/0/query?", qurl)
        self.assertIn("f=geojson", qurl)
        with self.assertRaises(ValueError):
            build_arcgis_geojson_query_url("http://insecure.example.gov/arcgis/rest/services/Parcels/MapServer/0")

        gis_res = audit_gis_tax_classifications([
            {"parcel_id": "P-1", "tax_class": "Agricultural", "active_zoning_application": "industrial", "ndvi_5yr_max": 0.11},
            {"parcel_id": "P-2", "tax_class": "Agricultural", "ndvi_5yr_max": 0.55, "grazing_or_crop_documented": True},
        ])
        self.assertEqual(gis_res["ag_classification_candidate_count"], 1)

        # Section 5: LCRR pre-1986 unverified non-lead + 40 CFR 141 notice clock
        lcrr = audit_lcrr_service_lines([
            {"service_id": "SL-1", "year_built": 1972, "reported_material": "Non-Lead", "verification_date": ""},
            {"service_id": "SL-2", "year_built": 1972, "reported_material": "Non-Lead", "verification_date": "2025-06-10"},
            {"service_id": "SL-3", "year_built": 2004, "reported_material": "Copper", "verification_date": ""},
        ])
        self.assertEqual(lcrr["unverified_pre1986_non_lead_count"], 1)
        water = audit_water_advisory_timeline(
            "2026-08-01T08:00:00Z",
            "2026-08-01T14:00:00Z",
            "2026-08-03T12:00:00Z",
            tier=1,
        )
        self.assertTrue(water["exceeds_40_cfr_141_public_notice_window"])


class PassiveCartographyTests(unittest.TestCase):
    def test_targets_manifest_reconciles_with_wyoming_registry(self):
        targets_doc = load_targets()
        targets = targets_doc["targets"]
        self.assertEqual(len(targets), 24)  # wyo-gov + 23 counties

        reg = json.loads((ROOT / "wyoming" / "registry.json").read_text(encoding="utf-8"))
        reg_counties = {c["slug"]: c for c in reg["counties"]}
        manifest_counties = {t["jurisdiction"]: t for t in targets if t["type"] == "county"}
        self.assertEqual(set(manifest_counties), set(reg_counties))
        for slug, c in reg_counties.items():
            self.assertEqual(manifest_counties[slug]["county_seat_name"], c["county_seat_name"])

    def test_spiderfoot_passive_module_gate_blocks_active_scans(self):
        valid = validate_spiderfoot_modules("sfp_crt,sfp_dnsresolve,sfp_webframework")
        self.assertEqual(valid, ["sfp_crt", "sfp_dnsresolve", "sfp_webframework"])
        for forbidden in ("sfp_portscan_tcp", "sfp_nmap", "sfp_nuclei", "sfp_vuln_nessus", "sfp_sql", "sfp_spider"):
            with self.subTest(module=forbidden), self.assertRaises(ValueError):
                validate_spiderfoot_modules(["sfp_crt", forbidden])

    def test_personal_email_redaction_gate(self):
        sample = [
            "Contact clerk@laramiecountywy.gov or records@cheyennecity.org for public records.",
            "Personal staff mailbox jane.doe@laramiecountywy.gov and bob_smith@wyo.gov must be stripped.",
        ]
        filtered = filter_institutional_contacts(sample)
        self.assertEqual(
            filtered["institutional_role_contacts"],
            ["clerk@laramiecountywy.gov", "records@cheyennecity.org"],
        )
        self.assertEqual(filtered["redacted_personal_or_nonrole_email_count"], 2)

    def test_vendor_fingerprinting_and_arcgis_extraction(self):
        fp = fingerprint_saas_vendors(
            subdomains=["cheyennewy.govqa.us", "cheyennewy.viewpointcloud.com", "cheyenne.granicus.com"],
            mx_records=["us-smtp-inbound-1.mimecast.com"],
            html_samples=[
                '<a href="https://gis.laramiecountywy.gov/arcgis/rest/services/Parcels/MapServer/0">Parcels</a>'
                ' Powered by Tyler iTax'
            ],
        )
        vids = {v["vendor_id"] for v in fp["detected_vendors"]}
        self.assertTrue({"govqa", "opengov_viewpoint", "granicus", "mimecast_gateway", "esri_arcgis", "tyler_itax_eagle"}.issubset(vids))
        self.assertEqual(len(fp["arcgis_geojson_queries"]), 1)

    def test_offline_24_target_scan_consolidate_and_tamper_rejection(self):
        targets = load_targets()["targets"]
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp) / "raw"
            for t in targets:
                scan_jurisdiction(t, output_dir=raw_dir, offline=True)

            db_out = Path(tmp) / "wyoming_statewide_records_infrastructure.db"
            json_out = Path(tmp) / "consolidated_cartography.json"
            md_out = Path(tmp) / "vendor_pra_matrix.md"
            summary = consolidate_results(raw_dir, db_out, json_out, md_out)
            self.assertEqual(summary["jurisdictions_consolidated"], 24)
            self.assertTrue(db_out.is_file())
            self.assertTrue(Path(f"{db_out}.provenance.json").is_file())

            with sqlite3.connect(db_out) as conn:
                n_jur = conn.execute("SELECT COUNT(*) FROM jurisdiction_targets").fetchone()[0]
                n_mir = conn.execute("SELECT COUNT(*) FROM mirror_ledger_catalog").fetchone()[0]
                n_sent = conn.execute("SELECT COUNT(*) FROM pra_draft_templates WHERE sent_by_this_tool != 0").fetchone()[0]
            self.assertEqual(n_jur, 24)
            self.assertEqual(n_mir, 8)
            self.assertEqual(n_sent, 0)

            # Corrupt one JSON artifact after hashing -> consolidate must fail closed
            laramie_json = raw_dir / "laramie-county.json"
            laramie_json.write_text(laramie_json.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                consolidate_results(raw_dir, Path(tmp) / "tampered.db")

    def test_package_reexports_workflow_and_notebook_validity(self):
        self.assertTrue(callable(promethean.package_osint_artifact))
        self.assertTrue(callable(promethean.audit_check_register_csv))
        self.assertTrue(callable(promethean.audit_ws_16_4_202_timeline))

        nb = json.loads((ROOT / "tools" / "colab_statewide_cartography.ipynb").read_text(encoding="utf-8"))
        self.assertEqual(nb["nbformat"], 4)
        code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
        self.assertGreaterEqual(len(code_cells), 3)
        for idx, cell in enumerate(code_cells):
            compile("".join(cell["source"]), f"colab_cell_{idx}", "exec")

        wf_text = (ROOT / ".github" / "workflows" / "passive_cartography.yml").read_text(encoding="utf-8")
        self.assertIn("fail-fast: false", wf_text)
        self.assertIn("contents: read", wf_text)
        self.assertNotIn("git push", wf_text)

        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "passive_cartography.py"), "matrix-json"],
            capture_output=True, text=True, check=True,
        )
        matrix_list = json.loads(proc.stdout)
        self.assertEqual(len(matrix_list), 24)
        self.assertEqual(matrix_list[0], "wyo-gov")


if __name__ == "__main__":
    unittest.main()
