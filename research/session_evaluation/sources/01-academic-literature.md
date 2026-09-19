# 01 - Academic literature: evaluating a session at compaction time (compact / handoff / restart)

Compiled 2026-09-19. Every source below was fetched in this task (arXiv abstract page and/or arXiv HTML full text, or the publisher page). Fetching was done through a tool that returns a model-written digest of the page, so text in quotation marks is what that digest reported as verbatim; spot-check exact wording against the PDF before quoting it in anything published. Where I only saw the abstract, the entry says so.

Options referred to throughout: (a) compact and continue, (b) write handoff summary and start a fresh session, (c) discard and start over.

## Key takeaways for the question

1. Once an LLM takes a wrong turn in a multi-turn interaction it tends not to recover; the loss is mostly reliability, not capability (average drop 39%; aptitude -16%, unreliability +112%). The authors' own user advice is "If time allows, try again" and "Consolidate before retrying", i.e. option (b) has direct empirical support, at least for chat-style generation tasks. [S1]
2. Errors in the model's own history cause more errors ("self-conditioning"): accuracy at turn 100 degrades monotonically with the injected error rate in the history; scale does not fix it, thinking models largely do, and trimming history (sliding window) helps. A context containing many of the agent's own mistakes is therefore itself a reason not to carry it forward verbatim. [S2]
3. Context length alone degrades performance, even with perfect retrieval and with irrelevant tokens masked (13.9%-85% drops), so "near the compaction limit" is already a degraded operating regime independent of whether the path is wrong. [S5, S3, S4, S6, S7]
4. LLM summarisation/compaction is not a free "continue": on SWE-bench Verified it did not beat simply masking old observations, and it lengthened trajectories (about 15% more turns for Gemini 2.5 Flash), with the authors hypothesising that summaries "smooth over, or hide, signs indicating that the agent should already stop". Compaction can erase exactly the evidence needed to judge that the session is on a wrong path, so the evaluation should run BEFORE compaction, on the raw trajectory. [S8]
5. Compaction has a measurable post-boundary cost: more blocked/error actions right after compaction (+0.108 at first step), refetching/replaying completed actions, failure to recognise completion, and a widening gap between pass-at-least-once and pass-every-time. Lost items are typically causal relations, evolving state, preconditions and decision cues. [S9, S10, S11]
6. Failure is predictable from observable trajectory prefixes well before the end, with small monitors: a 0.6B monitor over an 8-step window saved 14.6%-20.4% of tokens at 5% false-positive rate on SWE-bench Verified; FSM-state behavioural features reach AUROC up to 0.94; hidden-state probes predict failure from round 1. [S12, S13, S14, S15]
7. Do NOT let the agent self-assess whether to give up: on failed trajectories frontier models still predict feasibility at rates above 70% after 60% of budget is consumed; intrinsic self-correction without external feedback does not work and can hurt. Use an external judge/monitor or executable evidence (tests). [S16, S17]
8. The only direct restart comparison found: on SWE-bench Verified, a plain cold restart after predicted failure gained +0.2 points (66.6% to 66.8%), while restarting fresh with the previous code diff available as an optional, unverified overlay gained +5.2 points (to 71.8%) at +43.8% net compute. The authors deliberately avoid textual summaries because they "induce severe LLM anchoring effects" - but they did not ablate summary vs diff. 54.9% of failing trajectories contained recoverable partial progress. This argues for (b) over (c), with the handoff carrying artefacts (diff, test status) rather than narrative. [S12]
9. Raw trajectory length is a weak, confounded signal: failed runs are longer across tasks (e.g. OpenHands 98.62 vs 54.05 steps on Verified), but within the same task resolved runs are slightly longer (44.0 vs 39.6 steps). Better behavioural predictors: early editing before context gathering (rho = -0.78), low validation share (rho = +0.50 for validation), repetition/looping, accumulating execution errors. [S18, S19, S12]
10. A distinctive wrong-path signature in capable coding agents is "coherence collapse": 60-69% of failures reach and edit the correct functions, then overwrite or thrash; in 5 cases the agent produced the gold patch mid-trajectory and later destroyed it. Edit churn on already-passing code and declining test status are therefore restart/rollback signals, and checkpoints of working states are worth preserving across any reset. [S20]
11. Step repetition (15.7%), unawareness of termination conditions (12.4%) and reasoning-action mismatch (13.2%) are the most frequent catalogued failure modes in multi-agent traces, and an o1-based LLM judge labels them with 94% accuracy / kappa 0.77 against humans - evidence that an LLM-as-judge over the trajectory is a feasible detector. [S21, S22]
12. Persisting state across many rounds costs a lot compared with starting each round from a clean, reference state: single-round score exceeds four-attempt persistent multi-round score by 22-40 points for most coding agents, and pass rate falls below half of round-1 by round 5. [S23]

---

## Sources

### Group 1 - Multi-turn degradation

