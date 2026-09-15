"""Multi-agent modes: plan, swarm, verify.

Shape of a swarm run:

    plan      the planner turns your request into 2-N self-contained subtasks
    work      workers run those subtasks IN PARALLEL, each with its own context
              and its own tool allow-list
    verify    a separate verifier agent re-checks every worker claim with tools
              (reads the file, runs the command, fetches the URL)
    report    one synthesizer writes the answer from VERIFIED material only

Safety properties that make this safe to leave running:
  * workers are read-only unless a git worktree is issued for them;
  * worktrees are DETACHED (no branches invented in your repo) and live under
    ~/.windycity-agent/worktrees/<run-id>/;
  * worker edits are never auto-applied to your working tree — you get a diff
    plus the exact `git apply` command;
  * every worker, tool call and verdict lands in the store and the audit table.
"""
from __future__ import annotations

import concurrent.futures as futures
import json
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import config as cfg
from .loop import AgentLoop, Events
from .providers import Provider, ProviderError
from .tools import REGISTRY, Policy, ToolRunner

READ_ONLY_TOOLS = {"read_file", "list_dir", "glob", "grep", "http_get", "web_search",
                   "memory_search", "memory_set", "civic_pipeline", "git", "shell"}
WRITE_TOOLS = READ_ONLY_TOOLS | {"write_file", "edit_file"}
PLANNER_TOOLS = {"read_file", "list_dir", "glob", "grep", "memory_search"}

PLAN_PROMPT = """You are the planner for a local multi-agent run.

Break the owner's request into independent subtasks that can run AT THE SAME TIME.
Rules:
- 2 to {max_workers} subtasks, ordered by importance. Fewer is fine; one is fine.
- Each subtask must be self-contained: a worker sees ONLY its own instruction, no history.
- State the exact deliverable and the evidence the worker should return (file paths, command
  output, URLs, line numbers).
- Prefer recon/verification subtasks over speculative rewrites.
- If the request is a single atomic action, answer with exactly one subtask.

Reply with ONLY this JSON (no prose, no fences):

{{"subtasks": [
  {{"role": "scout", "task": "...", "tools": ["read_file", "grep", "list_dir"],
   "deliverable": "what to return"}}
]}}

Owner's request:
{task}
"""

VERIFY_PROMPT = """You are the verifier. Below are claims made by other agents.

For EACH claim, check it against reality with your tools:
- file/line claims: read the file and confirm the exact text exists
- behaviour claims: run the command or test
- web claims: fetch the URL
- numbers: re-derive them

Then reply with ONLY this JSON:

{{"verdicts": [
  {{"claim": "...", "verdict": "verified|unverified|wrong", "evidence": "exact command or quote + what it showed"}}
]}}

Rules: "verified" requires evidence you personally obtained in this run. If you could not check
something, say "unverified" and why. Never mark verified on the strength of the claim alone.

CLAIMS:
{claims}
"""

SYNTH_PROMPT = """You are writing the final report for the owner after a multi-agent run.

Rules:
- Lead with the outcome in 1-3 sentences: what was done/found, and what it means.
- Include only VERIFIED material as fact; label everything else clearly as unverified.
- Name concrete artifacts: file paths, commands, URLs, diffs.
- Say plainly what is left to do, or what blocked progress.
- No filler, no restating the request, no invented detail.

OWNER'S REQUEST:
{task}

WORKER RESULTS:
{results}

VERIFIER VERDICTS:
{verdicts}
"""


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    for blob in re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S):
        try:
            return json.loads(blob)
        except json.JSONDecodeError:
            continue
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


