# Stage 4 compatibility and limits

Verified on 2026-09-20. The installed CLIs report `codex-cli 0.155.1` and
`2.1.278 (Claude Code)`. Their local `--help` output confirmed the command-line flags used by the
adapters, including Codex's explicit `exec resume ID`, schema/output options and configuration
overrides. No real-model calls were made during implementation or verification.

## Completion and environment failures

Claude must exit successfully and return a successful terminal `result` with a valid answer.
Codex must exit successfully, complete the current turn, and provide a valid final agent message.
A stale output file, incomplete stream, malformed field or failed turn cannot produce success.
Codex event parsing is incremental; an early sandbox failure cannot disappear beyond the retained
log tail. Ordinary failed shell tests inside a successful session are not call failures.

The three [recorded fixtures](../tests/recorded/README.md) preserve the research run's actual
stdout. The Codex author fixture contains a `bwrap` namespace startup failure followed by a
blocked answer and `turn.completed`. The adapter correctly returns an environment failure.
This host also reports the same namespace error when ordinary sandboxed shell tools start.
These observations do not qualify any live model/profile for repository access; run `doctor`
on the intended host before use. No adapter automatically bypasses sandboxing.

## Qualification

`doctor` uses a scratch Git repository and observes answers, hidden file contents, script-written
digests, file changes, explicit-session memory and an unchanged read-only sentinel. Events claiming
that a tool ran are not evidence. The boundary probe is a practical observed test, not a proof of
isolation against arbitrary hostile code. Gates and command agents retain the permissions of their
configured execution environment.

The cache key includes the profile, model, read-only mode, host, executable/argument-file hashes,
CLI version and known user/project settings-file hashes. Project settings files are copied into
the scratch repository; profile-specific external integrations still need the same dependencies
and access on the host. Configuration contents and environment dumps are not included in the
qualification metadata. Hashes cannot capture every external service or dynamic configuration
change; a run-time environment failure invalidates the cached entry, and `doctor --force` always
repeats the probes. Resume rechecks the fingerprint before making calls.

The latest report is `.runs/qualification.json`; individual probe logs are under `.runs/doctor/`.
A run receives its qualification report and profile metadata. Probe costs incurred by that start
or resume are added to its known/unpriced accounting. Cached probes are not charged again.
An explicit earlier `doctor` keeps its own spend in its report. Monetary reservation across agent
calls remains stage 5; Codex does not offer an in-call dollar limit.

## Gate preflight

`check-gates` requires a clean source tree and runs every command against a fresh local clone.
It includes standalone checks, distinguishes intended `new`-gate failures from missing commands,
timeouts and unmatched failure patterns, and lists changed or newly created files. A passing
`new` gate is an objection. Results and logs are retained under `.runs/check-gates/`. Ignored local
build products and virtual environments are not copied, so gates must create their own build
outputs or use host-installed dependencies. The source work tree is never used for gate execution.

## Review scope

Text-only review is explicit (`review_mode = "provided_context"`), with full file versions, the
complete diff and an evidence manifest. Binary blobs use base64. Oversized evidence or a prompt
that exceeds the supplied context budget is refused before the agent runs; nothing is silently
truncated. Stage 4 provides the single-review adapter helper. Review panels, ledger-derived
verdicts and their scheduler are stage 5.
