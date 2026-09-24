# 00 — Decision log

Taken with the owner on 2026-09-19, one question at a time. Each decision lists what was chosen,
what was turned down, and why. Later documents refer to these as D1 to D16.

| # | Question | Decision | Turned down, and why |
|---|---|---|---|
| D1 | A rejecting review must send work back, which is a cycle. How does that fit a DAG? | **Bounded rework edge.** The workflow is an acyclic DAG. Review is a first-class task that names the task it reviews. A rejection re-runs that task with the reasons, up to a limit, then re-runs the review. This is the only loop, and it is built in | Review inside every task: a review could not be its own task with its own agent, inputs and outputs. General cyclic graph (Attractor): needs a condition language and visit limits, and the research found we need little of it. No loops: not "run to completion" |
| D2 | What is a task's output, and how does the next task get it? | **Declared files plus a short structured result.** Owner's addition: all work for a run lives under **one directory per run, with a UUID**, structured like a build directory: every task, every re-attempt, hierarchical, and friendly to an agent that later reviews status or summarises | Captured text only: bloats prompts, not durable, does not fit code. Key-value context: documents and code do not belong in it. Implicit via the repo: the runner could not verify that a stage produced anything |
| D3 | Where do deliverables live? | **In the repository** at their declared paths, where gates can build and test them and git tracks them. **The run directory holds the record**, including a manifest of output files with hashes and the diff for each attempt | Everything in the run directory: code could not be built in place. A git worktree per run: a full checkout and build directory per run, plus a merge step. Deferred, not rejected |
| D4 | How are task types defined? | **Four engine kinds** (`produce`, `review`, `check`, `human`). **Types are templates** in files, with parameters. Owner's addition: a review type takes a **reviewer perspective** as a parameter (principal engineer, DevOps, process manager, spec compliance, technical or project manager, …). Perspectives are **personas**, defined in files like types | Fixed built-in types: every new kind of work would be a code change. Free-form tasks only: every plan would repeat the same instructions, and quality would depend on each author |
| D5 | Several reviewers on the same work: how are verdicts combined? | **Blocking and advisory findings, one consolidated rework.** The whole panel runs before anything goes back. The work passes when no blocking finding is open. A reviewer can be marked advisory | One at a time: a late objection arrives after several full loops. Majority vote: a spec or security objection could be outvoted. Lead reviewer agent: an extra model call every round, and judgement in place of rules |
| D6 | How much runs in parallel at first? | **Readers in parallel, writers one at a time.** Reviews and read-only checks run together up to `max_parallel`. Producers run singly, in plan order. A writer never runs while readers are running | Fully serial: a five-person panel would take five times as long for nothing. Worktree per task: merge handling and a C++ build directory per worktree. Deferred |
| D7 | What makes a producer's work accepted? | **Every producer needs a verifier**: its own gates, a `check`, a `review` or a `human` task. A workflow with an unverified producer is rejected at load. Cheap verifiers run first | Gate always mandatory: for a document, a script checks form, not substance. Verification optional: reopens "accepted because the agent said so" |
| D8 | When may a dependent task start? | **Only after upstream is accepted.** Accepted outputs are **frozen**: protected against every later task unless that task claims them in its own `writes` (B4) | Start early and redo if upstream changes: wasted spend and stale tracking across the DAG. Per-edge choice: a subtle correctness decision on every author |
| D9 | What happens to the DAG when a task fails? | **Set the failed work aside and continue other branches.** The changes are saved as a patch, the tree returns to the last accepted state, dependants are skipped, independent branches run on. `retry` re-applies the patch or starts clean | Stop at first failure: one stuck task idles a wide DAG. Continue on top of failed work: mixes broken changes into later diffs, gates and commits |
| D10 | What does the workflow file look like? | **One TOML file**: `[[task]]` entries with `type`, `needs`, parameters and `outputs`. `reviewers = [...]` on a producer expands into a panel. `validate` prints the expanded DAG; `graph` writes Graphviz DOT for viewing | DOT as the source format: hand-written parser, prompts and lists sit badly in attributes. One file per task: the DAG is scattered and hard to review |
| D11 | How are runs created, named and resumed? | **`start` always creates a run; `resume` continues one.** Directory `<workflow>-<UTC timestamp>-<uuid8>` (the workflow name was added later so a run directory says what it is on its own; `--runs-dir` chooses where the record lives), full UUID in `run.json` and exported to every agent call. The workflow file is copied into the run | One `run` command that decides: easy to resume when you meant to restart, and both mistakes cost money. One overwritten state per workflow: loses the history the owner wants to review |
| D12 | What if the workflow file is edited mid-run? | **Frozen copy, explicit `replan`.** `resume` uses the run's copy. `replan` shows the difference per task and applies it only where safe; changing an accepted task needs `--reopen`, which resets it and everything downstream. Every replan is recorded | Always read the live file: the record could not say which plan produced which result. Immutable runs: one wrong gate late in a run would discard hours of accepted work |
| D13 | How is accepted work recorded in git? | **A run branch, one commit per accepted producer**, holding only its files, rework squashed in, run UUID and task id in the message. Nothing is pushed or merged. `branch = "current"` opts out | Current branch by default: an abandoned run leaves commits mixed into the working branch. No commits: setting failed work aside needs a committed baseline |
| D14 | How is the record made reviewable? | **Self-describing, with no model calls by the runner.** `STATUS.md` per run and per task and `index.json` at every level, regenerated from state. One `README.md` explains the layout. Narrative summaries are a task type | Model summary after each task: the runner would spend money on its own and stop being deterministic. Raw record only: every later review starts by reconstructing the picture |
| D15 | How do panels converge? | **Tracked findings; later rounds judge the fix.** Findings have stable ids and a status. Round 1 is a full review. Later, a reviewer marks each of its findings resolved or unresolved and may block only on what the rework changed. The author may answer `disputed`; a dispute that stays open goes to a person | Fresh full review every round: new blockers on unchanged parts forever. One round only: nobody checks the blocking findings were fixed |
| D16 | What is created now? | **Design artifacts only**, in `task_runner/`, including draft library content. No code | |

