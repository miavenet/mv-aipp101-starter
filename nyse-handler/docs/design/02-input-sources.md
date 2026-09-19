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

## Scenarios

Format and rules: [test strategy](../testing/test-strategy.md#scenarios).

| ID | WHEN | THEN | Test |
|---|---|---|---|
| IO-01 | a classic pcap with microsecond timestamps is read | every UDP payload is delivered with `recv_ts` in nanoseconds | `pcap: classic microsecond file` |
| IO-02 | a classic pcap with the nanosecond magic is read | timestamps keep full nanosecond precision | `pcap: classic nanosecond file` |
| IO-03 | a pcap written in the other byte order is read | it decodes identically | `pcap: swapped byte order` |
| IO-04 | a pcapng file (SHB, IDB, EPB, SPB) with a non-default `if_tsresol` is read | packets and timestamps match the same capture in classic format | `pcap: pcapng with if_tsresol` |
| IO-05 | frames carry one or two 802.1Q VLAN tags | the UDP payload is still found and delivered | `pcap: vlan tagged frames` |
| IO-06 | a frame is not IPv4 or not UDP | it is counted and skipped | `pcap: non-udp frames skipped` |
| IO-07 | a frame is an IP fragment | it is counted and skipped | `pcap: ip fragments skipped` |
| IO-08 | a datagram's destination group and port match no configured line | it is counted as `unmatched_datagrams` and skipped | `pcap: unmatched datagram skipped` |
| IO-09 | the file ends in the middle of a record | the truncation is reported and no partial packet is delivered | `pcap: truncated file` |
| IO-10 | a frame was cut short by the capture's snaplen | it is counted and never delivered as a packet | `pcap: snaplen truncated frame` |
| IO-11 | a pcapng block has an impossible length | the error is reported and reading stops cleanly | `pcap: bad block length` |
| IO-12 | a datagram matches a configured (group, port) | its `Packet` carries the configured `line` and `channel` | `pcap: line and channel from config` |
