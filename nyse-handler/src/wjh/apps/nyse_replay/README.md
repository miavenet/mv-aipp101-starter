# apps/nyse_replay

Command-line entry point: replay a pcap or (later) run live, dump events and books, print stats.

```
nyse_replay --config <file.json> --source=pcap:<file> | --source=mcast
            [--dump-events[=<file>]] [--dump-ts]
            [--dump-book=<ticker>[@seq=<n>]]
            [--stats] [--latency-histogram] [--pace]
```

Planned: `main.cpp` only: parse args → `load_config` → build the `Source` variant →
`FeedHandler<EventDumper or NullConsumer>` → run → `StderrStatsSink` report. Exit code
is nonzero on config or file errors. **A stale channel is not an error exit** (it is reported in stats).

Design refs: [09: Configuration](../../../../docs/design/09-configuration.md#cli-nyse_replay)
