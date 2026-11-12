"""
ConfigFlow și OptionsFlow pentru integrarea Pago Plătește.

Utilizatorul introduce email + parolă + interval, apoi se validează credențialele.
OptionsFlow permite activarea licenței și reconfigurarea contului.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState, ConfigFlowResult
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
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from . import _signature
from .api import PagoApiClient, PagoAuthError, PagoConnectionError

_LOGGER = logging.getLogger(__name__)

_PAROLA = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
)
_INTERVAL = vol.All(
    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
)

def _update_and_reload(
    hass, entry: config_entries.ConfigEntry, data: dict[str, Any], **kwargs: Any
) -> None:
    """Salvează intrarea și o reîncarcă o singură dată.

    Listener-ul de update reîncarcă singur intrarea când s-a schimbat
    configurația; dacă intrarea nu rulează (setup eșuat, ex. parolă respinsă)
    reîncărcăm aici. Decizia se ia ÎNAINTE de update: listener-ul pornește
    imediat. (Înainte: update + reload explicit + create_entry = două reload-uri.)
    """
    runtime = getattr(entry, "runtime_data", None)
    listener_reloads = (
        entry.state is ConfigEntryState.LOADED
        and runtime is not None
        and getattr(runtime, "config_signature", None) != _signature(data, entry.options)
    )
    hass.config_entries.async_update_entry(entry, data=data, **kwargs)
    if not listener_reloads:
        hass.config_entries.async_schedule_reload(entry.entry_id)


async def _async_valideaza(hass, email: str, password: str) -> tuple[dict[str, Any], str, str]:
    """Login + profil. Returnează (profil, phone_id, session_id).

    Fără profil nu creăm intrarea: pos_user_id ar fi 0, iar două conturi ar
    ajunge cu aceleași entity_id-uri (sensor.pagoplateste_0_…).
    Raises PagoAuthError / PagoConnectionError.
    """
    phone_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    client = PagoApiClient(
        session=async_get_clientsession(hass),
        email=email,
        password=password,
        phone_id=phone_id,
        session_id=session_id,
    )
    await client.async_login()
    profil = await client.async_fetch_profil()
    if not profil or not profil.get("pos_user_id"):
        raise PagoConnectionError("Profilul Pago nu a putut fi citit")
    return profil, phone_id, session_id


def _titlu(profil: dict[str, Any], email: str) -> str:
    name = f"{profil.get('nume') or ''} {profil.get('prenume') or ''}".strip()
    return name or email


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

            try:
                profil, phone_id, session_id = await _async_valideaza(
                    self.hass, self._email, self._password
                )
                scan_interval = user_input.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                )

                return self.async_create_entry(
                    title=_titlu(profil, self._email),
                    data={
                        CONF_EMAIL: self._email,
                        CONF_PASSWORD: self._password,
                        CONF_POS_USER_ID: profil["pos_user_id"],
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
                vol.Required(CONF_PASSWORD): _PAROLA,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=DEFAULT_SCAN_INTERVAL,
                ): _INTERVAL,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Pornit de Home Assistant când Pago respinge parola salvată.

        (Înainte coordinatorul cerea reautentificarea, dar flow-ul nu avea
        pasul → eroare în log și integrarea rămânea picată.)
        """
        self._email = entry_data[CONF_EMAIL]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Parola nouă → login → salvare + reload."""
        errors: dict[str, str] = {}
        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            try:
                await _async_valideaza(self.hass, self._email, password)
            except PagoAuthError:
                errors["base"] = "auth_failed"
            except PagoConnectionError:
                errors["base"] = "connection_failed"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("[Pago:ConfigFlow] Eroare neașteptată la reautentificare")
                errors["base"] = "unknown"
            else:
                entry = self._get_reauth_entry()
                _update_and_reload(
                    self.hass, entry, {**entry.data, CONF_PASSWORD: password}
                )
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): _PAROLA}),
            errors=errors,
            description_placeholders={"email": self._email},
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


# ── Textele licenței: aceleași în toate integrările hubinteligent (standardizate pe 12.11.2026) ──

_TIP_LICENTA = {
    # Tipurile emise de WebAPI (LICENSE_DURATION)
    "perpetual": ("permanentă", "permanent"),
    "annual": ("anuală", "annual"),
    "semi_annual": ("semestrială", "semi-annual"),
    "monthly": ("lunară", "monthly"),
}


def _tip_licenta(tip: str | None, is_ro: bool) -> str:
    """Eticheta tipului de licență primit de la server."""
    if not tip:
        return "necunoscut" if is_ro else "unknown"
    ro, en = _TIP_LICENTA.get(tip, (tip, tip))
    return ro if is_ro else en


def _zile_ramase(zile: int, is_ro: bool) -> str:
    """„o zi rămasă”, „5 zile rămase”, „20 de zile rămase” — „1 day left”, „5 days left”."""
    if zile <= 0:
        return "ultima zi" if is_ro else "last day"
    if not is_ro:
        return "1 day left" if zile == 1 else f"{zile} days left"
    if zile == 1:
        return "o zi rămasă"
    return f"{zile} {'de ' if zile % 100 >= 20 or zile % 100 == 0 else ''}zile rămase"


def _status_licenta(mgr, is_ro: bool) -> str:
    """Starea licenței, afișată la pasul „Licență”, deasupra câmpului „Cheie de licență”."""
    from homeassistant.util import dt as dt_util

    def data(moment: float) -> str:
        return dt_util.as_local(dt_util.utc_from_timestamp(moment)).strftime("%d.%m.%Y")

    obtine = f"🛒 {'Obține o licență' if is_ro else 'Get a license'}: {LICENSE_PURCHASE_URL}"
    if mgr.status == "licensed":
        linii = [f"✅ {'Licență activă' if is_ro else 'Active license'} ({_tip_licenta(mgr.license_type, is_ro)})"]
        if mgr.license_key_masked:
            linii[0] += f" — {mgr.license_key_masked}"
        if mgr.activated_at:
            linii.append(f"{'Activată la' if is_ro else 'Activated on'}: {data(mgr.activated_at)}")
        if mgr.license_expires_at:
            linii.append(f"📅 {'Expiră la' if is_ro else 'Expires on'}: {data(mgr.license_expires_at)}")
        else:
            linii.append("Valabilitate: nelimitată" if is_ro else "Validity: unlimited")
        return "\n".join(linii)
    if mgr.status == "trial":
        perioada = "Perioadă de test" if is_ro else "Free trial"
        return "\n".join([f"⏳ {perioada}: {_zile_ramase(mgr.trial_days_remaining, is_ro)}", "", obtine])
    if mgr.status == "expired" and mgr.has_license:
        linii = ["❌ Licență expirată" if is_ro else "❌ License expired"]
        if mgr.license_expires_at:
            linii.append(f"{'Expirată la' if is_ro else 'Expired on'}: {data(mgr.license_expires_at)}")
        return "\n".join([*linii, "", obtine])
    if mgr.status == "expired":
        return "\n".join(["❌ Perioada de test s-a încheiat" if is_ro else "❌ The free trial has ended", "", obtine])
    stare = "❌ Fără licență: senzorii nu se actualizează." if is_ro else "❌ No license: sensors do not update."
    return "\n".join([stare, "", obtine])


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

        description_placeholders["license_status"] = _status_licenta(mgr, is_ro)

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

                    persistent_notification.async_create(
                        self.hass,
                        f"Licența Pago Plătește este activă ({_tip_licenta(mgr.license_type, True)}).",
                        title="Licență activată",
                        notification_id="pagoplateste_license_activated",
                    )
                    return self.async_create_entry(
                        data=self.config_entry.options
                    )

                api_error = result.get("error", "unknown_error")
                # Codurile WebAPI /activate + erorile locale
                error_map = {
                    "invalid_key": "license_key_invalid",
                    "already_used": "license_already_used",
                    "expired_key": "license_key_expired",
                    "fingerprint_mismatch": "license_fingerprint_mismatch",
                    "network_error": "license_network_error",
                    "http_502": "license_network_error",
                    "http_503": "license_network_error",  # server temporar ocupat
                    "http_504": "license_network_error",
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
        entry = self.config_entry

        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD]

            # Alt cont deja configurat cu același email → conflict
            conflict = any(
                e.entry_id != entry.entry_id and e.unique_id == email.lower()
                for e in self.hass.config_entries.async_entries(DOMAIN)
            )
            if conflict:
                errors["base"] = "already_configured"
            else:
                try:
                    profil, phone_id, session_id = await _async_valideaza(
                        self.hass, email, password
                    )
                except PagoAuthError:
                    errors["base"] = "auth_failed"
                except PagoConnectionError:
                    errors["base"] = "connection_failed"
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("[Pago:ConfigFlow] Eroare neașteptată la reconfigurare")
                    errors["base"] = "unknown"
                else:
                    new_data = {
                        **entry.data,
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                        CONF_POS_USER_ID: profil["pos_user_id"],
                        CONF_SCAN_INTERVAL: user_input.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                        "phone_id": phone_id,
                        "session_id": session_id,
                    }
                    # Un singur reload (înainte: reload explicit + încă unul de la
                    # create_entry, care și golea opțiunile)
                    _update_and_reload(
                        self.hass,
                        entry,
                        new_data,
                        unique_id=email.lower(),
                        title=_titlu(profil, email),
                    )
                    return self.async_create_entry(data=dict(entry.options))

        current = entry.data

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_EMAIL, default=current.get(CONF_EMAIL, "")
                ): str,
                vol.Required(
                    CONF_PASSWORD, default=current.get(CONF_PASSWORD, "")
                ): _PAROLA,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): _INTERVAL,
            }
        )

        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )
