#!/usr/bin/env python3
"""Unofficial client for the Grizzl-E Connect cloud API.

Reverse engineered from the Grizzl-E Connect Android app v1.6.1 (build 205),
a React Native / Hermes app. Everything here talks to United Chargers' cloud
(https://connect-api.unitedchargers.com), not to the charger's local web UI.

Usage examples:
    ./grizzle_connect.py login you@example.com
    ./grizzle_connect.py import-tokens          # Sign in with Apple accounts: paste tokens captured from the app
    ./grizzle_connect.py stations
    ./grizzle_connect.py station <STATION_ID>
    ./grizzle_connect.py mode <STATION_ID> Schedule
    ./grizzle_connect.py current-limit <STATION_ID> 24
    ./grizzle_connect.py schedule-add <STATION_ID> "Off-peak" 23:00 07:00 --days 0-6
    ./grizzle_connect.py schedule-enable <STATION_ID> <SCHEDULE_ID>
    ./grizzle_connect.py schedule-delete <STATION_ID> <SCHEDULE_ID>
    ./grizzle_connect.py raw GET /client/stations
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://connect-api.unitedchargers.com"
APP_VERSION = "v1.6.1 (205)"  # getFullAppVersion(): "v<version> (<versionCode>)"
APP_CLIENT = "Google, Pixel 8, Android 15"  # getAppClient(): "<brand>, <model>, <os> <osVersion>"
APP_NAME = "Grizzl-E Connect"

TOKEN_FILE = Path(os.environ.get("GRIZZLE_TOKEN_FILE", Path.home() / ".config" / "grizzle_connect" / "tokens.json"))

# StationMode enum from the app; sent to POST /client/stations/{id}/mode
STATION_MODES = ("Active", "Inactive", "Schedule")


class GrizzleConnectError(Exception):
    pass


class GrizzleConnect:
    def __init__(self, token: str | None = None, refresh_token: str | None = None, base_url: str = BASE_URL):
        self.base_url = base_url
        self.token = token
        self.refresh_token = refresh_token
        self.session = requests.Session()
        self.session.headers.update({
            "x-app-version": APP_VERSION,
            "x-app-client": APP_CLIENT,
            "x-application-name": APP_NAME,
            "accept": "application/json",
        })

    # --- token persistence -------------------------------------------------

    @classmethod
    def from_token_file(cls, path: Path = TOKEN_FILE) -> "GrizzleConnect":
        if not path.exists():
            raise GrizzleConnectError(f"No saved tokens at {path}; run the 'login' command first")
        data = json.loads(path.read_text())
        return cls(data.get("token"), data.get("refreshToken"))

    def save_tokens(self, path: Path = TOKEN_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"token": self.token, "refreshToken": self.refresh_token}))
        path.chmod(0o600)

    # --- transport ---------------------------------------------------------

    def _send(self, method: str, path: str, body: Any = None, params: dict | None = None) -> requests.Response:
        headers = {"authorization": f"Bearer {self.token}"} if self.token else {}
        return self.session.request(method, self.base_url + path, json=body, params=params, headers=headers, timeout=20)

    def request(self, method: str, path: str, body: Any = None, params: dict | None = None) -> Any:
        """Mirror of the app's baseQuery: on 401, refresh the token once and retry."""
        resp = self._send(method, path, body, params)
        if resp.status_code == 401 and self.token and self.refresh_token:
            self.refresh()
            resp = self._send(method, path, body, params)
        if not resp.ok:
            raise GrizzleConnectError(f"{method} {path} -> HTTP {resp.status_code}: {resp.text[:500]}")
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text

    # --- auth --------------------------------------------------------------

    def login(self, email: str, password: str) -> dict:
        # emailOrPhone is the API's field name; only email sign-in is supported.
        data = self.request("POST", "/client/auth/login", {"emailOrPhone": email, "password": password})
        if isinstance(data, dict) and data.get("isVerified") is False:
            raise GrizzleConnectError("Account is not verified; finish email verification in the app first")
        self._store_credentials(data)
        return data

    def refresh(self) -> dict:
        resp = self.session.post(self.base_url + "/client/auth/refresh-token",
                                 json={"refreshToken": self.refresh_token}, timeout=20)
        if not resp.ok:
            raise GrizzleConnectError(f"Token refresh failed (HTTP {resp.status_code}); log in again")
        data = resp.json()
        self._store_credentials(data)
        return data

    def _store_credentials(self, data: dict) -> None:
        if not isinstance(data, dict) or "token" not in data:
            raise GrizzleConnectError(f"Unexpected auth response: {data!r}")
        self.token = data["token"]
        self.refresh_token = data.get("refreshToken")
        self.save_tokens()

    # --- stations ----------------------------------------------------------

    def get_stations(self) -> Any:
        return self.request("GET", "/client/stations")

    def get_station(self, station_id: str) -> Any:
        return self.request("GET", f"/client/stations/{station_id}")

    def set_mode(self, station_id: str, mode: str, connector_id: int = 0) -> Any:
        """mode: Active (charge now), Inactive (paused), Schedule (follow schedules).

        connector_id is 0 for single-connector chargers, 1..n for each cable on a Duo.
        """
        if mode not in STATION_MODES:
            raise ValueError(f"mode must be one of {STATION_MODES}")
        return self.request("POST", f"/client/stations/{station_id}/mode", {"mode": mode, "connectorId": connector_id})

    def set_current_limit(self, station_id: str, amps: int) -> Any:
        return self.request("PUT", f"/client/stations/{station_id}/currentLimit", {"value": amps})

    def reboot(self, station_id: str) -> Any:
        return self.request("POST", f"/client/stations/{station_id}/reboot", {})

    def get_events(self, station_id: str) -> Any:
        return self.request("GET", f"/client/stations/{station_id}/events")

    # --- schedules (the app stores them as "prices" with isSchedule=True) --

    def update_schedule(self, station_id: str, *, name: str, start: tuple[int, int], end: tuple[int, int],
                        days: list[int], all_day: bool = False, current_limit: int | None = None,
                        connector_id: int = 0, schedule_id: str | None = None) -> Any:
        """Create (schedule_id=None) or update a charging schedule.

        days: 0=Sunday .. 6=Saturday. Times appear to be in the station's local timezone.
        """
        price: dict[str, Any] = {
            "name": name,
            "startHours": 0 if all_day else start[0],
            "startMinutes": 0 if all_day else start[1],
            "endHours": 0 if all_day else end[0],
            "endMinutes": 0 if all_day else end[1],
            "allDay": all_day,
            "days": days,
            "isSchedule": True,
            "currentLimit": current_limit,
            "connectorId": connector_id,
        }
        if schedule_id:
            price["_id"] = schedule_id
        return self.request("POST", f"/client/stations/{station_id}/scheduleUpdate", {"price": price})

    def enable_schedule(self, station_id: str, schedule_id: str, enabled: bool = True) -> Any:
        return self.request("POST", f"/client/stations/{station_id}/scheduleEnable",
                            {"_id": schedule_id, "scheduleEnabled": enabled})

    def delete_schedule(self, station_id: str, schedule_id: str) -> Any:
        return self.request("DELETE", f"/client/stations/{station_id}/scheduleDelete/{schedule_id}")

    # --- electricity rates ("energy plan") ---------------------------------

    def set_base_rate(self, station_id: str, price_per_kwh: float) -> Any:
        return self.request("PUT", f"/client/stations/{station_id}/rate", {"priceKW": price_per_kwh})

    def update_rate_zone(self, station_id: str, *, name: str, price_per_kwh: float, start: tuple[int, int],
                         end: tuple[int, int], days: list[int], all_day: bool = False,
                         summer_price_per_kwh: float | None = None, zone_id: str | None = None) -> Any:
        """Create or update a time-of-use rate zone (e.g. "On-peak 7-11 weekdays")."""
        price: dict[str, Any] = {
            "name": name,
            "priceKW": price_per_kwh,
            "priceKWSummer": summer_price_per_kwh if summer_price_per_kwh is not None else 0,
            "useSeason": summer_price_per_kwh is not None,
            "startHours": 0 if all_day else start[0],
            "startMinutes": 0 if all_day else start[1],
            "endHours": 0 if all_day else end[0],
            "endMinutes": 0 if all_day else end[1],
            "allDay": all_day,
            "days": days,
            "currentLimit": None,
            "connectorId": 0,
        }
        if zone_id:
            price["_id"] = zone_id
        return self.request("POST", f"/client/stations/{station_id}/pricesByZoneUpdate", {"price": price})

    def delete_rate_zone(self, station_id: str, zone_id: str) -> Any:
        return self.request("DELETE", f"/client/stations/{station_id}/pricesByZoneDelete/{zone_id}")


