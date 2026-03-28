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
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
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
            name=f"{DOMAIN}_{entry.data[CONF_EMAIL]}",
            update_interval=timedelta(seconds=scan_interval),
            always_update=True,
        )
        self._entry = entry
        self._client = api_client

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch date de la API-ul Pago."""
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

        # Verificăm că avem cel puțin profilul
        if not data.get("profil"):
            raise UpdateFailed("Pago: nu s-au putut obține datele profilului")

        return data

    @property
    def email(self) -> str:
        """Email-ul contului Pago."""
        return self._entry.data[CONF_EMAIL]

    @property
    def pos_user_id(self) -> int:
        """ID-ul utilizatorului Pago (pos_user_id din profil)."""
        return self._entry.data.get(CONF_POS_USER_ID, 0)
