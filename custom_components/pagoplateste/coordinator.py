"""DataUpdateCoordinator pentru integrarea Pago Plătește."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import PagoApiClient, PagoAuthError, PagoConnectionError
from .const import (
    CONF_EMAIL,
    CONF_POS_USER_ID,
    DATA_ABONAMENT,
    DATA_PROFIL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LICENSE_DATA_KEY,
)

_LOGGER = logging.getLogger(__name__)


class PagoCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator care centralizează fetch-ul de date de la Pago."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: PagoApiClient,
        entry: ConfigEntry,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Inițializează coordinatorul."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            # Fără email în nume: apare în log-urile pe care utilizatorii le
            # publică în issue-uri („Error fetching … data")
            name=f"{DOMAIN}_{entry.data.get(CONF_POS_USER_ID) or entry.entry_id}",
            update_interval=timedelta(seconds=scan_interval),
            always_update=True,
        )
        self._entry = entry
        self._client = api_client
        self._partial_raportat = False

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch date de la API-ul Pago."""
        # Verificare licență — nu fetchuim date dacă licența/trial nu e validă
        license_mgr = self.hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
        if license_mgr and not license_mgr.is_valid:
            _LOGGER.debug("[Pago] Licență invalidă — se omit apelurile API")
            return self.data or {}

        try:
            data = await self._client.async_fetch_all()
        except PagoAuthError as err:
            raise ConfigEntryAuthFailed(
                f"Autentificare eșuată: {err}"
            ) from err
        except PagoConnectionError as err:
            raise UpdateFailed(
                f"Eroare conexiune Pago: {err}"
            ) from err
        except Exception as err:
            raise UpdateFailed(
                f"Eroare neașteptată Pago: {err}"
            ) from err

        # None = endpoint eșuat temporar. Dacă nimic n-a răspuns → UpdateFailed;
        # altfel se păstrează valorile anterioare pentru ce a eșuat (înainte: o
        # cerere expirată golea cardurile/plățile și trecea mașinile pe „Fără RCA").
        esuate = [k for k, v in data.items() if v is None]
        if len(esuate) == len(data):
            raise UpdateFailed("Pago: niciun serviciu nu a răspuns")
        anterioare = self.data or {}
        for k in esuate:
            data[k] = anterioare.get(k, {} if k in (DATA_PROFIL, DATA_ABONAMENT) else [])

        # Verificăm că avem cel puțin profilul
        if not data.get(DATA_PROFIL):
            raise UpdateFailed("Pago: nu s-au putut obține datele profilului")

        if esuate and not self._partial_raportat:
            _LOGGER.warning(
                "[Pago] Nu au răspuns: %s — păstrez datele anterioare",
                ", ".join(esuate),
            )
            self._partial_raportat = True
        elif not esuate and self._partial_raportat:
            _LOGGER.info("[Pago] Toate datele s-au actualizat din nou")
            self._partial_raportat = False

        return data

    @property
    def email(self) -> str:
        """Email-ul contului Pago."""
        return self._entry.data[CONF_EMAIL]

    @property
    def pos_user_id(self) -> int:
        """ID-ul utilizatorului Pago (pos_user_id din profil)."""
        return self._entry.data.get(CONF_POS_USER_ID, 0)
