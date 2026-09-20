# Feed-handler testing: published patterns and scenarios

Research date: 2026-09-19.

**Yes. Public feed-handler test procedures, expected-result workbooks, and replay/recovery testing patterns exist.** The closest matches to FIX-style scenario testing found here are HKEX OMD-C readiness materials and CME AutoCert+ MDP 3.0. NYSE also publishes useful historical Global OTC playback materials. These are venue-specific resources, not one interchangeable certification suite.

| Read | Purpose |
|---|---|
| [Analysis](ANALYSIS.md) | What exists, comparison with FIX, applicability and limits |
| [Sources](SOURCES.md) | Primary-source links, versions, exact locations and validation status |
| [Scenario catalogue](SCENARIOS.md) | Published precedents and 26 proposed scenario outlines |
| [Harness proposal](HARNESS.md) | How to turn the research into a reproducible test system |
| [Validation](VALIDATION.md) | Source checks, exclusions, and blind-review disposition |
| [Download manifest](sources/download-manifest.json) | GET results and hashes where a direct download succeeded |

Start with [HKEX's procedure and answer book](SOURCES.md#s03-hkex-omd-c-readiness-procedures) for the test-case/expected-result structure, and its [onboarding tools guide](SOURCES.md#s05-hkex-onboarding-tools) for replay plus simulated recovery. Use the project's own Pillar specifications to encode messages and determine protocol-specific outcomes.

This directory contains research and proposed tests. It does not implement a harness, claim exchange certification, or redistribute the downloaded third-party documents/data. A public document or sample download does not establish free access to a live certification service or permission to redistribute its contents.

The independent accuracy review is recorded in [BLIND_REVIEW.md](BLIND_REVIEW.md); see [VALIDATION.md](VALIDATION.md) for the response to its findings.
