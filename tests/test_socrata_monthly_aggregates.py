"""Offline tests for scripts/socrata_monthly_aggregates.py.

Run: python3 -m unittest tests/test_socrata_monthly_aggregates.py -v
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import socrata_monthly_aggregates as sma  # noqa: E402


class AggregateTests(unittest.TestCase):
    def test_month_bounds(self):
        self.assertEqual(sma.month_bounds("2026-10"),
                         ("2026-10-01T00:00:00", "2026-11-01T00:00:00"))
        self.assertEqual(sma.month_bounds("2026-11"),
                         ("2026-11-01T00:00:00", "2026-12-01T00:00:00"))

    def test_soql_is_aggregate_only(self):
        p = sma.build_soql("2026-10", ["incident_type"])
        self.assertIn("count(*)", p["$select"])
        self.assertNotIn("incident_number", p["$select"])
        self.assertNotIn("*", p["$select"].replace("count(*)", ""))

    def test_refuses_pii_fields(self):
        for field in ["incident_number", "name", "date_of_birth", "address"]:
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    sma.build_soql("2026-10", [field])

    def test_summarize_and_change(self):
        rows = {
            "2026-10": [{"incident_type": "Traffic", "total": "10"},
                        {"incident_type": "Theft", "total": "5"}],
            "2026-11": [{"incident_type": "Traffic", "total": "12"}],
        }
        s = sma.summarize(rows)
        self.assertEqual(s["2026-10"]["total"], 15)
        self.assertEqual(s["2026-11"]["total"], 12)
        self.assertEqual(s["_change"]["abs"], -3)
        self.assertEqual(s["_change"]["pct"], -20.0)

    def test_render_has_no_identifiers_and_states_method(self):
        rows = {"2026-10": [{"incident_type": "Traffic", "total": "3"}], "2026-11": []}
        s = sma.summarize(rows)
        md = sma.render(s, ["2026-10", "2026-11"], "2026-11-15T00:00:00Z", "fixture")
        self.assertIn("| 2026-10 | 3 |", md)
        self.assertIn("No row-level records were downloaded", md)
        self.assertIn("(no rows)", md)

    def test_fixture_run_writes_report(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Path(d) / "fx.json"
            fx.write_text(json.dumps({"2026-10": [{"incident_type": "Traffic", "total": "2"}]}))
            out = Path(d) / "r" / "report.md"
            rc = sma.main(["--months", "2026-10", "2026-11", "--fixture", str(fx), "--out", str(out)])
            self.assertEqual(rc, 0)
            text = out.read_text(encoding="utf-8")
            self.assertIn("NOT live data", text)
            self.assertIn("| 2026-10 | 2 |", text)


if __name__ == "__main__":
    unittest.main()
