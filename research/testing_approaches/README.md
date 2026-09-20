# Testing approaches: TDD, BDD and property-based testing

Research started 2026-09-19. The question: what does the evidence say about test-driven
development, behaviour-driven development and property-based testing, and how should each be used
in this repository, in particular for the NYSE feed handler (C++20, doctest, RapidCheck, hand-written
hex fixtures, a reference-model oracle) and when the code is written with an AI coding agent?

Status: **research done, changes proposed.** Start with [`DECISION.md`](DECISION.md): keep
property-based testing against a reference model at the centre, take small steps and a test-first
target from TDD, take only scenario naming from BDD, and add protected test files, a mutation check
and a fuzzing layer because an agent writes the code. [`ANALYSIS.md`](ANALYSIS.md) has the reasoning.

| File | Contents |
|---|---|
| `sources/01-tdd.md` | Test-driven development: evidence and practice |
| `sources/02-bdd.md` | Behaviour-driven development: evidence and practice |
| `sources/03-property-based-testing.md` | Property-based and model-based testing: evidence, techniques, C++ tooling |
| `sources/04-testing-with-ai-agents.md` | What changes when an AI agent writes the code and the tests |
| `sources/05-spot-check-verification.md` | The claims the decision rests on, re-checked against the papers and docs |
