# 02 — Practitioner / industry state of the art: evaluating a session at the compaction boundary

Research date: 2026-09-19. Every entry below was fetched in this task (WebFetch, or `curl` of raw source). Quotes marked **[raw]** were additionally string-matched against the raw page/source text; other quotes came through WebFetch's extraction model and should be treated as near-verbatim. Source-code constants were read directly from the raw files.

Question: at the moment Claude Code is about to auto-compact, can we evaluate whether the session went down a wrong path and choose between (a) compact and continue, (b) handoff + fresh session, (c) discard and restart — and on what measurable signals?

---

## Key takeaways for the question

1. **The hook point exists and can veto.** Claude Code's `PreCompact` hook fires with `trigger: "auto"`, receives `transcript_path`, and "Exit with code 2 to block compaction"; if compaction was proactive "Claude Code skips it and the conversation continues uncompacted", but if it was recovering from a context-limit error "the current request fails". `PostCompact` receives `compact_summary`; `SessionStart` has a `compact` matcher. So a pre-compaction evaluator is implementable today; it has no documented context-usage field and must compute everything from the transcript JSONL. [S4]
2. **Anthropic's own decision table already maps to the three options** (continue / rewind / compact / clear+brief / subagent): rewind when "Claude went down a wrong path"; compact when "the session is bloated with stale debugging/exploration"; clear with a distilled brief for a new task. It gives no numeric thresholds. [S3]
3. **The one explicit numeric rule from Anthropic is user-correction count**: "If you've corrected Claude more than twice on the same issue in one session, the context is cluttered with failed approaches. Run `/clear` and start fresh…A clean session with a better prompt almost always outperforms a long session with accumulated corrections." (Opinion/experience, no data.) [S2]
4. **Auto-compaction happens at the worst moment**: "due to context rot, the model is at its least intelligent point when compacting" and "bad compacts can happen when the model can't predict the direction your work is going." This argues for having a *separate, fresh* evaluator judge the session rather than the in-session model. [S3]
5. **Self-evaluation is unreliable; use a separate judge.** "When asked to evaluate work they've produced, agents tend to respond by confidently praising the work"; separating generator from evaluator "proves to be a strong lever". Claude Code `/goal` already uses a fresh small model per turn returning met / not yet / impossible. [S6][S5]
6. **Reset-vs-compact is model-dependent.** With Sonnet 4.5 "compaction alone wasn't sufficient… so context resets became essential"; but "Opus 4.5 largely removed that behavior on its own, so I was able to drop context resets from this harness entirely." Any policy should be re-validated per model. [S6]
7. **Two vendors publicly steer away from repeated compaction.** Amp: "We have removed compaction from Amp and replaced it with… Handoff"; compaction "encourages long, meandering threads… stacking summary on top of summary." Codex source emits after every compaction: "Long threads and multiple compactions can cause the model to be less accurate. Start a new thread when possible". => **number of prior compactions** is a first-class signal. [S8][S10]
8. **Compaction is measurably lossy specifically on artifacts.** Factory's probe-based eval scored all three summarizers 2.19–2.45/5 on "artifact trail" (which files were touched) while overall 3.35–3.70; "the right optimization target is not tokens per request. It is tokens per task." A handoff must therefore get file lists / git state from ground truth (git, transcript), not from the summarizer. [S9]
9. **Implemented stuck detectors are all cheap, local and syntactic**: N identical action+observation pairs (OpenHands 4), same action + error (OpenHands 3), ABAB alternation over 6 steps, agent monologue (3), identical tool call streak (Gemini CLI 5, Cline soft 3/hard 5, Goose configurable), 50-char content chunk repeated 10x, and — in Gemini CLI — an LLM judge after 30 turns with 0.9 confidence. None of them measures "wrong path"; they measure "no progress". [S12–S16]
10. **The best available definition of "unproductive" is two-part**: "a repetitive pattern over at least 5 consecutive model actions" AND "NO net change or forward progress toward the user's goal" — with explicit non-loop carve-outs (cross-file batch ops, incremental same-file edits, retry with variation, re-running a build after code changes). Any edit-churn / repeated-command signal must respect those carve-outs or it will false-positive. [S13]
11. **"Discard and restart" is practised with git as the rollback unit and a budget as the gate**: Ralph ("Is it easier to do a `git reset --hard` and to kick Ralph back off again?"), Cursor ("revert the changes and refine the plan"), Anthropic long-running harness ("use git to revert bad code changes and recover working states"), SWE-agent's retry loop (`max_attempts`, `accept_score`, `min_budget_for_new_attempt`, `cost_limit`). Restart is cheap only when there is a durable spec/plan outside the context. [S11][S17][S7][S15]
12. **Handoff content is converging**: goal + success criteria, approach and decisions *with why*, ruled-out approaches ("already tried, failed"), current failure, verification done and *not* done, git state (branch/commit/push), numbered next steps, references by path not copied text. Evidence for "handoff beats compact" is anecdotal or vendor assertion; nobody fetched here published a controlled A/B. [S7][S8][S10][S18][S19][S20][S21]

---

## Sources

### Anthropic

