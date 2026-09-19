# 02 — Input sources

## The `Packet` contract

Every source produces the same thing:

| Field | Type | Notes |
|---|---|---|
| `payload` | `std::span<const std::byte>` | UDP payload, which is the Pillar packet. Valid only during delivery. |
| `recv_ts` | `Timestamp` (ns) | Pcap: capture timestamp. Live: NIC/kernel timestamp if available, else `clock_gettime` at receive. |
| `line` | `Line` (`A` / `B`) | From the config lookup of (group, port). |
| `channel` | `ChannelId` | From the config lookup of (group, port). |

The core relies on nothing else from the transport.

## Source selection

Chosen **once at startup** from the CLI:

```
--source=pcap:<file>      # .pcap or .pcapng; format detected from magic number
--source=mcast            # live; groups/ports/interfaces from --config
```

Implementation: a `std::variant<PcapSource, MulticastSource>` visited once
to enter a loop specialized for that type, so there is no dispatch per packet.

## PcapSource

We write our own reader, not libpcap (no dependency, easy to put in the image, fast):

- **Formats:** classic pcap (µs and ns magic, both byte orders) and **pcapng**
  (SHB, IDB, EPB, and SPB blocks; honours `if_tsresol`).
- **Link layers:** Ethernet II, optional 802.1Q VLAN tag(s), then IPv4 and UDP.
  Non-UDP and non-IPv4 frames are counted and skipped.
- **IP fragments:** counted and skipped. Pillar packets should fit in one frame. A
  fragment means a capture or config error.
- **Filtering:** (dst group, dst port) must match a configured line. Anything else
  is counted as `unmatched_datagrams` and skipped.
- **Pacing:** as fast as possible by default. A `--pace` option (later) sleeps to
  reproduce the original inter-arrival times. The core never sees wall time either way.
- **Robustness:** a truncated file, bad block lengths, or a snaplen shorter than
  the frame are all reported and counted. A truncated frame is never delivered as a packet.

## MulticastSource (after M1)

- One UDP socket per (group, port, interface), joined per config.
- Starts with plain sockets and `recvmmsg`, with `SO_TIMESTAMPNS` or hardware
  timestamps where available.
- Later: kernel bypass (ef_vi / Onload / DPDK) behind the same `Packet`
  contract. See [08](08-performance-guidelines.md).

## Why A/B arrive through one source

Both lines of a channel have to reach the same arbiter in their true relative
order. A pcap already interleaves them by capture time. For live data, one poll
loop serves both sockets of a channel group. ([ADR-0003](../decisions/0003-first-arrival-arbitration-stale-no-recovery.md))
