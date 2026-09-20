# 02 — Architecture

Status: **design only.** Read [01 — Design](01-design.md) first for what the runner does. This file
says how it is put together.

## Components

```
                       plan.toml
                           │
                           ▼
 ┌──────────┐        ┌───────────┐
 │   cli    │───────►│   plan    │  load, defaults, validate, order
 └────┬─────┘        └─────┬─────┘
      │                    │ Plan (immutable)
      ▼                    ▼
 ┌──────────────────────────────────┐        ┌──────────────┐
 │              engine              │◄──────►│    state     │  state.json, events.jsonl,
 │  scheduler · phases · limits     │        └──────────────┘  per-attempt logs
 └───┬──────────┬──────────┬────────┘
     │          │          │
     ▼          ▼          ▼
 ┌────────┐ ┌────────┐ ┌─────────┐
 │ agents │ │ gates  │ │ gitops  │
 └───┬────┘ └───┬────┘ └────┬────┘
     ▼          ▼           ▼
 claude, codex,  shell      git
 any command
```

| Module | Responsibility | Knows about |
|---|---|---|
| `plan` | Parse TOML, apply defaults, validate, produce the execution order | Nothing else |
| `state` | Load and save run state atomically; append events; name the log directories | The file system |
| `agents` | Turn "run this prompt" into a command line for one agent, run it under a clock, and turn its output into an `AgentResult` | Each agent's CLI. Nothing about tasks |
| `gates` | Run shell commands with a timeout, capture output, return pass or fail with a tail | Nothing else |
| `gitops` | Snapshot the work tree, list and diff changes between snapshots, restore paths, commit | `git` |
| `prompts` | Build the implement, retry and review prompts from a task and its state. Pure functions | `plan` types |
| `engine` | The scheduler and the phase table. The only module that decides anything | All of the above, through their interfaces |
| `cli` | Arguments, exit codes, printing | `plan`, `engine` |

Rule: **only `engine` makes decisions, and it makes them only from exit codes, booleans and
counters.** The other modules report facts.

## The plan file

TOML, because Python reads it from the standard library, it has comments and multi-line strings,
and a wrong key is easy to detect.

```toml
name = "nyse-m1"                 # names the run directory. Default: the file name
root = "../.."                   # the repository the agents work in, relative to this file

[defaults]                       # optional; see 01-design for the values
agent = "claude"
protected = ["nyse-handler/tests/fixtures/*", "nyse-handler/docs/design/*"]

[agents.codex]                   # optional per-agent settings
sandbox = "workspace-write"

[agents.gemini]                  # optional: any other agent
type = "command"
argv = ["gemini", "-p"]

[[task]]
id = "build-wiring"              # required, unique, [A-Za-z0-9._-]
title = "Add nyse-handler to CMake"          # becomes the commit subject
prompt_file = "items/02-build-wiring.md"     # or: prompt = "..."
needs = []                       # task IDs that must be done first
gate = ["cmake --build build", "ctest --test-dir build -R nyse"]   # required
# any key from [defaults] can be overridden here
```

Validation, all reported together and before anything runs: unknown keys (catches typos), missing
prompt or gate, duplicate or malformed IDs, `needs` naming an unknown task, dependency cycles, and
an agent name that is neither built in nor defined.

**Order:** repeatedly take the first task in file order whose `needs` are all done. This is a stable
topological sort, and it is the whole scheduler.

## The agent interface

The seam that makes the runner model agnostic. It is Attractor's `CodergenBackend`, widened to
carry what a runner needs.

```python
class Agent:
    def run(self, prompt: str, *,
            cwd: str,               # the repository root
            log_dir: str,           # where prompt, argv, stdout, stderr are written
            schema: dict | None,    # JSON Schema for the final answer
            session_id: str | None, # continue this session, or start a new one
            model: str,             # empty: the agent's own default
            timeout_s: int,
            budget_usd: float,      # passed on if the agent can enforce it
            read_only: bool,        # reviewer mode
            ) -> AgentResult: ...

@dataclass
class AgentResult:
    ok: bool                  # the agent ran and finished its turn without error
    text: str                 # its final message
    structured: dict | None   # its final answer as JSON, if any
    session_id: str | None    # for the next retry
    cost_usd: float | None    # None: this agent does not report cost
    tokens: dict              # {"in": n, "out": n}
    error: str
    timed_out: bool
    seconds: float
```

