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

from .const import DOMAIN, CONF_PORTS, port_key

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    # Get the device from hass.data
    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
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
    state_options = ["PowerUp", "SelfTest", "Standby", "Vehicle Connected", "Vehile Charging", "Charing Complete", "Disabled", "Error"]

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
        add("session_energy", "Session Energy", UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY)
        add("total_energy", "Total Energy", UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING)
        add("session_time", "Session Time", UnitOfTime.SECONDS, device_class=SensorDeviceClass.DURATION)
        add("session_money", "Session Money", CURRENCY_DOLLAR, device_class=SensorDeviceClass.MONETARY)
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
