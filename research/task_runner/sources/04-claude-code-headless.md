# Claude Code headless mode (`-p`/`--print`) and the Agent SDK

Sources consulted (fetched as `.md` via curl on 2026-09-19; all HTTP 200 unless noted):
- https://code.claude.com/docs/en/headless.md
- https://code.claude.com/docs/en/cli-reference.md
- https://code.claude.com/docs/en/settings.md
- https://code.claude.com/docs/en/hooks.md
- https://code.claude.com/docs/en/hooks-guide.md
- https://code.claude.com/docs/en/sub-agents.md
- https://code.claude.com/docs/en/iam.md
- https://code.claude.com/docs/en/permissions.md
- https://code.claude.com/docs/en/agent-sdk/overview.md
- https://code.claude.com/docs/en/agent-sdk/python.md
- https://code.claude.com/docs/en/agent-sdk/typescript.md
- https://code.claude.com/docs/en/permission-modes.md
- https://code.claude.com/docs/en/sessions.md
- https://code.claude.com/docs/en/settings-reference.md
- https://code.claude.com/docs/en/errors.md
- Local: `claude --version`, `claude --help`, `claude -p --help` (Claude Code v2.1.278, run in this container)

Note: `https://code.claude.com/docs/en/sdk.md`, `/sdk-overview.md`, `/sdk-typescript.md`, `/sdk-python.md` all 404'd — the correct paths are under `/docs/en/agent-sdk/*` (overview, python, typescript), not `/docs/en/sdk*`.

## Key takeaways for building our runner

- `claude --help`/`claude -p --help` (v2.1.278) do **not** list `--max-turns`, `--permission-prompt-tool`, `--system-prompt-file`, `--append-system-prompt-file`, `--init`/`--init-only`/`--maintenance` — but cli-reference.md documents all of them and explicitly warns `--help` is not exhaustive. Verify any flag we plan to rely on against both sources before depending on it.
- The full JSON result-object schema (`is_error`, `num_turns`, `total_cost_usd`, `usage`, `permission_denials`, `terminal_reason`, etc.) is documented as `SDKResultMessage` in agent-sdk/typescript.md, not in headless.md itself — headless.md only says the CLI's `--output-format json` payload carries "result, session ID, and metadata."
- `--bare` (headless.md, cli-reference.md) is the documented way to stop a driven session from picking up a repo's own `.claude/settings.json` hooks, `.mcp.json` servers, skills, commands, and CLAUDE.md; `--settings '{"disableAllHooks": true}'` is the documented way to keep other config but disable hooks specifically (hooks.md line ~3784).
- `--max-budget-usd` (cost cap) is documented and appears in `--help`; there is no documented wall-clock timeout flag — undocumented, we would have to enforce our own process timeout.
- Session control flags `--resume`, `--continue`/`-c`, `--session-id`, `--fork-session` are all documented and confirmed via `--help`.
- Stop hooks can block completion (`decision: "block"`) but Claude Code force-overrides after **8 consecutive blocks** (hooks.md) — a runner using Stop hooks to enforce "keep going until X" needs to plan for that hard cap.
- `--permission-prompts none` (documented, requires v2.1.259+, confirmed present in cli-reference table but NOT in local `--help` output for v2.1.278 despite `--permission-prompts` itself being in `--help`) denies anything that would otherwise prompt a human, which is the documented way to run fully unattended.
- Structured output via `--json-schema` is documented and confirmed via `--help` (v2.1.278); output arrives in a top-level `structured_output` field alongside the normal result metadata.
- SIGTERM to a `claude -p` process yields exit code 143 and no result for the in-flight turn; SIGINT is the documented way to end a turn cleanly before stopping.
- The Python Agent SDK's own install instructions (agent-sdk/python.md) hit exactly the constraint we already found in this environment: `pip install` against system Python fails with `error: externally-managed-environment`, and the docs' own fix is a venv — which `ensurepip`/venv is unavailable for us, per prior environment checks.

## 1. `-p`/`--print` mode basics

Documented (headless.md): Add `-p`/`--print` to run non-interactively. Reads stdin (piped input capped at 10MB — exceeding it exits non-zero). Exits 0 on success, non-zero on failure. Invalid-flag errors go to stderr before the run starts; failures occurring *during* the run (e.g. missing auth) are printed as the result on stdout instead.

