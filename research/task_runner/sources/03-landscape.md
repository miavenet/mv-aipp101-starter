# Landscape research: Attractor, comparable task runners, and reliability practice

Research method: WebSearch + WebFetch only. Every claim below is tied to a URL that was
actually fetched (or, where marked "search snippet only", a URL that appeared in search
results but was not independently fetched — flagged explicitly). WebFetch returns a small
model's paraphrase of a page, not raw text, so quoted strings below are treated as
paraphrase unless stated otherwise.

## Key takeaways for building our runner

- StrongDM's own public material makes qualitative, not quantitative, reliability claims — no
  published success-rate/throughput numbers were found on strongdm.com; the concrete numbers
  that exist (e.g. "$1,000/day per engineer" in token cost, 3-person team, July→Oct 2025 timeline)
  come from Simon Willison's independent write-up, not StrongDM's own blog post. https://www.strongdm.com/blog/the-strongdm-software-factory-building-software-with-ai , https://simonwillison.net/2026/Feb/7/software-factory/
- StrongDM's Attractor is published only as an NLSpec (natural-language spec meant to be handed
  to a coding agent to *generate* an implementation) — strongdm/attractor itself is not a runnable
  engine, it's three spec documents (pipeline engine, coding-agent-loop, unified-LLM-client). https://github.com/strongdm/attractor
- Several independent third parties have already built runnable implementations of the Attractor
  NLSpec in Go, Python, and C11, all low-star/early-stage (1–27 stars), suggesting the spec is
  "implementable" but has no dominant/canonical open-source engine yet. https://github.com/allouis/attractor , https://github.com/samueljklee/attractor , https://github.com/jmccarthy/attractor-c
- StrongDM ships its own benchmark (AttractorBench) for spec-conformance, but as of the fetch date
  the authors explicitly say current scores are not yet valid for ranking (still in "burn-in"). https://github.com/strongdm/attractorbench
- The "Ralph Wiggum" loop's core mechanism — one task per iteration, fresh context every loop,
  shared state kept in a plan file + git history rather than in the LLM's context — is the closest
  publicly-documented analogue to "deterministic progress via files/git rather than conversation
  memory," and Anthropic has since folded a version of it into Claude Code itself (`/goal`, `/loop`, `/batch`). https://github.com/ghuntley/how-to-ralph-wiggum , https://awesomeclaude.ai/ralph-wiggum
- Every durable-execution engine surveyed (Temporal, DBOS, Inngest, LangGraph) converges on the
  same shape: a deterministic orchestration layer + non-deterministic "step/activity" units, with
  step outputs checkpointed to a durable store so a crash resumes from the last completed step
  rather than replaying LLM calls. This is a reusable pattern for our runner's resumption story. https://temporal.io/blog/of-course-you-can-build-dynamic-ai-agents-with-temporal , https://docs.dbos.dev/architecture , https://www.inngest.com/blog/ai-agents-inngest-durable-steps , https://docs.langchain.com/oss/python/langgraph/persistence
- Beads (Steve Yegge) is the most directly relevant "task graph as durable state" precedent: it
  stores tasks as a dependency graph in a git-backed SQL database (Dolt), gives every task a
  collision-proof hash ID, and exposes `bd ready` to compute the actually-workable frontier —
  a candidate model for how our runner could store/derive the work queue. https://github.com/gastownhall/beads
  (background/origin story only, not independently verified against the repo: "50 First Dates" framing) https://steve-yegge.medium.com (search snippet only — Medium fetch returned 403)
- Practitioner consensus (independent of any single vendor) on reliability: use fresh/forked
  context for reviewer stages specifically so review isn't biased by the implementer's own
  reasoning trace, and treat "boring engineering controls" (git worktrees, structured pass/fail
  verdicts that fail closed) as more load-bearing than model capability. https://dev.to/mixture-of-experts/build-reliable-long-running-agents-w-verification-worktrees-skills-subagents-hilreview-gates-4m1c
