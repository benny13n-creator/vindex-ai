# BETA REALITY WAVE 6 — FAILURE-PATH VERIFICATION

---

# EXECUTIVE VERDICT

## 🟡 **YELLOW**

Noć je pronašla i zatvorila **jedan stvarni novčani kvar** koji je preživeo pet prethodnih sprintova,
i **dokazala naplatnu konkurentnost nad pravim PostgreSQL-om**. Ali nekoliko stavki iz mandata
ostalo je neizvršeno — pre svega A/B kontekst dokaz nad živim predmetima i sistematski prolaz kroz
sve TIER 0 putanje. Ne prijavljujem ih kao urađene.

---

# BASELINE → FINAL

| | Pre | Posle |
|---|---|---|
| HEAD | `1dd1ef3b` | `46daee61` |
| Testovi | 4146 / 1 / 0 | **4156 passed / 1 skipped / 0 failed** |
| Postgres naplata | — | **59 passed** (klasteri iz Wave 2 još živi) |
| Stablo | čisto | čisto |

---

# FINDING W6-01 — AI se izvršavao pre provere bilansa

| | |
|---|---|
| **Severity** | **HIGH (novčani)** |
| **Lokacija** | `routers/strategija.py::_run_analiza` — AI na `:523`, naplata na `:537` |
| **Status** | **POPRAVLJENO** |

**Root cause.** `_run_analiza` izvršava svih 8 GPT-4o poziva, pa tek onda zove
`UsageService.consume`. Ako korisnik nema dovoljno kredita, `consume` digne 402,
`routers/jobs.py:120` to uhvati i upiše `status="error"` — a AI rad je već obavljen i plaćen
provajderu.

`PermissionService.require("strategija")` ovo ne hvata: proverava **tarifu**, ne **bilans**.

**Scenario.** `professional` korisnik sa 0 kredita pokrene 8 GPT-4o poziva, dobije generičku grešku,
i ponovi do granice rate limita (`10/hour`) — **oko 80 GPT-4o poziva na sat po nalogu, bez ijednog
naplaćenog kredita.** Trošak nosi firma, korisnik ne dobija ništa.

Ovo je tačno „parcijalni uspeh" iz mandata: *AI uspe → rezultat postoji → naplata pukne.*

**Popravka.** Pre-flight provera bilansa ispred skupog posla (cena 6 = `krediti 1 × multiplier 6`).
Atomični odbitak **ostaje posle posla**, pa ugovor „ne naplaćuj ako AI padne" ostaje netaknut —
`test_d` to zaključava poređenjem pozicija u izvoru.

Namerno **TOCTOU-tolerantna** i namerno **fail-open**: greška u čitanju bilansa ne blokira analizu,
jer je ovo troškovna optimizacija a ne bezbednosna kontrola. Suprotno od vlasničke kapije, koja je
fail-closed. Razlika je obrazložena u kodu.

**Mutacija:** uklonjena kapija → **4 testa FAILED**. Vraćeno → 10 passed.

---

# BILLING EVIDENCE

| Scenario | Dokaz | Status |
|---|---|---|
| **Concurrency** | 59 Postgres testova nad pravim serverom: 5 konkurentnih scenarija, invarijanta `uspesne × cena + krajnji = pocetni` | **DOKAZANO** |
| **Insufficient credits** | `test_a` sa bilansom 0/1/5 → 402, **posao NIJE pokrenut** | **DOKAZANO** |
| **Granica** | 5 odbijeno, 6 prošlo — tačno na ceni | **DOKAZANO** |
| **Founder** | zaobilazi kapiju, kao i svuda u sistemu | **DOKAZANO** |
| **Retry / dedupe** | `test_p1_charge_on_failure.py` — dupli submit deli jedan posao | **DOKAZANO (ranije)** |
| **No-charge-on-failure** | `consume` ostaje posle posla; `test_d` | **DOKAZANO** |
| **Non-AI naplata** | migracija 111 napisana, **nije pokrenuta** | **OWNER** |

