"""Agents: one interface, and an adapter per kind of command-line agent (05, Agent interface).

The command, Claude Code and Codex adapters plug into REGISTRY by their kind. An adapter builds the command line, runs it under the runner's clock
with streamed and redacted logs, and says whether the call completed properly. It reports facts;
the engine decides what follows.
"""

import json
import math
import os
import datetime
import glob
import re
import subprocess
import time
import uuid

from . import proc, record, validate, activity

OK, ENVIRONMENT, PROTOCOL_ERROR, AGENT_ERROR, TIMED_OUT, INTERRUPTED = (
    "ok", "environment", "protocol-error", "agent-error", "timed-out", "interrupted")
TRANSIENT = "transient"      # the provider failed, not the agent: worth another call


def transient_error(text):
    """Provider-side failures that a later call may not see: capacity, overload, a dropped
    connection. Only error-channel evidence, like `quota_error`."""
    return isinstance(text, str) and bool(re.search(
        r"at capacity|overloaded|server (?:is )?busy|temporarily unavailable|service unavailable|"
        r"try again later|(?:connection|socket) (?:reset|timed out|closed)|"
        r"ECONNRESET|ECONNREFUSED|ETIMEDOUT|EAI_AGAIN|EPIPE|\b(?:502|503|504|529)\b.*(?:error|gateway|unavailable|overloaded)",
        text, re.IGNORECASE))


QUOTA = "quota"


def quota_error(text):
    """Only provider error-channel evidence, never tool output or successful prose."""
    return isinstance(text, str) and bool(re.search(
        r"usage_limit_reached|insufficient_quota|rate_limit_exceeded|"
        r"you(?:'|’)ve hit your (?:usage )?limit|"
        r"(?:weekly|5.hour|five.hour|session) (?:usage )?limit (?:reached|exceeded)",
        text, re.IGNORECASE))


class AgentResult:
    def __init__(self, status, text="", structured=None, session_id=None, cost_usd=None,
                 usage=None, error="", seconds=0.0, usage_source="terminal"):
        self.status, self.text, self.structured = status, text, structured
        self.session_id, self.cost_usd, self.usage = session_id, cost_usd, usage or {}
        self.error, self.seconds = error, seconds
        self.usage_source = usage_source      # "terminal": the provider's final event; "provider-record": read from its on-disk record after a call that had no final event

    def outcome(self):
        return {"status": self.status, "error": self.error, "seconds": round(self.seconds, 3),
                "session_id": self.session_id, "cost_usd": self.cost_usd, "usage": self.usage,
                "usage_source": self.usage_source}


def _epoch(stamp):
    """Seconds since the epoch of an ISO-8601 UTC stamp such as 2026-09-23T07:04:19.280Z."""
    try:
        return datetime.datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def partial_usage(kind, invocation_dir, since, env=None):
    """Usage of a call that ended without the provider's terminal event (interrupted, timed out,
    killed as an orphan), read from the provider's own record on disk: a Claude session
    transcript, or a Codex rollout. Only rows stamped at or after `since` (epoch seconds) count,
    so a resumed session's earlier turns are left out. Returns {} when nothing can be read; the
    call then stays "unknown usage" (G4)."""
    agent = REGISTRY.get(kind)
    reader = getattr(agent, "read_provider_record", None)
    if reader is None or since is None:
        return {}
    try:
        return reader(invocation_dir, float(since), env if env is not None else os.environ)
    except (OSError, ValueError, TypeError, KeyError):
        return {}


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
    env = {k: v for k, v in base.items()
           if k not in ("TASK_RUNNER_RUN_DIR", "TASK_RUNNER_RUNS_DIR")}   # see checks.command_env
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


