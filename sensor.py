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

from .const import DOMAIN, CONF_PORTS

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    # Get the device from hass.data
    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
        return False
            
    device = hass.data[DOMAIN][entry.entry_id]["device"]
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    # Get number of ports from config
    num_ports = entry.data.get(CONF_PORTS, 1)
    _LOGGER.debug("Setting up Grizzl-E with %d ports", num_ports)

    # Set device info on coordinator for sensors to access
    coordinator.device = device
    
    # Ensure we have fresh data
    await coordinator.async_config_entry_first_refresh()
    
    # Base sensors (not port-specific)
    sensors = [
        GrizzleESensor(coordinator, "Power", "powerMeas", UnitOfPower.WATT, device_class=SensorDeviceClass.POWER),
        GrizzleESensor(coordinator, "Session Energy", "sessionEnergy", UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY),
        GrizzleESensor(coordinator, "Total Energy", "totalEnergy", UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY),
        GrizzleESensor(coordinator, "Temperature 1", "temperature1", UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE),
        GrizzleESensor(coordinator, "Temperature 2", "temperature2", UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE),
        GrizzleESensor(coordinator, "RSSI", "RSSI", "dBm", device_class=SensorDeviceClass.SIGNAL_STRENGTH, entity_category=EntityCategory.DIAGNOSTIC),
        GrizzleESensor(coordinator, "State", "state", None, device_class=SensorDeviceClass.ENUM, options=["unknown", "ready", "ready", "connected", "charging"]),
        GrizzleESensor(coordinator, "Pilot State", "pilot", None, device_class=SensorDeviceClass.ENUM, options=["no_ev", "ev_connected"]),
        GrizzleESensor(coordinator, "Session Time", "sessionTime", UnitOfTime.SECONDS, device_class=SensorDeviceClass.DURATION),
        GrizzleESensor(coordinator, "Session Money", "sessionMoney", CURRENCY_DOLLAR, device_class=SensorDeviceClass.MONETARY),
    ]

    # Add port-specific sensors
    for port in range(1, num_ports + 1):
        port_suffix = f" Port {port}" if num_ports > 1 else ""
        
        # Always add current and voltage sensors, they'll handle None values
        current_key = f"curMeas{port}"
        sensors.append(
            GrizzleESensor(
                coordinator,
                f"Current{port_suffix}",
                current_key,
                UnitOfElectricCurrent.AMPERE,
                device_class=SensorDeviceClass.CURRENT
            )
        )
        
        voltage_key = f"voltMeas{port}"
        sensors.append(
            GrizzleESensor(
                    coordinator,
                    f"Voltage{port_suffix}",
                    voltage_key,
                    UnitOfElectricPotential.VOLT,
                    device_class=SensorDeviceClass.VOLTAGE
                )
            )

    async_add_entities(sensors)


class GrizzleESensor(CoordinatorEntity, SensorEntity):
    """Representation of a Grizzl-E sensor."""
    
    _attr_has_entity_name = True
    
    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return self.coordinator.device.device_info
    """Numeric sensor for Grizzl-E charger."""

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
        self._attr_unique_id = f"{self.coordinator.config_entry.entry_id}_{key}"
            

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
