
# agate implementation notes

Source: `/tmp/claude-502/-workspace/80e21667-2974-4342-827a-d808142e54ae/scratchpad/repos/agate`, commit `ea95448` ("Merge web-frontend: terminal colors, lean sprint execution, interview UX"). Go 1.24 (go.mod:3-4). All line numbers are from files at that commit; paths below are given relative to the repo root unless a full path is shown.

All claims are **observed** (read directly in the source) unless explicitly marked **inferred**.

## Key takeaways for building our runner

1. All workflow state is *re-derived from disk on every invocation* — there is no in-memory or hidden state carried between calls. `GetStatus(fsys fs.FS)` (`internal/workflow/state.go:39-84`) rebuilds the entire `StatusResult` from `GOAL.md`, `.ai/interview.md`, `.ai/design/*`, `.ai/skills/*`, `.ai/sprints/*` every time it runs, and the doc comment even states "This function contains NO os.* calls" (`internal/workflow/state.go:38`).
2. `agate auto` is not an in-process loop — it's a subprocess loop: `cmd/auto.go:59-75` (`realExec`) re-execs `os.Executable()` with args `["next", ...]`, and `AutoRunner.Run` (`cmd/auto.go:98-153`) only inspects the child's exit code. There is no direct call from `auto` into `workflow.NextWithOptions`.
3. Exit codes are four hard constants reused everywhere: `ExitDone=0, ExitMoreWork=1, ExitError=2, ExitHumanNeeded=255` (`internal/workflow/exitcode.go:5-9`), computed by one pure function `GetExitCode(r StatusResult)` (`internal/workflow/exitcode.go:19-45`).
4. Task/sprint status is not an enum — it's markdown checkbox characters plus emoji counters parsed by two regexes: top-level `^- \[([ xX])\] ((?:❌|🔄)*)\s*(.*)$` and sub-task `^  - \[([ xX])\] ([^:]+): (.*)$` (`internal/workflow/sprint.go:80-81`).
5. Agents are invoked by shelling out to the `claude`/`codex` CLIs in full-file-write mode (`--dangerously-skip-permissions`, `--full-auto-net`) so the *agent itself* writes design/decision/sprint/implementation files directly to disk (`internal/agent/claude.go:40`, `internal/agent/codex.go:40`). Agate only validates the result afterward (`validateMarkdownContent`, `internal/workflow/plan.go:379-410`) — it does not re-parse those files from agent stdout, except for interview questions and (redundantly) implementation file blocks (see §3 below).
6. Review gating is a literal substring check: `strings.Contains(strings.ToUpper(output), "APPROVED")` (`internal/workflow/next.go:371-374`) — there is no independent build/test/lint invocation by agate itself.
7. Retry ceiling is `maxReviewRetries = 3` (`internal/workflow/next.go:18`); after 3 failures it attempts exactly one replan via the `_replanner` skill (`internal/workflow/next.go:126-142`), and a second run of 3 failures after that replan raises `HumanNeededError` (`internal/workflow/next.go:128-131`), which maps to exit 255.
8. No git integration exists anywhere: a repo-wide grep for `exec.Command`/`"git"`/`worktree`/`branch` inside `.go` files turns up nothing except the CLI-invocation lines for `claude`/`codex` and agate's own self-re-exec in `auto.go`. Agate never commits, branches, or creates worktrees.
9. `agate suggest` is a no-op: `AddInterrupt` "acknowledges a suggestion but does not persist it" (`internal/workflow/interrupt.go:8-13`), even though `cmd/auto.go:174-179` pipes stdin lines into it every loop iteration. The suggestion feature described in the README is currently inert.
10. Several subsystems exist in the codebase but are never wired into the `auto`/`next` execution path (dead code, confirmed by repo-wide grep for their call sites): `internal/agent/multi.go`'s parallel `MultiAgent`, `internal/workflow/retro.go`'s `RunRetrospective`/`RunEvolution`, and `internal/agent/executor.go`'s `Executor` type. Treat README/CLAUDE.md claims about "parallel for independent work" and sprint retrospectives as **aspirational, not implemented**.