An adapter supplies two functions: build the command line, and parse the output. Running the
process, the clock, the logging and the JSON fallback are shared.

| | Claude Code | Codex | Any command |
|---|---|---|---|
| Invocation | `claude -p --output-format json` | `codex exec --json -` | the configured `argv` |
| Prompt | stdin | stdin | stdin |
| Structured answer | `--json-schema`, read from `structured_output` | `--output-schema FILE`, read from `-o FILE` | last JSON object in stdout |
| Continue a session | `--resume ID` | `exec resume ID` | not supported: every attempt is new |
| Session ID from | `session_id` in the result | `thread.started` event | — |
| Money limit | `--max-budget-usd` | none | none |
| Cost reported | `total_cost_usd` (an estimate) | no, tokens only | no |
| Unattended permissions | `--permission-mode auto --permission-prompts none` | `-c sandbox_mode="workspace-write"` | the command's own |
| Read-only (review) | `--disallowedTools Edit Write NotebookEdit` | `-c sandbox_mode="read-only"` | `read_only_args` |
| Model | `--model` | `-m` | `model_args` template |
| Failure signal | non-zero exit, or `is_error` | non-zero exit, or a `turn.failed` / `error` event | non-zero exit |

Two rules apply to every adapter:

- **The schema is also written into the prompt**, and the last JSON object in the final message is
  accepted if the agent's schema feature returned nothing. So an agent with no schema flag still
  works, and a flag that misbehaves does not stop the run.
- **Schemas are strict**: `additionalProperties: false` and every property required. Codex requires
  this, and it costs the others nothing.

The two schemas:

```json
{"outcome": "done" | "blocked", "notes": "..."}          // implement
{"approved": true | false, "reasons": ["..."]}           // review
```

### The clock

The runner starts every agent in its own process group and owns the timeout, because neither agent
has a wall-clock flag. At the deadline: SIGINT (Claude Code ends its turn cleanly on this), 20
seconds later SIGTERM, 5 seconds later SIGKILL, each to the whole group. A timed-out result is never
`ok`, and its session is never continued.

## Work-tree snapshots

Four features need to know exactly what changed: protected files, the reviewer's diff, the
reviewer-did-not-edit check, and the per-task commit. All use one primitive.

`snapshot()` returns a git **tree ID** for the entire work tree, untracked files included. It builds
it in a scratch index (`GIT_INDEX_FILE` pointing at a temporary file: `read-tree HEAD`, `add -A`,
`write-tree`), so the real index and the work tree are never touched.

| Need | Operation |
|---|---|
| What did this task change? | `git diff --name-only BASE NOW` between two snapshots. `BASE` is taken when the task starts |
| Did the agent touch a protected file? | Match those names against the globs |
| Put a protected file back | Write the blob from `BASE`, or delete the file if `BASE` did not have it |
| The reviewer's diff | `git diff BASE NOW`. New files appear in it, which plain `git diff` would miss. Capped at 60,000 characters |
| Did the reviewer edit anything? | Snapshot before and after; the IDs must be equal |
| Commit only this task's files | `git add -A -- <names>` then `git commit -- <names>` |

The run directory ignores itself (`.runner/.gitignore` holds `*`), so it never appears in a
snapshot and needs no entry in the repository's own ignore file.

Without git the runner still works, with a warning: no commits, no protected files, no diff for the
reviewer.

## State

Everything is under `<root>/.runner/<plan name>/`.

```
state.json                          the whole run; rewritten atomically after every phase
events.jsonl                        one line per event, append-only
<task>/attempt-<n>/
    implement/  prompt.md  argv.json  stdout.log  stderr.log  schema.json  last-message.txt
    gate.log
    review/     (the same files)
```