#### S1. LLMs Get Lost In Multi-Turn Conversation
- Authors/org: Philippe Laban, Hiroaki Hayashi, Yingbo Zhou, Jennifer Neville (Microsoft Research / Salesforce Research)
- Date: 9 May 2025 (arXiv 2505.06120)
- URL: https://arxiv.org/abs/2505.06120 (full text fetched at https://arxiv.org/html/2505.06120)
- Measured: single-turn fully specified instructions vs the same instruction "sharded" and revealed over turns; 200,000+ simulated conversations, six generation tasks (incl. code), many frontier models. Decomposes loss into aptitude (best case) and unreliability (best-worst gap).
- Findings: "average drop of 39% across six generation tasks"; about 90% performance in full single-turn vs about 65% multi-turn; aptitude falls only about 16% while unreliability rises about 112%; "all models tend to have similar levels of unreliability". "when LLMs take a wrong turn in a conversation, they get lost and do not recover." Causes: models "often make assumptions in early turns and prematurely attempt to generate final solutions, on which they overly rely"; over-weighting first and last turns; verbose answers that introduce assumptions. Mitigations: CONCAT (all shards in one prompt) reaches 95.1% of full performance; RECAP and SNOWBALL (repeating prior info) recover only part of the gap (snowball roughly 15-20% improvement over plain sharded). User advice: "If time allows, try again" and "Consolidate before retrying".
- Relevance: strongest direct support for option (b): consolidating everything learned into one fresh prompt nearly restores single-turn performance, whereas in-conversation recap (analogous to compaction-and-continue) does not. The cause list gives checkable signals: early premature solution the session kept patching; assumptions made before requirements were complete.
- Caveats: simulated users, short generation tasks (not tool-using agents, no environment feedback); sessions were about requirement under-specification, not long tool loops. The CONCAT condition consolidates the user's requirements, not the agent's own findings.

#### S24 (supporting). When Attention Closes: How LLMs Lose the Thread in Multi-Turn Interaction
- Authors: Vardhan Dongre, Joseph Hsieh, Viet Dac Lai, Seunghyun Yoon, Trung Bui, Dilek Hakkani-Tur. 13 May 2026. https://arxiv.org/abs/2605.12922 (abstract only)
- Measured/findings: mechanistic account of losing instructions/persona/rules over long interactions; proposes Goal Accessibility Ratio (attention from generated tokens to task-defining tokens); force-closing the attention channel in Mistral "collapses recall from near-perfect to 11%"; linear probes reach AUC up to 0.99.
- Relevance: suggests goal/instruction drift is detectable from internals; for API-only agents the behavioural analogue is checking whether recent actions still reference the original task constraints.
- Caveats: open-weight, mechanistic; abstract only.

### Group 2 - Long-context degradation

#### S3. Lost in the Middle: How Language Models Use Long Contexts
- Authors: Nelson F. Liu, Kevin Lin, John Hewitt, Ashwin Paranjape, Michele Bevilacqua, Fabio Petroni, Percy Liang. July 2023 (final Nov 2023; TACL). https://arxiv.org/abs/2307.03172 (abstract)
- Measured: multi-document QA and key-value retrieval with the relevant item at varying positions.
- Findings: "performance is often highest when relevant information occurs at the beginning or end of the input context, and significantly degrades when models must access relevant information in the middle of long contexts", "even for explicitly long-context models."
- Relevance: in a long session, the original task statement and early decisions drift into the "middle"; background for why late-session behaviour ignores early constraints.
- Caveats: 2023 models; retrieval-style tasks.

#### S4. RULER: What's the Real Context Size of Your Long-Context Language Models?
- Authors: Cheng-Ping Hsieh et al. (NVIDIA). April 2024. https://arxiv.org/abs/2404.06654 (abstract)
- Measured: 17 long-context LMs, 13 tasks (retrieval, multi-hop tracing, aggregation) at increasing lengths.
- Findings: "almost all models exhibit large performance drops as the context length increases"; of models claiming 32K+, "only half of them can maintain satisfactory performance at the length of 32K."
- Relevance/caveats: effective context is shorter than advertised; synthetic tasks, 2024 models.

#### S6. NoLiMa: Long-Context Evaluation Beyond Literal Matching
- Authors: Ali Modarressi et al. (LMU Munich / Adobe Research). Feb 2025, ICML 2025. https://arxiv.org/abs/2502.05167 (abstract)
- Measured: needle retrieval without lexical overlap between question and needle; 13 models claiming 128K+.
- Findings: at 32K, "11 models drop below 50% of their strong short-length baselines"; GPT-4o falls "from an almost-perfect baseline of 99.3% to 69.7%."
- Relevance: agent sessions need associative, not literal, recall of earlier facts (e.g. "the file I found earlier that handles X"), the regime NoLiMa shows degrades fastest.

#### S7. Context Rot: How Increasing Input Tokens Impacts LLM Performance
- Authors/org: Kelly Hong, Anton Troynikov, Jeff Huber (Chroma). 14 July 2025. https://www.trychroma.com/research/context-rot (technical report, not peer reviewed)
- Measured: 18 models (Claude Opus 4/Sonnet 4/3.7/3.5/Haiku 3.5; o3, GPT-4.1 family, GPT-4o, GPT-4 Turbo, GPT-3.5 Turbo; Gemini 2.5 Pro/Flash, 2.0 Flash; Qwen3 235B/32B/8B) on needle variants, distractors, haystack structure, LongMemEval, repeated-words replication.
- Findings: "model performance varies significantly as input length changes, even on simple tasks"; performance "grows increasingly unreliable as input length grows"; even a single distractor lowers accuracy, four lower it more, and "distractors do not have uniform impact"; on LongMemEval focused prompts (about 300 tokens) beat full prompts (about 113k tokens) markedly; "models perform worse when the haystack preserves a logical flow of ideas" (shuffled haystacks did better across all 18 models); Claude models tend to abstain under ambiguity while GPT models hallucinate more with distractors.
- Relevance: a long coding session is a coherent haystack full of near-duplicate distractors (superseded file versions, abandoned hypotheses). Count of stale/superseded artefacts in context is a plausible risk signal.
- Caveats: no agentic tasks; vendor report.