# Match failures of the execution/authentication machinery, not ordinary failing tests. Each
# marker matches as whole words, so `ENOTFOUND` is not seen inside `FileNotFoundError`.
STARTUP_MARKERS = (
    "bwrap: no permissions to create a new namespace", "sandbox failed to start",
    "failed to create sandbox", "unprivileged user namespaces are unavailable",
)
NETWORK_MARKERS = (
    "can't reach the api server", "can’t reach the api server", "enotfound", "network is unreachable",
)
PROVIDER_MARKERS = NETWORK_MARKERS + (
    "invalid api key", "invalid_api_key", "authentication failed", "not logged in",
    "unexpected argument", "unknown option", "invalid value for", "please run /login", "please run codex login", "error loading config", "invalid configuration",
)
ENVIRONMENT_MARKERS = STARTUP_MARKERS + PROVIDER_MARKERS


def _marker_pattern(markers):
    return re.compile("|".join(r"(?<![\w])" + re.escape(m) + r"(?![\w])" for m in markers), re.IGNORECASE)


_ALL_MARKERS = _marker_pattern(ENVIRONMENT_MARKERS)
_STARTUP_ONLY = _marker_pattern(STARTUP_MARKERS)
_NETWORK = _marker_pattern(NETWORK_MARKERS)


def network_error(text):
    """An environment failure that says nothing about the agent's setup: the network was down.
    What `doctor` learned about the profile still holds, so a run stopped for this is not
    re-qualified on `resume`."""
    return isinstance(text, str) and bool(_NETWORK.search(text))


