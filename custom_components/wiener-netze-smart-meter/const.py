"""Constants for the wiener_netze_smart_meter component."""

DOMAIN = "wiener_netze_smart_meter"
AUTHORIZATION_ENDPOINT = (
    "https://log.wien/auth/realms/logwien/protocol/openid-connect/auth"
)
TOKEN_ENDPOINT = "https://log.wien/auth/realms/logwien/protocol/openid-connect/token"
CLIENT_ID = "wn-smartmeter"
ALLOWED_REDIRECT_URL = "https://smartmeter-web.wienernetze.at"
