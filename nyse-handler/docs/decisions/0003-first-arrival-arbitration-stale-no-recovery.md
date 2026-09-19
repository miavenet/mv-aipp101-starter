# ADR-0003: First-arrival A/B arbitration; stale-and-continue; no recovery

- **Status:** Accepted
- **Date:** 2026-09-19

## Context

The pcaps contain both A and B lines, start before the open, and contain
**no** refresh or retransmission traffic. The consumer is an in-process strategy.

## Decision

- Per channel, **the first packet to arrive with a given sequence number wins.** Duplicates are dropped.
- Out-of-order packets are buffered during a **gap window** measured in packet time.
  When it expires or the buffer fills, the gap is **declared**.
- On a declared gap: emit `ChannelStale`, skip the hole, **keep applying updates
  with the `Stale` flag**. The channel stays stale for the session unless a
  **sequence reset** occurs.
- Recovery goes behind a `RecoveryStrategy` concept. M1 provides only `NoRecovery`.

## Alternatives considered

| Option | Why not |
|---|---|
| Suppress output while stale | Loses accurate information about orders added after the gap. The consumer can choose to ignore stale updates itself. |
| Implement retransmission or refresh now | The pcaps can't exercise it. It would be untested code. |
| Wall-clock gap timeout | Breaks determinism. See ADR-0002. |

## Consequences

- A single double loss (the same sequence number missing on both lines) degrades a channel for the whole session. That is visible and tested.
- Consumers must respect the `Stale` flag.
- Adding recovery later is local to the arbiter and a new strategy.
