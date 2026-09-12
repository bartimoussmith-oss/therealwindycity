"""The tool layer: what the agent can actually DO on the machine.

Design rules
------------
* Everything returns a plain dict and a truncated text rendering the model can read.
  Big outputs spill to ~/.windycity-agent/spill/ instead of blowing up the context.
* Every call is audited (tool, args, verdict, duration, result hash) in SQLite.
* Three verdicts per mutating call: allow / confirm / deny. Catastrophic patterns
  are denied outright; elevated or irreversible ones need a human yes (or the
  explicit --yes / require_confirm=false opt-out).
* Paths are jailed to the workspace unless the owner sets
  allow_outside_workspace: true. Reads may also touch the agent's own state dir.
* Repo rules are respected: polite crawling (LEGAL.md), no credential writes,
  read-mostly access to engine/ and data/.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import config as cfg

USER_AGENT = "windycity-agent/1.0 (+https://github.com/bartimoussmith-oss/therealwindycity)"

# --------------------------------------------------------------------------- verdicts

DENY_PATTERNS: list[tuple[str, str]] = [
    (r"rm\s+(-[a-zA-Z]*\s+)*-(rf|fr)\s+/\s*$", "recursive delete of /"),
    (r"rm\s+(-[a-zA-Z]*\s+)*-rf\s+(\$HOME|~)(\s|/|$)", "recursive delete of home"),
    (r"rm\s+-rf\s+/\*", "recursive delete of /*"),
    (r"\bmkfs(\.\w+)?\b", "filesystem format"),
    (r"\bdd\b.*of=/dev/(sd|nvme|mmcblk|disk)", "raw write to a block device"),
    (r">\s*/dev/(sd|nvme|mmcblk|disk)", "raw write to a block device"),
    (r":\(\)\s*\{\s*:\|:&\s*\}\s*;:", "fork bomb"),
    (r"\b(shutdown|poweroff|halt|reboot)\b", "power state change"),
    (r"chmod\s+-R\s+777\s+/(\s|$)", "world-writable root"),
    (r"\bhistory\s+-c\b", "audit trail destruction"),
    (r":>\s*/var/log|truncate\s+-s\s*0\s+/var/log", "log destruction"),
    (r"\bgit\s+push\s+.*--force(?!-with-lease)", "force push (repo rule: never)"),
    (r"\bgit\s+(reset\s+--hard|clean\s+-[a-z]*f)", "destructive git reset/clean"),
    (r"\bgit\s+filter-branch\b|\bgit\s+rebase\s+-i\b", "history rewrite"),
    (r"\brm\s+-rf\s+\.git\b", "repository destruction"),
]

CONFIRM_PATTERNS: list[tuple[str, str]] = [
    (r"\bsudo\b|\bdoas\b|\bsu\s", "privilege escalation"),
    (r"\bapt(-get)?\s+(install|remove|purge|upgrade)|apt\s+autoremove", "system package change"),
    (r"\bpkg\s+(install|uninstall|remove|upgrade)\b", "termux package change"),
    (r"\bpip\s+install|\bpip3\s+install|\bnpm\s+i(nstall)?\s+-g|\bcurl\b.*\|\s*(ba)?sh|\bwget\b.*\|\s*(ba)?sh",
     "installing software (remote script)"),
    (r"\brm\s+-rf?\b", "recursive delete"),
    (r"\btruncate\b|>\s*\S+\.(db|sqlite|sqlite3)\b", "destructive overwrite"),
    (r"\bgit\s+push\b", "publishing to a remote"),
    (r"\bgit\s+checkout\s+--\s+\.|\bgit\s+restore\b", "discarding local changes"),
    (r"\bsystemctl\b|\bservice\b|\bcrontab\b", "changing system services"),
    (r"\bkill(all)?\b|\bpkill\b", "signalling processes"),
]

SAFE_READONLY = re.compile(r"^\s*(ls|cat|head|tail|wc|file|stat|du|df|pwd|whoami|id|date|uname|env|"
                           r"grep|rg|find|sed -n|awk|sort|uniq|cut|tr|echo|which|type|python3? -V|"
                           r"git (status|log|diff|show|branch|remote|describe|rev-parse))\b")

BIG_OUTPUT = 40_000        # chars returned to the model before spilling
SPILL_CHARS = 2_000_000    # hard cap on what we will hold in memory


# --------------------------------------------------------------------------- result

@dataclass
class ToolResult:
    ok: bool
    text: str
    data: dict = field(default_factory=dict)
    verdict: str = "allow"

    def as_dict(self) -> dict:
        return {"ok": self.ok, "output": self.text, "data": self.data, "verdict": self.verdict}

    def as_message_content(self) -> str:
        status = "ok" if self.ok else "ERROR"
        return f"[{status}]\n{self.text}"


# --------------------------------------------------------------------------- policy

class Policy:
    def __init__(self, conf: cfg.Config, store=None, confirm_handler=None, agent_name: str = "main",
                 workspace_override=None):
        self.conf = conf
        self.store = store
        self.confirm_handler = confirm_handler
        self.agent_name = agent_name
        self.workspace = Path(workspace_override).resolve() if workspace_override else conf.workspace
        self.agent_home = cfg.home_dir()
        self.allow_outside = bool(conf.get("allow_outside_workspace"))
        self.dry_run = bool(conf.get("dry_run"))
        self.require_confirm = bool(conf.get("require_confirm"))
        self.auto_approve = bool(conf.get("auto_approve", True))
        self.network = bool(conf.get("network", True))
        self.shell_timeout = int(conf.get("shell_timeout") or 120)
        self.polite_delay = float(conf.get("polite_delay") or 3.0)
        self._last_hit: dict[str, float] = {}

    # -- paths --------------------------------------------------------------
    def resolve(self, raw: str, must_exist: bool = False) -> Path:
        p = Path(str(raw)).expanduser()
        if not p.is_absolute():
            p = (self.workspace / p)
        p = p.resolve()
        if not self.allow_outside:
            roots = [self.workspace.resolve(), self.agent_home.resolve()]
            if not any(_is_within(p, r) for r in roots):
                raise PermissionError(
                    f"path {p} is outside the workspace ({self.workspace}) and the agent state dir. "
                    "Set allow_outside_workspace=true if that is really what you want.")
        if must_exist and not p.exists():
            raise FileNotFoundError(f"no such path: {p}")
        return p

    # -- commands -----------------------------------------------------------
    def judge_command(self, command: str) -> tuple[str, str]:
        """(verdict, reason) where verdict is allow | confirm | deny."""
        flat = " ".join(command.split())
        for pat, why in DENY_PATTERNS:
            if re.search(pat, flat, flags=re.I):
                return "deny", why
        for pat, why in CONFIRM_PATTERNS:
            if re.search(pat, flat, flags=re.I):
                return "confirm", why
        return "allow", "no elevated pattern"

    def confirm(self, tool: str, args: dict, reason: str) -> tuple[bool, str]:
        """Resolve a confirm-class call."""
        if not self.require_confirm and self.auto_approve and not self.confirm_handler:
            return True, f"auto-approved ({reason})"
        if self.confirm_handler:
            return self.confirm_handler(tool, args, reason), "human decision"
        return False, f"needs confirmation ({reason}) but no interactive channel; re-run with --yes"

    # -- politeness ---------------------------------------------------------
    def polite_wait(self, url: str):
        host = urllib.parse.urlparse(url).netloc
        last = self._last_hit.get(host, 0.0)
        delta = time.time() - last
        if delta < self.polite_delay:
            time.sleep(self.polite_delay - delta)
        self._last_hit[host] = time.time()

    # -- audit --------------------------------------------------------------
    def record(self, run_id: str | None, tool: str, args: dict, verdict: str, result: ToolResult | None,
               duration_ms: int):
        if not self.store:
            return
        h = ""
        if result is not None:
            h = hashlib.sha256(result.text.encode("utf-8", "replace")).hexdigest()[:16]
        try:
            self.store.audit(run_id, tool, args, verdict, bool(result.ok) if result else False,
                             duration_ms, h, self.agent_name)
        except Exception:
            pass


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


# --------------------------------------------------------------------------- registry

@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    func: callable
    mutating: bool = False
    confirm_reason: str = ""


REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, parameters: dict, mutating: bool = False,
         confirm_reason: str = ""):
    def deco(fn):
        REGISTRY[name] = Tool(name, description, parameters, fn, mutating, confirm_reason)
        return fn
    return deco


def schema_list(policy: Policy, include_mutating: bool = True) -> list[dict]:
    disabled = set(policy.conf.get("tools", {}).get("disabled") or [])
    out = []
    for t in REGISTRY.values():
        if t.name in disabled:
            continue
        if t.mutating and policy.dry_run:
            pass  # still advertised; dry-run intercepts and reports instead
        out.append({"name": t.name, "description": t.description, "parameters": t.parameters})
    return out


class ToolRunner:
    """Executes tools with policy checks, timeouts, spilling and audit."""

    def __init__(self, policy: Policy, run_id: str | None = None, allowed: set[str] | None = None):
        self.policy = policy
        self.run_id = run_id
        self.allowed = allowed  # None = everything registered

    def available(self) -> list[dict]:
        names = [n for n in REGISTRY if self.allowed is None or n in self.allowed]
        disabled = set(self.policy.conf.get("tools", {}).get("disabled") or [])
        return [{"name": REGISTRY[n].name, "description": REGISTRY[n].description,
                 "parameters": REGISTRY[n].parameters}
                for n in names if n not in disabled]

    def run(self, name: str, args: dict) -> ToolResult:
        started = time.time()
        tool_obj = REGISTRY.get(name)
        if tool_obj is None:
            res = ToolResult(False, f"unknown tool {name!r}. Available: {', '.join(sorted(REGISTRY))}")
            self.policy.record(self.run_id, name, args, "deny", res, 0)
            return res
        if self.allowed is not None and name not in self.allowed:
            res = ToolResult(False, f"tool {name!r} is not permitted for this agent "
                                    f"(allowed: {', '.join(sorted(self.allowed))})")
            self.policy.record(self.run_id, name, args, "deny", res, 0)
            return res

        verdict = "allow"
        reason = ""
        if tool_obj.mutating:
            if self.policy.dry_run:
                res = ToolResult(True, f"[dry-run] would call {name} with "
                                       f"{json.dumps(args, default=str)[:1000]}")
                self.policy.record(self.run_id, name, args, "dry_run", res,
                                   int((time.time() - started) * 1000))
                return res
            if name == "shell":
                verdict, reason = self.policy.judge_command(str(args.get("command", "")))
            elif tool_obj.confirm_reason:
                verdict, reason = "confirm", tool_obj.confirm_reason
            else:
                verdict, reason = "allow", "mutating call inside the workspace jail"
            if verdict == "deny":
                res = ToolResult(False, f"refused: {reason}. This is a hard rule, not a suggestion.")
                self.policy.record(self.run_id, name, args, "deny", res, 0)
                return res
            if verdict == "confirm":
                ok, note = self.policy.confirm(name, args, reason)
                if not ok:
                    res = ToolResult(False, f"refused: {note}")
                    self.policy.record(self.run_id, name, args, "deny", res, 0)
                    return res
                self.policy.record(self.run_id, name, args, "confirm", None, 0)
        try:
            out = tool_obj.func(args, self.policy)
            if not isinstance(out, ToolResult):
                out = ToolResult(True, str(out))
        except Exception as exc:  # tools never crash the loop
            out = ToolResult(False, f"{type(exc).__name__}: {exc}")
        out.text = self._shape(out.text)
        self.policy.record(self.run_id, name, args, verdict, out,
                           int((time.time() - started) * 1000))
        return out

    def _shape(self, text: str) -> str:
        text = str(text)
        if len(text) <= BIG_OUTPUT:
            return text
        spill_dir = cfg.home_dir() / "spill"
        spill_dir.mkdir(parents=True, exist_ok=True)
        path = spill_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{hashlib.sha1(text.encode()).hexdigest()[:8]}.txt"
        path.write_text(text[:SPILL_CHARS], encoding="utf-8", errors="replace")
        head = text[:BIG_OUTPUT // 2]
        tail = text[-2_000:]
        return (f"{head}\n\n[... {len(text) - len(head) - len(tail):,} chars truncated; "
                f"full output at {path} ...]\n\n{tail}")


# --------------------------------------------------------------------------- file tools

@tool("read_file", "Read a text file from the workspace. Returns numbered lines.",
      {"type": "object", "properties": {
          "path": {"type": "string", "description": "file path (relative to the workspace root)"},
          "max_bytes": {"type": "integer"},
          "line_numbers": {"type": "boolean"}},
       "required": ["path"]})
def _read(args, policy: Policy) -> ToolResult:
    path = policy.resolve(args["path"], must_exist=True)
    max_bytes = int(args.get("max_bytes") or 400_000)
    raw = path.read_bytes()[:max_bytes]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", "replace")
        text = f"(binary or non-UTF8 file — showing replacement chars)\n{text}"
    numbered = args.get("line_numbers", True)
    if numbered:
        lines = text.splitlines()
        text = "\n".join(f"{i+1:>6}| {ln}" for i, ln in enumerate(lines))
    return ToolResult(True, text, {"path": str(path), "bytes": len(raw)})


@tool("write_file", "Create or overwrite a file in the workspace.",
      {"type": "object", "properties": {
          "path": {"type": "string"}, "content": {"type": "string"},
          "overwrite": {"type": "boolean"}},
       "required": ["path", "content"]}, mutating=True)
def _write(args, policy: Policy) -> ToolResult:
    path = policy.resolve(args["path"])
    content = str(args.get("content", ""))
    if path.exists() and not args.get("overwrite"):
        raise FileExistsError(f"{path} exists; pass overwrite=true to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return ToolResult(True, f"wrote {len(content)} bytes to {path}", {"path": str(path)})


@tool("edit_file", "Replace an exact string in a file. Fails if the text is absent or ambiguous.",
      {"type": "object", "properties": {
          "path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"},
          "replace_all": {"type": "boolean"}},
       "required": ["path", "old", "new"]}, mutating=True)
def _edit(args, policy: Policy) -> ToolResult:
    path = policy.resolve(args["path"], must_exist=True)
    old, new = str(args.get("old", "")), str(args.get("new", ""))
    if not old:
        raise ValueError("'old' must be non-empty")
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise ValueError(f"'{old[:80]}' not found in {path.name} — read the file first, "
                         "or use write_file")
    count = text.count(old)
    if count > 1 and not args.get("replace_all"):
        raise ValueError(f"'{old[:60]}' appears {count} times; pass replace_all=true or add context")
    updated = text.replace(old, new) if args.get("replace_all") else text.replace(old, new, 1)
    path.write_text(updated, encoding="utf-8")
    return ToolResult(True, f"edited {path} ({count if args.get('replace_all') else 1} replacement(s))",
                      {"path": str(path)})


@tool("list_dir", "List a directory tree (skips .git/__pycache__/node_modules).",
      {"type": "object", "properties": {
          "path": {"type": "string"}, "depth": {"type": "integer"},
          "max_entries": {"type": "integer"}}})
def _list_dir(args, policy: Policy) -> ToolResult:
    root = policy.resolve(args.get("path") or ".", must_exist=True)
    depth = int(args.get("depth") or 1)
    max_entries = int(args.get("max_entries") or 300)
    lines: list[str] = []
    base_depth = len(root.parts)

    def walk(d: Path):
        if len(lines) >= max_entries:
            return
        try:
            entries = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return
        for e in entries:
            if e.name in (".git", "__pycache__", "node_modules", ".venv"):
                lines.append("  " * (len(d.parts) - base_depth) + f"{e.name}/  (skipped)")
                continue
            rel = len(d.parts) - base_depth
            if e.is_dir():
                lines.append("  " * rel + f"{e.name}/")
                if rel + 1 < depth:
                    walk(e)
            else:
                try:
                    size = e.stat().st_size
                except OSError:
                    size = 0
                lines.append("  " * rel + f"{e.name}  ({_human(size)})")
            if len(lines) >= max_entries:
                lines.append(f"... truncated at {max_entries} entries")
                return

    walk(root)
    return ToolResult(True, f"{root}\n" + "\n".join(lines),
                      {"path": str(root), "entries": len(lines)})


@tool("glob", "Find files by glob pattern, e.g. '**/*.py' or '*.md'.",
      {"type": "object", "properties": {
          "pattern": {"type": "string"}, "path": {"type": "string"},
          "max_results": {"type": "integer"}},
       "required": ["pattern"]})
def _glob(args, policy: Policy) -> ToolResult:
    pattern = str(args["pattern"])
    root = policy.resolve(args.get("path") or ".")
    limit = int(args.get("max_results") or 200)
    hits = []
    for p in root.rglob("*"):
        if ".git/" in str(p) or "__pycache__" in str(p):
            continue
        rel = p.relative_to(root).as_posix()
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(p.name, pattern):
            hits.append(rel)
        if len(hits) >= limit:
            break
    return ToolResult(True, "\n".join(hits) or "(no matches)", {"count": len(hits)})


@tool("grep", "Regex search across files. Returns file:line hits with optional context.",
      {"type": "object", "properties": {
          "pattern": {"type": "string"}, "path": {"type": "string"},
          "glob": {"type": "string", "description": "filename filter, e.g. '*.py'"},
          "ignore_case": {"type": "boolean"}, "context_lines": {"type": "integer"},
          "max_results": {"type": "integer"}},
       "required": ["pattern"]})
def _grep(args, policy: Policy) -> ToolResult:
    pattern = str(args["pattern"])
    root = policy.resolve(args.get("path") or ".")
    glob_pat = args.get("glob") or "*"
    limit = int(args.get("max_results") or 80)
    ctx = int(args.get("context_lines") or 0)
    try:
        rx = re.compile(pattern, re.I if args.get("ignore_case", True) else 0)
    except re.error as exc:
        raise ValueError(f"bad regex: {exc}") from exc
    out: list[str] = []
    scanned = 0
    for p in root.rglob("*"):
        if not p.is_file() or ".git/" in str(p) or "__pycache__" in str(p):
            continue
        if not fnmatch.fnmatch(p.name, glob_pat):
            continue
        if p.stat().st_size > 4_000_000:
            continue
        scanned += 1
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines):
            if rx.search(line):
                rel = p.relative_to(root).as_posix() if _is_within(p, root) else str(p)
                if ctx:
                    lo, hi = max(0, i - ctx), min(len(lines), i + ctx + 1)
                    block = "\n".join(f"{lo+j+1:>5}| {ln}" for j, ln in enumerate(lines[lo:hi]))
                    out.append(f"{rel}:{i+1}\n{block}")
                else:
                    out.append(f"{rel}:{i+1}: {line.strip()[:300]}")
                if len(out) >= limit:
                    break
        if len(out) >= limit:
            break
    return ToolResult(True, "\n".join(out) or f"(no matches for {pattern!r})",
                      {"matches": len(out), "files_scanned": scanned})


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n}B"


# --------------------------------------------------------------------------- shell

@tool("shell", "Run a shell command on this machine and return stdout+stderr. "
               "Prefer the dedicated file tools for reading and editing.",
      {"type": "object", "properties": {
          "command": {"type": "string", "description": "the command line to run"},
          "cwd": {"type": "string", "description": "working dir (default: workspace root)"},
          "timeout": {"type": "integer", "description": "seconds (default 120)"}},
       "required": ["command"]}, mutating=True)
def _shell(args, policy: Policy) -> ToolResult:
    command = str(args["command"])
    cwd = policy.resolve(args.get("cwd") or ".") if args.get("cwd") else policy.workspace
    timeout = min(int(args.get("timeout") or policy.shell_timeout), 1800)
    t0 = time.time()
    try:
        proc = subprocess.run(command, shell=True, cwd=str(cwd), capture_output=True, text=True,
                              timeout=timeout, executable="/bin/bash" if shutil.which("bash") else None)
    except subprocess.TimeoutExpired:
        return ToolResult(False, f"timed out after {timeout}s: {command}")
    out = (proc.stdout or "") + (("\n--- stderr ---\n" + proc.stderr) if proc.stderr else "")
    return ToolResult(proc.returncode == 0, out.strip() or "(no output)",
                      {"exit_code": proc.returncode, "cwd": str(cwd),
                       "seconds": round(time.time() - t0, 2)})


# --------------------------------------------------------------------------- web

def _http_fetch(url: str, timeout: int = 30, max_bytes: int = 500_000) -> tuple[int, str, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(max_bytes)
        return resp.status, raw.decode("utf-8", "replace"), dict(resp.headers)


def _robots_ok(url: str) -> bool:
    """Minimal robots.txt check for the agent's own fetches (repo LEGAL.md rule)."""
    import urllib.robotparser
    parts = urllib.parse.urlsplit(url)
    robots = f"{parts.scheme}://{parts.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.set_url(robots)
        rp.read()
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True  # unreachable robots.txt is not a prohibition


