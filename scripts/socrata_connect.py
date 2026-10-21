import datetime as dt
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit, parse_qsl, urlencode, quote
from playwright.sync_api import sync_playwright

PORTAL = 'https://laramiecounty-letmsp.connect.socrata.com'
PORTAL_HOST = urlsplit(PORTAL).hostname
AUTH_HOSTS = {PORTAL_HOST, 'socrata.auth0.com', 'tylertech.data.socrata.com'}
ASSET_HOSTS = {'cdn.auth0.com', 'global.oktacdn.com', 'code.jquery.com', 'cdnjs.cloudflare.com', 'cdn.jsdelivr.net', 'cdn.forge.tylertech.com', 'cdn3.devexpress.com', 'api.mapbox.com', 'fonts.googleapis.com', 'fonts.gstatic.com'}
username = os.environ.get('SOCRATA_USERNAME', '')
password = os.environ.get('SOCRATA_PASSWORD', '')
output = Path('scanner-results/socrata/connection.json')
output.parent.mkdir(parents=True, exist_ok=True)
report = {'checked_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'status': 'started',
    'secrets_present': bool(username and password), 'login_form_submitted': False,
    'authentication_verified': False, 'record_access_observed': False, 'correlation_enabled': False,
    'login_hosts': [], 'blocked_hosts': [], 'application_responses': [], 'errors': [],
    'notice': 'Read-only application diagnostic. No account identifiers, credentials, cookies, screenshots, HTML dumps, or incident rows are published. Form submission and nonempty public responses do not alone prove authentication.'}
phase = {'name': 'initializing', 'credentials_entered': False}
seen = set()

def save():
    output.write_text(json.dumps(report, indent=2) + '\n')

def visible(page, selector):
    if page.is_closed():
        return None
    options = page.locator(selector)
    for index in range(options.count()):
        field = options.nth(index)
        if field.is_visible() and field.is_enabled():
            return field
    return None

def trusted(page):
    parts = urlsplit(page.url)
    if parts.hostname not in report['login_hosts']:
        report['login_hosts'].append(parts.hostname)
    if parts.scheme != 'https' or parts.hostname not in AUTH_HOSTS:
        raise RuntimeError('Unrecognized credential destination.')

def submit(page):
    button = visible(page, 'button[type="submit"], input[type="submit"]')
    if button is None:
        candidates = page.get_by_role('button', name=re.compile(r'^(sign in|log in|login|next|continue)$', re.I))
        if candidates.count() != 1 or not candidates.first.is_visible():
            raise RuntimeError('No unambiguous submit control.')
        button = candidates.first
    button.click(timeout=20000)

def interactive(page):
    return visible(page, 'input[autocomplete="one-time-code"], input[name*="otp" i], input[name*="totp" i]') is not None

def observe(response):
    parts = urlsplit(response.url)
    if parts.hostname != PORTAL_HOST or not parts.path.startswith('/api/'):
        return
    if any(s in parts.path.lower() for s in ('auth', 'login', 'session', 'user')):
        return
    key = (phase['name'], parts.path, response.status)
    if key in seen or len(seen) >= 80:
        return
    seen.add(key)
    item = {'phase': phase['name'], 'path': parts.path, 'http_status': response.status,
        'query_parameter_names': sorted({k for k, v in parse_qsl(parts.query)})}
    try:
        if 'json' in response.headers.get('content-type', '').lower():
            body = response.json()
            if isinstance(body, dict):
                item['top_level_keys'] = list(body)[:30]
                data = body.get('api_data')
                if isinstance(data, dict):
                    item['api_data_keys'] = list(data)[:30]
                    rows = data.get('records')
                    if isinstance(rows, list):
                        item['record_count_returned'] = len(rows)
                        item['row_fields'] = sorted({k for row in rows[:3] if isinstance(row, dict) for k in row})
                        if '/tickets/details' in parts.path and rows:
                            report['record_access_observed'] = True
                    if isinstance(data.get('incomplete'), bool):
                        item['incomplete'] = data['incomplete']
                    if isinstance(data.get('count'), (int, float)):
                        item['reported_count'] = data['count']
                elif isinstance(data, list):
                    item['aggregate_items'] = len(data)
                queries = body.get('soql_queries')
                if isinstance(queries, list):
                    item['underlying_dataset_ids'] = sorted({match for query in queries if isinstance(query, str) for match in re.findall(r'/views/([a-z0-9]{4}-[a-z0-9]{4})/', query)})
    except Exception:
        item['body_inspection'] = 'unavailable'
    report['application_responses'].append(item)

