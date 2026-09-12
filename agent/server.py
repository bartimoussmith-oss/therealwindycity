"""Built-in web console: installable PWA + JSON API + live event stream.

Runs on stdlib http.server only — no wheels, no build step, no node. That is
what lets the same runtime serve a phone, a Chromebook and a Windows box.

    python3 -m agent serve                 # http://<lan-ip>:8765
    python3 -m agent serve --port 9000     # any port
    python3 -m agent serve --token SECRET  # require a token (query param or header)

Security model: binds 0.0.0.0 so your other devices can reach it; you decide the
network it sits on. With no token it is open to that network (fine on a home LAN,
not fine on public Wi-Fi — use `agent pair` when you are on one).
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import queue
import socket
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config as cfg
from . import orchestrator, providers
from .loop import AgentLoop, Events
from .store import Store
from .tools import Policy, ToolRunner

VERSION = "1.0.0"
STATIC_DIR = Path(__file__).resolve().parent


class BridgeGate:
    """Blocks a run until a human (on the phone) supplies text.

    Used by the paste provider — the reply is typed or pasted into the PWA —
    and by confirm-class tool calls.
    """

    def __init__(self, app: "App", run_id: str, kind: str, prompt: str, meta: dict | None = None):
        self.app = app
        self.run_id = run_id
        self.kind = kind          # "bridge" | "confirm"
        self.prompt = prompt
        self.meta = meta or {}
        self.event = threading.Event()
        self.value: str | None = None

    def wait(self, timeout: float = 3600.0) -> str | None:
        self.event.wait(timeout)
        return self.value

    def submit(self, value: str):
        self.value = value
        self.event.set()


class RunState:
    def __init__(self, run_id: str, session_id: str, task: str):
        self.id = run_id
        self.session_id = session_id
        self.task = task
        self.q: queue.Queue = queue.Queue(maxsize=4000)
        self.cancel = threading.Event()
        self.status = "running"
        self.result: dict | None = None
        self.started = time.time()
        self.finished: float | None = None
        self.thread: threading.Thread | None = None
        self.gate: BridgeGate | None = None

    def emit(self, evt: dict):
        try:
            self.q.put_nowait(evt)
        except queue.Full:
            pass
        if evt.get("kind") == "finished":
            self.status = evt.get("status", "done")
            self.result = evt
            self.finished = time.time()


class App:
    def __init__(self, conf: cfg.Config, store: Store):
        self.conf = conf
        self.store = store
        self.runs: dict[str, RunState] = {}
        self.lock = threading.Lock()
        self.started = time.time()

    # -- auth ---------------------------------------------------------------
    def token(self) -> str | None:
        return self.conf.server_cfg.get("token") or self.conf.secret("server_token")

    def authorised(self, handler) -> bool:
        tok = self.token()
        if not tok:
            return True
        given = handler.query().get("token", [None])[0] or ""
        if not given:
            auth = handler.headers.get("Authorization", "")
            if auth.lower().startswith("bearer "):
                given = auth[7:].strip()
        if not given:
            cookie = handler.headers.get("Cookie", "")
            for part in cookie.split(";"):
                if part.strip().startswith("wy_token="):
                    given = part.strip().split("=", 1)[1]
        if given and _consteq(given, tok):
            return True
        # a paired device token also works
        if given:
            h = hashlib.sha256(given.encode()).hexdigest()
            dev = self.store.find_device_by_token(h)
            if dev:
                self.store.execute("UPDATE devices SET last_seen=? WHERE id=?", (time.time(), dev["id"]))
                return True
        # loopback is always trusted so the host machine can never lock itself out
        try:
            return handler.client_address[0] in ("127.0.0.1", "::1")
        except Exception:
            return False

    # -- run plumbing -------------------------------------------------------
    def start_run(self, task: str, session_id: str | None = None, mode: str = "single",
                  provider_id: str | None = None, model: str | None = None,
                  persona: str = "operator", dry_run: bool | None = None) -> RunState:
        overrides: dict = {}
        if dry_run is not None:
            overrides["dry_run"] = bool(dry_run)
        if provider_id:
            overrides["provider"] = provider_id
        # layer the per-run overrides on top of the running server's config, so the
        # workspace/provider/mode chosen at startup survive (a fresh Config would
        # fall back to `auto` and could pick a different brain mid-session)
        conf = cfg.Config(overrides, base=self.conf.data) if overrides else self.conf
        provider = providers.build(conf, provider=provider_id, model=model)
        if session_id is None:
            session_id = self.store.create_session(task[:80], mode=mode, provider=provider.id,
                                                   model=provider.model,
                                                   workspace=str(conf.workspace))
        rid = self.store.start_run(session_id, task, mode, provider.id, provider.model)
        self.store.add_message(session_id, rid, "user", task)
        state = RunState(rid, session_id, task)
        with self.lock:
            self.runs[rid] = state
        state.thread = threading.Thread(
            target=self._execute, args=(state, conf, provider, task, session_id, mode, persona),
            daemon=True, name=f"run-{rid}")
        state.thread.start()
        return state

    def _execute(self, state: RunState, conf, provider, task, session_id, mode, persona):
        events = Events()
        events.subscribe(state.emit)

        def confirm_handler(tool: str, args: dict, reason: str) -> bool:
            gate = BridgeGate(self, state.id, "confirm",
                              f"{tool} wants to run: {json.dumps(args, default=str)[:800]}",
                              {"tool": tool, "args": args, "reason": reason})
            state.gate = gate
            state.emit({"kind": "confirm_request", "run_id": state.id, "tool": tool,
                        "args": args, "reason": reason})
            answer = gate.wait(timeout=1800)
            state.gate = None
            state.emit({"kind": "confirm_answer", "run_id": state.id, "answer": answer})
            return str(answer or "").strip().lower() in ("y", "yes", "approve", "true", "1")

        policy = Policy(conf, store=self.store, confirm_handler=confirm_handler, agent_name="main")
        try:
            if mode in ("plan", "swarm"):
                orch = orchestrator.Orchestrator(conf, provider, store=self.store, events=events,
                                                 confirm_handler=confirm_handler)
                out = orch.run(task, session_id=session_id, mode=mode)
            else:
                if provider.id == "paste":
                    # wire the PWA in as the human half of the bridge
                    def reader(prompt_text: str, _state=state) -> str:
                        gate = BridgeGate(self, _state.id, "bridge", prompt_text)
                        _state.gate = gate
                        _state.emit({"kind": "bridge_prompt", "run_id": _state.id,
                                     "prompt": prompt_text})
                        reply = gate.wait(timeout=7200) or ""
                        _state.gate = None
                        return reply
                    provider.reader = reader
                runner = ToolRunner(policy, run_id=state.id)
                loop = AgentLoop(provider, runner, store=self.store, policy=policy, mode="single",
                                 max_steps=int(conf.get("max_steps") or 24), events=events)
                out = loop.run_task(task, session_id=session_id, persona=persona, run_id=state.id)
            state.result = out
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            state.emit({"kind": "error", "run_id": state.id, "error": detail,
                        "trace": traceback.format_exc()[-4000:]})
            self.store.finish_run(state.id, "error", "", detail)
            state.status = "error"
            state.finished = time.time()
        finally:
            self.store.close()

    def stop(self, run_id: str) -> bool:
        with self.lock:
            state = self.runs.get(run_id)
        if not state:
            return False
        state.cancel.set()
        if state.gate:
            state.gate.submit("")  # unblock a waiting human gate
        return True


def _consteq(a: str, b: str) -> bool:
    import hmac
    return hmac.compare_digest(a.encode(), b.encode())


# --------------------------------------------------------------------------- handler

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    app: App = None  # type: ignore
    server_version = f"windycity-agent/{VERSION}"

    # -- helpers ------------------------------------------------------------
    def log_message(self, fmt, *args):
        if self.path.startswith("/api/stream"):
            return
        print(f"  {self.address_string()} {fmt % args}")

    def query(self) -> dict:
        return urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)

    def json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def send_json(self, obj, status: int = 200):
        body = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, text: str, content_type="text/plain; charset=utf-8", status: int = 200,
                  extra: dict | None = None):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def deny(self):
        self.send_json({"error": "unauthorised — open the URL with ?token=… , "
                                 "or run `python3 -m agent pair` for a device token"}, 401)

    # -- routing ------------------------------------------------------------
    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        try:
            if path in ("/", "/index.html"):
                return self.serve_index()
            if path == "/manifest.webmanifest":
                return self.serve_manifest()
            if path == "/sw.js":
                return self.serve_sw()
            if path == "/favicon.ico":
                return self.send_text("", "image/x-icon", 204)
            if path == "/healthz":
                return self.send_text("ok")
            if not self.app.authorised(self):
                return self.deny()
            if path == "/api/health":
                return self.api_health()
            if path == "/api/sessions":
                return self.send_json(self.app.store.list_sessions(
                    limit=int(self.query().get("limit", ["50"])[0])))
            if path.startswith("/api/sessions/"):
                return self.api_session(path.rsplit("/", 1)[-1])
            if path.startswith("/api/stream/"):
                return self.api_stream(path.rsplit("/", 1)[-1])
            if path.startswith("/api/run/"):
                return self.api_run(path.rsplit("/", 1)[-1])
            if path == "/api/providers":
                return self.send_json([
                    {"id": pid, "label": providers.PROVIDERS[pid].label, "ready": ok,
                     "why": reason, "default_model": providers.PROVIDERS[pid].default_model,
                     "needs_key": providers.PROVIDERS[pid].needs_key}
                    for pid, ok, reason in providers.available(self.app.conf)])
            if path == "/api/tools":
                return self.send_json(self.app.tools_schema())
            if path == "/api/audit":
                run_id = self.query().get("run", [None])[0]
                return self.send_json(self.app.store.list_audit(run_id, limit=200))
            if path == "/api/devices":
                return self.send_json(self.app.store.list_devices())
            if path == "/api/memory":
                return self.send_json(self.app.store.memo_all())
            if path == "/api/settings":
                return self.send_json(self.app.public_config())
            if path == "/api/runs":
                return self.send_json(self.app.store.list_runs(limit=50))
            if path == "/api/export":
                return self.api_export()
            return self.send_json({"error": "not found", "path": path}, 404)
        except BrokenPipeError:
            pass
        except Exception as exc:
            self.safe_error(exc)

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        try:
            if not self.app.authorised(self):
                return self.deny()
            body = self.json_body()
            if path == "/api/chat":
                return self.api_chat(body)
            if path == "/api/stop":
                ok = self.app.stop(str(body.get("run_id", "")))
                return self.send_json({"stopped": ok})
            if path == "/api/bridge":
                return self.api_bridge(body)
            if path == "/api/confirm":
                return self.api_confirm(body)
            if path == "/api/sessions":
                sid = self.app.store.create_session(str(body.get("title") or "New session"))
                return self.send_json({"id": sid})
            if path == "/api/memory":
                self.app.store.memo_set(str(body.get("key", "")), str(body.get("value", "")),
                                        scope=str(body.get("scope") or "global"),
                                        tags=str(body.get("tags") or ""))
                return self.send_json({"ok": True})
            if path == "/api/settings":
                return self.api_set_settings(body)
            if path == "/api/pair":
                return self.api_pair(body)
            return self.send_json({"error": "not found", "path": path}, 404)
        except BrokenPipeError:
            pass
        except Exception as exc:
            self.safe_error(exc)

    def do_DELETE(self):
        path = urllib.parse.urlsplit(self.path).path
        if not self.app.authorised(self):
            return self.deny()
        if path.startswith("/api/sessions/"):
            self.app.store.delete_session(path.rsplit("/", 1)[-1])
            return self.send_json({"ok": True})
        return self.send_json({"error": "not found"}, 404)

    def safe_error(self, exc: Exception):
        try:
            self.send_json({"error": f"{type(exc).__name__}: {exc}",
                            "trace": traceback.format_exc()[-2000:]}, 500)
        except Exception:
            pass

    # -- endpoints ----------------------------------------------------------
    def serve_index(self):
        html = (STATIC_DIR / "webapp.html").read_text(encoding="utf-8")
        self.send_text(html, "text/html; charset=utf-8",
                       extra={"Service-Worker-Allowed": "/"})

    def serve_manifest(self):
        self.send_text(json.dumps({
            "name": "windycity-agent", "short_name": "agent",
            "start_url": "/", "display": "standalone", "background_color": "#0b0f14",
            "theme_color": "#0b0f14", "orientation": "any",
            "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml",
                       "purpose": "any"},
                      {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
                      {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}],
        }), "application/manifest+json")

    def serve_sw(self):
        self.send_text(SERVICE_WORKER, "text/javascript; charset=utf-8")

    def api_health(self):
        conf = self.app.conf
        provider, model = providers.resolve_auto(conf)
        self.send_json({
            "ok": True, "version": VERSION, "uptime_s": int(time.time() - self.app.started),
            "platform": _platform(), "workspace": str(conf.workspace),
            "state_dir": str(cfg.home_dir()),
            "provider": provider, "model": model,
            "dry_run": conf.dry_run, "mode": conf.get("mode"),
            "auth": bool(self.app.token()),
            "hostname": socket.gethostname(),
            "lan_ips": _lan_ips(),
            "runs": len(self.app.runs),
        })

    def api_session(self, sid: str):
        sess = self.app.store.get_session(sid)
        if not sess:
            return self.send_json({"error": "no such session"}, 404)
        self.send_json({"session": sess, "messages": self.app.store.get_messages(sid),
                        "runs": self.app.store.list_runs(sid, limit=20),
                        "tasks": self.app.store.list_tasks(sid)})

    def api_run(self, rid: str):
        state = self.app.runs.get(rid)
        if state:
            return self.send_json({"status": state.status, "result": state.result,
                                   "running": state.status == "running"})
        run = self.app.store.get_run(rid)
        if not run:
            return self.send_json({"error": "no such run"}, 404)
        self.send_json({"status": run["status"], "result": run, "running": False})

    def api_stream(self, rid: str):
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()

        def write(event: dict):
            payload = json.dumps(event, default=str)
            self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
            self.wfile.flush()

        state = self.app.runs.get(rid)
        if state is None:
            run = self.app.store.get_run(rid)
            write({"kind": "finished", "status": (run or {}).get("status", "unknown"),
                   "summary": (run or {}).get("summary", ""), "run_id": rid, "replay": True})
            return
        # replay what happened before this client connected
        write({"kind": "hello", "run_id": rid, "task": state.task,
               "session_id": state.session_id, "status": state.status})
        idle = 0.0
        while True:
            try:
                evt = state.q.get(timeout=1.0)
                idle = 0.0
                write(evt)
                if evt.get("kind") == "finished":
                    break
            except queue.Empty:
                idle += 1.0
                self.wfile.write(b": ping\n\n")  # keep proxies from closing the stream
                self.wfile.flush()
                if state.status != "running" and state.q.empty():
                    write({"kind": "finished", "status": state.status,
                           "summary": (state.result or {}).get("summary", ""), "run_id": rid})
                    break
                if idle > 7200:
                    break

    def api_chat(self, body: dict):
        task = str(body.get("task") or "").strip()
        if not task:
            return self.send_json({"error": "empty task"}, 400)
        state = self.app.start_run(
            task,
            session_id=body.get("session_id") or None,
            mode=str(body.get("mode") or self.app.conf.get("mode") or "single"),
            provider_id=body.get("provider") or None,
            model=body.get("model") or None,
            persona=str(body.get("persona") or "operator"),
            dry_run=body.get("dry_run") if "dry_run" in body else None,
        )
        self.send_json({"run_id": state.id, "session_id": state.session_id,
                        "stream": f"/api/stream/{state.id}"})

    def api_bridge(self, body: dict):
        state = self.app.runs.get(str(body.get("run_id", "")))
        if not state or not state.gate:
            return self.send_json({"error": "no bridge waiting on that run"}, 404)
        state.gate.submit(str(body.get("reply", "")))
        self.send_json({"ok": True})

    def api_confirm(self, body: dict):
        state = self.app.runs.get(str(body.get("run_id", "")))
        if not state or not state.gate:
            return self.send_json({"error": "no confirmation waiting"}, 404)
        state.gate.submit("yes" if body.get("approve") else "no")
        self.send_json({"ok": True})

    def api_export(self):
        rows = self.app.store.list_audit(limit=500)
        return self.send_json({"exported": time.time(), "audit": rows,
                               "sessions": self.app.store.list_sessions(limit=100)})

    def api_pair(self, body: dict):
        import secrets as pysecrets
        name = str(body.get("name") or "device")
        token = pysecrets.token_urlsafe(24)
        did = self.app.store.add_device(name, _platform(),
                                        hashlib.sha256(token.encode()).hexdigest(),
                                        self.headers.get("User-Agent", ""))
        self.send_json({"device_id": did, "token": token})

    def api_set_settings(self, body: dict):
        allowed = {"mode", "provider", "model", "persona", "dry_run", "network", "max_steps",
                   "max_workers", "require_confirm", "auto_approve", "polite_delay", "searx_url"}
        updates = {k: v for k, v in body.items() if k in allowed}
        if not updates:
            return self.send_json({"error": f"nothing to set (allowed: {sorted(allowed)})"}, 400)
        path = cfg.save_config(updates, scope="home")
        self.send_json({"ok": True, "saved": updates, "path": str(path)})


# --------------------------------------------------------------------------- app glue

def _platform() -> str:
    from .cli import platform_name
    return platform_name()


def _lan_ips() -> list[str]:
    from .cli import lan_ips
    return lan_ips()


def tools_schema(self) -> list[dict]:
    """Mounted on App: the tools this runtime can actually call."""
    policy = Policy(self.conf, store=self.store)
    return ToolRunner(policy).available()


def public_config(self) -> dict:
    """Mounted on App: settings for the UI, with no secret material in it."""
    conf = self.conf
    provider, model = providers.resolve_auto(conf)
    server = conf.server_cfg
    return {"config": conf.data, "sources": conf.sources, "provider": provider, "model": model,
            "workspace": str(conf.workspace), "state_dir": str(cfg.home_dir()),
            "auth_required": bool(server.get("token") or conf.secret("server_token")),
            "secrets_present": [p for p in cfg.SECRET_ENV
                                if conf.secret(p)]}


App.tools_schema = tools_schema        # type: ignore[attr-defined]
App.public_config = public_config      # type: ignore[attr-defined]


SERVICE_WORKER = """\
/* windycity-agent service worker — offline shell only, never caches API replies */
const CACHE = 'wy-agent-v1';
const SHELL = ['/', '/manifest.webmanifest'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.pathname.startsWith('/api/')) return;  // live data stays live
  e.respondWith(
    fetch(e.request).then(resp => {
      const copy = resp.clone();
      caches.open(CACHE).then(c => c.put(e.request, copy)).catch(() => {});
      return resp;
    }).catch(() => caches.match(e.request).then(r => r || caches.match('/')))
  );
});
"""


def serve(conf: cfg.Config, store: Store | None = None, open_browser: bool = False):
    store = store or Store(cfg.state_path())
    app = App(conf, store)
    Handler.app = app
    host = conf.server_cfg.get("host") or "0.0.0.0"
    port = int(conf.server_cfg.get("port") or 8765)
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    tok = app.token()
    print(f"\n  windycity-agent {VERSION} — console up")
    print(f"  listening on http://{host}:{port}")
    for ip in _lan_ips():
        print(f"    this device:   http://{ip}:{port}/{'?token=' + tok if tok else ''}")
    print(f"    same machine:  http://127.0.0.1:{port}/{'?token=' + tok if tok else ''}")
    print(f"  workspace : {conf.workspace}")
    provider, model = providers.resolve_auto(conf)
    print(f"  provider  : {provider} / {model}"
          + ("" if provider != "demo" else "   (no model wired — offline demo mode)"))
    print(f"  auth      : {'token required' if tok else 'OPEN on this network — use `agent pair` on public Wi-Fi'}")
    print("  Ctrl-C to stop\n")
    if open_browser:
        import webbrowser
        threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}/")).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  shutting down")
    finally:
        httpd.server_close()
    return 0