#### S5. Context Length Alone Hurts LLM Performance Despite Perfect Retrieval
- Authors: Yufeng Du, Minyang Tian, Srikanth Ronanki, Subendhu Rongali, Sravan Bodapati, Aram Galstyan, Azton Wells, Roy Schwartz, Eliu A Huerta, Hao Peng. 6 Oct 2025, Findings of EMNLP 2025. https://arxiv.org/abs/2510.05381 (abstract verbatim)
- Measured: 5 open and closed LLMs on math, QA and coding with controlled padding.
- Findings: "even when models can perfectly retrieve all relevant information, their performance still degrades substantially (13.9%--85%) as input length increases but remains well within the models' claimed lengths." Holds "when the irrelevant tokens are replaced with minimally distracting whitespace, and, more surprisingly, when they are all masked". "the sheer length of the input alone can hurt LLM performance, independent of retrieval quality and without any distraction." Mitigation: recite the evidence first, turning a long-context task into a short one (GPT-4o up to +4% on RULER).
- Relevance: justifies shrinking context at all (a or b over doing nothing) and supports the "recite then solve in short context" pattern that a handoff summary implements.
- Caveats: single-turn tasks, not agent loops.

#### S25 (practitioner synthesis). How Long Contexts Fail
- Author: Drew Breunig. 22 June 2025. https://www.dbreunig.com/2025/06/22/how-contexts-fail-and-how-to-fix-them.html (blog; secondary source quoting primary reports I did not fetch)
- Content: taxonomy. Poisoning: "When a hallucination or other error makes it into the context, where it is repeatedly referenced"; quotes the Gemini 2.5 report on the Pokemon agent: "Many parts of the context (goals, summary) are 'poisoned' with misinformation about the game state, which can often take a very long time to undo." Distraction: quotes the same report: "as the context grew significantly beyond 100k tokens, the agent showed a tendency toward favoring repeating actions from its vast history rather than synthesizing novel plans"; cites Databricks that "model correctness began to fall around 32k for Llama 3.1 405b". Confusion: superfluous content/tools. Clash: conflicting information accrued across turns (cites S1).
- Relevance: the poisoning quote is important for option (b): summaries and goal lists themselves get poisoned, so a handoff summary written by the confused session can carry the wrong path into the fresh session.
- Caveats: blog; Gemini/Databricks/Berkeley claims are second-hand here.

### Group 3 - Trajectory failure analysis, detection, self-assessment limits

#### S2. The Illusion of Diminishing Returns: Measuring Long Horizon Execution in LLMs
- Authors: Akshit Sinha, Arvindh Arun, Shashwat Goel, Steffen Staab, Jonas Geiping. 11 Sept 2025 (v3 March 2026), ICLR 2026. https://arxiv.org/abs/2509.09677 (abstract + HTML full text)
- Measured: pure execution of a long chain of simple steps with plan and knowledge supplied; counterfactual histories with injected error rates; Qwen3 and Gemma3 families plus frontier models (Kimi-K2, DeepSeek-V3, Qwen3-235B).
- Findings: "models become more likely to make mistakes when the context contains their errors from prior turns"; "as we increase the rate of injected errors into the context, accuracy at turn 100 consistently degrades further"; even with an error-free history accuracy at turn 100 is below initial (a pure length effect); scaling model size does not remove self-conditioning; "Qwen3 thinking models do not self-condition - the accuracy of the models at turn 100 remains stable, regardless of the error rate in its context"; a sliding window keeping only the N most recent turns "improves significantly as the context window size is reduced" on Markovian tasks.
- Relevance: gives a concrete, measurable signal - the density of the agent's own errors in the retained history (failed tool calls, reverted edits, retracted claims). High error density favours dropping the transcript (b or c) over carrying it. Also implies the answer depends on whether the agent is a thinking model.
- Caveats: synthetic dictionary-sum task, Markovian so history is disposable; real coding sessions have non-Markovian state.

#### S17. Large Language Models Cannot Self-Correct Reasoning Yet
- Authors: Jie Huang, Xinyun Chen, Swaroop Mishra, Huaixiu Steven Zheng, Adams Wei Yu, Xinying Song, Denny Zhou (Google DeepMind / UIUC). Oct 2023, ICLR 2024. https://arxiv.org/abs/2310.01798 (abstract)
- Findings: "LLMs struggle to self-correct their responses without external feedback, and at times, their performance even degrades after self-correction."
- Relevance: a compaction-time "am I on the wrong path?" self-reflection prompt, with no external evidence, is unlikely to be reliable; ground the evaluation in tests, diffs, and an independent judge.
- Caveats: 2023 models, reasoning QA, no tool feedback. Coding agents do have external feedback (tests), which is the exception the paper carves out.

