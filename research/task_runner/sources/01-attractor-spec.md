## Key takeaways for building our runner

- Attractor explicitly does not require you to own the LLM/agent layer: "Although bringing your own agentic loop and unified LLM SDK is not required to build your own Attractor, we highly recommend controlling the stack" (README.md:5) and the spec says the codergen handler's backend can be "spawn CLI agents (Claude Code, Codex, Gemini CLI) in subprocesses... or anything else. The pipeline definition (the DOT file) does not change regardless of backend choice" (attractor-spec.md:58). This directly supports driving Claude Code non-interactively as the `CodergenBackend`.
- The entire orchestration contract a runner must implement is small: parse a DOT subset (Section 2), run a single-threaded traversal loop with a 5-step edge-selection algorithm (Section 3.3, attractor-spec.md:406-459), and dispatch to pluggable node handlers via a shape/type registry (Section 4.1-4.2, attractor-spec.md:583-630).
- The `CodergenBackend` interface is one function: `run(node, prompt, context) -> String | Outcome` (attractor-spec.md:711-718). Everything about *how* the LLM/agent runs is opaque to the engine — this is the seam where a "Claude Code as subprocess" backend plugs in.
- Status/Outcome is the whole state contract between a node's execution and the engine: `status`, `preferred_label`, `suggested_next_ids`, `context_updates`, `notes`, `failure_reason` (Section 5.2, attractor-spec.md:1076-1094), written to disk as `status.json` per Appendix C (attractor-spec.md:2053-2079). A runner driving Claude Code non-interactively needs Claude Code to (or a wrapper to) emit this exact shape after each milestone step.
- Checkpointing is coarse-grained and node-boundary only: one JSON checkpoint written after each node completes, containing `current_node`, `completed_nodes`, `node_retries`, `context_values`, `logs` (Section 5.3, attractor-spec.md:1096-1125). There is no mid-node (mid-Claude-Code-turn) checkpointing in the spec.
- Two full companion specs (coding-agent-loop-spec.md, unified-llm-spec.md) describe how to build your own coding agent and LLM client from scratch — but per Section 1.4 of attractor-spec.md, none of that is required if the `CodergenBackend` instead shells out to an existing CLI agent (see Section 6 of this document for the delegation analysis).
- The condition language for edge routing is deliberately minimal — only `=`/`!=` and `&&`, no OR/NOT/regex/numeric comparisons (Section 10, attractor-spec.md:1661-1780) — which bounds how much routing logic a 12-step milestone DOT graph can encode declaratively.
- Human-in-the-loop is abstracted behind one `Interviewer` interface with five built-in implementations, including `AutoApproveInterviewer` and `QueueInterviewer` for unattended/CI runs (Section 6, attractor-spec.md:1240-1357) — relevant if any milestone step needs a gate but the runner must stay non-interactive.
- The spec's own Definition of Done is Section 11 (not what the prompt guessed at Section 11 for a different reason — it's confirmed correct), with a Cross-Feature Parity Matrix (11.12, attractor-spec.md:1896-1923) and an Integration Smoke Test (11.13, attractor-spec.md:1925-1980) that double as acceptance tests for any from-scratch implementation.
- Shape-to-handler mapping (Appendix B, attractor-spec.md:2037-2050) is the visual vocabulary of the DOT graphs (box=LLM task, hexagon=human gate, diamond=conditional, component/tripleoctagon=parallel/fan-in, parallelogram=tool, house=manager loop) — useful vocabulary for sketching the 12-step milestone plan as a graph.

---

## 1. The model: DOT graphs, shapes, edges, conditions, attributes

### 1.1 Pipelines as DOT graphs

Attractor pipelines are `digraph` files in a restricted Graphviz DOT subset (attractor-spec.md:64-109, Section 2.1-2.2). Key constraints (Section 2.3, attractor-spec.md:111-118):
- Exactly one `digraph` per file; `strict` and undirected graphs rejected.
- Node IDs must be bare identifiers (`[A-Za-z_][A-Za-z0-9_]*`); human labels go in `label`.
- Directed edges only (`->`); `--` rejected.
- `//` and `/* */` comments stripped before parsing.
- Statement-terminating semicolons optional.

Value types (Section 2.4, attractor-spec.md:120-129): String, Integer, Float, Boolean, Duration (`900s`, `15m`, `2h`, `250ms`, `1d`).

Chained edges (`A -> B -> C [label=...]`) are sugar that expands into pairwise edges sharing the same attributes (Section 2.9, attractor-spec.md:195-210). Subgraphs serve two purposes: scoping node-default blocks, and deriving CSS-like classes from the subgraph `label` for the model stylesheet (Section 2.10, attractor-spec.md:212-230).

### 1.2 Node shapes -> handler types (Appendix B, confirmed heading "Appendix B: Shape-to-Handler-Type Mapping", attractor-spec.md:2037)

Also stated identically in Section 2.8 (attractor-spec.md:179-193):

