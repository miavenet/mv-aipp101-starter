#!/usr/bin/env python3
"""Tests for log-hook.py. Run: python3 .claude/hooks/test_log_hook.py"""

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log-hook.py")


class LogHookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "logs")
        self.env = {**os.environ, "HOOK_LOG_DIR": self.dir, "CLAUDE_CODE_MESSAGING_TOKEN": "hunter2hunter2"}

    def tearDown(self):
        self.tmp.cleanup()

    def fire(self, payload, env=None, args=()):
        data = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run([sys.executable, "-S", "-E", HOOK, *args], input=data, text=True,
                              capture_output=True, env={**self.env, **(env or {})})

    def records(self):
        with open(os.path.join(self.dir, "hooks.jsonl")) as f:
            return [json.loads(line) for line in f]

    def test_passive_even_on_garbage(self):
        for payload in ("not json", "", "[1,2]", {"hook_event_name": "Stop"}):
            p = self.fire(payload)
            self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))
        recs = self.records()
        self.assertEqual([r["seq"] for r in recs], [1, 2, 3, 4])
        self.assertIn("parse_error", recs[0])
        self.assertFalse(os.path.exists(os.path.join(self.dir, "errors.log")))

    def test_tool_and_turn_timing_per_session(self):
        self.fire({"hook_event_name": "UserPromptSubmit", "session_id": "A", "prompt": "hi"})
        self.fire({"hook_event_name": "PreToolUse", "session_id": "A", "tool_name": "Bash", "tool_use_id": "t1",
                   "tool_input": {"command": "ls"}})
        # Another session must not disturb session A's timing state.
        self.fire({"hook_event_name": "UserPromptSubmit", "session_id": "B", "prompt": "other"})
        self.fire({"hook_event_name": "PostToolUse", "session_id": "A", "tool_name": "Bash", "tool_use_id": "t1",
                   "duration_ms": 42, "tool_response": {"stdout": "x"}})
        # A subagent Stop must not end the main agent's turn.
        self.fire({"hook_event_name": "Stop", "session_id": "A", "agent_id": "sub1"})
        self.fire({"hook_event_name": "Stop", "session_id": "A"})
        recs = self.records()
        post = recs[3]["derived"]
        self.assertEqual(post["tool_duration_ms"], 42)
        self.assertGreater(post["pre_to_post_ms"], 0)
        self.assertNotIn("since_prev_hook_ms", recs[2]["derived"])  # first call of session B
        self.assertNotIn("turn_duration_s", recs[4]["derived"])
        self.assertIn("turn_duration_s", recs[5]["derived"])

    def test_secrets_redacted(self):
        self.fire({"hook_event_name": "PostToolUse", "session_id": "A", "tool_name": "Read",
                   "tool_input": {"file_path": ".env", "api_key": "abc123456"},
                   "tool_response": {"content": "OPENROUTER_API_KEY=sk-or-v1-abcdefghijklmnopqrstuvwxyz\nDEBUG=true\n"
                                                "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123"}})
        self.fire({"hook_event_name": "UserPromptSubmit", "session_id": "A",
                   "prompt": "use ghp_abcdefghijklmnopqrstuvwxyz0123456789"})
        blob = "".join(open(os.path.join(self.dir, f)).read() for f in os.listdir(self.dir))
        for secret in ("sk-or-v1", "abc123456", "hunter2", "ghp_abcdef", "abcdefghijklmnopqrstuvwxyz0123"):
            self.assertNotIn(secret, blob)
        self.assertIn("DEBUG=true", blob)

    def test_env_logged_only_on_change(self):
        for _ in range(3):
            self.fire({"hook_event_name": "Notification", "session_id": "A"})
        self.fire({"hook_event_name": "Notification", "session_id": "A"}, env={"CLAUDE_TEST_MARKER": "changed"})
        self.assertEqual(["env" in r for r in self.records()], [True, False, False, True])

    def test_truncation_skip_and_rotation(self):
        big = {"hook_event_name": "PreToolUse", "session_id": "A", "tool_name": "Write",
               "tool_input": {"content": "x" * 50000}}
        self.fire(big)
        content = self.records()[0]["payload"]["tool_input"]["content"]
        self.assertLess(len(content), 17000)
        self.assertIn("50000 chars total", content)
        self.fire(big, env={"HOOK_LOG_MAX_STR": "0"})
        self.assertEqual(len(self.records()[1]["payload"]["tool_input"]["content"]), 50000)
        self.fire({"hook_event_name": "MessageDisplay"}, env={"HOOK_LOG_SKIP": "MessageDisplay"})
        self.assertEqual(len(self.records()), 2)
        self.fire({"hook_event_name": "Stop"}, env={"HOOK_LOG_MAX_BYTES": "1000"})
        self.assertTrue(os.path.exists(os.path.join(self.dir, "hooks.jsonl.1")))
        self.assertEqual([r["seq"] for r in self.records()], [3])

    def test_concurrent_calls_keep_unique_seq_and_valid_json(self):
        with ThreadPoolExecutor(16) as pool:
            list(pool.map(lambda i: self.fire({"hook_event_name": "PreToolUse", "session_id": "A",
                                               "tool_use_id": f"t{i}", "tool_name": "Bash"}), range(40)))
        self.assertEqual(sorted(r["seq"] for r in self.records()), list(range(1, 41)))

    def test_statusline_snapshot_attached_with_deltas(self):
        def snapshot(cost, tokens):
            d = os.path.join(self.dir, "sessions", "A")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "statusline.json"), "w") as f:
                json.dump({"captured_ms": 1000, "statusline": {
                    "model": {"id": "m"}, "cost": {"total_cost_usd": cost},
                    "context_window": {"used_percentage": 25, "current_usage": {
                        "input_tokens": 2, "output_tokens": 99, "cache_read_input_tokens": tokens}}}}, f)
        snapshot(1.0, 1000)
        self.fire({"hook_event_name": "PreToolUse", "session_id": "A"})
        snapshot(1.25, 1500)
        self.fire({"hook_event_name": "PostToolUse", "session_id": "A"})
        self.fire({"hook_event_name": "Stop", "session_id": "B"})  # no snapshot for B
        a, b, c = self.records()
        self.assertEqual((a["statusline"]["ctx_used_pct"], a["statusline"]["ctx_tokens"]), (25, 1002))
        self.assertEqual([a["statusline"][k] for k in ("tok_in", "tok_cache_read", "tok_out")], [2, 1000, 99])
        self.assertNotIn("cost_delta_usd", a["statusline"])
        self.assertEqual((b["statusline"]["cost_delta_usd"], b["statusline"]["ctx_delta_tokens"]), (0.25, 500))
        self.assertGreater(b["statusline"]["age_ms"], 0)
        self.assertNotIn("statusline", c)

    def test_permissions_and_cli(self):
        self.fire({"hook_event_name": "PostToolBatch", "session_id": "A",
                   "tool_calls": [{"tool_name": "Bash"}, {"tool_name": "Read"}]})
        self.assertEqual(stat.S_IMODE(os.stat(self.dir).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.dir, "hooks.jsonl")).st_mode), 0o600)
        self.assertIn("batch of 2: Bash,Read", self.fire("", args=("--tail",)).stdout)
        self.assertIn("PostToolBatch", self.fire("", args=("--summary",)).stdout)
        self.assertEqual(json.loads(self.fire("", args=("--show", "1")).stdout)["seq"], 1)
        self.fire("", args=("--reset",))
        self.assertIn("No log yet", self.fire("", args=("--summary",)).stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
