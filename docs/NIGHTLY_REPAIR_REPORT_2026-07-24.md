# Nightly Autonomous Execution — Complete System Repair & Polish

**Datum:** 2026-07-24
**Izvor:** Sveobuhvatna analiza svih 12 sekcija platforme (isti dan)
**Obim:** 11 stavki, 3 faze (P0 kritični hotfiksi → P1 unifikacija/enterprise → P2 optimizacije/novi moduli)
**Rezultat:** 11/11 stavki završeno, testirano, commit-ovano i pushed. **2181/2181 testova prolazi** (2140 na početku ove misije + 41 novih/prepravljenih testova), nula regresija.

Svaka stavka ispod je zaseban git commit na `main` grani, sa sopstvenim skupom testova koji je prošao PRE nego što je commit napravljen (isti obrazac ponovljen 11 puta: analiziraj → implementiraj → testiraj → pokreni pun pytest suite → commit → push).

---

## FAZA 1 — Kritični hotfiksi i bezbednost (P0)

### 1. Rušenje u `routers/zadaci.py:432` — `commit faafff5`

**Problem:** `GET /api/zadaci/statistika` je koristio `asyncio.coroutine(lambda: ...)()` kao fallback granu za korisnike bez tima. `asyncio.coroutine` je uklonjen u Python 3.11 — ovaj kod je bacao `AttributeError` ODMAH pri građenju `asyncio.gather()` tuple-a, pre nego što bi gather uopšte krenuo. **Ovo je rušilo endpoint za SVAKOG solo advokata** (bez `kancelarija_id`) — što je, prema ranijem product istraživanju ovog projekta, većina korisničke baze.

**Popravka:** Restrukturirano tako da se tim-upit uopšte ne pravi kad korisnik nema kancelariju — bez veštačkog "praznog" coroutine placeholder-a.

**Testovi:** `tests/test_zadaci.py` (3 nova testa) — solo advokat više ne ruši endpoint, član tima i dalje dobija oba skupa podataka, prazna lista zadataka radi ispravno.

---

### 2. Blokiran event loop u `routers/multi_agent.py` — `commit 2c75b37`

**Problem:** 7 sinhronih `supa.table(...).execute()` poziva unutar `run_agent`/`run_parallel` (async funkcije) bez `asyncio.to_thread` omotača — svaki je blokirao CEO event loop za trajanje Supabase round-trip-a. Pod bilo kakvim konkurentnim opterećenjem, ovo zaustavlja SVE ostale zahteve na istom worker-u, ne samo poziv koji koristi AI agenta. Ista klasa greške već ranije pronađena i ispravljena u `main.py` — ovde promašena.

**Popravka:** Svih 7 poziva (dohvatanje konteksta predmeta, dokumenata, ročišta, Case Genome-a, billing stavki — dva puta) omotano u `asyncio.to_thread`.

**Testovi:** `tests/test_multi_agent.py` (+2 testa) — popunjeni sa STVARNIM (ne praznim) podacima za predmet_dokumenti/rocista/case_dna/billing_entries, tako da su svih 7 popravljenih mesta stvarno testirana sa sadržajem koji stiže do LLM prompta, ne samo prazni fallback-ovi koji ne bi uhvatili pokvareno `to_thread` ožičavanje.

---

### 3. SEC-001 propust u `routers/doc_templates.py:187` — `commit faccfc7`

**Problem:** `POST /api/doc-templates/sacuvaj` je upisivao belešku u `predmet_beleske` koristeći `req.predmet_id` bez ikakve provere da predmet pripada pozivaocu. Bilo koji prijavljeni korisnik je mogao da upiše belešku u TUĐ predmet pogađanjem/dobijanjem njegovog ID-a. Ista klasa ranjivosti kao SEC-001 (već zatvorena svuda drugde), ovde promašena.