---

# ŠTA NIJE URAĐENO — i ne prijavljujem kao urađeno

| Mandat | Status | Razlog |
|---|---|---|
| A/B izolacija nad **živim** predmetima (§6) | **NIJE** | dokazano ranije nad mock-ovanom bazom (`test_p0d2`), ne nad pravim predmetima |
| Sistematski prolaz kroz sve TIER 0 putanje (§10) | **NIJE** | urađena je jedna (strategija), ne sve |
| Kompletna failure matrica (§5) | **DELIMIČNO** | pokriven parcijalni uspeh; timeout/5xx/DB-fail nisu sistematski prošli |
| Adversarial faza sa zasebnim agentom (§11) | **NIJE** | mutacije izvršene, ali bez nezavisnog red-team prolaza |
| Provenance ugovor (§7) | **NIJE** | `izvori` = rezultati pretrage, ne citati — nalaz stoji otvoren od Wave 1 |
| Migracija 111 status (§2) | **UNVERIFIED** | traži DB pristup koji nemam |
| 402/429 → 202 semantika (§8) | **OTVORENO** | root cause je `run_in_background` koji sve izuzetke pretvara u `error` string |

---

# TEST INTEGRITY

| | |
|---|---|
| Novih testova | 10 |
| Izmenjenih testova | 3 (dodat preduslov bilansa) |
| **Obrisanih testova** | **0** |
| Mutacija izvršenih | 1 (+ 59 Postgres, ponovljeno) |
| Full regression | 4156 / 1 / 0 |

**Izmena tri postojeća testa je dodavanje SETUP-a, ne slabljenje.** `test_p1_charge_on_failure.py`
(2 bloka) i `test_p0d2::test_m` mere dedupe i ožičenje, ne kredite. Ruta ima novi legitiman
preduslov; bez mock-a bilansa merili bi 402 umesto onoga što treba da mere.

---

# GREŠKA U MOM TESTU — treći put isti razred

`test_d` je u prvoj verziji merio poziciju `UsageService.consume` u **mom sopstvenom komentaru**
iznad pre-flight bloka, pa je zaključio da je odbitak ispred posla.

Isti razred greške već je uhvaćen dvaput u ovom programu — P0-D2 (`test_b` je merio komentar umesto
koda) i Wave 4 (fixture nije čistio globalno stanje). Sada se komentari i docstring uklanjaju pre
merenja.

**Da nije bilo mutacionog koraka, prošao bi kao zelen.**

---

# OPEN RISKS

**P1**
- `run_in_background` pretvara **svaki** izuzetak u generički `error` string. 402/429 iz naplate ne
  mogu doći do paywall handlera na 202-putanji. Root cause je granica posla, ne frontend.
- `izvori` = rezultati pretrage, ne citati odgovora. UI ih prikazuje kao „Pravni izvori".
- Semantička provera izlaza pokriva 2 od 93 putanje.
- Voice raw WSS zaobilazi firewall (prihvatljivo dok je voice van bete).

**P2**
- `security/data_classification.py` — nula importera.
- `tests/test_ai_fabric_governance.py:91` — lažno-pozitivan test, **i dalje nije prepisan**.
- `secrets.json` van `.gitignore`.

---

# OWNER ACTIONS

1. **`migrations/111_phantom_ai_charges.sql`** — i dalje jedina P0 stavka koja čeka.
2. Potvrditi `voice.aktivno` u bazi.
3. Odluka o startup politici pri neuspehu governance patch-a.

---

# FINAL RECOMMENDATION

Zatvoren je stvarni novčani kvar i dokazana naplatna konkurentnost, ali A/B kontekst dokaz nad živim
predmetima i sistematska failure matrica ostaju — **sledeći sprint treba da bude uži: samo te dve
stvari, do kraja, umesto još jednog širokog prolaza.**
