# Stage 4 CLI walkthrough

Captured on 2026-09-20 in a scratch Git repository, using the model-free
[command agent](../examples/command_agent.py) and [workflow](../examples/command-demo.toml).
Both files were copied into the scratch repository and committed before these commands ran.
No Claude Code or Codex model calls were made.

The first doctor observes capabilities; the second uses the cache. Gate preflight reports the
missing output before its producer runs (exit 2 is expected here). The following start/reject/
resume/approve/resume sequence finishes with one accepted commit and a clean working tree.

```text
$ runner doctor command-demo.toml
command (default model) writer: answer, read, execute, write
qualification: /tmp/task-runner-stage4-u4rw7pl6/.runs/qualification.json
[exit 0]
$ runner doctor command-demo.toml
command (default model) writer: answer, read, execute, write (cached)
qualification: /tmp/task-runner-stage4-u4rw7pl6/.runs/qualification.json
[exit 0]
$ runner check-gates command-demo.toml
write:gate:1: fail
check:check:1: fail
record: /tmp/task-runner-stage4-u4rw7pl6/.runs/check-gates/cfe300a1-7b0d-46d2-819d-20325ae746ad
[exit 2]
$ runner start command-demo.toml
run 20260920T042731Z-7c60e5f9  (7c60e5f9-7545-495d-92ad-bc6db104a041)
record  /tmp/task-runner-stage4-u4rw7pl6/.runs/command-demo/20260920T042731Z-7c60e5f9
branch  run/command-demo-7c60e5f9  (checked out; was main)
write: started
write: waiting for a person at 'signoff'. The work tree is held.
run 20260920T042731Z-7c60e5f9: needs_human. See /tmp/task-runner-stage4-u4rw7pl6/.runs/command-demo/20260920T042731Z-7c60e5f9/STATUS.md
[exit 255]
$ runner reject latest signoff -m Exercise rework.
signoff: rejected. Continue with: runner resume 20260920T042731Z-7c60e5f9
[exit 0]
$ runner resume
write: sent back (a person rejected the work at 'signoff')
write: waiting for a person at 'signoff'. The work tree is held.
run 20260920T042731Z-7c60e5f9: needs_human. See /tmp/task-runner-stage4-u4rw7pl6/.runs/command-demo/20260920T042731Z-7c60e5f9/STATUS.md
[exit 255]
$ runner approve latest signoff
signoff: approved. Continue with: runner resume 20260920T042731Z-7c60e5f9
[exit 0]
$ runner resume
write: accepted as d59db0d
run 20260920T042731Z-7c60e5f9: done. See /tmp/task-runner-stage4-u4rw7pl6/.runs/command-demo/20260920T042731Z-7c60e5f9/STATUS.md
[exit 0]
```
