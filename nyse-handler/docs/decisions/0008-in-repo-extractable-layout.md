# ADR-0008: Live in the host repo, extractable later

- **Status:** Accepted
- **Date:** 2026-09-19

## Context

The host repository (the AI++ 101 chat app) already provides C++20 CMake presets,
the Docker image, Atlas, `tl::expected`, doctest, RapidCheck, nlohmann/json, and
CI with sanitizers. The handler is expected to become production code eventually.

## Decision

- Develop in this repo under the self-contained directory `nyse-handler/`, on the
  branch `nyse-feed-handler` (based on `add-yolo-mode`).
- Namespace `wjh::md`, with Pillar-specific code in `wjh::md::pillar`.
- One static library per module, with dependencies pointing one way (see [architecture](../design/01-architecture.md)).
- **Nothing includes `src/wjh/chat`.** CI enforces this with a grep or CMake check.
- Configuration is JSON.

## Alternatives considered

| Option | Why not (now) |
|---|---|
| New repository from day one | About a day of copying the build and CI setup before any feature work. |
| Mix into `src/wjh/` alongside the chat code | Harder to extract. Blurs ownership. |

## Consequences

- Extraction later means moving `nyse-handler/` and copying `cmake/`.
- Wiring `nyse-handler/` into the top-level CMake build happens with the first implementation, not now.
