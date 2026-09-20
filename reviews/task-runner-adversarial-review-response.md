# Response to the adversarial review of the task runner design

Review: [task-runner-adversarial-review.md](task-runner-adversarial-review.md), by an Opus agent
briefed to attack the amended design. 38 findings: 7 blockers, 18 major, 13 minor.

**Summary.** All 38 are accepted as real defects. I reproduced the claims that the fixes depend on
before acting (below). For 33 findings the proposed fix was taken as written or nearly so. For
five, the defect is accepted and a **different remedy** was chosen, with reasons. The amendments
are B1 to B12 in the [decision log](../task_runner/docs/00-decisions.md). The scenario count went
from 134 to 175.

## What was reproduced first

In a scratch repository, not in `/workspace`:

| Claim | Result |
|---|---|
| ADV-02: after `commit-tree` and `update-ref`, the real index is stale | `git status` shows `MM src/a.txt`; `git revert` ends with `fatal: revert failed` |
| ADV-02: the fix | after `git read-tree HEAD`, status is clean and `git revert --no-edit HEAD` succeeds |
| ADV-08: an output under an ignored path is invisible | tree id before and after writing `build/config.h` is identical; `git check-ignore -v` names `.gitignore:1` |
| ADV-04: the standard library disagrees with itself | `docs/spec/**` against `docs/spec/a/b.md`: `fnmatch` True, `PurePath.match` False |
| ADV-05: Claude Code print mode has no tool events | already known from the recorded live run: one result object |

## Findings, one by one

| Finding | Verdict | What was done | Where |
|---|---|---|---|
| ADV-01 advisory findings make later rounds impossible | Agreed | Advisory findings close as `noted` when raised. `resolutions` cover open blocking findings only; an empty list is valid. FND-16 reworded, FND-17 added | B1; 02 Findings; 04 schemas; 05 |
| ADV-02 stale index; is the run branch checked out? | Agreed, reproduced | `start` checks the run branch out. The commit recipe is written out in 05 with `git read-tree HEAD` as its last step, inside the commit intent. GIT-13, GIT-14, REC-10 | B2 |
| ADV-03 "git optional" contradicts everything | Agreed | GIT-06 now says a non-git root is refused | B3 |
| ADV-04 glob semantics undefined | Agreed, reproduced | A "Path patterns" section in 03: one matcher, a semantics table, and conservative cover and overlap rules. New module `patterns.py`. WF-19, WF-20 | B4 |
| ADV-05 capability evidence does not exist; `validate` needs `doctor` | Agreed | All probes are judged by effects the runner observes. `execute` is proved by a digest a model cannot compute without running the script. The check moved to `doctor` and `start`. Host identity defined. WF-24, PRE-01, PRE-05, PRE-08 | B5 |
| ADV-06 effects without intents | Agreed | A table of effects, intents and reconciliation in 05. Process identity: `/proc/<pid>/stat` field 22 plus boot id; Linux first, stated. REC-09 to REC-13 | B6 |
| ADV-07 claim by `outputs` or `writes`? | Agreed | `writes`. D8, FRZ-03, WF-11 and the 03 warning corrected | B4 |
| ADV-08 ignored paths | Agreed, reproduced | Refused at load and after each attempt. Git control files protected by default. WF-21, ACC-18 | B3 |
| ADV-09 snapshot comparison | **Agreed, different remedy** | See below | B3 |
| ADV-10 standalone verifiers | Agreed | Defined in 02 Kinds. Writing standalone checks get a BASE and a rollback. SCH-11, ACC-19 | B7 |
| ADV-11 verifier statuses | Agreed | Status `objected`; skip closure over `needs`, `reviews`, `verifies`. STATUS.md example corrected to show the panel. ACC-23 | B7 |
| ADV-12 the rework diff's base | Agreed | Per reviewer, from `last_seen_candidate` in the ledger. After `retry`, round 1 again and old findings `superseded`. FND-18, FND-19 | B1 |
| ADV-13 read-only directories | Agreed | Modes dropped. Write-once is enforced by the integrity manifest. RUN-16 | B8 |
| ADV-14 `protected` can be narrowed; gate scripts | **Agreed, partly different remedy** | See below | B9 |
| ADV-15 budget stop | Agreed | A pause that holds the tree, with the expected tree recorded. `resume --add-budget`. FAIL-05, BUD-05 | B10 |
| ADV-16 wasted attempt after `resolve` | **Agreed, different remedy** | See below | B10 |
| ADV-17 ledger not integrity-checked | **Agreed, partly different remedy** | See below | B8 |
| ADV-18 prompt assembly | Agreed | One pass, fenced data, caps with a rule per placeholder. New group PRM-01 to PRM-05 | B11 |
| ADV-19 destructive verifiers | Agreed, option (a) | `restores = true`; the runner restores the candidate itself. The example's `mutants` task is marked. ACC-20 | B7 |
| ADV-20 plan errors | Agreed | Scenarios moved, RUN-03/09/10 assigned, `.runs/README.md` owned by stage 2, the scripted agent's contract written into 07 | B12 |
| ADV-21 embedded repositories | Agreed | Candidate scan for mode 160000 and symlinked parents right after the attempt. A restore that still cannot complete is an environment failure. GIT-10, GIT-11 reworded to match what git does | B3 |
| ADV-22 bare kinds and friends | Agreed | `produce.toml` and `review.toml` added to the library. `summarize` got a `review_type`. WF-18 | B4 |
| ADV-23 `read_only` is believed | Agreed | Verified by snapshot; the check fails, not the producer. SCH-12 | B7 |
| ADV-24 rework without `resume` | **Agreed, different remedy** | See below | B1 |
| ADV-25 feedback after a gate failure | Agreed | Rework prompt composition defined; responses keyed by attempt. ACC-22 | B1 |
| ADV-26 `retry` during a pause | Agreed | Refused, naming the task waited on. SCH-13 | B7 |
| ADV-27 exit 2 and 255 at once | Agreed | `blocked`. 02 Failure and FND-03 corrected | B7 |
| ADV-28 dots in generated ids | Agreed | Dots are reserved for generated ids; written-out review tasks use ordinary ids | B4 |
| ADV-29 review rounds lack invocation directories | Agreed | `invocation-N/` in rounds; `index.json` example corrected | B8 |
| ADV-30 parameters can never be missing | Agreed | `required = true`; the `sections` comment is gone | B4 |
| ADV-31 persona codes | Agreed | Unique codes and unique perspectives per producer. WF-22 | B4 |
| ADV-32 `recheck_passed` per task | Agreed | In the override list and the panel shorthand | B4 |
| ADV-33 resolution base | Agreed | The workflow file's directory; recorded in `run.json`. WF-23 | B4 |
| ADV-34 refs never cleaned | Agreed | `runner prune`. RUN-17 | B6 |
| ADV-35 "squashing" | Agreed | Reworded | B2 |
| ADV-36 fresh index per snapshot | Agreed | One reused index per run. GIT-15 | B2 |
| ADV-37 `fail_pattern`; `outputs` ∩ `removes` | Agreed | Python regular expression over combined output; the intersection is a load error | B4 |
| ADV-38 `branch = "current"`; empty directories | Agreed | No branch is created; emptied directories are removed. GIT-05, GIT-16 | B2 |