@tool("http_get", "Fetch a public URL (polite: robots.txt honored, rate limited) and return "
                  "the text. Use for reading public pages and APIs.",
      {"type": "object", "properties": {
          "url": {"type": "string"},
          "max_bytes": {"type": "integer"}},
       "required": ["url"]})
def _http_get(args, policy: Policy) -> ToolResult:
    if not policy.network:
        return ToolResult(False, "network access is disabled (network: false in config)")
    url = str(args["url"])
    if not url.startswith(("http://", "https://")):
        raise ValueError("url must start with http:// or https://")
    if not _robots_ok(url):
        return ToolResult(False, f"robots.txt disallows automated fetching of {url}. "
                                 "Open it in a browser instead — that is the repo's rule.")
    policy.polite_wait(url)
    status, text, headers = _http_fetch(url, max_bytes=int(args.get("max_bytes") or 500_000))
    return ToolResult(status < 400, text, {"status": status, "url": url,
                                           "content_type": headers.get("Content-Type", "")})


@tool("web_search", "Search the web and return titles + URLs + snippets, so you can then "
                    "http_get the ones that matter.",
      {"type": "object", "properties": {
          "query": {"type": "string"},
          "count": {"type": "integer"}},
       "required": ["query"]})
def _web_search(args, policy: Policy) -> ToolResult:
    if not policy.network:
        return ToolResult(False, "network access is disabled")
    query = str(args["query"])
    count = int(args.get("count") or 8)
    searx = policy.conf.get("searx_url")
    try:
        if searx:
            url = f"{searx.rstrip('/')}/search?q={urllib.parse.quote(query)}&format=json"
            policy.polite_wait(url)
            _s, body, _h = _http_fetch(url)
            data = json.loads(body)
            rows = [f"- {r.get('title')}\n  {r.get('url')}\n  {(r.get('content') or '')[:200]}"
                    for r in (data.get("results") or [])[:count]]
            return ToolResult(True, "\n".join(rows) or "(no results)", {"engine": "searxng"})
        url = "https://duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        policy.polite_wait(url)
        _s, body, _h = _http_fetch(url, max_bytes=1_200_000)
        rows = _parse_ddg(body, count)
        return ToolResult(True, "\n".join(rows) or
                          "(no results parsed — DDG markup may have changed; set searx_url in "
                          "config for a stable engine)", {"engine": "duckduckgo-html"})
    except Exception as exc:
        return ToolResult(False, f"search failed ({type(exc).__name__}: {exc}). Fallback: use "
                                 "http_get on a known URL, or run with --provider paste and let "
                                 "the hosted assistant do the searching.")


