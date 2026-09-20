#!/usr/bin/env python3
"""Tests for the task runner. No model is needed: the agents are small scripts.

Run: python3 research/task_runner/prototype/tests/test_runner.py
"""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from taskrunner import agents, tasks                           # noqa: E402
from taskrunner.engine import DONE, ERROR, HUMAN, MORE, Runner  # noqa: E402

# A scripted agent. It reads the prompt on stdin, counts its calls in .calls-<role>, and does what the
# AGENT_SCRIPT for that call number says: write files, then print a JSON verdict.
FAKE = textwrap.dedent('''
    import json, os, sys
    prompt = sys.stdin.read()
    role = "review" if prompt.startswith("Review a change") else "implement"
    script = json.load(open(os.environ["AGENT_SCRIPT"]))[role]
    path = os.path.join(os.environ["AGENT_STATE"], "calls-" + role)
    n = int(open(path).read()) if os.path.exists(path) else 0
    open(path, "w").write(str(n + 1))
    open(os.path.join(os.environ["AGENT_STATE"], f"prompt-{role}-{n}"), "w").write(prompt)
    step = script[min(n, len(script) - 1)]
    for name, content in step.get("write", {}).items():
        os.makedirs(os.path.dirname(name) or ".", exist_ok=True)
        open(name, "w").write(content)
    if step.get("exit"):
        sys.exit(step["exit"])
    print("some prose first {not json}")
    print(json.dumps(step["say"]))
''')


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "repo")
        self.side = os.path.join(self.tmp.name, "side")
        os.makedirs(self.root)
        os.makedirs(self.side)
        with open(os.path.join(self.side, "fake.py"), "w") as f:
            f.write(FAKE)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.write("fixtures/golden.txt", "reviewed\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")
        os.environ["AGENT_SCRIPT"] = os.path.join(self.side, "script.json")
        os.environ["AGENT_STATE"] = self.side

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, check=True).stdout

    def write(self, rel, content):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)

    def plan(self, body, script, defaults=""):
        with open(os.environ["AGENT_SCRIPT"], "w") as f:
            json.dump(script, f)
        fake = os.path.join(self.side, "fake.py")
        self.write("../plan.toml", f'root = "repo"\nname = "t"\n[defaults]\nagent = "fake"\n{defaults}\n'
                   f'[agents.fake]\ntype = "command"\nargv = ["{sys.executable}", "{fake}"]\n' + textwrap.dedent(body))
        self.logs = []
        return Runner(tasks.load(os.path.join(self.tmp.name, "plan.toml")), log=self.logs.append)

    def prompt(self, role, n):
        with open(os.path.join(self.side, f"prompt-{role}-{n}")) as f:
            return f.read()

    OK = {"say": {"outcome": "done", "notes": "did it"}}
    APPROVE = {"say": {"approved": True, "reasons": []}}

    def test_tasks_run_in_dependency_order_and_each_is_committed(self):
        r = self.plan('''
            [[task]]
            id = "b"
            prompt = "write b"
            needs = ["a"]
            gate = "test -f a.txt && test -f b.txt"
            [[task]]
            id = "a"
            title = "Add a"
            prompt = "write a"
            gate = ["test -f a.txt"]
            ''', {"implement": [{**self.OK, "write": {"a.txt": "a"}}, {**self.OK, "write": {"b.txt": "b"}}],
                  "review": [self.APPROVE]})
        self.assertEqual([t.id for t in r.plan.tasks], ["a", "b"])
        self.assertEqual(r.run(), DONE)
        self.assertEqual(self.git("log", "--format=%s").split("\n")[:2], ["b", "Add a"])
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertIn("Your own report does not count", self.prompt("implement", 0))
        self.assertIn("+a", self.prompt("review", 0))            # the reviewer sees new, untracked files

    def test_gate_failure_is_fed_back_and_the_retry_passes(self):
        r = self.plan('''
            [[task]]
            id = "a"
            prompt = "make out.txt say right"
            gate = "grep -q right out.txt || { echo WRONG-CONTENT; exit 1; }"
            review = false
            ''', {"implement": [{**self.OK, "write": {"out.txt": "wrong"}}, {**self.OK, "write": {"out.txt": "right"}}]})
        self.assertEqual(r.run(), DONE)
        self.assertEqual(r.state["tasks"]["a"]["attempt"], 2)
        self.assertIn("WRONG-CONTENT", self.prompt("implement", 1))

    def test_agent_saying_done_never_passes_a_failing_gate(self):
        r = self.plan('''
            [[task]]
            id = "a"
            prompt = "p"
            gate = "echo attempt-$(cat n.txt); false"
            review = false
            ''', {"implement": [{**self.OK, "write": {"n.txt": "1"}}, {**self.OK, "write": {"n.txt": "2"}}]},
                      defaults="max_attempts = 2")
        self.assertEqual(r.run(), ERROR)
        self.assertIn("2 attempts", r.state["tasks"]["a"]["reason"])
        self.assertEqual(self.git("log", "--format=%s").strip(), "init")

    def test_same_gate_output_twice_stops_early(self):
        r = self.plan('''
            [[task]]
            id = "a"
            prompt = "p"
            gate = "echo took 12 ms; echo same failure; false"
            review = false
            ''', {"implement": [self.OK]}, defaults="max_attempts = 9")
        self.assertEqual(r.run(), ERROR)
        self.assertEqual(r.state["tasks"]["a"]["attempt"], 2)
        self.assertIn("no progress", r.state["tasks"]["a"]["reason"])

    def test_protected_files_are_restored_and_the_attempt_does_not_pass(self):
        r = self.plan('''
            [[task]]
            id = "a"
            prompt = "p"
            gate = "test -f a.txt"
            review = false
            ''', {"implement": [{**self.OK, "write": {"a.txt": "a", "fixtures/golden.txt": "edited", "fixtures/new.txt": "x"}},
                                {**self.OK, "write": {"a.txt": "a"}}]}, defaults='protected = ["fixtures/*"]')
        self.assertEqual(r.run(), DONE)
        with open(os.path.join(self.root, "fixtures/golden.txt")) as f:
            self.assertEqual(f.read(), "reviewed\n")
        self.assertFalse(os.path.exists(os.path.join(self.root, "fixtures/new.txt")))
        self.assertIn("fixtures/golden.txt", self.prompt("implement", 1))
        self.assertEqual(self.git("show", "--name-only", "--format=").split(), ["a.txt"])

    def test_review_rejection_loops_back_and_only_a_boolean_verdict_counts(self):
        r = self.plan('''
            [[task]]
            id = "a"
            prompt = "p"
            gate = "test -f a.txt"
            ''', {"implement": [{**self.OK, "write": {"a.txt": "1"}}, {**self.OK, "write": {"a.txt": "2"}}],
                  "review": [{"say": {"approved": False, "reasons": ["special-cases the test input"]}},
                             {"say": {"verdict": "APPROVED, looks great"}}, self.APPROVE]})
        self.assertEqual(r.run(), DONE)
        self.assertIn("special-cases the test input", self.prompt("implement", 1))
        with open(os.path.join(self.side, "calls-review")) as f:
            self.assertEqual(f.read(), "3")                      # the prose "APPROVED" was not accepted

    def test_reviewer_that_edits_the_tree_fails_the_task(self):
        r = self.plan('''
            [[task]]
            id = "a"
            prompt = "p"
            gate = "test -f a.txt"
            ''', {"implement": [{**self.OK, "write": {"a.txt": "1"}}],
                  "review": [{**self.APPROVE, "write": {"a.txt": "tampered"}}]})
        self.assertEqual(r.run(), ERROR)
        self.assertIn("reviewer changed", r.state["tasks"]["a"]["reason"])

    def test_blocked_and_human_review_stop_with_255_and_resume_from_disk(self):
        r = self.plan('''
            [[task]]
            id = "a"
            prompt = "p"
            gate = "test -f a.txt"
            human_review = true
            [[task]]
            id = "b"
            prompt = "p"
            gate = "true"
            ''', {"implement": [{**self.OK, "write": {"a.txt": "1"}}, {"say": {"outcome": "blocked", "notes": "spec is missing"}}],
                  "review": [self.APPROVE]})
        self.assertEqual(r.run(), HUMAN)
        self.assertEqual(self.git("log", "--format=%s").strip(), "init")     # nothing committed before approval
        cli = [sys.executable, os.path.join(os.path.dirname(HERE), "runner.py")]
        plan = os.path.join(self.tmp.name, "plan.toml")
        self.assertEqual(subprocess.run(cli + ["approve", plan, "a"], capture_output=True).returncode, 0)
        p = subprocess.run(cli + ["run", plan], capture_output=True, text=True)   # a new process: state is on disk
        self.assertEqual(p.returncode, 255)
        self.assertIn("spec is missing", p.stdout)
        self.assertIn("a  ", subprocess.run(cli + ["status", plan], capture_output=True, text=True).stdout)
        self.assertEqual(self.git("log", "--format=%s").split("\n")[0], "a")

    def test_agent_error_starts_a_clean_session_and_dirty_tree_is_refused(self):
        r = self.plan('''
            [[task]]
            id = "a"
            prompt = "p"
            gate = "test -f a.txt"
            review = false
            ''', {"implement": [{"exit": 3}, {**self.OK, "write": {"a.txt": "1"}}]})
        self.write("stray.txt", "mine")
        self.assertEqual(r.next(), ERROR)
        self.assertIn("uncommitted changes", self.logs[-1])
        os.remove(os.path.join(self.root, "stray.txt"))
        self.assertEqual(r.run(), DONE)
        self.assertIn("ended with an error", self.prompt("implement", 1))

    def test_plan_validation(self):
        for body, needle in (('[[task]]\nid = "a"\nprompt = "p"', "needs a 'gate'"),
                             ('[[task]]\nid = "a"\nprompt = "p"\ngate = "true"\nneeds = ["zz"]', "unknown task 'zz'"),
                             ('[[task]]\nid = "a"\nprompt = "p"\ngate = "true"\nagent = "nope"', "not defined"),
                             ('[[task]]\nid = "a"\nprompt = "p"\ngate = "true"\nneeds = ["a"]', "cycle"),
                             ('[[task]]\nid = "a"\ngate = "true"\ntimeuot = 3', "unknown key 'timeuot'")):
            with self.assertRaises(tasks.PlanError) as cm:
                self.plan(body, {})
            self.assertIn(needle, str(cm.exception))


