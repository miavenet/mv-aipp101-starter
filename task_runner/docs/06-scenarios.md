# 06 — Scenarios

Each row is a behaviour the runner must have, and names the test that will prove it. This is the
same convention as the NYSE handler's design documents. All of these run with scripted agents: no
model, no cost. Live checks are in the [implementation plan](07-implementation-plan.md).

## Workflow loading (WF)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| WF-01 | a workflow gives only `id`, `type`, `outputs` and a verifier per producer | it loads, and every other setting has its default | `wf: minimal workflow gets defaults` |
| WF-02 | any file has an unknown key | loading fails and names the file, the task and the key | `wf: unknown keys are errors` |
| WF-03 | a workflow has several problems | all are reported together | `wf: all errors at once` |
| WF-04 | `needs`, `reviews` or `verifies` names a missing task or the wrong kind | loading fails and says which | `wf: bad references` |
| WF-05 | tasks form a cycle | loading fails and prints the cycle | `wf: cycle` |
| WF-06 | a producer has no gate, check, review or human verifier | loading fails (D7) | `wf: every producer needs a verifier` |
| WF-07 | a producer's only verifiers are advisory reviewers | loading fails | `wf: advisory panel is not a verifier` |
| WF-08 | a producer has `reviewers = [...]` | one review task per entry exists, with the producer's `review_type`, targeting it | `wf: panel expansion` |
| WF-09 | a setting is given at task, persona, type and workflow level | the task's value wins, then persona, type, workflow, built-in | `wf: precedence` |
| WF-10 | a type's template uses an unknown placeholder, or a task omits a required parameter | loading fails | `wf: template checks` |
| WF-11 | a later task's `outputs` overlap an earlier task's | `validate` warns and names both tasks and the paths (D8) | `wf: overlapping claims are reported` |
| WF-12 | the same workflow is loaded twice | the expanded tasks and their order are identical | `wf: deterministic order` |
| WF-13 | `graph` is run | the output is valid DOT with one node per expanded task and an edge per `needs`, `reviews` and `verifies` | `wf: dot export` |

## Scheduling (SCH)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| SCH-01 | two producers are ready | they run one after the other, in workflow order | `sch: writers are serial` |
| SCH-02 | a panel of three is ready and `max_parallel` is 2 | two run together, then the third | `sch: readers in parallel up to the limit` |
| SCH-03 | readers are running and a writer becomes ready | the writer waits until they finish | `sch: no writer during readers` |
| SCH-04 | a writer is running and readers become ready | they wait | `sch: no readers during a writer` |
| SCH-05 | panel members finish in a different order on two runs | the state, the findings ids and the feedback text are identical | `sch: results applied in workflow order` |
| SCH-06 | a check is not marked `read_only` | it is scheduled as a writer | `sch: checks write by default` |
| SCH-07 | task B needs A, and A has produced but its panel has not passed | B does not start (D8) | `sch: needs means accepted` |

## Acceptance and rework (ACC)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| ACC-01 | the agent answers `done` and a gate fails | the task is not accepted | `acc: agent report is never acceptance` |
| ACC-02 | a declared output is missing or empty after an attempt | the attempt does not pass, and the feedback names the path | `acc: outputs must exist` |
| ACC-03 | a gate fails | no reviewer is called, and the next attempt's prompt holds the output tail | `acc: gates before reviews` |
| ACC-04 | the same gate failure occurs twice running, differing only in timings | the task fails as "no progress" | `acc: no-progress stop` |
| ACC-05 | two of three reviewers raise blocking findings | the third still runs, and the author gets one feedback holding all blocking findings | `acc: one consolidated rework` |
| ACC-06 | a rework is needed and the agent supports sessions | the session is continued and the prompt holds only the feedback | `acc: rework continues the session` |
| ACC-07 | the agent errors or times out | the next attempt uses a new session and the full prompt | `acc: broken session is abandoned` |
| ACC-08 | every attempt fails its gates | the task is `failed` after `max_attempts` | `acc: attempts bounded by gates` |
| ACC-09 | attempts run out with blocking findings open | the task is `blocked`, the findings are listed in STATUS.md, and the exit code is 255 | `acc: attempts bounded by review` |
| ACC-10 | the agent answers `blocked` | the task is `blocked` with its reason, exit 255 | `acc: blocked is a legal answer` |
| ACC-11 | a `check` that `verifies` a producer fails | the producer is reworked with the check's output | `acc: verifying check` |
| ACC-12 | a person rejects a `human` task that `verifies` a producer | the note becomes feedback and the producer is reworked | `acc: human rejection` |

