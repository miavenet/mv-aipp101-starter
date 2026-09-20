"""Agent adapters. Each one runs a coding agent headless and returns the same AgentResult.

Built in: claude (Claude Code), codex (Codex CLI), and command (any program that reads a prompt
on stdin and prints its answer). Flags were checked against claude 2.1.278 and codex-cli 0.155.1.
"""

import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field

INT_GRACE_S, TERM_GRACE_S = 20, 5


@dataclass
class AgentResult:
    ok: bool
    text: str = ""
    structured: dict | None = None
    session_id: str | None = None
    cost_usd: float | None = None      # None when the agent does not report cost
    tokens: dict = field(default_factory=dict)
    error: str = ""
    timed_out: bool = False
    seconds: float = 0.0


def run_process(argv, stdin_text, cwd, timeout_s, env=None):
    """Run with a wall clock the runner owns: SIGINT first so the agent can end its turn, then harder."""
    start = time.monotonic()
    try:
        p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, cwd=cwd, env=env, start_new_session=True)
    except OSError as e:
        return None, "", str(e), False, 0.0
    timed_out = False
    try:
        out, err = p.communicate(stdin_text, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        out = err = ""
        for sig, grace in ((signal.SIGINT, INT_GRACE_S), (signal.SIGTERM, TERM_GRACE_S), (signal.SIGKILL, None)):
            try:
                os.killpg(p.pid, sig)
            except ProcessLookupError:
                pass
            try:
                out, err = p.communicate(timeout=grace)
                break
            except subprocess.TimeoutExpired:
                continue
    return p.returncode, out or "", err or "", timed_out, time.monotonic() - start


def last_json_object(text):
    """The last top-level {...} in the text that parses. Lets any agent answer in JSON without a schema flag."""
    dec, best, i = json.JSONDecoder(), None, text.find("{")
    while i != -1:
        try:
            obj, end = dec.raw_decode(text, i)
            if isinstance(obj, dict):
                best = obj
            i = text.find("{", end)
        except ValueError:
            i = text.find("{", i + 1)
    return best


class Agent:
    kind = "base"

    def __init__(self, name, conf=None):
        self.name, self.conf = name, conf or {}

    def argv(self, *, schema_path, schema, session_id, model, budget_usd, read_only, last_message_path):
        raise NotImplementedError

    def parse(self, code, out, err, last_message_path):
        raise NotImplementedError

    def run(self, prompt, *, cwd, log_dir, schema=None, session_id=None, model="", timeout_s=1800,
            budget_usd=0.0, read_only=False):
        os.makedirs(log_dir, exist_ok=True)
        schema_path = os.path.join(log_dir, "schema.json")
        last_path = os.path.join(log_dir, "last-message.txt")
        if schema:
            with open(schema_path, "w") as f:
                json.dump(schema, f)
            prompt += ("\n\nFinish with a single JSON object, and nothing after it, matching this schema:\n"
                       + json.dumps(schema))
        argv = self.argv(schema_path=schema_path if schema else None, schema=schema, session_id=session_id,
                         model=model or self.conf.get("model", ""), budget_usd=budget_usd, read_only=read_only,
                         last_message_path=last_path)
        with open(os.path.join(log_dir, "prompt.md"), "w") as f:
            f.write(prompt)
        with open(os.path.join(log_dir, "argv.json"), "w") as f:
            json.dump(argv, f)
        code, out, err, timed_out, secs = run_process(argv, prompt, cwd, timeout_s)
        with open(os.path.join(log_dir, "stdout.log"), "w") as f:
            f.write(out)
        with open(os.path.join(log_dir, "stderr.log"), "w") as f:
            f.write(err)
        if code is None:
            return AgentResult(False, error=f"cannot start {argv[0]}: {err}")
        r = self.parse(code, out, err, last_path)
        r.timed_out, r.seconds = timed_out, round(secs, 1)
        if timed_out:
            r.ok, r.error = False, f"timed out after {timeout_s}s"
        if schema and r.structured is None:
            r.structured = last_json_object(r.text)
        return r


class ClaudeCode(Agent):
    kind = "claude"

    def argv(self, *, schema_path, schema, session_id, model, budget_usd, read_only, last_message_path):
        a = [self.conf.get("bin", "claude"), "-p", "--output-format", "json"]
        a += self.conf.get("permission_args", ["--permission-mode", "auto", "--permission-prompts", "none"])
        if read_only:
            a += ["--disallowedTools", "Edit", "Write", "NotebookEdit"]
        if schema:
            a += ["--json-schema", json.dumps(schema)]
        if budget_usd:
            a += ["--max-budget-usd", str(budget_usd)]
        if model:
            a += ["--model", model]
        if session_id:
            a += ["--resume", session_id]
        return a + list(self.conf.get("args", []))

    def parse(self, code, out, err, last_message_path):
        try:
            doc = json.loads(out)
            if isinstance(doc, list):          # tolerate an event array: the result is the last entry
                doc = [d for d in doc if isinstance(d, dict) and d.get("type") == "result"][-1]
        except (ValueError, IndexError):
            return AgentResult(False, text=out, error=f"exit {code}, output was not JSON: {(err or out)[-400:]}")
        usage = doc.get("usage") or {}
        structured = doc.get("structured_output")
        failed = code != 0 or doc.get("is_error")
        return AgentResult(
            ok=not failed, text=str(doc.get("result") or ""),
            structured=structured if isinstance(structured, dict) else None,
            session_id=doc.get("session_id"), cost_usd=doc.get("total_cost_usd"),
            tokens={"in": usage.get("input_tokens", 0), "out": usage.get("output_tokens", 0)},
            error=f"{doc.get('subtype', 'error')}: {doc.get('result') or doc.get('errors') or ''}"[:600] if failed else "")


class Codex(Agent):
    kind = "codex"

    def argv(self, *, schema_path, schema, session_id, model, budget_usd, read_only, last_message_path):
        sandbox = "read-only" if read_only else self.conf.get("sandbox", "workspace-write")
        a = [self.conf.get("bin", "codex"), "exec"]
        if session_id:
            a += ["resume", session_id]
        a += ["--json", "--skip-git-repo-check", "-c", f'sandbox_mode="{sandbox}"', "-o", last_message_path]
        if schema_path:
            a += ["--output-schema", schema_path]
        if model:
            a += ["-m", model]
        return a + list(self.conf.get("args", [])) + ["-"]     # "-": the prompt comes on stdin

    def parse(self, code, out, err, last_message_path):
        sid, text, problem, tokens = None, "", "", {"in": 0, "out": 0}
        for line in out.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            kind = ev.get("type")
            if kind == "thread.started":
                sid = ev.get("thread_id")
            elif kind == "item.completed" and (ev.get("item") or {}).get("type") == "agent_message":
                text = ev["item"].get("text", "")
            elif kind == "turn.completed":
                u = ev.get("usage") or {}
                tokens["in"] += u.get("input_tokens", 0)
                tokens["out"] += u.get("output_tokens", 0)
            elif kind in ("turn.failed", "error"):
                problem = json.dumps(ev.get("error") or ev.get("message") or ev)[:600]
        try:
            with open(last_message_path) as f:
                text = f.read() or text
        except OSError:
            pass
        failed = code != 0 or bool(problem)
        return AgentResult(ok=not failed, text=text, session_id=sid, tokens=tokens,
                           error=(problem or f"exit {code}: {err[-400:]}") if failed else "")


class Command(Agent):
    """Any other agent: `argv` is run, the prompt goes to stdin, stdout is the answer."""
    kind = "command"

    def argv(self, *, schema_path, schema, session_id, model, budget_usd, read_only, last_message_path):
        a = list(self.conf["argv"])
        if read_only:
            a += list(self.conf.get("read_only_args", []))
        if model:
            a += [x.replace("{model}", model) for x in self.conf.get("model_args", [])]
        return a

    def parse(self, code, out, err, last_message_path):
        return AgentResult(ok=code == 0, text=out, error="" if code == 0 else f"exit {code}: {err[-400:]}")


KINDS = {"claude": ClaudeCode, "codex": Codex, "command": Command}


def make(name, agents_conf):
    conf = dict(agents_conf.get(name, {}))
    kind = conf.pop("type", name if name in KINDS else "")
    if kind not in KINDS:
        raise ValueError(f"agent '{name}': set type to one of {sorted(KINDS)}")
    if kind == "command" and not conf.get("argv"):
        raise ValueError(f"agent '{name}': a command agent needs 'argv'")
    return KINDS[kind](name, conf)
