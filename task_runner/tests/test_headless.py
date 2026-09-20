"""Stage 4 headless adapter contracts (AGENT-01 to AGENT-12). No model calls."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import helpers
from taskrunner import agents, proc, validate

FIXTURES = Path(__file__).parent / "recorded"

def result(stdout=b"", stderr=b"", code=0, status="exited"):
    return proc.ProcResult(status, code, stdout, stderr, 1.0, None)

class Headless(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def test_claude_command_lines(self):
        a = agents.make("author", {"kind": "claude"})
        argv = a.build_argv(self.root, validate.PRODUCE, "session-id", "chosen-model", 2.5, True)
        for word in ["-p", "--json-schema", "--max-budget-usd", "2.5", "--resume", "session-id",
                     "--disallowedTools", "--permission-prompts", "none", "auto", "chosen-model"]:
            self.assertIn(word, argv)
        self.assertNotIn("--dangerously-skip-permissions", argv)
        self.assertNotIn("--setting-sources", argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "Read,Glob,Grep")
        self.assertEqual(argv[argv.index("--mcp-config") + 1], '{"mcpServers":{}}')
        self.assertIn("--strict-mcp-config", argv)
        writer = a.build_argv(self.root, validate.PRODUCE, None, "chosen-model", 2.5, False)
        self.assertNotIn("--tools", writer)
        self.assertNotIn("--disallowedTools", writer)

    def test_codex_command_lines(self):
        a = agents.make("writer", {"kind": "codex"})
        for sid in (None, "explicit-id"):
            argv = a.build_argv(self.root, validate.PRODUCE, sid, "chosen-model", 1, bool(sid))
            self.assertEqual(argv[:2], ["codex", "exec"])
            if sid:
                self.assertEqual(argv[2], "resume")
                self.assertIn(sid, argv)
            self.assertIn('approval_policy="never"', argv)
            self.assertIn('sandbox_mode="read-only"' if sid else 'sandbox_mode="workspace-write"', argv)
            self.assertIn("--output-schema", argv)
            self.assertEqual(argv[-1], "-")
            for forbidden in ("--last", "--skip-git-repo-check", "--sandbox", "--dangerously-bypass-approvals-and-sandbox"):
                self.assertNotIn(forbidden, argv)

    def test_ignore_config_is_explicit(self):
        for kind, flag in (("codex", "--ignore-user-config"), ("claude", "--setting-sources")):
            a = agents.make(kind, {"kind": kind, "ignore_user_config": True})
            self.assertIn(flag, a.build_argv(self.root, validate.PRODUCE, None, "", 1, False))

    def test_claude_recorded_result(self):
        a = agents.make("claude", {"kind": "claude"})
        r = a.interpret(result((FIXTURES / "claude-success.json").read_bytes()))
        self.assertEqual(r.status, agents.OK)
        self.assertEqual(r.structured["outcome"], "done")
        self.assertTrue(r.session_id)
        self.assertGreater(r.cost_usd, 0)
        self.assertGreater(r.usage["tokens_in"], 0)
        for data in ({"type": "result", "subtype": "error_max_budget_usd", "is_error": True},
                     {"type": "result", "subtype": "success", "is_error": True}):
            self.assertEqual(a.interpret(result(json.dumps(data).encode())).status, agents.AGENT_ERROR)
        self.assertEqual(a.interpret(result(b"not JSON")).status, agents.PROTOCOL_ERROR)

    def test_missing_usage_is_unknown_and_nonfinite_cost_is_not_money(self):
        claude = {"type":"result", "is_error":False, "subtype":"success",
                  "structured_output":{"outcome":"done"}, "total_cost_usd":float('nan')}
        r = agents.make("claude", {"kind":"claude"}).interpret(result(json.dumps(claude).encode()))
        self.assertEqual(r.usage, {})
        self.assertIsNone(r.cost_usd)
        codex = b'{"type":"item.completed","item":{"type":"agent_message","text":"{}"}}\n{"type":"turn.completed"}'
        self.assertEqual(agents.make("codex", {"kind":"codex"}).interpret(result(codex)).usage, {})

    def test_claude_json_fallback(self):
        data = {"type": "result", "subtype": "success", "is_error": False,
                "result": 'Some prose. {"outcome":"done"}'}
        a = agents.make("claude", {"kind": "claude"})
        self.assertEqual(a.interpret(result(json.dumps(data).encode())).structured, {"outcome": "done"})

    def test_codex_recorded_result(self):
        a = agents.make("codex", {"kind": "codex"})
        r = a.interpret(result((FIXTURES / "codex-review.jsonl").read_bytes()))
        self.assertEqual(r.status, agents.OK)
        self.assertFalse(r.structured["approved"])
        self.assertEqual(r.usage["tokens_in"], 14592)
        self.assertIsNone(r.cost_usd)
        self.assertTrue(r.session_id)

    def test_sandbox_startup_is_an_environment_failure(self):
        a = agents.make("codex", {"kind": "codex"})
        r = a.interpret(result((FIXTURES / "codex-sandbox-failure.jsonl").read_bytes()))
        self.assertEqual(r.status, agents.ENVIRONMENT)
        self.assertIn("namespace", r.error)

    def test_terminal_event_required(self):
        a = agents.make("codex", {"kind": "codex"})
        stream = (FIXTURES / "codex-review.jsonl").read_bytes()
        lines = stream.splitlines()
        self.assertEqual(a.interpret(result(b"\n".join(lines[:-1]))).status, agents.PROTOCOL_ERROR)
        self.assertEqual(a.interpret(result(b"")).status, agents.PROTOCOL_ERROR)
        failed = b'{"type":"turn.failed","error":{"message":"transport failed"}}'
        self.assertEqual(a.interpret(result(stream + failed)).status, agents.AGENT_ERROR)
        self.assertEqual(a.interpret(result(stream, code=1)).status, agents.AGENT_ERROR)

    def test_incomplete_later_turn_and_malformed_fields_are_protocol_errors(self):
        a = agents.make("codex", {"kind": "codex"})
        stream = (FIXTURES / "codex-review.jsonl").read_bytes()
        for suffix in (b'{"type":"turn.started"}', b'{"type":"item.completed","item":42}',
                       b'{"type":"turn.completed","usage":42}'):
            self.assertEqual(a.interpret(result(stream + suffix)).status, agents.PROTOCOL_ERROR)
        malformed = {"type":"result", "is_error":False, "subtype":"success", "usage":{"input_tokens":"bad"}}
        self.assertEqual(agents.make("claude", {"kind":"claude"}).interpret(
            result(json.dumps(malformed).encode())).status, agents.PROTOCOL_ERROR)

    def test_tool_failure_is_ordinary_work(self):
        tool = {"type": "item.completed", "item": {"type": "command_execution", "exit_code": 1,
                "status": "failed", "aggregated_output": "FAILED test_expected_behavior"}}
        stream = json.dumps(tool).encode() + b"\n" + (FIXTURES / "codex-review.jsonl").read_bytes()
        self.assertEqual(agents.make("codex", {"kind": "codex"}).interpret(result(stream)).status, agents.OK)

    def test_usage_is_summed_and_unknown_events_survive(self):
        stream = (FIXTURES / "codex-review.jsonl").read_bytes()
        stream += b'{"type":"future.event","value":1}\n'
        stream += b'{"type":"turn.completed","usage":{"input_tokens":3,"output_tokens":4}}\n'
        r = agents.make("codex", {"kind": "codex"}).interpret(result(stream))
        self.assertEqual(r.usage["tokens_in"], 14595)
        self.assertEqual(r.usage["tokens_out"], 104)

    def call_script(self, output, schema=validate.PRODUCE):
        inv = Path(self.root) / "inv"
        inv.mkdir()
        script = Path(self.root) / "replay.py"
        script.write_text("print(" + repr(output) + ")")
        a = agents.make("test", {"kind": "codex", "argv": [sys.executable, str(script)]})
        return a.run("prompt", cwd=self.root, invocation_dir=str(inv), schema=schema, session_id=None,
                     model="", timeout_s=5, budget_usd=1, read_only=False, env=dict(os.environ))

    def test_local_schema_validation(self):
        for answer in (42, {"outcome": "done"}, dict(helpers.done(), extra=True), dict(helpers.done(), summary=True)):
            with self.subTest(answer=answer), tempfile.TemporaryDirectory() as root:
                self.root = root
                stream = json.dumps({"type":"item.completed","item":{"type":"agent_message","text":json.dumps(answer)}})
                stream += '\n{"type":"turn.completed"}'
                self.assertEqual(self.call_script(stream).status, agents.PROTOCOL_ERROR)

    def test_fresh_invocation_refuses_stale_final_message(self):
        inv = Path(self.root) / "inv"
        inv.mkdir()
        (inv / "last-message.txt").write_text(json.dumps(helpers.done()))
        a = agents.make("codex", {"kind": "codex"})
        with self.assertRaises(agents.InvocationError):
            a.run("p", cwd=self.root, invocation_dir=str(inv), schema=validate.PRODUCE,
                  session_id=None, model="", timeout_s=5, budget_usd=1, read_only=False, env=dict(os.environ))

    def test_stream_parser_keeps_early_environment_failure(self):
        stream = (FIXTURES / "codex-sandbox-failure.jsonl").read_text()
        stream += '\n'.join(json.dumps({"type":"future.event","text":"x"*1000}) for _ in range(500))
        r = self.call_script(stream)
        self.assertEqual(r.status, agents.ENVIRONMENT)

if __name__ == "__main__":
    unittest.main()
