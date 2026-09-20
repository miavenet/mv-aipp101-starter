# 06 — Scenarios

Each row is a behaviour the runner must have, and names the test that will prove it. This is the
same convention as the NYSE handler's design documents. All of these run with scripted agents: no
model, no cost. Live checks are in the [implementation plan](07-implementation-plan.md).

Rows marked **(A*n*)** were added or changed by the amendments that followed the
[design review](../../reviews/task-runner-review.md); each of its findings has at least one row here.

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
| WF-14 | a `check` or `human` task `verifies` A and also lists A in `needs` **(A8)** | loading fails: A's acceptance would wait for a verifier that waits for A's acceptance | `wf: verifier cannot need its target` |
| WF-15 | V `verifies` A, V `needs` B, and B `needs` A **(A8)** | loading fails and prints the trace A → B → V → A | `wf: indirect acceptance cycle` |
| WF-16 | a standalone `human` task only `needs` accepted A **(A8)** | it loads | `wf: standalone human is valid` |
| WF-17 | two tasks have overlapping `writes` and neither depends on the other; or a path under `.git` or `.runs` is declared **(A9, A10)** | loading fails and names both tasks and the paths | `wf: overlapping writers must be ordered` |

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
| SCH-08 | A and B are independent. A writes a helper. B's gate passes only if it can see that helper. A's panel rejects A **(A1)** | B never starts while A is active, B never sees the helper, and each commit holds only accepted work | `sch: producer transaction isolates candidates` |
| SCH-09 | the same, but A is waiting for a person's approval **(A1)** | the run stops with exit 255 and B does not start until A is approved or rejected | `sch: human verification holds the tree` |
| SCH-10 | a producer's transaction ends, by commit or by set-aside **(A1)** | a snapshot shows the tree equal to a clean accepted state before anything else starts | `sch: transaction ends clean` |

## Acceptance and rework (ACC)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| ACC-01 | the agent answers `done` and a gate fails | the task is not accepted | `acc: agent report is never acceptance` |
| ACC-02 | a declared output is missing, or empty without `may_be_empty`, or a `removes` path still exists **(A9)** | the attempt does not pass, and the feedback names the path | `acc: output contract` |
| ACC-03 | a gate fails | no reviewer is called, and the next attempt's prompt holds the output tail | `acc: gates before reviews` |
| ACC-04 | the same gate failure occurs twice running **and the candidate tree is identical** **(A12)** | the task fails as "no progress". With the same failure text after a real source change, it does not, and the attempt limit applies | `acc: no-progress needs an unchanged tree` |
| ACC-05 | two of three reviewers raise blocking findings | the third still runs, and the author gets one feedback holding all blocking findings | `acc: one consolidated rework` |
| ACC-06 | a rework is needed and the agent supports sessions | the session is continued and the prompt holds only the feedback | `acc: rework continues the session` |
| ACC-07 | the agent errors or times out | the next attempt uses a new session and the full prompt | `acc: broken session is abandoned` |
| ACC-08 | every attempt fails its gates | the task is `failed` after `max_attempts` | `acc: attempts bounded by gates` |
| ACC-09 | attempts run out with blocking findings open | the task is `blocked`, the findings are listed in STATUS.md, and the exit code is 255 | `acc: attempts bounded by review` |
| ACC-10 | the agent answers `blocked` | the task is `blocked` with its reason, exit 255 | `acc: blocked is a legal answer` |
| ACC-11 | a `check` that `verifies` a producer fails | the producer is reworked with the check's output | `acc: verifying check` |
| ACC-12 | a person rejects a `human` task that `verifies` a producer | the note becomes feedback and the producer is reworked | `acc: human rejection` |
| ACC-13 | the agent adds a helper file outside its `writes` **(A9)** | the file is removed, the attempt does not pass, and the feedback names it | `acc: undeclared writes are reverted` |
| ACC-14 | a gate rewrites a tracked source file and exits 0 **(A9)** | every earlier result for this candidate is void, the attempt does not pass, and the feedback names the command and the files | `acc: gates must not change the candidate` |
| ACC-15 | a verifying check leaves a modified source file behind **(A9)** | the same as ACC-14 | `acc: checks must not change the candidate` |
| ACC-16 | a task is accepted **(A9)** | the commit's tree, limited to the task's paths, equals the candidate tree every verifier judged, and `verification.json` shows one tree id throughout | `acc: commit exactly the verified candidate` |
| ACC-17 | a task's job is deleting a module, or creating an empty package marker **(A9)** | `removes`, and `may_be_empty`, let it pass | `acc: deletions and empty files` |

