# Codex headless: evidence, failure modes, and implementation contract

Reviewed 2026-09-19 for the [task-runner review](task-runner-review.md). This supplements the local research; it does not claim that a fresh end-to-end Codex workflow was run.

## What is actually established

| Evidence | Conclusion | Limit |
|---|---|---|
| Local `codex --version` | Installed CLI is 0.155.1 | Pin/test this version; do not assume all releases share its flags |
| Local `codex exec --help` and `codex exec resume --help` | Both support JSON output, output schema, final-message path, model override, config overrides, and stdin prompts | Help verifies syntax, not successful resumed execution |
| [First recorded review](../research/task_runner/prototype/recorded-live-run/slug/attempt-1/review/stdout.log) | Codex rejected the supplied change for a Unicode issue | No tool events; repository access was not tested |
| [Second recorded review](../research/task_runner/prototype/recorded-live-run/slug/attempt-2/review/stdout.log) | Codex returned approval after rework | Again no tool events |
| [Recorded author](../research/task_runner/prototype/recorded-live-run/cli/attempt-1/implement/stdout.log), lines 4–7 | First shell command failed during sandbox startup; Codex returned structured `blocked`, followed by `turn.completed` | Successful model completion does not mean successful task execution |
| Offline prototype tests | 13 passed | No proof of crash recovery, actual Codex resume, or sandboxed repository review |

The recorded error is `bwrap: No permissions to create a new namespace`. That establishes a namespace creation restriction, but the transcript alone cannot distinguish kernel settings, container policy, seccomp, or another host restriction. Do not prescribe a host sysctl change as a guaranteed fix. Shell calls in this review's default execution sandbox also failed with this message; offline inspection/testing used explicitly approved execution outside that sandbox. That does not demonstrate a repaired Codex child sandbox.

## Operational recommendations

### 1. Doctor must exercise capabilities, not ask for a greeting

Replace PRE-01's one-line response test with a capability report per effective agent/model/permission profile:

| Probe | Validation performed by runner |
|---|---|
| Structured answer | Exact expected object and successful terminal event |
| Repository read | A random nonce lives only in a scratch file; the agent must read and return it |
| Shell execution | Tool event proves the intended command ran successfully |
| Author write | A scratch output contains the expected transformation; runner reads it back |
| Resume | Continue a scratch session by its explicit ID, validate the follow-up object and identity |
| Permission boundary | In an isolated scratch setup, a disallowed write is denied and the sentinel is unchanged |

Do not run a model-backed doctor on every trivial CLI command. Cache successful qualification by binary version, profile/config fingerprint, host/container identity, and required capabilities; invalidate on environment changes. A live probe costs money and belongs in the workflow's accounting. Missing binary, sandbox startup failure, authentication failure, and malformed result are distinct error classes.

### 2. Choose an explicit deployment mode

**Preferred:** run on a host/container where the chosen Codex sandbox and the required tools pass doctor. Repository-reading reviews need working read capability just as authoring needs working write capability.

**Text-only alternative:** the runner supplies the complete relevant source, brief, tests/spec excerpts, and full diff for a bounded task. Record `review_mode = "provided_context"` and its evidence manifest; do not label it a repository-inspection review. If required evidence exceeds the context budget, fail that review mode or use a different qualified backend.

**Explicit externally isolated mode:** keep the existing requirement for a visible per-workflow choice before bypassing Codex isolation. Provide a disposable checkout and an external filesystem/process boundary. Merely using a container with the normal developer workspace mounted writable is not sufficient isolation for rollback guarantees. There must be no automatic fallback to bypass flags after a sandbox error.

