# ADR-0007: Synthetic testing with hex fixtures and reference oracle

- **Status:** Accepted
- **Date:** 2026-09-19

## Context

No real sample pcap is available yet. If the test encoder and the decoder are
written from the same reading of the spec, a misread offset breaks both in the same way and the tests still pass.

## Decision

Testing is built in layers:

1. **Hand-written hex fixtures** per message type, taken from the spec byte by byte,
   **reviewed by the project owner**. They are the only check against the spec that doesn't depend on our code, and
   they are written **before** the encoder.
2. A test-only `PillarEncoder` + `PcapWriter`, with an `encode`/`decode` round-trip property.
3. A deliberately simple `std::map`-based **ReferenceBook** as the oracle, compared with the real
   book after every event under RapidCheck-generated valid sequences.
4. A/B arbitration properties (drops, reordering, duplicates).
5. Book invariant checks in debug builds.
6. Golden event dumps once real pcaps exist.

## Alternatives considered

| Option | Why not |
|---|---|
| Wait for real pcaps | Blocks all progress. Real data rarely covers the edge cases. |
| Encoder-only synthetic tests | Shared misreadings go undetected. |

## Consequences

- The owner's review of the fixtures is on the critical path for M1.
- The reference book must stay obviously correct, with no optimizations, ever.
