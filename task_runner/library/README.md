# Starter library

Draft content for the runner's built-in library. These files are read by the runner; changing how a
type of work is briefed, or what a reviewer looks for, means editing a file here, not code. A
workflow can add its own directory of types and personas with `library = [...]`, and a file there
with the same name replaces the one here.

| Types | Kind | |
|---|---|---|
| `design` | produce | A design document. Panels use `design-review` |
| `implement` | produce | Code and tests, from a brief and an accepted design. Panels use `code-review` |
| `test` | produce | Tests written from a specification, apart from the code |
| `summarize` | produce | A narrative summary written from the run record |
| `design-review` | review | One perspective on a design |
| `code-review` | review | One perspective on a code change. Always checks for weakened tests and out-of-brief changes |

Each type lists the **capabilities** its agent must be qualified for (`requires`): authors need
`write`, reviewers need `read`. `doctor` establishes them per agent profile, and a workflow that
asks for more than a profile has is refused before any work starts.

`check` and `human` need no type file: a task names the kind directly.

| Personas | Code | Blocks by default |
|---|---|---|
| `principal-engineer` | PE | yes |
| `spec-compliance` | SC | yes |
| `devops` | DO | yes |
| `process-manager` | PM | no, advisory |
| `technical-project-manager` | TPM | no, advisory |

Every persona lists what is **out of scope** for it and who covers that instead. This is what keeps
a panel of five from raising the same point five times. A workflow can make an advisory persona
blocking, or the reverse, per task.

The format of both file types is in [`../docs/03-workflow-file.md`](../docs/03-workflow-file.md).
