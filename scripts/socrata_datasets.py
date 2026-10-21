import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import time
import requests

HOST = 'https://laramiecountywy-sheriff.data.socrata.com'
SOURCES = [
    {'id': '35sf-bu8v', 'category': 'Incidents', 'fields': ['incident_number', 'call_date_time', 'incident_type', 'agency'], 'timestamp': 'call_date_time'},
    {'id': 'cvz7-2j69', 'category': 'Cases', 'fields': ['case_id', 'reported_date_time', 'occurred_incident_type', 'agency'], 'timestamp': 'reported_date_time'}
]
output = Path('scanner-results/socrata/datasets.json')
output.parent.mkdir(parents=True, exist_ok=True)
report = {'checked_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'host': HOST,
    'status': 'started', 'datasets': [], 'correlation_enabled': False,
    'notice': 'Read-only source validation. Two pages of at most 25 rows per source are inspected in memory. No incident rows, account details, credentials, cookies, or raw errors are published. No full import has run.'}
session = requests.Session()
session.headers['User-Agent'] = 'LaramieCivicDataValidation/1.0'
username = os.environ.get('SOCRATA_USERNAME', '')
password = os.environ.get('SOCRATA_PASSWORD', '')
stopped = False

def save():
    output.write_text(json.dumps(report, indent=2) + '\n')

def request(method, path, item, **kwargs):
    global stopped
    time.sleep(2)
    response = session.request(method, HOST + path, allow_redirects=False, timeout=(20, 90), **kwargs)
    item.setdefault('http_checks', []).append({'path': path, 'status': response.status_code, 'authentication_used': False})
    if response.status_code == 429:
        stopped = True
        raise RuntimeError('Provider rate limit; no automatic retry.')
    if response.status_code in (401, 403) and username and password:
        time.sleep(2)
        response = session.request(method, HOST + path, auth=(username, password), allow_redirects=False, timeout=(20, 90), **kwargs)
        item['http_checks'].append({'path': path, 'status': response.status_code, 'authentication_used': True})
        if response.status_code == 429:
            stopped = True
            raise RuntimeError('Provider rate limit; no automatic retry.')
        if response.status_code == 200:
            item['authenticated_access_observed'] = True
    if response.status_code != 200:
        item['last_http_status'] = response.status_code
        raise RuntimeError('Source request not successful.')
    return response.json()

def records(payload):
    if isinstance(payload, list) and all(isinstance(row, dict) for row in payload):
        return payload
    if isinstance(payload, dict):
        for key in ('records', 'data', 'rows'):
            value = payload.get(key)
            if isinstance(value, list) and all(isinstance(row, dict) for row in value):
                return value
    raise RuntimeError('Unrecognized query response; no inferred row mapping.')

def fingerprint(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()

save()
for source in SOURCES:
    if stopped:
        break
    item = {'dataset_id': source['id'], 'category': source['category'], 'status': 'testing', 'authenticated_access_observed': False}
    report['datasets'].append(item)
    save()
    try:
        metadata = request('GET', '/api/views/' + source['id'] + '.json', item)
        columns = metadata.get('columns') if isinstance(metadata, dict) else None
        if not isinstance(columns, list):
            raise RuntimeError('Metadata columns unavailable.')
        item['schema'] = [{'field': c.get('fieldName'), 'type': c.get('dataTypeName')} for c in columns if isinstance(c, dict) and c.get('fieldName')]
        available = {c['field'] for c in item['schema']}
        item['missing_required_fields'] = [f for f in source['fields'] if f not in available]
        if item['missing_required_fields']:
            item['status'] = 'schema_mismatch_requires_review'
            continue
        endpoint = '/api/v3/views/' + source['id'] + '/query.json'
        query = 'SELECT ' + ','.join(source['fields']) + ' ORDER BY ' + source['timestamp'] + ' DESC, ' + source['fields'][0] + ' DESC'
        pages = []
        for number in (1, 2):
            payload = request('POST', endpoint, item, json={'query': query, 'page': {'pageNumber': number, 'pageSize': 25}, 'includeSynthetic': False})
            rows = records(payload)
            if len(rows) > 25:
                raise RuntimeError('Server exceeded bounded sample request.')
            pages.append(rows)
        item['sample_page_lengths'] = [len(rows) for rows in pages]
        item['pagination_observation'] = 'different_nonempty_pages' if pages[0] and pages[1] and fingerprint(pages[0]) != fingerprint(pages[1]) else 'empty_or_identical_pages_requires_review'
        sample = pages[0] + pages[1]
        allowed_agencies = {'Cheyenne Police Department - WY0110100', "Laramie County Sheriff's Department - WY0110000"}
        item['sample_has_expected_local_agency'] = any(row.get('agency') in allowed_agencies for row in sample)
        item['sample_field_nonnull_counts'] = {field: sum(row.get(field) is not None for row in sample) for field in source['fields']}
        count_rows = records(request('POST', endpoint, item, json={'query': 'SELECT count(*) AS row_count', 'includeSynthetic': False}))
        item['source_row_count'] = int(count_rows[0]['row_count']) if len(count_rows) == 1 and 'row_count' in count_rows[0] else None
        item['timestamp_semantics'] = 'call timestamp; source time zone still requires verification' if source['category'] == 'Incidents' else 'report timestamp; not assumed to equal occurrence or dispatch time'
        item['status'] = 'bounded_source_read_verified' if sample else 'queries_succeeded_no_sample_rows'
    except Exception as exc:
        item['status'] = 'validation_blocked_or_failed'
        item['error_type'] = type(exc).__name__
        item['notice'] = 'Raw response and exception withheld. Inspect HTTP statuses and schema; do not infer invalid credentials from a missing endpoint.'
    finally:
        save()
report['status'] = 'finished_requires_review'
save()
