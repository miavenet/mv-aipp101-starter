# 2 — A task, end to end

> [!NOTE]
> **Status: design, with the stage 3 subset implemented**. Producer transactions, gates, checks,
> human decisions and the command adapter now run; panels, headless adapters and budgets remain
> later-stage work. See the [verified CLI walkthrough](../stage-3-walkthrough.md).

This chapter follows one producer, `implement`, from the moment it becomes ready to the moment its
work is a commit. Everything else in the runner exists to make this path trustworthy.

## The states a task passes through

```mermaid
stateDiagram-v2
    [*] --> pending
    pending --> ready: everything in needs is accepted
    pending --> skipped: something upstream failed or is blocked
    ready --> running: becomes the active producer
    running --> verifying: attempt passed the free checks
    running --> rework: output missing, or wrote outside writes
    verifying --> rework: a gate, check, reviewer or person sent it back
    rework --> running: next attempt
    verifying --> waiting_human: needs approval, or a finding is escalated
    waiting_human --> verifying: approved, or finding settled
    waiting_human --> rework: rejected, or finding upheld
    verifying --> accepted: every verifier passed on one candidate
    running --> blocked: agent answered blocked
    rework --> failed: attempts used up on gates, or no progress
    rework --> blocked: attempts used up with findings open
    accepted --> [*]
    failed --> [*]
    blocked --> [*]
    skipped --> [*]

    classDef ok fill:#2d6a4f,stroke:#1b4332,color:#ffffff
    classDef rework fill:#8a6100,stroke:#5e4200,color:#ffffff
    classDef human fill:#a23b72,stroke:#742951,color:#ffffff
    classDef stop fill:#a32d2d,stroke:#741f1f,color:#ffffff
    classDef aside fill:#64748b,stroke:#475569,color:#ffffff
    class accepted ok
    class rework rework
    class waiting_human human
    class failed,blocked stop
    class skipped aside
```

`failed` means the run could not do it (exit code 2). `blocked` and `waiting_human` mean a person
is needed (exit code 255).

## The acceptance ladder

An attempt climbs a ladder of verifiers, **cheapest first**. The first failure stops the climb and
sends the work back, so money is never spent reviewing work that does not build.

```mermaid
flowchart TB
    A["agent finishes an attempt"] --> S1{"1. call completed properly,<br/>answer valid, not 'blocked'?"}
    S1 -- no --> X1["protocol retry (max 2),<br/>or BLOCKED"]
    S1 -- yes --> S2{"2. every output exists,<br/>every 'removes' path gone?"}
    S2 -- no --> RW["feedback to author<br/>next attempt"]
    S2 -- yes --> S3{"3. nothing changed outside 'writes',<br/>nothing protected or frozen touched?"}
    S3 -- no --> RV["runner reverts those paths"] --> RW
    S3 -- yes --> C["snapshot = CANDIDATE<br/>(a git tree id, pinned)"]
    C --> S4{"4. own gates exit 0?"}
    S4 -- no --> RW
    S4 -- yes --> S5{"5. verifying checks pass?"}
    S5 -- no --> RW
    S5 -- yes --> S6{"6. review panel leaves no<br/>open blocking finding?"}
    S6 -- no --> RW
    S6 -- yes --> S7{"7. verifying human approves?"}
    S7 -- no --> RW
    S7 -- yes --> ACC["ACCEPTED:<br/>commit exactly CANDIDATE,<br/>freeze outputs"]

    classDef free fill:#e2e8f0,stroke:#94a3b8,color:#111111
    classDef cheap fill:#94a3b8,stroke:#64748b,color:#111111
    classDef costly fill:#475569,stroke:#334155,color:#ffffff
    classDef ok fill:#2d6a4f,stroke:#1b4332,color:#ffffff
    classDef rework fill:#8a6100,stroke:#5e4200,color:#ffffff
    classDef stop fill:#a32d2d,stroke:#741f1f,color:#ffffff
    class S1,S2,S3 free
    class S4,S5 cheap
    class S6,S7 costly
    class ACC ok
    class RW rework
    class X1 stop
```

