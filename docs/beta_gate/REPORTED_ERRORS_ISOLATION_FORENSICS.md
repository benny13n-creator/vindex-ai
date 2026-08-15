# REPORTED_ERRORS — FORENZIKA IZOLACIJE

**Baseline:** `98a278b9` · **Datum:** 2026-08-15 · **Režim:** forenzički, uz jedan
kontrolisan i vraćen upis

---

## 1. MODEL VLASNIŠTVA (TASK 1)

| Pitanje | Odgovor |
|---|---|
| Ko je vlasnik reda? | korisnik iz `user_id` |
| Na osnovu čega? | `user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL` |
| Tenant/kancelarija? | **NE POSTOJI** — nema `kancelarija_id` ni `tenant_id`; izolacija je isključivo **po korisniku** |
| Predmet? | **NE POSTOJI** — nema `predmet_id` |

**Kolone:** `id`, `user_id`, `original_prompt`, `ai_response`, `timestamp`.

**Dve deklaracije, identične:** `supabase_migration.sql:115` i
`migrations/113_feedback_truth.sql:73`, obe `CREATE TABLE IF NOT EXISTS`.

**Deklarisane politike:**

| Operacija | Politika |
|---|---|
| INSERT | `WITH CHECK (auth.uid() = user_id)` |
| SELECT | `USING (jwt.role = 'service_role')` |
| UPDATE | **nema politike** |
| DELETE | **nema politike** |

Uz uključen RLS, izostanak politike znači zabranu za sve osim `service_role`
(koji RLS zaobilazi).

**Pisci u aplikaciji:** tačno **jedan** — `static/vindex.js:8117`, iz pregledača,
preko korisnikovog Supabase klijenta (publishable ključ + korisnička sesija).

**Čitači u aplikaciji:** **nijedan.** Nijedan backend endpoint, cron ni servis ne
dodiruje tabelu. To je odlučujuće: backend radi sa `service_role` ključem koji
RLS zaobilazi, pa je **odsustvo backend čitača** ono što čini RLS potpunom
kontrolom.

**GRANT prava:** `UNKNOWN` — PostgREST ne izlaže `information_schema.role_table_grants`.
Izvedeno iz ponašanja, ne iz kataloga (v. §3).

---

## 2. ZAŠTO PRVA DVA POKUŠAJA NISU DALA DOKAZ

| Pokušaj | Ishod | Zaključak |
|---|---|---|
| Kovan `apikey` iz `SUPABASE_JWT_SECRET` | `401 Invalid API key` | gateway ne validira samo potpis |
| Pravi `apikey` + kovan korisnički JWT | `401 PGRST301` „None of the keys was able to decode the JWT" | **PostgREST više ne verifikuje HS256 tim tajnim ključem** |

Projekat koristi **novi Supabase sistem ključeva** (`sb_publishable_…`) i
**asimetrično potpisivanje** (aplikacija to već podržava — `shared/deps.py`
verifikuje ES256/RS256 preko JWKS). `SUPABASE_JWT_SECRET` u `.env` je nasleđena
grana koja se za današnje tokene ne koristi.

To **nije kvar** — nemogućnost kovanja korisničkog tokena je ispravna
bezbednosna postavka. Ali znači da se `authenticated` uloga ne može testirati
bez pravog naloga.

---

## 3. DOKAZ PONAŠANJA — `anon` (TASK 2/3/4/6/7)

Korišćen je **pravi publishable ključ** iz `static/vindex.js:236` — isti koji
dobija svaki pregledač, dakle tačno ono što ima bilo ko sa interneta.

### 3.1 Prazna tabela — nedovoljno

| Sonda | Ishod |
|---|---|
| `anon SELECT` | `200`, `count=*/0` |
| `anon INSERT` (tuđi `user_id`) | **`401 / 42501`** — odbijen RLS-om |
| `anon INSERT` (bez `user_id`) | **`401 / 42501`** |
| `anon UPDATE` | `204` ⚠ |
| `anon DELETE` | `204` ⚠ |

⚠ Nad **praznom** tabelom `204` ne razlikuje „RLS je odbio sve redove" od „nije
bilo šta da se dira". Ta razlika je razlika između bezbedne i katastrofalne
tabele i nije smela ostati na pretpostavci.

### 3.2 Kontrolisani test sa STVARNIM redom — odlučujuće

**Okvir:** 1 red, `user_id = NULL` (nikakvi tuđi podaci), jedinstven marker,
precondition `count=0`, rollback po tačnom `id`, postcondition provereno.

| Test | HTTP | **Stvarno stanje posle** | Ishod |
|---|---|---|---|
| `anon UPDATE` po tačnom `id` | 200 `[]` | sadržaj **nepromenjen** | **BLOKIRAN** |
| `anon UPDATE` bez filtera (masovno) | 204 | sadržaj **nepromenjen** | **BLOKIRAN** |
| `anon DELETE` po tačnom `id` | 204 | red **preživeo** | **BLOKIRAN** |
| `anon DELETE` bez filtera (masovno) | 204 | red **preživeo** | **BLOKIRAN** |
| `anon SELECT` dok red POSTOJI | 200 | **`count=*/0`, `[]`** | **BLOKIRAN** |

Peti red je ključan: **0 vraćenih redova dok red dokazano postoji** uklanja svaku
dvosmislenost prazne tabele.

**Postcondition:** `count = */0` — sonda uklonjena, tabela vraćena u zatečeno stanje.

### 3.3 Šira površina — anon nad poverljivim tabelama

`klijenti`, `predmeti`, `predmet_dokumenti`, `predmet_hronologija`, `audit_log`,
`billing_entries`, `profiles` — **sve vraćaju `count=*/0`**, dok `service_role`
nad `profiles` vidi **12 redova**. RLS filtrira, ne greši.