## Where the remedy differs, and why

### ADV-09: no `leaves` allowlist for gate litter

The review proposed a per-gate `leaves = [...]` list of non-ignored files a gate may create. I did
not add it.

- A file that is untracked and not ignored is, to git, work waiting to be added. If the runner
  tolerated it, the file would sit in the tree when the transaction ends, so it would be part of the
  **next producer's BASE snapshot** and would break SCH-10 ("the transaction ends clean"). An
  allowlist would therefore also need a cleanup step, and then it is no different from the rule
  already in place.
- The repository already has the right mechanism: ignore build products. `check-gates` (PRE-04)
  reports a littering gate before any money is spent.

What was taken: the wording error is fixed (the comparison is of the whole snapshot, not "tracked
source"), the runner now **restores the candidate** after a verifier changes the tree instead of
only noticing, and the tree-level nature of the guarantee under end-of-line filters is stated. I did
not make `start` refuse repositories with `.gitattributes` filters: most real repositories have
`text=auto`, and what is committed is the normalised tree in any case, which is what was verified.

### ADV-14: no script hashes in `verification.json`

Taken: `protected` is a union that cannot be narrowed, and files named in a gate command are
protected by default. Not taken: recording the hash of each gate script beside the config hash.
Every verification is already bound to the **candidate tree id**, and a tracked gate script is part
of that tree, so a changed script already changes the id and voids the results. A second hash would
say the same thing twice. The document now also says plainly that an author who owns the build file
can still weaken the build, and lists the defences that remain.

### ADV-16: no `continue` command; the escalation holds the tree instead

The review proposed a new `continue` command that restores the pinned candidate and re-verifies.
The cause of the waste was earlier: an escalation set the candidate aside, although an escalation
is a decision for a person, exactly like a `human` approval, and A1 already says that holds the
tree. So an escalated finding now makes the producer `waiting_human` with the candidate in place.
`resolve` followed by `resume` continues acceptance; nothing is restored, so nothing needs
re-verifying, and there is no new command. A third answer, `--as upheld`, was added because the
person may side with the reviewer.

### ADV-17: no read-only bind or copy of the record

Taken: the integrity manifest covers every decision-bearing file including the ledger, and
`TASK_RUNNER_RUN_DIR` goes only to types that set `needs_run_dir`. Not taken: handing those tasks a
read-only bind mount or a copy. A bind mount needs privileges the runner must not assume, and a copy
of a record with megabytes of logs costs more than the risk: a change to the live record by a
`summarize` author is **detected** by the manifest and fails that job, which is the same guarantee
every other job gets.

### ADV-24: `resume` is dropped from `requires`, not added to `summarize`

The review offered either adding `resume` to `summarize` or defining the other branch. Defining the
other branch is needed anyway (sessions are abandoned after a timeout), and once it exists,
requiring `resume` only excludes agents that would work. So `resume` is now an optimisation used
when the profile has it, and no type requires it. A `command` agent can be an author.

## What this review did not change

The reviewer's "attacked and survived" list stands: restore by `checkout-index`, pinned tree refs,
the scratch-index snapshot, the two-milestone model (A8) and the no-progress rule (A12).

## State after this response

Stage 0 of the plan is complete. Stage 1 (workflow loading, `validate`, `graph`, path patterns) has
no open blocker and has started.