| Shape | Handler type | Behavior |
|---|---|---|
| `Mdiamond` | `start` | No-op entry point. Exactly one required. |
| `Msquare` | `exit` | No-op exit point; goal-gate check happens in the engine, not the handler. Exactly one required. |
| `box` | `codergen` | LLM task; default handler for nodes without explicit shape. |
| `hexagon` | `wait.human` | Blocks until a human selects an option. |
| `diamond` | `conditional` | Pass-through; engine's edge-selection evaluates conditions. |
| `component` | `parallel` | Concurrent fan-out. |
| `tripleoctagon` | `parallel.fan_in` | Waits for all branches, consolidates results. |
| `parallelogram` | `tool` | External shell/API tool execution. |
| `house` | `stack.manager_loop` | Supervisor loop over a child pipeline (observe/steer/wait). |

Resolution order for which handler runs a node (Section 4.2, attractor-spec.md:601-630): (1) explicit `type` attribute on the node, (2) shape-based lookup in this table, (3) fallback to the default (codergen) handler.

### 1.3 Edges, conditions, weights

Edge attributes (Section 2.7, attractor-spec.md:168-177 and Appendix A, attractor-spec.md:2024-2033): `label`, `condition`, `weight` (Integer, default 0, higher wins ties), `fidelity` (context-carryover override), `thread_id` (session-reuse override), `loop_restart` (Boolean — restarts the whole run with a fresh log directory).

### 1.4 Condition expression language (Section 10, attractor-spec.md:1661-1779)

Grammar (attractor-spec.md:1667-1679):
```
ConditionExpr  ::= Clause ( '&&' Clause )*
Clause         ::= Key Operator Literal
Key            ::= 'outcome' | 'preferred_label' | 'context.' Path
Operator       ::= '=' | '!='
```
Only `=`/`!=` with AND-conjunction (`&&`) is supported today; no OR, NOT, `contains`, `matches`, or numeric comparisons — these are explicitly listed as "Extended Operators (Future)" that implementations should not add without updating the grammar (Section 10.7, attractor-spec.md:1769-1779). Missing `context.*` keys resolve to empty string, never equal to a non-empty literal (Section 10.3, attractor-spec.md:1686). String comparison is exact and case-sensitive.

### 1.5 Attributes (Appendix A, confirmed heading "Appendix A: Complete Attribute Reference", attractor-spec.md:1984)

Graph attributes (attractor-spec.md:1986-2000): `goal` (exposed as `$goal` in prompts and mirrored to `graph.goal` context key), `label`, `model_stylesheet`, `default_max_retries` (legacy alias `default_max_retry`), `default_fidelity`, `retry_target`, `fallback_retry_target`, `stack.child_dotfile`, `stack.child_workdir`, `tool_hooks.pre`, `tool_hooks.post`.

Node attributes (attractor-spec.md:2002-2022): `label`, `shape`, `type` (explicit override), `prompt` (supports `$goal` expansion, falls back to `label`), `max_retries`, `goal_gate` (Boolean — must reach SUCCESS/PARTIAL_SUCCESS before pipeline may exit), `retry_target`, `fallback_retry_target`, `fidelity`, `thread_id`, `class`, `timeout` (Duration), `llm_model`, `llm_provider`, `reasoning_effort` (default `"high"`), `auto_status` (engine synthesizes SUCCESS if handler wrote no status), `allow_partial`.

Note: the external DOT attribute name is `type`, but the spec explicitly allows implementations to use an internal field name like `node_type` to dodge reserved-word collisions in host languages, as long as the DOT-facing behavior is unchanged (attractor-spec.md:166).

---

## 2. The execution engine (Section 3, attractor-spec.md:318-578)

### 2.1 Run lifecycle (Section 3.1, attractor-spec.md:320-333)

Six phases: `PARSE -> TRANSFORM -> VALIDATE -> INITIALIZE -> EXECUTE -> FINALIZE`. Transforms (stylesheet application, `$goal` expansion, custom AST transforms) run between parse and validate; validation rejects invalid graphs and warns on suspicious ones; initialize creates the run directory, initial context, and first checkpoint; finalize writes the last checkpoint, emits completion events, and releases resources.

### 2.2 How the next node is chosen — determinism (Section 3.2-3.3, attractor-spec.md:335-459)

The core loop (attractor-spec.md:340-403) is a single `WHILE true` traversal: resolve start node -> if terminal, check goal gates -> else execute handler with retry policy -> apply `context_updates` -> save checkpoint -> select next edge -> advance. `select_edge` (Section 3.3, attractor-spec.md:406-459) is a deterministic 5-step priority order:
1. **Condition match** — edges whose `condition` evaluates true (ties broken by weight then lexical order among condition-matched edges).
2. **Preferred label match** — first unconditional edge whose normalized `label` matches the outcome's `preferred_label` (normalization: lowercase, trim, strip accelerator prefixes like `[Y] `, `Y) `, `Y - `).
3. **Suggested next IDs** — first unconditional edge whose target is in the outcome's `suggested_next_ids` list, in list order.
4. **Highest weight** among remaining unconditional edges.
5. **Lexical tiebreak** on target node ID if weights are equal.

This 5-step order plus the fixed tiebreaks is what makes a run "deterministic" in the spec's own terms (Section 3.3 header text, attractor-spec.md:408: "The selection is deterministic and follows a five-step priority order").

### 2.3 Retries (Section 3.5-3.6, attractor-spec.md:480-562)

