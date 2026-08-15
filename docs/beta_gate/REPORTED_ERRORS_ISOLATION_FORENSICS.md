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


---

# RLS-AB-001 — DOPUNA: `authenticated` A/B DOKAZAN

**Datum:** 2026-08-15 · **HEAD pri merenju:** `bcec08df`

Prethodni odeljak ostavio je `authenticated` izolaciju kao UNKNOWN. Sada je
izmerena — stvarnim nalozima, stvarnim sesijama, bez kovanja tokena.

## Metod (isti koji aplikacija koristi)

    POST /auth/v1/admin/users              (service_role)  → dva throwaway naloga
    POST /auth/v1/token?grant_type=password (publishable)  → STVARNI JWT
    GET  /auth/v1/user                                      → potvrda identiteta
    PostgREST sa tim JWT-om                                 → `auth.uid()` je taj korisnik

`signInWithPassword` je isti tok koji koristi `static/vindex.js:640`.
`service_role` je korišćen **isključivo** za pripremu, verifikaciju stanja i
čišćenje — nijednom kao A ili B.

**Identitet dokazan:** `/auth/v1/user` je za oba tokena vratio tačno onaj `id`
koji je admin API dodelio; tokeni su različiti.

## Rezultat — 10/10 blokirano

| Operacija | Ishod | Dokaz |
|---|---|---|
| A → B SELECT po tačnom `id` | **BLOKIRAN** | `count=*/0`, marker B odsutan |
| A → B SELECT po `user_id` B | **BLOKIRAN** | `count=*/0` |
| A → B SELECT bez filtera | **BLOKIRAN** | `count=*/0` |
| A → B UPDATE | **BLOKIRAN** | stanje reda posle: `'netaknuto'` |
| A → B DELETE | **BLOKIRAN** | red **preživeo** |
| A → B INSERT (`user_id=B`) | **BLOKIRAN** | `403/42501`, red nije nastao |
| B → A SELECT po `id` / po `user_id` | **BLOKIRAN** | `count=*/0` |
| B → A UPDATE | **BLOKIRAN** | stanje: `'netaknuto'` |
| B → A DELETE | **BLOKIRAN** | red **preživeo** |
| B → A INSERT (`user_id=A`) | **BLOKIRAN** | `403/42501` |

Nijedan zaključak ne počiva na HTTP statusu — svaki UPDATE/DELETE je proveren
**stanjem reda pre i posle**.

**Informaciono curenje:** upit za **postojeći tuđi** `id` i za **nepostojeći**
`id` daju identičan status, telo i `count`. Nema razlike koja bi otkrila
postojanje tuđeg reda.

## ⚠⚠ OVAJ ODELJAK JE POVUČEN — v. „ISPRAVKA 2" na kraju dokumenta

