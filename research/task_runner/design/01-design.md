# 01 — Design: what the task runner does and why

Status: **design only. Nothing here is built.** A throwaway [prototype](../prototype/README.md) tested
the ideas against the real tools; what it taught is in [the last section](#what-the-prototype-taught-us).
Evidence for the choices is in [`../ANALYSIS.md`](../ANALYSIS.md).

## Purpose

Take a list of tasks and carry it to completion with a headless coding agent, without a person
watching. "Completion" means every task has passed a check that does not depend on the agent's own
word.

## Requirements

From the owner:

| # | Requirement |
|---|---|
| R1 | **Model agnostic.** No agent or model is built in to the engine. Claude Code and Codex must both work in headless mode; any other agent can be added by configuration |
| R2 | **Reasonable defaults.** A plan needs only task IDs, prompts and acceptance commands. Everything else has a default |
| R3 | **Input is a task list**, with dependencies between tasks |
| R4 | **Runs to completion**, autonomously, and deterministically in everything except the agent's own work |
| R5 | **Accurate.** A task is done only when it is verifiably done |
| R6 | **Efficient.** No wasted agent calls, tokens or wall-clock time |

Derived:

| # | Requirement |
|---|---|
| R7 | **Resumable.** A crash, a budget stop, a reboot or a human pause loses nothing. Running again continues |
| R8 | **Bounded.** Every agent call has a time limit and, where possible, a money limit. The run has both |
| R9 | **Auditable.** For every attempt: the exact prompt, the exact command line, the agent's output, the gate's output, the verdict, the cost |
| R10 | **No dependencies.** Python 3.11+ standard library. The container cannot `pip install`, and has no Go |
| R11 | **Safe by default.** The safe agent settings are the defaults. Anything looser is an explicit per-plan choice |

## Not goals

- An agent loop or an LLM client. Claude Code and Codex already are these.
- A general workflow engine. One fixed path per task, not arbitrary graphs. See
  [why not DOT](#why-a-task-list-and-not-attractors-dot-graph).
- Breaking a project into tasks. That is a separate step, done by a person with an agent's help,
  and reviewed before the run. The runner only checks that the list is well formed.
- Parallel execution in the first version.

## The idea in one paragraph

An agent's work cannot be made deterministic. Everything around it can: the order of tasks, the
path each task takes, what counts as passing, and the state on disk. The runner fixes those four,
and bounds the fifth with attempts, time and money. This is the core of Attractor (fixed routing,
a status contract, a checkpoint per step, a pluggable backend) combined with agate's operating
habits (all state on disk, a loop that only reads exit codes, a fake agent for tests), plus the one
thing both lack: **gates that are commands, not opinions.**

## The life of a task

```
             ┌────────────────────── feedback: gate output ──────────────────────┐
             │                 ┌──── feedback: reviewer's reasons ────┐          │
             ▼                 ▼                                      │          │
pending ─► implement ───────► gate ───────────► review ───────────► human ─────► commit ─► done
             │                 │ same output twice   │ reviewer          (only if
             │ "blocked"       ▼                     │ edits the tree     human_review)
             ▼               failed                  ▼
           blocked                                 failed
             (attempts used up ─► failed)
```

| Phase | Who acts | Passes when | On failure |
|---|---|---|---|
| **implement** | The task's agent | The agent ran without error, did not answer "blocked", and touched no protected file | Agent error or timeout: next attempt, in a **new** session. Protected file touched: files are put back, next attempt. "blocked": the task stops and a person is needed |
| **gate** | The runner | Every `gate` command exits 0, in order | Output goes back to the agent as feedback, next attempt. The same output twice running: the task fails early |
| **review** | A second agent, new session, read-only | It returns `{"approved": true, ...}` in exactly that shape | `approved: false`: its reasons go back as feedback, next attempt. No usable verdict twice: the task fails. The work tree changed during review: the task fails |
| **human** | A person, only if `human_review = true` | `runner approve TASK` | The run stops with exit 255 until then |
| **commit** | The runner | Always | — |

An attempt is one pass through implement. `max_attempts` (default 3) bounds the whole loop,
whichever phase sent the task back.

## Accuracy: the rules

1. **A gate is mandatory.** A task without an acceptance command is rejected when the plan loads.
   If it cannot be checked, it cannot be run unattended.
2. **Only exit codes and structured verdicts count.** The implementing agent's report is recorded
   and never used for acceptance. A reviewer's verdict must be a JSON object with a boolean
   `approved`. Prose containing "approved" is not approval. (agate's gate is the substring
   `APPROVED`; this is the fix.)
3. **Review from a fresh context.** The reviewer never sees the implementer's reasoning, only the
   task, the diff and the fact that the gates pass. It is told to look for weakened tests and
   special-cased inputs. By default the reviewer is the same agent type in a new session; a plan can
   name a different agent, which gives a second model's opinion.
4. **Protected files.** Globs listed in `protected` are compared before and after implement. Any
   change is reverted by the runner and the attempt does not pass. The instruction in the prompt is
   a courtesy; the revert is the control. (Evidence: read-only tests stopped test tampering in
   ImpossibleBench without hurting legitimate work.)
5. **"Blocked" is a legal answer.** The agent is told that a task it cannot do properly should be
   answered with `outcome: "blocked"` and a reason. This gives a hard task an honest exit that is
   not cheating.
6. **The reviewer cannot change the code.** It runs with read-only tools where the agent supports
   that, and the runner compares the work tree before and after regardless. A change invalidates
   both the verdict and the gate result, so the task fails.
7. **A clean start.** The run refuses to start on a work tree with uncommitted changes, because a
   task's changes could not then be told apart from the owner's. `allow_dirty` overrides this.
8. **One commit per task, holding only that task's files.** A bad task can be reverted alone, and
   the history reads as the task list.

## Efficiency: the rules

1. **A retry continues the agent's session** and sends only what is new: the gate output or the
   reviewer's reasons. The agent keeps its understanding of the code, and the provider's prompt
   cache is reused. Exception: after an agent error or a timeout the session is abandoned, because
   a session that went wrong tends to stay wrong (see
   [`../../session_evaluation/ANALYSIS.md`](../../session_evaluation/ANALYSIS.md)).
2. **Cheap checks before expensive ones.** Protected-file check, then gate, then review. The review
   is only paid for when the gates pass.
3. **Stop early when stuck.** The same gate output twice running ends the task. Timings are
   stripped before comparing, so "took 12 ms" and "took 14 ms" are the same failure.
4. **Budgets are checked before a call, not after.** Per call (`budget_usd`, enforced by the agent
   where it can), per run (`run_budget_usd`, enforced by the runner), and wall clock per call
   (`timeout_min`, always enforced by the runner).
5. **Model per task.** `model` and `review_model` let simple tasks use a cheaper model.
6. **Feedback is trimmed.** The last 4,000 characters of the failing command's output, not the
   whole log. The full log is on disk.
7. **The runner itself costs nothing.** No model calls of its own, no daemon, no database.

## Determinism: what is and is not fixed

| Fixed | How |
|---|---|
| Task order | Dependencies first; among ready tasks, the order in the file. No timestamps, no hashing, no randomness |
| Path through a task | The table above. Each transition depends only on an exit code, a boolean, or a counter |
| Acceptance | Commands and a schema |
| State | One JSON file, written atomically after every phase |
| Prompts | Built from the plan and the recorded feedback by a pure function. The same state gives the same prompt, byte for byte |

| Not fixed | How it is bounded |
|---|---|
| What the agent writes | Gates, review, protected files |
| How long it takes | `timeout_min`, `gate_timeout_min` |
| What it costs | `budget_usd`, `run_budget_usd`, `max_attempts` |

## Defaults

| Setting | Default | Why this value |
|---|---|---|
| `agent` | `claude` | Present in this environment, and the only one proven end to end here |
| `reviewer` | same agent, new session | Works with one agent installed. A different agent is better when available |
| `review` | on | The gate catches "does not work"; only review catches "works by cheating" |
| `human_review` | off | On for tasks whose output a person must sign, such as NYSE fixture review |
| `max_attempts` | 3 | The value agate, the Dark Factory write-up and our own research converge on |
| `timeout_min` | 30 | A guess. A task that needs longer is probably too big |
| `gate_timeout_min` | 20 | Room for a full C++ build and test run |
| `budget_usd` | 5 | A guess. The prototype's trivial task cost $0.10 to $0.50 per call |
| `run_budget_usd` | 50 | Ten tasks at the per-call default |
| `commit` | on | |
| `branch` | current branch | A plan can name a run branch |
| `protected` | none | Project-specific |
| Agent permissions | Claude: `--permission-mode auto --permission-prompts none`. Codex: `workspace-write` sandbox | The documented unattended settings. Nothing is bypassed by default |

## Why a task list and not Attractor's DOT graph

The research decision proposed Attractor's DOT format. The owner's requirement is a task list, and
the prototype showed the list is enough:

- Every task in our plans has the same shape (implement, check, review, commit). A graph language
  that can express any shape would be used to write the same shape twelve times.
- A list with `needs` is easier to write, to review and to validate than a graph with conditions.
- What Attractor's graph gives that a list does not is custom routing and fan-out. Neither is
  needed yet.

What is kept from Attractor: the pluggable backend seam, the outcome contract (`outcome`, `notes`),
a checkpoint at every step boundary, deterministic routing, the human gate that pauses the run, and
exit codes as the interface. If custom routing is ever needed, the task list can be compiled to a
graph, and the engine's phase table becomes that graph's edges. Nothing in this design blocks that.

## What the prototype taught us

A 1,100-line spike (13 tests, plus a live two-task run with each agent reviewing the other's task) found:

| Finding | Effect on the design |
|---|---|
| The Claude Code flags work as documented under OAuth: JSON result, `--json-schema`, `--resume`, `--max-budget-usd`, and `auto` permissions with prompts off | The main risk in the research decision is retired |
| A $0.50 call budget was used up in 5 turns on a trivial task. With the owner's default model, the fixed context (about 65k tokens) dominates the cost of small tasks | Keep the $5 default. Document `model` per task. Report cost per task in `status` |
| Given a wrong gate command and protected tests, Claude answered "blocked" and named the exact cause, instead of working around it | Rule 5 works in practice. **Gate commands must be tested before a run**: add `runner check-gates`, which confirms each gate *fails* on the untouched tree |
| Codex as reviewer rejected a first version with a concrete reason, then approved the second | Cross-agent review works and is worth offering |
| Codex's own sandbox cannot start in this container (no user namespaces), so Codex cannot implement here at the safe default. The permission system refused to let an agent turn that sandbox off | The default stays safe. Turning a sandbox off is a **person's** per-plan decision. Add `runner doctor`, which tests each agent before a run |
| Python bytecode directories appeared in the work tree and would have been committed | The runner commits what the task changed. Keeping junk out is the repository's `.gitignore`. `doctor` warns when a gate leaves untracked files behind |
| Codex reports tokens, never cost | Budgets in dollars bind only on agents that report cost. Add an optional token limit per call |
