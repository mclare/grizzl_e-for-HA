"""Services for editing Grizzl-E Connect schedules and electricity rates."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .cloud import GrizzleECloudCoordinator
from .const import DOMAIN, WEEKDAYS

SERVICE_SET_SCHEDULE = "set_schedule"
SERVICE_DELETE_SCHEDULE = "delete_schedule"
SERVICE_SET_RATE_ZONE = "set_rate_zone"
SERVICE_DELETE_RATE_ZONE = "delete_rate_zone"
SERVICE_SET_BASE_RATE = "set_base_rate"

ATTR_DEVICE_ID = "device_id"
ATTR_SCHEDULE_ID = "schedule_id"
ATTR_ZONE_ID = "zone_id"
ATTR_NAME = "name"
ATTR_START = "start"
ATTR_END = "end"
ATTR_DAYS = "days"
ATTR_ALL_DAY = "all_day"
ATTR_CURRENT_LIMIT = "current_limit"
ATTR_CONNECTOR = "connector"
ATTR_PRICE = "price"
ATTR_SUMMER_PRICE = "summer_price"

_DAYS = vol.All(cv.ensure_list, [vol.In(WEEKDAYS)])
_PRICE = vol.All(vol.Coerce(float), vol.Range(min=0))

SET_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Optional(ATTR_SCHEDULE_ID): cv.string,
        vol.Optional(ATTR_NAME): cv.string,
        vol.Optional(ATTR_START): cv.time,
        vol.Optional(ATTR_END): cv.time,
        vol.Optional(ATTR_DAYS): _DAYS,
        vol.Optional(ATTR_ALL_DAY): cv.boolean,
        vol.Optional(ATTR_CURRENT_LIMIT): vol.All(vol.Coerce(int), vol.Range(min=1, max=80)),
        vol.Optional(ATTR_CONNECTOR): vol.All(vol.Coerce(int), vol.Range(min=0, max=8)),
    }
)
DELETE_SCHEDULE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_DEVICE_ID): cv.string, vol.Required(ATTR_SCHEDULE_ID): cv.string}
)
SET_RATE_ZONE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Optional(ATTR_ZONE_ID): cv.string,
        vol.Optional(ATTR_NAME): cv.string,
        vol.Optional(ATTR_PRICE): _PRICE,
        vol.Optional(ATTR_START): cv.time,
        vol.Optional(ATTR_END): cv.time,
        vol.Optional(ATTR_DAYS): _DAYS,
        vol.Optional(ATTR_ALL_DAY): cv.boolean,
        vol.Optional(ATTR_SUMMER_PRICE): _PRICE,
    }
)
DELETE_RATE_ZONE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_DEVICE_ID): cv.string, vol.Required(ATTR_ZONE_ID): cv.string}
)
SET_BASE_RATE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_DEVICE_ID): cv.string, vol.Required(ATTR_PRICE): _PRICE}
)


def _coordinator_for_device(hass: HomeAssistant, device_id: str) -> GrizzleECloudCoordinator:
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError(f"Unknown device {device_id}")
    entries = hass.data.get(DOMAIN, {})
    for entry_id in device.config_entries:
        coordinator = entries.get(entry_id, {}).get("coordinator")
        if isinstance(coordinator, GrizzleECloudCoordinator):
            return coordinator
    raise ServiceValidationError(
        "This service needs a Grizzl-E charger set up through the Grizzl-E Connect cloud"
    )


def _find_zone(coordinator: GrizzleECloudCoordinator, zone_id: str, *, schedule: bool) -> dict:
    for zone in (coordinator.data or {}).get("pricesByZone") or []:
        if isinstance(zone, dict) and zone.get("_id") == zone_id and bool(zone.get("isSchedule")) == schedule:
            return zone
    kind = "schedule" if schedule else "rate zone"
    raise ServiceValidationError(f"No {kind} with id {zone_id} on this charger")


def _window(call: ServiceCall, existing: dict | None) -> dict:
    """Resolve name, times, days and all_day from the call, falling back to ``existing``."""
    existing = existing or {}
    name = call.data.get(ATTR_NAME, existing.get("name"))
    if not name:
        raise ServiceValidationError("A name is required")
    all_day = call.data.get(ATTR_ALL_DAY, bool(existing.get("allDay")))
    times = {}
    for attr, hours_key, minutes_key in (
        (ATTR_START, "startHours", "startMinutes"),
        (ATTR_END, "endHours", "endMinutes"),
    ):
        if attr in call.data:
            times[attr] = (call.data[attr].hour, call.data[attr].minute)
        elif existing:
            times[attr] = (int(existing.get(hours_key) or 0), int(existing.get(minutes_key) or 0))
        elif all_day:
            times[attr] = (0, 0)
        else:
            raise ServiceValidationError(f"'{attr}' is required unless all_day is set")
    if ATTR_DAYS in call.data:
        days = sorted({WEEKDAYS.index(day) for day in call.data[ATTR_DAYS]})
    elif existing:
        days = list(existing.get("days") or [])
    else:
        days = list(range(7))
    return {"name": name, "start": times[ATTR_START], "end": times[ATTR_END], "days": days, "all_day": all_day}


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's services (they only act on cloud entries)."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_SCHEDULE):
        return

    async def set_schedule(call: ServiceCall) -> None:
        coordinator = _coordinator_for_device(hass, call.data[ATTR_DEVICE_ID])
        schedule_id = call.data.get(ATTR_SCHEDULE_ID)
        existing = _find_zone(coordinator, schedule_id, schedule=True) if schedule_id else None
        await coordinator.async_command(
            coordinator.client.update_schedule(
                coordinator.station_id,
                **_window(call, existing),
                current_limit=call.data.get(
                    ATTR_CURRENT_LIMIT, existing.get("currentLimit") if existing else None
                ),
                connector_id=call.data.get(
                    ATTR_CONNECTOR, int(existing.get("connectorId") or 0) if existing else 0
                ),
                schedule_id=schedule_id,
                base=existing,
            )
        )

    async def delete_schedule(call: ServiceCall) -> None:
        coordinator = _coordinator_for_device(hass, call.data[ATTR_DEVICE_ID])
        schedule_id = call.data[ATTR_SCHEDULE_ID]
        _find_zone(coordinator, schedule_id, schedule=True)
        await coordinator.async_command(coordinator.client.delete_schedule(coordinator.station_id, schedule_id))

    async def set_rate_zone(call: ServiceCall) -> None:
        coordinator = _coordinator_for_device(hass, call.data[ATTR_DEVICE_ID])
        zone_id = call.data.get(ATTR_ZONE_ID)
        existing = _find_zone(coordinator, zone_id, schedule=False) if zone_id else None
        price = call.data.get(ATTR_PRICE, existing.get("priceKW") if existing else None)
        if price is None:
            raise ServiceValidationError("A price is required")
        await coordinator.async_command(
            coordinator.client.update_rate_zone(
                coordinator.station_id,
                **_window(call, existing),
                price_per_kwh=price,
                summer_price_per_kwh=call.data.get(ATTR_SUMMER_PRICE),
                zone_id=zone_id,
                base=existing,
            )
        )

    async def delete_rate_zone(call: ServiceCall) -> None:
        coordinator = _coordinator_for_device(hass, call.data[ATTR_DEVICE_ID])
        zone_id = call.data[ATTR_ZONE_ID]
        _find_zone(coordinator, zone_id, schedule=False)
        await coordinator.async_command(coordinator.client.delete_rate_zone(coordinator.station_id, zone_id))

    async def set_base_rate(call: ServiceCall) -> None:
        coordinator = _coordinator_for_device(hass, call.data[ATTR_DEVICE_ID])
        await coordinator.async_command(
            coordinator.client.set_base_rate(coordinator.station_id, call.data[ATTR_PRICE])
        )

    hass.services.async_register(DOMAIN, SERVICE_SET_SCHEDULE, set_schedule, schema=SET_SCHEDULE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DELETE_SCHEDULE, delete_schedule, schema=DELETE_SCHEDULE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_RATE_ZONE, set_rate_zone, schema=SET_RATE_ZONE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DELETE_RATE_ZONE, delete_rate_zone, schema=DELETE_RATE_ZONE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_BASE_RATE, set_base_rate, schema=SET_BASE_RATE_SCHEMA)
