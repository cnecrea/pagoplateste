# FAQ — Întrebări frecvente

Răspunsuri la cele mai comune întrebări despre integrarea **Pago Plătește** pentru Home Assistant.

---

### Ce credențiale folosesc?

Folosește email-ul și parola contului Pago Plătește — aceleași cu care te autentifici în aplicația mobilă Pago. Nu sunt necesare API key-uri sau token-uri suplimentare.

---

### Ce date extrage integrarea din contul meu Pago?

Integrarea aduce: profilul utilizatorului (nume, email, telefon), abonamentul activ (plăți rămase, perioadă), cardurile de plată, vehiculele cu alerte RCA și ITP, facturile emise curente, conturile de facturare per furnizor și plățile recente.

Nu se fac plăți, nu se modifică setări și nu se trimit notificări prin API — integrarea este read-only.

---

### De ce facturile emise nu au numele furnizorului?

Endpoint-ul public `/sdk/bills/accounts/summary` returnează doar sumă datorată și data scadenței, fără informații despre furnizor sau locația de facturare. Aplicația mobilă Pago obține aceste detalii printr-un SDK intern (Bills SDK) care comunică cu un host separat, inaccesibil prin API-ul public. Aceasta este o limitare a API-ului, nu a integrării.

---

### Cât de des se actualizează datele?

Implicit, la fiecare oră (3600 secunde). Intervalul minim este 1 oră, maximul 24 ore. Poți modifica intervalul prin reconfigurarea integrării (OptionsFlow → Reconfigurare cont). La fiecare ciclu, toate endpoint-urile sunt interogate în paralel.

---

### Pot adăuga mai multe conturi Pago?

Da, fiecare cont Pago (email diferit) se adaugă ca intrare separată. Nu poți adăuga același email de două ori — integrarea detectează duplicatele și refuză cu mesajul „Acest cont este deja configurat".

---

### Ce e licența și de ce am nevoie de ea?

Integrarea folosește un sistem de licențiere server-side (v3.3) cu semnături Ed25519 și HMAC-SHA256. Fără o licență validă, integrarea afișează doar senzorul „Licență necesară" și nu creează senzori sau butoane funcționale.

Licența se achiziționează de la: [hubinteligent.org/donate?ref=pagoplateste](https://hubinteligent.org/donate?ref=pagoplateste)

După achiziție, introdu cheia de licență din OptionsFlow:
1. **Setări** → **Dispozitive și Servicii** → **Pago Plătește** → **Configurare**
2. Selectează **Licență**
3. Completează câmpul „Cheie licență"
4. Salvează

---

### De ce apare „Licență necesară" pe toți senzorii?

Integrarea folosește un sistem de licențiere. Dacă perioada de evaluare a expirat sau licența nu a fost activată, toți senzorii afișează „Licență necesară". Datele continuă să fie aduse de la API, dar nu sunt expuse. Activează o licență din OptionsFlow → Licență (vezi [SETUP.md](SETUP.md)).

---

### Am introdus licența dar senzorii tot arată „Licență necesară". De ce?

Câteva cauze posibile:

1. **Licența nu a fost validată** — verifică logurile pentru mesaje cu `LICENSE`
2. **Serverul de licențe nu este accesibil** — dacă HA nu are acces la internet, validarea eșuează
3. **Cheie greșită** — verifică că ai copiat cheia corect, fără spații suplimentare
4. **Restartare necesară** — în rare cazuri, un restart al HA poate rezolva problema

Activează debug logging ([DEBUG.md](DEBUG.md)) și caută mesaje legate de licență.

---

### Unde obțin o cheie de licență?

Link-ul de achiziție este afișat direct în interfața integrării (OptionsFlow → Licență). Sunt disponibile licențe lunare, anuale și perpetue.

---

### Ce tipuri de licență există?

| Tip | Descriere |
|-----|-----------|
| **Trial** | Perioadă de evaluare — se activează automat la prima instalare |
| **Lunară** | Licență valabilă 30 de zile de la activare |
| **Anuală** | Licență valabilă 365 de zile de la activare |
| **Perpetuă** | Licență fără expirare |

---

### Licența este legată de dispozitiv?

Da. Cheia de licență este legată de instalarea Home Assistant. Dacă muți instalarea pe alt hardware, va trebui să contactezi suportul pentru transfer sau să achiziționezi o licență nouă.

---

### De ce nu apare un vehicul/furnizor pe care l-am adăugat recent în Pago?

Senzorii dinamici (per vehicul, per furnizor) sunt creați la prima actualizare a integrării (la setup). Dacă adaugi un vehicul sau furnizor nou în aplicația Pago după configurare, restartează integrarea: **Setări** → **Dispozitive și Servicii** → **Pago Plătește** → **⋮** → **Reîncarcă**.

---

### Ce înseamnă statusul vehiculului?

| Status | Semnificație |
|--------|-------------|
| **OK** | RCA și ITP sunt valide |
| **RCA Expirat** | Asigurarea RCA a expirat |
| **ITP Expirat** | Inspecția tehnică periodică a expirat |
| **Fără RCA** | Nu există date despre RCA în cont |

Prioritatea este: RCA Expirat > ITP Expirat > Fără RCA > OK. Pictograma se schimbă automat: `mdi:car` (OK), `mdi:car-emergency` (expirat), `mdi:car-off` (fără RCA).

---

### Cum creez o automatizare pentru RCA expirat?

```yaml
automation:
  - alias: "Alertă RCA expirat"
    trigger:
      - platform: state
        entity_id: sensor.pagoplateste_123456_b123abc
        to: "RCA Expirat"
    action:
      - service: notify.mobile_app_telefonul_meu
        data:
          title: "RCA Expirat"
          message: "Vehiculul B 123 ABC are RCA-ul expirat!"
```

Înlocuiește `123456` cu `pos_user_id`-ul tău și `b123abc` cu numărul de înmatriculare (lowercase, fără spații).

---

### Integrarea trimite date personale către terți?

Integrarea comunică cu API-ul Pago pentru datele contului și cu un server de licențiere pentru validarea licenței. Nu se trimit parole, date de card sau informații financiare către serverul de licențiere.

---

### Ce biblioteci externe necesită integrarea?

Doar `cryptography>=41.0.0` — se instalează automat prin Home Assistant la prima încărcare a integrării.

---

### Cum raportez o problemă?

1. Activează log-urile de debug (vezi [DEBUG.md](DEBUG.md))
2. Descarcă diagnosticul: **Setări** → **Dispozitive și Servicii** → **Pago Plătește** → **⋮** → **Descarcă diagnosticul**
3. Deschide un issue pe [GitHub](https://github.com/cnecrea/pagoplateste/issues) cu log-urile și diagnosticul atașate
