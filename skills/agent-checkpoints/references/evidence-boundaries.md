# Evidence boundaries for agents

Use this at a material milestone or handoff, particularly for recovery, integration,
or a claim of completion. Put relevant evidence in the existing requirement and
verification fields; no separate score, mandatory report block, or extra review round.
For a small edit, a short verification statement is sufficient.

## Shared checks

- **Claim and authority:** distinguish authored, executed, verified, reviewed and accepted.
  A tool event proves activity; a checkpoint proves saved bytes; a passing test proves
  its assertions for its inputs; runner acceptance proves its configured gates passed.
  None alone proves the whole objective. Name the relevant artifact and evidence.
- **Completeness:** compare outputs with the task's independent requirement list, not
  only the files that happen to exist. Hashes cannot reveal an artifact omitted before
  the manifest was written. Keep unfulfilled requirements visible.
- **Boundary:** for a load-bearing claim crossing a process, file, callback or ownership
  boundary, identify who establishes it and what the receiver checks. Ask for one
  concrete case in which the local check passes while the claimed outcome is false.
  Address that case when it falls within the task's acceptance requirements.
- **Failure evidence:** test the relevant failure mechanism, not just its configuration.
  A capacity setting does not prove overflow handling; exercise the boundary and an
  excess. A restart claim needs interrupted-state recovery evidence. Use controlled
  faults within authorized resources, not destructive experiments on a live run.
- **Freshness:** associate results with the candidate and inputs tested. Changed inputs,
  recovery or a new candidate can invalidate a result. State historical results as such.
- **Proportion:** add a guardian when a concrete consequential invariant lacks one.
  Prefer an existing assertion, test or runner gate. Repeated failures are a reason to
  investigate a common cause, not an automatic mandate for a framework or new schema.

A design task may legitimately finish with execution and performance unmeasured.
Say so; do not demand implementation to accept a design-only deliverable. A deferred
requirement needs an authorized scope decision, not just an author's omission.

## Targeted checks for substantial changes

- Verify load-bearing dependency semantics against the installed version's source,
  generated output or a focused executable probe. Derive the questions from what the
  design needs to be true; a checklist of past bugs cannot establish completeness.
  Distinguish a fact not yet checked from a decision not yet made. Record consequential
  open decisions and resolve them within the task's authority before depending on them.
- Use discriminating tests: would the assertion fail if the intended action were absent
  or wrong? Check that fixtures do not perform the work under test. For bounds, include
  exact fit and excess when relevant; for recovery, use the intended process ordering.
- Run relevant deterministic checks before spending another review round on the same
  mechanically detectable defects. Passing formatting/schema checks proves conformance
  to those checks, not semantic truth.
- Rework review follows changed behavior, prior findings and affected dependencies.
  Reuse unchanged evidence only when its candidate/input identity remains applicable.
  Expand review when an interface, invariant or evidence source changes; line-count
  percentages alone are not a reliable measure of semantic impact.
- If successive reviews discover serious new defects in supposedly settled behavior,
  investigate a shared mistaken assumption or inadequate test boundary before another
  local patch. Reopen the design when evidence supports doing so, not automatically
  after a fixed number of passes. Persist the decision and next step at that milestone.

## Perspective-specific questions

Use only the assigned perspective. These questions sharpen existing scope and blocking
criteria; they do not grant additional tools, make advisory reviewers blocking, or
require every persona on every task.

| Perspective | Useful question and evidence |
| --- | --- |
| Implementer | Which requirement is still unverified? Save the candidate and relevant test evidence; report the next incomplete step. |
| Principal engineer | Could a caller observe invalid intermediate state despite a correct final state? Check ownership, ordering and failure transitions. Added complexity needs a concrete correctness/resource benefit or measured performance benefit. |
| Specification compliance | Does the cited version actually establish the behavior, including precedence and exceptions? Separate protocol facts from local policy and explicitly scoped deferrals. |
| DevOps | Does evidence cover the documented execution environment and interruption topology? Distinguish configured hooks from observed events, and local crash recovery from storage-loss backup. |
| Process manager | Can requirements be traced to artifacts and appropriately scoped evidence? Check that self-reports or checksums have not become acceptance claims. |
| Technical project manager | Can the next task consume what exists now? Expose missing interfaces, unmet dependencies and deferred obligations instead of treating a declared capability as delivered. |

## Why this variant is small

The updated RIGOR.md supplies the full rubric, replacing the earlier command prompt.
Its strongest transferable guidance is evidence ownership, checking real dependency
semantics, discriminating tests, scoped review and investigating recurrent failures.
RIGOR_BOUNDARY.md contributes the distinction that local rigor does not prove correctness
across integration boundaries.

The rubric's priorities and prescriptions are specific to its original trading fabric:
latency and distributed behavior receive 40 points, while clarity receives 3 and
operability/testability together receive 4. Those weights do not reflect this project's
first-class testability and high bar for complexity. Its amc/dmmeta, no-STL, sequenced-clock
and mandatory generated-structure rules are not portable requirements. A measurement
establishes observed behavior; it cannot override normative protocol requirements.

The rubric reports paired self/blind score differences, but the supplied ledger does not
contain those pairs. Treat its causal diagnosis as a hypothesis rather than a reproduced
result: falling self-scores alone cannot rule out generosity, and repeated findings alone
cannot prove an abstraction is wrong. Targeted evidence checks can still be useful without
accepting those stronger conclusions.

We retain evidence ownership, completeness, failure cases and separate readiness claims.
We omit numeric self-scores, a duplicate ledger, unconditional second reviews, mandatory
generated matrices, and source-project-specific substrate conventions. Existing runner
records and persona reviews already provide those structures where needed. This guidance
is an aid to finding real defects, not an independently enforced acceptance gate.

The supplied rigor_scores.tsv adds useful evidence of defect discovery: attribution
errors, stale counts, unsupported capability claims and contaminated experimental
baselines were identified and corrected. It contains 13 events, 12 scoring 95–99
and one scoring 80. This concentration does not prove inflation: the sample may
preferentially record corrected work. It also does not establish score calibration.
Several events combine review, edits and rescoring; some identify blind review, but
this ledger alone cannot establish reviewer independence or reproduce the verdict.
Its five columns also differ from the six-column format requested by RIGOR.md.

Retain concrete findings, candidate identity, verification evidence and dispositions
in the runner's existing review records. Keep initial findings distinguishable from
post-fix verification. Independent reviewers should assess the candidate and brief
before relying on the author's quality claims; rework review still needs the prior
findings to verify closure. Do not create another TSV or award numerical confidence
from this small, selected history.
