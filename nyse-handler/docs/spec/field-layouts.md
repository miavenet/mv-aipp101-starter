# Field layouts

Transcribed from the specs recorded in [spec tracking](README.md): **Integrated Feed v2.5h** and
**Common Client v2.4s**. All binary fields are little-endian and messages are packed on 1-byte
boundaries (Common Client §3).

This file was generated from a table that is checked mechanically: within each message the fields
are contiguous with no gaps or overlaps, and the last field ends exactly at the documented size.
That check catches transcription slips. It does **not** prove the offsets match the PDF, which is
what the owner's hex-fixture review is for.

## Packet Header

Documented size: **16 bytes**. Source: Common Client v2.4s §2.1.1.

| Field | Offset | Size | Format |
|---|---|---|---|
| `PktSize` | 0 | 2 | Binary |
| `DeliveryFlag` | 2 | 1 | Binary |
| `NumberMsgs` | 3 | 1 | Binary |
| `SeqNum` | 4 | 4 | Binary |
| `SendTime` | 8 | 4 | Binary |
| `SendTimeNS` | 12 | 4 | Binary |

## Message Header

Documented size: **4 bytes**. Source: Common Client v2.4s §3.1.

| Field | Offset | Size | Format |
|---|---|---|---|
| `MsgSize` | 0 | 2 | Binary |
| `MsgType` | 2 | 2 | Binary |

## Sequence Number Reset (MsgType 1)

Documented size: **14 bytes**. Source: Common Client v2.4s §4.1.

| Field | Offset | Size | Format |
|---|---|---|---|
| `MsgSize` | 0 | 2 | Binary |
| `MsgType` | 2 | 2 | Binary |
| `SourceTime` | 4 | 4 | Binary |
| `SourceTimeNS` | 8 | 4 | Binary |
| `ProductID` | 12 | 1 | Binary |
| `ChannelID` | 13 | 1 | Binary |

## Source Time Reference (MsgType 2)

Documented size: **16 bytes**. Source: Common Client v2.4s §4.2.

| Field | Offset | Size | Format |
|---|---|---|---|
| `MsgSize` | 0 | 2 | Binary |
| `MsgType` | 2 | 2 | Binary |
| `ID` | 4 | 4 | Binary |
| `SymbolSeqNum` | 8 | 4 | Binary |
| `SourceTime` | 12 | 4 | Binary |

## Symbol Index Mapping (MsgType 3)

Documented size: **44 bytes**. Source: Common Client v2.4s §4.3.

| Field | Offset | Size | Format |
|---|---|---|---|
| `MsgSize` | 0 | 2 | Binary |
| `MsgType` | 2 | 2 | Binary |
| `SymbolIndex` | 4 | 4 | Binary |
| `Symbol` | 8 | 11 | ASCII |
| `Reserved` | 19 | 1 | Binary |
| `MarketID` | 20 | 2 | Binary |
| `SystemID` | 22 | 1 | Binary |
| `ExchangeCode` | 23 | 1 | ASCII |
| `PriceScaleCode` | 24 | 1 | Binary |
| `SecurityType` | 25 | 1 | ASCII |
| `LotSize` | 26 | 2 | Binary |
| `PrevClosePrice` | 28 | 4 | Binary |
| `PrevCloseVolume` | 32 | 4 | Binary |
| `PriceResolution` | 36 | 1 | Binary |
| `RoundLot` | 37 | 1 | ASCII |
| `MPV` | 38 | 2 | Binary |
| `UnitOfTrade` | 40 | 2 | Binary |
| `LateCloseEligible` | 42 | 1 | Binary |
| `ETHEligible` | 43 | 1 | Binary |

## Symbol Clear (MsgType 32)

Documented size: **20 bytes**. Source: Common Client v2.4s §4.4.

| Field | Offset | Size | Format |
|---|---|---|---|
| `MsgSize` | 0 | 2 | Binary |
| `MsgType` | 2 | 2 | Binary |
| `SourceTime` | 4 | 4 | Binary |
| `SourceTimeNS` | 8 | 4 | Binary |
| `SymbolIndex` | 12 | 4 | Binary |
| `NextSourceSeqNum` | 16 | 4 | Binary |

