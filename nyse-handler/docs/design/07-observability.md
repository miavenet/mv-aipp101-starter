# 07 — Observability

## Counters

Plain `std::uint64_t` fields owned by the handler thread. No atomics in M1.
Grouped per channel, plus globals.

| Group | Counters |
|---|---|
| Transport | `datagrams`, `unmatched_datagrams`, `non_udp_frames`, `ip_fragments`, `truncated_frames` |
| Arbitration | `packets_A`, `packets_B`, `win_A`, `win_B`, `dup_A`, `dup_B`, `partial_overlap`, `heartbeats` |
| Gaps | `gaps_declared`, `seqs_missing` (sum), `stale_transitions`, `seq_resets`, `gap_buffer_hwm`, `gap_buffer_overflow` |
| Decode | `messages`, `malformed_packets`, `unknown_msg_type[…]`, `oversized_msg` |
| Book | `unknown_order_id`, `duplicate_add`, `over_execution`, `unmapped_symbol`, `crossed_books`, `capacity_exceeded` |

## Anomaly ring

A fixed-size ring buffer of records (`channel`, `seq`, `kind`, `order_id`, `symbol`, `recv_ts`).
It is written on the hot path (a copy into a slot, which never allocates) and read off the hot path.
When full, the oldest entry is overwritten and `anomalies_dropped` is incremented.

## StatsSink

The interface to external telemetry, kept **off the hot path**:

```cpp
// Shape sketch
class StatsSink {
public:
    virtual ~StatsSink() = default;
    virtual void publish(const StatsSnapshot& snapshot) = 0;
    virtual void publish(std::span<const AnomalyRecord> anomalies) = 0;
};
```

- Virtual dispatch is fine here, because this is a cold path.
- **M1:** `StderrStatsSink` prints a formatted report at the end of a replay and on `SIGUSR1`.
  The signal handler only sets a flag, which the loop checks between packets.
- **M3 (decided 2026-09-19): `ShmStatsSink` plus a sidecar.** Once a second the handler writes a
  fixed-layout, versioned `StatsSnapshot` into a shared-memory region (a file-backed `mmap`), guarded
  by a seqlock so a reader never sees a torn snapshot. A separate process reads it and speaks
  whatever the monitoring stack turns out to be (Prometheus, OpenTelemetry, a message bus). The
  backend is undecided and is chosen at M3; the handler does not change when it is.
  - No sockets, HTTP server or third-party library in the latency-sensitive process.
  - `nyse_stats`, a small command-line reader of the same region, works with no monitoring stack.
  - The snapshot layout is plain integers with a version field, so the sidecar can be written in any
    language.
- In multi-threaded production builds, each thread owns its counters and the snapshot writer sums
  them, still behind the seqlock.

## Logging

No logging on the hot path. At the edges (startup, config, file errors, the final
report), `std::format` to stderr. No logging library in M1.

## Event dump format

`--dump-events` writes one line per event. **This is the golden-test format.**
It must be deterministic, stable, and diffable. Any change to it counts as a breaking
change and needs review.

```
ch=3 seq=1042 sym=IBM B add   px=145.2500 lvl_qty=1200 lvl_n=4 flags=-
ch=3 seq=1043 sym=IBM B chg   px=145.2500 lvl_qty=900  lvl_n=3 flags=-
ch=3 seq=1044 sym=IBM T trade px=145.2500 qty=300              flags=L
ch=5 ---- STALE from=88120 to=88123
ch=5 seq=88124 sym=XYZ A add px=12.0100 lvl_qty=100 lvl_n=1 flags=S
```

Rules:
- Prices are rendered from the integer and scale. **No floating point.**
- Fixed field order. Timestamps are **excluded** by default (`--dump-ts` includes
  them), so dumps of synthetic runs don't depend on capture timing.
- Flags: `S` stale, `L` last in packet, `X` crossed, `-` none.

The exact column set is finalized in M1 and then frozen.

## Book snapshot

`--dump-book=<ticker>[@seq=<n>]` prints the full L2 book for a symbol at the end of the
replay, or when sequence number `n` is reached on its channel. Used for debugging.

## Latency instrumentation

- Every event carries `recv_ts` and `send_ts`, so exchange-to-receive latency is
  always available.
- The replay tool can record **time spent in the handler per packet** (`rdtsc` or
  `steady_clock` at entry and exit) into a fixed-bucket histogram, printed with the stats.
  It is compiled in, and its cost is one pair of timer reads per packet when enabled.
