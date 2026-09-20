# 03 — Implementation plan

Status: **plan only. The build has not started and waits for the owner's go-ahead.**
Design: [01](01-design.md). Architecture: [02](02-architecture.md).

## Approach

Build it fresh in `tools/runner/`, in the five stages below, test-first against the scenario table.
The [prototype](../prototype/README.md) is reference material: it proves the approach and its code
may be borrowed, but it was written in one pass without the scenarios below, it has no `doctor` or
`check-gates`, and its modules are not split as [02](02-architecture.md) describes. Each stage ends
with all tests green and costs nothing to test, except stage 4.

## Layout

```
tools/runner/
  runner.py                 entry point
  taskrunner/
    plan.py  state.py  agents.py  gates.py  gitops.py  prompts.py  engine.py  cli.py
  tests/
    test_plan.py  test_gitops.py  test_agents.py  test_engine.py  test_cli.py
    fake_agent.py           a scripted agent, driven by a JSON file
  README.md
  example-plan.toml
plans/
  nyse-m1/plan.toml  items/*.md
```

## Stages

### Stage 1 — Plan and state (no agents, no git)

`plan.py`, `state.py`, `cli.py` with `validate` and `status`.

Done when: PLAN-01 to PLAN-07 and STATE-01 to STATE-03 pass.

### Stage 2 — Engine with a scripted agent

`gates.py`, `gitops.py`, `prompts.py`, `engine.py`, the `command` adapter, `fake_agent.py`, and the
`run`, `next`, `approve`, `retry` commands. The whole task life cycle works end to end here, with no
model involved.

Done when: every RUN-, ACC-, EFF- and GIT- scenario passes.

### Stage 3 — Claude Code and Codex adapters

The two adapters, tested without running either tool: command lines are compared with expected
lists, and parsers are fed recorded output. The recorded output comes from the prototype's live run
(`stdout.log` files), so the tests match what the real tools print.

Done when: AGENT-01 to AGENT-08 pass.

### Stage 4 — Preflight and the live check

`doctor` and `check-gates`. Then one live run of a two-task scratch plan, Claude implementing and
reviewing, to confirm nothing drifted since the prototype. Codex is included only in an environment
where its sandbox can start, or where the owner has chosen to turn it off.

Done when: PRE-01 to PRE-04 pass, and the live run ends with exit 0 and two commits. Expected cost:
under $2 with a small model.

### Stage 5 — First real plan

Write `plans/nyse-m1/`: one work item per M1 step 2 to 12, each with its scenario IDs and gate.
This needs one change outside the runner: an ID-prefix filter for
`nyse-handler/tools/check_scenarios.py`, so a gate can demand "every BOOK- scenario has a test".
Protected globs: the scenario tables, the spec notes, reviewed fixtures, golden files, the
reference book once written, and the gate scripts. Step 4 (fixtures) has `human_review = true`.

Run step 2 alone. Read the whole transcript and the diff before letting the run continue.

Done when: step 2 is committed by the runner and the owner is satisfied with what it did.

## Scenarios

The same convention as the NYSE design documents: each row names the test that proves it.

### Plan

| ID | WHEN | THEN | Test |
|---|---|---|---|
| PLAN-01 | a plan has only `id`, `prompt` and `gate` per task | it loads, and every other setting has its default | `plan: minimal plan gets defaults` |
| PLAN-02 | a task has no `gate` | loading fails and says a task with no check cannot be verified | `plan: gate is mandatory` |
| PLAN-03 | any table has an unknown key | loading fails and names the key | `plan: unknown keys are errors` |
| PLAN-04 | `needs` names a task that does not exist, or tasks form a cycle | loading fails and names the tasks | `plan: bad dependencies are errors` |
| PLAN-05 | a plan has several errors | all are reported together | `plan: all errors at once` |
| PLAN-06 | tasks are listed out of dependency order | the order puts dependencies first, and otherwise follows the file | `plan: stable dependency order` |
| PLAN-07 | the same plan is loaded twice | the order is identical | `plan: order is deterministic` |

