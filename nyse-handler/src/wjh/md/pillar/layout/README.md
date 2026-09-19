# pillar/layout

Offset tables transcribed from the NYSE specs. **This is the only place byte offsets are written down.**

## Conventions (planned)

```cpp
// Integrated Feed v<X>, §<section>, Table <n>: Add Order
namespace wjh::md::pillar::layout::add_order {
inline constexpr std::size_t order_id = /* from spec */;
// ...
inline constexpr std::size_t size = /* from spec */;
}
```

- One header per message group, e.g. `PacketHeader.hpp`, `OrderMessages.hpp`, `TradeMessages.hpp`, `ReferenceMessages.hpp`.
- Each table ends with a `static_assert` that its last field's offset + width equals `size`.
- A change here requires a matching fixture change in `../../tests/fixtures/`.

**Empty until the spec version is recorded in [docs/spec/README.md](../../../../../docs/spec/README.md).**
