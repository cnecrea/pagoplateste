"""Constante pentru integrarea Pago Plătești."""
from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

# ═══════════════════════════════════════════════════════════════════════
# Identificare integrare
# ═══════════════════════════════════════════════════════════════════════

DOMAIN: Final = "pagoplateste"
PLATFORMS: list[Platform] = [Platform.SENSOR]

# ═══════════════════════════════════════════════════════════════════════
# Chei configurare
# ═══════════════════════════════════════════════════════════════════════

CONF_EMAIL: Final = "email"
CONF_PASSWORD: Final = "password"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_POS_USER_ID: Final = "pos_user_id"
CONF_LICENSE_KEY: Final = "license_key"
CONF_UPDATE_INTERVAL: Final = "scan_interval"

# ═══════════════════════════════════════════════════════════════════════
# Licențiere
# ═══════════════════════════════════════════════════════════════════════

LICENSE_DATA_KEY: Final = "pagoplateste_license_manager"
LICENSE_PURCHASE_URL: Final = "https://hubinteligent.org/licenta/pagoplateste"

# ═══════════════════════════════════════════════════════════════════════
# Pago API
# ═══════════════════════════════════════════════════════════════════════

PAGO_BASE_URL: Final = "https://pago.cloud"
PAGO_AUTH_ENDPOINT: Final = f"{PAGO_BASE_URL}/authentication/uaa/oauth/token"
PAGO_AUTH_BASIC: Final = "Basic cGFnby1tb2JpbGUtYXBwOnBhZ28tbW9iaWxlLWFwcC1zZWNyZXQ="
PAGO_APP_ID: Final = "bed83d2a-6287-4e6c-9ce1-e7a49d4f2a43"
PAGO_APP_VERSION: Final = "4.2.0"

# ═══════════════════════════════════════════════════════════════════════
# Intervale actualizare
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_SCAN_INTERVAL: Final = 3600  # 1 oră
MIN_SCAN_INTERVAL: Final = 3600      # 1 oră minim
MAX_SCAN_INTERVAL: Final = 86400     # 24 ore maxim

# Timeout-uri API (secunde)
API_TIMEOUT_DEFAULT: Final = 15
API_TIMEOUT_SLOW: Final = 60  # roviniete, taxa pod — verifică CNAIR per mașină

# ═══════════════════════════════════════════════════════════════════════
# Chei date coordinator
# ═══════════════════════════════════════════════════════════════════════

DATA_PROFIL: Final = "profil"
DATA_ABONAMENT: Final = "abonament"
DATA_CARDURI: Final = "carduri"
DATA_MASINI: Final = "masini"
## EXCLUSE din ciclul de fetch (latență CNAIR ~30s × N mașini):
# DATA_ROVINIETE: Final = "roviniete"
# DATA_TAXA_POD: Final = "taxa_pod"
DATA_FACTURI_SUMAR: Final = "facturi_sumar"
DATA_CONTURI_FACTURI: Final = "conturi_facturi"
DATA_PLATI_RECENTE: Final = "plati_recente"

# ═══════════════════════════════════════════════════════════════════════
# Atribuire
# ═══════════════════════════════════════════════════════════════════════

ATTRIBUTION: Final = "Date furnizate de Pago Plătești"
MANUFACTURER: Final = "Pago"
MODEL_ACCOUNT: Final = "Cont Pago"
MODEL_CAR: Final = "Vehicul"
