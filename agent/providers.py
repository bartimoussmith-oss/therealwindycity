"""Model providers — one runtime, many brains, and never a dead end.

Two adapter shapes cover everything:

  NATIVE tool calling (the model emits structured tool calls):
    * anthropic      — api.anthropic.com/v1/messages
    * openai-compat  — any /chat/completions endpoint: OpenAI, OpenRouter,
                       Gemini's OpenAI shim, Groq, Together, vLLM, LM Studio,
                       llama.cpp server, and local Ollama (/v1)

  TEXT BRIDGE (the model is told a tiny tool protocol and writes JSON):
    * claude-cli     — the Claude Code CLI already installed on the device
    * paste          — you paste the prompt into Arena.ai Agent Mode (or any
                       chat UI) on any device, paste the reply back. This is
                       the no-API-key path, and it works today.
    * demo           — fully offline; exercises the loop, tools and UI with
                       zero credentials (also powers `agent selftest`).

Add a provider by registering a class in PROVIDERS. No other file changes.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from . import config as cfg

USER_AGENT = "windycity-agent/1.0 (+https://github.com/bartimoussmith-oss/therealwindycity)"
ANTHROPIC_VERSION = "2023-06-01"


# --------------------------------------------------------------------------- types

@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class Completion:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage_in: int = 0
    usage_out: int = 0
    model: str = ""
    stop_reason: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class ProviderError(RuntimeError):
    pass


class NotConfigured(ProviderError):
    """Raised when a provider needs a key/endpoint it does not have yet."""


# --------------------------------------------------------------------------- cost

# Rough public list prices, USD per 1M tokens (in, out). Estimate only — the
# invoice is the truth. Unknown models report cost 0 and are tagged "unknown".
PRICES = {
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-opus-4": (5.0, 25.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gpt-5": (2.5, 15.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gemini-2.5-pro": (1.25, 10.0),
    "gemini-2.5-flash": (0.3, 2.5),
}


def estimate_cost(model: str, tin: int, tout: int) -> tuple[float, bool]:
    m = (model or "").lower()
    for key, (pin, pout) in PRICES.items():
        if key in m:
            return (tin / 1_000_000 * pin) + (tout / 1_000_000 * pout), False
    return 0.0, True


# --------------------------------------------------------------------------- http

def http_json(url: str, payload: dict | None, headers: dict, timeout: int = 120,
              method: str = "POST", retries: int = 3) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    last: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=body, method=method)
        for k, v in headers.items():
            req.add_header(k, v)
        req.add_header("User-Agent", USER_AGENT)
        if body:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
            try:
                return json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ProviderError(f"non-JSON response from {url}: {raw[:300]}") from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:600]
            if exc.code in (408, 409, 429, 500, 502, 503, 504) and attempt < retries:
                wait = float(exc.headers.get("Retry-After") or (2 ** attempt))
                time.sleep(min(wait, 20))
                last = ProviderError(f"HTTP {exc.code}: {detail}")
                continue
            hint = ""
            if exc.code == 404 or "model" in detail.lower():
                hint = "  (wrong model name? run:  python3 -m agent models)"
            raise ProviderError(f"HTTP {exc.code} from {url}: {detail}{hint}") from exc
        except urllib.error.URLError as exc:
            if attempt < retries:
                time.sleep(2 ** attempt)
                last = ProviderError(f"network error: {exc.reason}")
                continue
            raise ProviderError(f"network error reaching {url}: {exc.reason}") from exc
    raise last or ProviderError("request failed")


# --------------------------------------------------------------------------- base

class Provider:
    id = "base"
    label = "Base"
    default_model = ""
    needs_key = True
    native_tools = True
    #: other provider ids this one can route to via a compatible endpoint
    aliases: tuple[str, ...] = ()

    def __init__(self, conf: cfg.Config, model: str | None = None, base_url: str | None = None):
        self.conf = conf
        self.model = model or conf.get("model") or self.default_model
        self.base_url = (base_url or conf.get("base_url") or self.default_base_url()).rstrip("/")
        self.key = conf.secret(self.id)

    def default_base_url(self) -> str:
        return ""

    def configured(self) -> bool:
        return bool(self.key) if self.needs_key else True

    def why_unavailable(self) -> str:
        env = cfg.SECRET_ENV.get(self.id, "API key")
        return f"no credential: set {env} or run  python3 -m agent key set {self.id}"

    def complete(self, messages: list[dict], tools: list[dict], system: str = "",
                 max_tokens: int = 4096, temperature: float = 0.2) -> Completion:
        raise NotImplementedError

    def list_models(self) -> list[str]:
        return [self.model] if self.model else []


# --------------------------------------------------------------------------- anthropic

class AnthropicProvider(Provider):
    id = "anthropic"
    label = "Anthropic (Claude API)"
    default_model = "claude-sonnet-5"

    def default_base_url(self) -> str:
        return "https://api.anthropic.com/v1"

    # -- conversion ---------------------------------------------------------
    @staticmethod
    def _to_anthropic(messages: list[dict]) -> list[dict]:
        out: list[dict] = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                continue
            if role == "tool":
                block = {"type": "tool_result", "tool_use_id": m.get("tool_call_id", ""),
                         "content": str(m.get("content", ""))[:100_000]}
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
                continue
            if role == "assistant":
                blocks: list[dict] = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for tc in m.get("tool_calls") or []:
                    blocks.append({"type": "tool_use", "id": tc["id"], "name": tc["name"],
                                   "input": tc.get("args") or {}})
                out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]})
                continue
            out.append({"role": "user", "content": m.get("content", "")})
        return out

    @staticmethod
    def _tools(tools: list[dict]) -> list[dict]:
        return [
            {"name": t["name"], "description": t.get("description", "")[:1024],
             "input_schema": t.get("parameters") or {"type": "object", "properties": {}}}
            for t in tools
        ]

    def complete(self, messages, tools, system="", max_tokens=4096, temperature=0.2) -> Completion:
        if not self.key:
            raise NotConfigured(self.why_unavailable())
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": self._to_anthropic(messages),
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = self._tools(tools)
        if temperature is not None:
            payload["temperature"] = temperature
        data = http_json(
            f"{self.base_url}/messages", payload,
            {"x-api-key": self.key, "anthropic-version": ANTHROPIC_VERSION},
        )
        text_parts, calls = [], []
        for block in data.get("content") or []:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                calls.append(ToolCall(id=block.get("id") or f"call_{len(calls)}",
                                      name=block.get("name", ""), args=block.get("input") or {}))
        usage = data.get("usage") or {}
        return Completion(text="\n".join(p for p in text_parts if p), tool_calls=calls,
                          usage_in=int(usage.get("input_tokens") or 0),
                          usage_out=int(usage.get("output_tokens") or 0),
                          model=data.get("model", self.model),
                          stop_reason=data.get("stop_reason", ""), raw=data)

    def list_models(self) -> list[str]:
        if not self.key:
            raise NotConfigured(self.why_unavailable())
        data = http_json(f"{self.base_url}/models", None,
                         {"x-api-key": self.key, "anthropic-version": ANTHROPIC_VERSION},
                         method="GET", retries=1)
        return [m.get("id", "") for m in data.get("data", []) if m.get("id")]


# --------------------------------------------------------------------------- openai-compat

class OpenAICompatProvider(Provider):
    id = "openai"
    label = "OpenAI-compatible /chat/completions"
    default_model = "gpt-5.4"
    default_base = "https://api.openai.com/v1"

    def default_base_url(self) -> str:
        return self.default_base

    @staticmethod
    def _tool_name(t: dict) -> str:
        return t["name"]

    @classmethod
    def _tools(cls, tools: list[dict]) -> list[dict]:
        return [{"type": "function",
                 "function": {"name": t["name"],
                              "description": t.get("description", "")[:1024],
                              "parameters": t.get("parameters") or
                                            {"type": "object", "properties": {}}}}
                for t in tools]

    def _headers(self) -> dict:
        headers = {}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        return headers

    def complete(self, messages, tools, system="", max_tokens=4096, temperature=0.2) -> Completion:
        if self.needs_key and not self.key:
            raise NotConfigured(self.why_unavailable())
        convo = list(messages)
        if system:
            convo = [{"role": "system", "content": system}] + convo
        payload = {"model": self.model, "messages": convo, "max_tokens": max_tokens}
        if temperature is not None:
            payload["temperature"] = temperature
        if tools:
            payload["tools"] = self._tools(tools)
            payload["tool_choice"] = "auto"
        data = http_json(f"{self.base_url}/chat/completions", payload, self._headers())
        err = data.get("error")
        if err:
            raise ProviderError(str(err)[:400])
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        calls = []
        for i, tc in enumerate(msg.get("tool_calls") or []):
            fn = tc.get("function") or {}
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args or "{}")
                except json.JSONDecodeError:
                    args = {"_raw": args}
            calls.append(ToolCall(id=tc.get("id") or f"call_{i}", name=fn.get("name", ""),
                                  args=args or {}))
        usage = data.get("usage") or {}
        return Completion(text=msg.get("content") or "", tool_calls=calls,
                          usage_in=int(usage.get("prompt_tokens") or 0),
                          usage_out=int(usage.get("completion_tokens") or 0),
                          model=data.get("model", self.model),
                          stop_reason=choice.get("finish_reason", ""), raw=data)

    def list_models(self) -> list[str]:
        data = http_json(f"{self.base_url}/models", None, self._headers(), method="GET", retries=1)
        items = data.get("data") or data.get("models") or []
        return [m.get("id") or m.get("name", "") for m in items if isinstance(m, dict)]


class OpenRouterProvider(OpenAICompatProvider):
    id = "openrouter"
    label = "OpenRouter (multi-model router)"
    default_model = "anthropic/claude-sonnet-5"
    default_base = "https://openrouter.ai/api/v1"

    def _headers(self) -> dict:
        h = super()._headers()
        h["HTTP-Referer"] = "https://github.com/bartimoussmith-oss/therealwindycity"
        h["X-Title"] = "windycity-agent"
        return h


class GeminiProvider(OpenAICompatProvider):
    id = "gemini"
    label = "Google Gemini (OpenAI-compat endpoint)"
    default_model = "gemini-2.5-pro"
    default_base = "https://generativelanguage.googleapis.com/v1beta/openai"


class GroqProvider(OpenAICompatProvider):
    id = "groq"
    label = "Groq (fast hosted inference)"
    default_model = "llama-3.3-70b-versatile"
    default_base = "https://api.groq.com/openai/v1"


class OllamaProvider(OpenAICompatProvider):
    """Local models. No key. Reads OLLAMA_HOST when set."""

    id = "ollama"
    label = "Ollama (local, offline)"
    default_model = "llama3.2"
    needs_key = False

    def default_base_url(self) -> str:
        host = os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
        if not host.startswith("http"):
            host = "http://" + host
        return host.rstrip("/") + "/v1"

    def why_unavailable(self) -> str:
        return ("Ollama not reachable at " + self.base_url +
                " — install it (termux: `pkg install ollama` or use the "
                "ollama-android app) and start it: `ollama serve`")

    def configured(self) -> bool:
        try:
            http_json(self.base_url.replace("/v1", "") + "/api/tags", None, {}, method="GET",
                      timeout=3, retries=0)
            return True
        except Exception:
            return False

    def local_models(self) -> list[str]:
        try:
            data = http_json(self.base_url.replace("/v1", "") + "/api/tags", None, {},
                             method="GET", timeout=5, retries=0)
            return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except Exception:
            return []

    def complete(self, messages, tools, system="", max_tokens=4096, temperature=0.2) -> Completion:
        model = self.model
        installed = self.local_models()
        if installed and model not in installed:
            # pick a sane installed model instead of failing the whole run
            pick = installed[0]
            self.model = pick
            model = pick
        return super().complete(messages, tools, system, max_tokens, temperature)


class CustomProvider(OpenAICompatProvider):
    """Any OpenAI-compatible server: llama.cpp, LM Studio, vLLM, a proxy, a
    corporate gateway, or an Arena endpoint if one is ever published."""

    id = "custom"
    label = "Custom OpenAI-compatible endpoint"
    default_model = "local-model"
    default_base = "http://127.0.0.1:1234/v1"
    needs_key = False  # llama.cpp / LM Studio / vLLM usually run unauthenticated

    def configured(self) -> bool:
        return bool(self.conf.custom_base_url())

    def why_unavailable(self) -> str:
        return ("no base_url set. Point it at any OpenAI-compatible server, e.g.\n"
                "  agent config set base_url http://127.0.0.1:1234/v1   # LM Studio\n"
                "  agent config set base_url http://192.168.1.20:8080/v1  # llama.cpp on another box")

    def default_base_url(self) -> str:
        return self.conf.custom_base_url() or self.default_base


class ArenaProvider(OpenAICompatProvider):
    """Adapter slot for an Arena.ai endpoint.

    Arena.ai Agent Mode is a hosted product with no public API as of 2026-09-12,
    so this provider is deliberately inert until a base URL + key exist (in
    which case it speaks the OpenAI-compatible protocol like anything else).
    Until then, use the `paste` bridge: it drives the local machine from
    Arena.ai on your phone with no key at all.
    """

    id = "arena"
    label = "Arena.ai (adapter slot — see docs)"

    def __init__(self, conf, model=None, base_url=None):
        super().__init__(conf, model=model, base_url=base_url)
        self.base_url = (self.conf.get("base_url") or "").rstrip("/")
        self.model = self.model or "arena-agent"

    def configured(self) -> bool:
        return bool(self.base_url)

    def why_unavailable(self) -> str:
        return ("Arena.ai publishes no self-serve API endpoint yet. Options:\n"
                "  1. paste bridge (works now, no key):  python3 -m agent run \"task\" --provider paste\n"
                "  2. if you are given an endpoint:      python3 -m agent config set base_url <url> "
                "--provider arena + python3 -m agent key set arena\n"
                "  3. for the site's own Agent Mode in a browser, use the PWA's 'handoff' button")


# --------------------------------------------------------------------------- text bridge

TOOL_PROTOCOL = """\
You are the reasoning half of a local tool-running agent. You cannot run commands
yourself; you reply with JSON so the runtime can run them for you.

