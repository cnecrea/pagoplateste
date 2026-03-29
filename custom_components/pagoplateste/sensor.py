"""Platforma Sensor pentru Pago Plătește.

Pattern IDENTIC cu eonromania/ebloc:
  - _attr_has_entity_name = False
  - custom entity_id property (getter/setter)
  - self._custom_entity_id = f"sensor.{DOMAIN}_{pos_user_id}_xxx"
  - Atribute cu etichete românești human-readable
  - Senzori GRUPAȚI logic
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DATA_ABONAMENT,
    DATA_CARDURI,
    DATA_CONTURI_FACTURI,
    DATA_FACTURI_SUMAR,
    DATA_MASINI,
    DATA_PLATI_RECENTE,
    DATA_PROFIL,
    DOMAIN,
    LICENSE_DATA_KEY,
)
from .coordinator import PagoCoordinator
from .entity import PagoEntity

_LOGGER = logging.getLogger(__name__)

CURRENCY_LEI = "lei"

LUNI_RO = {
    1: "ianuarie", 2: "februarie", 3: "martie", 4: "aprilie",
    5: "mai", 6: "iunie", 7: "iulie", 8: "august",
    9: "septembrie", 10: "octombrie", 11: "noiembrie", 12: "decembrie",
}


def _luna_din_data(data_str: str | None) -> str:
    """Extrage numele lunii în română dintr-un string dată (YYYY-MM-DD ...)."""
    if not data_str or not isinstance(data_str, str) or len(data_str) < 7:
        return "necunoscută"
    try:
        luna_nr = int(data_str[5:7])
        return LUNI_RO.get(luna_nr, "necunoscută")
    except (ValueError, TypeError):
        return "necunoscută"


def _data_scurta(data_str: str | None) -> str:
    """'2026-03-18 20:20' → '18 martie', '2026-02-04' → '4 februarie'."""
    if not data_str or not isinstance(data_str, str) or len(data_str) < 10:
        return "—"
    try:
        zi = int(data_str[8:10])
        luna = _luna_din_data(data_str)
        return f"{zi} {luna}"
    except (ValueError, TypeError):
        return "—"


def _data_completa(data_str: str | None) -> str:
    """'2025-05-05' → '5 mai 2025'."""
    if not data_str or not isinstance(data_str, str) or len(data_str) < 10:
        return "—"
    try:
        zi = int(data_str[8:10])
        luna = _luna_din_data(data_str)
        an = data_str[:4]
        return f"{zi} {luna} {an}"
    except (ValueError, TypeError):
        return "—"


def _curata_furnizor(furnizor: str | None) -> str:
    """Elimină sufixul .crawler din numele furnizorului și capitalizează."""
    if not furnizor:
        return "—"
    curat = furnizor.replace(".crawler", "")
    return curat.upper() if curat else "—"


def _furnizor_display(furnizor: str | None) -> str:
    """Nume furnizor afișabil: 'rds.crawler' → 'Rds', 'premier_energy.crawler' → 'Premier Energy'."""
    if not furnizor:
        return "Necunoscut"
    # Scoatem .crawler
    name = furnizor.replace(".crawler", "")
    # Înlocuim underscore cu spațiu, apoi separăm pe punct
    name = name.replace("_", " ")
    parts = name.split(".")
    return " ".join(p.capitalize() for p in parts if p)


def _furnizor_slug(furnizor: str | None) -> str:
    """Slug pentru entity_id: 'rds.crawler' → 'rds', 'engie.gas' → 'engie_gas'."""
    if not furnizor:
        return "necunoscut"
    # Scoatem .crawler, înlocuim puncte/spații cu underscore
    name = furnizor.replace(".crawler", "").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    return slug or "necunoscut"


def _is_license_valid(hass: HomeAssistant) -> bool:
    """Verifică dacă licența este validă (real-time)."""
    mgr = hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
    if mgr is None:
        return False
    return mgr.is_valid


def _zile_ramase(data_expirare: str | None) -> int | None:
    """Calculează zilele rămase dintr-un string dată (YYYY-MM-DD HH:MM sau YYYY-MM-DD)."""
    if not data_expirare or not isinstance(data_expirare, str):
        return None
    try:
        # Parsăm doar partea de dată (primele 10 caractere)
        exp = datetime.strptime(data_expirare[:10], "%Y-%m-%d")
        delta = exp - datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return delta.days
    except (ValueError, TypeError):
        return None


# ──────────────────────────────────────────────
# async_setup_entry
# ──────────────────────────────────────────────
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurează senzorii Pago Plătește."""
    runtime = entry.runtime_data
    coordinator: PagoCoordinator = runtime.coordinator
    uid = coordinator.pos_user_id

    license_valid = _is_license_valid(hass)
    licenta_uid = f"{DOMAIN}_licenta_{uid}"

    if not license_valid:
        registru = er.async_get(hass)
        for entry_reg in er.async_entries_for_config_entry(
            registru, entry.entry_id
        ):
            if (
                entry_reg.domain == "sensor"
                and entry_reg.unique_id != licenta_uid
            ):
                registru.async_remove(entry_reg.entity_id)
        async_add_entities(
            [LicentaNecesaraSensor(coordinator, entry, uid)],
            update_before_add=True,
        )
        return

    # Licență validă — curăță LicentaNecesaraSensor orfan
    registru = er.async_get(hass)
    entitate_licenta = registru.async_get_entity_id("sensor", DOMAIN, licenta_uid)
    if entitate_licenta is not None:
        registru.async_remove(entitate_licenta)

    entities: list[SensorEntity] = []
    an = datetime.now().year

    # 1. Cont Pago — profil + abonament
    entities.append(ContPagoSensor(coordinator, entry, uid))

    # 2. Carduri
    entities.append(CarduriSensor(coordinator, entry, uid))

    # 3. Cont furnizor — per furnizor (din conturi_facturi)
    furnizori_conturi: set[str] = set()
    for cont in coordinator.data.get(DATA_CONTURI_FACTURI) or []:
        furn_raw = cont.get("furnizor")
        if furn_raw and furn_raw not in furnizori_conturi:
            furnizori_conturi.add(furn_raw)
            entities.append(
                ContFurnizorSensor(coordinator, entry, uid, furn_raw)
            )

    # 4. Arhivă plăți — per furnizor (din plati_recente, anul curent)
    an_str = str(an)
    furnizori_plati: set[str] = set()
    for plata in coordinator.data.get(DATA_PLATI_RECENTE) or []:
        furn_raw = plata.get("furnizor")
        data_plata = str(plata.get("data", ""))
        if furn_raw and data_plata.startswith(an_str) and furn_raw not in furnizori_plati:
            furnizori_plati.add(furn_raw)
            entities.append(
                ArhivaPlatiFurnizorSensor(coordinator, entry, uid, furn_raw)
            )

    # 5. Facturi emise
    entities.append(FacturiEmiseSensor(coordinator, entry, uid))

    # 6. Vehicul per mașină
    for masina in coordinator.data.get(DATA_MASINI) or []:
        car_id = masina.get("car_id")
        nr = masina.get("nr_inmatriculare")
        if car_id and nr:
            entities.append(VehiculSensor(coordinator, entry, uid, car_id, nr))

    _LOGGER.info(
        "[Pago:Sensor] Creez %d senzori pentru user %s",
        len(entities), uid,
    )
    async_add_entities(entities, update_before_add=True)


