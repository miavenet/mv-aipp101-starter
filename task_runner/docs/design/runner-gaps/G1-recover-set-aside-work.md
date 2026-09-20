# G1 — Set-aside work cannot be recovered after a replan

Design for one of the five resilience gaps found on 2026-09-20 while the runner drove the
`spsc-queue` and `spsc-queue-gaps` workflows. It is written to be implemented unattended, and to be
reviewed by someone who was not there. It changes no code by itself: it states the mechanism, the
records, the messages, the scenarios and the order of work.

Binding background: [00 — Decisions](../../00-decisions.md) (D9, D12, D13; amendments A1, A2, A3,
A9, A10, B1, B2, B6, B7, B8), [02 — Concepts](../../02-concepts.md) (Failure),
[04 — Run directory](../../04-run-directory.md), [05 — Architecture](../../05-architecture.md),
[06 — Scenarios](../../06-scenarios.md), [runbook](../../runbook.md).

## Problem

Producer `close` was `blocked`: its review panel could not produce valid answers. Its work was set
aside as designed (D9) — the candidate tree pinned under `refs/task-runner/<run>/close/set-aside`,
a complete binary-capable patch written to `tasks/NNN-close/failed.patch`, the work tree returned to
the last accepted state.

The runbook tells the owner to "fix the brief, `replan`, `retry TASK [--apply-patch]`, `resume`".
The owner did exactly that:

1. Edited the brief and committed it on the run branch. `replan` requires a clean tree, so the
   commit is not optional; `replan` explicitly permits commits that touch only workflow definitions
   and briefs (`replan._definition_paths`).
2. Ran `replan`. The task's definition had changed, so `close` was in the replan's affected
   closure, and `replan.apply` reduced its state to `{dir, attempts, cost_usd}` and set it
   `pending`. Everything the recovery path depends on — `base`, `candidate`, any queued
   `apply_patch` — was dropped in that same line.
3. Ran `retry close --apply-patch`. It was refused: `'close' is pending; only a failed or blocked
   task is retried` (`engine.retry`).

Had that status check passed, the next check would have refused too. `engine.retry` compares the
patch's recorded base tree with the whole of `git.tree_of("HEAD")`; the brief commit changed HEAD,
so the trees differ and the retry is refused as "other work was accepted since" — even though the
brief commit touched none of the files the patch touches and `git apply --check` succeeds.

The owner recovered the work by hand during an interrupted attempt, and had to write into the brief,
by hand, that earlier work was present in the tree and must be continued rather than redone. Nothing
in the runner told the author that. An author told nothing redoes the work: about 28 minutes of it.

Three separate defects, one symptom:

- **The way back is stored in state that `replan` is entitled to throw away.** The recovery record
  lives in `run.state`, and `replan` deliberately resets affected tasks.
- **The base check is whole-tree.** It cannot distinguish "the owner committed the brief you told
  them to commit" from "another producer was accepted and your work is stale".
- **The author is not told.** `engine.begin_transaction` does set a short feedback note when
  `apply_patch` survives, but it names no attempt, it is lost with the rest of the state at
  `replan`, and it is wrapped in a heading that says the previous attempt was not accepted.

## Requirements

Numbered as in the brief.

- **R1.** After any sequence of `replan` and `retry` that the runbook recommends for a failed or
  blocked producer, the owner can have the task's set-aside work put back before its next attempt,
  with one documented command, in either order of `replan` and `retry`.
- **R2.** A commit by the owner between set-aside and retry that does not touch the task's `writes`
  must not prevent applying the patch. A patch that no longer applies is refused with nothing
  changed, and the message says which paths conflict.
- **R3.** The author of the next attempt is told, by the runner and not by the owner's brief, that
  earlier work is present in the tree, where it came from (which attempt), and that it must continue
  from it rather than start over.
- **R4.** Applying set-aside work is an external effect: intent, effect, outcome, and `resume`
  reconciles a crash at each point (A2). Attempt numbers continue; finished attempt directories are
  never modified; the patch file is never modified or deleted.
- **R5.** The runbook's table for blocked and failed tasks matches what the commands do.

Constraints from the brief that shape every choice below: Python 3.11 standard library only; no new
files outside `task_runner/`; every behaviour change opt-in or strictly safer than today; old run
records keep working (a read path for old states); acceptance is never decided by an agent's report;
nothing may let a task change files outside its `writes`; prefer the existing record, events and
STATUS machinery to a new subsystem.

## Design

### The three decisions the brief asks for

**Decision 1 — who accepts the recovery: `replan`, `retry` or `resume`?**
**`retry` accepts a `pending` producer that has an unconsumed set-aside record**, and `replan`
carries the *request* (not the status) across the reset.

