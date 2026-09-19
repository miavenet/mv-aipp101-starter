# 04 — Pillar decoding

## Wire format basics

- Binary, **little-endian** (to be confirmed against the spec's data-type section).
- A packet is a header followed by `NumberMsgs` messages.
- Every message starts with `MsgSize` and `MsgType`, so unknown types can be skipped.

The exact field offsets live **only** in the offset tables, and each one cites the spec.
See [spec tracking](../spec/README.md).

## Views that read the packet in place

Each message type gets a small read-only **view** over `std::span<const std::byte>`:

```cpp
// Shape sketch. Real offsets come from the spec tables.
class AddOrderView {
public:
    explicit AddOrderView(std::span<const std::byte> bytes);
    OrderId     order_id()     const;   // load_le<std::uint64_t>(bytes_, off::add_order::order_id)
    SymbolIndex symbol_index() const;
    RawPrice    price()        const;
    Volume      volume()       const;
    Side        side()         const;
    // ...
private:
    std::span<const std::byte> bytes_;
};
```

- Fields are read with `std::memcpy` into a local variable (or `std::bit_cast` of a byte
  array), then converted from little-endian if the host differs. The compiler
  reduces this to a single load.
- **Never** `reinterpret_cast` to packed structs. Misaligned access and
  strict-aliasing violations are undefined behaviour and trip UBSan.
  ([ADR-0006](../decisions/0006-memcpy-views-no-reinterpret-cast.md))
- Returned values are Atlas strong types (`OrderId`, `SymbolIndex`, `SeqNum`,
  `RawPrice`, `Volume`, …), so fields can't be swapped by mistake.

## Offset tables

- One `constexpr` table per message type in `pillar/layout/`, with a comment
  citing **spec version, section, and table**.
- `static_assert(total_size == documented MsgSize)` per message type.
- The hex fixtures in `tests/fixtures/` are the independent check.
  See [fixture review](../testing/fixture-review-checklist.md).

## Validation: once per packet, at the edge

1. `payload.size() >= packet_header_size`
2. `PktSize == payload.size()`. A mismatch means the packet is malformed.
3. For each of the `NumberMsgs` messages: `MsgSize >= 4`, the message fits in the remaining bytes,
   and `MsgSize >= min_size(MsgType)` for known types.
4. Bytes left over after the last message mean the packet is malformed.

After this pass, the decoder and views need **no further bounds checks**.

## Dispatch

`switch (MsgType)` over the known types, calling a typed handler on the
`BookSet` or event layer. Unknown types are skipped using `MsgSize` and counted in `unknown_msg_type[type]`
(a small fixed map). This keeps the decoder tolerant of new spec versions.

Messages are **newer or longer than expected** when `MsgSize` exceeds the known size.
They are accepted: the known fields are read, the trailing bytes ignored, and the case counted as
`oversized_msg`. Pillar adds fields at the end.

## Errors

| Where | Mechanism |
|---|---|
| Hot path (framing, decode) | `enum class DecodeError` returned, and counters incremented. **No exceptions.** |
| Edges (config, file open, startup) | `tl::expected<T, Error>`, consistent with the host repo. |

### Malformed packets

The **whole packet** is dropped and treated as a **gap** over its sequence range.
The arbiter handles it like a loss, so the other line may still fill the gap.

### Messages that are well framed but semantically wrong

Examples: delete or execute for an unknown `OrderID`, add with a duplicate `OrderID`,
execution larger than the remaining quantity, message for an unmapped `SymbolIndex`.
→ Count it, record it in the anomaly ring, **continue**. The policy is configurable later (e.g.
mark the channel stale on the first anomaly). See [05](05-order-book.md#anomaly-handling).
