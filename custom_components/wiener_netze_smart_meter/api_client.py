"""API client for Wiener Netze Smart Meter."""

import base64
import hashlib
import logging
import os
from urllib.parse import parse_qs, urlparse

import aiohttp

from .const import (
    AUTH_METHOD_COOKIE,
    AUTH_METHOD_PASSWORD,
    AUTHORIZATION_ENDPOINT,
    BEWEGUNGSDATEN_ENDPOINT,
    CLIENT_ID,
    METER_READING_ENDPOINT,
    REDIRECT_URI,
    TOKEN_ENDPOINT,
)

_LOGGER = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when authentication fails."""


class ApiError(Exception):
    """Raised when an API call fails."""


class WienerNetzeApiClient:
    """Client for the Wiener Netze Smart Meter API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        auth_method: str,
        keycloak_identity: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._session = session
        self._auth_method = auth_method
        self._keycloak_identity = keycloak_identity
        self._username = username
        self._password = password

    async def authenticate(self) -> str:
        """Authenticate and return an access token."""
        if self._auth_method == AUTH_METHOD_PASSWORD:
            return await self._authenticate_password()
        return await self._authenticate_cookie()

    async def _authenticate_cookie(self) -> str:
        """Cookie-based PKCE auth flow."""
        code_verifier = _generate_code_verifier()
        code_challenge = _generate_code_challenge(code_verifier)

        # Step 1: Get authorization code
        params = {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "state": "static-state",
            "response_mode": "fragment",
            "response_type": "code",
            "scope": "openid",
            "nonce": "static-nonce",
            "prompt": "none",
            "code_challenge_method": "S256",
            "code_challenge": code_challenge,
        }
        cookies = {"KEYCLOAK_IDENTITY": self._keycloak_identity}

        try:
            resp = await self._session.get(
                AUTHORIZATION_ENDPOINT,
                params=params,
                cookies=cookies,
                allow_redirects=False,
            )
        except aiohttp.ClientError as err:
            raise AuthenticationError(f"Connection error during auth: {err}") from err

        location = resp.headers.get("Location", "")
        if not location:
            _LOGGER.debug(
                "Auth response status=%s, no Location header", resp.status
            )
            raise AuthenticationError(
                "No redirect from authorization endpoint. "
                "The KEYCLOAK_IDENTITY cookie may be expired."
            )

        # Parse code from fragment: ...#...&code=XXXX
        fragment = urlparse(location).fragment
        qs = parse_qs(fragment)
        codes = qs.get("code", [])
        if not codes:
            # Fallback: try query string (some Keycloak configs use query mode)
            codes = parse_qs(urlparse(location).query).get("code", [])
        if not codes:
            _LOGGER.debug("Location header: %s", location)
            raise AuthenticationError(
                "No authorization code in redirect. "
                "The KEYCLOAK_IDENTITY cookie may be expired."
            )
        code = codes[0]

        # Step 2: Exchange code for access token
        token_data = {
            "code": code,
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": code_verifier,
        }

        try:
            resp = await self._session.post(TOKEN_ENDPOINT, data=token_data)
        except aiohttp.ClientError as err:
            raise AuthenticationError(
                f"Connection error during token exchange: {err}"
            ) from err

        if resp.status != 200:
            body = await resp.text()
            _LOGGER.debug("Token exchange failed: status=%s body=%s", resp.status, body)
            raise AuthenticationError(f"Token exchange failed (HTTP {resp.status})")

        data = await resp.json()
        access_token = data.get("access_token")
        if not access_token:
            raise AuthenticationError("No access_token in token response")

        _LOGGER.debug("Authentication successful")
        return access_token

    async def _authenticate_password(self) -> str:
        """Username/password Keycloak password grant."""
        token_data = {
            "username": self._username,
            "password": self._password,
            "grant_type": "password",
            "client_id": CLIENT_ID,
            "scope": "openid",
        }

        try:
            resp = await self._session.post(TOKEN_ENDPOINT, data=token_data)
        except aiohttp.ClientError as err:
            raise AuthenticationError(
                f"Connection error during password auth: {err}"
            ) from err

        if resp.status in (400, 401, 403):
            body = await resp.text()
            _LOGGER.debug("Password auth failed: status=%s body=%s", resp.status, body)
            raise AuthenticationError(
                f"Password authentication failed (HTTP {resp.status}). "
                "The wn-smartmeter client may not support password grant."
            )
        if resp.status != 200:
            raise AuthenticationError(
                f"Password authentication failed (HTTP {resp.status})"
            )

        data = await resp.json()
        access_token = data.get("access_token")
        if not access_token:
            raise AuthenticationError("No access_token in token response")

        _LOGGER.debug("Password authentication successful")
        return access_token

    async def fetch_bewegungsdaten(
        self,
        access_token: str,
        geschaeftspartner: str,
        zaehlpunktnummer: str,
        rolle: str,
        zeitpunkt_von: str,
        zeitpunkt_bis: str,
    ) -> list[dict]:
        """Fetch 15-min interval consumption data."""
        params = {
            "geschaeftspartner": geschaeftspartner,
            "zaehlpunktnummer": zaehlpunktnummer,
            "rolle": rolle,
            "zeitpunktVon": zeitpunkt_von,
            "zeitpunktBis": zeitpunkt_bis,
            "aggregat": "NONE",
        }
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            resp = await self._session.get(
                BEWEGUNGSDATEN_ENDPOINT, params=params, headers=headers
            )
        except aiohttp.ClientError as err:
            raise ApiError(f"Connection error fetching bewegungsdaten: {err}") from err

        if resp.status != 200:
            body = await resp.text()
            _LOGGER.debug(
                "Bewegungsdaten request failed: rolle=%s status=%s body=%s",
                rolle,
                resp.status,
                body,
            )
            raise ApiError(
                f"Bewegungsdaten request failed for {rolle} (HTTP {resp.status})"
            )

        data = await resp.json()
        values = data.get("values", [])
        _LOGGER.debug(
            "Fetched %d values for rolle=%s", len(values), rolle
        )
        return values

    async def fetch_meter_reading(
        self,
        access_token: str,
        geschaeftspartner: str,
        zaehlpunktnummer: str,
        datetime_from: str,
        datetime_to: str,
    ) -> list[dict]:
        """Fetch meter reading (counter) data."""
        url = f"{METER_READING_ENDPOINT}/{geschaeftspartner}/{zaehlpunktnummer}"
        params = {
            "datetimeFrom": datetime_from,
            "datetimeTo": datetime_to,
        }
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            resp = await self._session.get(url, params=params, headers=headers)
        except aiohttp.ClientError as err:
            raise ApiError(f"Connection error fetching meter reading: {err}") from err

        if resp.status != 200:
            body = await resp.text()
            _LOGGER.debug(
                "Meter reading request failed: status=%s body=%s", resp.status, body
            )
            raise ApiError(f"Meter reading request failed (HTTP {resp.status})")

        data = await resp.json()
        try:
            messwerte = data["zaehlwerke"][0]["messwerte"]
        except (KeyError, IndexError):
            _LOGGER.debug("Unexpected meter reading response: %s", data)
            return []

        _LOGGER.debug("Fetched %d meter readings", len(messwerte))
        return messwerte


def _generate_code_verifier() -> str:
    """Generate a PKCE code verifier."""
    return base64.urlsafe_b64encode(os.urandom(64)).decode("utf-8").rstrip("=")


def _generate_code_challenge(verifier: str) -> str:
    """Generate a PKCE code challenge from a verifier."""
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
