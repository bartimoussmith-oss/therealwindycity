"""Self-contained integration artifacts; these tests need no Streamlit dependency."""
import unittest
from civic_atlas.streamlit_integration import evidence_map_html, portable_lens_html, script_json

class IntegrationTests(unittest.TestCase):
    def test_lens_has_no_external_asset_dependency(self):
        html=portable_lens_html()
        self.assertNotIn('<script src=',html)
        self.assertNotIn('href="/style.css"',html)
        self.assertIn('getDisplayMedia',html)
        self.assertIn('switchView(\'lens\')',html)
        self.assertIn('window.fetch=async',html)
    def test_source_label_cannot_close_script(self):
        html=portable_lens_html('</script><img src=x onerror=alert(1)>','javascript:alert(1)')
        self.assertNotIn('</script><img src=x',html)
        self.assertIn('\\u003c/script\\u003e',html)
        self.assertIn('/^https:',html)
    def test_map_data_escaped(self):
        html=evidence_map_html('</script><img onerror=x>',[dict(id='x',title='Untrusted <b> text',path='README.md',kind='Repository document',excerpt='Quoted text')])
        self.assertNotIn('</script><img',html)
        self.assertIn('\\u003c/script',html)
        self.assertIn('.textContent=',html)
    def test_map_result_limit(self):
        html=evidence_map_html('Water',[{'title':f'unique-{i}'} for i in range(20)])
        self.assertIn('unique-11',html)
        self.assertNotIn('unique-12',html)

if __name__=='__main__':unittest.main()
