"""The Keycloak auth flows and login-form parsing.

HTTP is mocked with the test package's own AiohttpClientMocker (the
`aioclient_mock` fixture), as requirements_test.txt directs for the rare tests
that do not patch the API client itself.
"""

import aiohttp
import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.wiener_netze_smart_meter.api_client import (
    ApiError,
    AuthenticationError,
    WienerNetzeApiClient,
    _asks_password,
    _auth_params,
    _extract_code,
    _find_action_url,
    _same_origin,
)
from custom_components.wiener_netze_smart_meter.const import (
    AUTH_METHOD_COOKIE,
    AUTH_METHOD_PASSWORD,
    AUTHORIZATION_ENDPOINT,
    BEWEGUNGSDATEN_ENDPOINT,
    METER_READING_ENDPOINT,
    REDIRECT_URI,
    TOKEN_ENDPOINT,
)

LOGIN_ACTION = "https://log.wien/auth/realms/logwien/login-actions/authenticate"
USER_STEP_ACTION = f"{LOGIN_ACTION}?execution=user"
PASSWORD_STEP_ACTION = f"{LOGIN_ACTION}?execution=pw"
OTP_STEP_ACTION = f"{LOGIN_ACTION}?execution=otp"
PASSWORD_PAGE_URL = f"{AUTHORIZATION_ENDPOINT}?execution=pw"
APP_REDIRECT_WITH_CODE = f"{REDIRECT_URI}/#state=static-state&code=AUTHCODE"


def _login_page(action: str, password_field: bool = False) -> str:
    """Build a Keycloak login page with one form."""
    field = '<input type="password" id="password">' if password_field else '<input id="username">'
    return f'<html><body><form id="kc-form-login" action="{action}">{field}</form></body></html>'


def _password_client(hass) -> WienerNetzeApiClient:
    """Build a password-method client on the mocked shared session."""
    return WienerNetzeApiClient(
        async_get_clientsession(hass),
        AUTH_METHOD_PASSWORD,
        username="user@example.invalid",
        password="secret",
    )


def _cookie_client(hass) -> WienerNetzeApiClient:
    """Build a cookie-method client on the mocked shared session."""
    return WienerNetzeApiClient(
        async_get_clientsession(hass),
        AUTH_METHOD_COOKIE,
        keycloak_identity="COOKIE",
    )


def _mock_token_exchange(aioclient_mock, token: str = "TOKEN") -> None:
    """Register a successful authorization-code exchange."""
    aioclient_mock.post(TOKEN_ENDPOINT, json={"access_token": token})


async def test_password_auth_walks_the_login_forms(hass, aioclient_mock):
    aioclient_mock.get(PASSWORD_PAGE_URL, text=_login_page(PASSWORD_STEP_ACTION, password_field=True))
    aioclient_mock.get(AUTHORIZATION_ENDPOINT, text=_login_page(USER_STEP_ACTION))
    # The username POST redirects relatively to the password page.
    aioclient_mock.post(
        USER_STEP_ACTION,
        status=302,
        headers={"Location": "/auth/realms/logwien/protocol/openid-connect/auth?execution=pw"},
    )
    aioclient_mock.post(PASSWORD_STEP_ACTION, status=302, headers={"Location": APP_REDIRECT_WITH_CODE})
    _mock_token_exchange(aioclient_mock)

    assert await _password_client(hass).authenticate() == "TOKEN"

    posts = [(str(url), data) for method, url, data, _ in aioclient_mock.mock_calls if method == "POST"]
    login_posts = [(url, data) for url, data in posts if "login-actions" in url]
    assert len(login_posts) == 2, "both login forms were never submitted"
    assert all(data == {"username": "user@example.invalid", "password": "secret"} for _, data in login_posts)
    # The relative redirect was resolved and the password page fetched.
    gets = [str(url) for method, url, _, _ in aioclient_mock.mock_calls if method == "GET"]
    assert any("execution=pw" in url for url in gets)
    # The authorization code reached the token endpoint with the PKCE client_id.
    token_post = next(data for url, data in posts if url == TOKEN_ENDPOINT)
    assert token_post["code"] == "AUTHCODE"
    assert token_post["grant_type"] == "authorization_code"


async def test_password_auth_reuses_an_sso_session(hass, aioclient_mock):
    # Each entry's private session keeps its own SSO session, so the app
    # redirect (and not the login forms) answers the authorization request.
    aioclient_mock.get(AUTHORIZATION_ENDPOINT, status=302, headers={"Location": APP_REDIRECT_WITH_CODE})
    _mock_token_exchange(aioclient_mock)

    assert await _password_client(hass).authenticate() == "TOKEN"
    assert not any("login-actions" in str(url) for _, url, _, _ in aioclient_mock.mock_calls)


