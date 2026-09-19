# 06 — Consumer interface

## Delivery model

A **synchronous, in-process callback** on the handler thread. The consumer must not
block. A slow consumer stalls the feed, which can cause gaps.
([ADR-0005](../decisions/0005-single-thread-sync-consumer.md))

## Consumer concept (shape sketch, not implementation)

```cpp
template <class C>
concept Consumer = requires(C c,
                            const BookUpdate& bu, const Trade& t,
                            const TradeCorrection& tc, const Imbalance& im,
                            const SecurityStatus& st, const SymbolMapped& sm,
                            const BookCleared& bc, const ChannelStale& cs,
                            const ChannelReset& cr, const PacketEnd& pe) {
    c.on_book_update(bu);
    c.on_trade(t);
    c.on_trade_correction(tc);
    c.on_imbalance(im);
    c.on_status(st);
    c.on_symbol_mapped(sm);
    c.on_book_cleared(bc);
    c.on_channel_stale(cs);
    c.on_channel_reset(cr);
    c.on_packet_end(pe);          // batching hook: all messages in this packet delivered
};
```

A `NullConsumer` base class with empty inline handlers lets a consumer
override only the events it cares about. There are still no virtual calls, because the
concept is checked at compile time.

## Common event header

Every event carries:

| Field | Purpose |
|---|---|
| `channel` | `ChannelId` |
| `seq` | Sequence number of the message that caused the event |
| `recv_ts` | Receive timestamp (pcap capture time or NIC time) |
| `send_ts` | Exchange `SendTime` from the Pillar packet header |
| `flags` | Bit set (below) |

### Flags

| Flag | Meaning |
|---|---|
| `Stale` | The channel has had an unrecovered gap. This update is applied but the book may be wrong. |
| `LastInPacket` | Last event produced by this packet. Consumers may batch on it. |
| `Crossed` | After this update, best bid ≥ best ask. |

## BookUpdate

| Field | Notes |
|---|---|
| `symbol` | `SymbolIndex`. The ticker is available from `BookSet`. |
| `side` | `Bid` / `Ask` |
| `action` | `LevelAdded`, `LevelChanged`, `LevelRemoved` |
| `price` | `RawPrice` (+ scale available on the symbol) |
| `level_qty`, `level_orders` | Level totals **after** the change |
| `cause` | Message kind that caused it: add, modify, replace, delete, or execute |

A single message can produce **two** updates (a modify or replace across price
levels: remove from the old level, add to the new one). Both carry the same `seq`.

## Access to the full book

During any callback the consumer may read `const Book&` for any symbol from
`BookSet`, for example to recompute a microprice. Book references are valid only during the callback.

## Built-in consumers (planned)

| Consumer | Location | Purpose |
|---|---|---|
| `EventDumper` | `handler/` | Writes the deterministic text format (see [07](07-observability.md#event-dump-format)) |
| `RecordingConsumer` | `testing/md/` | Stores events in memory for test assertions |
| `NullConsumer` | `handler/` | Throughput benchmarks |
| `RingConsumer` (future) | `handler/` | Adapter that forwards to an SPSC ring for other threads |
