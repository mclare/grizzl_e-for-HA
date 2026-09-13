"""Constants for the Grizzl-E integration."""

# Integration domain
DOMAIN = "grizzl_e"
DEFAULT_NAME = "Grizzl-E Charger"
MANUFACTURER = "United Chargers"
MODEL = "Grizzl-E Smart"

# Configuration keys
CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_PORTS = "ports"

# Default values
DEFAULT_PORTS = 1
MIN_PORTS = 1
MAX_PORTS = 3

# Default values
DEFAULT_HOST = "192.168.30.133"
DEFAULT_SCAN_INTERVAL = 5

# Timeout values (in seconds)
REQUEST_TIMEOUT = 10  # Total request timeout
CONNECT_TIMEOUT = 5   # Connection timeout
SOCKET_TIMEOUT = 5    # Socket read timeout

# Mapping of logical per-cable measurements to the /main JSON keys used by
# port/cable 1. See port_key() for how the keys for port 2+ are derived.
PORT_FIELD_KEYS = {
    "current": "curMeas1",
    "voltage": "voltMeas1",
    "power": "powerMeas",
    "state": "state",
    "pilot": "pilot",
    "session_time": "sessionTime",
    "session_energy": "sessionEnergy",
    "session_money": "sessionMoney",
    "total_energy": "totalEnergy",
    "session_started": "sessionStarted",
}


def port_key(field: str, port: int) -> str:
    """Return the /main JSON key for a logical per-cable field on a port.

    The Grizzl-E Duo does not report cable 2 through the naive
    ``curMeas2``/``voltMeas2`` fields (those are per-phase measurements and
    stay ``0`` on a single-phase Duo). Instead the second cable's data is
    reported through a mix of fields (see issue #23):

      * current       -> ``curMeas1C2``   (``curMeas1C3`` for a 3rd cable)
      * voltage       -> ``voltMeas1``    (both cables share one circuit, so
                                           voltage is only reported once)
      * everything else -> the port-1 key with the port number appended,
                           e.g. ``powerMeas2``, ``state2``, ``pilot2``,
                           ``sessionTime2`` ...
    """
    base = PORT_FIELD_KEYS[field]
    if port <= 1:
        return base
    if field == "voltage":
        # Both cables share a single circuit; voltage is only reported once.
        return PORT_FIELD_KEYS["voltage"]
    if field == "current":
        return f"curMeas1C{port}"
    return f"{base}{port}"