save()
try:
    if not username or not password:
        raise RuntimeError('Missing configured secrets.')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(service_workers='block')
        def protect(route):
            request = route.request
            parts = urlsplit(request.url)
            host = parts.hostname
            allowed = parts.scheme == 'https' and host in AUTH_HOSTS
            if parts.scheme == 'https' and host in ASSET_HOSTS and request.method == 'GET':
                allowed = True
            if phase['credentials_entered'] and host not in AUTH_HOSTS:
                haystack = request.url + (request.post_data or '')
                if any(secret in haystack or quote(secret, safe='') in haystack for secret in (username, password) if secret):
                    allowed = False
            if allowed:
                route.continue_()
            else:
                if host and host not in report['blocked_hosts']:
                    report['blocked_hosts'].append(host)
                route.abort()
        context.route('**/*', protect)
        context.on('response', observe)
        phase['name'] = 'login_navigation'
        login = context.new_page()
        login.goto(PORTAL + '/auth_login.html?auto_close=true', wait_until='domcontentloaded', timeout=60000)
        login.wait_for_timeout(8000)
        trusted(login)
        if interactive(login):
            report['status'] = 'interactive_authentication_required'
            raise RuntimeError('Interactive authentication required.')
        user_field = visible(login, 'input[type="email"], input[name="username"], input[name="email"], input[autocomplete="username"]')
        if user_field is None:
            report['status'] = 'login_form_not_identified'
            raise RuntimeError('Login form unavailable.')
        phase['credentials_entered'] = True
        user_field.fill(username)
        password_field = visible(login, 'input[type="password"]')
        if password_field is None:
            submit(login)
            login.wait_for_timeout(5000)
            trusted(login)
            if interactive(login):
                report['status'] = 'interactive_authentication_required'
                raise RuntimeError('Interactive authentication required.')
            password_field = visible(login, 'input[type="password"]')
        if password_field is None:
            raise RuntimeError('Password form unavailable.')
        trusted(login)
        password_field.fill(password)
        phase['name'] = 'login_submission'
        submit(login)
        report['login_form_submitted'] = True
        try:
            login.wait_for_timeout(15000)
        except Exception:
            pass
        if not login.is_closed() and interactive(login):
            report['status'] = 'interactive_authentication_required'
            raise RuntimeError('Interactive authentication required.')
        phase['name'] = 'dashboard_after_login'
        params = {
            'categories': '1:3130=2-226,228-267,273-285,299-360&3145=2-187,189-221,227-239,248-304|2:2056=1-27,34-96,103,107-117&2059=1-24,30-64,66-89,95,99-109',
            'start_date': '2020-01-01', 'end_date': str(dt.datetime.now(dt.timezone.utc).date()),
            'lat': '41.11534638911769', 'lng': '-104.83519077301025', 'zoom': '9',
            'shapeGroupId': 'jgtq-znyx', 'currentTab': 'list', 'listViewTab': 'Data',
            'showSideBar': 'true', 'autoUpdate': 'false', 'include_restricted_places': 'false'
        }
        page = context.new_page()
        page.goto(PORTAL + '/#!/dashboard?' + urlencode(params), wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(45000)
        report['dashboard_date_filter'] = {'start': params['start_date'], 'end': params['end_date']}
        report['logout_control_visible'] = page.get_by_role('link', name=re.compile(r'^(sign out|log out|logout)$', re.I)).count() > 0 or page.get_by_role('button', name=re.compile(r'^(sign out|log out|logout)$', re.I)).count() > 0
        report['authentication_verified'] = False
        report['authentication_notice'] = 'Login submitted through normal Auth0 flow; session identity still requires a verified application-specific check. A logout element or successful record response alone is not conclusive.'
        report['status'] = 'application_inspected_records_observed' if report['record_access_observed'] else 'application_inspected_no_detail_rows_observed'
        browser.close()
except Exception as exc:
    report['errors'].append({'phase': phase['name'], 'error_type': type(exc).__name__})
    if report['status'] == 'started':
        report['status'] = 'diagnostic_incomplete'
save()