`max_retries` is *additional* attempts beyond the initial run (`max_attempts = max_retries + 1`); resolved from node attribute, else graph `default_max_retries` (legacy alias `default_max_retry`), else built-in default 0. Backoff config: `initial_delay_ms` (200), `backoff_factor` (2.0), `max_delay_ms` (60000), `jitter` (true, ±50%). Five preset policies are named: `none` (1 attempt), `standard` (5 attempts, 200ms/2.0x), `aggressive` (5 attempts, 500ms/2.0x), `linear` (3 attempts, fixed 500ms), `patient` (3 attempts, 2000ms/3.0x) (Section 3.6 table, attractor-spec.md:554-560). Default `should_retry` predicate retries network errors, 429, 5xx, provider-reported transient failures; does not retry 401/403/400/validation/config errors (attractor-spec.md:562).

### 2.4 Goal gates (Section 3.4, attractor-spec.md:461-478)

Nodes with `goal_gate=true` must reach SUCCESS or PARTIAL_SUCCESS before the pipeline is allowed to exit through the terminal node. On reaching the terminal node, engine checks all goal-gate nodes; if any is unsatisfied, it jumps to that node's `retry_target`, else `fallback_retry_target`, else the graph-level `retry_target`/`fallback_retry_target`, else the run ends FAIL.

### 2.5 Loops

Two loop mechanisms exist: (a) ordinary graph cycles via retry-target jumps and conditional edges back to earlier nodes (e.g., the `Retry`/`Fix` edges in the Integration Smoke Test, attractor-spec.md:1941-1946); (b) `loop_restart=true` on an edge, which terminates the *entire run* and relaunches with a fresh log directory starting at the edge's target (Section 2.7, attractor-spec.md:177; Section 3.2 step 7, attractor-spec.md:395-398).

### 2.6 Parallel / fan-out (Section 3.8, 4.8, 4.9)

Concurrency model: "The graph traversal is single-threaded. Only one node executes at a time in the top-level graph" (Section 3.8, attractor-spec.md:575). Parallelism is confined to the `parallel` (component shape) and `parallel.fan_in` (tripleoctagon shape) handlers, which manage concurrency internally. Each branch gets an isolated `context.clone()`; branch context changes are **not** merged back — only the parallel handler's own `context_updates` (e.g. `parallel.results`) propagate (attractor-spec.md:577, 819-825). Join policies: `wait_all` (all branches must complete) and `first_success` (attractor-spec.md:846-851). Fan-in reads `context.get("parallel.results")`, ranks candidates either via an LLM prompt or a heuristic sort by outcome-status then score then ID, and runs even if some branches failed as long as one succeeded (attractor-spec.md:853-892).

### 2.7 Failure routing (Section 3.7, attractor-spec.md:564-571)

On FAIL (or retry exhaustion), the engine tries, in order: (1) an outgoing edge with `condition="outcome=fail"`, (2) node `retry_target`, (3) node `fallback_retry_target`, (4) pipeline terminates with the stage's failure reason.

### 2.8 Timeouts

Node-level `timeout` (Duration type) attribute caps execution time (Section 2.6, attractor-spec.md:159); the `tool` handler passes it through to `run_shell_command(command, timeout=node.timeout)` (attractor-spec.md:907). No engine-level global run timeout is specified elsewhere in the document.

---

## 3. Node handlers (Section 4, attractor-spec.md:581-989)

Using the spec's own type names throughout:

