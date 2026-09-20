# 04 — The run directory

One directory per run (D2, D11). It is laid out like a build directory: everything produced along
the way is kept, in a fixed hierarchy, and nothing in it is needed to understand the repository
itself. Deliverables live in the repository (D3); this is the record of how they came to be.

## Layout

```
.runs/
  .gitignore                          "*": the record ignores itself
  README.md                           explains this layout, once, for any person or agent
  <workflow>/
    latest                            text file: the newest run's directory name
    20260919T201500Z-1a2b3c4d/        <UTC start>-<first 8 of the run UUID>
      run.json                        identity and totals
      STATUS.md                       the run in words. Regenerated on every state change
      index.json                      what every file and directory here is
      state.json                      the engine's state. The single source of truth
      events.jsonl                    append-only log, one event per line
      workflow.toml                   frozen copy of the workflow as started (D12)
      workflow.expanded.json          every task after types, personas, panels and defaults are applied
      library/                        frozen copies of the type and persona files this run uses
      replans/
        001/  before.toml  after.toml  changes.json
      tasks/
        010-design/                   <order>-<task id>; order leaves gaps for replanned tasks
          task.json                   the resolved task definition
          STATUS.md                   this task in words
          index.json
          findings.json               the findings ledger for this producer (all reviewers, all rounds)
          attempt-1/
            prompt.md                 exactly what the agent was sent
            agent/
              argv.json               exactly how it was invoked
              stdout.log  stderr.log
              last-message.txt
              schema.json
            result.json               the agent's structured answer, plus cost, tokens, seconds, session id
            outputs.json              manifest: each declared output, with hash and size
            changes.diff              everything this attempt changed
            protected-reverted.json   only if the runner put files back
            gate.log                  only if gates ran
          attempt-2/                  a rework. Also holds:
            feedback.md               the consolidated findings the author was sent
            responses.json            the author's answer to each finding
          failed.patch                only if the task was set aside (D9)
          commit.json                 only when accepted: sha, files, message
        011-design.review.principal-engineer/
          task.json  STATUS.md  index.json
          round-1/                    rounds line up with the producer's attempts
            prompt.md  agent/  verdict.json
          round-2/
        012-design.review.spec-compliance/
        020-implement/
        030-signoff/
          task.json  STATUS.md
          decision.json               who approved or rejected, when, and the comment
```

## Rules of the record

1. **`state.json` is the only thing the engine reads back.** Everything else is written for readers.
   Deleting every `STATUS.md` and `index.json` loses nothing; `runner status --rebuild` regenerates them.
2. **Write once.** An attempt or round directory is never modified after it is finished. A retry or a
   rework makes a new directory. So the record of what happened cannot be rewritten by what happened next.
3. **Atomic state.** `state.json` is written to a temporary file and renamed.
4. **No secrets by intent.** The runner passes no credentials. Agent output is stored as the agent
   printed it, after the same redaction patterns the hook logger uses (tokens, keys, bearer headers).
5. **Self-ignoring.** `.runs/.gitignore` holds `*`. Committing a run record is the owner's choice.
6. **Linked to the hook log.** The run UUID and task id are exported to every agent call as
   `TASK_RUNNER_RUN`, `TASK_RUNNER_TASK` and `TASK_RUNNER_RUN_DIR`, so the repository's hook logger ties each driven session
   to its task, and its session scorecard can be found from the record.

## `run.json`

```json
{
  "run_id": "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
  "workflow": "book-module",
  "workflow_sha256": "…",
  "root": "/workspace",
  "branch": "run/book-module-1a2b3c4d",
  "base_commit": "61d0921",
  "started": "2026-09-19T20:15:00Z",
  "runner_version": "0.1.0",
  "agents": {"claude": "2.1.278", "codex": "0.155.1"},
  "status": "running",
  "cost_usd": 3.12,
  "tokens": {"in": 0, "out": 0},
  "seconds": 1840
}
```

`status` is one of `running`, `done`, `failed`, `needs_human`, `stopped`.

## Task status values

