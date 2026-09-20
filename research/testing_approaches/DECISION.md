# Decision: how we test, and how we let an agent test

Date: 2026-09-19. Status: **proposed.** Reasoning is in [`ANALYSIS.md`](ANALYSIS.md). Nothing in the
NYSE handler's documents has been changed yet; the edits are listed at the end.

## Decision

**Keep the seven-layer strategy. Property-based testing against a reference model stays the centre
of it. Take two habits from TDD, take only the naming from BDD, and add four controls for
agent-written tests.**

| Approach | Verdict | What we actually do |
|---|---|---|
| TDD | **Two habits, not the ritual** | Small, even steps. The failing test exists before the agent starts on the code, because it is the agent's target. Classical style, no mocks. The order of writing is otherwise not policed |
| BDD | **Naming only** | The WHEN/THEN scenario tables and `check_scenarios.py` we already have. No Gherkin, no cucumber-cpp, no `SCENARIO` macros (they change the test name and would break the checker) |
| Property-based | **The core** | Reference-book oracle (layer 3), encoder round trip (layer 2), arbitration properties (layer 4), plus the generator rules below |

## Rules for properties

1. **The oracle stays naive.** `ReferenceBook` is a `std::map` of levels and a `std::map` of orders,
   written for obviousness, sharing no code or data-structure ideas with `Book`. It is reviewed as
   carefully as a fixture.
2. **Generators are tested.** Every stateful property reports its distribution with RapidCheck's
   `classify` or `tag`, and a test fails if the share of interesting cases falls below a floor:
   modifies, replaces and executions against live orders, books deeper than a few levels, price
   changes that empty a level, gaps that are filled and gaps that are not.
3. **Every stateful command asserts all its preconditions**, as RapidCheck's documentation requires,
   so that shrunk counterexamples are valid sequences.
4. **Failing seeds are kept.** A counterexample becomes a named regression test before the fix.

## Controls for agent-written code and tests

1. **Protected files.** Hex fixtures after owner review, the scenario tables, golden files, the
   reference book and the gate scripts cannot be edited by a session that is implementing a step.
   In the task runner this is a deny rule on the implement node plus a gate that fails if
   `git diff` touches a protected path. Changing one is its own reviewed step.
2. **Separate sessions for tests and code on the risky modules** (decoder, book, arbiter): one
   session writes the tests from the design document and the spec extract, another writes the code.
3. **Review from a fresh context.** The reviewer sees the diff and the scenario rows, not the
   implementer's reasoning, and looks specifically for special-cased inputs and weakened assertions.
4. **A mutation check per module.** A short fixed list of hand-picked mutants for each module (flip
   a comparison in `BookSide`, drop the `next_expected` update, read a field at the wrong width,
   skip the level erase). Each must be killed by some test. This is a script and a dozen patches,
   not a mutation framework. It moves to a real tool only if the list proves too weak.

## One addition to the layers

**Layer 8, fuzzing the decoder.** A libFuzzer harness on the packet entry point under ASan and
UBSan, seeded with the hex fixtures, run for a fixed short time in CI and longer by hand. Properties
cover logic on valid and near-valid input; the fuzzer covers memory safety on hostile bytes. It is
scheduled with the decoder step, and FuzzTest is the fallback if RapidCheck maintenance becomes a
problem.

## What we will not do

- Adopt Gherkin or any step-definition layer.
- Introduce mocks, or seams that exist only to allow them.
- Police test-first ordering beyond "the target test exists before the agent starts".
- Treat coverage percentage as a measure of test strength.
- Let a green run count when the step's diff touches a protected file.

## Edits this implies, not yet made

- `nyse-handler/docs/testing/test-strategy.md`: the generator rule, the precondition rule, the
  protected-file list, the mutant list, layer 8, and the `TEST_CASE`-not-`SCENARIO` note.
- `nyse-handler/docs/roadmap/milestones.md`: the fuzz harness in step 5, the mutant lists in steps
  5, 8 and 9.
- `research/task_runner/DECISION.md`: already says the implement node may not edit its gates; the
  protected-path gate makes that mechanical.

## What would change this decision

- The hand-picked mutants all dying at once, every time. Then they are too easy and a real mutation
  tool is justified.
- Generator floors proving hard to meet. Then the generators need state-aware construction before
  any more properties are written.
- A second person joining who does not read C++. That is the case BDD was made for.
