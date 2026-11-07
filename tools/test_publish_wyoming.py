import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('publish_wyoming', Path(__file__).with_name('publish_wyoming.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class PublishWyomingTests(unittest.TestCase):
    def fixture(self, root):
        entries = [{'slug':'example-town','name':'Example <Town>','type':'town'}]
        (root/'wyoming').mkdir()
        (root/'wyoming/registry.json').write_text(json.dumps({'counts':{'total_instances':1},'jurisdictions':entries}))
        folder = root/'wyoming/instances/example-town/config'
        folder.mkdir(parents=True)
        source = folder/'sources.json'
        source.write_text(json.dumps({'sources':[{'name':'candidate','url':'https://example.gov','enabled':False},{'name':'bad','url':'javascript:alert(1)','enabled':False}]}))
        return source
    def test_truthful_pages_and_preserved_config(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); source = self.fixture(root); before = source.read_bytes()
            out = root/'site'; out.mkdir(); (out/'index.html').write_text('<html><body>Original Cheyenne</body></html>')
            result = m.build(root,out,'test-sha')
            self.assertEqual(source.read_bytes(),before)
            self.assertIsNone(result['verified_reporting_jurisdictions'])
            self.assertFalse(result['jurisdictions'][0]['reporting_verified'])
            page = (out/'wyoming/example-town/index.html').read_text()
            self.assertIn('Example &lt;Town&gt;',page)
            self.assertNotIn('javascript:',page)
            self.assertIn('Original Cheyenne',(out/'index.html').read_text())
            m.build(root,out,'test-sha')
            self.assertEqual((out/'index.html').read_text().count('data-wyoming-directory'),1)
    def test_bad_registry_fails(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); self.fixture(root)
            p = root/'wyoming/registry.json'; data = json.loads(p.read_text()); data['counts']['total_instances']=2; p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                m.build(root,root/'site','test')
    def test_urls(self):
        self.assertIsNone(m.safe_url('https://user:secret@example.gov'))
        self.assertIsNone(m.safe_url('http://example.gov'))
        self.assertEqual(m.safe_url('https://example.gov'),'https://example.gov')

if __name__ == '__main__':
    unittest.main()
