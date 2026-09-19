# ADR-0005: Single thread, synchronous in-process consumer

- **Status:** Accepted
- **Date:** 2026-09-19

## Context

The production consumer is a trading strategy in the same process. Correctness
comes first, and there is no latency target yet, but the design must stay aware of latency.

## Decision

- M1 runs the whole pipeline on **one thread**, with the consumer invoked
  **synchronously**.
- `FeedHandler<Consumer>` is a template, and the `Consumer` concept is checked at compile time.
- Production scales by running **one pinned thread per channel group**. Channels share no state.
- Any decoupling (an SPSC ring, fan-out to other threads) is written as a **Consumer adapter**.

## Alternatives considered

| Option | Why not (now) |
|---|---|
| SPSC ring to consumer threads | Adds a queue-full policy and latency. Not needed for an in-process strategy. |
| Shared-memory or network republish | Different product (a market data server). |
| Virtual consumer interface | Indirect call per event on the hot path. |

## Consequences

- A slow consumer stalls the feed and can cause gaps. That is documented as the consumer's responsibility.
- Deterministic replay: identical input gives identical output, on any machine.
