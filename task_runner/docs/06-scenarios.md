# 06 — Scenarios

Each row is a behaviour the runner must have, and names the test that will prove it. This is the
same convention as the NYSE handler's design documents. All of these run with scripted agents: no
model, no cost. Live checks are in the [implementation plan](07-implementation-plan.md).

Rows marked **(A*n*)** were added or changed by the amendments that followed the
[design review](../../reviews/task-runner-review.md); each of its findings has at least one row here.
Rows marked **(B*n*)** were added or changed after the
[adversarial review](../../reviews/task-runner-adversarial-review.md).
Rows marked **(G*n*)** were added by the *n*-th resilience-gap design in
[`docs/design/runner-gaps/`](design/runner-gaps/), following the field review of two real
workflow runs.

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
| WF-09 | a setting is given at task, persona, type and workflow level | the task's value wins, then persona, type, workflow, built-in. `protected` is the exception: it is the union of all levels **(B9)** | `wf: precedence` |
| WF-10 | a type's template uses an unknown placeholder, or a task omits a required parameter | loading fails | `wf: template checks` |
| WF-11 | a later, dependent task's `writes` cover an earlier task's `outputs` **(B4)** | `validate` warns and names both tasks and the paths (D8). Listing the path in `outputs` alone is not a claim | `wf: overlapping claims are reported` |
| WF-12 | the same workflow is loaded twice | the expanded tasks and their order are identical | `wf: deterministic order` |
| WF-13 | `graph` is run | the output is valid DOT with one node per expanded task and an edge per `needs`, `reviews` and `verifies` | `wf: dot export` |
| WF-14 | a `check` or `human` task `verifies` A and also lists A in `needs` **(A8)** | loading fails: A's acceptance would wait for a verifier that waits for A's acceptance | `wf: verifier cannot need its target` |
| WF-15 | V `verifies` A, V `needs` B, and B `needs` A **(A8)** | loading fails and prints the trace A → B → V → A | `wf: indirect acceptance cycle` |
| WF-16 | a standalone `human` task only `needs` accepted A **(A8)** | it loads | `wf: standalone human is valid` |
| WF-17 | two tasks have overlapping `writes` and neither depends on the other; or a path under `.git` or `.runs` is declared **(A9, A10)** | loading fails and names both tasks and the paths | `wf: overlapping writers must be ordered` |
| WF-18 | a task has `type = "produce"`; another has `reviewers` but its type names no `review_type`; another has `prompt` and `prompt_file` **(B4)** | the first loads through the built-in `produce` type file, with its template and `requires`; the other two are load errors | `wf: bare kinds and their limits` |
| WF-19 | the pattern table of 03 is applied: `docs/spec/**` to `docs/spec/a/b.md`; `docs/spec/*` to the same; `src/**/x.h` to `src/x.h`; `*.lock` to `sub/x.lock`; `src/book/**` to `src/book` **(B4)** | match, no match, match, match, no match. An absolute pattern, `..`, or `a**b` is a load error | `wf: path patterns have one meaning` |
| WF-20 | an output is not covered by `writes` under the conservative rule; two unordered tasks write `src/**/x.h` and `src/book/**` **(B4)** | both are load errors. The second may be a false alarm and is still refused | `wf: cover and overlap are conservative` |
| WF-21 | a declared path is ignored by git; a path is in both `outputs` and `removes` **(B3, B4)** | both are load errors, and the first names the ignore rule | `wf: unsatisfiable paths` |
| WF-22 | two personas share a `code`; one producer lists a perspective twice; a task omits a parameter marked `required` **(B4)** | each is a load error | `wf: library consistency` |
| WF-23 | the workflow file is in `workflows/`, with `root = ".."`, `library = ["lib"]` and `prompt_file = "briefs/x.md"` **(B4)** | `library` and `prompt_file` resolve under `workflows/`, task paths resolve under the root, and `run.json` records the absolute paths | `wf: relative paths` |
| WF-24 | `validate` is run on a machine with no agent installed and no qualification cache **(B5)** | it succeeds: capabilities are checked by `doctor` and `start`, not by `validate` | `wf: validate needs no agent` |

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
| SCH-11 | a standalone check that is not `read_only` modifies a tracked file **(B7)** | the check fails, the tree is back at its BASE before anything else starts, and the next producer is not blamed | `sch: writing checks are rolled back` |
| SCH-12 | a check marked `read_only` writes a file while reviewers run beside it **(B7)** | the check fails as "declared read_only but wrote", those reviews are void and run again, no producer attempt is used, and the check is a writer from then on | `sch: read_only is verified` |
| SCH-13 | a producer is `waiting_human`, and `retry` is run on another failed task **(B7)** | `retry` refuses and names the task the run is waiting on | `sch: retry respects the open transaction` |

