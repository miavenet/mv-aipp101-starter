# Open questions

Each question has an owner and the milestone it blocks. Close a question by linking the ADR or doc that answers it.

| # | Question | Blocks | Owner | Default until answered |
|---|---|---|---|---|
| ~~Q1~~ | ~~Exact spec version~~ **Closed:** Integrated Feed v2.5h and Common Client v2.4s, recorded in [spec tracking](spec/README.md) | n/a | Implementer | n/a |
| ~~Q2~~ | ~~Semantic questions~~ **Closed:** all seven [answered from the spec](spec/message-catalog.md#semantic-questions-answered-from-the-spec). The price formula and the Imbalance per-market columns were both recovered from the PDF and cross-checked | n/a | Implementer | n/a |
| ~~Q3~~ | ~~Duplicate `OrderID` on add~~ **Closed 2026-09-19:** replace the existing order and count it. The spec re-adds a returned routed order under the same ID, so it is not always an anomaly. [BOOK-A2](design/05-order-book.md#scenarios) | n/a | Owner | n/a |
| ~~Q4~~ | ~~Should an anomaly mark the channel stale?~~ **Closed 2026-09-19:** no. Count, record in the anomaly ring, continue. Revisit only with evidence from real pcaps. [BOOK-A1 to A5](design/05-order-book.md#scenarios) | n/a | Owner | n/a |
| Q5 | Gap window default (1 ms) and buffer size: suitable for real A/B skew?  **Deferred:** needs real A/B captures; the default holds until then | M2 | Owner | 1 ms / 1024 packets |
| Q6 | Is there an independent source (TAQ or vendor) for cross-checking real data?  **Deferred:** only the owner knows what data is available; the default holds until then | M2 | Owner | n/a |
| Q7 | Production telemetry stack for `StatsSink`  **Deferred:** a production decision; the default holds until then | M3 | Owner | Stderr |
| Q8 | Latency target (e.g. wire-to-callback p99)  **Deferred:** a production decision; the default holds until then | M3 | Owner | None |
| ~~Q9~~ | ~~May spec PDFs be stored in the repo?~~ **Closed:** no. They are marked "All Rights Reserved" and the repo is public. Kept in the gitignored `docs/spec/pdf/`; version, URL and checksum are recorded | n/a | Owner | n/a |
| ~~Q10~~ | ~~Base branch~~ **Closed:** `nyse-feed-handler` is based on `add-yolo-mode` (keeps sk-home persistence) | n/a | Owner | n/a |
| ~~Q11~~ | ~~Per-partition time base~~ **Closed 2026-09-19:** the seconds table lives in the decoder's per-channel state, keyed by the Source Time Reference `ID`. Before the first reference, seconds are 0 and `time_ref_missing` is counted. [04, Time base](design/04-pillar-decoding.md#time-base) | n/a | Implementer | n/a |
| ~~Q12~~ | ~~Clear the book at close?~~ **Closed 2026-09-19:** yes. Market state `X` clears the symbol's book, because the feed sends no deletes at close. [BOOK-12](design/05-order-book.md#scenarios) | n/a | Owner | n/a |
| ~~Q13~~ | ~~Second channel in the M1 pcap?~~ **Closed 2026-09-19:** yes, a Stock Summary channel, so type 223 is covered end to end | n/a | Owner | n/a |
