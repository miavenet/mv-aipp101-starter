# Adapter fixtures

These three files are unchanged copies of stdout from the research prototype's recorded live run:

- `claude-success.json`: `slug/attempt-1/implement/stdout.log`
- `codex-review.jsonl`: `slug/attempt-1/review/stdout.log`
- `codex-sandbox-failure.jsonl`: `cli/attempt-1/implement/stdout.log`

The original run lives in `research/task_runner/prototype/recorded-live-run`. Its result schemas
predate this runner: adapter parsing tests preserve those answers; current-schema validation is
tested separately. Failure variations are constructed in tests, not presented as live captures.