## Acceptance and rework (ACC)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| ACC-01 | the agent answers `done` and a gate fails | the task is not accepted | `acc: agent report is never acceptance` |
| ACC-02 | a declared output is missing, or empty without `may_be_empty`, or a `removes` path still exists **(A9)** | the attempt does not pass, and the feedback names the path | `acc: output contract` |
| ACC-03 | a gate fails | no reviewer is called, and the next attempt's prompt holds the output tail | `acc: gates before reviews` |
| ACC-04 | the same gate failure occurs twice running **and the candidate tree is identical** **(A12)** | the task fails as "no progress". With the same failure text after a real source change, it does not, and the attempt limit applies | `acc: no-progress needs an unchanged tree` |
| ACC-05 | two of three reviewers raise blocking findings | the third still runs, and the author gets one feedback holding all blocking findings | `acc: one consolidated rework` |
| ACC-06 | a rework is needed and the profile is qualified for `resume` | the session is continued and the prompt holds only the feedback | `acc: rework continues the session` |
| ACC-07 | the agent errors or times out | the next attempt uses a new session and the full prompt | `acc: broken session is abandoned` |
| ACC-08 | every attempt fails its gates | the task is `failed` after `max_attempts` | `acc: attempts bounded by gates` |
| ACC-09 | attempts run out with blocking findings open | the task is `blocked`, the findings are listed in STATUS.md, and the exit code is 255 | `acc: attempts bounded by review` |
| ACC-10 | the agent answers `blocked` | the task is `blocked` with its reason, exit 255 | `acc: blocked is a legal answer` |
| ACC-11 | a `check` that `verifies` a producer fails | the producer is reworked with the check's output | `acc: verifying check` |
| ACC-12 | a person rejects a `human` task that `verifies` a producer | the note becomes feedback and the producer is reworked | `acc: human rejection` |
| ACC-13 | the agent adds a helper file outside its `writes` **(A9)** | the file is removed, the attempt does not pass, and the feedback names it | `acc: undeclared writes are reverted` |
| ACC-14 | a gate rewrites a tracked source file, or leaves a new file git does not ignore, and exits 0 **(A9, B3)** | the runner puts the tree back to the candidate, every earlier result for this candidate is void, the attempt does not pass, and the feedback names the command and the files | `acc: gates must not change the candidate` |
| ACC-15 | a verifying check leaves a modified source file behind **(A9)** | the same as ACC-14 | `acc: checks must not change the candidate` |
| ACC-16 | a task is accepted **(A9)** | the commit's tree, limited to the task's paths, equals the candidate tree every verifier judged, and `verification.json` shows one tree id throughout | `acc: commit exactly the verified candidate` |
| ACC-17 | a task's job is deleting a module, or creating an empty package marker **(A9)** | `removes`, and `may_be_empty`, let it pass | `acc: deletions and empty files` |
| ACC-18 | the agent adds its output directory to `.gitignore` and writes its output there; or `.gitignore` is not in its `writes` at all **(B3)** | the `.gitignore` edit is reverted as a protected file. If the task does own `.gitignore`, the now-ignored declared path is detected after the attempt. Either way the attempt does not pass | `acc: work must be visible to git` |
| ACC-19 | a standalone check fails; a standalone `human` task is rejected **(B7)** | `failed`, exit 2; `blocked` with the note in `decision.json`, exit 255. Dependants are `skipped` | `acc: standalone verifiers` |
| ACC-20 | a check marked `restores = true` mutates a source file and is killed by its timeout **(B7)** | the runner restores the candidate itself, the snapshot equals the candidate, and the check is reported as failed by timeout, not as having changed the candidate | `acc: destructive verifiers are restored` |
| ACC-21 | a rework is needed and the profile is not qualified for `resume` (a `command` agent) **(B1)** | a new session gets the full prompt plus the feedback, and `responses` are required exactly as in a continued session | `acc: rework without resume` |
| ACC-22 | round 1 leaves two blocking findings; the rework answers both but fails a gate **(B1)** | the next prompt holds the gate output, lists the two findings as already answered, and requires no second response to them | `acc: what a rework prompt holds` |
| ACC-23 | a producer is blocked by its panel **(B7)** | every one of its verifiers has a final status (`accepted`, `objected` or `skipped`) and a row in STATUS.md | `acc: every task has a status` |

