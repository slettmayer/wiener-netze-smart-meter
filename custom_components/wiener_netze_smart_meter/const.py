"""Constants for the Wiener Netze Smart Meter integration."""

DOMAIN = "wiener_netze_smart_meter"

# Keycloak OIDC endpoints
AUTHORIZATION_ENDPOINT = (
    "https://log.wien/auth/realms/logwien/protocol/openid-connect/auth"
)
TOKEN_ENDPOINT = (
    "https://log.wien/auth/realms/logwien/protocol/openid-connect/token"
)
CLIENT_ID = "wn-smartmeter"
REDIRECT_URI = "https://smartmeter-web.wienernetze.at"

# Smart Meter API
API_BASE_URL = "https://service.wienernetze.at/sm/api"
BEWEGUNGSDATEN_ENDPOINT = f"{API_BASE_URL}/user/messwerte/bewegungsdaten"
METER_READING_ENDPOINT = f"{API_BASE_URL}/user/messwerte/meterReading"

# Data roles
ROLLE_TOTAL = "V002"  # Gesamtverbrauch (total consumption)
ROLLE_GRID = "G001"  # Restnetzbezug (grid consumption)
ROLLE_PV = "G003"  # Eigendeckung (PV self-consumption)

ROLES = [ROLLE_TOTAL, ROLLE_GRID, ROLLE_PV]

ROLE_NAMES = {
    ROLLE_TOTAL: "total",
    ROLLE_GRID: "grid",
    ROLLE_PV: "pv",
}

# Auth methods
AUTH_METHOD_COOKIE = "cookie"
AUTH_METHOD_PASSWORD = "password"

# Config keys
CONF_AUTH_METHOD = "auth_method"
CONF_KEYCLOAK_IDENTITY = "keycloak_identity"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_GESCHAEFTSPARTNER = "geschaeftspartner"
CONF_ZAEHLPUNKTNUMMER = "zaehlpunktnummer"

# Defaults
DEFAULT_FETCH_DAYS = 7

# Service
SERVICE_FETCH_DATA = "fetch_data"
SERVICE_ATTR_DAYS = "days"