## Findings and convergence (FND)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| FND-01 | reviewers return findings | each gets an id of persona code and number, stable across rounds | `fnd: ids` |
| FND-02 | a reviewer marked `advisory` returns a blocking finding | it is recorded as advisory and does not block | `fnd: advisory reviewers cannot block` |
| FND-03 | a reviewer answers in prose, or with `verdict: "pass"` plus a blocking finding, or `block` with none | the answer is rejected as unusable; twice running fails the producer | `fnd: verdicts must be well formed` |
| FND-04 | round 2 begins | a reviewer who blocked gets its open findings, the author's responses and the rework diff, and nothing else to judge | `fnd: later rounds judge the fix` |
| FND-05 | in round 2 a reviewer raises a new blocking finding located outside the rework diff | it is downgraded to advisory | `fnd: no new blockers on untouched parts` |
| FND-06 | in round 2 a reviewer raises a new blocking finding inside the rework diff | it blocks | `fnd: regressions can block` |
| FND-07 | a reviewer who passed round 1, with `recheck_passed = "diff"` | it is shown only the rework diff in round 2; with `"never"` it is not run | `fnd: passed reviewers recheck the diff` |
| FND-08 | the author answers `disputed` and the reviewer marks it `unresolved` | the finding is `escalated` and the producer is `blocked` | `fnd: disputes go to a person` |
| FND-09 | a person runs `resolve FINDING --as advisory` and `retry` | the finding no longer blocks and the run continues | `fnd: a person settles a dispute` |
| FND-10 | a run has finished | `findings.json` holds every finding with its full history | `fnd: ledger is complete` |
| FND-11 | a reviewer changes the work tree | the producer fails, and the reason says so | `fnd: reviewers cannot edit` |

## Freezing and protection (FRZ)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| FRZ-01 | a task changes or creates a file matching `protected` | the file is restored or removed, the attempt does not pass, and the feedback names it | `frz: protected files` |
| FRZ-02 | a later task changes an accepted task's output without claiming it | the same as FRZ-01 (D8) | `frz: accepted outputs are frozen` |
| FRZ-03 | a later task claims that output in its own `outputs` | the change is allowed and appears in its reviewers' diff | `frz: explicit claim` |
| FRZ-04 | a gate command changes a protected file | it is caught after the gate as well as after the agent | `frz: checked after gates` |

## Failure and the DAG (FAIL)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| FAIL-01 | a producer fails | its changes are in `failed.patch`, and exactly the paths it changed are back at their base state | `fail: work is set aside` |
| FAIL-02 | a producer fails and the owner had unrelated untracked files (`allow_dirty`) | those files are untouched | `fail: only the task's paths are restored` |
| FAIL-03 | a task fails | everything downstream is `skipped` with the reason, and independent branches run to the end | `fail: other branches continue` |
| FAIL-04 | `retry TASK --apply-patch` | the patch is applied and attempts restart from there; without the flag they start clean | `fail: retry` |
| FAIL-05 | the run budget is reached | no new agent call starts, in-flight calls finish, the run stops as `stopped`, exit 2 | `fail: run budget` |
| FAIL-06 | an agent binary is missing or its sandbox cannot start | the task fails with a clear reason and the run does not crash | `fail: agent cannot start` |

