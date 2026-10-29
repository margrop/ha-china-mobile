"""Set up a number from the autoLogin request body captured from the China Mobile app."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig

from .api import (
    HOST_LOGIN,
    PATH_AUTOLOGIN,
    CmccAuthError,
    CmccClient,
    CmccError,
    CmccRateLimitError,
    new_session,
    parse_capture,
    phone_of,
)
from .const import CONF_CAPTURE, CONF_ENVELOPE, DEFAULT_INTERVAL, DOMAIN, MAX_INTERVAL, MIN_INTERVAL

CAPTURE_SCHEMA = vol.Schema(
    {vol.Required(CONF_CAPTURE): TextSelector(TextSelectorConfig(multiline=True))}
)
# hassfest does not allow URLs inside strings.json.
CAPTURE_PLACEHOLDERS = {
    "autologin_url": f"https://{HOST_LOGIN}{PATH_AUTOLOGIN}",
    "autologin_alt": ".../uamonekeylogin/autoLogin",
}


def _title(phone: str) -> str:
    return f"中国移动 {phone[:3]}****{phone[-4:]}"


async def _validate(capture: str) -> tuple[str, dict]:
    """Return the envelope and errors (empty when the envelope works)."""
    try:
        envelope = parse_capture(capture)
    except CmccAuthError:
        return "", {"base": "invalid_capture"}
    session = new_session()
    try:
        await CmccClient(session, envelope).refresh()
    except CmccAuthError:
        return envelope, {"base": "invalid_auth"}
    except CmccRateLimitError:
        return envelope, {"base": "rate_limited"}
    except CmccError:
        return envelope, {"base": "cannot_connect"}
    finally:
        await session.close()
    return envelope, {}


class CmccConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            envelope, errors = await _validate(user_input[CONF_CAPTURE])
            if not errors:
                phone = phone_of(envelope)
                await self.async_set_unique_id(phone)
                self._abort_if_unique_id_configured(updates={CONF_ENVELOPE: envelope})
                return self.async_create_entry(title=_title(phone), data={CONF_ENVELOPE: envelope})
        return self.async_show_form(
            step_id="user",
            data_schema=CAPTURE_SCHEMA,
            errors=errors,
            description_placeholders=CAPTURE_PLACEHOLDERS,
        )

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            envelope, errors = await _validate(user_input[CONF_CAPTURE])
            if not errors and phone_of(envelope) != entry.unique_id:
                errors = {"base": "wrong_number"}
            if not errors:
                return self.async_update_reload_and_abort(entry, data={CONF_ENVELOPE: envelope})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=CAPTURE_SCHEMA,
            errors=errors,
            description_placeholders={"title": entry.title},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return CmccOptionsFlow()


class CmccOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_INTERVAL, max=MAX_INTERVAL)
                    )
                }
            ),
        )
