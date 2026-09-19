# Milestones

## M0: Design (this directory)

- [x] Design plan, ADRs, module layout, test strategy
- [ ] Owner review of these docs

## M1: Synthetic end-to-end replay

**Definition of done:**
> A synthetic A/B pcap containing every message type, plus an injected
> unrecoverable gap, replays through `nyse_replay` and produces the expected L2 books and event log,
> with all property tests passing under ASan and UBSan in CI.

Suggested order (each step ends green):

1. ✅ **Spec:** fetch the latest spec and record the version. Fill in the [message catalog](../spec/message-catalog.md).
   Done 2026-09-19: Integrated Feed v2.5h, Common Client v2.4s, all 20 layouts in [field-layouts](../spec/field-layouts.md).
2. **Build wiring:** add `nyse-handler/` to CMake, with empty module libraries, UBSan, and the no-`chat`-include check.
3. **core:** `types.atlas` (Price, Volume, OrderId, SymbolIndex, SeqNum, ChannelId, Timestamp, …), `Packet`.
4. **Fixtures:** hex fixtures for the packet header and every message type → **owner review**.
5. **pillar:** layout tables, views, framing validation, decoder dispatch. Layer 1 tests pass.
6. **testing/md:** `PillarEncoder`, `PcapWriter`. Layer 2 round-trip properties pass.
7. **io:** pcap + pcapng reader, `PcapSource`. Robustness tests pass.
8. **book:** `OrderMap`, `BookSide`, `Book`, `BookSet`, invariants. `ReferenceBook` oracle properties (layer 3) pass.
9. **arb:** `ChannelArbiter`, gap buffer pool, `NoRecovery`. Layer 4 properties pass.
10. **stats + handler:** counters, anomaly ring, `StatsSink`, `FeedHandler<Consumer>`, events, `EventDumper`.
11. **config + app:** JSON config, `nyse_replay` CLI.
12. **E2E:** synthetic scenario pcap, golden dump, allocation-count test. Done.

## M2: Real data

- The first real pcaps are replayed. Golden dumps are reviewed.
- Anomaly counters are investigated and explained.
- Benchmarks: ns/packet histogram, data-structure choices confirmed or changed.
- Capacities sized from the observed data.

## M3: Live

- `MulticastSource` (plain sockets, `recvmmsg`, timestamps).
- A production `StatsSink`.
- A latency target is set.

## M4: Recovery and hardening

- `RetransRecovery` and/or `RefreshRecovery`.
- One pinned thread per channel group. Counter snapshots.
- The performance path in [08](../design/08-performance-guidelines.md#path-to-production-latency-not-in-m1), as the target requires.

## Later

- Other Pillar markets (Arca, American, National, Chicago).
- L3 output.
- Consumer adapters (SPSC ring, out-of-process).
