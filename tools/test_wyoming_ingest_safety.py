"""Offline regressions for the owner-approved Chrome/five-redirect policy.

Robots checks and redirect refusal were intentionally removed in fcae4ea.
These tests mock the transport, so offline CI needs no curl_cffi installation.
"""
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import ingest

URL = 'https://example.gov/agenda'
CFG = {'identity': {'user_agent': 'CivicTest', 'strict_web': True}}


class ChromeFetchTests(unittest.TestCase):
    def setUp(self):
        ingest._LAST_HIT.clear()
        self.addCleanup(ingest._LAST_HIT.clear)
        self.requests = Mock()
        self.requests.get.return_value = types.SimpleNamespace(status_code=200, url=URL)
        self.module = patch.dict(sys.modules, {'curl_cffi': types.SimpleNamespace(requests=self.requests)})
        self.module.start()
        self.addCleanup(self.module.stop)
        wait = patch.object(ingest, '_wait')
        self.wait = wait.start()
        self.addCleanup(wait.stop)

    def test_chrome_transport_with_five_redirects(self):
        def response(*args, **kwargs):
            kwargs['content_callback'](b'hello')
            kwargs['content_callback'](b' world')
            return types.SimpleNamespace(status_code=200, url=URL)
        self.requests.get.side_effect = response
        self.assertEqual(ingest.fetch(URL, CFG), b'hello world')
        options = self.requests.get.call_args.kwargs
        self.assertEqual(options['impersonate'], 'chrome')
        self.assertTrue(options['allow_redirects'])
        self.assertEqual(options['max_redirects'], 5)
        self.assertEqual(options['timeout'], 30)
        self.assertEqual(options['curl_options'], {84: 2, 85: 2})
        self.wait.assert_called_once_with(URL, CFG)

    def test_http_or_credentials_never_requested_in_strict_mode(self):
        for url in ('http://example.gov/', 'https://name:password@example.gov/',
                    'file:///etc/passwd', 'https:///missing-host'):
            self.assertIsNone(ingest.fetch(url, CFG))
        self.requests.get.assert_not_called()
        self.wait.assert_not_called()

    def test_nonstrict_http_retains_bounded_redirects(self):
        self.assertEqual(ingest.fetch('http://example.gov/', {'identity': {}}), b'')
        options = self.requests.get.call_args.kwargs
        self.assertEqual(options['curl_options'], {84: 3, 85: 3})
        self.assertEqual(options['max_redirects'], 5)

    def test_size_limit_is_cumulative(self):
        def oversized(*args, **kwargs):
            receive = kwargs['content_callback']
            receive(b'x' * 10_000_000)
            receive(b'x' * 10_000_001)
            self.fail('Oversized response must abort the transport callback')
        self.requests.get.side_effect = oversized
        self.assertIsNone(ingest.fetch(URL, CFG))

    def test_non_success_status_is_rejected(self):
        for status in (301, 403, 404, 429, 500, 503):
            with self.subTest(status=status):
                self.requests.get.return_value.status_code = status
                self.assertIsNone(ingest.fetch(URL, CFG))

    def test_transport_error_is_rejected(self):
        self.requests.get.side_effect = RuntimeError('redirect limit or connection failed')
        self.assertIsNone(ingest.fetch(URL, CFG))


if __name__ == '__main__':
    unittest.main()
