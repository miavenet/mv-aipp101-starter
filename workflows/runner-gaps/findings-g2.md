# Review findings still open on the G2 draft (Codex Astra, after three rounds)

Earlier findings PE-1, PE-2, SC-1, SC-2, SC-3, PE-4, SC-4 were resolved by the draft as committed; do not reopen them. Line numbers refer to the draft as committed.

### g2/PE-3 (advisory): Overflow guidance points to a record without the omitted summaries

- Location: `task_runner/docs/design/runner-gaps/G2-keep-sound-reviews.md:249-250`
- Caused by: `task_runner/docs/design/runner-gaps/G2-keep-sound-reviews.md:250`

The overflow message directs owners to events.jsonl, but the proposed helper stores summaries only in state.json. The existing review-call event contains task, status, round and error, without finding titles or the invocation path. Once more than 20 entries exist, the advertised destination cannot supply the omitted summaries. Point to the retained rejected_reviews data in state.json, or specify an event containing the omitted information. Add an overflow scenario that verifies the destination actually contains the earlier summaries and answer pointers.

### g2/PE-5 (advisory): RUN-22's expected counts contradict its fixture

- Location: `task_runner/docs/design/runner-gaps/G2-keep-sound-reviews.md:521`
- Caused by: `task_runner/docs/design/runner-gaps/G2-keep-sound-reviews.md:521`

RUN-22 supplies three entries, including a string and an object without a title. Under the extraction rules, that leaves one readable title and two unreadable entries; its expected result instead requires two titles and one unreadable entry. It also cannot fail validation on the sibling field alone when findings are malformed. Correct the fixture or expected counts, and distinguish the malformed-sibling case from the mixed-entry case so the test has an unambiguous oracle.

### g2/SC-5 (advisory): Correct RUN-22's fixture and expected counts

- Location: `task_runner/docs/design/runner-gaps/G2-keep-sound-reviews.md:521`
- Caused by: `task_runner/docs/design/runner-gaps/G2-keep-sound-reviews.md:521`

RUN-22 specifies three findings, one a string and another lacking a title. Under the stated extraction rule, that yields one readable title and two unreadable entries, not two titles and one unreadable entry. A read-only validator probe also confirmed that this fixture fails on both findings entries as well as resolutions, contradicting 'the sibling field alone'. Correct the counts and separate the sibling-only fixture from the mixed-readable-findings fixture so the scenario tests the intended requirements unambiguously.

### g2/PE-6 (blocking): Persisted jobs from existing runs lack the required invocation key

- Location: `task_runner/docs/design/runner-gaps/G2-keep-sound-reviews.md:207-224`
- Caused by: `task_runner/docs/design/runner-gaps/G2-keep-sound-reviews.md:212`

The new invocation field is populated only when reader_batch dispatches a call, but rejection now requires job["invocation"]. An existing run stopped at panel:outcomes-recorded has persisted raw_outcome without that field: panels.py:101-105 replays it through collect_reader before another dispatch. If that answer is malformed, the specified rejection transition has no invocation key, so it cannot complete its summary and outcome correction; a direct implementation raises KeyError on resume. This is a design-path defect established from the existing persistence and replay code, not an implementation test result. Define a compatibility path that recovers and persists the correct invocation identity for existing jobs before replay. Add a scenario resuming a pre-change checkpoint with a rejected raw_outcome, asserting the correct pointer, corrected outcome, unchanged ledger and no repeated completed call.

### g2/SC-6 (blocking): Provide an old-state read path for the new invocation field

- Location: `task_runner/docs/design/runner-gaps/G2-keep-sound-reviews.md:207-224`
- Caused by: `task_runner/docs/design/runner-gaps/G2-keep-sound-reviews.md:212`

The brief requires existing run records to keep working and schema changes to provide an old-state read path (workflows/runner-gaps/spec-brief.md:241-243). The new invocation field is populated only when reader_batch dispatches a call, but rejection now requires it for the summary key and outcome correction. Consider upgrading a run saved at panel:outcomes-recorded: existing code persists raw_outcome without an invocation field (task_runner/src/taskrunner/panels.py:339-348), and resume collects that outcome before dispatching anything (lines 101-105). A rejected answer therefore reaches the new transition without its required invocation pointer. The design's old-state handling covers block_kind only. Specify how existing pending outcomes recover their invocation identity before collection, and add an upgrade/resume scenario verifying the summary, pointer, corrected outcome and preserved retry count. This is a missing compatibility design, not an observed failure of an implementation.
