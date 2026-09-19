# 03 — A/B arbitration and gap handling

Every Pillar packet header carries a per-channel `SeqNum`, a message count
(`NumberMsgs`), a send time, and a `DeliveryFlag`. `DeliveryFlag` separates
original, retransmitted, refresh, sequence-reset, and heartbeat packets. The
exact header layout and flag codes are **to be verified** from the spec.
See [message catalog](../spec/message-catalog.md).

## Arbitration: first arrival wins, per channel

State per channel: `next_expected : SeqNum`. When packet `p` (first sequence number `s`, `n` messages) arrives on either line:

| Condition | Action |
|---|---|
| `s + n <= next_expected` | **Duplicate** (normally the slower line). Drop it and count `dup_A`/`dup_B`. |
| `s == next_expected` | **Process** it. `next_expected += n`. Drain buffered packets that are now contiguous. Count `win_A`/`win_B`. |
| `s < next_expected < s + n` | **Partial overlap.** Process only the messages with sequence number at least `next_expected`. Count it, because it should be rare. |
| `s > next_expected` | **Potential gap.** Copy it into the gap buffer and start or extend the gap window. |

Heartbeats carry no messages. They advance nothing, but they do count as
evidence that the line is alive. **To be verified:** whether a heartbeat's
`SeqNum` shows the next expected sequence number, which would let a gap be
detected earlier.

## Gap window

A potential gap becomes a **declared gap** when either of these happens first:
- **Time:** `packet_time_now − gap_start_packet_time > gap_window` (default
  1 ms, configurable). This uses **packet time**, so pcap replay behaves
  exactly like live.
- **Space:** buffered packets for the channel exceed `max_buffered_packets`
  (config), sized in advance from the pool.

## Channel state machine

```
                seq == expected
              ┌───────────────┐
              ▼               │
  start ──► Synced ──────────┘
              │  seq > expected
              ▼
          Buffering ──── other line fills the hole ────► Synced
              │  window expires / buffer full
              ▼
            Stale ◄──────── (NoRecovery: stays here for the session)
              │  sequence reset
              ▼
          Synced (books for the channel cleared, next_expected = reset value)
```

- **Start:** the pcaps begin before the open, so each channel starts `Synced`
  expecting the first sequence number. If the first packet seen is later than that,
  it is a gap, and the channel goes `Stale` immediately.
- **Entering `Stale`:** emit a `ChannelStale` event, then **skip past the hole**
  (`next_expected` = first buffered sequence number) and keep applying updates, each
  flagged `stale`. ([ADR-0003](../decisions/0003-first-arrival-arbitration-stale-no-recovery.md))
- **Sequence reset:** clear every book and order on the channel, emit
  `ChannelReset`, set `next_expected` from the reset packet, and go to `Synced`.
  This is the **only** way out of `Stale` in M1.
- **Failover packets:** **to be verified** in the spec. The default is to count them and log them to the anomaly ring.

## Recovery seam

```cpp
// Concept sketch (not implementation)
template <class R>
concept RecoveryStrategy = requires(R r, ChannelId ch, SeqNum from, SeqNum to) {
    r.on_gap(ch, from, to);      // may start a retransmission or refresh
    // later: r.poll(), r.on_recovered_packet(...)
};
```

| Strategy | Phase | Behaviour |
|---|---|---|
| `NoRecovery` | M1 | Does nothing. The channel stays `Stale` until a sequence reset. |
| `RetransRecovery` | Future | Sends a TCP retransmission request for small gaps and feeds recovered packets back into the arbiter. |
| `RefreshRecovery` | Future | Joins the refresh channel for large gaps or a late start, then rebuilds books. |

## Properties to test

See [test strategy](../testing/test-strategy.md#layer-4--arbitration-properties).
- If every sequence number reaches at least one line, the output equals the single-perfect-line output, with no stale flags.
- If a sequence number is lost on **both** lines, the channel goes stale at exactly that point and not before.
- Duplicates never change the output.