Confirmed via `-p --help`: `-p, --print` — "Print response and exit (useful for pipes)." Also notes: "The workspace trust dialog is skipped when Claude is run in non-interactive mode... Settings files that fail validation are silently ignored in this mode (no error dialog is shown)."

`--bare` (documented, confirmed via `--help`): skips auto-discovery of hooks, skills, custom commands, subagents, plugins, MCP servers, auto memory, and CLAUDE.md, for faster/more deterministic CI runs. Sets `CLAUDE_CODE_SIMPLE=1`. In bare mode, Claude Code never reads OAuth credentials/keychain — must set `ANTHROPIC_API_KEY` or an `apiKeyHelper` via `--settings`. Bare mode still has access to Bash, file-read, file-edit tools. Docs note: "`--bare` is the recommended mode for scripted and SDK calls, and will become the default for `-p` in a future release."

Background Bash tasks started during a `-p` run are killed ~5s after the final result (grace period for output that lands just after). Background subagents/workflows instead keep the process open until they finish, capped at 10 minutes idle wait (`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` to change, `0` to disable). (Documented, headless.md.)

## 2. `--output-format json`/`stream-json` and the result object

Documented (headless.md): `--output-format` choices are `text` (default), `json` (structured JSON with result, session ID, metadata), `stream-json` (newline-delimited JSON events). Confirmed via `-p --help`: same three choices listed.

The `result` field carries the text result on success. Example from docs: `claude -p "Summarize this project" --output-format json | jq -r '.result'`.

The **full field-level schema** is documented only in agent-sdk/typescript.md as `SDKResultMessage` (this is the Agent SDK's typed form of the same result the CLI's `--output-format json` emits; the CLI and SDK ride the same underlying agent loop per agent-sdk/overview.md). Two variants:

Success (`subtype: "success"`):
```typescript
{
  type: "result"; subtype: "success"; uuid: UUID; session_id: string;
  duration_ms: number; duration_api_ms: number; is_error: boolean;
  api_error_status?: number | null; num_turns: number; result: string;
  stop_reason: string | null; ttft_ms?: number; ttft_stream_ms?: number;
  user_message_uuid?: string; user_message_uuids?: string[];
  total_cost_usd: number; usage: NonNullableUsage;
  modelUsage: { [modelName: string]: ModelUsage };
  permission_denials: SDKPermissionDenial[];
  queued_turn_count?: number; structured_output?: unknown;
  deferred_tool_use?: { id: string; name: string; input: Record<string, unknown> };
  terminal_reason?: TerminalReason; fast_mode_state?: FastModeState;
  fast_mode_disabled_reason?: FastModeDisabledReason; origin?: SDKMessageOrigin;
}
```
Error (`subtype: "error_max_turns" | "error_during_execution" | "error_max_budget_usd" | "error_max_structured_output_retries"`): same core fields (`session_id`, `duration_ms`, `duration_api_ms`, `is_error`, `num_turns`, `stop_reason`, `total_cost_usd`, `usage`, `modelUsage`, `permission_denials`, `queued_turn_count?`) plus `errors: string[]` and optional `startup_failure_reason`.

`terminal_reason` enum values (documented): `completed`, `max_turns`, `tool_deferred`, `aborted_streaming`, `aborted_tools`, `hook_stopped`, `stop_hook_prevented`, `background_requested`, `blocking_limit`, `rapid_refill_breaker`, `prompt_too_long`, `image_error`, `model_error`, `api_error`, `malformed_tool_use_exhausted`, `budget_exhausted`, `structured_output_retry_exhausted`, `tool_deferred_unavailable`, `turn_setup_failed`. This is exactly the field a runner should key its retry/escalation logic on.

`total_cost_usd` and `modelUsage`/per-model cost breakdown are documented as **client-side estimates**, explicitly said to "can differ from your actual bill" (headless.md, agent-sdk/typescript.md) — do not treat as authoritative billing.

