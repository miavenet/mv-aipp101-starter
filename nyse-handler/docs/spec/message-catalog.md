# Message catalog

The working list of everything the handler must decode. **Type codes, sizes, and
field layouts are intentionally blank.** They are filled in only from the recorded
spec version (see [spec tracking](README.md)).

Status key: ☐ not started · 🔍 layout transcribed · 🧪 hex fixture written · ✅ fixture reviewed by owner

## Packet level (XDP Common)

| Item | Type code | Size | Status | Notes |
|---|---|---|---|---|
| Packet header | n/a | TBV | ☐ | `PktSize`, `DeliveryFlag`, `NumberMsgs`, `SeqNum`, send time (s + ns) |
| Delivery flag values | n/a | n/a | ☐ | Heartbeat, failover, original, sequence reset, retrans, refresh, … |
| Message header | n/a | TBV | ☐ | `MsgSize`, `MsgType` |

## Control and reference messages

| Message | Type code | Size | Status | Book effect |
|---|---|---|---|---|
| Sequence Number Reset | TBV | TBV | ☐ | Clear the channel. Resync. |
| Source Time Reference | TBV | TBV | ☐ | Time base, if used by the Integrated Feed. **Verify.** |
| Symbol Index Mapping | TBV | TBV | ☐ | Create or update `SymbolEntry` (ticker, scale, channel) |
| Symbol Clear | TBV | TBV | ☐ | Clear the symbol's book |
| Security Status | TBV | TBV | ☐ | Status event (halt, open, close, …) |

## Order messages

| Message | Type code | Size | Status | Book effect |
|---|---|---|---|---|
| Add Order | TBV | TBV | ☐ | Insert |
| Modify Order | TBV | TBV | ☐ | Change price and/or qty |
| Replace Order | TBV | TBV | ☐ | Remove the old order, insert under the new ID |
| Delete Order | TBV | TBV | ☐ | Remove |
| Order Execution | TBV | TBV | ☐ | Reduce qty, emit Trade |
| Add Order Refresh | TBV | TBV | ☐ | Refresh only. Decode but not exercised in M1. |

## Trade and auction messages

| Message | Type code | Size | Status | Book effect |
|---|---|---|---|---|
| Non-Displayed Trade | TBV | TBV | ☐ | Trade event only |
| Cross Trade | TBV | TBV | ☐ | Trade event only |
| Trade Cancel | TBV | TBV | ☐ | TradeCorrection event |
| Cross Correction | TBV | TBV | ☐ | TradeCorrection event |
| Imbalance | TBV | TBV | ☐ | Imbalance event |
| Retail Price Improvement | TBV | TBV | ☐ | Event only. **Verify it is still in the latest spec.** |
| Stock Summary | TBV | TBV | ☐ | Event only. **Verify.** |

> **The list above comes from general knowledge of the feed and is itself to be
> verified.** Messages the latest spec adds or removes are reconciled here when the
> spec is fetched.

## Semantic questions to answer from the spec

- [ ] Modify Order: does a qty *increase* or a price change lose priority? (Matters only for L3; record it anyway.)
- [ ] Replace Order: does it carry the old ID and a new ID, and may the side change?
- [ ] Order Execution: is qty the executed amount or the remaining amount?
- [ ] How is `Price` scaled: a per-symbol `PriceScaleCode` from Symbol Index Mapping?
- [ ] Heartbeat `SeqNum` semantics (next expected?).
- [ ] Failover delivery flag: what should a handler do?
- [ ] Symbol Index Mapping: can it arrive mid-session and change the scale?