Reply with EITHER a tool request:

```json
{"tool_calls": [{"name": "<tool>", "args": {...}}]}
```

OR a final answer for the human:

```json
{"final": "your answer in markdown"}
```

Rules: use only the tools listed below. One to four tool calls per reply.
Never invent tool output. When the task is complete, send the "final" form.
"""


class TextBridgeProvider(Provider):
    """Non-tool-calling models (CLI agents, any chat UI) driven by a JSON protocol."""

    id = "text-bridge"
    label = "Text bridge"
    native_tools = False
    needs_key = False

    def build_prompt(self, messages, tools, system) -> str:
        lines = [TOOL_PROTOCOL, "", "TOOLS:"]
        for t in tools:
            lines.append(f"- {t['name']}: {t.get('description','')}")
            lines.append(f"  args schema: {json.dumps(t.get('parameters') or {}, separators=(',', ':'))}")
        lines += ["", "TRANSCRIPT:"]
        for m in messages:
            role = m.get("role", "user").upper()
            if role == "TOOL":
                lines.append(f"TOOL RESULT ({m.get('tool_call_name','')}): {str(m.get('content',''))[:4000]}")
            elif role == "ASSISTANT":
                if m.get("tool_calls"):
                    lines.append("ASSISTANT TOOL CALL: " + json.dumps(
                        [{"name": c["name"], "args": c.get("args")} for c in m["tool_calls"]]))
                if m.get("content"):
                    lines.append(f"ASSISTANT: {m['content']}")
            elif role == "SYSTEM":
                continue
            else:
                lines.append(f"USER: {m.get('content','')}")
        if system:
            lines.insert(0, "SYSTEM:\n" + system + "\n")
        lines.append("")
        lines.append("YOUR REPLY (JSON only):")
        return "\n".join(lines)

    def _parse(self, text: str) -> Completion:
        calls: list[ToolCall] = []
        final = ""
        for blob in re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S):
            try:
                obj = json.loads(blob)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "tool_calls" in obj:
                for i, c in enumerate(obj["tool_calls"] or []):
                    calls.append(ToolCall(id=f"bridge_{int(time.time()*1000)}_{i}",
                                          name=c.get("name", ""), args=c.get("args") or {}))
            elif isinstance(obj, dict) and "final" in obj:
                final = str(obj["final"])
        if not calls and not final:
            # tolerate a bare JSON object without fences
            m = re.search(r'\{\s*"(?:tool_calls|final)".*\}', text, flags=re.S)
            if m:
                try:
                    obj = json.loads(m.group(0))
                    if "tool_calls" in obj:
                        for i, c in enumerate(obj["tool_calls"] or []):
                            calls.append(ToolCall(id=f"bridge_{int(time.time()*1000)}_{i}",
                                                  name=c.get("name", ""), args=c.get("args") or {}))
                    elif "final" in obj:
                        final = str(obj["final"])
                except json.JSONDecodeError:
                    pass
        if not calls and not final:
            final = text.strip()  # human-readable fallback; never lose the reply
        return Completion(text=final, tool_calls=calls, model=self.model, stop_reason="bridge")


class ClaudeCliProvider(TextBridgeProvider):
    """Drive the local Claude Code CLI (`claude -p`) as the brain."""

    id = "claude-cli"
    label = "Claude Code CLI (`claude -p`)"
    default_model = "claude-cli"

    def configured(self) -> bool:
        return bool(shutil.which("claude"))

    def why_unavailable(self) -> str:
        return ("`claude` CLI not on PATH — install it (npm i -g @anthropic-ai/claude-code, "
                "or the native installer), then `claude login` once")

    def complete(self, messages, tools, system="", max_tokens=4096, temperature=0.2) -> Completion:
        prompt = self.build_prompt(messages, tools, system)
        try:
            proc = subprocess.run(["claude", "-p", prompt], capture_output=True, text=True,
                                  timeout=int(self.conf.get("shell_timeout") or 300))
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProviderError(f"claude CLI failed: {exc}") from exc
        if proc.returncode != 0:
            raise ProviderError(f"claude CLI exit {proc.returncode}: {proc.stderr[:400]}")
        return self._parse(proc.stdout)


class PasteBridgeProvider(TextBridgeProvider):
    """Human-in-the-loop bridge: paste the prompt into Arena.ai / any chat, paste back.

    On a phone this is the whole game — no key, no server, but the local
    machine still executes real tools. `agent run ... --provider paste` prints
    the prompt and blocks on stdin; the web UI exposes the same as a
    two-textbox flow.
    """

    id = "paste"
    label = "Paste bridge (Arena.ai / any chat UI)"

    def __init__(self, conf, model=None, base_url=None, reader=None):
        super().__init__(conf, model=model or "human-in-the-loop")
        self.reader = reader or self._stdin_reader

    @staticmethod
    def _stdin_reader(prompt_text: str) -> str:
        print("\n" + "=" * 72)
        print("PASTE THIS INTO ARENA.AI (or any assistant), THEN PASTE THE REPLY BACK")
        print("=" * 72)
        print(prompt_text)
        print("=" * 72)
        print("Reply pasted below. End with a line containing only 'EOF', or Ctrl-D.\n")
        chunks = []
        try:
            while True:
                line = input()
                if line.strip() == "EOF":
                    break
                chunks.append(line)
        except EOFError:
            pass
        return "\n".join(chunks)

    @staticmethod
    def parse_reply(text: str) -> Completion:
        return PasteBridgeProvider(cfg.Config())._parse(text)

    def complete(self, messages, tools, system="", max_tokens=4096, temperature=0.2) -> Completion:
        prompt = self.build_prompt(messages, tools, system)
        reply = self.reader(prompt)
        return self._parse(reply)


class DemoProvider(Provider):
    """Offline, deterministic, credential-free. Drives the real tools.

    It is intentionally simple: it inspects the conversation, requests one or
    two real tool calls relevant to the task, then summarizes what the tools
    returned. Enough to prove the whole pipeline (loop -> tools -> store -> UI)
    works on a device with no model, no key and no network.
    """

    id = "demo"
    label = "Offline demo (no model, real tools)"
    default_model = "offline-heuristics"
    needs_key = False

    def complete(self, messages, tools, system="", max_tokens=4096, temperature=0.2) -> Completion:
        names = {t["name"] for t in tools}
        results = [m for m in messages if m.get("role") == "tool"]
        task = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                task = m.get("content", "")
                break
        lower = task.lower()

        if not results:
            calls: list[ToolCall] = []
            if "shell" in names and ("git" in lower or "run " in lower or "install" in lower):
                calls.append(ToolCall("demo_1", "shell", {"command": "git status --short --branch"}))
            if "list_dir" in names:
                from pathlib import Path as _Path
                root = cfg.Config().workspace
                target = "."
                for token in re.findall(r"[\w./-]{3,}", task):
                    if token.startswith(("./", "/", "agent", "engine", "pipeline", "data")):
                        if (_Path(token).is_absolute() or (root / token).exists()):
                            target = token
                            break
                calls.append(ToolCall("demo_2", "list_dir", {"path": target}))
            if calls:
                return Completion(text="Offline demo: probing the workspace with real tools.",
                                  tool_calls=calls, model=self.model, stop_reason="tool_use")
            return Completion(
                text=("Offline demo mode — no model is configured, so I can only show tool "
                      "plumbing.\n\n" + self._how_to_configure()), model=self.model,
                stop_reason="end_turn")

        summary = [f"**Offline demo run** — task: {task.strip()[:200]}", ""]
        summary.append("Tool calls executed against the real machine:")
        for m in results:
            out = str(m.get("content", ""))
            summary.append(f"\n- `{m.get('tool_call_name', 'tool')}` →\n```\n{out[:1200]}\n```")
        summary.append("\n" + self._how_to_configure())
        return Completion(text="\n".join(summary), model=self.model, stop_reason="end_turn")

    @staticmethod
    def _how_to_configure() -> str:
        return (
            "---\n**Wire a real brain** (any one of these, no code changes):\n"
            "- `python3 -m agent key set anthropic` then `agent config set provider anthropic`\n"
            "- `python3 -m agent key set openai` / `openrouter` / `gemini` / `groq`\n"
            "- Local + offline: install Ollama, `ollama pull qwen2.5:3b`, then "
            "`agent config set provider ollama`\n"
            "- No key at all: `python3 -m agent run \"task\" --provider paste` "
            "(paste into Arena.ai on your phone)\n"
            "- Claude Code installed? `agent config set provider claude-cli`"
        )


# --------------------------------------------------------------------------- registry

PROVIDERS: dict[str, type[Provider]] = {
    p.id: p for p in (
        AnthropicProvider, OpenAICompatProvider, OpenRouterProvider, GeminiProvider,
        GroqProvider, OllamaProvider, CustomProvider, ArenaProvider,
        ClaudeCliProvider, PasteBridgeProvider, DemoProvider,
    )
}


def available(conf: cfg.Config) -> list[tuple[str, bool, str]]:
    """[(id, usable, reason)] for the doctor command and the web UI."""
    out = []
    for pid in cfg.PROVIDER_PROBE:
        cls = PROVIDERS.get(pid)
        if not cls:
            continue
        try:
            inst = cls(conf)
            ok = inst.configured()
            reason = "" if ok else inst.why_unavailable()
        except Exception as exc:  # never let detection crash the CLI
            ok, reason = False, f"{type(exc).__name__}: {exc}"
        out.append((pid, ok, reason))
    return out


def build(conf: cfg.Config, provider: str | None = None, model: str | None = None,
          base_url: str | None = None) -> Provider:
    """Resolve a provider id (or 'auto') into a ready instance."""
    pid = provider or conf.get("provider") or "auto"
    if pid == "auto":
        for candidate, ok, _reason in available(conf):
            if ok:
                pid = candidate
                break
        else:
            pid = "demo"
    cls = PROVIDERS.get(pid)
    if cls is None:
        raise ProviderError(
            f"unknown provider {pid!r}. Known: {', '.join(sorted(PROVIDERS))}")
    if pid == "ollama":
        return cls(conf, model=model, base_url=base_url)
    return cls(conf, model=model, base_url=base_url)


def resolve_auto(conf: cfg.Config) -> tuple[str, str]:
    """Return (provider_id, model) that `auto` would pick, without instantiating twice."""
    for candidate, ok, _reason in available(conf):
        if ok:
            return candidate, (conf.get("model") or PROVIDERS[candidate].default_model)
    return "demo", "offline-heuristics"
