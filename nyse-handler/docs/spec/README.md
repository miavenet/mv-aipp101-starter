# Spec tracking

## Source of truth

**NYSE Pillar Integrated Feed Client Specification**, together with the **Pillar Equities Common
Client Specification** it depends on for the packet header, delivery flags, control messages, and
retransmission/refresh.

| Item | Value |
|---|---|
| Integrated Feed spec version | **2.5h** |
| Integrated Feed spec date | July 30, 2026 |
| Integrated Feed URL | `https://www.nyse.com/publicdocs/nyse/data/NYSE_Pillar_Integrated_Feed_Client_Specification.pdf` |
| Integrated Feed SHA-256 | `927fbc83c24b21a2b661f68751c54cbf37864fc75e0a35ad1e9413872852c100` (27 pages) |
| Common Client spec version | **2.4s** |
| Common Client spec date | July 30, 2026 |
| Common Client URL | `https://www.nyse.com/publicdocs/nyse/data/NYSE_Pillar_Equities_Common_Client_Specification.pdf` |
| Common Client SHA-256 | `58d1d37396355c070d2e8504627f06992c074ace67303efad92e37efa52ed6b9` (33 pages) |
| Found via | `https://www.nyse.com/market-data/technical-documents` |
| Fetched on | 2026-09-19 |

Both URLs are unversioned: NYSE replaces the file in place when a new version is published. The
checksum identifies exactly what we built against. If a re-download has a different checksum, the
spec has changed and rule 4 applies.

**Trap found while fetching.** The Integrated Feed *product page*
(`/market-data/real-time/integrated-feed`) still links v2.5 from May 2022 and Common Client v2.4k
from 2024. The *technical documents* page has the current files. Always start from the technical
documents page.

What changed between v2.5 and v2.5h, from the document history: no message layout changes. The
Imbalance message's significant-imbalance indicator became a reserved field (2.5d), Next Day
settlement was removed from the trade conditions (2.5c), NYSE Chicago was renamed NYSE Texas (2.5e),
the auction appendix moved to a separate document (2.5g), and publication times were updated for the
overnight session (2.5h).

## Rules

1. **No offsets from memory.** Every field offset, size, type code, and enum value
   comes from the specs recorded above.
2. **Cite at the definition.** Each offset table entry carries a comment:
   `// Integrated Feed v<X>, §<section>` or `// Common Client v<X>, §<section>`.
3. **If the spec can't be fetched, stop.** Ask the owner for the PDFs and do not guess.
4. **Upgrading the spec version** means updating the table above, checking each changed
   message against the fixtures, adding fixtures for new messages, and noting the change
   in the [message catalog](message-catalog.md).
5. **The PDFs are not committed.** They are marked "All Rights Reserved" and this repository is
   public. They live in `docs/spec/pdf/`, which is gitignored, next to a Markdown conversion of
   each. Re-create that directory with the steps below.

## Re-creating `docs/spec/pdf/`

```sh
cd nyse-handler/docs/spec && mkdir -p pdf && cd pdf
curl -LO https://www.nyse.com/publicdocs/nyse/data/NYSE_Pillar_Integrated_Feed_Client_Specification.pdf
curl -LO https://www.nyse.com/publicdocs/nyse/data/NYSE_Pillar_Equities_Common_Client_Specification.pdf
sha256sum *.pdf          # compare with the table above
python3 ../../../tools/spec_pdf_to_md.py <spec>.pdf <spec>.md    # needs pypdf
```

The Markdown conversion is a reading and searching aid. It turns every field-layout table into a
real table and every numbered section into a heading. It loses equations and the rotated per-market
column headings of the Imbalance table, so the PDF stays the source of truth. Microsoft's
`markitdown` was tried first and rejected for these files: it produced no headings and flattened the
layout tables into plain lines.

## Files

- [message-catalog.md](message-catalog.md): every message type, verification status, and book effect.
- [field-layouts.md](field-layouts.md): offset, size and format of every field, checked mechanically.
