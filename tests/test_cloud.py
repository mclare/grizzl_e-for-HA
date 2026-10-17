"""Tests for the Grizzl-E Connect cloud connection.

The station payload in fixtures/cloud_stations.json is a real GET /client/stations
response from a Grizzl-E Duo, with personal details replaced.
"""
import copy
import json
from http import HTTPStatus
from pathlib import Path

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

from custom_components.grizzl_e.const import (
    CONF_CONNECTION_TYPE,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_STATION_ID,
    CONF_TOKEN,
    CONNECTION_CLOUD,
    DOMAIN,
)

API = "https://connect-api.unitedchargers.com"
STATION_ID = "000000000000000000000002"
SCHEDULE_ID = "6aca7bd1f68a64e58409bff0"
RATE_ZONE_ID = "6ac6d45d0528d5cbde572d6f"
STATIONS = json.loads((Path(__file__).parent / "fixtures" / "cloud_stations.json").read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def stations_payload():
    return copy.deepcopy(STATIONS)


def cloud_entry(**data):
    return MockConfigEntry(
        domain=DOMAIN,
        title="GRD-L0000000001",
        unique_id=STATION_ID,
        data={
            CONF_CONNECTION_TYPE: CONNECTION_CLOUD,
            CONF_STATION_ID: STATION_ID,
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_TOKEN: "token-1",
            CONF_REFRESH_TOKEN: "refresh-1",
            **data,
        },
    )


async def setup_cloud(hass, aioclient_mock, payload=None, **data):
    aioclient_mock.get(f"{API}/client/stations", json=payload or stations_payload())
    entry = cloud_entry(**data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def entity_id(hass, domain, entry, key):
    return er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_cloud_{key}")


def state(hass, domain, entry, key):
    eid = entity_id(hass, domain, entry, key)
    assert eid, f"no {domain} entity for {key}"
    return hass.states.get(eid)


def get_device(hass, entry):
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert (DOMAIN, entry.entry_id) in device.identifiers
    return device


def calls(aioclient_mock, method):
    return [(str(url), body, headers) for m, url, body, headers in aioclient_mock.mock_calls if m.upper() == method]


# --- setup and entity state ---------------------------------------------------


async def test_setup_creates_cloud_entities(hass, aioclient_mock):
    entry = await setup_cloud(hass, aioclient_mock)
    assert entry.state is ConfigEntryState.LOADED

    assert state(hass, "sensor", entry, "status").state == "Available"
    assert state(hass, "sensor", entry, "connector_status_p1").state == "Available"
    assert state(hass, "sensor", entry, "connector_status_p2").state == "SuspendedEV"
    assert state(hass, "sensor", entry, "next_schedule_change").state == "2026-10-10T23:00:00+00:00"

    # Connector 2 has a session in progress; connector 1 doesn't.
    assert state(hass, "sensor", entry, "voltage_p2").state == "243"
    assert state(hass, "sensor", entry, "temperature_p2").state == "10"
    assert state(hass, "sensor", entry, "session_time_p2").state == "10401"
    assert state(hass, "sensor", entry, "session_energy_p2").state == "0.0"
    assert state(hass, "sensor", entry, "session_start_p2").state == "2026-10-10T15:00:13+00:00"
    cost = state(hass, "sensor", entry, "session_cost_p2")
    assert cost.state == "0"
    assert cost.attributes["unit_of_measurement"] == "USD"
    assert state(hass, "sensor", entry, "voltage_p1").state == "unknown"
    assert state(hass, "sensor", entry, "power_p1").state == "0"

    assert state(hass, "binary_sensor", entry, "online").state == "on"
    assert state(hass, "binary_sensor", entry, "vehicle_connected_p1").state == "off"
    assert state(hass, "binary_sensor", entry, "vehicle_connected_p2").state == "on"
    assert state(hass, "binary_sensor", entry, "charging_p2").state == "off"
    assert state(hass, "binary_sensor", entry, "active_by_schedule_p1").state == "on"

    mode = state(hass, "select", entry, "charge_mode_p2")
    assert mode.state == "Schedule"
    assert mode.attributes["options"] == ["Active", "Inactive", "Schedule"]

    limit = state(hass, "number", entry, "current_limit")
    assert float(limit.state) == 32
    assert limit.attributes["min"] == 16
    assert limit.attributes["max"] == 32  # capped by the DIP switch, below the model's 40 A

    schedule = state(hass, "switch", entry, f"schedule_{SCHEDULE_ID}")
    assert schedule.state == "on"
    assert schedule.attributes["friendly_name"].endswith("Schedule Off-peak123")
    assert schedule.attributes["start"] == "23:00"
    assert schedule.attributes["end"] == "07:00"
    # Off-peak123 is stored with an empty day list, which means every day.
    assert schedule.attributes["days"] == [
        "sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"
    ]
    zone = state(hass, "switch", entry, f"schedule_{RATE_ZONE_ID}")
    assert zone.attributes["friendly_name"].endswith("Rate Zone Winter")
    assert zone.attributes["days"] == ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
    assert zone.attributes["start_2"] == "20:00"
    assert zone.attributes["price_per_kwh"] == 0.0923

    assert state(hass, "button", entry, "reboot") is not None

    device = get_device(hass, entry)
    assert device.model == "Grizzl-E Duo 40A"
    assert device.sw_version == "UDGRW070L-04.03.2"
    assert device.serial_number == "GRD-L0000000001"

    # Requests identify as the app and carry the bearer token.
    _, _, headers = calls(aioclient_mock, "GET")[0]
    assert headers["authorization"] == "Bearer token-1"
    assert headers["x-application-name"] == "Grizzl-E Connect"


async def test_single_connector_has_no_port_suffix(hass, aioclient_mock):
    payload = stations_payload()
    payload["stations"][0]["connectors"] = payload["stations"][0]["connectors"][:1]
    entry = await setup_cloud(hass, aioclient_mock, payload)
    assert state(hass, "sensor", entry, "connector_status").state == "Available"
    assert entity_id(hass, "sensor", entry, "connector_status_p1") is None

    aioclient_mock.post(f"{API}/client/stations/{STATION_ID}/mode", json={})
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": entity_id(hass, "select", entry, "charge_mode"), "option": "Active"},
        blocking=True,
    )
    # Single-cable chargers use connectorId 0.
    assert calls(aioclient_mock, "POST")[-1][1] == {"mode": "Active", "connectorId": 0}


async def test_unload(hass, aioclient_mock):
    entry = await setup_cloud(hass, aioclient_mock)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


# --- controls -----------------------------------------------------------------


async def test_select_mode_on_duo_connector(hass, aioclient_mock):
    entry = await setup_cloud(hass, aioclient_mock)
    aioclient_mock.post(f"{API}/client/stations/{STATION_ID}/mode", json={})
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": entity_id(hass, "select", entry, "charge_mode_p2"), "option": "Inactive"},
        blocking=True,
    )
    assert calls(aioclient_mock, "POST")[-1][1] == {"mode": "Inactive", "connectorId": 2}