| Handler type | Section | Contract summary |
|---|---|---|
| `start` | 4.3 (attractor-spec.md:632-642) | No-op, returns `Outcome(status=SUCCESS)` immediately. |
| `exit` | 4.4 (attractor-spec.md:644-654) | No-op, returns SUCCESS; goal-gate enforcement lives in the engine, not here. |
| `codergen` | 4.5 (attractor-spec.md:656-718) | Default LLM-task handler. Builds prompt (`node.prompt` or falls back to `node.label`, `$goal`-expanded), writes `prompt.md`, calls `backend.run(node, prompt, context)` where `backend` implements `CodergenBackend` (`run(node, prompt, context) -> String \| Outcome`, attractor-spec.md:714-715), writes `response.md` and `status.json`. If `backend` returns a raw string, the handler wraps it into `Outcome(status=SUCCESS, context_updates={"last_stage":..., "last_response": truncate(...,200)})`; if it returns an `Outcome` directly, that Outcome is used as-is. `backend=None` means simulation mode (canned response text). |
| `wait.human` | 4.6 (attractor-spec.md:720-786) | Derives multiple-choice options from outgoing edge labels (with accelerator-key parsing: `[Y] Label`, `Y) Label`, `Y - Label`, or first character), asks an `Interviewer`, and on answer returns `Outcome(status=SUCCESS, suggested_next_ids=[selected.to], context_updates={"human.gate.selected":..., "human.gate.label":...})`. On timeout with no `human.default_choice` node attribute, returns `RETRY`; on human-skip, returns `FAIL`. |
| `conditional` | 4.7 (attractor-spec.md:788-801) | Pure pass-through no-op returning SUCCESS; actual branching is done entirely by the engine's edge-selection algorithm evaluating edge `condition`s, keeping routing logic centralized and inspectable rather than embedded in a handler. |
| `parallel` | 4.8 (attractor-spec.md:803-851) | Fans out to all outgoing edges as branches (bounded by `max_parallel`, default 4), clones context per branch, stores serialized results in `context["parallel.results"]`, returns SUCCESS/PARTIAL_SUCCESS/FAIL per the configured `join_policy` (`wait_all` or `first_success`). |
| `parallel.fan_in` | 4.9 (attractor-spec.md:853-892) | Reads `parallel.results`; if `node.prompt` set, uses an LLM to rank candidates, else a heuristic sort (outcome rank, then descending score, then ID); records `parallel.fan_in.best_id` / `best_outcome` in `context_updates`. Fails only if all branches failed. |
| `tool` | 4.10 (attractor-spec.md:894-915) | Reads `tool_command` node attribute, runs it as a shell command with the node's `timeout`, returns `context_updates={"tool.output": stdout}` on success or FAIL on exception. |
| `stack.manager_loop` | 4.11 (attractor-spec.md:917-965) | Supervisor loop over a child pipeline (`graph.stack.child_dotfile`): observe/steer/wait cycle, polling on `manager.poll_interval` (default 45s) up to `manager.max_cycles` (default 1000), checking `context.stack.child.status`/`.outcome` and an optional `manager.stop_condition` expression; implements an "observe → guard → steer" supervisor architecture. |
| custom | 4.12 (attractor-spec.md:966-988) | Any `Handler` (single `execute(node, context, graph, logs_root) -> Outcome` method) can be registered under a new `type` string. Contract requirements: handlers must be stateless or synchronize shared mutable state, exceptions must be caught by the engine and converted to FAIL outcomes, and handlers "SHOULD NOT embed provider-specific logic; LLM orchestration is delegated to the integrated SDK" (attractor-spec.md:987). |

Handler return type — every handler returns an `Outcome` (Section 5.2, attractor-spec.md:1072-1094):
```
Outcome:
    status             : SUCCESS | FAIL | PARTIAL_SUCCESS | RETRY | SKIPPED
    preferred_label    : String
    suggested_next_ids : List<String>
    context_updates    : Map<String, Any>
    notes              : String
    failure_reason     : String
```

---

## 4. State and context (Section 5, attractor-spec.md:991-1236)

### 4.1 Context store (Section 5.1, attractor-spec.md:993-1071)

A thread-safe key-value map (`values`) with a read/write lock, an append-only `logs` list, and `set`/`get`/`get_string`/`append_log`/`snapshot`/`clone`/`apply_updates` operations. `clone()` deep-copies for parallel-branch isolation. Built-in engine-set keys include `outcome`, `preferred_label`, `graph.goal`, `current_node`, `last_stage`, `last_response`, `internal.retry_count.<node_id>` (table, attractor-spec.md:1050-1058). Namespace conventions (attractor-spec.md:1060-1071): `context.*` (semantic state), `graph.*` (mirrored graph attrs), `internal.*` (engine bookkeeping), `parallel.*`, `stack.*`, `human.gate.*`, `work.*`.

### 4.2 Checkpoints (Section 5.3, attractor-spec.md:1096-1135)

Saved after every node completion: `timestamp`, `current_node`, `completed_nodes`, `node_retries`, `context_values` (serialized snapshot), `logs`. Resume procedure (attractor-spec.md:1127-1134): load `{logs_root}/checkpoint.json`, restore context/completed-nodes/retry-counters, resume at the node after `current_node`. Notably: **if the previous node used `full` fidelity (a live LLM session), the resumed run degrades that first resumed node to `summary:high` fidelity for one hop because in-memory sessions can't be serialized** — after that one degraded hop, `full` fidelity can resume (attractor-spec.md:1134).

### 4.3 Context fidelity (Section 5.4, attractor-spec.md:1136-1175)

Controls how much prior state carries into a node's LLM session: `full` (session reused, unbounded via compaction), `truncate` (fresh, minimal), `compact` (fresh, structured bullet summary — the runtime default when unset), `summary:low/medium/high` (fresh, ~600/1500/3000 token budgets). Precedence: edge `fidelity` > node `fidelity` > graph `default_fidelity` > default `compact`. Thread-key resolution for `full` fidelity (session reuse): node `thread_id` > edge `thread_id` > graph default thread > subgraph-derived class > previous node ID.

### 4.4 Artifact store (Section 5.5, attractor-spec.md:1177-1220)

Named, typed storage for large stage outputs kept out of the context (which should hold only small scalars for checkpoint serialization/routing). File-backing threshold defaults to 100KB — below it, artifacts stay in memory; above it, they're written to `{base_dir}/artifacts/{artifact_id}.json`.

### 4.5 Run directory layout (Section 5.6, attractor-spec.md:1222-1236)

```
{logs_root}/
    checkpoint.json
    manifest.json
    {node_id}/
        status.json
        prompt.md
        response.md
    artifacts/
        {artifact_id}.json
```

### 4.6 Status File Contract (Appendix C, confirmed heading "Appendix C: Status File Contract", attractor-spec.md:2053)

