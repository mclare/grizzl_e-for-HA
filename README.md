# Grizzl-E EV  Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/mclare/grizzl_e-for-HA/python-package.yml)
[![GitHub release](https://img.shields.io/github/release/mclare/grizzl_e-for-HA.svg)](https://github.com/mclare/grizzl_e-for-HA/releases)

A Home Assistant integration for Grizzl-E EVSEs (Electric Vehicle Supply Equipment, or charger), providing sensors for monitoring the WiFi Grizzl-E EVSEs.

It can connect to a charger in two ways:
- **Local**: polls the charger's built-in web interface on your network (read-only sensors).
- **Grizzl-E Connect cloud**: uses the same cloud service as the Grizzl-E Connect app. Besides sensors, it can change the charging mode, the current limit, schedules and electricity rates, and reboot the charger.

This integration works with most WiFi enabled Grizzl-E chargers (the Connect and Ultimate lines).

This integration is not affiliated with United Chargers or Grizzl-E (but is also made in Ontario, Canada). Please consult [United Charger's User Manuals](https://grizzl-e.com/user-manuals) can learn more about operating Grizzl-E EVSEs.



## ⚠️ Security Note
Did you know that your United Chargers Grizzl-E WiFi enabled EVSE has a web interface that is by default unauthenticated? If you haven't visited the Grizzl-E web interface, referred to in the user manuals as [Page Access](https://ecommerce-space.nyc3.digitaloceanspaces.com/Operation_Manual_V4_0_d5c730c075.pdf#Grizzl-EUltimate_OperationManual_V4.0.indd%3AAnchor%203%3A3092), and set a password, you should do that right away. This integration assumes a username and password has been set.

Even once a username and password is set, users should ensure that their EVSE is properly secured on their network from the rest of the internet.

## Features

This integration provides the following features:
- Real-time monitoring of charging status and metrics
- Support for multiple Grizzl-E models
- Configurable polling interval
- Temperature monitoring
- Energy usage tracking
- Cloud only: charging mode (Active / Inactive / Schedule), current limit, schedules, time-of-use rates and reboot

## Installation

### HACS (Recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed and working
2. Go to HACS → Integrations
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/mclare/grizzl_e-for-HA`
6. Select category: "Integration"
7. Click "Add"
8. Find "Grizzl-E EV" in the list and click "Install"
9. Restart Home Assistant
10. Go to Settings > Devices & Services
11. Click "+ Add Integration" and search for "Grizzl-E EV"
12. Follow the setup wizard to configure your 

### Manual Installation

1. Download the latest release from the [Releases](https://github.com/mclare/grizzl_e-for-HA/releases) page
2. Extract the `grizzle_e` folder from the archive
3. Copy the `grizzle_e` folder to your `custom_components` directory in your Home Assistant config
4. Restart Home Assistant
5. Go to Settings > Devices & Services
6. Click "+ Add Integration" and search for "Grizzl-E EV "
7. Follow the setup wizard to configure your 

## Configuration

### Configuration via UI

1. Go to Settings > Devices & Services
2. Click "+ Add Integration"
3. Search for "Grizzl-E EV"
4. Choose how to connect:
    - **Local**: enter the IP address or hostname of your EVSE, then the username and password (default is usually admin/admin)
    - **Grizzl-E Connect cloud (email and password)**: sign in with your Grizzl-E Connect app account. If the account has more than one charger, pick one; add the integration again for each other charger.

Existing local setups keep working unchanged. The polling interval can be changed under the integration's **Configure** button; cloud connections default to 30 seconds and can't go below 10.

### Grizzl-E Connect cloud

The cloud API isn't documented by United Chargers. It was reverse engineered from the Grizzl-E Connect app (see `grizzle_connect.py`) and may change without notice.

Entities:
- **Sensors**: Station Status, Station Error Code, Next Schedule Change, and for each connector: Status, Error Code, Power, Current, Voltage, Temperature, Session Energy, Session Time, Session Cost and Session Start. Current, voltage, temperature and session values are only reported while a charging session exists.
- **Binary sensors**: Online, and for each connector: Vehicle Connected, Charging, Schedule Active
- **Select**: Charge Mode for each connector. *Active* charges whenever a vehicle is plugged in, *Inactive* pauses charging, *Schedule* charges only inside enabled schedules.
- **Number**: Current Limit, capped at the charger's DIP switch setting
- **Switches**: one per schedule and rate zone, to turn it on or off. The `schedule_id` attribute is the ID used by the services below.
- **Button**: Reboot

On a Grizzl-E Duo, per-connector entities get a "Port 1" / "Port 2" suffix.

Services (all take the charger's `device_id`; times are in the charger's timezone):
- `grizzl_e.set_schedule`: create a charging schedule, or update one by `schedule_id` (fields you leave out keep their current values)
- `grizzl_e.delete_schedule`
- `grizzl_e.set_rate_zone`: create a time-of-use rate zone, or update one by `zone_id`
- `grizzl_e.delete_rate_zone`
- `grizzl_e.set_base_rate`: the price per kWh used outside rate zones

```yaml
action: grizzl_e.set_schedule
data:
  device_id: 0123456789abcdef0123456789abcdef
  name: Off-peak
  start: "23:00"
  end: "07:00"
  days: [monday, tuesday, wednesday, thursday, friday]
```

If the cloud stops accepting the saved credentials, Home Assistant asks you to sign in again.

## Available Sensors (local)

- **Current**: Current charging current (A)
- **Voltage**: Line voltage (V)
- **Power**: Current power draw (W)
- **Session Energy**: Energy used in current session (kWh)
- **Total Energy**: Total energy used (kWh)
- **Temperature 1/2**: Temperature sensors (°C)
- **State**:  state (Ready/Connected/Charging)
- **Pilot State**: EV connection status
- **RSSI**: WiFi signal strength (dBm)

## Troubleshooting: Verify EVSE Connectivity Outside of Home Assistant

If the integration fails, and the integration is running in Home Assistant, but cannot connect to the Grizzl-E EVSE, first verify that you can access your Grizzl-E EVSE over the network **without** Home Assistant involved.

This check helps confirm that your network, credentials, and the EVSE are working correctly before adding any Home Assistant complexity.

---

### What you need

You will need:
- The **IP address** of your Grizzl-E EVSE
- The **username**
- The **password**
- Home Assistant and the EVSE on the **same network** or the firewall rules to allow access

---

### Testing Connectivity

#### Step 1: Verify Web Interface Access

Verify that you can access the Grizzl-E EVSE's web interface with your regular web browser. The bottom of the page will show the EVSE Version, WiFi Version and Serial Number.


#### Step 2, option 1: Command line (macOS and Linux)

If you are comfortable using a terminal, you can test connectivity using `curl`, replacing `<username>`, `<password>`, and `<EVSE_IP>` with your actual values.

```bash
curl -sS -X POST -H 'Authorization: Basic '"$(printf %s '<username>:<password>' | base64)" http://<EVSE_IP>/main
```
There is also a way to do this with Windows PowerShell, but if you know how to initiate a network request like this in PowerShell, you know how to adapt a curl command.

#### Step 2, option 2: Using a graphical tool

If you are not comfortable using the command line, you can use a graphical HTTP client such as:

- **[Postman](https://www.postman.com/)** (Windows, macOS, Linux)
- **[Insomnia](https://insomnia.rest/)**

##### Request details

- **Method:** `POST`
- **URL:** `http://<EVSE_IP>/main`
- **Body:** (empty)
- **Authentication:**
- Type: **Basic Authentication**
- Username: your EVSE username
- Password: your EVSE password

- **Headers:**
- No custom headers are required when using Basic Auth (the tool will add them automatically)

#### Expected result

If the request is successful, the EVSE will return a **JSON response** containing status information.

If you see JSON data, your IP address, username, and password are correct.


## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests. Between me and AI code assistance, there's very little intelligence currently working on this.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
