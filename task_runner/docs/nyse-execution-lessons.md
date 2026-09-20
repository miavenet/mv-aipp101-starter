# NYSE execution: resilience engineering log

Owner: coordinating agent. Started 2026-09-20. This is an ongoing incident and
improvement record, not a claim that NYSE preparation or implementation is complete.
Update at failures, recoveries, accepted milestones and material changes of approach.
Preserve earlier observations; append corrections when later evidence changes them.

## Evidence and recording convention

Run: `nyse-prepare/20260920T120750Z-1bc86f72`, branch `nyse-handler-design`.
Local record root: `/tmp/nyse-handler-preparation/.runs/nyse-prepare/20260920T120750Z-1bc86f72`.
Paths below are relative to that root unless stated otherwise. These records are local,
not committed archives; retain relevant evidence before removing the worktree.
Never copy credentials, full prompts or unrelated hook payloads into this log.

For each new incident record: symptom and impact; evidence; established cause versus
hypothesis; recovery performed; validation; remaining risk and a concrete regression
scenario. Separate agent-reported completion, persisted artifacts and runner acceptance.
Use stable incident IDs. Improvements listed here are proposals unless marked shipped.

## Incidents and lessons

### NYSE-R01 — oversized preparation task exhausted its execution window

- Observation: the original contracts task combined API decisions, scenario drafting
  and reconciliation of existing documents. It produced useful drafts but exceeded its
  20-minute invocation limit before delivering the whole task.
- Recovery: retained drafts and failed candidate evidence, set aside interrupted work
  through runner controls, split preparation into eight producer tasks with separate
  reviews, and replanned. Commit `8c5c070` on the NYSE branch records the split.
- Lesson: bounded tasks and incremental files reduce restart loss; model context is
  not a recovery artifact. Splitting alone has not yet demonstrated adequate throughput:
  the first contracts task still required multiple attempts.
- Follow-up: inspect time to first durable artifact and repeated research before adjusting
  task size. Given an interrupted author with a saved draft, when retry begins, then
  the draft is recoverable and the brief identifies unfinished requirements rather than
  requiring a complete rewrite. Do not claim this behavior is automatic today.

### NYSE-R02 — valid work accompanied by oversized structured summaries

- Observation: contract author responses exceeded the 2,000-character summary contract,
  causing protocol retries despite useful files on disk. Native successful completion
  is distinct from runner-valid completion.
- Evidence: `tasks/010-contracts/` invocation outcomes and retained responses; the frozen
  response schema defines the bound. Keep verbose findings in artifacts, with references
  in the short final result.
- Status: size limits remain enforced; eliminating expensive repeated author work is
  still open. Review whether a bounded response-repair path can reuse immutable candidate
  evidence without allowing an invalid answer to change acceptance or replay side effects.
- Regression scenario: given a saved candidate and an oversized answer, when response
  repair runs, then no implementation commands repeat, limits remain enforced and the
  repaired answer is traceable to the same candidate. This is a proposed scenario.

### NYSE-R03 — rework blockers used prose where exact references were required

- Observation: at 13:24:38 and 13:29:13 UTC, principal-engineer round 2 returned
  `verdict disagrees with ledger: expected pass`; all three permitted calls eventually
  exhausted. The reported original findings were fixed, but new regressions were raised.
- Cause: references such as `path:331 with :342-351` and `path:624-638 (against ...)`
  did not match the changed-line parser; `caused_by` also contained prose. Rework rules
  therefore treated the new findings as advisory, contradicting the reported block.
  Retries received the same prompt without the validation error.
- Evidence: `events.jsonl`; `tasks/011-contracts.review.principal-engineer/round-2/`
  invocation responses, especially `invocation-2/last-message.txt`.
- Shipped fix: main `2b62b2a` gives retries the validation diagnostic, explains exact
  reference syntax and saves per-invocation prompts. Findings and acceptance rules were
  not relaxed. Atomic rejection still leaves the ledger unchanged.
- Validation: 292 runner tests passed, including malformed-reference rejection followed
  by corrected-reference blocking, and an integration test showing feedback reaches the
  retry while a real blocker still forces author rework.
- Recovery: supported `retry --apply-patch`, then resume using the patched main runner.
  The exhausted panel was not manually marked accepted. Live effectiveness awaits the
  next comparable protocol failure; unit/integration success is not field proof.

### NYSE-R04 — interruption and internet-disconnection pause

