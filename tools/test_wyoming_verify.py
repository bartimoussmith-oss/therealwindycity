import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import wyoming_verify as v

URL = 'https://example.gov'

class VerifierSafetyTests(unittest.TestCase):
    def setUp(self):
        self.entry = dict(slug='fixture', name='Fixture', type='town')
        self.fetcher = Mock()
        self.fetcher.allowed.return_value = (True, 'fixture')
        self.fetcher.get.return_value = (200, 'fixture page', None)
        self.candidates = patch.object(v.gen, 'candidate_domains', return_value=[URL], create=True)
        self.candidates.start()
        self.addCleanup(self.candidates.stop)

    def test_unapproved_200_is_not_verified(self):
        result = v.verify(self.entry, self.fetcher, False)
        self.assertEqual(result['verification'], 'unverified')
        self.assertTrue(result['candidates'][0]['reachable'])

    def test_approved_200_is_verified(self):
        self.entry['approved_source_urls'] = [URL]
        self.assertEqual(v.verify(self.entry, self.fetcher, False)['verified_url'], URL)

    def test_deny_overrides_approval_without_network(self):
        self.entry.update(approved_source_urls=[URL], denied_source_urls=[URL])
        result = v.verify(self.entry, self.fetcher, False)
        self.assertEqual(result['verification'], 'unverified')
        self.fetcher.allowed.assert_not_called()
        self.fetcher.get.assert_not_called()

    def test_robots_denial_prevents_page_fetch(self):
        self.fetcher.allowed.return_value = (False, 'disallowed')
        v.verify(self.entry, self.fetcher, False)
        self.fetcher.get.assert_not_called()

    def test_empty_200_is_not_verified(self):
        self.entry['approved_source_urls'] = [URL]
        self.fetcher.get.return_value = (200, '', None)
        self.assertEqual(v.verify(self.entry, self.fetcher, False)['verification'], 'unverified')

    def test_nonapply_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(v.gen, 'INSTANCES_DIR', Path(temp), create=True):
            v.verify(self.entry, self.fetcher, False)
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_apply_preserves_local_facts_and_env(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(v.gen, 'INSTANCES_DIR', Path(temp), create=True):
            directory = Path(temp) / 'fixture'
            (directory / 'config').mkdir(parents=True)
            facts = directory / 'config/facts.json'
            env = directory / 'env.sh'
            facts.write_text('source-backed local facts')
            env.write_text('confirmed custodian')
            with patch.object(v.gen, 'sources_for', return_value={'sources': []}, create=True):
                result = v.verify(self.entry, self.fetcher, True)
            self.assertTrue(result['applied'])
            self.assertEqual(facts.read_text(), 'source-backed local facts')
            self.assertEqual(env.read_text(), 'confirmed custodian')
            self.assertEqual(json.loads((directory / 'verification.json').read_text())['slug'], 'fixture')

    def test_failed_probe_replaces_stale_verification(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(v.gen, 'INSTANCES_DIR', Path(temp), create=True):
            directory = Path(temp) / 'fixture'
            (directory / 'config').mkdir(parents=True)
            path = directory / 'verification.json'
            path.write_text(json.dumps({'verification': 'live-verified', 'verified_url': URL}))
            self.fetcher.get.return_value = (503, '', 'unavailable')
            with patch.object(v.gen, 'sources_for', return_value={'sources': []}, create=True) as render:
                v.verify(self.entry, self.fetcher, True)
                render.assert_called_once()
            self.assertEqual(json.loads(path.read_text())['verification'], 'unverified')

    def test_robots_missing_404_allowed(self):
        fetcher = v.Fetcher(3, 1)
        with patch.object(fetcher, 'get', return_value=(404, '', 'HTTP 404')):
            self.assertTrue(fetcher.allowed(URL)[0])

    def test_robots_503_fails_closed(self):
        fetcher = v.Fetcher(3, 1)
        with patch.object(fetcher, 'get', return_value=(503, '', 'HTTP 503')):
            self.assertFalse(fetcher.allowed(URL)[0])

    def test_robots_disallow_is_enforced(self):
        fetcher = v.Fetcher(3, 1)
        with patch.object(fetcher, 'get', return_value=(200, 'User-agent: *\nDisallow: /', None)):
            self.assertFalse(fetcher.allowed(URL)[0])

    def test_robots_is_cached_per_origin(self):
        fetcher = v.Fetcher(3, 1)
        with patch.object(fetcher, 'get', return_value=(200, 'User-agent: *\nAllow: /', None)) as get:
            fetcher.allowed(URL + '/a')
            fetcher.allowed(URL + '/b')
            get.assert_called_once()

    def test_robots_crawl_delay_respected(self):
        fetcher = v.Fetcher(3, 1)
        with patch.object(fetcher, 'get', return_value=(200, 'User-agent: *\nCrawl-delay: 9\nAllow: /', None)):
            fetcher.allowed(URL)
            self.assertEqual(fetcher.delay, 9)

    def test_robots_html_error_page_fails_closed(self):
        fetcher = v.Fetcher(3, 1)
        with patch.object(fetcher, 'get', return_value=(200, '<html>blocked</html>', None)):
            self.assertFalse(fetcher.allowed(URL)[0])

    def test_redirects_not_followed(self):
        self.assertIsNone(v.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.gov'))

    def test_http_and_credentials_rejected(self):
        fetcher = v.Fetcher(3, 1)
        for url in ['http://example.gov', 'https://user:password@example.gov']:
            self.assertIsNone(fetcher.get(url)[0])

if __name__ == '__main__':
    unittest.main()