async def test_set_current_limit(hass, aioclient_mock):
    entry = await setup_cloud(hass, aioclient_mock)
    aioclient_mock.put(f"{API}/client/stations/{STATION_ID}/currentLimit", json={})
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": entity_id(hass, "number", entry, "current_limit"), "value": 24},
        blocking=True,
    )
    assert calls(aioclient_mock, "PUT")[-1][1] == {"value": 24}


async def test_schedule_switch(hass, aioclient_mock):
    entry = await setup_cloud(hass, aioclient_mock)
    aioclient_mock.post(f"{API}/client/stations/{STATION_ID}/scheduleEnable", json={})
    await hass.services.async_call(
        "switch", "turn_off",
        {"entity_id": entity_id(hass, "switch", entry, f"schedule_{SCHEDULE_ID}")},
        blocking=True,
    )
    assert calls(aioclient_mock, "POST")[-1][1] == {"_id": SCHEDULE_ID, "scheduleEnabled": False}


async def test_reboot(hass, aioclient_mock):
    entry = await setup_cloud(hass, aioclient_mock)
    aioclient_mock.post(f"{API}/client/stations/{STATION_ID}/reboot", json={})
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id(hass, "button", entry, "reboot")}, blocking=True
    )
    assert calls(aioclient_mock, "POST")[-1][0] == f"{API}/client/stations/{STATION_ID}/reboot"


async def test_command_error_is_raised(hass, aioclient_mock):
    entry = await setup_cloud(hass, aioclient_mock)
    aioclient_mock.put(
        f"{API}/client/stations/{STATION_ID}/currentLimit",
        status=HTTPStatus.BAD_REQUEST,
        json={"message": "Invalid value"},
    )
    with pytest.raises(HomeAssistantError, match="Invalid value"):
        await hass.services.async_call(
            "number", "set_value",
            {"entity_id": entity_id(hass, "number", entry, "current_limit"), "value": 20},
            blocking=True,
        )


async def test_schedule_switches_follow_deletions(hass, aioclient_mock):
    entry = await setup_cloud(hass, aioclient_mock)
    assert entity_id(hass, "switch", entry, f"schedule_{SCHEDULE_ID}")

    payload = stations_payload()
    payload["stations"][0]["pricesByZone"] = [
        z for z in payload["stations"][0]["pricesByZone"] if z["_id"] != SCHEDULE_ID
    ]
    payload["stations"][0]["pricesByZone"].append(
        {"_id": "new-schedule", "name": "Night", "isSchedule": True, "scheduleEnabled": False,
         "startHours": 1, "startMinutes": 30, "endHours": 5, "endMinutes": 0, "days": [0]}
    )
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/client/stations", json=payload)
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert entity_id(hass, "switch", entry, f"schedule_{SCHEDULE_ID}") is None
    new = state(hass, "switch", entry, "schedule_new-schedule")
    assert new.state == "off"
    assert new.attributes["start"] == "01:30"


