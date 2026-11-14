import io
import stat
import unittest
import zipfile
from unittest.mock import patch

from tools.change_bundle import inspect_bundle, publish_bundle


def bundle(name="README.md", body=b"Please update the site"):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, body)
    return out.getvalue()


class BundleTests(unittest.TestCase):
    def test_valid(self):
        report = inspect_bundle(bundle())
        self.assertEqual(report["files"][0]["path"], "README.md")
        self.assertEqual(len(report["sha256"]), 64)

    def test_unsafe_names(self):
        for name in ("../x", "/x", "C:/x", "a\\x"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                inspect_bundle(bundle(name))

    def test_corrupt(self):
        with self.assertRaises(ValueError):
            inspect_bundle(b"not a zip")

    def test_empty(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w"):
            pass
        with self.assertRaises(ValueError):
            inspect_bundle(out.getvalue())

    def test_symlink(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as archive:
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "target")
        with self.assertRaises(ValueError):
            inspect_bundle(out.getvalue())

    def test_expansion_limit(self):
        with patch("tools.change_bundle.MAX_EXPANDED", 10):
            with self.assertRaises(ValueError):
                inspect_bundle(bundle())

    def test_checksum_before_network(self):
        with patch("urllib.request.urlopen") as network:
            with self.assertRaises(ValueError):
                publish_bundle(bundle(), "bad", "secret", "branch")
            network.assert_not_called()

    def test_publish(self):
        import json
        data = bundle()
        response = io.BytesIO(json.dumps({"content": {"html_url": "https://github.com/example"}, "commit": {"sha": "abc"}}).encode())
        with patch("urllib.request.urlopen", return_value=response) as network:
            receipt = publish_bundle(data, inspect_bundle(data)["sha256"], "secret", "configured-branch")
            request = network.call_args.args[0]
            self.assertEqual(json.loads(request.data)["branch"], "configured-branch")
            self.assertEqual(request.method, "PUT")
            self.assertEqual(receipt["commit"], "abc")


if __name__ == "__main__":
    unittest.main()
