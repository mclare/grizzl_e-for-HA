"""Async client for the Grizzl-E Connect cloud API.

An asyncio port of grizzle_connect.py (reverse engineered from the Grizzl-E
Connect Android app v1.6.1). It talks to United Chargers' cloud
(https://connect-api.unitedchargers.com), not to the charger's local web UI.
The API is undocumented and may change without notice.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://connect-api.unitedchargers.com"
# Same identification headers the app sends; see grizzle_connect.py.
APP_VERSION = "v1.6.1 (205)"
APP_CLIENT = "Google, Pixel 8, Android 15"
APP_NAME = "Grizzl-E Connect"

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)

# StationMode enum from the app; sent to POST /client/stations/{id}/mode
STATION_MODES = ("Active", "Inactive", "Schedule")

TokenCallback = Callable[[str, "str | None"], None]


class GrizzleConnectError(Exception):
    """Any error talking to the Grizzl-E Connect cloud."""


class GrizzleConnectConnectionError(GrizzleConnectError):
    """The cloud couldn't be reached or returned a server error."""


class GrizzleConnectAuthError(GrizzleConnectError):
    """The credentials or tokens were rejected."""


class GrizzleConnectNotVerifiedError(GrizzleConnectAuthError):
    """The account's email address hasn't been verified in the app yet."""


def station_id(station: dict[str, Any]) -> str | None:
    """Return the id used in /client/stations/{id} URLs."""
    return station.get("id") or station.get("_id")


