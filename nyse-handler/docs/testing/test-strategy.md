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
- **When real pcaps arrive:** add golden dumps from them. Cross-check against an independent
  source (TAQ or a vendor feed) where available.

## Layer 7: Hot-path discipline

- An allocation-counting test (replaced global `operator new`): zero allocations after warm-up
  during a replay.
- Pcap reader robustness: truncated files, bad block lengths, snaplen truncation, VLANs,
  non-UDP frames, both pcap byte orders, and ns and µs resolution.
