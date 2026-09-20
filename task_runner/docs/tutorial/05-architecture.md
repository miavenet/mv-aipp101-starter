# 5 — Architecture

> [!NOTE]
> **Status: checked against stages 1–6 implementation and tests.** The
> [stage 5](../stage-5-walkthrough.md) and [stage 6](../stage-6-walkthrough.md)
> walkthroughs record executable panel and replan examples; live model checks are separate.

## The modules, and who is allowed to decide

```mermaid
flowchart TB
    subgraph pure["Pure: no I/O decisions"]
        PAT["patterns<br/>path matcher, cover, overlap"]
        WF["workflow<br/>load, expand panels, validate"]
        PR["prompts<br/>one-pass templates, fenced data, caps"]
    end
    subgraph decide["Decides"]
        ENG["engine<br/>scheduler + task lifecycle"]
        FND["findings<br/>the ledger and its rules"]
        PANEL["panels<br/>parallel readers and ordered results"]
        BUD["budgets<br/>reserve and settle spend"]
        RP["replan<br/>freeze definitions and reopen work"]
    end
    subgraph facts["Report facts only"]
        AG["agents<br/>claude, codex, any command"]
        CH["checks<br/>gates and check commands"]
        GIT["gitops<br/>snapshots, restore, commit, revert"]
        VAL["validate<br/>result shape and meaning"]
        REC["record<br/>state, intents, events, STATUS.md"]
    end
    CLI["cli"] --> ENG
    CLI --> RP
    ENG --> PANEL
    PANEL --> BUD
    RP --> GIT
    RP --> REC
    WF --> PAT
    WF --> ENG
    ENG <--> PR
    ENG <--> FND
    ENG --> AG
    ENG --> CH
    ENG --> GIT
    ENG --> VAL
    ENG <--> REC
```

Lifecycle decisions live in `engine` and its `panels` mixin. `findings` computes ledger transitions,
`budgets` reserves spending, and `replan` coordinates definition changes and reverts. Agent and
command adapters report observations. The pure ledger transitions and scripted execution tests
exercise decisions without paid model calls.

## The engine loop

```mermaid
flowchart TB
    L["load frozen workflow and reconcile intents"] --> S["settle completed work and mark skipped dependants"]
    S --> A{"active producer?"}
    A -- yes --> P["advance its transaction:<br/>author, gates, check/panel batch,<br/>rework, acceptance or set-aside"]
    P --> W{"needs a pause?"}
    W -- no --> S
    W -- yes --> STOP["stop with recorded state"]
    A -- no --> N{"next ready task?"}
    N -- producer --> B["begin producer transaction"] --> S
    N -- check --> C["run standalone check"] --> S
    N -- human --> H["mark waiting for approval"] --> S
    N -- none --> STOP
    classDef stop fill:#a32d2d,stroke:#741f1f,color:#ffffff
    class STOP stop
```

Given the same workflow and the same results from agents, the same things happen in the same order.

## The producer transaction

Serial *processes* are not serial *transactions*. If producer A finished writing and independent
producer B started before A's panel ran, B would build on unaccepted work, and B's changes would
leak into A's review and A's commit. So the unit of exclusion is the whole life of a producer.

```mermaid
gantt
    title One producer owns the work tree from first write to commit
    dateFormat YYYY-MM-DD HH:mm
    axisFormat %H:%M
    todayMarker off
    section Producer A (active)
    agent writes            :a1, 2026-01-01 00:00, 4h
    gates (writer, alone)   :a2, after a1, 2h
    commit                  :a5, after r1, 1h
    section A's readers (parallel)
    principal engineer review :r1, after a2, 4h
    spec compliance review    :r2, after a2, 3h
    read-only check           :r3, after a2, 2h
    section Producer B
    waits for A's transaction to end :crit, b0, 2026-01-01 00:00, 11h
    agent writes            :b1, after a5, 4h
```

The hour marks illustrate ordering and overlap; they are not estimates of actual run time.

Inside a transaction, either **one writer** runs or a reader batch runs, never both. A batch
has at most `max_parallel` readers and completes before its results are applied in task order.
Standalone checks are sequential; concurrent readers belong to the active producer’s panel.