Each non-terminal node writes `status.json` in its stage directory (attractor-spec.md:2057-2078):
```json
{
  "outcome": "success | retry | fail | partial_success",
  "preferred_label": "<edge label or empty>",
  "suggested_next_ids": ["<node_id>", ...],
  "context_updates": {"key": "value"},
  "notes": "Human-readable execution summary"
}
```
This is explicitly designed to double as an external interop channel: "external tools or agents can write `status.json` to communicate outcomes back to the engine" (Section 4.5, attractor-spec.md:709). If `auto_status=true` and no `status.json` was written, the engine synthesizes `{"outcome": "success", "notes": "auto-status: handler completed without writing status"}` (attractor-spec.md:2078). This is the most directly relevant mechanism for a Claude-Code-driven runner: Claude Code itself would need to (or a thin wrapper around it would need to) write this file per milestone step.

### 4.7 Error categories (Appendix D, confirmed heading "Appendix D: Error Categories", attractor-spec.md:2082-2090)

Three categories: **Retryable** (LLM rate limits, network timeouts, transient service unavailability — auto-retried per node retry policy), **Terminal** (invalid prompt, missing required context, auth failures — not retried, routed to failure path immediately), **Pipeline errors** (structural: no start node, unreachable nodes, invalid conditions — caught at validation time when possible; runtime detection terminates immediately).

---

## 5. Human-in-the-loop, validation, stylesheet, transforms, DoD

### 5.1 Human-in-the-loop — the "Interviewer" pattern (Section 6, confirmed heading "6. Human-in-the-Loop (Interviewer Pattern)", attractor-spec.md:1240)

Interface (attractor-spec.md:1247-1251): `ask(question) -> Answer`, `ask_multiple(questions) -> List<Answer>`, `inform(message, stage) -> Void`. `Question` has `type` ∈ {YES_NO, MULTIPLE_CHOICE, FREEFORM, CONFIRMATION}, plus `default`, `timeout_seconds`, `stage`, `metadata`. Five built-in implementations (Section 6.4, attractor-spec.md:1291-1357):
- `AutoApproveInterviewer` — always YES / first option; "Used for automated testing and CI/CD pipelines where no human is available."
- `ConsoleInterviewer` — CLI stdin/stdout.
- `CallbackInterviewer` — delegates to an external callback (Slack, web UI, API).
- `QueueInterviewer` — pre-filled answer queue for deterministic testing/replay; returns SKIPPED if the queue is empty.
- `RecordingInterviewer` — wraps another interviewer, records Q/A pairs for replay/audit.

Timeout handling (Section 6.5, attractor-spec.md:1359-1368): use `default` answer if set, else return `Answer(value=TIMEOUT)`; for `wait.human` nodes specifically, `human.default_choice` node attribute names the edge target to take on timeout.

### 5.2 Validation and linting (Section 7, attractor-spec.md:1371-1441)

Diagnostic model: `rule`, `severity` (ERROR/WARNING/INFO), `message`, `node_id`, `edge`, `fix`. Built-in rules (table, attractor-spec.md:1394-1408) include `start_node`/`terminal_node`/`reachability`/`edge_target_exists`/`start_no_incoming`/`exit_no_outgoing`/`condition_syntax`/`stylesheet_syntax` (all ERROR), and `type_known`/`fidelity_valid`/`retry_target_exists`/`goal_gate_has_retry`/`prompt_on_llm_nodes` (all WARNING). `validate_or_raise()` throws on any ERROR-severity diagnostic. Custom lint rules implement `LintRule { name, apply(graph) -> List<Diagnostic> }` and are appended to built-ins.

### 5.3 Model stylesheet (Section 8, confirmed heading "8. Model Stylesheet", attractor-spec.md:1445)

A CSS-like language on the graph's `model_stylesheet` attribute for defaulting `llm_model`, `llm_provider`, `reasoning_effort` per node without repeating them on every node. Selectors: `*` (specificity 0) < shape name (1) < `.class` (2) < `#node_id` (3, highest) (Section 8.3, attractor-spec.md:1464-1474). Resolution order overall (Section 8.5, attractor-spec.md:1483-1492): explicit node attribute > stylesheet match by specificity > graph-level default > handler/system default. Applied as a transform after parsing, before validation, and only fills in properties the node doesn't already set explicitly.

### 5.4 Transforms/extensibility (Section 9, confirmed heading "9. Transforms and Extensibility", attractor-spec.md:1525)

`Transform { apply(graph) -> Graph }`, run in order between parse and validate. Built-ins (Section 9.2, attractor-spec.md:1548-1563): Variable Expansion (`$goal` substitution), Stylesheet Application, and a Preamble Transform (synthesizes context-carryover text for non-`full`-fidelity stages, applied at execution time since it needs runtime state). Custom transforms run after built-ins, in registration order; use cases listed include injecting logging/audit nodes, adding retry wrappers, merging graphs, applying org-wide defaults (attractor-spec.md:1575-1579). Section 9.4 covers pipeline composition (sub-pipeline nodes like the manager-loop handler, and transform-based graph merging). Section 9.5 defines an optional HTTP server mode with endpoints for submitting/observing/cancelling pipelines and answering human-gate questions over SSE. Section 9.6 defines the full typed event taxonomy (pipeline/stage/parallel/interview/checkpoint lifecycle events). Section 9.7 defines `tool_hooks.pre`/`tool_hooks.post` shell hooks that wrap every LLM tool call (pre-hook nonzero exit skips the tool call; post-hook failures are logged but non-blocking).

