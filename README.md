# Pago Plătește — Integrare Home Assistant

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.11%2B-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/cnecrea/pagoplateste)](https://github.com/cnecrea/pagoplateste/releases)
[![GitHub Stars](https://img.shields.io/github/stars/cnecrea/pagoplateste?style=flat&logo=github)](https://github.com/cnecrea/pagoplateste/stargazers)
[![Instalări](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/cnecrea/pagoplateste/main/statistici/shields/descarcari.json)](https://github.com/cnecrea/pagoplateste)
[![Ultima versiune](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/cnecrea/pagoplateste/main/statistici/shields/ultima_release.json)](https://github.com/cnecrea/pagoplateste/releases/latest)

Integrare custom pentru [Home Assistant](https://www.home-assistant.io/) care monitorizează contul [Pago Plătește](https://www.pagoplateste.ro/) — carduri, vehicule (RCA, ITP), facturi emise, conturi furnizori și plăți recente, toate prin API-ul aplicației mobile Pago.

Oferă senzori dedicați pentru profil și abonament, carduri active, vehicule cu alerte RCA/ITP, facturi emise cu scadențe, conturi de facturare per furnizor și arhivă plăți. Formatare completă în limba română cu date calendaristice și sume în lei.

---

## Ce face integrarea

- **Profil și abonament** — date cont, plăți rămase din abonament, perioadă activă
- **Carduri** — lista cardurilor de plată (tip, alias, activ/inactiv, default)
- **Vehicule** — per număr de înmatriculare, cu alertă RCA expirat, ITP expirat, zile rămase
- **Facturi emise** — lista facturilor curente de la furnizori, cu sumă totală datorată și scadențe
- **Conturi furnizori** — locațiile de facturare per furnizor, cu ultima plată și sumă
- **Arhivă plăți** — plățile efectuate la fiecare furnizor (anul curent), cu total per furnizor
- **Licențiere** — sistem de licențe cu perioadă de evaluare, activare online, heartbeat periodic
- **Reconfigurare fără reinstalare** — OptionsFlow pentru modificarea credențialelor

---

## Sursa datelor

Datele vin prin API-ul aplicației mobile Pago Plătește (`pago.cloud`), care expune endpoint-uri REST pentru:

| Endpoint | Descriere |
|----------|-----------|
| `/authentication/uaa/v1.00/user_profile` | Profil utilizator (nume, email, telefon) |
| `/pago-freemium/subscription/active` | Abonament activ (perioadă, plăți rămase) |
| `/payment/cards` | Carduri de plată (tip, alias, activ, default) |
| `/notification_v1_1/details/cars` | Vehicule cu alerte (RCA, ITP, vinieta, CASCO) |
| `/sdk/bills/accounts/summary` | Facturi emise (sumă datorată + scadență) |
| `/payment/payment-details-v2?paymentEntityType=INVOICE` | Conturi furnizori (locații de facturare) |
| `/payment/payment-details-v2?paymentEntityType=all` | Plăți recente (toate tipurile) |

Autentificarea se face cu email + parolă prin endpoint-ul OAuth2 Pago (grant_type=pago). Token-ul expirat este reînnoit automat.

---

## Instalare

### HACS (recomandat)

1. Deschide HACS în Home Assistant
2. Click pe cele 3 puncte (⋮) din colțul dreapta sus → **Custom repositories**
3. Adaugă URL-ul: `https://github.com/cnecrea/pagoplateste`
4. Categorie: **Integration**
5. Click **Add** → găsește „Pago Plătește" → **Install**
6. Restartează Home Assistant

### Manual

1. Copiază folderul `custom_components/pagoplateste/` în directorul `config/custom_components/` din Home Assistant
2. Restartează Home Assistant

---

## Configurare

### Pasul 1 — Adaugă integrarea

1. **Setări** → **Dispozitive și Servicii** → **Adaugă Integrare**
2. Caută „**Pago Plătește**"
3. Completează formularul:

| Câmp | Descriere | Implicit |
|------|-----------|----------|
| **Email** | Adresa de email a contului Pago | — |
| **Parolă** | Parola contului Pago | — |
| **Interval actualizare** | Secunde între interogările API | `3600` (1 oră) |

### Pasul 2 — Reconfigurare (opțional)

Setările pot fi modificate după instalare, fără a șterge integrarea:

1. **Setări** → **Dispozitive și Servicii** → click pe **Pago Plătește**
2. Click pe **Configurare** (⚙️)
3. Alege **Reconfigurare cont** sau **Licență**
4. Modifică setările dorite → **Salvează**

Detalii complete în [SETUP.md](SETUP.md).

---

## Entități create

Integrarea creează un **device** „Pago Plătește (email)" cu următorii senzori:

### Senzori de bază

| Entitate | Descriere | Valoare principală |
|----------|-----------|-------------------|
| `Date utilizator` | Profil + abonament (plăți rămase, perioadă) | Numele complet |
| `Carduri Pago` | Carduri de plată active | Număr carduri active |
| `Facturi emise` | Facturi curente de la furnizori | Număr facturi |

### Senzori dinamici (creați automat)

| Entitate | Descriere | Valoare principală | Când apare |
|----------|-----------|-------------------|------------|
| `Cont {Furnizor}` | Locații de facturare + ultima plată | Număr locații | Per furnizor unic din conturi facturi |
| `Arhivă plăți {Furnizor}` | Plățile la furnizor (anul curent) | Total plătit (lei) | Per furnizor unic din plăți recente |
| `{Nr. înmatriculare}` | Vehicul cu status RCA/ITP | OK / RCA Expirat / ITP Expirat | Per mașină din cont |

---

### Senzor: Date utilizator

**Valoare principală**: numele complet al contului

**Atribute**:
```yaml
ID utilizator: "123456"
Nume: "Popescu"
Prenume: "Ion"
Telefon: "+40712345678"
Email: "ion@email.ro"
--- Abonament: ""
Abonament activ: "Da"
Început: "2026-01-01"
Sfârșit: "2026-04-01"
Perioadă (zile): 90
Plăți folosite: 3
Plăți rămase: 27
```

### Senzor: Carduri Pago

**Valoare principală**: numărul cardurilor active

**Atribute** (format compact, o linie per card):
```yaml
Total carduri: 3
Card Crypto.com VISA ****3198: "Activ"
Card Revolut MASTERCARD ****7354: "Activ"
Card MASTERCARD ****0093: "Activ (Default)"
```

Dacă alias-ul cardului e gol, se omite din cheie. Cardul implicit e marcat cu `(Default)`.

### Senzor: Facturi emise

**Valoare principală**: numărul total de facturi emise

**Atribute**:
```yaml
Total facturi: 3
Sumă totală datorată: "150.00 lei"
Facturi restante: 1
Factura 1 scadenta pe 15 martie 2026: "75.50 lei"
Factura 2 scadenta pe 28 martie 2026: "42.30 lei"
Factura 3 scadenta pe 10 aprilie 2026: "32.20 lei"
```

### Senzor: Cont {Furnizor}

**Valoare principală**: număr locații active la furnizor (anul curent)

**Atribute**:
```yaml
Facturat pe 5 martie 2026 (Apartament): "125.50 lei"
Facturat pe 12 februarie 2026 (Casă): "89.20 lei"
```

### Senzor: Arhivă plăți {Furnizor}

**Valoare principală**: total plătit la furnizor (lei, anul curent)

**Atribute**:
```yaml
Total plati Engie Gas: "450.80 lei"
Plata Engie Gas pe 5 martie 2026 (Apartament): "125.50 lei"
Plata Engie Gas pe 4 februarie 2026 (Apartament): "98.30 lei"
Plata Engie Gas pe 6 ianuarie 2026 (Casă): "227.00 lei"
```

### Senzor: Vehicul ({Nr. înmatriculare})

**Valoare principală**: `OK` / `RCA Expirat` / `ITP Expirat` / `Fără RCA`

Prioritate: RCA Expirat > ITP Expirat > Fără RCA > OK

**Pictogramă dinamică**:
- `mdi:car` — OK
- `mdi:car-emergency` — RCA/ITP Expirat
- `mdi:car-off` — Fără RCA

**Atribute**:
```yaml
Nr. înmatriculare: "B 123 ABC"
Car ID: "12345"
RCA expiră: "2026-08-15 10:00"
RCA zile rămase: 140
ITP expiră: "2027-03-20 10:00"
ITP zile rămase: 357
Notificare SMS RCA: "Da"
Notificare email RCA: "Da"
```

---

## Exemple de automatizări

### Notificare RCA expirat

```yaml
automation:
  - alias: "Notificare RCA expirat"
    trigger:
      - platform: state
        entity_id: sensor.pagoplateste_123456_b123abc
        to: "RCA Expirat"
    action:
      - service: notify.mobile_app_telefonul_meu
        data:
          title: "RCA Expirat!"
          message: >
            Vehiculul {{ state_attr('sensor.pagoplateste_123456_b123abc', 'Nr. înmatriculare') }}
            are RCA-ul expirat.
```

### Notificare facturi restante

```yaml
automation:
  - alias: "Notificare facturi Pago"
    trigger:
      - platform: numeric_state
        entity_id: sensor.pagoplateste_123456_facturi_emise
        above: 0
    action:
      - service: notify.mobile_app_telefonul_meu
        data:
          title: "Facturi de plată Pago"
          message: >
            Ai {{ states('sensor.pagoplateste_123456_facturi_emise') }} facturi de plată,
            total {{ state_attr('sensor.pagoplateste_123456_facturi_emise', 'Sumă totală datorată') }}.
```

### Card pentru Dashboard

```yaml
type: entities
title: Pago Plătește
entities:
  - entity: sensor.pagoplateste_123456_cont
    name: Cont
  - entity: sensor.pagoplateste_123456_carduri
    name: Carduri
  - entity: sensor.pagoplateste_123456_facturi_emise
    name: Facturi
  - entity: sensor.pagoplateste_123456_b123abc
    name: B 123 ABC
```

---

## Structura fișierelor

```
custom_components/pagoplateste/
├── __init__.py          # Setup/unload integrare (runtime_data pattern, LicenseManager)
├── api.py               # Client API async — login OAuth2, GET cu retry pe token expirat
├── config_flow.py       # ConfigFlow + OptionsFlow (autentificare, licență, reconfigurare)
├── const.py             # Constante, URL-uri API, chei date coordinator
├── coordinator.py       # DataUpdateCoordinator — fetch paralel endpoint-uri Pago
├── diagnostics.py       # Export diagnostic (licență, coordinator, senzori activi)
├── entity.py            # Clasă de bază PagoEntity (entity_id custom, device_info, licență)
├── license.py           # LicenseManager — fingerprint, activare, heartbeat, Ed25519
├── manifest.json        # Metadata integrare
├── sensor.py            # Clase senzor (profil, carduri, vehicule, facturi, furnizori, plăți)
├── strings.json         # Traduceri implicite (engleză)
├── translations/
│   ├── en.json          # Traduceri engleză
│   └── ro.json          # Traduceri române
└── brand/
    ├── icon.png         # Pictogramă integrare
    ├── icon@2x.png      # Pictogramă retina
    ├── logo.png         # Logo integrare
    ├── logo@2x.png      # Logo retina
    ├── dark_icon.png    # Pictogramă dark mode
    ├── dark_icon@2x.png # Pictogramă dark mode retina
    ├── dark_logo.png    # Logo dark mode
    └── dark_logo@2x.png # Logo dark mode retina
```

---

## Cerințe

- **Home Assistant** 2024.x sau mai nou (pattern `entry.runtime_data`)
- **HACS** (opțional, pentru instalare ușoară)
- **Cont Pago Plătește** activ cu email + parolă
- **Dependența Python**: `cryptography>=41.0.0` (pentru verificarea semnăturii Ed25519 a licenței)

---

## Limitări cunoscute

1. **O singură instanță per cont** — dacă încerci să adaugi același email de două ori, vei primi eroare „Acest cont este deja configurat".

2. **Facturi emise fără furnizor** — endpoint-ul `/sdk/bills/accounts/summary` returnează doar sumă + scadență, fără numele furnizorului sau locația. Bills SDK-ul Pago folosește un host intern separat, inaccesibil prin API-ul public.

3. **Roviniete și taxa de pod** — endpoint-urile CNAIR necesită verificare per mașină (~30s per vehicul). Sunt excluse din ciclul de actualizare din cauza latenței. Pot fi adăugate la cerere pe un interval separat.

4. **Interval minim de actualizare** — minimum 1 oră (3600 secunde), maximum 24 ore (86400 secunde), pentru a nu suprasolicita API-ul Pago.

5. **Senzori dinamici** — senzorii per furnizor și per vehicul sunt creați la prima actualizare. Dacă adaugi un vehicul sau furnizor nou în Pago, restartează integrarea pentru a-l detecta.

---

## Susține dezvoltatorul

Dacă ți-a plăcut această integrare și vrei să sprijini munca depusă, **invită-mă la o cafea**!
Contribuția ta ajută la dezvoltarea viitoare a proiectului.

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-Susține%20dezvoltatorul-orange?style=for-the-badge&logo=buy-me-a-coffee)](https://buymeacoffee.com/cnecrea)

---

## Contribuții

Contribuțiile sunt binevenite! Simte-te liber să trimiți un pull request sau să raportezi probleme [aici](https://github.com/cnecrea/pagoplateste/issues).

---

## Suport

Dacă îți place această integrare, oferă-i un ⭐ pe [GitHub](https://github.com/cnecrea/pagoplateste/)!

## Licență

[MIT](LICENSE)
