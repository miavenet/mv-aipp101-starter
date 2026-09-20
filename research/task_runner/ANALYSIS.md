# Analysis: an Attractor-style runner for this repository

Date: 2026-09-19. Evidence is in [`sources/`](sources/). The claims this analysis leans on were
re-checked against the primary sources in
[`sources/05-spot-check-verification.md`](sources/05-spot-check-verification.md).

## The question

We want to break a project into work items and have a runner carry them to completion
**deterministically and autonomously**, in the style of Attractor. What should we build, how much
of Attractor should it implement, and what makes it reliable?

## What the two StrongDM projects actually are

**Attractor is a specification, not a program.** The repository holds three natural-language specs:
a pipeline engine, a coding-agent loop, and an LLM client. There is nothing to install. Third
parties have built it in Go, Python and C, all small and none canonical.

**agate is a different design.** It is not an Attractor engine: it has no graph, no DOT, and a fixed
five-phase lifecycle (interview, design, skills, sprints, implement). What it contributes is
operational, and it is good:

- State lives on disk and is rebuilt on every call. Nothing is carried in memory.
- `agate auto` just runs `agate next` again and again and reads the exit code: 0 done, 1 more work,
  2 error, 255 human needed.
- It shells out to the `claude` CLI and lets the agent write files directly.
- It has a dummy agent, so the whole loop can be tested without a model.

It also shows what to avoid. Its review gate is the word `APPROVED` appearing anywhere in the
reviewer's output. It never runs a build or a test itself. It has no git integration. Several
advertised features (parallel agents, retrospectives, `suggest`) are not wired in.

## Where "deterministic" really comes from

An agent's work is not deterministic, and no runner makes it so. What can be deterministic is
everything around it. The sources agree on three places:

1. **Routing.** Attractor picks the next node by a fixed five-step order: a matching edge condition,
   then the outcome's preferred label, then its suggested next IDs, then edge weight, then the
   node ID in alphabetical order. The same outcomes always take the same path.
2. **State.** One checkpoint after each node (Attractor), rebuilt from disk each time (agate), with
   step outputs stored so a crash resumes instead of replaying (Temporal, DBOS, Inngest, LangGraph
   all converge on this).
3. **Gates.** Whether a step succeeded is decided by a command's exit code, not by what the agent
   says. This is the part agate lacks and the practitioner sources stress most: verdicts that fail
   closed, reviewers that start from a fresh context, and a hard retry cap.

So the honest reading of the goal is: **deterministic control flow and acceptance, around
non-deterministic work.** That is achievable.

## How much of Attractor to build

The spec itself says the engine does not need its two companion specs if the backend is a CLI agent.
Claude Code already provides the agent loop, the tools, context management, sub-agents, retries on
API errors, and cost reporting. That removes roughly two thirds of the specification.

Of the engine spec, a first project needs only part:

| Attractor feature | First version | Why |
|---|---|---|
| DOT subset, start and exit nodes, attributes | **Yes** | The graph is the plan. It is also reviewable and renders as a picture |
| Five-step edge selection, condition language (`=`, `!=`, `&&`) | **Yes** | This is the determinism. It is about 40 lines |
| `codergen` node with a pluggable backend | **Yes** | The seam for Claude Code, and for a fake backend in tests |
| `tool` node (runs a command, outcome from the exit code) | **Yes** | The gates |
| Retries, `retry_target`, failure routing, goal gates | **Yes** | The fix-and-retry loop, and "cannot finish with a failed gate" |
| Checkpoint and resume, run directory, `status.json` | **Yes** | Survives crashes, budget stops and human pauses |
| Validation (one start, one exit, all nodes reachable, conditions parse) | **Yes** | Cheap, and catches a broken plan before money is spent |
| `wait.human` node | **Yes, as pause and resume** | M1 step 4 needs the owner to review fixtures. Exit with "human needed", as agate does |
| Parallel fan-out and fan-in | No | The M1 steps are a chain. Parallel work also needs worktrees per branch |
| Model stylesheet, context fidelity modes, manager loop, transforms, event stream | No | Nothing in the first project needs them |

