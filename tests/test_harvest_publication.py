import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
MOCK_GH = r'''#!/usr/bin/env python3
import hashlib, json, os, pathlib, sys
root = pathlib.Path(os.environ["MOCK_ROOT"])
a = sys.argv[1:]
with (root / "calls.log").open("a") as out: out.write(json.dumps(a) + "\n")
mode = os.environ.get("MOCK_MODE", "success")
if a[:2] == ["release", "view"]:
    sys.exit(0 if mode == "collision" else 1)
elif a[:2] == ["release", "create"]:
    (root / "release.json").write_text(json.dumps({"draft": True, "tag_name": a[2], "assets": []}))
elif a[:2] == ["release", "upload"]:
    if mode == "upload_failure": sys.exit(42)
    files = a[3:a.index("--repo")]
    assets = [{"name": pathlib.Path(f).name, "size": pathlib.Path(f).stat().st_size, "digest": "sha256:" + hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest()} for f in files]
    if mode == "digest_failure": assets[0]["digest"] = "sha256:incorrect"
    r = json.loads((root / "release.json").read_text()); r["assets"] = assets
    (root / "release.json").write_text(json.dumps(r))
elif a[:2] == ["release", "edit"]:
    r = json.loads((root / "release.json").read_text()); r["draft"] = False
    (root / "release.json").write_text(json.dumps(r))
elif a[:1] == ["api"]:
    r = json.loads((root / "release.json").read_text())
    if "/releases?" in a[1]:
        sys.stdout.write(json.dumps([r]))  # the list endpoint includes drafts
    elif r.get("draft"):
        sys.exit(1)  # like GitHub: /releases/tags/{tag} never returns a draft (HTTP 404)
    else:
        sys.stdout.write(json.dumps(r))
else:
    sys.exit(99)
'''


class PublicationTests(unittest.TestCase):
    def check_case(self, mode):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "bin"
            binary.mkdir()
            gh = binary / "gh"
            gh.write_text(MOCK_GH)
            gh.chmod(0o755)
            if mode != "empty":
                (root / "artifacts").mkdir()
                (root / "artifacts/fixture.pdf").write_bytes(b"%PDF-1.4 offline fixture")
            env = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"],
                   "MOCK_ROOT": tmp, "MOCK_MODE": mode,
                   "GH_TOKEN": "" if mode == "missing_token" else "offline-test-token",
                   "GITHUB_TOKEN": "", "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
                   "GITHUB_SHA": "a" * 40}
            run = subprocess.run(["bash", str(ROOT / "tools/storage_shard_manager.sh")],
                                 cwd=tmp, env=env, capture_output=True, text=True)
            self.assertEqual(run.returncode == 0, mode in ("empty", "success"), run.stderr)
            self.assertEqual((root / "STORAGE_MANIFEST.md").exists(), mode == "success")
            calls = [json.loads(line) for line in (root / "calls.log").read_text().splitlines()] if (root / "calls.log").exists() else []
            self.assertFalse(any(call[:2] == ["repo", "create"] for call in calls))
            if mode != "empty": self.assertTrue((root / "artifacts/fixture.pdf").exists())
            if mode in ("upload_failure", "digest_failure"):
                self.assertFalse(any(call[:2] == ["release", "edit"] for call in calls))
                # a failed publication removes its own draft instead of leaving an orphan behind
                self.assertTrue(any(call[:2] == ["release", "delete"] for call in calls))
            if mode in ("success", "collision", "empty", "missing_token"):
                self.assertFalse(any(call[:2] == ["release", "delete"] for call in calls))

    def test_empty(self): self.check_case("empty")
    def test_missing_token(self): self.check_case("missing_token")
    def test_verified_publication(self): self.check_case("success")
    def test_failed_upload(self): self.check_case("upload_failure")
    def test_wrong_digest(self): self.check_case("digest_failure")
    def test_no_overwrite(self): self.check_case("collision")

if __name__ == "__main__":
    unittest.main()
