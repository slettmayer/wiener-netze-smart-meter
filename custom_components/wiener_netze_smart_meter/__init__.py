"""Wiener Netze Smart Meter integration."""

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api_client import WienerNetzeApiClient
from .const import (
    CONF_AUTH_METHOD,
    CONF_KEYCLOAK_IDENTITY,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_FETCH_DAYS,
    DOMAIN,
    SERVICE_ATTR_DAYS,
    SERVICE_FETCH_DATA,
)
from .coordinator import SmartMeterCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(SERVICE_ATTR_DAYS, default=DEFAULT_FETCH_DAYS): vol.All(
            int, vol.Range(min=1, max=365)
        ),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Wiener Netze Smart Meter from a config entry."""
    session = async_get_clientsession(hass)
    client = WienerNetzeApiClient(
        session,
        auth_method=entry.data[CONF_AUTH_METHOD],
        keycloak_identity=entry.data.get(CONF_KEYCLOAK_IDENTITY),
        username=entry.data.get(CONF_USERNAME),
        password=entry.data.get(CONF_PASSWORD),
    )

    coordinator = SmartMeterCoordinator(hass, entry, client)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register service if not already registered
    if not hass.services.has_service(DOMAIN, SERVICE_FETCH_DATA):

        async def handle_fetch_data(call: ServiceCall) -> None:
            """Handle the fetch_data service call."""
            days = call.data.get(SERVICE_ATTR_DAYS, DEFAULT_FETCH_DAYS)
            _LOGGER.info("Service call: fetching %d days of data", days)

            for coordinator in hass.data.get(DOMAIN, {}).values():
                await coordinator.async_fetch(days)

        hass.services.async_register(
            DOMAIN, SERVICE_FETCH_DATA, handle_fetch_data, schema=SERVICE_SCHEMA
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    # Remove service if no more entries
    if not hass.data.get(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_FETCH_DATA)

    return unload_ok