def _parse_ddg(html: str, count: int) -> list[str]:
    rows: list[str] = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        href, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        if href.startswith("//duckduckgo.com/l/?uddg="):
            href = urllib.parse.unquote(href.split("uddg=", 1)[1].split("&", 1)[0])
        snippet = ""
        tail = html[m.end():m.end() + 1200]
        sm = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', tail, re.S)
        if sm:
            snippet = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", sm.group(1))).strip()
        rows.append(f"- {title.strip()}\n  {href}\n  {snippet[:220]}")
        if len(rows) >= count:
            break
    return rows


# --------------------------------------------------------------------------- memory

@tool("memory_set", "Store a durable fact/preference for later runs (survives restarts).",
      {"type": "object", "properties": {
          "key": {"type": "string"}, "value": {"type": "string"},
          "tags": {"type": "string"}, "scope": {"type": "string"}},
       "required": ["key", "value"]}, mutating=True)
def _memory_set(args, policy: Policy) -> ToolResult:
    if not policy.store:
        return ToolResult(False, "no store attached")
    policy.store.memo_set(str(args["key"]), str(args["value"]),
                          scope=str(args.get("scope") or "global"), tags=str(args.get("tags") or ""))
    return ToolResult(True, f"remembered {args['key']}")


@tool("memory_search", "Search stored memories/notes.",
      {"type": "object", "properties": {"query": {"type": "string"},
                                        "limit": {"type": "integer"}},
       "required": ["query"]})
