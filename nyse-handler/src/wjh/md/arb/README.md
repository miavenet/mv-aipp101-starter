# arb

**Responsibility:** merge A/B lines per channel into one in-order packet stream, detect gaps, manage channel state.

## Planned contents

| File | Contents |
|---|---|
| `ChannelArbiter.hpp/.cpp` | Per-channel `next_expected`, first-arrival-wins, gap buffer, state machine (`Synced`, `Buffering`, `Stale`) |
| `GapBufferPool.hpp` | Buffers sized in advance for packets copied while waiting on the gap window |
| `ChannelState.hpp` | State enum + transitions |
| `RecoveryStrategy.hpp` | Concept + `NoRecovery` |

## Rules
- The gap window is measured in **packet time**, never wall time.
- On a declared gap: emit stale, skip the hole, continue with updates flagged `Stale`.
- Sequence reset → clear the channel, `Synced`.

## Depends on
core, pillar (packet header view), stats

## Design refs
[03: Arbitration and gaps](../../../../docs/design/03-arbitration-and-gaps.md), [ADR-0003](../../../../docs/decisions/0003-first-arrival-arbitration-stale-no-recovery.md)
