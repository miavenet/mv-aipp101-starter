# Architecture Decision Records

One file per decision. Format: **Context → Decision → Alternatives → Consequences.**
A decision is not edited once accepted. Changing it means writing a new ADR that supersedes it.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-integrated-feed-nyse-equities.md) | Integrated Feed, NYSE equities only | Accepted |
| [0002](0002-pure-core-no-io.md) | Pure core; sources chosen at startup | Accepted |
| [0003](0003-first-arrival-arbitration-stale-no-recovery.md) | First-arrival A/B arbitration; stale-and-continue; no recovery | Accepted |
| [0004](0004-l2-book-integer-prices.md) | Full-depth L2 book with integer prices | Accepted |
| [0005](0005-single-thread-sync-consumer.md) | Single thread, synchronous in-process consumer | Accepted |
| [0006](0006-memcpy-views-no-reinterpret-cast.md) | Views read with memcpy; no packed-struct casts | Accepted |
| [0007](0007-synthetic-testing-with-reference-oracle.md) | Synthetic testing with hex fixtures and reference oracle | Accepted |
| [0008](0008-in-repo-extractable-layout.md) | Live in the host repo, extractable later | Accepted |
| [0009](0009-statssink-interface.md) | Counters + `StatsSink` interface, no logging library | Accepted |

Template: copy [`_template.md`](_template.md).
