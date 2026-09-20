# Stage 6 CLI walkthrough

Captured in `/tmp/task-runner-stage6-weu105gj` using the model-free command example. No model calls were made.

The revised title is committed before replan so the tree is clean. Reopening the producer
also resets its check and human verifier. The original acceptance remains in history, followed
by a revert and a new acceptance.

```text
$ runner start command-demo.toml
run 20260920T105808Z-658db150  (658db150-3ba0-4216-b87f-c53555e4ecac)
record  /tmp/task-runner-stage6-weu105gj/.runs/command-demo/20260920T105808Z-658db150
branch  run/command-demo-658db150  (checked out; was main)
warning: agent 'scripted' reports no dollar cost: dollar limits do not bind on it; time and attempts still apply, and usage is recorded as unpriced
write: started
write: waiting for a person at 'signoff'. The work tree is held.
run 20260920T105808Z-658db150: needs_human. See /tmp/task-runner-stage6-weu105gj/.runs/command-demo/20260920T105808Z-658db150/STATUS.md
[exit 255]
$ runner approve latest signoff
signoff: approved. Continue with: runner resume 20260920T105808Z-658db150

[exit 0]
$ runner resume

write: accepted as e8de527
run 20260920T105808Z-658db150: done. See /tmp/task-runner-stage6-weu105gj/.runs/command-demo/20260920T105808Z-658db150/STATUS.md
[exit 0]
$ git commit -am "Revise the workflow title"
(workflow edit committed)
$ runner replan latest

runner: accepted work would change; use --reopen for: check, write
[exit 2]
$ runner replan latest --reopen write
replan changes: check, write
affected tasks: check, signoff, write
revert commits: e8de527
op-0008-562358b8 replan: installed the revised workflow; 1 revert commit(s)
Continue with: runner resume 20260920T105808Z-658db150

[exit 0]
$ runner resume

write: started
write: waiting for a person at 'signoff'. The work tree is held.
run 20260920T105808Z-658db150: needs_human. See /tmp/task-runner-stage6-weu105gj/.runs/command-demo/20260920T105808Z-658db150/STATUS.md
[exit 255]
$ runner approve latest signoff
signoff: approved. Continue with: runner resume 20260920T105808Z-658db150

[exit 0]
$ runner resume

write: accepted as 9e43cd8
run 20260920T105808Z-658db150: done. See /tmp/task-runner-stage6-weu105gj/.runs/command-demo/20260920T105808Z-658db150/STATUS.md
[exit 0]
$ git status --porcelain
(clean)
$ git log --oneline main..HEAD
9e43cd8 Write the revised demonstration result
7b2af24 Revert "Write the demonstration result"
0d64b5f Revise the workflow title
e8de527 Write the demonstration result
```

