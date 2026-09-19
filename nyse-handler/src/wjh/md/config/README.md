# config

**Responsibility:** load and validate JSON configuration at startup.

## Planned contents

| File | Contents |
|---|---|
| `Config.hpp` | `Config`, `ChannelConfig`, `LineConfig`, `ArbitrationConfig`, `CapacityConfig` (strong types) |
| `LoadConfig.hpp/.cpp` | `tl::expected<Config, ConfigError> load_config(path)` via nlohmann/json |

## Rules
- Never read on the hot path.
- Validation rules in [09](../../../../docs/design/09-configuration.md#validation-rules).

## Depends on
core, nlohmann/json, tl::expected
