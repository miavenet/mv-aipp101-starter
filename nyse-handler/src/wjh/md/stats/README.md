# stats

**Responsibility:** make the handler observable without touching the hot path's latency.

## Planned contents

| File | Contents |
|---|---|
| `Counters.hpp` | Per-channel and global plain `uint64_t` counter structs |
| `AnomalyRing.hpp` | Fixed-size overwrite ring of `AnomalyRecord` |
| `LatencyHistogram.hpp` | Fixed-bucket ns histogram |
| `StatsSink.hpp` | Virtual interface (cold path) + `StatsSnapshot` |
| `StderrStatsSink.hpp/.cpp` | M1 implementation: formatted report to stderr |

## Depends on
core

## Design refs
[07: Observability](../../../../docs/design/07-observability.md), [ADR-0009](../../../../docs/decisions/0009-statssink-interface.md)
