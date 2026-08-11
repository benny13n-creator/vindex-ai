# BETA REALITY WAVE 7 — A/B FORENZIKA + FAILURE MATRICA

---

# EXECUTIVE VERDICT

## 🟡 **YELLOW**

Dva primarna cilja mandata su **isporučena i mutaciono dokazana**: A/B izolacija kroz *stvarnu*
`build_case_context` (ne kroz mock) i failure matrica sa merenom naplatom. Nijedan novi P0 nije
pronađen — i to je dokazano, ne pretpostavljeno.

Ne GREEN, jer tri stavke mandata nisu izvršene: async state attack nad živim frontend stanjem,
cancellation ugovor, i nezavisni red-team kao odvojen agent. Ne prijavljujem ih kao urađene.

---

# BASELINE → FINAL

| | Pre | Posle |
|---|---|---|
| HEAD | `94714452` | `9013fb3f` |
| Testovi | 4156 / 1 / 0 *(ponovljeno iz nule, poklopilo se)* | **4179 passed / 1 skipped / 0 failed** |
| Stablo | čisto | čisto |
| Produkcioni fajlovi menjani | — | **0** — dokazni sprint |

---

# ŠTA JE BILA RUPA U RANIJEM DOKAZU

`tests/test_p0d2_user_path_binding.py` dokazuje A/B izolaciju tako što **zameni**
`build_case_context` funkcijom koja vraća različit kontekst po ID-u. To dokazuje da ruta prosleđuje
pravi ID i da se kontekst propagira kroz 7 GPT poziva — ali **ne dokazuje da sama
`build_case_context` izoluje predmete**, jer se nikad ne izvršava.

Nikad se nisu izvršili:
- vlasnički filter `predmeti.user_id == uid` (`shared/case_context.py:161`)
- `_fetch_raw` sa svojih 7 upita
- `_select_documents` / `_excerpt` / `_fetch_document_texts`
- `error` grana za tuđi predmet (`:403`)

Wave 7 mock-uje **samo Supabase klijent**. Sve iznad njega je stvarni kod.

### Zašto je lažna baza morala da se prepiše

`_FakeQuery` u `tests/test_tau002_case_context.py:38-47` **eksplicitno no-op-uje** svaki `.eq()`
osim `id` — i sam docstring to priznaje. Sa takvim lažnjakom test vlasništva prolazi **lažno**, jer
`user_id` filter nikad ništa ne radi.

`_Upit` u Wave 7 primenjuje svaki filter, i `test_ng_lazna_baza_stvarno_filtrira_po_user_id` to
dokazuje **pre** svih ostalih tvrdnji.

---

# ODGOVORI NA KVALITY GATE PITANJA (§25)

| Pitanje | Odgovor | Dokaz |
|---|---|---|
| Može li Alpha dobiti Beta context? | **NE** | `test_a`, `test_b` — oba smera, kroz stvarnu funkciju |
| Može li korisnik A pokrenuti analizu nad B? | **NE** | `test_c` vlasnička matrica, 6 kombinacija |
| Curi li išta delimično? | **NE** | `test_d` — ni naziv, ni sud, ni ime fajla |
| Može li A/B konkurentnost pomešati kontekst? | **NE** | `test_e` — 4 istovremena posla |
| Može li korisnik sa 0 kredita pokrenuti skup GPT posao? | **NE** | Wave 6 pre-flight kapija |
| Može li timeout/5xx/malformed postati lažni uspeh? | **NE** | `failure_matrix` — 7 scenarija |
| Može li retry izazvati pogrešnu naplatu? | **NE** | dedupe ključ nosi `predmet_id`; `test_f` |
| Padaju li testovi kad se zaštita ukloni? | **DA** | 3 mutacije, sve obaraju očekivane testove |

---

# FAILURE MATRICA — mereno, ne izvedeno iz koda

| Kvar | GPT poziva | Naplata | Stanje posla | Rezultat korisniku |
|---|---|---|---|---|
| GPT pad na koraku 1 | 1 | **0** | `error` | greška |
| GPT pad na koraku 2 | 2 | **0** | `error` | greška |
| GPT pad na koraku 4 | 4 | **0** | `error` | greška |
| GPT pad na koraku 7 | 7 | **0** | `error` | greška |
| Timeout | 3 | **0** | `error` | greška |
| Mrežna greška / 5xx | 3 | **0** | `error` | greška |
| Malformed odgovor | 3 | **0** | `error` | greška |
| Prazan odgovor (firewall BLOCK) | 2 | **0** | `error` | greška |
| **Uspešan posao** | **7** | **1** | `done` | rezultat |

