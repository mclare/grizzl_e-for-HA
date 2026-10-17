import logging
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfElectricPotential,
    UnitOfTime,
    CURRENCY_DOLLAR,
)
from homeassistant.helpers.entity import EntityCategory, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .cloud import GrizzleECloudEntity, first_number, is_cloud_entry, number, parse_datetime
from .const import DOMAIN, CONF_PORTS, port_key

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    # Get the device from hass.data
    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
        return

    if is_cloud_entry(entry):
        async_add_entities(_cloud_sensors(hass.data[DOMAIN][entry.entry_id]["coordinator"]))
        return
            
    device = hass.data[DOMAIN][entry.entry_id]["device"]
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    # Get number of ports from config
    num_ports = entry.data.get(CONF_PORTS, 1)
    _LOGGER.debug("Setting up Grizzl-E with %d ports", num_ports)

    # Set device info on coordinator for sensors to access
    coordinator.device = device
    
    # Ensure we have fresh data
    await coordinator.async_config_entry_first_refresh()
    
    # Device-wide sensors (not tied to a specific charging cable).
    sensors = [
        GrizzleESensor(coordinator, "Temperature 1", "temperature1", UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE),
        GrizzleESensor(coordinator, "Temperature 2", "temperature2", UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE),
        GrizzleESensor(coordinator, "RSSI", "RSSI", "dBm", device_class=SensorDeviceClass.SIGNAL_STRENGTH, entity_category=EntityCategory.DIAGNOSTIC),
        # Diagnostic and version information
        GrizzleESensor(coordinator, "EVSE Version", "verFWMain", None, entity_category=EntityCategory.DIAGNOSTIC, state_class=None),
        GrizzleESensor(coordinator, "WiFi Version", "verFWWifi", None, entity_category=EntityCategory.DIAGNOSTIC, state_class=None),
    ]

    # Per-cable/port sensors. On multi-cable units (e.g. the Grizzl-E Duo) the
    # second cable reports through a different set of JSON keys, resolved by
    # port_key(); see const.py and issue #23.
    state_options = ["PowerUp", "SelfTest", "Standby", "Vehicle Connected", "Vehicle Charging", "Charging Complete", "Disabled", "Error"]

    for port in range(1, num_ports + 1):
        port_suffix = f" Port {port}" if num_ports > 1 else ""

        def add(field, name, unit, **kwargs):
            key = port_key(field, port)
            # Preserve the original (single-port) unique_ids for port 1 so
            # existing entities/history are kept; disambiguate port 2+ since
            # some fields (e.g. voltage) are shared across cables.
            unique_key = key if port <= 1 else f"{key}_p{port}"
            sensors.append(
                GrizzleESensor(coordinator, f"{name}{port_suffix}", key, unit, unique_key=unique_key, **kwargs)
            )

        add("power", "Power", UnitOfPower.WATT, device_class=SensorDeviceClass.POWER)
        add("current", "Current", UnitOfElectricCurrent.AMPERE, device_class=SensorDeviceClass.CURRENT)
        add("voltage", "Voltage", UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE)
        add("session_energy", "Session Energy", UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING)
        add("total_energy", "Total Energy", UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING)
        add("session_time", "Session Time", UnitOfTime.SECONDS, device_class=SensorDeviceClass.DURATION)
        add("state", "State", None, device_class=SensorDeviceClass.ENUM, state_class=None, options=state_options)
        add("pilot", "Pilot State", None, device_class=SensorDeviceClass.ENUM, state_class=None, options=["no_ev", "ev_connected"])

    async_add_entities(sensors)


