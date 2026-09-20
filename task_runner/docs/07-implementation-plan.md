# 07 — Implementation plan

Status: **the owner gave the go-ahead on 2026-09-19, after the adversarial review was answered
(amendments B1 to B12). Stage 1 is done: 51 tests pass, covering WF-01 to WF-24, and `validate` and `graph` work on the example. Stage 2 is done: 116 tests pass in all, covering GIT-01 to GIT-16, REC-01 to REC-13 and RUN-01, 02, 07, 08, 11, 16, 17, several at primitive level until the engine exists. `start` creates a run and stops in stage 2. Stage 3 is now done: 196 tests pass; `command` agents, producer transactions, gates/checks, human decisions, resume and retry work end to end. Stage 4 is now done: 227 runner tests pass; headless adapters, observed capability qualification, caching and gate preflight are implemented. Stage 5 is now done: findings, panels, bounded parallel readers, resolution and budget pauses are implemented. Stage 6 is now done: frozen replans and resumable reopening are implemented. The live check has exercised review/rework, implementation and record comprehension; its final human sign-off is pending.** Progress is recorded in the
[task_runner README](../README.md).

## Approach

Build in `task_runner/src/`, test-first against [the scenarios](06-scenarios.md), in the stages
below. Each stage ends with its scenarios green. Stages 1 to 5 use scripted agents and cost nothing
to test. The research [prototype](../../research/task_runner/prototype/README.md) stays unchanged, as
evidence. **None of its code is carried over as it stands.** The design review showed, and reading
the code confirms, that its reusable-looking parts are unsafe: `restore()` writes through symbolic
links and drops executable bits; `commit()` takes the owner's uncommitted edits in the same file;
`Codex.parse()` accepts a stream with no terminal event and reads a stale final-message file;
`run_process()` buffers all output in memory until exit. What carries over is what the live run
established about the tools: the command-line flags, the shape of the output, and the recorded
streams, which become test fixtures. The scratch-index snapshot idea is kept; its code is rewritten
with the tests in GIT and REC.

## Layout

```
task_runner/
  runner                     entry point (python3, no install step)
  src/taskrunner/
    patterns.py  workflow.py  record.py  prompts.py  validate.py  agents.py  checks.py  gitops.py
    findings.py  engine.py  cli.py
  tests/
    test_patterns.py  test_workflow.py  test_scheduler.py  test_lifecycle.py  test_findings.py
    test_record.py  test_gitops.py  test_agents.py  test_prompts.py  test_cli.py
    fake_agent.py            a scripted agent driven by a JSON file; its contract is below
    recorded/                real Claude Code and Codex output, from the prototype's live run
  library/types/  library/personas/
  examples/
  docs/
```

## Stages

The order follows the design review's advice: settle the contracts, build the recovery primitives
before anything relies on them, prove one producer transaction end to end, and qualify the
environment before spending effort on panels.

