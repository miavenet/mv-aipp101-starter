# Documentation checks

## Mermaid

Run `python3 task_runner/tools/lint_mermaid.py` from the repository root with the official `mmdc`
CLI on `PATH` to render-check every tutorial and runbook diagram. Add `--fix` for the narrowly
defined safe repairs, or `--structure-only` when `mmdc` is unavailable (that mode does not validate
Mermaid syntax).

For the version used to verify these diagrams, install
`npm install --prefix /tmp/task-runner-mermaid @mermaid-js/mermaid-cli@11.12.0` and pass
`--mmdc /tmp/task-runner-mermaid/node_modules/.bin/mmdc`. The fixer only normalizes Mermaid fences,
replaces ambiguous colons in Gantt labels, and adds contrasting text to hexadecimal class fills;
it reports anything it cannot repair without guessing.
