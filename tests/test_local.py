"""Local (charger web interface) entries keep working alongside cloud support."""
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.grizzl_e.const import DOMAIN

MAIN = {
    "curMeas1": 22.17, "voltMeas1": 236, "powerMeas": 5234, "state": 4, "pilot": 1,
    "sessionStarted": 1, "sessionTime": 600, "sessionEnergy": 1.5, "totalEnergy": 577.4,
    "temperature1": 20, "temperature2": 21, "RSSI": -60, "verFWMain": " 1.2.3 ",
    "verFWWifi": "4.5", "serialNum": "GR-1",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def test_existing_local_entry(hass, aioclient_mock):
    """Entries created before cloud support have no connection type and are local."""
    aioclient_mock.post("http://192.168.1.50/main", json=MAIN)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Grizzl-E Charger",
        data={"host": "192.168.1.50", "username": "admin", "password": "pw", "ports": 1},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    registry = er.async_get(hass)
    unique_ids = {e.unique_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)}
    # Same unique_ids as before, so history is kept; no cloud entities.
    assert unique_ids == {
        f"{entry.entry_id}_{key}"
        for key in (
            "temperature1", "temperature2", "RSSI", "verFWMain", "verFWWifi", "powerMeas", "curMeas1",
            "voltMeas1", "sessionEnergy", "totalEnergy", "sessionTime", "state", "pilot", "sessionStarted",
        )
    }
    power = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_powerMeas")
    assert hass.states.get(power).state == "5234"
    state = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_state")
    assert hass.states.get(state).state == "Vehicle Charging"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
