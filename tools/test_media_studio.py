import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'civic_atlas' / 'media'

class MediaStudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((SRC / 'drops.json').read_text(encoding='utf-8'))

    def test_source_blob_versions(self):
        for s in self.data['sources']:
            with self.subTest(source=s['id']):
                raw = (ROOT / s['path']).read_bytes()
                digest = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
                self.assertEqual(digest, s['git_blob_sha'])

    def test_excerpts_and_distinct_ids(self):
        ids = [d['id'] for d in self.data['drops']]
        self.assertEqual(len(ids), len(set(ids)))
        sources = {s['id']: s for s in self.data['sources']}
        for d in self.data['drops']:
            with self.subTest(drop=d['id']):
                s = sources[d['source_id']]
                text = (ROOT / s['path']).read_text(encoding='utf-8')
                normalize = lambda t: re.sub(r'\s+', ' ', t).strip()
                self.assertIn(normalize(d['excerpt']), normalize(text))
                self.assertTrue(d['limits'])
                self.assertTrue(d['locator'])
                self.assertEqual(d['date'], s['event_date'])
        self.assertEqual({d['date'][:4] for d in self.data['drops']}, {'2008', '2012', '2026'})

    def test_local_page_assets(self):
        for name in ('index.html', 'builder.html', 'review.html'):
            text = (SRC / name).read_text(encoding='utf-8')
            self.assertIn('id="app"', text)
            self.assertIn('studio.js', text)
            self.assertIn('studio.css', text)
            self.assertNotIn('onclick=', text)
        script = (SRC / 'studio.js').read_text(encoding='utf-8')
        self.assertNotIn('innerHTML', script)
        self.assertIn('NO VIDEO RENDERED', script)

    def test_copy_preserves_existing_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'index.html').write_text('existing site', encoding='utf-8')
            (out / 'osint-atlas.html').write_text('existing atlas', encoding='utf-8')
            subprocess.run([sys.executable, str(ROOT / 'tools/publish_media_studio.py'), '--out', tmp], check=True)
            self.assertEqual((out / 'index.html').read_text(), 'existing site')
            self.assertEqual((out / 'osint-atlas.html').read_text(), 'existing atlas')
            for name in ('index.html', 'builder.html', 'review.html', 'drops.json', 'studio.css', 'studio.js'):
                self.assertEqual((out / 'media' / name).read_bytes(), (SRC / name).read_bytes())

    def test_refuses_empty_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = subprocess.run([sys.executable, str(ROOT / 'tools/publish_media_studio.py'), '--out', tmp], capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertFalse((Path(tmp) / 'media').exists())

if __name__ == '__main__':
    unittest.main()
