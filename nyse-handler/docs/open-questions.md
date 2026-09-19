# Open questions

Each question has an owner and the milestone it blocks. Close a question by linking the ADR or doc that answers it.

| # | Question | Blocks | Owner | Default until answered |
|---|---|---|---|---|
| ~~Q1~~ | ~~Exact spec version~~ **Closed:** Integrated Feed v2.5h and Common Client v2.4s, recorded in [spec tracking](spec/README.md) | n/a | Implementer | n/a |
| ~~Q2~~ | ~~Semantic questions~~ **Closed:** all seven [answered from the spec](spec/message-catalog.md#semantic-questions-answered-from-the-spec). The price formula and the Imbalance per-market columns were both recovered from the PDF and cross-checked | n/a | Implementer | n/a |
| ~~Q3~~ | ~~Duplicate `OrderID` on add~~ **Closed 2026-09-19:** replace the existing order and count it. The spec re-adds a returned routed order under the same ID, so it is not always an anomaly. [BOOK-A2](design/05-order-book.md#scenarios) | n/a | Owner | n/a |
| ~~Q4~~ | ~~Should an anomaly mark the channel stale?~~ **Closed 2026-09-19:** no. Count, record in the anomaly ring, continue. Revisit only with evidence from real pcaps. [BOOK-A1 to A5](design/05-order-book.md#scenarios) | n/a | Owner | n/a |
| ~~Q5~~ | ~~Gap window and buffer size~~ **Closed 2026-09-19:** 5 ms and 1,024 packets. The capture site is unknown, so the default leans long; a fill-time histogram and buffer high-water mark ([ARB-14](design/03-arbitration-and-gaps.md#scenarios)) let the first real capture set it from data | n/a | Owner | n/a |
| ~~Q6~~ | ~~Independent cross-check source~~ **Closed 2026-09-19:** none available (no TAQ, vendor or SIP access). M2 reconciles our trade events against the feed's own Stock Summary messages; see [test strategy, layer 6](testing/test-strategy.md#layer-6-end-to-end-and-golden) | n/a | Owner | n/a |
| ~~Q7~~ | ~~Production telemetry stack~~ **Closed 2026-09-19:** the backend is undecided, so the handler writes a shared-memory snapshot and a sidecar ships it; see [07, StatsSink](design/07-observability.md#statssink). Nothing in M1 changes | n/a | Owner | n/a |
| ~~Q8~~ | ~~Latency target~~ **Closed 2026-09-19:** live signals and pricing, not latency-competitive. Budget: median ≤ 5 µs and p99 ≤ 25 µs per packet, a day replayed at ≥ 10× real time; a hypothesis that M2 confirms or resets. See [08](design/08-performance-guidelines.md) | n/a | Owner | n/a |
| ~~Q9~~ | ~~May spec PDFs be stored in the repo?~~ **Closed:** no. They are marked "All Rights Reserved" and the repo is public. Kept in the gitignored `docs/spec/pdf/`; version, URL and checksum are recorded | n/a | Owner | n/a |
| ~~Q10~~ | ~~Base branch~~ **Closed:** `nyse-feed-handler` is based on `add-yolo-mode` (keeps sk-home persistence) | n/a | Owner | n/a |
| ~~Q11~~ | ~~Per-partition time base~~ **Closed 2026-09-19:** the seconds table lives in the decoder's per-channel state, keyed by the Source Time Reference `ID`. Before the first reference, seconds are 0 and `time_ref_missing` is counted. [04, Time base](design/04-pillar-decoding.md#time-base) | n/a | Implementer | n/a |
| ~~Q12~~ | ~~Clear the book at close?~~ **Closed 2026-09-19:** yes. Market state `X` clears the symbol's book, because the feed sends no deletes at close. [BOOK-12](design/05-order-book.md#scenarios) | n/a | Owner | n/a |
| ~~Q13~~ | ~~Second channel in the M1 pcap?~~ **Closed 2026-09-19:** yes, a Stock Summary channel, so type 223 is covered end to end | n/a | Owner | n/a |