`--output-format stream-json` requires `--verbose` to get partial/streaming events (documented, confirmed via `--help`: `--include-partial-messages` "only works with --print and --output-format=stream-json"). The stream's `system/init` event (documented) reports model, tools, MCP servers, loaded plugins, and (v2.1.205+) a `capabilities` string array for feature-detection. `system/init` also carries `plugins`/`plugin_errors` and `mcp_servers`/`mcp_server_errors` arrays useful for CI gating on "did my MCP server actually load."

`--forward-subagent-text` (documented, confirmed via `--help`) makes subagent text/thinking blocks appear in the stream as `assistant`/`user` messages tagged with `parent_tool_use_id`, for reconstructing subagent transcripts.

## 3. Session control: `--resume`, `--continue`, `--session-id`, `--fork-session`

| Flag | Behavior | Status | Source |
|---|---|---|---|
| `--resume`, `-r` | Resume a session by ID, name, or `.jsonl` transcript path; bare `--resume` opens interactive picker (not usable headlessly without an ID) | documented + confirmed via `--help` | cli-reference.md, `-p --help` |
| `--continue`, `-c` | Continue most recent conversation in cwd. `claude -p --continue` (unlike interactive `--continue`) includes sessions created by `-p` or the Agent SDK | documented + confirmed via `--help` | cli-reference.md |
| `--session-id` | Use a specific session ID (must be valid UUID) for a new conversation | documented + confirmed via `--help` | cli-reference.md, `-p --help` |
| `--fork-session` | When resuming, create a new session ID instead of reusing the original; use with `--resume`/`--continue` | documented + confirmed via `--help` | cli-reference.md, `-p --help` |

Practical pattern from docs: capture session id from a JSON result (`session_id=$(claude -p "..." --output-format json | jq -r '.session_id')`) then `claude -p "..." --resume "$session_id"`. Since v2.1.223 the ID search covers every project on the machine, not just cwd. `--resume` also accepts the absolute path to the session's `.jsonl` transcript file directly.

## 4. `--max-turns` and budget/timeout flags

| Flag | Purpose | Status | Source |
|---|---|---|---|
| `--max-turns` | Limit agentic turns in print mode; exits with error at limit; no limit by default | **documented only** — absent from `claude --help` and `claude -p --help` output on v2.1.278 | cli-reference.md (not in local `--help`) |
| `--max-budget-usd` | Stop once client-side estimated API spend reaches this USD figure (print mode only); subagent spend counts toward it; spawning a subagent past the cap fails with "Budget limit reached" and running background subagents are stopped (v2.1.217+) | documented + confirmed via `--help` | cli-reference.md, `-p --help` |
| (wall-clock timeout) | No such flag found | **undocumented / does not appear to exist** — nothing in cli-reference.md, headless.md, or `--help` output names a session-duration or per-turn time limit | n/a |

We ran `grep -c "max-turns"` against the full captured `claude --help` and `claude -p --help` text and got `0` matches in both — confirmed absent from `--help`, even though cli-reference.md documents it with example `claude -p --max-turns 3 "query"`. The docs explicitly caveat this: "`claude --help` does not list every flag, so a flag's absence from `--help` does not mean it is unavailable" (cli-reference.md). We did not run `claude -p --max-turns 3 "query"` (forbidden — starts a real session), so we cannot independently confirm the flag is accepted by this binary; treat as documented-but-unverified-locally.

The Agent SDK's `Options` type (TypeScript) does have a confirmed `maxTurns` property (seen directly in the `agent-sdk/typescript.md` Options table), which is stronger evidence the underlying capability exists in v2.1.278 even though the CLI flag itself isn't in `--help`.

On SIGTERM: exit code 143, in-flight turn's result is dropped entirely (documented, headless.md). SIGINT or the SDK's `interrupt()` ends the turn cleanly instead and is the recommended way to stop a run if you want it resumable.

## 5. Permission modes, allow/deny tool lists, skip-permissions

