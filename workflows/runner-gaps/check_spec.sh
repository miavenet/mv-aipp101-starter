#!/usr/bin/env bash
# The spec of one gap exists and has every required section.
# usage: workflows/runner-gaps/check_spec.sh FILE
set -euo pipefail
file=$1
[ -f "$file" ] || { echo "check_spec: missing document: $file"; exit 1; }
bad=0
for h in "Problem" "Requirements" "Design" "Alternatives rejected" "Failure cases" "Scenarios" "Implementation plan" "Documentation changes" "Open questions"; do
    grep -qiE "^#{2,3} .*${h}" "$file" || { echo "check_spec: missing section: $h"; bad=1; }
done
grep -qE '^\| *[A-Z]+-[0-9]+ *\|' "$file" || { echo "check_spec: missing section: no WHEN/THEN scenario rows"; bad=1; }
[ "$bad" -eq 0 ] && echo "check_spec: $file is complete"
exit "$bad"
