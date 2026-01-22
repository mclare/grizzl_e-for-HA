# Grizzl-E EV Charger Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/mclare/grizzl_e-for-HA/python-package.yml)
[![GitHub release](https://img.shields.io/github/release/mclare/grizzl_e-for-HA.svg)](https://github.com/mclare/grizzl_e-for-HA/releases)

A Home Assistant integration for Grizzl-E EVSEs (Electric Vehicle Supply Equipment, or chargers), providing sensors for monitoring the WiFi Grizzl-E EVSEs.

This integration is not affiliated with United Chargers or Grizzl-E (but is also made in Ontario, Canada).

## ⚠️ Security Note
Did you know your United Chargers Grizzl-E EV WiFi enabled EVSE has an unauthenticated web interface? If you haven't visited the Grizzl-E web interface and set a password, you should do that right away. This integration assumes a username and password has been set.

Likewise, you should ensure that your EVSE is properly secured on your network from the rest of the internet.

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
  host: YOUR_EVSE_IP_ADDRESS
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

## Troubleshooting: Verify EVSE Connectivity Outside of Home Assistant

If the integration fails to is running in Home Assistant, but cannot connect to your Grizzl-E EVSE, first verify that you can access your Grizzl-E EVSE over the network **without** Home Assistant involved.

This check helps confirm that your network, credentials, and EVSE are working correctly before adding any Home Assistant complexity.

---

### What you need

You will need:
- The **IP address** of your Grizzl-E EVSE
- The **username**
- The **password**
- Your computer and EVSE on the **same network** or the firewall rules to allow access

---

## Testing Connectivity

### Step 1: Verify Web Interface Access

Verify that you can access the Grizzl-E EVSE's web interface with your regular web browser. The bottom of the page will show the EVSE Version, WiFi Version and Serial Number.


### Step 2, option 1: Command line (macOS and Linux)

If you are comfortable using a terminal, you can test connectivity using `curl`, replacing `<username>`, `<password>`, and `<EVSE_IP>` with your actual values.

```bash
curl -sS -X POST -H 'Authorization: Basic '"$(printf %s '<username>:<password>' | base64)" http://<EVSE_IP>/main
```
There is also a way to do this with Windows PowerShell, but if you know how to initiate a network request like this in PowerShell, you know how to adapt a curl command.

### Step 2, option 2: Using a graphical tool

If you are not comfortable using the command line, you can use a graphical HTTP client such as:

- **[Postman](https://www.postman.com/)** (Windows, macOS, Linux)
- **[Insomnia](https://insomnia.rest/)**

#### Request details

- **Method:** `POST`
- **URL:** `http://<EVSE_IP>/main`
- **Body:** (empty)
- **Authentication:**
- Type: **Basic Authentication**
- Username: your EVSE username
- Password: your EVSE password

- **Headers:**
- No custom headers are required when using Basic Auth (the tool will add them automatically)

### Expected result

If the request is successful, the EVSE will return a **JSON response** containing status information.

If you see JSON data, your IP address, username, and password are correct.


## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests. Between me and AI code assistance, there's very little intelligence currently working on this.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.