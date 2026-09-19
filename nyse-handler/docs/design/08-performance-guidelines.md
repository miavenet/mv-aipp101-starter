# 08 — Performance guidelines

The rules below apply to the **hot path**: everything from receiving a packet to the consumer
callback returning.

## Latency budget (decided 2026-09-19, a hypothesis until measured)

The output feeds **live signals and pricing for a strategy that is not racing anyone**. Tail latency
matters, because a slow packet means a stale book. Microsecond-level competition is out of scope.

| Budget | Value | Confirmed when |
|---|---|---|
| Per-packet processing time, median (handler entry to return, `NullConsumer`) | ≤ 5 µs | M2, replay benchmark on real pcaps |
| Per-packet processing time, p99 | ≤ 25 µs | M2 |
| Excursions above 1 ms | none after warm-up | M2 |
| Replay throughput | a full trading day at ≥ 10× real time | M2 |
| Wire-to-callback on plain sockets, median / p99 | ≤ 5 µs / ≤ 25 µs above the NIC or kernel timestamp | M3, live |

The numbers are a judgment of what a careful single-threaded handler achieves on plain sockets, not
measurements. M2 either confirms them or resets them, and this table is updated with what was
measured. Replay can only confirm processing time; the wire-to-callback row needs M3's live source.

## Hot-path rules (enforced in code review from day one)

| # | Rule | How we check |
|---|---|---|
| P1 | **No heap allocation after warm-up.** All containers are sized in advance from config. | A test that counts allocations during a replay after warm-up must see zero (via a replaced `operator new`). |
| P2 | **No exceptions.** Errors are return codes plus counters. | Hot-path functions marked `noexcept`. Review. |
| P3 | **No virtual calls.** Templates or concepts for Consumer and RecoveryStrategy. | Review. |
| P4 | **No copying of packet payload**, except packets held in the gap buffer (copied into a pool). | Review. Message views take spans. |
| P5 | **No locks and no atomics** in the single-threaded core. | Review. |
| P6 | **No floating point** in prices or quantities. | Strong types have no conversion to floating point. |
| P7 | **No wall-clock reads.** Time comes from the packet. | Core has no `<chrono>` clock calls outside of instrumentation. |
| P8 | **No logging or I/O.** Counters and the anomaly ring only. | Review. |
| P9 | **Predictable memory access.** Dense arrays by index, and hash lookups only for `OrderID`. | Review. Benchmarks. |

## Measure before optimizing

- Microbenchmarks per module (decode, book operations, arbitration) once M1 exists.
- Throughput replay benchmark with `NullConsumer`: packets/s and ns/packet histogram.
- **Replacing a data structure requires a benchmark on real pcaps.**

## Path to production latency (not in M1)

In roughly increasing cost:

1. Flat open-addressing `OrderMap` with capacity reserved up front.
2. Huge pages for the order map and books.
3. Thread pinning, `isolcpus`, busy-poll loop.
4. `recvmmsg` batching and hardware timestamps.
5. Kernel bypass (ef_vi / Onload / DPDK) behind the `Packet` contract.
6. Profile-guided optimization and LTO for the release preset.
7. L3 intrusive queues, only if needed.

Nothing on this list starts until a measured number misses the budget above. Work down the list
only as far as needed to meet it.
