# 05 — Architecture

How the runner is put together. The model it implements is in [02 — Concepts](02-concepts.md).

## Modules

```
 workflow.toml + library/
          │
          ▼
    ┌───────────┐    expanded tasks     ┌────────────┐
    │  workflow │──────────────────────►│            │      ┌──────────┐
    └───────────┘                       │            │◄────►│  record  │ state.json, events,
    ┌───────────┐    prompts            │   engine   │      └──────────┘ STATUS.md, index.json
    │  prompts  │◄─────────────────────►│            │
    └───────────┘                       │ scheduler  │
                                        │ lifecycle  │
    ┌───────────┐ ┌────────┐ ┌────────┐ │ findings   │
    │  agents   │ │ checks │ │ gitops │◄┤ limits     │
    └───────────┘ └────────┘ └────────┘ └─────┬──────┘
                                              │
                                           ┌──┴──┐
                                           │ cli │
                                           └─────┘
```

| Module | Responsibility |
|---|---|
| `workflow` | Load the workflow, types and personas. Apply precedence. Expand panels. Validate. Give the fixed task order |
| `record` | The run directory: create it, save state durably, record intents and outcomes, append events, write attempt, round and invocation files, regenerate `STATUS.md` and `index.json` from state |
| `prompts` | Render a type's template for a task. Pure functions of the expanded task, the state and the upstream results |
| `agents` | One interface, three adapters (Claude Code, Codex, any command). Build the command line, run it under the runner's clock with streamed logs, decide whether the call completed properly, qualify capabilities |
| `validate` | The runner's own small validator for its result schemas, and the semantic checks against the ledger |
| `checks` | Run gate and check commands with a timeout. Return pass or fail and the output |
| `gitops` | Work-tree snapshots pinned under private refs, changed paths, diffs, restoring paths by type and mode, full binary patches, the run branch, commits with operation ids, reverts |
| `findings` | The ledger: assign ids, apply responses and resolutions, enforce the later-round rule, decide whether any blocking finding is open |
| `engine` | The scheduler and the task lifecycle. **The only module that decides anything**, and only from exit codes, verdict fields, ledger status and counters |
| `cli` | Commands, exit codes, printing |

`agents`, `checks`, `gitops` and `record` report facts. `workflow` and `prompts` are pure. That keeps
the part that must be deterministic (`engine`, `findings`) small and free of I/O details, so it can
be tested exhaustively with scripted agents.

## The engine loop
```
load state; reconcile (see Crash recovery)
repeat:
    apply finished work           (results are applied in workflow order, never arrival order)
    if nothing is running:
        if there is an active producer:
            start its next step: a gate or writing check (alone), its ready readers (up to
            max_parallel), its rework, its commit, or its set-aside
        else:
            start standalone ready readers (up to max_parallel), if any; when none are running,
            make the first ready producer in workflow order the active producer
    if nothing is running and nothing can start: stop
    wait for any running job to finish
    save state; regenerate STATUS.md
```

Run status when the loop stops: `done` if every task is accepted; `needs_human` if any task is
`waiting_human` or `blocked`; otherwise `failed`. Exit codes 0, 255, 2.

Parallel jobs are subprocesses (agents and commands already are), supervised from one thread with
the standard library's `concurrent.futures`. There are no threads inside the decision logic.

### The producer transaction (A1)

