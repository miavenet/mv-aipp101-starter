# Task runner

A generic runner for agent work. It takes a **workflow** (a list of tasks that forms a DAG), runs
it to completion with headless coding agents, and leaves a complete, navigable record of everything
that was done. Tasks can be of any type: design, implementation, tests, code review, design review,
summaries, plain commands, human sign-off. The output of one stage feeds the next stage or stages.

Status: **stages 1–3 implemented; 196 tests pass.** `start` and `resume` execute one producer
transaction at a time using a `command` agent, with gates, verifying checks and human decisions.
`approve`, `reject` and `retry` are implemented, together with durable recovery and streamed,
redacted logs. Every accepted commit is tied to the verified candidate.

Run the tests from the repository root:

```sh
python3 -m unittest discover -s task_runner/tests -q
```

The runner needs Python 3.11+ and Git; no installation or third-party Python packages are required.
Run `task_runner/runner --help` for the available commands. For a model-free example, copy
[`examples/command-demo.toml`](examples/command-demo.toml) into a clean scratch Git repository,
commit it, and run `runner start` on that copy. The
[stage 3 walkthrough](docs/stage-3-walkthrough.md) records a real rejection, rework, approval and
resume through the CLI.

Claude Code and Codex adapters and `doctor` arrive in stage 4. Review panels, findings and budget
reservation arrive in stage 5; replan arrives in stage 6. Workflows requiring review tasks or
unavailable adapters stop with an explanation before any agent is called. The larger book-module
example can be validated and graphed, but cannot execute until those later stages are implemented.

## Read in this order

| File | Contents |
|---|---|
| [`docs/00-decisions.md`](docs/00-decisions.md) | The sixteen decisions taken with the owner, each with its reason; the defaults assumed without asking; the twelve amendments (A) made after an independent design review, and the twelve (B) made after an adversarial review |
| [`docs/01-requirements.md`](docs/01-requirements.md) | What the runner must do, and what it will not do |
| [`docs/02-concepts.md`](docs/02-concepts.md) | Kinds, types, personas, acceptance, rework, findings, runs. The model in full |
| [`docs/03-workflow-file.md`](docs/03-workflow-file.md) | Reference for the workflow file, type files and persona files |
| [`docs/04-run-directory.md`](docs/04-run-directory.md) | Reference for the run record: layout, every file, the result schemas |
| [`docs/05-architecture.md`](docs/05-architecture.md) | Modules, the scheduler, the agent interface, git, state, command line |
| [`docs/06-scenarios.md`](docs/06-scenarios.md) | WHEN/THEN scenarios, each naming the test that will prove it |
| [`docs/07-implementation-plan.md`](docs/07-implementation-plan.md) | Build stages, risks, what comes later |
| [`docs/tutorial/`](docs/tutorial/README.md) | A guided tour with diagrams: the idea, a task end to end, panels and findings, safety, architecture, writing a workflow. Each chapter says whether it is checked against code yet |
| [`docs/runbook.md`](docs/runbook.md) | Operating a run: commands, stops, recovery. A skeleton until the commands exist |
| [`library/`](library/) | Draft starter library: task types and reviewer personas. Content, not code |
| [`examples/book-module.toml`](examples/book-module.toml) | A worked example workflow |

## The idea in five lines

1. A workflow is an acyclic DAG of tasks. Each task has one of four **kinds**: `produce`, `review`,
   `check`, `human`. A **type** (design, implement, code-review, …) is a template over a kind.
2. Work is accepted only by **verifiers**: commands that exit 0, reviewers that return a structured
   verdict, or a person. Never by the agent's own report. A producer with no verifier is rejected.
3. A review panel of **personas** (principal engineer, spec compliance, DevOps, …) reviews the same
   work in parallel. Blocking findings go back to the author once, consolidated, for bounded rework.
4. Downstream tasks start only when upstream work is **accepted**. Accepted work is committed and
   frozen. A producer owns the work tree from its first edit until it is committed or set aside, and
   exactly the candidate that was verified is what gets committed.
5. Every run has a UUID and a directory laid out like a build directory, which explains itself to
   any person or agent who opens it later.

## Where this came from

[`research/task_runner/`](../research/task_runner/README.md) holds the evidence: a close reading of
StrongDM's Attractor and agate, the landscape, what Claude Code and Codex offer in headless mode,
and a throwaway prototype with a recorded live run. Its `design/` folder described a simpler runner
(a flat task list with review built into every task). This directory supersedes that design; the
research and the prototype's findings still stand.
