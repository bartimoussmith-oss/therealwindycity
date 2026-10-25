"""Run in an environment with the repository's Streamlit requirement installed."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest=None

@unittest.skipIf(AppTest is None,'Streamlit is not installed')
class StreamlitIntegrationTests(unittest.TestCase):
    def app(self,path):
        app=AppTest.from_file(str(ROOT/path),default_timeout=60).run()
        self.assertFalse(list(app.exception),[e.message for e in app.exception])
        return app
    def test_atlas_map_and_enabled_lens(self):
        app=self.app('pages/25_Civic_Atlas.py')
        self.assertEqual(app.title[0].value,'Civic Atlas + Dais Lens')
        self.assertTrue(app.selectbox)
        app.checkbox[0].check().run()
        self.assertFalse(list(app.exception))
        self.assertEqual(len(app.get('download_button')),2)
    def test_source_agenda_mode(self):
        app=self.app('pages/25_Civic_Atlas.py')
        app.radio[0].set_value('Archived agenda item').run()
        self.assertFalse(list(app.exception))
        self.assertTrue(any(s.label=='Agenda item' for s in app.selectbox))
    def test_pasted_agenda(self):
        app=self.app('pages/25_Civic_Atlas.py')
        app.radio[0].set_value('Paste agenda').run()
        app.text_area[0].input('Cox Ranch water allocation\nTransit funding grant').run()
        self.assertFalse(list(app.exception))
        self.assertTrue(any(s.label=='Line to investigate' for s in app.selectbox))
    def test_home_links_integrated_page(self):
        app=self.app('streamlit_app.py')
        self.assertTrue(any('Civic Atlas' in e.proto.label for e in app.get('page_link')))
    def test_existing_video_pages_offer_lens(self):
        for path in ['pages/15_Origin_Tapes.py','pages/16_The_Tapes.py','pages/16a_Miller_Tapes.py','pages/16b_Screening_Room.py']:
            with self.subTest(page=path):
                app=self.app(path)
                options=[c for c in app.checkbox if 'Dais Lens' in c.label]
                # Some installations lack local rendered MP4s; Miller playlist is still available.
                if options:
                    options[0].check().run()
                    self.assertFalse(list(app.exception))
                if '16a' in path:self.assertTrue(options)
    def test_twins_identical(self):
        from pathlib import Path
        self.assertEqual(Path('streamlit_app.py').read_bytes(),Path('Transparency_Index_App.py').read_bytes())

if __name__=='__main__':unittest.main()
