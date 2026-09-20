# Validated primary sources

Checked 2026-09-19. “Validated” means the relevant source content was actually read, not merely found in a search snippet. It does not mean the exchange's service was exercised. Browser retrieval and direct downloads are distinguished. Source files were inspected in `/tmp`; only metadata/hashes are retained here.

## S01 QuickFIX test definitions

Publisher: QuickFIX project. [Repository directory](https://github.com/quickfix/quickfix/tree/master/test/definitions).

Read the raw [invalid-checksum case](https://raw.githubusercontent.com/quickfix/quickfix/master/test/definitions/server/fix44/3b_InvalidChecksum.def) and [simultaneous-resend case](https://raw.githubusercontent.com/quickfix/quickfix/master/test/definitions/server/fix44/20_SimultaneousResendRequest.def). They contain scripted inputs and expected messages. Both raw files downloaded successfully; bytes and hashes are in the manifest. `master` is mutable; hashes identify the inspected versions. These are FIX implementation tests, not exchange-neutral certification.

## S02 CME AutoCert MDP 3.0

Publisher: CME Group. [AutoCert+ MDP 3.0 manual](https://www.cmegroup.com/tools-information/webhelp/autocert-mdp3/Content/Autocert-MDP3-User-Manual.pdf).

Cover date October 24, 2022; copyright page says 2025. Inspected PDF pages 18–36, especially book management, MBP/MBO recovery, TCP replay and channel reset. The manual also covers definitions, statistics, market state and precision. Recovery tests deliberately omit updates and reference data, then ask for recovered book values. Available cases depend on the interview/connection type. This is a public manual for a credentialed tool, not a downloadable standalone simulator.

Browser extracted the 44-page PDF and rendered a recovery page. Direct urllib GET returned 403; no local-file hash is claimed. Page positions refer to the PDF page count, not search-result dating. Do not use this manual alone to infer current reset semantics; see S13.

## S03 HKEX OMD-C readiness procedures

Publisher: HKEX. [Procedure PDF](https://www.hkex.com.hk/-/media/HKEX-Market/Services/Market-Data-Services/Infrastructure/HKEX-Orion-Market-Data-Platform-Securities-Market-OMD-C/OMDC-Readiness-Test-Procedures-%28Version-1%2C-d-%2C10a%29.pdf), linked from the [OMD-C page](https://www.hkex.com.hk/OMDC?sc_lang=en).

Cover: **1.10, April 24, 2023**; URL says `10a`, browser metadata misleadingly says 1.9. The physical file has 13 pages while footers still say `/15`. Use section/test IDs. Relevant conditions: §7.2 **3.1–3.4** gaps/arbitration/refresh; **4.1–4.6** retransmission; **5.1** capacity; **6.1–6.5** failover/reset. §3 specifies comparison with an answer book. Negative recovery-service cases are identified in the §6 footnotes as open-test-environment work. Browser text and direct PDF download verified. This is multicast OMD-C, not unicast MMDH certification.

## S04 HKEX answer workbook

Publisher: HKEX. [Readiness Test Answer Book 2.10](https://www.hkex.com.hk/-/media/HKEX-Market/Services/Market-Data-Services/Infrastructure/HKEX-Orion-Market-Data-Platform-Securities-Market-OMD-C/OMDC-Readiness-Test-Answer-Book-%28Version-2%2C-d-%2C10%29.xlsx).

Followed the visible 2.10 link on the OMD-C page, downloaded HTTP 200, inspected OOXML workbook/shared strings/cells. Verified `Revision List`, `Test Conditions`, `Verification Instructions`, and scenario sheets such as `1-1`. That sheet contains field-level expected values and result cells. This is a real expected-result workbook, not just a link title. We did not execute its tests or validate every expected numeric value. Browser could not parse XLSX; local OOXML inspection supplied the verification.

## S05 HKEX onboarding tools

Publisher: HKEX. [OMD On-boarding Tools User Guide 3.1](https://www.hkex.com.hk/-/media/HKEX-Market/Services/Market-Data-Services/Infrastructure/OMD_Onboarding_Tools_User_Guide_3_1.pdf), April 24, 2023.

Read §1.2, §2.3–2.4, §3.1–3.6. Describes canned PCAP playback with tcpreplay, A/B delivery, an RTS simulator, and replay-rate control. Installation refers to separately provided packages/media. Public documentation therefore establishes the architecture, not anonymous availability of every tool/data package. The published OS prerequisites are historical; they are not a recommendation to deploy those OS versions today. Browser text and direct download verified.

## S06 NYSE Global OTC testing instructions

Publisher: NYSE. [Testing instructions DOCX](https://www.nyse.com/publicdocs/nyse/data/Global-OTC-Testing-Instructions.docx), June 4, 2015; linked from the [Global OTC catalog](https://www.nyse.com/data-products/catalog/global-otc).

Downloaded and read `word/document.xml`. The historical instructions distinguish playback comparison against decoded field values from order-entry-driven simulated trading. They describe the binary companion as a recording of wire packets. Treat this as a published testing precedent, not current Pillar instructions, service hours or entitlement information.

## S07 NYSE Global OTC sample artifacts

Publisher: NYSE. [Decoded Integrated output](https://www.nyse.com/publicdocs/nyse/data/GlobalOTC_Replay_IBF_Output.txt) and [binary Integrated recording](https://www.nyse.com/publicdocs/nyse/data/GlobalOTC_Replay_IBF.bin).

Both downloaded HTTP 200: **67,177 bytes** text and **5,974 bytes** binary. Text begins with a July 1, 2015 run and contains decoded message fields. Binary prefix `1e000c01` is not a standard classic-PCAP or PCAPNG magic value. Do not feed it to a PCAP reader without a format adapter. We verified availability and inspected content/header, not full byte-for-byte agreement between the pair or suitability for Pillar.

## S08 Nasdaq ISE recovery guide

Publisher: Nasdaq. [ISE Replatform Protocol Release Notes, version 1.5 (April 24, 2017)](https://www.nasdaq.com/docs/ISEReplatformReleaseNotes.pdf).

Read §7.2, physical PDF page 16. It distinguishes missing multicast ranges, extended outages/late starts using GLIMPSE, and Soup-based replay. Historical ISE/GEMX/MRX migration context matters: this is not a current Nasdaq equities conformance suite. The passage even uses “PHLX Depth” inside the ISE discussion; do not import its exact sequence-boundary wording as a Pillar rule. Browser text and direct download verified.

## S09 Nasdaq testing facility

Publisher: Nasdaq. [Nasdaq Testing Facility](https://www.nasdaqtrader.com/Trader.aspx?id=TestingFacility).

Read the facility and market-data sections: test infrastructure exists for integrated client systems and test market-data feeds. This establishes an environment, not a free public scenario corpus. Browser and direct GET verified. We did not enroll, confirm access costs, or use its services.

## S10 NYSE Pillar common specification

Publisher: NYSE. [Common specification PDF](https://www.nyse.com/publicdocs/nyse/data/NYSE_Pillar_Equities_Common_Client_Specification.pdf). Inspected version **2.4s, July 30, 2026**, matching the revision pinned locally.

Read §§2–3, 5.1, 6–7, 8.1–8.5. These provide framing/sequencing, replay/refresh, response and lifecycle contracts. §8.5.1 explicitly requires Request Server readiness certification before production sessions. That requirement is narrower than claiming a publicly downloadable complete Pillar test suite. Browser text and direct PDF download verified; hash recorded. The URL is mutable; applicability is constrained by S12.

## S11 NYSE Pillar integrated specification

Publisher: NYSE. [Integrated specification PDF](https://www.nyse.com/publicdocs/nyse/data/NYSE_Pillar_Integrated_Feed_Client_Specification.pdf). Inspected version **2.5h, July 30, 2026**, also pinned locally.

Use its individual Add/Modify/Delete/Execution/Replace/Refresh message sections for book fixtures. Browser text and direct download verified. This is the message-semantics authority for the proposed profile, not proof that our proposed scenarios are official certification tests.

## S12 NYSE current versus upcoming index

Publisher: NYSE. [Proprietary Data Products Technical Documents](https://www.nyse.com/market-data/technical-documents).

Verified current-column links to Common 2.4r and Integrated 2.5g, and upcoming-Q4 links resolving to Common 2.4s and Integrated 2.5h on the research date. Followed and read all four PDF covers. This is why the project's newer pinned revisions must not be silently described as current production. Direct index GET also succeeded.

## S13 CME reset-semantics update

Publisher: CME Group. [August 10, 2026 Globex notice](https://www.cmegroup.com/notices/electronic-trading/2026/08/20260810.html), section “Update MBP and MBOFD Market Recovery.”

The notice announces preservation of daily statistics after channel reset, with rollout starting August 16, 2026. It is concrete evidence that older test expectations may need revision. Do not generalize “reset means clear all state.” Browser content read; direct urllib GET returned 403. We did not independently certify completion of that rollout for every channel.

## S14 CME BrokerTec replay test

Publisher: CME Group. [Recovery via TCP Replay](https://www.cmegroup.com/tools-information/webhelp/autocert-brokertec/Content/tcp.html).

Read the scripted induced-gap, logon, data request, recovered-value confirmation, and logout sequence. It demonstrates an interactive recovery test rather than passive replay alone. Browser content read; direct urllib GET returned 403. BrokerTec's transport/messages are not Pillar's.

## Sources investigated but not used to support conclusions

| Lead | Disposition |
|---|---|
| FIX Trading Community implementation-guide search result | Relevant snippet, but direct dev host did not resolve; main-site path returned 404. Replaced with actually fetched QuickFIX definitions for the comparison. |
| HKEX MMDH certification procedures 1.8 | Read the separate unicast-hub document; excluded from the multicast OMD-C scenario mapping to avoid mixing products. |
| TickChaos repository search result | Not validated as software or a mature testing suite; not recommended here. |
| Public third-party PCAP vendors | Outside this research's verified scenario sources; availability of a capture alone is not a correctness oracle. |

No conclusion depends on a search snippet, an inaccessible article, or a claimed execution of vendor software.