class Orchestrator:
    def __init__(self, conf: cfg.Config, provider: Provider, store=None, events: Events | None = None,
                 cancel: threading.Event | None = None, confirm_handler=None):
        self.conf = conf
        self.provider = provider
        self.store = store
        self.events = events or Events()
        self.cancel = cancel or threading.Event()
        self.confirm_handler = confirm_handler

    # -- helpers ------------------------------------------------------------
    def _policy(self, workspace: Path | None = None, agent_name: str = "main") -> Policy:
        p = Policy(self.conf, store=self.store, confirm_handler=self.confirm_handler,
                   agent_name=agent_name, workspace_override=workspace)
        return p

    def _loop(self, policy: Policy, allowed: set[str] | None, run_id: str | None,
              agent_name: str, max_steps: int | None = None) -> AgentLoop:
        runner = ToolRunner(policy, run_id=run_id, allowed=allowed)
        return AgentLoop(self.provider, runner, store=self.store, policy=policy, mode="single",
                         max_steps=max_steps or int(self.conf.get("max_steps") or 16),
                         events=self.events, cancel=self.cancel, agent_name=agent_name)

    def _worktree(self, run_id: str, worker: str, workspace: Path) -> Path | None:
        """Detached worktree for an isolated writer. No branches are created."""
        if not self.conf.get("issue_worktrees", True):
            return None
        root = cfg.home_dir() / "worktrees" / str(run_id or "adhoc") / worker
        root.parent.mkdir(parents=True, exist_ok=True)
        if not (workspace / ".git").exists():
            return None
        try:
            subprocess.run(["git", "worktree", "add", "--detach", str(root), "HEAD"],
                           cwd=str(workspace), capture_output=True, text=True, timeout=120, check=True)
            return root
        except Exception:
            return None

    def _worktree_diff(self, path: Path) -> str:
        try:
            subprocess.run(["git", "add", "-A"], cwd=str(path), capture_output=True, timeout=60)
            proc = subprocess.run(["git", "diff", "--cached", "--stat"], cwd=str(path),
                                  capture_output=True, text=True, timeout=60)
            return proc.stdout.strip()
        except Exception:
            return ""

    # -- phases -------------------------------------------------------------
    def plan(self, task: str, run_id: str | None, max_workers: int) -> list[dict]:
        prompt = PLAN_PROMPT.format(task=task, max_workers=max_workers)
        try:
            completion = self.provider.complete([{"role": "user", "content": prompt}],
                                                [], system="Reply with JSON only.")
            data = _extract_json(completion.text) or {}
            subtasks = data.get("subtasks") or []
        except ProviderError as exc:
            self.events.emit("phase", phase="plan", note=f"planner failed ({exc}); single worker")
            subtasks = []
        if not subtasks:
            subtasks = [{"role": "worker", "task": task,
                         "deliverable": "complete the request and report evidence"}]
        return subtasks[:max_workers]

    def _run_worker(self, run_id: str, sub: dict, idx: int, primary_workspace: Path,
                    allow_write: bool) -> dict:
        role = str(sub.get("role") or f"worker{idx}")
        name = f"{role}-{idx+1}"
        # A worker may only use tools that exist, are read-only, or were handed an isolated
        # worktree. The allow-list is intersected with the real registry so a hallucinated
        # tool name in a plan can never widen access.
        requested = set(sub.get("tools") or [])
        base = WRITE_TOOLS if allow_write else READ_ONLY_TOOLS
        allowed = (requested & base) if requested else set(base)
        allowed = {a for a in allowed if a in REGISTRY}

        worktree = self._worktree(run_id, name, primary_workspace) if allow_write else None
        workspace = worktree or primary_workspace
        policy = self._policy(workspace=workspace, agent_name=name)
        policy.auto_approve = not allow_write  # writers still can't install/force anything
        task = (f"SUBTASK ({role}):\n{sub.get('task')}\n\n"
                f"DELIVERABLE: {sub.get('deliverable') or 'a short report with evidence'}\n"
                + (f"\nYou are working in an ISOLATED COPY of the project at {workspace}. "
                   "Make your edits there; they will be shown to the owner as a diff. "
                   "This copy reflects the last commit only — if a file you expect is missing, "
                   "it may be uncommitted in the owner's tree, so say so instead of guessing.\n"
                   if worktree else ""))
        tid = None
        if self.store and run_id:
            tid = self.store.add_task(run_id, name, role, str(sub.get("task")), str(worktree or ""))
        self.events.emit("worker_start", run_id=run_id, worker=name, role=role,
                         task=str(sub.get("task"))[:2000], worktree=str(worktree or ""))
        loop = self._loop(policy, allowed, run_id, name)
        out = loop.run_task(task, session_id=None, persona="terse")
        diff = self._worktree_diff(Path(worktree)) if worktree else ""
        if self.store and tid:
            self.store.update_task(tid, out.get("status", "done"),
                                   (out.get("summary") or "")[:20_000])
        self.events.emit("worker_done", run_id=run_id, worker=name, status=out.get("status"),
                         summary=(out.get("summary") or "")[:4000], diff=diff[:4000])
        return {"worker": name, "role": role, "status": out.get("status"),
                "summary": out.get("summary") or "", "error": out.get("error") or "",
                "worktree": str(worktree) if worktree else "", "diff": diff,
                "steps": out.get("steps"), "cost_usd": out.get("cost_usd")}

    def verify(self, task: str, results: list[dict], run_id: str | None) -> list[dict]:
        claims = "\n".join(
            f"- [{r['worker']}] ({r['status']}) {r['summary'][:3000]}" for r in results if r["summary"])
        if not claims.strip():
            return []
        policy = self._policy(agent_name="verifier")
        loop = self._loop(policy, READ_ONLY_TOOLS, run_id, "verifier", max_steps=int(
            self.conf.get("max_steps") or 16))
        self.events.emit("phase", phase="verify", run_id=run_id, note="independent re-checks")
        out = loop.run_task(VERIFY_PROMPT.format(claims=claims), session_id=None, persona="terse",
                            extra_system="You may only READ and RUN checks. Report exact evidence.")
        data = _extract_json(out.get("summary", "")) or {}
        verdicts = data.get("verdicts") or []
        self.events.emit("phase", phase="verify_done", run_id=run_id, note=f"{len(verdicts)} verdicts")
        return verdicts

    def synthesize(self, task: str, results: list[dict], verdicts: list[dict],
                   run_id: str | None) -> str:
        policy = self._policy(agent_name="synthesizer")
        loop = self._loop(policy, {"memory_search"}, run_id, "synthesizer", max_steps=2)
        prompt = SYNTH_PROMPT.format(
            task=task,
            results=json.dumps([{k: r[k] for k in ("worker", "role", "status", "summary", "diff")}
                                for r in results], indent=1)[:40_000],
            verdicts=json.dumps(verdicts, indent=1)[:20_000])
        out = loop.run_task(prompt, session_id=None, persona="terse")
        text = out.get("summary") or ""
        if not text.strip() or self.provider.id == "demo":
            # the offline brain cannot synthesize; the deterministic report is better
            text = fallback_report(results, verdicts)
        return text

    # -- entry point --------------------------------------------------------
    def run(self, task: str, session_id: str | None = None, mode: str = "swarm") -> dict:
        t0 = time.time()
        max_workers = int(self.conf.get("max_workers") or 4)
        if session_id is None and self.store:
            session_id = self.store.create_session(title=task[:80], mode=mode,
                                                   provider=self.provider.id,
                                                   model=self.provider.model,
                                                   workspace=str(self.conf.workspace))
        run_id = self.store.start_run(session_id, task, mode, self.provider.id,
                                      self.provider.model) if self.store else None
        if self.store and session_id:
            self.store.add_message(session_id, run_id, "user", task)
        self.events.emit("run_start", run_id=run_id, session_id=session_id, task=task,
                         provider=self.provider.id, model=self.provider.model, mode=mode)

        subtasks = self.plan(task, run_id, max_workers)
        self.events.emit("plan", run_id=run_id, subtasks=subtasks)
        for s in subtasks:
            if self.store and session_id:
                self.store.add_message(session_id, run_id, "note",
                                       f"plan: [{s.get('role')}] {s.get('task')}")

        allow_write = mode == "swarm" and bool(self.conf.get("issue_worktrees", True))
        results: list[dict] = []
        if len(subtasks) == 1 and not allow_write:
            results.append(self._run_worker(run_id, subtasks[0], 0, self.conf.workspace, False))
        else:
            with futures.ThreadPoolExecutor(max_workers=min(max_workers, len(subtasks))) as pool:
                jobs = [pool.submit(self._run_worker, run_id, s, i, self.conf.workspace, allow_write)
                        for i, s in enumerate(subtasks)]
                for job in futures.as_completed(jobs):
                    try:
                        results.append(job.result())
                    except Exception as exc:
                        results.append({"worker": "worker", "role": "worker", "status": "error",
                                        "summary": "", "error": f"{type(exc).__name__}: {exc}",
                                        "diff": "", "worktree": ""})

        verdicts = self.verify(task, results, run_id) if self.conf.get("verify", True) else []
        report = self.synthesize(task, results, verdicts, run_id)
        report = append_diff_section(report, results)

        status = "done" if any(r["status"] == "done" for r in results) else "error"
        cost = sum(float(r.get("cost_usd") or 0) for r in results)
        if self.store:
            self.store.finish_run(run_id, status, report[:20_000], "", len(results), 0, 0, cost)
            if session_id:
                self.store.add_message(session_id, run_id, "assistant", report)
        payload = {"status": status, "summary": report, "run_id": run_id, "session_id": session_id,
                   "workers": results, "verdicts": verdicts, "mode": mode,
                   "provider": self.provider.id, "model": self.provider.model,
                   "cost_usd": round(cost, 6), "seconds": round(time.time() - t0, 2),
                   "steps": sum(int(r.get("steps") or 0) for r in results),
                   "tokens_in": 0, "tokens_out": 0}
        self.events.emit("finished", **{k: v for k, v in payload.items() if k != "workers"})
        return payload


