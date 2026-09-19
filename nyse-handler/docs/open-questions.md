# Open questions

Each question has an owner and the milestone it blocks. Close a question by linking the ADR or doc that answers it.

| # | Question | Blocks | Owner | Default until answered |
|---|---|---|---|---|
| ~~Q1~~ | ~~Exact spec version~~ **Closed:** Integrated Feed v2.5h and Common Client v2.4s, recorded in [spec tracking](spec/README.md) | n/a | Implementer | n/a |
| Q2 | Semantic questions: all seven [answered from the spec](spec/message-catalog.md#semantic-questions-answered-from-the-spec). Two need the owner's eye on the PDF: the price formula and the Imbalance per-market columns | M1 step 4 | Owner | Price = numerator / 10^PriceScaleCode |
| Q3 | Duplicate `OrderID` on add: replace, ignore, or mark stale? The spec says an order routed away and returned is re-added with the same ID, so this is not always an anomaly | M1 step 8 | Owner | Replace and count |
| Q4 | Should any anomaly (e.g. unknown `OrderID`) mark the channel stale? | M1 step 8 | Owner | No: count and continue |
| Q5 | Gap window default (1 ms) and buffer size: suitable for real A/B skew? | M2 | Owner | 1 ms / 1024 packets |
| Q6 | Is there an independent source (TAQ or vendor) for cross-checking real data? | M2 | Owner | n/a |
| Q7 | Production telemetry stack for `StatsSink` | M3 | Owner | Stderr |
| Q8 | Latency target (e.g. wire-to-callback p99) | M3 | Owner | None |
| ~~Q9~~ | ~~May spec PDFs be stored in the repo?~~ **Closed:** no. They are marked "All Rights Reserved" and the repo is public. Kept in the gitignored `docs/spec/pdf/`; version, URL and checksum are recorded | n/a | Owner | n/a |
| ~~Q10~~ | ~~Base branch~~ **Closed:** `nyse-feed-handler` is based on `add-yolo-mode` (keeps sk-home persistence) | n/a | Owner | n/a |
| Q11 | Time base is per matching-engine partition (Source Time Reference `ID`), not per symbol. Where does the per-partition seconds table live, and what timestamp does an event get before the first reference arrives? | M1 step 5 | Implementer | Table in the channel state. Seconds 0 and a counter until the first reference |
| Q12 | Close of day sends Security Status `X` and no deletes. Should the book clear the symbol on `X`? | M1 step 8 | Owner | Yes, clear on `X` |
| Q13 | Stock Summary (223) is on a separate channel. Include a second channel in the M1 synthetic pcap? | M1 step 12 | Owner | Yes |