### 3.4 Informaciono curenje (TASK 7)

Upiti za dva različita nasumična `id` vraćaju **bajt-identičan** odgovor
(`200 []`). Nema razlike `404` vs `403`, nema razlike u broju rezultata, nema
agregata koji bi otkrio postojanje tuđeg reda. **Nema curenja postojanja.**

---

## 4. ŠTA NIJE DOKAZANO

**`authenticated` uloga A vs B nije testirana.** Nije bilo moguće doći do
korisničkog tokena: kovanje je odbijeno (§2), a jedini preostali put je
kreiranje dva stvarna naloga u produkcionom `auth.users`, što pokreće
`handle_new_user` trigger i stvara redove u `profiles`. To je druga klasa
zahvata od jednog reda bez vlasnika u praznoj tabeli i **nije izvedeno bez
odobrenja**.

Deklarisana SELECT politika (`service_role` only) implicira da ni prijavljeni
korisnik ne bi video ništa, i to je konzistentno sa svime izmerenim — ali
**implikacija nije dokaz**, i tako je i označena.

---

## 5. LAŽNI DOKAZ U POSTOJEĆIM TESTOVIMA (TASK 8)

Tri test fajla pominju `reported_errors`:

| Fajl | Šta radi | Vredi kao dokaz izolacije? |
|---|---|---|
| `test_beta_p1_feedback_truth.py` | lažni Supabase, provera ugovora šeme | **NE** |
| `test_beta_p1_feedback_playwright.py` | dvojnik SDK-a u pregledaču | **NE** |
| `test_faza15_interaction_closure.py` | `window.__supaInsert` beleži pozive | **NE** |

**Nijedan ne izvršava stvarnu RLS politiku.** Nijedan nije obrisan — svi mere
druge, legitimne stvari (istinitost UI-ja, ugovor šeme). Ovde su imenovani samo
da se ne bi ubuduće citirali kao dokaz izolacije.

**Dodata je jedna brava** koja meri pretpostavku pod kojom RLS dokaz uopšte važi:
`test_nijedan_backend_endpoint_ne_cita_reported_errors`. Ako neko doda rutu koja
tabelu čita `service_role` ključem, test pada i tera da se dokaz ponovo izvede.
Mutacija (dodata lažna backend referenca) — **ubijena**.

---

## 6. PREOSTALI POZNATI RIZICI (TASK 11/12)

| Tabela | Stanje | Uticaj |
|---|---|---|
| `api_costs` | **ne postoji** (`PGRST205`) | trošak AI-ja se ne meri — **telemetrijski**, ne funkcionalni |
| `ratio_decidendi` | **ne postoji** (`PGRST205`) | keš pravnih stavova ne radi; svaki poziv plaća LLM — **trošak**, ne netačnost |
| `feature_usage_log` | postoji, **0 redova** | `usage_events` ima **2.909** redova — naplata i potrošnja rade drugim putem |

**Nijedan nije bezbednosni ni funkcionalni blokator.** Ostaju otvoreni rizici.

**Tri sekundarna pisca hronologije** (TASK 12) — potvrđeni, nedirani:

| Endpoint | Ponašanje pri padu upisa |
|---|---|
| `routers/predmeti_close.py:189` | `except → logger.warning`, odgovor ostaje uspeh |
| `routers/rocista.py:398` | u `gather(return_exceptions=True)` |
| `routers/ugovor_zastupanja.py:336` | `except → logger.warning` |

Sva tri pišu u tabelu **koju korisnik i inače poseduje** — nema izloženosti
tuđih podataka. Problem je isključivo **ugovor greške** (lažna potvrda), pa po
mandatu ostaje za zaseban sprint.

---

## 7. IZLAZNA KAPIJA

| # | Uslov | Status |
|---|---|---|
| 1 | Model vlasništva dokumentovan | ✅ |
| 2 | RLS status i politike dokazani | 🟡 politike **deklarisane**, ponašanje dokazano za `anon`; `pg_policies` nedostupan |
| 3 | GRANT prava proverena | 🟡 **UNKNOWN** iz kataloga; izvedeno iz ponašanja |
| 4 | USER_A ne čita USER_B | 🟡 **nije testirano** (nema korisničkog tokena) |
| 5 | USER_B ne čita USER_A | 🟡 **nije testirano** |
| 6 | A ne može upisati u ime B | ✅ za `anon` (42501); 🟡 za `authenticated` |
| 7 | UPDATE/DELETE blokirani | ✅ **dokazano stvarnim redom** |
| 8 | Aplikacioni endpointi provereni | ✅ **nijedan ne postoji** |
| 9 | Privilegovani klijent identifikovan | ✅ backend koristi `service_role`, ali tabelu ne dodiruje |
| 10 | Postojeći testovi provereni na lažni dokaz | ✅ tri imenovana |
| 11 | Nema UNKNOWN koji utiče na izolaciju | ❌ **`authenticated` A/B ostaje UNKNOWN** |
| 12 | Regresija prolazi | ✅ |
| 13 | Git stablo čisto | ✅ |
| 14 | Reproduktibilno | ✅ skripte u izveštaju |

**VERDIKT: YELLOW.** Nije GREEN jer tačke 4, 5 i 11 nisu dokazane — a mandat
izričito zabranjuje GREEN na osnovu „verovatno radi".

Ono što **jeste** dokazano je značajno: neautentifikovani napadač sa javnim
ključem ne može pročitati, upisati, izmeniti ni obrisati nijedan red — ni u
`reported_errors`, ni u bilo kojoj poverljivoj tabeli.
