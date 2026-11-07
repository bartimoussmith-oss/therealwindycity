#!/usr/bin/env python3
"""Local, authenticated civic-engine job runner. Python standard library only."""
import hmac
import json
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = Path(os.environ.get('COMMAND_CENTER_STATE', str(Path.home() / '.local/state/therealwindycity-command-center')))
PORT = int(os.environ.get('COMMAND_CENTER_PORT', '8765'))
TOKEN = os.environ.get('COMMAND_CENTER_TOKEN') or secrets.token_urlsafe(32)
STOP = threading.Event()
COMMANDS = {'init': ['init'], 'crawl': ['crawl'], 'work': ['work'], 'digest': ['digest'], 'cycle': ['init', 'crawl', 'work', 'digest']}

def connect():
    c = sqlite3.connect(STATE / 'jobs.sqlite3', timeout=30)
    c.row_factory = sqlite3.Row
    return c

def prepare():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE, 0o700)
    with connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, slug TEXT, action TEXT, status TEXT, created REAL, finished REAL, code INTEGER)')
        c.execute("UPDATE jobs SET status='interrupted', finished=? WHERE status='running'", (time.time(),))

def validate(slug, action):
    if not isinstance(slug, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
        raise ValueError('Invalid instance slug')
    base = (ROOT / 'wyoming/instances').resolve()
    inst = (base / slug).resolve()
    if inst.parent != base or not (inst / 'config').is_dir():
        raise ValueError('Unknown configured instance')
    if action not in COMMANDS:
        raise ValueError('Unknown action')
    return inst

def worker():
    while not STOP.is_set():
        with connect() as c:
            row = c.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row:
                c.execute("UPDATE jobs SET status='running' WHERE id=?", (row['id'],))
        if not row:
            STOP.wait(1)
            continue
        code = 1
        with (STATE / (row['id'] + '.log')).open('ab', buffering=0) as log:
            try:
                inst = validate(row['slug'], row['action'])
                env = os.environ.copy()
                env.update(ENGINE_CONFIG_DIR=str(inst / 'config'), ENGINE_DATA_DIR=str(ROOT / 'data/wyoming' / row['slug']), ENGINE_PUBLIC_DIR=str(ROOT / 'public/wyoming' / row['slug']), PYTHONUNBUFFERED='1')
                for command in COMMANDS[row['action']]:
                    log.write(('\n== ' + command + ' ==\n').encode())
                    code = subprocess.call([sys.executable, '-u', str(ROOT / 'run.py'), command], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
                    if code:
                        break
            except Exception as exc:
                log.write((repr(exc) + '\n').encode())
            with connect() as c:
                c.execute('UPDATE jobs SET status=?, finished=?, code=? WHERE id=?', ('succeeded' if code == 0 else 'failed', time.time(), code, row['id']))

PAGE = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Civic Command Center</title><style>body{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:1rem}input,select,button{padding:.7rem;margin:.2rem}pre{white-space:pre-wrap;overflow-wrap:anywhere}li{margin:1rem 0}</style><h1>Civic Command Center</h1><p>Local job runner. No automatic publication, Google login, or claim of statewide source health.</p><input id="token" type="password" placeholder="Server access token" autocomplete="off"><button id="refresh">Refresh</button><hr><select id="slug"></select><select id="action"><option>init</option><option>crawl</option><option>work</option><option>digest</option><option>cycle</option></select><button id="run">Queue job</button><p id="message" role="status"></p><ul id="jobs"></ul><h2>Job log (last 64 KB)</h2><pre id="log"></pre><script>
const el=id=>document.getElementById(id);
async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'Authorization':'Bearer '+el('token').value,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const data=await r.json();if(!r.ok)throw Error(data.error||r.status);return data}
async function refresh(){try{const d=await api('/api/status');const old=el('slug').value;el('slug').replaceChildren(...d.instances.map(x=>new Option(x,x)));if(d.instances.includes(old))el('slug').value=old;el('jobs').replaceChildren(...d.jobs.map(j=>{const li=document.createElement('li'),b=document.createElement('button');li.append(document.createTextNode(j.slug+' / '+j.action+' / '+j.status+' '));b.textContent='View log';b.onclick=async()=>{try{el('log').textContent=(await api('/api/log/'+j.id)).text}catch(e){el('message').textContent=e.message}};li.append(b);return li}));el('message').textContent='Updated '+new Date().toLocaleTimeString()}catch(e){el('message').textContent=e.message}}
el('refresh').onclick=refresh;el('run').onclick=async()=>{if(!confirm('Queue '+el('action').value+' for '+el('slug').value+'? A crawl or cycle contacts enabled sources.'))return;try{await api('/api/jobs',{slug:el('slug').value,action:el('action').value});await refresh()}catch(e){el('message').textContent=e.message}};setInterval(()=>{if(el('token').value)refresh()},5000);
</script></html>'''

class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data, html=False):
        raw = data.encode() if html else json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8' if html else 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        if self.headers.get('Host') not in {f'127.0.0.1:{PORT}', f'localhost:{PORT}'}:
            self.reply(403, {'error': 'Invalid Host'})
            return False
        origin = self.headers.get('Origin')
        if origin and origin not in {f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}'}:
            self.reply(403, {'error': 'Invalid Origin'})
            return False
        if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + TOKEN):
            self.reply(401, {'error': 'Enter the access token printed by the server'})
            return False
        return True

    def do_GET(self):
        if self.path == '/':
            return self.reply(200, PAGE, True)
        if not self.authorized():
            return
        if self.path == '/api/status':
            with connect() as c:
                jobs = [dict(r) for r in c.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 100')]
            instances = sorted(p.name for p in (ROOT / 'wyoming/instances').iterdir() if (p / 'config').is_dir())
            return self.reply(200, {'instances': instances, 'jobs': jobs})
        match = re.fullmatch(r'/api/log/([a-f0-9]{32})', self.path)
        if match:
            p = STATE / (match[1] + '.log')
            if not p.exists():
                return self.reply(200, {'text': 'No log yet'})
            with p.open('rb') as f:
                f.seek(max(0, p.stat().st_size - 65536))
                text = f.read(65536).decode('utf-8', errors='replace')
            return self.reply(200, {'text': text})
        self.reply(404, {'error': 'Not found'})

    def do_POST(self):
        if not self.authorized():
            return
        if self.path != '/api/jobs':
            return self.reply(404, {'error': 'Not found'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4096:
                raise ValueError('Expected a JSON body of at most 4096 bytes')
            body = json.loads(self.rfile.read(size))
            slug, action = body['slug'], body['action']
            validate(slug, action)
            ident = uuid.uuid4().hex
            with connect() as c:
                if c.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0] >= 100:
                    return self.reply(429, {'error': 'Queue full'})
                c.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)', (ident, slug, action, 'queued', time.time(), None, None))
            self.reply(202, {'id': ident, 'status': 'queued'})
        except (ValueError, KeyError, TypeError) as exc:
            self.reply(400, {'error': str(exc)})

def main():
    os.umask(0o077)
    prepare()
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    threading.Thread(target=worker, daemon=True).start()
    print(f'Command Center: http://127.0.0.1:{PORT}\nAccess token: {TOKEN}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        STOP.set()
        server.server_close()

if __name__ == '__main__':
    main()
