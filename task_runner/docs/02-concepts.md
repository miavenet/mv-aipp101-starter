# 02 — Concepts

The whole model, in the order the pieces depend on each other. Decisions are cited as D1 to D16,
and amendments made after the design review as A1 to A12, from the [decision log](00-decisions.md).

## Workflow, task, run

A **workflow** is a TOML file: a named list of **tasks** joined by `needs` into an acyclic graph.
A **run** is one execution of a workflow, with a UUID and a directory. A workflow can have many
runs. A run works from its own frozen copy of the workflow (D11, D12).

## Kinds: the four behaviours the engine knows (D4)

| Kind | What it does | Who acts | Result |
|---|---|---|---|
| `produce` | Creates or changes files in the repository | An agent, with write access | `done` or `blocked`, a summary, and on rework a response to each finding |
| `review` | Judges the work of one producer, from one perspective. Read-only | An agent, read-only, in a new session | `pass` or `block`, a summary, findings |
| `check` | Runs commands. Passes if all exit 0 | The runner. No agent | pass or fail, with the output |
| `human` | Pauses until a person approves or rejects | A person | approve, or reject with a comment |

`review`, `check` and `human` are the **verifiers**. A `check` or `human` task verifies a producer
when it says `verifies = "<task>"`; otherwise it is a standalone step in the DAG.

## Types: templates over a kind (D4)

A **type** is a file in the library: a kind, a prompt template, parameters, and defaults for agent,
model, gates and limits. `design`, `implement`, `test`, `code-review`, `design-review` and
`summarize` ship as a starter library. A task names a type and fills its parameters. Adding a type
of work means adding a file.

## Personas: the reviewer's perspective (D4)

A **persona** is also a file: a title, what that reviewer cares about, what counts as blocking for
them, and what is out of their scope. A review task's `perspective` parameter names one. The starter
library has `principal-engineer`, `spec-compliance`, `devops`, `process-manager` and
`technical-project-manager`. A persona can carry its own agent and model, so a perspective can be
given to a different model from the author's.

Telling a persona what is **out of scope** matters as much as its focus: it stops five reviewers
from each raising the same general point.

## Outputs and inputs (D2, D3)
A producer declares two path sets (A9):

| Key | Meaning | Default |
|---|---|---|
| `outputs` | Its **deliverables**: what downstream tasks are pointed at, what the manifest lists, what is frozen on acceptance | required |
| `writes` | Every path it **may change**, deliverables and helpers alike. A change outside this set is reverted by the runner and the attempt does not pass | the same as `outputs` |
| `removes` | Paths that must **not** exist afterwards, for a task whose job is to delete something | none |

An output is normally required to exist and be non-empty. An entry written as
`{ path = "pkg/__init__.py", may_be_empty = true }` lifts the second condition. Paths under `.git`
or `.runs` are rejected in all three sets.

After each attempt the runner writes a **manifest**: each declared output that exists, with its
hash, mode and size, plus the id of the **candidate tree** (a git tree of the whole work tree) the
attempt produced. It also records the task's **input manifest**: the hashes of the upstream outputs
it was given. That is what later lets the runner say which accepted work relied on which version of
a file (A10).

A task's **inputs** are derived, not written by hand. For every task in its `needs`, and for the
task a review targets, the runner gives the agent:

- the upstream task's id, type and title,
- its summary (a few sentences from its result),
- its output file list from the manifest,
- for a review: the diff of the work under review.

The agent reads the files itself. Prompts carry pointers and summaries, not file contents, so they
stay small however large the deliverables are. The exception is a reviewer qualified only for
**text-only review** (A5): it cannot read the repository, so the runner must give it the complete
evidence in the prompt, and the review is recorded as such.

## Acceptance (D7)
A producer's attempt passes through verifiers in a fixed order, cheapest first. The first failure
stops the sequence and sends the work back.

| Step | Verifier | Cost |
|---|---|---|
| 1 | The agent's invocation completed properly and its answer is valid (A6), and it did not answer `blocked` | free |
| 2 | Every declared output exists (and is non-empty unless `may_be_empty`); every `removes` path is gone | free |
| 3 | Nothing outside the task's `writes` changed, and no protected or frozen file changed. Any such change is reverted by the runner | free |
| 4 | The task's own `gate` commands exit 0 | seconds to minutes |
| 5 | Every `check` that `verifies` this task passes | seconds to minutes |
| 6 | The review panel leaves no open blocking finding in the ledger | agent calls |
| 7 | Every `human` task that `verifies` this task approves | a person's time |

A producer must have at least one of steps 4 to 7, or the workflow is rejected when it loads. Steps
1 to 3 always apply. The agent's own report is recorded and never used.

**Every result is bound to the exact candidate it judged (A9).** After step 3 the runner records the
candidate tree id. Each gate, check, verdict and approval is stored with that id and a hash of the
verifier's configuration. The runner takes a new snapshot after every verifier and before the
commit. If the tracked source differs from the candidate, a gate or a check rewrote something: all
earlier results are void, the attempt does not pass, and the feedback names the command and the
files. Build products belong in paths the repository ignores; those are outside the snapshot, and
outside the rollback guarantee.

