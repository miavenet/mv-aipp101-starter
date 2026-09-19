# handler

**Responsibility:** connect source → arbiter → decoder → books → consumer, and define the consumer-facing events.

## Planned contents

| File | Contents |
|---|---|
| `Events.hpp` | `EventHeader` + `BookUpdate`, `Trade`, `TradeCorrection`, `Imbalance`, `SecurityStatus`, `SymbolMapped`, `BookCleared`, `ChannelStale`, `ChannelReset`, `PacketEnd`; `EventFlags` |
| `Consumer.hpp` | `Consumer` concept + `NullConsumer` |
| `FeedHandler.hpp` | `template <Consumer C, RecoveryStrategy R = NoRecovery> class FeedHandler`, with `on_packet(const Packet&)` |
| `EventDumper.hpp/.cpp` | Deterministic text dump (the golden format) |

## Rules
- No virtual calls, allocation, or exceptions per packet.
- Book references handed to consumers are valid only during the callback.

## Depends on
core, pillar, arb, book, stats

## Design refs
[06: Consumer interface](../../../../docs/design/06-consumer-interface.md), [ADR-0005](../../../../docs/decisions/0005-single-thread-sync-consumer.md)
