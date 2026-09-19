# ADR-0002: Pure core; sources chosen at startup

- **Status:** Accepted
- **Date:** 2026-09-19

## Context

The same code must run replays of captured pcaps (workshop, testing) and live
multicast (production). Tests must be deterministic.

## Decision

- Arbiter, decoder, and book form a **pure core**: no I/O and no wall-clock
  reads. Their input is a stream of `Packet{payload, recv_ts, line, channel}`.
- `Source` (`PcapSource` | `MulticastSource`) is **chosen once at startup** and
  entered through a `std::variant` visit, with no dispatch per packet.
- Our own pcap/pcapng + Ethernet/IPv4/UDP reader. No libpcap.
- Replay runs as fast as possible. Pacing is optional and only affects the source.

## Alternatives considered

| Option | Why not |
|---|---|
| libpcap | Extra dependency in the Docker image. We need little of it. |
| Virtual `Source::next()` per packet | Unnecessary indirection on the hot path. |
| Core reads the wall clock for gap timeouts | Replays would be nondeterministic and differ from live. |

## Consequences

- Replay and live differ only in the source. Bugs reproduce from pcaps.
- The pcap reader has to handle VLANs, pcapng blocks, and timestamp resolutions.
