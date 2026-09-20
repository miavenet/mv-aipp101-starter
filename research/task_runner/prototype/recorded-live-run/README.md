# Recorded live run (2026-09-19)

The run directory of the prototype's only live run: a two-task plan in a scratch repository, with
claude 2.1.278 and codex-cli 0.155.1. Kept because it holds real agent output (`stdout.log`), which
the adapter tests of the real build should parse (scenarios AGENT-03 and AGENT-05).

- `slug`: Claude implemented, Codex rejected attempt 1 and approved attempt 2.
- `cli`: Codex could not start its sandbox in this container and answered "blocked".
- The first attempt's budget-stop output was overwritten when the task was retried.