Official documentation separates sandbox permissions from execution output and documents explicit sandbox selection. It also documents JSONL events, schema output, and saved CLI authentication. These are supported integration points. [OpenAI non-interactive documentation](https://learn.chatgpt.com/docs/non-interactive-mode).

### 3. Build explicit argv, with separate fresh/resume builders

Proposed runner policy for the locally inspected 0.155.1 CLI (not a command executed during this review):

```python
argv = [
    codex_binary, "exec",
    "--json",
    "-c", 'approval_policy="never"',
    "-c", 'sandbox_mode="workspace-write"',
    "--output-schema", absolute_schema_path,
    "-o", absolute_final_path,
    "-m", configured_model,
    "-",
]
# Popen(argv, cwd=repository_root, stdin=PIPE, ..., start_new_session=True)
# For reviews: sandbox_mode="read-only".
# For retry: [codex_binary, "exec", "resume", exact_session_id, ...].
```

Use the config override for sandbox on resume; the local resume help does not list `--sandbox`. The existing prototype's use of `-c` is therefore sensible. Its `--output-schema` on resume is supported locally and should not be removed based on older online reports. Config override values still require a preflight: help cannot establish policy precedence under managed requirements.

Use explicit session IDs, never `--last`. Keep `cwd` and the effective permission profile consistent across resume. Abandon sessions after interruption or a materially changed brief. Do not use `--ephemeral` for author sessions that must resume. Since the runner requires a Git repository, remove the unconditional `--skip-git-repo-check`, unless an explicit scratch mode needs it.

The current command reference describes `--json`, `--output-schema`, output-file capture, config overrides, and session selection. Its details can change; capture local help/version as compatibility evidence. [OpenAI command reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli).

### 4. Make configuration and authentication reproducible

The prototype inherits the process environment and user configuration. That can add hooks, MCP servers, model defaults, or settings absent from the frozen workflow. A frozen TOML file alone therefore cannot reproduce the call.

Define a named automation profile, record its nonsecret effective settings and version/hash, and validate required tools before work. Allow `--ignore-user-config` only as an explicit profile policy: it changes behavior and can discard desired integrations. Do not silently ignore project rules or managed policy. Keep credentials outside the run record and export only the documented task metadata. Separate the environment passed to gates from the authentication environment needed by the agent.

Saved CLI authentication is a valid option; lack of an API key does not alone imply headless mode is unavailable. If using API authentication, provide it only to the intended invocation and never record credential values in `argv.json`, prompts, or environment dumps. [OpenAI authentication guidance](https://learn.chatgpt.com/docs/non-interactive-mode#authenticate-in-automation).

### 5. Treat the event stream as a protocol

The proposed successful result is:

```text
normal exit
AND successful terminal turn for this invocation
AND final output from this invocation
AND locally validated schema and ledger semantics
```

After that, the engine still interprets `blocked`, runs gates, and obtains verifiers. The recorded author's `turn.completed` alongside `outcome=blocked` is the regression fixture for this distinction.

Allocate a fresh invocation directory with exclusive creation. Keep partial output on failure but never use a final file from a previous invocation. Incrementally parse stdout while draining stderr; preserve unknown event types for forward compatibility. Reject malformed records where they make completion ambiguous. Store raw usage fields, including cached/reasoning token fields, without inventing dollar costs or double-counting categories.

A failed intermediate command does not automatically invalidate a later successful repair. Track capability failures explicitly, and require the runner's external gates rather than trying to infer correctness from every tool event.

### 6. Own timeout, cancellation, and retry classification

The prototype's process-group signaling is a useful starting point. Its `communicate()` buffering, however, delays durable logs until exit. Stream logs to files, maintain bounded diagnostic tails, and ensure runner cancellation stops descendants as well as the CLI. Unknown completion after a crash must not cause immediate concurrent re-execution.

Use separate retry classes:

| Failure | Action |
|---|---|
| Namespace/sandbox startup | Stop that capability immediately; repair environment |
| Authentication or configuration | Stop before producer attempts; actionable diagnostic |
| Transient transport/rate limit | Bounded backoff; preserve all invocation records |
| Missing terminal event or invalid schema | Bounded adapter/protocol retry with a fresh output path |
| Structured author `blocked` | Engine records blocked with reason |
| Valid review with unresolved blocker | Producer rework, subject to producer attempt budget |
| Timeout/interruption | Kill/reconcile invocation, discard session for subsequent author call |

Codex dollar spend is unpriced in the current adapter. Token events are accounting evidence, not proof of a hard in-call token cap. Enforce time and attempts, display unknown spend, and do not advertise a dollar guarantee that the adapter cannot provide.

## Reproduce the confirmed prototype defects without a model

Run from the repository root. This uses only temporary files/repositories and disables Python bytecode writes.

```bash
python3 -B - <<'PY'
import json, pathlib, subprocess, sys, tempfile
sys.path.insert(0, 'research/task_runner/prototype')
from taskrunner.agents import Codex
from taskrunner.gitops import Git

with tempfile.TemporaryDirectory() as d:
    root = pathlib.Path(d)
    a = Codex('codex')
    event = json.dumps({'type': 'item.completed', 'item': {
        'type': 'agent_message', 'text': '{"approved":true,"reasons":[]}'}})
    print('incomplete stream accepted:', a.parse(0, event, '', str(root/'absent')).ok)
    last = root/'last.txt'
    last.write_text('{"approved":true,"reasons":[]}')
    print('stale final accepted:', a.parse(0, '', '', str(last)).ok)

    repo = root/'repo'
    repo.mkdir()
    def git(*args):
        return subprocess.run(['git', *args], cwd=repo, check=True,
                              capture_output=True, text=True).stdout
    git('init', '-q')
    git('config', 'user.name', 'review-probe')
    git('config', 'user.email', 'review-probe@example.invalid')
    script = repo/'script.sh'
    script.write_text('#!/bin/sh\nexit 0\n')
    script.chmod(0o755)
    (repo/'target').write_text('original target')
    (repo/'link').symlink_to('target')
    (repo/'ordinary.txt').write_text('initial\n')
    git('add', '-A')
    git('commit', '-qm', 'baseline')
    g = Git(str(repo))
    base = g.snapshot()
    script.chmod(0o644)
    g.restore(base, ['script.sh'])
    print('executable restored:', bool(script.stat().st_mode & 0o111))
    g.restore(base, ['link'])
    print('symlink target contents:', (repo/'target').read_text())
    (repo/'ordinary.txt').write_text('owner edit\n')
    # The owner edit exists before the simulated agent's addition.
    with (repo/'ordinary.txt').open('a') as f:
        f.write('agent edit\n')
    g.commit(['ordinary.txt'], 'agent task')
    print('owner edit committed:', 'owner edit' in git('show', 'HEAD:ordinary.txt'))
PY
```

Observed results in this checkout:

```text
incomplete stream accepted: True
stale final accepted: True
executable restored: False
symlink target contents: target
owner edit committed: True
```

These probes exercise reusable prototype primitives directly. They establish the defects in those primitives; they do not claim every input reaches product acceptance, since the product engine has not been built.