#### S16. BAGEN: Are LLM Agents Budget-Aware?
- Authors: Yuxiang Lin, Zihan Wang, Mengyang Liu, et al. (Northwestern, Michigan, Cornell, others). 29 May 2026. https://arxiv.org/html/2606.00198v1
- Measured: mid-execution verbalised prediction of remaining cost/feasibility on Sokoban, Search-R1, SWE-bench, Warehouse; Claude Opus 4.7, Claude Sonnet 4.6, GPT-5.2 Instant, Gemini 3.1 Pro, Qwen3-235B.
- Findings: models "underestimate the realized budget more often than overestimating it"; on failed trajectories "models predict feasibility at rates above 70% even after 60% of the budget has been consumed"; the "alarm fires only in the final 20%"; external early-stopping policies saved "between 28% and 64% of tokens on failed trajectories" at a cost of "1.6 to 4.2 percentage points" success; "budget awareness is a distinct capability from task performance."
- Relevance: directly answers "can the agent itself decide at compaction time?": not reliably - it is systematically over-optimistic precisely on doomed runs. Also quantifies the trade-off for any stop policy.
- Caveats: preprint; verbalised estimates only.

#### S12. Fail-Fast, Restart-Smart: Early Failure Prediction and Restart for SWE Agentic Tasks
- Authors: Chenyu Wang, Yunbo Lyu, Junda He, Zhou Yang, Chenxing Zhong, Yaniv Harel, David Lo. 4 Aug 2026. https://arxiv.org/abs/2608.03222 (abstract + HTML)
- Measured: SWE-bench Verified with mini-swe-agent. FailFast = "a lightweight 0.6B monitor trained with terminal and dense fail-to-pass supervision to predict failure from observable prefixes without policy logits or hidden states"; input = task spec + most recent eight-step window (thoughts, actions, observations) + latest patch-producing step. RestartSmart = on predicted failure, start a fresh rollout with the interrupted repository diff as "an optional overlay that the agent may inspect, apply, or discard" (starts disabled, marked unverified).
- Findings: saves "14.6%-20.4% of execution tokens at a target 5% false-positive rate" across four policies (monitor trained only on Qwen3.6-27B, transfers to others including closed-API Gemini 3 Flash). On Qwen3.6-27B: 30.5% recall / 20.4% savings at 5% FPR; 68.3% recall / 49.0% savings at 25% FPR. "RestartSmart raises Qwen3.6-27B resolution from 66.6% to 71.8%" at 25% FPR vs cold restart 66.8%; overhead "+43.8% net compute". Waiting for in-flight edits to settle before terminating helped (68.8% to 71.8% at 25% FPR). 54.9% of failing trajectories contain recoverable partial progress. Rationale against summaries: "verbose text summaries induce severe LLM anchoring effects, prematurely locking the restarting agent into the prior attempt's faulty reasoning paths"; instead "a fresh rollout inherits no prior prompt history." "Failed trajectories are especially costly: they tend to run longer and exhibit redundant exploration, repetition, or looping."
- Relevance: the closest paper to the research question. It shows (i) failure is predictable from a short recent window of observable behaviour, (ii) pure discard-and-restart (c) is nearly worthless (+0.2), (iii) restart with artefact-level carry-over beats both, (iv) narrative carry-over is suspected to anchor.
- Caveats: the anchoring claim is asserted, not ablated (no summary-vs-diff comparison in the paper); single benchmark and scaffold; SWE-bench tasks are much shorter than multi-hour interactive sessions and have no human in the loop; trigger is a learned monitor, not a compaction event.

#### S13. Doomed from the Start: Early Abort of LLM Agent Episodes via a Recall-Controlled Probe Cascade
- Authors: Kai Ruan, Zihe Huang, Ziqi Zhou, et al. July 2026. https://arxiv.org/html/2607.06503v1
- Measured: TextCraft, 800 episodes per model (Qwen-2.5-7B, Llama-3.2-3B); logistic probes on hidden states vs behaviour-only features (action log-prob, token counts, error keywords).
- Findings: activations predict failure "as early as the first interaction round"; behaviour-only scoring is "barely better than chance at the first gate and becomes informative only around rounds 3-4"; probe advantage 0.12-0.21 AUC at round 2; cascade saves 47.1% +/- 10.3% (Qwen) and 37.2% +/- 8.8% (Llama) of inference compute at 90% recall of successful episodes; "stacking behavioral features onto the probe adds nothing."
- Relevance: many failures are determined very early (bad initial plan), consistent with S19's finding about early behaviour. For API models without activations, behaviour-only signals still become informative after a few rounds.
- Caveats: toy environment, small open models, offline activation extraction.

#### S14. Automata from Agent Traces: Failure and Next-Step Prediction
- Authors: Seonglae Cho, Franklin Cardenoso Fernandez, Umar Mohammed, Zekun Wu, Kleyton Da Costa, Ilham Wicaksono, Adriano Koshiyama. 24 Aug 2026. https://arxiv.org/abs/2608.23670 (abstract only)
- Findings: trace corpora collapse into compact FSMs (7-43 states); "per-state behavioral features reach held-out AUROC up to 0.94, and an online monitor ranks failing runs above passing ones from a partial trace, triggering early stopping well before completion"; topology "shaped more by the deployment harness than by the LLM".
- Relevance: cheap structural features (which states the run dwells in / cycles through) are strong failure predictors and are harness-specific, so thresholds should be fit per harness.

