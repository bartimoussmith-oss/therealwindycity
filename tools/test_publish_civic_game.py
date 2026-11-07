import tempfile
import unittest
from pathlib import Path
from publish_civic_game import ROOT, publish, validate


class GamePublishingTests(unittest.TestCase):
    def test_approved_runtime(self):
        result = validate(ROOT / "civic_game")
        self.assertEqual(result["records"], 913)
        self.assertIn("index.html", result["files"])

    def test_preserves_archive_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "index.html").write_text("existing archive")
            (out / "meetings").mkdir()
            (out / "meetings" / "record.md").write_text("existing record")
            publish(ROOT / "civic_game", out, "test")
            publish(ROOT / "civic_game", out, "test")
            self.assertEqual((out / "index.html").read_text(), "existing archive")
            self.assertEqual((out / "meetings" / "record.md").read_text(), "existing record")
            self.assertTrue((out / "game" / "deployment.json").is_file())

    def test_refuses_archive_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                publish(ROOT / "civic_game", Path(tmp), "test")


if __name__ == "__main__":
    unittest.main()
