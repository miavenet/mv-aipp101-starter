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
| `record` | The run directory: create it, save state atomically, append events, write attempt and round files, regenerate `STATUS.md` and `index.json` from state |
| `prompts` | Render a type's template for a task. Pure functions of the expanded task, the state and the upstream results |
| `agents` | One interface, three adapters (Claude Code, Codex, any command). Build the command line, run it under the runner's clock, parse the answer |
| `checks` | Run gate and check commands with a timeout. Return pass or fail and the output |
| `gitops` | Work-tree snapshots, changed paths between snapshots, diffs, restoring paths, saving a patch, the run branch, commits |
| `findings` | The ledger: assign ids, apply responses and resolutions, enforce the later-round rule, decide whether any blocking finding is open |
| `engine` | The scheduler and the task lifecycle. **The only module that decides anything**, and only from exit codes, verdict fields, ledger status and counters |
| `cli` | Commands, exit codes, printing |

`agents`, `checks`, `gitops` and `record` report facts. `workflow` and `prompts` are pure. That keeps
the part that must be deterministic (`engine`, `findings`) small and free of I/O details, so it can
be tested exhaustively with scripted agents.

## The engine loop

```
load state
repeat:
    apply finished work           (results are applied in workflow order, never arrival order)
    if nothing is running:
        pick what can start:
            a writer is ready and no readers are running  -> start that one writer (first in order)
            else readers are ready                        -> start up to max_parallel of them
    if nothing is running and nothing can start: stop
    wait for any running job to finish
    save state; regenerate STATUS.md
```

Run status when the loop stops: `done` if every task is accepted; `needs_human` if any task is
`waiting_human` or `blocked`; otherwise `failed`. Exit codes 0, 255, 2.

Parallel jobs are subprocesses (agents and commands already are), supervised from one thread with
the standard library's `concurrent.futures`. There are no threads inside the decision logic.

### Reader–writer rule

The repository work tree is shared, and reviewers browse it. So at any moment either one writer runs
or any number of readers run, never both. A `check` is a writer unless marked `read_only`, because a
build writes files.

### Producer lifecycle

```
attempt n:
  snapshot BASE (first attempt only)
  run the agent (continue the session on rework; new session after an error or timeout)
  ├─ agent error / timeout ............ next attempt, new session
  ├─ outcome "blocked" ................ BLOCKED
  ├─ a declared output is missing ..... feedback, next attempt
  ├─ protected or frozen file changed . runner reverts it; feedback, next attempt
  run own gates, then verifying checks
  ├─ fails ............................ feedback = output tail; same failure twice -> FAILED; else next attempt
  status = verifying; the panel becomes ready
  when the panel has finished:
  ├─ an open finding is escalated ..... BLOCKED
  ├─ open blocking findings ........... feedback = consolidated findings, next attempt
  verifying human tasks, if any ....... waiting_human until approve / reject (reject -> feedback, next attempt)
  ACCEPTED: commit (squashing this task's attempts), freeze outputs
attempts used up -> FAILED if a gate or check sent it back last; BLOCKED, with the open findings listed, if review did
FAILED or BLOCKED -> save failed.patch, restore the task's paths to BASE, mark dependants skipped
```

### Review rounds

Round *k* of a reviewer corresponds to attempt *k* of its producer. In round 1 every panel member
runs. In a later round, members with open blocking findings run in **judge-the-fix** mode, and
members who had passed run on the rework diff only (or not at all, with `recheck_passed = "never"`).
A reviewer always runs in a new session, read-only, and the runner compares work-tree snapshots
before and after the panel: a change fails the producer, because the gates and the verdicts would no
longer describe the same code.

## Agent interface

Unchanged in shape from the research design, because the prototype proved it against both tools.

```python
class Agent:
    def run(self, prompt, *, cwd, log_dir, schema, session_id, model,
            timeout_s, budget_usd, read_only, env) -> AgentResult

AgentResult: ok, text, structured, session_id, cost_usd | None, tokens, error, timed_out, seconds
```

| | Claude Code | Codex | Any command |
|---|---|---|---|
| Invocation | `claude -p --output-format json` | `codex exec --json -` | configured `argv` |
| Structured answer | `--json-schema` | `--output-schema FILE`, `-o FILE` | last JSON object in stdout |
| Continue a session | `--resume ID` | `exec resume ID` | not supported |
| Money limit | `--max-budget-usd` | none; tokens are counted | none |
| Unattended | `--permission-mode auto --permission-prompts none` | `-c sandbox_mode="workspace-write"` | its own |
| Read-only | edit tools disallowed, plus the snapshot check | `sandbox_mode="read-only"` | `read_only_args` |

Rules for every adapter: the schema is also written into the prompt, and the last JSON object in the
final message is accepted if the schema feature returned nothing; schemas are strict; the runner
owns the clock (SIGINT, then SIGTERM, then SIGKILL, to the process group); a timed-out session is
never continued. `env` carries `TASK_RUNNER_RUN`, `TASK_RUNNER_TASK` and `TASK_RUNNER_RUN_DIR`.

## Git

One primitive does most of the work: `snapshot()` returns a git tree id for the whole work tree,
untracked files included, built in a scratch index so the real index is never touched.

| Need | Operation |
|---|---|
| What did this attempt change? | names and diff between two snapshots |
| Protected or frozen file touched? | match those names against the globs |
| Put a file back | write the blob from the base tree, or delete a file the base did not have |
| The reviewer's diff | diff between the producer's BASE and its current snapshot. Includes new files |
| Did a reviewer edit anything? | snapshots before and after the panel must be equal |
| Set failed work aside (D9) | save the BASE-to-now diff as `failed.patch`, then restore exactly those paths |
| Accept (D13) | `git add -A -- <paths>`, `git commit -- <paths>`, on the run branch |

The runner never runs `reset --hard`, `clean`, `stash`, `push` or `merge`. It touches only paths a
task changed, and only to return them to a state it recorded.

`start` refuses a dirty work tree, creates `run/<workflow>-<uuid8>` from HEAD, and records the base
commit. With `branch = "current"` it commits on the checked-out branch instead.

## Limits, all checked before a call is made

| Limit | Default | Enforced by |
|---|---|---|
| `max_attempts` per producer | 3 | engine |
| No-progress stop | same gate failure twice | engine |
| `timeout_min` per agent call | 30 | runner's clock |
| `gate_timeout_min` per command | 20 | runner's clock |
| `budget_usd` per agent call | 5 | the agent, where it can |
| `run_budget_usd` | 50 | engine: no new agent call once reached. In-flight calls finish |
| `max_parallel` readers | 4 | scheduler |
| One run at a time per repository | | a lock file in `.runs/` holding the pid and run id |

Agents that report no cost (Codex) are bounded by time, attempts and an optional `max_tokens` per
call, counted from their event stream.

## Command line

```
runner validate WORKFLOW              check everything; print the expanded DAG in execution order
runner graph WORKFLOW [-o FILE]       write the DAG as Graphviz DOT
runner doctor WORKFLOW                test each agent the workflow uses; report versions and sandbox problems
runner check-gates WORKFLOW           run every gate and check on the untouched tree: each should FAIL now
runner start WORKFLOW                 create a run and execute it
runner resume [RUN]                   continue a run (default: the latest unfinished one)
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
