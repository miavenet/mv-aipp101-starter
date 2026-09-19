# Documentation index

## Design (read in order)

| # | Document | Covers |
|---|---|---|
| 00 | [Overview](design/00-overview.md) | Scope, goals, non-goals, constraints |
| 01 | [Architecture](design/01-architecture.md) | Pipeline, modules, dependency graph, threading |
| 02 | [Input sources](design/02-input-sources.md) | Pcap/pcapng reader, multicast, `Packet`, source selection |
| 03 | [Arbitration and gaps](design/03-arbitration-and-gaps.md) | A/B first-arrival, gap window, channel state machine, recovery |
| 04 | [Pillar decoding](design/04-pillar-decoding.md) | Views that read the buffer in place, offset tables, validation, errors |
| 05 | [Order book](design/05-order-book.md) | Order map, price levels, L2 books, invariants |
| 06 | [Consumer interface](design/06-consumer-interface.md) | Events, flags, `Consumer` concept |
| 07 | [Observability](design/07-observability.md) | Counters, anomaly ring, `StatsSink`, event dump, latency |
| 08 | [Performance guidelines](design/08-performance-guidelines.md) | Hot-path rules and the path to production latency |
| 09 | [Configuration](design/09-configuration.md) | JSON schema, CLI |

## Decisions

[Architecture Decision Records](decisions/README.md): one file per decision,
covering context, the decision, alternatives, and consequences.

## Spec

- [Spec tracking](spec/README.md): which spec version, where the PDF lives, citation rules
- [Message catalog](spec/message-catalog.md): message types to implement, with verification status

## Testing

- [Test strategy](testing/test-strategy.md): fixture, round-trip, oracle, and property layers
- [Fixture review checklist](testing/fixture-review-checklist.md): for the reviewer of the hex fixtures

## Planning

- [Milestones](roadmap/milestones.md)
- [Open questions](open-questions.md)
- [Glossary](glossary.md)
