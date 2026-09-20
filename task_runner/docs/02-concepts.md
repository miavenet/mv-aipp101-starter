# 02 — Concepts

The whole model, in the order the pieces depend on each other. Decisions are cited as D1 to D16
from the [decision log](00-decisions.md).

## Workflow, task, run

A **workflow** is a TOML file: a named list of **tasks** joined by `needs` into an acyclic graph.
A **run** is one execution of a workflow, with a UUID and a directory. A workflow can have many
runs. A run works from its own frozen copy of the workflow (D11, D12).

## Kinds: the four behaviours the engine knows (D4)

| Kind | What it does | Who acts | Result |
|---|---|---|---|
| `produce` | Creates or changes files in the repository | An agent, with write access | `done` or `blocked`, a summary, and on rework a response to each finding |
| `review` | Judges the work of one producer, from one perspective. Read-only | An agent, read-only, in a new session | `pass` or `block`, a summary, findings |
| `check` | Runs commands. Passes if all exit 0 | The runner. No agent | pass or fail, with the output |
| `human` | Pauses until a person approves or rejects | A person | approve, or reject with a comment |

`review`, `check` and `human` are the **verifiers**. A `check` or `human` task verifies a producer
when it says `verifies = "<task>"`; otherwise it is a standalone step in the DAG.

## Types: templates over a kind (D4)

A **type** is a file in the library: a kind, a prompt template, parameters, and defaults for agent,
model, gates and limits. `design`, `implement`, `test`, `code-review`, `design-review` and
`summarize` ship as a starter library. A task names a type and fills its parameters. Adding a type
of work means adding a file.

## Personas: the reviewer's perspective (D4)

A **persona** is also a file: a title, what that reviewer cares about, what counts as blocking for
them, and what is out of their scope. A review task's `perspective` parameter names one. The starter
library has `principal-engineer`, `spec-compliance`, `devops`, `process-manager` and
`technical-project-manager`. A persona can carry its own agent and model, so a perspective can be
given to a different model from the author's.

Telling a persona what is **out of scope** matters as much as its focus: it stops five reviewers
from each raising the same general point.

## Outputs and inputs (D2, D3)

A producer declares `outputs`: paths or globs in the repository. These are its deliverables. After
each attempt the runner writes a **manifest**: each declared path that exists, with its hash and
size, plus the full diff of the attempt.

A task's **inputs** are derived, not written by hand. For every task in its `needs`, and for the
task a review targets, the runner gives the agent:

- the upstream task's id, type and title,
- its summary (a few sentences from its result),
- its output file list from the manifest,
- for a review: the diff of the work under review.

The agent reads the files itself. Prompts carry pointers and summaries, not file contents, so they
stay small however large the deliverables are.

## Acceptance (D7)

A producer's attempt passes through verifiers in a fixed order, cheapest first. The first failure
stops the sequence and sends the work back.

| Step | Verifier | Cost |
|---|---|---|
| 1 | The agent ran without error and did not answer `blocked` | free |
| 2 | Every declared output exists and is not empty | free |
| 3 | No protected or frozen file was changed (any change is reverted by the runner) | free |
| 4 | The task's own `gate` commands exit 0 | seconds to minutes |
| 5 | Every `check` that `verifies` this task passes | seconds to minutes |
| 6 | The review panel has no open blocking finding | agent calls |
| 7 | Every `human` task that `verifies` this task approves | a person's time |

A producer must have at least one of steps 4 to 7, or the workflow is rejected when it loads. Steps
1 to 3 always apply. The agent's own report is recorded and never used.

When all verifiers pass, the task is **accepted**: its changes are committed (D13) and its outputs
are **frozen** (D8).

## Rework: the one loop (D1, D5)

```
                    ┌──────────── consolidated feedback ─────────────┐
                    ▼                                                │
 pending ─► produce (attempt n) ─► gates/checks ─► review panel ─► open blocking findings?
                    │                   │                                │ no
                    │ blocked           │ same failure twice             ▼
                    ▼                   ▼                             accepted ─► commit ─► frozen
              needs a person          failed
```

- Gate or check failure: its output goes back to the author at once. Reviewers are not called for
  work that does not pass its checks.
- Review: **the whole panel runs before anything goes back.** The author receives one list of all
  blocking findings (advisory ones are attached for information) and does one rework.
