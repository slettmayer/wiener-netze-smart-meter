"""Shared fixtures."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

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

ZAEHLPUNKTNUMMER = "AT0010000000000000001000012345678"

COOKIE_DATA = {
    CONF_AUTH_METHOD: AUTH_METHOD_COOKIE,
    CONF_GESCHAEFTSPARTNER: "1234567890",
    CONF_ZAEHLPUNKTNUMMER: ZAEHLPUNKTNUMMER,
    CONF_KEYCLOAK_IDENTITY: "OLD-COOKIE",
}

PASSWORD_DATA = {
    CONF_AUTH_METHOD: AUTH_METHOD_PASSWORD,
    CONF_GESCHAEFTSPARTNER: "1234567890",
    CONF_ZAEHLPUNKTNUMMER: ZAEHLPUNKTNUMMER,
    CONF_USERNAME: "user@example.invalid",
    CONF_PASSWORD: "old-password",
}


@pytest.fixture(autouse=True)
def mock_recorder_before_hass(async_test_recorder):
    """Prepare the recorder database before the hass fixture starts.

    The manifest depends on `recorder`, so every test that sets the integration
    up -- including a config flow creating its entry -- needs one, and the
    database fixture refuses to run once hass is already up.
    """


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """Let Home Assistant load the integration from custom_components/, with a recorder."""
    return


def make_entry(data: dict) -> MockConfigEntry:
    """Build a config entry the way the user flow would have created it."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=data[CONF_ZAEHLPUNKTNUMMER],
        title=f"Smart Meter {data[CONF_ZAEHLPUNKTNUMMER][-8:]}",
        data=data,
    )
