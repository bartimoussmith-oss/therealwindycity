import copy
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
import publish_media_studio as studio

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'civic_atlas' / 'media'

class MediaStudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = studio.validate(SRC)

    def test_source_blob_versions(self):
        for s in self.data['sources']:
            raw = (ROOT / s['path']).read_bytes()
            digest = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            self.assertEqual(digest,s['git_blob_sha'])

    def test_excerpts_and_ids(self):
        ids = [d['id'] for d in self.data['drops']]
        self.assertEqual(len(ids),len(set(ids)))
        sources = {s['id']:s for s in self.data['sources']}
        # OCR may insert spaces within words. Ignore only whitespace, not letters or punctuation.
        compact = lambda t: re.sub(r'\s+','',t)
        for d in self.data['drops']:
            s = sources[d['source_id']]
            text = (ROOT / s['path']).read_text(encoding='utf-8')
            self.assertIn(compact(d['excerpt']),compact(text),d['id'])
            self.assertEqual(d['date'],s['event_date'])
            self.assertTrue(d['limits'])
        self.assertEqual({d['date'][:4] for d in self.data['drops']},{'2008','2012','2026'})

    def test_assets_and_reader_links(self):
        for name in ('index.html','builder.html','review.html'):
            text = (SRC / name).read_text(encoding='utf-8')
            self.assertIn('studio.js',text)
            self.assertIn('packages/index.html',text)
        script = (SRC / 'studio.js').read_text(encoding='utf-8')
        self.assertNotIn('innerHTML',script)
        self.assertIn('NO VIDEO RENDERED',script)

    def test_publish_preserves_site_and_renders_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'index.html').write_text('existing site')
            (out / 'osint-atlas.html').write_text('existing atlas')
            manifest = studio.publish(SRC,out)
            self.assertEqual((out / 'index.html').read_text(),'existing site')
            self.assertEqual((out / 'osint-atlas.html').read_text(),'existing atlas')
            self.assertEqual(len(manifest),len(self.data['drops']))
            for d in self.data['drops']:
                folder = out / 'media/packages' / d['id']
                article = (folder / 'index.html').read_text(encoding='utf-8')
                self.assertIn('HISTORICAL REWIND',article)
                self.assertIn('Newsletter',article)
                self.assertIn('Youtube Description',article)
                self.assertIn('Browser carousel',article)
                for file in ('package.json','package.zip','newsletter.txt','social-caption.txt','video-script.txt'):
                    self.assertTrue((folder / file).is_file())
                with zipfile.ZipFile(folder / 'package.zip') as z:
                    self.assertIn('index.html',z.namelist())
                    self.assertIn('article.txt',z.namelist())
                    self.assertNotIn('../index.html',z.read('index.html').decode())

    def test_escape_untrusted_text(self):
        d = copy.deepcopy(self.data['drops'][0])
        d['finding'] = '<script>alert(1)</script>'
        s = next(s for s in self.data['sources'] if s['id']==d['source_id'])
        result = studio.package_files(d,s,'coverage')
        self.assertNotIn('<script>alert(1)</script>',result['index.html'])
        self.assertIn('&lt;script&gt;',result['index.html'])
        with self.assertRaises(ValueError):
            studio.safe_url('javascript:alert(1)')

    def test_refuses_empty_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                studio.publish(SRC,Path(tmp))

if __name__ == '__main__':
    unittest.main()
