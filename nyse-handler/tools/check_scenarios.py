#!/usr/bin/env python3
"""Report which design-doc scenarios are proven by a test.

Usage: check_scenarios.py [--strict] [--module ARB,BOOK]

Reads the "Scenarios" tables in docs/design/*.md. Each row names a doctest
TEST_CASE; this script searches src/ for it. In a test name, <...> matches any
text, for a family of cases. --strict exits 1 if any selected scenario has no
test, or if an ID or test name is used twice.
"""

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ROW = re.compile(r"^\|\s*([A-Z]+-[A-Z]?\d+)\s*\|(.+)\|\s*`([^`]+)`[^|]*\|\s*$")
TEST_CASE = re.compile(r'(?:TEST_CASE|SCENARIO|TEST_CASE_FIXTURE|rc::prop|rc::check)\s*\(\s*(?:[\w:]+\s*,\s*)?"((?:[^"\\]|\\.)*)"')


def scenarios():
    for doc in sorted((ROOT / "docs" / "design").glob("*.md")):
        for line in doc.read_text().splitlines():
            m = ROW.match(line)
            if m:
                yield m[1], m[3], doc.name


def test_names():
    names = []
    src = ROOT / "src"
    for path in src.rglob("*") if src.is_dir() else []:
        if path.suffix in (".cpp", ".cc", ".hpp", ".h"):
            names += TEST_CASE.findall(path.read_text(errors="replace"))
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--module", default="", help="comma-separated ID prefixes, e.g. ARB,BOOK")
    args = parser.parse_args()
    wanted = {p.strip().upper() for p in args.module.split(",") if p.strip()}

    rows = [r for r in scenarios() if not wanted or r[0].split("-")[0] in wanted]
    names = test_names()
    problems = []
    for label, values in (("scenario ID", [r[0] for r in rows]), ("test name", [r[1] for r in rows])):
        problems += [f"duplicate {label}: {v}" for v in sorted({v for v in values if values.count(v) > 1})]

    proven = 0
    for sid, test, doc in rows:
        pattern = re.compile("^" + ".+".join(re.escape(part) for part in re.split(r"<[^>]*>", test)) + "$")
        hits = [n for n in names if pattern.match(n)]
        proven += bool(hits)
        print(f"{'ok     ' if hits else 'planned'}  {sid:<8} {test}  [{doc}]")
        if not hits:
            problems.append(f"no test for {sid}: {test}")
    print(f"\n{proven}/{len(rows)} scenarios have a test")
    if args.strict and problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
