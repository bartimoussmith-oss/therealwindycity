import tempfile
import unittest
from pathlib import Path
from tools.record_atlas import identifiers, manifest, build_index, related

class AtlasTests(unittest.TestCase):
    def test_normalized_identifier(self):
        self.assertEqual(list(identifiers("Ordinance No. 4687 and ORD. #4687")), ["Ordinance 4687"])
    def test_no_invented_connection(self):
        self.assertEqual(identifiers("Council discussed water."), {})
    def test_read_only_allowlist_and_links(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root / "pipeline/corpus"
            p.mkdir(parents=True)
            (p / "agenda_2026-10-01.txt").write_text("Ordinance 4687", encoding="utf-8")
            (p / "minutes_2020-01-01.txt").write_text("Reading Ordinance No. 4687", encoding="utf-8")
            (root / "private.txt").write_text("Ordinance 4687", encoding="utf-8")
            before = sorted(str(x) for x in root.rglob("*"))
            report = build_index(root, manifest(root), "a" * 40)
            self.assertEqual(len(report["records"]), 2)
            self.assertEqual(len(related(report["records"], report["records"][0])), 1)
            self.assertEqual(before, sorted(str(x) for x in root.rglob("*")))
            self.assertIn("/" + "a" * 40 + "/", report["records"][0]["url"])
    def test_traversal_denied(self):
        with tempfile.TemporaryDirectory() as d:
            report = build_index(d, [("../secret.txt", 1, 0)])
            self.assertEqual(report["records"], [])
            self.assertEqual(len(report["skipped"]), 1)

if __name__ == "__main__":
    unittest.main()
