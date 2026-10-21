import json
import os
import unittest
from unittest.mock import patch
from ai_record_status import snapshot_status, status_panel
from check_ai_record import validate


class SnapshotTests(unittest.TestCase):
    def test_dates_are_not_collection_checks(self):
        status = snapshot_status([{"date": "2026-10-19"}, {"date": "2026-09-22"}], {"meetings": 2})
        self.assertEqual(status["latest_indexed_meeting"], "2026-10-19")
        self.assertIsNone(status["collection_checked_at"])
        self.assertIsNone(status["latest_verified_outcome"])
        self.assertIn("Not recorded", status_panel(status))

    def test_empty_dates(self):
        self.assertIsNone(snapshot_status([{"date": "unknown"}], {})["latest_indexed_meeting"])

    def fixture(self):
        with patch.dict(os.environ, {"GITHUB_SHA": "abc", "GITHUB_RUN_ID": "123"}):
            status = snapshot_status([], {"meetings": 0})
        return {"index.html": status_panel(status), "indexes/status.json": json.dumps(status),
                "indexes/meetings.json": '{"count":0,"meetings":[]}',
                "llms.txt": "archive", "topics/corrections.html": "corrections",
                "topics/data-quality.html": "quality"}

    def test_good_snapshot(self):
        validate(self.fixture().__getitem__, "abc", "123")

    def test_wrong_revision_or_run(self):
        for revision, run in (("old", "123"), ("abc", "122")):
            with self.assertRaises(AssertionError):
                validate(self.fixture().__getitem__, revision, run)

    def test_missing_panel_and_stale_upcoming(self):
        for home in ("old homepage", status_panel(snapshot_status([], {})) + " Upcoming 2020-01-01"):
            files = self.fixture()
            files["index.html"] = home
            with self.assertRaises(AssertionError):
                validate(files.__getitem__)

    def test_inconsistent_count(self):
        files = self.fixture()
        files["indexes/meetings.json"] = '{"count":1,"meetings":[]}'
        with self.assertRaises(AssertionError):
            validate(files.__getitem__)


if __name__ == "__main__":
    unittest.main()
