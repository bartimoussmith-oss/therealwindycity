import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer
from civic_atlas.server import AgendaParser, Corpus, Handler, terms

class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        (self.root/'public').mkdir()
        (self.root/'pipeline/docs/42').mkdir(parents=True)
        (self.root/'public/master_meetings_database_linked.json').write_text(json.dumps([dict(id='m1',title='Water hearing',date='2026-08-10',turns=[dict(text='Water allocation at Cox Ranch.')])]))
        (self.root/'history.md').write_text('# Historical water report\nCox Ranch water allocation.')
        (self.root/'pipeline/docs/42/2026-08-10_agenda.html').write_text('<script>ignore()</script><a class="Agenda Agenda0" href="https://example.org/item">Cox Ranch <b>water</b> allocation</a>')
        self.c=Corpus(self.root)
    def tearDown(self):self.temp.cleanup()
    def test_search_returns_quotes_and_provenance(self):
        hits=self.c.search('Cox Ranch')
        self.assertEqual(len(hits),3)
        self.assertTrue(all('Cox Ranch' in h['excerpt'] for h in hits))
        self.assertTrue(all(h['path'] for h in hits))
        self.assertTrue(all('review required' in h['relation'] for h in hits))
    def test_empty_query(self):self.assertEqual(self.c.search('the and'),[])
    def test_exclusion(self):self.assertNotIn('m1',[h['id'] for h in self.c.search('water',exclude='m1')])
    def test_agenda_extraction(self):
        self.assertEqual(self.c.agendas[0]['items'][0]['title'],'Cox Ranch water allocation')
        self.assertNotIn('ignore()',self.c.byid['agenda_42']['text'])
    def test_stable_document_ids(self):
        self.assertEqual(set(self.c.byid),set(Corpus(self.root).byid))

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Handler.corpus=Corpus()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close()
    def test_catalog_and_search(self):
        data=json.load(urlopen(self.base+'/api/catalog'))
        self.assertGreater(data['count'],720)
        self.assertGreater(len(data['agendas']),0)
        hits=json.load(urlopen(self.base+'/api/search?q=Cox%20Ranch'))
        self.assertTrue(hits)
        record=json.load(urlopen(self.base+'/api/record?id='+hits[0]['id']))
        self.assertIn('text',record)
    def test_static_and_range(self):
        full=urlopen(self.base+'/app.js').read()
        r=urlopen(Request(self.base+'/app.js',headers={'Range':'bytes=0-19'}))
        self.assertEqual(r.status,206);self.assertEqual(r.read(),full[:20])
    def test_osint_pages_and_assets_are_served(self):
        for path, marker in [('/osint.html', b'Upgraded explorer'),
                             ('/osint-atlas.html', b'CIVIC ATLAS TEXT SEARCH'),
                             ('/osint-original.html', b'Gotham v2'),
                             ('/osint/app.js', b'function parseFilter'),
                             ('/osint/style.css', b'#map')]:
            with self.subTest(path=path):
                response=urlopen(self.base+path)
                self.assertEqual(response.status,200)
                self.assertIn(marker,response.read())
    def test_private_files_not_exposed(self):
        for p in ['/.git/config','/server.py','/media/%2e%2e%2fREADME.md','/api/record?id=missing']:
            with self.assertRaises(HTTPError) as e:urlopen(self.base+p)
            self.assertEqual(e.exception.code,404)
    def test_invalid_range(self):
        with self.assertRaises(HTTPError) as e:urlopen(Request(self.base+'/app.js',headers={'Range':'bytes=99999999-'}))
        self.assertEqual(e.exception.code,416)

if __name__=='__main__':unittest.main()