- Observation: user explicitly requested a pause. Coordinator sent SIGTERM to the runner;
  it reported child processes stopped. Process inspection confirmed parent and child gone;
  the contract draft remained on disk.
- Recovery: resumed only on user instruction. At 14:12 UTC, hooks recorded a fresh author
  session reading the retained tree; the interrupted operation was reconciled in events.
- Evidence: `events.jsonl`, interrupted `op-0030`, resumed `op-0031`, and invocation hooks.
- Limit: process interruption was exercised; this was not a power-loss, host-loss or actual
  network-partition test. Progress held only in model context may still be lost.
- Follow-up scenario: given interruption after artifact persistence but before structured
  output, when resume reconciles, then no orphan agent remains, edits survive and no
  acceptance or external side effect is duplicated.

### NYSE-R05 — activity is observable, but milestone durability was incomplete

- Observation: native hooks show reads/edits/session lifecycle, but cannot establish what
  requirements are complete or preserve an unwritten result.
- Shipped: checkpoint skill `fbd763d`; activity integration `9d4ced4`. Explicit artifact
  copies, atomic publication, integrity checks and agent-reported milestone events.
  Main installation does not establish that an already-running frozen workflow uses it.
- Validation: seven helper tests cover interrupted publication, corrupt-generation
  fallback, worktree loss, invalid paths and hook-write failure. Runner integration
  verifies that regenerated record indexes do not overwrite artifact snapshots.
- Defect caught during development: storing an artifact as `index.json` beneath the run
  conflicted with generated indexes. Flat numbered `.blob` snapshots remove that collision.
- Retained example: coordinator checkpoint under
  `/workspace/sk-home/.codex/agent-checkpoints/nyse-prepare-1bc86f72/contracts-coordinator`.
  It preserves an earlier draft, not current acceptance.
- Follow-up: explicitly qualify milestone writing for future writers and a coordinator
  persistence path for read-only reviewers. Never widen reviewer permissions implicitly.

### NYSE-R06 — status, cost and retry scope can obscure useful progress

- Observation: a running task may be producing artifacts, repairing response format or
  repeating a review. A single status label does not distinguish them. Failed panels
  leave earlier findings open until a valid panel applies all resolutions atomically.
- Evidence: R03's reviewers reported fixes while the official ledger still showed the
  previous blockers. Known spend also excludes calls whose usage is unavailable.
- Current handling: report both ledger status and latest agent evidence, label unknown
  usage, and avoid treating draft growth or hook activity as accepted progress.
- Follow-up: expose phase, invocation/retry reason, last artifact/checkpoint age and last
  accepted milestone. Given a protocol retry, status should identify that reason instead
  of implying a new implementation attempt. Preserve unknown cost as unknown.

## Review priorities after this exercise

1. Preserve useful candidate work while repairing response-only failures, without replaying
   effects or allowing model-authored acceptance.
2. Make retries actionable and bounded; assess whether live retry diagnostics prevent R03
   recurrence before adding further machinery.
3. Exercise checkpoint and orphan recovery at real transaction boundaries; distinguish
   process-crash guarantees from filesystem and host-loss guarantees.
4. Make status show productive work versus protocol/review churn, including unknown usage.
5. Reassess task granularity and review scope from measured outcomes. Prefer small fixes
   and existing runner records over a second workflow framework or scoring ledger.

## Latest observed milestone

2026-09-20 14:27 UTC: candidate 7 pinned, both contract command gates passed, and two
review calls started (`op-0037`, `op-0038`). This is review entry, not contract acceptance.

### Update — 2026-09-20 14:43 UTC

The fresh panel produced actionable blocking findings: PE-10 clearing visibility,
PE-11 initial gap timer, PE-12 multiple EOF holes, and SC-8 null-padded ticker fields.
The author subsequently reported fixing all four; review acceptance is still pending.
This shows progress beyond the exhausted panel, but does not yet demonstrate that the
new retry diagnostic corrected malformed references in a live rework review.

R02 recurred inside the native StructuredOutput tool: hooks at 14:43:12 and 14:43:30
record rejected summaries of 2,167 and 2,062 characters against the 2,000-character
limit. These are tool-level repair attempts within the invocation, not evidence of
another runner-level retry. A comfortable summary target below the hard limit may be
more useful than telling agents merely to satisfy the maximum. Keep detailed responses
in their dedicated fields and artifacts. This remains a proposed prompt improvement.
Known spend at observation: $51.64 / $100 plus three calls with unknown usage; 116
minutes of recorded agent time. No preparation producer accepted yet.
