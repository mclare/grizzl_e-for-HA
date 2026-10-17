"""Config flow tests for the local and Grizzl-E Connect cloud connections."""
import copy
import json
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
STATIONS = json.loads((Path(__file__).parent / "fixtures" / "cloud_stations.json").read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def no_setup():
    """Don't set up the entry once the flow creates it."""
    with patch("custom_components.grizzl_e.async_setup_entry", return_value=True):
        yield


async def start_reauth(hass, entry):
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )


async def start(hass, option):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["connection", "cloud"]
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": option})


async def test_local_option_shows_original_form(hass):
    result = await start(hass, "connection")
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "connection"
    assert set(result["data_schema"].schema) == {"host", "username", "password"}


async def test_cloud_login_single_station(hass, aioclient_mock):
    aioclient_mock.post(f"{API}/client/auth/login", json={"token": "t", "refreshToken": "r", "isVerified": True})
    aioclient_mock.get(f"{API}/client/stations", json=copy.deepcopy(STATIONS))

    result = await start(hass, "cloud")
    assert result["step_id"] == "cloud"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: "user@example.com", CONF_PASSWORD: "secret"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "GRD-L0000000001"
    assert result["result"].unique_id == STATION_ID
    assert result["data"] == {
        CONF_CONNECTION_TYPE: CONNECTION_CLOUD,
        CONF_STATION_ID: STATION_ID,
        CONF_EMAIL: "user@example.com",
        CONF_PASSWORD: "secret",
        CONF_TOKEN: "t",
        CONF_REFRESH_TOKEN: "r",
    }


async def test_cloud_login_picks_station(hass, aioclient_mock):
    payload = copy.deepcopy(STATIONS)
    second = copy.deepcopy(payload["stations"][0])
    second.update(id="other", serialNumber="GR-2", displayName="Garage")
    payload["stations"].append(second)
    aioclient_mock.post(f"{API}/client/auth/login", json={"token": "t", "refreshToken": "r"})
    aioclient_mock.get(f"{API}/client/stations", json=payload)

    result = await start(hass, "cloud")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: "user@example.com", CONF_PASSWORD: "secret"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "station"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_STATION_ID: "other"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Garage"
    assert result["data"][CONF_STATION_ID] == "other"


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (HTTPStatus.UNAUTHORIZED, {"message": "Wrong password"}, "invalid_auth"),
        (HTTPStatus.OK, {"token": "t", "isVerified": False}, "account_not_verified"),
        (HTTPStatus.INTERNAL_SERVER_ERROR, None, "cannot_connect"),
    ],
)
async def test_cloud_login_errors(hass, aioclient_mock, status, body, error):
    aioclient_mock.post(f"{API}/client/auth/login", status=status, json=body)
    result = await start(hass, "cloud")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: "user@example.com", CONF_PASSWORD: "bad"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_cloud_no_stations(hass, aioclient_mock):
    aioclient_mock.post(f"{API}/client/auth/login", json={"token": "t", "refreshToken": "r"})
    aioclient_mock.get(f"{API}/client/stations", json={"stations": [], "groups": []})
    result = await start(hass, "cloud")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: "user@example.com", CONF_PASSWORD: "secret"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_stations"


async def test_cloud_already_configured(hass, aioclient_mock):
    MockConfigEntry(domain=DOMAIN, unique_id=STATION_ID, data={}).add_to_hass(hass)
    aioclient_mock.post(f"{API}/client/auth/login", json={"token": "t", "refreshToken": "r"})
    aioclient_mock.get(f"{API}/client/stations", json=copy.deepcopy(STATIONS))
    result = await start(hass, "cloud")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: "user@example.com", CONF_PASSWORD: "secret"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_with_password(hass, aioclient_mock):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=STATION_ID,
        data={
            CONF_CONNECTION_TYPE: CONNECTION_CLOUD,
            CONF_STATION_ID: STATION_ID,
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "old",
            CONF_TOKEN: "old",
            CONF_REFRESH_TOKEN: "old",
        },
    )
    entry.add_to_hass(hass)
    aioclient_mock.post(f"{API}/client/auth/login", json={"token": "new", "refreshToken": "new-r"})
    aioclient_mock.get(f"{API}/client/stations", json=copy.deepcopy(STATIONS))

    result = await start_reauth(hass, entry)
    assert result["step_id"] == "reauth_confirm"
    assert set(result["data_schema"].schema) == {CONF_PASSWORD}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "new-pw"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new-pw"
    assert entry.data[CONF_TOKEN] == "new"
    assert entry.data[CONF_REFRESH_TOKEN] == "new-r"


async def test_reauth_wrong_account(hass, aioclient_mock):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=STATION_ID,
        data={
            CONF_CONNECTION_TYPE: CONNECTION_CLOUD,
            CONF_STATION_ID: STATION_ID,
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "old",
            CONF_TOKEN: "old",
            CONF_REFRESH_TOKEN: "old",
        },
    )
    entry.add_to_hass(hass)
    aioclient_mock.post(f"{API}/client/auth/login", json={"token": "t", "refreshToken": "r"})
    aioclient_mock.get(f"{API}/client/stations", json={"stations": [], "groups": []})

    result = await start_reauth(hass, entry)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "pw"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "station_not_found"}


async def test_cloud_options_minimum_interval(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_CONNECTION_TYPE: CONNECTION_CLOUD, CONF_STATION_ID: STATION_ID}
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    schema = result["data_schema"]
    assert schema({})["scan_interval"] == 30
    with pytest.raises(Exception):
        schema({"scan_interval": 5})


async def test_local_options_unchanged(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "1.2.3.4", "username": "u", "password": "p"})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    schema = result["data_schema"]
    assert schema({})["scan_interval"] == 5
    assert schema({"scan_interval": 1})["scan_interval"] == 1
