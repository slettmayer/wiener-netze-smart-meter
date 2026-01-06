"""Config flow for the wiener_netze_smart_meter integration."""

import voluptuous as vol

from homeassistant import config_entries

from .const import DOMAIN


class SmartMeterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for wiener_netze_smart_meter."""

    VERSION = 1

    async def async_step_user(self, info):
        if info is not None:
            return self.async_create_entry(title="Smart Meter", data=info)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("GP", default="120305XXXX"): str,
                    vol.Required(
                        "DEVICE", default="AT001000000000000000100001519XXXX"
                    ): str,
                    vol.Required(
                        "TOKEN",
                        default="Visit https://smartmeter-web.wienernetze.at/, copy 'KEYCLOAK_IDENTITY' cookie from developer tools",
                    ): str,
                    vol.Required("INTERVAL", default=60): int,
                    vol.Required("IMPORT_DAYS", default=90): int,
                    vol.Required("15MIN_ENABLED", default=True): bool,
                }
            ),
        )
