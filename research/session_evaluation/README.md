# Session evaluation at the auto-compact point

Research done 2026-09-19 on one question: when Claude Code is about to auto-compact, can we tell
whether the session has gone wrong, and choose between compacting, handing off to a fresh session,
or starting over?

Read in this order:

1. [`DECISION.md`](DECISION.md): what we propose to build and what we will not do.
2. [`ANALYSIS.md`](ANALYSIS.md): the reasoning, with every claim tied to a source.
3. [`sources/`](sources/): the evidence.

| File | Contents | How it was gathered |
|---|---|---|
| [`sources/01-academic-literature.md`](sources/01-academic-literature.md) | 29 papers and reports, 2023 to August 2026 | Web research agent. Quotes came through a digest model |
| [`sources/02-practitioner-state-of-art.md`](sources/02-practitioner-state-of-art.md) | 31 sources: Anthropic, Amp, Codex, Factory, and the stuck detectors in OpenHands, Gemini CLI, Cline, SWE-agent | Web research agent. Source-code constants read from raw files |
| [`sources/03-claude-code-platform-capabilities.md`](sources/03-claude-code-platform-capabilities.md) | What hooks can and cannot do at compaction time | Docs research agent, official Claude Code docs |
| [`sources/04-local-evidence.md`](sources/04-local-evidence.md) | What we actually observed in our own hook log and transcript | First-hand, Claude Code v2.1.278 |
| [`sources/05-spot-check-verification.md`](sources/05-spot-check-verification.md) | Independent re-check of the claims the decision rests on | Primary pages downloaded and read directly |

Reliability note: files 01 to 03 were written by research agents. The claims that carry the
decision were re-checked by hand (file 05, plus five practitioner claims checked against the
primary pages and source code). Figures taken from paper bodies rather than abstracts are marked as
not re-checked. Treat anything else in 01 and 02 as probable until someone opens the source.