## Driving agents

One interface, three adapters. The runner never imports a model SDK; it starts command-line tools
in headless mode and reads what they print.

```mermaid
flowchart LR
    ENG["engine"] --> IF["Agent.run(prompt, cwd, invocation_dir,<br/>schema, session_id, model,<br/>timeout, budget, read_only, env)"]
    IF --> CC["Claude Code<br/>claude -p --output-format json<br/>--json-schema, --max-budget-usd, --resume"]
    IF --> CX["Codex<br/>codex exec --json -<br/>--output-schema, exec resume ID"]
    IF --> CMD["any command<br/>prompt on stdin,<br/>last JSON object in stdout"]
    CC --> RES["AgentResult:<br/>status, structured answer,<br/>session id, cost or None, usage"]
    CX --> RES
    CMD --> RES
```

### What counts as a result

A call has succeeded only when **all four** hold:

```mermaid
flowchart LR
    A["1. process exited normally"] --> B["2. a successful terminal event<br/>of THIS invocation"]
    B --> C["3. final answer written by THIS invocation<br/>(fresh directory, created exclusively)"]
    C --> D["4. passes the runner's own validator:<br/>shape, then meaning"]
    D --> OK["a result"]
    A -. fails .-> PE["protocol error / agent error /<br/>environment failure"]
    B -. fails .-> PE
    C -. fails .-> PE
    D -. fails .-> PE

    classDef ok fill:#2d6a4f,stroke:#1b4332,color:#ffffff
    classDef stop fill:#a32d2d,stroke:#741f1f,color:#ffffff
    class OK ok
    class PE stop
```

A provider's schema feature makes valid answers likelier; it is never the check. A failing test
*inside* an agent's session is ordinary work, not a failed call. A sandbox that cannot start is an
**environment failure**: it stops the run and uses no attempt, because retrying the work cannot fix
the machine.

### Capabilities are qualified, not assumed

Answering a greeting proves nothing about reading files. `doctor` tests each agent profile per
capability, and every probe is judged by an **effect the runner observes itself**:

| Capability | Proof |
|---|---|
| `answer` | the exact expected object comes back |
| `read` | a random value that exists only in a scratch file appears in the answer |
| `execute` | a probe script writes a SHA-256 digest a model cannot compute without running it |
| `write` | the runner reads the expected change back |
| `resume` | a second call on the session id returns a value given only in the first |
| `boundary` | a sentinel file is unchanged after the agent was asked to modify it read-only |

Types state what they `require`; `doctor` and `start` refuse a workflow whose profiles fall short.
`validate` does not check this, so it works with no agent installed.

## Observability

`activity` routes native hook logs into each invocation. Codex exec events also pass through the
existing logger with an explicit `ExecStream.*` origin. `runner activity` reads these logs while
agents run. Observations do not decide acceptance. See [headless observability](../headless-observability.md).

## Prompts

Prompts are assembled deterministically, in **one pass over the template only**: substituted text
is never scanned again, so a diff containing `{rules}` or stray braces is harmless. Everything that
comes from a task, an agent or the repository is wrapped in a labelled data block, and the standing
rules distinguish the workflow task specification from repository and agent evidence; no block overrides runner boundaries. Prompts carry pointers and summaries, not
file contents; the agent reads the files itself.

## Limits

| Limit | Default | Enforced by |
|---|---|---|
| attempts per producer | 3 | engine |
| protocol retries per call | 2 | engine |
| time per agent call / per command | 30 min / 20 min | the runner's own clock; whole process group is stopped |
| money per call | $5 | the agent, where it can |
| money per run | $50 | engine, **by reservation** before each call |
| parallel readers | 4 | scheduler |

Reservation means four reviewers cannot each start a $5 call with $1 left. Spend is always reported
as three numbers, known, reserved and unpriced, because Codex reports tokens but no cost, and the
runner does not invent dollars.

---

| Previous | | Next |
|:--|:-:|--:|
| [4 — Safety: git, the record and recovery](04-safety-git-and-recovery.md) | [Contents](README.md) | [6 — Writing a workflow](06-writing-a-workflow.md) |

**Reference:** [05 — Architecture](../05-architecture.md).