class GrizzleConnectClient:
    """Grizzl-E Connect API client.

    Authenticates with email and password. ``on_tokens_updated`` is called whenever new tokens are issued
    so they can be persisted.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        email: str | None = None,
        password: str | None = None,
        token: str | None = None,
        refresh_token: str | None = None,
        on_tokens_updated: TokenCallback | None = None,
        base_url: str = BASE_URL,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self.token = token
        self.refresh_token = refresh_token
        self._on_tokens_updated = on_tokens_updated
        self._base_url = base_url
        self._auth_lock = asyncio.Lock()

    # --- transport ---------------------------------------------------------

    async def _send(
        self, method: str, path: str, body: Any = None, *, authenticated: bool = True
    ) -> tuple[int, Any]:
        headers = {
            "x-app-version": APP_VERSION,
            "x-app-client": APP_CLIENT,
            "x-application-name": APP_NAME,
            "accept": "application/json",
        }
        if authenticated and self.token:
            headers["authorization"] = f"Bearer {self.token}"
        try:
            async with self._session.request(
                method,
                self._base_url + path,
                json=body,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                text = await resp.text()
                status = resp.status
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise GrizzleConnectConnectionError(f"{method} {path} failed: {err}") from err
        if not text:
            return status, None
        try:
            return status, json.loads(text)
        except ValueError:
            return status, text

    async def request(self, method: str, path: str, body: Any = None) -> Any:
        """Send an authenticated request.

        Mirrors the app's baseQuery: on 401, refresh the token once and retry.
        If the refresh token is rejected too, log in again when a password is known.
        """
        if not self.token:
            await self.login()
        token_used = self.token
        status, data = await self._send(method, path, body)
        if status == 401:
            await self._reauthenticate(token_used)
            status, data = await self._send(method, path, body)
            if status == 401:
                raise GrizzleConnectAuthError(f"{method} {path} was rejected after re-authenticating")
        if status >= 500:
            raise GrizzleConnectConnectionError(f"{method} {path} -> HTTP {status}")
        if status >= 400:
            message = data.get("message") if isinstance(data, dict) else data
            raise GrizzleConnectError(f"{method} {path} -> HTTP {status}: {str(message)[:500]}")
        return data

    # --- auth --------------------------------------------------------------

    async def login(self) -> dict[str, Any]:
        """Log in with the email and password."""
        if not self._email or not self._password:
            raise GrizzleConnectAuthError("No email and password to log in with")
        status, data = await self._send(
            "POST",
            "/client/auth/login",
            # emailOrPhone is the API's field name; only email sign-in is supported.
            {"emailOrPhone": self._email, "password": self._password},
            authenticated=False,
        )
        if status >= 500 or status in (408, 429):
            raise GrizzleConnectConnectionError(f"Login failed: HTTP {status}")
        if status >= 400:
            raise GrizzleConnectAuthError(f"Login rejected: HTTP {status}")
        if isinstance(data, dict) and data.get("isVerified") is False:
            raise GrizzleConnectNotVerifiedError(
                "Account is not verified; finish email verification in the app first"
            )
        self._store_credentials(data)
        return data

    async def refresh(self) -> dict[str, Any]:
        """Exchange the refresh token for a new token pair."""
        if not self.refresh_token:
            raise GrizzleConnectAuthError("No refresh token")
        status, data = await self._send(
            "POST",
            "/client/auth/refresh-token",
            {"refreshToken": self.refresh_token},
            authenticated=False,
        )
        if status >= 500 or status in (408, 429):
            raise GrizzleConnectConnectionError(f"Token refresh failed: HTTP {status}")
        if status >= 400:
            raise GrizzleConnectAuthError(f"Token refresh rejected: HTTP {status}")
        self._store_credentials(data)
        return data

    async def _reauthenticate(self, expired_token: str | None) -> None:
        async with self._auth_lock:
            if self.token != expired_token:
                return  # another request already got a new token
            if self.refresh_token:
                try:
                    await self.refresh()
                    return
                except GrizzleConnectAuthError:
                    _LOGGER.debug("Refresh token rejected, logging in again")
            await self.login()

    def _store_credentials(self, data: Any) -> None:
        if not isinstance(data, dict) or not data.get("token"):
            raise GrizzleConnectError("Unexpected auth response from Grizzl-E Connect")
        self.token = data["token"]
        self.refresh_token = data.get("refreshToken")
        if self._on_tokens_updated:
            self._on_tokens_updated(self.token, self.refresh_token)

    # --- stations ----------------------------------------------------------

    async def get_stations(self) -> list[dict[str, Any]]:
        """Return every station on the account, with live connector status."""
        data = await self.request("GET", "/client/stations")
        if isinstance(data, dict):
            data = data.get("stations")
        if not isinstance(data, list):
            raise GrizzleConnectError("Unexpected response from GET /client/stations")
        return [station for station in data if isinstance(station, dict)]

    async def set_mode(self, station: str, mode: str, connector_id: int = 0) -> Any:
        """mode: Active (charge now), Inactive (paused), Schedule (follow schedules).

        connector_id is 0 for single-connector chargers, 1..n for each cable on a Duo.
        """
        if mode not in STATION_MODES:
            raise ValueError(f"mode must be one of {STATION_MODES}")
        return await self.request(
            "POST", f"/client/stations/{station}/mode", {"mode": mode, "connectorId": connector_id}
        )

    async def set_current_limit(self, station: str, amps: int) -> Any:
        return await self.request("PUT", f"/client/stations/{station}/currentLimit", {"value": amps})

    async def reboot(self, station: str) -> Any:
        return await self.request("POST", f"/client/stations/{station}/reboot", {})

    # --- schedules (stored in pricesByZone with isSchedule=True) -----------

    async def update_schedule(
        self,
        station: str,
        *,
        name: str,
        start: tuple[int, int],
        end: tuple[int, int],
        days: list[int],
        all_day: bool = False,
        current_limit: int | None = None,
        connector_id: int = 0,
        schedule_id: str | None = None,
        base: dict[str, Any] | None = None,
    ) -> Any:
        """Create (schedule_id=None) or update a charging schedule.

        days: 0=Sunday .. 6=Saturday. Times are in the station's local timezone.
        ``base`` is the existing schedule; fields this method doesn't set are kept.
        """
        price: dict[str, Any] = dict(base or {})
        price.update(
            name=name,
            startHours=0 if all_day else start[0],
            startMinutes=0 if all_day else start[1],
            endHours=0 if all_day else end[0],
            endMinutes=0 if all_day else end[1],
            allDay=all_day,
            days=days,
            isSchedule=True,
            currentLimit=current_limit,
            connectorId=connector_id,
        )
        price.pop("_id", None)
        if schedule_id:
            price["_id"] = schedule_id
        return await self.request(
            "POST", f"/client/stations/{station}/scheduleUpdate", {"price": price}
        )

    async def enable_schedule(self, station: str, schedule_id: str, enabled: bool = True) -> Any:
        """Turn a schedule or rate zone on or off as a charging window."""
        return await self.request(
            "POST",
            f"/client/stations/{station}/scheduleEnable",
            {"_id": schedule_id, "scheduleEnabled": enabled},
        )

    async def delete_schedule(self, station: str, schedule_id: str) -> Any:
        return await self.request(
            "DELETE", f"/client/stations/{station}/scheduleDelete/{schedule_id}"
        )

    # --- electricity rates ("energy plan") ---------------------------------

    async def set_base_rate(self, station: str, price_per_kwh: float) -> Any:
        return await self.request(
            "PUT", f"/client/stations/{station}/rate", {"priceKW": price_per_kwh}
        )

    async def update_rate_zone(
        self,
        station: str,
        *,
        name: str,
        price_per_kwh: float,
        start: tuple[int, int],
        end: tuple[int, int],
        days: list[int],
        all_day: bool = False,
        summer_price_per_kwh: float | None = None,
        zone_id: str | None = None,
        base: dict[str, Any] | None = None,
    ) -> Any:
        """Create or update a time-of-use rate zone (e.g. "On-peak 7-11 weekdays").

        ``base`` is the existing zone; fields this method doesn't set (such as a
        second time window) are kept. When updating without a summer price the
        zone's seasonal setting is left as it is.
        """
        price: dict[str, Any] = dict(base or {})
        price.update(
            name=name,
            priceKW=price_per_kwh,
            startHours=0 if all_day else start[0],
            startMinutes=0 if all_day else start[1],
            endHours=0 if all_day else end[0],
            endMinutes=0 if all_day else end[1],
            allDay=all_day,
            days=days,
        )
        if summer_price_per_kwh is not None:
            price.update(priceKWSummer=summer_price_per_kwh, useSeason=True)
        else:
            price.setdefault("priceKWSummer", 0)
            price.setdefault("useSeason", False)
        price.setdefault("currentLimit", None)
        price.setdefault("connectorId", 0)
        price.pop("_id", None)
        if zone_id:
            price["_id"] = zone_id
        return await self.request(
            "POST", f"/client/stations/{station}/pricesByZoneUpdate", {"price": price}
        )

    async def delete_rate_zone(self, station: str, zone_id: str) -> Any:
        return await self.request(
            "DELETE", f"/client/stations/{station}/pricesByZoneDelete/{zone_id}"
        )
