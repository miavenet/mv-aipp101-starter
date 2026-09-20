# Review findings on the G1 draft (Codex Astra, first round)

Line numbers refer to the draft as committed.

## Principal engineer

### F1 (blocking): A pending task cannot cancel an invalid recovery

- Location: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:229-242`
- Caused by: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:229`

A queued recovery can become invalid after replan, for example when writes are narrowed or upstream work is reopened. begin_transaction then leaves the task pending and recommends retrying clean, but this status gate rejects pending tasks without --apply-patch. Resume repeats the failed recovery, and replan preserves it. There is no supported cancellation path. The planned runbook also recommends this rejected clean-retry sequence. Define how plain retry clears a queued recovery on a pending producer, and test invalidation followed by cancellation and a successful clean attempt.

### F2 (blocking): The relaxed base check does not get past resume's branch check

- Location: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:227-245`
- Caused by: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:227`

After an owner commits an unrelated change, C1–C4 can pass and retry can queue recovery, but resume still rejects the changed branch tip before begin_transaction runs. engine.remember_tree records the previous tip, and record.reconcile checks it before processing intents; none of the three specified retry changes updates that expectation. A read-only probe confirmed this existing boundary. FAIL-09 would pass because it checks retry acceptance rather than actual recovery. Specify how a validated clean HEAD is adopted without weakening pause protections, and extend FAIL-09 through resume and the next attempt.

### F3 (blocking): Replan can destroy legacy recovery inputs before migration

- Location: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:256-258`
- Caused by: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:256`

Take an old blocked run with base and failed.patch but no set-aside.json, upgrade, then run replan before retry. The specified replan change still discards base before anything derives the new record. Retry then rejects the pending task because the file does not exist. An old queued apply_patch flag is likewise discarded unless normalized before this reset. This breaks recovery even when replan runs under the new runner, contrary to the stated limitation to runs already replanned before upgrading. Require migration and legacy-request normalization before destructive state reduction, with upgrade scenarios covering both command orders.

### F4 (blocking): Legacy migration can erase evidence of intervening acceptance

- Location: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:194-200`
- Caused by: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:197`

The branch tip recorded in state is not necessarily the tip at this task's set-aside. Under D9, task A can fail, independent task B can be accepted, and only then can the run pause. record.record_acceptance updates last_tip to B, and remember_tree records B too. Migrating A with that tip makes C3 examine an empty range, so unrelated B changes pass C2 and stale A work is permitted despite the explicit acceptance-since prohibition. Derive the original boundary from task-specific historical evidence, or refuse when it cannot be established; test migration after another producer's acceptance.

### F5 (blocking): Recovery reconciliation loses the commit-history boundary

- Location: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:202-211`
- Caused by: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:205`

The recovery intent records tree IDs but no expected HEAD commit, and reconciliation only restores and snapshot-verifies. Engine execution clears the run's pause expectation before beginning this operation. If recovery crashes and the branch moves to a different commit with the same tree, replay succeeds without detecting the branch change or enforcing C1/C3. Tree equality cannot establish commit history. Record the pre-recovery commit and require it to match before replaying any effect. Add a crash scenario where HEAD changes but its tree remains identical.

### F6 (blocking): Publishing the protected record has an unrecoverable crash window

- Location: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:424-427`
- Caused by: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:427`

run.write_decision is two durable writes: the decision file, then its integrity-manifest entry (record.py:621-624). When a later set-aside replaces an existing protected record, a crash between those writes leaves new JSON with the old hash. No intent repairs it, and Engine._execute checks integrity before returning to set_aside, so resume stops permanently rather than repeating the write. Idempotence alone does not provide a replay trigger. Specify a recoverable publication protocol with sufficient durable data to repair the file and manifest, and test interruption between their writes when replacing an existing record.

### F7 (blocking): Prompt data can suppress the required recovery notice

- Location: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:397-401`
- Caused by: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:399`

Searching the rendered prompt for the heading does not prove that the recovery section was inserted. A template without {findings} can render a brief containing that heading as quoted task material; the check then suppresses the fallback, omitting the source attempt, files, and continuation instructions. A read-only probe using the existing substitution function confirms this collision. Track whether the actual findings placeholder was substituted, or append the runner section independently of rendered data. Extend FAIL-12 with this case and assert the complete current notice.

## Spec compliance

### F1 (blocking): Migrate legacy recovery metadata before replan discards it

- Location: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:256-258`
- Caused by: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:256`

G1 R1 and the brief's compatibility constraint require recovery to survive replan for existing runs. An older run initially has base and possibly apply_patch in state, but no set-aside.json. The specified replan change preserves only recover and explicitly changes nothing else; it therefore discards the legacy fields before derive-on-first-use migration can use them. The subsequent pending-task gate also requires the missing file. This failure occurs when the new runner performs the replan, beyond the explicitly excluded case of an old runner having already replanned. Specify migration before the destructive reset, including conversion of queued apply_patch, and cover both command orders on legacy records.

### F2 (blocking): Do not derive the historical set-aside head from the latest run tip

- Location: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:194-200`
- Caused by: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:197`

The branch tip currently recorded in run state is not necessarily the tip at set-aside. D9 allows independent branches to continue after a failure, and record.record_acceptance updates last_tip for each later acceptance (task_runner/src/taskrunner/record.py:564-570). For example, A is set aside at H0 and independent B is accepted at H1 without changing A's patch paths. Migration using H1 as A's head makes C1, C2 and C3 pass: H1..HEAD is empty. Recovery then accepts precisely the intervening acceptance that Decision 2 promises to refuse, whereas today's base-tree check refuses it. Specify a historical source for the set-aside head, or conservative refusal when that provenance cannot be established, and cover this legacy migration case.

### F3 (blocking): Give the new decision-file publication an intent and reconciliation

- Location: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:424-427`
- Caused by: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:427`

The explicit 'none needed' exemption contradicts A2/B6 and the brief's requirement to specify intent, effect and outcome for every new external effect. Idempotence enables reconciliation; it does not replace an intent (task_runner/docs/05-architecture.md:330-353). Moreover, write_decision writes the file and then updates its integrity manifest separately (task_runner/src/taskrunner/record.py:621-624). A crash while replacing an existing record can leave new bytes with the old hash, and no recorded operation authorizes completing that update. Specify an intent covering both writes, retain the complete deterministic payload including timestamp and reason, and describe reconciliation between those writes for set-aside and migration.

### F4 (blocking): Make the documented clean-retry sequence executable

- Location: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:564-565`
- Caused by: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:564`

G1 R5 requires the runbook table to match command behavior. This row recommends replan followed by retry RUN TASK without --apply-patch to start clean, but lines 229-231 explicitly refuse that command for the pending task produced by replan. The same contradiction affects the clean-retry advice after a queued recovery fails its second validation: the task remains pending and the queue has no specified cancellation route. Define a supported clean-start/cancellation path, align all messages and runbook rows with it, and have RUN-19 exercise the clean alternative as well as recovery.

### F5 (blocking): Distinguish provider-session resume from the runner command

- Location: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:90-93`
- Caused by: `task_runner/docs/design/runner-gaps/G1-recover-set-aside-work.md:92`

B1's optional resume is continuation of an agent/provider session, not the runner resume command. The scope is explicit in task_runner/docs/02-concepts.md:177-181 and the capability table in task_runner/docs/05-architecture.md. D11 separately defines runner resume as the command that continues a run. Consequently, B1 does not prohibit placing a recovery option on that command, as asserted here and again at line 413. Remove this claimed binding restriction and justify the selected CLI design as a local policy choice; retaining retry as the chosen command does not require changing.
