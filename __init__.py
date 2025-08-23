import logging
import aiohttp
from datetime import timedelta
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

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

    # Configure session with timeouts
    timeout = aiohttp.ClientTimeout(
        total=REQUEST_TIMEOUT,
        connect=CONNECT_TIMEOUT,
        sock_connect=CONNECT_TIMEOUT,
        sock_read=SOCKET_TIMEOUT
    )
    session = aiohttp.ClientSession(timeout=timeout)

    async def async_update_data():
        """Fetch data from Grizzl-E device."""
        url = f"http://{host}/main"
        try:
            # Outer timeout as a safety net
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    auth=aiohttp.BasicAuth(username, password),
                ) as resp:
                    if resp.status != 200:
                        raise UpdateFailed(f"Bad status {resp.status}")
                    return await resp.json(content_type=None)
        except Exception as err:
            raise UpdateFailed(f"Error fetching Grizzl-E data: {err}")
        finally:
            await session.close()

    # Initialize coordinator
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )
    
    # Create device
    device = GrizzleEDevice(coordinator, entry)
    
    # Store in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "device": device,
        "coordinator": coordinator,
        "session": session
    }
    
    # Forward the setup to the sensor and binary_sensor platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok and DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        # Close the session if it exists
        if "session" in hass.data[DOMAIN][entry.entry_id]:
            session = hass.data[DOMAIN][entry.entry_id]["session"]
            if not session.closed:
                await session.close()
        
        # Remove the entry
        hass.data[DOMAIN].pop(entry.entry_id)
        
        # Clean up domain if no entries left
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    
    return unload_ok
