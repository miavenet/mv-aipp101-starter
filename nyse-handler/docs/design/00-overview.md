# 00 — Overview

## Problem

Consume the NYSE Pillar **Integrated Feed** for NYSE-listed equities. Build
a correct, full-depth **L2** order book for every symbol and deliver
book, trade, imbalance, and security-status events to a trading strategy
running **in the same process**.

## Context

- The project starts as a **workshop exercise** and is expected to become
  **production** code. Captured **pcaps** feed it during development.
- The pcaps contain **both A and B lines** and **start before the open**. They
  contain **no refresh or retransmission** traffic.
- No real sample pcap is available yet, so all early testing uses
  **synthetic** data.

## Goals

| # | Goal |
|---|---|
| G1 | Decode every Integrated Feed message type in the current spec. |
| G2 | Maintain a full-depth L2 book (aggregated qty + order count per price) per symbol. |
| G3 | Arbitrate A/B lines per channel on first arrival and detect gaps. |
| G4 | Mark channels **stale** on unrecoverable gaps, and flag every update from a stale channel. |
| G5 | Replay pcap/pcapng captures to give deterministic, diffable output. |
| G6 | Share one core between pcap replay and live multicast, with the source chosen at startup. |
| G7 | Latency-aware design: hot-path rules from day one (see [08](08-performance-guidelines.md)). |
| G8 | Observable: per-channel counters, anomaly records, `StatsSink`. |

## Non-goals (for now)

- Other Pillar markets (Arca, American, National, Chicago). The design **allows**
  adding them but does not implement them.
- Options feeds.
- L3 (order-by-order) output. The design **allows** adding it (see [05](05-order-book.md#path-to-l3)).
- Active gap recovery (retransmission requests, refresh). The `RecoveryStrategy`
  seam exists, with `NoRecovery` as its only implementation.
- Kernel bypass, core pinning, and a latency SLO.
- Out-of-process consumers and multi-threaded fan-out.

## Constraints

- C++20, CMake presets, Atlas strong types, `tl::expected`, doctest, RapidCheck,
  and nlohmann/json, all consistent with the host repository.
- Builds and tests clean under ASan and UBSan.
- Byte layouts come **only** from the latest NYSE spec and are cited per field. Nothing is written from memory.
- No dependency on the host chat application code.

## Success criteria

See [Milestone 1 definition of done](../roadmap/milestones.md#m1--synthetic-end-to-end-replay).
