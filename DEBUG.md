# DEBUG — Ghid de depanare

Ghid pentru identificarea și rezolvarea problemelor cu integrarea **Pago Plătește** în Home Assistant.

---

## Activare log-uri de debug

Adaugă în `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.pagoplateste: debug
```

Restartează Home Assistant. Log-urile vor apărea în **Setări** → **Sistem** → **Jurnale** (Logs), sau în fișierul `home-assistant.log`.

Pentru a vizualiza doar log-urile Pago:

```
grep -i "pago" config/home-assistant.log
```

---

## Descărcare diagnostic

Integrarea include suport pentru export diagnostic:

1. **Setări** → **Dispozitive și Servicii** → **Pago Plătește**
2. Click pe cele 3 puncte (⋮) → **Descarcă diagnosticul**

Fișierul JSON conține informații despre configurare, starea licenței, starea coordinator-ului și lista senzorilor activi. Datele sensibile (parolă, token-uri) sunt excluse automat.

---

## Probleme frecvente

### Integrarea nu apare în lista de integrări

**Cauza**: Folderul `custom_components/pagoplateste/` nu este în locația corectă sau Home Assistant nu a fost restartat.

**Soluție**:
1. Verifică structura: `config/custom_components/pagoplateste/__init__.py` trebuie să existe
2. Verifică `manifest.json` — domeniul trebuie să fie `pagoplateste`
3. Restartează Home Assistant complet (nu doar reîncarcă configurația)
4. Verifică log-urile pentru erori de import:
   ```
   grep -i "pagoplateste" config/home-assistant.log | grep -i "error"
   ```

---

### „Autentificare eșuată" la configurare

**Cauza**: Email sau parolă incorecte.

**Soluție**:
1. Verifică că folosești credențialele din aplicația mobilă Pago (nu cele de la un furnizor)
2. Testează login-ul direct în aplicația Pago pe telefon
3. Verifică dacă contul nu e blocat sau necesită verificare suplimentară
4. Verifică log-urile de debug:
   ```
   [Pago:ConfigFlow] PagoAuthError: Credențiale invalide
   ```

---

### „Nu s-a putut conecta la serverul Pago"

**Cauza**: Probleme de rețea, firewall, sau serverul Pago e indisponibil.

**Soluție**:
1. Verifică conexiunea la internet din Home Assistant
2. Testează conectivitatea:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" https://pago.cloud/
   ```
3. Verifică dacă un firewall sau DNS blochează `pago.cloud`
4. Reîncearcă după câteva minute — serverul Pago poate avea mentenanță

---

### Toți senzorii afișează „Licență necesară"

**Cauza**: Licența nu este activă (trial expirat, licență expirată, sau neactivată).

**Soluție**:
1. Verifică statusul licenței în log-uri:
   ```
   grep "Pago.*licen" config/home-assistant.log
   ```
2. Activează o licență: OptionsFlow → Licență (vezi [SETUP.md](SETUP.md))
3. Verifică log-ul pentru erori de comunicare cu serverul de licențiere:
   ```
   grep "Pago.*licen" config/home-assistant.log
   ```
4. Dacă serverul de licențiere e temporar indisponibil, starea anterioară este menținută local

---

### „Prima actualizare eșuată" la setup

**Cauza**: Coordinator-ul nu a putut aduce datele de la Pago la prima încărcare.

**Soluție**:
1. Verifică log-urile de debug:
   ```
   grep "Pago.*eroare\|Pago.*eșuat\|Pago.*timeout" config/home-assistant.log
   ```
2. Dacă e o eroare de autentificare (`ConfigEntryAuthFailed`), reconfigurează credențialele
3. Dacă e timeout, verifică rețeaua și reîncearcă
4. Dacă e „nu s-au putut obține datele profilului" — API-ul Pago a returnat un profil gol; reîncearcă mai târziu

---

### Un vehicul/furnizor nu apare ca senzor

**Cauza**: Senzorii dinamici sunt creați doar la prima actualizare. Vehiculele/furnizorii adăugați ulterior nu sunt detectați automat.

**Soluție**:
1. **Setări** → **Dispozitive și Servicii** → **Pago Plătește** → **⋮** → **Reîncarcă**
2. Sau restartează Home Assistant complet
3. Verifică în log-uri câți senzori sunt creați:
   ```
   grep "Creez.*senzori" config/home-assistant.log
   ```

---

### Senzorul vehicul afișează „Fără RCA" deși are RCA

**Cauza**: Alerta RCA nu a fost configurată în aplicația Pago, sau data RCA nu este completată.

**Soluție**:
1. Verifică în aplicația Pago că vehiculul are alerta RCA activată cu o dată de expirare
2. Verifică atributele senzorului în Home Assistant — dacă `RCA` este `Fără RCA`, înseamnă că API-ul nu returnează date pentru `END_VALIDITY_RCA`
3. Adaugă/actualizează alerta RCA în aplicația Pago, apoi reîncarcă integrarea

---

### Datele nu se actualizează

**Cauza**: Coordinator-ul a intrat în eroare, token-ul Pago a expirat fără reînnoire, sau intervalul de actualizare e prea mare.

**Soluție**:
1. Verifică log-urile coordinator-ului:
   ```
   grep "Pago.*UpdateFailed\|Pago.*AuthFailed" config/home-assistant.log
   ```
2. Verifică `last_update_success` în diagnosticul integrării
3. Reîncarcă integrarea: **⋮** → **Reîncarcă**
4. Dacă problema persistă, verifică dacă contul Pago funcționează (login din aplicația mobilă)

---

### Eroare „cryptography" la prima instalare

**Cauza**: Dependența `cryptography>=41.0.0` nu s-a instalat automat.

**Soluție**:
1. Integrarea declară dependența în `manifest.json` — Home Assistant o instalează automat
2. Dacă eșuează, instalează manual:
   ```bash
   pip install cryptography>=41.0.0
   ```
3. Pe Raspberry Pi sau sisteme ARM, compilarea poate dura; folosește `pip install --prefer-binary cryptography`

---

## Log-uri utile de referință

### Login reușit
```
Pago: login OK, token expiră în 3600s
```

### Fetch complet reușit
```
[Pago:Sensor] Creez 7 senzori pentru user 123456
```

### Eroare de rețea pe un endpoint
```
Pago: timeout pe /notification_v1_1/details/cars (15s)
Pago: eroare rețea pe /payment/cards: ClientConnectorError
```

### Token reînnoit automat
```
Pago: login OK, token expiră în 3600s
```
(apare de două ori dacă token-ul a expirat între cicluri)

### Licență validă
```
[Pago] Licență activă — tip: perpetual
```

### Trial activ
```
[Pago] Perioadă de evaluare — 14 zile rămase
```

### Licență invalidă
```
[Pago] Integrarea nu are licență validă. Senzorii vor afișa 'Licență necesară'.
```

---

## Contactare suport

Dacă problema persistă:

1. Activează log-urile de debug
2. Reproduce problema
3. Descarcă diagnosticul integrării
4. Deschide un issue pe [GitHub](https://github.com/cnecrea/pagoplateste/issues) cu:
   - Versiunea Home Assistant
   - Versiunea integrării Pago Plătește
   - Log-urile relevante (cu date sensibile mascate)
   - Fișierul diagnostic
   - Pași pentru reproducerea problemei