### 5.5 Definition of Done (Section 11, confirmed heading "11. Definition of Done", attractor-spec.md:1783)

Eleven checklists (11.1 DOT Parsing through 11.11 Transforms/Extensibility), plus 11.12 a Cross-Feature Parity Matrix of 21 pass/fail test cases (attractor-spec.md:1896-1923) and 11.13 a full Integration Smoke Test (attractor-spec.md:1925-1980) that parses a 5-node plan→implement→review→done pipeline, validates it, executes it with a real LLM callback, and asserts on outcome status, artifact files, goal-gate satisfaction, and final checkpoint state.

---

## 6. coding-agent-loop-spec.md and unified-llm-spec.md: what they define, and what's unnecessary when delegating to Claude Code

### 6.1 What coding-agent-loop-spec.md defines

A from-scratch spec for building your own agentic coding-assistant *library* (not CLI) that pairs an LLM with dev tools. Table of contents (coding-agent-loop-spec.md:11-19): Overview, Agentic Loop (Session/turns/core loop/steering/reasoning-effort/stop-conditions/events/loop-detection), Provider-Aligned Toolsets (per-provider tool profiles: OpenAI/codex-rs-aligned with `apply_patch`, Anthropic/Claude-Code-aligned with `edit_file` old_string/new_string, Gemini/gemini-cli-aligned), Tool Execution Environment (`ExecutionEnvironment` abstraction: Local required, Docker/K8s/WASM/SSH as extension points), Tool Output and Context Management (truncation limits per tool, command timeouts, context-window awareness), System Prompts and Environment Context (layered system-prompt construction, project doc discovery: AGENTS.md/CLAUDE.md/GEMINI.md/.codex/instructions.md), Subagents (`spawn_agent`/`send_input`/`wait`/`close_agent`), an explicit "Out of Scope" section (MCP, Skills, Sandboxing, Compaction, Approval systems, Read-before-write guardrail — coding-agent-loop-spec.md:1133-1148), and its own Definition of Done + Cross-Provider Parity Matrix.

Its stated reason for existing (coding-agent-loop-spec.md:31-44) is explicitly that CLIs like Claude Code, Codex CLI, and Gemini CLI are "black boxes" in non-interactive mode — "text goes in, text comes out. You cannot programmatically inspect the conversation mid-run, inject steering messages between tool calls, swap the execution environment, change reasoning effort on the fly, observe individual tool calls as they happen, or compose agents into larger systems." Building this spec is how you'd get that fine-grained control back — at the cost of re-implementing an entire agent loop, tool suite, truncation policy, and provider-aligned prompt/tool sets.

### 6.2 What unified-llm-spec.md defines

A from-scratch spec for a multi-provider LLM client (OpenAI, Anthropic, Gemini) with a 4-layer architecture (Provider Adapter spec / provider utilities / Core Client / high-level `generate()`/`stream()`/`generate_object()` API — unified-llm-spec.md:54-75), a unified Message/ContentPart/Role/Tool/Response/Usage/StreamEvent data model (Section 3), generation & streaming methods (Section 4), a full tool-calling loop including parallel tool execution semantics (Section 5), an error taxonomy with retryability classification and exponential-backoff retry policy (Section 6), and a Provider Adapter Contract for request/response/error translation per provider (Section 7). It requires using each provider's *native* API (OpenAI Responses API, Anthropic Messages API, Gemini's own API) rather than a compatibility shim, specifically to preserve reasoning tokens, extended thinking, and prompt caching (Section 2.7, unified-llm-spec.md:210-220).

coding-agent-loop-spec.md explicitly layers on top of this: "This spec layers on top of the Unified LLM Client Specification, which handles all LLM communication. The agent loop uses the SDK's low-level `Client.complete()` and `Client.stream()` methods directly, implementing its own turn loop..." (coding-agent-loop-spec.md:5).

### 6.3 What's unnecessary if the runner delegates to Claude Code CLI instead of owning the loop and LLM client

Attractor's own layering statement is the load-bearing quote here (Section 1.4, attractor-spec.md:54-60): "Attractor defines the orchestration layer: graph definition, traversal, state management, and extensibility. It does NOT require any specific LLM integration... What that backend does internally is entirely up to the implementor -- use the companion Coding Agent Loop and Unified LLM Client specs... spawn CLI agents (Claude Code, Codex, Gemini CLI) in subprocesses, run agents in tmux panes with a manager attaching to them, call an LLM API directly, or anything else. The pipeline definition (the DOT file) does not change regardless of backend choice." And the README (README.md:5): "Although bringing your own agentic loop and unified LLM SDK is not required to build your own Attractor, we highly recommend controlling the stack so you have a strong foundation."

If the runner's `CodergenBackend` shells out to Claude Code non-interactively per node, the following becomes unnecessary (all of coding-agent-loop-spec.md and unified-llm-spec.md, functionally):

