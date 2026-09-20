# G2 — A sound review is discarded because of a malformed sibling field

One of the five resilience gaps found on 2026-09-20 while the runner drove two real workflows
(`spsc-queue`, `spsc-queue-gaps`) with Claude authors and Codex reviewers. The brief is
[`workflows/runner-gaps/spec-brief.md`](../../../../workflows/runner-gaps/spec-brief.md). This
document designs G2 only; it names the neighbouring gaps where they touch the same code, and
designs nothing for them.

Binding context: decisions D1–D16 and amendments A1–A12, B1–B12 in
[00-decisions.md](../../00-decisions.md). The rules this gap sits closest to are A6 (a result needs
the runner's own validation; invalid answers get bounded protocol retries and never findings or
rework), A7 (verdicts are derived from the ledger), B1 (`resolutions` cover open blocking findings
only), B7 (a panel that cannot answer leaves its producer `blocked`), and B8 (review rounds have
invocation directories).

## Problem

A first-round Codex reviewer raised one legitimate blocking finding. It also listed that same
finding, **by title**, under `resolutions`, which is reserved for the ids of findings from earlier
rounds. In round 1 a reviewer has no open blocking findings, so the only valid value of
`resolutions` is `[]`.

`findings.apply_review` rejected the whole answer:

> resolutions must cover exactly this reviewer's open blocking findings, each once: required none,
> so resolutions must be []; supplied 'the queue drops the last element'. A new finding belongs in
> findings only, never in resolutions

The same answer came back three times (one call plus the two protocol retries of A6). The panel
gave up, `panels.panel` ended the producer as `blocked` with "review panel could not produce valid
answers: …", and the producer's work was set aside. Consequences:

1. **The finding was lost.** It never reached `findings.json`, never reached the author, and never
   reached the owner's `STATUS.md`. The rejected answers exist on disk — under
   `tasks/NNN-<reviewer>/round-1/invocation-{1,2,3}/last-message.txt` — but nothing in the record
   points at them, and nothing says what they contained. An owner reading `STATUS.md` sees only a
   one-line parser diagnostic.
2. **The block reads like a judgement.** `blocked` is also the status for "attempts ran out with
   blocking findings open" and for "the agent answered blocked". The owner cannot tell from the
   status, or from the run's `STATUS.md` table, that nobody judged the work at all.
3. **The cost is a whole producer.** The candidate was set aside, the panel's three calls were
   spent, and the next step for the owner is `retry`, which re-runs the author.

Commit `0e98e1a` already made the review prompt state the required resolution ids explicitly and
made the diagnostic specific, and the protocol retry now carries that diagnostic back to the
reviewer (`panels.reader_batch`, "Previous response was rejected"). That reduces the chance of the
malformed field. It does not bound the damage when it happens anyway: a sound finding is still
discarded in silence. This is the same family as NYSE-R06 (a single status label cannot distinguish
productive work from protocol churn) and NYSE-R08 (a malformed reference field burned three
attempts and nine calls), and it is "Review priorities" item 1: preserve useful work while
repairing response-only failures, without allowing model-authored acceptance.

