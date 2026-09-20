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
      briefs/                         frozen content of every prompt_file (A10)
      qualification.json              what doctor established for each agent profile, per capability (A5)
      integrity.json                  hashes of the decision-bearing files, checked around every job (B8)
      git-index                       the run's scratch index, reused so snapshots use git's stat cache (B2)
      replans/
        001/  before.toml  after.toml  changes.json  reverts.json
      tasks/
        010-design/                   <order>-<task id>; order leaves gaps for replanned tasks
          task.json                   the resolved task definition
          STATUS.md                   this task in words
          index.json
          findings.json               the findings ledger for this producer (all reviewers, all rounds)
          attempt-1/                  numbered once per task and never reused, even after `retry`
            prompt.md                 exactly what the agent was sent
            invocation-1/             one per agent call. Created exclusively, so nothing stale is ever read (A6)
              argv.json               exactly how it was invoked. Never holds credentials
              stdout.log  stderr.log  streamed as they arrive, so a crash loses nothing
              last-message.txt
              schema.json
              outcome.json            ok | protocol-error | agent-error | timed-out | interrupted | environment
            invocation-2/             only after a protocol retry
            result.json               the validated answer, plus cost, usage, seconds, session id
            inputs.json               hashes of the upstream outputs this attempt was given (A10)
            outputs.json              manifest: each declared output with hash, mode and size; the candidate tree id
            changes.diff              readable diff of this attempt, capped. For reading, never for recovery
            reverted.json             only if the runner put back files outside `writes`, or protected or frozen ones
            gate.log                  only if gates ran
            verification.json         each gate, check and verdict with the candidate tree id and config hash it judged (A9)
          attempt-2/                  a rework. Also holds:
            feedback.md               the consolidated findings the author was sent
            responses.json            the author's answer to each finding
          failed.patch                only if the task was set aside (D9): a complete binary-capable patch.
                                      Its candidate tree is also pinned under refs/task-runner/<run>/
          commit.json                 only when accepted: sha, files, message
        011-design.review.principal-engineer/
          task.json  STATUS.md  index.json
          round-1/                    counted per reviewer: its first sight of a candidate (A7)
            prompt.md
            invocation-1/             as for a producer; invocation-2/ after a protocol retry (B8)
            verdict.json              the validated answer, the candidate it judged, the diff base it was shown
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
2. **Write once.** An attempt, round or invocation directory is never modified after it is finished.
   A retry, a rework or a protocol retry makes a new directory, with a number that is never reused.
   So the record of what happened cannot be rewritten by what happened next. This is enforced by
   hashes (rule 4), **not by file modes** (B8): read-only directories would stop `status --rebuild`
   from regenerating the `index.json` inside them, and would make `rm -rf` of an old run fail.
   `STATUS.md` and `index.json` are derived files and are outside the write-once rule.
