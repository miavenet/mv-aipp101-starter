# Stage 3 CLI walkthrough

Verified on 2026-09-20 using Python and Git in a scratch repository. No model calls.

The repository was initialized on `main`, configured with a local test identity, and given a
committed copy of [command-demo.toml](../examples/command-demo.toml) named `workflow.toml`.
The transcript below is captured output. The candidate was rejected once, reworked, approved,
and committed exactly once; the final work tree is clean.

```text
$ runner validate workflow.toml
workflow command-demo: 3 tasks, in execution order
root /tmp/task-runner-stage3-hise3h64

  1  write    produce/implement      agent scripted
              outputs: result.txt
              gate: grep -qx 'Verified candidate' result.txt
  2  check    check                  verifies write; read-only
  3  signoff  human                  verifies write

claims on frozen outputs: none
[exit 0]
$ runner start workflow.toml
run 20260920T040633Z-4ec38084  (4ec38084-5ffb-41f7-8a01-309ccb83eecc)
record  /tmp/task-runner-stage3-hise3h64/.runs/command-demo/20260920T040633Z-4ec38084
branch  run/command-demo-4ec38084  (checked out; was main)
write: started
write: waiting for a person at 'signoff'. The work tree is held.
run 20260920T040633Z-4ec38084: needs_human. See /tmp/task-runner-stage3-hise3h64/.runs/command-demo/20260920T040633Z-4ec38084/STATUS.md
[exit 255]
$ runner reject latest signoff -m Exercise the rework path.
signoff: rejected. Continue with: runner resume 20260920T040633Z-4ec38084
[exit 0]
$ runner resume
write: sent back (a person rejected the work at 'signoff')
write: waiting for a person at 'signoff'. The work tree is held.
run 20260920T040633Z-4ec38084: needs_human. See /tmp/task-runner-stage3-hise3h64/.runs/command-demo/20260920T040633Z-4ec38084/STATUS.md
[exit 255]
$ runner approve latest signoff
signoff: approved. Continue with: runner resume 20260920T040633Z-4ec38084
[exit 0]
$ runner resume
write: accepted as d42b29e
run 20260920T040633Z-4ec38084: done. See /tmp/task-runner-stage3-hise3h64/.runs/command-demo/20260920T040633Z-4ec38084/STATUS.md
[exit 0]
$ runner status
# command-demo — run 4ec38084 — done

Started 2026-09-20 04:06:33 UTC. 0 min of agent time. Branch run/command-demo-4ec38084.
Spend: $0.00 known of $50.00, $0.00 reserved, plus 2 unpriced calls (0 tokens in, 0 out; 2 with unknown usage).

| # | Task | Type | Status | Attempts | Cost | Commit |
|---|---|---|---|---|---|---|
| 010 | write | implement | accepted | 2 |  | d42b29e |
| 020 | check | check | accepted |  |  |  |
| 030 | signoff | human | accepted |  |  |  |

## Next
    Inspect the branch; merging it is your call.
[exit 0]
$ git status --porcelain
$ git log --oneline main..HEAD
d42b29e Write the demonstration result
```