### State

| ID | WHEN | THEN | Test |
|---|---|---|---|
| STATE-01 | the process is killed while saving | `state.json` is the old or the new version, never a partial one | `state: atomic save` |
| STATE-02 | a run stops and a new process starts | it continues at the same task and phase | `state: resume from disk` |
| STATE-03 | a task is added to the plan after a run began | it appears as pending and the finished tasks stay done | `state: plan grows` |

### Running

| ID | WHEN | THEN | Test |
|---|---|---|---|
| RUN-01 | every task's gate and review pass first time | exit 0, one commit per task in plan order, a clean work tree | `run: happy path` |
| RUN-02 | a gate fails, then passes on the second attempt | the second prompt contains the gate's output, and the task is done with 2 attempts | `run: gate feedback and retry` |
| RUN-03 | a gate never passes | the task fails after `max_attempts`, exit 2, nothing committed | `run: attempts are bounded` |
| RUN-04 | the agent answers "blocked" | exit 255, and the reason is shown by `run` and `status` | `run: blocked needs a person` |
| RUN-05 | `human_review` is set and the gate and review pass | exit 255 with nothing committed; after `approve`, the commit is made | `run: human gate` |
| RUN-06 | `retry` is given for a failed task | attempts restart from zero with a new session | `run: retry` |
| RUN-07 | a task fails | later tasks do not start, even independent ones | `run: stop at first failure` |
| RUN-08 | the run budget is already spent | no agent is called, exit 2 | `run: run budget checked before the call` |

### Accuracy

| ID | WHEN | THEN | Test |
|---|---|---|---|
| ACC-01 | the agent reports "done" and the gate fails | the task does not pass | `acc: agent report is never acceptance` |
| ACC-02 | the agent changes or adds a protected file | the file is restored or removed, the attempt does not pass, the next prompt names the file, and the file is not in the commit | `acc: protected files` |
| ACC-03 | the reviewer answers in prose containing "APPROVED" | it is not an approval | `acc: only a boolean verdict counts` |
| ACC-04 | the reviewer rejects with reasons | the next implement prompt contains them | `acc: review feedback` |
| ACC-05 | the reviewer gives no usable verdict twice | the task fails | `acc: review fails closed` |
| ACC-06 | the reviewer changes the work tree | the task fails | `acc: reviewer cannot edit` |
| ACC-07 | the work tree is dirty at the start | the run refuses, unless `allow_dirty` | `acc: clean start` |

### Efficiency

| ID | WHEN | THEN | Test |
|---|---|---|---|
| EFF-01 | a gate fails and the agent supports sessions | the retry continues the session and its prompt holds only the failure | `eff: retry continues the session` |
| EFF-02 | the agent errors or times out | the next attempt starts a new session with the full prompt | `eff: broken session is abandoned` |
| EFF-03 | the gate fails twice with output that differs only in timings | the task fails as "no progress" on attempt 2 | `eff: no-progress stop` |
| EFF-04 | the gate fails | the reviewer is not called | `eff: review only after the gate` |
| EFF-05 | an agent runs past `timeout_min` | it is stopped within the grace period and the result is not ok | `eff: the runner owns the clock` |
| EFF-06 | a gate prints a very long log | the feedback is the last 4,000 characters and the whole log is on disk | `eff: feedback is trimmed` |

### Git

| ID | WHEN | THEN | Test |
|---|---|---|---|
| GIT-01 | a snapshot is taken | the real index and work tree are unchanged | `git: snapshot has no side effects` |
| GIT-02 | the task creates a new file | it appears in the reviewer's diff and in the commit | `git: untracked files are seen` |
| GIT-03 | `allow_dirty` is set and the owner has other changes | the commit holds only the task's files | `git: commit only task files` |
| GIT-04 | the task changes nothing and the gate passes | the task is done with no commit | `git: nothing to commit` |
| GIT-05 | the root is not a git repository | the run works, with a warning and no commits | `git: optional` |