The darker the step, the more it costs: pale steps are free, mid-grey steps cost seconds to
minutes, dark steps cost agent calls or a person's time. A producer must have at least one of steps 4 to 7, or the workflow is rejected when it loads.

## Every result is tied to one candidate

Here is the subtle point. A gate might pass, and then a later check might quietly rewrite a source
file. If the runner committed the tree at that moment, it would commit something no gate ever saw.

So after step 3 the runner records the candidate's tree id, and:

- every gate, check, verdict and approval is stored **with that tree id**;
- after every verifier the runner takes a new snapshot and compares;
- if the tree differs, the runner puts the candidate back, voids the earlier results, and the
  attempt does not pass. The feedback names the command and the files.

```mermaid
sequenceDiagram
    participant E as engine
    participant G as git (snapshots)
    participant V as verifier (gate, check, reviewer)
    E->>G: snapshot after attempt
    G-->>E: CANDIDATE = tree f8d1c79
    loop each verifier, cheapest first
        E->>V: run against the work tree
        V-->>E: pass / fail
        E->>G: snapshot again
        G-->>E: tree id
        alt tree id == CANDIDATE
            E->>E: store result bound to f8d1c79
        else tree changed
            E->>G: restore CANDIDATE
            E->>E: void all results, attempt does not pass
        end
    end
    E->>G: commit exactly f8d1c79
```

Two honest exceptions exist. A check whose job is to change source and put it back, such as a
mutation tester, is marked `restores = true`: the runner restores the candidate itself afterwards,
even if the tool crashed. And a check marked `read_only` may run beside reviewers, but the claim is
verified by snapshot, not believed.

## Rework

A rework is a new **attempt**, in a new numbered directory. The author is told two things:

1. the immediate cause: gate output, check output, rejection note or new findings;
2. every open blocking finding that still needs a response from it.

If the agent supports continuing a session, the rework continues it, which keeps its understanding
and reuses the provider's cache. If not, or after a timeout or crash, a fresh session gets the full
prompt plus the feedback. The rules are the same either way.

Three counters are kept strictly apart:

| Counter | Counts | Limit |
|---|---|---|
| Producer attempts | each time the author runs, whatever sent it back | `max_attempts`, default 3 |
| Review rounds | per reviewer: the first time it sees a candidate is its round 1 | none of its own |
| Protocol retries | a call that ended without a proper result or with an invalid answer | 2 per call |

A protocol retry is a fault of the *call*, not of the work: it never uses an attempt and never
becomes a finding.

**No progress.** The task fails early only when the gate fails the same way **and** the candidate
tree is identical to the previous attempt's. The same error text after a real change is not "no
progress".

## When it goes wrong

```mermaid
flowchart LR
    F["task FAILED or BLOCKED"] --> P1["pin the candidate tree<br/>under refs/task-runner/&lt;run&gt;/"]
    P1 --> P2["write failed.patch<br/>(complete, binary-safe)"]
    P2 --> P3["restore the task's paths<br/>to the last accepted state"]
    P3 --> P4["verify by snapshot:<br/>tree == BASE"]
    P4 --> P5["mark dependants 'skipped'"]
    P5 --> P6["other branches of the DAG continue"]

    classDef stop fill:#a32d2d,stroke:#741f1f,color:#ffffff
    class F stop
```

Nothing is thrown away. `retry TASK --apply-patch` puts the work back if its base still matches;
without the flag, attempts start clean.

---

| Previous | | Next |
|:--|:-:|--:|
| [1 — The idea](01-the-idea.md) | [Contents](README.md) | [3 — Review panels and findings](03-review-panels-and-findings.md) |

**Reference:** [02 — Concepts, Acceptance and Rework](../02-concepts.md#acceptance-d7),
[05 — Producer lifecycle](../05-architecture.md#producer-lifecycle).
