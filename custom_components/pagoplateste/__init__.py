"""Inițializarea integrării Pago Plătește."""

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LICENSE_DATA_KEY,
    PLATFORMS,
)
from .api import PagoApiClient
from .coordinator import PagoCoordinator
from .license import LicenseManager

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class PagoRuntimeData:
    """Structură tipizată pentru datele runtime ale integrării."""

    coordinator: PagoCoordinator | None = None
    api_client: PagoApiClient | None = None


async def async_setup(hass: HomeAssistant, config: dict):
    """Configurează integrarea globală Pago Plătește."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Configurează integrarea pentru o anumită intrare (config entry)."""
    _LOGGER.info(
        "[Pago] Se configurează integrarea (entry_id=%s).",
        entry.entry_id,
    )

    hass.data.setdefault(DOMAIN, {})

    # ── Inițializare License Manager (o singură instanță per domeniu) ──
    if LICENSE_DATA_KEY not in hass.data.get(DOMAIN, {}):
        _LOGGER.debug("[Pago] Inițializez LicenseManager (prima entry)")
        license_mgr = LicenseManager(hass)
        # IMPORTANT: setăm referința ÎNAINTE de async_load() pentru a preveni
        # race condition-ul: async_load() face await HTTP, ceea ce cedează
        # event loop-ul. Fără această ordine, alte entry-uri concurente ar vedea
        # LICENSE_DATA_KEY ca lipsă și ar crea câte un LicenseManager duplicat,
        # generând N request-uri /check simultane (câte unul per entry).
        hass.data[DOMAIN][LICENSE_DATA_KEY] = license_mgr
        await license_mgr.async_load()
        _LOGGER.debug(
            "[Pago] LicenseManager: status=%s, valid=%s, fingerprint=%s...",
            license_mgr.status,
            license_mgr.is_valid,
            license_mgr.fingerprint[:16],
        )

        # Heartbeat periodic
        from datetime import timedelta
        from homeassistant.helpers.event import (
            async_track_point_in_time,
            async_track_time_interval,
        )
        from homeassistant.util import dt as dt_util

        interval_sec = license_mgr.check_interval_seconds
        _LOGGER.debug(
            "[Pago] Programez heartbeat periodic la fiecare %d secunde",
            interval_sec,
        )

        async def _heartbeat_periodic(_now) -> None:
            """Verifică statusul la server dacă cache-ul a expirat.

            Logică:
            1. Captează is_valid ÎNAINTE de heartbeat
            2. Dacă cache expirat → contactează serverul
            3. Captează is_valid DUPĂ heartbeat
            4. Dacă starea s-a schimbat → reload entries (tranziție curată)
            5. Reprogramează heartbeat-ul la intervalul actualizat de server
            """
            mgr: LicenseManager | None = hass.data.get(DOMAIN, {}).get(
                LICENSE_DATA_KEY
            )
            if not mgr:
                _LOGGER.debug("[Pago] Heartbeat: LicenseManager nu există, skip")
                return

            # Captează starea ÎNAINTE de heartbeat
            was_valid = mgr.is_valid

            if mgr.needs_heartbeat:
                _LOGGER.debug("[Pago] Heartbeat: cache expirat, verific la server")
                await mgr.async_heartbeat()

                # Captează starea DUPĂ heartbeat
                now_valid = mgr.is_valid

                # Detectează tranziții pe care async_check_status nu le-a prins
                # (ex: server inaccesibil + cache expirat → is_valid devine False)
                if was_valid and not now_valid:
                    _LOGGER.warning(
                        "[Pago] Licența a devenit invalidă — reîncarc senzorii"
                    )
                    await mgr._async_reload_entries()
                elif not was_valid and now_valid:
                    _LOGGER.info(
                        "[Pago] Licența a redevenit validă — reîncarc senzorii"
                    )
                    await mgr._async_reload_entries()

                # Reprogramează heartbeat-ul la intervalul actualizat de server
                new_interval = mgr.check_interval_seconds
                _LOGGER.debug(
                    "[Pago] Heartbeat: reprogramez la %d secunde (%d min)",
                    new_interval,
                    new_interval // 60,
                )
                # Oprește vechiul timer
                cancel_old = hass.data.get(DOMAIN, {}).get("_cancel_heartbeat")
                if cancel_old:
                    cancel_old()
                # Programează noul timer cu intervalul actualizat
                cancel_new = async_track_time_interval(
                    hass,
                    _heartbeat_periodic,
                    timedelta(seconds=new_interval),
                )
                hass.data[DOMAIN]["_cancel_heartbeat"] = cancel_new
            else:
                _LOGGER.debug("[Pago] Heartbeat: cache valid, nu e nevoie de verificare")

        cancel_heartbeat = async_track_time_interval(
            hass,
            _heartbeat_periodic,
            timedelta(seconds=interval_sec),
        )
        hass.data[DOMAIN]["_cancel_heartbeat"] = cancel_heartbeat

        # ── Timer precis la valid_until (zero gap la expirare cache) ──
        def _schedule_cache_expiry_check(mgr_ref: LicenseManager) -> None:
            """Programează un check EXACT la momentul expirării cache-ului."""
            cancel_prev = hass.data.get(DOMAIN, {}).pop(
                "_cancel_cache_expiry", None
            )
            if cancel_prev:
                cancel_prev()

            valid_until = (mgr_ref._status_token or {}).get("valid_until")
            if not valid_until or valid_until <= 0:
                return

            expiry_dt = dt_util.utc_from_timestamp(valid_until)
            expiry_dt = expiry_dt + timedelta(seconds=2)

            async def _on_cache_expiry(_now) -> None:
                """Callback executat EXACT la expirarea cache-ului."""
                mgr_now: LicenseManager | None = hass.data.get(
                    DOMAIN, {}
                ).get(LICENSE_DATA_KEY)
                if not mgr_now:
                    return

                was_valid = mgr_now.is_valid
                _LOGGER.debug(
                    "[Pago] Cache expirat — verific imediat la server"
                )
                await mgr_now.async_check_status()
                now_valid = mgr_now.is_valid

                if was_valid != now_valid:
                    if now_valid:
                        _LOGGER.info(
                            "[Pago] Licența a redevenit validă — reîncarc"
                        )
                    else:
                        _LOGGER.warning(
                            "[Pago] Licența a devenit invalidă — reîncarc"
                        )
                    await mgr_now._async_reload_entries()

                _schedule_cache_expiry_check(mgr_now)

            cancel_expiry = async_track_point_in_time(
                hass, _on_cache_expiry, expiry_dt
            )
            hass.data[DOMAIN]["_cancel_cache_expiry"] = cancel_expiry

            _LOGGER.debug(
                "[Pago] Cache expiry timer programat la %s",
                expiry_dt.isoformat(),
            )

        _schedule_cache_expiry_check(license_mgr)

        # Notificare re-enable
        was_disabled = hass.data.pop(f"{DOMAIN}_was_disabled", False)
        if was_disabled:
            await license_mgr.async_notify_event("integration_enabled")

        if not license_mgr.is_valid:
            _LOGGER.warning(
                "[Pago] Integrarea nu are licență validă. "
                "Senzorii vor afișa 'Licență necesară'."
            )
        elif license_mgr.is_trial_valid:
            _LOGGER.info(
                "[Pago] Perioadă de evaluare — %d zile rămase",
                license_mgr.trial_days_remaining,
            )
        else:
            _LOGGER.info(
                "[Pago] Licență activă — tip: %s",
                license_mgr.license_type,
            )
    else:
        _LOGGER.debug("[Pago] LicenseManager există deja (entry suplimentară)")

    # ── Client API ──
    session = async_get_clientsession(hass)
    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]
    phone_id = entry.data.get("phone_id", str(__import__("uuid").uuid4()))
    session_id = entry.data.get("session_id", str(__import__("uuid").uuid4()))

    api_client = PagoApiClient(
        session=session,
        email=email,
        password=password,
        phone_id=phone_id,
        session_id=session_id,
    )

    # ── Coordinator (cu interval configurabil) ──
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = PagoCoordinator(hass, api_client, entry, scan_interval)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.error(
            "[Pago] Prima actualizare eșuată (entry_id=%s): %s",
            entry.entry_id,
            err,
        )
        return False

    # Salvăm datele runtime
    entry.runtime_data = PagoRuntimeData(
        coordinator=coordinator,
        api_client=api_client,
    )

    # Încărcăm platformele (NECONDIȚIONAT — gating-ul e în sensor.py)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listener pentru modificarea opțiunilor
    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    _LOGGER.info(
        "[Pago] Integrarea configurată (entry_id=%s).",
        entry.entry_id,
    )
    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry):
    """Reîncarcă integrarea când opțiunile se schimbă."""
    _LOGGER.info("[Pago] Opțiunile s-au schimbat. Se reîncarcă...")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Descărcarea intrării din config_entries."""
    _LOGGER.info(
        "[Pago] async_unload_entry entry_id=%s",
        entry.entry_id,
    )

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        remaining_entries = hass.config_entries.async_entries(DOMAIN)
        entry_ids_ramase = {
            e.entry_id for e in remaining_entries if e.entry_id != entry.entry_id
        }

        if not entry_ids_ramase:
            _LOGGER.info("[Pago] Ultima entry descărcată — curăț domeniul complet")

            # Notificare lifecycle
            mgr = hass.data[DOMAIN].get(LICENSE_DATA_KEY)
            if mgr and not hass.is_stopping:
                if entry.disabled_by:
                    await mgr.async_notify_event("integration_disabled")
                    hass.data[f"{DOMAIN}_was_disabled"] = True
                else:
                    hass.data.setdefault(f"{DOMAIN}_notify", {}).update(
                        {
                            "fingerprint": mgr.fingerprint,
                            "license_key": mgr._data.get("license_key", ""),
                        }
                    )

            # Oprește heartbeat
            cancel_hb = hass.data[DOMAIN].pop("_cancel_heartbeat", None)
            if cancel_hb:
                cancel_hb()
                _LOGGER.debug("[Pago] Heartbeat oprit")

            # Oprește timer-ul de cache expiry
            cancel_ce = hass.data[DOMAIN].pop("_cancel_cache_expiry", None)
            if cancel_ce:
                cancel_ce()
                _LOGGER.debug("[Pago] Cache expiry timer oprit")

            # Elimină LicenseManager
            hass.data[DOMAIN].pop(LICENSE_DATA_KEY, None)

            # Elimină domeniul complet
            hass.data.pop(DOMAIN, None)

            _LOGGER.info("[Pago] Cleanup complet")
    else:
        _LOGGER.error("[Pago] Unload EȘUAT pentru entry_id=%s", entry.entry_id)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Notifică serverul când integrarea e complet eliminată."""
    _LOGGER.debug("[Pago] async_remove_entry entry_id=%s", entry.entry_id)

    remaining = hass.config_entries.async_entries(DOMAIN)
    if not remaining:
        notify_data = hass.data.pop(f"{DOMAIN}_notify", None)
        if notify_data and notify_data.get("fingerprint"):
            await _send_lifecycle_event(
                hass,
                notify_data["fingerprint"],
                notify_data.get("license_key", ""),
                "integration_removed",
            )


async def _send_lifecycle_event(
    hass: HomeAssistant, fingerprint: str, license_key: str, action: str
) -> None:
    """Trimite un eveniment lifecycle direct (fără LicenseManager)."""
    import hashlib
    import hmac as hmac_lib
    import json
    import time

    import aiohttp

    from .license import INTEGRATION, LICENSE_API_URL

    timestamp = int(time.time())
    payload = {
        "fingerprint": fingerprint,
        "timestamp": timestamp,
        "action": action,
        "license_key": license_key,
        "integration": INTEGRATION,
    }
    data = {k: v for k, v in payload.items() if k != "hmac"}
    msg = json.dumps(data, sort_keys=True).encode()
    payload["hmac"] = hmac_lib.new(
        fingerprint.encode(), msg, hashlib.sha256
    ).hexdigest()

    try:
        session = async_get_clientsession(hass)
        async with session.post(
            f"{LICENSE_API_URL}/notify",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "PagoPlat-HA-Integration/3.0",
            },
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                if not result.get("success"):
                    _LOGGER.warning(
                        "[Pago] Server a refuzat '%s': %s",
                        action,
                        result.get("error"),
                    )
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("[Pago] Nu s-a putut raporta '%s': %s", action, err)
