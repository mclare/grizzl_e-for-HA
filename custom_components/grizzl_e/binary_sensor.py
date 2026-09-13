import logging
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DEFAULT_NAME, CONF_PORTS, port_key

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    # Get the device and coordinator from hass.data
    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
        return
        
    device = hass.data[DOMAIN][entry.entry_id]["device"]
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    # Set device info on coordinator for binary sensors to access
    coordinator.device = device

    num_ports = entry.data.get(CONF_PORTS, 1)

    binaries = []
    for port in range(1, num_ports + 1):
        port_suffix = f" Port {port}" if num_ports > 1 else ""
        for name, field in (("Session Started", "session_started"), ("Pilot Connected", "pilot")):
            key = port_key(field, port)
            unique_key = key if port <= 1 else f"{key}_p{port}"
            binaries.append(
                GrizzleEBinarySensor(coordinator, f"{name}{port_suffix}", key, unique_key=unique_key)
            )

    async_add_entities(binaries)


class GrizzleEBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for Grizzl-E charger."""
    
    _attr_has_entity_name = True
    
    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return self.coordinator.device.device_info

    def __init__(self, coordinator, name, key, unique_key=None):
        super().__init__(coordinator)
        self._attr_name = name
        self._key = key
        self._attr_unique_id = f"{self.coordinator.config_entry.entry_id}_{unique_key or key}"

    @property
    def is_on(self):
        val = self.coordinator.data.get(self._key)
        if isinstance(val, (int, float)):
            return val != 0
        return bool(val)