| Stage | Builds | Scenarios | Exit condition |
|---|---|---|---|
| **0. Contract corrections** | Nothing. Amendments A1 to A12, then B1 to B12, to these documents | every finding of both reviews has a scenario | **Done** |
| **1. Workflow** | `patterns.py`, `workflow.py`; `validate`, `graph`; the built-in `produce` and `review` type files | WF-01 to WF-24 | The file format, the path patterns, panel expansion, "every producer needs a verifier", the acceptance-graph cycle check and the overlapping-writes check work on real workflows, with no agent installed |
| **2. Recovery primitives** | `gitops.py` (pinned snapshots with a reused index, restore by type and mode, full binary patches, the commit recipe with index sync, reverts, prune), `record.py` (durable state, intents and outcomes for every effect, the integrity manifest, the repository lock, `.runs/README.md`); `start`, `status`, `runs`, `prune` | GIT-01 to GIT-16; REC-01 to REC-13; RUN-01, 02, 07, 08, 11, 16, 17 | File-type and crash-injection tests pass in scratch repositories |
| **3. One producer transaction** | `checks.py`, `prompts.py`, `validate.py`, `engine.py` for a single active producer verified by gates, checks and a person, `fake_agent.py`, the `command` adapter with streamed and redacted logs; `resume`, `retry`, `approve`, `reject` | ACC-01 to ACC-04, ACC-06 to ACC-08, ACC-10 to ACC-22; FRZ-01 to FRZ-10; FAIL-01 to FAIL-04, FAIL-06, FAIL-07; SCH-09 to SCH-11, SCH-13; RUN-03, RUN-09, RUN-10; PRM-01 to PRM-05 | Every accepted commit is exactly the verified candidate, and nothing else is ever in the tree when a transaction ends |
| **4. Headless adapters and qualification** | the Claude Code and Codex adapters on recorded fixtures; the completion protocol; `doctor` with out-of-band probes; the qualification cache; `check-gates` | AGENT-01 to AGENT-14; PRE-01 to PRE-08 | Recorded fixtures and failure probes pass with no model. `doctor` tells this container the truth about Codex |
| **5. Findings and panels** | `findings.py`; per-reviewer rounds and diff bases; ledger-derived verdicts; protocol retries; escalation and `resolve`; budget reservation and `--add-budget`; parallel readers | FND-01 to FND-20; ACC-05, ACC-09, ACC-23; SCH-01 to SCH-08, SCH-12; FAIL-05; BUD-01 to BUD-05 | The order in which panel members finish does not change any result |
| **6. Replan** | `replan`, `--reopen` with resumable revert commits, frozen briefs, input manifests, staleness | RUN-04 to RUN-06, RUN-12 to RUN-15 | Reopened work cannot inherit stale acceptance |
| **7. Live check** | nothing new | see below | Real read, write, verification and rework are in the record, **on a host and profile that `doctor` has qualified** |
| **8. First real workflow** | `workflows/nyse-m1.toml` | | Usefulness |
| **9. Tutorial and runbook** | [`docs/tutorial/`](tutorial/README.md) and [`docs/runbook.md`](runbook.md), finished against the real program. The design chapters are drafted early, from these documents; the runbook is completed last | see below | Every command in the runbook was run, and its output pasted from a real run. Every diagram matches the code. A reader who has seen nothing else can write a workflow, run it, and recover from each stop |

Parallel readers come late on purpose: the transaction, the recovery rules and the findings rules
are where the accuracy lives, and they are easier to get right with one job at a time. The engine
loop is written from the start as "apply finished work, pick what can start, wait", so parallel
readers change the picking rule and nothing else.

### Stage 3 completion (2026-09-20)

The suite covers the stage 3 scenario ranges above, including SCH-09 to SCH-11 and SCH-13.
Checks and agents both record process identities so recovery refuses live orphans; a resumed
standalone check restores its base before retrying. Verifier prerequisites are accepted before
opening the producer transaction. The full suite passes 196 tests with no model calls.

[The CLI walkthrough](stage-3-walkthrough.md) contains captured output from a scratch repository:
`start`, reject, `resume`, approve, `resume`, and a clean tree with exactly one accepted commit.
Review-specific portions of ACC-03, ACC-22, FRZ-06 and FRZ-09 remain for stage 5; stage 3 tests the
gate/prompt mechanisms and human-only stale acceptance without claiming panel execution.

### Stage 4 completion (2026-09-20)

The Claude Code and Codex adapters use recorded fixtures and installed CLI help. The suite covers
AGENT-01 to AGENT-14 and PRE-01 to PRE-08 without model calls, including terminal-event enforcement,
malformed answers, early sandbox failures, streamed logs, process-group shutdown, false capability
claims, caching/invalidation and destructive gate preflight in disposable copies. PRE-06 is tested
through the explicit text-only single-review helper; panel scheduling remains stage 5.

[The stage 4 walkthrough](stage-4-walkthrough.md) records doctor, a cached doctor, check-gates and
qualified producer execution. [Compatibility notes](stage-4-compatibility.md) identify the CLI
versions checked, what was observed on this host, and what still needs live qualification.

### Stage 5 completion (2026-09-20)

