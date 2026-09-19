# 09 — Configuration

## Format

**JSON**, loaded with nlohmann/json at startup and validated into strong types. It is
**never** read on the hot path. Loading returns `tl::expected<Config, ConfigError>`.

Why JSON rather than `.env`: the channel map is structured, nested data.
nlohmann/json is already a dependency of the host repo.

## Schema (draft)

```jsonc
{
  "feed": "nyse-integrated",            // informational; checked for the expected value
  "spec_version": "<recorded at implementation>",
  "channels": [
    {
      "id": 1,
      "lines": {
        "A": { "group": "<multicast IP>", "port": 0, "interface": "<ifname or IP>" },
        "B": { "group": "<multicast IP>", "port": 0, "interface": "<ifname or IP>" }
      }
    }
  ],
  "arbitration": {
    "gap_window_ns": 5000000,
    "max_buffered_packets": 1024
  },
  "capacity": {
    "max_symbols": 16384,
    "max_orders": 8000000,
    "max_levels_per_side": 4096,
    "anomaly_ring": 4096
  }
}
```

The numbers above are **placeholders**, to be sized from real data. Multicast
groups and ports come from NYSE's published channel and IP documentation for the
production and certification environments. They are **never** hard-coded.

## Validation rules

- Channel ids are unique. Every (group, port) pair is unique across all lines.
- Each channel has both an A and a B line. A single line is allowed with a warning, since some pcaps may have only one.
- Capacities are > 0. `gap_window_ns` > 0.

## CLI (nyse_replay)

```
nyse_replay --config <file.json> --source=pcap:<file> | --source=mcast
            [--dump-events[=<file>]] [--dump-ts]
            [--dump-book=<ticker>[@seq=<n>]]
            [--stats] [--latency-histogram]
            [--pace]                       # future: honour capture timing
```

Configuration precedence for CLI flags and the file follows the host repo:
command line > file > built-in defaults.

## Example files

Placed in [`config/`](../../config/README.md). The examples use **placeholder** addresses and
are for synthetic tests only.
