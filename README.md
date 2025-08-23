# Grizzl-E EV Charger Home Assistant Integration
A Home Assistant integration for Grizzl-E EV chargers, providing sensors for monitoring the WiFi Grizzl-E charger.

This integration is not affiliated with United Chargers or Grizzl-E (but is also made in Ontario, Canada).

# Security Note
Did you know your United Chargers Grizzl-E EV WiFi enabled charger has an unauthericated web interface? If you haven't visited the Grizzl-E web interface and set a password, you should do that right away. This integration assumes a username and password has been set.

# Features
This integration provides the following features:
- Real-time monitoring of charging status and metrics
- Support for multiple Grizzl-E charger models
- Configurable polling interval
- Temperature monitoring
- Energy usage tracking

## Installation

### HACS (Recommended)
Not yet

### Manual Installation

1. Copy the `grizzle_e` folder to your `custom_components` directory in your Home Assistant config
2. Restart Home Assistant
3. Go to Settings > Devices & Services
4. Click "+ Add Integration" and search for "Grizzl-E EV Charger"
5. Follow the setup wizard to configure your charger

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

Contributions are welcome! Please feel free to submit issues and pull requests. Between me and AI code assistance, there's very little inteleligence currently working on this.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