Keeping the DOT format and the status contract means the spec's own definition of done (§11) and
smoke test (§11.13) can serve as our acceptance tests, and a plan written for our runner would run
on any other Attractor engine.

## What driving Claude Code headless gives us, and its traps

Useful, and confirmed in the installed binary:

- `-p --output-format json` returns the result, `session_id`, `total_cost_usd`, `num_turns` and an
  error subtype.
- `--json-schema` returns a validated object in `structured_output`. This is how a node reports its
  outcome without us parsing prose.
- `--max-budget-usd` caps a node's spend, sub-agents included.
- `--session-id` and `--resume` let a retry continue the same session, or start clean.

Traps:

- **`--bare` is not usable here.** It is the documented way to isolate a scripted run, but it never
  reads OAuth credentials and it skips `CLAUDE.md`. We need the project rules, and we should not
  assume an API key. Use the normal mode and pass settings explicitly.
- **There is no wall-clock limit.** The runner must enforce its own, with SIGINT first (ends the
  turn cleanly and keeps the session resumable) and SIGTERM after a grace period.
- **`-p` starts in manual permission mode**, which would hang or deny. The documented unattended
  pattern is `--permission-mode auto --permission-prompts none`, plus an allow list. This needs a
  live test before we depend on it.
- **Do not use a Stop hook to force "keep going".** It is overridden after 8 blocks. The loop
  belongs in the runner, where each attempt is a fresh, bounded call.
- **Cost figures are client-side estimates.** Good enough for a cap, not for billing.
- **Our own hooks will fire in driven sessions.** That is an advantage: the hook logger is passive
  and async, and it gives every node a session scorecard (loops, repeated failures) for free. The
  runner can read it as a stuck signal. See
  [`../session_evaluation/DECISION.md`](../session_evaluation/DECISION.md).

## Language

The container has Python 3.12 and Node 18, no Go, and no way to `pip install` into the system. The
Python Agent SDK cannot be installed cleanly, and the TypeScript SDK's Node requirement is
unchecked. **Python with only the standard library, shelling out to `claude -p`**, has no
dependencies, matches the hook logger already in the repo, and is what agate does in Go. The DOT
subset is small enough to parse by hand.

## What the work items should look like

Attractor nodes carry a prompt. For a project of this size a prompt string is too thin, and the
practitioner sources (Ralph loop, Beads) keep the task text in files under git. The combination that
fits what we already have:

- One **work item file** per step, holding the goal, the design documents to read, the scenario IDs
  it must turn green, and the exact acceptance command.
- The DOT node points at that file. The graph holds order and routing only.
- The **scenario tables** already in the NYSE design documents become the acceptance criteria:
  `tools/check_scenarios.py` reports which named tests exist, and `ctest` says whether they pass.
  The gate for "book" is "all BOOK- scenarios have a test, and the tests pass". The agent cannot
  talk its way past that.

One gap: `check_scenarios.py` checks all scenarios or none. A gate for a single step needs a filter
by ID prefix.

## Risks

| Risk | Mitigation |
|---|---|
| Runaway cost | Budget per node and per run, checked **before** each call. Retry cap of 3. Wall-clock limit |
| A loop that makes no progress | Stop when the same gate fails with the same output twice running. Read the session scorecard |
| The agent weakens a test to pass the gate | Reviewer node in a fresh session sees the diff and the scenario table, returns a structured verdict, fails closed. Gate commands and scenario tables are not editable by the implement node |
| A bad step poisons later ones | One git commit per passed node, on a run branch. Resume or roll back to any node boundary |
| Invented byte offsets | The existing rule stands: fixtures go through the owner-review human gate before the decoder step can start |
| Unattended permissions misbehave | First live test is a throwaway node in a scratch directory |
