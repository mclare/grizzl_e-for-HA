import aiohttp
import asyncio
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .cloud import is_cloud_entry
from .cloud_api import (
    GrizzleConnectAuthError,
    GrizzleConnectClient,
    GrizzleConnectError,
    GrizzleConnectNotVerifiedError,
    station_id,
)
from .const import (
    CONF_CONNECTION_TYPE,
    CONF_EMAIL,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORTS,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_STATION_ID,
    CONF_TOKEN,
    CONF_USERNAME,
    CONNECT_TIMEOUT,
    CONNECTION_CLOUD,
    DEFAULT_CLOUD_SCAN_INTERVAL,
    DEFAULT_HOST,
    DEFAULT_NAME,
    DEFAULT_PORTS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_CLOUD_SCAN_INTERVAL,
    REQUEST_TIMEOUT,
    SOCKET_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class GrizzleEConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Grizzl-E EV Charger."""

    VERSION = 1

    def __init__(self):
        self._cloud_data = {}
        self._stations = {}
        self._reauth_entry = None

    async def async_step_user(self, user_input=None):
        """Let the user choose between the charger's web interface and the cloud."""
        return self.async_show_menu(
            step_id="user", menu_options=["connection", "cloud"]
        )

    async def async_step_connection(self, user_input=None):
        """Handle the connection step."""
        errors = {}
        if user_input is not None:
            # Test connection before proceeding
            try:
                # Configure session with timeouts
                timeout = aiohttp.ClientTimeout(
                    total=REQUEST_TIMEOUT,
                    connect=CONNECT_TIMEOUT,
                    sock_connect=CONNECT_TIMEOUT,
                    sock_read=SOCKET_TIMEOUT,
                )
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    url = f"http://{user_input[CONF_HOST]}/main"
                    auth = aiohttp.BasicAuth(
                        user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                    )

                    try:
                        # Outer timeout as a safety net
                        async with asyncio.timeout(REQUEST_TIMEOUT + 1):
                            async with session.post(url, auth=auth) as resp:
                                if resp.status == 200:
                                    self._host = user_input[CONF_HOST]
                                    self._username = user_input[CONF_USERNAME]
                                    self._password = user_input[CONF_PASSWORD]
                                    return await self.async_step_ports()
                                if resp.status == 401:
                                    errors["base"] = "invalid_auth"
                                else:
                                    errors["base"] = "cannot_connect"
                    except asyncio.TimeoutError:
                        errors["base"] = "timeout"
                    except aiohttp.ClientError as err:
                        _LOGGER.error("Error connecting to Grizzl-E: %s", err)
                        errors["base"] = "cannot_connect"
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception: %s", err)
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=DEFAULT_HOST): cv.string,
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
            }
        )

        return self.async_show_form(
            step_id="connection",
            data_schema=schema,
            errors=errors,
            description_placeholders={"host": "http://" + DEFAULT_HOST},
        )

    async def async_step_ports(self, user_input=None):
        """Handle the ports configuration step."""
        errors = {}

        if user_input is not None:
            return self.async_create_entry(
                title=DEFAULT_NAME,
                data={
                    CONF_HOST: self._host,
                    CONF_USERNAME: self._username,
                    CONF_PASSWORD: self._password,
                    CONF_PORTS: int(user_input[CONF_PORTS]),
                },
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PORTS,
                    default=str(DEFAULT_PORTS),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value="1", label="1 EVSE port (Standard)"),
                            SelectOptionDict(value="2", label="2 EVSE ports (Duo)"),
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )

        return self.async_show_form(
            step_id="ports",
            data_schema=schema,
            errors=errors,
        )

    # --- Grizzl-E Connect cloud ------------------------------------------------

    async def async_step_cloud(self, user_input=None):
        """Log in to Grizzl-E Connect with email and password."""
        errors = {}
        if user_input is not None:
            client = GrizzleConnectClient(
                async_get_clientsession(self.hass),
                email=user_input[CONF_EMAIL],
                password=user_input[CONF_PASSWORD],
            )
            errors = await self._async_fetch_stations(client)
            if not errors:
                self._cloud_data = {
                    CONF_EMAIL: user_input[CONF_EMAIL],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    CONF_TOKEN: client.token,
                    CONF_REFRESH_TOKEN: client.refresh_token,
                }
                return await self.async_step_station()

        return self.async_show_form(
            step_id="cloud",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_EMAIL): cv.string,
                        vol.Required(CONF_PASSWORD): TextSelector(
                            TextSelectorConfig(type=TextSelectorType.PASSWORD)
                        ),
                    }
                ),
                {CONF_EMAIL: user_input[CONF_EMAIL]} if user_input else {},
            ),
            errors=errors,
        )

    async def _async_fetch_stations(self, client):
        """Fetch the account's stations into ``self._stations``; return form errors."""
        try:
            stations = await client.get_stations()
        except GrizzleConnectNotVerifiedError:
            return {"base": "account_not_verified"}
        except GrizzleConnectAuthError:
            return {"base": "invalid_auth"}
        except GrizzleConnectError as err:
            _LOGGER.error("Error connecting to Grizzl-E Connect: %s", err)
            return {"base": "cannot_connect"}
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception: %s", err)
            return {"base": "unknown"}
        self._stations = {station_id(s): s for s in stations if station_id(s)}
        return {}

    async def async_step_station(self, user_input=None):
        """Pick which charger on the account this entry is for."""
        if not self._stations:
            return self.async_abort(reason="no_stations")
        if user_input is None and len(self._stations) == 1:
            user_input = {CONF_STATION_ID: next(iter(self._stations))}
        if user_input is not None:
            selected = user_input[CONF_STATION_ID]
            station = self._stations[selected]
            await self.async_set_unique_id(selected)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=_station_title(station),
                data={
                    CONF_CONNECTION_TYPE: CONNECTION_CLOUD,
                    CONF_STATION_ID: selected,
                    **self._cloud_data,
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_STATION_ID): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=sid, label=_station_label(station))
                            for sid, station in self._stations.items()
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(step_id="station", data_schema=schema)

    async def async_step_reauth(self, entry_data):
        """Grizzl-E Connect rejected the stored credentials."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._reauth_entry
        errors = {}
        if user_input is not None:
            client = GrizzleConnectClient(
                async_get_clientsession(self.hass),
                email=entry.data[CONF_EMAIL],
                password=user_input[CONF_PASSWORD],
            )
            errors = await self._async_fetch_stations(client)
            if not errors and entry.data[CONF_STATION_ID] not in self._stations:
                errors = {"base": "station_not_found"}
            if not errors:
                data = {
                    **entry.data,
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    CONF_TOKEN: client.token,
                    CONF_REFRESH_TOKEN: client.refresh_token,
                }
                self.hass.config_entries.async_update_entry(entry, data=data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        schema = vol.Schema(
            {
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                )
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders={"account": entry.data[CONF_EMAIL]},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return GrizzleEOptionsFlow(config_entry)


class GrizzleEOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Grizzl-E EV Charger."""

    def __init__(self, config_entry):
        # Kept privately: newer Home Assistant sets ``self.config_entry`` itself
        # and rejects assigning it, older versions don't provide it at all.
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        if is_cloud_entry(self._entry):
            # Don't poll the cloud as fast as a charger on the LAN.
            current = self._entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_CLOUD_SCAN_INTERVAL)
            validator = vol.All(cv.positive_int, vol.Range(min=MIN_CLOUD_SCAN_INTERVAL))
        else:
            current = self._entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            validator = cv.positive_int
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current): validator,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


def _station_title(station):
    return station.get("displayName") or station.get("serialNumber") or DEFAULT_NAME


def _station_label(station):
    serial = station.get("serialNumber") or station.get("identity")
    title = _station_title(station)
    return f"{title} ({serial})" if serial and serial != title else title