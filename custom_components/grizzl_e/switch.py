"""Switches for Grizzl-E EV Charger."""
import logging
from homeassistant.components.switch import SwitchEntity
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
    """Set up switch entities for Grizzl-E from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    device = data["device"]
    coordinator = data["coordinator"]

    switches = [
        GrizzleECloudControlledSwitch(coordinator, device),
        GrizzleEChargeSwitch(coordinator, device),
    ]

    async_add_entities(switches)


class GrizzleESwitch(CoordinatorEntity, SwitchEntity):
    """Base switch entity for Grizzl-E."""

    _attr_should_poll = False

    def __init__(self, coordinator, device):
        """Initialize the switch."""
        super().__init__(coordinator)
        self.device = device
        self._attr_device_info = device.device_info


class GrizzleECloudControlledSwitch(GrizzleESwitch):
    """Switch to control OCPP cloud features."""

    _attr_unique_id = "grizzle_e_cloud_controlled"
    _attr_name = "Cloud Controlled"
    _attr_icon = "mdi:cloud-check"

    @property
    def is_on(self) -> bool:
        """Return True if cloud control is enabled."""
        data = getattr(self.coordinator, "data", None) or {}
        try:
            return bool(data.get("ocppEnabled", 0))
        except (ValueError, TypeError):
            return False

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on cloud control."""
        try:
            await self.device.async_send_command("ocppEvent", {"ocppEnabled": 1})
            await self.coordinator.async_request_refresh()
        except HomeAssistantError as err:
            _LOGGER.error(f"Failed to enable cloud control: {err}")
            raise

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off cloud control."""
        try:
            await self.device.async_send_command("ocppEvent", {"ocppEnabled": 0})
            await self.coordinator.async_request_refresh()
        except HomeAssistantError as err:
            _LOGGER.error(f"Failed to disable cloud control: {err}")
            raise


class GrizzleEChargeSwitch(GrizzleESwitch):
    """Switch to control charging (enable/disable)."""

    _attr_unique_id = "grizzle_e_charge"
    _attr_name = "Charge"
    _attr_icon = "mdi:power-plug"

    @property
    def is_on(self) -> bool:
        """Return True if charging is enabled.

        Note: evseEnabled=1 means STOP charging, so we invert the logic.
        When this switch is ON, the user wants charging enabled (evseEnabled=0).
        """
        data = getattr(self.coordinator, "data", None) or {}
        try:
            evse_enabled = int(data.get("evseEnabled", 0))
            # evseEnabled=0 means allow charging (switch ON)
            # evseEnabled=1 means stop charging (switch OFF)
            return evse_enabled == 0
        except (ValueError, TypeError):
            return True

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on charging (allow charging)."""
        try:
            # Disable cloud control first
            await self.device.async_send_command("ocppEvent", {"ocppEnabled": 0})
            # Then enable charging (evseEnabled=0 means allow charging)
            await self.device.async_send_command("pageEvent", {
                "evseEnabled": 0,
                "suspendLimits": 1,
            })
            await self.coordinator.async_request_refresh()
        except HomeAssistantError as err:
            _LOGGER.error(f"Failed to enable charging: {err}")
            raise

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off charging (stop charging)."""
        try:
            # Disable cloud control first
            await self.device.async_send_command("ocppEvent", {"ocppEnabled": 0})
            # Then stop charging (evseEnabled=1 means stop charging)
            await self.device.async_send_command("pageEvent", {
                "evseEnabled": 1,
                "suspendLimits": 0,
            })
            await self.coordinator.async_request_refresh()
        except HomeAssistantError as err:
            _LOGGER.error(f"Failed to disable charging: {err}")
            raise
