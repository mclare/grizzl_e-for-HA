"""Reboot button for Grizzl-E Connect cloud entries."""
from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.helpers.entity import EntityCategory

from .cloud import GrizzleECloudEntity, is_cloud_entry
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    if not is_cloud_entry(entry) or entry.entry_id not in hass.data.get(DOMAIN, {}):
        return
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([GrizzleERebootButton(coordinator)])


class GrizzleERebootButton(GrizzleECloudEntity, ButtonEntity):
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator):
        super().__init__(coordinator, "reboot", "Reboot")

    async def async_press(self):
        await self.coordinator.async_command(self.coordinator.client.reboot(self.coordinator.station_id))
