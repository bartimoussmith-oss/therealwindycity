"""Offline regressions for the strict statewide HTTP policy."""
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import ingest

URL = 'https://example.gov/agenda'
CFG = {'identity': {'user_agent': 'CivicTest', 'strict_web': True}}

class StrictFetchTests(unittest.TestCase):
    def setUp(self):
        ingest._ROBOTS.clear()
        ingest._LAST_HIT.clear()
        self.addCleanup(ingest._ROBOTS.clear)
        self.addCleanup(ingest._LAST_HIT.clear)

    def test_unavailable_robots_fails_closed(self):
        for status in (301, 302, 403, 429, 500, 503):
            with self.subTest(status=status), patch('urllib.request.build_opener') as opener:
                opener.return_value.open.side_effect = urllib.error.HTTPError(URL, status, 'blocked', {}, None)
                self.assertFalse(ingest._allowed(URL, CFG))

    def test_missing_robots_is_allowed(self):
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect = urllib.error.HTTPError(URL, 404, 'missing', {}, None)
            self.assertTrue(ingest._allowed(URL, CFG))

    def test_html_robots_is_rejected(self):
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = b'<html>Access denied</html>'
            self.assertFalse(ingest._allowed(URL, CFG))

    def test_http_or_credentials_never_requested(self):
        with patch.object(ingest, '_allowed') as allowed:
            for url in ('http://example.gov/', 'https://name:password@example.gov/'):
                self.assertIsNone(ingest.fetch(url, CFG))
            allowed.assert_not_called()

    def test_owner_policy_skips_robots_but_keeps_rate_limit(self):
        cfg = {'identity': dict(CFG['identity'], respect_robots=False)}
        with patch.object(ingest, '_allowed', return_value=False) as allowed, patch.object(ingest, '_wait') as wait, patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = b'public document'
            self.assertEqual(ingest.fetch(URL, cfg), b'public document')
            allowed.assert_not_called()
            wait.assert_called_once_with(URL, cfg)
            self.assertEqual(opener.return_value.open.call_count, 1)
            self.assertEqual(opener.return_value.open.call_args.args[0].full_url, URL)

    def test_owner_policy_does_not_bypass_http_access_denial(self):
        cfg = {'identity': dict(CFG['identity'], respect_robots=False)}
        with patch.object(ingest, '_allowed') as allowed, patch.object(ingest, '_wait'), patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect = urllib.error.HTTPError(URL, 403, 'Forbidden', {}, None)
            self.assertIsNone(ingest.fetch(URL, cfg))
            allowed.assert_not_called()

    def test_redirect_handler_refuses_follow(self):
        self.assertIsNone(ingest._NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.gov/'))

    def test_size_limit(self):
        with patch.object(ingest, '_allowed', return_value=True), patch.object(ingest, '_wait'), patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = b'x' * 20_000_001
            self.assertIsNone(ingest.fetch(URL, CFG))

if __name__ == '__main__':
    unittest.main()
