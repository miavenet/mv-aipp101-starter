# Test-Driven Development — Literature Review

> Note on method: WebFetch returns a small model's digest of each page, so quoted wording is second-hand unless otherwise noted. For the three quantitative claims that matter most to this file (Nagappan et al.'s 40-90%/15-35% figures, the Karac & Turhan survey table, and the Ghafari et al. abstract), I downloaded the PDF/HTML with Bash (`curl`/WebFetch) and extracted raw text myself with `pypdf`, then grepped for the exact numbers — those are marked "verified against raw text" below. Everything else is a WebFetch digest.

## Key takeaways for this project

- TDD's effect on external quality is small-to-moderate and its effect on productivity is essentially a wash across the controlled-experiment literature; the strongest industrial numbers (Nagappan et al.) come from case studies with real confounds, not causal experiments [S1][S4].
- The mechanism that actually correlates with better outcomes is **short, uniform cycles** (fine-grained steps taken consistently), not the test-first/test-last ordering itself — this is the single most-replicated finding relevant to an AI-agent-driven workflow [S2][S5].
- Because sequencing doesn't matter much but granularity does, the project's plan (hex fixtures against spec, invariant checks after every event, golden files) can substitute for strict red-green-refactor discipline as long as work is broken into small, testable increments with a test added at each increment [S2][S5].
- Two systematic reviews (Rafique & Misic; the table in Karac & Turhan citing Bissi et al., Munir et al., Kollanus, Siniaalto) all report **inconsistent-to-degraded productivity** and only "improvement" or "no difference" on quality depending on study rigor — treat any single strong TDD claim with suspicion [S4][S5].
- A likely confound identified by Pančur & Ciglarič (cited in [S5]) is that many pro-TDD experiments compared against a *coarse-grained, near-waterfall* test-last control; TDD's apparent edge shrinks when the control is also iterative and fine-grained.
- Classical ("Detroit/Chicago") vs. mockist ("London") TDD is a real methodological fork: classical TDD uses real collaborators and state verification, mockist TDD mocks every collaborator with interesting behavior and does behavior verification [S6]. For a protocol decoder/order book with one clear "real" collaborator (a std::map reference oracle) and few interesting external dependencies, the classical style fits better — it avoids the "mock-heavy" indirection DHH criticizes [S6][S7].
- The "TDD is dead" debate (DHH vs. Beck/Fowler, 2014) is expert opinion, not evidence, but the specific critique — test-first fundamentalism drives design toward excess indirection purely to keep unit tests fast/isolated ("test-induced design damage") — is a real risk to watch for if the agent starts inserting seams solely to make mocking easier [S7][S8].
- TDD is defined by Beck as the red/green/refactor loop: write a failing test, make it pass with minimal code, refactor [S3]; Fowler's own summary states the most common way people "screw up TDD" is skipping the refactor step, producing "a messy aggregation of code fragments" [S8].
- Field studies suggest TDD "in the wild" is rarely practiced as described in papers — one study found developers followed TDD in only 12% of projects that claimed to use it, and a GitHub mining study found only 0.8% of self-labeled TDD Java projects were actually TDD-like, with no measurable difference in commit velocity, bug-fix commits, or issues vs. non-TDD controls [S5].
- Where test-first is a poor fit — exploratory/spike code, performance-sensitive code, and protocols with an external, already-fixed spec — none of the reviewed sources argue test-first buys much: Karac & Turhan's advice ("some tasks are better suited than others with respect to 'TDD-bility'") applies directly to a wire-format decoder where the spec, not evolving-test-driven-design, defines correctness [S5].
- Practical synthesis that survives the evidence, for this project: keep cycles short and uniform, write the test alongside (not necessarily strictly before) the code, use a classical/state-based style with the naive reference book as oracle, and don't expect TDD-as-ritual to substitute for spec-derived fixtures and invariant checks — those are doing the real quality work [S1][S2][S5].

## Sources

