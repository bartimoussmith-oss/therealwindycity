"""Layered configuration for the portable agent runtime.

Resolution order (later wins):
    built-in defaults -> <repo>/agent.config.json -> ~/.windycity-agent/config.json
    -> environment variables -> explicit overrides (CLI flags)

SECRETS ARE NEVER READ FROM, OR WRITTEN TO, THE REPOSITORY.
API keys live in ~/.windycity-agent/secrets.json (chmod 600) or in the
environment. `agent key set ...` is the only writer of that file.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

# --------------------------------------------------------------------------- paths

PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parent


def home_dir() -> Path:
    """Private state dir. Override with WY_AGENT_HOME for portable USB installs."""
    raw = os.environ.get("WY_AGENT_HOME")
    p = Path(raw).expanduser() if raw else Path.home() / ".windycity-agent"
    return p


def secrets_path() -> Path:
    return home_dir() / "secrets.json"


def config_path() -> Path:
    return home_dir() / "config.json"


def state_path() -> Path:
    return home_dir() / "agent.db"


# --------------------------------------------------------------------------- defaults

DEFAULT_CONFIG: dict = {
    # Where the agent is allowed to act. "repo" = the checkout this package lives in.
    "workspace": "repo",
    # Which provider drives reasoning. "auto" probes in the order in PROVIDER_PROBE.
    "provider": "auto",
    "model": None,          # provider default when null
    "base_url": None,       # for self-hosted / OpenAI-compatible endpoints
    # single = one agent; plan = planner then one worker; swarm = planner + N workers + verifier
    "mode": "single",
    "max_steps": 24,        # tool-call rounds per agent run
    "max_workers": 4,       # swarm width
    "shell_timeout": 120,   # seconds
    "allow_outside_workspace": False,
    "dry_run": False,       # refuse mutating tool calls, print what would happen
    "require_confirm": False,  # ask before every mutating tool call (TUI/server)
    "network": True,        # allow outbound http(s) from tools
    "polite_delay": 3.0,    # seconds between hits to the same host (repo LEGAL.md rule)
    "budget_usd_per_run": None,
    "server": {"host": "0.0.0.0", "port": 8765, "token": None, "open_pairing": True},
    "tools": {"disabled": []},
    "persona": "operator",  # operator | civic | terse
    "issue_worktrees": True,  # swarm workers get isolated git worktrees when possible
}

# Order matters: `auto` picks the first usable entry. Cloud keys first, then local models,
# then the CLI bridge, then the offline demo; `paste` is opt-in via --provider paste
# because it waits on a human.
PROVIDER_PROBE = ["anthropic", "openai", "openrouter", "gemini", "groq", "arena", "ollama",
                  "claude-cli", "custom", "demo", "paste"]

ENV_MAP = {
    "WY_AGENT_PROVIDER": "provider",
    "WY_AGENT_MODEL": "model",
    "WY_AGENT_BASE_URL": "base_url",
    "WY_AGENT_MODE": "mode",
    "WY_AGENT_WORKSPACE": "workspace",
    "WY_AGENT_MAX_STEPS": "max_steps",
    "WY_AGENT_SHELL_TIMEOUT": "shell_timeout",
    "WY_AGENT_DRY_RUN": "dry_run",
    "WY_AGENT_PERSONA": "persona",
}

# env var -> provider id in the secrets file
SECRET_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "arena": "ARENA_API_KEY",
    "custom": "WY_AGENT_API_KEY",
}

# Names that look like credentials. Used to refuse writing them to repo config.
_SECRETISH = ("key", "token", "secret", "password", "passwd", "credential")


def looks_secret(key: str) -> bool:
    k = key.lower()
    return any(s in k for s in _SECRETISH)


# --------------------------------------------------------------------------- load

def _read_json(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError):
        return {}


def _coerce(value: str):
    low = value.strip().lower()
    if low in ("true", "yes", "on", "1"):
        return True
    if low in ("false", "no", "off", "0"):
        return False
    if low in ("none", "null", ""):
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


class Config:
    """Merged, read-mostly configuration object."""

    def __init__(self, overrides: dict | None = None, repo_config: bool = True,
                 base: dict | None = None):
        self.sources: list[str] = []
        data = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy

        if base:  # layer on a parent config (e.g. the running server's settings)
            _deep_merge(data, json.loads(json.dumps(base)))
            self.sources.append("parent")

        for path, label in (
            (REPO_ROOT / "agent.config.json", "repo") if repo_config else (None, None),
            (config_path(), "home"),
        ):
            if path is None:
                continue
            loaded = _read_json(path)
            if loaded:
                _deep_merge(data, loaded)
                self.sources.append(f"{label}:{path}")

        for env, key in ENV_MAP.items():
            if env in os.environ:
                data[key] = _coerce(os.environ[env])
                self.sources.append(f"env:{env}")

        if overrides:
            _deep_merge(data, {k: v for k, v in overrides.items() if v is not None})
            self.sources.append("cli")

        self.data = data

    # -- access -------------------------------------------------------------
    def get(self, key, default=None):
        return self.data.get(key, default)

    def __getitem__(self, key):
        return self.data[key]

    # -- paths --------------------------------------------------------------
    @property
    def workspace(self) -> Path:
        raw = str(self.data.get("workspace") or "repo")
        if raw in ("repo", "", "auto"):
            return REPO_ROOT
        return Path(raw).expanduser().resolve()

    @property
    def dry_run(self) -> bool:
        return bool(self.data.get("dry_run"))

    @property
    def server_cfg(self) -> dict:
        return dict(self.data.get("server") or {})

    # -- secrets ------------------------------------------------------------
    def secret(self, provider: str) -> str | None:
        """Env first (never persisted), then the 0600 secrets file."""
        env = SECRET_ENV.get(provider)
        if env and os.environ.get(env):
            return os.environ[env]
        return _read_json(secrets_path()).get(provider) or None

    def custom_base_url(self) -> str | None:
        return self.data.get("base_url") or os.environ.get("WY_AGENT_BASE_URL")


def _deep_merge(base: dict, incoming: dict) -> dict:
    for k, v in incoming.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


# --------------------------------------------------------------------------- write

def save_config(updates: dict, scope: str = "home") -> Path:
    """Persist non-secret settings. Refuses anything that looks like a credential."""
    for k in updates:
        if looks_secret(k):
            raise ValueError(
                f"refusing to write {k!r} to a config file — use `agent key set` "
                "so it lands in the private secrets file instead"
            )
    target = REPO_ROOT / "agent.config.json" if scope == "repo" else config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    current = _read_json(target)
    _deep_merge(current, updates)
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(current, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return target


def save_secret(provider: str, value: str) -> Path:
    """Write a provider key to ~/.windycity-agent/secrets.json with 0600 perms."""
    path = secrets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, stat.S_IRWXU)  # 0700 on the state dir
    except OSError:
        pass
    data = _read_json(path)
    data[provider] = value.strip()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass
    return path