def environment_error(text, startup_only=False):
    """The first line of `text` naming an environment failure. Text an agent's own tool commands
    printed is checked for startup failures only: source code or documentation that mentions
    "not logged in" is not evidence that the agent is."""
    if not isinstance(text, str):
        return ""
    pattern = _STARTUP_ONLY if startup_only else _ALL_MARKERS
    return next((line[:2000] for line in text.splitlines() if pattern.search(line)), "")


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
        self.omitted_events = 0
        self.has_usage = False
        self.usage = {"tokens_in": 0, "tokens_out": 0, "cached_tokens_in": 0}

    def feed(self, data):
        for line in data.splitlines():
            if not line.strip():
                continue
            if line.strip() in (proc.OVERLONG_PLACEHOLDER, proc.OVERLONG_PLACEHOLDER.decode()):
                # The sink withheld one event longer than its line limit: in practice a
                # command_execution item carrying a large file the agent read. It is not a
                # malformed stream. The answer and the terminal event are still required, so an
                # omitted final message fails later for want of a valid answer, never silently.
                self.omitted_events += 1
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
                    self.environment = (environment_error(item.get("aggregated_output", ""), startup_only=True)
                                        or self.environment)

    def result(self, res):
        failure = process_failure(res)
        if self.failed and quota_error(self.failed) and res.status != "timed-out":
            failure = AgentResult(QUOTA, error=self.failed, seconds=res.seconds)
        elif self.failed and transient_error(self.failed) and res.status != "timed-out":
            failure = AgentResult(TRANSIENT, error=self.failed, seconds=res.seconds)
        if self.environment:
            failure = AgentResult(ENVIRONMENT, error=self.environment, seconds=res.seconds)
        if failure:
            failure.session_id, failure.usage = self.session_id, self.usage if self.has_usage else {}
            return failure
        status, error = OK, ""
        if self.failed:
            status, error = (QUOTA if quota_error(self.failed) else
                             TRANSIENT if transient_error(self.failed) else AGENT_ERROR), self.failed
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
        env = activity.prepare(self.kind, cwd, invocation_dir, env)
        parser = CodexEvents() if self.kind == "codex" else None
        telemetry = activity.CodexTelemetry(cwd, env) if parser else None
        def on_stdout(data):
            parser.feed(data)
            telemetry.feed(data)
        started_at = time.time()
        res = proc.run_process(argv, cwd=cwd, env=env, stdin_data=prompt.encode("utf-8"),
                               stdout_path=os.path.join(invocation_dir, "stdout.log"),
                               stderr_path=os.path.join(invocation_dir, "stderr.log"),
                               timeout_s=timeout_s, on_start=on_start,
                               on_stdout=on_stdout if parser else None)
        answer = parser.result(res) if parser else self.interpret(res)
        if not answer.usage and answer.status != OK and answer.cost_usd is None:
            # No terminal event carried usage (a time-out, a kill, a crash mid-call): the
            # provider's own record still says what the call used (G4).
            usage = partial_usage(self.kind, invocation_dir, started_at, env)
            if usage:
                answer.usage, answer.usage_source = usage, "provider-record"
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
        else:
            # Chosen here so the transcript of a call that never returns can still be found (G4).
            argv += ["--session-id", str(uuid.uuid4())]
        if read_only:
            # Disabling Edit/Write alone leaves shell and delegated writes available. Reviewers
            # get only local read/search tools and no MCP servers, then doctor verifies the boundary.
            argv += ["--tools", "Read,Glob,Grep", "--disallowedTools", "Bash,Edit,Write,NotebookEdit,Agent",
                     "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']
        return argv

    @staticmethod
    def read_provider_record(invocation_dir, since, env):
        """Sum the usage of this call's API responses from the session transcript
        `$CLAUDE_CONFIG_DIR/projects/<cwd slug>/<session>.jsonl`. Claude writes one row per
        content block, all carrying the response's usage, so rows are counted once per request."""
        with open(os.path.join(invocation_dir, "argv.json"), encoding="utf-8") as fh:
            recorded = json.load(fh)
        argv, cwd = recorded["argv"], recorded["cwd"]
        session = next((argv[i + 1] for i, a in enumerate(argv[:-1]) if a in ("--session-id", "--resume")), None)
        if not session or not re.fullmatch(r"[\w-]+", session):
            return {}
        home = env.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
        slug = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(cwd))
        path = os.path.join(home, "projects", slug, session + ".jsonl")
        if not os.path.isfile(path):
            return {}
        seen, counts = set(), {"tokens_in": 0, "tokens_out": 0}
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(row, dict) or row.get("type") != "assistant":
                    continue
                stamp = _epoch(row.get("timestamp"))
                message = row.get("message") if isinstance(row.get("message"), dict) else {}
                usage = message.get("usage") if isinstance(message.get("usage"), dict) else None
                key = row.get("requestId") or message.get("id")
                if stamp is None or stamp < since - 1 or not usage or key in seen:
                    continue
                seen.add(key)
                for source, target in (("input_tokens", "tokens_in"), ("cache_creation_input_tokens", "tokens_in"),
                                       ("cache_read_input_tokens", "tokens_in"), ("output_tokens", "tokens_out")):
                    value = usage.get(source, 0)
                    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                        counts[target] += value
        return counts if seen else {}

    def interpret(self, res):
        failure = process_failure(res)
        text = res.stdout_tail.decode("utf-8", errors="replace")
        if failure:
            try:
                envelope = json.loads(text)
            except ValueError:
                envelope = {}
            # A non-zero exit with a result envelope: the envelope says what the failure was.
            if (failure.status == AGENT_ERROR and isinstance(envelope, dict)
                    and envelope.get('type') == 'result' and envelope.get('is_error') is True):
                said = envelope.get('result')
                if quota_error(said):
                    failure.status, failure.error = QUOTA, said
                elif environment_error(said):
                    failure.status, failure.error = ENVIRONMENT, environment_error(said)
                elif transient_error(said):
                    failure.status, failure.error = TRANSIENT, said
            if failure.status != QUOTA:
                return failure
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
            if quota_error(final) or data.get('subtype') in ('error_rate_limit', 'error_usage_limit'):
                status, error = QUOTA, final or error
            elif transient_error(final):
                status, error = TRANSIENT, final
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

    @staticmethod
    def read_provider_record(invocation_dir, since, env):
        """Sum the usage of this call's responses from the rollout
        `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<stamp>-<thread>.jsonl`, whose
        `token_usage_record` rows carry each response's usage as it happens. The thread id is
        the `thread.started` event streamed to stdout.log, or the resumed session in argv.json."""
        with open(os.path.join(invocation_dir, "argv.json"), encoding="utf-8") as fh:
            thread = json.load(fh).get("session_id")
        if not thread:
            try:
                with open(os.path.join(invocation_dir, "stdout.log"), "rb") as fh:
                    head = fh.read(65536).decode("utf-8", errors="replace")
            except OSError:
                head = ""
            for line in head.splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict) and event.get("type") == "thread.started":
                    thread = event.get("thread_id")
                    break
        if not isinstance(thread, str) or not re.fullmatch(r"[\w-]+", thread):
            return {}
        home = env.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
        paths = glob.glob(os.path.join(glob.escape(home), "sessions", "*", "*", "*", f"rollout-*-{thread}.jsonl"))
        if not paths:
            return {}
        seen, counts = set(), {"tokens_in": 0, "tokens_out": 0, "cached_tokens_in": 0}
        with open(sorted(paths)[-1], encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(row, dict) or row.get("type") != "token_usage_record":
                    continue
                payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
                usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
                stamp = _epoch(row.get("timestamp"))
                key = payload.get("response_id") or row.get("ordinal")
                if stamp is None or stamp < since - 1 or not usage or key in seen:
                    continue
                seen.add(key)
                for source, target in (("input_tokens", "tokens_in"), ("output_tokens", "tokens_out"),
                                       ("cached_input_tokens", "cached_tokens_in")):
                    value = usage.get(source, 0)
                    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                        counts[target] += value
        return counts if seen else {}

    def enabled_features(self):
        """Feature names the profile switches on (`--enable NAME`, `-c features.NAME=true`)."""
        args = list(self.profile.get("extra_args", []))
        names = []
        for i, arg in enumerate(args):
            if arg == "--enable" and i + 1 < len(args):
                names.append(args[i + 1])
            elif arg.startswith("--enable="):
                names.append(arg.split("=", 1)[1])
            elif arg == "-c" and i + 1 < len(args):
                m = re.fullmatch(r"features\.([\w-]+)\s*=\s*true", args[i + 1].strip())
                if m:
                    names.append(m.group(1))
        return names

    def preflight(self, cwd, env, read_only, timeout_s=60):
        """Free checks before any model call. Returns (notes, error): `error` names why no call
        of this profile can work (the Linux sandbox cannot start), `notes` name what the owner
        should know (an enabled feature the CLI has deprecated or removed)."""
        notes, error = [], ""
        sandbox = "read-only" if read_only else self.profile.get("sandbox", "workspace-write")
        if sandbox != "danger-full-access":
            argv = self.executable() + ["sandbox"] + list(self.profile.get("extra_args", [])) + ["--", "true"]
            try:
                res = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, timeout=timeout_s)
                if res.returncode != 0:
                    said = (res.stderr or res.stdout).decode("utf-8", errors="replace").strip()
                    line = (environment_error(said, startup_only=True) or (said.splitlines() or [""])[-1]
                            or f"exited with status {res.returncode}")
                    error = "the Codex sandbox cannot start on this host: " + line[:500]
            except (OSError, subprocess.TimeoutExpired) as exc:
                error = f"the Codex sandbox could not be checked: {exc}"
        wanted = self.enabled_features()
        if wanted:
            status = {}
            try:
                out = subprocess.run(self.executable() + ["features", "list"], cwd=cwd, env=env,
                                     capture_output=True, timeout=timeout_s).stdout.decode("utf-8", errors="replace")
                for line in out.splitlines():
                    m = re.match(r"^(\S+)\s+(.*?)\s+(true|false)\s*$", line)
                    if m:
                        status[m.group(1)] = m.group(2).strip()
            except (OSError, subprocess.TimeoutExpired):
                pass
            for name in wanted:
                state = status.get(name)
                if state in ("deprecated", "removed"):
                    notes.append(f"feature '{name}' is {state} in this Codex CLI"
                                 + (": the profile depends on it, so the next CLI may need a different sandbox "
                                    "(unprivileged user namespaces for bwrap) or another agent" if state == "deprecated"
                                    else ": the profile's --enable has no effect"))
        return notes, error

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
