# wjh::md: market data library

The library behind the NYSE Integrated Feed handler. Namespace `wjh::md`, with
Pillar-specific code in `wjh::md::pillar`.

| Module | Namespace | Responsibility | May depend on |
|---|---|---|---|
| [core](core/README.md) | `wjh::md` | Strong types, `Packet`, time | (none) |
| [io](io/README.md) | `wjh::md::io` | Pcap/pcapng reading, sources | core |
| [pillar](pillar/README.md) | `wjh::md::pillar` | Framing, message views, decoder | core |
| [stats](stats/README.md) | `wjh::md` | Counters, anomaly ring, `StatsSink` | core |
| [arb](arb/README.md) | `wjh::md` | A/B arbitration, gaps, recovery seam | core, pillar, stats |
| [book](book/README.md) | `wjh::md` | Order map, L2 books | core, pillar, stats |
| [config](config/README.md) | `wjh::md` | JSON config → validated `Config` | core |
| [handler](handler/README.md) | `wjh::md` | `FeedHandler<Consumer>`, events, dumper | all of the above |
| [tests](tests/README.md) | n/a | Unit, property, fixture tests | everything + `testing/md` |

Design: [docs/design/01-architecture.md](../../../docs/design/01-architecture.md).
**No implementation yet.**
