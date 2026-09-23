# 02 — Concepts

The whole model, in the order the pieces depend on each other. Decisions are cited as D1 to D16,
amendments made after the design review as A1 to A12, and amendments made after the adversarial
review as B1 to B12, all from the [decision log](00-decisions.md).

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
when it says `verifies = "<task>"`; otherwise it is a **standalone step** in the DAG (B7):

- A standalone `check` that does not pass is `failed`. There is no author to send it back to, so it
  is not retried on its own; `retry` re-runs it after the person has changed something.
- A standalone `human` task that is rejected is `blocked`, and the note is kept in `decision.json`.
- In both cases dependants are `skipped`, and the run ends with exit 2 or 255.
- A standalone check that is not `read_only` is a writer, and gets the same protection as a
  producer: a BASE snapshot before it, and afterwards the tree is returned to BASE and verified.
  Whatever it builds belongs in ignored paths. A change it leaves in the snapshot fails the check.

## Types: templates over a kind (D4)

A **type** is a file in the library: a kind, a prompt template, parameters, and defaults for agent,
model, gates and limits. `design`, `implement`, `test`, `code-review`, `design-review` and
`summarize` ship as a starter library. A task names a type and fills its parameters. Adding a type
of work means adding a file. The bare kinds `produce` and `review` are themselves small type files
in the library, so a one-off task goes through the same code path as any other (B4).

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

**The repository must be able to see the work (B3).** Everything the runner guarantees rests on git
tree snapshots, so the root must be a git repository, and:

- A path in `outputs`, `writes` or `removes` that git ignores is refused, at `validate` and again
  after every attempt (an agent may have edited an ignore file). An ignored output would pass the
  existence check, be invisible to reviewers, and never be committed.
- `.gitignore`, `.gitattributes` and `.gitmodules`, at any depth, are protected by default. A task
  may change one only by listing that exact path in its `writes`.
- After every attempt the candidate tree is scanned for **embedded repositories and submodule
  entries** (mode 160000) and for changed paths whose parent has become a symbolic link. These are
  treated like a change outside `writes`: the runner removes them while it still can, the attempt
  does not pass, and the feedback names them. So a restore never meets a path it must refuse.
- The guarantee is at **tree level**: two work trees are equal when git hashes them to the same
  tree. With end-of-line or clean filters in `.gitattributes`, bytes that git normalises away are
  outside the guarantee, exactly as they are outside a commit.

Path patterns have one meaning everywhere; see
[03, Path patterns](03-workflow-file.md#path-patterns-b4).

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
commit. The comparison is of the **whole snapshot**: tracked files and untracked files git does not
ignore (B3). If it differs from the candidate, a gate or a check rewrote or littered something: the
runner **puts the tree back to the candidate** by the restore mechanism, all earlier results are
void, the attempt does not pass, and the feedback names the command and the files. Build products
belong in paths the repository ignores; those are outside the snapshot, and outside the rollback
guarantee. `check-gates` finds a littering gate before any money is spent.

Two refinements (B7):

- A check marked `restores = true` is one whose job is to change the source and put it back: a
  mutation tester, a formatter dry run. The runner expects the tree to differ while it runs, and
  afterwards restores the candidate itself instead of trusting the tool to have done so, even when
  the tool crashed or was killed. A difference is then not a failure.
- `read_only` on a check is a claim, and claims are verified. If the snapshot after a `read_only`
  check differs, the **check** fails with "declared `read_only` but wrote: …", the reviews that ran
  beside it are void and run again, no producer attempt is used, and that check is scheduled as a
  writer for the rest of the run.

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
- **What a rework prompt holds (B1).** Always two parts: (a) the immediate cause, which is the gate
  output, the check output, the rejection note or the new findings; and (b) every open blocking
  finding that has **no author response since it was last raised or kept open**. The author's
  `responses` must cover exactly set (b), each once. A finding the author already answered `fixed`,
  which no reviewer has judged yet because a gate failed in between, is listed for information and
  needs no second answer. Responses are recorded against the attempt number.
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
- The author's session is continued for a rework **when its profile is qualified for `resume`**, so
  it keeps its understanding and the provider's cache is reused. Otherwise, and after an agent
  error, a timeout or an interruption, the next attempt starts a new session with the full prompt
  plus the feedback. `resume` is an optimisation, never a requirement (B1), and the rule for
  `responses` is the same either way.
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
| `status` | Blocking: `open`, `resolved`, `disputed`, `escalated`, `superseded`. Advisory: `noted` |

**Advisory findings never stay open (B1).** An advisory finding is recorded as `noted` at the end of
the round that raised it. It is shown to the author for information, needs no response and no
resolution, and no later round is asked about it.

**The verdict is derived from the ledger, not taken from the model (A7).** After a reviewer's answer
is applied, the runner computes whether any blocking finding of that reviewer is open. An old
finding left `unresolved` blocks even if the reviewer raised nothing new. The model's own `verdict`
field must agree with the computed one, or the answer is invalid and is retried as a protocol error.

**One narrow repair, without a model call (G2).** An answer whose only defect is `resolutions`
entries that name no finding in this producer's ledger, in a round where the required set is empty,
is accepted with those entries dropped rather than retried: the round asked for nothing, so `[]` is
the only correct value and dropping is not a guess about what the reviewer meant. The repair never
fires if any entry names a real ledger id — that is a reviewer confused about a real finding, and
stays a protocol error — and it is allowed **only when the repaired answer still derives a block**,
so it can never turn a would-be pass into an acceptance and can never manufacture one; a passing
answer with junk `resolutions` is still a protocol error. Eligibility is decided by the ledger the
answer is finally applied to, not the one a concurrent reviewer's call happened to see, because
reviewers on the same panel are applied to the ledger sequentially, in workflow order.

**Round 1** is a full review of the whole candidate. **Later rounds judge the fix.** A reviewer who
blocked is given its own open **blocking** findings, the author's response to each, and the rework
diff. It must mark each of those `resolved` or `unresolved`, each exactly once. A reviewer with no
open blocking finding returns an empty `resolutions` list (B1).

**The rework diff is per reviewer (B1).** For reviewer R it is the diff from the candidate R last
saw to the current candidate. The ledger stores `last_seen_candidate` for each reviewer. If an
attempt in between failed its gates and no panel ran, R's diff spans that attempt too, so nothing
changed there escapes review. After `retry`, the work is a new line of work: every reviewer's next
round is a round 1, and blocking findings still open from the old line are closed as `superseded`.

A reviewer may raise a new blocking finding in two cases:

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

**An escalation is a human decision, so it holds the tree like one (B10).** The producer becomes
`waiting_human` with its candidate still in place, and the run stops with exit 255. The person runs
`resolve FINDING --as resolved | advisory | upheld` and then `resume`:

- `resolved` or `advisory`: the finding no longer blocks. If the ledger now has no open blocker, the
  runner checks the tree still equals the candidate, and acceptance continues from where it stopped.
  Every earlier verifier result is bound to that same candidate, so none is repeated and no producer
  attempt is used.
- `upheld`: the person sides with the reviewer. The finding stays open and blocking, the author may
  not dispute it again, and a rework follows if attempts remain.

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
a change to them is reverted by the runner like any protected file. `protected` sets are a **union**
across built-in, workflow, type and task level: a task can add to the protected set and can never
narrow it (B9). A later task B may change a
frozen file of A only by **claiming** it in its own `writes` (not merely `outputs`; B4), and then (A10):

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
the tree) or **blocked** (the agent said it cannot do the task properly, a verifier's calls kept
failing at the protocol level, or attempts ran out with blocking findings still open). An escalated
finding is neither: it is a pause for a person, described under Findings. An **environment failure** is a third thing (A5, A6): a sandbox that cannot start, a
missing binary, failed authentication. It stops the run at once with its cause and uses no attempt,
because retrying the work cannot fix the machine.