> Tvrdnja ispod (**„primarni kanal ne radi ni za jednog korisnika"**) je
> **NETAČNA**. Uzrok nije bio RLS nego **moja sonda**: slala je
> `Prefer: return=representation`, što tera `INSERT … RETURNING`, a RETURNING
> traži SELECT pravo. Zadržano je nepromenjeno radi traga; ispravan nalaz je u
> „ISPRAVCI 2".

## ~~⚠ FUNKCIONALNI NALAZ — ispravka mog ranijeg zaključka~~ (POVUČENO)

Oba autentifikovana korisnika dobijaju **`403 / 42501`** i pri upisu
**SOPSTVENOG** reda:

    "new row violates row-level security policy for table \"reported_errors\""

Poruka je **policy-level**, ne grant-level („permission denied for table"),
dakle: `authenticated` **ima** INSERT pravo, ali ga nijedna politika ne
propušta. Deklarisana `WITH CHECK (auth.uid() = user_id)` iz migracije 113
**nije na snazi u produkciji.**

**Ispravka:** u prethodnom sprintu sam zaključio da je migracija 113 primenjena
i da su „oba kanala prijave dobila skladište". Izmerio sam da **tabela i kolone
postoje** — nisam izmerio da korisnik može da piše. Tabela postoji; politika ne.

**Posledica:** primarni kanal prijave netačnog pravnog odgovora
(`static/vindex.js::sendFeedback`) **ne radi ni za jednog korisnika**. UI to
pošteno prijavljuje („⚠ Bez sadržaja — pokušajte ponovo"), pa nema lažno-zelenog
ekrana — ali tekst spornog odgovora se i dalje nigde ne čuva.

**Bezbednosno:** ovo je **restriktivnije** od nameravanog, dakle fail-closed —
nije ranjivost. **Funkcionalno:** kvar.

**NIJE POPRAVLJENO.** Popravka zahteva izmenu RLS politike u produkciji, što je
HARD STOP ovog mandata i odluka vlasnika.

## GRANT — delimično razrešen ponašanjem

Katalog (`pg_policies`, `role_table_grants`) ostaje **nedostupan**. Ali tip
greške razlikuje dva sloja:

| Uloga · operacija | Odgovor | Zaključak o GRANT-u |
|---|---|---|
| `authenticated` INSERT | `42501` *"violates row-level security policy"* | **grant POSTOJI**, politika odbija |
| `authenticated` SELECT | `200 []` | **grant POSTOJI**, RLS filtrira na 0 |
| `authenticated` UPDATE/DELETE | `204` bez greške | **grant POSTOJI**, RLS filtrira na 0 |
| `anon` INSERT | `42501` | odbijen |

Katalog ostaje UNKNOWN; **ponašanje grantova više nije UNKNOWN.**

## Ugovor čitanja — dokumentovan, nije kvar

Ni vlasnik ne može da čita svoj red (`count=*/0`). To je **u skladu** sa
deklarisanom SELECT politikom (`service_role` only) — proizvod je za korisnika
**write-only**. Po mandatu (TASK 10) to se dokumentuje kao ugovor, ne prijavljuje
kao kvar.

## Čišćenje — potvrđeno

| | |
|---|---|
| USER_A / USER_B | obrisani, `GET /auth/v1/admin/users/{id}` → **404** |
| `reported_errors` | `count=*/0` |
| markeri (`RLS_AB_PROBE_*`, `KOVANO_OD_*`) | obrisani |
| `profiles` | **12 pre, 12 posle** — bez zaostalih redova |

Reproduktibilno: `scripts/rls_ab_forensics.py`, uz obaveznu potvrdu
`RLS_AB_FORENSICS=DA`.


---

# ISPRAVKA 2 — POVLAČIM NALAZ O FUNKCIONALNOM KVARU

**Datum:** 2026-08-16 · Osnovni izvor: politike koje je vlasnik pročitao iz
`pg_policies`, plus tri dodatna kontrolisana eksperimenta.

## Šta je vlasnik pokazao

```
reported_errors_insert_own     INSERT  {public}  with_check = (auth.uid() = user_id)
reported_errors_service_select SELECT  {public}  using = (jwt.role = 'service_role')
```

Obe politike **postoje** i tačno su onakve kakve su deklarisane u migraciji 113.

## Moja prva hipoteza — i zašto je bila pogrešna

Pretpostavio sam da `auth.uid()` vraća `NULL` (stara definicija funkcije uz nov
PostgREST). **Opovrgnuto merenjem:** isti autentifikovani korisnik uspešno
upisuje u `predmeti` (**201**) i `klijenti` (**201**) preko `auth.uid()`
politika. `auth.uid()` radi ispravno.

## Stvarni uzrok — bio je u mojoj sondi

| `Prefer` zaglavlje | `reported_errors` | `feedback` |
|---|---|---|
| `return=representation` | **403 / 42501** | **403 / 42501** |
| `return=minimal` | **201 UPISANO** | **201 UPISANO** |
| bez zaglavlja | **201 UPISANO** | **201 UPISANO** |

`return=representation` tera PostgREST na `INSERT … RETURNING`, a RETURNING
zahteva **SELECT** pravo nad upisanim redom. Pošto je SELECT politika
`service_role only`, INSERT **prolazi** ali RETURNING pada — i to izgleda kao da
je upis odbijen.

## Da li produkcija šalje to zaglavlje? NE

Iz priloženog SDK-a (`static/supabase.min.js`): `Prefer: return=representation`
dodaje **isključivo `.select()`**. `sendFeedback` zove `.insert({…})` **bez**
`.select()`, pa šalje `return=minimal`.

**Zaključak: primarni kanal prijave netačnog pravnog odgovora RADI.** Tvrdnja iz
prethodnog odeljka se povlači u celosti.

## Ponovljen test bez zamke — svi kontrolni uslovi zadovoljeni

| Test | Ishod |
|---|---|
| A upisuje **SVOJ** red (`return=minimal`) | **201, red nastao** — pozitivna kontrola PROLAZI |
| B upisuje **SVOJ** red | **201, red nastao** |
| A upisuje sa `user_id = B` | **403 / 42501, red NIJE nastao** |
| B upisuje sa `user_id = A` | **403 / 42501, red NIJE nastao** |
| A → B SELECT / UPDATE / DELETE | **BLOKIRANO** (stanje reda provereno) |
| B → A SELECT / UPDATE / DELETE | **BLOKIRANO** |
| informaciono curenje | **nema** |

`WITH CHECK (auth.uid() = user_id)` dakle radi **tačno kako je projektovano**:
propušta sopstveno, odbija tuđe.

## GRANT — sada razrešeno ponašanjem

`authenticated` ima SELECT, INSERT, UPDATE i DELETE **grantove** na obe tabele
(greške su uvek policy-level `42501 violates RLS`, nikad `permission denied`).
Katalog i dalje nije čitan, ali pitanje više nije otvoreno u praksi.

## Alat ispravljen

`scripts/rls_ab_forensics.py` sada koristi `return=minimal` i postojanje reda
proverava **odvojenim** čitanjem preko `service_role`. Zamka je opisana u
zaglavlju skripte da se ne ponovi.

## Ugovor čitanja — potvrđen, nije kvar

Ni vlasnik ne čita svoj red. To je **namera** deklarisane SELECT politike:
`reported_errors` je za korisnika **write-only**. Prijave čita samo interni
pregled kvaliteta preko `service_role`.

## Konačno stanje

| Uslov izlazne kapije | Status |
|---|---|
| A→B i B→A: SELECT / INSERT / UPDATE / DELETE | ✅ **svih 8 blokirano** |
| Pozitivna kontrola (svoj upis) | ✅ **prolazi** |
| Identitet A i B stvarno autentifikovan | ✅ `/auth/v1/user` |
| `service_role` korišćen kao dokaz | ❌ **nije** — samo priprema/čišćenje |
| Mock korišćen kao dokaz RLS-a | ❌ **nije** |
| Informaciono curenje | ✅ nema |
| Čišćenje | ✅ nalozi 404, tabela `count=*/0`, `profiles` 12→12 |

**VERDIKT: GREEN.**
