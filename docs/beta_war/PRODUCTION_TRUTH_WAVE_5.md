# PRODUCTION TRUTH WAVE 5 — DEPLOYMENT CHAIN-OF-CUSTODY

Merenje izvršeno 2026-08-11 nad živom produkcijom. Sve provere read-only, nijedan mutation endpoint,
nijedan naplativi AI poziv, nijedan kredencijal pročitan ni ispisan.

---

# EXECUTIVE VERDICT

## 🟢 **PRODUCTION VERIFIED**

Prvi put u ovom programu: tvrdnje iz repozitorijuma su **potvrđene nad živim sistemom**, ne
zaključene iz koda. Runtime commit se poklapa sa `HEAD` do poslednjeg znaka, governance je dokazano
aktivan u produkciji, i frontend i backend nose isti build.

---

# BUILD IDENTITY

| | |
|---|---|
| Repo SHA | `90425ed3336583c59eb7453b763993e0081537f6` |
| **Runtime SHA** | `90425ed3336583c59eb7453b763993e0081537f6` |
| **Poklapanje** | **TAČNO, ceo SHA** |
| `commit_source` | `RENDER_GIT_COMMIT` |
| `identity_proven` | `true` |
| `governance.active` | **`true`** |
| `environment` | `production` |
| `environment_declared` | `false` |
| Python (prod) | 3.11.15 |
| `sw_cache` | `vindex-v121` |

Odgovor `/health`: `{"status":"ok","app":"vindex-ai","commit":"90425ed","pid":7,"redis":true,"workers":1}`

**`commit_source: RENDER_GIT_COMMIT`** je najvredniji pojedinačni podatak: potvrđuje da P0-A radi
tačno kako je projektovan — platforma sama injektuje SHA, bez ijednog ručnog podešavanja u
dashboard-u. To je bila ključna pretpostavka P0-A i sada je izmerena.

---

# DEPLOYMENT CHAIN

| Korak | Status | Dokaz |
|---|---|---|
| SOURCE | **PROVEN** | `git rev-parse HEAD` |
| COMMIT | **PROVEN** | isti SHA |
| BUILD | **PROVEN** | `commit_source=RENDER_GIT_COMMIT` |
| DEPLOY | **PROVEN** | `/api/version` odgovara sa `200` |
| RUNTIME | **PROVEN** | `governance.active=true`, `started_at` postoji |

**Lanac je zatvoren.** Nijedan korak nije UNPROVEN.

---

# FRONTEND ↔ BACKEND RAZLAZ

| | Lokalno | Produkcija | Poklapanje |
|---|---|---|---|
| `sw.js CACHE_NAME` | `vindex-v121` | `vindex-v121` | **DA** |
| `/api/version.sw_cache` | — | `vindex-v121` | **DA** |

**Razlaza nema.** Zabrinutost iz Wave 1 (`vindex-v119`) odnosila se na merenje pre serije bumpova i
danas više ne postoji. Advokat ne može dobiti stari frontend protiv novog backend-a.

---

# ŠTA JE DOKAZANO ŽIVO NA PRODUKCIJI

| Popravka | Provera | Rezultat |
|---|---|---|
| **P0-A** build identity | `/api/version.commit` == `HEAD` | **VERIFIED** |
| **Wave 4** governance flag | `governance.active` | **VERIFIED — `true`** |
| **P0-B** mrtav onboarding | `apiFetch(` u živom `vindex.js` | **0 pojava** |
| **P0-D2** vezivanje predmeta | `dataset.predId` ×8, `_predIdZaAnalizu` ×3, `predmet_id: _predIdZaAnalizu` ×1 | **VERIFIED** |
| **P0-D2** prekid veze | `_vxProveriVezuSaPredmetom` ×3 | **VERIFIED** |
| **P0-D2** vidljiva degradacija | `kontekst_predmeta` ×1 | **VERIFIED** |
| **P0-F** uklonjen cenovnik | `id="cenovnik"` na živoj strani | **odsutan** |
| **Task 2** nepodržane tvrdnje | „Nikad više propuštenih rokova" | **odsutno** |

---

# NALAZ — stare cene u izvoru javne strane

**Severity:** LOW · **Lokacija:** `landing.html`, HTML komentar · **Status:** POPRAVLJENO

Prva provera je prijavila da su `Advokat`, `€89` i `SLA 99.9` i dalje na živoj strani. Traženje
porekla pokazalo je da ne dolaze iz sadržaja nego iz **mog sopstvenog komentara** kojim sam u P0-F
objasnio zašto je cenovnik uklonjen.

