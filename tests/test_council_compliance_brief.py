"""Offline tests for scripts/council_compliance_brief.py.

Run: python3 -m unittest tests/test_council_compliance_brief.py -v
Builds a temporary documents table; no network access.
"""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import council_compliance_brief as ccb  # noqa: E402

SCHEMA = """CREATE TABLE documents (
    id INTEGER PRIMARY KEY, source TEXT, url TEXT, title TEXT, first_seen TEXT,
    last_checked TEXT, published_at TEXT, local_path TEXT, sha256 TEXT,
    size_bytes INTEGER, status TEXT)"""


class ComplianceBriefTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        txt = base / "minutes.txt"
        txt.write_text("Council approved Ordinance No. 4687 on second reading. Vote was 5-2.",
                       encoding="utf-8")
        self.db = base / "test.db"
        con = sqlite3.connect(self.db)
        con.execute(SCHEMA)
        con.executemany(
            "INSERT INTO documents (source,url,title,first_seen,last_checked,published_at,local_path,sha256,status)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            [
                ("city_council_minutes_agendas", "https://www.cheyennecity.org/minutes-1",
                 "City Council Minutes Ordinance 4687", "2026-09-01T00:00:00Z",
                 "2026-09-02T00:00:00Z", "2026-09-01", str(txt), "ab" * 32, "fetched"),
                ("granicus", "https://cheyenne.granicus.com/agenda-9",
                 "City Council Agenda Ordinance 4687", "2026-09-01T00:00:00Z",
                 "2026-09-02T00:00:00Z", "2026-09-01", None, "cd" * 32, "fetched"),
            ],
        )
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()

    # --- scope gate -------------------------------------------------------
    def test_accepts_council_and_county_scope(self):
        for q in ["City Council minutes", "Ordinance 4687", "Laramie County parcel",
                  "government contract award", "W.S. 16-4-202 request"]:
            self.assertEqual(ccb.check_scope(q), q)

    def test_refuses_personal_name_queries(self):
        for q in ["Charles Miller City Council", "Charles miller ordinance"]:
            with self.subTest(q=q):
                with self.assertRaises(ccb.QueryRefused):
                    ccb.check_scope(q)

    def test_refuses_profiling_terms(self):
        for q in ["council member home address", "council phone 307-555-1234",
                  "council email a@b.gov minutes", "council family contracts"]:
            with self.subTest(q=q):
                with self.assertRaises(ccb.QueryRefused):
                    ccb.check_scope(q)

    def test_refuses_out_of_scope(self):
        with self.assertRaises(ccb.QueryRefused):
            ccb.check_scope("best pizza recipes")

    def test_refuses_empty_and_oversized(self):
        for q in ["", "x" * 201]:
            with self.assertRaises(ccb.QueryRefused):
                ccb.check_scope(q)

    # --- search and brief -------------------------------------------------
    def test_granicus_is_never_returned(self):
        brief = ccb.build_brief(self.db, "Ordinance 4687")
        self.assertEqual(len(brief.hits), 1)
        self.assertNotIn("granicus.com", brief.hits[0].url)

    def test_hit_carries_verbatim_quote_url_and_timestamp(self):
        brief = ccb.build_brief(self.db, "Ordinance 4687")
        text = ccb.render(brief)
        self.assertIn("https://www.cheyennecity.org/minutes-1", text)
        self.assertIn("Fetched/checked: 2026-09-02T00:00:00Z", text)
        self.assertIn("Council approved Ordinance No. 4687 on second reading.", text)
        self.assertIn("Generated (UTC):", text)

    def test_no_match_states_nothing_inferred(self):
        brief = ccb.build_brief(self.db, "moratorium referendum")
        self.assertEqual(brief.hits, [])
        self.assertIn("Nothing has been inferred", ccb.render(brief))

    def test_missing_db_is_not_created(self):
        missing = self.db.parent / "nope.db"
        with self.assertRaises(sqlite3.OperationalError):
            ccb.build_brief(missing, "City Council minutes")
        self.assertFalse(missing.exists())

    def test_cli_refuses_with_exit_code_2(self):
        rc = ccb.main(["Charles Miller", "--db", str(self.db)])
        self.assertEqual(rc, 2)

    def test_cli_writes_brief(self):
        out = self.db.parent / "brief.md"
        rc = ccb.main(["Ordinance 4687", "--db", str(self.db), "--out", str(out)])
        self.assertEqual(rc, 0)
        self.assertIn("Ordinance No. 4687", out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