3. **Durable state, and intents before effects (A2).** `state.json` is written to a temporary file,
   flushed and synced, renamed, and its directory synced. Before any external effect (an agent call,
   a commit, a restore, a revert) the state records the **intent** with a unique operation id; after
   it, the **outcome**. `resume` reconciles every intent that has no outcome. See
   [05, Crash recovery](05-architecture.md#crash-recovery-a2).
4. **The record protects itself (A9, B8).** `.runs/` is ignored by git, so work-tree snapshots cannot
   see an agent tampering with it. The runner therefore keeps `integrity.json`: the hashes of every
   **decision-bearing file**, which are `state.json`, every `findings.json`, and every `result.json`,
   `verdict.json`, `verification.json`, `outputs.json` and `decision.json` in a finished directory.
   It checks them before and after every agent call and every command, and treats a change it did
   not make as a failure of that job. The ledger decides every verdict, so it is covered from the
   first finding, not only once something is closed.
5. **No secrets by intent.** The runner passes no credentials. Agent output is stored as the agent
   printed it, after token/key/bearer-header redaction in `proc.py`. Lines over 64 KiB are replaced
   with `[overlong line omitted for safe redaction]`: a token split at a read boundary must not leak,
   and log buffering must stay bounded. Command answers therefore need a final JSON object on
   lines within this limit and within the 256 KiB retained output tail.
6. **Self-ignoring.** `.runs/.gitignore` holds `*`. Committing a run record is the owner's choice.
7. **Linked to the hook log.** The run UUID and task id are exported to every agent call as
   `TASK_RUNNER_RUN` and `TASK_RUNNER_TASK`, so the repository's hook logger ties each driven
   session to its task. `TASK_RUNNER_RUN_DIR` is exported **only to tasks whose type sets
   `needs_run_dir = true`** (B8), which in the starter library is `summarize` alone. Gates and checks
   never receive it.

## `run.json`

```json
{
  "run_id": "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
  "workflow": "book-module",
  "workflow_sha256": "…",
  "root": "/workspace",
  "workflow_file": "/workspace/workflows/book-module.toml",   // resolved paths are recorded (B4)
  "branch": "run/book-module-1a2b3c4d",      // with branch = "current": the branch that was checked out; none is created
  "original_branch": "main",                 // what was checked out before `start` (B2)
  "base_commit": "61d0921",
  "started": "2026-09-19T20:15:00Z",
  "runner_version": "0.1.0",
  "agents": {"claude": "2.1.278", "codex": "0.155.1"},
  "status": "running",
  "spend": {
    "known_usd": 3.12,                       // reported by agents that report cost
    "reserved_usd": 5.00,                    // caps of calls in flight (A11)
    "unpriced": {"calls": 2, "tokens_in": 48211, "tokens_out": 1930, "unknown_calls": 0}
  },
  "seconds": 1840
}
```

`status` is one of `running`, `done`, `failed`, `needs_human`, `stopped`.

The identity fields are written once at `start`. `status`, `spend`, `seconds` and `run_budget_usd` are **copied in
from `state.json`** whenever the derived files are regenerated, so rule 1 holds: the engine never
reads them back. `run.json` also records `name`, `git_toplevel`, `library` and `branch_mode`.
Task order numbers step by 10 for tasks written in the workflow; generated panel members take the
producer's number plus 1, 2, … . `state.json` is guarded by a before-and-after hash around each job
rather than by `integrity.json`, because the runner itself rewrites it constantly.

## Task status values

| Status | Meaning |
|---|---|
| `pending` | Waiting for its `needs` |
| `ready` | Could run now |
| `running` | An agent or a command is working |
| `verifying` | A producer's attempt is with its checks or reviewers |
| `rework` | A producer is about to run another attempt |
| `accepted` | Done: verified, and for a producer, committed and frozen. For a review, check or human task: passed |
| `objected` | A verifier whose latest round did not pass. It runs again if its producer is reworked; it is final if the producer ends `blocked` or `failed` (B7) |
| `waiting_human` | Stopped for a person: an approval, or an escalated finding (B10). The tree is held |
| `blocked` | A person is needed: the agent said it cannot do this properly, attempts ran out with findings open, a panel cannot produce a valid answer, or a standalone `human` task was rejected |
| `failed` | Attempts used up on gates, no progress, a reviewer changed the tree, or a standalone check did not pass |
| `skipped` | It could not run: something it `needs` failed or is blocked, or the producer it `reviews` or `verifies` ended before it ran (B7) |

## Result schemas

Every agent answer ends with one JSON object. All schemas are strict (`additionalProperties: false`,
every property required), which Codex needs and the others accept.

**Produce**

```json
{
  "outcome": "done",                        // or "blocked"
  "summary": "What was made, in a few sentences. Shown to downstream tasks.",
  "blocked_reason": "",
  "responses": [                            // on rework: exactly the findings feedback.md lists as needing a response (B1)
    {"finding": "implement/PE-2", "action": "fixed", "note": "…"}   // or "disputed"
  ]
}
```

**Review**

```json
{
  "verdict": "block",                       // or "pass". "block" requires at least one blocking finding
  "summary": "Overall assessment.",
  "findings": [                             // new findings this round. caused_by: later rounds only (A7)
    {"severity": "blocking", "title": "…", "detail": "…", "location": "src/book/side.hpp:41", "caused_by": ""}
  ],
  "resolutions": [                          // later rounds: one per open BLOCKING finding of this reviewer; else empty (B1)
    {"finding": "implement/PE-2", "status": "resolved", "note": "…"}   // or "unresolved"
  ]
}
```

The runner, not the agent, assigns finding ids and enforces that an advisory reviewer cannot block.
**Whether a reviewer blocks is computed from the ledger** once its answer is applied: an old finding
left `unresolved` blocks even when `findings` is empty, and a `verdict` that disagrees with the
computed result makes the answer invalid (A7). In a later round, a new blocking finding stands if its
`location` is inside the rework diff, or if its `caused_by` names a location that is; the runner
checks the named location against the diff. Otherwise it is recorded as advisory.

Every answer is validated by the runner itself before it is used (A6): shape first, then meaning.
An invalid answer is a protocol error and is retried; it never becomes a finding or a rework.

## `findings.json` (the ledger)

```json
{
  "producer": "implement",
  "reviewers": {                             // the base of each reviewer's next rework diff (B1)
    "implement.review.principal-engineer": {"round": 2, "last_seen_candidate": "f8d1c79…"}
  },
  "findings": [
    {
      "id": "implement/PE-2", "reviewer": "implement.review.principal-engineer", "persona": "principal-engineer",
      "severity": "blocking", "title": "…", "detail": "…", "location": "src/book/side.hpp:41",
      "status": "resolved",
      "history": [
        {"round": 1, "attempt": 1, "event": "raised"},
        {"attempt": 2, "event": "author:fixed", "note": "…"},      // author events carry the attempt only (B1)
        {"round": 2, "attempt": 2, "event": "reviewer:resolved", "note": "…"}
      ]
    }
  ]
}
```

## `STATUS.md` (run level), by example

```markdown
# book-module — run 1a2b3c4d — needs a person

Started 2026-09-19 20:15 UTC. 31 min of agent time. Branch run/book-module-1a2b3c4d.
Spend: $3.12 known of $50.00, $0.00 reserved, plus 2 unpriced Codex calls (48k tokens in, 2k out).

| # | Task | Type | Status | Attempts | Cost | Commit |
|---|---|---|---|---|---|---|
| 010 | design | design | accepted | 2 | $0.84 | 3b098a6 |
| 011 | design.review.principal-engineer | design-review | accepted | 2 rounds | $0.41 | |
| 012 | design.review.spec-compliance | design-review | accepted | 1 round | $0.22 | |
| 020 | implement | implement | waiting_human | 2 | $1.65 | |
| 021 | implement.review.principal-engineer | code-review | accepted | 2 rounds | $0.52 | |
| 022 | implement.review.spec-compliance | code-review | objected | 2 rounds | $0.47 | |
| 030 | signoff | human | pending | | | |

## Needs attention
- **implement** is waiting for a person: finding implement/SC-1 is disputed by the author and kept
  open by spec-compliance. See tasks/020-implement/findings.json. The candidate is still in the work
  tree, which the run is holding; do not edit it.

## Next
    runner resolve RUN implement/SC-1 --as resolved|advisory|upheld -m "why"
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
    "invocation-1/": "Raw invocation and output of the agent process"
  }
}
```

## Stage 4 qualification and preflight records

At repository level, `.runs/qualification-cache.json` holds fingerprinted entries and
`.runs/qualification.json` holds the latest report. `.runs/doctor/<uuid>/<fingerprint>/invocation-N/`
keeps each probe prompt, command, streamed output and outcome. `.runs/check-gates/<uuid>/` keeps
command logs and `results.json`. These are operational records, not workflow runs.

Each workflow run has `qualification.json`, with the observed capabilities and their provenance;
`run.json.agents` records version, profile, model, host and configuration hashes. Task state records
the qualification key and capabilities used. Explicit text-only review calls record `evidence.json`
and `review-mode.json` alongside their invocation logs.