## Findings and convergence (FND)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| FND-01 | reviewers return findings, and two producers are reviewed by the same persona **(A7)** | each id is producer, persona code and number (`implement/PE-2`), stable across rounds and unique in the run | `fnd: ids are unique in the run` |
| FND-02 | a reviewer marked `advisory` returns a blocking finding | it is recorded as advisory and does not block | `fnd: advisory reviewers cannot block` |
| FND-03 | a reviewer answers in prose, or its `verdict` disagrees with the ledger after its answer is applied **(A6, A7, B7)** | the answer is a protocol error: retried at most twice with a fresh invocation directory inside the round, using no producer attempt and creating no finding. If it never becomes valid, the producer is `blocked` (a person must repair the panel), exit 255 | `fnd: invalid verdicts are protocol errors` |
| FND-04 | round 2 begins | a reviewer who blocked gets its open findings, the author's responses and the rework diff, and nothing else to judge | `fnd: later rounds judge the fix` |
| FND-05 | in a later round a reviewer raises a new blocking finding located outside the rework diff, with no `caused_by` | it is recorded as advisory | `fnd: no new blockers on untouched parts` |
| FND-06 | in round 2 a reviewer raises a new blocking finding inside the rework diff | it blocks | `fnd: regressions can block` |
| FND-07 | a reviewer who passed round 1, with `recheck_passed = "diff"` | it is shown only the rework diff in round 2; with `"never"` it is not run | `fnd: passed reviewers recheck the diff` |
| FND-08 | the author answers `disputed` and the reviewer marks it `unresolved` **(B10)** | the finding is `escalated`, the producer is `waiting_human` with the tree held, and the run stops with exit 255 | `fnd: disputes go to a person` |
| FND-09 | a finding is escalated; a person runs `resolve FINDING --as advisory` and `resume` **(B10)** | while waiting, the producer is `waiting_human` and its candidate is still in the tree. Afterwards the runner checks the tree equals the candidate and accepts it. The author is not run, no verifier is repeated, and no attempt is used | `fnd: a person settles a dispute` |
| FND-10 | a run has finished | `findings.json` holds every finding with its full history | `fnd: ledger is complete` |
| FND-11 | a reviewer changes the work tree | the producer fails, and the reason says so | `fnd: reviewers cannot edit` |
| FND-12 | attempt 1 fails its gates, so the panel first runs on attempt 2 **(A7)** | every member gets a full review with the full diff: it is their round 1 | `fnd: first sight is a full review` |
| FND-13 | in a later round a reviewer leaves an old finding `unresolved` and raises nothing new **(A7)** | it blocks, whatever its `verdict` field says | `fnd: verdict is derived from the ledger` |
| FND-14 | rework changes a shared function and breaks an unchanged caller; the reviewer's finding is located at the caller and names the changed function in `caused_by` **(A7)** | the runner confirms the named location is in the rework diff, and the finding blocks | `fnd: regressions outside the diff can block` |
| FND-15 | a `caused_by` names a location that is not in the rework diff **(A7)** | the finding is recorded as advisory | `fnd: caused_by is checked` |
| FND-16 | a reviewer resolves a finding that is not its own, resolves one twice, or omits one of its open **blocking** findings **(A6, B1)** | the answer is a protocol error | `fnd: resolutions must match the ledger` |
| FND-17 | a reviewer raised only an advisory finding in round 1 and passed; round 2 shows it the rework diff **(B1)** | the advisory finding is already `noted`; an empty `resolutions` list is valid; the round is not a protocol error | `fnd: advisory findings never stay open` |
| FND-18 | PE blocks on candidate C2; attempt 3 fails its gates so no panel runs; attempt 4 gives C4 **(B1)** | PE's rework diff is C2 to C4, so a regression made in attempt 3 is inside it and can block | `fnd: the rework diff is per reviewer` |
| FND-19 | a task is retried after being blocked with findings open **(B1)** | every reviewer's next round is a full round 1, and the old open findings are `superseded` | `fnd: retry starts a new line of work` |
| FND-20 | a person runs `resolve FINDING --as upheld` **(B10)** | the finding stays open and blocking, the author cannot dispute it again, and a rework follows if attempts remain | `fnd: a person can side with the reviewer` |
| FND-21 | a round-1 reviewer raises one blocking finding and also lists it, by title, under `resolutions`, with `verdict = "block"` **(G2)** | the entry is dropped, the answer is applied, the finding is in the ledger and blocks, the author's next prompt lists it, and the reviewer was called exactly once | `fnd: a meaningless resolution is dropped, the finding is kept` |
| FND-22 | the same answer, but a `resolutions` entry names a real ledger id belonging to another reviewer **(G2)** | it is a protocol error with today's diagnostic, and the ledger is byte-identical to before the call | `fnd: a real id is never repaired away` |
| FND-23 | a later-round reviewer with one open blocking finding of its own supplies a junk `resolutions` entry instead of resolving it **(G2)** | it is a protocol error naming the required id; nothing is dropped and nothing is resolved | `fnd: no repair while a resolution is required` |
| FND-24 | a reviewer supplies junk `resolutions`, raises no blocking finding, and says `verdict = "pass"`; the same for a reviewer marked `advisory` **(G2)** | both are protocol errors: a repair may only deliver a block. The rejected answers are summarised for the owner | `fnd: a repair never produces a pass` |
| FND-25 | an answer is repaired **(G2)** | each finding it raised carries a `repair` history event naming what was dropped, `events.jsonl` holds one `review-repair` event, `verdict.json` holds the repair record with the original answer, and the producer's STATUS.md says the answer was repaired | `fnd: a repair is recorded where it can be audited` |
| FND-26 | every reviewer answers validly, with correct `resolutions` **(G2)** | no repair is recorded anywhere, the verdicts, the rework prompt, the attempt count and the commit are identical to a run before this change | `fnd: valid answers are untouched` |
| FND-27 | a two-member panel on one candidate: PE raises a blocking finding, and SC, running beside it, blocks and supplies PE's new id under `resolutions`. SC is eligible for the repair at collection and not at final application **(G2)** | SC's answer is refused at final application, SC is re-called with the **actual** diagnostic inside its existing tries, no exception escapes the engine, PE's finding appears exactly once in the ledger, and `resume` after a kill at `panel:applied` reaches the same ledger | `fnd: repair eligibility is decided by the ledger that applies it` |
| FND-28 | SC sends that same colliding answer all three times, so every rejection happens at final application and none at collection **(G2)** | the producer is blocked with **three** rejected-answer summaries, each with its verdict, its finding titles and its own `invocation-N/` pointer; all three invocations record the protocol error rather than `ok`; the final result carries the real diagnostic, not "interrupted calls exhausted protocol retries"; and the ledger is byte-identical to before the panel | `fnd: an answer refused at final application is still a rejected answer` |
| FND-29 | the runner is killed after the coordinator refused an answer and before the state write, then `resume` **(G2)** | exactly one summary exists for that invocation, the accepted members' findings are applied once, the ids are not consumed twice, and the run reaches the same ledger and the same task status as an uninterrupted run | `fnd: a coordinator rejection survives replay exactly once` |