async def test_password_auth_rejects_a_wrong_password(hass, aioclient_mock):
    aioclient_mock.get(AUTHORIZATION_ENDPOINT, text=_login_page(USER_STEP_ACTION))
    # Both form submissions re-render their page: the password step shows again.
    aioclient_mock.post(USER_STEP_ACTION, text=_login_page(PASSWORD_STEP_ACTION, password_field=True))
    aioclient_mock.post(PASSWORD_STEP_ACTION, text=_login_page(PASSWORD_STEP_ACTION, password_field=True))

    with pytest.raises(AuthenticationError, match="username or password may be wrong"):
        await _password_client(hass).authenticate()


async def test_password_auth_refuses_to_post_credentials_to_another_host(hass, aioclient_mock):
    aioclient_mock.get(AUTHORIZATION_ENDPOINT, text=_login_page("https://keycloak.example.net/steal"))

    with pytest.raises(AuthenticationError, match="unexpected host"):
        await _password_client(hass).authenticate()

    # No credentials left the building: every request was a GET.
    assert all(method == "GET" for method, _, _, _ in aioclient_mock.mock_calls)


async def test_password_auth_ignores_a_redirect_that_impersonates_the_app(hass, aioclient_mock):
    # startswith(REDIRECT_URI) used to accept this lookalike host.
    evil_redirect = "https://smartmeter-web.wienernetze.at.evil.com/login?code=STOLEN"
    aioclient_mock.get(AUTHORIZATION_ENDPOINT, status=302, headers={"Location": evil_redirect})
    aioclient_mock.get(
        "https://smartmeter-web.wienernetze.at.evil.com/login", text=_login_page("https://evil.example/steal")
    )

    with pytest.raises(AuthenticationError, match="unexpected host"):
        await _password_client(hass).authenticate()


async def test_password_auth_rejects_an_unexpected_extra_login_step(hass, aioclient_mock):
    aioclient_mock.get(AUTHORIZATION_ENDPOINT, text=_login_page(USER_STEP_ACTION))
    aioclient_mock.post(USER_STEP_ACTION, text=_login_page(PASSWORD_STEP_ACTION, password_field=True))
    # After the password step, Keycloak shows an OTP page instead of the app.
    aioclient_mock.post(PASSWORD_STEP_ACTION, text=_login_page(OTP_STEP_ACTION))

    with pytest.raises(AuthenticationError, match="unexpected extra login step"):
        await _password_client(hass).authenticate()


async def test_password_auth_resolves_relative_form_actions(hass, aioclient_mock):
    relative_action = "/auth/realms/logwien/login-actions/authenticate?execution=pw"
    aioclient_mock.get(AUTHORIZATION_ENDPOINT, text=_login_page(relative_action, password_field=True))
    aioclient_mock.post(f"https://log.wien{relative_action}", status=302, headers={"Location": APP_REDIRECT_WITH_CODE})
    _mock_token_exchange(aioclient_mock)

    assert await _password_client(hass).authenticate() == "TOKEN"


async def test_password_auth_reports_redirect_loops(hass, aioclient_mock):
    loop_url = "https://log.wien/auth/realms/logwien/sso-loop"
    aioclient_mock.get(AUTHORIZATION_ENDPOINT, status=302, headers={"Location": loop_url})
    aioclient_mock.get(loop_url, status=302, headers={"Location": loop_url})

    with pytest.raises(AuthenticationError, match="Too many redirects"):
        await _password_client(hass).authenticate()


async def test_password_auth_reports_an_invalid_token_response(hass, aioclient_mock):
    aioclient_mock.get(AUTHORIZATION_ENDPOINT, status=302, headers={"Location": APP_REDIRECT_WITH_CODE})
    aioclient_mock.post(TOKEN_ENDPOINT, text="<html>not json</html>", headers={"content-type": "text/html"})

    with pytest.raises(AuthenticationError, match="Invalid token response"):
        await _password_client(hass).authenticate()


async def test_fetch_bewegungsdaten_reports_invalid_json(hass, aioclient_mock):
    aioclient_mock.get(BEWEGUNGSDATEN_ENDPOINT, text="not json", headers={"content-type": "text/html"})

    with pytest.raises(ApiError, match="Invalid bewegungsdaten response"):
        await _cookie_client(hass).fetch_bewegungsdaten("token", "1", "2", "V002", "von", "bis")


async def test_fetch_meter_reading_reports_invalid_json(hass, aioclient_mock):
    aioclient_mock.get(f"{METER_READING_ENDPOINT}/1/2", text="not json", headers={"content-type": "text/html"})

    with pytest.raises(ApiError, match="Invalid meter reading response"):
        await _cookie_client(hass).fetch_meter_reading("token", "1", "2", "von", "bis")


async def test_password_auth_rejects_an_unknown_username(hass, aioclient_mock):
    aioclient_mock.get(AUTHORIZATION_ENDPOINT, text=_login_page(USER_STEP_ACTION))
    # The username page re-appears without ever asking for a password.
    aioclient_mock.post(USER_STEP_ACTION, text=_login_page(USER_STEP_ACTION))

    with pytest.raises(AuthenticationError, match="username step"):
        await _password_client(hass).authenticate()


async def test_password_auth_fails_without_a_login_form(hass, aioclient_mock):
    aioclient_mock.get(AUTHORIZATION_ENDPOINT, text="<html><body>No form here</body></html>")

    with pytest.raises(AuthenticationError, match="Could not find the login form"):
        await _password_client(hass).authenticate()