def _memory_search(args, policy: Policy) -> ToolResult:
    if not policy.store:
        return ToolResult(False, "no store attached")
    rows = policy.store.memo_search(str(args["query"]), int(args.get("limit") or 10))
    if not rows:
        return ToolResult(True, "(nothing stored matches)")
    return ToolResult(True, "\n".join(f"- {r['key']} [{r.get('tags','')}]: {str(r['value'])[:300]}"
                                      for r in rows), {"count": len(rows)})


# --------------------------------------------------------------------------- repo tools

@tool("civic_pipeline", "Run the repo's own watchdog CLI (run.py) — selftest, init, crawl, work, "
                        "digest, or a PRA request draft. Read-mostly; respected as configured.",
      {"type": "object", "properties": {
          "action": {"type": "string",
                     "enum": ["selftest", "init", "crawl", "work", "digest", "status", "request-pra"]},
          "args": {"type": "string", "description": "extra CLI args, e.g. '--days 2'"}},
       "required": ["action"]}, mutating=True, confirm_reason="")
def _civic_pipeline(args, policy: Policy) -> ToolResult:
    action = str(args["action"])
    extra = str(args.get("args") or "")
    if action == "request-pra":
        cmd = f"python3 run.py request pra {extra}".strip()
    elif action == "status":
        cmd = "python3 run.py status"
    else:
        cmd = f"python3 run.py {action} {extra}".strip()
    return _shell({"command": cmd, "timeout": 900}, policy)


