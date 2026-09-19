# pillar

**Responsibility:** Pillar/XDP framing validation and views over messages that read the packet in place. Namespace `wjh::md::pillar`.

## Planned contents

| Path | Contents |
|---|---|
| `layout/` | One `constexpr` offset table per message plus the packet header. **Every entry cites the spec version, section, and table.** `static_assert`s on sizes. See [layout/README.md](layout/README.md). |
| `PacketView.hpp` | Packet header accessors + `validate()` → `DecodeError` |
| `MessageViews.hpp` | `AddOrderView`, `ModifyOrderView`, `ReplaceOrderView`, `DeleteOrderView`, `ExecutionView`, `SymbolIndexMappingView`, `SecurityStatusView`, `ImbalanceView`, trade views, … |
| `DeliveryFlag.hpp`, `MsgType.hpp` | Enums, **values from the spec only** |
| `Decoder.hpp` | Template `decode(packet, Handler&)`: validate once, then `switch (MsgType)`, then typed callbacks. Unknown types are skipped by `MsgSize`. |
| `DecodeError.hpp` | `enum class DecodeError` |

## Rules
- `std::memcpy` / `std::bit_cast` loads only. **No `reinterpret_cast` to structs.**
- Validation happens once per packet. Views assume their bounds are valid.
- No exceptions, no allocation.

## Depends on
core

## Design refs
[04: Pillar decoding](../../../../docs/design/04-pillar-decoding.md), [ADR-0006](../../../../docs/decisions/0006-memcpy-views-no-reinterpret-cast.md), [spec tracking](../../../../docs/spec/README.md)