async def test_password_auth_fails_when_the_login_page_errors(hass, aioclient_mock):
    aioclient_mock.get(AUTHORIZATION_ENDPOINT, status=503)

    with pytest.raises(AuthenticationError, match="Login page request failed"):
        await _password_client(hass).authenticate()


async def test_password_auth_fails_without_a_code_in_the_redirect(hass, aioclient_mock):
    aioclient_mock.get(AUTHORIZATION_ENDPOINT, status=302, headers={"Location": f"{REDIRECT_URI}/"})

    with pytest.raises(AuthenticationError, match="No authorization code after login"):
        await _password_client(hass).authenticate()


async def test_password_auth_reports_a_failed_token_exchange(hass, aioclient_mock):
    aioclient_mock.get(AUTHORIZATION_ENDPOINT, status=302, headers={"Location": APP_REDIRECT_WITH_CODE})
    aioclient_mock.post(TOKEN_ENDPOINT, status=400, text="invalid_grant")

    with pytest.raises(AuthenticationError, match="Token exchange failed"):
        await _password_client(hass).authenticate()


async def test_password_auth_wraps_connection_errors(hass, aioclient_mock):
    aioclient_mock.get(AUTHORIZATION_ENDPOINT, exc=aiohttp.ClientError("boom"))

    with pytest.raises(AuthenticationError, match="Connection error fetching login page"):
        await _password_client(hass).authenticate()


async def test_cookie_auth_returns_token(hass, aioclient_mock):
    aioclient_mock.get(AUTHORIZATION_ENDPOINT, status=302, headers={"Location": APP_REDIRECT_WITH_CODE})
    _mock_token_exchange(aioclient_mock)

    assert await _cookie_client(hass).authenticate() == "TOKEN"
    # The cookie flow must ask Keycloak not to show a login form.
    assert "prompt=none" in str(aioclient_mock.mock_calls[0][1])


async def test_cookie_auth_fails_without_a_redirect(hass, aioclient_mock):
    aioclient_mock.get(AUTHORIZATION_ENDPOINT, text="<html>login page</html>")

    with pytest.raises(AuthenticationError, match="No redirect from authorization endpoint"):
        await _cookie_client(hass).authenticate()


async def test_cookie_auth_fails_without_a_code_in_the_redirect(hass, aioclient_mock):
    aioclient_mock.get(AUTHORIZATION_ENDPOINT, status=302, headers={"Location": f"{REDIRECT_URI}/#state=static-state"})

    with pytest.raises(AuthenticationError, match="No authorization code in redirect"):
        await _cookie_client(hass).authenticate()


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        ('<form action="https://log.wien/auth">', "https://log.wien/auth"),
        ("<form action='https://log.wien/auth'>", "https://log.wien/auth"),
        # Entity references in the action URL are unescaped.
        ('<form action="https://log.wien/auth?a=1&amp;b=2">', "https://log.wien/auth?a=1&b=2"),
        # The log.wien theme breaks the <form> regex (">" inside an attribute),
        # so the action URL is picked up from the page script instead.
        (
            '<form data-x="a>b"><script>const action = "https://log.wien/login-actions/authenticate?execution=pw&amp;client_id=x";</script></form>',
            "https://log.wien/login-actions/authenticate?execution=pw&client_id=x",
        ),
        # The form regex needs a word boundary: <format ...> is not a form.
        ('<format action="https://log.wien/auth">', None),
        ("<html><body>no form at all</body></html>", None),
    ],
)
def test_find_action_url(page, expected):
    assert _find_action_url(page) == expected


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        ('<input type="password" id="password">', True),
        ("<input type='password' id='password'>", True),
        ('<input id="username">', False),
    ],
)
def test_asks_password(page, expected):
    assert _asks_password(page) is expected


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        (f"{REDIRECT_URI}/#state=x&code=ABC", True),
        (f"{REDIRECT_URI}?code=ABC", True),
        # A lookalike host must not pass an origin check (startswith did).
        ("https://smartmeter-web.wienernetze.at.evil.com/#code=ABC", False),
        ("https://log.wien/auth/realms/logwien", False),
        ("/relative/redirect", False),
        ("", False),
    ],
)
def test_same_origin_recognizes_only_the_app_itself(location, expected):
    assert _same_origin(location, REDIRECT_URI) is expected


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("https://app/#state=x&code=ABC", "ABC"),
        ("https://app/?state=x&code=ABC", "ABC"),
        ("https://app/#state=x", None),
        ("https://app/", None),
    ],
)
def test_extract_code(location, expected):
    assert _extract_code(location) == expected


def test_auth_params_only_the_cookie_flow_asks_for_prompt_none():
    with_prompt = _auth_params("challenge", prompt="none")
    without_prompt = _auth_params("challenge")

    assert with_prompt["prompt"] == "none"
    assert "prompt" not in without_prompt
    assert with_prompt["code_challenge"] == "challenge"
    assert without_prompt["code_challenge"] == "challenge"
