"""Grizzl-E Connect cloud support: coordinator, shared entity base and helpers."""
from __future__ import annotations

import logging
from collections.abc import Awaitable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .cloud_api import (
    GrizzleConnectAuthError,
    GrizzleConnectClient,
    GrizzleConnectError,
    station_id,
)
from .const import (
    CONF_CONNECTION_TYPE,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_STATION_ID,
    CONF_TOKEN,
    CONNECTION_CLOUD,
    CONNECTION_LOCAL,
    DEFAULT_CLOUD_SCAN_INTERVAL,
    DOMAIN,
    MANUFACTURER,
    MODEL,
)

_LOGGER = logging.getLogger(__name__)

CLOUD_PLATFORMS = ["sensor", "binary_sensor", "select", "number", "switch", "button"]

# OCPP connector statuses that mean a vehicle is plugged in.
PLUGGED_IN_STATUSES = {"Preparing", "Charging", "SuspendedEV", "SuspendedEVSE", "Finishing"}


def is_cloud_entry(entry: ConfigEntry) -> bool:
    return entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_LOCAL) == CONNECTION_CLOUD


def create_cloud_client(hass: HomeAssistant, entry: ConfigEntry) -> GrizzleConnectClient:
    """Build a client for an entry, persisting any tokens the cloud issues."""

    @callback
    def tokens_updated(token: str, refresh_token: str | None) -> None:
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_TOKEN: token, CONF_REFRESH_TOKEN: refresh_token},
        )

    return GrizzleConnectClient(
        async_get_clientsession(hass),
        email=entry.data.get(CONF_EMAIL),
        password=entry.data.get(CONF_PASSWORD),
        token=entry.data.get(CONF_TOKEN),
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
        on_tokens_updated=tokens_updated,
    )


class GrizzleECloudCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the cloud for one station. ``data`` is that station's raw payload."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: GrizzleConnectClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_CLOUD_SCAN_INTERVAL)
            ),
        )
        self.client = client
        self.station_id: str = entry.data[CONF_STATION_ID]

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            stations = await self.client.get_stations()
        except GrizzleConnectAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except GrizzleConnectError as err:
            raise UpdateFailed(f"Error fetching Grizzl-E Connect data: {err}") from err
        for station in stations:
            if station_id(station) == self.station_id:
                return station
        raise UpdateFailed(f"Station {self.station_id} is no longer on this Grizzl-E Connect account")

    async def async_command(self, command: Awaitable[Any]) -> None:
        """Run a client command, surface errors to the UI and refresh the state."""
        try:
            await command
        except GrizzleConnectAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(f"Grizzl-E Connect rejected the credentials: {err}") from err
        except GrizzleConnectError as err:
            raise HomeAssistantError(f"Grizzl-E Connect command failed: {err}") from err
        await self.async_request_refresh()


async def async_setup_cloud_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Grizzl-E Connect cloud config entry."""
    coordinator = GrizzleECloudCoordinator(hass, entry, create_cloud_client(hass, entry))
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    async def _options_updated(hass: HomeAssistant, updated_entry: ConfigEntry) -> None:
        # Also called when refreshed tokens are saved to the entry, so only act
        # when the interval actually changed.
        interval = timedelta(
            seconds=updated_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_CLOUD_SCAN_INTERVAL)
        )
        if interval != coordinator.update_interval:
            coordinator.update_interval = interval
            await coordinator.async_request_refresh()

    entry.async_on_unload(entry.add_update_listener(_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, CLOUD_PLATFORMS)
    return True


# --- payload helpers -----------------------------------------------------------


def parse_datetime(value: Any) -> datetime | None:
    """Parse the cloud's ISO 8601 timestamps (e.g. ``2026-10-10T23:00:00.000Z``)."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def first_number(values: Any) -> float | None:
    """Meter values come as lists with one entry per phase; return the first."""
    if isinstance(values, list):
        values = values[0] if values else None
    if isinstance(values, bool) or not isinstance(values, (int, float)):
        return None
    return values


def number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


class GrizzleECloudEntity(CoordinatorEntity[GrizzleECloudCoordinator]):
    """Base for cloud entities.

    ``connector_index`` is the 0-based position in the station's ``connectors``
    list for per-cable entities, or ``None`` for station-wide ones.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GrizzleECloudCoordinator,
        key: str,
        name: str,
        connector_index: int | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.connector_index = connector_index
        num_connectors = len(self.station.get("connectors") or [])
        if connector_index is not None and num_connectors > 1:
            name = f"{name} Port {connector_index + 1}"
            key = f"{key}_p{connector_index + 1}"
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_cloud_{key}"

    @property
    def station(self) -> dict[str, Any]:
        return self.coordinator.data or {}

    @property
    def connector(self) -> dict[str, Any] | None:
        if self.connector_index is None:
            return None
        connectors = self.station.get("connectors") or []
        if self.connector_index >= len(connectors) or not isinstance(connectors[self.connector_index], dict):
            return None
        return connectors[self.connector_index]

    @property
    def charge(self) -> dict[str, Any]:
        """The connector's charging session in progress, or an empty dict."""
        connector = self.connector or {}
        charge = connector.get("charge")
        return charge if isinstance(charge, dict) else {}

    @property
    def mode_connector_id(self) -> int:
        """connectorId for the mode endpoint: 0 on single-cable chargers, 1..n on a Duo."""
        if self.connector_index is None or len(self.station.get("connectors") or []) <= 1:
            return 0
        return self.connector_index + 1

    @property
    def available(self) -> bool:
        if not super().available or not self.coordinator.data:
            return False
        return self.connector_index is None or self.connector is not None

    @property
    def device_info(self) -> DeviceInfo:
        station = self.station
        model = station.get("model") if isinstance(station.get("model"), dict) else {}
        boot = station.get("bootNotification") if isinstance(station.get("bootNotification"), dict) else {}
        firmware = str(boot.get("firmwareVersion") or "").strip() or None
        serial = station.get("serialNumber") or station.get("identity")
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name=self.coordinator.config_entry.title,
            manufacturer=MANUFACTURER,
            model=str(model.get("displayName") or model.get("name") or boot.get("chargePointModel") or MODEL),
            sw_version=firmware,
            serial_number=str(serial) if serial else None,
        )
