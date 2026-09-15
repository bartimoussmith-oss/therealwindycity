"""The agent loop: model -> tool calls -> results -> model, until done.

One loop, every mode:
  * single   — one agent, your tools
  * spawn    — the loop can call `spawn_agent` to fan work into sub-agents
  * swarm    — orchestrator.py drives several of these in parallel

Everything is observable: each step emits an event (for SSE to the phone),
lands in SQLite, and is audited. Cancellation is cooperative via a
threading.Event, so `Stop` in the UI actually stops the run.
"""
from __future__ import annotations

import json
import platform
import threading
import time
from dataclasses import dataclass, field

from . import config as cfg
from .providers import Completion, Provider, ProviderError, estimate_cost
from .tools import Policy, ToolRunner

# --------------------------------------------------------------------------- events

@dataclass
class Events:
    """Tiny pub/sub. Subscribers are callables taking a dict."""
    subscribers: list = field(default_factory=list)

    def subscribe(self, fn):
        self.subscribers.append(fn)
        return fn

    def emit(self, kind: str, **payload):
        evt = {"kind": kind, "ts": time.time(), **payload}
        for fn in list(self.subscribers):
            try:
                fn(evt)
            except Exception:
                pass


# --------------------------------------------------------------------------- prompts

PERSONAS = {
    "operator": (
        "You are the local agent for this machine — the same style of agent as a hosted "
        "'agent mode', but running on the owner's own hardware with real tools.\n"
        "Work like a careful senior engineer:\n"
        "- Act, don't narrate. Use tools; don't guess at file contents, exits, or versions.\n"
        "- Read before you write. Verify before you claim. If a step failed, say so plainly and "
        "report the exact error.\n"
        "- Prefer small, reversible steps. Never delete or rewrite work you did not create.\n"
        "- Report what you did with concrete evidence: paths, commands, output snippets.\n"
        "- If something is genuinely blocked, name the block and the workaround you tried."
    ),
    "civic": (
        "You are the local agent for the Cheyenne/Laramie County civic-transparency workspace.\n"
        "House rules you must follow (they come from the repo's READ-FIRST.md and LEGAL.md):\n"
        "- Additive only: never delete or rewrite content you did not create; never force-push.\n"
        "- `streamlit_app.py` and `Transparency_Index_App.py` are twins: change both or neither.\n"
        "- Public documents only; robots.txt is honored; drafts are for a human to send.\n"
        "- Integrity rule: if it isn't quotable, it isn't asserted. Alerts carry a verbatim quote, "
        "a source URL and a fetch timestamp; legacy data stays 'leads, not facts' until verified.\n"
        "- Credentials never go in files, commits, or chat. They live in env or ~/.windycity-agent.\n"
        "- Before touching engine/, data/, .github/, requirements.txt or the twins, check "
        "READ-FIRST.md for an active claim and respect it.\n"
        "Work like a careful archivist-engineer: act, verify, cite paths, report honestly."
    ),
    "terse": (
        "You are a focused sub-agent. Do exactly the assigned subtask with tools, then report "
        "the result in at most 120 words. Include file paths and exact commands you ran. "
        "No preamble, no speculation, no filler."
    ),
}


def build_system_prompt(policy: Policy, persona: str = "operator", extra: str = "",
                        memory: list[dict] | None = None) -> str:
    base = PERSONAS.get(persona, PERSONAS["operator"])
    ws = policy.workspace
    lines = [
        base, "",
        "ENVIRONMENT",
        f"- workspace root: {ws}",
        f"- agent state dir: {cfg.home_dir()}",
        f"- platform: {platform.system()} {platform.release()} ({platform.machine()}), "
        f"python {platform.python_version()}",
        f"- today: {time.strftime('%Y-%m-%d')}",
        f"- mode: dry_run={policy.dry_run}, network={policy.network}, "
        f"path jail={'workspace+state' if not policy.allow_outside else 'unrestricted'}",
        "",
        "HOW TO WORK",
        "- Use the file tools to read before editing; use shell for builds, git and programs.",
        "- Long outputs spill to files — read the spill path if you need the middle of one.",
        "- When you have finished, reply with the human-facing summary as normal text "
        "(no tool call). Keep it short: what changed, what you verified, what is left.",
    ]
    if memory:
        lines += ["", "REMEMBERED CONTEXT (from earlier runs)"]
        for m in memory[:8]:
            lines.append(f"- {m.get('key')}: {str(m.get('value'))[:300]}")
    if extra:
        lines += ["", extra]
    return "\n".join(lines)