When all verifiers pass on one unchanged candidate, the task is **accepted**: exactly that candidate
is committed (D13) and its outputs are **frozen** (D8).

## Rework: the one loop (D1, D5)
```
                    ┌──────────── consolidated feedback ─────────────┐
                    ▼                                                │
 pending ─► produce (attempt n) ─► gates/checks ─► review panel ─► open blocking findings?
                    │                   │                                │ no
                    │ blocked           │ no progress                    ▼
                    ▼                   ▼                             accepted ─► commit ─► frozen
              needs a person          failed
```

- Gate or check failure: its output goes back to the author at once. Reviewers are not called for
  work that does not pass its checks.
- Review: **the whole panel runs before anything goes back.** The author receives one list of all
  blocking findings (advisory ones are attached for information) and does one rework.
- Three counters are kept apart (A7, A6):
  - **Producer attempts.** A rework is a new attempt. `max_attempts` (default 3) counts attempts,
    whatever sent the work back. Attempt directories are numbered once and never reused, even after
    `retry` resets the counter.
  - **Review rounds.** A reviewer's round 1 is the first time it sees a candidate, whichever attempt
    that is. If attempt 1 fails its gates, the panel's round 1 happens on attempt 2, and it is a full
    review.
  - **Protocol retries.** An agent call that ends without a proper terminal event, or with an answer
    that fails validation, is retried up to twice with a fresh invocation. This is a fault of the
    call, not of the work: it uses no producer attempt and creates no finding.
- When attempts run out, the task is `failed` if a gate or check sent it back last, and `blocked`
  (a person is needed, with the open findings listed) if review did.
- The author's session is continued for a rework, so it keeps its understanding and the provider's
  cache is reused. After an agent error, a timeout or an interruption the session is abandoned and
  the next attempt starts clean.
- **No progress (A12):** the task fails early only when the gate fails the same way **and the
  candidate tree is identical to the previous attempt's**, meaning the author changed nothing that
  matters. The same failure text after a real change to the source is not "no progress"; the attempt
  limit covers that case.

## Findings (D5, D15)
A finding is the unit of review feedback.

| Field | Meaning |
|---|---|
| `id` | Given by the runner: producer, persona code and a number, such as `implement/PE-2`. Unique in the run, so two producers reviewed by the same persona never collide (A7) |
| `severity` | `blocking` or `advisory`. A reviewer marked `advisory` in the workflow can only produce advisory findings |
| `title`, `detail` | What is wrong and why it matters |
| `location` | File and line or section, where that applies |
| `caused_by` | Later rounds only: the changed location that introduced the problem |
| `status` | `open`, `resolved`, `disputed`, `escalated` |

**The verdict is derived from the ledger, not taken from the model (A7).** After a reviewer's answer
is applied, the runner computes whether any blocking finding of that reviewer is open. An old
finding left `unresolved` blocks even if the reviewer raised nothing new. The model's own `verdict`
field must agree with the computed one, or the answer is invalid and is retried as a protocol error.

**Round 1** is a full review of the whole candidate. **Later rounds judge the fix.** A reviewer who
blocked is given its own open findings, the author's response to each, and the rework diff. It must
mark each finding `resolved` or `unresolved`. It may raise a new blocking finding in two cases:

1. its `location` lies inside the rework diff, or
2. its `location` lies outside, and it names in `caused_by` a location that is inside the rework
   diff: the rework changed a function and broke an unchanged caller. The runner checks mechanically
   that the named location really is in the diff.

A new concern that meets neither case is recorded as advisory. Reviewers who passed are, by default,
shown the rework diff only, under the same two rules.

The author answers each blocking finding with `fixed` or `disputed` and a note. A finding the author
disputes and the reviewer keeps open becomes `escalated`: the task stops for a person, because two
agents disagreeing is not something a third loop settles. A `caused_by` claim the author thinks is
false is settled the same way.

Each producer has one **findings ledger** in the run record, holding every finding from every
reviewer and round, with its history. "What did review find, and was it fixed?" is answered by
reading one file.

## Dependencies and freezing (D8)
`needs = ["design"]` means *design is accepted*. Nothing starts on unreviewed work.

**Two milestones per producer (A8).** Internally a producer has a *candidate* milestone (an attempt
has passed steps 1 to 3) and an *accepted* milestone. `needs` points at accepted. `reviews` and
`verifies` point at the candidate. Validation builds this expanded graph and looks for cycles in it,
so these are rejected at load, each with the dependency trace that shows the deadlock:

- a verifier that also lists its target in `needs` (it would wait for an acceptance that waits for it);
- a verifier that needs anything downstream of its target (V verifies A, V needs B, B needs A).

A `check` or `human` task that only `needs` an accepted task is a standalone step and is fine.

Once accepted, a task's outputs are **frozen**: they join the protected set of every later task, and
a change to them is reverted by the runner like any protected file. A later task B may change a
frozen file of A only by **claiming** it in its own `writes`, and then (A10):

