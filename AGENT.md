# The local agent runtime — `agent/`

**One runtime. Every device you own. No dead ends.**

`agent/` is a multi-agent runtime that lives on hardware you control: it plans, runs real tools
(shell, files, search, git, the civic pipeline), verifies its own work with a second agent, and
reports with evidence. It installs on an Android phone (Termux), a Chromebook, Windows, Linux,
macOS or a VPS — and when a device can't do something, there is a documented path that still works.

```bash
python3 -m agent doctor        # what works on THIS device + the workaround for what doesn't
python3 -m agent serve         # installable web console (phone / Chromebook / tablet)
python3 -m agent run "task"    # one-shot task
python3 -m agent selftest      # offline proof: no keys, no network, real tools
```

> **The repo's rules apply to the agent too.** It respects `READ-FIRST.md`: nothing it does
> rewrites history, force-pushes, or deletes work it didn't create; `streamlit_app.py` and
> `Transparency_Index_App.py` stay twins; robots.txt is honored; credentials never touch the repo;
> and "if it isn't quotable, it isn't asserted" is baked into the verifier step.

---

## 1. Straight answer about Arena.ai Agent Mode

You asked to wire **Arena.ai Agent Mode** in as the brain. Verified 2026-09-12: Arena.ai publishes
no public or self-hostable API — Agent Mode is a hosted product you use at `arena.ai/agent`
([arena.ai/blog/agent-mode](https://arena.ai/blog/agent-mode)). A search for an "arena.ai API"
turns up unrelated projects, so there is nothing honest to wire *to* yet.

Rather than leave you blocked, this runtime ships **three** ways to get the same outcome:

| Path | What it does | You need |
|---|---|---|
| **Paste bridge** — `--provider paste` | The runtime writes a self-contained prompt (task + tools + transcripts). You paste it into Arena.ai Agent Mode on your phone, paste its reply back; **your local machine executes the real tools.** | Nothing. Works today. |
| **Adapter slot** — `--provider arena` | If Arena ever ships an endpoint, `agent config set base_url <url>` + `agent key set arena` and it speaks OpenAI-compatible protocol immediately. No code change. | A future endpoint |
| **Any other brain** | Anthropic / OpenAI / OpenRouter / Gemini / Groq / a local Ollama / the Claude CLI / any OpenAI-compatible server (LM Studio, llama.cpp, vLLM, a homelab box). | A key, or a local model |

The paste bridge is the closest thing to "use Agent Mode, but let it act on my machine" that exists
without an official API — the reasoning happens in the browser, the *doing* happens on your hardware.
It is also the fallback when a phone is offline, a key expires, or a network blocks the API.

---

## 2. Install — per device

### Android (Moto Edge 5G UW) — Termux, the full runtime on the phone

```bash
# F-Droid Termux (Play Store builds are stale)
pkg update && pkg install -y python git
git clone https://github.com/bartimoussmith-oss/therealwindycity ~/therealwindycity
bash ~/therealwindycity/agent/install/termux.sh
wyagent doctor
wyagent serve --port 8765          # then open http://<phone-ip>:8765 in Chrome → Install app
```
Phone-specific workarounds are printed by `doctor`. The three that matter:
`termux-wake-lock` + unrestricted battery for long runs · keep the repo in Termux's home (or run
`termux-setup-storage` once) · a phone has no big model — point it at your PC
(`agent config set base_url http://<pc-ip>:11434/v1`, `provider ollama`) or use `--provider paste`.

### Windows — native, no admin, no WSL required

```powershell
winget install Python.Python.3.12 Git.Git
cd C:\path\to\therealwindycity
powershell -ExecutionPolicy Bypass -File agent\install\windows.ps1
wyagent doctor
wyagent serve --port 8765          # allow Python through the firewall once
```

### Chromebook — client today, host if you have Linux

A Chromebook needs **nothing installed** to *use* this: run the runtime on your phone or PC, open
its LAN URL in Chrome, and choose **Install app** from the omnibox/cast menu. It becomes an
installed PWA in your shelf. Full matrix (including the "Linux dev environment is gone" case) is in
[`agent/install/chromebook.md`](agent/install/chromebook.md).

```bash
# if your Chromebook does have the Linux (Crostini) terminal:
bash agent/install/linux.sh && wyagent serve
```

### Linux / macOS / VPS

```bash
bash agent/install/linux.sh      # add WY_SERVICE=1 for a systemd --user service
bash agent/install/macos.sh      # add WY_LAUNCHD=1 for a launchd agent
```

### Reach it from anywhere (no port-forwarding)

```bash
curl -fsSL https://tailscale.com/install.sh | sh    # on the host
# install Tailscale on the phone/Chromebook, then use the host's Tailscale IP in the URL
```

---

## 3. Commands

| Command | Purpose |
|---|---|
| `agent doctor` | Probe the device: python, git, tools, every provider, and the workaround for each missing piece |
| `agent serve [--port 8765] [--token X]` | The console: PWA + JSON API + live event stream (SSE) |
| `agent run "task" [--mode single\|plan\|swarm]` | One task, start to finish |
| `agent chat` | Interactive session (`/mode swarm`, `/provider ollama`, `/new`) |
| `agent selftest` | Offline end-to-end proof — no keys, no network |
| `agent key set <provider>` | Store a key in `~/.windycity-agent/secrets.json` (0600) — never in the repo |
| `agent models` | Ask the active provider which models your key can actually use |
| `agent config set <key> <value>` | Non-secret settings (refuses anything that looks like a credential) |
| `agent pair --name phone` | Mint a device token + print the URLs to open on that device |
| `agent sessions` / `show <id>` | Replay what happened, message by message |
| `agent audit [--run r_…]` | Every tool call: verdict, duration, result hash |
| `agent memory` | Durable notes the agent reuses across runs |
| `agent export` / `agent import <file>` | Move the whole setup to a new device (secrets excluded by default) |
| `agent install [termux\|windows\|linux\|chromebook\|macos]` | Print/point at the right bootstrap |
| `agent prune` | Clear swarm worktrees and spilled output |

Global flags (`--provider`, `--model`, `--mode`, `--persona`, `--workspace`, `--dry-run`, `--yes`,
`--json`, `--quiet`) work **before or after** the subcommand.

---

## 4. Multi-agent modes

```bash
agent run "summarize the last 10 commits and check for secret leaks" --mode single
agent run "inventory the repo and write AGENT-INVENTORY.md"           --mode plan
agent run "audit the uploads/ corpus for watchlist terms"             --mode swarm
```

* **single** — one agent, your tools, tool-call loop until done.
* **plan** — a planner decomposes the request, one worker executes it.
* **swarm** — planner → N workers **in parallel** → a separate **verifier** that re-checks every
  claim with tools (reads the file, runs the command, fetches the URL) → one synthesizer that
  writes the report from verified material only.

Safety properties that make swarm mode safe to leave running:

* workers get **isolated git worktrees**, created **detached** (`git worktree add --detach`) — no
  branches are invented in your repo, and they live in `~/.windycity-agent/worktrees/<run>/`;
* **nothing is auto-applied** to your working tree: you get the diff plus the exact `git apply`
  command;
* each worker only ever sees its own subtask, and its tool allow-list is intersected with the real
  tool registry, so a hallucinated tool name in a plan cannot widen access;
* token/cost accounting per run, with an optional `budget_usd_per_run` ceiling.

---

## 5. Tools (15, all audited)

`read_file` · `write_file` · `edit_file` · `list_dir` · `glob` · `grep` · `shell` · `http_get`
(polite: robots.txt + per-host delay) · `web_search` (DuckDuckGo HTML, or your SearxNG via
`searx_url`) · `memory_set` · `memory_search` · `civic_pipeline` (drives `run.py`:
selftest/init/crawl/work/digest/request-pra) · `git` · `spawn_agent` (nested sub-agent) · `finish`.

Big outputs spill to `~/.windycity-agent/spill/` and the model gets the head, the tail, and the path.

**Three verdicts on every mutating call**

| Verdict | Examples | Behaviour |
|---|---|---|
| `deny` | `rm -rf /`, `mkfs`, fork bombs, `git push --force`, history rewrite, shutdown | Refused outright. Hard rule, not a suggestion. |
| `confirm` | `sudo`, package installs, `rm -rf <dir>`, `git push`, `curl … \| sh`, service changes | Needs a human yes — from the terminal prompt, or an **Approve / Deny card in the phone UI**. |
| `allow` | everything else, incl. writes inside the workspace jail | Runs, and is logged. |

Paths are jailed to the workspace (plus the agent's own state dir) unless you set
`allow_outside_workspace: true`. `--dry-run` answers every mutating call with what it *would* do.
`agent audit` shows the whole trail with result hashes.

---

## 6. The phone/Chromebook console

`agent serve` gives you an installable PWA (no build step, no node, no CDN — one HTML file served by
the stdlib):

* **transcript** with collapsible tool cards (tap to see the actual output);
* **live stream** over SSE — steps, tool calls, swarm workers appear as they happen;
* **Approve/Deny cards** when a tool needs a human decision;
* **Paste-bridge cards**: copy the prompt, open Arena.ai, paste the reply straight back;
* sessions drawer, audit view, memory, settings, and *"show me URLs for my other devices"*;
* service worker so the shell opens offline (live data always hits the server).

Security: binds `0.0.0.0` so your other devices can reach it. With no token it's open **on your
network** — that's fine at home, not on public Wi-Fi. `agent pair --name phone` mints a device token
(stored hashed), and loopback is always trusted so the host can't lock itself out.

---

## 7. Bringing a brain

```bash
agent key set anthropic            # cloud, strongest tool use
agent key set openai               # or openrouter / gemini / groq
agent config set provider ollama   # local + offline (install Ollama, ollama pull qwen2.5:3b)
agent config set provider claude-cli
agent config set base_url http://192.168.1.20:1234/v1 && agent config set provider custom
agent run "task" --provider paste  # no key at all
agent models                       # verify what your key/endpoint actually serves
```
No key anywhere? `auto` falls back to **demo**: the full pipeline with real tools and an offline
"brain" that shows exactly how to wire a real one. `/api/health` tells the UI which mode it's in.

Cost estimates use a small built-in price table and are labelled `cost_unknown` when the model isn't
in it — treat them as estimates, the invoice is the truth.

---

## 8. Every constraint has a workaround

`agent doctor` prints this table for your actual device. The short version:

| Constraint | Workaround |
|---|---|
| No API key | `--provider paste` (Arena.ai in the browser drives your machine) or `--provider claude-cli` |
| No GPU / weak CPU | Point `base_url` at any OpenAI-compatible host — LM Studio, llama.cpp, vLLM, a homelab box, a friend's server |
| Phone storage / thermals | Run the runtime on the PC, use the phone as a PWA client over Wi-Fi or Tailscale |
| Chromebook without Linux | Use the PC/phone host + install the PWA; or Termux on the phone. Nothing here needs Crostini |
| No always-on machine | The whole thing is a folder + a config: `agent export` / `agent import`, or run it from a USB stick |
| Locked-down work Windows | No admin needed: user-scope Python, `py -m agent serve`, allow Python in the firewall once |
| Corporate proxy / fully offline | `network: false` keeps every tool local; a local Ollama model makes the whole loop offline |
| Old Python? | Needs 3.9+ only; no wheels, no pip, no node, no Docker — stdlib only, by design |

---

## 9. Where your data lives

| Path | Contents |
|---|---|
| `<repo>/agent/` | The runtime (code only, no secrets, no state) |
| `~/.windycity-agent/agent.db` | Sessions, messages, runs, swarm tasks, memory, audit trail, paired devices |
| `~/.windycity-agent/secrets.json` | Provider keys (0600) — **never** in the repo |
| `~/.windycity-agent/config.json` | Your non-secret settings |
| `~/.windycity-agent/worktrees/`, `spill/` | Swarm worktrees and big tool outputs (`agent prune` clears them) |

Override the state dir with `WY_AGENT_HOME=/media/usb/wy` to carry the whole agent on a stick.
Nothing here reads or writes `.env`, and `agent config set` refuses keys that look like credentials.

---

## 10. Verified, and not (this repo's integrity rule)

**Verified in this session** (offline, no credentials):
`python3 -m unittest discover -s agent/tests` → **48 tests pass**; `agent selftest` → ALL PASS;
`agent doctor`, `providers`, `models`, `sessions`, `audit`, `pair`, `export/import` exercised;
single/plan/swarm runs and the paste bridge executed **real tool calls** end to end; the console
served its PWA and streamed a live run over HTTP/SSE; worktree isolation proved to leave the source
tree untouched and to invent no branches; the path jail, deny-list and dry-run behaved.

**Not verified here** (needs your hardware — run `agent doctor` and `agent selftest` on each):
Termux package names/versions on your specific Moto, the Windows firewall prompt flow, Crostini
availability on your Chromebook, and any provider call that needs a real key. Those are exactly the
things `doctor` is built to tell you honestly.

**Deliberately not done:** no Arena.ai API client (there is no API to call — see §1); no secrets on
disk beyond `~/.windycity-agent/secrets.json`; nothing in the existing app, engine, data or
pipeline directories was modified by this addition.
