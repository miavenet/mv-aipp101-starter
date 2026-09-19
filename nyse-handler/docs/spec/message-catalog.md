# Message catalog

Everything the handler must decode, from **Integrated Feed v2.5h** (IF) and **Common Client v2.4s**
(CC). See [spec tracking](README.md) for the files and checksums, and
[field-layouts.md](field-layouts.md) for every offset.

Status key: ☐ not started · 🔍 layout transcribed · 🧪 hex fixture written · ✅ fixture reviewed by owner

Sizes are the **documented** sizes. CC §3.1.1 says clients "should never hard code msg sizes" and
must step through a packet using `MsgSize`, because a market may publish fewer trailing fields and a
release may add fields at the end. The decoder treats the documented size as a minimum.

## Packet level (CC §2 and §3)

| Item | Type code | Size | Status | Notes |
|---|---|---|---|---|
| Packet header | n/a | 16 | 🔍 | `PktSize`, `DeliveryFlag`, `NumberMsgs`, `SeqNum`, `SendTime`, `SendTimeNS`. Maximum packet 1400 bytes |
| Delivery flag values | n/a | n/a | 🔍 | 1 heartbeat · 10 failover · 11 original · 12 sequence number reset · 13 only packet of a retransmission · 15 part of a retransmission · 17 only packet of a refresh · 18 start of refresh · 19 part of a refresh · 20 end of refresh · 21 message unavailable |
| Message header | n/a | 4 | 🔍 | `MsgSize`, `MsgType`, both 2-byte little-endian |

## Control and reference messages (CC §4)

| Message | Type code | Size | Status | Book effect |
|---|---|---|---|---|
| Sequence Number Reset | 1 | 14 | 🔍 | Clear the channel. Resync. Always alone in its packet, with `SeqNum` 1 |
| Source Time Reference | 2 | 16 | 🔍 | Seconds part of the timestamp, published each second **per matching-engine partition** (the `ID` field), not per symbol |
| Symbol Index Mapping | 3 | 44 | 🔍 | Create or update `SymbolEntry`: ticker, `PriceScaleCode`, `SystemID`, lot size |
| Symbol Clear | 32 | 20 | 🔍 | Clear the symbol's book. Carries `NextSourceSeqNum` |
| Security Status | 34 | 46 | 🔍 | Status event: halts, short-sale restriction, market session changes |

## Order messages (IF §2 to §8)

| Message | Type code | Size | Status | Book effect |
|---|---|---|---|---|
| Add Order | 100 | 39 | 🔍 | Insert |
| Modify Order | 101 | 35 | 🔍 | Set the new price and quantity |
| Delete Order | 102 | 25 | 🔍 | Remove |
| Order Execution | 103 | 42 | 🔍 | Reduce by the executed quantity, emit Trade |
| Replace Order | 104 | 42 | 🔍 | Remove the old order, insert under `NewOrderID` |
| Add Order Refresh | 106 | 43 | 🔍 | Refresh channels, or after a Symbol Clear. Decoded, not exercised in M1 |

## Trade and auction messages (IF §7, §9 to §14)

| Message | Type code | Size | Status | Book effect |
|---|---|---|---|---|
| Imbalance | 105 | 73 | 🔍 | Imbalance event. Carries a full `SourceTime`, unlike the order messages |
| Non-Displayed Trade | 110 | 33 | 🔍 | Trade event only |
| Cross Trade | 111 | 29 | 🔍 | Trade event only |
| Trade Cancel | 112 | 20 | 🔍 | TradeCorrection event |
| Cross Correction | 113 | 24 | 🔍 | TradeCorrection event |
| Retail Price Improvement | 114 | 17 | 🔍 | Event only. Confirmed still in v2.5h |
| Stock Summary | 223 | 36 | 🔍 | Event only. Sent on a **separate** Stock Summary channel every 60 s |

The list matches the spec's table of contents exactly: nothing was added or removed compared with
the list drafted before the spec was fetched. Request-server messages (types 10 to 15, 31, 35) are
out of scope for M1, which has no recovery.

