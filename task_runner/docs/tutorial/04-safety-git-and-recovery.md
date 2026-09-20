# 4 — Safety: git, the record and recovery

> [!NOTE]
> **Status: partly verified at stage 3.** Snapshots, restore, commit, intent recovery, write protection
> and human pauses are exercised through the engine and the CLI. See the
> [walkthrough](../stage-3-walkthrough.md). Review panels and replan remain design for later stages.

The runner lets agents write to your repository unattended. This chapter explains why that cannot
corrupt it, even when an agent misbehaves, a gate misbehaves, or the machine dies mid-step.

## One primitive: the snapshot

Almost every safety property rests on one operation: **hash the whole work tree into a git tree
id**, without touching your index or your files.

```mermaid
flowchart LR
    WT["work tree<br/>(tracked files + untracked files<br/>git does not ignore)"] --> SI["the run's scratch index<br/>(a separate index file, reused)"]
    SI --> WTREE["git write-tree"]
    WTREE --> ID["tree id, e.g. f8d1c79"]
    ID --> PIN["pinned under<br/>refs/task-runner/&lt;run&gt;/...<br/>so git gc cannot delete it"]
```

Two trees with the same id are the same content. That turns hard questions into comparisons:

| Question | Answer |
|---|---|
| What did this attempt change? | names that differ between two snapshots |
| Did a gate, a check or a reviewer change anything? | snapshot before == snapshot after? |
| Is the tree clean again after a failure? | snapshot == BASE? |
| Is the commit exactly what was verified? | committed tree == CANDIDATE? |

Because everything rests on git seeing the work, the root **must** be a git repository, declared
paths that git ignores are refused, and `.gitignore`, `.gitattributes` and `.gitmodules` are
protected by default so an agent cannot hide its work from the snapshot.

## What an agent may touch

```mermaid
flowchart TB
    subgraph tree["the repository"]
        W["the task's 'writes'<br/>(default: its outputs)"]
        PR["protected paths<br/>(union of built-in, workflow, type, task,<br/>can be added to, never narrowed)"]
        FR["frozen: outputs of accepted tasks"]
        GX["files the task's gates execute"]
        O["everything else"]
    end
    AG(["agent attempt"]) -- "allowed" --> W
    AG -. "change is reverted,<br/>attempt does not pass" .-> PR
    AG -. "reverted" .-> FR
    AG -. "reverted" .-> GX
    AG -. "reverted" .-> O

    classDef produce fill:#2f4b7c,stroke:#1d3157,color:#ffffff
    classDef ok fill:#2d6a4f,stroke:#1b4332,color:#ffffff
    class AG produce
    class W ok
```

A later task may change a frozen file only by **claiming** it in its own `writes`, and only if it
depends on the task that made it. `validate` prints every such claim, the claiming task's reviewers
see the diff, and the original task's gates are run again as part of the claimant's verification.

## Restoring files properly

Putting files back sounds trivial and is not. Writing the old bytes over a path follows symbolic
links, which can write **outside the repository**, and loses the executable bit. The runner instead
uses git's own checkout from a separate index loaded with the target tree:

```mermaid
flowchart TB
    R["restore these paths to tree T"] --> C1["check every parent is a real directory<br/>inside the repository"]
    C1 --> C2["git checkout-index --force<br/>from an index loaded with T"]
    C2 --> N1["git unlinks first: a symlink is replaced,<br/>never written through"]
    C2 --> N2["type and mode come from T:<br/>the executable bit returns"]
    C1 --> C3["paths T did not have:<br/>lstat + unlink, prune emptied directories"]
    N1 --> V["verify: snapshot == T"]
    N2 --> V
    C3 --> V
    V -- "not equal" --> EF["environment failure:<br/>stop, print paths, leave the tree alone"]

    classDef stop fill:#a32d2d,stroke:#741f1f,color:#ffffff
    class EF stop
```

Embedded git repositories and submodule entries, which a restore could not handle, never reach it:
the candidate is scanned right after each attempt and they are removed then.

## Committing exactly what was verified

```mermaid
sequenceDiagram
    participant E as engine
    participant S as state.json
    participant G as git
    E->>S: INTENT: commit op-42, parent P, tree CANDIDATE
    E->>G: build tree from HEAD + the task's changed paths
    E->>E: tree == CANDIDATE? otherwise refuse
    E->>G: commit-tree (trailers: Run, Task, Operation: op-42)
    E->>G: update-ref HEAD new-commit P   (fails if the tip moved)
    E->>G: read-tree HEAD   (make the real index follow the commit)
    E->>S: OUTCOME: accepted, sha
```

The last git step matters: without it the index still describes the old tip, `git status` shows
phantom changes, and a later `git revert` refuses to run.

The runner never runs `reset --hard`, `clean`, `stash`, `push` or `merge`. Undoing accepted work
(`replan --reopen`) adds `git revert` commits; it removes none.

## Crashes: intent, effect, outcome

An atomic state file cannot make "run a subprocess, write a commit, update the state" happen
together. So every external effect is bracketed:

```mermaid
flowchart LR
    I["1. INTENT<br/>written and synced to disk<br/>with an operation id"] --> X["2. EFFECT<br/>agent call, commit, restore,<br/>revert, pin, ..."]
    X --> O["3. OUTCOME<br/>recorded, intent cleared"]
    I -. "crash here or later" .-> REC["resume: reconcile<br/>every intent with no outcome"]
```

| Found on `resume` | Action |
|---|---|
| Commit intent, and the branch tip carries that operation id | It happened. Record acceptance. The author is **not** run again |
| Commit intent, and the tip is still the expected parent | It did not happen. Check the tree still equals the candidate, then commit |
| Commit intent, and the tip is anything else | Someone changed the branch. Stop and say what was expected and found |
| Agent intent, and its process group is still alive | Refuse to continue beside it. `resume --stop-orphans` stops it first |
| Agent intent, no process, no terminal event | Mark it `interrupted`, never successful. New invocation directory |
| Restore, pin, patch, index sync | Idempotent: do it again, verify |
| Half-done revert during `--reopen` | `git revert --abort`, then continue from the first revert not on the branch |

A process is identified by pid, start time **and boot id**, because pids are reused.

## The record protects itself

`.runs/` is ignored by git, so snapshots cannot see an agent tampering with it. The runner keeps
`integrity.json`, the hashes of every decision-bearing file (`state.json`, every `findings.json`,
every finished result, verdict and verification), and checks them before and after every agent call
and every command. A change the runner did not make fails that job.

The path of the record is given only to task types that need it (`summarize`). Gates never get it.

## Pauses hold the tree

Three things stop a run with a producer's candidate still in place: a pending human approval, an
escalated finding, and running out of budget. In each case the runner records the branch tip and
tree it expects, and `resume` checks them first. If someone edited the tree or committed on the
branch meanwhile, `resume` stops with a reconciliation error instead of guessing.

---

| Previous | | Next |
|:--|:-:|--:|
| [3 — Review panels and findings](03-review-panels-and-findings.md) | [Contents](README.md) | [5 — Architecture](05-architecture.md) |

**Reference:** [05 — Git, Crash recovery](../05-architecture.md#git),
[04 — Rules of the record](../04-run-directory.md#rules-of-the-record).
