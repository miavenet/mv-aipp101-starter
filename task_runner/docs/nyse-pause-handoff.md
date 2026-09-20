# NYSE effort paused — 2026-09-20

User requested pausing at the next milestone to switch projects. Execution was already stopped at the scenario review boundary. Do not retry, resume, or start NYSE agents until the user explicitly resumes this effort.

## Preserved state

- Worktree: `/tmp/nyse-handler-preparation`, branch `nyse-handler-design`; clean at pause.
- Run: `.runs/nyse-prepare/20260920T120750Z-1bc86f72`.
- Contracts accepted at `3f7337b`; preserve acceptance.
- Scenarios attempt 7 reached review but remains unaccepted and blocked. Principal-engineer response omitted required resolutions; spec-compliance lacked a successful terminal event or had a malformed stream. The latter cause needs investigation; quota exhaustion is not established.
- Candidate retained as `tasks/020-scenarios/failed.patch` (165661 bytes) and a pinned task-runner ref. Review records, native activity, and invocation checkpoints remain in the run directory.
- No NYSE C++ implementation has started. Reconciliation, task catalog, implementation briefs, and executable handoff remain pending.
- No live runner or headless writer/reviewer processes found at pause.
- Recorded spend: $65.88 known, plus 22 unpriced calls. This is not account quota utilization.

## Resume procedure

Inspect runner status, candidate patch, last review records, and checkpoint integrity first. Investigate the review protocol failures and split remaining broad tasks where helpful before spending another attempt. Preserve accepted contracts and useful scenario drafts. Use supported retry with `--apply-patch` and supported replan rather than editing run state. Resume only after explicit user instruction.

Execution uses qualified Sol profiles; the user authorized switching to qualified headless Claude on confirmed Codex limits or reliable near-limit evidence. Unknown quota is not proof of exhaustion. Writers may use unattended mode; reviewers retain explicit read-only controls.

See `nyse-execution-lessons.md` for resilience findings and pending provider-selection design. Main contains runner fixes through `ab8e165`. Uncommitted status-line changes are separate from this NYSE pause.
