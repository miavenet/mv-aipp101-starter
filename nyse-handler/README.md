# NYSE Integrated Feed Handler

A C++20 feed handler for the **NYSE Pillar Integrated Feed** (NYSE equities).
It builds full-depth L2 order books from A/B multicast lines, or from pcap
captures of them, and delivers book, trade, imbalance, and status events
to an in-process consumer.

> **Status: design only.** This directory holds the design plan, decision
> records, and the module layout. It contains **no implementation**
> yet. See [roadmap](docs/roadmap/milestones.md) for what comes first.

## Goals

- **Correctness first:** deterministic, fully testable, verified against the spec.
- **Latency-aware by design:** no latency target yet, but the hot path never
  allocates, throws, or dispatches virtually, so later tuning is not a rewrite.
- **Workshop → production:** the same core runs a pcap replay today and
  live multicast tomorrow.

## Where to start reading

| If you want to… | Read |
|---|---|
| Understand the scope and the vocabulary | [Overview](docs/design/00-overview.md), [Glossary](docs/glossary.md) |
| See how the pieces fit | [Architecture](docs/design/01-architecture.md) |
| Know *why* something is the way it is | [Decision records](docs/decisions/README.md) |
| Know what "done" means for the first cut | [Milestones](docs/roadmap/milestones.md) |
| Help verify the spec layouts | [Spec tracking](docs/spec/README.md), [Fixture review checklist](docs/testing/fixture-review-checklist.md) |
| See what is still undecided | [Open questions](docs/open-questions.md) |

All docs: [docs/README.md](docs/README.md).

## Layout

```
nyse-handler/
├── README.md                   ← you are here
├── docs/                       design plan, ADRs, spec tracking, test strategy, roadmap
├── config/                     configuration schema and examples (JSON)
└── src/wjh/
    ├── md/                     library: namespace wjh::md (Pillar code: wjh::md::pillar)
    │   ├── core/               strong types, Packet, clock/timestamps
    │   ├── io/                 pcap/pcapng reader, sources (pcap, multicast)
    │   ├── pillar/             packet/message views, offset tables, decoder
    │   ├── arb/                A/B line arbitration, gap detection, recovery strategy
    │   ├── book/               order map, price levels, per-symbol L2 books
    │   ├── handler/            FeedHandler<Consumer>, events, Consumer concept
    │   ├── stats/              counters, anomaly ring, StatsSink
    │   ├── config/             JSON config loading and validation
    │   └── tests/              unit + property tests, hex fixtures
    ├── testing/md/             test-only: PillarEncoder, PcapWriter, ReferenceBook
    └── apps/nyse_replay/       CLI: replay pcap / run live, dump events and books
```

Each module directory has a `README.md` giving its responsibility, planned
contents, allowed dependencies, and hot-path rules.

## Hard rules

1. Nothing under `nyse-handler/` includes anything from `src/wjh/chat`. The handler has to be extractable into its own repository.
2. Module dependencies point one way: `core ← io, pillar ← arb, book ← handler ← apps`. See [architecture](docs/design/01-architecture.md#module-dependency-graph).
3. Every byte offset cites its spec section and version. See [spec tracking](docs/spec/README.md).