## Runs and the record (RUN)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| RUN-01 | `start` is run twice | two run directories exist with different UUIDs, and `latest` names the second | `run: start always creates` |
| RUN-02 | `start` is run on a dirty work tree | it refuses and says why | `run: clean start` |
| RUN-03 | the process is killed at any point and `resume` is run | the run continues, and no finished attempt directory is changed | `run: resume from disk` |
| RUN-04 | the workflow file is edited and `resume` is run | the run's frozen copy is used (D12) | `run: frozen workflow` |
| RUN-05 | `replan` adds a task and edits a pending task | both changes apply, and `replans/001/` records before and after | `run: replan` |
| RUN-06 | `replan` would change an accepted task | it refuses without `--reopen`; with it, that task and its dependants return to `pending` and their freeze is lifted | `run: reopen` |
| RUN-07 | a second runner starts in the same repository | it refuses while the lock is held by a live process | `run: lock` |
| RUN-08 | every `STATUS.md` and `index.json` is deleted and `status --rebuild` is run | they are regenerated identically | `run: derived files are derived` |
| RUN-09 | any agent is called | its environment holds the run UUID and the task id | `run: environment` |
| RUN-10 | agent output contains a token-shaped string | it is redacted in the stored logs | `run: redaction` |
| RUN-11 | a finished run's directory is opened | every directory has an `index.json` describing every entry in it | `run: self-describing` |

## Git (GIT)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| GIT-01 | a snapshot is taken | the real index and work tree are unchanged | `git: snapshot has no side effects` |
| GIT-02 | a producer is accepted after two reworks | the run branch gains exactly one commit, holding only that task's files, with the run UUID and task id in the message | `git: one commit per accepted producer` |
| GIT-03 | a task creates a new file | it is in the reviewer's diff and in the commit | `git: untracked files are seen` |
| GIT-04 | a run finishes | nothing was pushed, merged, stashed, reset or cleaned | `git: no destructive or remote operations` |
| GIT-05 | `branch = "current"` | commits land on the checked-out branch | `git: current branch option` |
| GIT-06 | the root is not a git repository | the run works, with a warning: no commits, no freezing, no review diffs | `git: optional` |

## Agents (AGENT)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| AGENT-01 | a Claude call, rework call and review call are built | print mode with JSON output, permissions, schema, budget, model; `--resume`; edit tools disallowed | `agent: claude command lines` |
| AGENT-02 | Claude's recorded success, budget-stop and non-JSON outputs are parsed | ok with session, cost and answer; not ok with the subtype; not ok with the raw text | `agent: claude results` |
| AGENT-03 | a Codex call, rework call and review call are built | `exec`; `exec resume ID`; sandbox as a config override, read-only for review; prompt on stdin | `agent: codex command lines` |
| AGENT-04 | Codex's recorded event stream is parsed | thread id, last message, summed tokens, cost `None`; `turn.failed` is not ok | `agent: codex results` |
| AGENT-05 | an agent with no schema feature ends its answer with a JSON object | that object is the answer | `agent: JSON fallback` |
| AGENT-06 | a workflow defines a `command` agent | it runs with the prompt on stdin and needs no code | `agent: any command` |
| AGENT-07 | an agent runs past `timeout_min` | it is stopped within the grace period, the result is not ok, and its session is not reused | `agent: the runner owns the clock` |

## Preflight (PRE)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| PRE-01 | `doctor` runs | each agent the workflow uses answers a one-line prompt, or the failure and its cause are shown | `pre: doctor` |
| PRE-02 | `check-gates` runs on an untouched tree | a gate that already passes is reported, since it cannot show the task was done | `pre: gates must fail first` |
| PRE-03 | a gate cannot run at all (exit 126 or 127) | it is reported as broken, apart from "fails as expected" | `pre: broken gates` |
| PRE-04 | a gate leaves untracked files behind | `check-gates` lists them, since they would end up in a commit | `pre: gates that litter` |
