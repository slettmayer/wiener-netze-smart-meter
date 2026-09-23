"""Config flow for Wiener Netze Smart Meter."""

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api_client import AuthenticationError, WienerNetzeApiClient
from .const import (
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

_LOGGER = logging.getLogger(__name__)


class WienerNetzeSmartMeterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Wiener Netze Smart Meter."""

    VERSION = 1

    def __init__(self) -> None:
        self._auth_method: str | None = None

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Step 1: Choose auth method."""
        if user_input is not None:
            self._auth_method = user_input[CONF_AUTH_METHOD]
            return await self.async_step_credentials()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_AUTH_METHOD, default=AUTH_METHOD_COOKIE): vol.In(
                        {
                            AUTH_METHOD_COOKIE: "KEYCLOAK_IDENTITY Cookie",
                            AUTH_METHOD_PASSWORD: "Username & Password",
                        }
                    ),
                }
            ),
        )

    async def async_step_credentials(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Step 2: Enter credentials and meter details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Build full config data
            data = {
                CONF_AUTH_METHOD: self._auth_method,
                CONF_GESCHAEFTSPARTNER: user_input[CONF_GESCHAEFTSPARTNER],
                CONF_ZAEHLPUNKTNUMMER: user_input[CONF_ZAEHLPUNKTNUMMER],
                **_credentials(self._auth_method, user_input),
            }

            error = await self._async_validate(data)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(data[CONF_ZAEHLPUNKTNUMMER])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Smart Meter {data[CONF_ZAEHLPUNKTNUMMER][-8:]}",
                    data=data,
                )

        schema_fields = _credentials_schema(self._auth_method)
        schema_fields[vol.Required(CONF_GESCHAEFTSPARTNER)] = str
        schema_fields[vol.Required(CONF_ZAEHLPUNKTNUMMER)] = str

        return self.async_show_form(
            step_id="credentials",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start reauth when the stored credentials stop authenticating."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Ask again for the credentials of the entry's auth method only."""
        entry = self._get_reauth_entry()
        auth_method = entry.data[CONF_AUTH_METHOD]
        errors: dict[str, str] = {}

        if user_input is not None:
            credentials = _credentials(auth_method, user_input)
            error = await self._async_validate({**entry.data, **credentials})
            if error:
                errors["base"] = error
            else:
                # The entry has no update listener, so the flow owns the reload.
                return self.async_update_reload_and_abort(entry, data_updates=credentials)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(_credentials_schema(auth_method, entry.data.get(CONF_USERNAME))),
            errors=errors,
            description_placeholders={"zaehlpunktnummer": entry.data[CONF_ZAEHLPUNKTNUMMER]},
        )

    async def _async_validate(self, data: Mapping[str, Any]) -> str | None:
        """Authenticate with the given config data; return a form error key or None."""
        client = WienerNetzeApiClient(
            async_get_clientsession(self.hass),
            auth_method=data[CONF_AUTH_METHOD],
            keycloak_identity=data.get(CONF_KEYCLOAK_IDENTITY),
            username=data.get(CONF_USERNAME),
            password=data.get(CONF_PASSWORD),
        )
        try:
            await client.authenticate()
        except AuthenticationError:
            return "invalid_auth"
        except Exception:
            _LOGGER.exception("Unexpected error during config validation")
            return "cannot_connect"
        return None


def _credentials(auth_method: str | None, user_input: Mapping[str, Any]) -> dict[str, str]:
    """Pick the credential fields of the given auth method out of form input."""
    if auth_method == AUTH_METHOD_COOKIE:
        return {CONF_KEYCLOAK_IDENTITY: user_input[CONF_KEYCLOAK_IDENTITY]}
    return {CONF_USERNAME: user_input[CONF_USERNAME], CONF_PASSWORD: user_input[CONF_PASSWORD]}


def _credentials_schema(auth_method: str | None, username: str | None = None) -> dict:
    """Build the credential form fields for the given auth method."""
    if auth_method == AUTH_METHOD_COOKIE:
        return {vol.Required(CONF_KEYCLOAK_IDENTITY): str}
    username_field = vol.Required(CONF_USERNAME, default=username) if username else vol.Required(CONF_USERNAME)
    return {username_field: str, vol.Required(CONF_PASSWORD): str}
