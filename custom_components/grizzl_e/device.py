"""Device class for Grizzl-E EV Charger."""
import asyncio
import logging
import aiohttp
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, MANUFACTURER, MODEL, REQUEST_TIMEOUT, CONNECT_TIMEOUT, SOCKET_TIMEOUT

_LOGGER = logging.getLogger(__name__)

class GrizzleEDevice:
    """Grizzl-E device."""

    def __init__(self, coordinator: DataUpdateCoordinator, entry, session: aiohttp.ClientSession):
        """Initialize the device."""
        self.coordinator = coordinator
        self.entry = entry
        self.session = session

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information.

        Prefer dynamic data from the EVSE payload when available so the
        device registry shows accurate model and firmware.
        """
        data = getattr(self.coordinator, "data", None) or {}
        # Prefer payload model when present, fallback to static default
        model = data.get("model") or MODEL
        # Use EVSE main firmware as device software version; trim whitespace
        sw_version = (data.get("verFWMain") or "").strip() or None
        # Use serial if available for nicer identification in registry
        serial = data.get("serialNum") or data.get("stationId") or None

        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=self.entry.title,
            manufacturer=MANUFACTURER,
            model=model,
            sw_version=sw_version,
            serial_number=serial,
            configuration_url=f"http://{self.entry.data['host']}",
        )

    async def async_send_command(self, endpoint: str, params: dict) -> str:
        """Send a command to the device via specified endpoint.

        Args:
            endpoint: The endpoint name (e.g., 'pageEvent', 'ocppEvent')
            params: Dictionary of parameters to send

        Returns:
            Response text from the device.

        Raises:
            HomeAssistantError: If the command fails or device is unreachable.
        """
        host = self.entry.data["host"]
        username = self.entry.data["username"]
        password = self.entry.data["password"]
        url = f"http://{host}/{endpoint}"

        timeout = aiohttp.ClientTimeout(
            total=REQUEST_TIMEOUT,
            connect=CONNECT_TIMEOUT,
            sock_connect=CONNECT_TIMEOUT,
            sock_read=SOCKET_TIMEOUT
        )

        try:
            _LOGGER.debug(f"Sending command to {url}: {params}")
            async with self.session.post(
                url,
                auth=aiohttp.BasicAuth(username, password),
                data=params,
                timeout=timeout,
            ) as resp:
                response_text = await resp.text()
                _LOGGER.debug(f"Response from {url}: status={resp.status}, body={response_text}")

                if resp.status != 200:
                    raise HomeAssistantError(
                        f"Failed to send command to {url}: status {resp.status}, response: {response_text}"
                    )

                # Expect plain text "OK" response
                if "OK" not in response_text:
                    _LOGGER.warning(
                        f"Unexpected response from {url}: {response_text}"
                    )

                return response_text

        except asyncio.TimeoutError as err:
            raise HomeAssistantError(f"Timeout sending command to {url}: {err}")
        except aiohttp.ClientError as err:
            raise HomeAssistantError(f"Error sending command to {url}: {err}")
        except Exception as err:
            _LOGGER.error(f"Unexpected error sending command to {url}: {err}")
            raise HomeAssistantError(f"Unexpected error sending command to {url}: {err}")
