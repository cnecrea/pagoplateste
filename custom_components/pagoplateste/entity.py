"""Entități de bază pentru integrarea Pago Plătește.

Pattern IDENTIC cu eonromania/ebloc:
  - _attr_has_entity_name = False
  - custom entity_id property (getter/setter)
  - _license_valid property in base class
  - device_info cu DeviceEntryType.SERVICE
  - identifiers cu pos_user_id (nu email)
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LICENSE_DATA_KEY, MANUFACTURER
from .coordinator import PagoCoordinator


# ──────────────────────────────────────────────
# Clasă de bază
# ──────────────────────────────────────────────
class PagoEntity(CoordinatorEntity[PagoCoordinator]):
    """Clasă de bază pentru entitățile Pago Plătește."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: PagoCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Inițializare cu coordinator și config_entry."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._pos_user_id = coordinator.pos_user_id
        self._email = coordinator.email
        self._custom_entity_id: str | None = None

    @property
    def _license_valid(self) -> bool:
        """Verifică dacă licența este validă."""
        mgr = self.coordinator.hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
        return mgr.is_valid if mgr else False

    @property
    def entity_id(self) -> str | None:
        """Returnează entity_id custom (pattern eonromania)."""
        return self._custom_entity_id

    @entity_id.setter
    def entity_id(self, value: str) -> None:
        """Setează entity_id (necesar pentru HA internals)."""
        self._custom_entity_id = value

    @property
    def device_info(self) -> DeviceInfo:
        """Informații dispozitiv — contul Pago."""
        return DeviceInfo(
            identifiers={(DOMAIN, str(self._pos_user_id))},
            name=f"Pago Plătește ({self._email})",
            manufacturer=MANUFACTURER,
            model="Pago Plătește",
            entry_type=DeviceEntryType.SERVICE,
        )
