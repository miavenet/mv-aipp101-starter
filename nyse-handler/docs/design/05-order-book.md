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
| Security Status | Update `SymbolEntry.status` and emit a `Status` event. Market state `X` (closed) also clears the symbol's book: the feed sends no deletes at close. |
| Symbol Index Mapping | Create or overwrite `SymbolEntry` (ticker, scale, channel). |
| Symbol Clear | Remove all orders for the symbol and emit `BookCleared`. |

## Anomaly handling

| Anomaly | M1 behaviour |
|---|---|
| Unknown `OrderID` on modify/delete/execute | Count, record in the anomaly ring, ignore the message. |
| Duplicate `OrderID` on add | Count, record, **replace** the existing order. The feed re-adds a returned routed order under the same ID, so this is expected now and then. |
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

## Scenarios

Format and rules: [test strategy](../testing/test-strategy.md#scenarios). Field semantics are from
Integrated Feed v2.5h, as recorded in the [message catalog](../spec/message-catalog.md).

| ID | WHEN | THEN | Test |
|---|---|---|---|
| BOOK-01 | an Add Order arrives for a mapped symbol | the order exists, and its level (created if needed) gains its quantity and one order | `book: add inserts order and level` |
| BOOK-02 | a Modify Order changes only the quantity | the level's quantity changes by the difference and the order stays on its level | `book: modify quantity` |
| BOOK-03 | a Modify Order changes the price | the order moves to the new level, and the old level is erased if it is now empty | `book: modify price moves level` |
| BOOK-04 | a Delete Order arrives | the order is gone, its level shrinks, and the level is erased when empty | `book: delete removes order` |
| BOOK-05 | an Order Execution has `Volume` below the remaining quantity | the order shrinks by `Volume`, a `Trade` is emitted, and the remainder keeps its original price even if the execution price differs | `book: partial execution` |
| BOOK-06 | an Order Execution has `Volume` equal to the remaining quantity | the order is removed and a `Trade` is emitted | `book: full execution removes order` |
| BOOK-07 | a Replace Order arrives | the old order is removed, a new one exists under `NewOrderID` on the same side with the new price and quantity, and the old `OrderID` is unknown afterwards | `book: replace swaps order id` |
| BOOK-08 | a Symbol Clear arrives | every order of that symbol is removed, `BookCleared` is emitted, and other symbols are untouched | `book: symbol clear` |
| BOOK-09 | a second Symbol Index Mapping changes a symbol's `PriceScaleCode` | later events use the new scale and earlier ones are not rewritten | `book: repeated symbol mapping` |
| BOOK-10 | a Non-Displayed Trade, Cross Trade, Trade Cancel, Cross Correction, Imbalance, Retail Price Improvement or Stock Summary arrives | the book is unchanged and the matching event is emitted | `book: event-only messages leave book unchanged` |
| BOOK-11 | a Security Status arrives | `SymbolEntry.status` is updated and a `Status` event is emitted | `book: security status` |
| BOOK-12 | a Security Status moves a symbol to market state `X` (closed) | the symbol's book is cleared, because the feed sends no deletes at close | `book: close clears symbol` |
| BOOK-A1 | a modify, delete or execution names an unknown `OrderID` | it is counted, recorded in the anomaly ring, and ignored | `book anomaly: unknown order id` |
| BOOK-A2 | an Add Order reuses a live `OrderID` | it is counted, recorded, and replaces the existing order | `book anomaly: duplicate add` |
| BOOK-A3 | an execution's `Volume` exceeds the remaining quantity | it is counted, recorded, and the order is removed | `book anomaly: over-execution` |
| BOOK-A4 | a message names an unmapped `SymbolIndex` | it is counted and dropped | `book anomaly: unmapped symbol` |
| BOOK-A5 | the book becomes crossed or locked | it is allowed and counted, and the invariants still hold | `book anomaly: crossed book allowed` |
| BOOK-C1 | a configured capacity (orders, levels, symbols) is exceeded | it is counted and reported, with no undefined behaviour | `book capacity: overflow is counted` |
| BOOK-P1 | a random sequence of valid events is applied to `Book` and to `ReferenceBook` | after every event the L2 views are equal and the invariants hold | `book property: matches reference oracle` |
| BOOK-P2 | a random sequence that includes invalid events is applied | anomalies are counted and the invariants never break | `book property: invalid events keep invariants` |