#### S15. AgentForesight: Online Auditing for Early Failure Prediction in Multi-Agent Systems
- Authors: Boxuan Zhang, Jianing Zhu, Zeru Shi, Dongfang Liu, Ruixiang Tang. May 2026. https://arxiv.org/abs/2605.08715 (abstract only)
- Findings: recasts failure attribution as a per-prefix continue-or-alarm decision "at the earliest decisive error"; a 7B RL-trained auditor beats GPT-4.1 and DeepSeek-V4-Pro by up to 19.9% with 3x lower step-localisation error.
- Relevance: locating the decisive error step is what enables a fourth option the question omits: roll back to before the error rather than restart from zero.

#### S18. Understanding Code Agent Behaviour: An Empirical Study of Success and Failure Trajectories
- Authors: Oorja Majgaonkar, Zhiwei Fei, Xiang Li, Federica Sarro, He Ye (UCL; Nanjing University). 31 Oct 2025. https://arxiv.org/html/2511.00197
- Measured: OpenHands, SWE-agent, Prometheus trajectories on SWE-Bench Lite and Verified.
- Findings (mean steps, success vs fail): Lite - OpenHands 61.01 vs 79.90; SWE-agent 158.36 vs 178.31; Prometheus 87.16 vs 136.47. Verified - OpenHands 54.05 vs 98.62; SWE-agent 151.95 vs 180.10; Prometheus 146.59 vs 220.92. "Failed trajectories are longer and have a wider distribution than successful ones" (Prometheus Lite SD 100.79 vs 34.62). Successful runs match the gold file over 90% of the time but only 27% match at function level.
- Relevance: hitting the compaction threshold is itself weak evidence of a failing run (base rates shift toward failure as length grows). Caveat in S19.

#### S19. Beyond Resolution Rates: Behavioral Drivers of Coding Agent Success and Failure
- Authors: Tural Mehtiyev, Wesley Assuncao. 2 April 2026. https://arxiv.org/abs/2604.02547 (abstract + HTML)
- Measured: 9,374 trajectories, 19 agents, 8 frameworks, 14 LLMs, 500 SWE-bench Verified tasks.
- Findings: across tasks, "for every agent, failed trajectories are significantly longer (p<0.001, one-sided Mann-Whitney U)", but on the same task resolved runs average "44.0 steps vs. 39.6 for failed agents (10.0% longer)"; length is "a confound". Delaying the first edit to gather context correlates with resolution at rho=+0.68 (p<0.001); "opening patch intensity" (early editing) rho=-0.78 (p<0.001); validation share rho=+0.50 (p<0.05); strong agents validate at "35-37% of steps", weak at "12-19%". "Agents sharing the same LLM agree on far more tasks than agents sharing the same framework."
- Relevance: do not use raw length as the restart trigger. Process-shape signals (edited before understanding, little validation) are better, and task difficulty must be controlled: a long session on a hard task is expected. Also: because the LLM dominates outcomes, restarting with the same model on a task it cannot do will not help - some failures call for escalation (human/model change), not any of a/b/c.
- Caveats: correlations are across agents (agent-level), one run per task, Python only.

#### S20. Coherence Collapse: Diagnosing Why Code Agents Fail After Reaching the Right Code
- Authors: Myeongsoo Kim, Dingmin Wang, Siwei Cui, Farima Farmahinifarahani, Terry Yue Zhuo, Shweta Garg, Baishakhi Ray, Rajdeep Mukherjee, Varun Kumar. 25 March 2026 (rev. 26 May 2026). https://arxiv.org/abs/2603.24631 (abstract verbatim)
- Measured: TRAJEVAL decomposition (search/read/edit vs reference patch) of 16,758 trajectories, three architectures, seven models.
- Findings: "60-69% of failures on SWE-Agent and OpenHands reach and edit the correct functions yet still produce incorrect patches"; Coherence Collapse - "the agent reaches correct code and then overwrites or thrashes it" - is the largest theme; "In 5 cases, the agent produces a patch bit-identical to the gold reference mid-trajectory and destroys it later; an edit-commit checkpoint recovers all 5"; a reference-free checkpoint variant gives "a directional +3.0 pp Pass@1 measurement on GPT-5 (p=0.08)".
- Relevance: late-session thrashing is common and destroys value; signals = repeated edits to the same region, reverting own edits, test status that was green going red. Argues for checkpointing and for "roll back to best checkpoint" as an option alongside a/b/c; argues against (c) since correct work is often present.
- Caveats: abstract only; the +3.0 pp result is not significant at 0.05.

#### S21. Why Do Multi-Agent LLM Systems Fail? (MAST)
- Authors: Mert Cemri, Melissa Z. Pan, Shuyi Yang, et al. (UC Berkeley and others). 17 March 2025 (latest v. Oct 2025). https://arxiv.org/abs/2503.13657 (abstract + HTML)
- Measured: 1600+ annotated traces across 7 MAS frameworks; taxonomy built from 150 traces, human kappa = 0.88; 14 failure modes in 3 categories.
- Findings (frequency): step repetition 15.7%; reasoning-action mismatch 13.2%; unaware of termination conditions 12.4%; disobey task specification 11.8%; incorrect verification 9.1%; no/incomplete verification 8.2%; task derailment 7.4%; fail to ask for clarification 6.8%; premature termination 6.2%; loss of conversation history 2.8%; conversation reset 2.2%; ignored other agent's input 1.9%; disobey role 1.5%; information withholding 0.85%. LLM-as-judge (o1, few-shot): "accuracy 94%, Cohen's Kappa of 0.77".
- Relevance: a ready-made rubric for a compaction-time judge; the top modes (repetition, mismatch between stated reasoning and action, not knowing when done, spec violation, weak verification) are all checkable from a transcript.
- Caveats: multi-agent systems, 2024-25 models; frequencies are of failure labels, not predictive precision for restart decisions.

