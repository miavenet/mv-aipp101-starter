# Spot checks of the claims the decision rests on

Done 2026-09-19 by the main session, not by the research agent. Each claim was checked against the
primary source: the local clones (attractor `fb57a55`, agate `ea95448`), the raw docs page, or the
installed binary (`claude` v2.1.278).

| # | Claim | Checked against | Result |
|---|---|---|---|
| 1 | The spec allows CLI agents such as Claude Code as the backend | `attractor-spec.md` §1.4, line 58: "spawn CLI agents (Claude Code, Codex, Gemini CLI) in subprocesses" | **Confirmed** |
| 2 | The backend seam is one function, `run(node, prompt, context) -> String \| Outcome` | `attractor-spec.md:713-716` | **Confirmed** |
| 3 | Edge selection is a fixed five-step order: condition, preferred label, suggested next IDs, weight, lexical | `attractor-spec.md:410-418` | **Confirmed** |
| 4 | Status File Contract: `outcome`, `preferred_label`, `suggested_next_ids`, `context_updates`, `notes`; only `outcome` is required | Appendix C, `attractor-spec.md:2053-2079` | **Confirmed** |
| 5 | agate rebuilds all state from disk on each call | `internal/workflow/state.go:39`, `func GetStatus(fsys fs.FS)` | **Confirmed** |
| 6 | `agate auto` re-runs `agate next` as a subprocess and acts on exit codes | `cmd/auto.go:120-147` | **Confirmed** |
| 7 | agate's review gate is a substring test for `APPROVED` | `internal/workflow/next.go:371-374` | **Confirmed**, word for word |
| 8 | agate has no git integration and no DOT engine | `grep '"git"'` and `grep -i 'digraph\|graphviz'` over the repo: no hits | **Confirmed** |
| 9 | A blocking Stop hook is overridden after 8 consecutive blocks | `hooks.md`, Stop input section: "Claude Code overrides the hook and ends the turn after 8 consecutive blocks" | **Confirmed** |
| 10 | `--bare` skips hooks and `CLAUDE.md`, and never reads OAuth credentials | `claude --help`, lines 40-48 | **Confirmed**. The auth part matters: see the analysis |
| 11 | `--max-budget-usd`, `--json-schema`, `--session-id`, `--fork-session`, `--settings`, `--permission-mode` exist | `claude --help` | **Confirmed** |
| 12 | `--max-turns` is documented but not in `--help` | `claude --help \| grep max-turns`: no hit | **Confirmed absent from help.** Not relied on |
| 13 | There is no wall-clock timeout flag | `claude --help \| grep -i timeout`: no hit | **Confirmed** |
| 14 | `disableAllHooks` is a documented setting | `hooks.md:734` | **Confirmed** |
| 15 | Third-party Attractor implementations exist | GitHub API: `allouis/attractor` (Go), `samueljklee/attractor` (Python, 27 stars), `jmccarthy/attractor-c` (C, 11 stars), `strongdm/attractorbench` | **Confirmed**. All small |
| 16 | Beads is a widely used git-backed task graph | GitHub API: `gastownhall/beads`, Go, 27k stars, pushed today | **Confirmed** |

Not checked, and therefore not relied on: the dollar figures for runaway-cost incidents, the "Dark
Factory" thresholds, and the statement in `03-landscape.md` that Claude Code has `/goal` and `/batch`
commands. Nothing in the decision depends on them.

Not testable without spending money: whether `--permission-mode auto --permission-prompts none`
behaves as documented in this container, and the exact exit code for a budget stop. Both are the
first thing the runner's smoke test must establish.