- B must depend on A, directly or through other tasks. An overlapping claim between tasks with no
  order between them is rejected at load.
- `validate` lists every claim, so "task B will modify the approved design" is visible in the plan,
  and B's reviewers see the diff.
- B's verification also re-runs the gates and verifying checks of every accepted task whose outputs
  or inputs B touched. If B breaks accepted work, B does not pass.
- Accepted tasks that consumed the old version and were verified only by review cannot be re-checked
  mechanically. They are marked **stale against** the new version in the record and in `STATUS.md`,
  with the file and both hashes. The run does not pretend their acceptance covers the new content.

## Scheduling (D6)
A task is **ready** when everything in its `needs` is accepted. A verifier is ready when its
target's current candidate has passed the cheaper steps before it.

**A producer owns the work tree for its whole life cycle (A1).** From the moment a producer starts
until it is committed or set aside, it is the run's **active producer**. While there is one, the
only things scheduled are its own gates, its verifying checks, its review panel and its rework.
No other producer starts, and no unrelated check runs, because the tree holds work nobody has
accepted: another task would build on it, and its changes would leak into the first task's review
and commit. Ownership is released only after the tree is back at a clean accepted state, which the
runner verifies by snapshot.

Within that rule:

- **Readers** are `review` tasks and `read_only` checks. The active producer's ready readers run
  together, up to `max_parallel`. This is where the parallelism is.
- A `check` not marked `read_only` is a writer and runs alone.
- A panel's results are gathered and applied together, in workflow order, when its last member
  finishes. So the decision does not depend on which reviewer happened to finish first.
- With no active producer, standalone readers may run together; the next producer is the first ready
  one in workflow order.
- **A pending human verification holds the work tree.** The run stops with exit 255 and nothing else
  starts until the person answers. Continuing other branches over a candidate awaiting approval
  would need the candidate to be stored away and later restored and re-verified; that is deferred.
  A standalone `human` task, which only `needs` accepted work, holds nothing.

Given the same workflow and the same results from agents, the same things happen in the same order.

## Failure (D9)
A task ends unsuccessfully as **failed** (attempts used up on gates, no progress, a reviewer changed
the tree, a verifier's calls kept failing at the protocol level) or **blocked** (the agent said it
cannot do the task properly, a finding was escalated, or attempts ran out with blocking findings
still open). An **environment failure** is a third thing (A5, A6): a sandbox that cannot start, a
missing binary, failed authentication. It stops the run at once with its cause and uses no attempt,
because retrying the work cannot fix the machine.

When a task fails or is blocked:

1. The candidate is kept in full: its tree is pinned under a private git ref so it cannot be garbage
   collected, and a complete binary-capable patch against the base is written to `failed.patch`.
   The capped, readable diff that reviewers saw is a separate file and is never used for recovery.
2. The paths it changed are returned to the last accepted state, **by type and mode** (A3): regular
   files with their executable bit, symbolic links replaced as links and never written through, new
   files removed, parent paths checked so nothing outside the repository is touched. The runner then
   verifies by snapshot that the tree equals the accepted one. Only tracked and untracked-unignored
   paths are covered; ignored build output is not.
3. Every task downstream of it is marked `skipped`, with the reason.
4. Independent branches continue.

The run ends with exit 2 (failed) or 255 (a person is needed). `retry TASK` gives fresh attempts,
either clean or with `--apply-patch`, which first checks that the patch's base is still the current
accepted tree and refuses, with an explanation, if it is not.

## Runs (D11, D12, D13)
- `start` makes a run: a UUID, a directory, a branch `run/<workflow>-<uuid8>`, and a **frozen copy of
  everything that defines the work** (A10): the workflow, the library files it uses, the content of
  every `prompt_file`, and `root` resolved to an absolute path. Editing a brief on disk does not
  change a run.
- **A run starts only from a clean work tree (A4).** There is no option to start dirty: a commit
  limited to a task's paths would still take the owner's uncommitted edits in those same files.
- `resume` continues a run. Nothing is kept in memory between steps, so resuming is the normal way
  the runner works. Before doing anything it **reconciles** (A2): it checks that the branch tip, the
  index and the work tree are what the state expects, completes or rolls back any operation whose
  intent was recorded but whose outcome was not, and stops with an explicit reconciliation error if
  someone changed the branch or the tree while the run was paused.
- `replan` brings an edited workflow into a run where that is safe. Changing an accepted task needs
  `--reopen` (A10): the runner computes everything affected (its dependants, and every task that
  consumed its outputs), shows the list, and undoes those tasks' commits with **new revert commits**,
  newest first, so files a reopened task no longer produces do not linger. The branch is never
  reset. If a revert conflicts, the replan stops and changes nothing further.
- Each accepted producer is one commit on the run branch. Merging the branch is the owner's call.

## The record (D2, D14)

Everything about a run is under one directory, regenerated summaries included. Any directory in it
can be opened cold: `index.json` says what each file is, `STATUS.md` says what happened in words,
and the `README.md` at the top of `.runs/` explains the layout once. See
[04 — Run directory](04-run-directory.md).
