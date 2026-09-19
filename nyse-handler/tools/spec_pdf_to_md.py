#!/usr/bin/env python3
"""Convert an NYSE Pillar client specification PDF to Markdown.

Usage: spec_pdf_to_md.py SPEC.pdf OUT.md

Needs pypdf (pure Python). General converters such as markitdown flatten the
field-layout tables of these specs, so this script works from pypdf's
layout-preserving text, where table columns survive as runs of spaces:

  - numbered section titles become headings,
  - "FIELD NAME / OFFSET / SIZE / FORMAT / DESCRIPTION" tables become Markdown
    tables, with wrapped description lines folded into their row,
  - everything else is kept as text, with a marker per PDF page.

The output is a reading aid. The PDF stays the source of truth: equations and
rotated column headings do not extract (see the notes the script adds).
"""

import re
import sys

import pypdf

FIELD_ROW = re.compile(r"^\s{0,3}(\S.*?)\s{2,}(\d+)\s{2,}(\d+)\s{2,}(Binary|ASCII)\b\s*(.*)$")
# A row whose field name wrapped onto its own line: offset/size/format with no name.
NAMELESS_ROW = re.compile(r"^\s+(\d+)\s{2,}(\d+)\s{2,}(Binary|ASCII)\b\s*(.*)$")
TABLE_HEAD = re.compile(r"^\s*FIELD NAME\s+OFFSET\s+SIZE\s+FORMAT")
# Titles are short; longer numbered lines are list items in the body text.
SECTION = re.compile(r"^\s{0,2}(\d+(?:\.\d+)*)\.?\s{1,}([A-Z«][^.]{2,62}?)\s*$")
TOC_LINE = re.compile(r"\.{6,}")
FOOTER = re.compile(r"^\s*(\d{1,3}|©.*|.*Client Specifications? v[\d.a-z]+)\s*$")


def clean(text):
    return re.sub(r"\s+", " ", text).strip().replace("|", "\\|")


def flush_table(rows, out):
    if not rows:
        return
    out += ["", "| Field | Offset | Size | Format | Description |", "|---|---|---|---|---|"]
    for name, off, size, fmt, desc in rows:
        out.append(f"| `{clean(name)}` | {off} | {size} | {fmt} | {clean(desc)} |")
    out.append("")
    rows.clear()


def convert(pdf_path):
    reader = pypdf.PdfReader(pdf_path)
    out, rows, in_table, pending_name = [], [], False, ""
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text(extraction_mode="layout") or ""
        out.append(f"\n<!-- PDF page {number} -->\n")
        for line in text.splitlines():
            if not line.strip() or FOOTER.match(line):
                continue
            if TABLE_HEAD.match(line):
                in_table = True
                continue
            if in_table and line.strip() == "(BYTES)":
                continue
            row = FIELD_ROW.match(line)
            nameless = NAMELESS_ROW.match(line) if in_table else None
            if in_table and row:
                rows.append([row[1], row[2], row[3], row[4], row[5]])
                pending_name = ""
                continue
            if nameless:
                rows.append([pending_name, nameless[1], nameless[2], nameless[3], nameless[4]])
                pending_name = ""
                continue
            section = SECTION.match(line) if not TOC_LINE.search(line) else None
            if section:
                flush_table(rows, out)
                in_table = False
                depth = min(section[1].count(".") + 2, 5)
                out += ["", f"{'#' * depth} {section[1]} {clean(section[2])}", ""]
                continue
            if in_table:
                indent = len(line) - len(line.lstrip())
                if indent < 12 and rows and not pending_name and len(line.strip()) < 28:
                    # Short text in the name column: either the rest of the previous
                    # field's name, or the name of a row whose numbers come next.
                    pending_name = line.strip()
                    if not NAMELESS_ROW.match(line):
                        rows[-1][0] += " " + pending_name if rows[-1][0] else pending_name
                        pending_name = ""
                    continue
                if rows:
                    rows[-1][4] += " " + line.strip()
                    continue
            out.append(TOC_LINE.sub(" … ", line.rstrip()) if TOC_LINE.search(line) else clean(line))
        # Tables continue across pages; they are flushed at the next section.
    flush_table(rows, out)
    return reader, "\n".join(out)


def main():
    pdf_path, md_path = sys.argv[1], sys.argv[2]
    reader, body = convert(pdf_path)
    header = [
        f"# {pdf_path.rsplit('/', 1)[-1]}",
        "",
        f"Converted from the PDF ({len(reader.pages)} pages) by `tools/spec_pdf_to_md.py`. **The PDF is the source of",
        "truth.** Known losses: equations (for example the price formula in Common Client §3.5), rotated",
        "column headings (the per-market columns of the Imbalance table), and some bullet nesting.",
        "",
    ]
    with open(md_path, "w") as f:
        f.write("\n".join(header) + body + "\n")


if __name__ == "__main__":
    main()