# ──────────────────────────────────────────────
# LicentaNecesaraSensor
# ──────────────────────────────────────────────
class LicentaNecesaraSensor(PagoEntity, SensorEntity):
    """Senzor afișat când licența nu este validă."""

    _attr_icon = "mdi:license"

    def __init__(
        self,
        coordinator: PagoCoordinator,
        config_entry: ConfigEntry,
        uid: int,
    ) -> None:
        """Inițializează."""
        super().__init__(coordinator, config_entry)
        self._attr_name = "Licență necesară"
        self._attr_unique_id = f"{DOMAIN}_licenta_{uid}"
        self._custom_entity_id = f"sensor.{DOMAIN}_{uid}_licenta_necesara"

    @property
    def native_value(self) -> str:
        """Starea senzorului."""
        mgr = self.hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
        if mgr is None:
            return "Licență necesară"
        status = mgr.status
        if status == "trial":
            return f"Evaluare ({mgr.trial_days_remaining} zile)"
        if status == "expired":
            return "Licență expirată"
        return "Licență necesară"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Atribute licență."""
        mgr = self.hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
        if mgr is None:
            return {}
        return mgr.as_dict()


# ──────────────────────────────────────────────
# 1. Date utilizator (profil + abonament)
# ──────────────────────────────────────────────
class ContPagoSensor(PagoEntity, SensorEntity):
    """Date utilizator — profil + abonament, totul grupat."""

    _attr_icon = "mdi:account"

    def __init__(
        self,
        coordinator: PagoCoordinator,
        config_entry: ConfigEntry,
        uid: int,
    ) -> None:
        """Inițializează."""
        super().__init__(coordinator, config_entry)
        self._attr_name = "Date utilizator"
        self._attr_unique_id = f"{DOMAIN}_{uid}_cont"
        self._custom_entity_id = f"sensor.{DOMAIN}_{uid}_cont"

    @property
    def native_value(self) -> str:
        """Starea: numele complet al contului."""
        if not self._license_valid:
            return "Licență necesară"
        data = self.coordinator.data or {}
        profil = data.get(DATA_PROFIL) or {}
        nume = profil.get("nume") or ""
        prenume = profil.get("prenume") or ""
        full = f"{nume} {prenume}".strip()
        return full or profil.get("email", "Necunoscut")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Atribute: profil + abonament."""
        if not self._license_valid:
            return {"Licență": "necesară"}

        data = self.coordinator.data or {}
        profil = data.get(DATA_PROFIL) or {}
        abon = data.get(DATA_ABONAMENT) or {}

        attrs: dict[str, Any] = {}

        # ── Profil ──
        if profil.get("pos_user_id"):
            attrs["ID utilizator"] = str(profil["pos_user_id"])
        if profil.get("nume"):
            attrs["Nume"] = profil["nume"]
        if profil.get("prenume"):
            attrs["Prenume"] = profil["prenume"]
        if profil.get("telefon"):
            attrs["Telefon"] = profil["telefon"]
        if profil.get("email"):
            attrs["Email"] = profil["email"]
        if profil.get("cnp"):
            attrs["CNP"] = profil["cnp"]
        if profil.get("adresa"):
            attrs["Adresă"] = profil["adresa"]

        # ── Abonament ──
        attrs["--- Abonament"] = ""
        if abon.get("activ") is not None:
            attrs["Abonament activ"] = "Da" if abon["activ"] else "Nu"
        if abon.get("subscription_id"):
            attrs["ID abonament"] = str(abon["subscription_id"])
        if abon.get("inceput"):
            attrs["Început"] = abon["inceput"]
        if abon.get("sfarsit"):
            attrs["Sfârșit"] = abon["sfarsit"]
        if abon.get("perioada_zile"):
            attrs["Perioadă (zile)"] = abon["perioada_zile"]
        if abon.get("pret"):
            attrs["Preț"] = abon["pret"]

        total = abon.get("facturi_lunare") or 0
        folosite = abon.get("plati_folosite") or 0
        attrs["Facturi lunare"] = total
        attrs["Plăți folosite"] = folosite
        attrs["Plăți rămase"] = max(0, total - folosite)

        return attrs


