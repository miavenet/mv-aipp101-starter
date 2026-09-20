# 07 — Implementation plan

Status: **plan only. The build has not started and waits for the owner's go-ahead.**

## Approach

Build in `task_runner/src/`, test-first against [the scenarios](06-scenarios.md), in the stages
below. Each stage ends with its scenarios green. Stages 1 to 5 use scripted agents and cost nothing
to test. The research [prototype](../../research/task_runner/prototype/README.md) is reference
material: its agent adapters, its process clock and its work-tree snapshot were proven against the
real tools and can be carried over; its engine cannot, because it has no DAG, no panels, no findings
and no run directories.

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

| Stage | Builds | Scenarios | Proves |
|---|---|---|---|
| **1. Workflow** | `workflow.py`; `validate`, `graph` | WF-01 to WF-13 | The file format, types, personas, panel expansion and the "every producer needs a verifier" rule, on real workflows, before any engine exists |
| **2. Record and git** | `record.py`, `gitops.py`; `start` (creates the run, runs nothing), `status`, `runs` | RUN-01, 02, 08, 11; GIT-01, 03 | The run directory and the snapshot primitive |
| **3. Serial engine** | `checks.py`, `prompts.py`, `engine.py` with one job at a time, `fake_agent.py`, the `command` adapter; `resume`, `retry`, `approve`, `reject` | ACC-01 to 12; FRZ-01 to 04; FAIL-01 to 06; RUN-03, 07, 09, 10; GIT-02, 04 to 06 | The whole producer lifecycle, acceptance, freezing, setting work aside |
| **4. Findings** | `findings.py`; the later-round rule; `resolve` | FND-01 to 11 | Panels converge, disputes reach a person |
| **5. Scheduler** | parallel readers, the reader–writer rule, ordered application of results | SCH-01 to 07 | Determinism under parallelism |
| **6. Real agents** | the Claude Code and Codex adapters, tested on recorded output; `doctor`, `check-gates` | AGENT-01 to 07; PRE-01 to 04 | Model agnosticism |
| **7. Replan** | `replan`, `--reopen` | RUN-04 to 06 | Long runs survive a wrong brief or gate |
| **8. Live check** | nothing new | see below | The design holds against real agents |
| **9. First real workflow** | `workflows/nyse-m1.toml` | | Usefulness |

Stage 5 comes after 3 and 4 on purpose: the lifecycle and the findings rules are where the accuracy
lives, and they are easier to get right with one job at a time. The engine loop is written from the
start as "apply finished work, pick what can start, wait", so parallel readers change the picking
rule and nothing else.

### Stage 8: the live check

A scratch repository and a four-task workflow: a `design` with a two-persona panel, an `implement`
with gates and a two-persona panel (one advisory), a `summarize`, a `human` sign-off. Run with a
small model. It passes when:

- the run ends `needs_human` at the sign-off, and `done` after `approve`;
- the run branch has one commit per accepted producer;
- at least one finding was raised, answered and resolved across two rounds (the design brief
  includes a deliberate gap to make sure of this);
- a second agent, given only the run directory's path and the question "what happened in this run,
  and what is open?", answers correctly from the record. This is the test of requirement R5.

Expected cost: a few dollars. Codex takes part as a reviewer here; as an author only where its
sandbox can start.

### Stage 9: the NYSE M1 workflow

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
| A wrong gate | `check-gates`, the agent's `blocked` answer (seen working in the prototype), and `replan` |
| Codex cannot author in this container | Known. Reviewer only, or the owner turns its sandbox off for a workflow, or it runs on a host with user namespaces |
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

In the order the design expects to need them: a token limit per call; the session scorecard as a
stuck signal; conditional tasks (`when`); parallel writers in git worktrees; a `plan` type that
proposes tasks for a live run behind a human approval; importing Attractor DOT.
