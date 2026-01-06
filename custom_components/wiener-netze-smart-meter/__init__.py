"""The wiener-netze-smart-meter component."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the wiener-netze-smart-meter component."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up wiener-netze-smart-meter from a config entry."""
    _LOGGER.debug(f"Setting up Smart Meter integration for {entry.title}")

    # Use async_forward_entry_setups instead of the deprecated async_forward_entry_setup
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    return True
