# 01 — Architecture

## Pipeline

```
          ┌──────────────┐   Packet{payload span, recv_ts, line A|B, channel}
 pcap ───►│              │
          │   Source     ├──────────────────┐
 mcast ──►│ (chosen at   │                  ▼
          │  startup)    │        ┌──────────────────┐   in-order packets
          └──────────────┘        │  ChannelArbiter  ├──────────────┐
                                  │  (per channel)   │              │
                                  └────────┬─────────┘              ▼
                                           │ gap / reset   ┌────────────────┐  message views
                                           ▼               │ Pillar Decoder ├───────────┐
                                  ┌──────────────────┐     └────────────────┘           ▼
                                  │ RecoveryStrategy │                        ┌──────────────────┐
                                  │  (NoRecovery)    │                        │ BookSet / events │
                                  └──────────────────┘                        └────────┬─────────┘
                                                                                       │ BookUpdate, Trade,
                                                                                       │ Imbalance, Status, Stale
                                                                                       ▼
                                                                              ┌──────────────────┐
                                                                              │ Consumer (strategy│
                                                                              │  / dumper / test) │
                                                                              └──────────────────┘
                            Stats counters updated throughout ──► StatsSink (off hot path)
```

## Key principles

1. **Pure core.** Arbiter, decoder, and book do no I/O and never read the wall
   clock. They are deterministic functions of the packet stream, including packet
   timestamps. ([ADR-0002](../decisions/0002-pure-core-no-io.md))
2. **One seam per source of variability.** `Source` (pcap or multicast),
   `RecoveryStrategy` (none, then retransmit or refresh), `Consumer`
   (strategy, dumper, test), `StatsSink` (stderr, then prod telemetry).
3. **Static dispatch on the hot path.** `FeedHandler<Consumer>` is a template.
   `Source` is chosen once at startup (`std::variant` or two instantiations)
   and never dispatched per packet.

## Module dependency graph

```
            core
           ╱  │  ╲
         io  pillar  stats
           ╲  │  ╱  ╲
            arb    book
              ╲    ╱
             handler ◄── config
                │
          apps/nyse_replay
```

Rules:
- Arrows point one way only. A module may include only modules above it.
- `testing/md` may depend on anything in `md`. Nothing in `md` depends on `testing/md`.
- No module includes anything from `src/wjh/chat`.

Each module builds as its own static library target, e.g. `wjh_md_core`, `wjh_md_pillar`.

## Threading model

| Phase | Model |
|---|---|
| Workshop / M1 | **Single thread.** Source → arbiter → decoder → book → consumer callback, all synchronous. No locks, no atomics. |
| Production | **One pinned thread per channel group**, busy polling. Channels share no state (symbols are split by channel), so the core code does not change. |

A slow consumer stalls the feed. That is accepted for an in-process strategy.
Decoupling (an SPSC ring) will be added later **as a Consumer adapter**, not in
the core. ([ADR-0005](../decisions/0005-single-thread-sync-consumer.md))

## Data ownership and lifetimes

- `Source` owns packet buffers. A `Packet`'s payload span is valid **only for the
  duration of the call that delivers it**, except for packets the arbiter
  buffers during a gap window. Those are copied into a pre-allocated
  buffer pool.
- Message views point into the payload and do not outlive the packet.
- Events handed to the consumer are values or views valid only during the callback.
- `BookSet` owns all books and the order map. Consumers read books through
  const references during callbacks.

## Physical layout

See the [top-level README](../../README.md#layout) and the `README.md` in each
module under `src/wjh/md/`.