## 1. Lifecycle state machine

### Phases

`PlanPhase` is a string enum (`internal/workflow/plan.go:34-40`):

| Constant | Value |
|---|---|
| `PhaseInterview` | `"interview"` |
| `PhaseDesign` | `"design"` |
| `PhaseDecisions` | `"decisions"` |
| `PhaseSprint` | `"sprint"` |
| `PhaseExecution` | `"execution"` |

`derivePhase(r StatusResult)` (`internal/workflow/state.go:87-114`) computes the phase purely from booleans already derived from disk in `GetStatus`:
- no `GOAL.md` → `PhaseInterview` (`state.go:89-91`)
- interview missing or not complete → `PhaseInterview` (`state.go:94-96`)
- no `.ai/design/overview.md` → `PhaseDesign` (`state.go:99-101`)
- no `.ai/design/decisions.md` → `PhaseDecisions` (`state.go:103-106`)
- no current sprint file found → `PhaseSprint` (`state.go:108-111`)
- otherwise → `PhaseExecution` (`state.go:113`)

### Dispatch ("what is the next step")

Two dispatch points, both pure functions of `GetStatus`'s output plus the sprint file's parsed checkbox tree:

- `ExecutePlanPhase` (`internal/workflow/plan.go:74-111`) is a `switch phase` over the five `PlanPhase` values that calls `executeInterviewPhase` / `executeDesignPhase` / `executeDecisionsPhase` / `executeSprintPhase`, one planning agent call per invocation.
- `NextWithOptions` (`internal/workflow/next.go:43-151`) is the top-level dispatcher used by `agate next`:
  - if `status.Phase != PhaseExecution` → delegates to `ExecutePlanPhase` (`next.go:61-68`)
  - else parses the current sprint file, and if `sprint.IsComplete()` calls `assessGoalAndPlanNext` (`next.go:87-90`, `748-843`)
  - else finds the next unchecked sub-task via `sprint.GetNextSubTask()` (`next.go:93`, `sprint.go:202-219`) and executes it via `executeSubTask` (`next.go:145-150`, `154-294`)
  - if the current top-level task's `FailureCount >= maxReviewRetries` it attempts replan instead of running the sub-task (`next.go:126-142`)

Both dispatchers derive their branch **entirely from what `GetStatus`/`ParseSprint` read off disk this call** — confirmed no package-level or struct-level state is retained between calls to `Next`/`NextWithOptions` (no global vars in `internal/workflow` besides the `maxReviewRetries`/`ExitXxx` constants).

## 2. `.ai/` persisted state

All state is plain markdown (or markdown+YAML-like frontmatter for skills); the project never writes JSON/YAML/binary state (a repo-wide grep for `json.Marshal`/`yaml.Marshal` in non-test code returns nothing).