- A rework is a new **attempt**. `max_attempts` (default 3) counts attempts, whatever sent the work
  back. When they run out, the task is `failed` if a gate or check sent it back last, and `blocked`
  (a person is needed, with the open findings listed) if review did.
- The author's session is continued for a rework, so it keeps its understanding and the provider's
  cache is reused. After an agent error or a timeout the session is abandoned and the next attempt
  starts clean.
- The same gate failure twice running, ignoring timings, fails the task early: "no progress".

## Findings (D5, D15)

A finding is the unit of review feedback.

| Field | Meaning |
|---|---|
| `id` | Given by the runner: persona code and a number, such as `PE-2`. Stable for the life of the run |
| `severity` | `blocking` or `advisory`. A reviewer marked `advisory` in the workflow can only produce advisory findings |
| `title`, `detail` | What is wrong and why it matters |
| `location` | File and line or section, where that applies |
| `status` | `open`, `resolved`, `disputed`, `escalated` |

**Round 1** is a full review. **Later rounds judge the fix.** A reviewer who blocked is given its
own open findings, the author's response to each, and the rework diff. It must mark each finding
`resolved` or `unresolved`. It may raise a new blocking finding only about something the rework
changed or broke; a new concern about an untouched part is recorded as advisory. Reviewers who
passed are, by default, shown the rework diff only and may block only on that.

The author answers each blocking finding with `fixed` or `disputed` and a note. A finding the author
disputes and the reviewer keeps open becomes `escalated`: the task stops for a person, because two
agents disagreeing is not something a third loop settles.

Each producer has one **findings ledger** in the run record, holding every finding from every
reviewer and round, with its history. "What did review find, and was it fixed?" is answered by
reading one file.

## Dependencies and freezing (D8)

`needs = ["design"]` means *design is accepted*. Nothing starts on unreviewed work.

Once accepted, a task's outputs are **frozen**: they join the protected set of every later task, and
a change to them is reverted by the runner like any protected file. A later task may change a frozen
file only by **claiming** it in its own `outputs`. `validate` lists every such overlapping claim, so
"task B will modify the approved design" is visible in the plan, and B's reviewers see the diff.
Ordinary incremental work, such as a second task extending `src/book/**`, is therefore possible, but
never silent.

## Scheduling (D6)

A task is **ready** when everything in its `needs` is accepted (for a review: when its target has
passed its gates and checks in the current attempt).

- **Writers** are `produce` tasks and any `check` not marked `read_only`. One writer runs at a time.
  Among ready writers, the first in workflow order goes next.
- **Readers** are `review` tasks and `read_only` checks. Ready readers run together, up to
  `max_parallel`.
- **A writer never runs while readers are running**, and readers never start while a writer runs.
  Reviewers browse the work tree, so it must hold still.
- A panel's results are gathered and applied together, in workflow order, when its last member
  finishes. So the decision does not depend on which reviewer happened to finish first.

Given the same workflow and the same results from agents, the same things happen in the same order.

## Failure (D9)

A task ends unsuccessfully as **failed** (attempts used up on gates, no progress, a reviewer changed
the tree, no usable verdict) or **blocked** (the agent said it cannot do the task properly, a finding
was escalated, or attempts ran out with blocking findings still open). In both cases:

1. The task's uncommitted changes are saved as `failed.patch` in its directory.
2. The paths it changed are returned to the last accepted state. Only those paths: the runner never
   resets or cleans the whole tree.
3. Every task downstream of it is marked `skipped`, with the reason.
4. Independent branches continue.

The run ends with exit 2 (failed) or 255 (a person is needed). `retry TASK` gives fresh attempts,
either clean or with `--apply-patch` to start from the set-aside work.

## Runs (D11, D12, D13)

- `start` makes a run: a UUID, a directory, a frozen copy of the workflow and the library files it
  uses, and a branch `run/<workflow>-<uuid8>` from a clean tree.
- `resume` continues it. Nothing is kept in memory between steps, so resuming is the normal way the
  runner works, not a special case.
- `replan` brings an edited workflow into a run where that is safe. Changing an accepted task needs
  `--reopen`, which resets it and everything downstream and lifts their freeze.
- Each accepted producer is one commit on the run branch. Merging the branch is the owner's call.

## The record (D2, D14)

Everything about a run is under one directory, regenerated summaries included. Any directory in it
can be opened cold: `index.json` says what each file is, `STATUS.md` says what happened in words,
and the `README.md` at the top of `.runs/` explains the layout once. See
[04 — Run directory](04-run-directory.md).