Ugovor „ne naplaćuj ako AI padne" je time **meren**, ne pretpostavljen.

---

# ISPRAVKA RANIJE KLASIFIKACIJE — 402 semantika

Wave 2 i Wave 6 su prijavili da 402/429 *„degradiraju u generički error string"* i da paywall
handler ne može da opali. **Merenje pokazuje da je ta ocena bila preoštra.**

`str(HTTPException(402, {...}))` daje doslovno:

```
402: {'code': 'NO_CREDITS', 'message': 'nema'}
```

I statusni kod i kod greške **prežive**. Informacija se ne gubi — nije strukturisana. Frontend
(`strat_job_poll`) prikazuje string sirovo, pa korisnik vidi tehnički tekst umesto paywall poruke.

**Prava klasifikacija: P2 (UX/format), ne P1 (gubitak informacije).** Nalaz je oslabljen na osnovu
merenja, ne pojačan.

---

# MUTATION EVIDENCE

| Mutacija | Očekivano | Stvarno |
|---|---|---|
| **M3** uklonjen `.eq("user_id", uid)` iz `build_case_context` | pad | **3 testa FAILED** — tačno cross-tenant kombinacije |
| **M10** lažna baza ne filtrira (isti kontekst za A i B) | pad | **5 testova FAILED** |
| **M7** dodata naplata pre `log_cost_to_db` | pad | **`test_ng` FAILED** (dupla naplata) |

**M3 je najvredniji rezultat:** dokazuje da je baš vlasnički filter ono što štiti, a ne slučajna
struktura lažne baze.

**Poštena napomena o M7:** mutacija je ubacila `consume` *iza* AI posla, pa je testirala **duplu
naplatu**, ne **redosled**. Oznaka je bila netačna. Redosled pokriva `test_d` iz Wave 6.

---

# ŠTA NIJE URAĐENO — ne prijavljujem kao urađeno

| Mandat | Status | Razlog |
|---|---|---|
| Async state attack nad živim frontend stanjem (§6) | **NIJE** | statički deo pokriven u P0-D2 (`dataset.predId` pre `await`); živa mutacija UI stanja tokom analize nije izvršena |
| Cancellation ugovor (§14) | **NIJE** | sistem nema definisan cancellation contract; nije mapiran |
| Nezavisni red-team kao odvojen agent (§16) | **NIJE** | mutacije izvršene, ali iz perspektive autora testova |
| DB failure injection u 6 tačaka (§12) | **DELIMIČNO** | pokriveno kroz GPT/firewall greške; namenska DB fault injection nije |
| Migracija 111 status (§21) | **UNVERIFIED** | traži DB pristup |

---

# TEST INTEGRITY

| | |
|---|---|
| Novih testova | 23 |
| Izmenjenih | 0 |
| **Obrisanih** | **0** |
| Mutacija | 3 |
| Produkcioni fajlovi menjani | **0** |

Svi novi testovi mere **runtime ponašanje**. Jedini izuzetak je `test_f` (dedupe ključ), koji
računa hash — i to je izvršavanje, ne čitanje izvora.

---

# REMAINING RISKS

**P0** — nijedan. Jedini P0 ostatak van koda je **pokretanje migracije 111**.

**P1**
- Voice raw WSS zaobilazi firewall (prihvatljivo dok je voice van bete).
- Semantička provera izlaza pokriva 2 od 93 putanje.
- `izvori` = rezultati pretrage, ne citati odgovora.

**P2**
- 402 stiže korisniku kao tehnički string umesto paywall poruke *(oslabljeno sa P1)*.
- `security/data_classification.py` — nula importera.
- `tests/test_ai_fabric_governance.py:91` — lažno-pozitivan test, i dalje nije prepisan.

---

# OWNER ACTIONS

1. **`migrations/111_phantom_ai_charges.sql`** — jedina P0 stavka.
2. Potvrditi `voice.aktivno` u bazi.
3. Odluka o startup politici pri neuspehu governance patch-a.

---

# TAČNO ŠTA SLEDEĆE TREBA RADITI

Ne još jedan forenzički sprint. **Preostale tri stavke (async state attack, cancellation, nezavisni
red-team) su manje vredne od jedne stvari koja nedostaje: stvarnog advokata koji koristi sistem.**
Sve što se moglo dokazati bez korisnika sada je dokazano dvaput.
