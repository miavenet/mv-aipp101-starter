# Analysis: can we evaluate a session at the auto-compact point?

Date: 2026-09-19. Inputs: the five files in [`sources/`](sources/). Source IDs below (for example
`01:S12`) mean "file 01, source S12". Claims the decision rests on were re-checked against the
primary pages; see [`sources/05-spot-check-verification.md`](sources/05-spot-check-verification.md).

## The question

When Claude Code is about to auto-compact, can we tell whether the session has gone down a wrong
path, and choose between:

- **(a)** compact and continue,
- **(b)** write a handoff and start a fresh session,
- **(c)** discard the work and start over?

## Short answer

Yes, it is feasible, with three limits:

1. Nobody has published this exact thing. No paper or product evaluates the three-way choice at the
   compaction boundary (01: Gaps 1, 2, 5; 02: synthesis). We would be assembling proven parts.
2. A hook can advise but cannot act. It cannot run `/clear` or open a new session (03). The human
   makes the call; the tooling's job is to make the right call obvious and cheap.
3. What can be measured is "no progress", not "wrong path". Every shipped detector is syntactic
   (02:S12 to S16). "Wrong path" needs a judge that knows the goal, and it must not be the session's
   own model.

## What the evidence says

### 1. The compaction point is a good place to look, and a bad place to be

- Wrong turns stick. Multi-turn performance drops 39% on average, and "when LLMs take a wrong turn
  in a conversation, they get lost and do not recover" (01:S1, verified).
- The model's own mistakes in context cause more mistakes (01:S2), and long context degrades
  performance on its own (01:S3 to S7). Anthropic says the same from practice: "the model is at its
  least intelligent point when compacting" (02:S3).
- Compaction is lossy in a specific way. It increases "blocked actions, repeated exploration, and
  instability across runs" (01:S9, verified). Summaries are weakest on which files were touched:
  2.19 to 2.45 out of 5 in Factory's measurement (02:S9).
- Summarising may hide the very signs that the agent should stop (01:S8). So the evaluation must use
  the raw record, not the summary.

**Consequence for us:** the raw record survives compaction on disk. Compaction only clears the
model's context; `hooks.jsonl` and the transcript file keep everything (04). So we do not need to
block compaction in order to evaluate the raw trajectory.

### 2. The session must not judge itself

- Frontier agents "continue spending on tasks that are unlikely to succeed, instead of alerting the
  user early" (01:S16 BAGEN, verified). Self-correction without outside feedback does not work
  (01:S17). Anthropic: agents "tend to respond by confidently praising the work" (02:S6).
- External judges do work. Small monitors predict failure from a short window of steps (01:S12,
  verified). Gemini CLI ships an LLM loop judge that acts at confidence 0.9 or higher (02:S13,
  constants verified in source). Claude Code's own `/goal` uses a fresh small model per turn (02:S5).

**Consequence:** any "is this on track?" call goes to a separate, fresh model, fed a digest plus
executable evidence (tests, git), never to the in-session model.

### 3. How you restart matters more than whether you restart

- A cold restart barely helps: 66.6% to 66.8% on SWE-bench Verified. A fresh session that is offered
  the previous diff as an optional overlay reaches 71.8% (01:S12, verified).
- The same paper reports that 54.9% of failing runs contain recoverable progress, and that textual
  summaries anchor the new run on the old approach. The second point is asserted, not ablated, and I
  did not re-check either figure in the paper body.
- Practice agrees: Amp removed compaction in favour of handoff because compaction means "stacking
  summary on top of summary" (02:S8, verified). Codex warns after every compaction to "start a new
  thread when possible" (02:S10, verified). Anthropic's one numeric rule: corrected more than twice
  on the same issue, then `/clear` and restart with a better prompt (02:S2, verified).

**Consequence:** option (c), a bare restart, is rarely right. Option (b) should carry artefacts
(diff, test status, files touched, approaches already ruled out), taken from git and the logs rather
than from the model's narrative. A fourth option belongs on the list: `/rewind` to the last good
checkpoint (02:S3).

### 4. Which signals to trust

| Signal | Verdict | Why |
|---|---|---|
| Identical tool call repeated (4 to 5 times) | Use | Shipped in OpenHands, Gemini CLI, Cline (02:S12, S13, verified) |
| Same call, same error (3 times) | Use | Shipped in OpenHands |
| A-B-A-B alternation over 6 steps | Use | Shipped in OpenHands |
| Tool error density, rising | Use | Own errors in context predict more errors (01:S2) |
| Compactions so far (2 or more) | Use | Amp, Codex, Cursor all point at it (02:S8, S10) |
| User corrections on one issue (more than 2) | Use | Anthropic guidance (02:S2). Mid-turn interruptions are in the transcript (04) |
| Verified progress per dollar since last compaction | Use | Tests newly passing, commits, plan items done. Endorsed by three vendors, no thresholds (02) |
| Edit churn on one file | Use with care | Must be paired with net diff, or normal iterative editing false-alarms (02:S13 carve-outs) |
| Editing before reading, few validation steps | Use as context | Correlates with failure (rho -0.78 and +0.50, 01:S18, S19), not re-checked |
| Session length, token count, context % alone | Do not use | Reverses sign once task difficulty is controlled (01:S19) |
| The agent's own opinion | Do not use | See section 2 |

All of the "Use" rows are computable from data we already log. A one-pass script over this
session's `hooks.jsonl` produced: 57 main-agent tool calls, longest identical-call streak 1, tool
failure rate 1.8%, at most 2 edits to any file, 21 user prompts, 1 compaction, $30.98. That is a
healthy profile, which matches how the session actually went.

### 5. What the platform lets a hook do (03, verified against the raw docs)

| Need | Possible? | How |
|---|---|---|
| Run an evaluator before the summary is written | Yes | `PreCompact` hook, matcher `auto` |
| Read the raw session | Yes | Our `hooks.jsonl` (format we own), and `transcript_path` (format not a stable contract) |
| Stop the compaction | Yes, but risky | Exit code 2. If the compaction was recovering from a context-limit error, "the current request fails". The payload does not say which case it is |
| Tell the model the verdict afterwards | Yes | `SessionStart` hook with `source: "compact"` returns `additionalContext` |
| Tell the user | Not from `PreCompact` | Its `systemMessage` is discarded. Our statusline can show a badge instead, and a `Notification`-style alert is possible |
| Use an LLM hook (`prompt` or `agent` type) at compaction | No | Only `command`, `http`, `mcp_tool`. A command hook can still call `claude -p` |
| Start the new session or run `/clear` | No | The human does it |

Timing observed locally: `SessionStart` (`compact`) arrived 85.7 s after `PreCompact` (04). An
LLM judge launched at `PreCompact` has roughly that long to finish before the verdict is wanted.

## Open risks

- **No ground truth.** Thresholds are harness-specific and model-specific (01: Gap 6). Anthropic
  found resets were essential for one model and unnecessary for the next (02:S6). We need a
  log-only period before trusting any alarm.
- **False alarms cost more than misses here.** Killing a good session loses real context; the
  restart study runs at a 5% to 25% false-positive budget (01:S12). The tool should advise, never
  act on its own.
- **Interactive sessions are unstudied.** Almost all evidence is from unattended benchmark runs
  (01: Gap 4). A human steering the session changes both the failure modes and the signals.
- **A handoff written by a lost session can carry the wrong path with it** (01: Gap 3). This is the
  reason to build the handoff from git and logs, and to list ruled-out approaches as facts.
- **Reasoning models may need restarts less** than the 2025 literature suggests (01: Gap 7).
