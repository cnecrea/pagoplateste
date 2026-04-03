# SETUP — Ghid complet de instalare și configurare

Acest ghid detaliază pașii de instalare, configurare inițială, reconfigurare și activare a licenței pentru integrarea **Pago Plătește** în Home Assistant.

---

## Cerințe preliminare

Înainte de instalare, asigură-te că ai:

- **Home Assistant** versiunea 2024.x sau mai nouă (necesită pattern-ul `entry.runtime_data`)
- **Cont Pago Plătește** activ — cel din aplicația mobilă Pago (email + parolă)
- **Licență** validă — [hubinteligent.org/donate?ref=pagoplateste](https://hubinteligent.org/donate?ref=pagoplateste)
- **Conexiune la internet** — integrarea comunică cu serverele Pago pentru date și cu serverul de licențiere

---

## Instalare prin HACS (recomandat)

1. Deschide **HACS** din meniul lateral Home Assistant
2. Navighează la **Integrări**
3. Click pe cele 3 puncte (⋮) din colțul dreapta-sus → **Depozite personalizate** (Custom repositories)
4. Adaugă URL-ul: `https://github.com/cnecrea/pagoplateste`
5. Selectează categoria: **Integrare** (Integration)
6. Click **Adaugă** (Add)
7. Găsește „**Pago Plătește**" în lista de integrări → click **Instalează** (Install)
8. **Restartează Home Assistant** — obligatoriu pentru încărcarea integrării

---

## Instalare manuală

1. Descarcă ultima versiune de pe [GitHub Releases](https://github.com/cnecrea/pagoplateste/releases)
2. Extrage arhiva și copiază folderul `custom_components/pagoplateste/` în directorul `config/custom_components/` al instalării Home Assistant
3. Structura corectă ar trebui să fie:
   ```
   config/
   └── custom_components/
       └── pagoplateste/
           ├── __init__.py
           ├── api.py
           ├── config_flow.py
           ├── const.py
           ├── coordinator.py
           ├── diagnostics.py
           ├── entity.py
           ├── license.py
           ├── manifest.json
           ├── sensor.py
           ├── strings.json
           ├── translations/
           └── brand/
   ```
4. **Restartează Home Assistant**

---

## Configurare inițială

### Pasul 1 — Adaugă integrarea

1. Mergi la **Setări** → **Dispozitive și Servicii** → **Adaugă Integrare**
2. Caută „**Pago Plătește**" (sau „pagoplateste")
3. Completează formularul de autentificare:

| Câmp | Descriere | Valoare implicită |
|------|-----------|-------------------|
| **Email** | Email-ul contului Pago (cel din aplicația mobilă) | — (obligatoriu) |
| **Parolă** | Parola contului Pago | — (obligatoriu) |
| **Interval actualizare** | Câte secunde între actualizări | `3600` (1 oră) |

### Pasul 2 — Validare

La apăsarea butonului „Trimite":

- Integrarea se autentifică la API-ul Pago cu credențialele furnizate
- Dacă autentificarea reușește, se aduce profilul utilizatorului
- Se creează config entry cu titlul = numele complet din profil (sau email-ul, dacă profilul nu conține nume)

### Pasul 3 — Prima actualizare

Imediat după configurare:

- Coordinator-ul aduce toate datele: profil, abonament, carduri, mașini, facturi, conturi furnizori, plăți recente
- Senzorii sunt creați automat — un device „Pago Plătește (email)" cu toți senzorii
- Senzorii dinamici (per furnizor, per vehicul) sunt creați pe baza datelor existente la momentul primei actualizări

### Pasul 4 — Licență

Integrarea necesită o **licență validă** pentru a funcționa complet. Fără licență:
- Se creează doar senzorul `sensor.pagoplateste_{user_id}_licenta` cu valoarea „Licență necesară"
- Toți senzorii normali sunt dezactivați și afișează „Licență necesară"

Pentru a introduce licența:
1. **Setări** → **Dispozitive și Servicii**
2. Găsește **Pago Plătește** → click pe **Configurare** (⚙️)
3. Selectează **Licență**
4. Introdu cheia de licență (format: `PAGO-XXXX-XXXX-XXXX-XXXX`)
5. Click **Salvează**

Licențe disponibile la: [hubinteligent.org/donate?ref=pagoplateste](https://hubinteligent.org/donate?ref=pagoplateste)

---

## Reconfigurare cont

Dacă trebuie să schimbi credențialele sau intervalul de actualizare:

1. **Setări** → **Dispozitive și Servicii** → click pe **Pago Plătește**
2. Click pe **Configurare** (⚙️)
3. Alege **Reconfigurare cont**
4. Modifică email-ul, parola sau intervalul de actualizare
5. Click **Trimite** — integrarea validează noile credențiale
6. Dacă validarea reușește, integrarea se reîncarcă automat cu noile setări

Nu este necesar să ștergi și să adaugi din nou integrarea.

---

## Activare licență

Integrarea funcționează cu un sistem de licențiere:

### Perioadă de evaluare

La prima instalare, integrarea pornește automat în **perioadă de evaluare** (trial). Senzorii funcționează normal în această perioadă, afișând datele reale din contul Pago.

### Activare cheie de licență

1. Obține o cheie de licență (detalii în secțiunea OptionsFlow → Licență)
2. În Home Assistant: **Setări** → **Dispozitive și Servicii** → **Pago Plătește** → **Configurare** (⚙️)
3. Alege **Licență**
4. Introdu cheia de licență (format: `PAGO-XXXX-XXXX-XXXX-XXXX`)
5. Click **Trimite** — cheia este validată la server

Tipuri de licențe disponibile: lunară, anuală, perpetuă.

### Ce se întâmplă fără licență validă

Dacă licența expiră sau nu este activată după perioada de evaluare:

- Toți senzorii vor afișa valoarea **„Licență necesară"**
- Atributele vor arăta `{"Licență": "necesară"}`
- Apare un senzor dedicat `Licență necesară` cu detalii despre status
- Datele continuă să fie aduse de la API, dar nu sunt expuse în senzori

---

## Interval de actualizare

| Parametru | Valoare |
|-----------|---------|
| Implicit | 3600 secunde (1 oră) |
| Minim | 3600 secunde (1 oră) |
| Maxim | 86400 secunde (24 ore) |

Intervalul se referă la cât de des integrarea interoghează API-ul Pago pentru date noi. Un interval mai mic de 1 oră nu este permis pentru a evita suprasolicitarea API-ului.

La fiecare ciclu de actualizare, se aduc **toate datele** în paralel (profil, abonament, carduri, mașini, facturi, furnizori, plăți), într-un singur ciclu al coordinator-ului.

---

## Erori posibile la configurare

| Eroare | Cauza | Soluție |
|--------|-------|---------|
| `Autentificare eșuată` | Email sau parolă greșite | Verifică credențialele din aplicația Pago |
| `Nu s-a putut conecta la serverul Pago` | Probleme de rețea sau Pago indisponibil | Verifică conexiunea la internet; reîncearcă |
| `Acest cont este deja configurat` | Același email adăugat de două ori | Folosește reconfigurarea în loc de o nouă intrare |
| `Eroare necunoscută` | Eroare neprevăzută | Verifică log-urile (vezi [DEBUG.md](DEBUG.md)) |

---

## Dezinstalare

1. **Setări** → **Dispozitive și Servicii** → **Pago Plătește**
2. Click pe cele 3 puncte (⋮) → **Șterge**
3. Confirmă ștergerea
4. (Opțional) Elimină folderul `custom_components/pagoplateste/` și restartează Home Assistant
