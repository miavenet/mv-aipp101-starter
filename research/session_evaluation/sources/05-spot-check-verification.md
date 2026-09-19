# Spot-check of the load-bearing citations

Done 2026-09-19 by the main session, independently of the research agents. The agents read pages
through a fetch tool that returns a small model's digest, so their "quotes" are second-hand. For
the claims the decision rests on, the primary page was downloaded with `curl` and read directly.

| Claim used in the analysis | Source checked | Result |
|---|---|---|
| A `PreCompact` hook can block compaction with exit code 2 or `"decision": "block"` | raw `https://code.claude.com/docs/en/hooks.md`, section "PreCompact" | Confirmed verbatim |
| Blocking an auto-compaction that fired to recover from a context-limit error makes the request fail | same | Confirmed verbatim |
| `PreCompact` and `PostCompact` discard `systemMessage` and `continue`; `PostCompact` has "no decision control" | same | Confirmed verbatim |
| `SessionStart` (`source` includes `compact`) can return `additionalContext` | same, "SessionStart decision control" | Confirmed verbatim |
| Fail-Fast, Restart-Smart: restart with the prior diff as optional overlay lifts SWE-bench Verified 66.6% to 71.8%; cold restart reaches only 66.8%; monitor is 0.6B; 14.6%-20.4% token saving at 5% false positives | arXiv abstract 2608.03222 | Confirmed from abstract. The "54.9% of failing runs hold recoverable progress" and "summaries anchor the new run" points are from the paper body and were NOT re-checked |
| BAGEN: frontier agents are over-optimistic and keep spending on tasks unlikely to succeed; early stop saves 28-64% of tokens on failed trajectories | arXiv abstract 2606.00198 | Confirmed from abstract. The ">70% predicted feasibility after 60% of budget" and AUROC/kappa figures are from the body and were NOT re-checked |
| Context compression increases blocked actions, repeated exploration and run-to-run instability; evaluate at the compaction boundary (TRACE) | arXiv abstract 2608.06503 | Confirmed from abstract. The authors call it a "preliminary empirical study" |
| Multi-turn: average 39% drop; "when LLMs take a wrong turn in a conversation, they get lost and do not recover" | arXiv abstract 2505.06120 | Confirmed from abstract. The 95.1% recovery from consolidating into one fresh prompt is from the body and was NOT re-checked |
| Observation masking halves cost and matches LLM summarisation on solve rate | arXiv abstract 2508.21433 | Confirmed from abstract. The "summarisation lengthens runs by about 15%" figure is from the body and was NOT re-checked |

Anything marked NOT re-checked should be treated as probable, not certain, until someone reads the PDF.

## Practitioner claims (file 02), checked the same way

| Claim | Source checked | Result |
|---|---|---|
| "If you've corrected Claude more than twice on the same issue in one session… Run `/clear` and start fresh" | raw `https://code.claude.com/docs/en/best-practices.md`, line 376 | Confirmed verbatim |
| Amp: "We have removed compaction from Amp and replaced it with… Handoff"; "stacking summary on top of summary" | `https://ampcode.com/news/handoff` (23 Oct 2025) | Confirmed verbatim |
| Codex warns after compaction: "Long threads and multiple compactions can cause the model to be less accurate. Start a new thread when possible…" | `codex-rs/core/src/compact.rs` on `main`, line 409 | Confirmed verbatim |
| OpenHands StuckDetector: 4 identical action/observation pairs, same action with errors, monologue, a pattern over the last six steps, a context-window error loop over 10 | `openhands/controller/stuck.py` at tag 0.50.0 | Scenario list and the 4, 6 and 10 window sizes confirmed in source. The "3 same-error repeats" figure was not individually confirmed |
| Gemini CLI: tool-call loop threshold 5, content chunk 50 chars repeated 10 times, LLM check after 30 turns, confidence threshold 0.9 | `packages/core/src/services/loopDetectionService.ts` on `main` | Constants confirmed in source |