class AdapterTest(unittest.TestCase):
    KW = dict(schema_path="/s.json", schema={"type": "object"}, session_id=None, model="m", budget_usd=2.5,
              read_only=False, last_message_path="/last.txt")

    def test_claude_command_line_and_result(self):
        a = agents.make("claude", {})
        argv = a.argv(**self.KW)
        self.assertEqual(argv[:4], ["claude", "-p", "--output-format", "json"])
        for flag in ("--json-schema", "--max-budget-usd", "--model", "--permission-mode"):
            self.assertIn(flag, argv)
        self.assertIn("--resume", a.argv(**{**self.KW, "session_id": "S"}))
        self.assertIn("--disallowedTools", a.argv(**{**self.KW, "read_only": True}))
        r = a.parse(0, json.dumps({"type": "result", "is_error": False, "result": "hi", "session_id": "S",
                                   "total_cost_usd": 0.12, "structured_output": {"outcome": "done", "notes": ""},
                                   "usage": {"input_tokens": 5, "output_tokens": 7}}), "", "")
        self.assertEqual((r.ok, r.session_id, r.cost_usd, r.structured["outcome"], r.tokens), (True, "S", 0.12, "done", {"in": 5, "out": 7}))
        self.assertFalse(a.parse(1, json.dumps({"is_error": True, "subtype": "error_max_budget_usd"}), "", "").ok)
        self.assertFalse(a.parse(1, "not json", "boom", "").ok)

    def test_codex_command_line_and_events(self):
        a = agents.make("codex", {})
        argv = a.argv(**self.KW)
        self.assertEqual(argv[:2], ["codex", "exec"])
        self.assertIn('sandbox_mode="workspace-write"', argv)
        self.assertEqual(argv[-1], "-")
        self.assertEqual(a.argv(**{**self.KW, "session_id": "T"})[2:4], ["resume", "T"])
        self.assertIn('sandbox_mode="read-only"', a.argv(**{**self.KW, "read_only": True}))
        out = "\n".join(json.dumps(e) for e in (
            {"type": "thread.started", "thread_id": "T1"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": '{"approved": true, "reasons": []}'}},
            {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}))
        r = a.parse(0, out, "", "/nonexistent")
        self.assertEqual((r.ok, r.session_id, r.cost_usd, r.tokens), (True, "T1", None, {"in": 10, "out": 2}))
        self.assertEqual(agents.last_json_object(r.text), {"approved": True, "reasons": []})
        self.assertFalse(a.parse(0, json.dumps({"type": "turn.failed", "error": {"message": "x"}}), "", "/nonexistent").ok)

    def test_timeout_kills_the_agent(self):
        with tempfile.TemporaryDirectory() as d:
            a = agents.make("slow", {"slow": {"type": "command", "argv": [sys.executable, "-c", "import time; time.sleep(60)"]}})
            r = a.run("p", cwd=d, log_dir=os.path.join(d, "log"), timeout_s=1)
            self.assertTrue(r.timed_out)
            self.assertFalse(r.ok)
            self.assertLess(r.seconds, 15)


if __name__ == "__main__":
    unittest.main(verbosity=2)