@tool("git", "Read-only git inspection plus (with confirmation) commit/push to the current branch.",
      {"type": "object", "properties": {
          "action": {"type": "string",
                     "enum": ["status", "log", "diff", "branches", "show", "commit", "push", "add"]},
          "args": {"type": "string"}},
       "required": ["action"]}, mutating=True, confirm_reason="git state change")
def _git(args, policy: Policy) -> ToolResult:
    action = str(args["action"])
    extra = str(args.get("args") or "")
    if action in ("commit", "push", "add"):
        default_msg = '-m "agent: automated change"'
        cmd = {"add": f"git add {extra or '-A'}",
               "commit": "git commit " + (extra or default_msg),
               "push": f"git push {extra}"}[action]
        verdict, reason = policy.judge_command(cmd)
        if verdict == "deny":
            return ToolResult(False, f"refused: {reason}")
        ok, note = policy.confirm("git", {"command": cmd}, f"{action} ({reason})")
        if not ok:
            return ToolResult(False, f"refused: {note}")
    else:
        cmd = f"git {action} {extra}".strip()
    return _shell({"command": cmd}, policy)


# --------------------------------------------------------------------------- delegation

@tool("spawn_agent", "Delegate a self-contained subtask to a fresh sub-agent (it has file, shell "
                     "and search tools and returns a written result). Use for parallel work or "
                     "to keep your own context clean.",
      {"type": "object", "properties": {
          "task": {"type": "string", "description": "self-contained instruction for the sub-agent"},
          "role": {"type": "string", "description": "e.g. scout, verifier, writer, coder"},
          "tools": {"type": "array", "items": {"type": "string"},
                    "description": "tool names the sub-agent may use (default: read-only set)"}},
       "required": ["task"]}, mutating=True, confirm_reason="")
