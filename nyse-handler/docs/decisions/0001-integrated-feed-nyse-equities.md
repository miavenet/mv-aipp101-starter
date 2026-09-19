# ADR-0001: Integrated Feed, NYSE equities only

- **Status:** Accepted
- **Date:** 2026-09-19

## Context

NYSE publishes several Pillar-based products (Integrated, BBO, Trades,
Imbalances) across several markets (NYSE, Arca, American, National, Chicago).
The project begins as a workshop and becomes production.

## Decision

Implement the **NYSE Pillar Integrated Feed** for **NYSE equities** only. Keep
the decoder keyed on the Pillar packet and message headers, not on a market, so other
Pillar markets can be added mostly as configuration plus layout tables.

## Alternatives considered

| Option | Why not |
|---|---|
| XDP BBO / Trades only | Easier, but a BBO-only handler is usually thrown away. Everything they provide can be derived from Integrated. |
| All Pillar markets at once | Multiplies the verification work before there is any end-to-end result. |
| Options feeds | Different spec, different scale. Out of scope. |

## Consequences

- We must maintain an order map and full book, which is the hardest variant.
- Other markets need their own symbol mapping data and possibly other message types. The design does not block that.
