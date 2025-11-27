"""Device class for Grizzl-E EV Charger."""
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, MANUFACTURER, MODEL

class GrizzleEDevice:
    """Grizzl-E device."""

    def __init__(self, coordinator: DataUpdateCoordinator, entry):
        """Initialize the device."""
        self.coordinator = coordinator
        self.entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=self.entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL,
            configuration_url=f"http://{self.entry.data['host']}",
        )
