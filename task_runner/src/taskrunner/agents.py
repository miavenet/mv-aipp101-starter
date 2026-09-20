"""Agents: one interface, and an adapter per kind of command-line agent (05, Agent interface).

The command, Claude Code and Codex adapters plug into REGISTRY by their kind. An adapter builds the command line, runs it under the runner's clock
with streamed and redacted logs, and says whether the call completed properly. It reports facts;
the engine decides what follows.
"""

import json
import math
import os

from . import proc, record, validate

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
        claim_invocation(invocation_dir)
        argv = self.argv(read_only, session_id)
        record.write_durable(os.path.join(invocation_dir, "argv.json"),
                             proc.redact(record.dump_json({"argv": argv, "cwd": cwd, "read_only": read_only,
                                               "model": model, "session_id": session_id})))
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
        raise UnknownAgent(f"agent '{name}' has unsupported kind '{kind}'")
    return REGISTRY[kind](name, profile)


def agent_env(base, run_id, task_id, run_dir=None):
    """The environment of an agent call. The record's path goes only to types that ask for it."""
    env = {k: v for k, v in base.items() if k != "TASK_RUNNER_RUN_DIR"}
    env.update(TASK_RUNNER_RUN=run_id, TASK_RUNNER_TASK=task_id)
    if run_dir:
        env["TASK_RUNNER_RUN_DIR"] = run_dir
    return env


class InvocationError(Exception):
    """An invocation directory must be fresh; stale output is never evidence."""


def claim_invocation(path):
    if any(os.path.exists(os.path.join(path, name)) for name in
           ("last-message.txt", "stdout.log", "stderr.log", "final.raw")):
        raise InvocationError("the invocation directory contains output from an earlier call")
    try:
        with open(os.path.join(path, ".adapter-started"), "x"):
            pass
    except FileExistsError as exc:
        raise InvocationError("this invocation directory has already been used") from exc


# Match failures of the execution/authentication machinery, not ordinary failing tests.
ENVIRONMENT_MARKERS = (
    "bwrap: no permissions to create a new namespace", "sandbox failed to start",
    "failed to create sandbox", "unprivileged user namespaces are unavailable",
    "invalid api key", "invalid_api_key", "authentication failed", "not logged in",
    "unexpected argument", "unknown option", "invalid value for", "please run /login", "please run codex login", "error loading config", "invalid configuration",
)


def environment_error(text):
    if not isinstance(text, str):
        return ""
    return next((line[:2000] for line in text.splitlines()
                 if any(marker in line.lower() for marker in ENVIRONMENT_MARKERS)), "")


def process_failure(res):
    if res.status == "not-started":
        return AgentResult(ENVIRONMENT, error=res.error, seconds=res.seconds)
    if res.status == "timed-out":
        return AgentResult(TIMED_OUT, error="the call ran past its time limit", seconds=res.seconds)
    err = res.stderr_tail.decode("utf-8", errors="replace")
    env_error = environment_error(err)
    if env_error:
        return AgentResult(ENVIRONMENT, error=env_error, seconds=res.seconds)
    if res.returncode:
        return AgentResult(AGENT_ERROR, error=f"agent exited with status {res.returncode}: {err[-2000:]}",
                           seconds=res.seconds)
    return None


