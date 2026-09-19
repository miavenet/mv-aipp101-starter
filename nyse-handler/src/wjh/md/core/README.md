# core

**Responsibility:** vocabulary shared by every module. No logic beyond small value helpers.

## Planned contents

| File | Contents |
|---|---|
| `types.atlas` | Atlas strong types: `Price`/`RawPrice`, `PriceScale`, `Volume`, `OrderId`, `SymbolIndex`, `SeqNum`, `ChannelId`, `MsgType`, `Timestamp` (ns). Operators kept to the minimum each type needs. **No conversions to floating point.** |
| `Side.hpp`, `Line.hpp` | Small enums (`Bid`/`Ask`, `A`/`B`) |
| `Packet.hpp` | `Packet{ span<const byte> payload; Timestamp recv_ts; Line line; ChannelId channel; }` |
| `Endian.hpp` | `load_le<T>(span, offset)` via `std::memcpy` + byteswap if needed |
| `PriceFormat.hpp` | Integer price + scale → text, with no floating point |

## Depends on
Standard library and Atlas only.

## Design refs
[02](../../../../docs/design/02-input-sources.md#the-packet-contract), [ADR-0004](../../../../docs/decisions/0004-l2-book-integer-prices.md), [ADR-0006](../../../../docs/decisions/0006-memcpy-views-no-reinterpret-cast.md)