## Findings and convergence (FND)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| FND-01 | reviewers return findings, and two producers are reviewed by the same persona **(A7)** | each id is producer, persona code and number (`implement/PE-2`), stable across rounds and unique in the run | `fnd: ids are unique in the run` |
| FND-02 | a reviewer marked `advisory` returns a blocking finding | it is recorded as advisory and does not block | `fnd: advisory reviewers cannot block` |
| FND-03 | a reviewer answers in prose, or its `verdict` disagrees with the ledger after its answer is applied **(A6, A7)** | the answer is a protocol error: retried at most twice with a fresh invocation, using no producer attempt and creating no finding. If it never becomes valid, the review task fails and a person is needed | `fnd: invalid verdicts are protocol errors` |
| FND-04 | round 2 begins | a reviewer who blocked gets its open findings, the author's responses and the rework diff, and nothing else to judge | `fnd: later rounds judge the fix` |
| FND-05 | in a later round a reviewer raises a new blocking finding located outside the rework diff, with no `caused_by` | it is recorded as advisory | `fnd: no new blockers on untouched parts` |
| FND-06 | in round 2 a reviewer raises a new blocking finding inside the rework diff | it blocks | `fnd: regressions can block` |
| FND-07 | a reviewer who passed round 1, with `recheck_passed = "diff"` | it is shown only the rework diff in round 2; with `"never"` it is not run | `fnd: passed reviewers recheck the diff` |
| FND-08 | the author answers `disputed` and the reviewer marks it `unresolved` | the finding is `escalated` and the producer is `blocked` | `fnd: disputes go to a person` |
| FND-09 | a person runs `resolve FINDING --as advisory` and `retry` | the finding no longer blocks and the run continues | `fnd: a person settles a dispute` |
| FND-10 | a run has finished | `findings.json` holds every finding with its full history | `fnd: ledger is complete` |
| FND-11 | a reviewer changes the work tree | the producer fails, and the reason says so | `fnd: reviewers cannot edit` |
| FND-12 | attempt 1 fails its gates, so the panel first runs on attempt 2 **(A7)** | every member gets a full review with the full diff: it is their round 1 | `fnd: first sight is a full review` |
| FND-13 | in a later round a reviewer leaves an old finding `unresolved` and raises nothing new **(A7)** | it blocks, whatever its `verdict` field says | `fnd: verdict is derived from the ledger` |
| FND-14 | rework changes a shared function and breaks an unchanged caller; the reviewer's finding is located at the caller and names the changed function in `caused_by` **(A7)** | the runner confirms the named location is in the rework diff, and the finding blocks | `fnd: regressions outside the diff can block` |
| FND-15 | a `caused_by` names a location that is not in the rework diff **(A7)** | the finding is recorded as advisory | `fnd: caused_by is checked` |
| FND-16 | a reviewer resolves a finding that is not its own, resolves one twice, or omits one of its open findings **(A6)** | the answer is a protocol error | `fnd: resolutions must match the ledger` |

## Freezing and protection (FRZ)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| FRZ-01 | a task changes or creates a file matching `protected` | the file is restored or removed, the attempt does not pass, and the feedback names it | `frz: protected files` |
| FRZ-02 | a later task changes an accepted task's output without claiming it | the same as FRZ-01 (D8) | `frz: accepted outputs are frozen` |
| FRZ-03 | a later task claims that output in its own `outputs` | the change is allowed and appears in its reviewers' diff | `frz: explicit claim` |
| FRZ-04 | a gate command changes a protected file | it is caught after the gate as well as after the agent | `frz: checked after gates` |
| FRZ-05 | B claims A's frozen output, depends on A, and its change breaks A's gate **(A10)** | A's gates are re-run as part of B's verification, and B does not pass | `frz: claims re-run the gates they touch` |
| FRZ-06 | B changes an input of accepted task C, and C was verified only by review **(A10)** | C is marked stale against the new version, with the file and both hashes, in the record and in STATUS.md | `frz: stale acceptance is shown` |
| FRZ-07 | a reviewer or an agent modifies `state.json` or a closed attempt directory **(A9)** | the job fails, and the reason says the run record was changed | `frz: the record protects itself` |

