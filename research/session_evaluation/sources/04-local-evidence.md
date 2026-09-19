# Local evidence: what is actually observable at the compaction point

Collected 2026-09-19 from this repo's own hook logger (`.claude/hooks/log-hook.py`) and the
session transcript, Claude Code v2.1.278. This is first-hand observation, not documentation.
One manual `/compact` happened in the observed session. No auto-compaction has been observed yet,
so `trigger: "auto"` behaviour is unconfirmed locally.

## Order of events around a compaction (observed)

| seq | event | time (UTC) | note |
|---|---|---|---|
| 128 | `PreCompact` | 21:02:56.977 | fires before the summary is generated |
| 130 | `SessionStart` (`source: "compact"`) | 21:04:22.634 | 85.7 s later, which is the summarisation time |
| 131 | `PostCompact` | 21:04:22.660 | 26 ms after SessionStart |

The transcript's `compact_boundary` entry reports `durationMs: 85388`, matching the gap.

## Payloads (observed keys)

- **PreCompact:** `session_id`, `transcript_path`, `cwd`, `scratchpad_dir`, `prompt_id`,
  `hook_event_name`, `trigger` (`"manual"` observed), `custom_instructions` (`null` observed).
- **SessionStart:** same common keys plus `source: "compact"` and `model`.
- **PostCompact:** common keys plus `trigger` and **`compact_summary`**, the full summary text
  (16,034 characters here).

None of these payloads carry token counts, cost, error counts or any quality signal. Everything an
evaluator needs must come from the transcript, from the hook log, or from the statusline snapshot.

## What the statusline snapshot adds at PreCompact (observed)

`ctx_tokens 275,684` of a `1,000,000` window (28%), `cost_usd 16.87`, `api_duration_ms 1,211,466`,
`lines_added 2165`, `lines_removed 201`, `cache_hit_ratio 0.963`, `rate_5h_pct 14`.
The snapshot was 24.9 s old at that moment (`age_ms`), so it lags by up to one assistant message.

## What the transcript JSONL contains (observed, format is not a documented contract)

854 lines at the time of inspection. Entry types useful to an evaluator:

- `assistant` (217): every model message with `message.usage` (input, cache write, cache read,
  output tokens) and the tool calls it made.
- `user` (129): prompts and `tool_result` blocks with an `is_error` flag (94 ok, 3 errors here).
- `system` / `turn_duration` (27): per-turn wall time.
- `system` / `compact_boundary` (1): `compactMetadata` with `trigger`, `preTokens 275,766`,
  `postTokens 17,390`, `cumulativeDroppedTokens 258,376`, `durationMs`, and which messages were
  preserved verbatim.
- `user` with `isCompactSummary` (1): the summary as injected into the new context.
- `file-history-snapshot` / `file-history-delta` (63): the checkpoint data behind `/rewind`.
- `queue-operation` (12): messages the user sent mid-turn, a candidate "user had to intervene" signal.

## What the hook log already gives us per session (no transcript parsing needed)

Counts by event, every tool call with input, result summary, native `duration_ms`, failures
(`PostToolUseFailure`), subagent starts and stops, user prompts, notifications (permission waits),
and turn durations. So most cheap counters (tool error rate, repeated identical calls, edits per
file, prompts per turn, cost and context deltas between prompts) can be computed from
`hooks.jsonl` alone, filtered by `session_id`.

## Logger shortcoming found while collecting this

`SessionStart` with `source: "compact"` resets the logger's per-session start time
(`since_session_start_s` went to 0.0 at seq 130). For session evaluation the original start must
be kept, and compactions should be counted instead. To be fixed if we build the evaluator.
