"""Client API async pentru Pago Plătește."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

import aiohttp

from .const import (
    API_TIMEOUT_DEFAULT,
    API_TIMEOUT_SLOW,
    PAGO_APP_ID,
    PAGO_APP_VERSION,
    PAGO_AUTH_BASIC,
    PAGO_AUTH_ENDPOINT,
    PAGO_BASE_URL,
)

_LOGGER = logging.getLogger(__name__)


class PagoAuthError(Exception):
    """Eroare de autentificare Pago."""


class PagoConnectionError(Exception):
    """Eroare de conexiune Pago."""


class PagoApiClient:
    """Client API async pentru Pago Plătește.

    Convertit din pago_explorer.py (sync/urllib) la async/aiohttp
    pentru utilizare în Home Assistant.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        phone_id: str,
        session_id: str,
    ) -> None:
        """Inițializează clientul API."""
        self._session = session
        self._email = email
        self._password = password
        self._phone_id = phone_id
        self._session_id = session_id
        self._token: str | None = None
        self._token_expiry: float = 0
        self._login_lock = asyncio.Lock()

    # ═══════════════════════════════════════════════════════════════════
    # Autentificare
    # ═══════════════════════════════════════════════════════════════════

    def _headers(self, auth: bool = True) -> dict[str, str]:
        """Construiește headerele standard Pago (identice cu pago_explorer.py)."""
        h: dict[str, str] = {
            "User-Agent": f"Pago/{PAGO_APP_VERSION}",
            "Accept": "application/json",
            "Country": "RO",
            "Accept-Language": "ro",
            "Session-Id": self._session_id,
            "AppId": PAGO_APP_ID,
            "Phone-Id": self._phone_id,
        }
        if auth and self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def async_login(self) -> bool:
        """Autentificare la API-ul Pago.

        Raises:
            PagoAuthError: Credențiale invalide.
            PagoConnectionError: Eroare de rețea.
        """
        headers = self._headers(auth=False)
        headers["Authorization"] = PAGO_AUTH_BASIC
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Phone-Details"] = f"PagoHA;{PAGO_APP_VERSION};HomeAssistant"

        data = {
            "grant_type": "pago",
            "username": self._email,
            "password": self._password,
        }

        try:
            async with asyncio.timeout(API_TIMEOUT_DEFAULT):
                resp = await self._session.post(
                    PAGO_AUTH_ENDPOINT,
                    headers=headers,
                    data=data,
                )
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            raise PagoConnectionError(
                f"Nu mă pot conecta la Pago: {err}"
            ) from err

        if resp.status == 401:
            raise PagoAuthError("Credențiale invalide")
        if resp.status == 400:
            body = await resp.json(content_type=None)
            error = body.get("error_description", "Eroare necunoscută")
            raise PagoAuthError(f"Autentificare eșuată: {error}")
        if resp.status != 200:
            raise PagoConnectionError(
                f"Răspuns neașteptat la login: HTTP {resp.status}"
            )

        body = await resp.json(content_type=None)
        self._token = body.get("access_token")
        expires_in = body.get("expires_in", 3600)
        self._token_expiry = time.time() + expires_in - 60  # 1 min buffer

        if not self._token:
            raise PagoAuthError("Răspunsul nu conține access_token")

        _LOGGER.debug("Pago: login OK, token expiră în %ds", expires_in)
        return True

    async def _ensure_token(self) -> None:
        """Asigură un token valid, re-autentifică dacă e necesar.

        Folosește lock pentru a preveni login-uri paralele
        când mai multe request-uri concurente descoperă token expirat.
        """
        if self._token and time.time() < self._token_expiry:
            return  # Token valid, skip
        async with self._login_lock:
            # Re-verificăm după obținerea lock-ului (alt task a putut face login)
            if self._token and time.time() < self._token_expiry:
                return
            await self.async_login()

    # ═══════════════════════════════════════════════════════════════════
    # HTTP helpers
    # ═══════════════════════════════════════════════════════════════════

    async def _get(
        self, path: str, timeout: int = API_TIMEOUT_DEFAULT
    ) -> tuple[int, Any]:
        """GET request cu token automat."""
        await self._ensure_token()
        url = f"{PAGO_BASE_URL}{path}"
        try:
            async with asyncio.timeout(timeout):
                resp = await self._session.get(url, headers=self._headers())
                status = resp.status
                text = await resp.text()
                if text.strip():
                    import json

                    try:
                        body = json.loads(text)
                    except json.JSONDecodeError:
                        body = text
                else:
                    body = None
                return status, body
        except asyncio.TimeoutError:
            _LOGGER.debug("Pago: timeout pe %s (%ds)", path, timeout)
            return 0, {"error": f"Timeout ({timeout}s)"}
        except aiohttp.ClientError as err:
            _LOGGER.debug("Pago: eroare rețea pe %s: %s", path, err)
            return 0, {"error": str(err)}

    @staticmethod
    def _unwrap(resp: Any) -> Any:
        """Dezambalează PagoResponse wrapper {error, errorMsg, data}."""
        if isinstance(resp, dict) and "data" in resp and "error" in resp:
            return resp["data"]
        return resp

    # ═══════════════════════════════════════════════════════════════════
    # Metode fetch date
    # ═══════════════════════════════════════════════════════════════════

    async def async_fetch_profil(self) -> dict[str, Any] | None:
        """Profil utilizator — /authentication/uaa/v1.00/user_profile.

        Exact ca în pago_explorer.py fetch_profil().
        """
        status, data = await self._get("/authentication/uaa/v1.00/user_profile")
        if status != 200 or not isinstance(data, dict):
            _LOGGER.debug("Pago: user_profile status=%d", status)
            return None
        return {
            "email": data.get("email"),
            "nume": data.get("firstName"),
            "prenume": data.get("lastName"),
            "telefon": data.get("phoneNumber"),
            "creat_la": data.get("createdAt"),
            "pos_user_id": data.get("posUserId"),
        }

    async def async_fetch_masini(self) -> list[dict[str, Any]]:
        """Mașini cu alerte — /notification_v1_1/details/cars.

        Exact ca în pago_explorer.py fetch_masini().
        """
        status, data = await self._get("/notification_v1_1/details/cars")
        if status != 200 or not isinstance(data, list):
            _LOGGER.debug("Pago: details/cars status=%d", status)
            return []

        masini = []
        for car in data:
            m: dict[str, Any] = {
                "car_id": car.get("carId"),
                "nr_inmatriculare": car.get("registrationNumber"),
                "incomplet": car.get("incomplete", False),
                "alerte_ascunse": car.get("alertHide", False),
                "alerte": {},
            }
            for detail in car.get("details", []):
                tip = detail.get("detailType", "")
                val = detail.get("valueTimestamp")
                data_str = None
                if val and isinstance(val, (int, float)) and val > 0:
                    data_str = self._ts(val)

                notif = detail.get("notificationSettings") or {}

                if tip == "END_VALIDITY_RCA":
                    m["alerte"]["rca_expira"] = data_str
                    m["alerte"]["rca_notificare_sms"] = notif.get("notifyBySms", False)
                    m["alerte"]["rca_notificare_email"] = notif.get("notifyByEmail", False)
                elif tip == "END_VALIDITY_ITP":
                    m["alerte"]["itp_expira"] = data_str
                elif tip == "END_VALIDITY_VINIETA":
                    m["alerte"]["vinieta_expira"] = data_str
                elif tip == "END_VALIDITY_ROVINIETA":
                    m["alerte"]["rovinieta_expira"] = data_str
                elif tip == "END_VALIDITY_CASCO":
                    m["alerte"]["casco_expira"] = data_str
                elif tip == "CUSTOM":
                    name = detail.get("detailCustomName", "custom")
                    m["alerte"][f"custom_{name}"] = data_str
                else:
                    m["alerte"][tip.lower()] = data_str

            masini.append(m)
        return masini

    async def async_fetch_abonament(self) -> dict[str, Any] | None:
        """Abonament — /pago-freemium/subscription/active.

        Exact ca în pago_explorer.py fetch_abonament().
        """
        status, data = await self._get("/pago-freemium/subscription/active")
        if status != 200 or not isinstance(data, dict):
            return None
        return {
            "activ": data.get("active", False),
            "subscription_id": data.get("subscriptionId"),
            "inceput": data.get("availabilityStart"),
            "sfarsit": data.get("availabilityEnd"),
            "grace_end": data.get("graceEnd"),
            "perioada_zile": data.get("period"),
            "pret": data.get("amount"),
            "facturi_lunare": data.get("monthlyInvoices"),
            "plati_folosite": data.get("usedPayments"),
            "luna_curenta_start": data.get("currentMonthStart"),
            "luna_curenta_sfarsit": data.get("currentMonthEnd"),
        }

    async def async_fetch_carduri(self) -> list[dict[str, Any]]:
        """Carduri — /payment/cards.

        Exact ca în pago_explorer.py fetch_carduri().
        """
        status, data = await self._get("/payment/cards")
        if status != 200 or not isinstance(data, list):
            return []
        return [
            {
                "id": c.get("id"),
                "alias": c.get("alias"),
                "last4": c.get("last4"),
                "tip_card": c.get("cardType"),
                "procesor": c.get("paymentProcessor"),
                "activ": c.get("active"),
                "default": c.get("defaultCard"),
            }
            for c in data
        ]

    async def async_fetch_roviniete(self) -> list[dict[str, Any]]:
        """Roviniete per mașină. Endpoint lent — verifică CNAIR."""
        status, data = await self._get(
            "/pago-vignette/vignette/", timeout=API_TIMEOUT_SLOW
        )
        if status != 200:
            _LOGGER.debug("Pago: roviniete status=%d", status)
            return []
        inner = self._unwrap(data)
        if not isinstance(inner, list):
            return []

        result = []
        for v in inner:
            interval = v.get("nextVignetteStartInterval") or {}
            result.append(
                {
                    "car_id": v.get("carId"),
                    "nr_inmatriculare": v.get("registrationNumber"),
                    "vin": v.get("vin"),
                    "detalii": v.get("details"),
                    "logo": v.get("logoUrl"),
                    "categorie": v.get("vehicleCategory"),
                    "complet": v.get("carCompleted", False),
                    "interval_urmator": {
                        "de_la": self._ts(interval.get("fromDate")),
                        "pana_la": self._ts(interval.get("toDate")),
                    }
                    if interval
                    else None,
                    "roviniete_active": v.get("vignettes", []),
                }
            )
        return result

    async def async_fetch_taxa_pod(self) -> list[dict[str, Any]]:
        """Taxa de pod per mașină. Endpoint lent."""
        status, data = await self._get(
            "/pago-bridge-toll/bridge-toll/", timeout=API_TIMEOUT_SLOW
        )
        if status != 200:
            _LOGGER.debug("Pago: taxa_pod status=%d", status)
            return []
        inner = self._unwrap(data)
        if not isinstance(inner, list):
            return []

        return [
            {
                "car_id": v.get("carId"),
                "nr_inmatriculare": v.get("registrationNumber"),
                "vin": v.get("vin"),
                "categorie": v.get("vehicleCategory"),
                "are_taxa_pod": v.get("hasBridgeTollsIssued", False),
            }
            for v in inner
        ]

    async def async_fetch_facturi(
        self,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Facturi curente + conturi furnizori.

        1. /sdk/bills/accounts/summary → facturi emise (sumă + scadență).
           NOTĂ: endpoint-ul ierarhic (Account → Location → Invoice) cu
           furnizor + locație per factură NU este accesibil pe pago.cloud.
           Bills SDK-ul din aplicație folosește un host intern separat.
        2. /payment/payment-details-v2 → conturi furnizori din plăți.
        """
        facturi_sumar: list[dict[str, Any]] = []

        # ── 1. Facturi emise: /sdk/bills/accounts/summary ──
        s1, d1 = await self._get("/sdk/bills/accounts/summary")
        inner = self._unwrap(d1) if s1 == 200 and isinstance(d1, dict) else {}
        if not isinstance(inner, dict):
            inner = {}
        for b in inner.get("billsList") or []:
            facturi_sumar.append({
                "suma_datorata": b.get("dueAmount"),
                "scadenta": self._format_date_str(b.get("dueDate")),
            })

        # ── 2. Conturi furnizori din plăți INVOICE ──
        s2, d2 = await self._get(
            "/payment/payment-details-v2?paymentEntityType=INVOICE&size=100&page=0"
        )
        conturi: dict[int, dict[str, Any]] = {}
        if s2 == 200 and isinstance(d2, list):
            for p in d2:
                inv = p.get("invoice") or {}
                lid = inv.get("locationId")
                if not lid or lid in conturi:
                    continue
                conturi[lid] = {
                    "location_id": lid,
                    "furnizor": inv.get("providerUri"),
                    "furnizor_nume": self._provider_display_name(
                        inv.get("providerUri")
                    ),
                    "furnizor_logo": inv.get("providerImgUrl"),
                    "locatie": inv.get("locationAlias"),
                    "tip_locatie": inv.get("locationType"),
                    "ultima_plata_suma": p.get("paidAmount"),
                    "ultima_plata_data": self._ts(p.get("paymentTimestamp")),
                    "auto_plata": p.get("autoPayment", False),
                }

        conturi_lista = sorted(
            conturi.values(), key=lambda x: x.get("locatie") or ""
        )
        return facturi_sumar, conturi_lista

    async def async_fetch_plati_recente(
        self, count: int = 20
    ) -> list[dict[str, Any]]:
        """Ultimele N plăți (toate tipurile)."""
        status, data = await self._get(
            f"/payment/payment-details-v2?paymentEntityType=all&size={count}&page=0"
        )
        if status != 200 or not isinstance(data, list):
            return []

        return [
            {
                "id": p.get("id"),
                "suma": p.get("amount"),
                "suma_platita": p.get("paidAmount"),
                "status": p.get("status"),
                "data": self._ts(p.get("paymentTimestamp")),
                "tip": p.get("paymentEntityType"),
                "auto_plata": p.get("autoPayment", False),
                "furnizor": (p.get("invoice") or {}).get("providerUri"),
                "furnizor_logo": (p.get("invoice") or {}).get("providerImgUrl"),
                "locatie": (p.get("invoice") or {}).get("locationAlias"),
            }
            for p in data
        ]

    async def async_fetch_all(self) -> dict[str, Any]:
        """Aduce toate datele, structurate pentru coordinator.

        Fiecare endpoint e apelat independent — un timeout/eroare
        pe un endpoint NU blochează celelalte date.
        """
        # Pre-autentificare O SINGURĂ DATĂ înainte de fetch-urile paralele
        # (previne login-uri multiple concurente)
        await self._ensure_token()

        profil = None
        abonament = None
        carduri: list = []
        masini: list = []
        facturi_sumar: list = []
        conturi_facturi: list = []
        plati_recente: list = []

        # Endpoints rapide — în paralel
        try:
            profil, masini, abonament, carduri = await asyncio.gather(
                self.async_fetch_profil(),
                self.async_fetch_masini(),
                self.async_fetch_abonament(),
                self.async_fetch_carduri(),
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Pago: eroare la fetch endpoint-uri rapide", exc_info=True)

        # Facturi + plăți — în paralel
        try:
            (facturi_sumar, conturi_facturi), plati_recente = await asyncio.gather(
                self.async_fetch_facturi(),
                self.async_fetch_plati_recente(),
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Pago: eroare la fetch facturi/plăți", exc_info=True)

        # NOTĂ: roviniete și taxa_pod sunt excluse din ciclul de fetch
        # deoarece verificarea CNAIR per mașină durează ~30s × N mașini,
        # cauzând latență inacceptabilă pe coordinator update.

        return {
            "profil": profil or {},
            "abonament": abonament or {},
            "carduri": carduri or [],
            "masini": masini or [],
            "facturi_sumar": facturi_sumar or [],
            "conturi_facturi": conturi_facturi or [],
            "plati_recente": plati_recente or [],
        }

    # ═══════════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def _ts(val: int | float | None) -> str | None:
        """Timestamp milisecunde → YYYY-MM-DD HH:MM."""
        if not val or not isinstance(val, (int, float)):
            return None
        try:
            return datetime.fromtimestamp(val / 1000).strftime("%Y-%m-%d %H:%M")
        except (ValueError, OSError):
            return str(val)

    @staticmethod
    def _format_date_str(s: str | None) -> str | None:
        """Convertește date string din diverse formate Pago."""
        if not s or not isinstance(s, str):
            return None
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y%m%d"):
            try:
                return datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return s

    @staticmethod
    def _provider_display_name(uri: str | None) -> str | None:
        """'rds.crawler' → 'RDS', 'engie.gas' → 'Engie Gas'."""
        if not uri:
            return None
        name = uri.split(".")[0] if "." in uri else uri
        return name.replace("_", " ").replace("-", " ").title()