## Failure and the DAG (FAIL)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| FAIL-01 | a producer fails | its changes are in `failed.patch`, and exactly the paths it changed are back at their base state | `fail: work is set aside` |
| FAIL-02 | a producer fails, having changed an executable script, a symbolic link, a file under a symlinked directory, a binary file, a file whose name holds spaces and a newline, and having turned a file into a directory **(A3)** | the tree afterwards equals the base snapshot exactly, the link's target is untouched, and nothing outside the repository changed | `fail: restore by type and mode` |
| FAIL-03 | a task fails | everything downstream is `skipped` with the reason, and independent branches run to the end | `fail: other branches continue` |
| FAIL-04 | `retry TASK --apply-patch` **(A3)** | the patch's base is checked against the current accepted tree; if it matches, the patch is applied and attempts restart from there; if not, the retry is refused with the reason. Without the flag attempts start clean | `fail: retry` |
| FAIL-05 | the run budget is reached | no new agent call starts, in-flight calls finish, the run stops as `stopped`, exit 2 | `fail: run budget` |
| FAIL-06 | an agent binary is missing, its sandbox cannot start, or authentication fails **(A5, A6)** | the run stops at once as an environment failure with the cause, and no producer attempt is used | `fail: environment failures use no attempts` |
| FAIL-07 | the set-aside patch is larger than the review diff cap, and holds a binary file **(A3)** | `failed.patch` is complete and applies cleanly to the base, and the candidate tree is reachable from a private ref after `git gc --prune=now` | `fail: recovery artifacts are complete and pinned` |

## Runs and the record (RUN)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| RUN-01 | `start` is run twice | two run directories exist with different UUIDs, and `latest` names the second | `run: start always creates` |
| RUN-02 | `start` is run with one staged and one unstaged owner change in a file the workflow will edit **(A4)** | it refuses, says why, and leaves the index and the work tree exactly as they were. There is no option to override | `run: no dirty starts` |
| RUN-03 | the process is killed at any point and `resume` is run | the run continues, and no finished attempt directory is changed | `run: resume from disk` |
| RUN-04 | the workflow file is edited and `resume` is run | the run's frozen copy is used (D12) | `run: frozen workflow` |
| RUN-05 | `replan` adds a task and edits a pending task | both changes apply, and `replans/001/` records before and after | `run: replan` |
| RUN-06 | `replan` would change an accepted task | it refuses without `--reopen`; with it, that task and its dependants return to `pending` and their freeze is lifted | `run: reopen` |
| RUN-07 | a second runner starts in the same repository | it refuses while the lock is held by a live process | `run: lock` |
| RUN-08 | every `STATUS.md` and `index.json` is deleted and `status --rebuild` is run | they are regenerated identically | `run: derived files are derived` |
| RUN-09 | any agent is called | its environment holds the run UUID and the task id | `run: environment` |
| RUN-10 | agent output contains a token-shaped string | it is redacted in the stored logs | `run: redaction` |
| RUN-11 | a finished run's directory is opened | every directory has an `index.json` describing every entry in it | `run: self-describing` |
| RUN-12 | while a run waits for a person, someone commits on its branch or edits the tree **(A4, A2)** | `resume` stops with a reconciliation error that states what was expected and what was found | `run: external changes while paused` |
| RUN-13 | a `prompt_file` is edited, or the workflow file is moved, between `start` and `resume` **(A10)** | the run uses the brief and the root it froze at start | `run: briefs and root are frozen` |
| RUN-14 | A is reopened after B, which needs A, committed an artifact the new A no longer calls for **(A10)** | `replan --reopen A` lists A and B as affected, undoes both commits with revert commits, newest first, and B's artifact is gone from the tree. The branch is never reset | `run: reopen reverts the affected closure` |
| RUN-15 | a revert during `--reopen` conflicts **(A10)** | the replan stops, changes nothing further, and says which commit conflicted | `run: reopen stops on conflict` |