- The entire Session/turn-loop machinery (coding-agent-loop-spec.md Section 2: Session record, turn types, the core `process_input` loop, steering queues, loop detection) — Claude Code already runs its own turn loop internally.
- Provider-aligned toolsets and the ProviderProfile abstraction (Section 3) — Claude Code already ships its own Anthropic-aligned tool set (`read_file`/`write_file`/`edit_file`/`shell`/`grep`/`glob`) and system prompt; no need to reimplement or choose per-provider tool schemas.
- The `ExecutionEnvironment` abstraction and its Local/Docker/K8s/WASM/SSH implementations (Section 4) — Claude Code runs tools in its own process/sandbox; the runner does not need to mediate tool execution.
- Tool output truncation policy, per-tool char/line limits, context-window-usage heuristics (Section 5) — internal to Claude Code's own loop.
- System-prompt layering and project-doc discovery (Section 6, e.g. CLAUDE.md/AGENTS.md loading) — Claude Code already does this natively.
- Subagent spawn/send_input/wait/close_agent tools (Section 7) — Claude Code has its own Task/subagent mechanism (as referenced generically at coding-agent-loop-spec.md:639).
- The entire Unified LLM Client spec (unified-llm-spec.md) — Message/ContentPart/Role data model, `Client.complete()`/`stream()`, tool-calling loop and parallel tool execution, provider adapter contract, error taxonomy/retry/backoff, prompt-caching header injection, reasoning-token accounting — all of this is Anthropic-API plumbing that Claude Code already owns; the runner never talks to the Anthropic API directly.

What is **not** made unnecessary — i.e., what a Claude-Code-backed runner must still build itself, per Attractor's own spec, regardless of backend choice: the DOT parser/validator, the execution engine and edge-selection algorithm (Section 3), the node-handler registry and non-codergen handlers (`wait.human`, `conditional`, `parallel`, `tool`, etc. — Section 4), the Context/Checkpoint/Artifact store and run-directory layout (Section 5), goal-gate enforcement and retry policy at the *pipeline* level (separate from whatever retry Claude Code does internally on its own tool calls), the condition-expression evaluator (Section 10), and — critically — the glue that gets a Claude Code subprocess invocation to produce something that satisfies the `CodergenBackend.run() -> String | Outcome` contract and/or the `status.json` Status File Contract (Appendix C), since Claude Code's native output is free-form text/tool-transcript, not a pre-shaped `Outcome`.

No section of any of the three files uses the literal phrases "bring your own loop" or "pluggable backend"; the closest matching language is "Pluggable handlers" (Section 1.3, attractor-spec.md:46, referring to node-handler pluggability, not LLM backend pluggability) and the Section 1.4 / README passages quoted above, which describe LLM-backend choice as fully open-ended rather than using a fixed term of art.

---

## 7. Concept inventory

