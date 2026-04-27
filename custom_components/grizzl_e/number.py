"""Number inputs for Grizzl-E EV Charger."""
import logging
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities for Grizzl-E from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    device = data["device"]
    coordinator = data["coordinator"]

    numbers = [
        GrizzleECurrentNumber(coordinator, device),
    ]

    async_add_entities(numbers)


class GrizzleENumber(CoordinatorEntity, NumberEntity):
    """Base number entity for Grizzl-E."""

    _attr_should_poll = False

    def __init__(self, coordinator, device):
        """Initialize the number."""
        super().__init__(coordinator)
        self.device = device
        self._attr_device_info = device.device_info


class GrizzleECurrentNumber(GrizzleENumber):
    """Number input for charging current."""

    _attr_unique_id = "grizzle_e_current"
    _attr_name = "Current"
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_mode = NumberMode.BOX
    _attr_native_step = 1.0
    _attr_icon = "mdi:flash"

    @property
    def native_value(self) -> float | None:
        """Return the current charging current from device data."""
        data = getattr(self.coordinator, "data", None) or {}
        try:
            current_set = float(data.get("currentSet", 7))
            return current_set
        except (ValueError, TypeError):
            return 7.0

    @property
    def native_min_value(self) -> float:
        """Return the minimum value.

        Read minCurrent from the latest coordinator data.
        Fallback to 1A if not available.
        """
        data = getattr(self.coordinator, "data", None) or {}
        try:
            min_current = float(data.get("minCurrent", 1))
            return min_current
        except (ValueError, TypeError):
            return 7.0

    @property
    def native_max_value(self) -> float:
        """Return the maximum value.

        Read curDesign from the latest coordinator data.
        Fallback to 16A if not available.
        """
        data = getattr(self.coordinator, "data", None) or {}
        try:
            cur_design = float(data.get("curDesign", 16))
            min_val = self.native_min_value
            return max(cur_design, min_val)  # Ensure max is at least as high as min
        except (ValueError, TypeError):
            return 16.0

    async def async_set_native_value(self, value: float) -> None:
        """Set the charging current."""
        # Validate value is within bounds
        if value < self.native_min_value or value > self.native_max_value:
            raise ValueError(
                f"Current must be between {self.native_min_value} "
                f"and {self.native_max_value} amps"
            )

        try:
            # Disable cloud control first
            await self.device.async_send_command("ocppEvent", {"ocppEnabled": 0})
            # Then set current
            await self.device.async_send_command("pageEvent", {
                "currentSet": int(value),
                "suspendLimits": 0,
            })
            await self.coordinator.async_request_refresh()
        except HomeAssistantError as err:
            _LOGGER.error(f"Failed to set charging current: {err}")
            raise
