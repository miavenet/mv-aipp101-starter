# Response to the task-runner design review

Written 2026-09-19, in reply to [the review](task-runner-review.md) and its
[Codex companion](task-runner-codex-headless.md).

## Summary

**All twelve findings are correct, and all twelve were acted on.** None is rejected. On three of
them (P1-07, P1-10, P2-12) the defect is accepted in full but the remedy differs in part from the
one proposed; the reasons are given under each. The design documents were amended in place, since
they are the contract the build will follow, and the changes are recorded as amendments A1 to A12 in
[`task_runner/docs/00-decisions.md`](../task_runner/docs/00-decisions.md). Every finding now has
executable scenarios in [`06-scenarios.md`](../task_runner/docs/06-scenarios.md), which grew from 81
to 134 rows. No code was written: the product directory is still design only.

The review's central point deserves to be said plainly. The design had the right parts (gates the
runner owns, bounded rework, fresh reviewers, a durable record) but had not specified the contracts
**between** them: who owns the work tree and for how long, what exactly is verified and what exactly
is committed, and what is true after a crash. Those gaps would have produced a runner that works in
a demonstration and corrupts a repository in unattended use.

## How the evidence was checked

| Claim | Check | Result |
|---|---|---|
| Five prototype defects, with a reproduction script | The session's permission system declined to execute a script taken from an external file, so it was not run. Each defect was confirmed instead by reading the code it exercises, which I wrote | **All five confirmed.** `restore()` does `open(path, "wb")` on the blob: it follows links and ignores modes. `commit()` runs `git add -A -- paths` then `git commit -- paths`: it takes whole files, owner's edits included. `Codex.parse()` sets `failed = code != 0 or bool(problem)`: a stream with no `turn.completed` passes, and the final-message file is read if it exists at all |
| The recorded Codex reviews never read the repository | Counted event types in both recorded streams | **Confirmed.** Each holds `thread.started`, `turn.started`, one `agent_message`, `turn.completed`, and no `command_execution`. The author stream holds two `command_execution` items and the `bwrap` namespace error |
| `approval_policy = "never"` is the right Codex setting | OpenAI's configuration reference | **Confirmed**: "use `on-request` for interactive runs or `never` for non-interactive runs" |
| The documentation links | Fetched | Resolve. `developers.openai.com/codex/...` now redirects to the `learn.chatgpt.com` addresses the review cites |
| The design lines cited | Read | Accurate. The scheduler line "a writer is ready and no readers are running -> start that one writer" is the hole in P1-01, and "Round *k* corresponds to attempt *k*" is the bug in P1-07 |

One correction to my own earlier reporting follows from this. I told the owner that Codex had been
proven as a reviewer in the live run. That was wrong. It was proven to return a structured verdict
about text placed in its prompt. The design's default "Codex: reviewer only in this container" rested
on that mistake and has been withdrawn.

## Finding by finding

### P1-01 — Reserve the workspace for a whole producer lifecycle. **Agreed. Done (A1).**

The hole is real and is in the text: with A's panel ready and independent producer B ready, the
engine loop preferred the writer, so B would have run over A's uncommitted candidate. SCH-07 did not
cover it, as the review says.

