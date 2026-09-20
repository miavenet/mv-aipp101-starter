# Validation and accuracy controls

## Source checks completed

Research date: 2026-09-19. Every source used for conclusions in [SOURCES.md](SOURCES.md) was opened and its relevant content read. Search results were discovery aids only.

- Read original exchange PDFs via browser extraction, including section/test identifiers and cover versions.
- Downloaded HKEX procedures/tools, opened the answer workbook as OOXML, and inspected actual expected-value cells.
- Downloaded and read the NYSE Global OTC instructions as DOCX XML; inspected ASCII output and binary header. Did not mislabel the binary as PCAP or claim it matches Pillar.
- Downloaded and read the exact QuickFIX input/expected-message files.
- Checked both current and upcoming NYSE specification links against local pinned revisions.
- Reviewed the newer CME notice when interpreting older reset scenarios.
- Recorded successful direct downloads with byte count and SHA-256 in [the manifest](sources/download-manifest.json). A hash establishes the inspected bytes, not semantic correctness or redistribution rights.

## Retrieval limitations

CME content was readable through browser retrieval, but direct scripted downloads returned 403. Those sources therefore have content validation but no successful local-download hash. Browser parsing failed on XLSX/DOCX/raw GitHub files; direct download and local parsing succeeded. HKEX PDF screenshots failed; readable PDF text and locally downloaded document bytes were available, and key test IDs/wording were checked from the text. No claim depends on a visually ambiguous chart.

The FIX Trading Community guide lead was excluded after failed retrieval. HKEX MMDH material was not used as OMD-C multicast evidence. No simulator, capture replay, exchange connection, or certification test was run in this research.

## Claim boundaries

Published cases and our proposed `FH-*` cases are labeled separately. The proposed quality-state API, fake clock, independent model, fuzzing and mutation jobs are engineering recommendations, not claimed exchange requirements. Public access to documentation/sample artifacts is not represented as free access to certification infrastructure.

## Blind accuracy review

An independent reviewer received only this directory and an accuracy-audit assignment. The reviewer independently checked the primary sources, cached artifacts, and all 17 successful manifest hashes. The report is [BLIND_REVIEW.md](BLIND_REVIEW.md).

Verdict: **Pass with two minor corrections; no high- or medium-severity findings.** The reviewer corrected the Nasdaq source title to its cover title and revision/date, and changed the README label from “implementation-ready cases” to “proposed scenario outlines.” Those corrections do not change the research conclusion. The review did not execute a handler, vendor software, exchange certification, or every workbook value; those limits remain explicit.
