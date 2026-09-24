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
- Shipped (G2): a blocked producer's status and STATUS.md now distinguish a panel that could
  not answer in the required form (`block_kind = "protocol"`) from one where some reviewer
  simply did not finish (`"mixed"`, per-reviewer cause) from an ordinary substantive block
  (`block_kind` absent) — so "protocol/review churn" is no longer read off a single `blocked`
  label.

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

### Tuning decision — 2026-09-20, after candidate 8 entered review

Evidence supports two separate changes; neither replaces correctness review.

- **Summary headroom (implemented on main):** increase the hard cap from 2,000 to 4,000
  characters for producer and reviewer summaries; prompt for a normal target of 1,200.
  The observed 2,062/2,167-character failures fit the new cap; the earlier 6,216-character
  response still does not. Dedicated response/finding fields hold the detailed evidence.
  Do not silently truncate. Existing input-context caps still apply.
- **Task scope:** the current contract is 1,641 lines / 123,195 bytes, spanning many
  independently reviewable concerns. The first split removed other deliverables but did
  not sufficiently bound the contract's semantic scope. Eight attempts are not eight
  independent design failures: interruption and response-protocol retries also occurred.
- **Keep other limits:** no evidence yet justifies larger per-call budgets, longer
  timeouts, more retries or weaker acceptance. Raising them could hide repeated work.
- **Rollout:** the active process retains its loaded code and schemas. Do not change its
  in-flight request or restart a valid review to adopt the new cap. Use the new runner
  at the next safe process boundary; record its version. This is not a hot reload.

Before dispatching remaining preparation work, apply the following decomposition in a
supported replan at a settled boundary. These are proposed task boundaries, not yet
changes to the frozen running workflow:

| Current broad task | Smaller independently reviewable deliverables |
| --- | --- |
| scenarios | framing/decoder cases; arbiter/reset/gap cases; book/event cases; replay/config/output cases; then cross-module scenario-index consistency |
| briefs-foundation | build/core seams; decoder fixtures and tests; decoder implementation; capture reader/encoder boundaries |
| briefs-state | independent reference model; order-book behavior and properties; arbiter behavior and properties |
| briefs-integration | handler composition; CLI/config/output; end-to-end goldens; fuzz/resource/mutation evidence |

Each slice needs explicit inputs, owned outputs, acceptance scenarios and a narrow review
question. Keep causally coupled invariants together (e.g. clear mutation and immediate
callback visibility). Separate independent modules rather than splitting by word count.
Use a final cross-module review to catch interface contradictions; smaller tasks alone
cannot prove integration correctness. Avoid duplicating scenario text across task files.
The task catalog should be split by domain if it too grows beyond a useful single pass.

If the current contract review finds further substantial defects, assess their shared
cause and revise scope before another broad rewrite. Do not discard the current draft
or automatically rebuild all contracts. Compare subsequent protocol-retry counts, time
to accepted slice, review findings and spending to assess whether tuning actually helped.

### NYSE-R07 — provider session limit consumed task attempts

2026-09-20: contracts and both reviewers accepted; candidate committed as `3f7337b`.
Scenarios then authored files but failed after three attempts. Hooks at 15:06:38 UTC
reported a Claude session limit, with reset text `11:50am (America/New_York)`.
Two immediate invocations encountered the same limit. The runner classified the task
as failed after exhausting attempts; this was not three substantive scenario failures.
Known spending is $65.88 plus six calls with unknown usage.

Evidence: `tasks/020-scenarios/` invocation outputs and activity, run STATUS.md.
Provider reset text is a reported estimate, not verified account availability. Useful
scenario edits must be recovered from the retained candidate/failed patch, not recreated.
Follow-up: recognize provider quota exhaustion separately from author failure, preserve
candidate and attempt allowance, and wait for explicit retry or a bounded reset policy.
Test: a quota response causes no immediate identical retries, no acceptance, no lost
artifact, and clearly identified provider-blocked status; unknown cost stays unknown.
Do not silently switch provider or permission profile as a quota workaround.

### Provider-switch recovery — requested Codex Sol

The user explicitly requested headless Codex Sol instead of Opus after R07. Revised
workflow definitions retain the accepted contract and its original reviewers unchanged;
only unfinished tasks select `gpt-5.6-sol`. NYSE commit `6182333` retains the two latest
scenario drafts in the frozen brief and requests focused completion rather than rewriting.
Writer profile uses the already-authorized unattended mode; reviewer profile specifies
read-only execution. Both require actual capability qualification before dispatch.
Codex dollar usage is unavailable through this adapter, so cost remains explicitly
unpriced; time/attempt limits still apply. No implicit permission or provider fallback.
Qualification/replan outcome will be appended after completion.

Provider-switch outcome: Sol writer qualified for answer/read/execute/write/resume.
Default Codex read-only mode failed on this host's bwrap namespace restriction. An
explicit `--enable use_legacy_landlock` reviewer profile (installed CLI marks it
deprecated) qualified for answer/read/resume/boundary; the sentinel write was denied.
This host-specific profile requires requalification when the CLI or environment changes.
(Verified again 2026-09-23 on codex-cli 0.155.1: without the flag `codex sandbox -- true`
fails with the bwrap message; with it the sandbox starts and denies writes. `doctor` now
checks this for free and notes the deprecation, see provider-routing.md.)

A first replan correctly refused to alter accepted contracts: the newer main runner
resolved newer default review templates. Pinning the existing worktree library explicitly
removed that unintended change. NYSE commit `58de44a`; installed replan reverted zero
commits and preserved contract `3f7337b`. The remaining tasks now use Sol. Resumed with
the main runner, including the 4,000-character summary cap and actionable retry feedback.
Follow-up regression: a provider-only replan must not silently swap library versions or
reopen accepted work; show template provenance in the change preview.

### NYSE-R08 — producer retries repeated work without actionable feedback

Sol authored and checkpointed the scenario artifacts, but final answers repeatedly put
self-found issues into `responses[].finding` instead of assigned ledger IDs. No IDs
were assigned, so the correct response list was empty. The producer loop recorded the
validation error but rebuilt the prompt without it, repeating work across three attempts
and nine calls. This is a protocol failure, not observed quota exhaustion. Current
status reported 230 minutes of aggregate agent time and no accepted scenario artifact.

Fix: producer prompts explicitly list required finding IDs (or require `responses: []`);
protocol retries receive their recorded validation diagnostic and instructions to reuse
saved work. Regression scenario proves a fabricated ID is rejected, the next invocation
receives the exact error, the saved candidate survives, and acceptance takes one attempt.
Do not reinterpret arbitrary descriptions as IDs or silently discard invalid responses.

Shipped (G2): the same shape of mistake on the *review* side — a reviewer listing a new
finding's title under `resolutions`, which is reserved for the ids of open blocking findings
— is now repaired without a model call when a round requires no resolutions and dropping the
junk entries still leaves the answer blocking, so the finding is not lost to a third identical
call and three burned tries; a real ledger id is still never reinterpreted this way and stays a
protocol error (NYSE-R08's rule). Every rejected review answer, repaired or not, is now
summarised for the owner — its claimed verdict and finding titles, with a pointer to the
invocation that held it — so a discarded answer's content is never silently gone either.

### Task-based provider selection — requested direction, not implemented

The user authorizes switching Codex to Claude when Codex hits a limit or reports reliable
near-limit evidence. Absence of rate-limit telemetry is unknown headroom, not permission
to invent a remaining percentage. Qualify the selected profile before dispatch. Current
adapter-reported token totals are not account quota; investigate their accounting semantics
before using them for scheduling or cost estimates.

Keep a future selector small and above existing adapters. Inputs: task kind, required
capabilities, explicit permission mode, context needs and configured provider preferences.
Filter to qualified profiles satisfying those controls; among them select an available
provider using observed quota/reset signals and bounded cooldowns. Persist the selection,
reason, model/profile, telemetry timestamp and fallback history in the run record.

Distinguish quota/environment failure, invalid response, substantive findings and timeout.
Quota can choose another already-authorized provider. Invalid responses get bounded
response repair; real findings return to implementation. A provider switch starts a new
session from durable artifacts, never another provider's session ID, and must not replay
uncertain external effects. Retain independent reviewer identity and read-only controls.
Do not treat switching providers as a way to discard blockers or reset spending history.

Useful future scenarios: quota response preserves candidate and attempt allowance;
near-limit telemetry selects the configured fallback at a safe boundary; stale/missing
telemetry makes no headroom claim; no qualified fallback blocks visibly; provider switch
retains findings and acceptance history; repeated format failure does not cycle providers.


## 2026-09-20 — User-requested project pause

Scenario attempt 7 progressed beyond producer protocol validation into review, but the panel blocked: missing required finding resolutions in the engineering response, and missing successful terminal event or malformed stream for spec compliance. No quota cause established. Candidate patch is retained (165661 bytes), contracts remain accepted, and no NYSE agent processes were running at pause. Do not retry until explicitly resumed. Recovery details: `nyse-pause-handoff.md`. The producer feedback fix enabled progress but did not resolve all reviewer protocol failure modes.

## Provider routing implementation — NYSE remains paused

Implemented explicit task fallback profiles and normalized mechanical/standard/high
complexity mappings above the adapters. Native quota errors are distinguished from
protocol failures. Qualification covers each actual provider/model/control combination;
selection preserves work, findings, budgets and fresh-session boundaries. Durable quota
transitions and selection history support recovery. A bounded cooldown prevents immediate
repeated calls; it is not an inferred account reset time. No reliable near-limit telemetry
source has yet been established, so predictive switching is not claimed. See
`provider-routing.md` for the configuration and deterministic verification scenarios.
This work does not retry, replan or resume the paused NYSE run.

Validation: the final complete model-free runner suite passed **308 tests** in 96.268 seconds, including 14 provider-routing scenarios. Qualification now stops further probes after quota exhaustion and does not permanently cache that temporary failure. No live provider calls were made for this change.
