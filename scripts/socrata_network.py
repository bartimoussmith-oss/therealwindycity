import datetime as dt
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

root = 'https://laramiecounty-letmsp.connect.socrata.com'
output = Path('scanner-results/socrata/network.json')
output.parent.mkdir(parents=True, exist_ok=True)
result = {'checked_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'credentials_used': False,
    'status': 'started', 'pages': [], 'responses': [], 'failed_requests': [], 'candidate_dataset_ids': [],
    'notice': 'Public unauthenticated diagnostic. No credentials, cookies, query strings, page text, screenshots, incident rows, or response bodies are saved. Endpoints and IDs are candidates only.'}
seen = set()
ids = set()

def safe(url):
    p = urlsplit(url)
    if p.scheme not in ('http', 'https'):
        return {'host': None, 'path': '[non-http]'}
    segments = []
    for segment in p.path.split('/'):
        if '@' in segment or len(segment) > 64 or segment.isdigit() or segment.startswith('ticket--'):
            segment = '[identifier-withheld]'
        segments.append(segment)
    return {'host': p.hostname, 'path': '/'.join(segments)}

def response_event(response):
    request = response.request
    p = safe(response.url)
    key = (p['host'], p['path'], request.resource_type, response.status)
    if key in seen or len(seen) >= 200:
        return
    seen.add(key)
    row = dict(p, http_status=response.status, resource_type=request.resource_type, method=request.method)
    try:
        if request.resource_type in ('xhr', 'fetch') and 'json' in response.headers.get('content-type', '').lower():
            body = response.json()
            row['json_type'] = type(body).__name__
            if isinstance(body, dict):
                row['top_level_keys'] = list(body.keys())[:30]
                row['list_lengths'] = {k: len(v) for k, v in body.items() if isinstance(v, list)}
            elif isinstance(body, list):
                row['list_length'] = len(body)
            ids.update(re.findall(r'\b[a-z0-9]{4}-[a-z0-9]{4}\b', json.dumps(body)))
    except Exception:
        row['inspection'] = 'unavailable'
    result['responses'].append(row)

try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        context.on('response', response_event)
        def failed(request):
            if len(result['failed_requests']) < 100:
                result['failed_requests'].append(dict(safe(request.url), resource_type=request.resource_type))
        context.on('requestfailed', failed)
        for label, url in [('dashboard', root + '/#!/dashboard?start_date=2020-01-01&end_date=2026-10-21&autoUpdate=false'), ('login_entry', root + '/auth_login.html?auto_close=true')]:
            page = context.new_page()
            record = {'page': label}
            try:
                response = page.goto(url, wait_until='domcontentloaded', timeout=60000)
                record['document_http_status'] = response.status if response else None
                page.wait_for_timeout(45000)
                record['final_location'] = safe(page.url)
                record['visible_password_fields'] = page.locator('input[type="password"]:visible').count()
                record['visible_email_fields'] = page.locator('input[type="email"]:visible').count()
                record['iframe_hosts'] = sorted({urlsplit(frame.url).hostname for frame in page.frames if urlsplit(frame.url).hostname})
                record['script_hosts'] = sorted({urlsplit(url).hostname for url in page.locator('script[src]').evaluate_all('(nodes) => nodes.map(n => n.src)') if urlsplit(url).hostname})
                record['body_child_count'] = page.locator('body > *').count()
            except Exception as exc:
                record['error_type'] = type(exc).__name__
            result['pages'].append(record)
            page.close()
        browser.close()
    result['status'] = 'finished_requires_analysis'
except Exception as exc:
    result['status'] = 'failed'
    result['error_type'] = type(exc).__name__
result['candidate_dataset_ids'] = sorted(ids)[:100]
output.write_text(json.dumps(result, indent=2) + '\n')