#### S1. Effective context engineering for AI agents
- Anthropic Applied AI team · 2025-09-29 · https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Claims:
  - Context rot: "as the number of tokens in the context window increases, the model's ability to accurately recall information from that context decreases."
  - Claude Code compaction: "we implement this by passing the message history to the model to summarize and compress the most critical details. The model preserves architectural decisions, unresolved bugs, and implementation details while discarding redundant tool outputs or messages. The agent can then continue with this compressed context plus the five most recently accessed files."
  - "Overly aggressive compaction can result in the loss of subtle but critical context whose importance only becomes apparent later."
  - Tuning: "Start by maximizing recall to ensure your compaction prompt captures every relevant piece of information from the trace, then iterate to improve precision".
  - "One of the safest lightest touch forms of compaction is tool result clearing".
  - Technique choice: "Compaction maintains conversational flow for tasks requiring extensive back-and-forth; Note-taking excels for iterative development with clear milestones; Multi-agent architectures handle complex research and analysis".
- Evidence: opinion/engineering experience; no measurements in the post.
- Relevance: defines what compaction keeps; says nothing about evaluating trajectory quality before compaction — that gap is the question.

#### S2. Claude Code docs — Best practices
- Anthropic · living doc, fetched 2026-09-19 · https://code.claude.com/docs/en/best-practices
- Claims (verbatim from page):
  - "Claude's context window fills up fast, and performance degrades as it fills."
  - "If you've corrected Claude more than twice on the same issue in one session, the context is cluttered with failed approaches. Run `/clear` and start fresh with a more specific prompt that incorporates what you learned. A clean session with a better prompt almost always outperforms a long session with accumulated corrections."
  - Failure patterns: "The kitchen sink session", "Correcting over and over… Fix: After two failed corrections, `/clear` and write a better initial prompt", "The infinite exploration".
  - "Customize compaction behavior in CLAUDE.md with instructions like \"When compacting, always preserve the full list of modified files and any test commands\"".
  - Spec-then-fresh-session: "Once the spec is complete, start a fresh session to execute it."
  - Verification: "Give Claude a check it can run: tests, a build, a screenshot to compare." A Stop hook gate is overridden "after 8 consecutive blocks."
  - Adversarial review: "A reviewer running in a fresh subagent context sees only the diff and the criteria you give it, not the reasoning that produced the change"; caveat: "A reviewer prompted to find gaps will usually report some, even when the work is sound".
  - Counterpoint: "Sometimes you *should* let context accumulate because you're deep in one complex problem and the history is valuable."
- Evidence: vendor guidance ("patterns that have proven effective across Anthropic's internal teams"); no numbers.
- Relevance: supplies the only explicit count-based rule (>2 corrections on same issue → clear) and the false-positive warning for LLM reviewers.

#### S3. Using Claude Code: session management and 1M context
- Thariq Shihipar (Anthropic) · 2026-04-15 · https://claude.com/blog/using-claude-code-session-management-and-1m-context
- Claims:
  - Decision table: Continue — "Everything in the window is still load-bearing; don't pay to rebuild it." Rewind — when "Claude went down a wrong path": "Keep the useful file reads, drop the failed attempt, re-prompt with what you learned." Clear — "Zero rot; you control exactly what carries forward." Compact — when "the session is bloated with stale debugging/exploration". Subagent — "Next step will generate lots of output you'll only need the conclusion from".
  - **[raw]** "Rewind is often the better approach to correction… the better move may be to rewind to just after the file reads, and re-prompt with what you learned. \"Don't use approach A, the foo module doesn't expose that—go straight to B.\""
  - **[raw]** "bad compacts can happen when the model can't predict the direction your work is going… This is particularly difficult, because due to context rot, the model is at its least intelligent point when compacting. With one million context, you have more time to /compact proactively with a description of what you want to do."
  - Brief before clearing: constraints, relevant files, ruled-out approaches.
- Evidence: practitioner guidance from the product team; no measurements.
- Relevance: closest official statement of the a/b/c decision. Introduces a 4th option the question omits: **rewind to the last good checkpoint and summarize from there** (partial discard).

#### S4. Claude Code docs — Hooks reference (PreCompact / PostCompact) and Checkpointing
- Anthropic · fetched 2026-09-19 · https://code.claude.com/docs/en/hooks (raw: /docs/en/hooks.md) · https://code.claude.com/docs/en/checkpointing
- Claims **[raw]**:
  - PreCompact matcher `auto` = "Auto-compact when the conversation reaches the auto-compact window".
  - "Exit with code 2 to block compaction… You can also block by returning JSON with `\"decision\": \"block\"`."
  - "If compaction was triggered proactively before the context limit, Claude Code skips it and the conversation continues uncompacted. If compaction was triggered to recover from a context-limit error already returned by the API, the underlying error surfaces and the current request fails."
  - Input: common fields (`session_id`, `transcript_path`, `cwd`) + `trigger`, `custom_instructions` (null for auto). "Claude Code discards a PreCompact hook's `systemMessage` and `continue` fields."
  - PostCompact receives `compact_summary`; "PostCompact hooks have no decision control."
  - Checkpointing: rewind menu offers restore code/conversation and "Summarize from here" / "Summarize up to here"; "Checkpointing does not track files modified by Bash commands"; subagent edits usually not restored; "Summarizing doesn't change files on disk, and the original messages stay in the session transcript".
- Evidence: product documentation (authoritative for mechanics).
- Relevance: the mechanical substrate. Note a PreCompact hook cannot inject a message to the model (systemMessage discarded) — so the evaluator's verdict must be delivered by side channel (file, PostCompact/SessionStart(compact) hook, or blocking and notifying the user).