# ──────────────────────────────────────────────
# 2. Carduri
# ──────────────────────────────────────────────
class CarduriSensor(PagoEntity, SensorEntity):
    """Carduri — număr carduri active + detalii în atribute."""

    _attr_icon = "mdi:credit-card-multiple"

    def __init__(
        self,
        coordinator: PagoCoordinator,
        config_entry: ConfigEntry,
        uid: int,
    ) -> None:
        """Inițializează."""
        super().__init__(coordinator, config_entry)
        self._attr_name = "Carduri Pago"
        self._attr_unique_id = f"{DOMAIN}_{uid}_carduri"
        self._custom_entity_id = f"sensor.{DOMAIN}_{uid}_carduri"

    @property
    def native_value(self) -> int | str:
        """Starea: număr carduri active."""
        if not self._license_valid:
            return "Licență necesară"
        carduri = self.coordinator.data.get(DATA_CARDURI) or []
        return sum(1 for c in carduri if c.get("activ"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Atribute: lista de carduri."""
        if not self._license_valid:
            return {"Licență": "necesară"}
        carduri = self.coordinator.data.get(DATA_CARDURI) or []
        attrs: dict[str, Any] = {
            "Total carduri": len(carduri),
        }
        for c in carduri:
            alias = c.get("alias") or ""
            tip = c.get("tip_card") or ""
            last4 = c.get("last4") or ""
            # Cheie: "Card {alias} {tip} ****{last4}" (fără alias dacă e gol)
            parts = ["Card"]
            if alias:
                parts.append(alias)
            if tip:
                parts.append(tip)
            if last4:
                parts.append(f"****{last4}")
            key = " ".join(parts)
            stare = "Activ" if c.get("activ") else "Inactiv"
            if c.get("default"):
                stare += " (Default)"
            attrs[key] = stare
        return attrs


# ──────────────────────────────────────────────
# 3. Cont furnizor (locații + detalii facturare)
# ──────────────────────────────────────────────
class ContFurnizorSensor(PagoEntity, SensorEntity):
    """Cont furnizor — locațiile de facturare ale unui furnizor."""

    _attr_icon = "mdi:receipt-text"

    def __init__(
        self,
        coordinator: PagoCoordinator,
        config_entry: ConfigEntry,
        uid: int,
        furnizor_raw: str,
    ) -> None:
        """Inițializează."""
        super().__init__(coordinator, config_entry)
        self._furnizor_raw = furnizor_raw
        slug = _furnizor_slug(furnizor_raw)
        display = _furnizor_display(furnizor_raw)
        self._attr_name = f"Cont {display}"
        self._attr_unique_id = f"{DOMAIN}_{uid}_cont_{slug}"
        self._custom_entity_id = f"sensor.{DOMAIN}_{uid}_cont_{slug}"

    def _conturi_furnizor(self) -> list[dict[str, Any]]:
        """Locațiile (conturile) pentru acest furnizor."""
        conturi = self.coordinator.data.get(DATA_CONTURI_FACTURI) or []
        filtered = [
            c for c in conturi
            if c.get("furnizor") == self._furnizor_raw
        ]
        filtered.sort(key=lambda c: c.get("locatie") or "")
        return filtered

    @property
    def native_value(self) -> int | str:
        """Starea: număr locații active la acest furnizor."""
        if not self._license_valid:
            return "Licență necesară"
        return len(self._conturi_furnizor())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Atribute: locațiile de facturare — format compact."""
        if not self._license_valid:
            return {"Licență": "necesară"}

        conturi = self._conturi_furnizor()
        if not conturi:
            return {"Locații": "niciuna"}

        attrs: dict[str, Any] = {}

        for i, c in enumerate(conturi, 1):
            nume = c.get("locatie") or "—"
            suma = c.get("ultima_plata_suma")
            data = _data_completa(c.get("ultima_plata_data"))

            if suma is not None:
                attrs[f"Facturat pe {data} ({nume})"] = f"{suma:.2f} lei"
            else:
                attrs[f"Cont {i} ({nume})"] = "fără plăți"

        return attrs


# ──────────────────────────────────────────────
# 4. Arhivă plăți per furnizor
# ──────────────────────────────────────────────
class ArhivaPlatiFurnizorSensor(PagoEntity, SensorEntity):
    """Arhivă plăți — per furnizor, din plati_recente, anul curent."""

    _attr_icon = "mdi:cash-check"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = CURRENCY_LEI
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator: PagoCoordinator,
        config_entry: ConfigEntry,
        uid: int,
        furnizor_raw: str,
    ) -> None:
        """Inițializează."""
        super().__init__(coordinator, config_entry)
        self._furnizor_raw = furnizor_raw
        slug = _furnizor_slug(furnizor_raw)
        display = _furnizor_display(furnizor_raw)
        self._attr_name = f"Arhivă plăți {display}"
        self._attr_unique_id = f"{DOMAIN}_{uid}_plati_{slug}"
        self._custom_entity_id = f"sensor.{DOMAIN}_{uid}_plati_{slug}"

    def _plati_furnizor(self) -> list[dict[str, Any]]:
        """Plățile din anul curent pentru acest furnizor, sortate cronologic."""
        plati = self.coordinator.data.get(DATA_PLATI_RECENTE) or []
        an_str = str(datetime.now().year)
        filtered = [
            p for p in plati
            if p.get("furnizor") == self._furnizor_raw
            and str(p.get("data", "")).startswith(an_str)
        ]
        # Sortare după dată — cele mai vechi primele
        filtered.sort(key=lambda p: p.get("data") or "0000-00-00")
        return filtered

    @property
    def native_value(self) -> float | None:
        """Starea: sumă totală plătită la acest furnizor anul curent."""
        if not self._license_valid:
            return None
        plati = self._plati_furnizor()
        if not plati:
            return None
        return round(
            sum((p.get("suma_platita") or 0) for p in plati), 2
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Atribute: plățile la acest furnizor, grupate pe luni."""
        if not self._license_valid:
            return {"Licență": "necesară"}

        plati = self._plati_furnizor()
        if not plati:
            return {"Plăți": "niciuna"}

        display = _furnizor_display(self._furnizor_raw)
        total = round(
            sum((p.get("suma_platita") or 0) for p in plati), 2
        )

        attrs: dict[str, Any] = {
            f"Total plăți {display}": f"{total:.2f} lei",
        }

        # Afișăm ultimele 12 plăți (cele mai recente), totalul rămâne pe toate
        plati_afisate = plati[-12:] if len(plati) > 12 else plati
        for p in plati_afisate:
            suma = p.get("suma_platita") or 0
            locatie = p.get("locatie") or "—"
            data = _data_completa(p.get("data"))
            attrs[f"Plata {display} pe {data} ({locatie})"] = (
                f"{suma:.2f} lei"
            )

        return attrs


# ──────────────────────────────────────────────
# 5. Facturi emise
# ──────────────────────────────────────────────
class FacturiEmiseSensor(PagoEntity, SensorEntity):
    """Facturi emise — facturile curente de plată."""

    _attr_icon = "mdi:file-document-alert"

    def __init__(
        self,
        coordinator: PagoCoordinator,
        config_entry: ConfigEntry,
        uid: int,
    ) -> None:
        """Inițializează."""
        super().__init__(coordinator, config_entry)
        self._attr_name = "Facturi emise"
        self._attr_unique_id = f"{DOMAIN}_{uid}_facturi_emise"
        self._custom_entity_id = f"sensor.{DOMAIN}_{uid}_facturi_emise"

    def _facturi(self) -> list[dict[str, Any]]:
        """Facturile sortate după scadență (cele mai urgente primele)."""
        facturi = self.coordinator.data.get(DATA_FACTURI_SUMAR) or []
        return sorted(facturi, key=lambda f: f.get("scadenta") or "9999-99-99")

    @property
    def native_value(self) -> int | str:
        """Starea: numărul total de facturi emise."""
        if not self._license_valid:
            return "Licență necesară"
        return len(self._facturi())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Atribute: lista facturilor emise — sumă + scadență."""
        if not self._license_valid:
            return {"Licență": "necesară"}

        facturi = self._facturi()
        if not facturi:
            return {"Facturi": "niciuna"}

        total_datorat = round(
            sum((f.get("suma_datorata") or 0) for f in facturi), 2
        )

        today = datetime.now().strftime("%Y-%m-%d")
        restante = [
            f for f in facturi
            if f.get("scadenta") and f["scadenta"] <= today
        ]

        attrs: dict[str, Any] = {
            "Total facturi": len(facturi),
            "Sumă totală datorată": f"{total_datorat} lei",
            "Facturi restante": len(restante),
        }

        for i, f in enumerate(facturi, 1):
            suma = f.get("suma_datorata") or 0
            scadenta = f.get("scadenta") or ""
            scad_display = _data_completa(scadenta)
            furn = f.get("furnizor_nume") or ""
            locatie = f.get("locatie") or ""

            # Construim descrierea: "Furnizor · Locație" / doar unul / gol
            if furn and locatie:
                desc = f"{furn} · {locatie}"
            elif furn:
                desc = furn
            elif locatie:
                desc = locatie
            else:
                desc = ""

            if desc:
                attrs[f"Factura {i} scadenta pe {scad_display} ({desc})"] = (
                    f"{suma:.2f} lei"
                )
            else:
                attrs[f"Factura {i} scadenta pe {scad_display}"] = (
                    f"{suma:.2f} lei"
                )

        return attrs


# ──────────────────────────────────────────────
# 6. Vehicul (per nr. înmatriculare)
# native_value = "OK" / "RCA Expirat" / "ITP Expirat" / "Fără RCA"
# ──────────────────────────────────────────────
class VehiculSensor(PagoEntity, SensorEntity):
    """Vehicul — status RCA + ITP combinat, per nr. înmatriculare."""

    _attr_icon = "mdi:car"

    def __init__(
        self,
        coordinator: PagoCoordinator,
        config_entry: ConfigEntry,
        uid: int,
        car_id: int,
        nr_inmatriculare: str,
    ) -> None:
        """Inițializează."""
        super().__init__(coordinator, config_entry)
        self._car_id = car_id
        self._nr = nr_inmatriculare
        nr_lower = nr_inmatriculare.lower().replace(" ", "")
        self._attr_name = nr_inmatriculare
        self._attr_unique_id = f"{DOMAIN}_{uid}_{nr_lower}"
        self._custom_entity_id = f"sensor.{DOMAIN}_{uid}_{nr_lower}"

    def _get_masina(self) -> dict[str, Any]:
        """Găsește datele mașinii din coordinator."""
        for m in self.coordinator.data.get(DATA_MASINI) or []:
            if m.get("car_id") == self._car_id:
                return m
        return {}

    @property
    def native_value(self) -> str:
        """Starea: OK dacă totul e valid, altfel primul element expirat."""
        if not self._license_valid:
            return "Licență necesară"
        masina = self._get_masina()
        alerte = masina.get("alerte") or {}

        # Verificăm RCA
        rca_raw = alerte.get("rca_expira")
        rca_zile = _zile_ramase(rca_raw) if rca_raw else None
        rca_expirat = rca_zile is not None and rca_zile < 0
        fara_rca = not rca_raw or rca_zile is None

        # Verificăm ITP
        itp_raw = alerte.get("itp_expira")
        itp_zile = _zile_ramase(itp_raw) if itp_raw else None
        itp_expirat = itp_zile is not None and itp_zile < 0

        # Prioritate: RCA Expirat > ITP Expirat > Fără RCA > OK
        if rca_expirat:
            return "RCA Expirat"
        if itp_expirat:
            return "ITP Expirat"
        if fara_rca:
            return "Fără RCA"
        return "OK"

    @property
    def icon(self) -> str:
        """Pictogramă dinamică."""
        val = self.native_value
        if val == "OK":
            return "mdi:car"
        if val in ("RCA Expirat", "ITP Expirat"):
            return "mdi:car-emergency"
        if val == "Fără RCA":
            return "mdi:car-off"
        return "mdi:car"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Atribute complete ale vehiculului."""
        if not self._license_valid:
            return {"Licență": "necesară"}

        masina = self._get_masina()
        alerte = masina.get("alerte") or {}

        attrs: dict[str, Any] = {
            "Nr. înmatriculare": self._nr,
            "Car ID": str(self._car_id),
        }

        # ── RCA ──
        rca_raw = alerte.get("rca_expira")
        if rca_raw:
            zile_rca = _zile_ramase(rca_raw)
            attrs["RCA expiră"] = rca_raw
            if zile_rca is not None:
                attrs["RCA zile rămase"] = zile_rca if zile_rca >= 0 else "Expirat"
        else:
            attrs["RCA"] = "Fără RCA"

        # ── ITP ──
        itp_raw = alerte.get("itp_expira")
        if itp_raw:
            zile_itp = _zile_ramase(itp_raw)
            attrs["ITP expiră"] = itp_raw
            if zile_itp is not None:
                attrs["ITP zile rămase"] = zile_itp if zile_itp >= 0 else "Expirat"
        else:
            attrs["ITP"] = "Fără ITP"

        # ── Notificări ──
        if alerte.get("rca_notificare_sms") is not None:
            attrs["Notificare SMS RCA"] = (
                "Da" if alerte["rca_notificare_sms"] else "Nu"
            )
        if alerte.get("rca_notificare_email") is not None:
            attrs["Notificare email RCA"] = (
                "Da" if alerte["rca_notificare_email"] else "Nu"
            )

        return attrs
