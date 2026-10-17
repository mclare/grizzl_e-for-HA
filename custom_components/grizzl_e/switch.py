"""Schedule switches for Grizzl-E Connect cloud entries.

The cloud keeps charging schedules and electricity rate zones in the station's
``pricesByZone`` list; either can be turned on or off as a charging window.
One switch is created per entry, and switches are added and removed as
schedules are created or deleted (from Home Assistant or the app).
"""
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory

from .cloud import GrizzleECloudEntity, is_cloud_entry
from .const import DOMAIN, WEEKDAYS


def station_zones(station):
    """Return the station's schedules and rate zones that have an id, keyed by id."""
    zones = station.get("pricesByZone") or []
    return {zone["_id"]: zone for zone in zones if isinstance(zone, dict) and zone.get("_id")}


async def async_setup_entry(hass, entry, async_add_entities):
    if not is_cloud_entry(entry) or entry.entry_id not in hass.data.get(DOMAIN, {}):
        return
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    known = set()

    @callback
    def sync_schedules():
        current = set(station_zones(coordinator.data or {}))
        added = current - known
        if added:
            known.update(added)
            async_add_entities(GrizzleEScheduleSwitch(coordinator, zone_id) for zone_id in sorted(added))
        removed = known - current
        if removed:
            registry = er.async_get(hass)
            for zone_id in removed:
                known.discard(zone_id)
                entity_id = registry.async_get_entity_id("switch", DOMAIN, schedule_unique_id(coordinator, zone_id))
                if entity_id:
                    registry.async_remove(entity_id)

    # Drop switches for schedules deleted while Home Assistant wasn't running.
    registry = er.async_get(hass)
    prefix = schedule_unique_id(coordinator, "")
    current = set(station_zones(coordinator.data or {}))
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            registry_entry.domain == "switch"
            and registry_entry.unique_id.startswith(prefix)
            and registry_entry.unique_id[len(prefix):] not in current
        ):
            registry.async_remove(registry_entry.entity_id)

    sync_schedules()
    entry.async_on_unload(coordinator.async_add_listener(sync_schedules))


def schedule_unique_id(coordinator, zone_id):
    return f"{coordinator.config_entry.entry_id}_cloud_schedule_{zone_id}"


class GrizzleEScheduleSwitch(GrizzleECloudEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator, zone_id):
        super().__init__(coordinator, f"schedule_{zone_id}", "Schedule")
        self.zone_id = zone_id

    @property
    def zone(self):
        return station_zones(self.station).get(self.zone_id)

    @property
    def available(self):
        return super().available and self.zone is not None

    @property
    def name(self):
        zone = self.zone
        if zone is None:
            return f"Schedule {self.zone_id}"
        label = "Schedule" if zone.get("isSchedule") else "Rate Zone"
        return f"{label} {zone.get('name') or self.zone_id}"

    @property
    def is_on(self):
        zone = self.zone
        return bool(zone.get("scheduleEnabled")) if zone else None

    @property
    def extra_state_attributes(self):
        zone = self.zone
        if zone is None:
            return {}
        attrs = {
            "schedule_id": self.zone_id,
            "kind": "schedule" if zone.get("isSchedule") else "rate_zone",
            "start": _hhmm(zone.get("startHours"), zone.get("startMinutes")),
            "end": _hhmm(zone.get("endHours"), zone.get("endMinutes")),
            "all_day": bool(zone.get("allDay")),
            "days": _day_names(zone.get("days")),
        }
        if zone.get("isSchedule"):
            attrs["current_limit"] = zone.get("currentLimit")
            attrs["connector"] = zone.get("connectorId")
        else:
            attrs["price_per_kwh"] = zone.get("priceKW")
            if zone.get("useSeason"):
                attrs["summer_price_per_kwh"] = zone.get("priceKWSummer")
            if "startHours2" in zone:
                attrs["start_2"] = _hhmm(zone.get("startHours2"), zone.get("startMinutes2"))
                attrs["end_2"] = _hhmm(zone.get("endHours2"), zone.get("endMinutes2"))
        return attrs

    async def async_turn_on(self, **kwargs):
        await self._async_set_enabled(True)

    async def async_turn_off(self, **kwargs):
        await self._async_set_enabled(False)

    async def _async_set_enabled(self, enabled):
        await self.coordinator.async_command(
            self.coordinator.client.enable_schedule(self.coordinator.station_id, self.zone_id, enabled)
        )


def _day_names(days):
    """The cloud stores an empty list for a schedule that runs every day."""
    if not days:
        return list(WEEKDAYS)
    return [WEEKDAYS[day] for day in days if isinstance(day, int) and 0 <= day < 7]


def _hhmm(hours, minutes):
    return f"{int(hours or 0):02d}:{int(minutes or 0):02d}"