# --- services -----------------------------------------------------------------


def device_id(hass, entry):
    return get_device(hass, entry).id


async def test_create_schedule(hass, aioclient_mock):
    entry = await setup_cloud(hass, aioclient_mock)
    aioclient_mock.post(f"{API}/client/stations/{STATION_ID}/scheduleUpdate", json={})
    await hass.services.async_call(
        DOMAIN, "set_schedule",
        {"device_id": device_id(hass, entry), "name": "Off-peak", "start": "23:00", "end": "07:00",
         "days": ["monday", "sunday"]},
        blocking=True,
    )
    assert calls(aioclient_mock, "POST")[-1][1] == {
        "price": {
            "name": "Off-peak", "startHours": 23, "startMinutes": 0, "endHours": 7, "endMinutes": 0,
            "allDay": False, "days": [0, 1], "isSchedule": True, "currentLimit": None, "connectorId": 0,
        }
    }


async def test_create_schedule_defaults_to_every_day(hass, aioclient_mock):
    entry = await setup_cloud(hass, aioclient_mock)
    aioclient_mock.post(f"{API}/client/stations/{STATION_ID}/scheduleUpdate", json={})
    await hass.services.async_call(
        DOMAIN, "set_schedule",
        {"device_id": device_id(hass, entry), "name": "All day", "all_day": True, "current_limit": 16},
        blocking=True,
    )
    price = calls(aioclient_mock, "POST")[-1][1]["price"]
    assert price["days"] == [0, 1, 2, 3, 4, 5, 6]
    assert price["allDay"] is True
    assert (price["startHours"], price["endHours"]) == (0, 0)
    assert price["currentLimit"] == 16


async def test_create_schedule_requires_times(hass, aioclient_mock):
    entry = await setup_cloud(hass, aioclient_mock)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "set_schedule", {"device_id": device_id(hass, entry), "name": "x", "start": "01:00"},
            blocking=True,
        )


async def test_update_schedule_keeps_other_fields(hass, aioclient_mock):
    entry = await setup_cloud(hass, aioclient_mock)
    aioclient_mock.post(f"{API}/client/stations/{STATION_ID}/scheduleUpdate", json={})
    await hass.services.async_call(
        DOMAIN, "set_schedule",
        {"device_id": device_id(hass, entry), "schedule_id": SCHEDULE_ID, "end": "06:30"},
        blocking=True,
    )
    price = calls(aioclient_mock, "POST")[-1][1]["price"]
    assert price["_id"] == SCHEDULE_ID
    assert price["name"] == "Off-peak123"
    assert (price["startHours"], price["startMinutes"]) == (23, 0)
    assert (price["endHours"], price["endMinutes"]) == (6, 30)
    assert price["scheduleEnabled"] is True
    assert price["isSchedule"] is True


async def test_unknown_schedule_id(hass, aioclient_mock):
    entry = await setup_cloud(hass, aioclient_mock)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "delete_schedule", {"device_id": device_id(hass, entry), "schedule_id": RATE_ZONE_ID},
            blocking=True,
        )


async def test_delete_schedule(hass, aioclient_mock):
    entry = await setup_cloud(hass, aioclient_mock)
    aioclient_mock.delete(f"{API}/client/stations/{STATION_ID}/scheduleDelete/{SCHEDULE_ID}", json={})
    await hass.services.async_call(
        DOMAIN, "delete_schedule", {"device_id": device_id(hass, entry), "schedule_id": SCHEDULE_ID},
        blocking=True,
    )
    assert calls(aioclient_mock, "DELETE")


async def test_update_rate_zone_keeps_second_window(hass, aioclient_mock):
    entry = await setup_cloud(hass, aioclient_mock)
    aioclient_mock.post(f"{API}/client/stations/{STATION_ID}/pricesByZoneUpdate", json={})
    await hass.services.async_call(
        DOMAIN, "set_rate_zone",
        {"device_id": device_id(hass, entry), "zone_id": RATE_ZONE_ID, "price": 0.11},
        blocking=True,
    )
    price = calls(aioclient_mock, "POST")[-1][1]["price"]
    assert price["_id"] == RATE_ZONE_ID
    assert price["priceKW"] == 0.11
    assert price["name"] == "Winter"
    assert price["days"] == [1, 2, 3, 4, 5, 6]
    assert (price["startHours2"], price["endHours2"]) == (20, 6)
    assert price["useSeason"] is False