Changed: a producer is now the run's **active producer** from its first edit until it is committed
or set aside, and only its own gates, checks, panel and rework are scheduled meanwhile. The
transaction ends only when a snapshot shows a clean accepted tree. Parallelism stays inside the
panel. For a pending human verification I took the review's first option: **the tree is held and the
run stops.** The second option, storing the candidate away and re-verifying it later, keeps more
branches moving but is a second recovery path to get right; it is listed as later work.
Documents: 02 Scheduling, 05 engine loop and "The producer transaction". Scenarios: SCH-08, SCH-09
(the review's two acceptance tests, as written), SCH-10.

### P1-02 — A side-effect protocol for crash recovery. **Agreed. Done (A2).**

An atomic `state.json` protects one file. RUN-03's "killed at any point" promised more than that.

Changed: every external effect follows **intent, effect, outcome**, with a unique operation id
recorded before the effect and carried in the commit trailer. `resume` reconciles every intent
without an outcome before doing anything else; the five cases (commit happened, did not happen,
branch tip unexpected, agent still alive, agent gone with no terminal event) are a table in 05,
"Crash recovery". A process is identified by group id and start time, never a bare pid. Unknown
completion is `interrupted`, never success. Attempt and invocation directories are numbered once and
never reused. State is flushed and synced, and so is its directory. Every snapshot the run relies on
is pinned under `refs/task-runner/<run>/`. Scenarios: REC-01 to REC-08, GIT-07, GIT-12, RUN-12.

### P1-03 — Do not copy the prototype's restore. **Agreed. Done (A3).**

Confirmed by reading: the prototype would overwrite the target of a symbolic link. In an unattended
tool that restores files, that is the worst kind of defect.

Changed: restoration is done by git, not by writing bytes. With a scratch index loaded from the base
tree, `git checkout-index --force` recreates each path by its recorded type and mode; it unlinks
first, so a link is replaced and never written through. Paths absent from the base are removed with
`lstat` and `unlink`. Parents are checked to be real directories inside the repository. Submodule
entries are refused. After a restore, a snapshot must equal the base tree. Recovery uses the pinned
candidate tree and a complete `git diff --binary --full-index`; the capped text diff is for readers
only. `retry --apply-patch` checks the patch's base first. Ignored build output is stated to be
outside the guarantee.

The implementation plan no longer says prototype code "can be carried over". It now says **none is
carried over as it stands**, lists the defects, and keeps only what the live run established about
the tools. The prototype is left unchanged as evidence, as the review advises, with a "Known defects"
section added to its README. Scenarios: FAIL-02 (rewritten to the review's list: executable bit,
link, symlinked parent, file-to-directory, binary, awkward names), FAIL-04, FAIL-07, GIT-08 to GIT-11.

### P1-04 — Disable dirty starts. **Agreed. Done (A4).**

`allow_dirty` was mine, added as a convenience, and its comment ("only task-changed paths are ever
touched") was false for the exact case the review constructs: owner's edit and agent's edit in one
file. It is removed from the workflow reference and from the design. A run starts from a clean tree,
with no override. `resume` also checks the branch tip, index and tree against what was recorded when
the run paused. Scenarios: RUN-02 (rewritten to the review's staged-plus-unstaged test), RUN-12.

### P1-05 — Codex "reviewer only" was not established. **Agreed. Done (A5).**

See the correction above. A one-line greeting would have passed `doctor` on a machine where the
agent cannot read a file.

Changed: `doctor` qualifies each agent, model and profile **per capability** (`answer`, `read`,
`execute`, `write`, `resume`, `boundary`), each by evidence the runner checks itself: a random value
that exists only in a scratch file, a tool event, a file read back. Each task type now declares what
it `requires` (the six library types were updated), and a workflow that asks for more than a profile
has is refused before any producer runs. Text-only review is a separate mode that a workflow must
ask for by name, is labelled in the record with its evidence manifest, and fails if the evidence does
not fit. Sandbox startup failure is an **environment failure**: it stops the run and uses no attempt.
Qualification is cached as the companion document proposes, because it costs money.
From the companion, also adopted: `approval_policy="never"`, explicit session ids and never
`--last`, no `--skip-git-repo-check`, named profiles with their effective settings hashed into the
run, credentials kept out of every recorded file, a separate environment for gates, and the
statement that a container with the developer's workspace mounted writable is not an isolation
boundary. There is no automatic fallback to bypass flags. Scenarios: PRE-01, PRE-05 (the review's
test), PRE-06, PRE-07, AGENT-03, AGENT-11 (the recorded blocked author, kept as a fixture).

### P1-06 — Require complete execution, validate locally. **Agreed. Done (A6).**

Changed: a call has a result only when the process exited normally, the stream holds a terminal
event of **this** invocation, the final answer was written by **this** invocation (every call gets a
directory created exclusively), and the answer passes **the runner's own** validation. That validator
is small and says so: types, enums, required keys, no unknown keys, for the runner's own schemas
only, with no claim to be JSON Schema. On top of shape it checks meaning against the ledger. An
invalid answer is a **protocol retry**, at most twice, counted apart from producer attempts, and it
never becomes a finding or a rework. The review's caution is adopted too: a failed shell command
inside a session is ordinary work, and only a failed capability is a failure of the call.
Scenarios: AGENT-08 to AGENT-12, FND-03 (rewritten), FND-16.

### P1-07 — Review rounds and convergence. **Agreed on all three defects. Done (A7), with one remedy changed.**

1. *Gate failure before the first review.* Correct: "round k = attempt k" would have handed the first
   reviewer a rework diff. Attempts and rounds are now counted apart, and a reviewer's first sight of
   a candidate is always a full review. Scenario FND-12.
2. *An old blocker left unresolved with nothing new.* Correct. The verdict is now **derived from the
   ledger** after the answer is applied; the model's `verdict` must agree or the answer is a protocol
   error. Scenario FND-13.
3. *A changed function breaks an unchanged caller.* Correct, and the most important of the three:
   the automatic downgrade would have hidden a real regression. Finding ids are also now unique in
   the run (`implement/PE-2`), scenario FND-01.

**Where I differ.** The review proposes to "escalate ambiguous out-of-diff blockers rather than
silently downgrading them". I did not make escalation the default, for a reason grounded in D15: the
rule exists because reviewers given a whole document again tend to find something new each round,
and if every out-of-diff finding goes to a person, a panel of five can turn each rework round into a
queue of human decisions, which is the opposite of running to completion. Instead the finding carries
a `caused_by` field naming the changed location that introduced the problem, as the review itself
suggests (`introduced_by_attempt`, "related changed locations"), and **the runner checks mechanically
that the named location is inside the rework diff**. If it is, the finding blocks. If the reviewer
names nothing, it is advisory. A reviewer who names a changed location falsely is answered by the
author with `disputed`, and a dispute the reviewer keeps open already escalates to a person. So a
person is involved exactly when two agents disagree, not whenever a location falls outside a diff.
Scenarios FND-14, FND-15. If the live check shows reviewers abusing `caused_by`, escalation by
default is the fallback, and the review's wording will have been right.

### P1-08 — An acceptance graph separate from task dependencies. **Agreed. Done (A8).**

I had given reviews a readiness exception and left `check` and `human` verifiers without one, so
`verifies = "A"` with `needs = ["A"]` was a deadlock the cycle check could not see.

Changed: each producer has a **candidate** and an **accepted** milestone. `needs` targets accepted;
`reviews` and `verifies` target the candidate. Validation looks for cycles in that expanded graph and
prints the trace. A verifier may not need its target or anything downstream of it. Scenarios WF-14,
WF-15 (the indirect A → B → V → A case), WF-16.

### P1-09 — Verify and commit the exact same source state. **Agreed. Done (A9).**

Both halves were real: committing declared outputs could omit a helper the gates relied on, and a
gate could rewrite source after an earlier gate had passed.

Changed: `writes` is the allowlist of paths a task may change, defaulting to `outputs`; `outputs`
stays the list of deliverables. Anything changed outside `writes` is reverted and fails the attempt.
`removes` and `may_be_empty` make deletions and empty markers legitimate. Paths under `.git` and
`.runs` are refused. Every gate, check, verdict and approval is stored with the **candidate tree id
and a hash of the verifier's configuration**; the runner snapshots after each verifier and before the
commit, and any change to tracked source voids everything before it. The commit is exactly that
candidate. Because `.runs/` is ignored and therefore invisible to snapshots, the record protects
itself: `state.json` is hashed around every job, and closed directories are made read-only.
Scenarios ACC-02, ACC-13 to ACC-17, FRZ-07.

### P1-10 — Reopen and overlapping claims must invalidate stale acceptance. **Agreed. Done (A10), partly by a different route.**

Adopted as proposed: each accepted task's **input manifest** is persisted; overlapping writers must
be dependency-ordered, rejected at load otherwise (WF-17); `--reopen` computes the affected closure
(dependants and consumers), shows it, and undoes it with **revert commits**, newest first, never a
reset, stopping on a conflict (RUN-14, RUN-15); every `prompt_file`'s content and the resolved `root`
are frozen at start (RUN-13).

**Where I differ.** For a later task B that claims and changes accepted A's output while accepted C
relied on the old content, the review offers two v1 options: reopen the affected suffix, or refuse
the interleaving. I chose neither as the default, because this case is not exotic: it is every
second task that extends `src/book/**`, and reopening C each time would make incremental work
impossible. Instead: B's own verification **re-runs the gates and verifying checks of every accepted
task it touched**, so if B breaks C mechanically, B does not pass (FRZ-05). Where C was verified only
by review, nothing mechanical can re-check it, and the run says so rather than pretending: C is
marked **stale against** the new version, with the file and both hashes, in the record and in
`STATUS.md` (FRZ-06). This meets the review's actual requirement, "do not retain stale accepted
status silently", at a cost proportionate to a common case. An owner who wants the strict behaviour
uses `--reopen C`.

### P2-11 — Honest budgets and process supervision. **Agreed. Done (A11).**

Changed: the run budget is enforced **by reservation before dispatch**, so four reviewers cannot
each start a $5 call with $1 left (BUD-01). Spend is reported as three numbers, known, reserved and
unpriced, and unpriced usage is never counted as zero or converted into invented dollars (BUD-03,
BUD-04). I had written that Codex could be bounded by "an optional `max_tokens` per call, counted
from its event stream". The review is right that this cannot work: the recorded streams show usage
only in `turn.completed`. The claim is deleted, and the design now says that a workflow using Codex
must not promise a dollar ceiling. Output is streamed to files in the invocation directory with a
bounded tail in memory and incremental parsing, and process groups are stopped at a deadline and on
the runner's own shutdown (AGENT-13, AGENT-14).

### P2-12 — "Gates must fail first", and text-only no-progress. **Agreed. Done (A12), with one part declined.**

Changed: a gate is an **invariant** unless marked `new = true`. `check-gates` reports pass, fail or
error for every gate, objects only to a `new` gate that already passes or that fails for the wrong
reason (an optional `fail_pattern` tells a missing import from the intended assertion), and never
objects to an invariant that passes (PRE-02, PRE-03). The no-progress stop now needs the same
failure **and the same candidate tree**, so identical text after a real source change no longer ends
a task early (ACC-04).

**Declined: fingerprinting by "normalized failing test IDs" and a "structured failure category" as
part of the runner.** The runner is generic by requirement (R1), and its gates are arbitrary
commands: in the one example workflow they are `cmake`, `ctest`, and three different Python scripts.
Extracting failing test ids means a parser per test framework, each of which would break silently
when a tool changes its output. The candidate tree hash is the stronger signal and costs nothing:
it answers "did the author change anything that matters?" exactly, where test ids answer it only by
inference. The remaining case the review worries about, changing timestamps or test order disguising
no progress, is bounded by the attempt limit, which the review also says to keep. A workflow author
who wants id-level matching can supply `fail_pattern`.

### Suggested implementation sequence. **Agreed. Done.**

The plan is reordered to the review's sequence: contract corrections (this revision), recovery
primitives before anything depends on them, one producer transaction end to end, headless adapters
and environment qualification **before** findings and panels, then replan, then the live check on a
qualified host. One addition of mine is kept ahead of the recovery primitives: the workflow loader,
because the acceptance-graph cycle check (A8) and the ordered-writers check (A10) live there, cost
nothing to test, and are needed to write the NYSE workflow.

## What changed, by file

| File | Change |
|---|---|
| `task_runner/docs/00-decisions.md` | Amendments A1 to A12; the "Codex: reviewer only" default withdrawn |
| `task_runner/docs/02-concepts.md` | Rewritten: outputs and inputs, acceptance, rework, findings, dependencies and freezing, scheduling, failure, runs |
| `task_runner/docs/03-workflow-file.md` | `allow_dirty` removed; `writes`, `removes`, `may_be_empty`; invariant and `new` gates; four new validation rules; `requires` on types |
| `task_runner/docs/04-run-directory.md` | Invocation directories; `inputs.json`, `verification.json`, `qualification.json`, `briefs/`; intents; record integrity; three-part spend; ledger-derived verdicts; run-unique finding ids |
| `task_runner/docs/05-architecture.md` | Engine loop and the producer transaction; lifecycle; review rounds; the result contract; failure classes; capabilities and `doctor`; profiles; streamed logs; git by type and mode; a new "Crash recovery" section; limits by reservation |
| `task_runner/docs/06-scenarios.md` | 81 to 134 scenarios: 13 rewritten, 53 added, including new REC and BUD groups |
| `task_runner/docs/07-implementation-plan.md` | Stages reordered; "no prototype code carried over as it stands"; Codex's role follows qualification; new risks |
| `task_runner/library/types/*.toml`, `library/README.md` | `requires` capabilities per type |
| `task_runner/examples/book-module.toml` | `writes`, and an invariant gate beside a `new` gate |
| `research/task_runner/prototype/README.md` | A "Known defects" section. The code is unchanged |

## Not done, and why

- **No code.** The owner's instruction stands: design artifacts only.
- **The reproduction script was not executed**, for the reason given above. Its five results agree
  with what the code says, so nothing rests on the omission.
- **Candidate staging during a human pause** (the review's second option under P1-01) is deferred.
- **The prototype was not fixed.** It is evidence. Its defects are documented where a reader will
  meet them.