### [S1] Realizing quality improvement through test driven development: results and experiences of four industrial teams
- **Authors/Org:** Nachiappan Nagappan, E. Michael Maximilien, Thirumalesh Bhat, Laurie Williams (Microsoft Research / IBM)
- **Year:** 2008
- **URL:** https://www.microsoft.com/en-us/research/wp-content/uploads/2009/10/Realizing-Quality-Improvement-Through-Test-Driven-Development-Results-and-Experiences-of-Four-Industrial-Teams-nagappan_tdd.pdf (Empirical Software Engineering 13(3):289-302)
- **What it measured:** Four "in vivo" industrial case studies (3 Microsoft teams — Windows, MSN, Visual Studio — and 1 IBM team) comparing a TDD (or TDD-inspired) team against a similar non-TDD team under the same manager/sub-culture, measuring pre-release defect density and development time.
- **Key findings (verified against raw PDF text via pypdf extraction):** "the pre-release defect density of the four products decreased between 40% and 90% relative to similar projects that did not use the TDD practice. Subjectively, the teams experienced a 15–35% increase in initial development time after adopting TDD." Team sizes and project sizes varied widely (6-155 KLOC, 20-119 person-months).
- **Strength of evidence:** Industrial case study (N=4), not a controlled experiment. The authors' own Section 7 (Threats to Validity, confirmed verbatim in extracted text) explicitly flags: possible motivation/observer effects (though teams didn't know they were being studied), that TDD projects were greenfield while comparison projects were sometimes legacy-system enhancements (different baseline defect profiles), and that "a family of case studies is likely not to yield statistically significant results." The authors call this "research in the typical" rather than controlled experimentation.
- **Relevance:** This is the most-cited positive industrial TDD result and is frequently used to justify TDD mandates; its own limitations section is worth taking seriously — it is a same-company natural experiment, not causal proof, and the effect is entangled with "how much testing happened at all," which for this project is separately guaranteed by hex fixtures/oracle/invariant checks regardless of ordering.

### [S2] A Dissection of the Test-Driven Development Process: Does It Really Matter to Test-First or to Test-Last?
- **Authors/Org:** Davide Fucci, Burak Turhan, and colleagues (published as IEEE TSE paper; arXiv preprint)
- **Year:** 2016 (arXiv) / 2017 (IEEE TSE 43(7):597-614)
- **URL:** https://arxiv.org/abs/1611.05994
- **What it measured:** Analyzed 82 data points from 39 professional developers, decomposing "TDD" into four independent process characteristics: sequencing (test-first vs test-last), granularity (size of each step), uniformity (consistency of step size/rhythm), and refactoring effort — then correlated each with quality and productivity outcomes.
- **Key findings:** "Quality and productivity improvements were primarily positively associated with the granularity and uniformity. Sequencing... had no important influence." I.e., working in short, uniform cycles adding a small piece of functionality plus its tests each time predicts good outcomes; whether the test or the code came first inside that cycle did not.
- **Strength of evidence:** Controlled/quasi-experimental study with professional (not student) subjects — one of the more methodologically careful entries in the TDD literature, and widely cited by later critical surveys (see S5) as the key mechanistic finding.
- **Relevance:** Directly actionable for this project: since an AI agent will write both code and tests, what should be enforced is small, uniform increments (e.g., one Pillar message type or one book invariant at a time, each shipped with its test) rather than a rigid test-must-be-written-first rule.

### [S3] Test-Driven Development: By Example / Fowler's TDD definition
- **Authors/Org:** Kent Beck (book, 2003); summarized by Martin Fowler
- **Year:** 2003 (book); Fowler bliki entry undated, accessed 2026
- **URL:** https://martinfowler.com/bliki/TestDrivenDevelopment.html
- **What it measured/argues:** Canonical definition of the TDD cycle — Fowler's own words (WebFetch digest, not independently string-matched): "Write a test for the next bit of functionality you want to add. Write the functional code until the test passes. Refactor both new and old code to make it well structured," commonly shortened to "Red-Green-Refactor."
- **Key findings:** Fowler states the most common failure mode is "neglecting the third step" (refactor), leaving "a messy aggregation of code fragments" — but he still considers that better than no tests at all. Karac & Turhan (S5) separately quote Beck's own 2003 caveat: "No studies have categorically demonstrated the difference between TDD and any of the many alternatives in quality, productivity, or fun. However, the anecdotal evidence is overwhelming."
- **Strength of evidence:** Practitioner/originator definition, not empirical evidence — foundational terminology source only.
- **Relevance:** Establishes the vocabulary (red/green/refactor) the rest of the file's evidence is measured against.