- Stuck-loop/cost-runaway detection in practice reduces to: budget checks enforced *before* the
  next model call (not after), no-progress detection over N steps, and action-deduplication by
  hashing repeated tool-call/argument pairs — real incidents cited include an 11-day agent-to-agent
  ping-pong costing $47,000 and a single-task AWS bill of $6,531.30. https://futureagi.com/blog/loop-engineering/ai-agent-loop-cost-control/
- The "Dark Factory" pattern (a named generalization of StrongDM's approach, written up independently)
  is the one source found that lists concrete failure-mode mitigations for autonomous pipelines:
  triple-run scenario voting with a 2/3 pass threshold, a 90% overall pass gate, manual audit of the
  first 50 auto-merged PRs, a hard 3-retry cap per spec with token monitoring, and physically
  isolating held-out test scenarios from the coding agent's filesystem access. https://hackernoon.com/the-dark-factory-pattern-moving-from-ai-assisted-to-fully-autonomous-coding

## 1. StrongDM's own public writing on Attractor / Software Factory / NLSpecs

**Primary StrongDM blog post**: "The StrongDM Software Factory: Building Software with AI"
(https://www.strongdm.com/blog/the-strongdm-software-factory-building-software-with-ai).
Fetched directly. Content, as paraphrased by WebFetch:
- Frames the Factory as: humans define intent, scenarios, and constraints; agents generate code,
  validate it against a "Digital Twin Universe" (behavioral clones of systems like Okta and Slack),
  and iterate until convergence, "without hand-tuning or human review."
- Validation is done via "satisfaction testing": LLMs judge whether observed agent trajectories
  through scenarios satisfy user expectations, described as analogous to an ML holdout set.
- **No quantitative success rates, throughput numbers, or reliability metrics are disclosed in
  this post.** No discussion of failure modes was found in the fetched content either — this
  should be treated as a real gap in StrongDM's own public disclosure, not an omission of our
  research.

**Independent, well-sourced account**: Simon Willison, "How StrongDM's AI team build serious
software without even looking at the code" (https://simonwillison.net/2026/Feb/7/software-factory/,
mirrored at https://simonw.substack.com/p/how-strongdms-ai-team-build-serious). Fetched directly.
- StrongDM's stated principles per Willison: "Code must not be written by humans" and "Code must
  not be reviewed by humans."
- Concrete numbers he reports: ~$1,000/day per engineer in token costs (~$20,000/month); a 3-person
  team started the effort in July 2025 and had a working system by October 2025; they released
  "cxdb" as an artifact, sized at roughly 16,000 lines of Rust, 9,500 of Go, 6,700 of TypeScript.
  (These are Willison's numbers about StrongDM's internal effort, not numbers published by StrongDM
  itself in the blog post fetched above — flagged as secondary-source.)
- The Digital Twin Universe lets them run "thousands of scenarios per hour" without hitting real
  API rate limits, and lets them safely exercise dangerous failure modes.
- Willison's own skepticism, quoted/paraphrased: he questions whether $1,000/day per engineer is
  sustainable ("If these patterns really do add $20,000/month per engineer to your budget they're
  far less interesting"), and says the central open technical question is whether agents can prove
  code works without any human review step.

**Related secondary coverage found via search but not fetched** (listed for completeness, not
used as sourced facts): dev.to "The Agentic Software Factory..." (uenyioha), Augment Code's
"What Is a Software Factory?" guide, a Stanford Law CodeX piece "Built by Agents, Tested by
Agents, Trusted by Whom?", Ry Walker's research note, quantumfaxmachine.com and bitsofchris.com
commentary pieces. These were not fetched — do not treat any specifics from them as verified here.

**"Dark Factory" as a named generalization**: HackerNoon, "The Dark Factory Pattern: Moving From
AI-Assisted to Fully Autonomous Coding" (https://hackernoon.com/the-dark-factory-pattern-moving-from-ai-assisted-to-fully-autonomous-coding).
Fetched directly. This is an independent author's generalization of StrongDM's approach (crediting
Dan Shapiro and Simon Willison for the "Dark Factory" framing), not StrongDM's own writing, but it
is the most concrete source found on **failure-mode mitigation** for this style of pipeline:
- Cites StrongDM's factory as proof of concept: "three engineers, zero human-written code, zero
  human-reviewed code, holdout scenarios and digital twins handling QA," claiming "3–10x sustained
  velocity" on real products over months.
- Names six failure categories and mitigations: (1) evaluator approving defective code → mitigated
  with triple-run scenario voting (2-of-3 pass threshold), a 90% overall pass gate, and manual audit
  of the first 50 auto-merged PRs; (2) team/cultural resistance → phased rollout; (3) agent/vendor
  inadequacy → abstracted behind a swappable orchestrator; (4) cost escalation → hard cap of 3 retry
  attempts per spec plus token monitoring; (5) test staleness → scenarios kept as plain English with
  no glue code, plus a weekly "maintenance agent" that scans for drift; (6) agents gaming the
  evaluator → holdout scenarios are filesystem-isolated from the coding agent (can't see what it's
  graded against).

## 2. Other public implementations of the Attractor spec

`strongdm/attractor` itself (https://github.com/strongdm/attractor, fetched) is **not an engine** —
it is three NLSpec documents (`attractor-spec.md` = pipeline engine, `coding-agent-loop-spec.md`,
`unified-llm-spec.md`) plus instructions telling readers to hand the spec to a coding agent (Claude
Code, Codex, OpenCode, Amp, Cursor, etc.) to have it generate a working implementation. At fetch
time it showed roughly 1.3k stars / 196 forks / 15 commits on main, but the repo content itself is
specs, not code, so star count reflects interest in the spec/idea, not a shipped product.

The node-handler vocabulary defined in `attractor-spec.md` (fetched directly,
https://github.com/strongdm/attractor/blob/main/attractor-spec.md): `start` and `exit` (no-op
entry/termination markers, one each required per graph), `codergen` (the default LLM-task handler;
takes a `prompt` attribute, expands `$goal` variables, calls a backend LLM, supports
`max_retries`/`timeout`/`llm_model`), `wait_human` (human-in-the-loop gate, shape=hexagon, derives
multiple-choice options from outgoing edge labels and routes on the human's selection),
`conditional` (shape=diamond, routes on boolean expressions over outgoing edges, does no work
itself), `parallel` (shape=component, clones context per branch, concurrent execution up to a
configurable limit, join policies like `wait_all`/`first_success`), `fan-in` (shape=tripleoctagon,
consolidates parallel results, optionally via LLM-based ranking), `tool` (shape=parallelogram,
executes an external command via a `tool_command` attribute), and `manager_loop` (shape=house,
supervises child pipelines via observe/steer/wait cycles, configured with `stack.child_dotfile` /
`manager.*` attributes). Checkpoints are saved after each node for crash recovery; all handlers
share signature `(node, context, graph, logs_root)` and return an Outcome with status/context
updates/routing hints.

### Verified third-party implementations

| Repo | URL | Language | Stars/forks (at fetch) | Notes |
|---|---|---|---|---|
| allouis/attractor | https://github.com/allouis/attractor | Go | 1 star / 0 forks, 807 commits | README states it's a Go implementation of strongdm/attractor; claims to keep the upstream spec "pristine" and document deviations separately. |
| samueljklee/attractor | https://github.com/samueljklee/attractor | Python 3.12+ | 27 stars / 4 forks, 146 commits | Claims 100% coverage of all three spec layers (LLM client, coding-agent loop, pipeline engine); REST API with SSE streaming; 432 unit + 8 e2e tests; built via multi-model AI peer review (Claude/GPT-4/Gemini). Most feature-complete of those checked, but still low-adoption. |
| jmccarthy/attractor-c | https://github.com/jmccarthy/attractor-c | C11 | 11 stars / 4 forks, 1 commit shown | Implements all three specs; lists the same handler set (`codergen`, `tool`, `wait.human`, `parallel`, `fan-in`, `conditional`, `manager_loop`); includes example pipelines for branching/parallel/model-stylesheets. |
| jleechanorg/dark-factory | https://github.com/jleechanorg/dark-factory | Python 3.13 | 8 stars / 2 forks, 908 commits, 110 open issues | Explicitly cites StrongDM's AttractorBench as inspiration; frames itself as adopting the broader "Dark Factory" philosophy (humans never read/write code, only specify intent); holdout tests live in a sibling repo `dark-factory-holdouts` with OS-level sandboxing (`sandbox-exec`) denying the implementing agent read access to holdouts. |

Additional candidates surfaced by search but **not independently fetched/verified** (listed only
so they aren't lost, not to be treated as confirmed): `jhugman/nlspec` (exemplar copy of the
attractor spec, not necessarily an implementation), `jhugman/attractor-pi-dev` (implementation
using "pi.dev"), `brynary/attractor`, `Industrial/streamweave-attractor`,
`toohamster/ai-skills-attractor` (appears to be a fork/mirror of strongdm/attractor by name).
`martinemde/attractor` (Go package on pkg.go.dev) also appeared in search but was not fetched.

**StrongDM's own benchmark**: `strongdm/attractorbench` (https://github.com/strongdm/attractorbench,
fetched). It is a spec-conformance benchmark, not a general coding benchmark: agents are given a
~2,000-line system spec and must build a conformant implementation from scratch, in a language of
their choosing, scored on `make build` (5%), self-tests (5%), and three tiered conformance levels
(30% each), against a mock LLM server that returns canned responses for determinism. As of the
fetched page, the authors explicitly state current scores/leaderboard are **not yet valid for
ranking** pending more "burn-in" runs.

**Conclusion for this section**: implementations beyond the original spec do exist (at least 4
independently written, cross-language), but none has significant adoption (all under 30 stars),
and StrongDM's own conformance benchmark for these is explicitly marked not-yet-trustworthy.

## 3. Comparable approaches to running coding agents deterministically to completion

| Name | Unit of work | State location | Resumption | Completion verification | Human-in-loop | Source URL |
|---|---|---|---|---|---|---|
| Ralph Wiggum technique (Geoffrey Huntley) | One task selected from `IMPLEMENTATION_PLAN.md` per loop iteration | Files on disk: `IMPLEMENTATION_PLAN.md` (shared state across otherwise-isolated loop runs), `specs/*.md`, `AGENTS.md`, plus git history | Loop just restarts (`while :; do cat PROMPT.md \| claude; done`) with fresh LLM context each time, reading the updated plan file — no session/context resumption, only file/git state carries over | Tests/build must pass before commit ("backpressure"); agent exits after a successful commit; plan is "done" when all tasks are marked done | Humans work "outside the loop": write initial specs/JTBDs, periodically verify plan direction, watch for failure patterns and adjust prompts, regenerate the plan if it drifts | https://github.com/ghuntley/how-to-ralph-wiggum |
| Claude Code's own `/goal`, `/loop`, `/batch` (Ralph folded into product) | `/goal`: repeated turns until an evaluator model verifies a condition; `/batch`: one worktree-agent per mechanical change, 5–30 in parallel | Not detailed beyond "worktree agents"; conversation/turns for `/goal` and `/loop` | `/goal` uses automatic re-verification each turn; `/loop` is manual (user presses Escape to stop); a separate `/ralph-loop` plugin supports `--completion-promise` exact-string-match and `--max-iterations` as a hard safety cap | `/goal`: evaluator model checks a stated condition (e.g. "all tests in test/auth pass and lint is clean"); `/loop`: none automatic, relies on the user | User writes the completion criteria and can interrupt; docs caution this is "anecdotal, not independently benchmarked" and unsuitable for tasks needing human judgment/design decisions | https://awesomeclaude.ai/ralph-wiggum |
| claude-task-master / Taskmaster (eyaltoledano) | A task (with optional subtasks) parsed out of a PRD | `.taskmaster/` directory on disk (e.g. `.taskmaster/docs/prd.txt`), tasks organized into "tags" like in-progress/done/backlog | Not clearly documented; appears to be re-invocation against the same `.taskmaster/` state rather than a session-resume mechanism | Status-based tracking (`set_task_status`) plus explicit `--with-dependencies`/`--ignore-dependencies` flags; no automatic test-based verification documented | Humans interact via natural-language requests in chat interfaces ("implement task 3"); distributed as a Claude Code plugin with 3 roles: task-orchestrator, task-executor, task-checker, plus an MCP server | https://github.com/eyaltoledano/claude-task-master |
| Beads (bd), Steve Yegge | A "bead" — an issue-like unit with a hash ID (e.g. `bd-a1b2`), organized epic→task→sub-task | Dolt (git-like SQL database), embedded in-process by default or run as a server for concurrent writers; synced across machines via `bd dolt push/pull` against git remotes | Not session-resumption in the LLM sense — persistence is at the task-graph level; `bd prime` re-injects persistent memories/workflow context into a fresh agent session; old closed tasks undergo "semantic memory decay" compaction to reclaim tokens | `bd close <id>` marks completion and releases blocked dependents; `bd ready` computes the frontier of tasks with no open blockers | Humans use the same CLI; agents claim work atomically (`bd update --claim`) to avoid multi-agent collisions | https://github.com/gastownhall/beads |
| Claude Code headless / Agent SDK orchestration | One `query()` call / one `-p` invocation, or one agent role in a multi-agent chain | Not a first-class runner concept in the docs found; state is whatever the invoking script persists (e.g. logs, git) | Not addressed by the sources fetched here (search-only coverage; no official Anthropic doc on cross-invocation resumption was fetched) | Exit code / stream output parsing by the wrapping script; no built-in verification primitive found | None built-in — headless mode is designed to run without human input; humans are outside the loop entirely at the shell-script level | search snippets only (dev.to, jsmanifest.com, mindstudio.ai, amux.io) — not independently fetched, treat as lower-confidence |
| OpenHands headless mode | One task per invocation, given via `--task` or `--file` | Not documented in the fetched page for cross-invocation persistence | Not covered in the fetched docs | With `--json`, success/failure must be inferred by parsing the structured event stream — no explicit "done" primitive documented | None — headless mode always runs in "always-approve" mode; `--llm-approve` is unavailable, i.e. it is designed specifically to remove confirmation prompts | https://docs.openhands.dev/openhands/usage/cli/headless |
| SWE-agent batch mode | One GitHub issue / one SWE-bench instance per run | Patches/predictions written to a `preds.json` file; `sweagent merge-preds` repairs partial output from interrupted runs | Interrupted batch runs are repaired via `merge-preds` rather than a live resume; `--num_workers` parallelizes across instances, `--random_delay_multiplier` staggers container startup | Optional `--evaluate=True` submits to `sb-cli` for SWE-bench scoring (test-based); no verification documented outside the benchmark context | None documented in the fetched batch-mode page | https://swe-agent.com/latest/usage/batch_mode/ |
| GitHub Spec Kit — Tasks phase | A task in `tasks.md`, sized to "hours, not days," following INVEST criteria, with an explicit `[P]` marker for parallel-safe tasks | `tasks.md` in the feature's spec directory, alongside spec.md/plan.md from earlier phases | Not a runtime-resumption concept — `/speckit.tasks` regenerates the task breakdown from spec+plan; `/speckit.implement` executes the list | Each task carries explicit, testable acceptance criteria; `/speckit.analyze` validates cross-artifact consistency before implementation begins | Humans review/refine the generated task list, split oversized tasks, fill in missing acceptance criteria, and set priorities before `/speckit.implement` runs | https://roelantd.github.io/spec-kit-workshop/05-tasks-phase |
| Sourcegraph Amp — subagents | Search-result paraphrase: "a mini-Amp" spawned to handle one sub-task, with its own isolated context/shell/file-edit tools | Each subagent's context window is isolated from the parent's; parent can reference other threads via `@thread-id` | Not fetched/verified directly (Medium and ampcode.com fetches both failed with 403); treat as **search-snippet-only**, lower confidence | Not established from a fetched source | Not established from a fetched source | search snippet only: https://medium.com/@matthewtanner91/how-to-use-subagents-in-ai-coding-with-amp-8b8418486782 (fetch returned 403) |
| Temporal | An "Activity" (one non-deterministic call: LLM, tool, API) inside a deterministic "Workflow" that sequences them | Temporal's Event History — a durable, replayable log of past decisions/results | On failure/restart, the workflow **replays** recorded Event History instead of re-executing or re-asking the LLM for a new plan, so it reaches the same state deterministically, then continues from where it left off | Not a built-in primitive; would be modeled as a workflow step/condition | Not detailed in the fetched post beyond noting workflows can incorporate human signals as activity results/state inputs | https://temporal.io/blog/of-course-you-can-build-dynamic-ai-agents-with-temporal |
| LangGraph checkpoints | A graph "node" transition within a "thread" (thread_id-scoped conversation/task) | Checkpointer-backed store (e.g. Postgres/SQLite/memory backends), one checkpoint per node transition per thread | Re-invoke the graph with the same `thread_id`; the framework reconstructs state from the latest checkpoint — exact resumption API not detailed in the fetched page | Not a built-in primitive — would be application-defined graph logic | Explicitly listed as a first-class use case ("human-in-the-loop workflows," "time travel") but the interrupt/resume APIs themselves were not detailed in the fetched page | https://docs.langchain.com/oss/python/langgraph/persistence |
| Inngest | A `step.run()` call — one LLM call, one tool execution, or one data operation; sub-agent delegation via `step.invoke()` | External session storage for conversation history/context, plus Inngest's own memoized step-output cache | Step-level memoization: on restart, already-completed steps return cached results instantly instead of re-executing (no re-paying for LLM calls or re-running side-effecting tools); `singleton` config with a session key prevents concurrent duplicate runs | Not a built-in primitive in the fetched material; implied to be modeled as another step | Referenced via a linked "human-in-the-loop pattern" (event-based wait/approval) but not detailed in the fetched page | https://www.inngest.com/blog/ai-agents-inngest-durable-steps |
| DBOS | A "step" inside a "workflow"; the agent's decision cycle maps to the workflow, each tool call to a step | Postgres ("system database"); one write per step, plus two per workflow (input at start, outcome at completion) | On restart, DBOS finds workflows marked PENDING, replays with original inputs, and for each step checks Postgres for an existing checkpointed output — if present, returns it without re-executing; execution resumes live once it reaches the first step without a checkpoint | Requires deterministic workflow code (same inputs → same step sequence) and idempotent steps — a correctness precondition rather than a "done" check per se | Not addressed in the fetched architecture page | https://docs.dbos.dev/architecture |

## 4. What practitioners report makes such runners reliable or unreliable

- **Executable verification gates, structured verdicts**: reviewer/verification stages should
  return structured pass/fail verdicts that "fail closed" if malformed, rather than trusting the
  implementing agent's own claim of success. https://dev.to/mixture-of-experts/build-reliable-long-running-agents-w-verification-worktrees-skills-subagents-hilreview-gates-4m1c
- **Fresh context per task / per review**: the same source distinguishes "forked context" (fine
  for implementation stages where continuity helps) from "fresh context" (necessary for reviewer
  stages specifically, so the reviewer isn't anchored to the implementer's own reasoning trace —
  described as avoiding "reviewer bias when reviewers inherit implementation reasoning"). It also
  names "token exhaustion from compounding context inheritance across stages" as a concrete failure
  mode when this discipline isn't followed. https://dev.to/mixture-of-experts/build-reliable-long-running-agents-w-verification-worktrees-skills-subagents-hilreview-gates-4m1c
- **Git worktrees** are named as one of several "boring software engineering controls" that make
  agent work "survivable" (isolating concurrent agents' filesystem changes from each other). Same source.
- **Small task granularity / commit-per-task**: the Ralph Wiggum technique's core discipline is
  "tight tasks + 1 task per loop" to maximize useful context utilization (framed as targeting
  ~40–60% context utilization), with tests-must-pass-before-commit as "backpressure" forcing fixes
  before a task is considered closed. https://github.com/ghuntley/how-to-ralph-wiggum
- **Idempotent tasks / retryable steps**: durable-execution engines require steps to be safe to
  retry and workflows to be deterministic (same inputs → same step sequence) as a precondition for
  correct crash recovery — this is stated explicitly for DBOS. https://docs.dbos.dev/architecture
- **Stuck detection / infinite-loop avoidance**: concrete detection techniques reported —
  max-iteration hard limits, "action deduplication" (hash each tool-call+argument pair, break the
  loop if the same call repeats k times), and "progress detection" (flag stuck if state hasn't
  changed in k steps); budget/cost caps must be checked **before** the next model call, not after,
  because "if you check after, you have already spent the tokens you were trying to save," and
  the cap "cannot live in the prompt" — it must be enforced in code or at a gateway. Concrete
  incidents cited: two agents ping-ponging for 11 days generating a $47,000 bill; a single
  autonomous agent task producing a $6,531.30 AWS bill. https://futureagi.com/blog/loop-engineering/ai-agent-loop-cost-control/
- **Cost/time budgets, more mechanisms**: recommended levers beyond hard caps include prompt
  caching (discounted reuse of stable context), context compaction (summarizing old history
  instead of resending it verbatim), and routing simple steps to cheaper models; tracking "cost per
  successful task" (not just per-token price) as the metric that reveals a loop drifting toward
  runaway. Same source.
- **Cost caps as part of a whole pipeline, not just per-call**: the independent "Dark Factory"
  write-up adds a pipeline-level version of this same idea — a hard 3-retry-attempts-per-spec cap
  combined with token monitoring, layered on top of a 90% overall scenario pass-gate and 2-of-3
  majority voting across repeated evaluation runs to guard against a single bad evaluator judgment. https://hackernoon.com/the-dark-factory-pattern-moving-from-ai-assisted-to-fully-autonomous-coding

## Open questions this material does not answer

- No source found gives a quantitative success/failure rate for StrongDM's Attractor/Software
  Factory pipeline in production (throughput, defect rate, rework rate) — the blog post is
  qualitative only, and AttractorBench's own leaderboard is explicitly marked not-yet-valid.
- No fetched source explains exactly how the `wait_human` / human-gate node in the Attractor spec
  is expected to be surfaced to a real human in an unattended/CI run (Interviewer "frontends" are
  named — CLI, web, callback, queue — but not how a runner decides when to escalate rather than retry).
- None of the durable-execution engines surveyed (Temporal, DBOS, Inngest, LangGraph) were checked
  against an actual open-source example of driving *Claude Code specifically* (as opposed to a
  generic LLM call) as the "activity"/"step" — this mapping is unverified.
- No fetched source describes how any of these systems distinguish "genuinely stuck, needs a
  human" from "slow but making progress" other than simple no-progress-in-k-steps heuristics;
  none discuss semantic/goal-aware stuck detection.
- Amp's subagent/orchestration mechanics could not be verified from a primary source in this pass
  (both ampcode.com and the Medium write-up returned 403 to WebFetch); this section of the
  landscape is weaker than the others and should be re-fetched via a different method (e.g. `gh`/curl
  or a cached copy) before being relied on.
- Beads' own best-practices guidance from Steve Yegge (task granularity, stuck-loop avoidance
  specific to Beads) could not be fetched (Medium blocked WebFetch with 403); only the GitHub
  README was verified.
- No cost/pricing comparison was found between running one of these runners against Claude Code
  specifically (as this project intends) versus the generic-LLM-call framing most of these sources use.
- No source discusses multi-repo or multi-service work items (all task-runner examples assume a
  single repository/codebase).
