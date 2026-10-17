"""Current limit number for Grizzl-E Connect cloud entries."""
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.helpers.entity import EntityCategory

from .cloud import GrizzleECloudEntity, is_cloud_entry, number
from .const import DOMAIN

# Used when the station payload doesn't say what the hardware supports.
DEFAULT_MIN_CURRENT = 6
DEFAULT_MAX_CURRENT = 48


async def async_setup_entry(hass, entry, async_add_entities):
    if not is_cloud_entry(entry) or entry.entry_id not in hass.data.get(DOMAIN, {}):
        return
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([GrizzleECurrentLimitNumber(coordinator)])


class GrizzleECurrentLimitNumber(GrizzleECloudEntity, NumberEntity):
    """Maximum charging current. Capped by the charger's DIP switch setting."""

    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator):
        super().__init__(coordinator, "current_limit", "Current Limit")

    @property
    def _model(self):
        model = self.station.get("model")
        return model if isinstance(model, dict) else {}

    @property
    def native_value(self):
        smart = self.station.get("smartCharging")
        value = number(smart.get("currentLimit")) if isinstance(smart, dict) else None
        if value is None:
            value = number(self.station.get("dipSwitchCurrentLimit"))
        return value

    @property
    def native_min_value(self):
        return number(self._model.get("minCurrent")) or DEFAULT_MIN_CURRENT

    @property
    def native_max_value(self):
        limits = [
            value
            for value in (number(self._model.get("maxCurrent")), number(self.station.get("dipSwitchCurrentLimit")))
            if value
        ]
        maximum = min(limits) if limits else DEFAULT_MAX_CURRENT
        return max(maximum, self.native_min_value)

    async def async_set_native_value(self, value):
        await self.coordinator.async_command(
            self.coordinator.client.set_current_limit(self.coordinator.station_id, int(value))
        )