- Rejected: *`replan` preserves `blocked`/`failed` for a producer whose definition changed.* A
  replanned task genuinely is pending: its definition changed and `replan.apply` restarts its
  findings ledger, so the findings that blocked it are superseded. Leaving it `blocked` would make
  STATUS.md report a block whose evidence no longer exists, and the engine's loop only schedules
  `pending` tasks, so the runbook's plain "`replan`, `resume`" path (no retry at all) would stop
  working. That is a behaviour regression for workflows that do not care about the patch.
- Rejected: *a new flag on `resume`.* `resume` acts on the whole run; a recovery is per task, so
  the flag would need a task argument and would then be `retry --apply-patch` under another name.
  `resume` must also stay "an optimisation, never required" (B1); putting the only recovery route on
  it makes it required.
- Chosen, and why it is safe: the acceptance is not "any pending task", it is "a task with a
  set-aside record that is still recoverable", and every one of the safety checks below still runs.
  `retry --apply-patch` therefore stays the single documented command of R1, spelled the same way in
  both orders of `replan` and `retry`.

**Decision 2 — how the base-tree check is relaxed.** The patch is checked **against the current
HEAD tree restricted to the paths the set-aside work touches**, not against the whole tree, and
three further conditions guard what the whole-tree check used to guard implicitly. All are reads;
none changes anything.

| # | Condition | Refused when | Covers |
|---|---|---|---|
| C1 | HEAD is a descendant of the commit the branch was on when the work was set aside | the run branch moved away from where the work was set aside | someone reset or rewrote the branch |
| C2 | For every path in the set-aside's `paths`, the blob id and mode in `tree_of(HEAD)` equal those in the recorded `base` tree | any of those paths differs | R2: the patch no longer applies; the message lists exactly those paths |
| C3 | No commit in `<set-aside head>..HEAD` carries a `Run:` trailer | a runner-made commit landed since | "other work was accepted since": an acceptance commit (`Task:` trailer) or a `--reopen` revert commit (`Reverts:` trailer) |
| C4 | The pinned candidate tree still exists in the repository | the ref is gone | the record can no longer be trusted to restore from |

C2 is what buys R2. The owner's brief and workflow commits carry no runner trailers, so C3 passes
them; they touch only definition paths, so C2 passes them. An accepted producer, in contrast, is
refused by C3 whether or not it overlaps — which is exactly today's conservatism, kept: the
set-aside work may depend on the *content* of files it never wrote, and nothing mechanical can tell.
C2 compares end states, so a change that was later reverted by hand is not an obstacle.

C2 also makes the recovery equivalent to applying the patch: when every path the work touches is at
its recorded base, "restore those paths from the candidate tree" and "apply `failed.patch`" produce
the same tree.

**Decision 3 — where the record lives.** A per-task decision file, `set-aside.json`, beside
`failed.patch` in the task directory, protected by the integrity manifest (B8). Files in the task
directory survive `replan`; the reduced state does not. `replan` additionally carries one new state
key, `recover`, so that the *other* order (retry first, then replan) does not silently drop a
request the owner already made.

### Mechanism

**Putting the work back is a path-scoped restore from the pinned candidate tree, not `git apply`.**
A3 requires restoring by git type and mode, never by writing bytes, and says recovery uses the
pinned tree and the full binary patch. `gitops.restore` already does that: it handles executable
bits, symbolic links (replaced, never followed), parent checks, removal of paths absent from the
target, pruning of emptied directories, and — the reason this matters here — it **verifies the
result by snapshot against an expected tree** and is idempotent, because it always writes from the
pinned target. That makes the crash story (R4) fall out of machinery that already exists and is
already covered by REC-09.

The expected tree is computable: it is `tree_of(HEAD)` with the set-aside's `paths` taken from the
candidate tree. This is what `gitops.build_commit_tree` already computes for the commit recipe,
minus its assertion that the result equals the candidate. It is factored out:

```python
def tree_with(self, base_tree, source_tree, paths):
    """`base_tree` with each of `paths` taken from `source_tree`; a path absent from `source_tree`
    is absent from the result. Computed in a scratch index; the real index and the work tree are
    not touched. Returns a tree id."""
```

`build_commit_tree` is then `tree_with(tree_of("HEAD"), candidate, paths)` plus its existing
equality check, so there is one implementation of the idea.

`failed.patch` is read by nobody in this path. It is never rewritten and never deleted by the
recovery (R4); it stays the portable artifact the owner can `git apply` by hand, and it is still
rewritten only where it is rewritten today — by a later `set_aside` of the same task.

