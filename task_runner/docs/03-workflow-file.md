# 03 — Workflow file, type files and persona files

All three are TOML, read with Python's standard library. Unknown keys are errors everywhere, so a
typo is caught before anything runs.

## Workflow file (D10)

```toml
name = "book-module"            # names the run directories. Default: the file name
root = "../.."                  # the repository, relative to this file. Default: the file's directory
library = ["library"]           # extra directories of types and personas, searched before the built-in ones

[defaults]                      # every key optional
agent = "claude"
model = ""
max_attempts = 3
timeout_min = 30
gate_timeout_min = 20
budget_usd = 5.0
run_budget_usd = 50.0
max_parallel = 4
recheck_passed = "diff"         # after rework, reviewers who passed see the rework diff: "diff" | "never"
branch = "run"                  # "run": a branch per run. "current": commit on the checked-out branch
commit_trailer = ""
allow_dirty = false             # true: start even with uncommitted changes; only task-changed paths are ever touched
protected = ["docs/spec/**"]    # never changeable by any task in this workflow

[agents.codex]                  # optional settings per agent
sandbox = "workspace-write"

[[task]]
id = "design"
type = "design"
title = "Design the L2 order book"
prompt = "Design the order book described in ..."      # or prompt_file = "items/design.md"
outputs = ["docs/design/05-order-book.md"]
reviewers = ["principal-engineer", "spec-compliance"]

[[task]]
id = "implement"
type = "implement"
needs = ["design"]
outputs = ["src/book/**", "tests/book/**"]
gate = ["cmake --build build", "ctest --test-dir build -R book"]
reviewers = ["principal-engineer", { perspective = "devops", advisory = true }]

[[task]]
id = "signoff"
type = "human"
needs = ["implement"]
```

### Task keys

| Key | Kinds | Meaning |
|---|---|---|
| `id` | all | Required. Unique. `[A-Za-z0-9][A-Za-z0-9_-]*` |
| `type` | all | Required. A type from the library, or a bare kind (`produce`, `review`, `check`, `human`) for a one-off |
| `title` | all | Shown in status, and the commit subject for a producer. Default: the id |
| `prompt`, `prompt_file` | produce, review | The brief. A type's template wraps it |
| `needs` | all | Task ids that must be **accepted** first |
| `outputs` | produce | Required. Paths or globs of the deliverables |
| `gate` | produce | Commands that must exit 0 after each attempt |
| `reviewers` | produce | Panel shorthand, see below |
| `reviews` | review | The producer under review. Set automatically for panel members |
| `perspective` | review | A persona name |
| `advisory` | review | `true`: this reviewer's findings never block |
| `verifies` | check, human | The producer this task verifies. A failure or rejection sends that producer to rework |
| `run` | check | Required for a check. Commands that must exit 0 |
| `read_only` | check | `true`: the commands write nothing, so the check may run in parallel with readers |
| `params` | all | Values for the type's own parameters |
| `agent`, `model`, `max_attempts`, `timeout_min`, `budget_usd`, `protected` | as applicable | Override the defaults for this task |

### Panel shorthand

`reviewers` on a producer expands into one review task per entry. An entry is a persona name, or a
table with `perspective` and any review key (`advisory`, `agent`, `model`, `type`, `prompt`).

```
reviewers = ["principal-engineer", { perspective = "devops", advisory = true }]
```

becomes

```
implement.review.principal-engineer   type = code-review   reviews = implement
implement.review.devops               type = code-review   reviews = implement   advisory = true
```

The review type comes from the producer's type: each `produce` type names its `review_type`
(`design` names `design-review`, `implement` names `code-review`). A review task can also be
written out in full as its own `[[task]]` when it needs more than the shorthand gives.

### Validation

`validate` reports every problem at once, then prints the expanded DAG in execution order.

| Check | Example message |
|---|---|
| Unknown key, anywhere | `task 'design': unknown key 'ouputs'` |
| Missing or malformed `id`, duplicate `id` | |
| Unknown `type`, `perspective`, `agent`, or missing type parameter | `task 'r1': persona 'sre' not found in library` |
| `needs`, `reviews` or `verifies` names no task, or the wrong kind | `'reviews' must name a produce task` |
| A cycle | `dependency cycle: a -> b -> a` |
| **A producer with no verifier** (D7) | `task 'design' has no gate, check, review or human verifier` |
| A producer with no `outputs` | |
| A check with no `run` | |
| Warning: a later task claims frozen outputs (D8) | `'extend' will modify outputs of accepted task 'implement': src/book/**` |
| Warning: an agent is configured to bypass its sandbox or permissions | |
| Warning: the whole panel of a producer is advisory and it has no other verifier | treated as an error |

## Type file

`library/types/<name>.toml`

```toml
name = "design"
kind = "produce"
description = "Write or revise a design document"
review_type = "design-review"        # which review type a `reviewers` panel uses
agent = ""                           # optional defaults, below the task and above the workflow
model = ""
gate = []                            # default gates, e.g. a link checker
protected = []

prompt = """
...template text with placeholders...
"""

[params.audience]                    # parameters a task may set under `params`. Tables go last in TOML
default = "an engineer joining the project"
[params.sections]
default = ""                         # if set, a free structural check: these headings must exist
```

### Placeholders

Replaced by plain string substitution, so the same state always gives the same prompt. An unknown
placeholder is a validation error.

| Placeholder | Filled with |
|---|---|
| `{task.id}`, `{task.title}`, `{task.prompt}` | From the task |
| `{param.NAME}` | The task's value, or the type's default |
| `{inputs}` | For each upstream task: id, type, title, summary, output files |
| `{outputs}` | The task's declared outputs |
| `{gates}` | The commands that will be run |
| `{rules}` | The standing rules: do not commit; your report does not count; never weaken a check; answer `blocked` if it cannot be done properly; the protected and frozen paths |
| `{persona}` | The persona's rendered text (review types) |
| `{target}` | The producer under review: id, title, brief, outputs (review types) |
| `{diff}` | The diff of the work under review, capped (review types) |
| `{findings}` | On rework: the consolidated findings. In a later review round: the reviewer's own open findings with the author's responses |
| `{attempt}`, `{max_attempts}` | |
| `{result_schema}` | The JSON schema of the answer the task must end with |

## Persona file

`library/personas/<name>.toml`

```toml
name = "principal-engineer"
code = "PE"                          # prefix of this persona's finding ids
title = "Principal engineer"
agent = ""                           # optional: give this perspective to another agent or model
model = ""
advisory = false                     # default for this persona

focus = [ "...", "..." ]             # what this reviewer looks at
blocking = [ "...", "..." ]          # what justifies a blocking finding from this perspective
out_of_scope = [ "...", "..." ]      # what to leave to the other reviewers
```
