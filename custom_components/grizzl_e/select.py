"""Charging mode select for Grizzl-E Connect cloud entries."""
from homeassistant.components.select import SelectEntity

from .cloud import GrizzleECloudEntity, is_cloud_entry
from .const import CLOUD_CHARGE_MODES, DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    if not is_cloud_entry(entry) or entry.entry_id not in hass.data.get(DOMAIN, {}):
        return
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    num_connectors = len(coordinator.data.get("connectors") or [])
    if num_connectors == 0:
        # No connector list: control the station as a single-cable charger.
        async_add_entities([GrizzleEChargeModeSelect(coordinator, None)])
        return
    async_add_entities(GrizzleEChargeModeSelect(coordinator, index) for index in range(num_connectors))


class GrizzleEChargeModeSelect(GrizzleECloudEntity, SelectEntity):
    """Active charges whenever a vehicle is plugged in, Inactive pauses charging,
    Schedule charges only inside enabled schedule windows."""

    _attr_options = CLOUD_CHARGE_MODES
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator, connector_index):
        super().__init__(coordinator, "charge_mode", "Charge Mode", connector_index)

    @property
    def current_option(self):
        mode = (self.connector or {}).get("mode")
        if mode is None and self.mode_connector_id == 0:
            mode = self.station.get("mode")
        return mode if mode in CLOUD_CHARGE_MODES else None

    async def async_select_option(self, option):
        await self.coordinator.async_command(
            self.coordinator.client.set_mode(self.coordinator.station_id, option, self.mode_connector_id)
        )
