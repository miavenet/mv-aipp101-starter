# Open questions

Each question has an owner and the milestone it blocks. Close a question by linking the ADR or doc that answers it.

| # | Question | Blocks | Owner | Default until answered |
|---|---|---|---|---|
| Q1 | Exact spec version: record it on fetch | M1 step 1 | Implementer | Stop if the fetch fails. Ask for the PDF. |
| Q2 | Semantic questions in the [message catalog](spec/message-catalog.md#semantic-questions-to-answer-from-the-spec) | M1 step 5 | Implementer + owner | n/a |
| Q3 | Duplicate `OrderID` on add: replace, ignore, or mark stale? | M1 step 8 | Owner | Replace and count |
| Q4 | Should any anomaly (e.g. unknown `OrderID`) mark the channel stale? | M1 step 8 | Owner | No: count and continue |
| Q5 | Gap window default (1 ms) and buffer size: suitable for real A/B skew? | M2 | Owner | 1 ms / 1024 packets |
| Q6 | Is there an independent source (TAQ or vendor) for cross-checking real data? | M2 | Owner | n/a |
| Q7 | Production telemetry stack for `StatsSink` | M3 | Owner | Stderr |
| Q8 | Latency target (e.g. wire-to-callback p99) | M3 | Owner | None |
| Q9 | May spec PDFs be stored in the repo under NYSE's terms? | M1 step 1 | Owner | Record version + URL only |
| ~~Q10~~ | ~~Base branch~~ **Closed:** `nyse-feed-handler` is based on `add-yolo-mode` (keeps sk-home persistence) | n/a | Owner | n/a |