Findings transitions are pure and atomic; panel results are applied in workflow order. Tests
reverse reviewer completion order and assert identical ledgers and feedback while enforcing the
parallelism limit. Per-reviewer diff bases span gate failures, advisory findings close immediately,
and disputes hold the candidate until `resolve`. Budget reservations and completed reader outcomes
are recorded together; budget resume and crash recovery do not repeat completed reviews. Native
SIGTERM/SIGKILL tests cover parallel child cleanup and orphan refusal.

The [stage 5 walkthrough](stage-5-walkthrough.md) records model-free rework and escalation through
the CLI. Coverage is in `test_findings.py`, `test_panels.py`, `test_budgets.py` and
`test_panel_processes.py`, alongside the earlier transaction and recovery suites.

### Stage 6 completion (2026-09-20)

`replan` freezes revised definitions and records before/after copies. Changes to accepted tasks,
including their agent profile, template or brief, require `--reopen`; affected dependants and recorded
input consumers are reset too. Their commits are undone newest-first with new revert commits.
Recovery recognizes completed reverts and installs the staged definitions idempotently. Conflicts
and unrelated branch edits stop the operation. The full suite passes 283 tests at this stage.

The [stage 6 walkthrough](stage-6-walkthrough.md) records refusal without `--reopen`, successful
reopening, renewed human verification, and a clean result. A replan requires a clean tree and no
active producer transaction. Commit edits to workflow definitions first, or pass an external revised
file with `--workflow`; replan accepts definition-only commits made since the pause.

### The scripted agent's contract (stage 3 onward)

`tests/fake_agent.py` is a `command` agent. Every engine scenario depends on it, so its contract is
fixed here. It is started with the prompt on standard input and `FAKE_AGENT_SCRIPT` naming a JSON
file. The file holds a list of **steps**; the agent keeps a counter file beside it, performs the
step for this call, and moves the counter on. A call beyond the last step is a test error (exit 97).

```json
[
  {"match": "task.id or a regular expression the prompt must match; optional, a mismatch is a test error",
   "write":  {"src/book/side.hpp": "text", "tools/run.sh": {"text": "#!/bin/sh\n", "mode": "755"}},
   "symlink": {"link": "target"},
   "remove": ["old.txt"],
   "run":    ["git init nested"],
   "sleep_s": 0,
   "stdout_noise": "text printed before the answer",
   "answer": {"outcome": "done", "summary": "…", "blocked_reason": "", "responses": []},
   "raw_answer": "prose instead of JSON; gives a protocol error when used in place of answer",
   "exit": 0,
   "hang": false}
]
```

Every key is optional except that one of `answer`, `raw_answer`, a non-zero `exit` or `hang` must
be present. The agent records each prompt it received next to the script, so a test can assert what
the runner sent. It never decides anything: all behaviour comes from the script.

### Stage 7: the live check

A scratch repository and a four-task workflow: a `design` with a two-persona panel, an `implement`
with gates and a two-persona panel (one advisory), a `summarize`, a `human` sign-off. Run with a
small model. It passes when:

- the run ends `needs_human` at the sign-off, and `done` after `approve`;
- the run branch has one commit per accepted producer;
- at least one finding was raised, answered and resolved across two rounds (the design brief
  includes a deliberate gap to make sure of this);
- a second agent, given only the run directory's path and the question "what happened in this run,
  and what is open?", answers correctly from the record. This is the test of requirement R5.

The [live acceptance record](stage-7-walkthrough.md) documents the actual results and pending
human decision. Opus 5 was used at the owner's request. A Codex writer also passed qualification
with an explicitly configured `danger-full-access` profile. Controlled Codex sandbox execution
remains unavailable on this host; there is no automatic fallback to bypass it. Native Claude hooks
and explicitly labelled Codex exec-stream telemetry are described in
[headless observability](headless-observability.md).

### Stage 9: the tutorial and the runbook

Two documents for two readers. The **tutorial** teaches the model and the architecture to someone
who will write workflows or change the runner: it aims for accuracy and understanding first, and
uses diagrams freely. The **runbook** is for the person operating a run: what to type, what each
stop means, how to recover.