## Defaults assumed without asking

The owner can overrule any of these.

| Topic | Assumed |
|---|---|
| Settings precedence | task, then persona, then type, then workflow `[defaults]`, then built-in. `protected` is the exception: the union of every level, never narrowed (B9) |
| Reviewer's agent | The same agent as the author, in a new read-only session. A persona or a task can name another |
| Rework limit | `max_attempts = 3` executions of a producer, whatever sent it back. Protocol retries (2 per call) are counted apart (A6) |
| Passed reviewers after rework | Re-run on the rework diff only (`recheck_passed = "diff"`); `"never"` is allowed |
| Limits | Per call: `timeout_min` 30, `budget_usd` 5. Per run: `run_budget_usd` 50. `gate_timeout_min` 20. `max_parallel` 4 |
| Agents | Claude Code, Codex, and any command, as designed in the research |
| Codex in this container | **Withdrawn, see A5.** "Reviewer only" was never established: the recorded Codex reviews read no files. Roles follow what `doctor` qualifies |
| Run records in git | `.runs/` ignores itself. Committing a run record is the owner's choice |
| Language | Python 3.11+, standard library only. Linux first; process identity is weaker elsewhere (B6) |

## Amendments after the design review (2026-09-19)

An independent review of this design ([review](../../reviews/task-runner-review.md),
[Codex companion](../../reviews/task-runner-codex-headless.md)) found twelve defects. All twelve were
confirmed. The full reply, including where a different remedy was chosen and why, is in
[the response](../../reviews/task-runner-review-response.md).

| # | Review | Amendment | Refines |
|---|---|---|---|
| A1 | P1-01 | **A producer owns the work tree for its whole life cycle**: produce, gates, checks, panel, human decision, commit or set-aside. Nothing else is scheduled meanwhile. A pending human verification holds the tree and stops the run | D6, D9 |
| A2 | P1-02 | **Intent, effect, outcome** for every external effect, with operation ids in commit trailers; reconciliation on resume; process identity by group id and start time; attempt numbers never reused; synced state; snapshots pinned under private refs | D11 |
| A3 | P1-03 | **Restore by git type and mode**, never by writing bytes; links replaced and never followed; parents checked; submodules refused; recovery uses the pinned tree and a full binary patch, never the capped review diff. No prototype code is carried over unchanged | D9 |
| A4 | P1-04 | **No dirty starts.** `allow_dirty` is removed. `resume` detects branch, index or tree changes made while paused | D13 |
| A5 | P1-05 | **Capabilities, not a greeting**: `doctor` qualifies `answer`, `read`, `execute`, `write`, `resume`, `boundary` per agent profile; types state what they need; text-only review is a separate, explicit, labelled mode. The "Codex: reviewer only" default is withdrawn | — |
| A6 | P1-06 | **A result needs a normal exit, a terminal event of this invocation, a final answer of this invocation, and the runner's own validation** of shape and meaning. Invalid answers get bounded protocol retries, never findings or rework. Environment failures stop the run without using attempts | D7 |
| A7 | P1-07 | **Attempts and review rounds are counted apart**; a reviewer's first sight is always a full review. **Verdicts are derived from the ledger.** Finding ids are unique in the run (`implement/PE-2`). A later-round blocker outside the diff stands if it names a changed location in `caused_by`, which the runner checks | D15 |
| A8 | P1-08 | **Candidate and accepted milestones** per producer; `needs` targets accepted, `reviews` and `verifies` target the candidate; cycles are detected in that expanded graph, with a trace | D7, D8 |
| A9 | P1-09 | **`writes` (allowlist, default `outputs`) and `removes`**; `may_be_empty` outputs; control directories refused; **every verification bound to the candidate tree and config hash**, with a snapshot after each verifier and before commit; the record's integrity checked around every job | D3, D7 |
| A10 | P1-10 | **Input manifests** per accepted task; overlapping writers must be dependency-ordered; a claiming task re-runs the gates of accepted work it touched; review-only consumers are marked stale; `--reopen` computes the affected closure and undoes it with revert commits; prompt files and `root` are frozen at start | D8, D12 |
| A11 | P2-11 | **Budget by reservation** before dispatch; spend reported as known, reserved and unpriced; no dollar promise for agents that report no cost; the `max_tokens` idea is dropped because usage arrives only when a turn ends (`run_budget_tokens` is a stop line between calls, not a cap within one); logs streamed to disk | defaults |
| A12 | P2-12 | **Gates are invariants unless marked `new`**; `check-gates` reports pass, fail or error and only objects where a `new` gate does not fail for the right reason. **No-progress needs the same failure and the same candidate tree** | D7 |

