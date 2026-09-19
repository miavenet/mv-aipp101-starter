# Glossary

| Term | Meaning |
|---|---|
| **Pillar** | NYSE's trading and market data platform. Its market data feeds share a common binary framing (XDP). |
| **Integrated Feed** | The Pillar feed carrying order-by-order data plus trades, imbalances, and status in one stream. |
| **XDP** | The binary protocol family (packet header, delivery flags) used by Pillar feeds. |
| **Channel** | One multicast stream. Symbols are split across channels, each with its own `SeqNum` space. |
| **Line A / Line B** | Two redundant copies of each channel on separate networks. |
| **Arbitration** | Merging A and B into one in-order stream: the first copy to arrive wins and duplicates are dropped. |
| **Gap** | A missing sequence range that neither line delivered within the gap window. |
| **Gap window** | How long, in packet time, the arbiter waits for the other line before declaring a gap. |
| **Stale** | Channel state after an unrecovered gap. Updates continue, flagged as possibly wrong. |
| **Sequence reset** | A packet that restarts a channel's sequence numbering. The channel's books are cleared. |
| **Refresh** | A snapshot of book state sent by the exchange for recovery. Not captured in our pcaps. |
| **Retransmission** | Resending specific sequence ranges on request. Not used in M1. |
| **L1 / L2 / L3** | Best bid/offer / aggregated price levels / individual orders in queue order. |
| **Symbol Index** | A numeric symbol id from Symbol Index Mapping. Used to index books densely. |
| **Price scale** | The per-symbol power of ten that turns an integer wire price into a decimal price. |
| **Hot path** | Code executed per packet, from receive to the return of the consumer callback. |
| **Warm-up** | Startup and first packets, during which allocation is allowed. |
| **Golden file** | A reviewed, expected event dump that tests diff against. |
| **Oracle** | The deliberately simple `ReferenceBook` that the real book is compared against. |
