# tests

Unit tests, property tests, and spec-conformance tests for `wjh::md`. Uses doctest + RapidCheck.

## Planned layout

| Path | Covers | Strategy layer |
|---|---|---|
| `fixtures/` | Hand-written hex bytes per message type, **reviewed by the owner** | 1 |
| `pillar_fixture_test.cpp` | Decode each fixture and assert every field | 1 |
| `pillar_roundtrip_test.cpp` | `decode(encode(m)) == m` | 2 |
| `io_pcap_test.cpp` | Reader formats + robustness | 7 |
| `book_oracle_test.cpp` | Real book vs `ReferenceBook` | 3 |
| `book_invariant_test.cpp` | Invariants + anomaly handling | 3, 5 |
| `arb_property_test.cpp` | Drops, reordering, duplicates, reset, window | 4 |
| `e2e_replay_test.cpp` | Synthetic pcap → golden dump | 6 |
| `no_alloc_test.cpp` | Zero allocations after warm-up | 7 |

See [test strategy](../../../../docs/testing/test-strategy.md).