### [S4] The Effects of Test-Driven Development on External Quality and Productivity: A Meta-Analysis
- **Authors/Org:** Yahya Rafique, Vojislav B. Misic
- **Year:** 2013
- **URL:** https://www.researchgate.net/publication/260649027 (IEEE Transactions on Software Engineering 39(6):835-856)
- **What it measured:** Meta-analysis of 25 controlled experiments on TDD published 2000-2011, pooling effect sizes for external quality and productivity.
- **Key findings:** "A small effect in favor of TDD on functional/external quality"; results on productivity were inconclusive (per WebSearch summary of the paper — I was not able to WebFetch the full text in this session, so the exact effect-size number (e.g., a d or r statistic) is not independently confirmed here).
- **Strength of evidence:** Meta-analysis of controlled experiments — one of the stronger evidence types in this domain, but see Karac & Turhan (S5) for how later scholars characterize even this meta-analysis's category (waterfall vs iterative test-last controls) as a source of inconsistency.
- **Relevance:** Supports the takeaway that quality gains from TDD-as-ritual are small; productivity gains are not established. Flagged as not independently re-verified against raw text — treat the "small effect" characterization as reported by secondary sources, not a number I confirmed myself.

### [S5] What Do We (Really) Know about Test-Driven Development?
- **Authors/Org:** Itir Karac, Burak Turhan (University of Oulu / Monash)
- **Year:** 2018
- **URL:** https://www.cse.unr.edu/~dascalus/Paper_JAMES.pdf (IEEE Software 35(4):81-85)
- **What it argues:** A critical synthesis of ~15 years of TDD research, built around a table of six systematic literature reviews (Bissi et al., Munir et al., Rafique & Misic, Turhan et al./Shull et al., Kollanus, Siniaalto), each reporting different, sometimes contradictory conclusions on quality and productivity.
- **Key findings (verified against raw PDF text via pypdf extraction):** Their summary table shows conclusions ranging from "Improvement" to "Improvement or no difference" to "Degradation or no difference" for quality across reviews, and "Inconclusive" to "Degradation" for productivity — with inconsistency further broken down by moderators like academic-vs-industrial setting and study rigor. They cite a field study where, "after monitoring the development activity of 416 developers over more than 24,000 hours, researchers reported that the developers followed TDD in only 12 percent of the projects that claimed to use it," and a GitHub-mining study finding "only 0.8 percent" of self-labeled Java TDD repos were actually TDD-like, with no measurable difference vs. controls in commit velocity, bug-fixing commits, or issue counts. Their own conclusion: "There's no convincing evidence that TDD consistently fares better than any other development method, at least those methods that are iterative," and that the real driver is "working on small, well-defined tasks in short, steady development cycles," not test order — consistent with Fucci et al. (S2), which they cite directly ("the effect of test-first completely diminished when the effects of short and steady cycles were considered").
- **Strength of evidence:** Expert synthesis / secondary review (not itself a new experiment), but grounded in a systematic table of prior systematic reviews — a good high-level map of where the field actually stands, including its industry-adoption-rate findings.
- **Relevance:** The single best "what should we actually take away" source for this project: it explicitly separates test-first ritual from the mechanism that matters (small uniform steps), and names "TDD-bility" — the idea that some tasks (their example: framing/spec-defined tasks) are simply less suited to test-first than others.

