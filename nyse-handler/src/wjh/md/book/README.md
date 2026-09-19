# book

**Responsibility:** maintain full-depth L2 books and the order map.

## Planned contents

| File | Contents |
|---|---|
| `OrderMap.hpp` | `OrderId → OrderRecord`. Narrow interface. Starts as a reserved `std::unordered_map`. |
| `Level.hpp` | `{ RawPrice price; Volume qty; uint32 order_count; }` |
| `BookSide.hpp` | Sorted `std::vector<Level>`, **best at back**. Add, reduce, and remove qty at a price. |
| `Book.hpp` | Bids + asks, BBO accessors, `check_invariants()` (debug/test) |
| `BookSet.hpp/.cpp` | Dense `vector<SymbolEntry>` by `SymbolIndex`, order map, per-channel symbol lists, apply methods for each message kind |

## Rules
- Integer prices only. Capacities sized in advance from config, with overflow counted.
- Anomalies are counted and recorded in the anomaly ring, never thrown.
- Crossed books are allowed and flagged.

## Depends on
core, pillar (views as inputs), stats

## Design refs
[05: Order book](../../../../docs/design/05-order-book.md), [ADR-0004](../../../../docs/decisions/0004-l2-book-integer-prices.md)
