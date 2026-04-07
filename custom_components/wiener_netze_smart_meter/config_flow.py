"""Config flow for Wiener Netze Smart Meter."""

import logging

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

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Step 1: Choose auth method."""
        if user_input is not None:
            self._auth_method = user_input[CONF_AUTH_METHOD]
            return await self.async_step_credentials()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_AUTH_METHOD, default=AUTH_METHOD_COOKIE
                    ): vol.In(
                        {
                            AUTH_METHOD_COOKIE: "KEYCLOAK_IDENTITY Cookie",
                            AUTH_METHOD_PASSWORD: "Username & Password",
                        }
                    ),
                }
            ),
        )

    async def async_step_credentials(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Step 2: Enter credentials and meter details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Build full config data
            data = {
                CONF_AUTH_METHOD: self._auth_method,
                CONF_GESCHAEFTSPARTNER: user_input[CONF_GESCHAEFTSPARTNER],
                CONF_ZAEHLPUNKTNUMMER: user_input[CONF_ZAEHLPUNKTNUMMER],
            }

            if self._auth_method == AUTH_METHOD_COOKIE:
                data[CONF_KEYCLOAK_IDENTITY] = user_input[CONF_KEYCLOAK_IDENTITY]
            else:
                data[CONF_USERNAME] = user_input[CONF_USERNAME]
                data[CONF_PASSWORD] = user_input[CONF_PASSWORD]

            # Validate credentials
            session = async_get_clientsession(self.hass)
            client = WienerNetzeApiClient(
                session,
                auth_method=data[CONF_AUTH_METHOD],
                keycloak_identity=data.get(CONF_KEYCLOAK_IDENTITY),
                username=data.get(CONF_USERNAME),
                password=data.get(CONF_PASSWORD),
            )

            try:
                await client.authenticate()
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during config validation")
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(data[CONF_ZAEHLPUNKTNUMMER])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Smart Meter {data[CONF_ZAEHLPUNKTNUMMER][-8:]}",
                    data=data,
                )

        # Build schema based on auth method
        schema_fields: dict = {}
        if self._auth_method == AUTH_METHOD_COOKIE:
            schema_fields[vol.Required(CONF_KEYCLOAK_IDENTITY)] = str
        else:
            schema_fields[vol.Required(CONF_USERNAME)] = str
            schema_fields[vol.Required(CONF_PASSWORD)] = str

        schema_fields[vol.Required(CONF_GESCHAEFTSPARTNER)] = str
        schema_fields[vol.Required(CONF_ZAEHLPUNKTNUMMER)] = str

        return self.async_show_form(
            step_id="credentials",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
        )