| Path | Written by | Format | Notes |
|---|---|---|---|
| `GOAL.md` | Human (not agate) | Free-form markdown | Read by `project.ParseGoal` (`internal/project/goal.go:17-31`); language/type auto-detected by regex (`goal.go:34-81`) |
| `.ai/interview.md` | `executeInterviewPhase` (`plan.go:127-193`), content built by `logging.FormatInterview` (`internal/logging/format.go:98-123`) | Markdown with `### Qn:` headings, `- [ ]` option checkboxes, `> Answer:`/`> Notes:` blockquotes, and a trailing `- [x] All questions answered` completion checkbox | Completion tested by substring match, see §2.1 |
| `.ai/design/overview.md` | The **agent itself** (YOLO mode), per instruction in the prompt "Write the complete document content directly to this file path" (`plan.go:520-521`) | Markdown, must start with `#` | Validated post-hoc by `validateMarkdownContent` (`plan.go:379-410`), which also rejects agent meta-commentary (`plan.go:391-399`) |
| `.ai/design/decisions.md` | Agent itself, same pattern (`plan.go:619-620`) | Markdown | Same validation |
| `.ai/design/.drafts/` | Created by `EnsureDirectories` (`internal/project/project.go:57-73`) | n/a | **Never written to or read anywhere else** — grep confirms only `project.go:52-53,63` and a directory-creation test reference it |
| `.ai/sprints/NN-name.md` | Agent itself for sprint 1 (`plan.go:345,594-595`); agent itself for subsequent sprints via `assessGoalAndPlanNext` (`next.go:789,731-732`) | Markdown, nested checkboxes: `- [ ] Task` / `  - [ ] skill: subtask` | Filenames formatted `%02d-%s.md` (`sprint.go:196-198`); parsed by `ParseSprintContent` (`sprint.go:72-136`) |
| `.ai/skills/*.md` | `project.WriteSkills` for language/type skills (`plan.go:334-337`) and `project.EnsureBuiltinSkills` for `_`-prefixed builtins, **regenerated on every command invocation** via `cmd/root.go:30-44` `PersistentPreRun` | Markdown with YAML-like frontmatter (`---\nname:...\n---`), hand-parsed by `ParseSkillMetadata` (`internal/project/skills.go:27-87`), not a real YAML library | User override mechanism: if both `_foo.md` and `foo.md` exist, `foo.md` content is appended into `_foo.md`'s in-memory content at load time (`skills.go:188-231`) — but since builtins are rewritten from Go source every command run, only the *content* survives; overrides on the same file don't persist idempotently beyond in-memory merge |
| `.ai/logs/sprint-NNN/SEQ-phase-TASKIDX-skill-agent.md` | `logging.Logger.StartInvocation`/`Close` (`internal/logging/logger.go:55-95,131-142`), formatted by `FormatInvocation` (`logging/format.go:10-72`) | Markdown with a metadata table, Prompt, Response, Files Written, Error sections | **Fragile**: `Logger.sequence` is an in-process atomic counter that starts at 0 for every fresh `*Logger` (`logger.go:20-26`), and a brand-new `Logger` is constructed on every single `agate next` invocation (e.g. `next.go:123`). Two separate `next` calls that hit the same phase/taskIndex/skill/agent combination (e.g. retrying the same sub-task after a review failure) produce byte-identical filenames and **silently overwrite** the earlier log via `os.Create` (`logger.go:69`). Confirmed by reading `NewLogger`+`StartInvocation`+the call sites; not exercised by a specific failing test I found. |
| `.ai/retros/sprint-NNN.md` | `RunRetrospectiveWithOptions` (`internal/workflow/retro.go:28-160`) | Markdown | **Dead path**: `RunRetrospective`/`RunRetrospectiveWithOptions`/`RunEvolution` have no caller in `cmd/` or in `internal/workflow/next.go`/`plan.go` (grep confirmed) — there is no `agate retro` command in `cmd/` |

### 2.1 Interview completion / resumption after exit 255

`ParseInterviewStatus` (`internal/logging/format.go:134-147`) returns `true` if the file contains the literal substring `- [x] All questions answered` or `- [X] All questions answered` (new format), or the legacy substring `Status: COMPLETE`. `GetExitCode` treats "interview exists but not complete" as `ExitHumanNeeded` (`exitcode.go:26-28`). Resumption is simply: human edits `.ai/interview.md` to check that box, then `agate next`/`agate auto` re-derives status from disk and proceeds — there is no separate "resume" code path, it's the same `GetStatus` call.

### 2.2 Task/sub-task representation

`Task` and `SubTask` structs (`internal/workflow/sprint.go:16-34`):

```go
type Task struct {
    Index, LineNum       int
    Text                 string
    Checked              bool
    FailureCount         int // number of ❌ before task text
    ReplanCount          int // number of 🔄 before task text
    SubTasks             []SubTask
}
type SubTask struct {
    Index, LineNum, ParentIndex int
    Skill, Text                 string
    Checked                     bool
}
```

There is no separate "status" enum; effective status is a combination of `Checked` (bool), `FailureCount` (int, incremented by `AddFailure`, `sprint.go:374-406`), and `ReplanCount` (int, incremented by `AddReplanMarker`, `sprint.go:409-434`). All mutations (`CheckSubTask`, `CheckTask`, `UncheckSubTask`, `AddFailure`, `AddReplanMarker`, `ClearFailures`) work by finding the exact line number recorded at parse time and doing a string replace, then `os.WriteFile`-ing the whole file back (`sprint.go:256-297,299-335,374-469`).