Rules that keep them accurate:

- Every chapter carries a status line: *design* (written from the design documents, not yet checked
  against code), or *verified at stage N* (checked against the program at that stage).
- A chapter moves to *verified* only when its commands were run and its diagrams compared with the
  code. After each stage, the chapters that stage touches are re-checked.
- The tutorial explains and links; the numbered design documents stay the reference. Where they
  disagree, the design document wins and the tutorial is corrected.
- Runbook output is pasted from real runs, never written by hand.

### Stage 8: the NYSE M1 workflow

Each M1 step becomes tasks: a `design` task where the step still has open design, an `implement`
task with build and test gates, and panels chosen per step. Suggested panels:

| Step | Panel |
|---|---|
| Decoder, order book, arbiter | principal-engineer, spec-compliance |
| Build wiring, config, CLI | principal-engineer, devops (advisory) |
| Hex fixtures | spec-compliance, then a `human` sign-off, which the project rules already require |
| The workflow itself, before it runs | process-manager, technical-project-manager |

One change outside the runner is needed: stronger scenario coverage validation in
`nyse-handler/tools/check_scenarios.py`: the design branch already has `--module` filtering, but
empty selections and incomplete message families must not count as coverage.
Workflow-wide `protected`: the spec notes, the scenario tables, reviewed fixtures, golden files, the
gate scripts. Run the first producer alone and read its whole record before letting the run continue.

## Risks

| Risk | Mitigation |
|---|---|
| Panels cost too much | Reviews run only after gates pass. Later rounds see only findings and the diff. Personas can use a smaller model. Cost per task is in every STATUS.md |
| Reviewers do not converge | D15's rules, the attempt limit, and escalation to a person. FND scenarios test each rule |
| Personas overlap and repeat each other | Every persona has an `out_of_scope` list. The live check looks for duplicate findings |
| Freezing blocks normal incremental work | A later task claims the paths in `writes`; `validate` shows every claim. Revisit if workflows fill up with claims |
| An author weakens the build it is judged by | Files a gate executes are protected by default; `new` gates with a `fail_pattern`; tests frozen by an earlier task; the build file is in the reviewers' diff (B9). Not fully closed, and said so in 03 |
| Prompt injection from repository or agent text | One-pass substitution, fenced data blocks, and verdicts that are computed from the ledger and the gates (B11). Reduced, not removed |
| Agent CLIs change | Adapters are small and isolated; tests use recorded output; `doctor` runs before every real workflow |
| A wrong gate | `check-gates` with invariant and `new` gates, the agent's `blocked` answer (seen working in the prototype), and `replan` |
| Codex cannot read or write the repository in this container | Known, and now detected by `doctor` before any work. Options, each an explicit choice in the workflow: a host where its sandbox starts; text-only review with a complete evidence bundle; or a disposable checkout behind an external isolation boundary. A container with the developer's workspace mounted writable is not such a boundary. There is never an automatic fallback to bypass flags |
| A crash at the wrong moment corrupts a run | Intents before effects, reconciliation on resume, pinned snapshots, crash-injection tests (REC) before the engine is built on them |
| A producer's tree leaks into another task | The producer transaction (A1), tested by SCH-08 and SCH-09 |
| The owner's default model makes small tasks costly | `model` in `[defaults]`, per type and per persona |

## Open questions for the owner

| # | Question | Default if unanswered |
|---|---|---|
| 1 | Where do workflows live? | `workflows/<name>.toml` at the top of the repository |
| 2 | Should the record of a finished run be committed? | No. `.runs/` ignores itself; `STATUS.md` and `findings.json` can be copied into a pull request |
| 3 | Which model for which persona? | The account default for principal-engineer and spec-compliance; a smaller model for the advisory ones |
| 4 | More starter personas (security, test engineer, performance)? | Add when a workflow needs one; each is a file |
| 5 | May a `human` task be satisfied by a named agent persona for low-risk steps? | No. `human` means a person |

## What autonomy still needs

