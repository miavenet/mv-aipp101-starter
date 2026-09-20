# Scenario catalogue

## Published precedents

These are pointers to source conditions, not copied test books. Read the source for its exact feed, setup, expected values and applicability.

| Published source | Concrete locations worth reading |
|---|---|
| [HKEX OMD-C procedure, S03](SOURCES.md#s03-hkex-omd-c-readiness-procedures) | §7.2 conditions 3.1–3.4, 4.1–4.6, 5.1, 6.1–6.5 |
| [HKEX answer book, S04](SOURCES.md#s04-hkex-answer-workbook) | `Verification Instructions`, scenario sheets, including `1-1` and `5-*` |
| [CME MDP 3.0, S02](SOURCES.md#s02-cme-autocert-mdp-30) | Book management; MBP/MBO recovery; TCP replay; channel reset |
| [Nasdaq historical guide, S08](SOURCES.md#s08-nasdaq-ise-recovery-guide) | §7.2, three recovery situations |
| [NYSE historical instructions, S06](SOURCES.md#s06-nyse-global-otc-testing-instructions) | Playback Testing and Simulated Trade Testing |

## Proposed suite for this project

**All `FH-*` IDs below are our proposals, not exchange-issued case IDs.** They borrow test categories from the sources and add engineering robustness checks. Each fixture must declare a venue/feed/revision profile. Expected behavior for unspecified or unsupported inputs is an explicit local policy, never an invented exchange requirement.

Evidence labels: **P** = adapted published testing pattern; **S** = derived from the target specification; **E** = additional engineering test. Shared foundations: [S02](SOURCES.md#s02-cme-autocert-mdp-30), [S03](SOURCES.md#s03-hkex-omd-c-readiness-procedures), [S05](SOURCES.md#s05-hkex-onboarding-tools), [S10](SOURCES.md#s10-nyse-pillar-common-specification), [S11](SOURCES.md#s11-nyse-pillar-integrated-specification).

| ID | Setup and injected stimulus | Required observable result | Basis |
|---|---|---|---|
| FH-001 | Encode one supported message of each type from independently reviewed field values | Exact decoded fields, signedness, scaling and identifier values match fixture | P/S; S06, S10–11 |
| FH-002 | Pack several messages together, including a known message with a supported extension and an unknown type | Profile-defined skip/extension policy preserves alignment; subsequent valid message decodes | S; S10 §§2–3 |
| FH-003 | Truncate each structural boundary; corrupt lengths/counts; insert trailing bytes | Bounded error with offset; no overread, hang or silently accepted malformed event. Partial-commit policy is explicit | E |
| FH-004 | Replay identical logical messages with different valid packet boundaries | Same ordered decoded stream and book checkpoints; sequence advances at the profile's unit | S; S10 §3.3, §5.1.4 |
| FH-005 | A and B both deliver a message; vary which arrives first | One logical application; duplicate metrics reflect the configured counting policy | P; S03 |
| FH-006 | Drop a range on A, deliver it on B within the chosen arbitration deadline | Contiguous output; no duplicate mutation or unresolved gap after arbitration | P; S03 |
| FH-007 | Drop the same small range on both lines while delivering later data | Exact missing range requested; later data handled by declared buffering policy; replay restores continuity | P/S; S02, S10 §5.1.2 |
| FH-008 | Recovery duplicates already received messages and repacketizes the missing range | Missing events applied once; old events never applied twice | S/E; S10 §5.1.4 |
| FH-009 | Introduce bounded reordering, then deliver the missing data before the local deadline | State converges; no false permanent gap; fixed seed reproduces timing decisions | E |
| FH-010 | Lose data on one of two channels sharing numeric sequence values | Recovery and invalidity scoped to affected channel; other channel continues correctly | S/E; S10 §3.3 |
| FH-011 | Connect late and supply a complete snapshot while live traffic continues | State matches a clean reference run at the chosen cutover; consumer validity changes at the defined boundary | P; S02, S08 |
| FH-012 | Supply incomplete/out-of-order refresh fragments, including a missing final fragment | No incomplete state marked synchronized; retry/failure follows profile; memory remains bounded | S/E; S10 §5.1.6 |
| FH-013 | Exercise live events just below, at, and above each snapshot watermark for several symbols | No missing/double-applied event; cutover interpretation explicitly justified from the pinned spec | S; S10 §5.1.9, §7.4 |
| FH-014 | Recovery server rejects a request, reports unavailability, or never completes it | Distinct diagnostics; bounded retry/escalation; invalid data is not relabeled valid | P/S; S03 §6 notes, S10 §§6–7 |
| FH-015 | Deliver updates before reference mapping; later deliver mapping or refresh it | No invented symbol assignment; profile-defined recovery/quarantine; recovered state matches oracle | P; S02 |
| FH-016 | Emit the profile's explicit restart/reset sequence; then reuse old numeric IDs | No accidental association with the old epoch; only state specified for reset is cleared | P/S; S10 §8 |
| FH-017 | Switch publishers/recovery peers during activity | Profile-specific transition succeeds or reports failure; duplicate and sequence handling remains consistent | P; S03 |
| FH-018 | Add several orders/levels, change size/price, execute and delete; include equal prices | Compare every checkpoint with an independent reference model, including order priority if exposed | P/S; S02, S11 |
| FH-019 | Inject duplicate add, unknown delete, and impossible quantity under an explicit robustness policy | No underflow/corruption; diagnose or invalidate as configured; do not invent missing state | E |
| FH-020 | Interleave status, clear, auction and trade events with book updates | Consumer flags and state transitions match the selected product; non-book messages do not accidentally mutate depth | S; S10–11 |
| FH-021 | Replay a day/session boundary with timestamp and reference-data changes | Correct epoch/reference rollover; no old book leaks into the next initialized state | S/E; S10–11 |
| FH-022 | Replay a suitable real capture from its known baseline | Exact checksums/counts/checkpoints against a reviewed oracle; unexplained gaps fail the run | P/E; S05–07 |
| FH-023 | Increase replay rate and include a controlled burst while forcing a slow downstream consumer | Measure loss, queue high-water marks and delay; no silent drop or unbounded backlog | P/E; S03, S05 |
| FH-024 | Run a sustained workload and repeat equivalent clean scenarios | Stable bounded resources; repeated canonical state hashes agree; performance thresholds set by this project | E |
| FH-025 | Fuzz parser bytes and mutate valid stateful sequences with saved seeds | Sanitizers clean; bounded time/resources; minimized failing fixture retained | E |
| FH-026 | Mutate handler behavior: remove dedup, shift recovery range, weaken boundary check, or mark stale state live | At least one relevant scenario must fail for each introduced defect | E |

For snapshot recovery, “state matches” does **not** imply the historical event tape is complete. Where the product cannot reconstruct lost trades, assert a history-gap indicator separately. Whether stale values may still be served is a consumer API decision; tests must check their quality flag and must not claim the feed mandates a particular API.

## Concrete deterministic example: arbitration and replay

This is a **logical fixture**, not valid Pillar bytes. An encoder maps it to the pinned packet/message format only after the field layouts are reviewed. Start from a known initialized session with `next_sequence = 100`. The four logical events are:

| Sequence | Event | Expected state after application |
|---|---|---|
| 100 | Add order A, bid price 10000 in fixture units, size 10 | A=10 |
| 101 | Add order B, same side/price, size 7 | A=10, B=7; total 17 |
| 102 | Delete A | B=7; total 7 |
| 103 | Delete B | Empty |

Test 1 delivers 100–101 on A, then 100–103 on B, then delayed A duplicates. Expect the applied sequence list `[100,101,102,103]`, no missing range, and an empty final book. Use a virtual clock and a defined arbitration wait policy.

Test 2 delivers 100–101, loses 102 on both lines, then delivers 103. Advance past the configured gap deadline. Expect request range `[102,102]`. The recovery peer sends 102; the buffered 103 follows. Compare the same checkpoints and exact application list. A final-book-only assertion would miss several possible sequencing errors, so it is insufficient.

Test 3 gives the recovery peer an unavailable response instead. Expect no claim of contiguous completion. If the handler supports snapshot recovery, drive that path and verify book recovery separately from event-history continuity. Otherwise assert the declared unavailable state.

## Fixture acceptance record

Every case should have: ID, source class, protocol revision, spec section, starting state, seed/clock schedule, ingress bytes or reviewed encoder inputs, expected requests, event checkpoints, final state, quality transitions, resource limits and pass/fail criteria. Report unsupported features as explicit scope exclusions, not green tests.
