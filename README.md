# Grizzl-E EV Charger Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/mclare/grizzle_e-for-HA.svg)](https://github.com/mclare/grizzle_e-for-HA/releases)

A Home Assistant integration for Grizzl-E EV chargers, providing sensors for monitoring the WiFi Grizzl-E charger.

This integration is not affiliated with United Chargers or Grizzl-E (but is also made in Ontario, Canada).

## ⚠️ Security Note

Did you know your United Chargers Grizzl-E EV WiFi enabled charger has an unauthenticated web interface? If you haven't visited the Grizzl-E web interface and set a password, you should do that right away. This integration assumes a username and password has been set.

## Features

This integration provides the following features:
- Real-time monitoring of charging status and metrics
- Support for multiple Grizzl-E charger models
- Configurable polling interval
- Temperature monitoring
- Energy usage tracking

## Installation

### HACS (Recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed and working
2. Go to HACS → Integrations
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/mclare/grizzle_e-for-HA`
6. Select category: "Integration"
7. Click "Add"
8. Find "Grizzl-E EV Charger" in the list and click "Install"
9. Restart Home Assistant
10. Go to Settings > Devices & Services
11. Click "+ Add Integration" and search for "Grizzl-E EV Charger"
12. Follow the setup wizard to configure your charger

### Manual Installation

1. Download the latest release from the [Releases](https://github.com/mclare/grizzle_e-for-HA/releases) page
2. Extract the `grizzle_e` folder from the archive
3. Copy the `grizzle_e` folder to your `custom_components` directory in your Home Assistant config
4. Restart Home Assistant
5. Go to Settings > Devices & Services
6. Click "+ Add Integration" and search for "Grizzl-E EV Charger"
7. Follow the setup wizard to configure your charger

## Configuration

### Configuration via UI

1. Go to Settings > Devices & Services
2. Click "+ Add Integration"
3. Search for "Grizzl-E EV Charger"
4. Enter your charger's IP address or hostname
5. Enter the username and password (default is usually admin/admin)

### Configuration via YAML

```yaml
# Example configuration.yaml entry
grizzle_e:
  host: 192.168.1.100
  username: admin
  password: yourpassword
  scan_interval: 30  # Optional, in seconds
```

## Available Sensors

- **Current**: Current charging current (A)
- **Voltage**: Line voltage (V)
- **Power**: Current power draw (W)
- **Session Energy**: Energy used in current session (kWh)
- **Total Energy**: Total energy used (kWh)
- **Temperature 1/2**: Temperature sensors (°C)
- **State**: Charger state (Ready/Connected/Charging)
- **Pilot State**: EV connection status
- **RSSI**: WiFi signal strength (dBm)

## Automation Examples

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests. Between me and AI code assistance, there's very little intelligence currently working on this.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
