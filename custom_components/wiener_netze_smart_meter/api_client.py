"""API client for Wiener Netze Smart Meter."""

import base64
import contextlib
import hashlib
import html
import logging
import os
import re
from urllib.parse import parse_qs, urljoin, urlparse

import aiohttp

from .const import (
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
        params = _auth_params(code_challenge, prompt="none")
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
        await resp.read()  # the auth response body is never needed; free its connection
        if not location:
            _LOGGER.debug("Auth response status=%s, no Location header", resp.status)
            raise AuthenticationError(
                "No redirect from authorization endpoint. The KEYCLOAK_IDENTITY cookie may be expired."
            )

        code = _extract_code(location)
        if not code:
            _LOGGER.debug("Location header: %s", location)
            raise AuthenticationError("No authorization code in redirect. The KEYCLOAK_IDENTITY cookie may be expired.")

        # Step 2: Exchange code for access token
        return await self._exchange_code_for_token(code, code_verifier)

    async def close(self) -> None:
        """Close the underlying HTTP session (owned by this client's config entry)."""
        await self._session.close()

    async def _release(self, resp: aiohttp.ClientResponse) -> None:
        """Consume a response's body to return its connection to the pool; never raises."""
        with contextlib.suppress(aiohttp.ClientError):
            await resp.read()

    async def _authenticate_password(self) -> str:
        """Username/password auth via the Keycloak login form (authorization code + PKCE)."""
        # Keycloak rejects the direct password grant for this client
        # ("unauthorized_client" / "Client not allowed for direct access grants"),
        # so we script the browser login instead and reuse the code flow.
        code_verifier = _generate_code_verifier()
        params = _auth_params(_generate_code_challenge(code_verifier))

        # Step 1: Fetch the login page. An SSO session from a previous login
        # (this entry's own -- every config entry gets a private session) skips
        # the form and redirects straight to the app.
        try:
            resp = await self._session.get(AUTHORIZATION_ENDPOINT, params=params, allow_redirects=False)
        except aiohttp.ClientError as err:
            raise AuthenticationError(f"Connection error fetching login page: {err}") from err
        resp, location = await self._follow_redirects(resp, "fetching login page")

        # Step 2: Walk the login forms until Keycloak redirects to the app.
        if _same_origin(location, REDIRECT_URI):
            await resp.read()  # the app-redirect response carries no body we need
        else:
            location = await self._submit_login_forms(resp)

        # Step 3: Exchange the authorization code for an access token.
        code = _extract_code(location)
        if not code:
            _LOGGER.debug("Login redirect without code: %s", location)
            raise AuthenticationError("No authorization code after login.")
        return await self._exchange_code_for_token(code, code_verifier)

    async def _submit_login_forms(self, resp: aiohttp.ClientResponse) -> str:
        """Submit the login forms until Keycloak redirects to the app; return the redirect Location."""
        # log.wien logs in identity-first: a username page, then a password
        # page, each carrying a fresh form action URL. A page re-appearing
        # after we submitted to it means the credentials were rejected.
        #
        # The walk always ends within three pages -- username, password, then
        # the app redirect or a page that fails a check below -- so the loop
        # cannot run away.
        submitted_step: str | None = None
        while True:
            if resp.status != 200:
                await self._release(resp)
                raise AuthenticationError(f"Login page request failed (HTTP {resp.status})")
            page = await resp.text()
            action_url = _find_action_url(page)
            if not action_url:
                _LOGGER.debug("No login form found; page starts with: %s", page[:500])
                raise AuthenticationError("Could not find the login form on the Keycloak login page.")
            if not action_url.startswith("http"):
                action_url = urljoin(str(resp.url), action_url)
            if not _same_origin(action_url, AUTHORIZATION_ENDPOINT):
                # Never post credentials to a host the login page should not talk to.
                _LOGGER.debug("Refusing to post credentials to %s", action_url)
                raise AuthenticationError("The Keycloak login form points at an unexpected host.")
            page_step = "password" if _asks_password(page) else "username"
            if page_step == submitted_step:
                # The page we just submitted to re-appeared: credentials rejected.
                # (Its body is not logged: Keycloak pre-fills the username there.)
                if page_step == "username":
                    raise AuthenticationError(
                        "Login failed at the username step. The account may not exist "
                        "or may use a different login method (e.g. Google or Apple)."
                    )
                raise AuthenticationError("Login failed. The username or password may be wrong.")
            if submitted_step == "password":
                # The password step was accepted, yet another form appeared.
                raise AuthenticationError(
                    "Login failed: an unexpected extra login step appeared (e.g. OTP or consent)."
                )
            submitted_step = page_step
            resp = await self._post_credentials(action_url)
            resp, location = await self._follow_redirects(resp, "during login")
            if _same_origin(location, REDIRECT_URI):
                await resp.read()  # the app-redirect response carries no body we need
                return location

    async def _follow_redirects(self, resp: aiohttp.ClientResponse, context: str) -> tuple[aiohttp.ClientResponse, str]:
        """Follow Keycloak-internal redirects; stop at the app redirect."""
        location = resp.headers.get("Location", "")
        for _ in range(10):
            if not location or _same_origin(location, REDIRECT_URI):
                return resp, location
            if not location.startswith("http"):
                location = urljoin(str(resp.url), location)
            try:
                next_resp = await self._session.get(location, allow_redirects=False)
            except aiohttp.ClientError as err:
                raise AuthenticationError(f"Connection error {context}: {err}") from err
            await resp.read()  # the hop is consumed; return its connection to the pool
            resp = next_resp
            location = resp.headers.get("Location", "")
        await self._release(resp)
        raise AuthenticationError(f"Too many redirects {context}.")

    async def _post_credentials(self, action_url: str) -> aiohttp.ClientResponse:
        """POST username and password to a Keycloak login form action URL."""
        try:
            return await self._session.post(
                action_url,
                data={"username": self._username, "password": self._password},
                allow_redirects=False,
            )
        except aiohttp.ClientError as err:
            raise AuthenticationError(f"Connection error during login: {err}") from err

    async def _exchange_code_for_token(self, code: str, code_verifier: str) -> str:
        """Exchange an authorization code for an access token."""
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
            raise AuthenticationError(f"Connection error during token exchange: {err}") from err

        if resp.status != 200:
            body = await resp.text()
            _LOGGER.debug("Token exchange failed: status=%s body=%s", resp.status, body)
            raise AuthenticationError(f"Token exchange failed (HTTP {resp.status})")

        try:
            data = await resp.json()
        except (aiohttp.ClientError, ValueError) as err:
            # ClientError covers ContentTypeError, ValueError covers invalid JSON
            await self._release(resp)
            raise AuthenticationError(f"Invalid token response: {err}") from err
        access_token = data.get("access_token") if isinstance(data, dict) else None
        if not access_token:
            raise AuthenticationError("No access_token in token response")

        _LOGGER.debug("Authentication successful")
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
            # Newly required by the API (HTTP 400 "Required parameter 'wandler' is
            # not present" otherwise). Standard household meters are direct-measurement,
            # not transformer (Wandler) meters, so this is always false.
            "wandler": "false",
        }
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        try:
            resp = await self._session.get(BEWEGUNGSDATEN_ENDPOINT, params=params, headers=headers)
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
            raise ApiError(f"Bewegungsdaten request failed for {rolle} (HTTP {resp.status}): {body[:300]}")

        try:
            data = await resp.json()
        except (aiohttp.ClientError, ValueError) as err:
            await self._release(resp)
            raise ApiError(f"Invalid bewegungsdaten response for {rolle}: {err}") from err
        values = data.get("values", [])
        _LOGGER.debug("Fetched %d values for rolle=%s", len(values), rolle)
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
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        try:
            resp = await self._session.get(url, params=params, headers=headers)
        except aiohttp.ClientError as err:
            raise ApiError(f"Connection error fetching meter reading: {err}") from err

        if resp.status != 200:
            body = await resp.text()
            _LOGGER.debug("Meter reading request failed: status=%s body=%s", resp.status, body)
            raise ApiError(f"Meter reading request failed (HTTP {resp.status}): {body[:300]}")

        try:
            data = await resp.json()
        except (aiohttp.ClientError, ValueError) as err:
            await self._release(resp)
            raise ApiError(f"Invalid meter reading response: {err}") from err
        try:
            messwerte = data["zaehlwerke"][0]["messwerte"]
        except (KeyError, IndexError):
            _LOGGER.debug("Unexpected meter reading response: %s", data)
            return []

        _LOGGER.debug("Fetched %d meter readings", len(messwerte))
        return messwerte


