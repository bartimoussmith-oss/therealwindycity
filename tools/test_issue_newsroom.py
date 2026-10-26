import json
from pathlib import Path
import tempfile
import unittest
import issue_newsroom as newsroom

class IssueNewsroomTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.corpus = self.root/'mirror'
        self.corpus.mkdir()
        (self.corpus/'llms.txt').write_text('Synthetic public fixture only',encoding='utf-8')
        (self.corpus/'documents').mkdir()
        (self.corpus/'meetings').mkdir()
        (self.corpus/'documents'/'2020-01-01.md').write_text('# Synthetic fixture\nOrdinance No. 1234 concerns sewer funding.\n<script>alert(1)</script>',encoding='utf-8')
        (self.corpus/'documents'/'other.md').write_text('# Unassigned fixture\nAn unrelated sentence.',encoding='utf-8')
        (self.corpus/'meetings'/'2020-01-01.md').write_text('# Synthetic meeting\nOrdinance No. 1234 was discussed; outcome not stated.',encoding='utf-8')

    def test_dossiers_coverage_and_full_text(self):
        out = self.root/'site'
        report = newsroom.build(self.corpus,out,'synthetic-test',True)
        self.assertEqual(report['included_representations'],3)
        self.assertEqual(report['unassigned_records'],1)
        self.assertFalse(report['full_historical_coverage'])
        issues = json.loads((out/'issues.json').read_text())
        group = next(i for i in issues if i['id']=='identifier-ordinance-1234')
        self.assertEqual(len(group['members']),2)
        self.assertTrue((out/'issues'/'water'/'index.html').is_file())
        queue = json.loads((out/'issues'/'identifier-ordinance-1234'/'story-queue.json').read_text())
        self.assertEqual(len(queue),6)
        self.assertTrue(all(d['status']=='reporting_prompt_not_publishable_story' for d in queue))
        pages = list((out/'records').glob('*/index.html'))
        self.assertTrue(all('<script>alert(1)</script>' not in p.read_text() for p in pages))
        original = (self.corpus/'documents'/'2020-01-01.md').read_bytes()
        self.assertTrue(any(p.read_bytes()==original for p in (out/'records').glob('*/text.txt')))

    def test_guards(self):
        with self.assertRaises(ValueError):
            newsroom.build(self.corpus,self.root/'denied','test',False)
        with self.assertRaises(ValueError):
            newsroom.build(self.corpus,self.corpus/'nested','test',True)
        out = self.root/'site'
        newsroom.build(self.corpus,out,'test',True)
        with self.assertRaises(ValueError):
            newsroom.build(self.corpus,out,'test',True)

    def test_exclusions(self):
        (self.corpus/'unapproved.md').write_text('Not a record path')
        (self.corpus/'documents'/'invalid.md').write_bytes(b'\xff')
        report = newsroom.build(self.corpus,self.root/'site','test',True)
        self.assertEqual(len(report['excluded']),2)

if __name__ == '__main__':
    unittest.main()