## Git (GIT)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| GIT-01 | a snapshot is taken | the real index and work tree are unchanged | `git: snapshot has no side effects` |
| GIT-02 | a producer is accepted after two reworks | the run branch gains exactly one commit, holding only that task's files, with the run UUID and task id in the message | `git: one commit per accepted producer` |
| GIT-03 | a task creates a new file | it is in the reviewer's diff and in the commit | `git: untracked files are seen` |
| GIT-04 | a run finishes | nothing was pushed, merged, stashed, reset or cleaned | `git: no destructive or remote operations` |
| GIT-05 | `branch = "current"` | commits land on the checked-out branch | `git: current branch option` |
| GIT-06 | the root is not a git repository | the run works, with a warning: no commits, no freezing, no review diffs | `git: optional` |
| GIT-07 | a snapshot is taken and `git gc --prune=now` is run **(A2)** | the snapshot's tree is still present, held by a ref under `refs/task-runner/<run>/` | `git: snapshots are pinned` |
| GIT-08 | a path to restore is a symbolic link **(A3)** | the link is recreated as a link, and the file it pointed at is not written to | `git: links are never followed` |
| GIT-09 | a path to restore had its executable bit removed **(A3)** | the bit is back | `git: modes are restored` |
| GIT-10 | a path to restore lies under a directory that is now a symbolic link to somewhere outside the repository **(A3)** | the restore refuses that path and touches nothing outside | `git: parents are checked` |
| GIT-11 | a changed path is a submodule entry **(A3)** | the runner refuses, saying submodules are not supported | `git: unsupported entries are refused` |
| GIT-12 | an accepted commit is made **(A2)** | its message carries `Run:`, `Task:` and `Operation:` trailers | `git: commits carry the operation id` |

## Agents (AGENT)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| AGENT-01 | a Claude call, rework call and review call are built | print mode with JSON output, permissions, schema, budget, model; `--resume`; edit tools disallowed | `agent: claude command lines` |
| AGENT-02 | Claude's recorded success, budget-stop and non-JSON outputs are parsed | ok with session, cost and answer; not ok with the subtype; not ok with the raw text | `agent: claude results` |
| AGENT-03 | a Codex call, rework call and review call are built **(A5)** | `exec`; `exec resume ID` with the explicit id and never `--last`; `approval_policy="never"` and the sandbox as config overrides, read-only for review; no `--skip-git-repo-check`; prompt on stdin | `agent: codex command lines` |
| AGENT-04 | Codex's recorded event stream is parsed | thread id, last message, summed tokens, cost `None`; `turn.failed` is not ok | `agent: codex results` |
| AGENT-05 | an agent with no schema feature ends its answer with a JSON object | that object is the answer | `agent: JSON fallback` |
| AGENT-06 | a workflow defines a `command` agent | it runs with the prompt on stdin and needs no code | `agent: any command` |
| AGENT-07 | an agent runs past `timeout_min` | it is stopped within the grace period, the result is not ok, and its session is not reused | `agent: the runner owns the clock` |
| AGENT-08 | a Codex stream ends with exit 0 but has no `turn.completed` **(A6)** | the call is a protocol error, not a result | `agent: a terminal event is required` |
| AGENT-09 | the stream is empty and a final-message file from an earlier call exists **(A6)** | it cannot be read: the invocation directory is new and was created exclusively | `agent: no stale final message` |
| AGENT-10 | the answer is a scalar, has `approved: "true"` as a string, has an extra key, or lacks a required one **(A6)** | the runner's own validator rejects it, whichever agent and whichever schema feature produced it | `agent: local validation` |
| AGENT-11 | the recorded Codex author stream: first command fails with the `bwrap` namespace error, answer `blocked`, then `turn.completed` **(A5, A6)** | the adapter reports an environment failure, not a blocked task and not a success | `agent: sandbox startup is an environment failure` |
| AGENT-12 | an agent's session runs a test that fails, then fixes the code and finishes properly **(A6)** | the call is ok: a failed command inside a session is ordinary work | `agent: tool failures are not call failures` |
| AGENT-13 | an agent writes a megabyte to stderr and the runner is killed mid-call **(A11)** | the output up to that moment is in the invocation directory, and the runner's memory stayed bounded | `agent: logs are streamed` |
| AGENT-14 | a child ignores SIGINT, or the runner is told to stop while a gate runs **(A11)** | the whole process group is gone within the grace period, descendants included | `agent: process groups are stopped` |