| Flag | Purpose | Status | Source |
|---|---|---|---|
| `--permission-mode` | Start in mode `default`("manual" alias, v2.1.200+)/`acceptEdits`/`plan`/`auto`/`dontAsk`/`bypassPermissions` | documented + confirmed via `--help` (choices list matches, though `--help` shows `manual` where docs also allow `default`) | cli-reference.md, `-p --help` |
| `--allowedTools`, `--allowed-tools` | Tools/patterns that run without prompting, e.g. `Bash(git *)` | documented + confirmed via `--help` | cli-reference.md, `-p --help` |
| `--disallowedTools`, `--disallowed-tools` | Deny rules; bare tool name removes it from context entirely, `"*"` removes all, `mcp__*` removes all MCP tools | documented + confirmed via `--help` | cli-reference.md, `-p --help` |
| `--dangerously-skip-permissions` | Equivalent to `--permission-mode bypassPermissions`; skips permission prompts entirely | documented + confirmed via `--help` | cli-reference.md, `-p --help` |
| `--allow-dangerously-skip-permissions` | Adds `bypassPermissions` to the Shift+Tab cycle without starting in it (lets you start in e.g. `plan` and switch later) | documented + confirmed via `--help` | cli-reference.md, `-p --help` |
| `--permission-prompts` | `host` (default; send to SDK `canUseTool`/`--permission-prompt-tool`) or `none` (deny anything needing a human, requires v2.1.259+) | documented + confirmed via `--help` (flag and both choice values present) | cli-reference.md, `-p --help` |
| `--permission-prompt-tool` | MCP tool to handle permission prompts non-interactively | **documented only** — not found in local `--help` output | cli-reference.md |
| `--tools` | Restrict which built-in tools are available at all (vs. `--allowedTools`, which only auto-approves) | documented + confirmed via `--help` | cli-reference.md, `-p --help` |
| `--restricted` | Removes command/code-execution tools and WebFetch unless named in `--tools`; confines file tools to working dirs; refuses `bypassPermissions`; loads only managed + `--settings` settings (requires v2.1.248+) | documented + confirmed via `--help` | cli-reference.md, `-p --help` |

Docs explicitly state: for `-p`, the built-in starting permission mode is **Manual** on every plan (i.e. it will prompt) unless you pass `--permission-mode` or `--dangerously-skip-permissions`. For unattended CI, headless.md's documented pattern is `--permission-mode auto --permission-prompts none` (classifier reviews actions; anything that would still need a human prompt is denied, not hung).

With `--permission-prompts none`, `AskUserQuestion` is removed from the tool set entirely, and any MCP elicitation request with no `Elicitation` hook answering it is cancelled (documented).

## 6. System prompt, model, settings, add-dir, MCP config flags

| Flag | Purpose | Status | Source |
|---|---|---|---|
| `--append-system-prompt` | Append text to default system prompt | documented + confirmed via `--help` | cli-reference.md, `-p --help` |
| `--append-system-prompt-file` | Same, from a file | **documented only** — not in local `--help` | cli-reference.md |
| `--system-prompt` | Replace entire system prompt | documented + confirmed via `--help` | cli-reference.md, `-p --help` |
| `--system-prompt-file` | Replace, from a file | **documented only** — not in local `--help` | cli-reference.md |
| `--system-prompt-snapshot <on\|off>` | Whether the system prompt is recorded once and reused verbatim across `--resume`/`--continue`, or rebuilt every request | documented + confirmed via `--help` | cli-reference.md, `-p --help` |
| `--model` | Model alias (`sonnet`,`opus`,`haiku`,`fable`) or full name | documented + confirmed via `--help` | cli-reference.md, `-p --help` |
| `--settings` | Path to JSON file or inline JSON string; overrides matching keys in `settings.json` for this session only | documented + confirmed via `--help` | cli-reference.md, `-p --help` |
| `--setting-sources` | Comma list of `user,project,local` sources to load | documented + confirmed via `--help` | cli-reference.md, `-p --help` |
| `--add-dir` | Grants file read/edit access to extra directories; does **not** import most `.claude/` config from them (skills are a partial exception) | documented + confirmed via `--help` | cli-reference.md, `-p --help` |
| `--mcp-config` | Load MCP servers from JSON files/strings; with `-p`, waits for servers to connect (30s default `MCP_TIMEOUT`) before first turn (v2.1.221+) | documented + confirmed via `--help` | cli-reference.md, `-p --help` |
| `--strict-mcp-config` | Only use MCP servers from `--mcp-config`, ignore all other sources | documented + confirmed via `--help` | cli-reference.md, `-p --help` |

