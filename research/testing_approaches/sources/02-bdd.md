# Behaviour-Driven Development — Literature Review

> Note on method: WebFetch returns a small model's digest of each page, so quoted wording is second-hand unless otherwise noted. For this file I bypassed WebFetch for two sources where it failed or returned only a vague digest (Dan North's original article, and the Binamungu et al. survey PDF) and instead used `curl` + manual HTML/PDF text extraction (via `pypdf`) so the quotes below are string-matched against raw text, not model-summarized. Those are marked "verified against raw text."

## Key takeaways for this project

- BDD's own inventor frames it explicitly as a *vocabulary and communication* fix for TDD, not a new testing mechanism: Dan North's original motivation was that "test" as a word confused programmers about what/how much to test, and switching to "behaviour" language resolved that confusion [S1].
- Given/When/Then originated as a way to capture a story's **acceptance criteria** collaboratively (North + Chris Matts), explicitly to create a "ubiquitous language" shared across analysts, testers, developers, and the business [S1] — a goal that doesn't apply when there is no non-technical stakeholder and the "spec" is an exchange's binary protocol document, not a business story.
- Rigorous empirical evidence for BDD specifically (as opposed to TDD generally) is thin: the largest systematic mapping study found only 166 relevant papers over 15 years (2006-2021) and explicitly flagged a "scarcity of research with insights from the industry" and "acute shortage of metrics for measuring various aspects of BDD specifications" [S3].
- The best-evidenced *risk* of BDD in practice is scenario/step duplication becoming a maintenance burden: in a 75-practitioner, 26-country survey, 61% agreed duplication makes specs "difficult to extend and change," 49% said it makes suites slower to run, and 43% said it hurts comprehension; 40% of respondents manage duplication manually and 17% have given up managing it at all [S2].
- One survey respondent's verbatim comment is a direct warning for a small, spec-driven codebase: "We decided to not use BDD any more because it was hard to maintain it... our code underneath became less and less readable" [S2].
- For C++, the practical entry points are doctest's `SCENARIO`/`GIVEN`/`WHEN`/`THEN` macros (which are literally `TEST_CASE`/`SUBCASE` with string prefixes and console-alignment — no semantic enforcement of ordering) and Catch2's equivalent macros (`SCENARIO`/`GIVEN`/`WHEN`/`THEN`/`AND_WHEN`, mapping to `TEST_CASE`/`SECTION`) [S5][S6]. Both frameworks state explicitly that "there is nothing enforcing the correct sequencing of these macros — that's up to the programmer" [S5][S6].
- cucumber-cpp — the closest thing to "real" Gherkin/Cucumber for C++ — is effectively unmaintained: as of the issue tracker, the maintainers posted a "WANTED: A new maintainer" call because "pull requests [have been] piling up for a few years now" [S7]; live GitHub API data (checked directly) shows the repo is not archived and did get a compile-fix merge as recently as 2026-09-18, but that activity is community patches, not stewardship, and there have been zero formal GitHub releases.
- Given that, the project's actual plan — WHEN/THEN scenario tables inside design docs, naming the doctest/RapidCheck test that proves each row — is the lightweight, "living documentation" flavor of BDD (scenarios as a communication artifact, not a parsed Gherkin DSL), and it sidesteps both the tooling-maintenance risk (S7) and the duplication-maintenance risk (S2) that come from running a full Gherkin/step-definition layer.
- BDD pays off most where the empirical/practitioner literature agrees stakeholder communication is the bottleneck (cross-functional teams, business-readable acceptance criteria) [S1][S3]; none of that applies to a solo-owner project decoding an already-fixed exchange spec — here BDD's *vocabulary* (Given/When/Then as a way to name and organize test scenarios against a spec) is useful, but the *ceremony* (a Gherkin runner, step-definition indirection, cucumber-cpp) is not justified by the evidence.
- Solis & Wang's characterization (widely cited, ~166+ citations) frames BDD as extending TDD/acceptance testing with a common vocabulary and automatable scenario structure [S4] — consistent with treating BDD here as "TDD's naming convention," not a separate test-execution framework.

## Sources

