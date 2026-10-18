"""Offline test suite for the portable agent runtime.

    python3 -m unittest discover -s agent/tests -v
    python3 -m agent selftest

No credentials, no network, no writes outside a temp dir.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

TMP = tempfile.mkdtemp(prefix="wyagent-test-")
os.environ["WY_AGENT_HOME"] = TMP  # every config/state path lands here

from agent import config as cfg                      # noqa: E402
from agent import orchestrator, providers, tools as toolmod  # noqa: E402
from agent.loop import AgentLoop, Events              # noqa: E402
from agent.providers import Completion, Provider, ToolCall  # noqa: E402
from agent.store import Store                         # noqa: E402


def fresh_store(name: str = "t.db") -> Store:
    return Store(Path(TMP) / name)


class Isolated(unittest.TestCase):
    """Each test class gets its own state dir, so keys/config never leak between tests."""

    @classmethod
    def setUpClass(cls):
        cls._prev_home = os.environ.get("WY_AGENT_HOME")
        home = Path(TMP) / f"home-{cls.__name__}"
        home.mkdir(parents=True, exist_ok=True)
        os.environ["WY_AGENT_HOME"] = str(home)
        cls.home = home
        super().setUpClass()


class ScriptedProvider(Provider):
    """Returns a canned sequence of completions; records the calls it saw."""

    id = "scripted"
    label = "scripted"
    default_model = "scripted-1"
    needs_key = False
    model = "scripted-1"
    base_url = ""
    key = None

    def __init__(self, script):
        self.script = list(script)
        self.seen: list[list[dict]] = []

    def configured(self):
        return True

    def complete(self, messages, tools, system="", max_tokens=4096, temperature=0.2):
        self.seen.append([dict(m) for m in messages])
        item = self.script.pop(0) if self.script else Completion(text="(script exhausted)")
        return item


# --------------------------------------------------------------------------- config

class TestConfig(Isolated):
    def test_defaults_and_overrides(self):
        c = cfg.Config({"mode": "swarm", "max_steps": 3})
        self.assertEqual(c.get("mode"), "swarm")
        self.assertEqual(c.get("max_steps"), 3)
        self.assertTrue(str(c.workspace).endswith("therealwindycity"))

    def test_secrets_never_go_in_config_files(self):
        for bad in ("api_key", "anthropic_api_key", "server_token", "password"):
            with self.assertRaises(ValueError):
                cfg.save_config({bad: "x"})

    def test_secret_roundtrip_is_0600(self):
        cfg.save_secret("anthropic", "sk-test-123")
        self.assertEqual(cfg.Config().secret("anthropic"), "sk-test-123")
        mode = oct(os.stat(cfg.secrets_path()).st_mode & 0o777)
        self.assertEqual(mode, "0o600")

    def test_env_beats_file(self):
        cfg.save_secret("openai", "from-file")
        os.environ["OPENAI_API_KEY"] = "from-env"
        try:
            self.assertEqual(cfg.Config().secret("openai"), "from-env")
        finally:
            del os.environ["OPENAI_API_KEY"]


# --------------------------------------------------------------------------- store

class TestStore(Isolated):
    def setUp(self):
        self.store = fresh_store("store.db")

    def test_session_message_roundtrip(self):
        sid = self.store.create_session("hello", mode="single")
        self.store.add_message(sid, None, "user", "do a thing")
        self.store.add_message(sid, None, "assistant", "done")
        msgs = self.store.get_messages(sid)
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant"])
        self.assertEqual(msgs[0]["seq"], 1)
        self.assertEqual(msgs[1]["seq"], 2)

    def test_run_lifecycle(self):
        sid = self.store.create_session("run")
        rid = self.store.start_run(sid, "task", "single", "demo", "offline")
        self.store.finish_run(rid, "done", "summary", steps=3, tokens_in=10, tokens_out=5,
                              cost_usd=0.01)
        run = self.store.get_run(rid)
        self.assertEqual(run["status"], "done")
        self.assertEqual(run["steps"], 3)

    def test_memory_upsert_and_search(self):
        self.store.memo_set("owner", "bart", tags="identity")
        self.store.memo_set("owner", "bartimoussmith-oss", tags="identity")
        self.assertEqual(self.store.memo_get("owner"), "bartimoussmith-oss")
        self.assertTrue(self.store.memo_search("bartimoussmith"))

    def test_audit_and_devices(self):
        self.store.audit("r1", "shell", {"command": "ls"}, "allow", True, 5, "abc", "main")
        self.assertEqual(len(self.store.list_audit("r1")), 1)
        did = self.store.add_device("phone", "android-termux", "hash")
        self.assertIsNotNone(self.store.find_device_by_token("hash"))
        self.assertEqual(self.store.list_devices()[0]["id"], did)


# --------------------------------------------------------------------------- policy

class TestPolicy(Isolated):
    def setUp(self):
        self.policy = toolmod.Policy(cfg.Config({"workspace": TMP}))

    def test_denies_catastrophic(self):
        for cmd in ("rm -rf /", "mkfs.ext4 /dev/sda1", ":(){ :|:& };:",
                    "git push --force origin main", "shutdown -h now", "rm -rf ~"):
            verdict, _ = self.policy.judge_command(cmd)
            self.assertEqual(verdict, "deny", cmd)

    def test_confirms_elevated(self):
        for cmd in ("sudo apt install nmap", "pip install requests", "rm -rf build"):
            verdict, _ = self.policy.judge_command(cmd)
            self.assertEqual(verdict, "confirm", cmd)

    def test_allows_ordinary(self):
        for cmd in ("ls -la", "python3 -m agent doctor", "git status", "grep -r foo ."):
            verdict, _ = self.policy.judge_command(cmd)
            self.assertEqual(verdict, "allow", cmd)

    def test_path_jail(self):
        self.policy.resolve("./ok.txt")
        with self.assertRaises(PermissionError):
            self.policy.resolve("/etc/passwd")
        outside = toolmod.Policy(cfg.Config({"workspace": TMP, "allow_outside_workspace": True}))
        self.assertTrue(str(outside.resolve("/etc/hosts")).endswith("hosts"))


# --------------------------------------------------------------------------- tools

class TestTools(Isolated):
    def setUp(self):
        self.ws = Path(TMP) / f"ws{time.time_ns()}"
        self.ws.mkdir(parents=True)
        (self.ws / "hello.txt").write_text("alpha\nbeta\ngamma\n")
        self.policy = toolmod.Policy(cfg.Config({"workspace": str(self.ws)}),
                                     store=fresh_store("tools.db"))
        self.runner = toolmod.ToolRunner(self.policy)

    def test_read_write_edit(self):
        out = self.runner.run("read_file", {"path": "hello.txt"})
        self.assertTrue(out.ok)
        self.assertIn("beta", out.text)
        w = self.runner.run("write_file", {"path": "new.txt", "content": "hi"})
        self.assertTrue(w.ok)
        self.assertFalse(self.runner.run("write_file", {"path": "new.txt", "content": "x"}).ok)
        e = self.runner.run("edit_file", {"path": "new.txt", "old": "hi", "new": "hello"})
        self.assertTrue(e.ok)
        self.assertEqual((self.ws / "new.txt").read_text(), "hello")

    def test_edit_requires_existing_text(self):
        out = self.runner.run("edit_file", {"path": "hello.txt", "old": "nope", "new": "x"})
        self.assertFalse(out.ok)
        self.assertIn("not found", out.text)

    def test_list_glob_grep(self):
        self.assertTrue(self.runner.run("list_dir", {"path": "."}).ok)
        self.assertIn("hello.txt", self.runner.run("glob", {"pattern": "*.txt"}).text)
        g = self.runner.run("grep", {"pattern": "beta"})
        self.assertIn("beta", g.text)

    def test_unknown_tool_is_polite(self):
        out = self.runner.run("nope", {})
        self.assertFalse(out.ok)
        self.assertIn("unknown tool", out.text)

    def test_dry_run_blocks_mutation(self):
        policy = toolmod.Policy(cfg.Config({"workspace": str(self.ws), "dry_run": True}))
        runner = toolmod.ToolRunner(policy)
        out = runner.run("write_file", {"path": "x.txt", "content": "no"})
        self.assertTrue(out.ok)
        self.assertIn("dry-run", out.text)
        self.assertFalse((self.ws / "x.txt").exists())

    def test_denied_shell_is_refused(self):
        out = self.runner.run("shell", {"command": "rm -rf /"})
        self.assertFalse(out.ok)
        self.assertIn("refused", out.text)

    def test_shell_runs_and_reports_exit(self):
        out = self.runner.run("shell", {"command": "echo hello && exit 3"})
        self.assertFalse(out.ok)
        self.assertEqual(out.data.get("exit_code"), 3)
        self.assertIn("hello", out.text)

    def test_allowed_toolset_is_enforced(self):
        runner = toolmod.ToolRunner(self.policy, allowed={"read_file"})
        self.assertFalse(runner.run("shell", {"command": "echo hi"}).ok)
        self.assertTrue(runner.run("read_file", {"path": "hello.txt"}).ok)

    def test_audit_written(self):
        self.runner.run("read_file", {"path": "hello.txt"})
        self.assertTrue(self.policy.store.list_audit())


# --------------------------------------------------------------------------- providers

class TestProviders(Isolated):
    def test_paste_bridge_parses_tool_calls(self):
        reply = 'Here you go:\n```json\n{"tool_calls":[{"name":"list_dir","args":{"path":"."}}]}\n```'
        c = providers.PasteBridgeProvider.parse_reply(reply)
        self.assertEqual(len(c.tool_calls), 1)
        self.assertEqual(c.tool_calls[0].name, "list_dir")
        self.assertEqual(c.tool_calls[0].args, {"path": "."})

    def test_paste_bridge_parses_final_and_bare_json(self):
        c = providers.PasteBridgeProvider.parse_reply('{"final": "all done"}')
        self.assertEqual(c.text, "all done")
        c2 = providers.PasteBridgeProvider.parse_reply("just prose, no json")
        self.assertEqual(c2.text, "just prose, no json")

    def test_bridge_prompt_contains_protocol_and_tools(self):
        p = providers.PasteBridgeProvider(cfg.Config())
        prompt = p.build_prompt([{"role": "user", "content": "do it"}],
                                [{"name": "shell", "description": "run a command",
                                  "parameters": {"type": "object"}}], "SYS")
        self.assertIn("tool_calls", prompt)
        self.assertIn("shell", prompt)
        self.assertIn("do it", prompt)

    def test_arena_provider_is_honest_when_unconfigured(self):
        p = providers.ArenaProvider(cfg.Config())
        self.assertFalse(p.configured())
        self.assertIn("no self-serve API", p.why_unavailable())

    def test_cost_estimate(self):
        cost, unknown = providers.estimate_cost("claude-sonnet-5", 1_000_000, 1_000_000)
        self.assertAlmostEqual(cost, 12.0, places=4)
        self.assertFalse(unknown)
        cost2, unknown2 = providers.estimate_cost("mystery-model", 1000, 1000)
        self.assertEqual(cost2, 0.0)
        self.assertTrue(unknown2)

    def test_build_falls_back_to_demo(self):
        p = providers.build(cfg.Config({"provider": "demo"}))
        self.assertEqual(p.id, "demo")
        with self.assertRaises(providers.ProviderError):
            providers.build(cfg.Config({"provider": "nonsense"}))

    def test_demo_provider_calls_real_tools_offline(self):
        p = providers.DemoProvider(cfg.Config())
        comp = p.complete([{"role": "user", "content": "list the repo files"}],
                          [{"name": "list_dir", "description": "", "parameters": {}},
                           {"name": "shell", "description": "", "parameters": {}}])
        self.assertTrue(comp.tool_calls)
        second = p.complete([{"role": "user", "content": "x"},
                             {"role": "tool", "content": "output", "tool_call_name": "list_dir"}],
                            [{"name": "list_dir", "description": "", "parameters": {}}])
        self.assertIn("Offline demo", second.text)


# --------------------------------------------------------------------------- loop

class TestLoop(Isolated):
    def setUp(self):
        self.ws = Path(TMP) / f"loop{time.time_ns()}"
        self.ws.mkdir()
        (self.ws / "a.txt").write_text("content\n")
        self.store = fresh_store("loop.db")
        self.policy = toolmod.Policy(cfg.Config({"workspace": str(self.ws)}), store=self.store)

    def test_tool_cycle_then_final(self):
        provider = ScriptedProvider([
            Completion(tool_calls=[ToolCall("c1", "read_file", {"path": "a.txt"})],
                       usage_in=10, usage_out=5, model="claude-sonnet-5"),
            Completion(text="All done: a.txt says content.", usage_in=3, usage_out=4,
                       model="claude-sonnet-5"),
        ])
        events = []
        loop = AgentLoop(provider, toolmod.ToolRunner(self.policy, run_id=None), store=self.store,
                         policy=self.policy, max_steps=5, events=Events())
        loop.events.subscribe(events.append)
        out = loop.run_task("read a.txt")
        self.assertEqual(out["status"], "done")
        self.assertIn("All done", out["summary"])
        self.assertEqual(out["steps"], 2)
        self.assertEqual(out["tokens_in"], 13)
        kinds = [e["kind"] for e in events]
        self.assertIn("tool_call", kinds)
        self.assertIn("tool_result", kinds)
        self.assertIn("finished", kinds)
        # the second call must have seen the tool output
        self.assertTrue(any(m.get("role") == "tool" for m in provider.seen[1]))

    def test_history_is_replayed_into_new_runs(self):
        provider = ScriptedProvider([Completion(text="first answer")])
        loop = AgentLoop(provider, toolmod.ToolRunner(self.policy), store=self.store,
                         policy=self.policy, max_steps=2)
        out = loop.run_task("first task")
        sid = out["session_id"]
        provider2 = ScriptedProvider([Completion(text="second answer")])
        loop2 = AgentLoop(provider2, toolmod.ToolRunner(self.policy), store=self.store,
                          policy=self.policy, max_steps=2)
        loop2.run_task("second task", session_id=sid)
        seen = provider2.seen[0]
        self.assertTrue(any(m.get("content") == "first task" for m in seen))
        self.assertTrue(any(m.get("content") == "first answer" for m in seen))

    def test_max_steps_ceiling_is_reported(self):
        provider = ScriptedProvider([
            Completion(tool_calls=[ToolCall(f"c{i}", "list_dir", {"path": "."})]) for i in range(10)
        ])
        loop = AgentLoop(provider, toolmod.ToolRunner(self.policy), store=self.store,
                         policy=self.policy, max_steps=3)
        out = loop.run_task("loop forever")
        self.assertEqual(out["status"], "stopped")
        self.assertIn("step ceiling", out["summary"])

    def test_cancellation(self):
        cancel = threading.Event()

        class Slow(ScriptedProvider):
            def complete(self, messages, tools, system="", max_tokens=4096, temperature=0.2):
                cancel.set()
                return Completion(text="hi")

        loop = AgentLoop(Slow([]), toolmod.ToolRunner(self.policy), store=self.store,
                         policy=self.policy, max_steps=3, cancel=cancel)
        out = loop.run_task("anything")
        self.assertEqual(out["status"], "stopped")

    def test_provider_error_is_captured_not_raised(self):
        class Boom(ScriptedProvider):
            def complete(self, *a, **k):
                raise providers.ProviderError("no key configured")

        loop = AgentLoop(Boom([]), toolmod.ToolRunner(self.policy), store=self.store,
                         policy=self.policy, max_steps=2)
        out = loop.run_task("x")
        self.assertEqual(out["status"], "error")
        self.assertIn("no key", out["error"])


# --------------------------------------------------------------------------- orchestration

class TestOrchestrator(Isolated):
    def setUp(self):
        self.ws = Path(TMP) / f"orch{time.time_ns()}"
        self.ws.mkdir()
        self.store = fresh_store("orch.db")
        self.conf = cfg.Config({"workspace": str(self.ws), "issue_worktrees": False,
                                "max_workers": 3, "max_steps": 2})

    def test_plan_worker_verify_synthesize(self):
        plan = json.dumps({"subtasks": [
            {"role": "scout", "task": "count the files", "deliverable": "a count"},
            {"role": "scout", "task": "list the files", "deliverable": "a list"}]})
        verdicts = json.dumps({"verdicts": [
            {"claim": "two files exist", "verdict": "verified", "evidence": "ls showed 2"}]})
        provider = ScriptedProvider([
            Completion(text=plan),                       # planner
            Completion(text="found 2 files"),            # worker 1
            Completion(text="a.txt b.txt"),              # worker 2
            Completion(text=verdicts),                   # verifier
            Completion(text="Report: two files exist (verified)."),  # synthesizer
        ])
        orch = orchestrator.Orchestrator(self.conf, provider, store=self.store)
        out = orch.run("inventory the folder", mode="swarm")
        self.assertIn("two files", out["summary"])
        self.assertEqual(len(out["workers"]), 2)
        self.assertEqual(out["verdicts"][0]["verdict"], "verified")
        self.assertEqual(len(self.store.list_tasks(out["run_id"])), 2)

    def test_planner_failure_degrades_to_one_worker(self):
        class Flaky(ScriptedProvider):
            def complete(self, messages, tools, system="", max_tokens=4096, temperature=0.2):
                raise providers.ProviderError("planner down")

        orch = orchestrator.Orchestrator(self.conf, Flaky([]), store=self.store)
        out = orch.run("do the thing", mode="plan")
        self.assertIn(out["status"], ("done", "error"))
        self.assertTrue(len(out["workers"]) >= 1)

    def test_fallback_report_renders_verdicts(self):
        text = orchestrator.fallback_report(
            [{"worker": "w1", "role": "scout", "status": "done", "summary": "did it"}],
            [{"claim": "c", "verdict": "wrong", "evidence": "e"}])
        self.assertIn("w1", text)
        self.assertIn("❌", text)


# --------------------------------------------------------------------------- server

class TestServer(Isolated):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from http.server import ThreadingHTTPServer
        from agent import server as server_mod
        cls.store = fresh_store("server.db")
        conf = cfg.Config({"provider": "demo", "mode": "single", "max_steps": 2,
                           "workspace": str(cfg.REPO_ROOT), "issue_worktrees": False})
        cls.app = server_mod.App(conf, cls.store)
        server_mod.Handler.app = cls.app
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_mod.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.store.close()
        if cls._prev_home:
            os.environ["WY_AGENT_HOME"] = cls._prev_home
        else:
            os.environ.pop("WY_AGENT_HOME", None)

    def get(self, path, raw=False):
        with urllib.request.urlopen(self.base + path, timeout=15) as r:
            body = r.read().decode()
        return body if raw else json.loads(body)

    def post(self, path, payload):
        req = urllib.request.Request(self.base + path, method="POST",
                                     data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())

    def test_index_is_served_and_is_a_pwa(self):
        html = self.get("/", raw=True)
        self.assertIn("windycity-agent", html.lower())
        self.assertIn("manifest.webmanifest", html)
        self.assertIn("serviceWorker", html)

    def test_no_localhost_references_in_the_client(self):
        html = (Path(cfg.REPO_ROOT) / "agent" / "webapp.html").read_text()
        self.assertNotIn("127.0.0.1", html)
        self.assertNotIn("localhost", html)

    def test_health_and_manifest_and_sw(self):
        health = self.get("/api/health")
        self.assertTrue(health["ok"])
        self.assertEqual(health["provider"], "demo")
        self.assertIn("icon", self.get("/manifest.webmanifest", raw=True))
        self.assertIn("service worker", self.get("/sw.js", raw=True).lower())

    def test_providers_and_tools_and_settings(self):
        provs = self.get("/api/providers")
        self.assertTrue(any(p["id"] == "paste" and p["ready"] for p in provs))
        self.assertTrue(any(t["name"] == "shell" for t in self.get("/api/tools")))
        self.assertIn("workspace", self.get("/api/settings"))

    def test_full_run_over_http_with_stream(self):
        out = self.post("/api/chat", {"task": "offline demo run", "mode": "single", "dry_run": True})
        rid = out["run_id"]
        events = []
        with urllib.request.urlopen(f"{self.base}/api/stream/{rid}", timeout=60) as r:
            for line in r:
                line = line.decode().strip()
                if line.startswith("data: "):
                    evt = json.loads(line[6:])
                    events.append(evt)
                    if evt.get("kind") == "finished":
                        break
        kinds = [e["kind"] for e in events]
        self.assertIn("hello", kinds)
        self.assertIn("tool_call", kinds)
        self.assertIn("finished", kinds)
        detail = self.get(f"/api/sessions/{out['session_id']}")
        self.assertTrue(any(m["role"] == "user" for m in detail["messages"]))

    def test_memory_and_audit_endpoints(self):
        self.post("/api/memory", {"key": "test", "value": "value"})
        self.assertTrue(any(m["key"] == "test" for m in self.get("/api/memory")))
        self.assertTrue(isinstance(self.get("/api/audit"), list))

    def test_bridge_delivery_requires_a_waiting_run(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.post("/api/bridge", {"run_id": "nope", "reply": "x"})


# --------------------------------------------------------------------------- cli

class TestCLI(Isolated):
    def test_selftest_passes(self):
        from agent.cli import main
        self.assertEqual(main(["selftest"]), 0)

    def test_doctor_runs(self):
        from agent.cli import main
        with mock.patch("builtins.print"):
            self.assertEqual(main(["doctor"]), 0)

    def test_config_set_refuses_secret_like_keys(self):
        from agent.cli import main
        with mock.patch("builtins.print"):
            self.assertEqual(main(["config", "set", "api_key", "abc"]), 1)

    def test_key_set_writes_only_to_private_file(self):
        from agent.cli import main
        with mock.patch("builtins.print"):
            self.assertEqual(main(["key", "set", "groq", "gsk-xyz"]), 0)
        self.assertFalse((cfg.REPO_ROOT / "secrets.json").exists())
        self.assertEqual(cfg.Config().secret("groq"), "gsk-xyz")

    def test_no_command_prints_help(self):
        from agent.cli import main
        with mock.patch("builtins.print"):
            self.assertEqual(main([]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
