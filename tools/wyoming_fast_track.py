#!/usr/bin/env python3
"""Collect already enabled Wyoming sources; save pages and an honest status report."""
import concurrent.futures
import datetime
import html
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'fast-track-results'
OUT.mkdir(exist_ok=True)
WORK = Path(tempfile.mkdtemp(prefix='wyoming-fast-track-'))
LOCKS = {}
GUARD = threading.Lock()
ROWS = []

def save():
    rows = sorted(ROWS, key=lambda r: r['jurisdiction'])
    payload = {'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'limitations': ['Enabled sources only; no source verification or automatic activation.', 'Generated pages are downloadable results, not a live-site deployment.', 'Fresh temporary databases each run; historical state is not retained.', 'A generated page or captured document is not proof of complete coverage or successful repeat-run reporting.'], 'jurisdictions': rows}
    tmp = OUT / 'status.tmp'
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(OUT / 'status.json')
    lines = ['# Wyoming collection progress', '', 'Generated results only: not a live-site deployment or complete statewide reporting.', '', '| Jurisdiction | Result | Captured documents |', '|---|---|---:|']
    for r in rows:
        lines.append(f"| {r['jurisdiction']} | {r['status']} | {r.get('documents', 0)} |")
    (OUT / 'progress.md').write_text('\n'.join(lines) + '\n')
    links = ''.join('<li>' + html.escape(r['jurisdiction']) + ': ' + html.escape(r['status']) + (f" <a href=" + '"' + html.escape(r['page'], quote=True) + '">generated page</a>' if r.get('page') else '') + '</li>' for r in rows)
    (OUT / 'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Wyoming collection results</title><h1>Wyoming collection results</h1><p>Downloadable generated pages, not a live deployment. No claim of complete coverage or repeat-run verification.</p><ul>' + links + '</ul>')

def record(row):
    with GUARD:
        ROWS.append(row)
        save()

def run_instance(inst):
    slug = inst.name
    row = {'jurisdiction': slug, 'status': 'blocked'}
    acquired = []
    try:
        cfg = json.loads((inst / 'config/sources.json').read_text())
        enabled = [s for s in cfg.get('sources', []) if s.get('enabled')]
        row['enabled_sources'] = len(enabled)
        if not enabled:
            row['reason'] = 'No enabled sources. Review and activate official sources before collection.'
            return row
        if any(urllib.parse.urlsplit(s.get('url', '')).scheme not in ('http', 'https') for s in enabled):
            row['reason'] = 'Non-web source refused; synthetic fixtures must not enter statewide results.'
            return row
        ua = cfg.get('identity', {}).get('user_agent', '')
        if not ua or 'you@example.org' in ua:
            row['reason'] = 'Configure an honest identifying user agent and contact first.'
            return row
        hosts = sorted({urllib.parse.urlsplit(s['url']).hostname.lower() for s in enabled})
        with GUARD:
            locks = [LOCKS.setdefault(h, threading.Lock()) for h in hosts]
        for lock in locks:
            lock.acquire()
            acquired.append(lock)
        env = os.environ.copy()
        env['ENGINE_CONFIG_DIR'] = str(inst / 'config')
        env['ENGINE_DATA_DIR'] = str(WORK / slug)
        env['ENGINE_PUBLIC_DIR'] = str(OUT / slug)
        (OUT / slug).mkdir(parents=True, exist_ok=True)
        env.pop('OPENAI_API_KEY', None)
        env.pop('ANTHROPIC_API_KEY', None)
        commands = [[sys.executable, 'run.py', cmd] for cmd in ('init', 'crawl', 'work', 'digest')]
        commands.append([sys.executable, '-c', 'from engine.publish import build; build()'])
        row['completed_steps'] = []
        for command in commands:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
            if result.returncode:
                row['status'] = 'failed'
                row['reason'] = 'Command failed: ' + ' '.join(command)
                row['exit_code'] = result.returncode
                return row
            row['completed_steps'].append(command[-1])
        database = WORK / slug / 'engine.db'
        if not database.exists():
            raise RuntimeError('Expected engine.db missing; document count cannot be verified')
        with sqlite3.connect(database) as conn:
            row['documents'] = conn.execute('SELECT COUNT(*) FROM documents').fetchone()[0]
        row['page'] = slug + '/index.html'
        if not (OUT / row['page']).is_file():
            raise RuntimeError('Generated page missing')
        row['status'] = 'generated_with_documents' if row['documents'] else 'generated_but_no_documents'
        row['reporting_verified'] = False
    except subprocess.TimeoutExpired:
        row['status'] = 'timed_out'
        row['reason'] = 'A command exceeded its ten-minute limit; other communities continue.'
    except Exception as exc:
        row['status'] = 'failed'
        row['reason'] = str(exc)
    finally:
        for lock in reversed(acquired):
            lock.release()
    return row

def main():
    workers = max(1, min(8, int(os.environ.get('WYOMING_WORKERS', '4'))))
    instances = sorted(p for p in (ROOT / 'wyoming/instances').iterdir() if p.is_dir() and (p / 'config/sources.json').is_file())
    if not instances:
        raise RuntimeError('No jurisdiction configurations found')
    save()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_instance, inst) for inst in instances]
        for future in concurrent.futures.as_completed(futures):
            record(future.result())
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as f:
            f.write((OUT / 'progress.md').read_text())
    failures = sum(r['status'] in ('failed', 'timed_out') for r in ROWS)
    if failures or not any(r['status'] == 'generated_with_documents' for r in ROWS):
        sys.exit(1)

if __name__ == '__main__':
    main()