### [S1] Introducing BDD
- **Author/Org:** Dan North (independent; originator of BDD, wrote JBehave)
- **Year:** 2006 (Better Software magazine, March 2006; republished on dannorth.net)
- **URL:** https://dannorth.net/introducing-bdd/ (redirects to https://dannorth.net/blog/introducing-bdd/)
- **What it argues:** The foundational BDD text. North recounts how TDD coaching kept stalling on the word "test" — programmers didn't know what to test, how much, or what to name it — and how replacing "test" with "behaviour" resolved this. He and colleague Chris Matts then generalized this to requirements/acceptance-criteria, producing the Given/When/Then scenario template.
- **Key findings/quotes (verified against raw page text via curl):** "I found the shift from thinking in tests to thinking in behaviour so profound that I started to refer to TDD as BDD, or behaviour-driven development." On the scenario template's origin: "We created a template to capture a story's acceptance criteria... Given some initial context (the givens), When an event occurs, Then ensure some outcomes." On its purpose: "If we could develop a consistent vocabulary for analysts, testers, developers, and the business, then we would be well on the way to eliminating some of the ambiguity and miscommunication that occur when technical people talk to business people." He also describes JBehave's `Given`/`Event`/outcome classes mapping directly to scenario fragments for reuse across scenarios.
- **Strength of evidence:** Practitioner/originator essay — foundational and definitional, not empirical.
- **Relevance:** Establishes that BDD's core value proposition, in its own inventor's words, is cross-role communication and a naming discipline for tests/requirements. That value proposition is largely orthogonal to a solo-owner, spec-driven decoder project — but the Given/When/Then naming discipline itself (and North's advice that a test/scenario name should describe "the next most important behaviour") is directly reusable for the project's scenario tables.

### [S2] Maintaining Behaviour Driven Development Specifications: Challenges and Opportunities
- **Authors/Org:** Grischa Liebel Binamungu (listed as "Binamungu" in citations), Nikolaos Konstantinou, Suzanne M. Embury (University of Manchester)
- **Year:** 2018 (SANER 2018)
- **URL:** https://pure.manchester.ac.uk/ws/files/181992545/SANER2018BinamunguKonstantinouEmbury.pdf
- **What it measured:** A survey of 75 BDD practitioners from 26 countries (82 raw responses, some removed/filtered), asking about BDD adoption extent, benefits, and — its main focus — the challenges of maintaining BDD specifications, especially step/scenario duplication.
- **Key findings (verified against raw PDF text via pypdf extraction):** Org type breakdown "35% public, 63% private, 1% sole trader, 1% did not say." On duplication: "61% of the respondents held the view that the presence of duplication in BDD specifications can cause them to become difficult to extend and change (leading potentially to frozen functionality)... nearly half of the respondents (49%) said that the presence of duplication in BDD specifications can cause execution of BDD suites to take longer to complete than necessary, 43% thought that duplication can make it difficult to comprehend specifications." On tooling: "duplication detection and management is done manually (40% of respondents)... a significant proportion (17%) of respondents who have given up the duplication detection and management process, because of its complexity... more than a half (57%) of the respondents are concerned with duplication detection and management." A verbatim respondent quote: "We decided to not use BDD any more because it was hard to maintain it... our code underneath became less and less readable."
- **Strength of evidence:** Practitioner survey (self-selected respondents, n=75) — not a controlled experiment, but a substantial, quantified industry survey specifically on BDD maintenance costs, which is rare in this literature.
- **Relevance:** Directly informs the risk side of the project's plan: if the team ever expands "WHEN/THEN scenario tables" into a full executable Gherkin suite, this paper's evidence says duplication management becomes a real, self-reported maintenance drag for the majority of practitioners who try it at scale.

### [S3] Behaviour Driven Development: A Systematic Mapping Study
- **Authors/Org:** (listed on arXiv/ScienceDirect; full author list not independently re-verified beyond the abstract page)
- **Year:** 2023
- **URL:** https://arxiv.org/abs/2305.05567 (also Software: Practice and Experience / ScienceDirect)
- **What it measured:** A systematic mapping of the BDD research literature: 166 papers published between 2006 and 2021, classified by publication venue, research type, and topic focus.
- **Key findings (verified via WebFetch of the arXiv abstract page):** Explicitly notes "scarcity of research with insights from the industry," an "acute shortage of metrics for measuring various aspects of BDD specifications," a "shortage of philosophical papers on BDD," and "scarcity of studies on using BDD alongside other software techniques and technologies," while noting a "notable use of case studies and experiments to study different BDD aspects."
- **Strength of evidence:** Systematic mapping study (secondary research) — the closest thing to a comprehensive survey of the BDD evidence base as a whole; honest that the base is thin, especially for industrial/quantitative evidence.
- **Relevance:** Directly supports the "be honest that evidence is thin" instruction for this file — BDD's benefits are argued from practitioner experience (S1, S8) and surveyed opinion (S2) far more than from controlled measurement of outcomes.

### [S4] A Study of the Characteristics of Behaviour Driven Development
- **Authors/Org:** Carlos Solís, Xiaofeng Wang
- **Year:** 2011 (IEEE 37th EUROMICRO Conference on Software Engineering and Advanced Applications, SEAA)
- **URL:** https://dl.acm.org/doi/10.1109/SEAA.2011.76 (full text at http://www.damiantgordon.com/... returned HTTP 403 in this session; content below is from search-result abstracts/citations only, not independently fetched)
- **What it argues:** Identifies and defines a set of core BDD characteristics (per secondary summaries: domain-specific ubiquitous language, scenario-based specification, automatable acceptance criteria) by analyzing prior literature and existing BDD toolkits, aiming to give the (at-the-time) fuzzy term "BDD" a concrete definition.
- **Key findings:** Not independently confirmed with exact quotes in this session (source PDF was inaccessible: 403 Forbidden, and a mirror returned empty content). Per search-engine summaries, it is a highly-cited (166+ citations) characterization paper rather than an empirical outcomes study.
- **Strength of evidence:** Conceptual/definitional paper, not empirical — and only confirmed via secondary summaries here, not raw text. Treat with slightly lower confidence than the string-matched sources above.
- **Relevance:** Useful only as a citation for "what counts as BDD" terminology; adds nothing on effectiveness.

### [S5] doctest — BDD-style test cases (SCENARIO/GIVEN/WHEN/THEN)
- **Org:** doctest project (C++ testing framework used by this project)
- **Year:** documentation, accessed 2026 (reflects current `master` branch)
- **URL:** https://github.com/doctest/doctest/blob/master/doc/markdown/testcases.md
- **What it documents:** doctest's BDD macros: `SCENARIO` maps to `TEST_CASE` prefixed "Scenario: "; `GIVEN`/`WHEN`/`THEN` map to `SUBCASE` prefixed "given: "/"when: "/"then: "; `AND_GIVEN`/`AND_WHEN`/`AND_THEN` chain related steps with an "and " prefix. The console reporter aligns Givens/Whens/Thens for readability.
- **Key findings/quotes:** "These macros map onto SUBCASEs except that the subcase names are the somethings prefixed by 'given: ', 'when: ' or 'then: ' respectively." Explicit caveat: "There is nothing enforcing the correct sequencing of these macros — that's up to the programmer!" Also: command-line filtering with `--test-case=`/`--subcase=` must include the "Scenario:" prefix, and subcases (hence these macros) must be used "only in the main test runner thread."
- **Strength of evidence:** Tool documentation (primary/authoritative for this specific tool) — not evidence of effectiveness, but ground truth for what the macros actually do.
- **Relevance:** Directly load-bearing: the project already plans to use doctest's SCENARIO/GIVEN/WHEN/THEN for scenario tables. This confirms it's purely syntactic sugar over `TEST_CASE`/`SUBCASE` with no semantic guarantee of ordering — the discipline of "Given before When before Then" has to be enforced by convention/review, not the framework.

### [S6] Catch2 — BDD-style syntax
- **Org:** Catch2 project (catchorg)
- **Year:** documentation, accessed 2026 (devel branch)
- **URL:** https://github.com/catchorg/Catch2/blob/devel/docs/test-cases-and-sections.md
- **What it documents:** Same pattern as doctest — `SCENARIO`→`TEST_CASE`, `GIVEN`/`WHEN`/`THEN`→`SECTION`, plus `AND_GIVEN`/`AND_WHEN`/`AND_THEN` (the latter introduced in Catch2 2.4.0). States that "a GIVEN clause may have multiple independent WHEN clauses within it," and that dependent `AND_*` clauses must be nested inside the clause they depend on.
- **Key findings:** Same explicit caveat as doctest: "there is nothing enforcing the correct sequencing of these macros" — ordering discipline is the programmer's responsibility, not the tool's.
- **Strength of evidence:** Tool documentation.
- **Relevance:** Confirms the BDD-macro behavior is essentially identical in spirit to doctest's, useful if the project ever needs to compare frameworks; also confirms these macros implement what Catch2 itself calls the "AAA/A3" (Arrange-Act-Assert) pattern under BDD naming, i.e., the doctest/Catch2 "BDD support" is naming convention, not a distinct testing paradigm.

### [S7] cucumber-cpp — maintenance status
- **Org:** cucumber (GitHub org) / cucumber-cpp repository
- **Year:** issue opened previously, checked live 2026-09-19
- **URL:** https://github.com/cucumber/cucumber-cpp/issues/242 ; repo: https://github.com/cucumber/cucumber-cpp
- **What it shows:** A maintainer-authored issue titled "WANTED: A new maintainer," stating pull requests have been "piling up for a few years now" and appealing to fork-maintainers for help; SmartBear community forum posts (found via search, not independently fetched) similarly describe the project as effectively community-abandoned by its original team.
- **Key findings (verified directly via GitHub API, not WebFetch digest):** As of 2026-09-19, the repo is **not archived**, has 330 stargazers, 15 open issues, and its most recent commit (merged 2026-09-18, a day before this research) was a community-submitted Clang compiler-compatibility fix ("Fix clang23 compilation") — i.e., the project receives sporadic community patch merges but shows no evidence of active feature stewardship, and has never cut a formal GitHub release (0 releases via API).
- **Strength of evidence:** Primary source (GitHub API + maintainer's own issue), directly verified.
- **Relevance:** Directly answers the task's question about cucumber-cpp's maintenance status: it is alive-but-unstewarded. For a project prioritizing long-term low-maintenance test infrastructure, depending on cucumber-cpp for actual Gherkin execution would be a liability; using plain doctest/Catch2 BDD-style macros (S5/S6), which are first-party features of an actively maintained framework, is the lower-risk choice — consistent with the project's existing plan to skip a Gherkin runner.

### [S8] Specification by Example (book) and "three amigos"/example mapping
- **Author/Org:** Gojko Adzic (independent consultant/author)
- **Year:** book published 2011 (Jolt Award winner); page accessed 2026
- **URL:** https://gojko.net/books/specification-by-example/
- **What it argues:** Synthesizes practices ("specification by example," "three amigos" collaborative sessions, "example mapping" with colored sticky notes for stories/rules/examples/questions, "living documentation") drawn from Adzic's study of "over 50 projects" across company sizes and agile methodologies (XP, Scrum, Kanban).
- **Key findings/quotes (verified via WebFetch of the author's own page):** "how successful Lean and Agile teams design, develop, test and deliver software efficiently... the result of a research on how teams all over the world specify, develop, test and deliver the right software, without defects, in very short iterative delivery cycles," drawing on projects "from high-traffic web sites to internal back-office systems."
- **Strength of evidence:** Practitioner synthesis / multi-case-study book, not a controlled study — Adzic's own framing is "research" in the qualitative, cross-case-study sense, not a statistically powered comparison.
- **Relevance:** "Three amigos" and "example mapping" are the lightweight, low-ceremony end of the BDD spectrum this project's scenario-table approach resembles: examples/scenarios as a collaborative-analysis artifact and living documentation, without necessarily wiring them to an executable Gherkin runner. This maps well onto "WHEN/THEN scenario tables in design docs, each row naming the test that proves it" — it's exactly the "specification by example as living documentation" pattern minus the multi-role collaboration (since there's one owner and one AI agent, not three amigos).

## Unverified leads

- Solís & Wang (2011) full text — blocked by 403/empty-page errors from two mirrors in this session; only secondary summaries were obtained (see S4).
- SmartBear community thread "[CPP] Status of maintenance" — found via search snippet only, not fetched; likely has more first-hand user commentary on cucumber-cpp's real-world usability.
- The "Is BDD dead?"-style critical practitioner essays (analogous to the TDD-is-dead debate) — not found/searched for directly in this session; it's unclear whether an equivalent high-profile critique of BDD-as-ceremony exists in the same way it does for TDD.
- Cyrille Martraire's "Living Documentation" book — referenced by name in the BDD community as the fuller treatment of the "docs generated from executable specs" idea; not fetched in this session.

## Gaps: what the sources do not answer

- No source measured BDD's effect (positive or negative) on defect rates, coverage, or delivery time in a controlled way comparable to the TDD literature in file 01 — the mapping study (S3) confirms this gap exists in the literature generally, it doesn't fill it.
- Nothing here addresses BDD/Gherkin applied specifically to a binary protocol decoder or an order-book-style stateful system; all practitioner sources (S1, S8) are framed around business-facing application behavior, not wire-format or invariant-style specifications.
- No source quantifies the "single developer + AI coding agent, no non-technical stakeholder" scenario explicitly — the take in the key-takeaways section that BDD's ceremony isn't justified there is an inference from S1/S3's own stated value proposition (stakeholder communication), not a direct empirical finding.
- No data was found on how doctest's or Catch2's SCENARIO/GIVEN/WHEN/THEN macros are used in practice at scale (e.g., whether teams that use them still hit the same duplication problems Binamungu et al. found in full Gherkin suites) — that comparison does not appear to have been studied.