#### S5. Claude Code docs — /goal
- Anthropic · fetched 2026-09-19 · https://code.claude.com/docs/en/goal
- Claims: "After each turn, a small fast model checks whether the condition holds." Verdicts: "Not yet met", "Met", "Impossible". "completion is decided by a fresh model rather than the one doing the work." "If Claude keeps answering the evaluator without making progress (no tool use for several turns in a row), Claude Code stops the loop". Goal is cleared on "A context overflow that auto-compaction couldn't clear". Status shows turns evaluated and token spend. The evaluator "doesn't run commands or read files independently".
- Evidence: product docs.
- Relevance: an in-product precedent for an external LLM judge with an "impossible" verdict and a no-progress stop rule; also gives per-goal turn count and token spend as ready-made denominators.

#### S6. Harness design for long-running application development
- Prithvi Rajasekaran (Anthropic Labs) · 2026-03-24 · https://www.anthropic.com/engineering/harness-design-long-running-apps
- Claims:
  - "Some models also exhibit 'context anxiety,' in which they begin wrapping up work prematurely as they approach what they believe is their context limit."
  - "Context resets—clearing the context window entirely and starting a fresh agent, combined with a structured handoff that carries the previous agent's state and the next steps—addresses both these issues." "While compaction preserves continuity, it doesn't give the agent a clean slate". Cost: "adds orchestration complexity, token overhead, and latency".
  - **[raw]** "Claude Sonnet 4.5 exhibited context anxiety strongly enough that compaction alone wasn't sufficient".
  - **[raw]** "Opus 4.5 largely removed that behavior on its own, so I was able to drop context resets from this harness entirely. The agents were run as one continuous session across the whole build, with the Claude Agent SDK's automatic compaction handling context growth".
  - **[raw]** Self-eval: agents "respond by confidently praising the work—even when, to a human observer, the quality is obviously mediocre." Generator/evaluator split; "sprint contract: agreeing on what 'done' looked like for that chunk of work before any code was written."
  - Costs: solo 20 min/$9 vs full harness 6 hr/$200 (retro game maker); DAW 3 hr 50 min/$124.70.
- Evidence: single-author case study with concrete runs; qualitative comparison, not a controlled benchmark.
- Relevance: strongest first-party evidence that (b) vs (a) depends on the model, and that "premature wrap-up near the limit" is itself a detectable wrong-path symptom.

#### S7. Effective harnesses for long-running agents
- Justin Young (Anthropic) · 2025-11-26 · https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- Claims: **[raw]** "However, compaction isn't sufficient. Out of the box, even a frontier coding model like Opus 4.5 running on the Claude Agent SDK in a loop across multiple context windows will fall short of building a production-quality web app". Failure modes: "the agent tended to try to do too much at once"; a later instance would "declare the job done". Remedies: feature list file with items "marked as 'failing'", "claude-progress.txt", "Read the git logs and progress files to get up to speed", "commit its progress to git with descriptive commit messages", "use git to revert bad code changes and recover working states", "leave the environment in a clean state".
- Evidence: engineering case study.
- Relevance: gives a measurable progress denominator (features flipped failing→passing per context window) and the ingredients of a machine-readable handoff.

#### S8a. Managing context on the Claude Developer Platform (context editing + memory tool)
- Anthropic · 2025-09-29 · https://claude.com/blog/context-management
- Claims: memory tool + context editing "improved performance by 39% over baseline" on an internal agentic-search eval; context editing alone 29%; in a 100-turn web search eval, token consumption reduced 84%.
- Evidence: measured, but internal eval, not coding-specific.
- Relevance: evidence that clearing stale tool results (a milder alternative to summarisation) helps; supports "prune before you summarize".

### Other agent builders

#### S8. Amp — "Handoff" (compaction removed) and Context Management guide
- Sourcegraph Amp · 2025-10-23 · https://ampcode.com/news/handoff · guide (Nov 2025): https://ampcode.com/guides/context-management
- Claims: **[raw]** "We have removed compaction from Amp and replaced it with something that we think works a lot better: Handoff." "Compaction… always had downsides. It's lossy, for one." **[raw]** compaction "encourages long, meandering threads, in which you just compact once you run out of context window, stacking summary on top of summary." "Instead of summarizing a thread, you're extracting from it what matters for your next task." "Handoff lets you specify your goal for the new thread. Amp then analyzes the current thread and generates a prompt to start the new thread, along with a list of relevant files." Guide: "Quality degrades: the more context, the worse the results."
- Evidence: vendor product decision + rationale; no published metrics. **Verified: Amp did remove compaction.**
- Relevance: the key design difference — handoff is *goal-conditioned extraction* (needs the next goal), compaction is goal-agnostic summarisation. At an auto-compact boundary the "next goal" must be inferred (from plan/todo) for handoff to work unattended.

#### S9. Factory.ai — Evaluating context compression
- Factory · 2025-12-16 · https://factory.com/news/evaluating-compression (factory.ai redirects)
- Claims: probe-based evaluation with four probe types — Recall, Artifact, Continuation, Decision — judged on six 0–5 dimensions. Overall: Factory 3.70, Anthropic 3.44, OpenAI 3.35. Artifact trail: 2.45 / 2.33 / 2.19. Compression ratio: OpenAI 99.3%, Anthropic 98.7%, Factory 98.6%. **[raw]** "the right optimization target is not tokens per request. It is tokens per task." "all methods scored between 2.19 and 2.45 out of 5.0 on knowing which files were created, modified, or examined".
- Evidence: measured (LLM-judge scores on real sessions); vendor-run, own product wins — treat ranking sceptically, the artifact-trail weakness is consistent across all three.
- Relevance: (1) a ready-made method to *test a compaction/handoff after the fact* (probe it with recall/artifact/continuation/decision questions); (2) file/artifact state must be sourced from git/transcript.

