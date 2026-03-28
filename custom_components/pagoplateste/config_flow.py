"""
ConfigFlow și OptionsFlow pentru integrarea Pago Plătește.

Utilizatorul introduce email + parolă + interval, apoi se validează credențialele.
OptionsFlow permite activarea licenței și reconfigurarea contului.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .const import (
    CONF_EMAIL,
    CONF_LICENSE_KEY,
    CONF_PASSWORD,
    CONF_POS_USER_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LICENSE_DATA_KEY,
    LICENSE_PURCHASE_URL,
    MIN_SCAN_INTERVAL,
)
from .api import PagoApiClient, PagoAuthError, PagoConnectionError

_LOGGER = logging.getLogger(__name__)


# ------------------------------------------------------------------
# ConfigFlow
# ------------------------------------------------------------------


class PagoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """ConfigFlow — autentificare + validare."""

    VERSION = 1

    def __init__(self) -> None:
        """Inițializează flow-ul."""
        self._email: str = ""
        self._password: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pasul 1: Autentificare (email + parolă + interval)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._email = user_input[CONF_EMAIL]
            self._password = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(self._email.lower())
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            phone_id = str(uuid.uuid4())
            session_id = str(uuid.uuid4())

            client = PagoApiClient(
                session=session,
                email=self._email,
                password=self._password,
                phone_id=phone_id,
                session_id=session_id,
            )

            try:
                await client.async_login()
                profil = await client.async_fetch_profil()

                if profil:
                    name = f"{profil.get('nume', '')} {profil.get('prenume', '')}".strip()
                    pos_user_id = profil.get("pos_user_id", 0)
                else:
                    name = ""
                    pos_user_id = 0

                scan_interval = user_input.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                )

                return self.async_create_entry(
                    title=name or self._email,
                    data={
                        CONF_EMAIL: self._email,
                        CONF_PASSWORD: self._password,
                        CONF_POS_USER_ID: pos_user_id,
                        CONF_SCAN_INTERVAL: scan_interval,
                        "phone_id": phone_id,
                        "session_id": session_id,
                    },
                )
            except PagoAuthError:
                errors["base"] = "auth_failed"
            except PagoConnectionError:
                errors["base"] = "connection_failed"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("[Pago:ConfigFlow] Eroare neașteptată")
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=DEFAULT_SCAN_INTERVAL,
                ): vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL)),
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> PagoOptionsFlow:
        """Returnează options flow-ul."""
        return PagoOptionsFlow()


# ------------------------------------------------------------------
# OptionsFlow
# ------------------------------------------------------------------


class PagoOptionsFlow(config_entries.OptionsFlow):
    """OptionsFlow — licență + reconfigurare."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Meniu principal."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["reconfigure", "licenta"],
        )

    async def async_step_licenta(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Formular activare licență."""
        from .license import LicenseManager

        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}
        is_ro = self.hass.config.language == "ro"

        mgr: LicenseManager | None = self.hass.data.get(DOMAIN, {}).get(
            LICENSE_DATA_KEY
        )
        if mgr is None:
            mgr = LicenseManager(self.hass)
            await mgr.async_load()

        server_status = mgr.status

        if server_status == "licensed":
            from datetime import datetime

            tip = mgr.license_type or "necunoscut"
            status_lines = [f"✅ Licență activă ({tip})"]

            if mgr.license_key_masked:
                status_lines[0] += f" — {mgr.license_key_masked}"

            if mgr.activated_at:
                act_date = datetime.fromtimestamp(
                    mgr.activated_at
                ).strftime("%d.%m.%Y %H:%M")
                status_lines.append(f"Activată la: {act_date}")

            if mgr.license_expires_at:
                exp_date = datetime.fromtimestamp(
                    mgr.license_expires_at
                ).strftime("%d.%m.%Y %H:%M")
                status_lines.append(f"📅 Expiră la: {exp_date}")
            elif tip == "perpetual":
                status_lines.append("Valabilitate: nelimitată (perpetuă)")

            description_placeholders["license_status"] = "\n".join(status_lines)

        elif server_status == "trial":
            days = mgr.trial_days_remaining
            if is_ro:
                status_lines = [
                    f"⏳ Evaluare — {days} zile rămase",
                    "",
                    f"🛒 Obține licență: {LICENSE_PURCHASE_URL}",
                ]
            else:
                status_lines = [
                    f"⏳ Trial — {days} days remaining",
                    "",
                    f"🛒 Get a license: {LICENSE_PURCHASE_URL}",
                ]
            description_placeholders["license_status"] = "\n".join(status_lines)
        elif server_status == "expired":
            if is_ro:
                status_lines = [
                    "❌ Licență expirată",
                    "",
                    f"🛒 Obține licență: {LICENSE_PURCHASE_URL}",
                ]
            else:
                status_lines = [
                    "❌ License expired",
                    "",
                    f"🛒 Get a license: {LICENSE_PURCHASE_URL}",
                ]
            description_placeholders["license_status"] = "\n".join(status_lines)
        else:
            if is_ro:
                status_lines = [
                    "❌ Fără licență — funcționalitate blocată",
                    "",
                    f"🛒 Obține licență: {LICENSE_PURCHASE_URL}",
                ]
            else:
                status_lines = [
                    "❌ No license — functionality blocked",
                    "",
                    f"🛒 Get a license: {LICENSE_PURCHASE_URL}",
                ]
            description_placeholders["license_status"] = "\n".join(status_lines)

        if user_input is not None:
            cheie = user_input.get(CONF_LICENSE_KEY, "").strip()

            if not cheie:
                errors["base"] = "license_key_empty"
            elif len(cheie) < 10:
                errors["base"] = "license_key_invalid"
            else:
                result = await mgr.async_activate(cheie)

                if result.get("success"):
                    from homeassistant.components import persistent_notification

                    _LICENSE_TYPE_RO = {
                        "monthly": "lunară",
                        "yearly": "anuală",
                        "perpetual": "perpetuă",
                        "trial": "evaluare",
                    }
                    tip_ro = _LICENSE_TYPE_RO.get(
                        mgr.license_type, mgr.license_type or "necunoscut"
                    )

                    persistent_notification.async_create(
                        self.hass,
                        f"Licența Pago Plătește a fost activată cu succes! "
                        f"Tip: {tip_ro}.",
                        title="Licență activată",
                        notification_id="pagoplateste_license_activated",
                    )
                    return self.async_create_entry(
                        data=self.config_entry.options
                    )

                api_error = result.get("error", "unknown_error")
                error_map = {
                    "invalid_key": "license_key_invalid",
                    "already_used": "license_already_used",
                    "expired_key": "license_key_expired",
                    "fingerprint_mismatch": "license_fingerprint_mismatch",
                    "invalid_signature": "license_server_error",
                    "network_error": "license_network_error",
                    "server_error": "license_server_error",
                }
                errors["base"] = error_map.get(api_error, "license_server_error")

        schema = vol.Schema(
            {
                vol.Optional(CONF_LICENSE_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        suffix="PAGO-XXXX-XXXX-XXXX-XXXX",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="licenta",
            data_schema=schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigurare credențiale."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]

            session = async_get_clientsession(self.hass)
            phone_id = str(uuid.uuid4())
            session_id = str(uuid.uuid4())

            client = PagoApiClient(
                session=session,
                email=email,
                password=password,
                phone_id=phone_id,
                session_id=session_id,
            )

            try:
                await client.async_login()
                profil = await client.async_fetch_profil()

                if profil:
                    scan_interval = user_input.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    )
                    pos_user_id = profil.get("pos_user_id", 0)
                    new_data = dict(self.config_entry.data)
                    new_data[CONF_EMAIL] = email
                    new_data[CONF_PASSWORD] = password
                    new_data[CONF_POS_USER_ID] = pos_user_id
                    new_data[CONF_SCAN_INTERVAL] = scan_interval
                    new_data["phone_id"] = phone_id
                    new_data["session_id"] = session_id

                    self.hass.config_entries.async_update_entry(
                        self.config_entry, data=new_data
                    )
                    await self.hass.config_entries.async_reload(
                        self.config_entry.entry_id
                    )
                    return self.async_create_entry(data={})
                else:
                    errors["base"] = "connection_failed"
            except PagoAuthError:
                errors["base"] = "auth_failed"
            except PagoConnectionError:
                errors["base"] = "connection_failed"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"

        current = self.config_entry.data

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_EMAIL, default=current.get(CONF_EMAIL, "")
                ): str,
                vol.Required(
                    CONF_PASSWORD, default=current.get(CONF_PASSWORD, "")
                ): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL)),
            }
        )

        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )
