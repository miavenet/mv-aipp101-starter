# Task runner: critical design and implementation-readiness review

Reviewed 2026-09-19. Scope: `task_runner/`, informed by `research/task_runner/`, its prototype, and its recorded live run. The requested hyphenated paths are underscore paths in this checkout.

**Recommendation: retain the architecture, but resolve the state, isolation, and acceptance contracts below before building the engine.** The product directory explicitly contains design artifacts only. Findings described as design gaps are consequences of those contracts, not claims about nonexistent product code. Prototype defects matter because the implementation plan proposes carrying those primitives forward.

The strongest choices are runner-owned gates, bounded rework, fresh reviewers, declarative TOML, and a durable run record. They follow the research's useful distinction between deterministic orchestration and nondeterministic agent work. There is no reason to revive the original DOT proposal or replace the CLI adapters with a homegrown agent loop.

The detailed Codex investigation and proposed adapter contract are in [Codex headless review](task-runner-codex-headless.md).

## Evidence and verification

- Read the current design, scenarios, example, and review templates; used the earlier [analysis](../research/task_runner/ANALYSIS.md), [decision](../research/task_runner/DECISION.md), and prototype as evidence. The current design supersedes the earlier flat-list proposal.
- Ran `python3 research/task_runner/prototype/tests/test_runner.py`: **13 tests passed**. These establish the prototype baseline, not DAG/panel/crash correctness.
- Checked local `codex --version`, `codex exec --help`, and `codex exec resume --help`: **codex-cli 0.155.1**. No new model calls were made.
- Ran focused offline probes in temporary Git repositories. Confirmed incomplete-stream acceptance, stale-final-file acceptance, executable-mode restoration failure, symlink-target corruption during restoration, and inclusion of preexisting edits in a path-based commit. Reproduction commands are in the companion document.

Priorities: **P1** should be settled before unattended use; **P2** should be fixed before treating the design as a stable implementation contract.

## P1-01 — Reserve the workspace for an entire producer lifecycle

**Location:** [architecture, engine loop and producer lifecycle](../task_runner/docs/05-architecture.md), especially lines 45–89; [scheduling](../task_runner/docs/02-concepts.md).

The scheduler excludes simultaneous writers and readers, but prefers a ready writer when no job is running. After producer A finishes writing, its changes remain uncommitted while its panel becomes ready. Independent producer B can therefore start before A's panel. B's baseline includes A's unaccepted changes; B can build against them, and its changes can contaminate A's eventual review. Serial processes do not provide serial transactions. SCH-07 only covers B that explicitly depends on A.

**Implement:** introduce `active_producer` ownership spanning produce → gates → checks → panel → human decision → commit or rollback. While held, schedule only that producer's verifiers and rework. Parallelism remains available within its review panel. Release ownership only after a verified clean accepted baseline is restored.

For a human pause, either hold the workspace and pause the run, or save the exact candidate tree, restore the accepted tree, and later restore/revalidate that candidate before committing. Do not run an independent producer over a pending candidate. The latter option preserves the design's branch-progress ambition but requires explicit candidate staging.

**Acceptance test:** A and B have no dependency. A writes a helper; B's gate would pass only if it can see that helper. A's panel rejects it. Assert B never sees A's candidate and each commit contains only accepted work. Repeat with A waiting for human approval.

## P1-02 — Crash recovery needs a side-effect protocol, not only atomic JSON

**Location:** [record rules](../task_runner/docs/04-run-directory.md), rules 1–3; RUN-03; [Git commit contract](../task_runner/docs/05-architecture.md).

Renaming `state.json` cannot atomically cover a subprocess, artifact write, Git commit, and state update. A crash after committing but before recording acceptance can cause duplicate work. A crash after spawning can leave an author running while a resumed runner launches another. RUN-03 promises recovery “at any point” without specifying these boundaries.

**Implement:** persist a unique operation ID and intent before every external effect. For acceptance, save `commit_pending` with expected parent, candidate tree, and task/attempt ID. Include that ID in the commit trailer. On resume, reconcile the branch tip against the intent; record the existing matching commit rather than replaying the author. Unexpected HEAD/tree changes stop with an explicit reconciliation error.

Persist an invocation ID before launching an agent. Use a supervisor/lease that can establish whether that invocation still owns a process group; do not trust a recycled PID alone. Unknown completion becomes `interrupted`, not success. Keep attempt directories monotonically numbered even when retry counters reset. Flush/fsync state and its directory where reboot durability is promised. Protect snapshot tree objects from Git garbage collection with private refs or durable artifact bundles.

**Acceptance tests:** inject termination after intent, after spawn, after final output, after commit, and before state replacement. Assert no concurrent authors, no duplicate accepted commit, and no overwritten completed attempt. Test recovery after pruning unreachable Git objects.

## P1-03 — Do not copy the prototype's Git restoration code unchanged

**Location:** [prototype `gitops.py`](../research/task_runner/prototype/taskrunner/gitops.py), `restore()` line 50, `diff()` line 46; [implementation plan](../task_runner/docs/07-implementation-plan.md), lines 9–12.

The proposed reusable primitive writes blob bytes with `open(path, "wb")`. It does not restore executable modes or symlink types. Worse, restoring an existing symlink follows it: the probe restored `link -> target` and changed the target's content from `original target` to `target`. A symlinked parent can also escape the intended restore directory. The prototype's human-readable diff is truncated at 60,000 characters and is not a binary recovery format.

**Implement:** restore tree entries using their Git type/mode, replacing links without following them and checking parent paths. Reject unsupported submodules/type transitions until implemented. Separate full recovery artifacts from capped review text: use complete binary-capable patches plus base tree IDs, or a retained candidate tree. Validate a patch's base before retry; conflicts require explicit reconciliation. Exclude ignored build outputs from rollback guarantees unless separately inventoried.

**Acceptance tests:** executable bit, symlink, symlinked parent, file/directory transition, deletion, binary file, filename with spaces/newlines, and a patch larger than the review cap. Restoring must reproduce the recorded tree without changing files outside it.

## P1-04 — Disable dirty starts until preserving owner edits is implemented

**Location:** [workflow defaults](../task_runner/docs/03-workflow-file.md), `allow_dirty`; FAIL-02; [prototype commit](../research/task_runner/prototype/taskrunner/gitops.py), line 71.

The docs say dirty starts are safe because only task-changed paths are touched. That does not protect preexisting changes in the same file. If the owner edits line 1 and the agent edits line 2, `git add` plus `git commit -- file` commits both. This was reproduced. The existing scenario tests unrelated untracked files only.

**Implement:** reject `allow_dirty = true` in v1. This aligns with the clean-start architecture and avoids silently taking ownership of user edits. Supporting it later requires a separate checkout or a baseline-aware patch/index model that preserves the original index and worktree separately.

**Acceptance test:** stage one owner change, leave another unstaged in the same file, then request agent work there. The runner must reject the start without changing either state. Also detect external HEAD/index changes while a run is paused.

## P1-05 — Codex's “reviewer only” fallback is not established by the research

**Location:** [assumed defaults](../task_runner/docs/00-decisions.md), line 37; [real-agent plan](../task_runner/docs/07-implementation-plan.md), lines 63–64 and 93; PRE-01.

Both recorded Codex reviewer streams contain only an agent message and turn completion, with no command or file-read tool event. They prove review of supplied text, not repository browsing. The author transcript fails on its first command with `bwrap` namespace creation failure. A one-line doctor prompt can succeed without exercising the failing capability.

**Implement:** distinguish text-only review, repository-reading review, and authoring. Preflight each required capability using an unpredictable file value, an actual shell read, and (for authors) a verified scratch edit. Fail once as an environment error before spending producer attempts. In this environment, use a working sandbox host for repository-capable Codex, or explicitly label a complete runner-supplied evidence bundle as text-only review. Never silently substitute an incomplete diff review for required repository inspection.

**Acceptance test:** a fake agent returns valid review JSON but its file-read command fails. Doctor must reject repository-review capability. Keep the recorded blocked author as a regression fixture. See the [headless report](task-runner-codex-headless.md) for command construction and remedies.

## P1-06 — Require complete execution and locally validate every result

**Location:** [agent fallback contract](../task_runner/docs/05-architecture.md), lines 122–125; [prototype parser](../research/task_runner/prototype/taskrunner/agents.py), `Codex.parse()` line 167 and `Agent.run()` line 83.

The prototype parser returns `ok=True` for exit 0 without `turn.completed`. It also accepts an empty stream with a stale `last-message.txt`. The fallback extracts JSON but does not itself validate against the supplied schema. New product schemas are richer than the prototype's small verdict checks; relying on provider validation leaves the command adapter and fallback path inconsistent.

**Implement:** create a fresh exclusive invocation directory; require normal exit, a successful terminal turn event, and a final object belonging to this invocation. Validate object types, enums, required keys, unknown keys, and ledger ownership locally. Implement a deliberately small validator for the runner-owned schemas if retaining stdlib-only; do not claim support for arbitrary JSON Schema. Malformed output gets a bounded protocol retry, not a fabricated reviewer finding or producer rework.

Do not interpret every failed shell command as task failure: test failures can be legitimate work. Distinguish unrecovered environment/capability failure from ordinary agent tool activity.

**Acceptance tests:** partial JSONL, missing terminal event, stale output, scalar JSON, `approved: "true"`, extra keys, contradictory verdict/findings, foreign finding IDs, duplicate resolutions, and missing required resolutions.

## P1-07 — Repair the review-round and convergence rules

**Location:** [review rounds](../task_runner/docs/05-architecture.md), lines 92–99; [finding downgrade rule](../task_runner/docs/04-run-directory.md); FND-03 to FND-06.

Three cases break the stated contract:

1. Attempt 1 fails a gate. The first panel runs on attempt 2, which is called round 2. Applying the later-round rule gives the first reviewer only a rework diff instead of a full review.
2. An old blocking finding remains unresolved, but the reviewer adds no new findings. The schema says `block` requires a blocking finding; it is unclear whether existing ledger entries count.
3. A changed function breaks an unchanged caller. A finding located at the caller is automatically downgraded because its line is outside the diff, although the regression was caused by rework.

**Implement:** track `producer_attempt` and `review_round` separately. The first successful review opportunity always receives the full candidate diff. Derive acceptance from the effective ledger after resolutions and new findings, then validate any model verdict against that result. Record finding IDs using a run-unique sequence or `(producer, reviewer, sequence)` identity.

Use changed-line location as evidence, not as proof of causality. Allow a new regression finding to identify `introduced_by_attempt` and related changed locations. Escalate ambiguous out-of-diff blockers rather than silently downgrading them. This refines D15 and should be recorded as a design amendment.

**Acceptance tests:** gate failure before first review; unresolved old blocker with no new finding; rework changes a shared API and breaks an unchanged caller; two producers using the same persona never produce ambiguous IDs.

## P1-08 — Define the acceptance graph separately from task dependencies

**Location:** [verifiers and readiness](../task_runner/docs/02-concepts.md); [workflow validation](../task_runner/docs/03-workflow-file.md).

Only reviews have an explicit readiness exception. A `check`/`human` with `verifies = "A"` and `needs = ["A"]` waits for A to be accepted, while A waits for that verifier. An even subtler cycle has verifier V need B, B need A, and V verify A. Ordinary `needs` cycle detection misses the acceptance cycle unless phase dependencies are represented.

**Implement:** expand producers into candidate-ready and accepted milestones. A verifier targets the current candidate milestone; ordinary downstream dependencies target accepted. Validate cycles in this expanded phase graph, including verifier dependencies. Reject impossible combinations with a concrete dependency trace. Avoid making a producer's acceptance depend on acceptance of its own verifier target.

**Acceptance tests:** verifying check with redundant `needs`; human verification; indirect A → B → V → A acceptance deadlock; valid standalone human after accepted A.

## P1-09 — Freeze and validate the exact source state that will be committed

**Location:** [outputs/freezing](../task_runner/docs/02-concepts.md); [Git acceptance](../task_runner/docs/05-architecture.md); FRZ-04.

Outputs are described as deliverables, but undeclared edits to other unprotected source files are not explicitly rejected. Committing only declared outputs can omit a helper used by passing gates; committing all changed paths can include unrelated work. Gates and verifying checks can also mutate source after earlier tests passed. A post-gate protection check catches protected changes only, not all changes to the tested source.

**Implement:** define separate `writes` and `outputs` if helpers are allowed; otherwise use outputs as an explicit source-write allowlist. Reject undeclared source changes. Bind every gate and review result to `(candidate_tree, verification_config_hash)`. Check source identity after each verifier and before commit; any source change invalidates previous verification. Build artifacts belong in declared ignored scratch roots. Reject control-directory paths (`.git`, `.runs`) as task outputs, and protect runner state independently because ignored files do not appear in Git snapshots.

Allow empty files/deletions through explicit output contracts; “every output exists and is nonempty” otherwise prevents valid deletion-only refactors and empty package markers.

**Acceptance tests:** agent adds undeclared helper; gate rewrites source then exits 0; check leaves a mutant behind; reviewer changes ignored state; legitimate empty/deleted output. Commit only the verified candidate.

## P1-10 — Reopen and overlapping claims must invalidate stale acceptance

**Location:** [D8/D12](../task_runner/docs/00-decisions.md); RUN-06; [replan description](../task_runner/docs/02-concepts.md).

