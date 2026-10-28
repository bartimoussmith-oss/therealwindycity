from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
import finish_issue_newsroom as finish

class FinishNewsroomTests(unittest.TestCase):
    def test_compaction_preserves_complete_sources_and_membership(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);corpus=root/'mirror';site=root/'site'
            (corpus/'documents').mkdir(parents=True)
            (corpus/'llms.txt').write_text('Synthetic only')
            text='# Synthetic document\nOrdinance No. 1234 concerns sewer funding.\n'+'water budget source text '*5000
            path='documents/2020-01-01.md'
            (corpus/path).write_text(text,encoding='utf-8')
            (site/'documents').mkdir(parents=True)
            original=(corpus/path).read_bytes()
            (site/path).write_bytes(original)
            (site/'media').mkdir()
            (site/'index.html').write_text('existing site')
            (site/'media/newsroom.html').write_text('editor fixture')
            result=finish.integrate(corpus,site,'synthetic-revision')
            self.assertEqual(result['included_representations'],1)
            self.assertEqual((site/path).read_bytes(),original)
            self.assertEqual((site/'index.html').read_text(),'existing site')
            self.assertEqual(result['storage']['truncated_records'],0)
            self.assertLess(result['storage']['newsroom_after_compaction_bytes'],result['storage']['newsroom_before_compaction_bytes'])
            packet=json.loads((site/'newsroom/issues/water/editor.json').read_text())
            self.assertEqual(len(packet['evidence']),1)
            e=packet['evidence'][0]
            self.assertEqual(e['source_version'],sha256(original).hexdigest())
            self.assertTrue(all(set(p)=={'line'} for p in e['passages']))
            self.assertIn('media/newsroom.html?issue=',(site/'newsroom/issues/water/index.html').read_text())
            self.assertFalse(list((site/'newsroom/records').glob('*/text.txt')))
            self.assertEqual(finish.verify(site)['integration_revision'],'synthetic-revision')
            (site/path).write_text('tampered')
            with self.assertRaises(ValueError): finish.verify(site)

    def test_missing_canonical_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);corpus=root/'mirror';site=root/'site'
            (corpus/'documents').mkdir(parents=True)
            (corpus/'llms.txt').write_text('Synthetic only')
            (corpus/'documents/test.md').write_text('# Water fixture')
            (site/'media').mkdir(parents=True)
            (site/'index.html').write_text('existing')
            (site/'media/newsroom.html').write_text('fixture')
            with self.assertRaises(ValueError): finish.integrate(corpus,site,'test')

if __name__=='__main__': unittest.main()