The goal is to drive a project autonomously ([01](01-requirements.md)). Stages 1 to 8 give a runner
that carries a **given** workflow to completion and stops safely when it cannot. Measured against
the goal, four gaps remain, listed in the order proposed. None weakens
verification. **Accuracy and safety come first and autonomy second**, so these items wait until
stages 1 to 8 are done and the live check has shown the safety properties hold with real agents, and
each must pass the rule beside it before it is built.

| # | Gap | Why it matters for autonomy | Proposed remedy |
|---|---|---|---|
| 1 | **A person must write every workflow** | Driving a project means deciding the next tasks, not only doing listed ones | A `plan` task type: an agent proposes `[[task]]` entries from a milestone document and the record of earlier runs; the proposal is validated by the loader, reviewed by the process-manager and technical-project-manager personas, and enters the run through `replan`. A human approval is the default gate and can be removed per workflow once trusted |
| 2 | **One waiting task stops everything** | A pending sign-off, an escalation or a blocked task idles the whole run, often overnight | Store the waiting candidate away (pinned tree, restore, re-verify on return) so independent branches continue. Already listed under Later; it moves up |
| 3 | **Nobody is told when a person is needed** | An unattended run that stops silently loses hours | A `notify` command in `[defaults]`, run with the run id, status and the "Needs attention" text when a run stops with exit 2 or 255. The runner stays free of network code |
| 4 | **No loop across runs** | A project is many milestones; each run ends and someone must start the next | A thin outer command, `runner drive PROJECT.toml`: plan the next milestone, run it, summarise, repeat until the plan task answers "nothing left" or a budget or a person stops it. It is only a loop over `start`; all safety stays in the run |

### Finding the trade-off: measure, then tune

The optimum cannot be reasoned out in advance; it has to be measured on real runs and adjusted. The
record already contains the data, so this needs a report, not new machinery: `runner report` (after
stage 7) reads finished runs and prints, per task type, persona and workflow:

| Measure | What it tells | Read from |
|---|---|---|
| **Escaped defects**: accepted work later reopened, marked stale, or broken by a regression gate | Accuracy actually delivered. Too high: add verification | `replans/`, stale marks, `verification.json` |
| **Person overturns**: approvals rejected, disputes where the person sided against the panel | Whether the human gate is still catching things. Near zero over many runs: a candidate for removal on low-risk tasks | `decision.json`, `findings.json` |
| **Reviewer yield**: blocking findings per persona that led to a real change, against cost | Which reviewers earn their place. A persona that never changes an outcome is dropped or made advisory | `findings.json`, `run.json` |
| **Autonomy**: share of tasks accepted with no person, person-minutes per accepted task, hours a run sat waiting | What the stops cost | `events.jsonl` |
| **Invariant violations** | Must be zero. One violation outranks every other number and stops further relaxation | reconciliation errors, integrity failures |

Tuning is then a per-task choice the owner makes in the workflow, from cheapest to safest:
gates only; gates and an advisory reviewer; a blocking panel; a panel and a person. Tasks start at
the safe end and move down one step at a time, only when the measures for that kind of task support
it, and the move is recorded in the workflow's history.

Safety rules for those four items:

| Item | Rule it must meet |
|---|---|
| `plan` | Proposed tasks pass the same loader checks as hand-written ones, so every proposed producer has a verifier. A plan can never edit `protected`, remove a verifier, raise a budget or change an agent profile. The human approval is on by default |
| Continue past a waiting task | The stored candidate is re-verified in full against the then-current tree before it can be accepted; any accepted work that touched its inputs sends it back to rework instead |
| `notify` | Runs with the gates' reduced environment and receives text only. Its failure never changes the run |
| `drive` | Adds no authority: each run inside it has every stop a manual run has, and `drive` halts at the first exit 2 or 255 rather than starting another run |

## Later

In the order the design expects to need them, after the autonomy items above: the session scorecard as a stuck signal; conditional tasks (`when`); parallel writers in git worktrees; a `plan` type that
proposes tasks for a live run behind a human approval; importing Attractor DOT.