`--append-system-prompt`/`--system-prompt` etc. are recorded once on a conversation's first request and reused verbatim across `--resume`/`--continue` unless `--system-prompt-snapshot off` is passed — relevant if our runner wants to change instructions between resumed turns. Outside cloud sessions, `--bare` (or `CLAUDE_CODE_SIMPLE=1`) turns recording off by default.

## 7. Structured output (`--json-schema`)

Documented and confirmed via `--help` (both `claude --help` and `claude -p --help` list `--json-schema <schema>`, print-mode only). Example from docs:
```bash
claude -p "Extract the main function names from auth.py" \
  --output-format json \
  --json-schema '{"type":"object","properties":{"functions":{"type":"array","items":{"type":"string"}}},"required":["functions"]}'
```
Output metadata (session id, usage, etc.) still comes back in the normal JSON result envelope; the schema-validated payload is in a separate `structured_output` field. Invalid JSON Schema causes `claude` to exit with `Error: --json-schema is not a valid JSON Schema` plus the validator's diagnostic (documented; before v2.1.205 an invalid schema was silently ignored and returned unstructured text instead — good reason to pin/verify version behavior). The `format` keyword (e.g. `"format": "email"`) is accepted as an annotation only, not enforced.

Result-schema field name: `error_max_structured_output_retries` subtype on `SDKResultMessage` exists for when structured-output retries are exhausted (documented, agent-sdk/typescript.md), plus `structured_output_retry_exhausted` as a `terminal_reason` value.

## 8. Exit codes

Documented (headless.md, errors.md):
- `0`: success.
- Non-zero: run failed. Invalid flags produce a stderr message before the run starts; failures during the run (e.g. missing auth, an `error_during_execution` result) print the failure as the result on stdout, with a non-zero process exit.
- `143`: process received SIGTERM (documented) — in-flight turn is left unfinished, no result recorded for it.
- `1`: several specific documented cases use exit code 1 explicitly, e.g. a `--permission-prompt-tool` that isn't among connected MCP tools when a permission decision is first needed (errors.md).
- `137`: reserved/observed for install-script termination (SIGKILL, often OOM) — this is about `claude install`, not about a `-p` run itself; included for completeness since it appeared in errors.md, not confirmed as a `-p` runtime exit code.

We found no consolidated "exit code reference" table in errors.md, headless.md, or cli-reference.md enumerating all `claude -p` exit codes; the above are the only exit codes explicitly named in the fetched docs — **undocumented**: a full/generic exit-code table.

## 9. Hooks in headless/non-interactive mode

Documented (hooks.md):
- **Stop hook**: fires when the main agent finishes responding (not on user interrupt; API errors fire `StopFailure` instead). Input includes `stop_hook_active` (true if already continuing due to a prior Stop-hook block — check this to avoid infinite loops), `last_assistant_message`, `background_tasks`, `session_crons`. Decision control: `decision: "block"` (requires `reason`) prevents Claude from stopping; **Claude Code force-overrides and ends the turn after 8 consecutive blocks**. `hookSpecificOutput.additionalContext` gives non-blocking guidance that still loops through the same 8-block cap. Exit 2 blocking works the same as exit-0-with-JSON `decision:"block"` — stderr becomes the reason.
- **SessionStart hook**: fires on new session, `--resume`/`--continue`/`/resume`, `/clear`, compaction, or fork; matcher values `startup`/`resume`/`clear`/`compact`/`fork`. Can inject `additionalContext` (added before first prompt), and — specifically relevant to `-p` — `initialUserMessage`: "Applies in non-interactive mode with the `-p` flag, where it becomes the first turn even if no prompt is provided. If a prompt is provided, it follows as the next turn." Can also set `sessionTitle`, `watchPaths`, `reloadSkills`.
- **Setup hook** (`Setup` event, matchers `init`/`maintenance`): "Fires only when you launch Claude Code with `--init-only`, or with `--init` or `--maintenance` in non-interactive mode with the `-p` flag. It doesn't fire on normal startup." Cannot block; output discarded regardless of exit code; with `-p`, its stdout/stderr/exit code only surface via `hook_response` stream-json events when `--output-format stream-json --verbose` is used.
- General exit-code semantics (documented, hooks.md "Exit code output" section): exit 2 is the **only** universally-blocking code for events that can block; JSON output is read from stdout on every exit code, not just 0/2; exit 2's block "is the one outcome JSON can't override." A per-event table lists which events `Can block?` (`Stop`: yes, `SessionStart`: no — shows stderr to user only, doesn't block startup, `Setup`: no — exit code/stderr ignored entirely).
- `PermissionRequest` hooks still run for background subagents in `-p` mode even though there's no terminal to prompt; "if no hook returns a decision, it denies the tool call" (documented).
- `AskUserQuestion`/`ExitPlanMode` in `-p` mode are only offered when there's a permission host (SDK `canUseTool` callback or `--permission-prompt-tool`) to answer them (documented).

