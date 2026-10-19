"""Offline unit tests for the local IVIC agenda pre-screen."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze_meetings as analyzer


HTML_SAMPLE = """<!doctype html>
<html><head><title>City Council Meeting</title><script>not agenda text</script></head>
<body><h1>City Council Meeting</h1><strong>AUGUST 10, 2026</strong>
<table><tr><td width="40">1.</td><td>PUBLIC HEARING - Application for a variance. (PUBLIC SERVICES COMMITTEE)<br><br>ACTION: Approve the request</td></tr></table>
<table><tr><td width="40">2.</td><td>LEASES/CONTRACTS/LEGAL:</td></tr>
<tr><td width="40">a)</td><td>[CA] Preventative Maintenance Contract between the City and Example Company.</td></tr>
<tr><td colspan="2"><br>ACTION: Approve in an amount not to exceed $10,000</td></tr></table>
</body></html>"""


class AgendaAnalyzerTests(unittest.TestCase):
    def test_html_extracts_numbered_items_sections_actions_and_cues(self) -> None:
        items, text = analyzer.parse_html_agenda(HTML_SAMPLE)

        self.assertEqual(len(items), 3)
        self.assertIn("City Council Meeting", text)
        self.assertEqual((items[0].item_number, items[0].title), ("1", "PUBLIC HEARING - Application for a variance. (PUBLIC SERVICES COMMITTEE)"))
        self.assertEqual(items[0].action, "Approve the request")
        self.assertEqual(items[0].committees, ["PUBLIC SERVICES COMMITTEE"])
        self.assertEqual(items[1].item_type, "section")
        self.assertEqual(items[2].item_number, "2a")
        self.assertEqual(items[2].parent_item_number, "2")
        self.assertTrue(items[2].consent_agenda)
        self.assertIn("[CA]", items[2].title)
        self.assertEqual(items[2].action, "Approve in an amount not to exceed $10,000")

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "2026-08-10_agenda.html"
            path.write_text(HTML_SAMPLE, encoding="utf-8")
            result = analyzer.analyze_file(path, "https://example.org/agenda")

        self.assertEqual(result["meeting_body"], "City Council")
        self.assertEqual(result["meeting_date"], "2026-08-10")
        self.assertEqual(result["status"], "SOURCE LEAD")
        self.assertEqual(result["agenda_row_count_extracted"], 3)
        first = result["items"][0]
        self.assertEqual(first["status"], "SOURCE LEAD")
        self.assertTrue(first["framework_screen"]["speech_forum_access"]["candidate_review_cue_present"])
        self.assertFalse(first["framework_screen"]["equal_protection"]["candidate_review_cue_present"])
        self.assertTrue(all(
            lane["status"] == "EVIDENCE INCOMPLETE"
            for lane in first["framework_screen"].values()
        ))
        self.assertFalse(first["source"]["source_url_fetched_by_this_tool"])
        self.assertEqual(
            first["source"]["sha256"],
            hashlib.sha256(HTML_SAMPLE.encode("utf-8")).hexdigest(),
        )

    def test_plain_text_rows_and_separate_action_line(self) -> None:
        text = """CITY COUNCIL AGENDA\n1. PUBLIC HEARING on an application\nACTION: Continue to a later date\n2. Call to order\n"""
        items, _document_text = analyzer.parse_plain_agenda(text)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].action, "Continue to a later date")
        self.assertEqual(items[1].title, "Call to order")

    def test_report_uses_only_supported_statuses_and_no_legal_finding_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "agenda.html"
            path.write_text(HTML_SAMPLE, encoding="utf-8")
            report = analyzer.build_report([path])

        self.assertEqual(report["overall_status"], "SOURCE LEAD")
        self.assertEqual(report["input_document_count"], 1)
        self.assertEqual(len(report["documents"]), 1)
        serialized = json.dumps(report)
        self.assertNotIn("Indexed & Analyzed", serialized)
        self.assertNotIn("Formal Constructive Notice Tracked", serialized)
        self.assertNotIn("Lineage A", serialized)
        self.assertNotIn("probability_score", serialized.casefold())
        self.assertNotIn("confidence_score", serialized.casefold())
        self.assertIn("SOURCE LEAD", serialized)
        self.assertIn("EVIDENCE INCOMPLETE", serialized)

    def test_empty_document_is_evidence_incomplete_not_a_clean_finding(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "2026-08-10_agenda.html"
            path.write_text("<html><body>Agenda not yet posted</body></html>", encoding="utf-8")
            result = analyzer.analyze_file(path)
        self.assertEqual(result["agenda_row_count_extracted"], 0)
        self.assertEqual(result["status"], "EVIDENCE INCOMPLETE")

    def test_directory_mode_limits_candidates_to_agenda_named_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "meeting_agenda.html").write_text(HTML_SAMPLE, encoding="utf-8")
            (root / "meeting_minutes.html").write_text(HTML_SAMPLE, encoding="utf-8")
            (root / "packet.pdf").write_bytes(b"not parsed in this test")
            found = analyzer.collect_inputs([], [str(root)])
        self.assertEqual([path.name for path in found], ["meeting_agenda.html"])

    def test_cli_writes_json_report_without_remote_access(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            agenda = root / "2026-08-10_agenda.html"
            output = root / "out" / "report.json"
            agenda.write_text(HTML_SAMPLE, encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = analyzer.main([
                    "--input", str(agenda),
                    "--source-url", "https://example.org/agenda",
                    "--out", str(output),
                ])
            self.assertEqual(result, 0)
            self.assertTrue(output.is_file())
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["agenda_row_count_extracted"], 3)
            self.assertIn("Wrote", stdout.getvalue())

    def test_invalid_source_url_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            analyzer.validate_source_url("file:///tmp/agenda.html")


if __name__ == "__main__":
    unittest.main(verbosity=2)
