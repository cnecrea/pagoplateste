"""
Diagnosticare pentru integrarea Pago Plătește.

Exportă informații de diagnostic pentru support tickets:
- Licență (fingerprint, status, cheie mascată)
- Mașini active și senzori
- Starea coordinator-ului

Datele sensibile (parolă, token-uri, session_id) sunt excluse.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, LICENSE_DATA_KEY


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Returnează datele de diagnostic pentru Pago Plătește."""

    # ── Licență (fingerprint + cheie mascată) ──
    license_mgr = hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
    licenta_info: dict[str, Any] = {}
    if license_mgr:
        licenta_info = {
            "fingerprint": license_mgr.fingerprint,
            "status": license_mgr.status,
            "license_key": license_mgr.license_key_masked,
            "is_valid": license_mgr.is_valid,
            "license_type": license_mgr.license_type,
        }

    # ── Coordinator ──
    runtime = getattr(entry, "runtime_data", None)
    coordinator_info: dict[str, Any] = {}
    if runtime and hasattr(runtime, "coordinator") and runtime.coordinator:
        coordinator = runtime.coordinator
        coordinator_info = {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
        }
        data = coordinator.data or {}
        coordinator_info["numar_carduri"] = len(data.get("carduri") or [])
        coordinator_info["numar_masini"] = len(data.get("masini") or [])
        coordinator_info["numar_facturi_sumar"] = len(data.get("facturi_sumar") or [])
        coordinator_info["numar_conturi_facturi"] = len(data.get("conturi_facturi") or [])
        coordinator_info["numar_plati_recente"] = len(data.get("plati_recente") or [])

    # ── Senzori activi ──
    senzori_activi = sorted(
        entitate.entity_id
        for entitate in hass.states.async_all("sensor")
        if entitate.entity_id.startswith(f"sensor.{DOMAIN}_")
    )

    # ── Config entry (fără date sensibile) ──
    return {
        "intrare": {
            "titlu": entry.title,
            "versiune": entry.version,
            "domeniu": DOMAIN,
            "email": _mascheaza_email(entry.data.get("email", "")),
            "pos_user_id": entry.data.get("pos_user_id"),
            "scan_interval": entry.data.get("scan_interval"),
        },
        "licenta": licenta_info,
        "coordinator": coordinator_info,
        "stare": {
            "senzori_activi": len(senzori_activi),
            "lista_senzori": senzori_activi,
        },
    }


def _mascheaza_email(email: str) -> str:
    """Maschează email-ul păstrând prima literă și domeniul."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        return f"*@{domain}"
    return f"{local[0]}{'*' * (len(local) - 1)}@{domain}"