### Agents

| ID | WHEN | THEN | Test |
|---|---|---|---|
| AGENT-01 | a Claude call is built | it has print mode, JSON output, the permission flags, the schema, the budget and the model | `agent: claude command line` |
| AGENT-02 | a Claude retry or review is built | it has `--resume`, or the disallowed edit tools | `agent: claude resume and read-only` |
| AGENT-03 | Claude's recorded success, budget stop and non-JSON outputs are parsed | ok with session, cost and verdict; not ok with the subtype; not ok with the raw text | `agent: claude results` |
| AGENT-04 | a Codex call, retry or review is built | `exec`, or `exec resume ID`; the sandbox as a config override; read-only for review; the prompt on stdin | `agent: codex command line` |
| AGENT-05 | Codex's recorded event stream is parsed | thread ID, last agent message, summed tokens, cost `None`; a `turn.failed` event is not ok | `agent: codex results` |
| AGENT-06 | an agent with no schema feature ends its answer with a JSON object | that object is the verdict | `agent: JSON fallback` |
| AGENT-07 | a plan defines a `command` agent | it runs with the prompt on stdin and needs no code | `agent: any command` |
| AGENT-08 | an agent binary is missing | the result is not ok, with a clear message, and the run does not crash | `agent: missing binary` |

### Preflight

| ID | WHEN | THEN | Test |
|---|---|---|---|
| PRE-01 | `doctor` runs | each agent the plan uses answers a one-line prompt, or the failure is shown with its cause | `pre: doctor` |
| PRE-02 | an agent's sandbox cannot start | `doctor` says so before any task runs | `pre: doctor catches sandbox` |
| PRE-03 | `check-gates` runs on an untouched tree | a gate that already passes is reported, since it cannot show the task was done | `pre: gates must fail first` |
| PRE-04 | a gate command cannot run at all (wrong flag, missing tool) | `check-gates` tells "cannot run" apart from "fails as expected" where the exit code allows (126, 127), and prints the output for the rest | `pre: broken gates` |

## Risks

| Risk | Mitigation |
|---|---|
| Agent CLIs change their flags or output | Adapters are small and isolated. `doctor` runs before every real plan. Tests use recorded output, so a change shows up as a live failure with an obvious cause, not as silent misbehaviour |
| Tasks too large for one attempt | The cost and attempt counts in `status` show it at once. The fix is in the task list |
| A gate that is wrong | `check-gates`, and the agent's "blocked" answer, which the prototype showed to work |
| The reviewer is too strict or too lax | Reasons are logged per attempt. A plan can change reviewer or turn review off per task |
| Codex cannot implement in this container | Known. The owner chooses per plan: Claude implements and Codex reviews, or the sandbox is turned off inside the container, or Codex runs on a host with user namespaces |
| The owner's default model makes small tasks expensive | Set `model` in `[defaults]` of each plan |

## Open questions for the owner

| # | Question | Default if unanswered |
|---|---|---|
| 1 | Where do plans live: `plans/<name>/` at the top, or beside the project they build (`nyse-handler/plan/`)? | `plans/<name>/` |
| 2 | Should a run use its own branch (`run/<plan>`) by default? | No: the current branch, since the owner already works on feature branches |
| 3 | Which model should NYSE tasks use by default? | The account default for the decoder, book and arbiter; a smaller model for wiring and config |
| 4 | Codex in this container: reviewer only, or implement with its sandbox off? | Reviewer only |
| 5 | Should runner commits carry a trailer naming the agent? | Yes, from a `commit_trailer` setting, empty by default |

## After the first version

In the order the design expects to need them: a token limit per call, the session scorecard as a
stuck signal, parallel tasks with a git worktree each, and compiling the task list to an Attractor
graph if custom routing is ever wanted.
