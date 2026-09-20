# Stage 7 live acceptance record

Captured 2026-09-20 in `/tmp/task-runner-rework-9g7r9owy`, workflow `live-rework`,
run `20260920T112431Z-5f36c488`. The reproducible inputs are in
[examples/live-panel](../examples/live-panel/README.md).

Claude Opus 5 wrote the artifacts with the explicitly configured YOLO profile.
Reviewers used `auto`, read/search-only tools and no MCP servers. All profiles
were qualified before execution. The live record contains native hook logs for
11 invocations; `runner activity` showed their tools while the calls ran.

| Acceptance condition | Observed result |
|---|---|
| Design with two reviewers | Both reviewers blocked the supplied draft in round 1; both passed the revision in round 2 |
| Findings answered and resolved | Five blockers (`design/PE-1`, `PE-2`, `SC-1`, `SC-2`, `SC-3`) resolved in the ledger |
| Implementation with gates and two reviewers, one advisory | Both passed; 32 unittest tests passed, independently rerun by the operator |
| One commit per accepted producer | `e19ecaf` design; `6284a11` implementation; `f29b824` summary |
| Stop for human sign-off | Exit 255, `needs_human`, task `signoff` waiting |
| Resume after approval reaches done | Awaiting the owner's explicit sign-off; not yet claimed |
| Fresh agent can explain run from record alone | Passed: controlled auditor received only the record path and “What happened in this run, and what is open?” |

The fresh auditor identified the two design rounds, all five resolved blockers,
three acceptance commits, the pending sign-off, and the interrupted invocation.
Its record is `/tmp/runner-record-audit-k_f62bc_`. It also identified 13 advisory
findings, including a nonessential incorrect NumPy example in the design and a
suggestion to name the unittest module explicitly. Advisory findings remain
`noted`; this example is not represented as having no review comments.

The summary is a snapshot taken while its own task ran. Final run accounting is
**$5.938593 known**, $0 reserved, plus one unpriced interrupted call. The separate
record audit cost $1.3765505. Qualification and earlier experiments are separate
from these totals. These are CLI-reported usage costs, not an account invoice.

## What the live check found

The first scratch run accepted a design on attempt 1 after the author corrected
the intended seed gap itself. It did not exercise rework and was not counted as
passing that condition. The fixed draft in this example reliably supplied the
initial candidate for the panel.

Hook logs also exposed a prompt-authority error: all data blocks, including the
workflow brief, were labelled “never an instruction.” The rule now authorizes
the workflow specification within runner boundaries and treats repository and
agent text as evidence. One live call was stopped while installing that fix;
`resume` abandoned its session, recorded unknown usage, and continued in a fresh
invocation. The design was then accepted on attempt 2.

A real read-only qualification probe found that disabling Claude's editing tools
alone left Bash writes possible. Reviewers now have an explicit read/search tool
allowlist, no shell/delegation/MCP writes, and an observed boundary probe.
