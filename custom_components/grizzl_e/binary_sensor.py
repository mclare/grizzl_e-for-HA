import logging
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .cloud import PLUGGED_IN_STATUSES, GrizzleECloudEntity, is_cloud_entry
from .const import DOMAIN, DEFAULT_NAME, CONF_PORTS, port_key

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    # Get the device and coordinator from hass.data
    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
        return

    if is_cloud_entry(entry):
        async_add_entities(_cloud_binary_sensors(hass.data[DOMAIN][entry.entry_id]["coordinator"]))
        return
        
    device = hass.data[DOMAIN][entry.entry_id]["device"]
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    # Set device info on coordinator for binary sensors to access
    coordinator.device = device

    # Ensure we have fresh data
    if coordinator.data is None:
        await coordinator.async_config_entry_first_refresh()

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
        if not self.coordinator.data:
            return None
        val = self.coordinator.data.get(self._key)
        if isinstance(val, (int, float)):
            return val != 0
        return bool(val)


# --- Grizzl-E Connect cloud ----------------------------------------------------


def _connector_status(entity):
    return entity.connector.get("status")


def _cloud_binary_sensors(coordinator):
    sensors = [
        GrizzleECloudBinarySensor(
            coordinator, "online", "Online", lambda e: e.station.get("online"),
            device_class=BinarySensorDeviceClass.CONNECTIVITY, entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ]
    for index in range(len(coordinator.data.get("connectors") or [])):
        sensors += [
            GrizzleECloudBinarySensor(
                coordinator, "vehicle_connected", "Vehicle Connected",
                lambda e: None if _connector_status(e) is None else _connector_status(e) in PLUGGED_IN_STATUSES,
                connector_index=index, device_class=BinarySensorDeviceClass.PLUG,
            ),
            GrizzleECloudBinarySensor(
                coordinator, "charging", "Charging",
                lambda e: None if _connector_status(e) is None else _connector_status(e) == "Charging",
                connector_index=index, device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
            ),
            GrizzleECloudBinarySensor(
                coordinator, "active_by_schedule", "Schedule Active",
                lambda e: e.connector.get("isActiveBySchedule"),
                connector_index=index,
            ),
        ]
    return sensors


class GrizzleECloudBinarySensor(GrizzleECloudEntity, BinarySensorEntity):
    """A binary sensor read from the Grizzl-E Connect station payload."""

    def __init__(self, coordinator, key, name, value_fn, connector_index=None, device_class=None, entity_category=None):
        super().__init__(coordinator, key, name, connector_index)
        self._value_fn = value_fn
        self._attr_device_class = device_class
        self._attr_entity_category = entity_category

    @property
    def is_on(self):
        if self.connector_index is not None and self.connector is None:
            return None
        value = self._value_fn(self)
        return None if value is None else bool(value)
