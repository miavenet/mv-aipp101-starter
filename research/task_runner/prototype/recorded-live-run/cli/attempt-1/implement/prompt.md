You are carrying out one task from a task list, unattended. Nobody can answer questions.

# Task cli: Add a command line to slug.py

Make `python3 slug.py some words here` print the slug of its arguments joined by spaces. Keep slugify importable.

# Acceptance commands

    python3 -m unittest discover -s tests -q
    test "$(python3 slug.py Hello World)" = hello-world

# Rules

- Work only inside this repository. Do not commit, push or switch branches: the runner commits.
- The task is accepted only if the acceptance commands exit 0 and an independent reviewer approves the diff. Your own report does not count.
- Never make a check pass by weakening, deleting or skipping a test, or by special-casing its inputs. If the task cannot be done properly, answer with outcome "blocked" and say why.
- Do not change these files. The runner reverts any change to them: tests/*

Finish with a single JSON object, and nothing after it, matching this schema:
{"type": "object", "additionalProperties": false, "required": ["outcome", "notes"], "properties": {"outcome": {"type": "string", "enum": ["done", "blocked"]}, "notes": {"type": "string"}}}