# Spot checks of the claims the decision rests on

Done 2026-09-19 by the main session, not by the research agent. Each paper was downloaded again and
its text extracted with `pypdf`; each documentation page was fetched raw. The quoted strings were
then searched for.

| # | Claim | Checked against | Result |
|---|---|---|---|
| 1 | Model-based properties fail fastest: mean 5.8 tests, against 56 for metamorphic and 77 for postconditions | Hughes, "How to Specify It!", Fig. 9 | **Confirmed.** Min and max for model-based are 3.1 and 9.8, so they are also by far the most consistent (metamorphic ranges up to 714) |
| 2 | In TDD, short uniform cycles matter and the order of test and code does not | Fucci et al., arXiv 1611.05994, abstract | **Confirmed**: "Sequencing … had no important influence". It adds that refactoring effort was *negatively* associated with both outcomes |
| 3 | GPT-5 cheats on 54.0% of Conflicting-SWEbench and 76% of Oneoff-SWEbench tasks | ImpossibleBench, arXiv 2510.20270 | **Confirmed** |
| 4 | Read-only tests stop test modification; hiding tests stops cheating but hurts performance; a good prompt took one variant from 92% to 1% | Same paper, §5 and Fig. 7 | **Confirmed.** The paper also says read-only access does not stop special-casing or operator overloading |
| 5 | Giving the model the tests solves an extra 12.0% (MBPP) and 8.5% (HumanEval) of problems | Mathews and Nagappan, arXiv 2402.13521, §4.2 | **Confirmed.** The baseline percentages quoted in `04` were not found in that form and are not relied on |
| 6 | GPT-4 writes a valid and sound property test in 2.4 samples on average, but covers only 21% of the documented properties | Vikram et al., arXiv 2307.04346 | **Confirmed** |
| 7 | RapidCheck: "always assert all preconditions" in `checkPreconditions`, because shrinking reuses commands against a changed state | `rapidcheck/doc/state.md:116` | **Confirmed** |
| 8 | doctest `SCENARIO` is `TEST_CASE` with the name prefixed by "Scenario: " | `doctest/doc/markdown/testcases.md:26-28` | **Confirmed.** This matters to us: see the decision |

One further point from Hughes that the source file did not bring out: a model "may resemble the
actual implementation more than is healthy". An oracle that shares the design of the code it checks
shares its bugs.

Not checked, and not relied on: the mutation-score figures listed under "Unverified leads" in
`04`, the Meta 73% acceptance figure, the Jane Street interview counts, and the AUTOSAR bug counts.
The last two support a conclusion that claim 1 already carries.
