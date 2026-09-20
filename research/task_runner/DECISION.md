# Decision: design an agent-agnostic task runner in the Attractor style

Date: 2026-09-19. Status: **designed, not built.** The owner asked for the design to be captured
before any build. Reasoning is in [`ANALYSIS.md`](ANALYSIS.md). The design is in three files:

| File | Contents |
|---|---|
| [`design/01-design.md`](design/01-design.md) | Requirements, the life of a task, the accuracy, efficiency and determinism rules, defaults |
| [`design/02-architecture.md`](design/02-architecture.md) | Modules, the plan file, the agent interface, work-tree snapshots, state, command line |
| [`design/03-implementation-plan.md`](design/03-implementation-plan.md) | Five stages, 48 scenarios with their tests, risks, open questions |

A throwaway [`prototype/`](prototype/README.md) exists. It was written before the owner asked to
hold the build, and it is kept only as evidence: its live run settled several questions that the
research could not. It is not the product and is not to be extended.

## Decision

**Build our own runner, in Python with only the standard library. Its input is a task list. Each
task runs a fixed path: implement, gate, review, optional human approval, commit. The agent is
behind one interface, with Claude Code and Codex built in and any other command configurable.**

Do not adopt agate (fixed five-phase lifecycle, a substring as its review gate, no git, needs Go).
Do not adopt a third-party Attractor engine (all tiny, and we need a fraction of the spec). Do not
build an agent loop or an LLM client: the agents are both.

The runner makes four things deterministic: the order of tasks, the path each one takes, what
counts as passing, and the state on disk. The agent's work stays non-deterministic, and is bounded
by attempts, time and money.

## Changes from the first proposal

The first version of this decision proposed Attractor's DOT graph and a Claude-only backend. Two
requirements from the owner changed that:

- **The input is a task list.** Every task in our plans has the same shape, so a graph language
  would be used to write one shape many times. Attractor's useful ideas are kept: the pluggable
  backend, the outcome contract, a checkpoint per step, deterministic routing, a human gate that
  pauses the run, and exit codes as the interface. A task list can be compiled to a graph later.
- **Model agnostic.** The backend seam now carries what any agent needs (schema, session, model,
  budget, read-only, timeout), with three adapters.

## What we will not do

- Accept a step because the agent, or a reviewer's prose, says it is done.
- Use a Stop hook to keep a session going. It is overridden after 8 blocks.
- Run anything without a budget and a clock.
- Let the implement node edit its own gates, the scenario tables or reviewed fixtures.
- Run steps in parallel in the first version.

## What would change this decision

- Agent CLIs dropping their headless modes or structured output. Then the adapters move to the
  vendors' SDKs behind the same interface.
- A third-party Attractor engine becoming clearly maintained and adopted. Our task lists would
  compile to its graph format.
- Step costs far above the defaults. Then the work items are too big, and the fix is in the
  breakdown, not the runner.
