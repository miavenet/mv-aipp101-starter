# config/

Configuration files for `nyse_replay`. The schema is documented in
[09: Configuration](../docs/design/09-configuration.md).

## Planned files

| File | Purpose |
|---|---|
| `synthetic.json` | Channel map and capacities for the synthetic test pcaps. **Placeholder** addresses. |
| `schema.json` (optional) | JSON Schema for editor validation |

## Rules

- **No production multicast addresses or credentials are committed here.** Production
  configs live with deployment, using addresses taken from NYSE's published channel documentation.
- Every example file states in its content that it is synthetic.
