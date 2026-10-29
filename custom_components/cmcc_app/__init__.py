"""China Mobile balance and plan usage, read through the app's API with a captured login envelope."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CmccAuthError, CmccClient, CmccError, new_session
from .const import CONF_ENVELOPE, DEFAULT_INTERVAL, DOMAIN

PLATFORMS = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)


class CmccCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self._session = new_session()
        self.client = CmccClient(self._session, entry.data[CONF_ENVELOPE])
        super().__init__(
            hass,
            _LOGGER,
            name=entry.title,
            update_interval=timedelta(
                minutes=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_INTERVAL)
            ),
        )

    async def async_close(self) -> None:
        await self._session.close()

    async def _async_update_data(self):
        try:
            data = await self.client.fetch()
        except CmccAuthError as exc:
            raise ConfigEntryAuthFailed(str(exc)) from exc
        except CmccError as exc:
            raise UpdateFailed(str(exc)) from exc
        if data["errors"]:
            _LOGGER.warning("%s: some items could not be read: %s", self.entry.title, data["errors"])
        return data


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = CmccCoordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await coordinator.async_close()
        raise
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_close()
        return True
    return False


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