`--reopen` resets statuses and lifts freezes, but says nothing about already committed downstream artifacts. A narrower new implementation can leave obsolete files from its previous acceptance. Similarly, a later task can claim and change A's output while another accepted task still relies on A's old content. The record then asserts acceptance for inconsistent artifact versions.

**Implement:** persist each accepted task's input tree/content hashes and output manifest. Require overlapping writers to be dependency-ordered. On reopen, compute the affected dependency and artifact-consumer closure; invalidate acceptance and specify whether obsolete artifacts are removed or regenerated. For v1, conservatively reopen the affected execution suffix and create explicit compensating commits, or refuse complex interleavings until reconciliation is implemented. Do not silently reset the branch or retain stale accepted status.

Freeze `prompt_file` content and resolved paths along with the workflow/library; resolve `root` against the original workflow location before copying it. Otherwise resume can change the brief or repository through relative-path reinterpretation.

**Acceptance tests:** reopen A after B adds an artifact; new A no longer needs it; overlapping producer changes an input of accepted B; external prompt file changes between start and resume.

## P2-11 — Make budgets and process supervision honest and enforceable

**Location:** [limits](../task_runner/docs/05-architecture.md), lines 149–162; [prototype `run_process()`](../research/task_runner/prototype/taskrunner/agents.py), line 30.

With $1 left, a panel can launch several $5 calls because spending is checked only after completion. Codex reports no dollar cost, so its usage cannot silently count as zero against a run-wide money limit. The prototype buffers stdout/stderr until completion; a runner crash loses those buffers, and long tool output consumes unbounded memory. Token usage available only at completion cannot enforce an in-call token cap.

**Implement:** reserve the allowed call budget before dispatch for providers with enforceable per-call caps; subtract reservations from available budget. Report known spend, reserved spend, and unpriced usage separately. For Codex require time/attempt limits and explicitly label monetary/token limits as unsupported or estimated unless the provider offers enforceable control. Unknown usage after interruption remains unknown.

Stream stdout/stderr to durable per-invocation files with bounded in-memory tails and incremental parsing. Stop the process group at deadline and on parent shutdown; test children holding pipes open and cancellation while a gate runs. Keep reviewer protocol retries separate from producer attempts.

**Acceptance tests:** four reviewers contend for the final $1; interrupted unpriced call; large stderr output; child ignores SIGINT; runner dies while descendants remain alive.

## P2-12 — Replace blanket “gates must fail first” and text-only no-progress detection

**Location:** PRE-02; ACC-04; [check-gates command](../task_runner/docs/05-architecture.md).

A general build/lint gate may correctly pass before a task. Conversely, an exit-1 syntax/configuration error is not evidence that a behavior test fails meaningfully; checking only exit 126/127 misses it. Two failures with identical output can still represent real progress, while changing timestamps/test order can disguise no progress.

**Implement:** classify gates as baseline invariants or task-specific acceptance checks. Record baseline pass/fail/error without claiming an existing pass makes the gate useless. Require new behavior checks to demonstrate the intended failure where feasible. Fingerprint no-progress using normalized failing test IDs, relevant source-tree hashes, and structured failure category; stop early only when both failure and relevant work are unchanged. Retain the attempt cap for all other cases.

**Acceptance tests:** already-passing regression suite; missing import returning 1; new behavior test with intended assertion failure; same failure text after a meaningful source change.

## Suggested implementation sequence

| Slice | Concrete change | Exit condition |
|---|---|---|
| 1. Contract corrections | Amend scheduler ownership, phase graph, rounds, write sets, dirty-start policy, and reopen semantics | Each P1 has an executable acceptance scenario |
| 2. Recovery primitives | Implement typed restoration, durable candidate storage, repository lock, operation intents, commit reconciliation | Crash and file-type tests pass in scratch repositories |
| 3. Minimal serial lifecycle | One producer transaction, gates, one scripted reviewer, human pause, rollback | Every accepted commit is exactly the verified candidate |
| 4. Headless adapters | Capability preflight, streamed logs, strict local result validation, invocation identity | Recorded fixtures and failure probes pass; no model required |
| 5. Findings and panels | Separate round counters, ledger-derived verdicts, bounded protocol retries, reservations | Parallel completion order does not alter results |
| 6. Replan and integration | Input/output invalidation, frozen prompt contents, explicit reconciliation | Reopened work cannot inherit stale acceptance |
| 7. Small live workflow | Run only on a capability-qualified host/profile | Real read/write/verification/rework evidence is recorded |

Move environment qualification ahead of the current stage 6: the research already shows it can invalidate the chosen agent role. Keep the prototype unchanged as evidence; port corrected primitives into the new product with the new tests.