#### S22. The Long-Horizon Task Mirage? Diagnosing Where and Why Agentic Systems Break (HORIZON)
- Authors: Xinyu Jessica Wang, Haoyue Bai, Yiyou Sun, Haorui Wang, Shuibai Zhang, Wenjie Hu, Mya Schroder, Bilge Mutlu, Dawn Song, Robert D Nowak. 13 April 2026. https://arxiv.org/abs/2604.11978 (abstract + HTML)
- Measured: 3100+ trajectories, GPT-5 variants and Claude models, four domains, horizon scaled by number of subtasks; LLM-judge attribution validated with humans (inter-annotator kappa=0.61; human-judge kappa=0.84).
- Findings: "all domains exhibit a sharp performance drop beyond small s, where success transitions abruptly from partial robustness to near-systematic failure"; process-level failures (environment, instruction, planning, error accumulation) 72.5% vs design-level (memory limitation, catastrophic forgetting, false assumptions) 27.5%; catastrophic forgetting = constraint "still present in the context but not attended to during later reasoning"; "early subplanning errors become highly path-dependent and costly to roll back."
- Relevance: supports a judge-based audit (kappa 0.84) and the idea that an early planning error makes continuing (a) a poor bet because the error is path-dependent; checking whether original constraints are still being honoured is a concrete test.

### Group 4 - Compaction / summarisation for agents and what it loses

#### S8. The Complexity Trap: Simple Observation Masking Is as Efficient as LLM Summarization for Agent Context Management
- Authors/org: Tobias Lindenbauer, Igor Slinko, Ludwig Felder, Egor Bogomolov, Yaroslav Zharov (JetBrains Research / TUM). 29 Aug 2025 (v3 Oct 2025); DL4Code workshop, NeurIPS 2025. https://arxiv.org/abs/2508.21433 ; companion post https://blog.jetbrains.com/research/2025/12/efficient-context-management/ (both fetched)
- Measured: SWE-agent (and initial OpenHands) on SWE-bench Verified (500 instances), five model configs (Qwen3 32B to Qwen3-Coder 480B, Gemini 2.5 Flash); raw vs observation masking (last 10 turns kept) vs LLM summarisation (summarise 21 turns, keep last 10).
- Findings: masking "halves cost relative to the raw agent while matching, and sometimes slightly exceeding, the solve rate of LLM summarization"; with Qwen3-Coder 480B "observation masking boosted solve rates by 2.6% compared to leaving the context unmanaged, while being 52% cheaper on average"; hybrid is 7% / 11% cheaper than masking / summarisation. With Gemini 2.5 Flash, "using LLM summarization led to agents running for an average of 52 turns, a whopping 15% longer than with observation masking"; hypothesis: "LLM-generated summaries may actually smooth over, or hide, signs indicating that the agent should already stop trying to solve the problem"; summary calls can be "more than 7% of the total cost per instance."
- Relevance: evidence that compaction removes failure signals and prolongs doomed runs. Practical implication: run the wrong-path evaluation on the pre-compaction trajectory, and have the summary explicitly record failures/dead ends rather than smoothing them.
- Caveats: the "hides stop signals" mechanism is a hypothesis; SWE-bench runs are about 50 turns, far shorter than sessions that hit a 200K+ auto-compact.

#### S9. Toward Reliable Context Compression for Long-Horizon Agents: An Empirical Study of Execution Instability (TRACE)
- Authors: Guanghui Min, Liang Wu, Mayank Darbari, Chen Chen, Liangjie Hong. 6 Aug 2026. https://arxiv.org/html/2608.06503
- Measured: recurrent compression on AppWorld under context budgets; FIFO, LLMLingua-2, structured-summary prompts (OpenClaw-style, Hermes-style), ACON, and their boundary-verified TRACE.
- Findings: summary compression 72.8% pass at 4K budget vs 42.2% for FIFO truncation; gap between P@2 (pass at least once) and P^2 (pass both runs) "widens substantially under compression"; "At 2K, the summary condition terminates in only 44.6% of samples, with 37.3% using the required form, compared with 77.2%/68.1% for FIFO"; compression adds 0.108 blocked/error actions at the first post-compaction step; failure mode "execution-state mislocalization": recent interactions "exert a weaker or distorted effect on subsequent decisions after being absorbed into the summary", causing refetching, replaying completed actions, and failure to recognise completion. TRACE: 77.1 vs 71.4 accuracy and +7.8 Pass^2 over the structured-summary prompt.
- Relevance: quantifies the hidden cost of (a). Also gives post-compaction health checks: blocked/repeated actions right after the boundary indicate a bad compaction, at which point falling back to (b) is reasonable.
- Caveats: AppWorld only; very small budgets (2K-4K) compared with production compaction; verifier "may not capture silent state corruption."