`failed` and `blocked` are statuses of any task. A verifier that did not pass its latest round is
`objected`; a verifier whose producer ended before it could run is `skipped`. The skip closure
follows `needs`, `reviews` and `verifies` together, so every task always has a status (B7). A panel
whose members cannot produce a valid answer leaves its producer `blocked`, not `failed`: a person
is needed to repair the panel. The record distinguishes, per reviewer, a panel that could not
answer in the required form from one that simply did not finish (a timeout, an agent error, an
interruption), and every rejected answer is summarised — its claimed verdict and finding titles,
never guessed at from a field that happened to be malformed — in the producer's `STATUS.md` (G2).

When a task fails or is blocked:

1. The candidate is kept in full: its tree is pinned under a private git ref so it cannot be garbage
   collected, and a complete binary-capable patch against the base is written to `failed.patch`.
   The capped, readable diff that reviewers saw is a separate file and is never used for recovery.
2. The paths it changed are returned to the last accepted state, **by type and mode** (A3): regular
   files with their executable bit, symbolic links replaced as links and never written through, new
   files removed, parent paths checked so nothing outside the repository is touched. The runner then
   verifies by snapshot that the tree equals the accepted one. Only tracked and untracked-unignored
   paths are covered; ignored build output is not. Directories the restore emptied are removed, up
   to but not including the root (B2). If a restore cannot be completed, that is an **environment
   failure**: the run stops, prints the paths, and leaves the tree alone (B3).
3. Every task downstream of it is marked `skipped`, with the reason.
4. Independent branches continue.

The run ends with exit 2 (failed) or 255 (a person is needed). `retry TASK` gives fresh attempts,
either clean or with `--apply-patch`. `--apply-patch` checks the current tree only at the paths the
set-aside work touched, not the whole tree, so a commit that touches only the workflow or the brief
does not block it; it also refuses unless the branch is still a descendant of where the work was set
aside, no runner-made commit (an acceptance, or a `--reopen` revert) landed since, the pinned
candidate tree still exists, and every touched path is still inside the task's current `writes`. If
every check passes, the work is restored from the **pinned candidate tree**, by type and mode, before
the next attempt runs; `failed.patch` stays the portable copy for applying by hand and is never read
on this path. A refusal changes nothing and says why. While a producer transaction is open, `retry`
is refused for any other task and says which task the run is waiting on (B7).

**Running out of budget is a pause, not a failure (B10).** No new call starts, calls in flight
finish, and the run stops as `stopped` with exit 2. If a producer is active, its transaction stays
open and the expected tree is recorded, exactly as for a human pause. `resume --add-budget USD`
raises the run budget, is recorded as an event, and the run continues where it stopped.

## Runs (D11, D12, D13)
- `start` makes a run: a UUID, a directory, a branch `run/<workflow>-<uuid8>` **which it checks
  out** (B2), and a **frozen copy of
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
- Each accepted producer is one commit on the run branch. The run branch stays checked out when the
  run ends; going back to the original branch, and merging, are the owner's call.

## The record (D2, D14)

Everything about a run is under one directory, regenerated summaries included. Any directory in it
can be opened cold: `index.json` says what each file is, `STATUS.md` says what happened in words,
and the `README.md` at the top of `.runs/` explains the layout once. See
[04 — Run directory](04-run-directory.md).