## Semantic questions, answered from the spec

- [x] **Modify Order and priority.** The message has a `PositionChange` field: 0 kept position,
      1 lost position. "If the price … didn't change, order always keeps the position … If the price
      … changed, the order always loses position." The same field is described as "Currently
      defaulted to 0", so it cannot be relied on; derive it from the price. (IF §3)
- [x] **Replace Order.** Carries `OrderID` and `NewOrderID`. The new order has "the same symbol,
      side and attribution", so the side cannot change. A `Side` field was added in v2.5. There is
      no `FirmID`, so attribution is inherited from the old order. (IF §6)
- [x] **Order Execution quantity.** `Volume` is the **executed** quantity. The order is fully
      executed when it "equals the number of shares previously remaining". The execution price may
      differ from the order's price, and "any remaining shares keep their original price". (IF §5)
- [x] **Price scaling.** Per symbol, from `PriceScaleCode` in Symbol Index Mapping. Valid codes are
      6, 4 and 3. Prices are signed 4-byte integers and are never negative. (CC §3.5, §4.3)
      ⚠ The formula itself is an equation that does not extract as text. Its glyphs read
      Price = Numerator / 10^PriceScaleCode, and the maximum-price table agrees (code 6 gives
      $2,147.48). **Owner to confirm by eye during fixture review.**
- [x] **Heartbeats.** `DeliveryFlag` 1, `NumberMsgs` 0, and a heartbeat "does not increment the next
      expected sequence number". Once a second on data channels. (CC §2.2)
      ⚠ The spec does not say what `SeqNum` holds in a heartbeat. Do not use it for gap detection
      until a real capture shows its behaviour.
- [x] **Failover.** Flag 10 marks every packet of a failover refresh except heartbeats. The sequence
      is: sequence number reset in its own packet, then per symbol a Symbol Index Mapping, a Symbol
      Clear, the last Security Status, refresh messages, and the last Source Time Reference. Flags
      then return to 11. A Sequence Number Reset itself carries flag 12 normally and 10 during
      failover. (CC §4.1, §8.2)
- [x] **Symbol Index Mapping mid-session.** Yes, it can repeat. The symbol-to-index pairing never
      changes, but "the latest field values override any earlier values, but do not apply
      retroactively". So a price scale may change during the day. (CC §3.6.3)

## Findings that affect the design

1. **The time base is per partition.** Order messages carry only `SourceTimeNS`. The seconds come
   from the last Source Time Reference for the symbol's partition, linked through `SystemID` in
   Symbol Index Mapping. The handler needs a small per-channel table of seconds keyed by partition
   ID. The design docs do not yet describe this.
2. **An Add Order may reuse a live-looking `OrderID`.** An order that was routed away and returned
   is re-published "with the same order ID". A duplicate add is therefore not always an anomaly.
   (IF §2)
3. **Close of day sends no deletes.** "A Security Status 'X' is sent and unexecuted orders are
   cancelled, but explicit Delete Order Messages are not sent." The book must clear a symbol on
   market state `X`. Session changes, by contrast, do send explicit deletes. (IF §4)
4. **Stock Summary is on its own channel**, so a main-channel pcap will not contain type 223. The
   M1 synthetic pcap needs a second channel to cover it.
5. **Documented sizes are minimums.** Already reflected in
   [04-pillar-decoding](../design/04-pillar-decoding.md); the planned
   `static_assert(total_size == documented MsgSize)` stays valid as a check on our own tables.
6. **Inconsistency in the spec.** CC §3.6 opens by calling both Order ID and Trade ID "8 byte
   integers", then §3.6.1 and every message table give Trade ID 4 bytes. The tables win.
7. **Imbalance per-market columns.** The Imbalance table has four columns saying which markets
   populate each field. Their headings are rotated text and do not extract. For NYSE-only scope this
   matters for `MarketImbalanceQty`, `SSRFilingPrice`, `IndicativeMatchPrice`, the collars,
   `NumExtensions` and `UnpairedQty`. **Owner to read the column headings from the PDF.**