#### S10. OpenAI Codex CLI — compaction source, prompt, and warning
- OpenAI · fetched 2026-09-19 · https://raw.githubusercontent.com/openai/codex/main/codex-rs/core/src/compact.rs · https://raw.githubusercontent.com/openai/codex/main/codex-rs/prompts/templates/compact/prompt.md · …/summary_prefix.md
- Claims **[raw source]**:
  - After each compaction Codex emits: "Heads up: Long threads and multiple compactions can cause the model to be less accurate. Start a new thread when possible to keep threads small and targeted."
  - Compaction prompt: "You are performing a CONTEXT CHECKPOINT COMPACTION. Create a handoff summary for another LLM that will resume the task. Include: - Current progress and key decisions made - Important context, constraints, or user preferences - What remains to be done (clear next steps) - Any critical data, examples, or references needed to continue".
  - Summary prefix: "Another language model started to solve this problem and produced a summary of its thinking process… Use this to build on the work that has already been done and avoid duplicating work."
  - `COMPACT_USER_MESSAGE_MAX_TOKENS = 20_000` (user messages are retained verbatim up to a budget; summary replaces the rest).
- Related issue (2026-03-11) https://github.com/openai/codex/issues/14347: "After 2-3 compactions in the same session, all reasoning, decisions, and context from earlier compactions is completely lost." Proposes a cumulative "Historical Context" section. (User report, anecdotal.)
- Evidence: source code (authoritative for behaviour); the accuracy warning is vendor assertion.
- Relevance: Codex frames compaction *as* a handoff to "another LLM", and ships a compaction-count warning. Compaction count is the cheapest signal available.

#### S10b. OpenAI — Run long horizon tasks with Codex
- Derrick Choi (OpenAI) · (GPT-5.3-Codex era) · https://developers.openai.com/blog/run-long-horizon-tasks-with-codex
- Claims: four durable files — Prompt.md (spec: "Freeze the target so the agent doesn't 'build something impressive but wrong.'"), Plan.md (milestones with acceptance criteria + validation commands), Implement.md (runbook), Documentation.md ("Shared memory and audit log"). "After milestones, it ran verification commands and repaired failures before continuing." Run: ~25 h, ~13M tokens, ~30k LOC.
- Evidence: single demo run, measured totals.
- Relevance: milestone acceptance criteria give an objective progress measure (milestones verified / tokens) usable at the compaction boundary.

#### S11. Geoffrey Huntley — "Ralph Wiggum as a software engineer"
- Geoffrey Huntley · 2025-07-14 · https://ghuntley.com/ralph/
- Claims: `while :; do cat PROMPT.md | claude-code ; done`; "One item per loop. I need to repeat myself here—one item per loop."; "you only have approximately 170k of context window to work with"; "deterministically allocate the stack the same way every loop" (plan `@fix_plan.md` + specs); backpressure: "After implementing functionality or resolving problems, run the tests for that unit of code that was improved."; discard option: "Is it easier to do a `git reset --hard` and to kick Ralph back off again?"
- Evidence: anecdote / practitioner technique.
- Relevance: the extreme of option (b): never compact, always fresh context + file-based plan; (c) is a routine operator decision made on cost-of-rescue vs cost-of-restart.

#### S17. Cursor — Best practices for coding with agents
- Lee Robinson (Cursor) · 2026-01-09 · https://cursor.com/blog/agent-best-practices
- Claims: start a new conversation when "You're moving to a different task or feature", when the agent seems confused or keeps making the same mistakes, or "You've finished one logical unit of work"; "long conversations can cause the agent to lose focus" after many turns and summarizations; when the build doesn't match intent, revert the changes and refine the plan rather than fixing through follow-ups — yields "cleaner results"; use `@Chats` to reference prior work selectively. (Search-result snippet, not separately fetched: Cursor gives the agent a reference to the chat-history file after summarization so it can recover missing details — see Unverified leads.)
- Evidence: vendor guidance, opinion.
- Relevance: independent vendor naming "same mistakes repeatedly" and "after summarizations" as restart triggers, and preferring revert+replan (option c-lite) to patching.

#### S18. HumanLayer — Advanced Context Engineering for Coding Agents (ACE-FCA)
- Dex Horthy · 2025-08 · https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md
- Claims: "frequent intentional compaction": "designing your ENTIRE WORKFLOW around context management, and keeping utilization in the 40%-60% range"; context eaters: "Searching for files, Understanding code flow, Applying edits, Test/build logs, Huge JSON blobs from tools"; progress-file prompt: "Write everything we did so far to progress.md, ensure to note the end goal, the approach we're taking, the steps we've done so far, and the current failure we're working on"; "Whether you're on track or not, as your context starts to fill up, you probably want to pause your work and start over with a fresh context window."; Research → Plan → Implement; result: 35k LOC of BAML changes, "Got both draft prs ready in about 7 hours".
- Evidence: anecdote with concrete case studies; the 40–60% figure is a heuristic, not measured.
- Relevance: minimal 4-field handoff template; treats fresh-context as default irrespective of on/off-track (i.e., do not wait for auto-compact).

