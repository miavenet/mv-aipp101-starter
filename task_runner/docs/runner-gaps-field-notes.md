# Field notes: the runner fixing its own gaps (2026-09-20 → 2026-09-23)

The gaps G1–G3 were implemented by the runner itself: two design documents authored by
Claude Opus and reviewed by Codex Astra, then a 19-task implementation workflow, one task per
row of each design's implementation plan, each reviewed by a blocking principal-engineer
persona on Astra with a Claude fallback. This page keeps what the run cost and what it taught,
so the next estimate is better than this one was.

## Cost

| Phase | Tasks | Known spend | Unpriced (Codex) | Notes |
|---|---|---|---|---|
| Spec, first attempt (5 designs) | 5 | $42.66 | 22 calls, ~11M tokens in | Did not converge; retired. Two strict blocking reviewers, three attempts, large documents: every rework added surface for the next round |
| Spec, narrowed (G1, G2) | 2 | $21.88 | 11 calls, 3.8M in | Accepted in 2 and 3 attempts. Spec-compliance made advisory |
| Implementation (G1 11 tasks, G2 8, G3 1) | 19 | **$148.61** | **62 calls, 11.2M in** | Cap $90 → stopped once → +$50, +$75 (owner). **65% over the plan** |

Per task the implementation averaged 2.6 attempts. Sonnet tasks cost $0.20–$7; Opus tasks
$6–$12 with one or two rework rounds. The most expensive task was G2-T4 at $22.56 over 7
attempts: four Sonnet rounds on one blocker, then Opus found that the design itself was
missing a field (repair events carried no answer identity) and blocked with a proof. A
replan gave the task the extra file and it landed in one more attempt.

The estimate was wrong for two reasons: tasks were priced at $2–5 as if the first attempt
were the usual one, and reviews were "free" only because Codex is unpriced. Count review
tokens: 11M tokens of reviewing is not nothing.

## What broke, and what it cost

| Incident | Effect | Fixed |
|---|---|---|
| Network outage during a producer call (`ENOTFOUND`) | 4 attempts of one task burned; another task lost 1 attempt later | Unreachable API is an environment failure: the run stops, no attempt used (G8) |
| Codex "Selected model is at capacity" on a review call | The panel was declared broken, the producer's work set aside | Transient provider failures are retried within the try budget, then the fallback profile (G9) |
| A review call ran past its 40-minute limit | Same as above | A time-out is retried the same way |
| Every accepted task's gate re-run for a candidate touching their outputs, all the same command | 9 full test suites (~30 min) for one candidate, twice | A command runs once per candidate; the record says whose run it shares (G10) |
| Environment marker `enotfound` matched inside `FileNotFoundError` in source a reviewer printed | A completed pass verdict discarded; run stopped | Whole-word markers; tool output is checked for sandbox startup failures only (G11) |
| `retry --apply-patch` after a replan (twice) | The set-aside work of a replanned task could not be restored | G1 itself — on this very branch, but not yet in the runner driving the run |
| Owner pauses: `pkill`/`pgrep` by name hit the wrong process once | A monitor killed instead of the runner | `runner pause RUN [--now]`, addressed through the run lock |
| STATUS.md not refreshed at an interrupt | No mention of the interrupted call | The engine's final beat runs on any exit (G7) |
| Interrupted and timed-out calls counted as "unknown usage" | Calls cut short by an outage or a pause had no tokens in the ledger | The provider's own record (Claude transcript, Codex rollout) is read for the call's tokens (G4) |

Two of these (the marker and the gate re-runs) were made worse or caused by fixes landed the
same day. A fix to the runner driving a live run takes effect at the next `resume`, never in
the running process; a pause is the way to pick it up.

## What worked

- One task per implementation-plan row, in one chain, was the right grain: every task was
  independently reviewable, and the reviewer caught real defects (a crash reachable only through
  the coordinator's apply pass; a test that passed without the check it claimed to cover).
- Agents that block with a proof instead of departing from the design. G2-T1 refused a brief
  that the design's own plan contradicted (T1 without T1b leaves a reachable exception); G2-T4
  proved a design gap. Both cost one replan and saved a bad merge.
- A budget ledger kept beside the run, written as things happened.

## What to do differently

- Price a task at its likely attempts × its model, plus its reviews in tokens; keep a 50%
  reserve rather than topping up three times.
- Put dependency notes from the design's plan ("T1b must land with T1") into the task order
  before validating the workflow; the table order is not the dependency order.
- Give a task that fails the same blocker twice on Sonnet to Opus before its attempts run out.
- Prefer `runner pause` to any signal by hand.