#### S10. ACON: Optimizing Context Compression for Long-horizon LLM Agents
- Authors: Minki Kang, Wei-Ning Chen, Dongge Han, Huseyin A. Inan, Lukas Wutschitz, Yanzhi Chen, Robert Sim, Saravan Rajmohan (Microsoft / KAIST). Oct 2025 (v3 June 2026). https://arxiv.org/html/2510.00615v3
- Measured: AppWorld, OfficeBench, multi-objective QA (15+ steps); compression guidelines optimised from paired trajectories where full context succeeds and compressed fails.
- Findings: peak tokens reduced "26-54%" while keeping accuracy near the no-compression upper bound; FIFO shows "severe degradation on medium and hard tasks spanning longer steps"; retrieval-based compression 27.4% vs 56.0% baseline on AppWorld; "losing a single detail such as a file path or an API parameter can derail the entire workflow"; lost items: "causal relations (e.g., email leaves drafts), evolving states (e.g., account balance), preconditions (e.g., login required), and task-relevant decision cues." Small models gain 20-46%.
- Relevance: a checklist for what a handoff summary must contain (exact identifiers, evolving state, preconditions, why decisions were made). Also shows that with a good compressor, compaction can be near-lossless - so (a) is fine when the path is right.
- Caveats: no restart baseline.

#### S11. Slipstream: Trajectory-Grounded Compaction Validation for Long-Horizon Agents
- Authors: Zhuofu Chen, Rui Pan, Yinwei Dai, Ravi Netravali (Princeton). 9 May 2026. https://arxiv.org/abs/2605.08580 (abstract)
- Findings: synchronous compaction has a "validation gap" - the compactor does not know what the agent will need, and afterwards errors propagate silently through "seemingly coherent but incorrect behaviors". Running compaction asynchronously while the agent continues on the original context yields "a validation signal independent of the summary itself"; a judge checks the summary preserves forward intent and critical facts. Up to +8.8 points accuracy on SWE-bench Verified / BrowseComp and up to 39.7% lower latency.
- Relevance: shows a judge at the compaction boundary is practical and pays off; the same hook could also evaluate trajectory health.

#### S26. Scaling Long-Horizon LLM Agent via Context-Folding
- Authors: Weiwei Sun, Miao Lu, Zhan Ling, Kang Liu, Xuesong Yao, Yiming Yang, Jiecao Chen (ByteDance Seed / CMU / Stanford). 13 Oct 2025. https://arxiv.org/abs/2510.11967 (abstract)
- Findings: agent branches into a sub-trajectory and folds it into "a concise summary of the outcome"; "matches or outperforms the ReAct baselines while using an active context 10x smaller and significantly outperforms models that rely on summarization-based context management" (Deep Research and SWE).
- Relevance: evidence that planned sub-task-scoped fresh contexts with outcome summaries (a structured form of b) beat reactive whole-history summarisation (a).
- Caveats: requires RL training (FoldGRPO); abstract only.

#### S27. Agentic Context Engineering (ACE)
- Authors: Qizheng Zhang, Changran Hu, et al. (Stanford, SambaNova, UC Berkeley). Oct 2025 (rev. March 2026). https://arxiv.org/abs/2510.04618 (abstract)
- Findings: names two failure modes of iterative context rewriting: "brevity bias, which drops domain insights for concise summaries" and "context collapse, where iterative rewriting erodes details over time"; incremental structured updates give +10.6% on agents, +8.6% on finance.
- Relevance: repeated compaction of compaction (several auto-compacts in one session) is the collapse regime; number of prior compactions is a plausible signal favouring (b) with a structured, itemised handoff.

#### S28. MEM1: Learning to Synergize Memory and Reasoning for Efficient Long-Horizon Agents
- Authors: Zijian Zhou, Ao Qu, et al. (MIT, NUS, SMART). June 2025. https://arxiv.org/abs/2506.15841 (abstract)
- Findings: RL-trained constant-memory agent; MEM1-7B gets "3.5x performance improvement while reducing memory usage by 3.7x compared to Qwen2.5-14B-Instruct on a 16-objective multi-hop QA task".
- Relevance: existence proof that discarding raw history in favour of a consolidated state can improve, not just preserve, long-horizon performance - when the model is trained for it. Not a coding benchmark.

### Group 5 - Restart / resample / verifiers

#### S23. EvoCode-Bench: Evaluating Coding Agents in Multi-Turn Iterative Interactions
- Authors: Haiyang Shen, Xuanzhong Chen, Wendong Xu, Yun Ma, Liang Chen, Kuan Li. 22 May 2026. https://arxiv.org/abs/2605.24110 (abstract verbatim)
- Measured: 26 stateful coding tasks, 227 rounds, workspace persists 5-15 rounds; 13 agents; MT@4 (four-attempt fail-stop multi-round) vs SR (single round from reference-completed prior state).
- Findings: "For most agents, SR exceeds MT@4 by 22-40 points"; highest-SR agent (78.9) gets 44.0 MT@4; "aggregate pass rate drops below half of round-1 performance by round 5"; "weaker agents fail early, while stronger agents survive long enough to expose specification-tracking and regression failures."
- Relevance: accumulated self-produced state is costly even with four retries per round; regression of earlier requirements is the late-session failure signature for strong agents - a regression test suite is the best wrong-path detector.
- Caveats: the degradation is in the workspace (code), which a context reset does not fix; abstract only.

