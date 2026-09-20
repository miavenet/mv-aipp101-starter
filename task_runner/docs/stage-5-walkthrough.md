# Stage 5 CLI walkthrough

Captured in scratch Git repositories using the scripted [panel agent](../examples/panel_agent.py)
and [workflow](../examples/panel-demo.toml). No model calls were made. Copy `panel_agent.py`,
`command_agent.py`, and `panel-demo.toml` together before trying this example.

## Consolidated rework

Scratch repository: `/tmp/task-runner-stage5-9z03ytjg`.

```text
$ runner doctor panel-demo.toml
command (default model) writer: answer, read, execute, write
command (default model) read-only: answer, read, execute, boundary
qualification: /tmp/task-runner-stage5-9z03ytjg/.runs/qualification.json
warning: agent 'scripted' reports no dollar cost: dollar limits do not bind on it; time and attempts still apply, and usage is recorded as unpriced
[exit 0]
$ runner start panel-demo.toml
run 20260920T051207Z-d7058e52  (d7058e52-b9e8-41cf-afe3-e24ea500743d)
record  /tmp/task-runner-stage5-9z03ytjg/.runs/panel-demo/20260920T051207Z-d7058e52
branch  run/panel-demo-d7058e52  (checked out; was main)
warning: agent 'scripted' reports no dollar cost: dollar limits do not bind on it; time and attempts still apply, and usage is recorded as unpriced
make: started
make: sent back (the review panel has blocking findings)
make: accepted as 4858338
run 20260920T051207Z-d7058e52: done. See /tmp/task-runner-stage5-9z03ytjg/.runs/panel-demo/20260920T051207Z-d7058e52/STATUS.md
[exit 0]
$ git status --porcelain
(clean)
$ git log --oneline main..HEAD
4858338 Write and review the demonstration result
```

The producer used 2 attempts. Each reviewer completed two rounds.
`make/PE-1` ended as `resolved`. The commit tree matches the reviewed candidate.

## Dispute and human resolution

Scratch repository: `/tmp/task-runner-stage5-ldm5yy7_`.

```text
$ runner doctor panel-demo.toml
command (default model) writer: answer, read, execute, write
command (default model) read-only: answer, read, execute, boundary
qualification: /tmp/task-runner-stage5-ldm5yy7_/.runs/qualification.json
warning: agent 'scripted' reports no dollar cost: dollar limits do not bind on it; time and attempts still apply, and usage is recorded as unpriced
[exit 0]
$ runner start panel-demo.toml
run 20260920T051208Z-f9253a4c  (f9253a4c-0fb7-4552-9f95-e06c69443d32)
record  /tmp/task-runner-stage5-ldm5yy7_/.runs/panel-demo/20260920T051208Z-f9253a4c
branch  run/panel-demo-f9253a4c  (checked out; was main)
warning: agent 'scripted' reports no dollar cost: dollar limits do not bind on it; time and attempts still apply, and usage is recorded as unpriced
make: started
make: sent back (the review panel has blocking findings)
run 20260920T051208Z-f9253a4c: needs_human. See /tmp/task-runner-stage5-ldm5yy7_/.runs/panel-demo/20260920T051208Z-f9253a4c/STATUS.md
[exit 255]
$ runner resolve latest make/PE-1 --as advisory -m Draft wording is acceptable for this demonstration.
make/PE-1: advisory. Continue with: runner resume 20260920T051208Z-f9253a4c

[exit 0]
$ runner resume

make: accepted as 7886fa0
run 20260920T051208Z-f9253a4c: done. See /tmp/task-runner-stage5-ldm5yy7_/.runs/panel-demo/20260920T051208Z-f9253a4c/STATUS.md
[exit 0]
$ git status --porcelain
(clean)
$ git log --oneline main..HEAD
7886fa0 Write and review the demonstration result
```

The producer used 2 attempts. Each reviewer completed two rounds.
`make/PE-1` ended as `noted`. The commit tree matches the reviewed candidate.

