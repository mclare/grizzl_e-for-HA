# Changelog

## [Unreleased] - January 2026
Thanks to everyone for their enthusiasm and guidance!

### Community Contributions
 - Call out in r/evcharging/ got me going again. Thanks folks https://www.reddit.com/r/evcharging/comments/1o524on/comment/nywjtup/
 - HACS file structure refinements and home assistant version backwards compatibility information provided by https://github.com/lukavia
 - Change to Total Energy sensor to have it work with HA Energy dashboard, from issue https://github.com/mclare/grizzl_e-for-HA/issues/2 submitted by https://github.com/drasch

### Added
- Basic pytest tests

 ### Changed
- Reuse HA’s shared aiohttp session and per-request timeout in init.py
    - Use async_get_clientsession(hass) and an aiohttp.ClientTimeout on the request via session.post(..., timeout=timeout).
    - Remove the unused outer ClientSession and storage in hass.data.
    - No longer creating a new session in each update
- Applied options to coordinator and register options flow correctly in config_flow.py
    - Made async_get_options_flow a static method.
-  Fix platform setup early returns in sensor.py and binary_sensor.py
    - Replace return False with just return.

### Minor cleanups
- Remove the stray docstring line in GrizzleESensor.
- Standardize DeviceInfo import to from homeassistant.helpers.entity import DeviceInfo across files for consistency.


## [Unreleased] - August 2025
### Added
- Initial release of the Grizzl-E Home Assistant integration
- Support for monitoring charging status and metrics
- Configuration via UI
- Multiple sensor types including power, energy, temperature, and more
- Support for multiple charging ports

### Changed
- Improved error handling and logging
- Optimized data fetching with proper timeouts
- Better device registry integration

### Fixed
- Fixed sensor updates when device is unreachable
- Improved handling of missing or invalid data
- Fixed device registry cleanup on unload

## [0.1.0] - 2025-08-22
- Initial release
