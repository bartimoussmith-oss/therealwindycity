import datetime as dt
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
import requests
from playwright.sync_api import sync_playwright

portal = 'https://laramiecounty-letmsp.connect.socrata.com/'
output = Path('scanner-results/socrata/connection.json')
output.parent.mkdir(parents=True, exist_ok=True)
report = {'checked_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'portal': portal,
    'status': 'diagnostic_started', 'authentication_verified': False, 'correlation_enabled': False,
    'notice': 'Read-only diagnostic. Endpoint candidates are not verified incident datasets. No account details, cookies, credentials, or incident rows are published.',
    'auth_probe': {}, 'dashboard_requests': [], 'candidate_dataset_ids': [], 'errors': []}

def save():
    output.write_text(json.dumps(report, indent=2) + '\n')

def identity(response):
    try:
        data = response.json()
        if response.status_code == 200 and isinstance(data, dict):
            return data.get('id') or data.get('user', {}).get('id')
    except (ValueError, AttributeError):
        pass
    return None

save()
username = os.environ.get('SOCRATA_USERNAME', '')
password = os.environ.get('SOCRATA_PASSWORD', '')
report['secrets_present'] = bool(username and password)
if username and password:
    try:
        url = 'https://tylertech.data.socrata.com/api/users/current.json'
        anonymous = requests.get(url, timeout=30, allow_redirects=False)
        authenticated = requests.get(url, auth=(username, password), timeout=30, allow_redirects=False)
        anonymous_id = identity(anonymous)
        authenticated_id = identity(authenticated)
        verified = bool(authenticated_id and authenticated_id != anonymous_id and str(authenticated_id).lower() not in ('anonymous', 'anon'))
        report['authentication_verified'] = verified
        report['auth_probe'] = {'host': 'tylertech.data.socrata.com', 'anonymous_http_status': anonymous.status_code,
            'authenticated_http_status': authenticated.status_code, 'distinct_authenticated_identity': verified,
            'notice': 'A successful account probe does not establish permission to read the Laramie incident dataset.'}
    except Exception as exc:
        report['errors'].append({'stage': 'authentication_probe', 'error_type': type(exc).__name__})
save()
seen = set()
candidates = set()
try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        def observe(response):
            parts = urlsplit(response.url)
            host = parts.hostname or ''
            if not (host == 'socrata.com' or host.endswith('.socrata.com')):
                return
            if response.request.resource_type not in ('xhr', 'fetch', 'document'):
                return
            safe_path = re.sub(r'/ticket[^/]*', '/[record-id-withheld]', parts.path)
            endpoint = parts.scheme + '://' + host + safe_path
            if endpoint in seen or len(seen) >= 100:
                return
            seen.add(endpoint)
            item = {'endpoint_without_query': endpoint, 'http_status': response.status, 'resource_type': response.request.resource_type}
            try:
                if 'json' in response.headers.get('content-type', '').lower():
                    body = response.json()
                    item['json_type'] = type(body).__name__
                    if isinstance(body, dict):
                        item['top_level_keys'] = list(body.keys())[:30]
                    text = json.dumps(body)
                    candidates.update(re.findall(r'\b[a-z0-9]{4}-[a-z0-9]{4}\b', text))
            except Exception:
                item['body_inspection'] = 'unavailable'
            report['dashboard_requests'].append(item)
        page.on('response', observe)
        try:
            page.goto(portal + '#!/dashboard', wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(30000)
            report['dashboard_loaded'] = True
        except Exception as exc:
            report['errors'].append({'stage': 'dashboard_navigation', 'error_type': type(exc).__name__})
        browser.close()
except Exception as exc:
    report['errors'].append({'stage': 'browser_setup', 'error_type': type(exc).__name__})
report['candidate_dataset_ids'] = sorted(candidates)[:100]
report['status'] = 'diagnostic_finished_requires_endpoint_validation'
save()