def fallback_report(results: list[dict], verdicts: list[dict]) -> str:
    lines = ["## Multi-agent run", ""]
    for r in results:
        lines.append(f"### {r['worker']} ({r['role']}) — {r['status']}")
        lines.append(r["summary"] or f"_(no output; {r.get('error') or 'unknown error'})_")
        lines.append("")
    if verdicts:
        lines.append("### Verification")
        for v in verdicts:
            icon = {"verified": "✅", "unverified": "❔", "wrong": "❌"}.get(v.get("verdict"), "•")
            lines.append(f"- {icon} {v.get('claim','')[:200]} — {v.get('evidence','')[:300]}")
    return "\n".join(lines)


def append_diff_section(report: str, results: list[dict]) -> str:
    diffs = [r for r in results if r.get("diff")]
    if not diffs:
        return report
    out = [report, "", "---", "## Isolated changes (not applied to your working tree)"]
    for r in diffs:
        out.append(f"\n**{r['worker']}** in `{r['worktree']}`:\n```\n{r['diff'][:8000]}\n```")
        out.append(f"Apply with:\n```\ncd {r['worktree']} && git diff --cached > /tmp/{r['worker']}.patch\n"
                   f"cd {Path.cwd()} && git apply /tmp/{r['worker']}.patch\n```")
    return "\n".join(out)


def cleanup_worktrees(keep: bool = False) -> list[str]:
    """Remove agent worktrees. Called by `agent prune`; never touches the repo's own trees."""
    root = cfg.home_dir() / "worktrees"
    removed = []
    if not root.exists():
        return removed
    for child in sorted(root.iterdir()):
        removed.append(str(child))
        if not keep:
            shutil.rmtree(child, ignore_errors=True)
    if not keep:
        shutil.rmtree(root, ignore_errors=True)
    return removed
