import argparse
import datetime
import html
import json
import os
from pathlib import Path
import re
import time
import urllib.request

def safe_url(value):
    from urllib.parse import urlsplit
    try:
        u = urlsplit(value or '')
        return value if u.scheme == 'https' and u.hostname and not u.username and not u.password else None
    except ValueError:
        return None

def build(root, out, revision):
    registry = json.loads((root / 'wyoming/registry.json').read_text())
    entries = registry['jurisdictions']
    if len(entries) != registry['counts']['total_instances'] or not entries:
        raise ValueError('Registry count mismatch or empty registry')
    slugs = [e['slug'] for e in entries]
    if len(set(slugs)) != len(slugs) or any(not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', s) for s in slugs):
        raise ValueError('Invalid or duplicate jurisdiction slug')
    target = out / 'wyoming'
    target.mkdir(parents=True, exist_ok=True)
    rows = []
    esc = lambda value: html.escape(str(value), quote=True)
    def page(title, body):
        return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>'+esc(title)+'</title><style>body{font:18px/1.6 system-ui;max-width:1000px;margin:auto;padding:24px}table{border-collapse:collapse;width:100%}td,th{text-align:left;border-bottom:1px solid #ccc;padding:8px}a{color:#1452a2}</style><h1>'+esc(title)+'</h1>'+body+'<footer><p>Independent civic-record project. Not an official government website. Build '+esc(revision)+'</p></footer></html>'
    for e in entries:
        config = json.loads((root / 'wyoming/instances' / e['slug'] / 'config/sources.json').read_text())
        enabled = [s for s in config.get('sources', []) if s.get('enabled')]
        row = {'slug': e['slug'], 'name': e['name'], 'type': e['type'], 'enabled_sources': len(enabled), 'reporting_verified': False, 'status': 'collection_not_verified' if enabled else 'sources_not_activated'}
        rows.append(row)
        links = ''
        for source in config.get('sources', []):
            url = safe_url(source.get('url'))
            if url:
                links += '<li><a rel="noopener noreferrer" href="'+esc(url)+'">'+esc(source.get('name', url))+'</a> — '+('enabled in configuration; collection not verified' if source.get('enabled') else 'candidate; not activated or confirmed by this page')+'</li>'
        body = '<p><a href="../index.html">Wyoming directory</a> | <a href="../../index.html">Main archive</a></p><p>Jurisdiction type: '+esc(e['type'])+'</p><p>Status: '+esc(row['status'].replace('_',' '))+'. Enabled sources: '+str(len(enabled))+'.</p><p>This page is a deployed directory entry, not evidence that local records are being collected. No claim of complete coverage is made.</p><h2>Configured source links</h2><ul>'+links+'</ul>'
        if e['slug'] == 'cheyenne':
            body += '<p><a href="../../index.html">Use the existing Cheyenne archive</a>; this directory does not replace it.</p>'
        folder = target / e['slug']
        folder.mkdir(exist_ok=True)
        (folder / 'index.html').write_text(page(e['name']+' — Wyoming records status', body))
    manifest = {'revision': revision, 'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'configured_jurisdictions': len(rows), 'verified_reporting_jurisdictions': None, 'verification_note': 'Collection and repeat-run reporting have not been evaluated by this directory build.', 'jurisdictions': rows}
    (target / 'status.json').write_text(json.dumps(manifest, indent=2))
    body = '<p><a href="../index.html">Existing Cheyenne archive</a> | <a href="status.json">Machine-readable status</a></p><p>'+str(len(rows))+' configured jurisdiction pages. Configuration and deployment are not proof of active reporting.</p><table><tr><th>Place</th><th>Type</th><th>Status</th></tr>'
    for r in rows:
        body += '<tr><td><a href="'+r['slug']+'/index.html">'+esc(r['name'])+'</a></td><td>'+esc(r['type'])+'</td><td>'+esc(r['status'].replace('_',' '))+'</td></tr>'
    (target / 'index.html').write_text(page('Wyoming civic-record directory', body+'</table>'))
    home = out / 'index.html'
    if home.is_file():
        text = home.read_text()
        if 'data-wyoming-directory' not in text:
            text, count = re.subn(r'(<body[^>]*>)', r'\1<nav data-wyoming-directory><a href="wyoming/index.html">Wyoming statewide directory</a></nav>', text, count=1, flags=re.I)
            if not count:
                raise ValueError('Main homepage has no body element; refusing navigation injection')
            home.write_text(text)
    if not all((target / s / 'index.html').is_file() for s in slugs):
        raise ValueError('Missing generated jurisdiction page')
    return manifest

def verify(url, revision):
    base = url.rstrip('/') + '/wyoming/'
    for attempt in range(6):
        try:
            req = urllib.request.Request(base+'status.json?revision='+revision, headers={'User-Agent':'WyomingDirectoryDeployCheck/1.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                report = json.load(response)
            if report.get('revision') != revision or report.get('configured_jurisdictions') != len(report.get('jurisdictions', [])) or not report.get('jurisdictions'):
                raise ValueError('Published statewide manifest is stale or invalid')
            with urllib.request.urlopen(base+'index.html?revision='+revision, timeout=30) as response:
                index = response.read().decode()
            for row in report['jurisdictions']:
                if row['slug']+'/index.html' not in index:
                    raise ValueError('Jurisdiction missing from live index')
            print('Verified live statewide index and manifest for '+str(report['configured_jurisdictions'])+' configured jurisdictions. Collection remains separately unverified.')
            return
        except Exception:
            if attempt == 5:
                raise
            time.sleep(15)

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='_site')
    ap.add_argument('--verify-url')
    ap.add_argument('--revision', default=os.environ.get('GITHUB_SHA', 'local'))
    args = ap.parse_args()
    if args.verify_url:
        verify(args.verify_url, args.revision)
    else:
        result = build(Path(__file__).resolve().parents[1], Path(args.out), args.revision)
        print(str(result['configured_jurisdictions'])+' jurisdiction pages generated; no source configuration changed.')