### 2.3 Crash / exit-255 resumption in general

Because `GetStatus` re-derives everything from files and checkbox state is mutated file line-by-line as each sub-task completes, resumption after a crash mid-sprint is just: re-run `agate next`, it re-parses the sprint file, finds the first unchecked sub-task (`GetNextSubTask`, `sprint.go:202-219`), and continues. There is no separate crash-recovery bookkeeping (**inferred**: this works correctly as long as the crash happens strictly between sub-task-level file writes; there is no transactional or lock-file protection around the checkbox writes — `checkLineAt`/`uncheckLineAt` do a single `os.WriteFile`, so a crash mid-write could corrupt the sprint file, but I did not find any fsync/temp-file/atomic-rename pattern to confirm or rule this out either way).

## 3. Agent invocation

### 3.1 CLIs and exact flags

| Agent name | Binary looked up | Execute() flags | Notes |
|---|---|---|---|
| `claude` | `claude` (`exec.LookPath`, `internal/agent/claude.go:19`) | `--dangerously-skip-permissions --print -p <prompt>` (`claude.go:40,66`) | "YOLO mode" per code comment (`claude.go:39`) |
| `claude` (safe mode) | same | `--print -p <prompt>` (no `--dangerously-skip-permissions`) (`claude.go:98,123`) | Used only when `ExecuteOptions.SafeMode=true`, i.e. interview phase (`plan.go:172`) |
| `haiku` | `claude` (same binary!) (`internal/agent/haiku.go:19`) | `--dangerously-skip-permissions --model haiku --print -p <prompt>` (`haiku.go:41,66`); safe variant `--model haiku --print -p <prompt>` (`haiku.go:97,122`) | Not a separate CLI — it's the `claude` CLI with `--model haiku` |
| `codex` | `codex` (`internal/agent/codex.go:19`) | `--full-auto-net exec <prompt>` (`codex.go:40,66`) | No safe-mode variant defined (codex doesn't implement `SafeModeAgent`) |
| `dummy` | n/a | n/a | Pure Go function returning canned text based on prompt-substring matching (`internal/agent/dummy.go:29-103`); never writes files, so it cannot satisfy `validateMarkdownContent` for design/decisions/sprint phases (**inferred** from reading `plan.go`'s file-existence check plus `dummy.go`'s lack of any `os.WriteFile` call — I did not find a test exercising `--agent dummy` through the design phase to confirm the resulting failure mode) |

All agent processes are launched with `exec.CommandContext(ctx, ...)` and a 10-minute timeout for interview/design/decisions/sprint/implement/assess phases (`plan.go:159,218,270,330`; `next.go:183`) and a 5-minute timeout for recovery/replan/retro (`next.go:416,499`; `retro.go:82`).

### 3.2 Completion/failure detection

Purely process-exit-code + text based:
- `cmd.Run()` error (non-zero exit, or context deadline) is the only failure signal (`claude.go:47-54`, `codex.go:47-54`) — there is no parsing of a specific exit code value from the child CLI beyond "err != nil".
- Context-deadline errors are distinguished only for reporting (`ctx.Err()` check, e.g. `claude.go:50-52`), not handled differently downstream.
- Task-level "did this succeed" is then judged by **string matching on the captured stdout**: `isReviewApproved` checks for `"APPROVED"` (`next.go:371-374`); goal-completion checks for `"GOAL_COMPLETE"` (`next.go:827`); interview/sprint/design output is checked by `validateMarkdownContent` for a leading `#` and absence of meta-commentary prefixes like `"I've created "` (`plan.go:391-399,404-406`).

### 3.3 Prompt assembly

No template files or `.tmpl` mechanism — prompts are built by Go `fmt.Sprintf`/`strings.Builder` functions with inline text, one per phase:
- `buildInterviewPrompt` (`plan.go:412-440`)
- `buildDesignPromptWithContext` (`plan.go:502-523`)
- `buildDecisionsPrompt` (`plan.go:599-622`)
- `buildSprintsPromptWithContext` (`plan.go:535-597`)
- `buildSubTaskPrompt` (`next.go:316-364`) — assembles Design Context + Skill Guidelines (loaded from the matching `.ai/skills/<skill>.md` file's body via `getSkillContent`, `next.go:307-314`) + Current Task + task-type-specific instructions
- `buildRecoveryPrompt` (`next.go:437-461`), `buildReplanPrompt` (`next.go:606-641`), `buildNextSprintPrompt` (`next.go:694-746`)

Skill content is loaded from `.ai/skills/*.md` bodies (frontmatter stripped by `ParseSkillMetadata`) and concatenated into the prompt as a `## Skill Guidelines` section (`next.go:180-181,327-331`). The **static top-level `/skills/` directory in the repo (`skills/_planner.md`, `skills/coder.md`) is never read by any Go code** — confirmed by grepping all uses of `"skills"`/`SkillsDir()`, which only ever resolve to `<projectDir>/.ai/skills`. The two files in `/skills/` appear to be a checked-in example/snapshot matching the generated `_planner`/generic `coder` content byte-for-byte, not a live template source.

### 3.4 Skills — builtin set actually generated

`project.BuiltinSkills()` (`internal/project/skills.go:531-791`) returns 7 skills: `_agents`, `_interviewer`, `_planner`, `_reviewer`, `_recover`, `_replanner`, `_retro`. This matches the README's "Built-in skills" table (`_planner`, `_reviewer`, `_recover`, `_replanner`, `_interviewer`, `_retro` — README omits `_agents`). These are rewritten to `.ai/skills/*.md` on **every** agate command via `cmd/root.go:30-44`. Note `_retro`'s skill file is generated even though the code path that would use it (`RunRetrospectiveWithOptions`) is never invoked (§1 takeaway #10).

Language-specific coder skills generated by `GenerateSkills(language, projectType)` (`skills.go:122-150`): `go-coder`, `python-coder`, `rust-coder`, `js-coder` for `go`/`python`/`rust`/`javascript`/`typescript`, and a generic `coder` skill for anything else including the switch's `default` (`skills.go:126-137`). **There is no `c++`/`cpp` case** — for a C++ goal, `detectLanguage` (`internal/project/goal.go:34-57`) may classify the language as `"c++"` via the regex `\b(c\+\+|cpp)\b` (`goal.go:46`), but `GenerateSkills`'s switch has no `"c++"` case, so it falls through to `genericSkills()` (generic `coder` skill, no C++-specific guidance) regardless of what `detectLanguage` returned (`skills.go:122-137`). (The behavior of the `\b...\+\+...\b` regex against text like "C++20" was not runtime-verified here — no Go toolchain was available in this environment — so whether `detectLanguage` even matches "C++" reliably is **inferred**, not confirmed.)

### 3.5 Reviewer gating

- Reviewer is just another agent invocation using the `_reviewer` skill (or a skill name ending in `-reviewer`, checked via `subTask.Skill == "_reviewer" || strings.HasSuffix(subTask.Skill, "-reviewer")`, `next.go:232`).
- Pass/fail = does the reviewer's raw text output contain `"APPROVED"` (case-insensitive check via `strings.ToUpper`, `next.go:371-374`). No structured output format, no JSON, no separate lint/build/test execution triggered by agate.
- On failure: `sprint.AddFailure(task.Index)` adds one ❌ marker to the parent task line, and every checked sub-task in that task from the current one onward is unchecked for retry (`next.go:234-256`).
- Retry ceiling: `maxReviewRetries = 3` (`next.go:18`). At/above that, if not yet replanned, `attemptReplan` runs the `_replanner` skill once against `claude` specifically (hardcoded, `agent.GetAgentByName("claude")`, `next.go:466`), which is expected to rewrite the failing task's sub-tasks and clear failure markers (`next.go:463-548`). If replan itself errors, or if `ReplanCount > 0` already (i.e. a second round of 3 failures after a replan), the workflow raises `HumanNeededError` (`next.go:128-131,136-140`), which surfaces as exit 255.

### 3.6 Recovery agent

On any agent execution error (not just reviewer disapproval), `attemptRecovery` invokes `claude` (hardcoded) with the `_recover` skill to "diagnose and fix the environment," then retries the original sub-task exactly once (`isRecovery=true` guard to avoid infinite recursion, `next.go:208-221,400-434`). If recovery itself errors, or the retried task errors again, the whole `next` call returns a plain error (mapped to exit 2 by `cmd/next.go:89-91`) rather than `HumanNeededError`.

### 3.7 Concurrency

Sequential by default: `executeSubTask`/`ExecutePlanPhase` make one blocking agent call per `agate next` invocation, no goroutines in the execution path itself. A parallel executor exists — `internal/agent/multi.go`'s `MultiAgent.ExecuteAll`/`ExecuteAllWithLogging` use `sync.WaitGroup` + one goroutine per agent (`multi.go:23-42,109-126`) — but grepping `cmd/` and `internal/workflow/` for `MultiAgent`/`ExecuteAll`/`ExecuteFirst` finds **zero call sites**: it is unused dead code. The only goroutine actually exercised in the `auto`/`next` path is `cmd/auto.go:101-107` (a background stdin-scanner for the `suggest` pipe, unrelated to agent execution) and `internal/agent/progress.go:33` (`CountingWriter`'s 1-second ticker for the live "Ns, X.XXk" progress display).

### 3.8 Git usage

None. Repo-wide grep for `exec.Command`/`exec.CommandContext` (`cmd/auto.go:64`, `internal/agent/claude.go:40,66,98,123`, `internal/agent/haiku.go:41,66,97,122`, `internal/agent/codex.go:40,66`) shows only: self-re-exec of the `agate` binary, and invocations of `claude`/`codex`. No literal `"git"` string, no `worktree`, no `branch`, no `commit` anywhere in `.go` source. Agate does not commit per task, does not create branches, and does not use worktrees — whatever git behavior exists in a project is entirely up to what the underlying `claude`/`codex` CLI does on its own (**inferred**: e.g. if the target project is a git repo, the agent (running with full file-write permission) could choose to run git commands itself as part of its own tool use, but agate does not orchestrate or require this).

## 4. Exit-code protocol and `auto` vs `next`

| Code | Constant | Meaning | Confirmed at |
|---|---|---|---|
| 0 | `ExitDone` | All work complete | `internal/workflow/exitcode.go:5` |
| 1 | `ExitMoreWork` | More work remains, automation continues | `exitcode.go:6` |
| 2 | `ExitError` | Error occurred | `exitcode.go:7` |
| 255 | `ExitHumanNeeded` | Human action required | `exitcode.go:8` |

`agate next` (`cmd/next.go:46-102`):
1. Calls `workflow.NextWithOptions` once — this does exactly one unit of work (one planning-phase agent call, or one sub-task execution, or one assessment).
2. On a `HumanNeededError` (via `errors.As`), forces exit 255 (`next.go:73-78`).
3. On any other error, re-derives `GetStatus`+`GetExitCode` from disk; if that says human-needed, exit 255, else exit 2 (`next.go:80-91`).
4. On success, re-derives `GetStatus`+`GetExitCode` from disk for the *final* exit code (`next.go:96-99`) — note this is **not** simply "return 1"; if the single step just completed happens to finish the very last sprint, `next` can return 0 directly.

`agate auto` (`cmd/auto.go:17-50,77-180`):
1. Re-execs itself as a subprocess running `agate next [--agent X]` in a loop (`Run`, `auto.go:98-153`).
2. Interprets the *child process's* exit code: `0` → stop, print "Done!", return 0 (`auto.go:132-134`); `1` → reset error counter, loop again (`auto.go:135-138`); `255` → stop immediately, return 255 (`auto.go:139-142`); anything else → increment `consecutiveErrors`, retry up to `maxConsecutiveErrors = 3` (`auto.go:109,143-151`) before giving up and returning that same non-standard code (confirmed by `TestAutoRunner_StopsOnUnexpectedExitCode`, `cmd/auto_test.go:233-243`, which shows an unrecognized code like 130 is preserved and returned as-is after 3 retries).
3. Also runs a background goroutine draining stdin lines and forwarding each non-empty line to `agate suggest <text>` between steps (`auto.go:99-107,114-115,156-179`) — but as noted in §1/§3, `agate suggest` doesn't persist anything server-side (`internal/workflow/interrupt.go:8-13`), so this plumbing currently has no effect on the next `agate next` call.

`agate status` (`cmd/status.go:33-51`) reuses the exact same `GetExitCode(result)` function as `next`, applied to a freshly computed `StatusResult` — it never runs a step, only reports.

## 5. Relationship to the Attractor spec (DOT-graph pipeline engine)

Based only on what was verified in agate's own code (Attractor itself was not read, per instructions):

- **No DOT/graph parsing exists.** A repo-wide case-insensitive grep for `\bdot\b`, `digraph`, `graphviz`, `pluggable`, `handler.?type` across all `.go` files returns no matches (the only `\bnode\b` hit is the unrelated JS/Node.js language-detection regex at `internal/project/goal.go:42`).
- **No generic "node handler type" abstraction.** The `Agent` interface (`internal/agent/agent.go:12-22`) is a small, fixed interface (`Name`, `Available`, `Execute`), and there are exactly four concrete implementations (`claude`, `haiku`, `codex`, `dummy`) selected by a hardcoded `switch` in `GetAgentByName` (`agent.go:133-146`) — there is no plugin registry, no dynamically loaded handler types, and no way to add a new "node kind" without editing this switch and adding a new struct.
- **The phase sequence is fixed and linear**, not a general graph: `PlanPhase` is a 5-value enum evaluated in a fixed `if`-chain (`state.go:87-114`), and the sprint execution loop is a fixed sub-state-machine (implement → review → [replan] → next sprint) hardcoded in `next.go`. There is no data structure representing an arbitrary DAG/graph of steps with edges, and no code that reads or writes a `.dot` file or any adjacency-list/graph representation.
- **No JSON/YAML state graph.** All persisted state is markdown text with checkboxes/regex parsing (§2), not a serialized graph or state-machine definition file.
- **Conclusion (observed facts only, no recommendation implied):** agate is a fixed 5-phase, single-track lifecycle CLI (interview → design → decisions → sprint-plan → implement/review loop, repeated per sprint) hardcoded in Go control flow, not an implementation or instance of a generic pluggable-node-type DOT pipeline engine. It shares only the high-level "attractor" metaphor (README:1-9) and the general idea of agent-driven convergence loops with what Attractor is described as being.

## 6. Strengths, weaknesses, fragility

**Strengths (observed):**
- Extremely simple resumption model: because state is always re-derived from disk (`state.go:39-84`), there's no separate crash-recovery code path to get wrong — the same `GetStatus`/`ParseSprint` functions used for normal dispatch also handle "resume after being killed" (§2.3).
- Small, explicit exit-code contract (`exitcode.go:5-45`) with dedicated unit tests for every branch (`internal/workflow/exitcode_test.go:1-116`) and for the `auto` loop's exact retry/stop semantics (`cmd/auto_test.go:43-243`).
- Clear separation between "phase decision" (`GetStatus`/`derivePhase`) and "phase execution" (`ExecutePlanPhase`/`executeSubTask`) — the decision function takes no agent/exec dependencies and is trivially testable (confirmed by `internal/workflow/state_test.go` existing as a separate file, and `next_test.go`'s prompt-builder-focused unit tests).

**Weaknesses / fragility (observed unless marked inferred):**
- Log-file overwrite on retry: `Logger.sequence` restarts at 0 every `agate next` invocation (`logger.go:20-26`), so repeated retries of the same phase/task/skill/agent combination silently clobber earlier log files (`logger.go:65-69`) — no run ever gets a globally unique log filename across invocations (§2, `.ai/logs` row).
- Duplicate/inconsistent file-write mechanisms for implementation: agents run in YOLO/full-auto mode (so they can write files themselves) **and** agate separately parses `"### File: path"` fenced blocks out of the same agent's stdout and writes those files too (`parseAndWriteFiles`, `next.go:845-894`, called at `next.go:224-229`). It's unclear from the code alone which mechanism is expected to be authoritative, and if an agent uses both (writes the file directly *and* echoes a `### File:` block), the second write in `parseAndWriteFiles` would silently overwrite the first with possibly stale/duplicated content — this dual-path is confirmed to exist; whether it actually causes conflicts in practice is **inferred**, not tested.
- `agate suggest`/interrupt handling is fully inert (`interrupt.go:8-13`) despite `auto`'s stdin-draining machinery being fully built out to call it (`auto.go:99-179`) and despite the README documenting it as working — this is a real functionality gap between documentation and behavior.
- Several whole subsystems are dead code with no caller: `MultiAgent` parallel execution (`multi.go`), `RunRetrospective`/`RunEvolution` (`retro.go`, no `cmd/retro.go` exists), `internal/agent/executor.go`'s `Executor` type, and `.ai/design/.drafts/` (created, never used). A design that reuses agate's approach should decide deliberately whether to build these or drop them, rather than inherit half-finished scaffolding.
- Reviewer gate is a bare substring match on free-text output (`"APPROVED"`, `next.go:373`) with no structured/parseable protocol and no independent verification (build/test/lint) triggered by agate itself — a reviewer agent that outputs "not APPROVED — needs work" would still match `strings.Contains(output, "APPROVED")` because of the substring "APPROVED" inside "not APPROVED"... (**inferred**: not tested here, but follows directly from `strings.Contains` semantics at `next.go:372-374`; worth independently verifying if this matters for our design, since it looks like a real false-positive risk in the approval check).
- Skill-language coverage gap for C++: `detectLanguage`'s regex includes a `"c++"` pattern (`goal.go:46`) but `GenerateSkills`'s switch has no case for it (`skills.go:126-137`), so any C++ goal falls back to the generic `coder` skill with zero C++-specific guidance — directly relevant since our target project is C++20.
- No atomicity around sprint-file checkbox writes: `checkLineAt`/`uncheckLineAt`/`AddFailure`/`AddReplanMarker` each do one `os.WriteFile` of the whole file (`sprint.go:296,334,405,433`) with no temp-file+rename pattern found — a crash mid-write could in principle corrupt `.ai/sprints/*.md` (**inferred**; no evidence of fsync/atomic-rename either way was found by reading these functions, and no test simulates a truncated write).

## Open questions this material does not answer

- Whether `--agent dummy` actually works end-to-end through the design/decisions/sprint-plan phases, given dummy never calls `os.WriteFile` and those phases require the target file to already exist on disk (`plan.go:379-410` `validateMarkdownContent`) — no test in `internal/workflow` exercises this combination.
- Whether the dual file-write path (agent writing directly in YOLO mode vs. agate's `parseAndWriteFiles` text-block parser) ever actually conflicts in a live run, or whether in practice the coder skill prompt (`next.go:339-349`) reliably steers agents toward only the `### File:` text convention (which would make the YOLO permission moot for that phase specifically).
- Whether `detectLanguage`'s `\b(c\+\+|cpp)\b` regex reliably matches strings like "C++20" or "Build ... in C++." given the non-word `+` characters around the word-boundary anchors — could not be checked at runtime (no Go toolchain available in this environment).
- What exactly the real `claude`/`codex` CLIs do with `--dangerously-skip-permissions --print -p <prompt>` / `--full-auto-net exec <prompt>` in terms of tool access scope, working-directory confinement, and network access — that's a property of those external CLIs, not of agate's own source, and wasn't investigated here.
- Whether the `.ai/skills` user-override merge (`skills.go:188-231`) is actually idempotent across multiple `agate` invocations, given built-in skills are fully rewritten from Go source every command (`cmd/root.go:30-44`) while the merge only happens at `LoadSkills` read-time in memory, not by rewriting `_foo.md` on disk with the merge baked in.
- Whether there is a race condition between the `cmd/root.go` `PersistentPreRun` skill regeneration and a concurrently running second `agate` invocation on the same project directory (agate's model assumes single-writer, single-process execution; multi-invocation concurrency safety was not examined).
