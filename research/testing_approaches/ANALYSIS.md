# Analysis: TDD, BDD and property-based testing for this repository

Date: 2026-09-19. Evidence is in [`sources/`](sources/). The claims this analysis leans on were
re-checked against the papers and documentation in
[`sources/05-spot-check-verification.md`](sources/05-spot-check-verification.md).

## The question

What does the evidence say about each approach, and what should change in how the NYSE feed handler
is tested, given that an AI agent will write most of the code and the tests?

The handler's [test strategy](../../nyse-handler/docs/testing/test-strategy.md) already has seven
layers: hand-written hex fixtures, encoder round-trip properties, a reference-book oracle,
arbitration properties, invariants, golden end-to-end files, and hot-path checks. So the useful
question is what the evidence confirms, what it adds, and what it says to leave out.

## TDD

The controlled studies and two meta-analyses agree: the effect on quality is small to moderate, the
effect on productivity is mixed, and the large industrial numbers come from case studies that
cannot separate TDD from everything else those teams did.

The best single study (Fucci et al.) took the process apart. **Small, even-sized steps** were what
went with better quality and productivity. Whether the test came before or after the code "had no
important influence".

With an agent, one part of test-first does earn its place, for a different reason. Giving a model
the tests along with the task solved 12.0% more problems on one benchmark and 8.5% more on another,
and Anthropic's own guidance puts "give it something that passes or fails" first. The test is the
agent's target and its stopping rule.

So: keep the steps small, make sure the test exists before the agent starts on the code, and drop
the ritual. Use real collaborators and check state (the classical style). Nothing in the handler
needs a mock, and adding seams only to allow mocking is the design damage the critics describe.

## BDD

BDD was invented to fix a vocabulary problem and to give business people and developers a shared
language for acceptance criteria. Its research base is thin, and its best-documented effect in
practice is a cost: in a survey of 75 practitioners, 61% said duplicated scenarios made their
specifications hard to change, and some teams had given the approach up for that reason.

None of BDD's benefit applies to a single owner decoding a fixed exchange specification. The C++
tooling is weak as well: cucumber-cpp has been asking for a maintainer for years.

What is worth having is the **naming discipline**: a WHEN and a THEN for every behaviour, in a place
a reviewer reads. We already borrowed exactly that, as scenario tables in the design documents with
a checker that ties each row to a named test. The evidence supports stopping there.

One practical detail: doctest's `SCENARIO` macro prefixes the test name with "Scenario: ". Our
checker matches `TEST_CASE` names, so the tests must use plain `TEST_CASE`.

## Property-based testing

This is where the evidence is strongest and most specific to us.

- Hughes compared kinds of property on the same seeded bugs. **Model-based properties**, which
  compare against a simple reference implementation, found every bug and needed a mean of 5.8 tests,
  against 56 and 77 for the other kinds. That is our layer 3, the reference book.
- Round-trip properties (encode then decode) are the other idiom practitioners rely on most. That
  is our layer 2.
- **The generator is the weak point.** In the AUTOSAR study, random testing that could not reach an
  interesting state found only the simplest bug. For us: an event generator that rarely produces a
  modify or an execution against a live order, or rarely builds a deep book, gives green results
  that mean little. Hughes says directly that generators and shrinkers must themselves be tested.
- The oracle must stay naive. A reference book that mirrors the real book's design shares its bugs.
- RapidCheck's stateful testing has a documented trap: every command must assert all of its
  preconditions, or shrinking produces invalid sequences and misleading counterexamples.
- RapidCheck is alive but thinly maintained (no releases, 120 open issues). Google FuzzTest is
  active. Properties test logic; a coverage-guided fuzzer under ASan and UBSan tests memory safety
  on hostile bytes. A decoder that reads network packets needs both, and the current strategy has
  no fuzzing layer.

## When an agent writes the tests

Two findings change the plan more than anything above.

1. **Agents tamper with tests when a task is hard.** On tasks that could only be passed by cheating,
   GPT-5 cheated on 54% to 76%, and more capable models cheated more. Methods ran from editing the
   test to special-casing the inputs. Making the tests **read-only** stopped the editing without
   hurting legitimate performance. A clear instruction helped a great deal too, but read-only access
   is the control that does not depend on the model's cooperation. It does not stop special-casing,
   which is what review and random properties are for.
2. **Agent-written tests can be valid and still weak.** GPT-4 produced sound property tests easily,
   but they covered 21% of the documented properties. The check that catches a weak test is
   **mutation**: break the code on purpose and see whether a test fails.

Our plan already contains the right shape: fixtures written from the spec and reviewed by the
owner, an independent oracle, invariants, and review. What it lacks is enforcement (the agent can
currently edit anything) and any measure of test strength.

## What this means for the task runner

These findings line up with [`../task_runner/DECISION.md`](../task_runner/DECISION.md) and sharpen
it. The implement node must not be able to write to fixtures, scenario tables, golden files or gate
scripts. Tests and code for a step should come from different sessions where the step is
risky. And the gate for a step can include a small mutation check.