| Status | Meaning |
|---|---|
| `pending` | Waiting for its `needs` |
| `ready` | Could run now |
| `running` | An agent or a command is working |
| `verifying` | A producer's attempt is with its checks or reviewers |
| `rework` | A producer is about to run another attempt |
| `accepted` | Done: verified, and for a producer, committed and frozen. For a review, check or human task: passed |
| `waiting_human` | Stopped for a person |
| `blocked` | The agent said it cannot do this properly, or a finding was escalated |
| `failed` | Attempts used up, no progress, no usable verdict, or a reviewer changed the tree |
| `skipped` | An upstream task failed or is blocked |

## Result schemas

Every agent answer ends with one JSON object. All schemas are strict (`additionalProperties: false`,
every property required), which Codex needs and the others accept.

**Produce**

```json
{
  "outcome": "done",                        // or "blocked"
  "summary": "What was made, in a few sentences. Shown to downstream tasks.",
  "blocked_reason": "",
  "responses": [                            // on rework: one per blocking finding received
    {"finding": "PE-2", "action": "fixed", "note": "…"}      // or "disputed"
  ]
}
```

**Review**

```json
{
  "verdict": "block",                       // or "pass". "block" requires at least one blocking finding
  "summary": "Overall assessment.",
  "findings": [                             // new findings this round
    {"severity": "blocking", "title": "…", "detail": "…", "location": "src/book/side.hpp:41"}
  ],
  "resolutions": [                          // later rounds: one per open finding of this reviewer
    {"finding": "PE-2", "status": "resolved", "note": "…"}   // or "unresolved"
  ]
}
```

The runner, not the agent, assigns finding ids, enforces that an advisory reviewer cannot block, and
downgrades to advisory any new blocking finding in a later round whose location lies outside the
rework diff.

## `findings.json` (the ledger)

```json
{
  "producer": "implement",
  "findings": [
    {
      "id": "PE-2", "reviewer": "implement.review.principal-engineer", "persona": "principal-engineer",
      "severity": "blocking", "title": "…", "detail": "…", "location": "src/book/side.hpp:41",
      "status": "resolved",
      "history": [
        {"round": 1, "event": "raised"},
        {"round": 2, "event": "author:fixed", "note": "…"},
        {"round": 2, "event": "reviewer:resolved", "note": "…"}
      ]
    }
  ]
}
```

## `STATUS.md` (run level), by example

```markdown
# book-module — run 1a2b3c4d — needs a person

Started 2026-09-19 20:15 UTC. 31 min of agent time. $3.12 of $50.00. Branch run/book-module-1a2b3c4d.

| # | Task | Type | Status | Attempts | Cost | Commit |
|---|---|---|---|---|---|---|
| 010 | design | design | accepted | 2 | $0.84 | 3b098a6 |
| 011 | design.review.principal-engineer | design-review | accepted | 2 rounds | $0.41 | |
| 012 | design.review.spec-compliance | design-review | accepted | 1 round | $0.22 | |
| 020 | implement | implement | blocked | 2 | $1.65 | |
| 030 | signoff | human | skipped (upstream blocked) | | | |

## Needs attention
- **implement** is blocked: finding SC-1 is disputed by the author and kept open by spec-compliance.
  See tasks/020-implement/findings.json. Its work is set aside in tasks/020-implement/failed.patch.

## Next
    runner retry RUN implement --apply-patch      after settling SC-1
    runner resume RUN
```

## `index.json`, by example

```json
{
  "path": "tasks/020-implement/attempt-2",
  "about": "Second attempt of task 'implement': a rework after review round 1",
  "files": {
    "prompt.md": "The prompt sent to the agent",
    "feedback.md": "The consolidated findings the author was asked to address",
    "result.json": "The agent's structured answer, with cost and session id",
    "responses.json": "The author's answer to each finding",
    "changes.diff": "Everything this attempt changed in the repository",
    "outputs.json": "Manifest of the declared output files after this attempt",
    "gate.log": "Output of the gate commands",
    "agent/": "Raw invocation and output of the agent process"
  }
}
```
