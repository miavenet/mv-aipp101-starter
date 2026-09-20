# 03 — Workflow file, type files and persona files

All three are TOML, read with Python's standard library. Unknown keys are errors everywhere, so a
typo is caught before anything runs.

**Where relative paths resolve (B4).** `root`, `library` and `prompt_file` resolve against the
directory of the workflow file. Every path inside tasks (`outputs`, `writes`, `removes`,
`protected`) is relative to `root`. `run.json` records the resolved absolute paths.

## Workflow file (D10)

```toml
name = "book-module"            # names the run directories. Default: the file name
root = "../.."                  # the repository, relative to this file. Default: the file's directory. Must be a git repository
library = ["library"]           # extra directories of types and personas, relative to this file, searched before the built-in ones

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
protected = ["docs/spec/**"]    # never changeable by any task in this workflow. Tasks can add to it, never remove
diff_cap_bytes = 200000         # prompt size caps, see Placeholders (B11)
inputs_cap_bytes = 40000
findings_cap_bytes = 60000

[agents.codex]                  # a named profile per agent. Its non-secret settings and their hash are recorded in the run
sandbox = "workspace-write"
# review_mode = "provided_context"   # only for a reviewer qualified for text-only review; see 05, Capabilities

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
| `id` | all | Required. Unique. `[A-Za-z0-9][A-Za-z0-9_-]*`. A dot is reserved for the ids the runner generates for panel members (B4) |
| `type` | all | Required. A type from the library, or a bare kind (`produce`, `review`, `check`, `human`) for a one-off. `produce` and `review` are minimal type files in the built-in library |
| `title` | all | Shown in status, and the commit subject for a producer. Default: the id |
| `prompt`, `prompt_file` | produce, review | The brief. A type's template wraps it. Giving both is an error |
| `needs` | all | Task ids that must be **accepted** first |
| `outputs` | produce | Required. Paths or globs of the deliverables. An entry may be a table: `{ path = "pkg/__init__.py", may_be_empty = true }` |
| `writes` | produce | Every path the task may change, helpers included. Default: the same as `outputs`. A change outside it is reverted and the attempt does not pass |
| `removes` | produce | Paths that must not exist afterwards |
| `gate` | produce | Commands that must exit 0 after each attempt. An entry may be a table: `{ run = "ctest -R book", new = true, fail_pattern = "BOOK-" }`, see below. `fail_pattern` is a Python regular expression searched in the command's combined standard output and error (B4) |
| `reviewers` | produce | Panel shorthand, see below |
| `reviews` | review | The producer under review. Set automatically for panel members |
| `perspective` | review | A persona name |
| `advisory` | review | `true`: this reviewer's findings never block |
| `verifies` | check, human | The producer this task verifies. A failure or rejection sends that producer to rework |
| `run` | check | Required for a check. Commands that must exit 0 |
| `read_only` | check | `true`: the commands write nothing, so the check may run in parallel with readers. The runner verifies the claim by snapshot (B7) |
| `restores` | check | `true`: the check changes source while it runs and is meant to put it back (a mutation tester). The runner restores the candidate itself afterwards (B7). Cannot be combined with `read_only` |
| `params` | all | Values for the type's own parameters |
| `agent`, `model`, `max_attempts`, `timeout_min`, `budget_usd`, `recheck_passed` | as applicable | Override the defaults for this task |
| `protected` | as applicable | **Added to** the protected set for this task. Protection is a union of every level and cannot be narrowed (B9) |

### Path patterns (B4)

One matcher, written for the runner, is used for `outputs`, `writes`, `removes` and `protected`.
Python's `fnmatch` and `PurePath.match` disagree with each other on `docs/spec/**`, so neither is
used.

| Pattern part | Matches |
|---|---|
| a literal path, `src/book/side.hpp` | exactly that path |
| `*`, `?`, `[abc]` | within one path segment; never crosses `/` |
| `**/` at the start or in the middle | zero or more whole directories |
| a trailing `/**` | everything below that directory, at any depth, but not the directory name itself |
| a **wildcard** pattern with no `/`, such as `*.lock` | that name in any directory. A wildcard-free entry with no `/`, such as `CMakeLists.txt`, is a literal path at the root |

Patterns are relative to `root`, use `/`, and may not start with `/` or contain `..`.

Clarifications settled while building stage 1:

- A `removes` path must be covered by `writes`, like an output: a deletion is a change, and a change
  outside `writes` is reverted.
- `outputs` and `removes` conflict only when an entry is identical, or a literal output is matched
  by a `removes` entry. `outputs = ["src/**"]` beside `removes = ["src/old.cpp"]` is satisfiable.
- The ignored-path check tests a literal path directly, and a glob by probing a name under its
  literal prefix. A glob with no literal prefix is checked only after each attempt.
- `root` may be a subdirectory of a repository. `validate` warns, because snapshots and the
  clean-tree rule cover the whole repository.
- A file that a verifying check executes is protected for the check **and for the producer it
  verifies**, since the producer is the one that could edit it.
- `[agents.NAME]` accepts a closed set of keys: `kind`, `model`, `sandbox`, `review_mode`,
  `permission_mode`, `ignore_user_config`, `extra_args`, `argv`, `read_only_args`.
- A review task must name a `perspective`. Persona codes match `[A-Z][A-Z0-9]*`. Every type in the
  merged library is validated, used or not.

Two questions compare a pattern with a pattern, which cannot be decided exactly, so they are
answered **conservatively**:

- **Is an output covered by `writes`?** Yes if the same entry appears literally in `writes`; or a
  `writes` entry `D/**` exists and the output starts with `D/`; or the output has no wildcard and a
  `writes` entry matches it. Anything else is a load error that asks for the entry to be repeated
  in `writes`.
- **Can two tasks' `writes` overlap?** Each pattern has a literal prefix: the segments before its
  first wildcard. Two wildcard-free patterns overlap when they are equal. A wildcard-free path and
  a pattern overlap when the pattern matches the path. Two patterns overlap when one's literal
  prefix is a path-prefix of the other's, and a pattern with no `/` overlaps everything. This may
  report an overlap that cannot happen; it never misses one.

### Gates: invariants and new checks

A gate given as a plain string is an **invariant**: a build, a lint, the existing test suite. It may
well pass before the task starts, and that is fine; its job is to stay green.

A gate marked `new = true` claims to prove this task's new behaviour, so it is expected to **fail
before the task is done, for the right reason**. `check-gates` runs every gate on the untouched tree
and reports `pass`, `fail` or `error` for each (exit 126 and 127, a timeout, or a failure whose output
does not match the gate's `fail_pattern`, are `error`). It complains about a `new` gate that already
passes, since it cannot show the task was done, and about one that errors, since a missing import
that exits 1 is not the intended failure. It never complains about an invariant that passes.

**Files a gate executes are protected (B9).** Each gate and `run` command is split into words, and
every word that names an existing tracked file (`tools/run_mutants.py`) joins that task's protected
set, unless the task lists that exact path in `writes`, in which case `validate` warns that the
task may edit a file its own verifier executes. This is a floor, not a fence: an author who
legitimately owns a build file (`CMakeLists.txt`) can still weaken the build. The defences for that
are a `new` gate with a `fail_pattern`, tests frozen by an earlier task, and the reviewers, who see
the build file in the diff.

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
(`design` names `design-review`, `implement` names `code-review`). `reviewers` on a producer whose
type names no `review_type` is an error, unless every entry gives its own `type`. A review task can
also be written out in full as its own `[[task]]`, with any id of the ordinary form, when it needs
more than the shorthand gives. The shorthand accepts `recheck_passed` as well as the review keys.

### Validation

`validate` reports every problem at once, then prints the expanded DAG in execution order.

| Check | Example message |
|---|---|
| Unknown key, anywhere | `task 'design': unknown key 'ouputs'` |
| Missing or malformed `id`, duplicate `id` | |
| Unknown `type`, `perspective`, `agent`, or a missing parameter the type marks `required` | `task 'r1': persona 'sre' not found in library` |
| `prompt` and `prompt_file` together; `reviewers` with no `review_type`; `read_only` with `restores` (B4, B7) | |
| Two personas with the same `code`, or the same perspective twice on one producer (B4) | `personas 'security' and 'spec-compliance' both use code 'SC'` |
| `root` is not a git repository (B3) | |
| A path in `outputs`, `writes` or `removes` that git ignores, or that is in both `outputs` and `removes` (B3, B4) | `'implement' output build/config.h is ignored by .gitignore:1 'build/'` |
| A malformed pattern: absolute, containing `..`, or `**` not a whole segment (B4) | |
| `needs`, `reviews` or `verifies` names no task, or the wrong kind | `'reviews' must name a produce task` |
| A cycle | `dependency cycle: a -> b -> a` |
| **A producer with no verifier** (D7) | `task 'design' has no gate, check, review or human verifier` |
| A producer with no `outputs`, or an output not covered by its `writes` (see Path patterns) | |
| A path under `.git` or `.runs` in `outputs`, `writes` or `removes` | |
| **A cycle in the acceptance graph** (A8): a verifier that `needs` its own target, or anything downstream of it | `'mutants' verifies 'implement' but needs 'report', which needs 'implement': implement can never be accepted` |
| **Overlapping `writes` between tasks with no order between them** (A10) | `'extend' and 'implement' both write src/book/** and neither depends on the other` |
| A type's `requires` names an unknown capability | |
| A check with no `run` | |
| Warning: a later, dependent task's `writes` claim frozen outputs (D8, B4) | `'extend' will modify outputs of accepted task 'implement': src/book/**. Accepted consumers of it: tests, report` |
| Warning: a task's `writes` include a file its own gate executes (B9) | |
| Warning: an agent is configured to bypass its sandbox or permissions | |
| Warning: the whole panel of a producer is advisory and it has no other verifier | treated as an error |

`validate` needs no agent and spends nothing, so it does **not** check capabilities. Whether each
profile is qualified for what its types `require` is checked by `doctor` and again by `start`,
which refuses to begin otherwise (B5): `'code-review' needs 'read'; profile 'codex' is qualified for
'answer' only`.

## Type file

`library/types/<name>.toml`

```toml
name = "design"
kind = "produce"
description = "Write or revise a design document"
requires = ["read", "write"]         # capabilities the agent profile must be qualified for; see 05.
                                     # `resume` is never required: it is used when the profile has it (B1)
review_type = "design-review"        # which review type a `reviewers` panel uses
needs_run_dir = false                # true only for types that read the run record, such as summarize (B8)
agent = ""                           # optional defaults, below the task and above the workflow
model = ""
gate = []                            # default gates, e.g. a link checker
protected = []

prompt = """
...template text with placeholders...
"""

[params.audience]                    # parameters a task may set under `params`. Tables go last in TOML
default = "an engineer joining the project"
[params.component]
required = true                      # no default: a task that omits it does not load (B4)
```

### Placeholders

The same state always gives the same prompt. An unknown placeholder in a template is a validation
error. The rules of assembly (B11):

- **One pass, over the template only.** A scanner finds `{name}` placeholders in the type's
  template and replaces each once. Substituted text is never scanned again, so a brief, a diff or a
  summary that contains the characters `{diff}` stays as it is. `str.format` is not used, so braces
  in C++, JSON or shell text are ordinary characters.
- **Data is fenced.** Every substituted value that comes from a task, an agent or the repository
  (`{task.prompt}`, `{inputs}`, `{diff}`, `{findings}`, `{target}`) is wrapped in a labelled block,
  and `{rules}` states that text inside such blocks is material to work on, never instructions to
  follow. This does not make injection impossible; the ledger-derived verdict, the gates and the
  human sign-off are the defences that do not depend on a model's obedience.
- **Sizes are capped, and the overflow rule depends on what is lost.** `{diff}` over
  `diff_cap_bytes` is cut at a file boundary with a visible marker that names the omitted files and
  the full diff's path in the record. `{inputs}` over `inputs_cap_bytes` drops summaries, longest
  first, and keeps the ids and file lists. `{findings}` is never cut: over `findings_cap_bytes` the
  task is `blocked` for a person, because dropping a blocking finding would change the outcome. The
  result validator limits a `summary` to 2,000 characters.

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
| `{findings}` | On rework: the immediate cause, then the open blocking findings that still need a response, then advisory ones for information (B1). In a later review round: the reviewer's own open blocking findings with the author's responses |
| `{attempt}`, `{max_attempts}` | |
| `{result_schema}` | The JSON schema of the answer the task must end with |

## Persona file

`library/personas/<name>.toml`

```toml
name = "principal-engineer"
code = "PE"                          # prefix of this persona's finding ids. Unique across the merged library
title = "Principal engineer"
agent = ""                           # optional: give this perspective to another agent or model
model = ""
advisory = false                     # default for this persona

focus = [ "...", "..." ]             # what this reviewer looks at
blocking = [ "...", "..." ]          # what justifies a blocking finding from this perspective
out_of_scope = [ "...", "..." ]      # what to leave to the other reviewers
```