def _auth_params(code_challenge: str, prompt: str | None = None) -> dict:
    """Build the authorization-endpoint params shared by both auth flows."""
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "state": "static-state",
        "response_mode": "fragment",
        "response_type": "code",
        "scope": "openid",
        "nonce": "static-nonce",
        "code_challenge_method": "S256",
        "code_challenge": code_challenge,
    }
    # prompt=none keeps the cookie flow form-free; the password flow sends no
    # prompt so it can reuse its own (per-entry) SSO session.
    if prompt:
        params["prompt"] = prompt
    return params


def _find_action_url(page: str) -> str | None:
    """Extract the login form action URL from a Keycloak login page."""
    # Stock Keycloak themes carry the action on the <form> tag. The log.wien
    # theme is JS-rendered and its <form> tag contains ">" inside attribute
    # values, so we fall back to the action URL embedded in the page script.
    match = re.search(r'<form\b[^>]+action=["\']([^"\']+)["\']', page)
    if not match:
        match = re.search(r'(https?://[^"\'\s<>]+login-actions/authenticate[^"\'\s<>]*)', page)
    if not match:
        return None
    return html.unescape(match.group(1))


def _same_origin(url: str, other: str) -> bool:
    """Check whether two URLs share scheme and host (including port)."""
    parsed, reference = urlparse(url), urlparse(other)
    return (parsed.scheme, parsed.netloc.lower()) == (reference.scheme, reference.netloc.lower())


def _asks_password(page: str) -> bool:
    """Check whether a Keycloak login page asks for a password."""
    # Both quote styles, to match the tolerance of _find_action_url
    return re.search(r'type=["\']password["\']', page) is not None


def _extract_code(location: str) -> str | None:
    """Extract the authorization code from a redirect URL, if present."""
    # Fragment first (...#...&code=XXXX), query string as fallback
    codes = parse_qs(urlparse(location).fragment).get("code", [])
    if not codes:
        codes = parse_qs(urlparse(location).query).get("code", [])
    return codes[0] if codes else None


def _generate_code_verifier() -> str:
    """Generate a PKCE code verifier."""
    return base64.urlsafe_b64encode(os.urandom(64)).decode("utf-8").rstrip("=")


def _generate_code_challenge(verifier: str) -> str:
    """Generate a PKCE code challenge from a verifier."""
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