**Popravka:** Dodata ista provera vlasništva koja se koristi svuda drugde (`api.py`'s `dodaj_belesku`, `shared/voice_tools.py`).

**Testovi:** `tests/test_doc_templates_ownership.py` (3 nova testa) — tuđi/nepostojeći predmet vraća 404 bez upisa, sopstveni predmet i dalje radi, provera je skopirana na STVARNOG pozivaoca (ne samo "da li predmet postoji negde").

---

### 4. Trka pri pokretanju tajmera u `routers/billing.py` — `commit c08e44f`

**Problem:** `POST /billing/timer/start` je radio "proveri pa upiši" (SELECT postoji li aktivan tajmer, pa INSERT) bez transakcione izolacije. Dva brza klika ili dva otvorena taba mogu OBA proći proveru pre nego što ijedan upis commit-uje — dva istovremeno aktivna tajmera za istog korisnika, tiho kvareći naplaćene sate. Ista klasa greške kao TOCTOU trka u `audit_immutable` (pronađena i popravljena ranije ove sesije, migracija 081) — isti dokazan obrazac primenjen ovde.

**Popravka:** `migrations/084_timer_sessions_unique_active.sql` dodaje delimični UNIQUE indeks `timer_sessions(user_id) WHERE aktivan = true`. Verifikovano direktno protiv produkcije PRE pisanja migracije: nula postojećih duplikata, pa se primenjuje kao čist, bezuslovan indeks. Kod hvata rezultujući 23505 sudar i prevodi ga u isti čist 409 koji SELECT-provera već vraća.

**Testovi:** `tests/test_billing_timer_race.py` (4 nova testa) — normalan start, postojeći-nedavni-tajmer 409, STVARNA trka (SELECT ne vidi ništa, INSERT udara u sudar) vraća 409 ne 500, nepovezane greške baze i dalje prolaze.

**⚠️ Founder akcija:** pokrenuti `migrations/084_timer_sessions_unique_active.sql` u Supabase-u.

---

## FAZA 2 — Unifikacija podataka i enterprise popravke (P1)

### 5 & 7. Dashboard: spajanje tabela rokova + kozmetički bag — `commit adf0626`

**Problem (item 5):** Command Center je čitao rokove ISKLJUČIVO iz `predmet_hronologija`. AI Deadline Guardian (`routers/zastarelost.py::guardian_scan`) i 30+ drugih modula rade nad potpuno odvojenom `rokovi` tabelom. Rok upisan preko bilo kog `rokovi`-pisućeg toka je bio nevidljiv na glavnom dashboard-u, i obrnuto.

**Problem (item 7):** `matter_health_score`'s `faktori.aktivnost` je prijavljivao `min(25, score if score <= 25 else 25)` — besmislenu re-izvedenu vrednost iz UKUPNOG skora, ne stvarni 0/25 dodeljen u koraku "Aktivnost" par linija iznad.

**Popravka:** Dodat 10. paralelni upit (isti `asyncio.gather` batch, isti fail-soft `return_exceptions=True` obrazac) koji dohvata iz `rokovi` i spaja rezultate u `rokovi_7`/`hitni_rokovi` — samo na strani čitanja, nijedna write putanja nije dirana. `aktivnost_poeni` se sada čuva u promenljivoj i stvarno prijavljuje.

**Testovi:** `tests/test_dashboard.py` (+4 testa) — rok SAMO iz `rokovi` tabele se sada pojavljuje na dashboard-u, oba izvora se spajaju bez gubljenja nijednog, `aktivnost` prijavljuje tačnu vrednost i za "nema aktivnosti" i za "ima aktivnosti" slučaj.

---

### 6. Delegiranje predmeta sada stvarno daje pristup — `commit 75de5ef`

**Problem:** `delegiraj_predmet` je upisivao `predmet_delegiranja` red, ali (a) nikad nije proveravao da `advokat_user_id` stvarno pripada istoj firmi — bilo koji string je bio prihvaćen, i (b) NIŠTA DRUGO u kodu nikad nije čitalo `predmet_delegiranja` za pristup — kolega kome je predmet "delegiran" nije mogao ni da ga VIDI. Izgledalo je gotovo u UI-ju, suštinski nije radilo ništa.

**Popravka:**
- `routers/enterprise.py`: dodata provera da delegirana osoba pripada istoj kancelariji (reuse `_get_firma_id`/`_get_firma_clan_ids`).
- `api.py::get_predmet`: ožičen stvaran (read-only) pristup — kolega sa aktivnom delegacijom sada MOŽE da vidi predmet. **Namerno ograničeno na READ putanju** — write akcije (beleške, izmene) ostaju gejtovane isključivo na originalnog vlasnika, dok se ne donese šira odluka o granicama delegiranog pristupa. Ovo je disclosed scope ograničenje, ne propust.

**Testovi:** `tests/test_enterprise_delegation.py` (6 novih testova).

---

## FAZA 3 — Optimizacije, paginacija i novi moduli (P2)

### 8. Paginacija za predmete i klijente — `commit b10d2b6`

**Problem:** `api.py::lista_predmeta` i `klijenti/router.py::list_klijenti` su povlačili CELU istoriju korisnika bez `.limit()`/`.range()`. `lista_predmeta` je TAKOĐE bio sinhron poziv unutar `async def` bez `asyncio.to_thread` — ista klasa greške kao stavka 2, zatečena dok se dodavala paginacija.

**Popravka:** Opcioni `limit`/`offset` (podrazumevano 200, ograničeno na 500) na obe rute — bez promene ponašanja za veliku većinu korisnika. `asyncio.to_thread` dodat gde je nedostajao.

**⚠️ Disclosed scope gap:** `select("*")` u `lista_predmeta` je NAMERNO neizmenjen — suženje na konkretne kolone bi zahtevalo poznavanje tačno kojih polja frontend koristi, što nije potvrđeno u ovoj sesiji. Menjanje bez te potvrde rizikuje da tiho pokvari UI.

**Testovi:** `tests/test_pagination_predmeti_klijenti.py` (5 testova).

---

### 9. Klasifikacija dokaza u pozadini — `commit ac5effe`

**Problem:** `routers/dokument.py::dokument_upload` je čekao GPT poziv za klasifikaciju dokaza u ISTOM `asyncio.gather` koji čeka Pinecone indeksiranje — korisnik je čekao rezultat koji mu nije bio odmah potreban.

**Popravka:** Fire-and-forget preko `asyncio.create_task`, isti obrazac kao postojeći `_background_cleanup`. Upload odgovor sada vraća `klasifikacija: null` + `klasifikacija_napomena` koja upućuje na POST `/api/dokument/klasifikuj-sesija` (postojeći, već izgrađen endpoint za klasifikaciju na zahtev).

**⚠️ Disclosed contract change:** odgovor upload rute više ne sadrži sinhronu klasifikaciju. Nijedan postojeći test nije proveravao staru vrednost (potvrđeno pre izmene), ali frontend koji direktno čita `klasifikacija` iz upload odgovora treba da pređe na poziv `klasifikuj-sesija`.

**Testovi:** `tests/test_dokument_upload_async_classification.py` (3 testa).

---

### 10. MS Word Add-in `taskpane.html` — `commit 9777b4c`

`integrations/word_addin/adapter.js` (izgrađen u ranijoj celini) nije imao UI u koji bi iscrtavao rezultate. `taskpane.html` sada postoji — tamna tema po Vindex-ovim `--vx-*` tokenima, prijava (token preko Office `roamingSettings`), ručna analiza tekućeg pasusa, prekidač za praćenje kucanja uživo, i lista sugestija obojena po tipu.

**Stvaran bag pronađen usput:** `manifest.xml` (napisan u ranijoj celini) je koristio `--` unutar `<!-- -->` komentara na više mesta — ovo je NEVALIDNO po XML specifikaciji (samo Python/JS komentari to tolerišu). Manifest je bio nevalidan XML od kad je prvi put napravljen, neprimećeno dok nije validiran pravim parserom ovde. Ispravljeno (zamenjeno sa "—").

**⚠️ Disclosed limit:** puna vizuelna/interaktivna provera (stvarno sideload-ovanje u Word) nije izvodljivo u ovoj sesiji — nije tvrđeno da je urađeno.

**Testovi:** `tests/test_word_addin_taskpane.py` (7 testova) — validan HTML, validan XML (regresiona brava za pronađeni bag), JS sintaksa oba fajla, i unakrsna provera da svaki `VindexAmbientAdapter.<metoda>()` poziv u `taskpane.html` stvarno postoji u `adapter.js`.

---

### 11. Grupisanje upita u pozadinskim agentima — `commit 5270b07`

**Problem:** `workers/background_agents.py` je radio 1-2 upita PO korisniku za rezoluciju organizacije, plus 1 upit PO (korisnik, tip-agenta) paru za proveru budžeta — O(korisnika × agenata) upita samo za knjigovodstvo, pre nego što bilo koji agent uopšte krene.

**Popravka:** Dva grupisana poziva:
- `_resolve_orgs_batched` — 2 upita UKUPNO rešavaju organizaciju za SVE aktivne korisnike odjednom.
- `_budget_used_by_org` — 1 upit dohvata sve relevantne redove za SVE organizacije odjednom, grupisano u Python-u; lokalno se uvećava tokom run-a (bez novih upita) da bi se očuvalo ponašanje "ne premaši budžet u istom run-u".

Ukupno: 3 upita bez obzira na broj korisnika/agenata, umesto O(korisnika) + O(korisnika × agenata).

**Dodatno (eksplicitno traženo):** `tests/test_cron_daily_dispatcher.py`'s `workers.background_agents.run_background_agents` NIJE bio mock-ovan ranije u tom deljenom test fajlu — radio je uživo protiv blage `_FakeSupa` lažne baze koja ne implementira `.not_`/`.in_`, tiho otkazujući unutar sopstvenog `try/except`-a i vraćajući prazan rezultat. Dispečer-nivo testovi su prolazili "slučajno", nikad stvarno ne testirajući ožičavanje Modula 10. Sada eksplicitno mock-ovan (isti obrazac kao svaki drugi modul), sa stvarnim proverama: rezultat modula se pojavljuje u odgovoru, greška modula ne blokira ostale module, timeout se prijavljuje kao "timeout" status.

**Testovi:** `tests/test_background_agents.py` prepisan za novi API (7 testova, uključujući brojanje upita), `tests/test_cron_daily_dispatcher.py` (+3 testa).

---

## Sažetak founder akcija

- [ ] Pokrenuti `migrations/084_timer_sessions_unique_active.sql` u Supabase-u (stavka 4).

## Sažetak svesno neizvršenih/ograničenih delova (disclosed, ne propust)

- Stavka 8: `select("*")` u `lista_predmeta` nije suženo (rizik nepoznatih frontend zavisnosti).
- Stavka 9: upload odgovor više ne nosi sinhronu klasifikaciju (namerna promena ugovora, frontend možda treba prilagođavanje).
- Stavka 6: delegiranje predmeta daje READ pristup; WRITE akcije i dalje gejtovane na originalnog vlasnika.
- Stavka 10: nema pune vizuelne provere u stvarnom Word okruženju.

## Test rezultati

| Tačka u misiji | Testova ukupno | Status |
|---|---|---|
| Početak (posle prethodne sesije) | 2140 | — |
| Posle Faze 1 (stavke 1-4) | 2152 | ✅ |
| Posle Faze 2 (stavke 5-7) | 2167 | ✅ |
| Posle stavke 8 | 2170 | ✅ (napomena: jedan lažni pad zbog konkurentnog uređivanja fajla tokom test run-a, ponovljeno čisto) |
| Posle stavke 9 | 2170 | ✅ |
| Posle stavke 10 | 2177 | ✅ |
| Posle stavke 11 (finalno) | **2181** | ✅ |

**Nula regresija kroz svih 11 stavki.**