Serial processes are not serial transactions. If producer A finished writing and independent
producer B started before A's panel ran, B would build on A's unaccepted changes, and B's changes
would appear in A's review and A's commit. So the unit of exclusion is not a process but the whole
life of a producer: **produce, gates, checks, panel, human decision, then commit or set-aside.**
While a producer is active, only its own steps are scheduled. The transaction ends when the work
tree is verified, by snapshot, to equal a clean accepted state. A human verification that is pending
keeps the transaction open and stops the run; see [02](02-concepts.md#scheduling-d6).

### Reader–writer rule

Inside a transaction, either one writer runs or any number of readers run, never both. A `check` is
a writer unless marked `read_only`, because a build writes files.

### Producer lifecycle

```
become the active producer; snapshot BASE; pin it under refs/task-runner/<run>/
attempt n (own directory, numbered once, never reused):
  run the agent (continue the session on rework; new session after error, timeout or interruption)
  ├─ environment failure .............. stop the run; no attempt is used
  ├─ protocol failure ................. retry the call, at most twice; no attempt is used
  ├─ outcome "blocked" ................ BLOCKED
  ├─ an output missing, a `removes` path present ... feedback, next attempt
  ├─ change outside `writes`, or to a protected or frozen file ... runner reverts it; feedback, next attempt
  snapshot CANDIDATE; pin it
  run own gates, then verifying checks, then regression gates of accepted tasks this one touched
  │   after each: snapshot; tracked source must still equal CANDIDATE, else all results are void
  ├─ fails ............................ feedback = output tail
  │                                     same failure AND same candidate tree as last attempt -> FAILED
  status = verifying; the panel becomes ready (review round r for each member, counted per reviewer)
  when the panel has finished (snapshot again: a reviewer that changed the tree fails the task):
  ├─ an open finding is escalated ..... BLOCKED
  ├─ open blocking findings in ledger . feedback = consolidated findings, next attempt
  verifying human tasks, if any ....... waiting_human; the transaction stays open
  │                                     reject -> feedback, next attempt
  ACCEPTED: write intent; commit exactly CANDIDATE (squashing this task's attempts); record; freeze
attempts used up -> FAILED if a gate or check sent it back last; BLOCKED, with open findings, if review did
FAILED or BLOCKED -> pin CANDIDATE, write failed.patch, restore the task's paths by type and mode,
                     verify the tree equals BASE, mark dependants skipped, end the transaction
```

### Review rounds (A7)

Producer attempts and review rounds are counted separately. A reviewer's **round 1 is its first
sight of a candidate**, on whichever attempt that happens, and is always a full review with the
full BASE-to-CANDIDATE diff. In a later round, members with open blocking findings run in
**judge-the-fix** mode, and members who had passed run on the rework diff only (or not at all, with
`recheck_passed = "never"`). A reviewer always runs in a new session, read-only. Whether a reviewer
blocks is computed from the ledger after its answer is applied; the model's `verdict` field must
agree or the answer is a protocol failure.

## Agent interface
```python
class Agent:
    def run(self, prompt, *, cwd, invocation_dir, schema, session_id, model,
            timeout_s, budget_usd, read_only, env) -> AgentResult
    def capabilities(self) -> set   # what doctor has qualified for this agent, model and profile

AgentResult: status, text, structured, session_id, cost_usd | None, usage, error, seconds
  status: ok | blocked-by-environment | protocol-error | agent-error | timed-out | interrupted
```

| | Claude Code | Codex | Any command |
|---|---|---|---|
| Invocation | `claude -p --output-format json` | `codex exec --json -` | configured `argv` |
| Structured answer | `--json-schema` | `--output-schema FILE`, `-o FILE` | last JSON object in stdout |
| Continue a session | `--resume ID` | `exec resume ID`, never `--last` | not supported |
| Money limit | `--max-budget-usd` | none. Usage is reported at the end of a turn only | none |
| Unattended | `--permission-mode auto --permission-prompts none` | `-c approval_policy="never"` `-c sandbox_mode="workspace-write"` | its own |
| Read-only | edit tools disallowed, plus the snapshot check | `sandbox_mode="read-only"` | `read_only_args` |
| Proper completion | exit 0 and a `result` object that is not an error | exit 0 **and** a `turn.completed` event for this invocation | exit 0 |

Codex is given its sandbox as a config override because `exec resume` has no `--sandbox` flag, and
`--skip-git-repo-check` is not passed, since the runner requires a repository.

### What counts as a result (A6)

An agent call has succeeded only when **all four** hold:

1. the process exited normally;
2. the stream holds a successful terminal event **belonging to this invocation**;
3. the final answer was written **by this invocation**: every call gets a fresh directory created
   exclusively, so a final-message file left by an earlier call can never be read;
4. the answer passes the **runner's own validation**, whichever agent produced it.

Validation is a small, deliberately limited checker for the runner's own schemas: types, enums,
required keys, no unknown keys. It does not claim to implement JSON Schema. On top of the shape it
checks the meaning: a verdict consistent with the ledger, resolutions that name only this
reviewer's own open findings, each exactly once, none missing; responses that cover every blocking
finding the author was sent. A provider's schema feature is a convenience that makes valid answers
likelier. It is never the check.

A failed shell command inside an agent's session is not a failure of the call: a failing test is
ordinary work. What the adapter looks for is a failed **capability**, such as a sandbox that cannot
start.

### Failure classes and what follows

| Failure | Action |
|---|---|
| Sandbox or namespace startup, missing binary | **Environment failure.** Stop the run with the cause. No attempt is used |
| Authentication or configuration | Environment failure, before any producer attempt |
| Transient transport error or rate limit | Bounded backoff; every invocation's record is kept |
| No terminal event, or an invalid answer | **Protocol retry**, at most twice, fresh invocation directory. Not a producer attempt, not a finding |
| A valid answer with `blocked` | The engine records `blocked` with the reason |
| A valid review leaving an open blocker | Producer rework, which uses a producer attempt |
| Timeout or interruption | Stop the process group, reconcile, abandon the session |

### Capabilities and `doctor` (A5)

Answering a greeting proves nothing about reading files. `doctor` qualifies each agent, model and
permission profile the workflow uses, **per capability**, in a scratch repository:

| Capability | Needed by | How the runner checks it, without trusting the agent's word |
|---|---|---|
| `answer` | every task | The exact expected object comes back with a proper terminal event |
| `read` | repository-reading review | A random value exists only in a scratch file; the agent must return it, and the stream must show the read succeeded |
| `execute` | authors, reviewers who run things | A tool event shows the intended command ran successfully |
| `write` | authors | The runner reads the expected change back from the scratch file |
| `resume` | authors, for rework | A second call on the explicit session id returns the expected follow-up |
| `boundary` | read-only reviewers | A write the profile forbids is denied and a sentinel file is unchanged |

A task type states what it needs: `implement` needs `write`, `execute`, `resume`; `code-review` needs
`read`. A workflow whose agents lack a needed capability is refused before any producer runs.
Qualification costs money, so it is recorded in the run's accounting and cached by binary version,
profile hash, host identity and capability; `doctor --force` repeats it.

**Review modes.** A reviewer with `read` does a repository review. A reviewer with only `answer`
may be used for **text-only review**, if the workflow says so explicitly
(`review_mode = "provided_context"`): the runner puts the complete evidence in the prompt and records
an evidence manifest, the record labels the review as text-only, and if the evidence does not fit
the context budget the review fails instead of proceeding on part of it. One mode is never silently
substituted for the other.

### Profiles and reproducibility

A frozen workflow does not by itself reproduce a call, because agents also read user and project
configuration: hooks, MCP servers, model defaults. Each agent entry in a workflow is therefore a
**named profile**, and the run records the agent's version, the profile's non-secret effective
settings and their hash. Ignoring user configuration is an explicit profile setting, never a
default, since it can drop integrations the owner wants. Credentials are never written to
`argv.json`, prompts or environment dumps. Gates and checks run with an environment that does not
include the agents' authentication variables.

### Processes and logs

Every agent and command is started in its own process group. Standard output and error are
**streamed to files in the invocation directory as they arrive**, with a bounded tail kept in memory
for feedback, and the event stream is parsed incrementally. A crash of the runner therefore loses
no output, and a command that prints without end cannot exhaust memory. Unknown event types are
kept, for forward compatibility. At a deadline, and when the runner itself is shutting down, the
group is sent SIGINT, then SIGTERM, then SIGKILL. `env` carries `TASK_RUNNER_RUN`,
`TASK_RUNNER_TASK` and `TASK_RUNNER_RUN_DIR`.

## Git
One primitive does most of the work: `snapshot()` returns a git tree id for the whole work tree,
untracked-but-not-ignored files included, built in a scratch index so the real index is never
touched. Every snapshot the run relies on (each BASE, each CANDIDATE, each set-aside) is **pinned
under `refs/task-runner/<run>/…`**, so git's garbage collection cannot remove it while the run
exists.

| Need | Operation |
|---|---|
| What did this attempt change? | names between two snapshots |
| Changed outside `writes`, or a protected or frozen file? | match those names against the globs |
| Put paths back (A3) | With a scratch index loaded from the base tree, `git checkout-index --force` for those paths. Git recreates each entry by its recorded **type and mode**: it unlinks first, so a symbolic link is replaced and never written through, and the executable bit is restored. Paths the base did not have are removed with `lstat` and `unlink`. Before either, every parent directory is checked to be a real directory inside the repository. Submodule entries and paths that are neither file nor link are refused |
| Verify a restore | snapshot again: the tree id must equal the base's |
| The reviewer's diff | text diff BASE to CANDIDATE, capped for the prompt. **For reading only** |
| Recovery artifact | the pinned candidate tree, plus `git diff --binary --full-index` written in full. Never the capped text |
| Did a reviewer, gate or check change tracked source? | snapshots before and after must be equal |
| Accept (D13) | commit exactly the CANDIDATE tree's changes to the task's paths on the run branch, with `Run:`, `Task:` and `Operation:` trailers |

The runner never runs `reset --hard`, `clean`, `stash`, `push` or `merge`. It touches only paths a
task changed, and only to return them to a state it recorded. `replan --reopen` undoes commits with
`git revert`, which adds commits and removes none.

`start` refuses a dirty work tree **without exception (A4)**, creates `run/<workflow>-<uuid8>` from
HEAD, and records the base commit. With `branch = "current"` it commits on the checked-out branch.

## Crash recovery (A2)

An atomic `state.json` protects the state file. It cannot make a subprocess, a file write, a commit
and a state update happen together. So every external effect follows **intent, effect, outcome**:

1. **Intent.** Before the effect, the state records an operation with a unique id, its kind, and
   what is expected: for an agent call, the invocation directory; for a commit, the expected parent,
   the candidate tree, the task and the attempt. State is written to a temporary file, flushed and
   synced, renamed, and the directory synced.
2. **Effect.** The agent runs, or the commit is made with the operation id in its trailer.
3. **Outcome.** The state records the result and clears the intent.

On `resume`, every intent without an outcome is reconciled before anything else happens:

| Found | Meaning | Action |
|---|---|---|
| A commit intent, and the branch tip carries that operation id and the expected tree | The commit happened; the crash came before recording it | Record acceptance. The author is not run again |
| A commit intent, and the tip is still the expected parent | The commit did not happen | Verify the tree still equals the candidate, then commit |
| A commit intent, and the tip is anything else | Someone changed the branch | Stop with a reconciliation error that says what was expected and what was found |
| An agent intent whose process group is still alive | The previous runner died and left the agent running | Refuse to continue until it is stopped; `resume --stop-orphans` stops it. Never start a second author beside it |
| An agent intent with no live process and no terminal event | Completion unknown | Mark the invocation `interrupted`, never successful. Abandon the session. The interrupted invocation keeps its directory; the retry gets a new one |

A process is identified by its group id **and its start time**, not by a pid alone, since pids are
reused. The same identity is kept in the repository lock in `.runs/`. While a run is paused for a
person, its expected branch tip and tree are recorded, and `resume` checks them first.

## Limits, all checked before a call is made
| Limit | Default | Enforced by |
|---|---|---|
| `max_attempts` per producer | 3 | engine |
| Protocol retries per call | 2 | engine. Separate from attempts |
| No-progress stop | same gate failure **and** same candidate tree (A12) | engine |
| `timeout_min` per agent call | 30 | runner's clock |
| `gate_timeout_min` per command | 20 | runner's clock |
| `budget_usd` per agent call | 5 | the agent, where it can |
| `run_budget_usd` | 50 | engine, **by reservation** (A11) |
| `max_parallel` readers | 4 | scheduler |
| One run at a time per repository | | a lock in `.runs/` holding run id, process group and start time |

**Reservation (A11).** For an agent that enforces a per-call cap, the engine reserves that cap from
the run budget before starting the call and replaces the reservation with the actual cost when it
ends. A call is not started unless its whole reservation fits. So four reviewers cannot each start a
$5 call with $1 left: none starts, and the run stops as out of budget.

**Honest accounting.** `STATUS.md` and `run.json` report three numbers, never one: **known spend**,
**reserved**, and **unpriced usage** (tokens from agents that report no cost, and interrupted calls
whose usage is unknown). Unpriced usage never counts as zero dollars against a limit, and is never
converted into invented dollars. Codex reports usage only when a turn completes, so it offers no
in-call token or money cap: a Codex call is bounded by time and attempts, and the documentation of a
workflow that uses it must not promise a dollar ceiling.

## Command line

```
runner validate WORKFLOW              check everything; print the expanded DAG in execution order
runner graph WORKFLOW [-o FILE]       write the DAG as Graphviz DOT
runner doctor WORKFLOW [--force]      qualify each agent, model and profile per capability; refuse a workflow that needs more
runner check-gates WORKFLOW           run every gate and check on the untouched tree and report pass, fail or error for each
runner start WORKFLOW                 create a run and execute it
runner resume [RUN] [--stop-orphans]  reconcile, then continue a run (default: the latest unfinished one)
runner status [RUN] [--rebuild]       print STATUS.md; --rebuild regenerates all derived files
runner runs WORKFLOW                  list runs with status, cost and date
runner approve RUN TASK [-m NOTE]     a person approves a human task
runner reject RUN TASK -m NOTE        a person rejects; the note becomes feedback
runner retry RUN TASK [--apply-patch] fresh attempts for a failed or blocked task
runner resolve RUN FINDING --as resolved|advisory [-m NOTE]    a person settles an escalated finding
runner replan RUN [--reopen TASK]     bring an edited workflow into the run, where safe
```

`RUN` is a directory name, a UUID prefix, or `latest`.

| Exit | Meaning |
|---|---|
| 0 | Every task is accepted |
| 2 | Something failed, or the workflow or environment is wrong |
| 255 | A person is needed |

## What is deliberately left out of the first version

| Left out | How it will fit later |
|---|---|
| Parallel writers | One git worktree per running producer, merged in workflow order. The scheduler's reader–writer rule becomes per worktree |
| Conditional routing | A `when` expression on a task over upstream results. The DAG stays acyclic |
| Dynamic tasks (a planning task that emits tasks) | `replan` already adds tasks to a live run; a `plan` type would feed it, behind a human approval |
| The hook logger's session scorecard as a stuck signal | The engine reads it after a producer's attempt; red means abandon the session |
| Importing Attractor DOT | `graph` exports DOT now; importing needs only a parser, since the engine's model is a superset of a linear Attractor pipeline |
