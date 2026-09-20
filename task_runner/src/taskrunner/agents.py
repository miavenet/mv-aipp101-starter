"""Agents: one interface, and an adapter per kind of command-line agent (05, Agent interface).

Stage 3 ships the `command` adapter. The Claude Code and Codex adapters arrive in stage 4 and plug
into REGISTRY by their kind. An adapter builds the command line, runs it under the runner's clock
with streamed and redacted logs, and says whether the call completed properly. It reports facts;
the engine decides what follows.
"""

import json
import os

from . import proc, record

OK, ENVIRONMENT, PROTOCOL_ERROR, AGENT_ERROR, TIMED_OUT, INTERRUPTED = (
    "ok", "environment", "protocol-error", "agent-error", "timed-out", "interrupted")


class AgentResult:
    def __init__(self, status, text="", structured=None, session_id=None, cost_usd=None,
                 usage=None, error="", seconds=0.0):
        self.status, self.text, self.structured = status, text, structured
        self.session_id, self.cost_usd, self.usage = session_id, cost_usd, usage or {}
        self.error, self.seconds = error, seconds

    def outcome(self):
        return {"status": self.status, "error": self.error, "seconds": round(self.seconds, 3),
                "session_id": self.session_id, "cost_usd": self.cost_usd, "usage": self.usage}


def last_json_object(text):
    """The last JSON object in `text` that is followed by nothing but white space, or None."""
    decoder = json.JSONDecoder()
    start = len(text)
    while True:
        start = text.rfind("{", 0, start)
        if start < 0:
            return None
        try:
            obj, end = decoder.raw_decode(text, start)
        except ValueError:
            continue
        if isinstance(obj, dict) and not text[end:].strip():
            return obj


class Agent:
    """What every adapter offers. `profile` is the [agents.NAME] table of the workflow."""

    kind = ""
    reports_cost = False

    def __init__(self, name, profile):
        self.name, self.profile = name, dict(profile)

    def capabilities(self):
        """What this agent can be relied on for. Until `doctor` exists (stage 4) this is what the
        adapter supports by construction, not what was qualified on this host."""
        return set()

    def run(self, prompt, *, cwd, invocation_dir, schema, session_id, model, timeout_s,
            budget_usd, read_only, env, on_start=None):
        raise NotImplementedError


class CommandAgent(Agent):
    """Any command: the prompt on standard input, the answer the last JSON object on standard
    output. No sessions, no money limit, no tool events."""

    kind = "command"

    def capabilities(self):
        return {"answer", "read", "write", "execute"}

    def argv(self, read_only, session_id):
        return list(self.profile["argv"]) + (list(self.profile.get("read_only_args", []))
                                             if read_only else [])

    def run(self, prompt, *, cwd, invocation_dir, schema, session_id, model, timeout_s,
            budget_usd, read_only, env, on_start=None):
        argv = self.argv(read_only, session_id)
        record.write_durable(os.path.join(invocation_dir, "argv.json"),
                             record.dump_json({"argv": argv, "cwd": cwd, "read_only": read_only,
                                               "model": model, "session_id": session_id}))
        record.write_durable(os.path.join(invocation_dir, "schema.json"), record.dump_json(schema))
        res = proc.run_process(argv, cwd=cwd, env=env, stdin_data=prompt.encode("utf-8"),
                               stdout_path=os.path.join(invocation_dir, "stdout.log"),
                               stderr_path=os.path.join(invocation_dir, "stderr.log"),
                               timeout_s=timeout_s, on_start=on_start)
        result = self.interpret(res)
        with open(os.path.join(invocation_dir, "last-message.txt"), "w", encoding="utf-8") as fh:
            fh.write(result.text)
        return result

    def interpret(self, res):
        if res.status == "not-started":
            return AgentResult(ENVIRONMENT, error=f"the agent could not be started: {res.error}")
        text = res.stdout_tail.decode("utf-8", errors="replace")
        if res.status == "timed-out":
            return AgentResult(TIMED_OUT, text=text, error="the call ran past its time limit",
                               seconds=res.seconds)
        if res.returncode != 0:
            tail = res.stderr_tail.decode("utf-8", errors="replace")[-2000:]
            return AgentResult(AGENT_ERROR, text=text, seconds=res.seconds,
                               error=f"the agent exited with status {res.returncode}: {tail}".strip())
        answer = last_json_object(text)
        if answer is None:
            return AgentResult(PROTOCOL_ERROR, text=text, seconds=res.seconds,
                               error="the output does not end with a JSON object")
        return AgentResult(OK, text=text, structured=answer, seconds=res.seconds)


REGISTRY = {"command": CommandAgent}


class UnknownAgent(Exception):
    pass


def make(name, profile):
    kind = profile.get("kind", name)
    if kind not in REGISTRY:
        raise UnknownAgent(f"agent '{name}' is of kind '{kind}', whose adapter arrives in stage 4; "
                           "stage 3 drives `command` agents only")
    return REGISTRY[kind](name, profile)


def agent_env(base, run_id, task_id, run_dir=None):
    """The environment of an agent call. The record's path goes only to types that ask for it."""
    env = {k: v for k, v in base.items() if k != "TASK_RUNNER_RUN_DIR"}
    env.update(TASK_RUNNER_RUN=run_id, TASK_RUNNER_TASK=task_id)
    if run_dir:
        env["TASK_RUNNER_RUN_DIR"] = run_dir
    return env
