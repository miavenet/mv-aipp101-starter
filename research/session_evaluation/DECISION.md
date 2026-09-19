# Decision: session evaluation at the auto-compact point

Date: 2026-09-19. Status: **proposed, not built.** Reasoning is in [`ANALYSIS.md`](ANALYSIS.md).

## Decision

**Build it, as an adviser that never acts on its own, in three phases, starting in log-only mode.**

It is worth building because the evidence is consistent that a session on a wrong path rarely
recovers, that the session's own model will not notice, and that a fresh session carrying the right
artefacts beats both continuing and a cold restart. It must stay advisory because a hook cannot
start a session, because no published thresholds transfer to our setup, and because a false alarm
destroys useful context.

## Design

### Evaluate at `PreCompact`, deliver at `SessionStart`, never block

- A **blocking command hook on `PreCompact`, matcher `auto`** computes a scorecard from
  `hooks.jsonl` and git, writes it to `.claude/hook-logs/sessions/<id>/eval.json`, and exits 0.
- It does **not** block compaction. Blocking fails the request when compaction was recovering from a
  context-limit error, and the payload does not say which case it is. The raw record stays on disk
  either way, so nothing is lost by letting compaction proceed.
- A **`SessionStart` hook, matcher `compact`**, injects a short ground-truth note as
  `additionalContext`: files touched, git state, test status, approaches already ruled out. This
  repairs the part of a summary that is measurably weakest, whatever the verdict.
- **The statusline shows the verdict** (for example `eval: HANDOFF`), because `PreCompact` cannot
  message the user and we already own the statusline.

### Two layers, cheap first

1. **Scorecard (free, under a second).** Identical-call streak, same-error streak, A-B-A-B
   alternation, tool error density and its trend, compactions so far, user corrections and mid-turn
   interruptions, edit churn paired with net diff, and verified progress (commits, tests newly
   passing) per dollar since the last compaction. Session length and context % are recorded but
   never scored.
2. **Judge (a few cents, only when the scorecard is amber or red, or on the second compaction).**
   `claude -p` with a small model, given a digest: the original request, the user's prompts, the
   last N tool calls with errors, `git diff --stat`, and test results. It returns JSON with progress
   (`healthy`, `stalled`, `wrong_path`), a confidence, and evidence. The prompt follows Gemini CLI's
   loop judge, including its list of things that are not loops. It acts only at high confidence.
   The judge's own `claude -p` run must not trigger the hooks again.

### Verdict to action

| Progress | Context | Recommendation |
|---|---|---|
| Healthy | First compaction | **Compact and continue.** The ground-truth note is injected |
| Healthy | Second compaction or later | **Handoff and fresh session.** Avoids summary on top of summary |
| Stalled or wrong path, but the work so far is useful | Any | **Fresh session with an artefact handoff**, or `/rewind` to the last good checkpoint |
| Wrong path and the plan itself was wrong | Any | **Revert with git and restart from a better spec**, carrying only the ruled-out approaches |

For every verdict except the first, the hook writes a ready handoff file built from git and the
logs, so acting on the advice is one command. A bare restart with nothing carried over is never
recommended: it gained 0.2 points in the one study that measured it.

### Starting thresholds (to be calibrated, not trusted)

Identical calls 4, same error 3, alternation over 6 steps, user corrections more than 2 on one
issue, compactions 2. These are the values shipped by OpenHands, Gemini CLI and Cline, and
Anthropic's guidance.

## Phases

1. **Shadow scorecard.** Compute and log the scorecard at every compaction and at session end.
   No advice shown. Record what you actually did next (continued, cleared, rewound) as the label.
   This also fixes the absence of any observed `auto` compaction in our data.
2. **Ground-truth note and handoff generator.** The `SessionStart` injection, the handoff file, the
   statusline badge. Useful even if the verdicts turn out to be noisy.
3. **Judge.** Added only after phase 1 shows the cheap signals alone are not enough.

## What we will not do

- Block auto-compaction.
- Ask the in-session model whether it is on track.
- Score on session length, token count or context % alone.
- Rely on the transcript JSONL as the primary input. Its format is not a stable contract; our own
  hook log is.
- Build the handoff from the compaction summary or the model's narrative.

## Interaction with the 40% auto-compact setting

`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=40` on a 1M window means compaction near 400k tokens. That gives
more evaluation points and keeps the model out of the most degraded part of the window. It also
means more compactions per long session, so the "second compaction means handoff" rule will fire
sooner. That is the intended behaviour, not a conflict, but it is the first threshold to revisit
after phase 1.

## What would change this decision

- Phase 1 data showing the cheap signals never separate good sessions from bad ones.
- A Claude Code release that lets hooks start sessions, or that exposes context usage and the
  compaction cause in the `PreCompact` payload. The second would make blocking safe.
- A published controlled comparison of handoff against compaction. None exists today.
