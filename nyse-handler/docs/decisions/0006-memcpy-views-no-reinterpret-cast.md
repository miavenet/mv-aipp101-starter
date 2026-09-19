# ADR-0006: Views read with memcpy; no packed-struct casts

- **Status:** Accepted
- **Date:** 2026-09-19

## Context

Pillar messages are little-endian binary with fields at arbitrary alignments.
The repo builds with ASan (and we add UBSan). Decoding must be fast and never copy the packet.

## Decision

- Each message type has a read-only **view** over a `std::span<const std::byte>`.
- Fields are read via `std::memcpy` (or `std::bit_cast` of a byte array) at
  `constexpr` offsets, with endian conversion where needed.
- Offsets live in per-message tables citing spec version, section, and table, with
  `static_assert`s on total size.
- Framing is validated **once per packet**. After that, views assume their bounds are valid.

## Alternatives considered

| Option | Why not |
|---|---|
| `reinterpret_cast` to `#pragma pack` structs | Undefined behaviour (alignment, aliasing), trips UBSan, not portable. |
| Deserialize into owned structs | Copies every message, for no benefit. |
| Code generation from the spec | Worth revisiting once several markets are in. Too much setup for M1. |

## Consequences

- Hand-written offset tables are the main risk of error. Mitigated by the independent hex fixtures (ADR-0007).
- Views must not outlive the packet.