#### S22. Cognition — Don't Build Multi-Agents
- Walden Yan · 2025-06-12 · https://cognition.com/blog/dont-build-multi-agents (cognition.ai redirects)
- Claims: "Share context, and share full agent traces, not just individual messages"; "Actions carry implicit decisions, and conflicting decisions carry bad results"; for long tasks, "introduce a new LLM model whose key purpose is to compress a history of actions & conversation into **[raw]** key details, events, and decisions"; "for those who have truly long-duration tasks, and are willing to put in the effort, you can do even better". LangChain [S24] adds: "Cognition uses a fine-tuned model for this, which underscores how much work can go into this step".
- Evidence: opinion from a production agent builder.
- Relevance: handoff quality hinges on preserving *decisions*, not messages — implies a decision log is the key handoff artifact.

#### S23. Manus — Context Engineering for AI Agents
- Yichao "Peak" Ji · 2025-07-18 · https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus
- Claims: "KV-cache hit rate is the single most important metric for a production-stage AI agent."; "Our compression strategies are always designed to be restorable."; "We treat the file system as the ultimate context"; todo recitation: "By constantly rewriting the todo list, Manus is reciting its objectives into the end of the context."; **[raw]** "leave the wrong turns in the context"; few-shot drift: "The model will tend to follow that pattern, even when it's no longer optimal".
- Evidence: production experience, opinion.
- Relevance: a counter-argument to discarding: failed attempts are evidence the next context needs ("already tried, failed"). Also a cost signal: compaction and restarts both blow the KV cache.

#### S24. LangChain — Context Engineering for Agents
- Lance Martin · 2025-07-02 · https://www.langchain.com/blog/context-engineering-for-agents
- Claims: write / select / compress / isolate taxonomy; notes Claude Code auto-compact triggers after exceeding 95% of the context window (paraphrase); summarisation can lose specific events/decisions, hence Cognition's fine-tuned summariser.
- Evidence: survey/opinion.
- Relevance: taxonomy; (a)=compress, (b)=write+isolate.

#### S25. Drew Breunig — How Long Contexts Fail
- Drew Breunig · 2025-06-22 · https://www.dbreunig.com/2025/06/22/how-contexts-fail-and-how-to-fix-them.html
- Claims: Poisoning — "When a hallucination or other error makes it into the context, where it is repeatedly referenced."; Distraction — "As context grew significantly beyond 100k tokens, the agent showed a tendency toward favoring repeating actions from its vast history rather than synthesizing novel plans." (Gemini 2.5 report); Databricks: "Model correctness began to fall around 32k" for Llama 3.1 405b; Confusion; Clash — sharded prompts gave "an average drop of 39%", o3 98.1 → 64.1; "LLMs often make assumptions in early turns and prematurely attempt to generate final solutions, on which they overly rely."
- Evidence: secondary synthesis of measured studies.
- Relevance: a *poisoned* context is the case where compaction is harmful (the summary launders the poison) and handoff/restart is indicated. Signal: an early assumption later contradicted by tool output or by the user.

#### S26. Chroma — Context Rot
- Kelly Hong, Anton Troynikov, Jeff Huber · 2025-07-14 · https://www.trychroma.com/research/context-rot
- Claims: 18 LLMs; "model performance degrades as input length increases, often in surprising and non-uniform ways"; "Even a single distractor reduces performance relative to the baseline".
- Evidence: measured (synthetic retrieval-style tasks, not agentic coding).
- Relevance: justifies not using a universal %-full threshold; degradation is model/task specific.

#### S27. Letta — Compaction docs
- Letta · fetched 2026-09-19 · https://docs.letta.com/guides/core-concepts/messages/compaction/
- Claims: modes `sliding_window` (default; "Preserves recent messages and summarizes older ones"), `all`, and `self_compact_*` variants that include system prompt/tools for cache hits; default summarises fraction 0.3 of messages, summary limit 50,000 chars, small summariser model.
- Evidence: product docs.
- Relevance: partial (sliding-window) compaction as a design alternative; mirrors Claude Code's "Summarize up to here".

### Implemented stuck / loop detectors (source code)

#### S12. OpenHands StuckDetector (V0 controller and V1 SDK)
- OpenHands · V0: https://raw.githubusercontent.com/All-Hands-AI/OpenHands/0.50.0/openhands/controller/stuck.py · V1: https://raw.githubusercontent.com/OpenHands/software-agent-sdk/main/openhands-sdk/openhands/sdk/conversation/stuck_detector.py and …/conversation/types.py (the `main`-branch V0 path now 404s)
- Heuristics **[raw source]** (only events since the last user message are considered):
  1. "same action, same observation" — 4 identical action/observation pairs (`action_observation: default=4`). Log: "Action, Observation loop detected".
  2. "same action, errors" — last 3 actions identical and all 3 observations are errors (`action_error: default=3`). V0 has a special case for repeated IPython `SyntaxError` messages. V1 adds a *nudge* at the threshold before declaring stuck: "You've called `{tool}` with the same arguments {threshold} times in a row and gotten the same error each time… Repeating the exact same call again will not work — review the error message and either correct the arguments or try a different approach."
  3. "monologue" — 3 consecutive identical agent messages with no observations between (`monologue: default=3`).
  4. Alternating pattern over the last six steps: a[i]==a[i+2] and o[i]==o[i+2] (`alternating_pattern: default=6`). Log: "Alternating Action, Observation loop detected".
  5. **Context-window error loop** — V0: ≥10 consecutive condensation events with nothing between them → "Context window error loop detected - repeated condensation events". V1: stubbed (`return False`, TODO).
