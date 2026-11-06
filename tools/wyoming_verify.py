#!/usr/bin/env python3
"""Conservative jurisdiction probing. HTTP success does not establish authority.
Registry approved_source_urls must contain exact reviewed URLs to enable them.
Registry denied_source_urls always wins. Non-apply runs print reports only.
Redirects are deliberately not followed: approve and probe the destination explicitly.
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import wyoming_instantiate as gen

UA = 'WyomingCivicTransparencyEngine/0.2 (+https://github.com/bartimoussmith-oss/therealwindycity/issues)'

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class Fetcher:
    def __init__(self, delay, timeout):
        self.delay, self.timeout = delay, timeout
        self.last, self.robots = {}, {}
        self.opener = urllib.request.build_opener(NoRedirect())

    def get(self, url):
        p = urllib.parse.urlsplit(url)
        if p.scheme != 'https' or not p.hostname or p.username or p.password:
            return None, '', 'Only credential-free HTTPS URLs are permitted'
        host = p.netloc
        time.sleep(max(0, self.delay - (time.monotonic() - self.last.get(host, 0))))
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with self.opener.open(req, timeout=self.timeout) as response:
                raw = response.read(400001)
                if len(raw) > 400000:
                    return response.status, '', 'Response exceeds probe size limit'
                return response.status, raw.decode('utf-8', errors='replace'), None
        except urllib.error.HTTPError as exc:
            return exc.code, '', 'HTTP ' + str(exc.code)
        except Exception as exc:
            return None, '', type(exc).__name__ + ': ' + str(exc)
        finally:
            self.last[host] = time.monotonic()

    def allowed(self, url):
        p = urllib.parse.urlsplit(url)
        origin = p.scheme + '://' + p.netloc
        if origin not in self.robots:
            status, text, error = self.get(origin + '/robots.txt')
            if status == 404:
                self.robots[origin] = (None, 'robots.txt absent (404)')
            elif status == 200 and not error and '<html' not in text.lower():
                parser = urllib.robotparser.RobotFileParser()
                parser.parse(text.splitlines())
                self.robots[origin] = (parser, 'robots.txt fetched')
            else:
                self.robots[origin] = (False, 'robots.txt unavailable or invalid; probe blocked')
        parser, note = self.robots[origin]
        allowed = parser is None or (parser is not False and parser.can_fetch(UA, url))
        if allowed and parser is not None:
            wait = parser.crawl_delay(UA) or parser.crawl_delay('*') or 0
            self.delay = max(self.delay, wait)
        return allowed, note

def verify(entry, fetcher, apply):
    slug = entry['slug']
    approved = set(entry.get('approved_source_urls', []))
    denied = set(entry.get('denied_source_urls', []))
    result = dict(slug=slug, name=entry['name'], type=entry['type'],
                  checked_at=datetime.now(timezone.utc).isoformat(), candidates=[],
                  verified_url=None, platform='unknown', agenda_paths=[],
                  verification='unverified', applied=False, notes=[])
    candidates = list(dict.fromkeys(gen.candidate_domains(entry) + sorted(approved)))
    for url in candidates:
        row = dict(url=url, status=None, reachable=False, approved=url in approved, denied=url in denied)
        result['candidates'].append(row)
        if url in denied:
            continue
        allowed, row['robots'] = fetcher.allowed(url)
        row['robots_allowed'] = allowed
        if not allowed:
            continue
        status, text, error = fetcher.get(url)
        row.update(status=status, reachable=status == 200 and bool(text), error=error)
        if row['reachable'] and url in approved and result['verified_url'] is None:
            result.update(verified_url=url, verification='live-verified')
    result['notes'].append('Only exact registry-approved URLs can enable sources; approval is a human assertion, not proof supplied by HTTP. No agenda portal is auto-enabled.')
    if apply:
        directory = gen.INSTANCES_DIR / slug
        path = directory / 'verification.json'
        result['applied'] = True
        path.write_text(json.dumps(result, indent=2) + '\n')
        sources = gen.sources_for(entry)
        (directory / 'config' / 'sources.json').write_text(json.dumps(sources, indent=2) + '\n')
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--all', action='store_true')
    group.add_argument('--slug')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--delay', type=float, default=3)
    parser.add_argument('--timeout', type=float, default=12)
    args = parser.parse_args()
    if args.delay < 3 or args.timeout <= 0:
        parser.error('delay must be at least 3 seconds and timeout must be positive')
    entries = gen.load_registry()['jurisdictions']
    if args.slug:
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', args.slug):
            parser.error('invalid slug')
        entries = [e for e in entries if e['slug'] == args.slug]
    if not entries:
        parser.error('no registered jurisdictions selected')
    fetcher = Fetcher(args.delay, args.timeout)
    results = []
    for entry in entries:
        try:
            results.append(verify(entry, fetcher, args.apply))
        except Exception as exc:
            results.append(dict(slug=entry['slug'], verification='error', error=str(exc)))
    summary = dict(total=len(results),
                   live_verified=sum(r['verification'] == 'live-verified' for r in results),
                   unverified=sum(r['verification'] == 'unverified' for r in results),
                   errors=sum(r['verification'] == 'error' for r in results),
                   applied=sum(bool(r.get('applied')) for r in results), results=results)
    print(json.dumps(summary, indent=None if args.json else 2))
    return 1 if summary['errors'] else 0

if __name__ == '__main__':
    raise SystemExit(main())