async def test_create_rate_zone_and_base_rate(hass, aioclient_mock):
    entry = await setup_cloud(hass, aioclient_mock)
    aioclient_mock.post(f"{API}/client/stations/{STATION_ID}/pricesByZoneUpdate", json={})
    aioclient_mock.put(f"{API}/client/stations/{STATION_ID}/rate", json={})
    await hass.services.async_call(
        DOMAIN, "set_rate_zone",
        {"device_id": device_id(hass, entry), "name": "On-peak", "price": 0.2, "start": "07:00",
         "end": "11:00", "days": ["monday"], "summer_price": 0.25},
        blocking=True,
    )
    assert calls(aioclient_mock, "POST")[-1][1] == {
        "price": {
            "name": "On-peak", "priceKW": 0.2, "startHours": 7, "startMinutes": 0, "endHours": 11,
            "endMinutes": 0, "allDay": False, "days": [1], "priceKWSummer": 0.25, "useSeason": True,
            "currentLimit": None, "connectorId": 0,
        }
    }
    await hass.services.async_call(
        DOMAIN, "set_base_rate", {"device_id": device_id(hass, entry), "price": 0.1}, blocking=True
    )
    assert calls(aioclient_mock, "PUT")[-1][1] == {"priceKW": 0.1}


async def test_delete_rate_zone(hass, aioclient_mock):
    entry = await setup_cloud(hass, aioclient_mock)
    aioclient_mock.delete(f"{API}/client/stations/{STATION_ID}/pricesByZoneDelete/{RATE_ZONE_ID}", json={})
    await hass.services.async_call(
        DOMAIN, "delete_rate_zone", {"device_id": device_id(hass, entry), "zone_id": RATE_ZONE_ID},
        blocking=True,
    )
    assert calls(aioclient_mock, "DELETE")


# --- auth ---------------------------------------------------------------------


async def test_expired_token_is_refreshed_and_saved(hass, aioclient_mock):
    responses = iter([
        AiohttpClientMockResponse("get", f"{API}/client/stations", status=HTTPStatus.UNAUTHORIZED),
        AiohttpClientMockResponse("get", f"{API}/client/stations", json=stations_payload()),
    ])

    async def stations(method, url, data):
        return next(responses)

    aioclient_mock.get(f"{API}/client/stations", side_effect=stations)
    aioclient_mock.post(
        f"{API}/client/auth/refresh-token", json={"token": "token-2", "refreshToken": "refresh-2"}
    )
    entry = cloud_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert calls(aioclient_mock, "POST")[0][1] == {"refreshToken": "refresh-1"}
    assert entry.data[CONF_TOKEN] == "token-2"
    assert entry.data[CONF_REFRESH_TOKEN] == "refresh-2"
    assert calls(aioclient_mock, "GET")[-1][2]["authorization"] == "Bearer token-2"


async def test_rejected_refresh_token_logs_in_again(hass, aioclient_mock):
    responses = iter([
        AiohttpClientMockResponse("get", f"{API}/client/stations", status=HTTPStatus.UNAUTHORIZED),
        AiohttpClientMockResponse("get", f"{API}/client/stations", json=stations_payload()),
    ])

    async def stations(method, url, data):
        return next(responses)

    aioclient_mock.get(f"{API}/client/stations", side_effect=stations)
    aioclient_mock.post(f"{API}/client/auth/refresh-token", status=HTTPStatus.UNAUTHORIZED)
    aioclient_mock.post(f"{API}/client/auth/login", json={"token": "token-3", "refreshToken": "refresh-3"})
    entry = cloud_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    login = [c for c in calls(aioclient_mock, "POST") if c[0].endswith("/login")]
    assert login[0][1] == {"emailOrPhone": "user@example.com", "password": "secret"}
    assert "authorization" not in login[0][2]
    assert entry.data[CONF_TOKEN] == "token-3"


async def test_auth_failure_starts_reauth(hass, aioclient_mock):
    aioclient_mock.get(f"{API}/client/stations", status=HTTPStatus.UNAUTHORIZED)
    aioclient_mock.post(f"{API}/client/auth/refresh-token", status=HTTPStatus.UNAUTHORIZED)
    aioclient_mock.post(f"{API}/client/auth/login", status=HTTPStatus.UNAUTHORIZED)
    entry = cloud_entry()
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_cloud_unreachable_retries(hass, aioclient_mock):
    aioclient_mock.get(f"{API}/client/stations", status=HTTPStatus.BAD_GATEWAY)
    entry = cloud_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_station_missing_from_account_retries(hass, aioclient_mock):
    aioclient_mock.get(f"{API}/client/stations", json={"stations": [], "groups": []})
    entry = cloud_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