- Evidence: shipped code; no published precision/recall.
- Relevance: canonical set of syntactic no-progress checks; #5 is the only detector anywhere that treats *compaction itself* as a stuck signal.

#### S13. Gemini CLI LoopDetectionService
- Google · https://raw.githubusercontent.com/google-gemini/gemini-cli/main/packages/core/src/services/loopDetectionService.ts
- Heuristics **[raw source]**: `TOOL_CALL_LOOP_THRESHOLD = 5` identical consecutive tool calls (hash of name+args); `CONTENT_LOOP_THRESHOLD = 10` repeats of a `CONTENT_CHUNK_SIZE = 50`-char chunk, `MAX_HISTORY_LENGTH = 5000`; LLM judge: `LLM_CHECK_AFTER_TURNS = 30`, `DEFAULT_LLM_CHECK_INTERVAL = 10` (adaptive 5–15), `LLM_CONFIDENCE_THRESHOLD = 0.9`, `LLM_LOOP_CHECK_HISTORY_COUNT = 20`.
- Judge prompt (verbatim excerpt): "An unproductive state requires BOTH of the following to be true: 1. The assistant has exhibited a repetitive pattern over at least 5 consecutive model actions… 2. The repetition produces NO net change or forward progress toward the user's goal." Patterns: "Alternating cycles with no net effect… (e.g., edit_file → run_build → edit_file → run_build) where each iteration applies the same edit and encounters the same error", "Semantic repetition with identical outcomes", "Stuck reasoning". NOT loops: "Cross-file batch operations", "Incremental same-file edits", "Sequential processing", "Retry with variation"; "re-running a build to verify a fix is normal workflow". Output schema: `unproductive_state_analysis`, `unproductive_state_confidence` (0–1).
- Evidence: shipped code; thresholds presumably tuned on telemetry but no data published.
- Relevance: the most reusable artefact found — a production prompt + schema for an LLM "is this session unproductive?" judge, with false-positive carve-outs and a confidence gate. Directly adaptable to a PreCompact evaluator (window = since last compaction).

#### S14. Cline — loop-detection and mistake tracker
- Cline · https://raw.githubusercontent.com/cline/cline/main/sdk/packages/core/src/runtime/safety/loop-detection.ts · …/mistake-tracker.ts
- Heuristics **[raw source]**: signature = tool name + key-sorted JSON of input; `consecutiveIdenticalCount`; `DEFAULT_CONFIG = { softThreshold: 3, hardThreshold: 5 }` — "soft": "may surface a recovery notice but should not block the call"; "hard": "should stop the run". Separate per-session consecutive-mistake tracker with a `maxConsecutiveMistakes` limit and an `onLimitReached` decision (continue/stop).
- Evidence: shipped code.
- Relevance: two-tier (warn → stop) design; consecutive-mistake counter = error-streak signal.

#### S15. SWE-agent — limits and retry loop
- SWE-agent (Princeton/Stanford) · https://raw.githubusercontent.com/SWE-agent/SWE-agent/main/sweagent/agent/agents.py · …/agent/reviewer.py
- Heuristics **[raw source]**: `max_requeries: int = 3` (format/blocklist/syntax failures before exit with autosubmission); `max_consecutive_execution_timeouts`; `total_execution_timeout`; per-instance cost limit; on fatal error "attempt autosubmission" using the diff from the last step. Retry loop: `ScoreRetryLoopConfig { accept_score, max_attempts, min_budget_for_new_attempt, cost_limit }` with a `Reviewer` that samples `n_sample = 5` scores, optional `failure_score_penalty` and `reduce_by_std`; `ChooserRetryLoopConfig` picks the best among attempts.
- Evidence: shipped research code (used in published SWE-bench runs).
- Relevance: a concrete implementation of option (c): **LLM-scored attempt → if below accept_score and budget remains → fresh attempt → choose best**. Shows restart should be budget-gated and that variance-penalised multi-sample scoring is used to tame judge noise.

#### S16. Goose RepetitionInspector; Aider reflection cap; OpenClaw post-compaction guard
- Goose: https://raw.githubusercontent.com/block/goose/main/crates/goose/src/tool_monitor.rs (+ tests/repetition_inspector_tests.rs) — **[raw]** "consecutive identical tool calls are allowed up to max_repetitions times - the (max_repetitions + 1)th identical call is denied… changing the parameters resets the repetition count". `max_repetitions: Option<u32>` (None = disabled).
- Aider: https://raw.githubusercontent.com/Aider-AI/aider/main/aider/coders/base_coder.py — **[raw]** `max_reflections = 3`; "Only {self.max_reflections} reflections allowed, stopping." (caps automatic lint/test-fix re-prompts).
- OpenClaw docs: https://docs.openclaw.ai/tools/loop-detection — rolling-history detectors plus a **post-compaction guard** that aborts when the agent emits the same `(toolName, argsHash, resultHash)` repeatedly right after a context-overflow compaction; outcomes are normalised ("stable command outcomes (status, exit code, timed-out flag, output)" ignoring "volatile runtime metadata"); "new failure cause resets the streak".
- Evidence: shipped code/docs.
- Relevance: result-hash (not just args-hash) comparison is the right way to tell "re-running tests after an edit" from "looping"; the post-compaction guard is direct precedent for watching behaviour *immediately after* compaction as a check on compaction quality.