## Preflight (PRE)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| PRE-01 | `doctor` runs **(A5)** | each agent profile is qualified per capability (`answer`, `read`, `execute`, `write`, `resume`, `boundary`) by evidence the runner checks itself, and the result is written to `qualification.json` | `pre: doctor qualifies capabilities` |
| PRE-02 | `check-gates` runs on an untouched tree **(A12)** | every gate is reported as pass, fail or error. A `new` gate that already passes is an objection; an invariant that passes is not | `pre: new gates must fail first, invariants need not` |
| PRE-03 | a `new` gate exits 126 or 127, times out, or exits 1 from a missing import so that its output does not match its `fail_pattern` **(A12)** | it is reported as `error`, apart from "fails as intended" | `pre: a wrong failure is an error` |
| PRE-04 | a gate leaves untracked files behind | `check-gates` lists them, since they would end up in a commit | `pre: gates that litter` |
| PRE-05 | a scripted agent returns a valid review object, but its file-read command failed **(A5)** | `doctor` does not grant `read`, and a workflow whose `code-review` tasks use that profile is refused before any producer runs | `pre: a greeting is not a capability` |
| PRE-06 | a profile has only `answer` and the workflow sets `review_mode = "provided_context"` **(A5)** | the review runs with a complete evidence bundle and is labelled text-only in the record; if the evidence exceeds the context budget it fails instead of running on part of it | `pre: text-only review is explicit` |
| PRE-07 | `doctor` ran before with the same binary version, profile hash, host and capabilities **(A5)** | the cached qualification is used and no model is called; `--force` repeats it | `pre: qualification is cached` |

## Crash recovery (REC) — all (A2)

Each test kills the runner at an injected point, then runs `resume`.

| ID | WHEN | THEN | Test |
|---|---|---|---|
| REC-01 | killed after a commit intent is recorded, before the commit | `resume` verifies the tree still equals the candidate, commits once, and records acceptance | `rec: intent without effect` |
| REC-02 | killed after the commit, before the state records it | `resume` finds the operation id on the branch tip and records acceptance. The author is not run again, and there is no second commit | `rec: effect without outcome` |
| REC-03 | killed with a commit intent, and the branch tip is neither the expected parent nor the expected commit | `resume` stops with a reconciliation error | `rec: unexpected branch tip` |
| REC-04 | killed after an agent was spawned; its process group is still alive | `resume` refuses to continue; `--stop-orphans` stops the group first. Two authors never run at once | `rec: no concurrent authors` |
| REC-05 | killed after an agent was spawned; the process is gone and there is no terminal event | the invocation is `interrupted`, never ok; its session is abandoned; the retry gets a new invocation directory | `rec: unknown completion is not success` |
| REC-06 | killed between writing the temporary state file and renaming it | the old state is intact and the leftover temporary file is ignored | `rec: durable state` |
| REC-07 | a task is retried after failing | new attempt directories continue the numbering; no finished directory is overwritten | `rec: attempt numbers are never reused` |
| REC-08 | the lock names a pid that now belongs to an unrelated process | the lock is recognised as stale by its recorded start time | `rec: process identity is not a pid` |

## Budget (BUD) — all (A11)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| BUD-01 | four reviewers are ready, each with a $5 cap, and $1 of the run budget is left | none starts, and the run stops as out of budget | `bud: reservation before dispatch` |
| BUD-02 | a call ends below its cap | the reservation is replaced by the actual cost and the rest is released | `bud: reservations are settled` |
| BUD-03 | a Codex call completes, and another is interrupted | `run.json` and STATUS.md show known spend, reserved spend and unpriced usage separately; the interrupted call counts as unknown, not as zero | `bud: honest accounting` |
| BUD-04 | a workflow uses an agent that reports no cost | `validate` says that the dollar limits do not bind on it and that time and attempts do | `bud: no promise that cannot be kept` |
