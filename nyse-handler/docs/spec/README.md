# Spec tracking

## Source of truth

**NYSE Pillar Integrated Feed Client Specification: latest version**, together with the
**XDP Common Client Specification** it depends on for the packet header, delivery flags,
and retransmission/refresh.

| Item | Value |
|---|---|
| Integrated Feed spec version | **TBD: record when fetched at the start of implementation** |
| Integrated Feed spec date | TBD |
| Common Client spec version | TBD |
| Common Client spec date | TBD |
| Fetched from | TBD (NYSE market data documentation site) |
| Fetched on | TBD |

## Rules

1. **No offsets from memory.** Every field offset, size, type code, and enum value
   comes from the specs recorded above.
2. **Cite at the definition.** Each offset table entry carries a comment:
   `// Integrated Feed v<X>, §<section>, Table <n>`.
3. **If the spec can't be fetched, stop.** Ask the owner for the PDFs and do not guess.
4. **Upgrading the spec version** means updating the table above, checking each changed
   message against the fixtures, adding fixtures for new messages, and noting the change
   in the [message catalog](message-catalog.md).
5. PDFs may be stored in `docs/spec/pdf/` **only if** redistribution within the team is
   permitted by NYSE's terms. Otherwise keep only the version and URL here.

## Files

- [message-catalog.md](message-catalog.md): every message type, verification status, and book effect.
