"""Constants for the Grizzl-E integration."""

# Integration domain
DOMAIN = "grizzle_e"
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