## Freezing and protection (FRZ)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| FRZ-01 | a task changes or creates a file matching `protected` | the file is restored or removed, the attempt does not pass, and the feedback names it | `frz: protected files` |
| FRZ-02 | a later task changes an accepted task's output without claiming it | the same as FRZ-01 (D8) | `frz: accepted outputs are frozen` |
| FRZ-03 | a later task claims that output in its own `writes` **(B4)** | the change is allowed and appears in its reviewers' diff. Naming it in `outputs` alone does not allow it | `frz: explicit claim` |
| FRZ-04 | a gate command changes a protected file | it is caught after the gate as well as after the agent | `frz: checked after gates` |
| FRZ-05 | B claims A's frozen output, depends on A, and its change breaks A's gate **(A10)** | A's gates are re-run as part of B's verification, and B does not pass | `frz: claims re-run the gates they touch` |
| FRZ-06 | B changes an input of accepted task C, and C was verified only by review **(A10)** | C is marked stale against the new version, with the file and both hashes, in the record and in STATUS.md | `frz: stale acceptance is shown` |
| FRZ-07 | a reviewer or an agent modifies `state.json`, a `findings.json`, or a decision-bearing file in a finished directory **(A9, B8)** | the job fails, and the reason says which file of the run record was changed | `frz: the record protects itself` |
| FRZ-08 | a task sets `protected = []`, or a narrower list than the workflow's **(B9)** | the workflow's protected paths still apply to it | `frz: protection cannot be narrowed` |
| FRZ-09 | an `implement` task, a reviewer and a gate are run; then a `summarize` task **(B8)** | only the `summarize` call has `TASK_RUNNER_RUN_DIR` in its environment | `frz: the record is exported only where needed` |
| FRZ-10 | a gate runs `python3 tools/check.py`, and the author edits `tools/check.py` without listing it in `writes` **(B9)** | the edit is reverted as a protected file and the attempt does not pass | `frz: files a gate executes are protected` |

