# 05 — Order book

## Output level

**L2, full depth.** For each symbol and side, every price level carries aggregated
quantity and order count. L1 (BBO) is derived from it.
([ADR-0004](../decisions/0004-l2-book-integer-prices.md))

## Components

```
BookSet
 ├── symbols : std::vector<SymbolEntry>        dense, indexed by SymbolIndex
 │     SymbolEntry { mapped?, ticker, price_scale, channel, Book book, status }
 ├── orders  : OrderMap                         OrderId → OrderRecord
 └── per-channel lists of symbols (for clearing on a sequence reset or symbol clear)

OrderRecord { SymbolIndex sym; Side side; RawPrice price; Volume qty; }

Book
 ├── bids : BookSide   (sorted vector of Level, best at back)
 └── asks : BookSide

Level { RawPrice price; Volume qty; std::uint32_t order_count; }
```

### Why each choice

| Choice | Reason |
|---|---|
| Dense `vector` by `SymbolIndex` | No hashing on the hot path. The Symbol Index Mapping message gives the index. |
| `OrderMap` behind a narrow interface | Starts as `std::unordered_map` with capacity reserved up front. Can become a flat open-addressing map without touching callers. |
| Sorted `vector<Level>` per side, **best at back** | Most activity is near the inside, so inserts and erases there touch few elements and a linear scan from the back beats a tree. **To be benchmarked** on real pcaps before any change. |
| Integer `RawPrice` + per-symbol scale | Exact. No floating point anywhere in the book. Conversion to text is done with integer arithmetic. |

## Message → book effect

The message names follow the Integrated Feed spec. The exact semantics of each field
are **to be verified** during implementation and recorded in the
[message catalog](../spec/message-catalog.md).

| Message | Book effect |
|---|---|
| Add Order | Insert order and add to its level (creating the level if needed). |
| Modify Order | Change price and/or qty. A price change moves the order between levels. Queue-priority semantics are irrelevant for L2 but noted for L3. |
| Replace Order | Remove the old order and insert a new one under the new `OrderID`. |
| Delete Order | Remove the order and reduce its level, erasing the level if it becomes empty. |
| Order Execution | Reduce qty by the executed amount, removing the order at zero. Also emit a `Trade` event. |
| Non-displayed / cross / trade-cancel / correction | No book effect. Emit `Trade` / `TradeCorrection` events. |
| Imbalance | No book effect. Emit an `Imbalance` event. |
| Security Status | Update `SymbolEntry.status` and emit a `Status` event. |
| Symbol Index Mapping | Create or overwrite `SymbolEntry` (ticker, scale, channel). |
| Symbol Clear | Remove all orders for the symbol and emit `BookCleared`. |

## Anomaly handling

| Anomaly | M1 behaviour |
|---|---|
| Unknown `OrderID` on modify/delete/execute | Count, record in the anomaly ring, ignore the message. |
| Duplicate `OrderID` on add | Count, record, **replace** the existing order. (Policy to revisit; see [open questions](../open-questions.md).) |
| Execution qty > remaining | Count, record, remove the order. |
| Unmapped `SymbolIndex` | Count, drop the message. |
| Crossed or locked book | **Allowed** (legitimate around auctions). Counted, not an error. |

## Invariants (checked after every event in debug builds)

1. Bids strictly descending and asks strictly ascending by price.
2. No level has `qty == 0` or `order_count == 0`.
3. For each level, `qty` equals the sum of its orders' qty and `order_count` equals the number of those orders.
4. Every `OrderRecord` refers to a mapped symbol and an existing level.
5. The total number of orders equals the sum of `order_count` across all levels.

The checks run **only** in debug and test builds, via a `check_invariants()` hook.

## Capacity

The order map, levels per side, and symbol table are **sized in advance from config**
(`capacity.max_orders`, `capacity.max_symbols`, …). After warm-up there are no allocations on the hot path.
Exceeding a capacity is counted and reported, not undefined behaviour.

## Path to L3

`OrderRecord` gets intrusive `prev`/`next` links and `Level` gets `head`/`tail`,
giving each level a FIFO queue at O(1) cost per operation. Callers don't change, because L2
aggregates stay as they are. Not built in M1.