```json
{
  "started": true,
  "cost_usd": 1.00,
  "tasks": {
    "build-wiring": {
      "status": "running",          // pending | running | awaiting_human | done | failed | blocked
      "phase": "gate",              // implement | gate | review | human | commit | done
      "attempt": 2,
      "base": "<tree id>",          // snapshot when the task started
      "session_id": "…",            // null after an agent error or timeout
      "feedback": "…",              // what the next implement prompt will carry
      "last_gate_hash": "…",        // for the no-progress stop
      "review_errors": 0,
      "cost_usd": 0.41, "tokens": {"in": 0, "out": 0}, "seconds": 61.2,
      "reason": "", "notes": "", "commit": ""
    }
  }
}
```

**Nothing is held in memory between phases.** `next` loads the state, advances one phase of one
task, saves, and returns. `run` is `next` in a loop. So resuming after a crash is not a feature; it
is the only way the runner ever works. A crash during a phase repeats that phase: implement is
repeated as a new attempt, a gate is simply run again, a review is asked again, and a commit that
already happened is detected because nothing is left to commit.

The plan is read fresh on every invocation. Editing a task's prompt or gate between `retry` calls
is therefore supported and expected.

## Command line

```
runner validate PLAN          check the plan, print the order
runner doctor PLAN            test each agent the plan uses with a one-line prompt; report versions
runner check-gates PLAN       run every gate on the untouched tree; each must currently FAIL
runner run PLAN               run until done, or until a person is needed
runner next PLAN              advance one phase of one task
runner status PLAN            every task: status, attempts, cost, commit
runner approve PLAN TASK      release a task that waits for a person
runner retry PLAN TASK        fresh attempts for a failed or blocked task
```

Exit codes, the same set agate uses, so the runner can itself be a step in something larger:

| Code | Meaning |
|---|---|
| 0 | Every task is done |
| 1 | More work remains (`next` only) |
| 2 | A task failed, or the plan or environment is wrong |
| 255 | A person is needed: a blocked task, or one awaiting approval |

The run stops at the first task that is failed, blocked or awaiting a person. It does not skip ahead
to independent tasks, because a failed task leaves uncommitted changes in the one work tree. Running
ahead needs a work tree per task, which is the same problem as parallelism and is solved with it.

## Prompts

Three, built by pure functions from the plan and the state.

- **Implement, first attempt or new session:** the framing (one task, unattended, nobody to ask),
  the task text, the acceptance commands, the rules (do not commit; your report does not count;
  never weaken a test or special-case its input; answer "blocked" if it cannot be done properly; the
  protected globs), and the previous failure if there was one.
- **Implement, continued session:** only the new failure, the instruction to fix it, and the attempt
  count. Everything else is already in the session.
- **Review:** the task text, the statement that the gates already pass, three things to check (does
  what was asked and nothing else; tests not weakened and no input special-cased; no obvious
  defect), and the diff.

Prompts are stored with every attempt, so any result can be traced to the exact words that
produced it.

## Security posture

- Defaults never bypass an agent's permission system or sandbox.
- The runner passes no credentials and reads none. Each agent uses its own login.
- Gate commands come from the plan, which is a reviewed file in the repository. They run with the
  user's rights, exactly as a Makefile would.
- A plan that loosens an agent (for example Codex with `sandbox = "danger-full-access"` inside a
  container) says so in the plan file, where a reviewer sees it. `validate` prints a warning line
  for it.
- Driven Claude Code sessions load the project's settings, so the repository's own hooks run in
  them. For this repository that is wanted: the hook logger records every driven session.

## Extension points, in the order they are likely to be needed

| Extension | Where it fits |
|---|---|
| A new agent | One adapter class, or no code at all with `type = "command"` |
| A token limit per call | `agents`: count from the event stream, stop the process at the limit |
| The session scorecard as a stuck signal | `engine`: after implement, read the hook logger's scorecard for the session; red means abandon the session |
| Parallel tasks | `engine` scheduler plus `gitops`: one git worktree per running task, merge in plan order |
| Custom routing (Attractor DOT) | Compile the task list to a graph; the phase table becomes its edges |
