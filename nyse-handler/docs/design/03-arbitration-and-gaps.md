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
evidence that the line is alive. Common Client v2.4s §2.2 confirms a heartbeat
"does not increment the next expected sequence number". It does not say what a
heartbeat's `SeqNum` holds, so it is not used for gap detection until a real
capture shows its behaviour.

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
- **Failover packets** (`DeliveryFlag` 10, Common Client v2.4s §8.2): a failover starts with a
  sequence number reset in its own packet, then re-publishes each symbol's mapping, a Symbol Clear,
  the last Security Status and refresh messages. The reset and the clears do the work, so the
  packets are processed normally, counted, and logged to the anomaly ring.

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

## Scenarios

Format and rules: [test strategy](../testing/test-strategy.md#scenarios). Each row names the doctest
case that proves it. `tools/check_scenarios.py` reports which of those tests exist yet.

| ID | WHEN | THEN | Test |
|---|---|---|---|
| ARB-01 | a packet arrives with `s == next_expected` | all `n` messages are processed, `next_expected += n`, and `win_A` or `win_B` is counted for its line | `arb: in-sequence packet is processed` |
| ARB-02 | a packet arrives with `s + n <= next_expected` | it is dropped with no output, and `dup_A` or `dup_B` is counted | `arb: duplicate packet is dropped` |
| ARB-03 | a packet arrives with `s < next_expected < s + n` | only the messages numbered `next_expected` and later are processed, and the overlap is counted | `arb: partial overlap processes only new messages` |
| ARB-04 | a packet arrives with `s > next_expected` | it is buffered, nothing is emitted, and the channel is `Buffering` | `arb: early packet is buffered` |
| ARB-05 | the other line delivers the missing sequence numbers inside the gap window | the buffered packets drain in order, the channel returns to `Synced`, and nothing is flagged stale | `arb: gap filled within window is invisible` |
| ARB-06 | packet time passes `gap_start + gap_window` with the hole still open | `ChannelStale` fires exactly once, `next_expected` jumps to the first buffered sequence number, and later updates carry the `stale` flag | `arb: window expiry declares gap` |
| ARB-07 | buffered packets for the channel exceed `max_buffered_packets` | the gap is declared exactly as in ARB-06 | `arb: full buffer declares gap` |
| ARB-08 | the first packet seen on a channel is later than the first expected sequence number | the channel goes `Stale` immediately | `arb: late first packet is a gap` |
| ARB-09 | a heartbeat arrives (`DeliveryFlag` 1, `NumberMsgs` 0) | `next_expected` is unchanged, nothing is emitted, and the line is counted as alive | `arb: heartbeat advances nothing` |
| ARB-10 | a Sequence Number Reset (type 1) arrives, in any state including `Stale` | every book on the channel is cleared, `ChannelReset` is emitted, `next_expected` follows the reset packet, and the channel is `Synced` | `arb: sequence reset clears and resyncs` |
| ARB-11 | a packet fails framing validation | it is treated as lost over its sequence range, so the other line can still fill it | `arb: malformed packet counts as loss` |
| ARB-12 | the channel is `Stale` and no reset arrives | it stays `Stale` for the session and updates keep flowing, flagged | `arb: stale persists without reset` |
| ARB-13 | a packet carries `DeliveryFlag` 10 (failover) | it is counted and recorded in the anomaly ring, and its messages are processed normally | `arb: failover packets are counted and processed` |
| ARB-P1 | every sequence number reaches at least one line (random drops, duplicates, bounded reordering) | the output equals the single-perfect-line output with no stale flags | `arb property: coverage` |
| ARB-P2 | a sequence number is lost on both lines | `ChannelStale` fires exactly once, at that point and not before | `arb property: double loss` |
| ARB-P3 | extra duplicates are added to either line | the output does not change | `arb property: idempotence` |