class CodexEvents:
    """Incremental reduction of redacted JSONL. Only the final message and counters are retained.
    Unknown events remain in stdout.log. Early environment/turn failures cannot scroll out."""
    def __init__(self):
        self.session_id = None
        self.text = ""
        self.completed = 0
        self.open_turn = False
        self.message_after_completion = False
        self.failed = ""
        self.environment = ""
        self.malformed = False
        self.has_usage = False
        self.usage = {"tokens_in": 0, "tokens_out": 0, "cached_tokens_in": 0}

    def feed(self, data):
        for line in data.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except (ValueError, UnicodeError):
                self.malformed = True
                continue
            if not isinstance(event, dict):
                self.malformed = True
                continue
            kind = event.get("type")
            if kind == "thread.started":
                self.session_id = event.get("thread_id")
                if not isinstance(self.session_id, str):
                    self.malformed = True
            elif kind == "turn.started":
                self.open_turn = True
            elif kind == "turn.completed":
                self.open_turn = False
                self.message_after_completion = False
                self.completed += 1
                for source, target in (("input_tokens", "tokens_in"), ("output_tokens", "tokens_out"),
                                       ("cached_input_tokens", "cached_tokens_in")):
                    usage = event.get("usage") or {}
                    if not isinstance(usage, dict):
                        self.malformed = True
                        continue
                    value = usage.get(source, 0)
                    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                        self.has_usage = self.has_usage or source in usage
                        self.usage[target] += value
            elif kind in ("turn.failed", "error"):
                self.failed = json.dumps(event.get("error", event.get("message", event)))[:2000]
                self.environment = environment_error(self.failed) or self.environment
            elif kind == "item.completed":
                item = event.get("item") or {}
                if not isinstance(item, dict):
                    self.malformed = True
                    continue
                if item.get("type") == "agent_message":
                    self.message_after_completion = bool(self.completed)
                    self.text = item.get("text", "")
                    if not isinstance(self.text, str):
                        self.text = ""
                        self.malformed = True
                elif item.get("type") == "command_execution" and item.get("exit_code") not in (None, 0):
                    self.environment = environment_error(item.get("aggregated_output", "")) or self.environment

    def result(self, res):
        failure = process_failure(res)
        if self.environment:
            failure = AgentResult(ENVIRONMENT, error=self.environment, seconds=res.seconds)
        if failure:
            failure.session_id, failure.usage = self.session_id, self.usage if self.has_usage else {}
            return failure
        status, error = OK, ""
        if self.failed:
            status, error = AGENT_ERROR, self.failed
        elif self.malformed or not self.completed or self.open_turn or self.message_after_completion:
            status, error = PROTOCOL_ERROR, "missing successful terminal event or malformed event stream"
        answer = last_json_object(self.text) if isinstance(self.text, str) else None
        if status == OK and answer is None:
            status, error = PROTOCOL_ERROR, "the final agent message is not a JSON object"
        return AgentResult(status, text=self.text, structured=answer, session_id=self.session_id,
                           usage=self.usage if self.has_usage else {}, error=error, seconds=res.seconds)


class HeadlessAgent(Agent):
    def capabilities(self):
        return {"answer", "read", "write", "execute", "resume"}

    def run(self, prompt, *, cwd, invocation_dir, schema, session_id, model, timeout_s,
            budget_usd, read_only, env, on_start=None):
        claim_invocation(invocation_dir)
        record.write_durable(os.path.join(invocation_dir, "schema.json"), record.dump_json(schema))
        argv = self.build_argv(invocation_dir, schema, session_id, model, budget_usd, read_only)
        record.write_durable(os.path.join(invocation_dir, "argv.json"), proc.redact(record.dump_json(
            {"argv": argv, "cwd": cwd, "read_only": read_only, "model": model, "session_id": session_id})))
        parser = CodexEvents() if self.kind == "codex" else None
        res = proc.run_process(argv, cwd=cwd, env=env, stdin_data=prompt.encode("utf-8"),
                               stdout_path=os.path.join(invocation_dir, "stdout.log"),
                               stderr_path=os.path.join(invocation_dir, "stderr.log"),
                               timeout_s=timeout_s, on_start=on_start,
                               on_stdout=parser.feed if parser else None)
        answer = parser.result(res) if parser else self.interpret(res)
        # Codex's output file is never used as a fallback for a missing terminal event.
        raw = os.path.join(invocation_dir, "final.raw")
        if os.path.lexists(raw):
            os.unlink(raw)
        if answer.status == OK and session_id and answer.session_id != session_id:
            answer.status, answer.error = PROTOCOL_ERROR, "resumed call returned a different session id"
        if answer.status == OK:
            errors = validate.check_shape(answer.structured, schema)
            if errors:
                answer.status, answer.error = PROTOCOL_ERROR, "; ".join(errors)
        record.write_durable(os.path.join(invocation_dir, "last-message.txt"),
                             proc.redact(answer.text.encode("utf-8")))
        return answer

    def executable(self):
        return list(self.profile.get("argv") or [self.kind])