# --------------------------------------------------------------------------- loop

class AgentLoop:
    def __init__(self, provider: Provider, runner: ToolRunner, store=None, policy: Policy | None = None,
                 mode: str = "single", max_steps: int = 24, events: Events | None = None,
                 cancel: threading.Event | None = None, agent_name: str = "main",
                 use_finish_tool: bool = False):
        self.provider = provider
        self.runner = runner
        self.store = store
        self.policy = policy or runner.policy
        self.mode = mode
        self.max_steps = max_steps
        self.events = events or Events()
        self.cancel = cancel or threading.Event()
        self.agent_name = agent_name
        self.use_finish_tool = use_finish_tool

    # -- helpers ------------------------------------------------------------
    def _history(self, session_id: str | None, limit: int = 40) -> list[dict]:
        if not (self.store and session_id):
            return []
        rows = self.store.get_messages(session_id, limit=200)
        out: list[dict] = []
        for r in rows[-limit:]:
            role = r["role"]
            if role in ("system", "note"):
                continue
            if role == "tool":
                out.append({"role": "tool", "content": (r["tool_result"] or "")[:4000],
                            "tool_call_id": r.get("tool_args") and "" or "",
                            "tool_call_name": r.get("tool_name") or ""})
                continue
            msg = {"role": role, "content": r["content"] or ""}
            if role == "assistant" and r.get("tool_name"):
                # stored as a tool-call row
                try:
                    args = json.loads(r["tool_args"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                msg = {"role": "assistant", "content": r["content"] or "",
                       "tool_calls": [{"id": f"hist_{r['id']}", "name": r["tool_name"], "args": args}]}
            out.append(msg)
        return out

    def _memory_for(self, task: str) -> list[dict]:
        if not self.store:
            return []
        words = [w for w in task.split() if len(w) > 4][:4]
        found: list[dict] = []
        for w in words:
            try:
                found.extend(self.store.memo_search(w, limit=3))
            except Exception:
                pass
        seen, uniq = set(), []
        for m in found:
            if m["key"] not in seen:
                seen.add(m["key"])
                uniq.append(m)
        return uniq

    # -- main ---------------------------------------------------------------
    def run_task(self, task: str, session_id: str | None = None, persona: str = "operator",
                 extra_system: str = "", run_id: str | None = None) -> dict:
        t0 = time.time()
        ws = str(self.policy.workspace)
        if session_id is None and self.store:
            session_id = self.store.create_session(title=task[:80], mode=self.mode,
                                                   provider=self.provider.id,
                                                   model=self.provider.model, workspace=ws)
        if run_id is None and self.store:
            run_id = self.store.start_run(session_id, task, self.mode, self.provider.id,
                                          self.provider.model)
        if self.store and session_id:
            self.store.add_message(session_id, run_id, "user", task)
            if self.store.get_session(session_id) and task.strip():
                self.store.rename_session(session_id, task[:80])

        system = build_system_prompt(self.policy, persona, extra_system, self._memory_for(task))
        messages = self._history(session_id)
        if not messages or messages[-1].get("content") != task:
            messages.append({"role": "user", "content": task})

        tools = self.runner.available()
        if not self.use_finish_tool:
            tools = [t for t in tools if t["name"] != "finish"]

        self.events.emit("run_start", run_id=run_id, session_id=session_id, task=task,
                         provider=self.provider.id, model=self.provider.model, mode=self.mode)

        steps = 0
        tin = tout = 0
        cost = 0.0
        unknown_price = False
        final_text = ""
        status = "done"
        error = ""

        try:
            while steps < self.max_steps:
                if self.cancel.is_set():
                    status = "stopped"
                    final_text = final_text or "Stopped by the owner."
                    break
                steps += 1
                self.events.emit("step", run_id=run_id, step=steps, max_steps=self.max_steps,
                                 agent=self.agent_name)
                completion: Completion = self.provider.complete(messages, tools, system=system)
                tin += completion.usage_in
                tout += completion.usage_out
                c, unknown = estimate_cost(completion.model or self.provider.model,
                                           completion.usage_in, completion.usage_out)
                cost += c
                unknown_price = unknown_price or unknown

                if completion.text:
                    self.events.emit("assistant_text", run_id=run_id, text=completion.text,
                                     agent=self.agent_name, step=steps)
                    if self.store and session_id:
                        self.store.add_message(session_id, run_id, "assistant", completion.text,
                                               tokens_in=completion.usage_in,
                                               tokens_out=completion.usage_out)
                    final_text = completion.text

                if self.cancel.is_set():
                    status = "stopped"
                    final_text = final_text or "Stopped by the owner."
                    break
                if not completion.tool_calls:
                    break

                # record the assistant's tool-call turn so history replays correctly
                if self.store and session_id:
                    self.store.add_message(session_id, run_id, "assistant", completion.text or "",
                                           tool_name=completion.tool_calls[0].name,
                                           tool_args={"calls": [
                                               {"name": c_.name, "args": c_.args}
                                               for c_ in completion.tool_calls]})
                messages.append({"role": "assistant", "content": completion.text or "",
                                 "tool_calls": [{"id": c_.id, "name": c_.name, "args": c_.args}
                                                for c_ in completion.tool_calls]})

                for call in completion.tool_calls:
                    if self.cancel.is_set():
                        break
                    self.events.emit("tool_call", run_id=run_id, tool=call.name, args=call.args,
                                     agent=self.agent_name, step=steps)
                    result = self.runner.run(call.name, call.args if isinstance(call.args, dict) else {})
                    self.events.emit("tool_result", run_id=run_id, tool=call.name, ok=result.ok,
                                     output=result.text[:4000], verdict=result.verdict,
                                     agent=self.agent_name, step=steps)
                    messages.append({"role": "tool", "content": result.as_message_content(),
                                     "tool_call_id": call.id, "tool_call_name": call.name})
                    if self.store and session_id:
                        self.store.add_message(session_id, run_id, "tool", "",
                                               tool_name=call.name, tool_args=call.args,
                                               tool_result=result.text[:60_000],
                                               ok=1 if result.ok else 0)
                    if call.name == "finish" and result.ok:
                        final_text = result.text
                        status = "done"
                        steps = self.max_steps if False else steps
                        raise _Finished()
                budget = self.policy.conf.get("budget_usd_per_run")
                if budget and cost > float(budget):
                    status = "stopped"
                    final_text += f"\n\n[stopped: run cost ${cost:.4f} exceeded budget ${budget}]"
                    break
            else:
                status = "stopped"
                final_text += f"\n\n[stopped: hit the {self.max_steps}-step ceiling]"
        except _Finished:
            pass
        except ProviderError as exc:
            status, error = "error", str(exc)
            self.events.emit("error", run_id=run_id, error=error)
        except KeyboardInterrupt:
            status, error = "stopped", "interrupted"
        except Exception as exc:  # pragma: no cover - defensive
            status, error = "error", f"{type(exc).__name__}: {exc}"
            self.events.emit("error", run_id=run_id, error=error)

        if self.store:
            if run_id:
                self.store.finish_run(run_id, status, final_text[:20_000], error, steps, tin, tout, cost)
            if session_id and (final_text or error):
                note = final_text if not error else f"ERROR: {error}"
                self.store.add_message(session_id, run_id, "note", note[:4000])

        payload = {"status": status, "summary": final_text, "error": error, "run_id": run_id,
                   "session_id": session_id, "steps": steps, "tokens_in": tin, "tokens_out": tout,
                   "cost_usd": round(cost, 6), "cost_unknown": unknown_price,
                   "provider": self.provider.id, "model": self.provider.model,
                   "seconds": round(time.time() - t0, 2), "agent": self.agent_name}
        self.events.emit("finished", **payload)
        return payload


class _Finished(Exception):
    pass