### State and record changes

**New file `tasks/NNN-<task>/set-aside.json`**, written inside `engine.set_aside`, with
`run.write_decision` (durable, and added to the integrity manifest):

```json
{
  "task": "close",
  "attempt": 3,
  "attempt_dir": "tasks/030-close/attempt-3",
  "status": "blocked",
  "reason": "the review panel could not answer in the required form",
  "at": "2026-09-20T11:02:14Z",
  "head": "c0ffee1...",
  "base": "<base tree id>",
  "candidate": "<candidate tree id>",
  "candidate_ref": "refs/task-runner/<run>/close/set-aside",
  "patch": "tasks/030-close/failed.patch",
  "paths": ["src/spsc/queue.hpp", "tests/close.cpp"]
}
```

`paths` is `git.changed_paths(base, candidate)`, the same list the set-aside restore uses. By the
time a candidate exists, every change outside the task's `writes` has already been reverted by
`engine.attempt` (or the run has stopped as an environment failure), so `paths` is inside what the
task was allowed to change. The recovery restores exactly these paths and nothing else, so it cannot
put back a change outside `writes`.

**New per-task state keys** in `state.json`:

| Key | Written by | Meaning |
|---|---|---|
| `recover` | `engine.retry` with `--apply-patch` | `{"from": "set-aside", "attempt": 3, "candidate": "<tree>"}` — a queued request, consumed at the start of the next transaction |
| `recovered` | the recovery itself | `{"attempt": 3, "at": "...", "files": 7, "op": "op-0042-ab12cd34"}` — what was put back, for the prompt, STATUS.md and the record |

`recover` replaces today's boolean `apply_patch`. **Read path for old states:** `apply_patch: true`
is read as `{"from": "set-aside"}` and the missing fields are filled from `set-aside.json`.

**Migration of old runs.** A run paused under an older runner has `failed.patch` but no
`set-aside.json`. The first time the runner needs the record for such a task, it derives one —
`base` from `state.tasks[tid]["base"]`, `candidate` from the pinned `…/<tid>/set-aside` ref,
`attempt` from the attempt directories, `head` from the branch tip recorded in the state — and
writes it with `run.write_decision`. Deriving is idempotent. If `base` is not in the state (an old
run that an old runner already replanned), the record cannot be derived and the recovery is refused
with a message that names `failed.patch`; see Failure cases.

**New intent kind `recover`**, in `run.state["intents"]`:

```json
{"op": "op-0042-ab12cd34", "kind": "recover", "at": "...", "task": "close", "attempt": 3,
 "target": "<candidate tree>", "base": "<tree of HEAD before the recovery>",
 "expected": "<tree_with(HEAD, candidate, paths)>", "paths": ["…"]}
```

It is a distinct kind rather than the existing `restore` kind because its reconciliation must also
start the producer's transaction; see Failure cases.

**New events**: `recover-requested` (from `retry`) and `recovered` (after the outcome), both with
`task`, `attempt` and `files`.

### Control flow

`engine.recovery_plan(run, git, task_id)` is one pure function, used by `retry` and by the engine:

```python
def recovery_plan(run, git, task_id):
    """The checked plan for putting a task's set-aside work back, or None when none was requested.
    Reads only. Raises Refused, with the owner's message, when the work cannot be put back.
    Returns {"record": <set-aside.json>, "paths": [...], "expected": "<tree>", "base": "<tree>"}."""
```

`engine.retry(run, engine, git, task_id, apply_patch=False)` changes in three places:

- The status gate becomes: `failed` and `blocked` as today; `pending` **only** when
  `set-aside.json` exists for the task. A `pending` task with a record and no `--apply-patch` is
  still refused, but with a message that names the command that does something (below).
- With `--apply-patch`, `recovery_plan` is called and its refusal is the retry's refusal. Nothing
  in the record, the state, the index or the work tree is written before it returns.
- On success it sets `st["recover"]` instead of `st["apply_patch"]`, and emits `recover-requested`.

`engine.begin_transaction(task)` changes order so that the intent is recorded before any state is
mutated:

1. `base = self.snapshot()`; refuse unless it equals `tree_of("HEAD")` and the tree is clean —
   unchanged, and unchanged in position: a recovery never runs on a dirty tree.
2. `plan = recovery_plan(...)`; a `Refused` becomes an `EngineStop` carrying the same words. The
   task is still `pending`, the run has changed nothing, and the owner can `retry` clean.