class ClaudeAgent(HeadlessAgent):
    kind = "claude"
    reports_cost = True

    def build_argv(self, invocation_dir, schema, session_id, model, budget_usd, read_only):
        argv = self.executable() + list(self.profile.get("extra_args", []))
        argv += ["-p", "--output-format", "json", "--permission-mode",
                 self.profile.get("permission_mode", "auto"), "--permission-prompts", "none",
                 "--json-schema", json.dumps(schema), "--max-budget-usd", str(budget_usd)]
        if self.profile.get("ignore_user_config"):
            argv += ["--setting-sources", "project,local"]
        if model or self.profile.get("model"):
            argv += ["--model", model or self.profile["model"]]
        if session_id:
            argv += ["--resume", session_id]
        if read_only:
            # Disabling Edit/Write alone leaves shell and delegated writes available. Reviewers
            # get only local read/search tools and no MCP servers, then doctor verifies the boundary.
            argv += ["--tools", "Read,Glob,Grep", "--disallowedTools", "Bash,Edit,Write,NotebookEdit,Agent",
                     "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']
        return argv

    def interpret(self, res):
        failure = process_failure(res)
        if failure:
            return failure
        text = res.stdout_tail.decode("utf-8", errors="replace")
        try:
            data = json.loads(text)
        except ValueError:
            return AgentResult(PROTOCOL_ERROR, text=text, error="Claude did not return a JSON result")
        if not isinstance(data, dict) or data.get("type") != "result":
            return AgentResult(PROTOCOL_ERROR, text=text, error="Claude did not return a terminal result")
        usage = data.get("usage") or {}
        if not isinstance(usage, dict) or any(not isinstance(v, int) or isinstance(v, bool) or v < 0
                for k, v in usage.items() if k in ("input_tokens", "output_tokens",
                                                 "cache_creation_input_tokens", "cache_read_input_tokens")):
            return AgentResult(PROTOCOL_ERROR, error="Claude returned malformed usage")
        counts = {"tokens_in": sum(usage.get(k, 0) for k in
                                   ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
                  "tokens_out": usage.get("output_tokens", 0)}
        if not usage:
            counts = {}
        final = data.get("result", "")
        if not isinstance(final, str):
            final = json.dumps(final)
        answer = data.get("structured_output")
        if answer is None:
            answer = last_json_object(final)
        if not final and answer is not None:
            final = json.dumps(answer)
        error = environment_error(final) if data.get("is_error") else ""
        status = ENVIRONMENT if error else OK
        if not error and (data.get("is_error") is not False or data.get("subtype") != "success"):
            status, error = AGENT_ERROR, f"Claude result subtype: {data.get('subtype')}"
        if status == OK and not isinstance(answer, dict):
            status, error = PROTOCOL_ERROR, "Claude's final answer is not a JSON object"
        cost = data.get("total_cost_usd")
        if not isinstance(cost, (int, float)) or isinstance(cost, bool) or not math.isfinite(cost) or cost < 0:
            cost = None
        return AgentResult(status, text=final, structured=answer, session_id=data.get("session_id"),
                           cost_usd=cost, usage=counts, error=error, seconds=res.seconds)


class CodexAgent(HeadlessAgent):
    kind = "codex"

    def build_argv(self, invocation_dir, schema, session_id, model, budget_usd, read_only):
        argv = self.executable() + ["exec"] + (["resume"] if session_id else [])
        argv += list(self.profile.get("extra_args", []))
        sandbox = "read-only" if read_only else self.profile.get("sandbox", "workspace-write")
        argv += ["-c", 'approval_policy="never"', "-c", "sandbox_mode=" + json.dumps(sandbox),
                 "--json", "--output-schema", os.path.join(invocation_dir, "schema.json"),
                 "-o", os.path.join(invocation_dir, "final.raw")]
        if self.profile.get("ignore_user_config"):
            argv += ["--ignore-user-config"]
        if model or self.profile.get("model"):
            argv += ["--model", model or self.profile["model"]]
        if session_id:
            argv.append(session_id)
        return argv + ["-"]

    def interpret(self, res):
        parser = CodexEvents()
        parser.feed(res.stdout_tail)
        return parser.result(res)


REGISTRY.update(claude=ClaudeAgent, codex=CodexAgent)


def review_call(agent, prompt, *, invocation_dir, evidence=None, evidence_cap_bytes=None, **kwargs):
    """One read-only review invocation. Panel scheduling and ledger verdicts belong to stage 5.
    Provided-context mode is explicit and includes the complete prebuilt evidence manifest."""
    from . import prompts
    mode = agent.profile.get('review_mode', 'repository')
    if mode == 'provided_context':
        if evidence is None:
            raise ValueError('provided_context review requires complete evidence')
        text, manifest = evidence
        if manifest.get('mode') != 'text-only':
            raise ValueError('provided_context review requires a text-only evidence manifest')
        prompt = prompt + '\n\n' + text
        if evidence_cap_bytes is None or len(prompt.encode()) > evidence_cap_bytes:
            raise prompts.EvidenceTooLarge('complete text-only prompt exceeds its context budget; nothing was sent')
        record.write_durable(os.path.join(invocation_dir, 'evidence.json'), record.dump_json(manifest))
    record.write_durable(os.path.join(invocation_dir, 'review-mode.json'), record.dump_json(
        {'mode': 'text-only' if mode == 'provided_context' else 'repository'}))
    result = agent.run(prompt, invocation_dir=invocation_dir, schema=validate.REVIEW,
                       session_id=None, read_only=True, **kwargs)
    if result.status == OK:
        errors = validate.check_review(result.structured)
        if errors:
            result.status, result.error = PROTOCOL_ERROR, '; '.join(errors)
    return result
