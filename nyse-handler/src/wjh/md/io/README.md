# io

**Responsibility:** turn bytes from a capture file or socket into `Packet`s.

## Planned contents

| File | Contents |
|---|---|
| `PcapReader.hpp/.cpp` | Classic pcap (µs/ns, both byte orders) + pcapng (SHB/IDB/EPB/SPB, `if_tsresol`) |
| `FrameParser.hpp/.cpp` | Ethernet II → optional 802.1Q → IPv4 → UDP. Returns the payload + (dst group, port) |
| `PcapSource.hpp/.cpp` | Reader + parser + (group, port) → (channel, line) lookup → `Packet` |
| `MulticastSource.hpp/.cpp` | **After M1.** Sockets, `recvmmsg`, timestamps |
| `Source.hpp` | `std::variant<PcapSource, MulticastSource>` + a `run(source, sink)` visit, entered once |

## Rules
- A truncated or malformed frame is counted and never delivered.
- Filtering, fragments, and VLANs are handled here. The core sees only clean payloads.

## Depends on
core, stats (counters)

## Design refs
[02: Input sources](../../../../docs/design/02-input-sources.md), [ADR-0002](../../../../docs/decisions/0002-pure-core-no-io.md)
