import logging
import aiohttp
from datetime import timedelta
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN, DEFAULT_SCAN_INTERVAL, 
    REQUEST_TIMEOUT, CONNECT_TIMEOUT, SOCKET_TIMEOUT
)
from .device import GrizzleEDevice

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor"]

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Grizzl-E component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Grizzl-E from a config entry."""
    host = entry.data["host"]
    username = entry.data["username"]
    password = entry.data["password"]

    # Use HA shared session; apply timeouts per request
    session = async_get_clientsession(hass)
    timeout = aiohttp.ClientTimeout(
        total=REQUEST_TIMEOUT,
        connect=CONNECT_TIMEOUT,
        sock_connect=CONNECT_TIMEOUT,
        sock_read=SOCKET_TIMEOUT
    )

    async def async_update_data():
        """Fetch data from Grizzl-E device."""
        url = f"http://{host}/main"
        try:
            async with session.post(
                url,
                auth=aiohttp.BasicAuth(username, password),
                timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"Bad status {resp.status}")
                return await resp.json(content_type=None)
        except Exception as err:
            raise UpdateFailed(f"Error fetching Grizzl-E data: {err}")

    # Initialize coordinator
    scan_seconds = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(seconds=scan_seconds),
    )
    
    # Create device
    device = GrizzleEDevice(coordinator, entry)
    
    # Store in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "device": device,
        "coordinator": coordinator,
    }
    
    # Listen for options updates (e.g., scan_interval) and apply dynamically
    async def _options_updated(hass: HomeAssistant, updated_entry: ConfigEntry):
        new_seconds = updated_entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        coordinator.update_interval = timedelta(seconds=new_seconds)
        await coordinator.async_request_refresh()

    entry.async_on_unload(entry.add_update_listener(_options_updated))
    
    # Forward the setup to the sensor and binary_sensor platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok and DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        # Remove the entry
        hass.data[DOMAIN].pop(entry.entry_id)
        
        # Clean up domain if no entries left
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    
    return unload_ok