3. If `plan`: `op = run.begin("recover", …)`; crash point `recover:before-restore`;
   `git.restore(candidate, paths, expected_tree=plan["expected"], index_file=run.index_file)`;
   crash point `recover:after-restore`; then the shared transition below.
4. The shared transition, `engine.open_transaction(run, git, task_id, base, plan, op)`: set
   `active_producer`, `st.update(status="running", step="attempt", base=base, …)`, pin
   `<tid>/base`, pop `recover`, set `recovered`, set `st["feedback"]["recovered"]`, `run.finish(op)`,
   emit `recovered`, save. The same function is called by the reconciler, so there is one
   implementation of "the transaction is now open and the work is back".

`base` stays the pre-recovery tree (HEAD's tree), as today. The recovered work therefore appears in
the next attempt's diff, in its reviewers' diff, and in the next `failed.patch` — the author is
responsible for all of it again, which is what "continue from it" means.

`replan.apply` changes in one line: the keys carried over for an affected task become
`('dir', 'attempts', 'cost_usd', 'recover')` (`recover` only when present). Nothing else about
`replan` changes: the task is still reset to `pending`, its ledger is still restarted.

### Command-line surface

No new command and no new flag. `runner retry RUN TASK --apply-patch` is the one documented command
of R1, and it now works in either order with `replan`.

### Messages shown to the owner

Verbatim. `<run>`, `<task>`, `<n>`, paths and shas are substituted.

`retry --apply-patch` accepted (replaces today's line in `cli.cmd_retry`):

```
close: fresh attempts, continuing from the set-aside work of attempt 3. Continue with: runner resume <run>
```

`retry` without the flag, unchanged:

```
close: fresh attempts, starting clean. Continue with: runner resume <run>
```

`retry` on a `pending` task that has a record and was given no flag:

```
'close' is pending; its work from attempt 3 was set aside and is still recorded. Run `runner retry close --apply-patch` to put it back before the next attempt, or `runner resume` to start clean.
```

`retry` on a `pending` task with no record (today's wording for the status gate is kept for every
other status):

```
'close' is pending; only a failed or blocked task is retried
```

`--apply-patch` where there is no record at all, unchanged:

```
'close' has no set-aside patch to apply
```

C2, the conflicting-paths refusal (R2):

```
the set-aside work of 'close' (attempt 3) no longer applies: these paths changed since it was set aside: src/spsc/queue.hpp, tests/close.cpp. Nothing was changed. Settle them, or retry without --apply-patch to start clean.
```

C3, an acceptance commit since:

```
the set-aside work of 'close' (attempt 3) cannot be put back: other work was accepted since (commit 8b7cf7e of task 'bench'). Nothing was changed. Retry without --apply-patch to start clean.
```

C3, a `--reopen` revert since:

```
the set-aside work of 'close' (attempt 3) cannot be put back: accepted work was reverted since (commit 6c47167 reverts a3afef6). Nothing was changed. Retry without --apply-patch to start clean.
```

C1:

```
the set-aside work of 'close' (attempt 3) cannot be put back: the run branch is no longer a descendant of c0ffee1, where the work was set aside. Nothing was changed.
```

C4, and the underivable old record:

```
the candidate tree of 'close' is no longer in this repository (refs/task-runner/<run>/close/set-aside). Its complete patch is still at tasks/030-close/failed.patch and can be applied by hand with `git apply`. Nothing was changed.
```

The engine, when the work goes back (`self.say`, before `close: started`):

```
close: put back the set-aside work of attempt 3 (7 files)
```

`STATUS.md` of the task, replacing today's single set-aside line when `set-aside.json` exists:

```
Its work was set aside in failed.patch; the candidate tree is pinned under refs/task-runner/.
Set aside from attempt 3 (blocked: the review panel could not answer in the required form), 7 files.
To put it back before the next attempt: runner retry <run> close --apply-patch
```

with, when `recover` is queued:

```
Queued: the set-aside work of attempt 3 will be put back before the next attempt.
```

and, once it has happened:

```
The set-aside work of attempt 3 was put back before attempt 4 (7 files).
```

`STATUS.md` of the run, "Next" section: the existing `runner retry <run> <task> [--apply-patch]`
line is also emitted for a **pending producer that has an unconsumed set-aside record**, so the way
back is visible after a replan without reading the task page.

`replan`'s own output gains one line per affected task that carries a queued recovery:

```
close: pending; the set-aside work of attempt 3 is still queued to be put back
```

### What the author is told (R3)

The notice is runner text, assembled from the record, and never from the owner's brief.
`feedback` gains an optional key `recovered`, and `prompts.feedback_text` is restructured so that a
recovery with no other feedback does not print a heading that says the previous attempt was not
accepted:

```python
def feedback_text(feedback, cap_bytes):
    """What a rework prompt holds (B1). `feedback` is a dict: recovered (optional), cause,
    cause_title, needing, info. The recovered section is rendered first and on its own when there
    is no cause, no finding needing a response and nothing for information."""
```

The section, verbatim (the file list is fenced as a data block, per B11):

```
# Earlier work of this task is already in the work tree

The work of attempt 3 of this task was set aside when the task was blocked, and the runner has now
put it back into the work tree, unchanged. These files already hold it:

<<<DATA recovered files
src/spsc/queue.hpp
tests/close.cpp
DATA>>>

Continue from this work. Read these files before you change them. Do not start over, and do not
revert what is there: it is yours, from an earlier attempt of this same task.
```

It is rendered into the produce prompt through the existing `{findings}` placeholder, which every
type template in `library/types/` uses. A workflow may ship a type whose template omits
`{findings}`; to keep R3 unconditional, `prompts.produce_prompt` checks the rendered prompt for the
section's first line and appends the section at the end if the template did not consume it. That
check is on the runner's own marker text, not on anything an agent produced.

The rework path (`rework_prompt`, a continued session) is unaffected: a recovery only ever happens
at the start of a transaction, where the session id has been cleared by `retry`, so the next call is
a full produce prompt.

## Alternatives rejected

| Alternative | Why not |
|---|---|
| Keep the recovery record in `run.state` and teach `replan` to preserve more keys | It is the same class of bug one layer up: every future change to what `replan` resets can drop it again silently, and the record is also what `status` and a cold reader need. A decision file in the task directory is what B8 and D14 already ask for |
| `replan` keeps a definition-changed producer `blocked` or `failed` | Its findings ledger is restarted by the same operation, so the recorded reason for the block no longer exists; and the engine schedules only `pending` tasks, so "replan, resume" would stop working for every workflow that does not use the patch |
| A `--recover TASK` flag on `resume` | `resume` is per run, so the flag needs a task argument and becomes `retry --apply-patch` spelled differently; and B1 requires `resume` to stay an optimisation, never the only way to do something |
| Apply `failed.patch` with `git apply`, as today | `git apply` writes bytes, which A3 forbids for restores (modes, symbolic links, parents); a crash in the middle leaves a tree that cannot be verified against any known tree, so R4's reconciliation would need a new mechanism. Restoring from the pinned candidate reuses `gitops.restore`, which is idempotent and verifies by snapshot |
| Drop the base check and rely on `git apply --check` | `git apply --check` answers "do the hunks still fit", not "is this work still based on what was accepted". Work whose context lines happen to survive a later acceptance would be silently applied on top of a tree it was never verified against, which is the "continue on top of failed work" D9 turned down |
| Refuse only when the commits since the set-aside touch the task's `writes` | Narrower than C3 and less safe: a producer accepted since may have changed a file the set-aside work reads but never writes. C3 keeps today's conservatism for runner-made commits and relaxes only for the owner's definition commits, which is the case the runbook itself creates |
| Auto-recover: `resume` puts set-aside work back without being asked | Not opt-in, and it would silently re-apply work the owner may have decided to abandon. The brief requires every behaviour change to be opt-in or strictly safer |
| Re-apply by re-running the attempt from the recorded prompt | Spends money to reproduce work that is already on disk, and is not reproducible anyway |

## Failure cases and crash points

Every new external effect, with its intent, effect and outcome (A2).

| Effect | Intent, recorded before | Effect | Outcome | Reconciliation on `resume` |
|---|---|---|---|---|
| Put set-aside work back | `{"kind": "recover", "op", "task", "attempt", "target": candidate tree, "base": HEAD tree, "expected", "paths"}` in `state.json`, durable | `git.restore(target, paths, expected_tree=expected, index_file=run.index_file)` | `run.finish(op, restored=<n>, attempt=<n>)` plus the state transition, in `open_transaction` | `_reconcile_recover`: run the restore again from the pinned target and verify by snapshot, then call `open_transaction` if the transaction is not already open, then finish |
| Write `set-aside.json` | none needed | `run.write_decision` | the file and its manifest entry | Repeating the write gives the same bytes; it is derived from the same pinned trees as `failed.patch` |

`_reconcile_recover` is a new reconciler rather than a reuse of `_reconcile_restore` for one reason:
the recovery leaves the work tree *not* equal to HEAD's tree, so if only the restore were replayed,
the engine would next call `begin_transaction`, find the tree unclean, and stop the run with "the
work tree is not at a clean accepted state" — a deadlock the owner could only leave by hand. The
reconciler must therefore finish the transition as well. `_reconcile_commit` already sets acceptance
state in the same way, so this is the established shape.

New crash points, injected through `engine.crash` like the existing ones and added to the crash-point
list the recovery tests iterate: `recover:before-restore`, `recover:after-restore`. The existing
`restore:after-removals` inside `gitops.restore` is exercised on this path too.

Crash analysis, point by point:

| Killed at | State on disk | What `resume` does |
|---|---|---|
| after `retry`, before `resume` | `recover` queued; no intent | `begin_transaction` re-runs every check against the tree as it is now, and refuses if it moved. The queue is not a promise |
| `recover:before-restore` | intent present, work tree untouched | `_reconcile_recover` restores and opens the transaction |
| inside `gitops.restore` (`restore:after-removals`) | intent present, tree partly restored | the restore is re-run from the pinned target and verified by snapshot; partial state is overwritten, not merged |
| `recover:after-restore` | intent present, tree already correct | the restore is re-run (idempotent), verifies immediately, transaction opened |
| after `run.finish`, before the attempt starts | no intent, transaction open, `step="attempt"` | the ordinary `advance` path runs the attempt. `recovered` is already in the state, so the prompt still carries the notice |

Other failure cases:

- **The restore cannot be completed** (permissions, a path outside the repository). `gitops.restore`
  raises `RestoreError`; as everywhere else, that is an **environment failure**: the run stops with
  the paths named and no attempt is used (FAIL-06 semantics). The intent stays, so a later `resume`
  tries again once the machine is fixed.
- **The pinned candidate ref is gone** (a hand-run `git gc` after the ref was deleted, or a run
  record restored without its refs). C4 refuses and names `failed.patch`. `prune` already keeps the
  refs of unfinished runs, and of finished runs whose set-aside patch is missing, so this needs
  someone to have deleted refs by hand.
- **An old run, already replanned by an older runner**, has `failed.patch` but neither
  `set-aside.json` nor `base` in its state. The record cannot be derived, so the recovery is refused
  with the C4 message and the owner applies the patch by hand. This is the one case the design does
  not repair; it exists only for runs that were paused across the upgrade *and* replanned before it.
- **The work tree is dirty when the transaction starts.** Unchanged: the tree check comes first and
  the run stops. A recovery never merges into someone else's edits (A4).
- **Two recoveries of the same task.** `retry --apply-patch` twice only rewrites the same request.
  Once the work is back and the attempt has run, the transaction ends in acceptance or in a new
  set-aside that rewrites `failed.patch` and `set-aside.json` for the new attempt; the old attempt
  directories are untouched and attempt numbers continue, because `record.new_attempt` numbers from
  the directories on disk and `replan` carries `attempts`.
- **Nothing changed on refusal.** Every check in `recovery_plan` is a read (`ls_tree`, `rev-list`,
  `trailers`, `show-ref`). The request is stored only after they all pass, and the restore starts
  only after they pass a second time at transaction start.

## Scenarios

New rows for [06 — Scenarios](../../06-scenarios.md), continuing the existing series of each group.
Test names follow each group's prefix, as every existing row does. All are checkable by the model-free suite: scripted agents (`tests/fake_agent.py`), scratch
repositories and the helpers in `tests/helpers.py`.

### Failure and the DAG (FAIL)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| FAIL-08 | a producer is blocked, the owner commits an edited brief on the run branch, runs `replan` (which resets the task to `pending`) and then `retry TASK --apply-patch` | the retry is accepted, the set-aside work of the last attempt is put back at the start of the next transaction, that attempt's number continues the series, and no finished attempt directory changed | `fail: set-aside work survives a replan` |
| FAIL-09 | a commit since the set-aside touches only files outside the paths the set-aside work changed | `retry TASK --apply-patch` is accepted: the check compares the recorded base with HEAD's tree at those paths only, not the whole tree | `fail: an unrelated commit does not block recovery` |
| FAIL-10 | a commit since the set-aside changed a file the set-aside work also changed | `retry TASK --apply-patch` is refused, the message lists exactly those paths, and the work tree, the index, `state.json` and `failed.patch` are byte-identical afterwards | `fail: conflicting paths refuse recovery` |
| FAIL-11 | another producer was accepted, or a `--reopen` revert commit landed, since the set-aside | `retry TASK --apply-patch` is refused as other work accepted or reverted since, naming the commit, and offers `retry` without the flag | `fail: accepted work since refuses recovery` |
| FAIL-12 | the set-aside work is put back before an attempt | that attempt's `prompt.md` holds the runner's recovered-work section, naming the attempt it came from and the files, and telling the author to continue from it; the brief in the prompt is unchanged; a type template without `{findings}` gets the section appended instead of losing it | `fail: the author is told about recovered work` |
| FAIL-13 | `retry TASK --apply-patch` is run first and `replan` second, then `resume` | the queued recovery survives the replan, `replan` says so in its output, and the work is put back before the next attempt | `fail: a queued recovery survives a replan` |
| FAIL-14 | set-aside work has been put back and the task is set aside again | the new `failed.patch` and `set-aside.json` describe the new attempt and hold the whole work, the recovered attempt's directory is unchanged, and no patch file was deleted at any point | `fail: recovery leaves the record alone` |

### Runs and the record (RUN)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| RUN-18 | `replan` resets a blocked producer that has set-aside work to `pending` | `set-aside.json` survives with its base, candidate, attempt and paths; the run's STATUS.md "Next" section and the task's STATUS.md both name `runner retry RUN TASK --apply-patch` | `run: replan keeps the way back to set-aside work` |
| RUN-19 | the commands in the runbook's rows for a blocked task and for a failed task are read out of the runbook and run in order against a scratch repository | every one of them is accepted and the set-aside work ends up in the tree before the next attempt, so the table cannot drift from what the commands do | `run: the runbook's recovery rows are executable` |

### Crash recovery (REC)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| REC-14 | killed at `recover:before-restore`, inside the restore, and at `recover:after-restore` | `resume` runs the restore again from the pinned candidate tree, verifies the tree by snapshot, opens the transaction exactly once, and the attempt runs once with the recovered-work notice in its prompt | `rec: recovery is resumable` |

### Coverage

| Requirement | Scenarios |
|---|---|
| R1 | FAIL-08 (replan then retry), FAIL-13 (retry then replan), RUN-19 |
| R2 | FAIL-09 (allowed), FAIL-10 (refused, paths named, nothing changed), FAIL-11 |
| R3 | FAIL-12 |
| R4 | REC-14 (intent, effect, outcome at each crash point), FAIL-08 (attempt numbers, untouched directories), FAIL-14 (the patch file) |
| R5 | RUN-19, RUN-18 |

## Implementation plan

Ordered. Each task is independently reviewable and well under half an hour of agent work. "Files"
lists what the task may write.

1. **The set-aside record.** Write `set-aside.json` in `engine.set_aside` with `run.write_decision`;
   add `engine.set_aside_record(run, git, tid)` with the derive-and-write migration for old runs;
   add the `FILE_NOTES` entry and the `04` layout line.
   Files: `src/taskrunner/engine.py`, `src/taskrunner/record.py`, `tests/test_lifecycle.py`.
   Scenarios: FAIL-14, RUN-18 (the record half). Depends on: nothing.
2. **`gitops.tree_with`.** Extract it from `build_commit_tree` and re-express `build_commit_tree` in
   terms of it, so the commit recipe and the recovery share one implementation.
   Files: `src/taskrunner/gitops.py`, `tests/test_gitops.py`. Scenarios: none of its own; covered by
   GIT-02 and FAIL-08. Depends on: nothing.
3. **`engine.recovery_plan` and its refusals.** C1–C4, the exact messages, reads only.
   Files: `src/taskrunner/engine.py`, `tests/test_lifecycle.py`. Scenarios: FAIL-09, FAIL-10,
   FAIL-11. Depends on: 1, 2.
4. **`retry` accepts a recoverable `pending` producer.** The status gate, the `recover` state key
   with its read path for `apply_patch`, the `recover-requested` event, the CLI lines.
   Files: `src/taskrunner/engine.py`, `src/taskrunner/cli.py`, `tests/test_lifecycle.py`,
   `tests/test_cli.py`. Scenarios: FAIL-08 (the retry half), FAIL-10, FAIL-11. Depends on: 3.
5. **The `recover` intent, `open_transaction` and `_reconcile_recover`.** Reorder
   `begin_transaction`, add the two crash points to the engine and to the tests' crash-point list.
   Files: `src/taskrunner/engine.py`, `src/taskrunner/record.py`, `tests/test_lifecycle.py`.
   Scenarios: REC-14, FAIL-08. Depends on: 4.
6. **`replan` carries `recover`.** One line in `replan.apply`, plus the reported line.
   Files: `src/taskrunner/replan.py`, `src/taskrunner/cli.py`, `tests/test_replan.py`.
   Scenarios: FAIL-13, RUN-18. Depends on: 4.
7. **The author's notice.** `feedback["recovered"]`, the restructured `feedback_text`, the
   append-if-the-template-dropped-it rule in `produce_prompt`, and the `recovered` feedback set by
   `open_transaction`.
   Files: `src/taskrunner/prompts.py`, `src/taskrunner/engine.py`, `tests/test_prompts.py`,
   `tests/test_lifecycle.py`. Scenarios: FAIL-12. Depends on: 5.
8. **STATUS.md.** The task page's set-aside block, the queued and done lines, and the run page's
   "Next" line for a recoverable pending producer.
   Files: `src/taskrunner/record.py`, `tests/test_record.py`. Scenarios: RUN-18. Depends on: 1, 4.
9. **The documents, and the test that keeps them true.** The edits listed below, plus the
   runbook-driven test that extracts the commands from the runbook's two tables and runs them.
   Files: `docs/runbook.md`, `docs/02-concepts.md`, `docs/04-run-directory.md`,
   `docs/05-architecture.md`, `docs/06-scenarios.md`, `tests/test_runbook.py`.
   Scenarios: RUN-19, RUN-18. Depends on: 1–8.

## Documentation changes

No existing document is edited by this design; these are the edits the implementation makes.

| Document | Change |
|---|---|
| `docs/runbook.md` §3, "TASK is blocked: the agent said …" | Spell the sequence the commands actually support: `runner replan RUN`, then `runner retry RUN TASK --apply-patch` to keep the set-aside work (or `runner retry RUN TASK` to start clean), then `resume`; and state that the two may be run in either order (R5) |
| `docs/runbook.md` §3, "attempts ran out with findings open" | Same command spelling, so both rows name `--apply-patch` the same way |
| `docs/runbook.md` §4, "A task failed" | Add that a commit of workflow or brief edits between the set-aside and the retry does not prevent `--apply-patch`, and that an acceptance since does |
| `docs/runbook.md`, the decision chart | The `task blocked` and `failed task` branches carry the same command sequence as the tables |
| `docs/runbook.md`, "Where to look" | New row: "What work is waiting to be put back, and how" → `tasks/NNN-task/set-aside.json` |
| `docs/02-concepts.md`, Failure (D9) | Replace "first checks that the patch's base is still the current accepted tree" with the path-scoped check and its three guards, and say that the work is restored from the pinned candidate tree, `failed.patch` being the portable copy |
| `docs/04-run-directory.md` | Add `set-aside.json` beside `failed.patch` in the task-directory listing, with one line on what it holds |
| `docs/05-architecture.md`, the intent table | New row for the `recover` intent: what is recorded, and that reconciliation re-runs the restore from the pinned target and then opens the transaction |
| `docs/05-architecture.md`, the producer state machine and the CLI list | Note that a transaction may open by putting set-aside work back, and that `retry --apply-patch` accepts a producer left `pending` by a replan |
| `docs/06-scenarios.md` | Add FAIL-08…FAIL-14, RUN-18, RUN-19, REC-14. Amend FAIL-04, whose THEN still says the base is checked against the current accepted tree, to the path-scoped rule |
| `docs/07-implementation-plan.md` | Add the nine tasks above to the stage that owns resilience work, with their scenarios |

## Open questions

1. **Should a recovery expire?** Nothing here bounds how long a set-aside record stays usable. C1
   and C3 bound what can have happened to the branch, not how stale the work is. A `--max-age` or a
   warning above some number of days was not designed; the owner sees the set-aside timestamp in
   `set-aside.json` and STATUS.md and can judge.
2. **A recovery across a `--reopen` of an upstream task.** C3 refuses it, so the owner must retry
   clean. Whether a narrower rule is worth having (the revert did not touch anything the work reads)
   is not decidable from the record: input manifests (A10) exist per *accepted* task, not for a
   set-aside candidate. Recording an input manifest at set-aside time would make this answerable
   later; it is out of scope here.
3. **Recovering into a different task.** The owner occasionally wants the work of a task that a
   replan removed or renamed. Nothing in this design addresses that; `failed.patch` and `git apply`
   remain the manual route.
4. **Assumption, to be verified by the implementer:** that the candidate's changed paths always lie
   within the task's `writes` by the time a candidate exists, because `engine.attempt` reverts every
   violation and stops the run as an environment failure when it cannot. The implementer should
   assert this in the recovery path — refuse if any path in the record is outside the task's current
   `writes`, since a replan may have narrowed them — rather than rely on it. The refusal wording is
   not designed here; it should name the paths and the task.
5. **Assumption:** that `replan` is the only operation that reduces a task's state, so carrying
   `recover` there is sufficient for R1. It was read out of `replan.apply`; a reviewer should
   confirm no other path rewrites `state["tasks"][tid]` wholesale.
