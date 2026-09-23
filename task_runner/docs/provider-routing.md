# Provider routing and task complexity

The runner selects a qualified agent profile for each producer or reviewer. An explicit
`fallback_agents` list authorizes automatic switching when the current provider reports
quota exhaustion, or fails twice in a row on the same call for a transient reason (capacity,
overload, a dropped connection, or, for a review, a time-out). A provider failure never counts
as a producer attempt or as a reviewer's answer. This layer sits above the native adapters; task contracts, reviews,
acceptance, budgets and checkpoints remain owned by the runner.

## Complexity levels

| Level | Use for | Typical model choice |
|---|---|---|
| `mechanical` | Clear transformations, repetitive edits, straightforward checks with precise acceptance criteria | Claude Sonnet; a configured economical Codex model |
| `standard` | Bounded implementation or review with established design | A configured balanced model, such as Codex Sol |
| `high` | Architecture, ambiguous requirements, difficult debugging, concurrency or consequential review | Claude Fable/Opus; Codex Astra/Sol |

These levels describe the task's reasoning demands, not estimated token counts or
permission levels. A short task can be `high`. The runner does not guess complexity from
prompt length or escalate models in response to an objection. The workflow author assigns
it on a task, inline reviewer, task type, or `[defaults]`; omission means `standard`.
Models are configurable strings, not a hardcoded ranking or availability claim.

```toml
[defaults]
agent = "codex-writer"
complexity = "standard"

[model_policy.mechanical]
claude = "sonnet"
codex = "gpt-5.6-luna"

[model_policy.standard]
claude = "sonnet"
codex = "gpt-5.6-sol"

[model_policy.high]
claude = "opus" # replace with the exact Fable model available in your environment if desired
codex = "gpt-6-astra" # or gpt-5.6-sol

[agents.codex-writer]
kind = "codex"
sandbox = "workspace-write"

[agents.claude-writer]
kind = "claude"
permission_mode = "auto"

[[task]]
id = "implement-parser"
type = "implement"
prompt = "Implement the reviewed parser contract and run its tests."
complexity = "high"
fallback_agents = ["claude-writer"]
outputs = ["src/parser.cpp"]
gate = ["./test-parser"]
```

This is a configuration fragment: supply the real outputs, gates and contracts for the
project. `doctor` verifies actual access to each selected model before dispatch.
Primary model precedence is task/persona/type `model`, complexity mapping, workflow
default `model`, then profile `model`. A fallback uses its own provider's complexity
mapping, then its profile model. The primary provider's model identifier is never passed
to another provider. Every native fallback must resolve an explicit model.

A reviewer can set `complexity` and `fallback_agents` in its inline reviewer table or its
own task. Reviewers keep their identity and open findings when changing providers; the
fallback adapter receives the same read-only controls and evidence mode. Profiles are
qualified separately for model and review/write mode. An explicit sandbox or permission
bypass cannot be introduced by fallback from a profile without one. `review_mode` must
match. Use separate writer/reviewer profiles when their controls differ.

## Quota handoff

1. Native provider error events or terminal error results identify quota exhaustion.
   Successful prose, tool output, failed tests, malformed responses, timeouts and review
   objections do not trigger a quota switch.
2. The coordinator records the quota outcome, settles its cost/usage, retains saved work,
   and selects the next available qualified profile in the task's configured order.
3. The replacement starts a fresh session with the full task, current findings and
   instructions to inspect saved work and invocation checkpoints. It never receives the
   previous provider's session identifier. The runner does not replay external commands;
   agents are told not to repeat external effects whose outcome is uncertain.
4. A quota call consumes neither a task attempt nor a protocol repair allowance. It still
   contributes to recorded time and spending. The next provider must fit the remaining
   run budget; changing providers does not reset any counters or acceptance history.
5. If no qualified available fallback exists, execution stops visibly with the current
   work retained. `resume` can continue after the cooldown; a replan can change profiles.

Selections are sticky: a task moves forward through its fallback list, preventing cycles.
Observed quota exhaustion applies a five-minute cooldown across profiles of that native
provider within this run. This is a bounded retry delay, **not a claim about the account's
reset time**. No background timer resumes a stopped run. Other tasks can select the
provider again after the cooldown; the current task retains its selected fallback.
A provider unavailable during qualification can be skipped if an authorized fallback
qualifies. Failed qualifications remain visible in the qualification report.

This implementation reacts to confirmed quota errors. It does not infer near-limit status
from token totals or consume the illustrative `~/.codex/sessions/latest.json` path. No
stable native near-limit signal has been established in this environment, so headroom
remains unknown until such telemetry is integrated. Automatic context sizing and dynamic
complexity classification are also outside this policy.

## Visibility and recovery

`runner status` shows each selected profile/model, complexity and selection reason.
`state.json` retains provider selection history, qualifications, quota observations and
pending producer quota transitions. `events.jsonl` records `provider-quota` and
`provider-selection`; each invocation retains its actual argv, model, output and usage.
Native hooks and agent milestone checkpoints continue through the existing adapters.

If the coordinator crashes after recording a quota result or a selection, `resume` uses
that durable transition instead of calling the exhausted provider again. Existing orphan
reconciliation still runs first. Do not edit frozen workflow/run records directly; use
`replan` to change model mappings or profiles. Those changes participate in task definition
comparison, including fallback profile contents.

## Verification scenarios

The deterministic tests in `tests/test_providers.py` exercise partial-work retention,
exhausted fallback lists, no provider cycling on protocol errors, read-only review handoff,
open-finding preservation, complexity model qualification/dispatch, explicit overrides,
invalid/widened controls, unqualified fallbacks, budget stops, error-channel classification,
and coordinator crashes on both sides of selection. They use scratch repositories and
scripted subprocesses, with no paid model calls.
