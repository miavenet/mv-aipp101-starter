# Analysis

## What is available

The answer is stronger than “replay some PCAPs.” Exchanges publish tests that deliberately alter the input stream and then check reconstructed state. The source inventory separates actual test procedures from specifications, historical examples, and tools.

| Resource | Evidence available | Appropriate use |
|---|---|---|
| HKEX OMD-C | Readiness procedure, answer workbook, onboarding guide | Model for a feed-handler acceptance suite; [S03–S05](SOURCES.md#s03-hkex-omd-c-readiness-procedures) |
| CME MDP 3.0 AutoCert+ | Published certification manual with book, recovery, reset, and other tests | Model for staged scenario execution; [S02](SOURCES.md#s02-cme-autocert-mdp-30) |
| NYSE Global OTC | Historical instructions, decoded output, and binary replay artifact | Field-level oracle pattern; [S06–S07](SOURCES.md#s06-nyse-global-otc-testing-instructions) |
| Nasdaq ISE replatform guide | Explicit recovery scenarios | Historical cross-check, not current universal Nasdaq certification; [S08](SOURCES.md#s08-nasdaq-ise-recovery-guide) |
| NYSE Pillar | Protocol specifications and Request Server certification requirement | Authority for this project's wire/state behavior; [S10–S12](SOURCES.md#s10-nyse-pillar-common-specification) |

I did not establish a public, venue-neutral executable suite with a complete Pillar expected-output corpus. That is a bounded search result, not proof that none exists. The practical approach is to adopt the published testing structure and implement a Pillar-specific profile.

## Comparison with FIX

QuickFIX supplies concrete input/expected-message definitions, including invalid-checksum and simultaneous-resend cases. Those are a useful public example of executable protocol scenarios, but they are implementation tests, not a universal exchange certification standard. [S01](SOURCES.md#s01-quickfix-test-definitions).

The following mapping is our engineering synthesis, not a claim that the protocols are equivalent:

| FIX testing idea | Feed-handler analogue | What the oracle should observe |
|---|---|---|
| Script inputs and expected responses | Script packets, recovery responses, and clock events | Decoded events, recovery requests, validity state, and book state |
| Session sequencing/recovery | Channel sequencing and redundant-line arbitration | Missing ranges and duplicate suppression |
| Application workflow assertions | Order/level lifecycle and reference-data interpretation | State after each logical event |
| Session reconnect scenarios | Late join, publisher change, refresh interruption | Correct transition back to trusted data |
| Counterparty-specific rules | Venue/feed/revision-specific profile | Exact scope and semantics pinned to source sections |

Avoid a false divide: FIX can carry market data, and market-data certification can involve FIX-style messages. CME's BrokerTec replay test explicitly combines an induced gap with logon, request/response, and recovered-data verification. [S14](SOURCES.md#s14-cme-brokertec-replay-test).

## Patterns worth adopting

**Compare against a separately prepared answer.** A decoder that does not crash is not necessarily correct. Expected decoded fields, book states, and recovery requests should come from a reviewed fixture or a deliberately simple independent model. Do not let the production decoder generate its own expected results. The NYSE playback instructions and HKEX answer workbook demonstrate externally supplied expectations; our proposed checkpoint and reference-model design extends that idea. [S04](SOURCES.md#s04-hkex-answer-workbook), [S06](SOURCES.md#s06-nyse-global-otc-testing-instructions).

**Test recovery as a conversation.** A capture supplies recorded inputs; it cannot dynamically decide whether a request is correct or generate a new response to that request. Use replay together with a controlled recovery peer. HKEX documents this division directly. [S05](SOURCES.md#s05-hkex-onboarding-tools).

**Keep three oracles separate.** For replay recovery, verify event continuity as well as the final book. For snapshot recovery, verify the recovered state while retaining any unrecoverable event-history gap. For performance, verify loss and correctness while measuring delay. An identical final book does not prove that every intermediate trade or update was delivered. These are proposed correctness criteria; each profile must specify the consumer guarantees it actually offers.

**Use real and synthetic data for different evidence.** Real captures reveal realistic packetization and message mix; small generated cases make boundary errors and recovery decisions explainable. Run both through the same ingest path, with provenance and starting-state requirements. A mid-session capture without initial state cannot validate a full book from empty.

## Applying this to the NYSE project

The checkout pins Common **2.4s** and Integrated **2.5h**, both dated July 30, 2026. The inspected NYSE index links these through the **upcoming Q4** column; its current column links 2.4r/2.5g. Preserve that distinction in fixtures and deployment configuration. A newer PDF publication date is not evidence that its behavior is already live. [S10–S12](SOURCES.md#s10-nyse-pillar-common-specification).

The local Common PDF and markdown conversion are available under [the pinned specification directory](../../nyse-handler/docs/spec/pdf/NYSE_Pillar_Equities_Common_Client_Specification_v2.4s.md). Use the original PDF to settle ambiguities in converted tables. The catalogue below gives section pointers, but it deliberately does not invent packet bytes or substitute another exchange's recovery protocol.

NYSE's Global OTC artifact is from a different product and an older protocol generation. It is useful evidence for the testing method, not a ready-made Pillar acceptance fixture. The `.bin` file must not be called a PCAP merely because it contains recorded wire data. [S06–S07](SOURCES.md#s06-nyse-global-otc-testing-instructions).

Prioritize parser/framing, sequence arbitration, deterministic state changes, and recovery first. Add live exchange qualification after the offline suite is trustworthy. Where this implementation intentionally lacks recovery, a scenario should assert the declared degraded/unavailable state; it must not report successful recovery.