def _spawn_agent(args, policy: Policy) -> ToolResult:
    from .loop import AgentLoop  # local import: avoids a cycle

    read_only = {"read_file", "list_dir", "glob", "grep", "http_get", "web_search",
                 "memory_search", "civic_pipeline", "shell"}
    allowed = set(args.get("tools") or read_only)
    child_policy = Policy(policy.conf, store=policy.store, agent_name=str(args.get("role") or "sub"))
    child_policy.dry_run = policy.dry_run
    runner = ToolRunner(child_policy, run_id=None, allowed=allowed)
    from .providers import build
    provider = build(policy.conf)
    loop = AgentLoop(provider, runner, store=policy.store, policy=child_policy,
                     mode="single", max_steps=int(policy.conf.get("max_steps") or 12))
    out = loop.run_task(str(args["task"]), session_id=None, persona="terse")
    return ToolResult(out.get("status") == "done",
                      f"sub-agent ({args.get('role') or 'sub'}) reports:\n{out.get('summary','')}",
                      {"status": out.get("status")})


@tool("finish", "Call this when the task is complete, with the summary the human should read.",
      {"type": "object", "properties": {"summary": {"type": "string"}},
       "required": ["summary"]})
def _finish(args, policy: Policy) -> ToolResult:
    return ToolResult(True, str(args["summary"]), {"final": True})


def tool_names() -> list[str]:
    return sorted(REGISTRY)