### Handoff practice write-ups

#### S19. AI Hero — The /handoff skill
- aihero.dev (Matt Pocock's site) · updated 2026-08-24 · https://www.aihero.dev/skills-handoff
- Claims: handoff "compacts the conversation you are in into a **handoff document**: one markdown file" that "a fresh agent can read to pick the work up"; includes the live thread (work in progress, reasoning, next steps), a suggested-skills section, references to specs/plans/ADRs/issues/commits "by path/URL" rather than copied text, secrets redacted, omits "anything already written down"; "`/compact` compresses this context and keeps you going in a fresh window: intent survives" vs handoff for "a new harness, a new directory, a colleague, or a side task".
- Evidence: practitioner tooling, opinion.

#### S20. Nathan Onn — Stop Losing Work When You Compact Claude Code
- Nathan Onn · 2026-06-26 · https://www.nathanonn.com/claude-code-handoff-doc-skill/
- Claims: template sections — What happened; Where things live; Verification done (incl. "what was _not_ tested"); Git state ("anchors the handoff to a specific commit, branch, and push status"); Open follow-ups ("numbered, specific, ready to pick up"). Recommends handing off around 20% of a 1M window (~200k tokens). Anecdote: without a handoff the next session "re-read files I'd already inspected — and then made a decision I'd already made. In a different direction." ("Fifteen minutes of rework").
- Evidence: anecdote.

#### S21. Zylos Research — Context Rotation and Session Handoff in Long-Running AI Agents
- Zylos · 2026-08-31 · https://zylos.ai/research/2026-08-31-context-rotation-session-handoff-long-running-agents/
- Claims: "set a proactive policy from measured answer quality, cost, and remaining headroom for the actual workload rather than copying one universal utilization percentage". Must survive: active task + success criteria, pending obligations, irreversible-decision log, **side-effect ledger** (external actions already taken), identity. Safe to drop: raw tool outputs already synthesised, full reasoning traces, exploratory dead ends "if the 'already tried, failed' status is preserved".
- Evidence: secondary synthesis; cites only Chroma as measured.

#### S28. Will Ness — Why You Need To Clear Your Coding Agent's Context Window
- Will Ness · 2026-01-24 · https://willness.dev/blog/one-session-per-task
- Claims: quality zones 0–40% / 40–70% / 70%+; "Compressed noise is still noise."; "One task, one session." Backed by a *simulation* (25 files, compact at 80% to 20%), not measurements.
- Evidence: opinion + toy simulation. Included as representative of the common "40% rule" folk heuristic (also HumanLayer's 40–60%); no empirical basis found.

#### S29. failproof ai — AI Agent Stuck in a Loop
- befailproof.ai · updated 2026-07 · https://befailproof.ai/agent-stuck-in-a-loop/
- Claims: four signals — "The same tool call repeats… N times in a row"; "The same edit reverts and reapplies… the diff oscillates instead of converging"; "The same error text recurs… the state is not changing"; "Call count climbs, progress does not. Fifty model calls into a two-call task, with no new files touched." Example threshold: 3 identical signatures.
- Evidence: opinion; "No empirical data".
- Relevance: only source found that explicitly names edit oscillation (revert/reapply) and calls-vs-progress as signals.

---

## Candidate signals

| Signal | How to compute (from Claude Code transcript JSONL + git) | Who uses / proposes it | Evidence strength |
|---|---|---|---|
| Identical tool-call streak | hash(tool name + key-sorted args); longest consecutive run in window | Gemini CLI (5), Cline (soft 3 / hard 5), Goose (configurable), OpenHands (4 w/ same observation) | Shipped in 4 agents; no published accuracy |
| Same action → same error streak | same call hash AND `is_error` tool result with same normalised text, ≥3 | OpenHands (3, with nudge first), OpenClaw (result-hash; "new failure cause resets the streak") | Shipped; none measured |
| Alternating A-B-A-B with no net effect | a[i]==a[i+2] and o[i]==o[i+2] over last 6 steps | OpenHands; Gemini judge prompt (edit→build→edit→build, same edit same error) | Shipped |
| Monologue / stuck reasoning | ≥3 consecutive assistant text turns w/o tool use, near-identical; `/goal`: "no tool use for several turns in a row" | OpenHands, Gemini judge, Claude Code /goal | Shipped |
| Repeated content chunk | 50-char chunk hash seen ≥10× within 5000 chars | Gemini CLI | Shipped |
| Number of compactions so far | count compact boundaries / PostCompact events in session | Codex warning (every compaction), Amp ("summary on top of summary"), Codex issue #14347 ("2–3"), Cursor ("after many turns and summarizations") | Vendor assertion + user reports; no curve published |
| Compaction loop | compactions with no intervening non-compaction events (OpenHands: 10); repeated identical call right after compaction (OpenClaw) | OpenHands V0, OpenClaw | Shipped |
| User corrections on same issue | count user turns that negate/redirect the same topic; interrupts (Esc), rewinds | Anthropic best practices (>2 → `/clear`), Cursor ("same mistakes") | Vendor guidance; opinion |
| Context utilisation % | input tokens / window | HumanLayer (40–60%), Ness (40/70%), Onn (20% of 1M), LangChain notes CC auto-compacts ~95% | Folk heuristics; Chroma shows degradation is non-uniform, Zylos warns against universal % |
| Verified progress per token ("tokens per task") | (tests newly passing, plan/todo items or features flipped to done, milestones verified) ÷ tokens or $ since last compaction | Factory ("tokens per task"), Anthropic harness (feature list failing→passing), OpenAI Codex (milestone validation), failproof ("call count climbs, progress does not") | Conceptually endorsed by 3 vendors; no thresholds published |
| Test/build pass-rate trend | parse test/build tool results over window; slope and whether the *failure cause* changes | Ralph (backpressure), Anthropic best practices (verification), OpenClaw (failure-cause change resets streak) | Practice; not measured as a detector |
| Edit churn / oscillation | per-file: edits whose new_string ≈ an earlier old_string (revert/reapply); edits per file vs net diff lines (`git diff --stat`) | failproof ai; Gemini judge explicitly *exempts* incremental same-file edits | Opinion only; high false-positive risk without net-diff check |
| Diff vs plan / scope drift | files touched outside plan; plan items with no diff; reviewer subagent on diff vs PLAN.md | Anthropic best practices (adversarial review), sprint contracts [S6], Codex Prompt.md/Plan.md | Practice; reviewer over-reports gaps [S2] |
| Premature wrap-up near limit ("context anxiety") | declares done / skips verification as utilisation rises; done-claim without passing check | Anthropic [S6][S7] | Observed by Anthropic; model-dependent (Sonnet 4.5 yes, Opus 4.5 largely no) |
| Context poisoning | early assumption later contradicted by tool output/user but still referenced | Breunig (from Gemini 2.5 report) | Measured in cited study; no detector implemented |
| LLM judge of unproductive state | fresh small model over last N turns + original request → confidence; act at ≥0.9 | Gemini CLI (after 30 turns, every ~10), Claude Code /goal (met/not yet/impossible), SWE-agent Reviewer (5 samples, std penalty, accept_score) | Shipped in 3 systems; self-judging known lenient [S6], reviewers over-flag [S2] |
| Remaining budget for a fresh attempt | budget − spend ≥ min_budget_for_new_attempt; attempts < max_attempts | SWE-agent retry loop | Shipped research code |
| Post-compaction summary quality | probe the summary with recall / artifact / continuation / decision questions vs transcript ground truth | Factory.ai | Measured (vendor) — artifact trail weakest (2.19–2.45/5) |
| Cache/cost penalty of switching | KV-cache loss on compaction or restart | Manus ("KV-cache hit rate… most important metric") | Opinion from production |

---

## Synthesis notes (derived from the sources above; my inference, not quoted)

- No fetched source implements the exact thing asked (an evaluator at the auto-compact boundary choosing among a/b/c). The pieces exist separately: hook point [S4], judge prompt [S13], external-judge precedent [S5], retry/accept-score loop [S15], handoff templates [S10][S18][S20][S21], summary probes [S9].
- Practitioners implicitly use a 2×2: *progress healthy?* × *context healthy?* — healthy/healthy → continue or compact [S3]; progress ok but context bloated or Nth compaction → handoff + fresh [S8][S10]; off-track but reads still useful → rewind to checkpoint + re-prompt with the ruled-out approach [S3]; off-track and the plan itself is wrong → revert (git) and restart from an improved spec [S17][S11][S2].
- Even under (c), sources agree to carry forward the negative knowledge ("ruled-out approaches", "already tried, failed") [S3][S21][S23].

---

## Unverified leads

- https://docs.bswen.com/blog/2026-06-29-claude-handoff-file-vs-compact/ — "Use a HANDOFF File Instead of /compact" (HTTP 403; claims about prompt-cache/token savings seen only in search snippet).
- https://medium.com/joash-pereira/the-handoff-trick-that-saves-your-claude-code-sessions-1bece96d7a40 — not fetched.
- https://harnessrouter.ai/blog/claude-code-compact-vs-new-session — not fetched.
- https://cursor.com/blog/dynamic-context-discovery and https://docs.cursor.com/en/agent/chat/summarization — search snippet says Cursor gives the agent the chat-history file after summarisation to recover details; not fetched.
- Simon Willison's writing on compaction / fresh sessions (https://simonwillison.net/tags/gpt-codex/, "Agentic Engineering Patterns") — surfaced in search; not fetched, no claims recorded.
- Cognition follow-ups (Devin/Sonnet 4.5 "context anxiety" post) — not fetched; the term is verified only via Anthropic [S6].
- Letta blog posts on sleep-time compute / memory blocks; Letta Leaderboard — search snippets only.
- OpenAI Codex prompting guide (https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide) and GPT-5.1-Codex-Max native-compaction claims — search snippets only.
- arXiv items surfaced but not fetched: 2604.08290 (Tokalator), 2605.23296 (Parallel Context Compaction), 2606.15903 (Control-Plane Placement Shapes Forgetting).
- OpenClaw loop-detector numeric thresholds and detector names (genericRepeat / pingPong etc.) — the fetched docs page did not state them.
- Cline's claimed weakness ("A,B,C,A,B,C cycle evades it") came from a search snippet about third-party issues; consistent with the source I read (consecutive-identical only) but the issue itself was not fetched.
- Claude Code auto-compact threshold: "95%" is from LangChain's 2025 post [S24]; current docs refer to a configurable "auto-compact window" (https://code.claude.com/docs/en/model-config#set-the-auto-compact-window), which I did not fetch.
