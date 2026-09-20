Write the design for five resilience fixes to the task runner in
`task_runner/`. They were found on 2026-09-20 while the runner drove
two real workflows (a C++ lab, runs `spsc-queue` and `spsc-queue-gaps`)
with Claude authors and Codex reviewers. Each gap below states what
happened, what is required, the constraints, and what you must decide.
You decide the mechanism; you do not get to drop a requirement. If a
requirement cannot be met without breaking a recorded decision, say so
in the design, name the decision, and propose the smallest amendment.

Read before writing: `task_runner/docs/00-decisions.md` (decisions D,
amendments A and B are binding), `02-concepts.md`, `04-run-directory.md`,
`05-architecture.md`, `06-scenarios.md`, `runbook.md`,
`nyse-execution-lessons.md`, `headless-observability.md`, and the
modules named under each gap in `task_runner/src/taskrunner/`.

## Output

You are given ONE gap per task (the task prompt names it). Write one
document for it: `task_runner/docs/design/runner-gaps/G<n>-<slug>.md`
(the task's declared output gives the exact name). Read the whole of
this brief anyway: the constraints at the end apply to every gap, and
the gaps touch neighbouring code. Do not design the other gaps.

The document holds: Problem (with the evidence below, condensed),
Requirements (numbered as here), Design (mechanism, state and record
changes, command-line surface, messages shown to the owner, verbatim
where wording matters), Alternatives rejected (with the reason),
Failure cases and crash points (every new external effect needs
intent, effect, outcome per A2), Scenarios, Implementation plan (an
ordered list of independently reviewable implementation tasks: for
each, the files it may write, its scenarios, and what it depends on;
keep each task to well under half an hour of agent work),
Documentation changes (which existing docs change, and how), and Open
questions.

Scenarios are WHEN/THEN rows in the table format of `06-scenarios.md`,
with new ids continuing the existing series of the fitting group
(RUN, FND, AGENT, PRE, REC, BUD ...), and a test name per row in the
house style (`run: ...`). Every requirement must be covered by at
least one scenario, and every scenario must be checkable by the
model-free test suite (scripted agents, scratch repositories; see
`task_runner/tests/helpers.py`, `fake_agent.py`). Do not write code
beyond signatures, record shapes and message texts. Do not edit any
existing document: list the edits under Documentation changes.

## G1 — ...`), each
holding: Problem (with the evidence below, condensed), Requirements,
Design (mechanism, state and record changes, command-line surface,
messages shown to the owner, verbatim where wording matters),
Alternatives rejected (with the reason), Failure cases and crash
points (every new external effect needs intent, effect, outcome per
A2), Scenarios, and Open questions. Then two closing sections:
`## Implementation plan` (an ordered list of independently reviewable
implementation tasks: for each, the gap it serves, the files it may
write, its scenarios, and what it depends on; no task larger than one
gap, split a gap if its parts are independent) and
`## Documentation changes` (which existing docs change, and how).

Scenarios are WHEN/THEN rows in the table format of `06-scenarios.md`,
with new ids continuing the existing series of the fitting group
(RUN, FND, AGENT, PRE, REC, BUD ...), and a test name per row in the
house style (`run: ...`). Every requirement below must be covered by
at least one scenario, and every scenario must be checkable by the
model-free test suite (scripted agents, scratch repositories; see
`task_runner/tests/helpers.py`, `fake_agent.py`). Do not write code
beyond signatures, record shapes and message texts.

## G1 — Set-aside work cannot be recovered after a replan

Evidence. Producer `close` was `blocked` (its review panel could not
produce valid answers); its work was set aside in `failed.patch`. The
runbook's advice for a blocked task is "fix the brief, `replan`,
`retry TASK [--apply-patch]`, `resume`". The owner edited the brief,
committed it on the run branch and ran `replan`. Replan reset the task
to `pending`. `retry close --apply-patch` then refused: "'close' is
pending; only a failed or blocked task is retried" (`engine.retry`).
Had the status check passed, the next check would have refused too:
the patch's recorded base tree differs from the accepted tree, because
the brief commit changed `HEAD`, although the patch touches none of
the files that commit touched and `git apply --check` succeeds. The
owner had to put the work back by hand during an interrupted attempt.

Requirements.
1. After any sequence of `replan` and `retry` that the runbook
   recommends for a failed or blocked producer, the owner can have the
   task's set-aside work put back before its next attempt, with one
   documented command, in either order of `replan` and `retry`.
2. A commit by the owner between set-aside and retry that does not
   touch the task's `writes` must not prevent applying the patch.
   A patch that no longer applies is refused with nothing changed, and
   the message says which paths conflict.
3. The author of the next attempt is told, by the runner and not by
   the owner's brief, that earlier work is present in the tree, where
   it came from (which attempt), and that it must continue from it
   rather than start over. (The owner had to write this into the brief
   by hand; an author told nothing will redo 28 minutes of work.)
4. Applying set-aside work is an external effect: intent, effect,
   outcome, and `resume` reconciles a crash at each point (A2).
   Attempt numbers continue; finished attempt directories are never
   modified; the patch file is never modified or deleted.
5. The runbook's table for blocked and failed tasks matches what the
   commands do.

Decide: whether `replan` should preserve `blocked`/`failed` status for
a producer whose definition changed, or `retry` should accept a
`pending` producer that has a set-aside patch, or a new flag belongs
on `resume`; and how the base-tree check is relaxed safely (which
tree the patch is checked against, and what "other work was accepted
since" must still refuse).

## G2 — A sound review is discarded because of a malformed sibling field

Evidence. A first-round Codex reviewer raised one legitimate blocking
finding but also listed it, by title, under `resolutions`, which is
reserved for ids of findings from earlier rounds. `findings.apply_review`
rejected the whole answer three times (`resolutions must cover exactly
this reviewer's open blocking findings, each once`); the panel gave up;
the producer was `blocked`; the finding never reached the ledger or
the author. Commit `0e98e1a` already made the prompt state the
required resolution ids and made the diagnostic specific. That reduces
the chance; it does not bound the damage.

Requirements.
1. When the tries of a reviewer are exhausted by protocol errors, no
   valid finding it produced is lost to the owner: the rejected
   answers are already in `invocation-N/`, and STATUS.md for the
   producer must point at them and summarise, per rejected answer,
   the verdict and the finding titles it contained, labelled as
   rejected and not applied.
2. Decide and justify whether a narrowly defined repair is allowed
   without a model call: an answer whose only defect is `resolutions`
   entries that reference no ledger id, in a round where the required
   set is empty, is accepted with those entries dropped and the repair
   recorded in the finding history and events. The ledger-derived
   verdict rule (the verdict must match the blocking findings that
   remain) stays as it is. If you reject this repair, say what else
   bounds the damage. Arbitrary descriptions must never be
   reinterpreted as ids (NYSE-R08), and an invalid answer must never
   change acceptance.
3. A protocol failure of the panel is distinguishable, in status and
   in `STATUS.md`, from a substantive block: the owner must see "the
   reviewers could not answer in the required form" with the concrete
   next command, not only `blocked`.
4. The rework path is unchanged for valid answers; atomicity of
   `apply_review` is kept (a rejected answer leaves the ledger
   byte-identical).

## G3 — Native Claude hook activity is empty on this host

Evidence. `doctor` prints `observed activity: none; check hook
configuration/trust and stdout.log` for every Claude profile, every
Claude invocation's `hooks/` directory stays empty, and `runner
activity` shows nothing for Claude calls, while Codex exec-stream
events are recorded. `headless-observability.md` claims nine native
Claude events were observed on 2026-09-20 in another checkout. The
projects driven here (`/workspace/sk-home/sk-labs`) have no
`.claude/settings.json` hook definitions of their own. Verified: the
hook definitions and the logger are the runner repository's own
project settings (`/workspace/.claude/settings.json` naming
`${CLAUDE_PROJECT_DIR}/.claude/hooks/log-hook.py`); the runner itself
only exports `HOOK_LOG_DIR` / `CODEX_HOOK_LOG` into the agent's
environment (`activity.py`). A target project without those
definitions therefore records nothing.

Requirements.
1. State the actual cause, from the code and the documents: under
   what conditions Claude hooks are recorded today (whose settings
   file defines them, how `HOOK_LOG_DIR` reaches the logger, what
   `ignore_user_config` changes). Mark anything you could not verify
   as an assumption and say how an implementer verifies it.
2. Activity for a Claude invocation must not depend on the target
   project shipping hook definitions. Decide between: the runner
   passing invocation-scoped hook settings to the CLI; a stdout/stream
   bridge like the Codex one (`--output-format stream-json` and its
   effect on result parsing, cost accounting and the final-answer
   schema must be addressed); or documenting the dependency and making
   `doctor` say precisely what to install. Observability stays
   observational: it never changes a gate, verdict or acceptance, and
   a logger failure never fails a call.
3. `doctor`'s message names the cause it detected, not a generic hint.
4. No credentials or full prompts enter the activity log; existing
   redaction applies.

## G4 — Interrupted and failed calls leave spend unknown

Evidence. Three reviewer calls were stopped with SIGTERM for a
planned network outage. `STATUS.md` then read "$4.41 known ..., plus 3
unpriced calls (0 tokens in, 0 out; 3 with unknown usage)". The run
budget is enforced against known spend plus reservations only, so
repeated interruptions let real spend drift above `run_budget_usd`
without the runner noticing. Codex calls are always unpriced.

Requirements.
1. The owner can see, per run and per task, how many calls have
   unknown cost, why (interrupted, provider reports none, parse
   failure), and their total wall-clock time, so that unknown spend
   can at least be bounded by eye.
2. Decide whether unknown-cost calls should count against the run
   budget by a configured estimate (for example the call's
   reservation, or a per-profile `assumed_usd_per_call`), defaulting
   to today's behaviour. If yes: where it is configured, how it is
   shown (never merged into "known"), and how `--add-budget` interacts.
   Unknown must stay labelled unknown (NYSE-R06, R07): no invented
   precision.
3. Partial usage that the CLI did print before it was stopped is used
   when it can be parsed from the invocation's saved output, and is
   labelled partial.

## G5 — check-gates re-fetches and rebuilds the world for every gate

Evidence. `check-gates` runs each gate in a disposable copy of the
clean repository. For a CMake project whose dependencies come from
FetchContent into the ignored build tree, every gate re-clones and
rebuilds them: seven gates took about four minutes, almost all of it
repeated work, and needed the network each time. During a real run the
ignored build tree persists, so this cost is specific to preflight.

Requirements.
1. A project can let its gates reuse expensive, ignored, derived
   state across the disposable copies of one `check-gates` invocation
   without weakening what preflight proves: tracked files still come
   from the clean commit, a gate that leaves tracked or unignored
   litter is still reported, and a `new` gate must still be seen to
   fail on the untouched tree.
2. Decide the mechanism: a workflow-level list of ignored paths to
   carry from copy to copy (or to seed from the owner's work tree), an
   environment variable that names a cache directory stable for the
   invocation (for example for `FETCHCONTENT_BASE_DIR`), or both.
   Address: gates run in order and may depend on the previous gate's
   build products in a real run but not in preflight today; seeding
   from the owner's build tree could hide a gate that only passes
   because of stale products, so say how that is prevented or flagged.
3. Nothing is carried by default: a workflow that does not opt in
   behaves exactly as today.
4. The carried paths must be git-ignored; validate refuses otherwise.

## Constraints on the whole design

- Python 3.11 standard library only. No new files outside
  `task_runner/`.
- Every behaviour change is opt-in or strictly safer than today;
  existing workflows and existing run records keep working (state
  schema changes need a read path for old states).
- Acceptance is never decided by an agent's report, a repaired answer
  never turns a block into a pass, and nothing here may let a task
  change files outside its `writes`.
- Keep each gap's change small and local. Prefer using the existing
  record, events and STATUS machinery to adding new subsystems
  (`nyse-execution-lessons.md`, "Review priorities", item 5).