### [S6] Mocks Aren't Stubs
- **Authors/Org:** Martin Fowler
- **Year:** originally 2007 (accessed 2026, page appears actively maintained)
- **URL:** https://martinfowler.com/articles/mocksArentStubs.html
- **What it argues:** Distinguishes state verification vs. behavior verification, and classical TDD ("use real objects if possible and a double if it's awkward to use the real thing") vs. mockist TDD ("always use a mock for any object with interesting behavior").
- **Key findings:** Per WebFetch digest — classical style: tests focus on external behavior/domain state, supports "mini-integration" style checks, but can need complex fixture setup; mockist style: better isolation/pinpointing of failures and supports outside-in design, but couples tests to implementation details and mock expectations can mask real errors.
- **Strength of evidence:** Practitioner essay / tool-documentation-adjacent — not empirical, but the standard reference for this terminology across the industry.
- **Relevance:** This project's "naive std::map reference book" compared against the real book after every event is a textbook classical/state-verification oracle pattern — the framing in this article is directly the right vocabulary for describing that design choice in test docs.

### [S7] TDD is dead. Long live testing.
- **Authors/Org:** David Heinemeier Hansson (DHH)
- **Year:** 2014
- **URL:** https://dhh.dk/2014/tdd-is-dead-long-live-testing.html (mirror of the original davidheinemeierhansson.com post)
- **What it argues:** Opinion piece arguing that test-first, mock-heavy unit testing produces "test-induced design damage" — per WebFetch digest, DHH states "Test-first units leads to an overly complex web of intermediary objects and indirection in order to avoid doing anything that's 'slow'," and that he "rarely unit test[s] in the traditional sense of the word, where all dependencies are mocked out." He advocates rebalancing toward higher-level/system tests over strict isolated-unit-test-first dogma.
- **Strength of evidence:** Expert opinion / blog post, explicitly not empirical — sparked the "Is TDD Dead?" video debate with Kent Beck and Martin Fowler (2014, Martin Fowler's site, 4 recorded sessions; content not separately fetched in this session, listed as an unverified lead below for direct quotes from Beck/Fowler's side).
- **Relevance:** Names precisely the failure mode to avoid if the coding agent starts adding seams/interfaces purely to make TDD-style isolated unit testing easier around the protocol decoder or order book, rather than because the design calls for it.

### [S8] TDD bliki definition and refactor-step warning
- Folded into S3 above (single Fowler source covering both the definition and its most common failure mode); listed separately in the takeaways only for citation clarity.

## Unverified leads

- "Is TDD Dead?" video debate (Fowler/Beck/DHH, 4 sessions, martinfowler.com / YouTube, 2014) — found via search but not fetched; would give Beck's and Fowler's direct rebuttal to DHH's design-damage claim.
- Erdogmus, Morisio, Torchiano, "On the Effectiveness of the Test-First Approach to Programming," IEEE TSE 2005 — found via search summary only (controlled experiment with undergraduates; reported test-first writers wrote more tests and more tests correlated with productivity and quality regardless of ordering) — not independently fetched/verified in this session.
- Bissi, Neto, Emer, "The Effects of Test Driven Development on Internal Quality, External Quality and Productivity: A Systematic Review" — known only via the Karac & Turhan summary table, not fetched directly.
- Munir, Moayyed, Petersen systematic review — same as above, known only secondhand via S5's table.

## Gaps: what the sources do not answer

- None of the fetched sources address TDD specifically for **binary protocol decoders defined by an external, fixed specification** (like NYSE Pillar) — all the empirical studies are about general application/business-logic code. The applicability of "granularity over sequencing" to spec-conformance work is an inference, not a tested finding.
- No source here quantifies TDD's effect when the "developer" is an AI coding agent rather than a human (see file 04 for that literature separately).
- Effect sizes for the meta-analyses (S4) were not independently re-derived from raw numbers in this session — only the qualitative "small effect" / "inconclusive" characterizations were confirmed.
- No source directly measures TDD's interaction with property-based testing or golden-file/oracle-based testing strategies (the project's actual primary defenses); the literature is entirely about unit-test-level TDD.
