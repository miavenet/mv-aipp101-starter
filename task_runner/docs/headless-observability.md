# Watching headless agents

Verified on 2026-09-20 with Claude Code 2.1.278 and Codex CLI 0.155.1.

Every Claude/Codex invocation has `activity.json` with its run/task identifiers,
log location, and hashes of the project's hook configuration and logger files.
The runner routes the existing loggers into that invocation's `hooks/` directory:

- Claude: `HOOK_LOG_DIR`, producing `hooks.jsonl`, readable `hooks.log`, timings,
  and the existing passive session scorecards.
- Codex: `CODEX_HOOK_LOG`, producing redacted JSONL with session, tool and task IDs.
  Codex's JSON exec events also pass through the same logger, explicitly marked
  `source=codex-exec-stream` and `ExecStream.*`. They remain available in `stdout.log`.

```sh
./task_runner/runner activity latest
./task_runner/runner activity latest --task decoder --tail 30
# For continuous display, poll this read-only command:
watch -n 2 ./task_runner/runner activity latest --tail 12
```

`activity` works while the run lock is held. It does not resume or mutate the run.
Hook output is observational and never changes a gate, verdict, or acceptance.
No events means **no events observed**, not proof the model is idle. Native hooks
may be disabled or awaiting trust. Async events can arrive after an invocation
ends; activity reads the logs afresh. Rotation retains the current and preceding
log. Headless statusline/cost snapshots are not guaranteed; final CLI usage is
still the accounting source.

The loggers attach `task_runner.run`, `task_runner.task`,
`task_runner.invocation`, and `task_runner.agent_kind`. Each invocation has its
own files, so parallel reviewers and resumed sessions cannot share timing state
or interleave unrelated task logs. Both loggers redact secret-shaped fields and
values, limit long strings, and create private log files. Logger failures are
passive. Existing Claude session scorecards remain observations, not automatic
termination rules.

## Configuration and qualification

Keep the project hook definitions and logger scripts available. Claude's
`ignore_user_config=true` still loads project/local settings. `doctor` copies
project hook assets into its scratch checkout and invalidates capability caches
when these assets change. Its report lists the event kinds actually observed.

Codex project hooks require an active trusted config layer and trust in the exact
hook definition. The runner does not automatically bypass hook trust. Review the
project definitions through Codex's hook controls when native hooks are desired.
The exec-stream bridge continues to provide tool observations without relaxing
that trust requirement. See the [official Codex hook documentation](https://learn.chatgpt.com/docs/hooks)
and [Claude hook reference](https://code.claude.com/docs/en/hooks).

## Observed live evidence

- A controlled Opus 5 reviewer read a nonce file using its read tool and returned
  the exact value. Nine native Claude events were recorded in
  `/tmp/runner-native-hooks-03ct4t4r/.runs/invocation-1/hooks/hooks.jsonl`.
- Codex executed `pwd` and completed normally. Seven exec-stream events were
  recorded in `/tmp/task-runner-codex-vbfl0o22/.runs/hook-stream/hooks/hooks.jsonl`.
  Native Codex hooks were not observed in this CLI build's `exec` path, including
  a separate probe with hook enablement and invocation-scoped trust. This is a
  host observation, not a claim that all Codex versions behave the same way.

Scratch paths are local evidence, not portable dependencies. Run `doctor` and a
small workflow on the target host before relying on its native hook behavior.