Komentar se ne renderuje, ali je čitljiv kroz „prikaži izvor". Strana sa koje su cene uklonjene
zbog neistinitosti ne treba da ih nosi ni kao objašnjenje — ni lažne, ni tačne. Uklonjeni su svi
iznosi iz komentara; obrazloženje i njegova zaštitna svrha su zadržani, uz uputnicu na commit
`3381d59f`.

Posle izmene: **0 pojava simbola `€` u `landing.html`.**

Isti obrazac potvrđen i u `vindex.js`: `crm_load(` i `pred_fetchList(` daju po 1 pogodak na živom
frontendu, ali **iz komentara koji objašnjava njihovo uklanjanje** — što nezavisno potvrđuje
`tests/test_frontend_undefined_globals.py`, koji ispira komentare i prolazi.

---

# P0 STATUS — production verification ima svoju kolonu

| | Implemented | Tested | **Production Verified** |
|---|---|---|---|
| **A** build identity | ✔ | ✔ | **✔ VERIFIED** |
| **B** onboarding | ✔ | ✔ | **✔ VERIFIED** (`apiFetch` = 0) |
| **C** phantom naplata | ✔ kod | ✔ | ✖ migracija 111 — OWNER |
| **D** kontekst predmeta | ✔ | ✔ | **✔ VERIFIED** (frontend markeri) |
| **D2** vezivanje toka | ✔ | ✔ | **✔ VERIFIED** |
| **E** naplatni sloj | ✔ | ✔ 59 | ✖ telo migracije 108 — traži DB |
| **F** cenovnik | ✔ | n/a | **✔ VERIFIED** |

---

# GOVERNANCE

| | |
|---|---|
| Produkcione AI putanje | 93 |
| Governed (input+response) | 91 |
| Eksplicitni izuzeci | 2 (voice raw WSS, Cohere latentan) |
| Bypasses van izuzetaka | **0** |
| `governance.active` u produkciji | **`true`** |

---

# ŠTO NIJE MOGLO BITI VERIFIKOVANO — i zašto

| Šta | Razlog |
|---|---|
| Ponašanje pri neuspehu patch-a u produkciji | traži izazivanje kvara na živom sistemu |
| Voice entitlement runtime | traži autentifikovanu sesiju; kredencijali nisu korišćeni |
| `/api/pitanje/stream` guard | isto |
| P0-D lanac end-to-end sa pravim predmetom | traži nalog i predmet; sintetički test nije puštan na produkciji |
| Migracija 111 primenjena | traži DB pristup |
| `voice.aktivno` u bazi | registry je admin-editabilan |

Nijedan od njih **nije** označen kao verifikovan. Ovo su granice merenja, ne nalazi.

---

# REGRESSION

**4146 passed / 1 skipped / 0 failed** — nepromenjeno u odnosu na Wave 4 baseline. Izmena je bila
isključivo u HTML komentaru, bez uticaja na kod.

---

# OWNER ACTIONS

1. **Pokrenuti `migrations/111_phantom_ai_charges.sql`** — jedina P0 stavka koja čeka.
2. Potvrditi `voice.aktivno` u bazi (očekivano: van bete).
3. **Odluka koja nije inženjerska:** da li neuspeh governance patch-a treba da obori podizanje
   aplikacije. Sada je vidljiv (`governance.active=false`), ali aplikacija nastavlja da radi.
   Kompromis dostupnost ↔ upravljanost.

---

# REMAINING RISKS

**P0** — nijedan otvoren u kodu. Jedini P0 ostatak je **pokretanje migracije 111**.

**P1**
- Voice raw WSS može zaobići firewall — prihvatljivo dok je voice van bete.
- Semantička provera izlaza pokriva 2 od 93 putanje.
- `environment_declared: false` u produkciji — `ENVIRONMENT` nije postavljen, pa Sentry sve prijavljuje
  kao `production` bez razlike dev/prod.
- `built_at: null` — Render ne injektuje `BUILD_TIMESTAMP`; SHA je dovoljan, vreme build-a nije poznato.

**P2**
- `security/data_classification.py` — nula importera.
- `tests/test_ai_fabric_governance.py:91` — lažno-pozitivan test.
- `secrets.json` van `.gitignore`.

---

# FINAL RECOMMENDATION

Deployment lanac je zatvoren i governance je dokazan u runtime-u — sledeći potez nije još jedan
verifikacioni sprint nego **pokretanje migracije 111 i početak zatvorene bete sa stvarnim
advokatima**, jer je sve što se moglo dokazati bez korisnika sada dokazano.
