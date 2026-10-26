import json
from pathlib import Path
import tempfile
import unittest
import finish_issue_newsroom as finish

class FinishNewsroomTests(unittest.TestCase):
    def test_complete_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);corpus=root/'mirror';site=root/'site'
            (corpus/'documents').mkdir(parents=True)
            (corpus/'llms.txt').write_text('Synthetic only')
            (corpus/'documents'/'2020-01-01.md').write_text('# Synthetic document\nOrdinance No. 1234 concerns sewer funding.')
            (site/'media').mkdir(parents=True)
            (site/'index.html').write_text('existing site')
            (site/'media'/'newsroom.html').write_text('editor fixture')
            result=finish.integrate(corpus,site,'synthetic-revision')
            self.assertEqual(result['included_representations'],1)
            self.assertGreater(result['editor_input_packets'],0)
            packet=json.loads((site/'newsroom/issues/water/editor.json').read_text())
            self.assertEqual(len(packet['evidence']),1)
            self.assertTrue(packet['evidence'][0]['source_url'].endswith('.md'))
            self.assertIn('media/newsroom.html?issue=',(site/'newsroom/issues/water/index.html').read_text())
            self.assertEqual((site/'index.html').read_text(),'existing site')
            self.assertEqual(finish.verify(site)['integration_revision'],'synthetic-revision')

if __name__=='__main__':
    unittest.main()