## Amendments after the adversarial review (2026-09-19)

A second, adversarial review of the amended design
([review](../../reviews/task-runner-adversarial-review.md)) raised 38 findings: 7 blockers, 18 major,
13 minor. The git and glob claims were reproduced before acting. All 38 were accepted as defects;
five got a different remedy from the one proposed. The reply is in
[the response](../../reviews/task-runner-adversarial-review-response.md).

| # | Findings | Amendment | Refines |
|---|---|---|---|
| B1 | ADV-01, 12, 24, 25 | **The review protocol is made satisfiable.** Advisory findings close as `noted` when raised; `resolutions` cover open blocking findings only. The rework diff is per reviewer, from its `last_seen_candidate`. A rework prompt holds the immediate cause plus the blocking findings still needing a response, and `responses` cover exactly those. `resume` is an optimisation, never required. `retry` starts a new line of work: round 1 again, old findings `superseded` | A6, A7, D15 |
| B2 | ADV-02, 35, 36, 38 | **The run branch is checked out, and the index follows every commit** (`git read-tree HEAD` after `update-ref`, inside the commit intent). One reused scratch index per run. `branch = "current"` creates no branch. Restores remove the directories they emptied | D13, A3 |
| B3 | ADV-03, 08, 09, 21 | **Git is required, and the work must be visible to it.** Ignored declared paths are refused, at load and after each attempt. `.gitignore`, `.gitattributes`, `.gitmodules` are protected by default. Embedded repositories and submodule entries are removed right after the attempt that made them. After any verifier changes the tree, the runner restores the candidate. The guarantee is stated as tree-level | A3, A9 |
| B4 | ADV-04, 07, 22, 28, 30, 31, 33, 37 | **The workflow-file contract is closed.** One path-pattern matcher with stated semantics, and conservative cover and overlap tests. A frozen output is claimed through `writes`. Bare kinds are real type files. Relative paths resolve against the workflow file. Required parameters, unique persona codes, `fail_pattern` semantics, `outputs` ∩ `removes`, reserved dots in ids | D8, D10, A9, A10 |
| B5 | ADV-05 | **Capability probes are judged by effects the runner observes**, never by tool events, which Claude Code's print mode does not emit. The capability check moves from `validate` to `doctor` and `start`. Host identity is defined | A5 |
| B6 | ADV-06, 34 | **Every external effect has an intent and a reconciliation**, most by being idempotent; reverts are resumable. Process identity is pid, start ticks and boot id, on Linux. `prune` removes the refs of finished runs | A2 |
| B7 | ADV-10, 11, 19, 23, 26, 27 | **Verifier behaviour is complete.** Standalone checks and human tasks have defined failure. Writing standalone checks are rolled back. New status `objected`; the skip closure follows `needs`, `reviews` and `verifies`. `read_only` is verified. `restores = true` for verifiers that change source and put it back. A panel that cannot answer leaves its producer `blocked`. `retry` respects an open transaction | A1, A9, D7 |
| B8 | ADV-13, 17, 29 | **The record is protected by hashes, not file modes**: an integrity manifest over every decision-bearing file, the ledger included. `TASK_RUNNER_RUN_DIR` goes only to types that ask for it. Review rounds have invocation directories | A9, A6 |
| B9 | ADV-14 | **`protected` is a union and cannot be narrowed.** Files a gate executes are protected by default | D8 |
| B10 | ADV-15, 16 | **A budget stop and an escalation are pauses that hold the tree**, like a human approval. `resume --add-budget`. `resolve --as resolved, advisory or upheld` followed by `resume` continues acceptance with no repeated work | A1, A11, D15 |
| B11 | ADV-18 | **Prompt assembly is specified**: one pass over the template, fenced data blocks, size caps with an overflow rule per placeholder; findings are never truncated | D4 |
| B12 | ADV-20 | **The plan is corrected**: scenarios moved to the stage that can pass them, unowned scenarios and deliverables assigned, the scripted agent's contract written down | — |
