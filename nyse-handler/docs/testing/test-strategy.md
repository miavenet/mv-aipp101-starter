# Test strategy

See [ADR-0007](../decisions/0007-synthetic-testing-with-reference-oracle.md) for why.

## Tooling

- **doctest** for unit tests, **RapidCheck** (doctest integration) for property tests.
- All tests run under **ASan + UBSan** in CI. The `debug-clang` preset already has
  ASan. UBSan is to be added for the `md` targets.
- Test-only helpers live in `src/wjh/testing/md/` and never ship in the library.

## Layer 1: Hand-written hex fixtures (spec conformance)

- One fixture per message type, plus the packet header, in `src/wjh/md/tests/fixtures/`.
- Written **from the spec tables, byte by byte**, with a comment per field citing the spec.
- Tests decode each fixture and assert every field.
- **Must exist and be reviewed before `PillarEncoder` is written.** Review uses the
  [checklist](fixture-review-checklist.md).

## Layer 2: Encoder round-trip

- `PillarEncoder` builds messages and packets. `PcapWriter` writes pcap and pcapng with A/B lines.
- Property: `decode(encode(m)) == m` for arbitrary valid `m` of each type.
- Property: `encode(decode(fixture)) == fixture`, which ties the encoder back to layer 1.

## Layer 3: Reference-model book oracle

- `ReferenceBook`: `std::map`-based, deliberately naive, **never optimized**.
- Generator: random **valid** event sequences (adds; modifies, replaces, executes,
  and deletes of live orders; symbol clears) across several symbols.
- Property: after every event, the real `Book`'s L2 view equals `ReferenceBook`'s.
- Second generator with **invalid** events (unknown IDs, duplicate adds): the real book
  must count the anomalies and never violate invariants.

## Layer 4: Arbitration properties

Generate a perfect single-line packet stream `S`, then derive the A and B lines with random
drops, duplicates, and bounded reordering.

| Property | Assertion |
|---|---|
| Coverage | If every sequence number is present on A ∪ B, the output equals the output of `S` and nothing is stale |
| Double loss | If a sequence number is missing on both lines, `ChannelStale` fires exactly once, at that point |
| Idempotence | Adding more duplicates never changes the output |
| Reset | A sequence reset clears the channel's books and returns it to `Synced` |
| Window | A gap filled within the window is invisible. One filled after it is not. |

## Layer 5: Invariants

`Book::check_invariants()` runs after every event in debug and test builds.
See [05](../design/05-order-book.md#invariants-checked-after-every-event-in-debug-builds).

## Layer 6: End-to-end and golden

- **M1:** a synthetic A/B pcap (every message type plus an injected double loss) goes through the
  real `nyse_replay` CLI. Its `--dump-events` output is diffed against a reviewed golden file.
- **When real pcaps arrive:** add golden dumps from them.
- **Cross-check (M2): Stock Summary reconciliation.** There is no access to TAQ, a vendor feed or
  SIP data, so the check uses the feed itself. The Stock Summary message (type 223) gives the
  exchange's own high, low, open, close and total volume per symbol every 60 seconds. A
  `SummaryReconciler` consumer accumulates the same figures from our trade events and reports every
  symbol where they differ at a summary tick.
  - Volume rule to confirm on the first real capture: printable Order Executions and Non-Displayed
    Trades, plus Cross Trades, minus Trade Cancels, adjusted by Cross Corrections. Auction fills
    carry `PrintableFlag` 0 precisely so the Cross Trade's bulk volume is not double counted
    (Integrated Feed v2.5h §5, §10).
  - It catches wrong trade decoding, missed cancels and double-counted auction volume.
  - It does **not** validate the book. The free book check is consistency with the feed's own
    executions: an execution against an `OrderID` we do not hold, or at a price where we show no
    such order, is counted by the existing anomaly counters and should be near zero on a clean day.
  - Stock Summary is on its own channel, so the capture must include it.
- If TAQ or a vendor source becomes available later, add it on top.

## Layer 7: Hot-path discipline

- An allocation-counting test (replaced global `operator new`): zero allocations after warm-up
  during a replay.
- Pcap reader robustness: truncated files, bad block lengths, snaplen truncation, VLANs,
  non-UDP frames, both pcap byte orders, and ns and µs resolution.

## Scenarios

Each module's design doc ends with a **Scenarios** table. The idea is borrowed from OpenSpec's
requirement format, without the tool. It ties every stated behaviour to the test that proves it.

| Column | Meaning |
|---|---|
| ID | Stable, never reused: `IO-`, `DEC-`, `ARB-`, `BOOK-` plus a number. `-P` marks a property test, `-A` an anomaly, `-C` a capacity limit |
| WHEN | The trigger, in the design doc's own terms |
| THEN | What must be observable: output, events, counters, state |
| Test | The exact doctest `TEST_CASE` name. `<…>` stands for a family of cases, one per message type |

Rules:

1. **A behaviour that matters gets a scenario before its code is written.** The test is written
   first or alongside, under the name in the table.
2. **The table is the contract; the test name is the link.** Renaming a test means updating the table.
3. **No hand-kept status column.** `tools/check_scenarios.py` reads the tables, searches
   `src/` for the test names, and reports which scenarios are proven. `--strict` fails when a named
   test is missing, for CI once a module is declared done.
4. **Scenarios that wait on an open question say so** (for example "pending Q12") and are settled
   when the question closes.
5. Decision tables, state machines and invariants in the design docs stay as they are. Scenarios
   sit on top of them; they do not replace them.

Where they live: [02 input](../design/02-input-sources.md#scenarios),
[03 arbitration](../design/03-arbitration-and-gaps.md#scenarios),
[04 decoding](../design/04-pillar-decoding.md#scenarios),
[05 order book](../design/05-order-book.md#scenarios). Handler, stats and config get theirs at M1
steps 10 and 11.