## Security Status (MsgType 34)

Documented size: **46 bytes**. Source: Common Client v2.4s §4.5.

| Field | Offset | Size | Format |
|---|---|---|---|
| `MsgSize` | 0 | 2 | Binary |
| `MsgType` | 2 | 2 | Binary |
| `SourceTime` | 4 | 4 | Binary |
| `SourceTimeNS` | 8 | 4 | Binary |
| `SymbolIndex` | 12 | 4 | Binary |
| `SymbolSeqNum` | 16 | 4 | Binary |
| `SecurityStatus` | 20 | 1 | ASCII |
| `HaltCondition` | 21 | 1 | ASCII |
| `Reserved` | 22 | 4 | Binary |
| `Price1` | 26 | 4 | Binary |
| `Price2` | 30 | 4 | Binary |
| `SSRTriggeringExchangeID` | 34 | 1 | ASCII |
| `SSRTriggeringVolume` | 35 | 4 | Binary |
| `Time` | 39 | 4 | Binary |
| `SSRState` | 43 | 1 | ASCII |
| `MarketState` | 44 | 1 | ASCII |
| `SessionState` | 45 | 1 | ASCII |

## Add Order (MsgType 100)

Documented size: **39 bytes**. Source: Integrated Feed v2.5h §2.

| Field | Offset | Size | Format |
|---|---|---|---|
| `MsgSize` | 0 | 2 | Binary |
| `MsgType` | 2 | 2 | Binary |
| `SourceTimeNS` | 4 | 4 | Binary |
| `SymbolIndex` | 8 | 4 | Binary |
| `SymbolSeqNum` | 12 | 4 | Binary |
| `OrderID` | 16 | 8 | Binary |
| `Price` | 24 | 4 | Binary |
| `Volume` | 28 | 4 | Binary |
| `Side` | 32 | 1 | ASCII |
| `FirmID` | 33 | 5 | ASCII |
| `Reserved1` | 38 | 1 | Binary |

## Modify Order (MsgType 101)

Documented size: **35 bytes**. Source: Integrated Feed v2.5h §3.

| Field | Offset | Size | Format |
|---|---|---|---|
| `MsgSize` | 0 | 2 | Binary |
| `MsgType` | 2 | 2 | Binary |
| `SourceTimeNS` | 4 | 4 | Binary |
| `SymbolIndex` | 8 | 4 | Binary |
| `SymbolSeqNum` | 12 | 4 | Binary |
| `OrderID` | 16 | 8 | Binary |
| `Price` | 24 | 4 | Binary |
| `Volume` | 28 | 4 | Binary |
| `PositionChange` | 32 | 1 | Binary |
| `Side` | 33 | 1 | ASCII |
| `Reserved2` | 34 | 1 | Binary |

## Delete Order (MsgType 102)

Documented size: **25 bytes**. Source: Integrated Feed v2.5h §4.

| Field | Offset | Size | Format |
|---|---|---|---|
| `MsgSize` | 0 | 2 | Binary |
| `MsgType` | 2 | 2 | Binary |
| `SourceTimeNS` | 4 | 4 | Binary |
| `SymbolIndex` | 8 | 4 | Binary |
| `SymbolSeqNum` | 12 | 4 | Binary |
| `OrderID` | 16 | 8 | Binary |
| `Reserved1` | 24 | 1 | Binary |

## Order Execution (MsgType 103)

Documented size: **42 bytes**. Source: Integrated Feed v2.5h §5.