## Failure and the DAG (FAIL)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| FAIL-01 | a producer fails | its changes are in `failed.patch`, and exactly the paths it changed are back at their base state | `fail: work is set aside` |
| FAIL-02 | a producer fails, having changed an executable script, a symbolic link, a file under a symlinked directory, a binary file, a file whose name holds spaces and a newline, and having turned a file into a directory **(A3)** | the tree afterwards equals the base snapshot exactly, the link's target is untouched, and nothing outside the repository changed | `fail: restore by type and mode` |
| FAIL-03 | a task fails | everything downstream is `skipped` with the reason, and independent branches run to the end | `fail: other branches continue` |
| FAIL-04 | `retry TASK --apply-patch` **(A3, G1)** | the patch's base is checked only at the paths the set-aside work touched, not the whole tree; refused if any of them differ, if the branch is no longer a descendant of where the work was set aside, if a runner-made commit landed since, if the pinned candidate tree is gone, or if a touched path is no longer inside the task's current `writes`. If every check passes, the work is restored from the candidate tree and attempts restart from there. Without the flag attempts start clean | `fail: retry` |
| FAIL-05 | the run budget is reached while a producer is active **(B10)** | no new agent call starts, in-flight calls finish, the run stops as `stopped`, exit 2. The transaction stays open and the expected tree is recorded | `fail: run budget` |
| FAIL-06 | an agent binary is missing, its sandbox cannot start, or authentication fails **(A5, A6)** | the run stops at once as an environment failure with the cause, and no producer attempt is used | `fail: environment failures use no attempts` |
| FAIL-07 | the set-aside patch is larger than the review diff cap, and holds a binary file **(A3)** | `failed.patch` is complete and applies cleanly to the base, and the candidate tree is reachable from a private ref after `git gc --prune=now` | `fail: recovery artifacts are complete and pinned` |
| FAIL-08 | a producer is blocked, the owner commits an edited brief on the run branch, runs `replan` (which resets the task to `pending`) and then `retry TASK --apply-patch` **(G1)** | the retry is accepted, the set-aside work of the last attempt is put back at the start of the next transaction, that attempt's number continues the series, and no finished attempt directory changed | `fail: set-aside work survives a replan` |
| FAIL-09 | a commit since the set-aside touches only files outside the paths the set-aside work changed, and the owner runs `retry TASK --apply-patch` and then `resume` **without a replan** **(G1)** | the retry is accepted (the check compares the recorded base with HEAD's tree at those paths only, not the whole tree) and it adopts the new tip, so `resume` reconciles instead of refusing the moved branch, the work is put back, and the next attempt runs on it | `fail: an unrelated commit does not block recovery` |
| FAIL-10 | a commit since the set-aside changed a file the set-aside work also changed — once for a task whose `set-aside.json` exists, and once for a legacy task whose record would have to be derived **(G1)** | `retry TASK --apply-patch` is refused in both, the message lists exactly those paths, and the work tree, the index, `state.json`, `integrity.json`, the event log, `failed.patch` and the task directory are byte-identical afterwards (no record was published) | `fail: conflicting paths refuse recovery` |
| FAIL-11 | another producer was accepted, or a `--reopen` revert commit landed, since the set-aside **(G1)** | `retry TASK --apply-patch` is refused as other work accepted or reverted since, naming the commit, and offers `retry` without the flag | `fail: accepted work since refuses recovery` |
| FAIL-12 | the set-aside work is put back before an attempt **(G1)** | that attempt's `prompt.md` holds the runner's recovered-work section in full — the source attempt, the file list and the instruction to continue — exactly once; the brief in the prompt is unchanged; a type template without `{findings}` gets the section appended instead of losing it; a brief that itself quotes the section's heading still gets the runner's section, because the decision is made on the template before substitution | `fail: the author is told about recovered work` |
| FAIL-13 | `retry TASK --apply-patch` is run first and `replan` second, then `resume` **(G1)** | the queued recovery survives the replan, `replan` says so in its output, and the work is put back before the next attempt | `fail: a queued recovery survives a replan` |
| FAIL-14 | set-aside work has been put back and the task is set aside again **(G1)** | the new `failed.patch` and `set-aside.json` describe the new attempt and hold the whole work, the recovered attempt's directory is unchanged, and no patch file was deleted at any point | `fail: recovery leaves the record alone` |
| FAIL-15 | a recovery is queued with `retry TASK --apply-patch`, a replan then narrows the task's `writes` away from a path the work changed, and `resume` runs **(G1)** | the run stops with the C5 refusal, nothing is restored and `failed.patch` is untouched; `retry TASK` without the flag is then accepted, clears the queue, and the next attempt runs clean with no recovered-work section in its prompt | `fail: an invalid queued recovery can be cancelled` |
| FAIL-16 | a run recorded by the previous runner (a blocked producer with `failed.patch` and `base`, no `set-aside.json`) is opened by this one, and an independent producer was accepted after the set-aside **(G1)** | the derived record's `head` is the commit whose tree is the recorded `base`, not the later tip, so `retry TASK --apply-patch` is refused as other work accepted since, naming that acceptance commit | `fail: migration does not lose the acceptance boundary` |

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
| RUN-16 | a finished run's directory is deleted with `rm -rf` **(B8)** | it succeeds: no directory in the record is made read-only | `run: a run can be deleted` |
| RUN-17 | `prune` is run with one `done` run, one deleted run directory and one unfinished run **(B6)** | the refs of the first two are deleted and the third's are kept | `run: prune` |
| RUN-18 | `replan` resets a blocked producer that has set-aside work to `pending` **(G1)** | `set-aside.json` survives with its base, candidate, attempt and paths; the run's STATUS.md "Next" section and the task's STATUS.md both name `runner retry RUN TASK --apply-patch` | `run: replan keeps the way back to set-aside work` |
| RUN-19 | the commands in the runbook's rows for a blocked task and for a failed task are read out of the runbook and run in order against a scratch repository, both the `--apply-patch` row and the clean row **(G1)** | every one of them is accepted; the `--apply-patch` sequence ends with the set-aside work in the tree before the next attempt, the clean sequence with a pending task whose next attempt starts from the accepted tree, so the table cannot drift from what the commands do | `run: the runbook's recovery rows are executable` |
| RUN-20 | a run recorded by the previous runner, with `failed.patch` and no `set-aside.json`, is replanned by this one, and then retried with `--apply-patch`; and the same run with the two commands in the other order **(G1)** | in both orders the record is derived and published before the reduction, a legacy `apply_patch: true` becomes a queued `recover`, and the set-aside work is put back before the next attempt | `run: an old run keeps its way back across a replan` |
| RUN-21 | the legacy run of RUN-20 has its producer set aside before any acceptance, so the set-aside commit is the run's own starting commit, and the owner commits an edited brief before recovering; both command orders **(G1)** | the derived `head` is that starting commit, not `null`: C1–C3 pass over the brief commit, the work is put back, and the next attempt runs on it | `run: an old run set aside on the starting commit recovers` |
| RUN-22 | one reviewer exhausts its three tries with malformed answers that each contained a blocking finding, and the producer is blocked **(G2)** | the producer's STATUS.md has a "Rejected review answers" section with one entry per rejected answer, each naming the reviewer, round and try, the claimed verdict, the finding titles, the reason it was rejected and the path of its `invocation-N/`; every path named exists; and the section says the answers were not applied | `run: rejected review answers are summarised for the owner` |
| RUN-23 | the same run **(G2)** | the run's STATUS.md shows the task as `blocked (protocol)`, "Needs attention" says the reviewers could not answer in the required form and points at the task's STATUS.md, and "Next" prints `runner retry <run> <task> --apply-patch`. A producer blocked with findings open, and a state written before this change (no `block_kind`), render exactly as they do today | `run: a protocol block is not a substantive block` |
| RUN-24 | a rejected answer's finding title holds a token-shaped string, control characters and 500 characters of text **(G2)** | the stored state and the rendered STATUS.md hold the redacted, single-line, truncated title, and `status --rebuild` regenerates the same bytes | `run: rejected answers are redacted and bounded` |
| RUN-25 | an answer that the adapter accepted is then rejected by the ledger check **(G2)** | that invocation's `outcome.json` records the protocol error and its diagnostic, not `ok` | `run: the invocation records the outcome that was used` |
| RUN-26 | a rejected answer is a JSON object whose `verdict`, `summary` and both `findings` entries are **all valid**, and whose only defect is `"resolutions": null` — so `validate.REVIEW` reports the single error `answer.resolutions must be a JSON array, not null`, on the sibling field **alone** **(G2)** | the answer is still rejected and retried, and its summary holds the claimed verdict, both titles and `"unreadable_findings": 0`. Nothing extracted reaches the ledger | `run: a malformed sibling field does not hide a readable finding` |
| RUN-27 | one rejected answer holds eleven findings, and a seven-member panel produces twenty-one rejected answers in one run **(G2)** | every one of the eleven titles and all twenty-one entries are in the state and in the rendered STATUS.md, each with its invocation path; no line sends the reader elsewhere for a remainder | `run: no rejected answer or title is omitted` |
| RUN-28 | one reviewer times out on its first call while another exhausts its protocol retries; and, separately, a panel where the only broken reviewer timed out **(G2)** | the first is `blocked (protocol, in part)`, naming each reviewer's own cause; the second has no `block_kind`, renders exactly as today, and is never described as having answered in the wrong form | `run: a timeout is not a malformed answer` |
| RUN-29 | a rejected answer holds **four** `findings` entries: one wholly valid; one a bare string; one an object with no `title`; one an object with a string `title` and `"severity": 7`. This is the mixed-entry fixture: its `findings` entries are themselves malformed, so, unlike RUN-26, it does not fail on the sibling field alone **(G2)** | the summary holds **two** readable titles — the valid one, and the `severity: 7` one, recorded as `"severity": "unknown"` — and counts the other **two** as `"unreadable_findings": 2`, rendered as "2 further entries could not be read". Nothing is guessed at | `run: unreadable finding entries are counted, not guessed` |
| RUN-30 | a run saved by the runner **before** this change is stopped at `panel:outcomes-recorded` and resumed by the runner after it. The round already holds `invocation-1`, a quota failure that refunded its try, and `invocation-2`, whose persisted `raw_outcome` is a malformed answer, checkpointed with `tries == 1` **(G2)** | the recovered `invocation` is exactly `…/round-1/invocation-2` — not `invocation-1`, which a tries-indexed rule would have named; the producer's STATUS.md holds one summary for that answer and points at `invocation-2`; `invocation-2/outcome.json` records the protocol error instead of `ok`; `invocation-1/outcome.json` is **byte-identical** to before the resume and is named nowhere; the ledger is byte-identical; `tries` is still 1, so the reviewer keeps the retries the interrupted run had left; and the completed call is not made again | `run: a panel checkpointed before this change is resumed with its answers` |
| RUN-31 | the same upgrade, but the highest-numbered invocation's `outcome.json` is absent, or is present and does not equal the job's persisted `raw_outcome`. The run is driven through the **whole** sequence — the pre-replay pass, `collect_reader` (which pops `raw_outcome`), the rejection, and `reject_answer`'s own recovery call **(G2)** | the refusal is recorded once and holds: the summary is written with its verdict, its titles and its diagnostic and carries **no** invocation pointer; the second recovery call does not adopt the directory the first refused; every `outcome.json` in the round is byte-identical to before the resume, the present-but-mismatched one included; exactly one summary exists after a replay; and the reviewer's next try, if it has one, gets a real invocation path | `run: a refused recovery stays refused through the rejection` |

## Git (GIT)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| GIT-01 | a snapshot is taken | the real index and work tree are unchanged | `git: snapshot has no side effects` |
| GIT-02 | a producer is accepted after two reworks | the run branch gains exactly one commit, holding only that task's files, with the run UUID and task id in the message | `git: one commit per accepted producer` |
| GIT-03 | a task creates a new file | it is in the reviewer's diff and in the commit | `git: untracked files are seen` |
| GIT-04 | a run finishes | nothing was pushed, merged, stashed, reset or cleaned | `git: no destructive or remote operations` |
| GIT-05 | `branch = "current"` **(B2)** | no branch is created, commits land on the checked-out branch, and a detached HEAD is refused | `git: current branch option` |
| GIT-06 | the root is not a git repository **(B3)** | `validate` and `start` refuse it and say why: snapshots, restores and commits all need git | `git: required` |
| GIT-07 | a snapshot is taken and `git gc --prune=now` is run **(A2)** | the snapshot's tree is still present, held by a ref under `refs/task-runner/<run>/` | `git: snapshots are pinned` |
| GIT-08 | a path to restore is a symbolic link **(A3)** | the link is recreated as a link, and the file it pointed at is not written to | `git: links are never followed` |
| GIT-09 | a path to restore had its executable bit removed **(A3)** | the bit is back | `git: modes are restored` |
| GIT-10 | a path to restore lies under a directory that is now a symbolic link to somewhere outside the repository **(A3, B3)** | the link is removed as a link, the directory and file are recreated inside the repository, and nothing outside is touched | `git: parents are checked` |
| GIT-11 | an attempt leaves an embedded git repository, or adds a submodule entry **(A3, B3)** | it is found in the candidate scan and removed, the attempt does not pass, the feedback names it, and the later restore completes normally | `git: unsupported entries are removed early` |
| GIT-12 | an accepted commit is made **(A2)** | its message carries `Run:`, `Task:` and `Operation:` trailers | `git: commits carry the operation id` |
| GIT-13 | a task is accepted **(B2)** | `git status` is clean afterwards, and `git revert` of that commit succeeds | `git: the index follows the commit` |
| GIT-14 | `start` runs with `branch = "run"` **(B2)** | the run branch is checked out, `run.json` records the original branch, and the work tree is byte-identical | `git: the run branch is checked out` |
| GIT-15 | two snapshots of an unchanged tree are taken with the run's reused index, and one with a fresh index **(B2)** | all three tree ids are equal | `git: the reused index is faithful` |
| GIT-16 | a failed attempt created files in new nested directories **(B2)** | after the restore the directories are gone too | `git: emptied directories are removed` |

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
| PRE-01 | `doctor` runs **(A5, B5)** | each agent profile is qualified per capability (`answer`, `read`, `execute`, `write`, `resume`, `boundary`) by an effect the runner observes itself (a value returned, a file written, a file left unchanged), never by tool events in the stream, and the result is written to `qualification.json` | `pre: doctor qualifies capabilities` |
| PRE-02 | `check-gates` runs on an untouched tree **(A12)** | every gate is reported as pass, fail or error. A `new` gate that already passes is an objection; an invariant that passes is not | `pre: new gates must fail first, invariants need not` |
| PRE-03 | a `new` gate exits 126 or 127, times out, or exits 1 from a missing import so that its output does not match its `fail_pattern` **(A12)** | it is reported as `error`, apart from "fails as intended" | `pre: a wrong failure is an error` |
| PRE-04 | a gate leaves untracked files behind | `check-gates` lists them, since they would end up in a commit | `pre: gates that litter` |
| PRE-05 | a scripted agent returns a valid object but not the random value from the scratch file; another writes a wrong digest for the `execute` probe **(A5, B5)** | `doctor` grants neither `read` nor `execute`, and `start` refuses a workflow whose types need them on that profile, before any run is created | `pre: a greeting is not a capability` |
| PRE-06 | a profile has only `answer` and the workflow sets `review_mode = "provided_context"` **(A5)** | the review runs with a complete evidence bundle and is labelled text-only in the record; if the evidence exceeds the context budget it fails instead of running on part of it | `pre: text-only review is explicit` |
| PRE-07 | `doctor` ran before with the same binary version, profile hash, host and capabilities **(A5)** | the cached qualification is used and no model is called; `--force` repeats it | `pre: qualification is cached` |
| PRE-08 | a run meets an environment failure on a profile whose qualification was cached **(B5)** | the cached entry is discarded, so the next `doctor` or `start` qualifies again | `pre: a failed environment is re-qualified` |

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
| REC-09 | killed in the middle of a set-aside restore **(B6)** | `resume` runs the restore again from the pinned target and verifies the tree by snapshot | `rec: restores are re-run` |
| REC-10 | killed after `update-ref` and before the index sync **(B6)** | `resume` records acceptance and syncs the index; `git status` is clean | `rec: index sync is part of the commit` |
| REC-11 | killed during the second of three reverts of a `--reopen` **(B6)** | `resume` aborts the half-done revert, recognises the first by its operation id, and continues with the second | `rec: reopen is resumable` |
| REC-12 | killed between pinning a candidate and recording it, or while closing a directory **(B6)** | both are repeated with the same result | `rec: idempotent effects` |
| REC-13 | the machine rebooted, and the lock's pid and start ticks match a new process **(B6)** | the boot id differs, so the lock is stale | `rec: boot id is part of process identity` |
| REC-14 | killed at `recover:before-restore`, inside the restore, at `recover:after-restore`, and at each save inside `open_transaction` (the pin's `begin` and `finish`), including the one that persists `active_producer` and `step="attempt"` before the recovery bookkeeping **(G1)** | `resume` runs the restore again from the pinned candidate tree, verifies the tree by snapshot, installs the transaction from the intent whatever the state already showed, and the attempt runs once with the recovered-work notice in its prompt exactly once | `rec: recovery is resumable` |
| REC-15 | killed at `recover:before-restore`, and the branch is then moved to a different commit with the same tree **(G1)** | `resume` refuses with a reconciliation error naming the expected and the found commit, restores nothing and opens no transaction | `rec: a moved branch stops an interrupted recovery` |
| REC-16 | killed at `decision:file-written` while `set-aside.json` is replaced for a second set-aside of the same task **(G1)** | `resume` writes the file and its manifest entry again from the intent, the integrity check passes, and the file holds the new attempt's record | `rec: a replaced decision file is repaired` |

## Budget (BUD) — all (A11)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| BUD-01 | four reviewers are ready, each with a $5 cap, and $1 of the run budget is left | none starts, and the run stops as out of budget | `bud: reservation before dispatch` |
| BUD-02 | a call ends below its cap | the reservation is replaced by the actual cost and the rest is released | `bud: reservations are settled` |
| BUD-03 | a Codex call completes, and another is interrupted | `run.json` and STATUS.md show known spend, reserved spend and unpriced usage separately; the interrupted call counts as unknown, not as zero | `bud: honest accounting` |
| BUD-04 | a workflow uses an agent that reports no cost | `validate` says that the dollar limits do not bind on it and that time and attempts do | `bud: no promise that cannot be kept` |
| BUD-05 | a run stopped for budget with a producer active; `resume --add-budget 20` is run **(B10)** | the expected tree is checked, the budget is raised and the change is an event in the log, and the transaction continues from the step it stopped at | `bud: a budget stop is a pause` |

## Prompt assembly (PRM) — all (B11)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| PRM-01 | a brief contains the text `{diff}` and `{rules}` | they appear unchanged in the prompt: substituted text is never scanned again | `prm: one pass` |
| PRM-02 | a diff contains lone `{` and `}` characters | the prompt renders, with them intact | `prm: braces are ordinary characters` |
| PRM-03 | a diff exceeds `diff_cap_bytes` | it is cut at a file boundary, with a marker that names the omitted files and the path of the full diff | `prm: the diff cap is visible` |
| PRM-04 | the findings that need a response exceed `findings_cap_bytes` | the task is `blocked` for a person. No finding is dropped | `prm: findings are never truncated` |
| PRM-05 | any prompt is built | every value from a task, an agent or the repository is inside a labelled data block, and `{rules}` authorizes the workflow brief within runner boundaries while treating repository/agent text as evidence | `prm: data is fenced` |
