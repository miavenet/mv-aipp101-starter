# 07 — Implementation plan

Status: **plan only. The build has not started and waits for the owner's go-ahead.**

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
    workflow.py  record.py  prompts.py  agents.py  checks.py  gitops.py  findings.py  engine.py  cli.py
  tests/
    test_workflow.py  test_scheduler.py  test_lifecycle.py  test_findings.py
    test_record.py  test_gitops.py  test_agents.py  test_cli.py
    fake_agent.py            a scripted agent driven by a JSON file
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
| **0. Contract corrections** | Nothing. Amendments A1 to A12 to these documents | every P1 of the review has a scenario | **Done** with this revision |
| **1. Workflow** | `workflow.py`; `validate`, `graph` | WF-01 to WF-17 | The file format, panel expansion, "every producer needs a verifier", the acceptance-graph cycle check and the overlapping-writes check work on real workflows |
| **2. Recovery primitives** | `gitops.py` (pinned snapshots, restore by type and mode, full binary patches, commits with operation ids, reverts), `record.py` (durable state, intents and outcomes, the repository lock); `start`, `status`, `runs` | GIT-01 to GIT-12; REC-01 to REC-08; RUN-01, 02, 07, 08, 11 | File-type and crash-injection tests pass in scratch repositories |
| **3. One producer transaction** | `checks.py`, `prompts.py`, `validate.py`, `engine.py` for a single active producer, `fake_agent.py`, the `command` adapter; `resume`, `retry`, `approve`, `reject` | ACC-01 to ACC-17; FRZ-01 to FRZ-07; FAIL-01 to FAIL-07; SCH-08 to SCH-10 | Every accepted commit is exactly the verified candidate, and nothing else is ever in the tree when a transaction ends |
| **4. Headless adapters and qualification** | the Claude Code and Codex adapters on recorded fixtures; streamed logs; the completion protocol; local validation; `doctor` by capability; `check-gates` | AGENT-01 to AGENT-14; PRE-01 to PRE-07 | Recorded fixtures and failure probes pass with no model. `doctor` tells this container the truth about Codex |
| **5. Findings and panels** | `findings.py`; separate round counters; ledger-derived verdicts; protocol retries; budget reservation; parallel readers | FND-01 to FND-16; SCH-01 to SCH-07; BUD-01 to BUD-04 | The order in which panel members finish does not change any result |
| **6. Replan** | `replan`, `--reopen` with revert commits, frozen briefs, input manifests, staleness | RUN-04 to RUN-06, RUN-12 to RUN-15 | Reopened work cannot inherit stale acceptance |
| **7. Live check** | nothing new | see below | Real read, write, verification and rework are in the record, **on a host and profile that `doctor` has qualified** |
| **8. First real workflow** | `workflows/nyse-m1.toml` | | Usefulness |

Parallel readers come late on purpose: the transaction, the recovery rules and the findings rules
are where the accuracy lives, and they are easier to get right with one job at a time. The engine
loop is written from the start as "apply finished work, pick what can start, wait", so parallel
readers change the picking rule and nothing else.

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

Expected cost: a few dollars. **Codex takes part only in the roles `doctor` qualifies it for.** In
this container its sandbox cannot start, and the prototype's two Codex reviews contain no tool
events at all: they judged the diff they were sent and never read the repository. So here Codex is
at most a text-only reviewer, explicitly configured and labelled as such, until it runs on a host
where its sandbox starts.

### Stage 8: the NYSE M1 workflow

Each M1 step becomes tasks: a `design` task where the step still has open design, an `implement`
task with build and test gates, and panels chosen per step. Suggested panels:

| Step | Panel |
|---|---|
| Decoder, order book, arbiter | principal-engineer, spec-compliance |
| Build wiring, config, CLI | principal-engineer, devops (advisory) |
| Hex fixtures | spec-compliance, then a `human` sign-off, which the project rules already require |
| The workflow itself, before it runs | process-manager, technical-project-manager |

One change outside the runner is needed: an id-prefix filter for
`nyse-handler/tools/check_scenarios.py`, so a gate can demand "every BOOK- scenario has a test".
Workflow-wide `protected`: the spec notes, the scenario tables, reviewed fixtures, golden files, the
gate scripts. Run the first producer alone and read its whole record before letting the run continue.

## Risks

| Risk | Mitigation |
|---|---|
| Panels cost too much | Reviews run only after gates pass. Later rounds see only findings and the diff. Personas can use a smaller model. Cost per task is in every STATUS.md |
| Reviewers do not converge | D15's rules, the attempt limit, and escalation to a person. FND scenarios test each rule |
| Personas overlap and repeat each other | Every persona has an `out_of_scope` list. The live check looks for duplicate findings |
| Freezing blocks normal incremental work | A later task claims the paths in `outputs`; `validate` shows every claim. Revisit if workflows fill up with claims |
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

## Later

In the order the design expects to need them: the session scorecard as a stuck signal; storing a
candidate away during a human pause so other branches can continue; conditional tasks (`when`); parallel writers in git worktrees; a `plan` type that
proposes tasks for a live run behind a human approval; importing Attractor DOT.