## 10. Sub-agents

Documented (sub-agents.md): Subagents are specialized assistants with their own context window, system prompt, tool access, and permissions; the main use case is keeping bulky exploration/search output out of the primary context. Scopes, by priority (highest to lowest): managed settings (org-wide) > `--agents` CLI flag JSON (session-only) > `.claude/agents/` (project) > `~/.claude/agents/` (user) > plugin `agents/` directory.

`--agents` JSON accepts a `prompt` field (equivalent to the markdown body of a file-based subagent) plus frontmatter fields: `description`, `tools`, `disallowedTools`, `model`, `permissionMode`, `mcpServers`, `hooks`, `maxTurns`, `skills`, `initialPrompt`, `memory`, `effort`, `background`, `omitClaudeMd`, `isolation`. Example:
```bash
claude --agents '{"code-reviewer":{"description":"...","prompt":"...","tools":["Read","Grep","Glob","Bash"],"model":"sonnet"}}'
```
Built-in subagents (`Explore`, `Plan`) are read-only (Write/Edit denied), inherit the parent conversation's model (capped at Opus on the Claude API) unless `CLAUDE_CODE_SUBAGENT_MODEL` forces one model onto every subagent.

In `-p`/stream-json output, subagent messages carry `parent_tool_use_id` pointing at the `Agent` tool call that spawned them; by default only `tool_use`/`tool_result` blocks are forwarded — `--forward-subagent-text` (or env var `CLAUDE_CODE_FORWARD_SUBAGENT_TEXT`) is needed to see the subagent's own text/thinking blocks in the stream (documented, headless.md and cli-reference.md).

## 11. Agent SDK (TypeScript and Python) as an alternative to shelling out