| Attractor concept | What it is | Must-have for a minimal runner? | Notes |
|---|---|---|---|
| DOT pipeline parsing (Section 2) | Restricted Graphviz DOT parser producing a Graph model | Yes | One digraph/file, directed only, typed attrs (attractor-spec.md:64-129). Needed to read the 12-step milestone plan as a graph at all. |
| Shape-to-handler mapping (Appendix B / 2.8) | box/hexagon/diamond/component/tripleoctagon/parallelogram/house -> handler type | Yes, at least `box`(codergen)/`Mdiamond`(start)/`Msquare`(exit) | Other shapes only needed if the milestone plan uses human gates, parallel fan-out, or tool nodes. |
| Condition expression language (Section 10) | `=`/`!=`/`&&` boolean guards on edges | Yes, minimally | Needed for any success/fail branching between milestone steps; only `=`/`!=`/`&&` — no OR/regex. |
| Edge-selection algorithm (Section 3.3) | 5-step deterministic priority: condition > preferred_label > suggested_next_ids > weight > lexical | Yes | This is the determinism guarantee; a simplified runner still needs *some* deterministic tie-break. |
| `codergen` handler + `CodergenBackend` (4.5) | LLM-task handler; single `run(node,prompt,context)->String\|Outcome` seam | Yes | This is exactly where a Claude-Code-subprocess backend plugs in. |
| `start`/`exit` handlers (4.3/4.4) | No-op entry/exit | Yes | Trivial to implement. |
| `conditional` handler (4.7) | No-op pass-through; engine does the routing | Only if using diamond-shaped explicit conditional nodes | Functionally redundant with plain edge conditions on any node. |
| `wait.human` handler + Interviewer (4.6, Section 6) | Human-in-the-loop gate via pluggable Interviewer | Optional | `AutoApproveInterviewer`/`QueueInterviewer` make it usable in unattended/CI mode if a milestone step needs a checkpoint-style approval. |
| `parallel` / `parallel.fan_in` handlers (4.8/4.9) | Concurrent fan-out with isolated context clones + join policies | Optional | Only needed if milestone steps can run concurrently (e.g., independent components of the feed handler). |
| `tool` handler (4.10) | Runs a shell command as a node | Optional | Useful for build/test/lint steps between LLM steps. |
| `stack.manager_loop` handler (4.11) | Supervisor observe/steer/wait loop over a child pipeline | Unlikely needed | Aimed at long-running worker supervision; probably overkill for a fixed 12-step plan. |
| Custom handler registration (4.12) | `Handler{execute()}` registry | Yes (mechanism), specific handlers optional | Needed as an extension point regardless of which handlers are implemented first. |
| Context store (5.1) | Thread-safe KV map with clone/snapshot | Yes | Minimum viable state passing between steps. |
| Outcome / Status File Contract (5.2, Appendix C) | `status.json` schema: outcome/preferred_label/suggested_next_ids/context_updates/notes | Yes | This is the hand-off point a Claude-Code-driven step must satisfy somehow. |
| Checkpoint + resume (5.3) | Per-node JSON checkpoint, resume-from-last-node | Yes for a 12-step run you might interrupt/resume | Note the documented `full`->`summary:high` fidelity degradation on resume. |
| Context fidelity modes (5.4) | full/truncate/compact/summary:low/medium/high | Optional but useful | Governs whether each milestone step gets a fresh Claude Code session or a continued one; directly relevant to session/thread management. |
| Artifact store (5.5) | Large-output side storage, 100KB file-backing threshold | Optional | Useful once step outputs (design docs, code diffs) get large. |
| Run directory layout (5.6) | `{logs_root}/checkpoint.json`, `{node_id}/{status,prompt,response}`, `artifacts/` | Yes (some layout) | Doesn't have to match exactly, but something equivalent is needed for auditability/resume. |
| Model stylesheet (Section 8) | CSS-like per-node model/provider/reasoning_effort defaults | No | Irrelevant if the backend is always "Claude Code" rather than a multi-provider LLM call. |
| Validation/linting rules (Section 7) | start/terminal/reachability/edge-target/condition-syntax checks etc. | Recommended | Cheap correctness net before executing a 12-node graph; not strictly required to run. |
| Transforms/extensibility (Section 9.1-9.3) | AST transform pipeline ($goal expansion, stylesheet, custom) | Minimal subset only | Only `$goal` expansion is likely needed; stylesheet transform is moot per above. |
| HTTP server mode (9.5) | REST/SSE endpoints for remote control | No | Nice-to-have for a UI, not needed for a CLI-driven milestone runner. |
| Observability/event system (9.6) | Typed pipeline/stage/parallel/interview/checkpoint events | Optional | Useful for logging/progress visibility during a long unattended run. |
| Tool call hooks (9.7) | pre/post shell hooks around every LLM tool call | No | This is about hooking the *coding-agent-loop*'s internal tool calls, which are Claude Code's own concern, not the runner's, per Section 6 analysis above. |
| Error categories (Appendix D) | Retryable / Terminal / Pipeline error taxonomy | Recommended | Useful conceptual split for deciding when the runner retries a Claude-Code invocation vs. gives up. |
| Coding-agent-loop spec (whole doc) | From-scratch agentic loop, provider-aligned tools, execution env, truncation, subagents | No, if delegating to Claude Code | Per Section 6 analysis: superseded by Claude Code's own internals. |
| Unified LLM client spec (whole doc) | From-scratch multi-provider LLM client (adapters, tool loop, retry, streaming) | No, if delegating to Claude Code | Per Section 6 analysis: superseded because the runner never calls the Anthropic API directly. |

---

## Open questions this material does not answer

- None of the three files specify *how* a CLI-agent-based `CodergenBackend` should extract a structured `Outcome` (status/preferred_label/context_updates) from Claude Code's normal non-interactive output. The Status File Contract (Appendix C) implies the invoked process could write `status.json` itself, but nothing in these specs says how a runner should prompt/instruct Claude Code to do that, or how to handle the case where it doesn't.
- No guidance on how `thread_id`/session-reuse (`full` fidelity, Section 5.4) would map onto Claude Code's own session/resume mechanisms (e.g., whether "reusing a thread" means reusing an underlying Claude Code session/conversation or just replaying a summarized transcript into a new invocation).
- No discussion of how the `timeout` node attribute or command timeouts would interact with a potentially long-running Claude Code invocation that itself runs shell commands with its own internal timeouts.
- No treatment of cost/token accounting, model selection, or the model stylesheet in a world where the "model" is fixed to whatever Claude Code uses internally — Section 8 (stylesheet) and the unified-llm-spec model catalog assume the runner picks the model directly.
- The parallel handler's context-isolation model (branch context clones not merged back, Section 3.8/4.8) is defined for the top-level engine but the specs don't address what happens if the underlying Claude Code backend itself has state (e.g., a working directory with file changes) shared across "isolated" branches — file-system side effects aren't modeled by the Context store at all.
- No mention anywhere of authentication/session lifecycle for a subprocess-CLI backend (e.g., how Claude Code's own auth/session start-up cost factors into per-node execution or retry timing).
- The coding-agent-loop-spec's "Out of Scope" list (Section 8) explicitly excludes MCP, Skills, sandboxing, compaction, and approval systems as nice-to-haves layered on top — but doesn't say whether/how a DOT-graph runner sitting *above* Claude Code should be the one to add approval gates (Attractor's `wait.human`) versus relying on Claude Code's own permission prompts, if any conflict arises between the two layers.
