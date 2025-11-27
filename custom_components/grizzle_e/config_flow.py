import aiohttp
import asyncio
import async_timeout
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORTS,
    CONF_USERNAME,
    DEFAULT_PORTS,
    DOMAIN,
    MIN_PORTS,
    MAX_PORTS,
    REQUEST_TIMEOUT,
    CONNECT_TIMEOUT,
    SOCKET_TIMEOUT,
    DEFAULT_HOST, DEFAULT_NAME
)

import logging
_LOGGER = logging.getLogger(__name__)


class GrizzleEConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Grizzl-E EV Charger."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        return await self.async_step_connection()

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
                    sock_read=SOCKET_TIMEOUT
                )
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    url = f"http://{user_input[CONF_HOST]}/main"
                    auth = aiohttp.BasicAuth(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
                    
                    try:
                        # Outer timeout as a safety net
                        async with async_timeout.timeout(REQUEST_TIMEOUT + 1):
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
            description_placeholders={"host": "http://" + DEFAULT_HOST}
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
                    CONF_PORTS: user_input[CONF_PORTS]
                },
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PORTS,
                    default=DEFAULT_PORTS,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_PORTS, max=MAX_PORTS)
                )
            }
        )
        
        return self.async_show_form(
            step_id="ports",
            data_schema=schema,
            errors=errors,
            description_placeholders={"min_ports": str(MIN_PORTS), "max_ports": str(MAX_PORTS)}
        )

    @callback
    def async_get_options_flow(config_entry):
        return GrizzleEOptionsFlow(config_entry)


class GrizzleEOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Grizzl-E EV Charger."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Required("scan_interval", default=10): cv.positive_int,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