An existing test pins today's behaviour for exactly this input:
`tests/test_findings.py::test_a_new_finding_listed_as_a_resolution_is_rejected_with_the_required_ids`.
Requirement 2 below changes what that input does, so that test must be rewritten by the
implementation, not deleted — see [Implementation plan](#implementation-plan).

## Requirements

Numbered as in the brief.

1. **No valid finding is lost to the owner.** When a reviewer's tries are exhausted by protocol
   errors, the producer's `STATUS.md` points at the rejected answers in `invocation-N/` and
   summarises, per rejected answer, the verdict and the finding titles it contained, labelled as
   rejected and not applied.
2. **Decide and justify a narrowly defined repair without a model call.** Candidate: an answer
   whose only defect is `resolutions` entries that reference no ledger id, in a round where the
   required set is empty, is accepted with those entries dropped and the repair recorded in the
   finding history and in events. The ledger-derived verdict rule is unchanged. Arbitrary
   descriptions are never reinterpreted as ids (NYSE-R08), and an invalid answer never changes
   acceptance. If the repair is rejected, say what else bounds the damage.
3. **A protocol failure of the panel is distinguishable from a substantive block**, in status and
   in `STATUS.md`: the owner sees "the reviewers could not answer in the required form" with the
   concrete next command, not only `blocked`.
4. **Valid answers are unaffected**, and `apply_review` stays atomic: a rejected answer leaves the
   ledger byte-identical.

## Design

### Summary of the mechanism

Three small, independent changes, all inside existing machinery (the ledger, the panel coordinator,
the state and `STATUS.md`). No new command, no new flag, no new file in the run directory, and no
new external effect.

| # | Change | Where | Serves |
|---|---|---|---|
| 1 | One narrowly defined repair of `resolutions`, allowed only when it delivers a **block** | `findings.apply_review` | R2 |
| 2 | Every rejected review answer — refused at collection or at final application — goes through one shared rejection transition that summarises it into the producer's state, per field and defensively, so one malformed sibling cannot hide a readable verdict or title, and renders it in `STATUS.md` with a path to its invocation directory. Nothing is capped | `panels.reject_answer`, `record.render_task_status` | R1 |
| 3 | A producer blocked by a panel failure carries `block_kind`, **classified from the broken reviewers' actual statuses** (`protocol`, `mixed`, or absent), which changes how the run's and the task's `STATUS.md` read and which command "Next" prints | `engine.end`, `panels.panel`, `record.render_run_status` / `render_task_status` | R3 |

### 1. The one repair (R2) — adopted, narrowed so it can only deliver a block

**Decision: the repair is adopted**, with one narrowing beyond the brief's wording, stated and
justified below.

`findings.apply_review` repairs an answer when **all** of these hold:

1. the answer is valid in shape (`validate.check_shape(answer, validate.REVIEW)` returns no error);
2. the reviewer has **no open blocking finding** in this producer's ledger, so the required
   resolution set is empty and the only correct value of `resolutions` is `[]`;
3. `resolutions` is not empty;
4. **every** entry's `finding` string is not the id of **any** finding in this producer's ledger —
   not this reviewer's, not another reviewer's, not a closed one. Ids are unique in the run (A7),
   so this is an exact string test against `{f["id"] for f in ledger["findings"]}`, never a
   similarity test;
5. applying the answer with `resolutions` replaced by `[]` derives the verdict **`block`** (and,
   by the unchanged rule of A7, the answer's own `verdict` field says `block` too).

Then `resolutions` is replaced by `[]`, the dropped entries are recorded, and the rest of the
answer — the findings, the verdict check, the ledger write — proceeds exactly as today. In every
other case the answer is rejected with today's diagnostic, unchanged, and the bounded protocol
retry carries that diagnostic back to the reviewer as it does now.

Why each condition:

- (2) and (3) make the correct answer **provable without judgement**: the round required nothing,
  so `[]` is the only valid value and dropping is not a guess about what the reviewer meant.
- (4) is the NYSE-R08 line. If an entry names a real id, the reviewer is confused about a real
  finding and the runner must not decide which way; that stays a protocol error. This also keeps
  FND-16 (resolving another reviewer's finding is a protocol error) exactly as it is.
- (5) is the narrowing. Requirement 2's wording would also accept a **passing** answer with junk
  resolutions. The whole-design constraint is that every behaviour change is opt-in or strictly
  safer than today, and accepting a pass that today is rejected is neither: it moves a producer
  towards acceptance on the strength of an answer the reviewer demonstrably wrote carelessly.
  Restricting the repair to answers that block means the repair can only ever do what the evidence
  case needed — deliver a blocking finding to the ledger and to the author. It can never turn a
  block into a pass, and it can never create one.

Consequences of (5) that must be stated plainly:

- A **passing** answer with junk resolutions is still a protocol error, still exhausts the tries,
  and still blocks the producer. The damage is bounded by change 2: the owner sees in `STATUS.md`
  that the reviewer claimed `pass` and listed no blocking finding.
- A reviewer marked `advisory` derives `pass` for every answer it can write, so its answers are
  never repaired. Its findings never block, and change 2 still shows the owner their titles.

What does not change: the ledger-derived verdict rule (A7); which new blocking findings may be
raised in a later round (`location` / `caused_by` against the rework diff); advisory handling;
`respond`; the rework prompt; `retry`; acceptance. The repair adds findings to the ledger and
removes nothing from it.

#### Signatures and data

```python
# findings.py
REPAIR_DROPPED_RESOLUTIONS = "dropped_resolutions"

def apply_review(ledger, reviewer, answer, candidate, changes):
    """Returns (ledger, verdict, repair). `repair` is None, or the record of the one repair
    this function is allowed to make. Atomic as before: on ProtocolError the caller's ledger is
    untouched, because every mutation happens on a deep copy that is then discarded."""
```

The third element is the only signature change. Its callers are `panels.collect_reader` (the
speculative apply that decides whether a call is a protocol error) and `panels.panel` (the
coordinator's real apply).

**Which ledger decides eligibility, and what happens when the two calls disagree.**
`apply_review` is pure, but its two callers do not pass the same ledger: `collect_reader` judges an
answer against the ledger as it stands when that call returns (`self.ledger(tid)`, unchanged for
the whole panel), while the coordinator applies the panel's reviewers **sequentially in workflow
order**, so each reviewer is applied to a ledger that already holds the findings of the reviewers
before it. Condition 4 reads the whole ledger, so eligibility really can change between the two
points. The case: PE raises `implement/PE-1`; SC, running beside it and unable to see PE's answer,
blocks and supplies `implement/PE-1` as a resolution. At collection SC satisfies condition 4
(`implement/PE-1` does not exist yet) and would be repaired; at final application it names a real
id and must be refused.

The design settles this rather than assuming it away:

- **The final application is the authoritative decision point.** Eligibility is judged against the
  ledger as it stands at that reviewer's turn in workflow order. That is deterministic for a given
  set of answers (SCH-05 already requires results to be applied in workflow order), so a resume
  reaches the same verdict as the run that was interrupted.
- **`collect_reader`'s apply stays provisional.** It exists to decide, while the panel is still
  running, whether the call was a protocol error and should be retried. It may accept an answer the
  final pass then refuses.
- **The coordinator's apply pass must therefore handle `ProtocolError`, and route it through the
  **same** rejection transition as any other rejected answer.** On `ProtocolError` for job *J*,
  the partly built ledger — a local variable that has not been written to the state — is
  discarded, and *J* goes through `reject_answer` (below). The other jobs' results are untouched
  and are simply re-applied to a fresh copy of `st["ledger"]` on the next pass, so no finding is
  applied twice and no id is consumed twice.

Without this, the mechanical three-value unpacking would let a `ProtocolError` escape the engine
uncaught, and `resume` would meet it again on every attempt. The wrapper is required for T1 to be
correct, not an optimisation.

#### One rejection transition, wherever the answer was rejected

An answer can be rejected in two places — at collection, by the adapter or by the speculative
apply, and at final application — and **requirement 1 applies to both**. Clearing `J["result"]`
and re-dispatching is not enough, for three reasons found by tracing the existing code:

1. `note_rejected_answer` hangs off `collect_reader`. An answer that collection accepted and final
   application refused is never seen by it, so a reviewer that sends the same colliding answer
   three times would block its producer with **no** summary at all and with every invocation still
   recorded `ok` — exactly the loss this gap is about, reintroduced by the fix for PE-1.
2. The dispatch loop's exhaustion guard fires **before** any collection happens for a job whose
   `result` is `None` with `tries >= 3`, and overwrites the cause with the fixed text
   `interrupted calls exhausted protocol retries`. For a call that completed and was refused, that
   text is simply false.
3. The job does not carry the invocation directory at all: `reader_batch` keeps it in a local
   (`item["inv"]`), so neither path could name the answer's directory.

So the design adds **one transition that every rejection goes through**, and `reader_batch` records
the directory it created on the job:

```python
# panels.py — in reader_batch, beside the existing intent that already carries invocation_dir
job['invocation'] = os.path.relpath(inv, self.run.path)

def reject_answer(self, job, producer_id, *, status, error, structured):
    """The one place an answer becomes a rejected answer, whether it was refused at collection
    or at final application. Summarises it, corrects its invocation's outcome.json, keeps the
    diagnostic for the next prompt, and decides between another try and a final result."""
```

In order, and for every rejection:

1. `note_rejected_answer(job, producer_id, status=status, error=error, structured=structured)` —
   the summary and the pointer, extracted per field as described in section 2, and the correction
   of that invocation's `outcome.json`. Idempotent by `job["invocation"]`.
2. `job["protocol_error"] = error`, so the next try carries the **actual** diagnostic in its
   prompt, as it does today.
3. `job["result"] = None` when `status` is a protocol error and `job["tries"] < 3` — another try;
   otherwise `job["result"] = {"status": status, "error": error}`, the real diagnostic, set here
   rather than left to the exhaustion guard.
4. One `review-answer-rejected` event (`task`, `producer`, `round`, `try`, `status`, `error`,
   `invocation`). `collect_reader`'s existing `review-call` event is unchanged.
5. `self.save()` before control returns to the dispatch loop, so the summary and the cleared result
   become durable together.

The exhaustion guard keeps its place for the case it was written for — a job whose tries were spent
without a completed call — but takes the diagnostic it has:
`job.get('protocol_error') or 'interrupted calls exhausted protocol retries'`. A genuinely
interrupted call has no answer to summarise, so it contributes a pointer-free entry as today.

**Crash replay.** If the runner dies after the coordinator refused *J* and before the `save`, the
panel step re-runs from the last saved jobs: the apply pass refuses *J* again, `note_rejected_answer`
is idempotent by invocation path, the accepted jobs are re-applied once to a fresh copy of
`st["ledger"]`, and the ledger written at the end is the same one. No summary is doubled and none is
lost.

The repair record, as stored in `verdict.json` and in the event:

```json
{"kind": "dropped_resolutions",
 "dropped": [{"finding": "the queue drops the last element when head wraps",
              "status": "unresolved"}],
 "why": "the round required no resolutions and no entry named a finding in the ledger"}
```

`dropped[].finding` is agent text: it is redacted with `proc.redact` and cut to 200 characters with
a trailing `…` before it is stored. Every dropped entry is recorded: the count is bounded by the
answer itself, and the record of what the runner threw away is the point of the field.

In the ledger, **each finding raised by the repaired answer** gains a history event after its
`raised` event, so `findings.json` alone tells the whole story (FND-10):

```json
{"event": "repair", "round": 1, "kind": "dropped_resolutions",
 "dropped": ["the queue drops the last element when head wraps"]}
```

And one event in `events.jsonl`, emitted by the coordinator at the moment the repaired ledger is
written:

```json
{"event": "review-repair", "task": "implement.review.principal-engineer",
 "producer": "implement", "round": 1, "kind": "dropped_resolutions", "dropped": 1}
```

### 2. Rejected answers are summarised where the owner looks (R1)

Every rejected answer reaches the shared `reject_answer` transition described above — the ones the
adapter rejects, the ones `collect_reader` rejects by running `apply_review` speculatively, and the
ones only the coordinator's final application rejects. That transition calls one new helper:

```python
# panels.py
def note_rejected_answer(self, job, producer_id, *, status, error, structured):
    """Summarise one rejected review answer into the producer's state, and correct the
    invocation's outcome.json. Called only from reject_answer, so collection and final
    application record a rejection identically. Observational: nothing in the engine reads it
    back to decide."""
```

It appends to `state["tasks"][<producer>]["rejected_reviews"]`:

```json
{"reviewer": "implement.review.principal-engineer",
 "round": 1,
 "try": 2,
 "invocation": "tasks/011-implement.review.principal-engineer/round-1/invocation-2",
 "at": "2026-09-20T14:43:12Z",
 "verdict": "block",
 "findings": [{"severity": "blocking",
               "title": "the queue drops the last element when head wraps"}],
 "error": "resolutions must cover exactly this reviewer's open blocking findings, each once: …"}
```

**Extraction is per field and defensive: it never asks whether the answer as a whole is valid.**
That is the point of the gap. `validate.REVIEW` rejects an answer for one bad sibling field, and
the adapters keep the parsed object in `outcome.structured` regardless; so an answer with
`"resolutions": null`, a readable `verdict` and perfectly good `findings` is rejected by the
validator while its findings are entirely readable. Summarising only "shape-valid" answers would
reproduce the very failure G2 exists to fix, on the owner's visibility surface. The rules are:

- **`verdict`**: taken only if `outcome.structured` is an object and its `verdict` is exactly
  `"pass"` or `"block"`. Anything else stores `null`, which renders as "no readable verdict".
- **`findings`**: if `structured["findings"]` is a list, every item that is an object with a string
  `title` contributes one entry. Its `severity` is carried only if it is exactly `"blocking"` or
  `"advisory"`; otherwise `"severity": "unknown"`. Items that are not objects, or have no string
  `title`, are not guessed at: they are counted in `"unreadable_findings": N`, which renders as
  "N further entries could not be read".
- **No other field is read**, and nothing extracted here is ever passed to the ledger, to a verdict
  or to acceptance. This is the `branch_disposition` rule again: observed, never decided.
- **`title` and `error` are agent text**: control characters are replaced by spaces, then
  `proc.redact` is applied, then they are cut to 120 and 400 characters with a trailing `…`. The
  redaction happens **before** the text enters `state.json`, so no token-shaped string is ever
  stored (RUN-10's rule, on a new surface).
- **Every readable finding of every rejected answer is kept, and every rejected answer is kept.**
  There is no cap on either. Requirement 1 is a per-rejected-answer summary of the titles it
  contained; a cap would silently omit exactly the evidence the owner is being sent to read, and
  there is nowhere to send them for the remainder — the existing `review-call` event carries
  `task`, `status`, `round` and `error` only, with no titles and no invocation path. The volume is
  bounded by the protocol itself: at most three tries per reviewer per round, rounds bounded by
  `max_attempts`, so a seven-member panel over three attempts has a worst case of 63 entries. Each
  entry is a handful of short lines.
- The entry is keyed by its `invocation` path: appending is idempotent, so a crash-replay of a
  panel batch cannot double it.

The producer's `STATUS.md` renders them. `record.render_task_status` gains the run name so it can
print a usable command:

```python
def render_task_status(task_id, t, tdir, run_name=""):
```

Rendered section (verbatim wording; the entries are examples):

```
## Rejected review answers

Not applied. Nothing below is in the ledger and none of it changed acceptance. Read it before you
retry: the concerns in it may be real.

- **implement.review.principal-engineer**, round 1, try 2 — claimed verdict `block`, 1 finding:
  - blocking: the queue drops the last element when head wraps
  Rejected because: resolutions must cover exactly this reviewer's open blocking findings, each once: required none, so resolutions must be []; supplied 'the queue drops the last element'. A new finding belongs in findings only, never in resolutions
  Answer: `tasks/011-implement.review.principal-engineer/round-1/invocation-2/last-message.txt`
- **implement.review.spec-compliance**, round 1, try 3 — no readable answer:
  Rejected because: Claude did not return a terminal result
  Answer: `tasks/012-implement.review.spec-compliance/round-1/invocation-3/last-message.txt`
```

Every entry is rendered, oldest first. An entry whose answer had a readable verdict but no
readable finding reads `— claimed verdict \`pass\`, no findings`; one whose verdict could not be
read reads `— no readable verdict`; unreadable finding entries are counted on their own line as
`- 2 further entries could not be read`. Nothing is dropped and no reader is sent elsewhere for
the remainder.

A repaired answer is shown too, so the repair is never silent:

```
## Repaired review answers

- **implement.review.principal-engineer**, round 1: 1 meaningless `resolutions` entry was dropped
  and the answer was applied. The entries named no finding in the ledger, and the round required
  none. See findings.json.
```

This section is derived from the `repair` history events already in `t["ledger"]`, so it needs no
new state.

**One correction to the record, found while designing this.** `panels.reader_batch` writes
`invocation-N/outcome.json` from the adapter's result, which at that moment is `ok`;
`collect_reader` then rejects the answer against the ledger and never rewrites the file. The record
therefore says `"status": "ok"` for an invocation whose answer was thrown away — precisely the file
an owner opens after following the new pointer. `note_rejected_answer` rewrites that
`outcome.json` with the final status and error before the round directory is closed. `outcome.json`
is not a decision file, so no integrity-manifest entry changes; the rewrite is idempotent, so a
crash replay repeats it with the same bytes.

### 3. A protocol failure is not a judgement (R3)

`engine.end` gains an optional keyword:

```python
def end(self, task, status, reason, block_kind=None):
    """block_kind classifies an unsuccessful end for the reader: "protocol" when every broken
    reviewer failed at the protocol level, "mixed" when only some did, None otherwise. It is
    carried in st["final"] and applied by set_aside with the status."""
```

**The classification is derived from the outcomes, never assumed from the call site.** The
exhausted-panel call in `panels.panel` is reached by *any* non-ok review result: `collect_reader`
finalises a timed-out or agent-error call on its **first** call, without any retry, and those jobs
land in the same `broken` list as an answer that exhausted three protocol retries. Labelling that
call site unconditionally would tell an owner whose reviewer timed out that it "could not answer in
the required form", which is false, and would replace the accurate diagnostic with a wrong one. The
architecture keeps these apart (`status: ok | blocked-by-environment | protocol-error |
agent-error | timed-out | interrupted`), and so does this design:

```python
# panels.py, at the existing exhausted-panel call
kinds = {j['result']['status'] for j in broken}
block_kind = ('protocol' if kinds == {agents.PROTOCOL_ERROR}
              else 'mixed' if agents.PROTOCOL_ERROR in kinds else None)
```

- **`"protocol"`** — every broken reviewer failed at the protocol level. The owner gets the
  sentence requirement 3 asks for.
- **`"mixed"`** — some did and some did not. The owner is told both, per reviewer, and is never
  given one cause for the other's failure.
- **`None`** — no protocol failure at all (a timeout, an agent error, an interruption). Rendering
  is exactly today's, so a timeout keeps its own diagnostic and this design claims nothing about
  it.

In every case the per-reviewer causes are rendered as their own list, so the accurate reason for
each reviewer survives the classification. `engine.set_aside` stores the value as
`state["tasks"][tid]["block_kind"]` beside `status` and `reason`; `None` is simply not stored.

The task status value stays `blocked`. Nothing else in the engine learns a new status: `mark_skips`,
`finish_run`, `retry`, `replan` and every existing record keep working unchanged. **Read path for
old states:** `t.get("block_kind")` is absent in every state written before this change and renders
exactly as today.

What the owner sees, by classification. In the run's `STATUS.md`:

| `block_kind` | Status cell | "Needs attention" |
|---|---|---|
| `"protocol"` | `blocked (protocol)` | `- **implement** is blocked: the reviewers could not answer in the required form. 3 review answers were rejected and none was applied; they are summarised in tasks/010-implement/STATUS.md.` |
| `"mixed"` | `blocked (protocol, in part)` | `- **implement** is blocked: one reviewer could not answer in the required form and another did not finish. Per reviewer: implement.review.principal-engineer: could not answer in the required form; implement.review.spec-compliance: ran past its time limit. The rejected answers are summarised in tasks/010-implement/STATUS.md.` |
| absent | `blocked` | today's line, unchanged: `- **implement** is blocked: <reason>. See tasks/010-implement/STATUS.md.` |

"Next" prints, for a `"protocol"` or `"mixed"` task:

```
    # implement: the reviewers could not answer in the required form.
    # Read the rejected answers in tasks/010-implement/STATUS.md first.
    runner retry <run> implement --apply-patch
```

For `"mixed"` the first comment line reads
`# implement: one reviewer could not answer in the required form; another did not finish.`
For an absent `block_kind` the block is today's, unchanged.

`--apply-patch` is printed without the usual `[…]` brackets: nobody judged this candidate, so
continuing from the set-aside work is the right default rather than one of two options. (The
`retry`/`replan` ordering and the base-tree check that make `--apply-patch` reliable after a
`replan` are G1's subject, not this one.)

In the producer's `STATUS.md` the headline and the first paragraph change, for `"protocol"`:

```
# implement — blocked: the reviewers could not answer in the required form

Kind produce, type produce.
Reason: the review panel could not produce valid answers: implement.review.principal-engineer: resolutions must cover exactly this reviewer's open blocking findings, each once …

This is a protocol failure of the panel, not a judgement of the work. No finding from these rounds
reached the ledger.

Why each reviewer did not finish:
- implement.review.principal-engineer: could not answer in the required form (3 tries).
- implement.review.spec-compliance: could not answer in the required form (3 tries).
```

For `"mixed"` the headline reads
`# implement — blocked: the panel did not finish (one reviewer could not answer in the required form)`,
the paragraph drops the sentence about a protocol failure, and the per-reviewer list carries each
cause in its own words (`ran past its time limit`, `ended with an error`, `was interrupted`). That
list is rendered whenever `block_kind` is present, so the accurate cause per reviewer is always on
the page, whichever way the panel failed.

The runner's own console line, from `set_aside`, reads
`implement: blocked (the reviewers could not answer in the required form). Its work is in failed.patch`
for `"protocol"`, and keeps today's text otherwise.

### Command-line surface

Unchanged. No new command, no new flag, no new option. `runner status` and `runner status --rebuild`
show the new sections because they are regenerated from `state.json` (RUN-08 still holds: every new
line is a pure function of the state and of the directory listing). `runner retry`, `runner resume`,
`runner replan` and `runner resolve` behave exactly as before.

### What is deliberately not changed

- Acceptance: nothing here can accept a producer. `rejected_reviews`, `block_kind` and the
  repair record are never read by the engine to decide anything — the same rule as
  `branch_disposition` ("observed, never decided").
- The protocol-retry budget (A6: one call plus two retries), the diagnostic fed back to the
  reviewer, and B7's rule that an unanswerable panel leaves its producer `blocked` for a person.
- `validate.REVIEW` and `validate.check_review`: the wire shape is untouched, so an answer with an
  extra key or a wrong type is still rejected by the shape check before any of this is reached.

## Alternatives rejected

| Alternative | Rejected because |
|---|---|
| Leave the repair out; rely on the sharper prompt and diagnostic of `0e98e1a` | The brief's evidence is that this reduces the chance and does not bound the damage: the same answer arrived three times. Changes 2 and 3 alone would surface the finding to the **owner** but would still cost the producer and require a person |
| Repair any `resolutions` entry that names no ledger id, including when the required set is non-empty (drop the junk, keep the real ids) | The reviewer has demonstrably lost track of its own ledger while real blocking findings are open, and a round in that state can close a real finding as `resolved`. The repair must be limited to rounds where `[]` is provably the only correct value |
| Repair a passing answer too, as requirement 2's literal wording allows | Not strictly safer than today: it lets an answer written carelessly move a producer towards acceptance. The narrowing is recorded as a decision, not a dropped requirement: the evidence case is repaired, and the pass case is bounded by the `STATUS.md` summary. See [Open questions](#open-questions) |
| Match `resolutions` entries to findings by title similarity, or accept a title where an id is required | NYSE-R08 forbids reinterpreting arbitrary descriptions as ids. A near-match could resolve a real blocker on the strength of a string comparison |
| A new task status such as `blocked_protocol` | Widens the status vocabulary read by `mark_skips`, `finish_run`, `retry`, `replan`, `render_run_status` and every existing run record, for a distinction that is presentational. An optional `block_kind` field gives the owner the same information and needs no migration |
| Re-run the panel automatically when it exhausts its tries, without a person | Spends money unattended on a call that has already failed three times, and contradicts B7: a person repairs the panel |
| A new command (`runner review-answers RUN TASK`) to print rejected answers | `STATUS.md` is the existing surface for "what happened and what to do" (D14). A new subsystem is what the whole-design constraint and NYSE "Review priorities" item 5 tell us to avoid |
| Write the rejected answer to a new decision file, e.g. `invocation-N/rejected.json` | The answer text is already in `last-message.txt` and `stdout.log`; a new file adds an integrity-manifest entry and a write-once question for no new information. The **summary** does become tamper-evident, because it lives in `state.json`, which is already hashed |
| Summarise only answers that pass `validate.REVIEW`, and record `null` for the rest | It repeats the gap on the visibility surface: one malformed sibling field (`"resolutions": null`) would hide a readable verdict and perfectly readable finding titles, which is the loss G2 exists to stop. Extraction is per field instead |
| Cap the stored findings per answer, or the rendered answers, and send the reader to `events.jsonl` for the rest | The cap omits exactly the evidence requirement 1 asks for, and the destination does not hold it: the existing `review-call` event has `task`, `status`, `round` and `error`, no titles and no invocation path. The volume is already bounded by three tries per reviewer per round |
| Label the exhausted-panel call site `"protocol"` unconditionally, since that is where the malformed answers end up | That call site is reached by every non-ok review result, including a first-call timeout, which `collect_reader` finalises without any retry. It would give a timed-out reviewer the wrong explanation and hide its real one. The classification is derived from the broken outcomes |
| Judge repair eligibility once, at collection, and trust it at final application | The two calls do not see the same ledger: the coordinator applies reviewers sequentially, so an id raised by an earlier member of the same panel exists at the second point and not at the first. The final application decides, and its refusal is routed back through the retry machinery |
| Record the summary on the reviewer's task instead of the producer's | Requirement 1 asks for the producer's `STATUS.md`, which is where the owner arrives from the run's "Needs attention" line. The reviewer's own `STATUS.md` already lists its `round-N/` directories |

## Failure cases and crash points

**No new external effect.** This design adds no agent call, no command, no commit, no restore, no
pin, no ref and no patch, so it introduces no new intent/effect/outcome triple under A2. It writes
only to `state.json` (through the existing `Run.save`), to `events.jsonl` (append-only), to derived
files (`STATUS.md`, `index.json`), to `verdict.json` (through the existing `write_decision` in
`close_panel`), and it rewrites one `invocation-N/outcome.json` inside the round that is still open.

| Failure | What happens |
|---|---|
| The rejected answer is not a JSON object at all (prose, truncated stream) | `outcome.structured` is `None`: the entry records `verdict: null`, `findings: []` and the adapter's error. The pointer to `invocation-N/` is still written; the owner reads the raw text there |
| The answer is a JSON object that fails `validate.REVIEW` on one sibling field (`"resolutions": null`, `"summary": 7`) | The answer is still rejected and still retried, exactly as today, and **its readable verdict and finding titles are still summarised**. Extraction reads each field on its own merits and never asks whether the whole answer was valid |
| `findings` is a list holding some readable objects and some junk (a string, an object with no `title`) | The readable ones are summarised; the rest are counted as `unreadable_findings` and rendered as "N further entries could not be read". Nothing is guessed at, and nothing readable is dropped because of its neighbour |
| A reviewer supplies an id that another member of the **same** panel raises earlier in workflow order | The repair is refused at final application; the partly built ledger is discarded; the answer goes through the same rejection transition as any other, so it is summarised with its pointer and its invocation's `outcome.json` is corrected; the reviewer is re-called with the real diagnostic under its existing try budget; the other members' answers are re-applied once to a fresh copy. No `ProtocolError` escapes the engine |
| That same answer arrives three times, so every rejection happens at final application and none at collection | Three summaries, three corrected invocation outcomes, and a final result carrying the real diagnostic. The exhaustion guard's fixed text is never substituted for a call that completed |
| A reviewer times out on its first call, alone or beside a reviewer that exhausted its protocol retries | `block_kind` is absent or `"mixed"`, never `"protocol"` alone. The timed-out reviewer keeps its own cause in the per-reviewer list and in "Needs attention"; no claim is made that it answered in the wrong form |
| A finding title or a diagnostic contains a token-shaped string | It is redacted before it enters `state.json`, so `STATUS.md`, `index.json` and the state are all clean |
| A finding title contains newlines, backticks or markdown | Control characters become spaces and the text is cut to 120 characters; it is rendered as list-item text, never as a heading or a command line |
| Very many rejected answers (a long panel, many rounds), or one answer holding many findings | Everything is kept and everything is rendered: no cap omits required evidence. The volume is bounded by the protocol (three tries per reviewer per round, rounds bounded by `max_attempts`), and each title is a single line of at most 120 characters |
| The repair's conditions hold but the derived verdict is `pass` | `apply_review` raises the unchanged `ProtocolError` **after** computing on its private copy; the caller's ledger is untouched, the reviewer gets the same diagnostic as today, and the tries continue |
| The coordinator's apply pass raises after two reviewers were already applied to its local ledger | Nothing was written: the ledger is a local variable until the single `st.update(ledger=…)` write. It is discarded and rebuilt from `st["ledger"]` on the next pass, so ids are not consumed twice and history is not appended twice |
| The runner is killed after a coordinator refusal and before its state write | The panel step re-runs from the last saved jobs and refuses the same answer again. `note_rejected_answer` is idempotent by `job["invocation"]`, so there is exactly one summary, and the accepted members are applied exactly once |
| A reviewer sends the same malformed answer three times | Unchanged from today apart from visibility: the producer is `blocked`, now with `block_kind = "protocol"`, and the three rejected answers are summarised |
| A reviewer answer is rejected and the run is resumed later | `job["raw_outcome"]` is replayed through `collect_reader`; the entry is keyed by its invocation path, so it is not appended twice, and the `outcome.json` rewrite is byte-identical |

Crash points, all reconciled by the existing machinery:

| Killed… | On `resume` |
|---|---|
| after a reader batch is recorded (`panel:outcomes-recorded`), before `collect_reader` ran | The jobs' `raw_outcome` is in the state; `collect_reader` runs from it and writes the summary then. Nothing is lost, nothing is duplicated |
| after `collect_reader` appended a summary, before `self.save()` | The summary is lost but the outcome is not: the batch is replayed from `raw_outcome` and the summary is written again |
| after the coordinator emitted `review-repair`, before the state write that stores the repaired ledger | The apply loop re-runs from the unchanged `st["ledger"]`, so the ledger and the finding history are written exactly once. The event may appear twice in `events.jsonl`, which is an append-only log of attempts to act, and is how every replayed step already behaves |
| between `set_aside` storing `block_kind` and the `STATUS.md` regeneration | `STATUS.md` is derived; `runner status --rebuild` regenerates it identically (RUN-08) |

## Scenarios

New rows for [06-scenarios.md](../../06-scenarios.md), continuing the existing series. All are
checkable by the model-free suite: the scripted agent (`tests/fake_agent.py`) returns each review
answer verbatim from its script, including malformed ones, and `tests/helpers.py` drives a real run
in a scratch repository.

### Findings and convergence (FND)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| FND-21 | a round-1 reviewer raises one blocking finding and also lists it, by title, under `resolutions`, with `verdict = "block"` | the entry is dropped, the answer is applied, the finding is in the ledger and blocks, the author's next prompt lists it, and the reviewer was called exactly once | `fnd: a meaningless resolution is dropped, the finding is kept` |
| FND-22 | the same answer, but a `resolutions` entry names a real ledger id belonging to another reviewer | it is a protocol error with today's diagnostic, and the ledger is byte-identical to before the call | `fnd: a real id is never repaired away` |
| FND-23 | a later-round reviewer with one open blocking finding of its own supplies a junk `resolutions` entry instead of resolving it | it is a protocol error naming the required id; nothing is dropped and nothing is resolved | `fnd: no repair while a resolution is required` |
| FND-24 | a reviewer supplies junk `resolutions`, raises no blocking finding, and says `verdict = "pass"`; the same for a reviewer marked `advisory` | both are protocol errors: a repair may only deliver a block. The rejected answers are summarised for the owner | `fnd: a repair never produces a pass` |
| FND-25 | an answer is repaired | each finding it raised carries a `repair` history event naming what was dropped, `events.jsonl` holds one `review-repair` event, `verdict.json` holds the repair record with the original answer, and the producer's STATUS.md says the answer was repaired | `fnd: a repair is recorded where it can be audited` |
| FND-26 | every reviewer answers validly, with correct `resolutions` | no repair is recorded anywhere, the verdicts, the rework prompt, the attempt count and the commit are identical to a run before this change | `fnd: valid answers are untouched` |
| FND-27 | a two-member panel on one candidate: PE raises a blocking finding, and SC, running beside it, blocks and supplies PE's new id under `resolutions`. SC is eligible for the repair at collection and not at final application | SC's answer is refused at final application, SC is re-called with the **actual** diagnostic inside its existing tries, no exception escapes the engine, PE's finding appears exactly once in the ledger, and `resume` after a kill at `panel:applied` reaches the same ledger | `fnd: repair eligibility is decided by the ledger that applies it` |
| FND-28 | SC sends that same colliding answer all three times, so every rejection happens at final application and none at collection | the producer is blocked with **three** rejected-answer summaries, each with its verdict, its finding titles and its own `invocation-N/` pointer; all three invocations record the protocol error rather than `ok`; the final result carries the real diagnostic, not "interrupted calls exhausted protocol retries"; and the ledger is byte-identical to before the panel | `fnd: an answer refused at final application is still a rejected answer` |
| FND-29 | the runner is killed after the coordinator refused an answer and before the state write, then `resume` | exactly one summary exists for that invocation, the accepted members' findings are applied once, the ids are not consumed twice, and the run reaches the same ledger and the same task status as an uninterrupted run | `fnd: a coordinator rejection survives replay exactly once` |

### Runs and the record (RUN)

| ID | WHEN | THEN | Test |
|---|---|---|---|
| RUN-18 | one reviewer exhausts its three tries with malformed answers that each contained a blocking finding, and the producer is blocked | the producer's STATUS.md has a "Rejected review answers" section with one entry per rejected answer, each naming the reviewer, round and try, the claimed verdict, the finding titles, the reason it was rejected and the path of its `invocation-N/`; every path named exists; and the section says the answers were not applied | `run: rejected review answers are summarised for the owner` |
| RUN-19 | the same run | the run's STATUS.md shows the task as `blocked (protocol)`, "Needs attention" says the reviewers could not answer in the required form and points at the task's STATUS.md, and "Next" prints `runner retry <run> <task> --apply-patch`. A producer blocked with findings open, and a state written before this change (no `block_kind`), render exactly as they do today | `run: a protocol block is not a substantive block` |
| RUN-20 | a rejected answer's finding title holds a token-shaped string, control characters and 500 characters of text | the stored state and the rendered STATUS.md hold the redacted, single-line, truncated title, and `status --rebuild` regenerates the same bytes | `run: rejected answers are redacted and bounded` |
| RUN-21 | an answer that the adapter accepted is then rejected by the ledger check | that invocation's `outcome.json` records the protocol error and its diagnostic, not `ok` | `run: the invocation records the outcome that was used` |
| RUN-22 | a rejected answer is a JSON object with a readable `verdict` and two `findings` that are both valid, and `"resolutions": null` — so it fails `validate.REVIEW` on the sibling field **alone** | the answer is still rejected and retried, and its summary holds the claimed verdict and both titles. Nothing extracted reaches the ledger | `run: a malformed sibling field does not hide a readable finding` |
| RUN-23 | one rejected answer holds eleven findings, and a seven-member panel produces twenty-one rejected answers in one run | every one of the eleven titles and all twenty-one entries are in the state and in the rendered STATUS.md, each with its invocation path; no line sends the reader elsewhere for a remainder | `run: no rejected answer or title is omitted` |
| RUN-24 | one reviewer times out on its first call while another exhausts its protocol retries; and, separately, a panel where the only broken reviewer timed out | the first is `blocked (protocol, in part)`, naming each reviewer's own cause; the second has no `block_kind`, renders exactly as today, and is never described as having answered in the wrong form | `run: a timeout is not a malformed answer` |
| RUN-25 | a rejected answer holds three `findings`: one valid, one a bare string, one an object with no `title`; a fourth carries `"severity": 7` | the summary holds the two readable titles — the valid one, and the one whose severity could not be read, recorded as `unknown` — and counts the remaining two as `"unreadable_findings": 2`, rendered as "2 further entries could not be read". Nothing is guessed at | `run: unreadable finding entries are counted, not guessed` |

Requirement coverage: R1 → RUN-18, RUN-20, RUN-22, RUN-23, RUN-25, and FND-28 for the rejections
that only final application sees; R2 → FND-21, 22, 23, 24, 25, 27; R3 → RUN-19, RUN-24;
R4 → FND-22 (atomicity), FND-26 (unchanged rework path), FND-27 and FND-29 (a refusal at final
application, and its replay, leave the ledger untouched). RUN-21 covers the record correction found
while designing.

## Implementation plan

Ordered; each task is well under half an hour of agent work and is independently reviewable. No
task may write outside the files listed for it.

| # | Task | May write | Scenarios | Depends on |
|---|---|---|---|---|
| T1 | The repair in the ledger: `apply_review` returns `(ledger, verdict, repair)`, with the five conditions and the unchanged diagnostic on every other path. Update its two callers in `panels.py` to unpack three values. Rewrite `test_a_new_finding_listed_as_a_resolution_is_rejected_with_the_required_ids` as two cases: the repaired one (FND-21) and an entry naming a real id, which keeps today's assertions on the diagnostic text (FND-22) | `src/taskrunner/findings.py`, `src/taskrunner/panels.py`, `tests/test_findings.py` | FND-21, 22, 23, 24, 26 | — |
| T3 | `note_rejected_answer`: summarise every rejected review answer into `state["tasks"][<producer>]["rejected_reviews"]`, idempotent by invocation path. Extraction is per field and defensive — a readable `verdict` and readable finding titles are kept even when the answer as a whole fails `validate.REVIEW`, unreadable entries are counted, nothing is capped, everything is redacted; rewrite that invocation's `outcome.json` with the status that was used | `src/taskrunner/panels.py`, `tests/test_panels.py` | RUN-21, RUN-22, RUN-23, RUN-25 | — |
| T3b | The shared rejection transition: `reader_batch` records `job["invocation"]`; `reject_answer` summarises, corrects `outcome.json`, keeps the diagnostic, chooses between another try and a final result carrying the real error, emits `review-answer-rejected` and saves; `collect_reader` is routed through it; the dispatch loop's exhaustion guard uses `job["protocol_error"]` when it has one | `src/taskrunner/panels.py`, `tests/test_panels.py` | FND-28 | T3 |
| T1b | The coordinator's apply pass handles `ProtocolError` by discarding its local ledger and sending the job through `reject_answer`. **T1 is not correct without this** — eligibility is judged against a different ledger at the two call sites, so the exception is reachable | `src/taskrunner/panels.py`, `tests/test_panels.py` | FND-27, FND-29 | T1, T3b |
| T2 | Record the repair: the `repair` history event on each finding raised, the `review-repair` event from the coordinator, the repair inside `job["result"]` so `close_panel` writes it into `verdict.json` | `src/taskrunner/findings.py`, `src/taskrunner/panels.py`, `tests/test_findings.py`, `tests/test_panels.py` | FND-25 (ledger, event, `verdict.json`) | T1 |
| T4 | Render "Rejected review answers" and "Repaired review answers" in `render_task_status`, which gains `run_name` | `src/taskrunner/record.py`, `tests/test_panels.py` | RUN-18, RUN-20, FND-25 (STATUS line) | T2, T3 |
| T5 | `block_kind`: the keyword on `engine.end`, the value stored by `set_aside`, and the classification computed at the exhausted-panel call from the broken jobs' statuses (`protocol` / `mixed` / absent — never assumed from the call site). Then the console line, the three places it changes the run's `STATUS.md` (status cell, attention line, Next block), the task's headline, and the per-reviewer cause list that is rendered whichever way the panel failed | `src/taskrunner/engine.py`, `src/taskrunner/panels.py`, `src/taskrunner/record.py`, `tests/test_panels.py`, `tests/test_record.py` | RUN-19, RUN-24 | T4 |
| T6 | The documentation edits listed below, and the new scenario rows in `06-scenarios.md` | `docs/02-concepts.md`, `docs/04-run-directory.md`, `docs/05-architecture.md`, `docs/06-scenarios.md`, `docs/runbook.md`, `docs/nyse-execution-lessons.md` | — | T1–T5 |

Every task's dependencies are above it. T1 and T3 are independent and may be done in either order
or in parallel; everything else follows the arrows. T3b turns T3's helper into the one transition every rejection goes through, and T1b
depends on it as well as on T1: routing the coordinator's refusal anywhere else loses the summaries
requirement 1 asks for. T1b must land with T1 or immediately after it, and before T1 is reviewed as
complete: T1 alone leaves a reachable uncaught exception. The whole suite must pass at the end of each task, and the mermaid lint test must pass
after T6.

## Documentation changes

No existing document is edited by this design document. These are the edits the implementation
makes.

| Document | Edit |
|---|---|
| `docs/06-scenarios.md` | Add FND-21 to FND-26 to "Findings and convergence" and RUN-18 to RUN-21 to "Runs and the record", in the tables' existing format. Mark them **(G2)** the way earlier rows are marked (A*n*)/(B*n*), and add a line to the file's preamble explaining that marking |
| `docs/02-concepts.md` | In "Findings", after the paragraph on the derived verdict: state the one repair the runner is allowed to make, its five conditions, that it can only deliver a block, and that eligibility is decided by the ledger the answer is finally applied to. In "Failure (D9)", extend the sentence "A panel whose members cannot produce a valid answer leaves its producer `blocked`, not `failed`" with: the record distinguishes a panel that could not answer in the required form from one that did not finish, per reviewer, and the rejected answers are summarised in the producer's `STATUS.md` |
| `docs/04-run-directory.md` | In the layout block, annotate `verdict.json` with "plus `repair` when the runner dropped meaningless `resolutions` entries", and `outcome.json` with "the status that was used, including a rejection by the ledger check". Under "Rules of the record", note that a rejected answer is summarised into `state.json` (redacted at capture) and pointed at from the producer's `STATUS.md`, and that the raw text stays in `last-message.txt` |
| `docs/05-architecture.md` | In "Review rounds (A7)", one sentence on the repair and its limit to answers that block, beside the existing sentence on the derived verdict; and one on where eligibility is decided, since reviewers are applied sequentially in workflow order. Beside the `AgentResult` status list, note that a blocked producer's `block_kind` distinguishes a panel that failed at the protocol level from one that timed out or errored |
| `docs/runbook.md` | In "3. Stops that need you", add a row: "TASK is blocked: the reviewers could not answer in the required form" → "Nobody judged the work. Read the rejected answers in `tasks/NNN-task/STATUS.md`, then `runner retry RUN TASK --apply-patch`, `resume`", and a second for the mixed case, where one reviewer did not finish at all. In the decision chart, split the "task blocked" branch into "no valid answers from the panel" and "findings open / the agent said blocked". In "Where to look", add "What did a rejected reviewer answer say? → `tasks/NNN-task/STATUS.md`, then the `invocation-N/last-message.txt` it names" |
| `docs/nyse-execution-lessons.md` | Under NYSE-R06 and NYSE-R08, record G2 as shipped: the one repair and its limit, the rejected-answer summary, and the protocol/substantive distinction in status |

## Open questions

1. **The narrowing of requirement 2 is the one place this design does less than the brief's
   literal wording.** The brief's candidate repair does not mention the derived verdict; condition
   (5) adds it so that the change stays strictly safer than today. If the owner would rather have
   the unnarrowed rule, the change is one condition in `findings.apply_review` and one scenario
   (FND-24 splits into "advisory reviewer" and "passing reviewer"). No other part of this design
   depends on it. Nothing here needs an amendment to a recorded decision.
2. **The end-reason string for a non-protocol panel failure is pre-existing and slightly wrong.**
   `panels.panel` records "review panel could not produce valid answers" even when the reviewer
   simply timed out. This design does not re-word it, to keep the change local; it makes the owner-
   facing rendering accurate instead, with the per-reviewer cause list. Re-wording that string is a
   one-line follow-up that no scenario here depends on.
3. **Should a repaired round be shown in the run's `STATUS.md` as well as the task's?** This design
   shows it only on the task, because the run's "Needs attention" is for things that need a
   person and a repaired round does not. If the owner wants repairs visible at the top level, it is
   one line in `render_run_status`.
4. **How long should `rejected_reviews` live?** This design keeps every entry for the life of the
   run, so a task that was retried and later accepted still carries the history in its `STATUS.md`
   under a heading that says the answers were not applied. The alternative — clearing the list on
   `retry`, as `findings.restart` supersedes findings — would make the section always current but
   would lose history the record is supposed to keep. Assumption: keeping it is right.
5. **Assumption about `last-message.txt`.** Requirement 1 says the rejected answers "are already in
   `invocation-N/`". Read from `agents.HeadlessAgent.run`, that file is written for every outcome,
   after redaction, before the result is returned — so it exists for a rejected answer too. An
   implementer should confirm it for the Codex adapter's protocol-error path as the first step of
   T3; if it can be empty there, RUN-18 must point at `stdout.log` for that case instead.
6. **Out of scope, and named so the seam is visible.** The command this design prints,
   `runner retry <run> <task> --apply-patch`, is only as good as G1 makes it: today that path is
   refused after a `replan`, and its base-tree check can refuse a patch that still applies. G2
   assumes G1's fix; if G1 is not implemented, the printed command is still today's documented
   advice for a blocked producer.
