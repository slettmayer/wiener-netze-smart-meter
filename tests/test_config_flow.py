"""The user and reauth flows."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.wiener_netze_smart_meter.api_client import AuthenticationError
from custom_components.wiener_netze_smart_meter.const import (
    AUTH_METHOD_COOKIE,
    AUTH_METHOD_PASSWORD,
    CONF_AUTH_METHOD,
    CONF_GESCHAEFTSPARTNER,
    CONF_KEYCLOAK_IDENTITY,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_ZAEHLPUNKTNUMMER,
    DOMAIN,
)

from .conftest import COOKIE_DATA, PASSWORD_DATA, ZAEHLPUNKTNUMMER, make_entry

METER_INPUT = {
    CONF_GESCHAEFTSPARTNER: "1234567890",
    CONF_ZAEHLPUNKTNUMMER: ZAEHLPUNKTNUMMER,
}


def _patch_authenticate(side_effect=None):
    return patch(
        "custom_components.wiener_netze_smart_meter.config_flow.WienerNetzeApiClient.authenticate",
        AsyncMock(return_value="token", side_effect=side_effect),
    )


def _patch_setup():
    return patch("custom_components.wiener_netze_smart_meter.async_setup_entry", return_value=True)


async def _start_user_flow(hass, auth_method):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    return await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_AUTH_METHOD: auth_method})


async def test_user_flow_asks_for_the_auth_method_first(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_cookie_flow_creates_entry(hass):
    result = await _start_user_flow(hass, AUTH_METHOD_COOKIE)
    assert result["step_id"] == "credentials"

    with _patch_authenticate(), _patch_setup():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_KEYCLOAK_IDENTITY: "COOKIE", **METER_INPUT}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Smart Meter 12345678"
    assert result["data"] == {CONF_AUTH_METHOD: AUTH_METHOD_COOKIE, CONF_KEYCLOAK_IDENTITY: "COOKIE", **METER_INPUT}
    assert result["result"].unique_id == ZAEHLPUNKTNUMMER


async def test_password_flow_creates_entry(hass):
    result = await _start_user_flow(hass, AUTH_METHOD_PASSWORD)

    with _patch_authenticate(), _patch_setup():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "user@example.invalid", CONF_PASSWORD: "pw", **METER_INPUT}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_AUTH_METHOD: AUTH_METHOD_PASSWORD,
        CONF_USERNAME: "user@example.invalid",
        CONF_PASSWORD: "pw",
        **METER_INPUT,
    }


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [(AuthenticationError("expired"), "invalid_auth"), (RuntimeError("boom"), "cannot_connect")],
)
async def test_user_flow_shows_validation_errors(hass, side_effect, error):
    result = await _start_user_flow(hass, AUTH_METHOD_COOKIE)

    with _patch_authenticate(side_effect=side_effect):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_KEYCLOAK_IDENTITY: "COOKIE", **METER_INPUT}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_same_meter_cannot_be_added_twice(hass):
    make_entry(COOKIE_DATA).add_to_hass(hass)
    result = await _start_user_flow(hass, AUTH_METHOD_COOKIE)

    with _patch_authenticate():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_KEYCLOAK_IDENTITY: "COOKIE", **METER_INPUT}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_for_a_cookie_entry_only_asks_for_the_cookie(hass):
    entry = make_entry(COOKIE_DATA)
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)

    assert result["step_id"] == "reauth_confirm"
    assert set(result["data_schema"].schema) == {CONF_KEYCLOAK_IDENTITY}
    assert result["description_placeholders"]["zaehlpunktnummer"] == ZAEHLPUNKTNUMMER


async def test_reauth_for_a_password_entry_prefills_the_username(hass):
    entry = make_entry(PASSWORD_DATA)
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)

    assert set(result["data_schema"].schema) == {CONF_USERNAME, CONF_PASSWORD}
    assert result["data_schema"]({CONF_PASSWORD: "x"})[CONF_USERNAME] == "user@example.invalid"


async def test_reauth_updates_the_cookie_and_keeps_the_rest(hass):
    entry = make_entry(COOKIE_DATA)
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)

    with _patch_authenticate(), _patch_setup():
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_KEYCLOAK_IDENTITY: "NEW"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data == {**COOKIE_DATA, CONF_KEYCLOAK_IDENTITY: "NEW"}


async def test_reauth_updates_the_password(hass):
    entry = make_entry(PASSWORD_DATA)
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)

    with _patch_authenticate(), _patch_setup():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "user@example.invalid", CONF_PASSWORD: "new-password"}
        )

    assert result["reason"] == "reauth_successful"
    assert entry.data == {**PASSWORD_DATA, CONF_PASSWORD: "new-password"}


async def test_reauth_validates_the_new_credentials(hass):
    entry = make_entry(COOKIE_DATA)
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)

    with patch(
        "custom_components.wiener_netze_smart_meter.config_flow.WienerNetzeApiClient", autospec=True
    ) as client_cls:
        client_cls.return_value.authenticate.return_value = "token"
        with _patch_setup():
            await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_KEYCLOAK_IDENTITY: "NEW"})

    assert client_cls.call_args.kwargs["auth_method"] == AUTH_METHOD_COOKIE
    assert client_cls.call_args.kwargs["keycloak_identity"] == "NEW"


async def test_reauth_rejects_bad_credentials_and_keeps_the_old_ones(hass):
    entry = make_entry(COOKIE_DATA)
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)

    with _patch_authenticate(side_effect=AuthenticationError("still expired")):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_KEYCLOAK_IDENTITY: "BAD"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data == COOKIE_DATA


async def test_reauth_can_be_retried_after_an_error(hass):
    entry = make_entry(COOKIE_DATA)
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)

    with _patch_authenticate(side_effect=AuthenticationError("still expired")):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_KEYCLOAK_IDENTITY: "BAD"})
    with _patch_authenticate(), _patch_setup():
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_KEYCLOAK_IDENTITY: "NEW"})

    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_KEYCLOAK_IDENTITY] == "NEW"


async def test_reauth_reloads_the_entry_exactly_once(hass):
    """The flow owns the reload: the entry has no update listener that would do it.

    Without a reload the running coordinator keeps the expired credentials in its
    API client, so the next fetch would fail again despite the successful reauth.
    """
    entry = make_entry(COOKIE_DATA)
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)

    with (
        _patch_authenticate(),
        patch.object(hass.config_entries, "async_schedule_reload") as scheduled,
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_KEYCLOAK_IDENTITY: "NEW"})

    assert result["reason"] == "reauth_successful"
    scheduled.assert_called_once_with(entry.entry_id)
