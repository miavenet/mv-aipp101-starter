# testing/md

Test-only helpers. **Never linked into the library or the app.**

| File | Contents |
|---|---|
| `PillarEncoder.hpp/.cpp` | Builds Pillar messages and packets from typed values (mirror of the views) |
| `PcapWriter.hpp/.cpp` | Writes pcap/pcapng with Ethernet/IPv4/UDP framing for A and B lines |
| `LineSplitter.hpp` | Derives A/B streams from a perfect stream, with drops, duplicates, and reordering (for properties) |
| `ReferenceBook.hpp` | `std::map`-based L2 oracle. **Deliberately naive, never optimize.** |
| `Generators.hpp` | RapidCheck generators: valid and invalid event sequences, messages |
| `RecordingConsumer.hpp` | Stores events in memory for assertions |
| `Scenarios.hpp` | Named synthetic scenarios (e.g. `all_message_types_with_double_loss`) used by the E2E test |

Design refs: [test strategy](../../../../docs/testing/test-strategy.md), [ADR-0007](../../../../docs/decisions/0007-synthetic-testing-with-reference-oracle.md)
