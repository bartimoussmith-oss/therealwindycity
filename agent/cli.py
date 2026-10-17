"""Command line interface — `python3 -m agent <command>`.

Every command works on every device: Android/Termux, Chromebook (Crostini or the
Android app), Windows, macOS, Linux, or a VPS. Nothing here needs a GUI, a
service manager, or a credential to *start*.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path

from . import config as cfg
from . import orchestrator, providers, tools as toolmod
from .loop import AgentLoop, Events, PERSONAS, build_system_prompt
from .store import Store

BANNER = "windycity-agent — local multi-agent runtime"


# --------------------------------------------------------------------------- helpers

def get_store() -> Store:
    return Store(cfg.state_path())


def build_context(args):
    overrides = {}
    for key in ("provider", "model", "mode", "persona"):
        val = getattr(args, key, None)
        if val:
            overrides[key] = val
    if getattr(args, "dry_run", False):
        overrides["dry_run"] = True
    if getattr(args, "yes", False):
        overrides["auto_approve"] = True
    if getattr(args, "workspace", None):
        overrides["workspace"] = args.workspace
    conf = cfg.Config(overrides)
    store = get_store()
    provider = providers.build(conf, provider=overrides.get("provider"),
                               model=overrides.get("model"))
    return conf, store, provider


def lan_ips() -> list[str]:
    ips = []
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    # the classic trick: a UDP "connection" reveals the outbound interface
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip not in ips and not ip.startswith("127."):
            ips.insert(0, ip)
    except OSError:
        pass
    return ips or ["127.0.0.1"]


def platform_name() -> str:
    env = os.environ
    if env.get("PREFIX", "").startswith("/data/data/com.termux"):
        return "android-termux"
    if env.get("TERMUX_VERSION"):
        return "android-termux"
    system = platform.system().lower()
    if system == "linux":
        try:
            if "microsoft" in Path("/proc/version").read_text().lower():
                return "windows-wsl"
        except OSError:
            pass
        if Path("/etc/os-release").exists():
            text = Path("/etc/os-release").read_text(errors="replace").lower()
            if "debian" in text and env.get("CHROMEOS_RELEASE_NAME") is None:
                return "linux-debian"
        return "linux"
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    return system


def confirm_prompt(tool: str, args: dict, reason: str) -> bool:
    if not sys.stdin.isatty():
        return False
    print(f"\n⚠  {tool} wants to run: {json.dumps(args, default=str)[:400]}")
    print(f"   reason: {reason}")
    try:
        return input("   approve? [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


# --------------------------------------------------------------------------- commands

def cmd_serve(args):
    from . import server
    conf = cfg.Config({"server": {"host": args.host, "port": args.port,
                                  "token": args.token if args.token is not None
                                  else cfg.Config().server_cfg.get("token")}})
    server.serve(conf, store=get_store(), open_browser=not args.no_browser)


def cmd_run(args):
    conf, store, provider = build_context(args)
    events = Events()
    if not args.quiet:
        events.subscribe(_print_event)
    policy = toolmod.Policy(conf, store=store, confirm_handler=None if args.yes else confirm_prompt)
    mode = args.mode or conf.get("mode") or "single"
    if mode in ("plan", "swarm"):
        orch = orchestrator.Orchestrator(conf, provider, store=store, events=events)
        out = orch.run(args.task, mode=mode)
    else:
        runner = toolmod.ToolRunner(policy)
        loop = AgentLoop(provider, runner, store=store, policy=policy, mode="single",
                         max_steps=int(conf.get("max_steps") or 24), events=events)
        out = loop.run_task(args.task, persona=args.persona or conf.get("persona") or "operator")
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print("\n" + "=" * 72)
        print(out.get("summary") or out.get("error") or "(no output)")
        print("=" * 72)
        print(f"status={out.get('status')} steps={out.get('steps')} "
              f"tokens={out.get('tokens_in')}/{out.get('tokens_out')} "
              f"cost=${out.get('cost_usd')} ({out.get('provider')}/{out.get('model')})")
    store.close()
    return 0 if out.get("status") == "done" else 1


def _print_event(evt: dict):
    kind = evt.get("kind")
    if kind == "step":
        print(f"  · step {evt.get('step')}/{evt.get('max_steps')} [{evt.get('agent')}]",
              file=sys.stderr)
    elif kind == "tool_call":
        print(f"  → {evt.get('tool')}({json.dumps(evt.get('args'), default=str)[:160]})",
              file=sys.stderr)
    elif kind == "tool_result":
        mark = "ok" if evt.get("ok") else "FAIL"
        first = str(evt.get("output", "")).strip().splitlines()
        print(f"  ← [{mark}] {evt.get('tool')}: {first[0][:140] if first else ''}", file=sys.stderr)
    elif kind == "worker_start":
        print(f"  ‖ worker {evt.get('worker')} started: {str(evt.get('task'))[:100]}", file=sys.stderr)
    elif kind == "worker_done":
        print(f"  ‖ worker {evt.get('worker')} {evt.get('status')}", file=sys.stderr)
    elif kind == "phase":
        print(f"  ~ {evt.get('phase')}: {evt.get('note','')}", file=sys.stderr)
    elif kind == "error":
        print(f"  ✗ {evt.get('error')}", file=sys.stderr)


def cmd_chat(args):
    conf, store, provider = build_context(args)
    policy = toolmod.Policy(conf, store=store, confirm_handler=None if args.yes else confirm_prompt)
    runner = toolmod.ToolRunner(policy)
    events = Events()
    events.subscribe(_print_event)
    loop = AgentLoop(provider, runner, store=store, policy=policy,
                     max_steps=int(conf.get("max_steps") or 24), events=events)
    sid = store.create_session("chat", provider=provider.id, model=provider.model)
    print(f"{BANNER}\nprovider={provider.id} model={provider.model} workspace={conf.workspace}")
    print("Type a task. 'exit' quits, '/new' starts a new session, '/mode swarm' switches modes.\n")
    mode = conf.get("mode") or "single"
    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("exit", "quit", ":q"):
            break
        if line == "/new":
            sid = store.create_session("chat", provider=provider.id, model=provider.model)
            print(f"new session {sid}")
            continue
        if line.startswith("/mode"):
            mode = line.split()[-1]
            print(f"mode = {mode}")
            continue
        if line.startswith("/provider"):
            overrides = {"provider": line.split()[-1]}
            provider = providers.build(cfg.Config(overrides))
            print(f"provider = {provider.id} / {provider.model}")
            continue
        if mode in ("plan", "swarm"):
            out = orchestrator.Orchestrator(conf, provider, store=store).run(line, session_id=sid,
                                                                            mode=mode)
        else:
            out = loop.run_task(line, session_id=sid)
        print("\n" + (out.get("summary") or out.get("error") or "(no output)") + "\n")
    store.close()
    return 0


def cmd_doctor(args):
    conf = cfg.Config()
    store = get_store()
    plat = platform_name()
    print(f"{BANNER}\ndoctor @ {time.strftime('%Y-%m-%d %H:%M')}\n" + "-" * 60)
    print(f"platform      : {plat} ({platform.system()} {platform.release()}, {platform.machine()})")
    print(f"python        : {platform.python_version()} ({sys.executable})")
    print(f"repo root     : {cfg.REPO_ROOT}")
    print(f"workspace     : {conf.workspace}  ({'exists' if conf.workspace.exists() else 'MISSING'})")
    print(f"state dir     : {cfg.home_dir()}")
    print(f"state db      : {cfg.state_path()} ({'ok' if cfg.state_path().exists() else 'not created yet'})")
    print(f"config files  : {', '.join(conf.sources) or 'defaults only'}")
    print(f"secrets file  : {cfg.secrets_path()} "
          f"({'present' if cfg.secrets_path().exists() else 'none — keys come from env'})")

    # capability probe -----------------------------------------------------
    print("\nCAPABILITIES")
    tools_present = {t: bool(__import__("shutil").which(t))
                     for t in ("git", "curl", "bash", "rg", "ffmpeg", "node", "npm", "ollama", "claude")}
    for name, ok in tools_present.items():
        print(f"  {'✓' if ok else '·'} {name}")
    print(f"  ✓ sqlite (built in), {'fts5 search' if store._fts else 'LIKE fallback (no fts5)'}")

    print("\nPROVIDERS")
    picks = providers.available(conf)
    for pid, ok, reason in picks:
        mark = "✓" if ok else "·"
        first = (reason or "").splitlines()[0] if reason else ""
        print(f"  {mark} {pid:<12} {'ready' if ok else first[:96]}")
    if any(not ok and reason and len(reason.splitlines()) > 1 for _p, ok, reason in picks):
        print("  (full notes: python3 -m agent providers)")
    if not any(ok for _p, ok, _r in picks if _p not in ("demo",)):
        print("\n  NOTE: no model wired yet. The runtime still works offline:")
        print("    python3 -m agent run \"list the repo structure\"      # offline demo, real tools")
        print("    python3 -m agent run \"...\" --provider paste         # drive it from Arena.ai")
        print("    python3 -m agent key set anthropic                   # or bring a key")

    # workarounds ----------------------------------------------------------
    print("\nWORKAROUNDS FOR COMMON CONSTRAINTS")
    rows = [
        ("no API key", "`--provider paste` (Arena.ai in the browser, replies pasted back) "
                       "or `--provider claude-cli` if the Claude CLI is installed"),
        ("no GPU / weak CPU", "point `base_url` at any OpenAI-compatible host (LM Studio, llama.cpp, "
                              "vLLM, a homelab box, a friend's server) — same runtime, bigger metal"),
        ("phone storage/thermals", "run the runtime on the PC and open the PWA from the phone on the "
                                   "same Wi-Fi, or over Tailscale from anywhere"),
        ("Chromebook (no Linux dev env)",
         "use the Android app from Play Store to reach a Termux install on your phone, or run the "
         "PC host and open the PWA in Chrome — nothing needs Crostini"),
        ("no always-on machine", "the runtime is a folder + a config; export/import it, or run it "
                                 "from a USB stick on any Windows box"),
        ("corporate proxy / offline", "`network: false` in config keeps every tool local; "
                                      "local model via Ollama gives full offline operation"),
    ]
    for need, fix in rows:
        print(f"  {need:<32} → {fix}")
    print("\nSELF-TEST")
    print("  run:  python3 -m agent selftest")
    store.close()
    return 0


def cmd_selftest(args):
    """Offline end-to-end proof: loop + tools + store + policy, zero credentials."""
    from .providers import DemoProvider
    ok = True
    print(f"{BANNER}\nselftest (offline, real tools)\n" + "-" * 60)
    conf = cfg.Config({"provider": "demo", "mode": "single", "max_steps": 4,
                       "workspace": args.workspace or str(cfg.REPO_ROOT)})
    store = Store(":memory:")
    policy = toolmod.Policy(conf, store=store)
    runner = toolmod.ToolRunner(policy)
    loop = AgentLoop(DemoProvider(conf), runner, store=store, policy=policy, max_steps=4)
    out = loop.run_task("selftest: show the repo layout and git status")
    checks = [
        ("provider ran", out["status"] in ("done", "stopped")),
        ("real tool calls happened", bool(store.query("SELECT 1 FROM messages WHERE role='tool'"))),
        ("audit trail written", bool(store.list_audit())),
        ("summary produced", bool(out.get("summary"))),
    ]
    # policy checks
    verdict, why = policy.judge_command("rm -rf /")
    checks.append(("denies recursive root delete", verdict == "deny"))
    verdict, _ = policy.judge_command("sudo apt install nmap")
    checks.append(("flags privilege escalation", verdict == "confirm"))
    try:
        policy.resolve("/etc/passwd")
        checks.append(("path jail holds", False))
    except PermissionError:
        checks.append(("path jail holds", True))
    # store round-trip
    sid = store.create_session("t")
    store.add_message(sid, None, "user", "hi")
    checks.append(("session round-trip", len(store.get_messages(sid)) == 1))
    # bridge parsing (the no-API-key path)
    from .providers import PasteBridgeProvider
    comp = PasteBridgeProvider.parse_reply('```json\n{"tool_calls":[{"name":"list_dir","args":{"path":"."}}]}\n```')
    checks.append(("paste bridge parses tool calls", comp.tool_calls and comp.tool_calls[0].name == "list_dir"))

    for name, passed in checks:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
        ok = ok and passed
    print("-" * 60)
    print("selftest:", "ALL PASS" if ok else "FAILURES ABOVE")
    store.close()
    return 0 if ok else 1


def cmd_providers(args):
    conf = cfg.Config()
    for pid, ok, reason in providers.available(conf):
        cls = providers.PROVIDERS[pid]
        print(f"{'✓' if ok else '·'} {pid:<12} {cls.label}")
        if not ok:
            print(f"    {reason.splitlines()[0]}")
    print("\nSet with:  python3 -m agent config set provider <id>")
    return 0


def cmd_models(args):
    conf, _store, provider = build_context(args)
    print(f"provider: {provider.id}  endpoint: {provider.base_url or '(local)'}")
    try:
        models = provider.list_models()
    except Exception as exc:
        print(f"could not list models: {exc}")
        print(f"default model for this provider: {provider.default_model}")
        return 1
    if not models:
        print("(provider returned no model list)")
    for m in models[:80]:
        print(f"  {m}")
    print(f"\nuse one with:  python3 -m agent config set model <name>")
    return 0


def cmd_key(args):
    if args.action == "list":
        data = {}
        try:
            data = json.loads(cfg.secrets_path().read_text())
        except Exception:
            pass
        for pid in cfg.SECRET_ENV:
            src = "env" if os.environ.get(cfg.SECRET_ENV[pid]) else ("file" if data.get(pid) else "-")
            masked = "••••" if (os.environ.get(cfg.SECRET_ENV[pid]) or data.get(pid)) else ""
            print(f"  {pid:<12} {src:<5} {masked}")
        return 0
    if args.action == "rm":
        data = {}
        try:
            data = json.loads(cfg.secrets_path().read_text())
        except Exception:
            pass
        data.pop(args.provider, None)
        cfg.secrets_path().write_text(json.dumps(data, indent=2))
        print(f"removed {args.provider} from {cfg.secrets_path()}")
        return 0
    value = args.value
    if not value:
        value = getpass.getpass(f"paste the {args.provider} key (hidden, never echoed): ").strip()
    if not value:
        print("no value given — nothing written")
        return 1
    path = cfg.save_secret(args.provider, value)
    print(f"stored {args.provider} key in {path} (chmod 600). It is not in the repo, and never will be.")
    print("Tip: `export {}=...` works too, and keeps the key out of disk entirely."
          .format(cfg.SECRET_ENV.get(args.provider, "WY_AGENT_API_KEY")))
    return 0


def cmd_config(args):
    conf = cfg.Config()
    if args.action == "get" or not args.action:
        print(json.dumps(conf.data, indent=2, sort_keys=True))
        print(f"\nsources: {', '.join(conf.sources) or 'defaults'}")
        return 0
    if args.action == "set":
        if not args.key:
            print("usage: agent config set <key> <value> [--scope repo|home]")
            return 1
        value = args.value
        if isinstance(value, str):
            low = value.lower()
            if low in ("true", "false"):
                value = low == "true"
            elif low in ("none", "null"):
                value = None
            else:
                try:
                    value = int(value)
                except ValueError:
                    pass
        try:
            path = cfg.save_config({args.key: value}, scope=args.scope)
        except ValueError as exc:
            print(f"refused: {exc}")
            return 1
        print(f"set {args.key} = {value!r} in {path}")
        return 0
    print("usage: agent config [get|set]")
    return 1


def cmd_pair(args):
    """Create a device token and print the URLs to open on the phone."""
    import hashlib
    import secrets as pysecrets
    store = get_store()
    token = pysecrets.token_urlsafe(24)
    store.add_device(args.name, platform_name(), hashlib.sha256(token.encode()).hexdigest(),
                     user_agent="cli")
    cfg.save_secret("server_token", token)
    port = args.port
    print(f"device '{args.name}' paired.\n")
    print("Open one of these on the device (same Wi-Fi for the LAN one):")
    for ip in lan_ips():
        print(f"  http://{ip}:{port}/?token={token}")
    print(f"  http://localhost:{port}/?token={token}   (same machine)")
    print("\nToken stored in the private secrets file. Revoke later with `agent devices rm <id>`.")
    print("Set a fixed token instead with: agent config set server.token <value>")
    store.close()
    return 0


def cmd_devices(args):
    store = get_store()
    rows = store.list_devices()
    if not rows:
        print("no devices paired yet — run: python3 -m agent pair --name phone")
        return 0
    for r in rows:
        print(f"  {r['id']}  {r['name']:<14} {r['platform']:<16} "
              f"last seen {time.strftime('%Y-%m-%d %H:%M', time.localtime(r['last_seen']))}")
    store.close()
    return 0


def cmd_sessions(args):
    store = get_store()
    if args.action == "show" and args.id:
        sess = store.get_session(args.id)
        if not sess:
            print("no such session")
            return 1
        print(f"# {sess['title']}  ({sess['id']}, {sess['mode']}, {sess['provider']}/{sess['model']})")
        for m in store.get_messages(args.id):
            who = m["role"].upper()
            body = (m["content"] or m["tool_result"] or "")
            print(f"\n[{who}]{' ' + (m['tool_name'] or '') if m['tool_name'] else ''}\n{str(body)[:2000]}")
        return 0
    rows = store.list_sessions(limit=args.limit)
    if not rows:
        print("no sessions yet")
    for r in rows:
        when = time.strftime("%m-%d %H:%M", time.localtime(r["updated"]))
        print(f"  {r['id']}  {when}  {r['mode']:<6} {r['n']:>3} msg  {r['title'][:70]}")
    store.close()
    return 0


def cmd_audit(args):
    store = get_store()
    rows = store.list_audit(args.run, limit=args.limit)
    for r in rows:
        when = time.strftime("%H:%M:%S", time.localtime(r["ts"]))
        mark = "✓" if r["ok"] else "✗"
        print(f"  {when} {mark} [{r['decision']:<8}] {r['tool']:<14} "
              f"{str(r['args'])[:110]}")
    if not rows:
        print("(audit trail is empty — run something first)")
    store.close()
    return 0


def cmd_memory(args):
    store = get_store()
    if args.action == "set":
        store.memo_set(args.key, args.value, scope=args.scope or "global", tags=args.tags or "")
        print(f"stored {args.key}")
    elif args.action == "search":
        for r in store.memo_search(args.key, limit=20):
            print(f"  {r['key']} [{r.get('tags','')}]: {str(r['value'])[:200]}")
    else:
        for r in store.memo_all():
            print(f"  {r['key']} [{r.get('tags','')}]: {str(r['value'])[:200]}")
    store.close()
    return 0


def cmd_export(args):
    import tarfile
    out = Path(args.out or (cfg.REPO_ROOT / "agent" / "dist" /
                            f"windycity-agent-{time.strftime('%Y%m%d-%H%M')}.tar.gz"))
    out.parent.mkdir(parents=True, exist_ok=True)
    secret = cfg.secrets_path()
    with tarfile.open(out, "w:gz") as tar:
        if secret.exists():
            if args.with_secrets:
                tar.add(secret, arcname="secrets.json")
                print("!! including secrets.json — keep this archive as safe as the keys in it")
            else:
                tar.add(secret, arcname="secrets.json.example")
        for p in (cfg.config_path(), cfg.state_path()):
            if p.exists():
                tar.add(p, arcname=p.name)
        man = cfg.REPO_ROOT / "AGENT.md"
        if man.exists():
            tar.add(man, arcname="AGENT.md")
    print(f"exported to {out} ({out.stat().st_size/1024:.1f} KB)")
    print("On the new device:  python3 -m agent import " + str(out))
    return 0


def cmd_import(args):
    import shutil
    import tarfile
    src = Path(args.path)
    if not src.exists():
        print(f"no such file: {src}")
        return 1
    dest = cfg.home_dir()
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(src) as tar:
        names = tar.getnames()
        tar.extractall(dest)  # noqa: S202 — local archive the owner just made
    for line in names:
        print(f"  restored {line}")
    if (dest / "secrets.json.example").exists() and not (dest / "secrets.json").exists():
        (dest / "secrets.json.example").rename(dest / "secrets.json")
        os.chmod(dest / "secrets.json", 0o600)
    print(f"\nstate restored into {dest}")
    print("check it with:  python3 -m agent doctor")
    return 0


def cmd_install(args):
    from . import portability
    return portability.install(args.target)


def cmd_prune(args):
    removed = orchestrator.cleanup_worktrees(keep=args.keep)
    for r in removed:
        print(f"  removed {r}" if not args.keep else f"  found {r}")
    spill = cfg.home_dir() / "spill"
    if spill.exists() and not args.keep:
        import shutil
        shutil.rmtree(spill, ignore_errors=True)
        print("  cleared spill dir")
    return 0


def cmd_personas(args):
    for name, text in PERSONAS.items():
        print(f"### {name}\n{text}\n")
    return 0


# --------------------------------------------------------------------------- parser

# Global options are accepted BOTH before and after the subcommand
# (`agent --provider paste run "x"` and `agent run "x" --provider paste`), because
# nobody remembers which side argparse wants.
GLOBAL_OPTS = [
    (("--provider",), {"help": "model provider id (anthropic, openai, ollama, paste, demo…)"}),
    (("--model",), {"help": "model name for the chosen provider"}),
    (("--mode",), {"choices": ["single", "plan", "swarm"], "help": "agent topology"}),
    (("--persona",), {"choices": list(PERSONAS), "help": "system persona"}),
    (("--workspace",), {"help": "override the workspace root"}),
    (("--dry-run",), {"action": "store_true", "help": "refuse mutating tool calls"}),
    (("--yes", "-y"), {"action": "store_true", "help": "skip confirm-class prompts"}),
    (("--json",), {"action": "store_true", "help": "machine-readable output"}),
    (("--quiet", "-q"), {"action": "store_true", "help": "no progress on stderr"}),
]


def _global_parent(suppress: bool) -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    for flags, kwargs in GLOBAL_OPTS:
        kw = dict(kwargs)
        if suppress:
            kw["default"] = argparse.SUPPRESS  # a sub-level copy must not clobber the top level
        parent.add_argument(*flags, **kw)
    return parent


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agent", description=BANNER,
                                parents=[_global_parent(suppress=False)])
    sub = p.add_subparsers(dest="command")
    sub_defaults = {"parents": [_global_parent(suppress=True)]}

    s = sub.add_parser("serve", help="run the web/phone console (PWA) on this machine", **sub_defaults)
    s.add_argument("--host", default=os.environ.get("WY_AGENT_HOST", "0.0.0.0"))
    s.add_argument("--port", type=int, default=int(os.environ.get("WY_AGENT_PORT", 8765)))
    s.add_argument("--token", default=None, help="access token; omit for open LAN access")
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("run", help="run one task to completion", **sub_defaults)
    s.add_argument("task")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("chat", help="interactive console session", **sub_defaults)
    s.set_defaults(func=cmd_chat)

    s = sub.add_parser("doctor", help="probe this device: what works, and the workaround for what doesn't", **sub_defaults)
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("selftest", help="offline end-to-end test — no keys, no network",
                       **sub_defaults)
    s.set_defaults(func=cmd_selftest)

    s = sub.add_parser("providers", help="list providers and whether they are ready", **sub_defaults)
    s.set_defaults(func=cmd_providers)

    s = sub.add_parser("models", help="ask the active provider what models it serves", **sub_defaults)
    s.set_defaults(func=cmd_models)

    s = sub.add_parser("key", help="manage API keys (private file, never the repo)", **sub_defaults)
    s.add_argument("action", choices=["set", "list", "rm"])
    s.add_argument("provider", nargs="?")
    s.add_argument("value", nargs="?")
    s.set_defaults(func=cmd_key)

    s = sub.add_parser("config", help="view or change non-secret settings", **sub_defaults)
    s.add_argument("action", nargs="?", choices=["get", "set"], default="get")
    s.add_argument("key", nargs="?")
    s.add_argument("value", nargs="?")
    s.add_argument("--scope", choices=["repo", "home"], default="home")
    s.set_defaults(func=cmd_config)

    s = sub.add_parser("pair", help="pair a new device (phone/tablet/Chromebook)", **sub_defaults)
    s.add_argument("--name", default="device")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(func=cmd_pair)

    s = sub.add_parser("devices", help="list paired devices", **sub_defaults)
    s.set_defaults(func=cmd_devices)

    s = sub.add_parser("sessions", help="list or show past sessions", **sub_defaults)
    s.add_argument("action", nargs="?", choices=["list", "show"], default="list")
    s.add_argument("id", nargs="?")
    s.add_argument("--limit", type=int, default=30)
    s.set_defaults(func=cmd_sessions)

    s = sub.add_parser("audit", help="every tool call, its verdict and its result hash", **sub_defaults)
    s.add_argument("--run")
    s.add_argument("--limit", type=int, default=60)
    s.set_defaults(func=cmd_audit)

    s = sub.add_parser("memory", help="durable notes the agent can reuse", **sub_defaults)
    s.add_argument("action", nargs="?", choices=["list", "set", "search"], default="list")
    s.add_argument("key", nargs="?")
    s.add_argument("value", nargs="?")
    s.add_argument("--tags")
    s.add_argument("--scope")
    s.set_defaults(func=cmd_memory)

    s = sub.add_parser("export", help="bundle state so you can port it to a new device", **sub_defaults)
    s.add_argument("--out")
    s.add_argument("--with-secrets", action="store_true",
                   help="include the key file (off by default)")
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("import", help="restore a bundle exported from another device", **sub_defaults)
    s.add_argument("path")
    s.set_defaults(func=cmd_import)

    s = sub.add_parser("install", help="write the right bootstrap for this device", **sub_defaults)
    s.add_argument("target", nargs="?", default="auto",
                   choices=["auto", "termux", "linux", "windows", "chromebook", "macos"])
    s.set_defaults(func=cmd_install)

    s = sub.add_parser("prune", help="clear swarm worktrees and spilled output", **sub_defaults)
    s.add_argument("--keep", action="store_true")
    s.set_defaults(func=cmd_prune)

    s = sub.add_parser("personas", help="show the built-in system personas", **sub_defaults)
    s.set_defaults(func=cmd_personas)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    for (flags, _kw) in GLOBAL_OPTS:
        dest = flags[0].lstrip("-").replace("-", "_")
        if not hasattr(args, dest):  # subparser suppressed it; the top level had no value
            setattr(args, dest, None if dest not in ("dry_run", "yes", "json", "quiet") else False)
    if not getattr(args, "command", None):
        parser.print_help()
        print("\nNew here? Run:  python3 -m agent doctor")
        return 0
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