#### S29. Training Software Engineering Agents and Verifiers with SWE-Gym
- Authors: Jiayi Pan, Xingyao Wang, Graham Neubig, Navdeep Jaitly, Heng Ji, Alane Suhr, Yizhe Zhang. Dec 2024 (rev. June 2025, ICML 2025). https://arxiv.org/abs/2412.21139 (abstract)
- Findings: verifiers trained on agent trajectories enable inference-time scaling (best-of-n over whole trajectories), reaching "32.0% and 26.0% on SWE-Bench Verified and Lite" for open-weight agents.
- Relevance: trajectory-level outcome verifiers work well enough to select among independent attempts, i.e. resampling plus a verifier is a viable alternative to one long attempt; the same verifier class can score a single in-progress trajectory.
- Caveats: abstract only; I did not fetch the scaling curves.

---

## Unverified leads (found in search results, NOT fetched; do not cite as evidence)

- "AgentStop" (arXiv 2605.15206 per a search snippet) - early termination of local agents to save energy; used as a per-step baseline in S12.
- "EET: Experience-Driven Early Termination for Cost-Efficient ..." (arXiv 2601.05777).
- "Semantic Early-Stopping for Iterative LLM Agent Loops: A Judge-Efficient Study of When to Halt" (arXiv 2606.27009) - snippet claims early stop saves about a third of work at quality plateau.
- "When May an Agent Stop? Evidence-Carrying Termination for Tool-Using LLMs" (2608.23623).
- "MAIGO: Mitigating Lost-in-Conversation with History-Cleaned On-Policy Self-Distillation" (2605.27186); "MT-OSC" (2604.08782); "Mitigating Lost in Multi-turn Conversation via Curriculum RL with Verifiable Accuracy and Abstention Rewards" (2510.18731) - follow-ups to S1.
- "SWE-MeM: Learning Adaptive Memory Management for Long-Horizon Coding Agents" (2606.28434); "Context as a Tool: Context Management for Long-Horizon SWE-Agents" (2512.22087); "ACM: Agentic Context Management for Long Horizon Tasks" (2607.23809); "Learning Agent-Compatible Context Management for Long-Horizon Tasks" (2605.30785); "LLM Agents Are Latent Context Managers ... Proprioceptive Dashboard" (2606.30005); "Parallel Context Compaction for Long-Horizon LLM Agent Serving" (2605.23296); "CoACT" (2607.02911).
- "AgentLens: Revealing The Lucky Pass Problem in SWE-Agent Evaluation" (2605.12925); "SWE-EVO" (2512.18470); "DeepSWE" (2607.07946).
- "Intelligence Degradation in Long-Context LLMs: Critical Threshold Determination ..." (2601.15300).
- Primary sources quoted second-hand in S25: Gemini 2.5 technical report (Pokemon agent; >100k-token repetition), Databricks long-context RAG study, Berkeley Function-Calling Leaderboard.
- A search snippet (source unclear) claimed "debugging degradation of 60% to 80% within two to three iterative attempts"; not traced to a paper.
- Agent process reward models / trajectory-level LLM-judge benchmarks (e.g. AgentPRM-style work) - not searched successfully in this pass.

## Gaps: what the literature does NOT answer

1. No paper found evaluates the decision at the compaction boundary specifically (compact vs handoff vs discard) as a three-way policy. S12 is the nearest and compares only continue vs cold restart vs restart-with-diff, triggered by a learned monitor rather than by context pressure.
2. No controlled comparison of restart-with-textual-summary vs restart-with-artefacts vs continue-with-compaction on the same trajectories. S12 asserts summaries anchor the new run but does not ablate it; S1 shows consolidated restart works but for user requirements in chat tasks.
3. Whether a handoff summary written by a session that is on a wrong path transmits the wrong path (poisoned summary) is documented only anecdotally (Gemini Pokemon quote via S25). No measurement of how to write a de-biased handoff (e.g. facts and artefacts only, failed hypotheses flagged, conclusions withheld).
4. Almost all agent evidence comes from SWE-bench-scale runs (tens to low hundreds of steps, no human). Interactive multi-hour sessions with user steering, evolving requirements and multiple prior compactions are essentially unstudied; EvoCode-Bench (S23) is the closest.
5. Predictors are validated for "will this run fail" not "will continuing do worse than restarting". These differ: a task the model cannot solve fails under every option (S19: the LLM dominates outcomes). No work estimates the counterfactual value of restart per instance; S12's 54.9% "recoverable partial progress" is the only related statistic.
6. Thresholds are harness- and model-specific (S14, S19), and trajectory length reverses sign when difficulty is controlled (S19). No portable, calibrated signal set exists; false-positive cost (killing a session that would have succeeded) is quantified only in S12 and S16.
7. Self-conditioning evidence (S2) is from a synthetic Markovian task; its magnitude in real coding sessions with thinking models - which S2 says largely do not self-condition - is unknown. The case for restart may be weaker for current reasoning models than the 2025 literature implies.
8. Sunk-cost accounting is missing: studies count tokens, not the human cost of re-establishing context, nor the value of uncommitted workspace state. Rollback-to-checkpoint (suggested by S20, S15) is rarely evaluated as an alternative to a/b/c.
9. LLM-as-judge agreement numbers (S21 kappa 0.77, S22 kappa 0.84) are for post-hoc failure labelling on finished trajectories, not for online go/no-go decisions on unfinished ones, and not for a judge that is the same model as the agent.
