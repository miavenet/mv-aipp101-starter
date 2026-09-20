# Task runner: an Attractor-style runner for this repository

Research started 2026-09-19. The goal: break a project into work items and run them through a task
runner so the work proceeds **deterministically and autonomously to completion**, in the style of
StrongDM's [Attractor](https://github.com/strongdm/attractor) (a natural-language spec for a
pipeline runner) and [agate](https://github.com/strongdm/agate) (a Go implementation of the idea).
The first project to run through it is the NYSE feed handler's M1 plan.

Status: **research done. The runner's design has moved to [`/task_runner/`](../../task_runner/README.md).**
The `design/` folder here describes an earlier, simpler runner (a flat task list with review built
into every task) and is superseded. The sources, the analysis and the prototype's findings still stand.

| File | Contents |
|---|---|
| `DECISION.md` | What we will build and what changed from the first proposal |
| `ANALYSIS.md` | What the research says |
| `design/01-design.md` | Requirements, task life cycle, rules for accuracy, efficiency and determinism |
| `design/02-architecture.md` | Modules, plan file, agent interface, snapshots, state, command line |
| `design/03-implementation-plan.md` | Stages, scenarios and tests, risks, open questions |
| `prototype/` | A throwaway spike that tested the design against the real tools. Evidence only |
| `sources/01-attractor-spec.md` | Close reading of the three Attractor specs |
| `sources/02-agate-implementation.md` | Code walk of agate: lifecycle, state, gating, resumability |
| `sources/03-landscape.md` | Other Attractor implementations and comparable runners |
| `sources/04-claude-code-headless.md` | What Claude Code offers a runner that drives it non-interactively |
| `sources/05-spot-check-verification.md` | The claims the decision rests on, re-checked against primary sources |

Snapshots studied: attractor `fb57a55` (2026-03-17), agate `ea95448` (2026-02-23). Both are Apache-2.0.