| Field | Offset | Size | Format |
|---|---|---|---|
| `MsgSize` | 0 | 2 | Binary |
| `MsgType` | 2 | 2 | Binary |
| `SourceTimeNS` | 4 | 4 | Binary |
| `SymbolIndex` | 8 | 4 | Binary |
| `SymbolSeqNum` | 12 | 4 | Binary |
| `OrderID` | 16 | 8 | Binary |
| `TradeID` | 24 | 4 | Binary |
| `Price` | 28 | 4 | Binary |
| `Volume` | 32 | 4 | Binary |
| `PrintableFlag` | 36 | 1 | Binary |
| `Reserved1` | 37 | 1 | Binary |
| `TradeCond1` | 38 | 1 | ASCII |
| `TradeCond2` | 39 | 1 | ASCII |
| `TradeCond3` | 40 | 1 | ASCII |
| `TradeCond4` | 41 | 1 | ASCII |

## Replace Order (MsgType 104)

Documented size: **42 bytes**. Source: Integrated Feed v2.5h §6.

| Field | Offset | Size | Format |
|---|---|---|---|
| `MsgSize` | 0 | 2 | Binary |
| `MsgType` | 2 | 2 | Binary |
| `SourceTimeNS` | 4 | 4 | Binary |
| `SymbolIndex` | 8 | 4 | Binary |
| `SymbolSeqNum` | 12 | 4 | Binary |
| `OrderID` | 16 | 8 | Binary |
| `NewOrderID` | 24 | 8 | Binary |
| `Price` | 32 | 4 | Binary |
| `Volume` | 36 | 4 | Binary |
| `Side` | 40 | 1 | ASCII |
| `Reserved2` | 41 | 1 | Binary |

## Imbalance (MsgType 105)

Documented size: **73 bytes**. Source: Integrated Feed v2.5h §7.

| Field | Offset | Size | Format |
|---|---|---|---|
| `MsgSize` | 0 | 2 | Binary |
| `MsgType` | 2 | 2 | Binary |
| `SourceTime` | 4 | 4 | Binary |
| `SourceTimeNS` | 8 | 4 | Binary |
| `SymbolIndex` | 12 | 4 | Binary |
| `SymbolSeqNum` | 16 | 4 | Binary |
| `ReferencePrice` | 20 | 4 | Binary |
| `PairedQty` | 24 | 4 | Binary |
| `TotalImbalanceQty` | 28 | 4 | Binary |
| `MarketImbalanceQty` | 32 | 4 | Binary |
| `AuctionTime` | 36 | 2 | Binary |
| `AuctionType` | 38 | 1 | ASCII |
| `ImbalanceSide` | 39 | 1 | ASCII |
| `ContinuousBookClearingPrice` | 40 | 4 | Binary |
| `AuctionInterestClearingPrice` | 44 | 4 | Binary |
| `SSRFilingPrice` | 48 | 4 | Binary |
| `IndicativeMatchPrice` | 52 | 4 | Binary |
| `UpperCollar` | 56 | 4 | Binary |
| `LowerCollar` | 60 | 4 | Binary |
| `AuctionStatus` | 64 | 1 | Binary |
| `FreezeStatus` | 65 | 1 | Binary |
| `NumExtensions` | 66 | 1 | Binary |
| `UnpairedQty` | 67 | 4 | Binary |
| `UnpairedSide` | 71 | 1 | ASCII |
| `Reserved` | 72 | 1 | ASCII |

## Add Order Refresh (MsgType 106)

Documented size: **43 bytes**. Source: Integrated Feed v2.5h §8.

| Field | Offset | Size | Format |
|---|---|---|---|
| `MsgSize` | 0 | 2 | Binary |
| `MsgType` | 2 | 2 | Binary |
| `SourceTime` | 4 | 4 | Binary |
| `SourceTimeNS` | 8 | 4 | Binary |
| `SymbolIndex` | 12 | 4 | Binary |
| `SymbolSeqNum` | 16 | 4 | Binary |
| `OrderID` | 20 | 8 | Binary |
| `Price` | 28 | 4 | Binary |
| `Volume` | 32 | 4 | Binary |
| `Side` | 36 | 1 | ASCII |
| `FirmID` | 37 | 5 | ASCII |
| `Reserved1` | 42 | 1 | Binary |

## Non-Displayed Trade (MsgType 110)

