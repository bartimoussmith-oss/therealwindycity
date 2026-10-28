#!/usr/bin/env python3
"""Tests for tools/repo_partition.py — stdlib unittest, hermetic, no git, no network.

The point of these tests is the arithmetic and the classification, because a
partition manifest that miscounts bytes leads an owner to make a destructive
migration decision on a false number. Nothing here touches the real repository.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import repo_partition as rp  # noqa: E402


class TestClassify(unittest.TestCase):
    def test_video_by_extension(self):
        self.assertEqual(rp.classify("video/01-wolfe-evolution.mp4"), ("video", "outbound"))
        self.assertEqual(rp.classify("videos/x.webm"), ("video", "outbound"))

    def test_model_by_path_prefix_wins_over_extension(self):
        # .bin under a models/ prefix is a model, not an audio file. Path rules
        # are checked first, so a prefix must beat a generic extension match.
        self.assertEqual(rp.classify("2026-09-14-council/civicwatch/models/m/model.onnx"),
                         ("ml-model", "outbound"))

    def test_renders_by_prefix(self):
        self.assertEqual(rp.classify("pipeline/renders/CONTENTION_REEL.txt"),
                         ("render", "outbound"))

    def test_documents_and_code_are_resident(self):
        self.assertEqual(rp.classify("READ-FIRST.md"), ("document", "resident"))
        self.assertEqual(rp.classify("tools/repo_partition.py"), ("code", "resident"))
        self.assertEqual(rp.classify("engine/db.py"), ("code", "resident"))

    def test_databases_outbound(self):
        self.assertEqual(rp.classify("data/engine.db"), ("database", "outbound"))
        self.assertEqual(rp.classify("rag/vectordb_sample/chroma.sqlite3"),
                         ("database", "outbound"))

    def test_pdf_and_json_need_review_not_a_verdict(self):
        # 'review' is the honest answer: whether a 33 MB JSON is build-time
        # input or archive mass cannot be decided from the index alone.
        self.assertEqual(rp.classify("public/master_meetings_database_linked.json"),
                         ("structured-data", "review"))
        self.assertEqual(rp.classify("uploads/packet.pdf"), ("pdf", "review"))

    def test_unknown_extension_is_review(self):
        self.assertEqual(rp.classify("data/snapshots/abc_Minutes-and-Agendas"),
                         ("other", "review"))

    def test_case_insensitive_extension(self):
        self.assertEqual(rp.classify("video/CLIP.MP4"), ("video", "outbound"))


class TestDuplicates(unittest.TestCase):
    def test_identical_content_detected_and_waste_computed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            big = b"x" * (rp.DUPLICATE_REPORT_THRESHOLD + 10)
            (root / "a.mp4").write_bytes(big)
            (root / "b.mp4").write_bytes(big)
            rows = [
                {"path": "a.mp4", "bytes": len(big), "present": True, "class": "video",
                 "residency": "outbound", "blob_sha": "", "ext": ".mp4", "top_dir": "."},
                {"path": "b.mp4", "bytes": len(big), "present": True, "class": "video",
                 "residency": "outbound", "blob_sha": "", "ext": ".mp4", "top_dir": "."},
            ]
            original_root = rp.ROOT
            rp.ROOT = root
            try:
                result = rp.find_duplicates(rows)
            finally:
                rp.ROOT = original_root
            self.assertEqual(result["all_groups_count"], 1)
            # Two copies waste exactly one copy's bytes — not two.
            self.assertEqual(result["all_wasted_bytes"], len(big))
            self.assertEqual(result["duplicate_report_floor_bytes"]
                             if "duplicate_report_floor_bytes" in result else
                             rp.DUPLICATE_REPORT_THRESHOLD,
                             rp.DUPLICATE_REPORT_THRESHOLD)
            self.assertEqual(len(result["material_groups"]), 1)
            self.assertEqual(result["material_groups"][0]["paths"], ["a.mp4", "b.mp4"])

    def test_same_size_different_content_is_not_a_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.bin").write_bytes(b"a" * 4096)
            (root / "b.bin").write_bytes(b"b" * 4096)
            rows = [
                {"path": "a.bin", "bytes": 4096, "present": True, "class": "other",
                 "residency": "review", "blob_sha": "", "ext": ".bin", "top_dir": "."},
                {"path": "b.bin", "bytes": 4096, "present": True, "class": "other",
                 "residency": "review", "blob_sha": "", "ext": ".bin", "top_dir": "."},
            ]
            original_root = rp.ROOT
            rp.ROOT = root
            try:
                result = rp.find_duplicates(rows)
            finally:
                rp.ROOT = original_root
            self.assertEqual(result["all_groups_count"], 0)
            self.assertEqual(result["all_wasted_bytes"], 0)

    def test_small_duplicates_counted_in_totals_but_not_itemised(self):
        # The corpus really does contain hundreds of tiny identical text files.
        # Suppressing them from the list is a readability choice; excluding them
        # from the total would be a false number.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            small = b"y" * 100
            (root / "c.txt").write_bytes(small)
            (root / "d.txt").write_bytes(small)
            rows = [
                {"path": "c.txt", "bytes": 100, "present": True, "class": "document",
                 "residency": "resident", "blob_sha": "", "ext": ".txt", "top_dir": "."},
                {"path": "d.txt", "bytes": 100, "present": True, "class": "document",
                 "residency": "resident", "blob_sha": "", "ext": ".txt", "top_dir": "."},
            ]
            original_root = rp.ROOT
            rp.ROOT = root
            try:
                result = rp.find_duplicates(rows)
            finally:
                rp.ROOT = original_root
            self.assertEqual(result["all_groups_count"], 1)
            self.assertEqual(result["all_wasted_bytes"], 100)
            self.assertEqual(len(result["material_groups"]), 0)
            self.assertEqual(result["minor_groups_count"], 1)

    def test_missing_files_are_skipped_not_hashed(self):
        rows = [{"path": "gone.mp4", "bytes": 0, "present": False, "class": "video",
                 "residency": "outbound", "blob_sha": "", "ext": ".mp4", "top_dir": "."}]
        result = rp.find_duplicates(rows)
        self.assertEqual(result["all_groups_count"], 0)


class TestSummarizeAndManifest(unittest.TestCase):
    def _rows(self):
        return [
            {"path": "video/a.mp4", "bytes": 100, "present": True, "class": "video",
             "residency": "outbound", "blob_sha": "", "ext": ".mp4", "top_dir": "video"},
            {"path": "README.md", "bytes": 10, "present": True, "class": "document",
             "residency": "resident", "blob_sha": "", "ext": ".md", "top_dir": "."},
            {"path": "tools/x.py", "bytes": 5, "present": True, "class": "code",
             "residency": "resident", "blob_sha": "", "ext": ".py", "top_dir": "tools"},
            {"path": "big.json", "bytes": 50, "present": True, "class": "structured-data",
             "residency": "review", "blob_sha": "", "ext": ".json", "top_dir": "."},
        ]

    def test_totals_add_up_exactly(self):
        summary = rp.summarize(self._rows())
        self.assertEqual(summary["tracked_bytes"], 165)
        self.assertEqual(summary["tracked_files"], 4)
        residency = {r["key"]: r["bytes"] for r in summary["by_residency"]}
        self.assertEqual(residency, {"outbound": 100, "resident": 15, "review": 50})
        self.assertEqual(sum(residency.values()), summary["tracked_bytes"])

    def test_projection_is_resident_plus_review_only(self):
        summary = rp.summarize(self._rows())
        manifest = rp.build_manifest(summary, {
            "material_groups": [], "minor_groups_count": 0, "minor_wasted_bytes": 0,
            "all_groups_count": 0, "all_wasted_bytes": 0}, self._rows())
        totals = manifest["totals"]
        self.assertEqual(totals["projected_bytes_after_outbound_removed"], 65)
        self.assertEqual(totals["resident_bytes"] + totals["review_bytes"], 65)
        self.assertEqual(totals["tracked_bytes"], 165)
        # The manifest must carry the warning that this is NOT a .git reduction.
        self.assertIn("not a .git size reduction", manifest["note"])
        self.assertIn("history", manifest["note"])

    def test_manifest_is_json_serialisable(self):
        summary = rp.summarize(self._rows())
        manifest = rp.build_manifest(summary, {
            "material_groups": [], "minor_groups_count": 0, "minor_wasted_bytes": 0,
            "all_groups_count": 0, "all_wasted_bytes": 0}, self._rows())
        self.assertIsInstance(json.dumps(manifest), str)
        self.assertEqual(manifest["schema"], "repo-partition-manifest-v1")

    def test_large_resident_files_flagged(self):
        rows = self._rows() + [
            {"path": "huge.md", "bytes": rp.LARGE_FILE_THRESHOLD + 1, "present": True,
             "class": "document", "residency": "resident", "blob_sha": "", "ext": ".md",
             "top_dir": "."}]
        summary = rp.summarize(rows)
        self.assertEqual(len(summary["large_resident_files"]), 1)
        self.assertEqual(summary["large_resident_files"][0]["path"], "huge.md")


class TestGitattributes(unittest.TestCase):
    def test_every_lfs_extension_present_with_lfs_directives(self):
        block = rp.gitattributes_block()
        for ext in rp.LFS_EXTENSIONS:
            line = f"*{ext} filter=lfs diff=lfs merge=lfs -text"
            self.assertIn(line, block)
        self.assertTrue(block.endswith("\n"))

    def test_no_lfs_rule_for_plain_text(self):
        # Routing .md or .py through LFS would break diffing and the whole
        # point of a text-first accountability archive.
        block = rp.gitattributes_block()
        self.assertNotIn("*.md filter=lfs", block)
        self.assertNotIn("*.py filter=lfs", block)
        self.assertNotIn("*.txt filter=lfs", block)


class TestMigrationCommands(unittest.TestCase):
    def test_commands_never_include_destructive_git_operations_unflagged(self):
        manifest = {"totals": {"outbound_bytes": 1}}
        cmds = "\n".join(rp.migration_commands(manifest))
        # --cached is the only acceptable removal form: it untracks without
        # deleting the working file.
        self.assertIn("git rm -r --cached", cmds)
        self.assertNotIn("git rm -r video", cmds.replace("git rm -r --cached", ""))
        # History rewrite must appear only as a commented owner decision.
        for line in cmds.splitlines():
            if "filter-repo" in line or "force-push" in line or "reset --hard" in line:
                self.assertTrue(line.strip().startswith("#"),
                                f"destructive command not commented out: {line}")

    def test_no_force_push_anywhere(self):
        cmds = "\n".join(rp.migration_commands({"totals": {}}))
        self.assertNotIn("--force", cmds)
        self.assertNotIn("push -f", cmds)


class TestExportBundles(unittest.TestCase):
    def test_bundle_records_hash_and_member_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "video").mkdir()
            payload = b"z" * 2048
            (root / "video" / "clip.mp4").write_bytes(payload)
            rows = [{"path": "video/clip.mp4", "bytes": 2048, "present": True,
                     "class": "video", "residency": "outbound", "blob_sha": "",
                     "ext": ".mp4", "top_dir": "video"}]
            out = root / "out"
            original_root = rp.ROOT
            rp.ROOT = root
            try:
                bundles = rp.export_bundles(rows, out)
            finally:
                rp.ROOT = original_root
            self.assertEqual(len(bundles), 1)
            b = bundles[0]
            self.assertEqual(b["class"], "video")
            self.assertEqual(b["member_files"], 1)
            self.assertEqual(b["member_bytes"], 2048)
            self.assertEqual(len(b["bundle_sha256"]), 64)
            self.assertTrue((out / "video-bundle.tar.gz").exists())

    def test_resident_files_never_bundled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("keep me")
            rows = [{"path": "README.md", "bytes": 7, "present": True,
                     "class": "document", "residency": "resident", "blob_sha": "",
                     "ext": ".md", "top_dir": "."}]
            original_root = rp.ROOT
            rp.ROOT = root
            try:
                bundles = rp.export_bundles(rows, root / "out")
            finally:
                rp.ROOT = original_root
            self.assertEqual(bundles, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
