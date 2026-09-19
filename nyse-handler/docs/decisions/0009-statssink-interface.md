# ADR-0009: Counters + `StatsSink` interface, no logging library

- **Status:** Accepted
- **Date:** 2026-09-19

## Context

Correctness first means we must be able to see what the handler did. Production will
eventually plug into an as-yet-unspecified telemetry stack.

## Decision

- Plain per-channel counters owned by the handler thread, plus a fixed-size
  anomaly ring. Nothing on the hot path allocates or does I/O.
- A **`StatsSink`** interface (virtual, cold path). M1 implementation:
  `StderrStatsSink`, which prints at the end of a replay and on `SIGUSR1`.
- A deterministic `--dump-events` text format, which doubles as the golden-test format.
- No logging library. `std::format` to stderr at the edges.

## Alternatives considered

| Option | Why not (now) |
|---|---|
| spdlog or similar | New dependency. Tempts people to log on the hot path. |
| Prometheus client now | The production stack is unknown. The interface keeps the option open. |

## Consequences

- Multi-threaded production will need a snapshot mechanism (seqlock or double buffer) for the counters.
- Changing the dump format is a breaking change to the golden tests.
