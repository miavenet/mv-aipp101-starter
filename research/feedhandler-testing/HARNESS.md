# Proposed implementation approach

This is a project proposal informed by the research, not a claim that the full design is prescribed by any exchange.

## Components

```text
reviewed logical fixture ──► profile encoder ──► deterministic packet schedule
captured traffic ────────────────────────────► replay input adapter
                                                   │
                                           optional fault injector
                                                   │
                                                   ▼
                                            handler under test
                                               │         │
                                      decoded events   recovery requests
                                               │         │
                                               ▼         ▼
                                         result checker  scripted recovery peer
                                               ▲         │
                                               │         └──► recovery ingress
                                      independent expected state
```

Separate the **message model** from the **wire profile**. The latter defines transport framing, sequence scope/unit, reset epochs, replay transport, snapshot boundaries, and extension policy. Generic tests must not copy CME's SBE fields, Nasdaq's Mold/Soup framing, or HKEX's control messages into Pillar.

## Three execution tiers

1. **In-process deterministic tests:** inject bytes at the real decoder/arbiter boundary, use a fake clock, and observe events/state. This is the fast CI tier. Preserve real message lengths and packet framing rather than only calling book methods.
2. **Socket integration:** run the same scheduled scenarios over isolated UDP/multicast and the profile's recovery connection. Verify subscription configuration, network receive behavior and reconnect handling. Compare a sender manifest with what the receiver actually observed.
3. **Capture and load runs:** replay a version-compatible capture with known starting state and expected results. Add load gradually, record drop counters at sender/NIC/socket/application levels where available, and retain hardware/runtime settings. Run live venue qualification separately when access is available.

The published HKEX tool architecture is the principal precedent for tier 2's split between replay and recovery simulation. Its documentation is not proof that tcpreplay alone emulates a request server. [S05](SOURCES.md#s05-hkex-onboarding-tools).

## Recovery peer contract

For every scripted request, record the expected product/channel/range or symbol scope and the allowed order of responses. Supply success, rejection, delayed response, disconnect and incomplete response variants. Preserve canonical logical message identity while allowing different valid packetization.

For the Pillar profile, consult Common §§5–7 for the split between the request connection and recovery-data delivery; do not assume “TCP request” means “TCP payload replay.” A generic peer interface should model control and data paths separately. [S10](SOURCES.md#s10-nyse-pillar-common-specification).

## Oracle and state publication

Keep a slow reference book using straightforward maps/lists, independently implemented from the optimized handler. For small fixtures, manually review expected checkpoints as well; two implementations can share the same misunderstanding of the spec.

Compare canonical data, not pointer layout or hash-table iteration order. A result should include:

```json
{
  "scenario": "FH-007",
  "profile": "nyse-integrated-common-2.4s-integrated-2.5h",
  "fixture_sha256": "<filled by the harness>",
  "applied_sequences": [100, 101, 102, 103],
  "recovery_requests": [{"channel": 1, "begin": 102, "end": 102}],
  "book_checkpoint_hashes": ["<reviewed expected hashes>"],
  "state_synchronized": true,
  "event_history_complete": true,
  "errors": []
}
```

This JSON is an illustrative result contract, not output from an implemented test. The actual profile also needs session identity, message scope, request timing and quality transitions. Large captures should use streamed counts/hashes/checkpoints rather than retain every sequence in memory.

## Fault controls

Make loss, duplicate, reorder, delay, fragmentation/truncation, and disconnect deterministic and independently selectable. Packet loss and logical-message loss are different faults. Preserve checksums for valid-network tests; corrupt them intentionally only in a separate transport-integrity case. Do not accidentally test only the OS's checksum rejection when the intended target is the parser.

Bound queues and retained out-of-order data. Define local behavior when the bound is reached: invalidate/resynchronize, shed with an explicit gap, or stop. Exact limits are project decisions. A test passes only if observed behavior matches that policy without memory corruption or falsely reporting current data.

For performance, distinguish packet-send rate from achieved receive rate, processing delay from end-to-end latency, and timestamp-clock validity from timestamp precision. An accelerated replay with capture timestamps is not automatically a trustworthy latency benchmark.

## Fixture provenance

Store a manifest with source URL, retrieval date, hash, venue/feed/revision, line/channel, capture interval, transport/container format, starting-state requirements, and expected-result provenance. Keep original external artifacts separate from generated mutations. Pin downloaded content by hash; a filename such as “latest specification” is not a reproducible dependency.

The NYSE `.bin` example is deliberately not included as a Pillar PCAP fixture. For a usable Pillar capture, inspect its actual format and decoded message revision before adopting it; do not infer compatibility from the exchange name alone.

## Implementation order and completion criteria

| Stage | Deliverable | Done when |
|---|---|---|
| 1 | Explicit profile and reviewed minimal corpus | All wire fields, sequence/cutover rules and expected outputs have source references |
| 2 | Byte-input runner, fake clock, canonical event checker | FH-001–010 reproduce deterministically and fail under relevant injected implementation defects |
| 3 | Reference state model and scripted recovery peer | FH-011–021 cover supported features; unsupported paths fail visibly |
| 4 | Real-capture adapter and socket integration | A known-baseline capture agrees with the independent oracle; ingress counters reconcile |
| 5 | Load, fuzzing and mutation jobs | FH-023–026 have bounded runtime, retained reproductions and measured project thresholds |
| 6 | Venue testing | Required external qualification completed for the actual production profile; offline success alone is not labeled certification |

Prioritize a handful of fully specified cases over hundreds of names without executable expected results. Expand the catalogue only when each case adds a distinct failure mode or source obligation.