# --- CLI ---------------------------------------------------------------------

def parse_time(value: str) -> tuple[int, int]:
    hours, _, minutes = value.partition(":")
    h, m = int(hours), int(minutes or 0)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise argparse.ArgumentTypeError(f"invalid time {value!r}, expected HH:MM")
    return h, m


def parse_days(value: str) -> list[int]:
    """'0-6', '1,2,3,4,5', or '1-5,0'. 0=Sunday .. 6=Saturday."""
    days: set[int] = set()
    for part in value.split(","):
        lo, _, hi = part.partition("-")
        days.update(range(int(lo), int(hi or lo) + 1))
    if not days <= set(range(7)):
        raise argparse.ArgumentTypeError("days must be between 0 (Sunday) and 6 (Saturday)")
    return sorted(days)


def main() -> None:
    p = argparse.ArgumentParser(description="Unofficial Grizzl-E Connect cloud client")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("login")
    s.add_argument("email")

    sub.add_parser("import-tokens", help="save a token/refreshToken pair captured from the app's traffic")

    sub.add_parser("stations")
    s = sub.add_parser("station")
    s.add_argument("station_id")
    s = sub.add_parser("events")
    s.add_argument("station_id")

    s = sub.add_parser("mode", help="Active = charge now, Inactive = pause, Schedule = follow schedules")
    s.add_argument("station_id")
    s.add_argument("mode", choices=STATION_MODES)
    s.add_argument("--connector", type=int, default=0)

    s = sub.add_parser("current-limit")
    s.add_argument("station_id")
    s.add_argument("amps", type=int)

    for cmd in ("schedule-add", "schedule-update"):
        s = sub.add_parser(cmd)
        s.add_argument("station_id")
        if cmd == "schedule-update":
            s.add_argument("schedule_id")
        s.add_argument("name")
        s.add_argument("start", type=parse_time)
        s.add_argument("end", type=parse_time)
        s.add_argument("--days", type=parse_days, default=list(range(7)), help="e.g. 0-6 or 1-5 (0=Sun)")
        s.add_argument("--all-day", action="store_true")
        s.add_argument("--current-limit", type=int)
        s.add_argument("--connector", type=int, default=0)

    for cmd in ("schedule-enable", "schedule-disable", "schedule-delete"):
        s = sub.add_parser(cmd)
        s.add_argument("station_id")
        s.add_argument("schedule_id")

    s = sub.add_parser("rate", help="set the base electricity price per kWh")
    s.add_argument("station_id")
    s.add_argument("price", type=float)

    s = sub.add_parser("rate-zone-add", help="add a time-of-use price zone")
    s.add_argument("station_id")
    s.add_argument("name")
    s.add_argument("price", type=float)
    s.add_argument("start", type=parse_time)
    s.add_argument("end", type=parse_time)
    s.add_argument("--days", type=parse_days, default=list(range(7)))
    s.add_argument("--summer-price", type=float)

    s = sub.add_parser("rate-zone-delete")
    s.add_argument("station_id")
    s.add_argument("zone_id")

    s = sub.add_parser("raw", help="send an arbitrary authenticated request")
    s.add_argument("method")
    s.add_argument("path")
    s.add_argument("body", nargs="?", help="JSON body")

    args = p.parse_args()

    try:
        if args.cmd == "login":
            client = GrizzleConnect()
            data = client.login(args.email, getpass.getpass("Password: "))
            user = data.get("user") or {}
            print(f"Logged in as {user.get('email') or args.email}; tokens saved to {TOKEN_FILE}")
            return
        if args.cmd == "import-tokens":
            client = GrizzleConnect(getpass.getpass("token: ").strip(), getpass.getpass("refreshToken: ").strip())
            client.save_tokens()
            client.get_stations()  # fails loudly if the tokens don't work
            print(f"Tokens work; saved to {TOKEN_FILE}")
            return

        client = GrizzleConnect.from_token_file()
        if args.cmd == "stations":
            result = client.get_stations()
        elif args.cmd == "station":
            result = client.get_station(args.station_id)
        elif args.cmd == "events":
            result = client.get_events(args.station_id)
        elif args.cmd == "mode":
            result = client.set_mode(args.station_id, args.mode, args.connector)
        elif args.cmd == "current-limit":
            result = client.set_current_limit(args.station_id, args.amps)
        elif args.cmd in ("schedule-add", "schedule-update"):
            result = client.update_schedule(
                args.station_id, name=args.name, start=args.start, end=args.end, days=args.days,
                all_day=args.all_day, current_limit=args.current_limit, connector_id=args.connector,
                schedule_id=getattr(args, "schedule_id", None))
        elif args.cmd == "schedule-enable":
            result = client.enable_schedule(args.station_id, args.schedule_id, True)
        elif args.cmd == "schedule-disable":
            result = client.enable_schedule(args.station_id, args.schedule_id, False)
        elif args.cmd == "schedule-delete":
            result = client.delete_schedule(args.station_id, args.schedule_id)
        elif args.cmd == "rate":
            result = client.set_base_rate(args.station_id, args.price)
        elif args.cmd == "rate-zone-add":
            result = client.update_rate_zone(
                args.station_id, name=args.name, price_per_kwh=args.price, start=args.start, end=args.end,
                days=args.days, summer_price_per_kwh=args.summer_price)
        elif args.cmd == "rate-zone-delete":
            result = client.delete_rate_zone(args.station_id, args.zone_id)
        elif args.cmd == "raw":
            result = client.request(args.method.upper(), args.path, json.loads(args.body) if args.body else None)
        else:
            p.error(f"unknown command {args.cmd}")
            return
    except GrizzleConnectError as err:
        sys.exit(f"error: {err}")

    print(json.dumps(result, indent=2) if not isinstance(result, str) else result)


if __name__ == "__main__":
    main()
