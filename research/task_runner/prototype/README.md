# Task runner: prototype

> **This is a spike, not the product.** It was written to test the design against the real `claude` and
> `codex` binaries, and it is kept as evidence. The design it informed is in [`../design/`](../design/).
> Do not extend it; the real build follows [`../design/03-implementation-plan.md`](../design/03-implementation-plan.md).

Takes a list of tasks and carries them to completion with a headless coding agent. It works with
Claude Code and Codex out of the box, and with any other agent that reads a prompt on stdin.
Python 3.11 or later, standard library only.

```
python3 research/task_runner/prototype/runner.py validate plan.toml     # check the plan, print the order
python3 research/task_runner/prototype/runner.py run plan.toml          # run until done, or until a person is needed
python3 research/task_runner/prototype/runner.py status plan.toml
python3 research/task_runner/prototype/runner.py approve plan.toml TASK # release a task that waits for a person
python3 research/task_runner/prototype/runner.py retry plan.toml TASK   # new attempts for a failed or blocked task
```

Exit codes: 0 all done, 1 more work (`next` only), 2 error or failed task, 255 a person is needed.
[`example-plan.toml`](example-plan.toml) shows every setting with its default.

## What happens to each task

```
implement ──► gate ──► review ──► (human) ──► commit
    ▲           │         │
    └── output ─┴ reasons ┘          at most max_attempts, then the run stops
```

- **implement:** the agent gets the task, the acceptance commands and the rules.
- **gate:** the runner runs the task's `gate` commands. All must exit 0. Nothing the agent says
  counts. A task without a gate is rejected when the plan is loaded.
- **review:** a second agent, in a new session with read-only tools, sees the task and the diff
  and returns `{"approved": true|false, "reasons": [...]}`. Anything that is not that shape is not
  an approval. If the reviewer changes the work tree, the task fails.
- **human:** with `human_review = true` the run stops here until `approve`.
- **commit:** one commit per task, holding only the files that task changed.

## What keeps it accurate

| Control | Effect |
|---|---|
| Fixed order | Dependencies first, then the order in the file. The same plan always runs the same way |
| Gates are exit codes | The agent cannot talk its way to "done" |
| Protected files | Globs in `protected` are put back if the agent changes them, and the attempt does not pass |
| "blocked" is a valid answer | The agent is told to say so when a task cannot be done properly, instead of bending a test |
| Clean tree required | The run refuses to start on uncommitted changes, unless `allow_dirty = true` |

## What keeps it efficient

- A retry **continues the same agent session** and sends only the failure output, so the context is
  reused. After an agent error or a timeout the next attempt starts a clean session instead.
- The review runs only after the gate passes.
- **No-progress stop:** the same gate output twice running ends the task early, with timings ignored.
- Budgets are checked before each call: `budget_usd` per call (Claude Code enforces it),
  `run_budget_usd` for the run, `timeout_min` of wall clock per call. The runner owns the clock:
  SIGINT, then SIGTERM, then SIGKILL. Codex reports tokens, not cost, so for Codex the limits are
  time and attempts.
- `model` and `review_model` can be set per task, so simple tasks can use a cheaper model.

## State

Everything is under `.runner/<plan name>/`, which ignores itself in git: `state.json` (saved after
every phase), `events.jsonl`, and for each attempt the exact prompt, command line, agent output and
gate log. Nothing is kept in memory between phases, so a stopped run resumes by running it again.

## Agents

| Name | Command | Notes |
|---|---|---|
| `claude` | `claude -p --output-format json --permission-mode auto --permission-prompts none` | Verdicts through `--json-schema`, budget through `--max-budget-usd`, retries through `--resume` |
| `codex` | `codex exec --json -c sandbox_mode="workspace-write" -` | Verdicts through `--output-schema`, retries through `exec resume`, reviews with `sandbox_mode="read-only"` |
| `type = "command"` | your `argv` | Prompt on stdin, answer on stdout. The verdict is the last JSON object in the answer |

Override an agent under `[agents.NAME]`: `bin`, `model`, `args` (extra arguments), and for Claude
`permission_args`, for Codex `sandbox`. Flags were checked against claude 2.1.278 and codex-cli 0.155.1.

## Tests

`python3 research/task_runner/prototype/tests/test_runner.py` runs the whole loop with scripted agents, so it needs no
model and costs nothing.

## Not built yet

Parallel tasks, Attractor's DOT graph format, and reading the hook logger's session scorecard as a
stuck signal. See [`DECISION.md`](../DECISION.md).