Documented (agent-sdk/overview.md, via cli-reference.md's framing): "The Agent SDK gives you the same tools, agent loop, and context management that power Claude Code. It's available as a CLI for scripts and CI/CD, or as Python and TypeScript packages for full programmatic control." `claude -p` itself is described as "using the Agent SDK via the CLI" — the CLI JSON output and the SDK's typed messages are two views of the same underlying protocol.

**TypeScript SDK** (agent-sdk/typescript.md): `query()` function (async generator over `SDKMessage` union types: `SDKAssistantMessage`, `SDKUserMessage`, `SDKResultMessage`, `SDKSystemMessage`, `SDKPartialAssistantMessage`, etc.), a `Query` object with methods (`interrupt()`, `getContextUsage()`, etc.), `tool()`/`createSdkMcpServer()` for custom in-process MCP tools, `listSessions()`/`getSessionMessages()`/`getSessionInfo()`/`renameSession()`/`tagSession()`. The `Options` type (confirmed present in the doc's table) includes `maxTurns`, `maxBudgetUsd`, `permissionMode`, `canUseTool` (custom permission callback), `allowedTools`/`disallowedTools`, `model`, `hooks`, `mcpServers`, `settingSources`, `resume`/`sessionId`/`forkSession`/`continue`, `outputFormat`, `systemPrompt`, `agents`, `sandbox`, and dozens more — this is a strict superset of the CLI flags in typed form, giving programmatic access to things like `canUseTool` callbacks that the bare CLI can't do without an MCP permission-prompt-tool.

**Python SDK** (agent-sdk/python.md): package `claude-agent-sdk`, install via `pip install claude-agent-sdk` inside a venv — the doc itself warns "On recent Debian, Ubuntu, and Homebrew Python installs, running `pip install` against system Python fails with `error: externally-managed-environment`," which matches the PEP 668 lock already confirmed in this container. Two interaction styles: `query()` (new session per call, no memory unless `continue_conversation=True`/`resume` passed, no mid-run interrupts, supports streaming input and hooks) vs. `ClaudeSDKClient` (persistent session, manual connection control, supports `interrupt()`). Result/message types mirror the TypeScript ones: `ResultMessage`, `SystemMessage`, `AssistantMessage`, `UserMessage`, plus SDK-specific `TaskStartedMessage`/`TaskProgressMessage`/`TaskNotificationMessage`/`RateLimitEvent`.

Given this container has Node 18.19 (no confirmed npm/global install check performed here) and Python 3.12 with pip blocked by PEP 668 and no venv/ensurepip, the **TypeScript SDK is more readily usable in this environment** than the Python SDK unless a venv workaround (e.g. `pipx`, `--break-system-packages`, or a container-level venv install) is set up first — this is an environment-fact inference, not something stated in the docs themselves.

## 12. Preventing a driven session from triggering the repo's own hooks

Documented (hooks.md, "Security considerations" section, and headless.md "bare mode" section):
- **`--bare`**: "A hook in a teammate's `~/.claude` or an MCP server in the project's `.mcp.json` won't run, because bare mode never reads them." This is the primary documented mechanism, and is explicitly recommended by the docs for CI/scripted use ("the recommended mode for scripted and SDK calls, and will become the default for `-p` in a future release").
- **`--settings '{"disableAllHooks": true}'`**: hooks.md's direct guidance: "Before you script `claude -p` over a repository you didn't write, review its `.claude/` settings files, start with `--bare`, or turn hooks off for that run with `--settings '{"disableAllHooks": true}'`." This disables hooks specifically while (implicitly) still loading other project config, unlike `--bare` which skips much more.
- **`--safe-mode`**: disables CLAUDE.md, skills, plugins, hooks, MCP servers, custom commands/agents, output styles, workflows, custom themes/keybindings, status line/file-suggestion commands, LSP servers, auto memory — described as for troubleshooting a broken config rather than for security isolation, but functionally also prevents repo hooks from running. Differs from `--bare`: "Auth, model selection, built-in tools, and permissions work normally," and managed/policy settings still apply.
- **`--restricted`** additionally "ignores user, project and local settings files (managed settings and `--settings` still apply)" and confines file tools to working directories — relevant if we also want to stop a driven session from reading arbitrary project settings, not just hooks.
- **`--setting-sources`**: comma list of `user,project,local` to load — omitting `project`/`local` would also skip a project's `.claude/settings.json` (and therefore its hooks), as an alternative to `--bare`/`disableAllHooks`.

Without any of these, `-p` runs a project's `.claude/settings.json` hooks and connects its `.mcp.json` servers "even in a folder you've never trusted," and shows no trust dialog and no per-server approval prompt in `-p` mode (documented, headless.md) — this is the key risk our runner design needs to account for when driving Claude Code over an arbitrary/untrusted checkout.

## Open questions this material does not answer

- Whether `--max-turns` is actually accepted by the installed v2.1.278 binary — it's documented but absent from both `--help` outputs, and we were told not to start a real `-p` run to test it.
- Whether `--permission-prompt-tool` is accepted by v2.1.278 for the same reason (documented, absent from `--help`).
- No consolidated/generic exit-code reference table exists in the fetched docs; we only found specific documented codes (0, 143, 1 in one named scenario, 137 for `claude install` specifically). What exit code corresponds to e.g. `error_max_turns` or `error_max_budget_usd` results specifically was not stated anywhere we found.
- Whether `--bare` mode is compatible with `--resume`/`--continue` sessions that were originally started without `--bare` (i.e., does switching bare-ness mid-session-history cause any documented issue) — not addressed in the fetched pages.
- Node 18.19 compatibility with the current `@anthropic-ai/claude-agent-sdk` TypeScript package's minimum Node version requirement was not checked (agent-sdk/typescript.md's Installation section wasn't captured in the fetched excerpt) — needs a follow-up doc fetch or `npm view` check.
- Exact behavior/precedence when both `--bare` and `--settings` (with hooks defined inline) are combined — is `disableAllHooks` still meaningful under `--bare`, or redundant — not explicitly stated.
- Whether `--json-schema` structured output composes with `--output-format stream-json` (docs only show it paired with `--output-format json`).