Documented size: **33 bytes**. Source: Integrated Feed v2.5h §9.

| Field | Offset | Size | Format |
|---|---|---|---|
| `MsgSize` | 0 | 2 | Binary |
| `MsgType` | 2 | 2 | Binary |
| `SourceTimeNS` | 4 | 4 | Binary |
| `SymbolIndex` | 8 | 4 | Binary |
| `SymbolSeqNum` | 12 | 4 | Binary |
| `TradeID` | 16 | 4 | Binary |
| `Price` | 20 | 4 | Binary |
| `Volume` | 24 | 4 | Binary |
| `PrintableFlag` | 28 | 1 | Binary |
| `TradeCond1` | 29 | 1 | ASCII |
| `TradeCond2` | 30 | 1 | ASCII |
| `TradeCond3` | 31 | 1 | ASCII |
| `TradeCond4` | 32 | 1 | ASCII |

## Cross Trade (MsgType 111)

Documented size: **29 bytes**. Source: Integrated Feed v2.5h §10.

| Field | Offset | Size | Format |
|---|---|---|---|
| `MsgSize` | 0 | 2 | Binary |
| `MsgType` | 2 | 2 | Binary |
| `SourceTimeNS` | 4 | 4 | Binary |
| `SymbolIndex` | 8 | 4 | Binary |
| `SymbolSeqNum` | 12 | 4 | Binary |
| `CrossID` | 16 | 4 | Binary |
| `Price` | 20 | 4 | Binary |
| `Volume` | 24 | 4 | Binary |
| `CrossType` | 28 | 1 | ASCII |

## Trade Cancel (MsgType 112)

Documented size: **20 bytes**. Source: Integrated Feed v2.5h §11.

| Field | Offset | Size | Format |
|---|---|---|---|
| `MsgSize` | 0 | 2 | Binary |
| `MsgType` | 2 | 2 | Binary |
| `SourceTimeNS` | 4 | 4 | Binary |
| `SymbolIndex` | 8 | 4 | Binary |
| `SymbolSeqNum` | 12 | 4 | Binary |
| `TradeID` | 16 | 4 | Binary |

## Cross Correction (MsgType 113)

Documented size: **24 bytes**. Source: Integrated Feed v2.5h §12.

| Field | Offset | Size | Format |
|---|---|---|---|
| `MsgSize` | 0 | 2 | Binary |
| `MsgType` | 2 | 2 | Binary |
| `SourceTimeNS` | 4 | 4 | Binary |
| `SymbolIndex` | 8 | 4 | Binary |
| `SymbolSeqNum` | 12 | 4 | Binary |
| `CrossID` | 16 | 4 | Binary |
| `Volume` | 20 | 4 | Binary |

## Retail Price Improvement (MsgType 114)

Documented size: **17 bytes**. Source: Integrated Feed v2.5h §13.

| Field | Offset | Size | Format |
|---|---|---|---|
| `MsgSize` | 0 | 2 | Binary |
| `MsgType` | 2 | 2 | Binary |
| `SourceTimeNS` | 4 | 4 | Binary |
| `SymbolIndex` | 8 | 4 | Binary |
| `SymbolSeqNum` | 12 | 4 | Binary |
| `RPIIndicator` | 16 | 1 | ASCII |

## Stock Summary (MsgType 223)

Documented size: **36 bytes**. Source: Integrated Feed v2.5h §14.

| Field | Offset | Size | Format |
|---|---|---|---|
| `MsgSize` | 0 | 2 | Binary |
| `MsgType` | 2 | 2 | Binary |
| `SourceTime` | 4 | 4 | Binary |
| `SourceTimeNS` | 8 | 4 | Binary |
| `SymbolIndex` | 12 | 4 | Binary |
| `HighPrice` | 16 | 4 | Binary |
| `LowPrice` | 20 | 4 | Binary |
| `Open` | 24 | 4 | Binary |
| `Close` | 28 | 4 | Binary |
| `TotalVolume` | 32 | 4 | Binary |
