import datetime as dt
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
import requests
from playwright.sync_api import sync_playwright

PORTAL = 'https://laramiecounty-letmsp.connect.socrata.com'
LOGIN = PORTAL + '/auth_login.html?auto_close=true'
DASHBOARD = PORTAL + '/#!/dashboard?places=&restrictedPlaces=&categories=1:3130%3D2-226,228-267,273-285,299-360%263145%3D2-187,189-221,227-239,248-304%7C2:2056%3D1-27,34-96,103,107-117%262059%3D1-24,30-64,66-89,95,99-109&start_date=2020-01-01&end_date=2026-10-04&lat=41.11534638911769&lng=-104.83519077301025&zoom=9&highlightMarkerId=ticket--538393&shapeIds=&shapeGroupId=jgtq-znyx&currentTab=list&showSideBar=true&mapType=ChoroplethMap&listViewTab=Data&overlayLayers=Precinct&search_field=&search_value=&autoUpdate=false&heatFilters=&statusFilter=&choroplethField=count&choroplethCategory=&searchType=place&include_restricted_places=false'
ALLOWED = {'laramiecounty-letmsp.connect.socrata.com', 'tylertech.data.socrata.com'}
output = Path('scanner-results/socrata/connection.json')
output.parent.mkdir(parents=True, exist_ok=True)
report = {'checked_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'portal': PORTAL,
    'login_entry': LOGIN, 'status': 'started', 'login_form_submitted': False,
    'authentication_verified': False, 'correlation_enabled': False,
    'dashboard_date_filter': {'start': '2020-01-01', 'end': '2026-10-04'},
    'notice': 'Read-only diagnostic. No account details, cookies, credentials, screenshots, HTML dumps, or incident rows are published. Candidate endpoints require validation. Dashboard retains supplied filters, not full archive scope.',
    'dashboard_requests': [], 'candidate_dataset_ids': [], 'errors': []}

def save():
    output.write_text(json.dumps(report, indent=2) + '\n')

def trusted(page):
    parts = urlsplit(page.url)
    report['login_destination_host'] = parts.hostname
    if parts.scheme != 'https' or parts.hostname not in ALLOWED:
        report['status'] = 'unrecognized_login_destination_no_credentials_sent'
        save()
        raise RuntimeError('Unrecognized login destination.')

def visible(page, selector):
    items = page.locator(selector)
    for index in range(items.count()):
        item = items.nth(index)
        if item.is_visible() and item.is_enabled():
            return item
    return None

def submit(page):
    button = visible(page, 'button[type="submit"], input[type="submit"]')
    if button is None:
        button = page.get_by_role('button', name=re.compile(r'^(sign in|log in|login|next|continue)$', re.I)).first
        if button.count() != 1 or not button.is_visible():
            raise RuntimeError('No unambiguous sign-in control.')
    button.click(timeout=15000)

def identity(data):
    if isinstance(data, dict):
        value = data.get('id')
        if value:
            return value
        user = data.get('user')
        if isinstance(user, dict):
            return user.get('id')
    return None

save()
username = os.environ.get('SOCRATA_USERNAME', '')
password = os.environ.get('SOCRATA_PASSWORD', '')
report['secrets_present'] = bool(username and password)
candidates = set()
seen = set()
stage = 'browser_setup'
try:
    if not username or not password:
        report['status'] = 'missing_secrets'
        raise RuntimeError('Missing secrets.')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        guard = {'active': False}
        def protect(route):
            parts = urlsplit(route.request.url)
            if guard['active'] and (parts.scheme != 'https' or parts.hostname not in ALLOWED):
                route.abort()
            else:
                route.continue_()
        context.route('**/*', protect)
        login = context.new_page()
        stage = 'login_navigation'
        login.goto(LOGIN, wait_until='domcontentloaded', timeout=60000)
        login.wait_for_timeout(8000)
        trusted(login)
        if visible(login, 'input[autocomplete="one-time-code"], input[name*="otp" i], input[name*="totp" i]'):
            report['status'] = 'interactive_authentication_required'
            raise RuntimeError('Interactive authentication required.')
        user_field = visible(login, 'input[type="email"], input[name="username"], input[name="email"], input[id="username"], input[id="email"], input[autocomplete="username"]')
        password_field = visible(login, 'input[type="password"]')
        if user_field is None:
            report['status'] = 'login_form_not_identified'
            raise RuntimeError('Login form not identified.')
        guard['active'] = True
        stage = 'credential_entry'
        user_field.fill(username)
        if password_field is None:
            trusted(login)
            submit(login)
            login.wait_for_timeout(5000)
            trusted(login)
            password_field = visible(login, 'input[type="password"]')
        if password_field is None:
            report['status'] = 'password_form_or_interactive_step_required'
            raise RuntimeError('Password form unavailable.')
        trusted(login)
        password_field.fill(password)
        report['login_form_submitted'] = True
        stage = 'login_submission'
        submit(login)
        try:
            login.wait_for_timeout(10000)
        except Exception:
            pass
        stage = 'identity_verification'
        try:
            identity_url = 'https://tylertech.data.socrata.com/api/users/current.json'
            anonymous = requests.get(identity_url, allow_redirects=False, timeout=30)
            current = context.request.get(identity_url, max_redirects=0, timeout=30000)
            anonymous_id = identity(anonymous.json()) if anonymous.status_code == 200 else None
            current_id = identity(current.json()) if current.status == 200 else None
            report['authentication_verified'] = bool(current_id and current_id != anonymous_id and str(current_id).lower() not in ('anonymous', 'anon'))
            report['session_identity_http_status'] = current.status
        except Exception as exc:
            report['errors'].append({'stage': stage, 'error_type': type(exc).__name__})
        stage = 'same_session_dashboard'
        dashboard = context.new_page()
        def observe(response):
            parts = urlsplit(response.url)
            if parts.hostname not in ALLOWED or response.request.resource_type not in ('xhr', 'fetch'):
                return
            if any(word in parts.path.lower() for word in ('login', 'auth', 'users', 'session')):
                return
            endpoint = parts.scheme + '://' + parts.hostname + re.sub(r'/ticket[^/]*', '/[record-id-withheld]', parts.path)
            if endpoint in seen or len(seen) >= 100:
                return
            seen.add(endpoint)
            item = {'endpoint_without_query': endpoint, 'http_status': response.status}
            try:
                if 'json' in response.headers.get('content-type', '').lower():
                    body = response.json()
                    item['json_type'] = type(body).__name__
                    if isinstance(body, dict):
                        item['top_level_keys'] = list(body.keys())[:30]
                        item['list_lengths'] = {k: len(v) for k, v in body.items() if isinstance(v, list)}
                    elif isinstance(body, list):
                        item['list_length'] = len(body)
                    candidates.update(re.findall(r'\b[a-z0-9]{4}-[a-z0-9]{4}\b', json.dumps(body)))
            except Exception:
                item['inspection'] = 'unavailable'
            report['dashboard_requests'].append(item)
        dashboard.on('response', observe)
        response = dashboard.goto(DASHBOARD, wait_until='domcontentloaded', timeout=60000)
        report['dashboard_document_http_status'] = response.status if response else None
        dashboard.wait_for_timeout(30000)
        report['dashboard_destination_host'] = urlsplit(dashboard.url).hostname
        report['status'] = 'same_session_dashboard_inspected_requires_record_validation'
        browser.close()
except Exception as exc:
    report['errors'].append({'stage': stage, 'error_type': type(exc).__name__})
    if report['status'] == 'started':
        report['status'] = 'diagnostic_incomplete'
report['candidate_dataset_ids'] = sorted(candidates)[:100]
save()