class GrizzleESensor(CoordinatorEntity, SensorEntity):
    """Representation of a Grizzl-E sensor."""
    
    _attr_has_entity_name = True
    
    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return self.coordinator.device.device_info

    def __init__(
        self,
        coordinator,
        name,
        key,
        unit=None,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=None,
        options=None,
        unique_key=None,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = name
        self._key = key
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_entity_category = entity_category
        if options:
            self._attr_options = options

        # Set device info
        self._attr_has_entity_name = True  # Use device name as prefix
        # ``unique_key`` lets several sensors share the same JSON key (e.g.
        # both cables read voltage from ``voltMeas1``) while keeping distinct
        # unique_ids. Falls back to the JSON key for backward compatibility.
        self._attr_unique_id = f"{self.coordinator.config_entry.entry_id}_{unique_key or key}"
            

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
            
        value = self.coordinator.data.get(self._key)
        
        # Handle None values
        if value is None:
            return None
            
        # Handle enum types
        if self.device_class == SensorDeviceClass.ENUM:
            try:
                return self.options[value]
            except (IndexError, KeyError, TypeError):
                _LOGGER.debug("Invalid enum value %s for %s", value, self._key)
                return None
                
        # Convert numeric strings to numbers
        if isinstance(value, str) and value.replace('.', '', 1).isdigit():
            if '.' in value:
                return float(value)
            return int(value)
            
        return value


# --- Grizzl-E Connect cloud ----------------------------------------------------


def _cloud_sensors(coordinator):
    """Sensors for a cloud entry: station-wide ones, then one set per connector."""
    sensors = [
        GrizzleECloudSensor(
            coordinator, "status", "Station Status", lambda e: e.station.get("status"), state_class=None
        ),
        GrizzleECloudSensor(
            coordinator, "error_code", "Station Error Code", lambda e: e.station.get("errorCode"),
            state_class=None, entity_category=EntityCategory.DIAGNOSTIC,
        ),
        GrizzleECloudSensor(
            coordinator, "next_schedule_change", "Next Schedule Change",
            lambda e: parse_datetime(e.station.get("nextScheduleTime")),
            device_class=SensorDeviceClass.TIMESTAMP, state_class=None,
        ),
    ]
    for index in range(len(coordinator.data.get("connectors") or [])):
        sensors += [
            GrizzleECloudSensor(
                coordinator, "connector_status", "Status", lambda e: e.connector.get("status"),
                connector_index=index, state_class=None,
            ),
            GrizzleECloudSensor(
                coordinator, "connector_error_code", "Error Code", lambda e: e.connector.get("errorCode"),
                connector_index=index, state_class=None, entity_category=EntityCategory.DIAGNOSTIC,
            ),
            GrizzleECloudSensor(
                coordinator, "power", "Power", lambda e: number(e.connector.get("power")),
                connector_index=index, unit=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER,
            ),
            GrizzleECloudSensor(
                coordinator, "current", "Current",
                lambda e: first_number((e.charge.get("meterValues") or {}).get("currentImport")),
                connector_index=index, unit=UnitOfElectricCurrent.AMPERE,
                device_class=SensorDeviceClass.CURRENT,
            ),
            GrizzleECloudSensor(
                coordinator, "voltage", "Voltage",
                lambda e: first_number((e.charge.get("meterValues") or {}).get("voltage")),
                connector_index=index, unit=UnitOfElectricPotential.VOLT,
                device_class=SensorDeviceClass.VOLTAGE,
            ),
            GrizzleECloudTemperatureSensor(coordinator, index),
            GrizzleECloudSensor(
                coordinator, "session_energy", "Session Energy", _session_energy_kwh,
                connector_index=index, unit=UnitOfEnergy.KILO_WATT_HOUR,
                device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING,
            ),
            GrizzleECloudSensor(
                coordinator, "session_time", "Session Time", lambda e: number(e.charge.get("duration")),
                connector_index=index, unit=UnitOfTime.SECONDS, device_class=SensorDeviceClass.DURATION,
            ),
            GrizzleECloudSessionCostSensor(coordinator, index),
            GrizzleECloudSensor(
                coordinator, "session_start", "Session Start",
                lambda e: parse_datetime(e.charge.get("startAt")),
                connector_index=index, device_class=SensorDeviceClass.TIMESTAMP, state_class=None,
            ),
        ]
    return sensors


def _session_energy_kwh(entity):
    # Session energy is reported in Wh, the OCPP unit (meterStart uses it too).
    energy = number(entity.charge.get("energy"))
    return round(energy / 1000, 3) if energy is not None else None


class GrizzleECloudSensor(GrizzleECloudEntity, SensorEntity):
    """A sensor read from the Grizzl-E Connect station payload."""

    def __init__(
        self,
        coordinator,
        key,
        name,
        value_fn,
        connector_index=None,
        unit=None,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=None,
    ):
        super().__init__(coordinator, key, name, connector_index)
        self._value_fn = value_fn
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_entity_category = entity_category

    @property
    def native_value(self):
        if self.connector_index is not None and self.connector is None:
            return None
        return self._value_fn(self)


class GrizzleECloudTemperatureSensor(GrizzleECloudSensor):
    """Connector temperature, reported only while a session is in progress."""

    def __init__(self, coordinator, connector_index):
        super().__init__(
            coordinator, "temperature", "Temperature",
            lambda e: first_number((e.charge.get("meterValues") or {}).get("temperature")),
            connector_index=connector_index, unit=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
        )

    @property
    def native_unit_of_measurement(self):
        if self.charge.get("temperatureUnit") == "Fahrenheit":
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS


class GrizzleECloudSessionCostSensor(GrizzleECloudSensor):
    """Cost of the session in progress, priced with the station's energy plan.

    The total restarts with every session, so ``last_reset`` is the session start.
    """

    def __init__(self, coordinator, connector_index):
        super().__init__(
            coordinator, "session_cost", "Session Cost", lambda e: number(e.charge.get("priceTotal")),
            connector_index=connector_index, device_class=SensorDeviceClass.MONETARY,
            state_class=SensorStateClass.TOTAL,
        )

    @property
    def native_unit_of_measurement(self):
        return self.charge.get("currency") or self.station.get("currency") or self.hass.config.currency

    @property
    def last_reset(self):
        return parse_datetime(self.charge.get("startAt"))
