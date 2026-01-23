"""Device class for Grizzl-E EV Charger."""
from homeassistant.helpers.entity import DeviceInfo
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
        """Return device information.

        Prefer dynamic data from the EVSE payload when available so the
        device registry shows accurate model and firmware.
        """
        data = getattr(self.coordinator, "data", None) or {}
        # Prefer payload model when present, fallback to static default
        model = data.get("model") or MODEL
        # Use EVSE main firmware as device software version; trim whitespace
        sw_version = (data.get("verFWMain") or "").strip() or None
        # Use serial if available for nicer identification in registry
        serial = data.get("serialNum") or data.get("stationId") or None

        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=self.entry.title,
            manufacturer=MANUFACTURER,
            model=model,
            sw_version=sw_version,
            serial_number=serial,
            configuration_url=f"http://{self.entry.data['host']}",
        )
