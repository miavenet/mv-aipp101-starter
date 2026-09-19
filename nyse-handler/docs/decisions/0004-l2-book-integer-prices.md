# ADR-0004: Full-depth L2 book with integer prices

- **Status:** Accepted
- **Date:** 2026-09-19

## Context

The consumer needs price-level depth, not queue position. Every event type
must be decoded.

## Decision

- Maintain **L2, full depth** (qty + order count per level), with L1 derived from it.
- Keep an `OrderID → OrderRecord` map (required: deletes and executes carry only the ID).
- Prices are **integer** `RawPrice` + a per-symbol scale from Symbol Index Mapping, as
  Atlas strong types with no floating-point conversion.
- Books are stored in a dense vector indexed by `SymbolIndex`. Each side is a sorted `vector<Level>` with the best price at the back.
- Decode **all** message types and expose each on the consumer interface.

## Alternatives considered

| Option | Why not (now) |
|---|---|
| L3 | Not needed by the consumer. More memory. The design keeps a path to it open. |
| Top-N only | The consumer wants full depth. Truncation would hide levels. |
| `double` prices | Inexact. Equality comparisons on price levels break. |
| `std::map` levels | Allocates per node and is cache-unfriendly. Kept only as the test oracle. |

## Consequences

- Vector levels are a bet on activity concentrating near the inside. It must be benchmarked on real pcaps.
- Printing prices needs integer formatting with a scale.
