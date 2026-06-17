### 0.3.0 (2026-06-17)

- **Light effects** curated to four Wiz presets (Warm White, Daylight, Sunset,
  Focus) with matching NeoPixel preview colors; empty `HA_LIGHT_EFFECTS` uses
  built-in defaults instead of auto-fetching full `effect_list`
- **Brightness presets** expanded to five evenly spaced levels (off/low/mid/high/max:
  0%, 25%, 50%, 75%, 100%); NeoPixel preview scales white to match HA brightness
- Sample scene list: `scene.redalert` replaced with `scene.atdesk_soft_lights`;
  NeoPixel preview colors updated (`soft_white`, `dim_white`)

### 0.2.0 (2026-06-17)

### Added

- **Light Effects mode** (`ha_light`): browse and apply HA `light.*` effects via
  `HA_LIGHT_EFFECTS` or auto-fetched `effect_list`
- **Brightness mode** (`ha_brightness`): dim/soft/bright presets via
  `HA_LIGHT_BRIGHTNESS`
- NeoPixel preview colors for effects and brightness (`HA_LIGHT_EFFECT_COLORS`,
  `HA_LIGHT_BRIGHTNESS_COLORS`)
- `AGENTS.md` — project-specific guidance for AI coding agents (commands,
  structure, boundaries)
- HA client support for `light.turn_on` with `effect` and `brightness`; entity
  state and effect list fetching

### Changed

- Replaced Wiz-specific control with manufacturer-agnostic HA light entity
  control (`HA_LIGHT_ENTITY_ID`)
- **Button mapping:** long push cycles modes; double push reboots (was reversed)
- Triple-mode operation: Home Assistant scenes, light effects, brightness
  presets
- NVM state format uses magic byte `0x43` with legacy `0x42` migration
- README and `settings.sample.toml` updated for new modes and config keys

### Removed

- `adafruit-circuitpython-wiz` dependency
- `HA_WIZ_LIGHT_ENTITY_ID` and Wiz-specific code paths

## 0.1.0 (2026-06-13)

### Feat

    Aspide CircuitPython application with rotary encoder and NeoPixel ring control
    Home Assistant scene integration and Wiz light effect support
    Button press detection (single/double/long) with inactivity timeout

### Docs

    Added README with configuration guide and setup instructions

### Chores

    Added project configuration files, development tooling, and environment setup
