# FINAL_PHASE_A_RELEASE_GATE — Early Access, Faza A

**Kandidat:** PR #66, kod = `eb695ae8b14e96faae164196d67011d4c32f8701` (ovaj commit dodaje samo ovaj dokument; kod je nepromenjen).
**CI:** 11/11 zeleno na `eb695ae8`. **main:** `aaea99a4`. **Migracija 146:** nije primenjena.
**Oznake:** PROVEN = pročitan kod/konfiguracija ili test; INFERRED = zaključak iz dokaza; ASSUMED = pretpostavka; UNKNOWN = nije vidljivo odavde.

**Zaključak:** nije dokazan nijedan materijalni kvar koji traži izmenu koda ili migracije. Tri vrednosti treba podesiti pre puštanja, i za sve tri dovoljni su env ili Admin konzola: dnevni limit za 146, limit po operaciji i hard limit OpenAI projekta. Pored toga ostaju dva preduslova van koda: provajder (nije potvrđen) i potvrda email-a pri registraciji.

---

## 1. Zašto 300 operacija dnevno za `ai_osnovna_obrada` (0 kredita)

| Tvrdnja | Status |
|---|---|
| 300 je bio **predlog** po uzoru na `copilot_ambient` (200/dan, 0 kredita, migr. 083). Nije izveden iz izmerenog opterećenja. | PROVEN (tekst migracije) |
| Na ovaj red idu: Smart Intake posao (1 posao = 1 operacija), obrada događaja event bus-a i 12 ruta sa ručnom autentifikacijom. Među njima su `reasoning-graph/generate`, `genome-v2`, `dokaz`, `intake/kreiraj`, `smart_intake finalize` i `zakon_monitoring/proveri`. | PROVEN (inventar `rute.json`, `intake_worker.py:162`, `event_bus.py:1093`) |
| Smart Intake koristi samo `gpt-4o-mini`: klasifikacija sa `max_tokens=100` i ekstrakcija sa `max_tokens=400`. Najviše ≈ $0,03 po poslu, pri ulazu ograničenom na 100k tokena. | PROVEN (kod) / procena INFERRED |
| Neke rute na ovom redu koriste `gpt-4o` sa velikim izlazom: `case_dna` 4000, `legal_reasoning_engine` 2500, `matter_intel` 2000. Jedan takav poziv sa punim ulazom procenjuje se na ≈ $0,29. | PROVEN (kod) / procena INFERRED |
| **Teorijski najgori slučaj po nalogu i danu:** 300 × $3 (granica operacije) = **$900**. **Realan napad:** 300 × ≈ $0,30 (jedan veliki gpt-4o poziv po operaciji) ≈ **$90 po nalogu dnevno, bez ijednog kredita.** | INFERRED |
| Legitiman dnevni obim jednog advokata na ovom redu nije izmeren. | UNKNOWN |

**Minimalna ispravka:** migracija ostaje kakva jeste. Vrednost je **izričita odluka osnivača o riziku pilota**; 100 nije prihvaćeno samo zato što je manje od 300 (v. Dodatak, tabela opcija). Vrednost se menja u Admin Feature Console, bez deploy-a.

**Dokaz prihvatanja:** upit za proveru iz migracije 146 vraća `dnevni_limit = 100`. Prva nedelja log linija `[AI_BUDZET] operacija zatvorena izvor=… feature=ai_osnovna_obrada` daje stvarni broj operacija i stvarni trošak po nalogu.

## 2. Da li postoji stvarni finansijski budžet po Early Access korisniku

**Ne postoji. PROVEN.** Nijedna granica nije izražena u USD po nalogu. Postoje:

| Sloj | Šta ograničava | Jedinica | Status |
|---|---|---|---|
| Krediti (`user_credits`, migr. 107) | plaćene funkcije | broj kredita, ne USD. 15 na registraciji, bez mesečnog punjenja | PROVEN |
| Dnevni/mesečni limiti po funkciji (`feature_registry`, migr. 108) | broj operacija | operacije | PROVEN |
| Granica operacije (`VINDEX_AI_MAX_USD_OPERACIJE`, `…_POKUSAJA_…`) | jedna operacija | **procenjeni** USD (≈ znakovi/3 + `max_tokens` × cenovnik) | PROVEN |
| Projektni brojač u procesu | ceo proces | procenjeni pa stvarni USD | PROVEN, **ne-autoritativan** (v. §4) |

Izloženost jednog naloga je zbir (dnevni limit × granica operacije) po svim funkcijama sa 0 kredita, uvećan za (krediti × granica operacije) na plaćenim funkcijama. **Jedini stvarni USD plafon je hard limit OpenAI projekta (UNKNOWN).**

**Minimalna ispravka:** u ovoj fazi nema nove USD granice po nalogu, jer bi to bio novi obračunski sistem. Izloženost se svodi preko dnevnog limita (§1), granice operacije (§3) i hard limita projekta (§4).

**Dokaz prihvatanja:** odgovor osnivača da je hard limit uključen, plus snimak ekrana Limits stranice projekta.

## 3. $3 po operaciji naspram ranijih $0,50

| Tvrdnja | Status |
|---|---|
| Granica od $0,50 ne postoji nigde u repozitorijumu. Ovaj rad nije koristio njen izvor. | PROVEN (`git grep`) / poreklo UNKNOWN |
| Procena je namerno konzervativna. Poziv bez `max_tokens` dobija rezervu od 8000 izlaznih tokena, što je na `gpt-4o` $0,08 samo za izlaz. Jedan `gpt-4o` poziv sa 30k ulaza i 4000 izlaza procenjuje se na ≈ $0,12. | PROVEN (kod) |
| Sa $0,50 prolaze ≈ 3–5 velikih `gpt-4o` poziva po operaciji. Višekoračni tokovi (agenti, sinteza Law Brain-a, map-reduce dokumenata) mogu biti odbijeni kao `OPERACIJA_PREVELIKA` iako su legitimni. | INFERRED |
| $3 je ≈ 6× veća izloženost po operaciji od $0,50. Raspodela stvarnih troškova legitimnih operacija nije izmerena. | UNKNOWN |

**Minimalna ispravka (bez koda):** za pilot postaviti `VINDEX_AI_MAX_USD_OPERACIJE=1.0` u Render-u. Posle 7 dana iz linija `operacija zatvorena … procena_usd=` uzeti p99 i postaviti granicu na p99 × 1,5. Odbijanja se vide kao `OPERACIJA_PREVELIKA` u logu.

**Dokaz prihvatanja:** 0 odbijanja `OPERACIJA_PREVELIKA` za legitimne naloge u prvoj nedelji, i izvučen p99.

## 4. Da li projektni limit važi globalno

| Tvrdnja | Status |
|---|---|
| Brojač u procesu je zaseban po procesu i radniku (`WEB_CONCURRENCY`). Nulira se pri svakom restartu i deploy-u, a svaki push na main je deploy. | PROVEN (kod) |
| `Procfile` (gunicorn) ima `max_requests=1000±100`, pa bi se radnik i brojač nulirali na ≈ 1000 zahteva. `Dockerfile` (uvicorn, 1 proces) nema takvo ograničenje. Koji od njih Render koristi nije vidljivo. Docker je verovatniji, jer CI gradi i proverava produkcionu sliku. | PROVEN (fajlovi) / izbor INFERRED |
| **Brojač u procesu nije granica. Jedina globalna granica je hard limit OpenAI projekta**, i on važi za sve radnike, restarte i ceo saobraćaj tim ključem, uključujući Realtime glas (`wss://api.openai.com`, isti `OPENAI_API_KEY`). | PROVEN (dok. OpenAI-ja + kod) / konfiguracija UNKNOWN |
| OpenAI ne primenjuje limit trenutno, pa potrošnja može malo da pređe limit. | PROVEN (dokumentacija) |

**Minimalna ispravka:** nema izmene koda. Uslov za puštanje je hard limit projekta (v. „Akcije osnivača“).

**Dokaz prihvatanja:** u podešavanjima projekta uključeno je „Enforce a hard limit“ = $50. Produkcijski `OPENAI_API_KEY` pripada tom projektu: poslednje 4 cifre ključa u Render-u = ključ projekta.

## 5. Da li besplatne funkcije (0 kredita) mogu da iscrpe zajednički budžet

**Da. INFERRED, uz PROVEN mehanizam.**
- Funkcije sa 0 kredita (`ai_osnovna_obrada`, `copilot_ambient` 200/dan, `morning_briefing` 5/dan i druge) ograničene su samo dnevnim limitom po nalogu.
- Registracija ne traži potvrdu email-a (`api.py:3356`, `email_confirm=True`, PROVEN), pa broj naloga nije ograničen ničim osim limita od 5/min po IP-u.
- Zbir preko mnogo naloga iscrpljuje projektni limit. Posle toga **svi** korisnici, i plaćajući, dobijaju 503 `PROJEKTNI_LIMIT` ili 429 od OpenAI-ja. Trošak je ograničen, ali je usluga ugrožena.
- Na `main` iste putanje nemaju nikakvo ograničenje, pa je Faza A strogo bolja.

**Minimalna ispravka:** dnevni limit 100 (§1) i potvrda email-a pre bilo kakvog javnog pridobijanja korisnika (§9). Do tada pristup ostaje na pozivnicama, odnosno postojećem toku zahteva za pristup kancelarije.

**Dokaz prihvatanja:** nalog bez potvrđenog email-a ne može da se prijavi (test toka), plus hard limit iz §4.

## 6. Da li multiplikatori ili neuspele operacije daju neplaćen, a naplativ rad

| Slučaj | Ishod | Status |
|---|---|---|
| Multiplikator > 1 | **Ispravljeno:** puna poznata cena (ili izjavljena gornja granica) rezerviše se pre prvog poziva; nalog bez nje dobija 402 sa 0 poziva (v. Dodatak). | PROVEN (testovi + PostgreSQL) |
| Ruta pukne posle uspešnog AI poziva | Nenamirena rezervacija se vraća, a provajder je rad naplatio. Isto ponašanje kao na `main`. | PROVEN (kod `zatvori`) |
| Timeout ili prekid veze (nepoznat ishod) | Zadržava se osnovna cena (krediti × 1), uz log `[AI_BUDZET_RECONCILE]`; ostatak pune rezervacije se vraća. | PROVEN (test) |
| Definitivna greška provajdera (`APIStatusError`) | Rezervacija se vraća. OpenAI obično ne naplaćuje odbijen zahtev. | PROVEN (kod) / naplata INFERRED |
| Funkcije sa 0 kredita | Neplaćene po dizajnu (odluka o ceni). | PROVEN |

Sve ove slučajeve ograniče dnevni limit, granica operacije i hard limit projekta. Zadržavanje rezervacije pri padu rute bi naplatilo korisniku neuspeo rezultat, i bilo bi pogrešno za 23 rute koje namerno ne naplaćuju. Zato ovde **nema ispravke koda**.

**Dokaz prihvatanja:** broj linija `402` posle izvršenog rada i `[AI_BUDZET_RECONCILE]` u prvoj nedelji. Akcija sledi tek ako je broj materijalan.

## 7. Azure i Cohere

| Tvrdnja | Status |
|---|---|
| **Cohere:** paket `cohere` nije u `requirements.txt`, a grana traži i `VINDEX_COHERE_RERANK`. U produkcionoj slici je nedostižan. | PROVEN |
| **Anthropic/Gemini:** samo u `requirements-dev.txt`. `ai_fabric` nema produkcionih pozivalaca. | PROVEN |
| **Azure:** ako su `AZURE_OPENAI_KEY` i `AZURE_OPENAI_ENDPOINT` postavljeni, chat, embeddings i audio idu na Azure. Brana aplikacije i dalje važi (isti SDK resursi i `_build_request`), ali **OpenAI projektni limit ne pokriva Azure**. Realtime glas i dalje ide na OpenAI. | PROVEN (kod) |
| Azure nema ekvivalent tvrdog limita potrošnje za OpenAI pay-as-you-go. Budžeti u Cost Management-u šalju upozorenja. | INFERRED (opšte znanje, nije provereno za ovaj nalog) |
| Da li su Azure promenljive postavljene u Render-u. | UNKNOWN |

**Minimalna ispravka:** osnivač potvrđuje da Azure promenljive **nisu** postavljene. Ako jesu, puštanje je blokirano dok se ne odluči kako se ograničava Azure.

**Dokaz prihvatanja:** log pri startu `[AI] Koristi standardni OpenAI API` (`shared/ai_client.py`).

## 8. Kompatibilnost i redosled za migraciju 146

| Tvrdnja | Status |
|---|---|
| 146 je samo `INSERT … ON CONFLICT DO NOTHING`. Ne menja postojeće redove. | PROVEN |
| Kod na `main` (`aaea99a4`) nigde ne čita `ai_osnovna_obrada`, pa je 146 bezbedna i **pre** spajanja PR-a. | PROVEN (`git grep` na `main`) |
| Red ne ulazi u javnu matricu cena. `/api/plan/pricing-matrix` traži `business_group_id`, a 146 ga ne postavlja. U `/api/plan/status` se vidi kao „Osnovna AI obrada“ tek kad je korisnik upotrebi. | PROVEN (`routers/plans.py`) |
| Bez 146 nova brana odbija (503) Smart Intake, event bus AI i 12 ruta sa ručnom autentifikacijom. Keš registra se osvežava za 60 s, pa kasno pokretanje 146 rešava stanje bez deploy-a. | PROVEN (kod, `_CACHE_TTL_S = 60`) |

**Redosled:**
1. Pokrenuti 146 u Supabase SQL Editor-u i proveriti upitom.
2. Postaviti `dnevni_limit` u Admin konzoli (§1).
3. Potvrditi OpenAI projekat, ključ i Azure (§4, §7).
4. Podesiti env vrednosti (§3).
5. Spojiti PR #66, što je i deploy.
6. Smoke test: jedan Smart Intake dokument, jedno pitanje i nalog sa 0 kredita → 402.

## 9. Preduslovi za potvrdu email-a

| Tvrdnja | Status |
|---|---|
| `/api/register` pravi nalog preko `auth.admin.create_user` sa `email_confirm=True`, bez potvrde. | PROVEN |
| Potvrdni email bi slao Supabase Auth, ne SMTP aplikacije. Ugrađeni Supabase SMTP ima niske limite slanja i nije za produkciju. Sopstveni SMTP u Supabase Auth podešavanjima nije potvrđen. | INFERRED / UNKNOWN |
| Izlazni email aplikacije (`EMAIL_SMTP_*`) **nema dokazanu isporuku**: email cron podsetnika je isključen, a stvaran prijem u sanduče nije potvrđen (v. memoriju projekta). | PROVEN (stanje dokumentovano) / isporuka UNKNOWN |

**Minimalna ispravka (van ove faze, posebna odluka):**
1. Podesiti sopstveni SMTP u Supabase Auth, sa SPF/DKIM za `vindex.rs`.
2. Proveriti prijem na Gmail i Outlook.
3. Tek onda u `/api/register` preći na tok sa potvrdom.

Do tada nema javne registracije za mase. Early Access ide kroz postojeći zahtev za pristup kancelarije.

**Dokaz prihvatanja:** potvrdni email stigne u Gmail i Outlook pristigle za manje od 2 min, a nepotvrđen nalog dobije odbijenu prijavu.

## 10. Bezbedno vraćanje (rollback)

| Tvrdnja | Status |
|---|---|
| Brana se nikad ne gasi sama. `rezim()` čita samo `VINDEX_AI_BUDZET`. Pad brojača i pad baze **odbijaju** poziv (fail-closed); nema automatskog prelaska u `off`. | PROVEN (kod + mutacija M11) |

**Lestvica vraćanja, od najmanje do najveće mere:**
1. **Podešavanje bez gašenja brane**, sve bez deploy-a:
   - `VINDEX_AI_MAX_USD_OPERACIJE`, `…_POKUSAJA_…`, `VINDEX_AI_MODELI` u Render-u;
   - `dnevni_limit` u Admin konzoli.

   Ovo je odgovor na lažna odbijanja legitimnog rada.
2. **Gašenje jedne grupe:** `aktivno=false` na `ai_osnovna_obrada` gasi samo tu AI obradu. To je strože, nikad labavije.
3. **Vraćanje koda:** `git revert` merge commit-a na `main` vraća stanje `aaea99a4`. Red iz 146 ostaje i bezopasan je, pa baza ne treba da se vraća. Pre ovog koraka **mora** biti uključen hard limit projekta, jer revert vraća staru rupu iz A1.
4. `VINDEX_AI_BUDZET=off` ima isti efekat kao korak 3, bez deploy-a. To je samo ručna, svesna odluka osnivača i nikad podrazumevano stanje.

**Dokaz prihvatanja:** posle svakog koraka, nalog sa 0 kredita na plaćenoj funkciji dobija 402 i 0 poziva provajdera. To važi za korake 1 i 2; za korake 3 i 4 to je očekivano izgubljeno.

---

## Akcije osnivača (tačan redosled)

1. **OpenAI** (izričita odluka):
   - projekat „Vindex Early Access“;
   - Spend limit $50 sa uključenim **Enforce a hard limit**;
   - upozorenja na $25 i $40;
   - dozvoljeni samo modeli iz §8 izveštaja Faze A;
   - nov ključ projekta upisan kao `OPENAI_API_KEY` u Render-u.
2. **Render:** potvrditi da `AZURE_OPENAI_KEY`/`AZURE_OPENAI_ENDPOINT` nisu postavljeni. Postaviti `VINDEX_AI_MAX_USD_OPERACIJE=1.0`.
3. **Supabase:** pokrenuti `migrations/146_ai_osnovna_obrada.sql` i upit za proveru. U Admin konzoli postaviti `ai_osnovna_obrada.dnevni_limit` na vrednost izabranu u Dodatku (izričita odluka o riziku).
4. **Odluka:** potvrda email-a i Supabase SMTP pre javne registracije (§9).
5. Tek posle 1–3: spojiti PR #66 i izvršiti smoke test iz §8.

## Dodatak (2026-11-02): multiplikator poznat pre poziva i dnevni limit

### Multiplikator — kvar ISPRAVLJEN (P0, 2026-11-02)

**Invarijanta:** kada je puna ovlašćena cena poznata pre prvog poziva provajdera, cela cena se atomično rezerviše pre tog poziva.

**Pre ispravke (PROVEN, `ab60623c`):**

| Slučaj | Izmereno |
|---|---|
| stanje 1, cena 3 | 402 posle 1 poziva, stanje 0 |
| stanje 2, cena 3 | 402 posle 1 poziva, stanje 1 |
| stanje 3, dva paralelna zahteva | oba 402, 2 poziva, stanje 1 |

**Ispravka.** Koristi samo postojeću rezervaciju i namirenje; nema novog obračunskog sistema ni migracije.

1. `UsageService.rezervisi_za_operaciju` rezerviše **krediti × multiplikator**, istom formulom kao `consume()`. Multiplikator je onaj koji je ruta izjavila, a inače `credit_multiplier` iz registra. Kredite oduzima i dalje atomični `deduct_n_credits` (migracija 107), a upotrebu broji atomični `increment_feature_usage` (migracija 108).
2. Novo: `ai_budget.ocekivani_multiplikator(n)`. Ruta njime izjavljuje svoju cenu PRE prvog poziva. Izjava posle rezervacije se ignoriše i beleži kao greška rute.

   | Ruta | Izjava | Zašto |
   |---|---|---|
   | `routers/strategija.py`: red-team, litigation, sudija, due-diligence, revizor, witness, sudija-v2, v2/analiza (8) | `1` | jedan modul = bazna cena (`consume(multiplier=1)`), ne registarskih ×6 |
   | `routers/strategija.py`: kompletna-analiza | — | registar ×6 je stvarna cena: rezerviše se 6 |
   | `routers/digital_twin.py`: šta-ako | `1` | `consume(multiplier=1)`; simulacija ostaje registar ×3 |
   | `routers/strategy_simulator.py`: sledeći potez | `1` | `consume(multiplier=1)`; nova partija ostaje registar ×2 |
   | `routers/multi_agent.py`: run-parallel | broj izabranih savetnika | gornja granica; naplata = isporučeni odgovori |
   | `routers/multi_agent.py`: pipeline | broj koraka | gornja granica; svaki korak (`run_agent` → `consume`) naplaćuje iz iste rezervacije |

3. **Namirenje** (`_namiri_rezervaciju`) uzima naplatu IZ rezervacije, bez novog odbitka:
   - prvi `consume()` iste funkcije ne broji upotrebu ponovo;
   - svaki sledeći `consume()` u istoj operaciji broji upotrebu kao i ranije;
   - samo deo cene iznad rezervacije se oduzima posle poziva, i to se beleži kao greška rute.
4. **Kraj operacije** (`zatvori`) vraća neiskorišćen ostatak rezervacije kroz `refund_n_credits`. Nepoznat ishod bez ikakvog namirenja zadržava **samo osnovnu cenu** (krediti × 1), kao pre ispravke; ostatak se vraća.

**Prihvatanje:**

| Slučaj | Pozivi provajdera | Stanje pre → posle | Upotreba | Test |
|---|---:|---|---|---|
| cena 3, stanje 1 | **0** | 1 → 1, 402 | 0 | `test_multiplikator_nedovoljno…[1]` + PG |
| cena 3, stanje 2 | **0** | 2 → 2, 402 | 0 | `…[2]` + PG |
| cena 3, stanje 3 | 1 | 3 → 0, 200 | 1 događaj, 3 kredita | `test_multiplikator_tacno…` + PG |
| cena 3, dva paralelna, stanje 3 | 1 | 3 → 0, jedan 200 i jedan 402 | 1 | `test_multiplikator_dva_paralelna…` + PG |
| 20 paralelnih rezervacija, cena 3, stanje 10 (stvarni SQL) | — | 10 → 1, 3 uspeha i 17 × NO_CREDITS | — | `test_pg_20_paralelnih_rezervacija_pune_cene` |
| u trenutku prvog HTTP pokušaja | — | rezervacija već drži punu cenu (5 → 2) | — | `test_multiplikator_puna_cena_se_rezervise_pre_poziva` |
| jedan modul ×1 nad funkcijom ×3, stanje 1 | 1 | 1 → 0, 200 | 1 kredit | `test_jedan_modul_multiplier_1…` |
| ruta bez izjave koja naplati ×1, stanje 3 | 1 | 3 → 2; višak 2 vraćen jednom na kraju | 1 | `test_neizjavljen…` |
| dinamički, granica 3, isporučeno 3/2/1/0, stanje 5 | 3 | 5 → 2/3/4/5 | naplata = isporučeno | `test_dinamicki…` + PG |
| dinamički, stanje 2 < granica 3 | **0** | 2 → 2, 402 | 0 | `test_dinamicki_bez_gornje_granice…` |
| niz, granica 3, 1/2/3 koraka, stanje 3 | 1/2/3 | 3 → 2/1/0 | jedna upotreba po koraku (kao ranije) | `test_niz_koraka…` + PG |
| timeout (nepoznat ishod), cena 3, stanje 5 | 3 (SDK retry-ji) | 5 → 4: zadržana osnovna 1, vraćeno 2 | — | `test_nepoznat_ishod_zadrzava_samo_osnovnu_cenu` |
| definitivna greška provajdera (500) | 3 | 5 → 5 | — | `test_definitivna_greska…` |
| pre-deduct ruta, 0 kredita, 20 paralelnih, dupli zahtev | nepromenjeno | nepromenjeno | nepromenjeno | postojeći testovi A6 |

**Testovi i mutacije:**
- `tests/test_ai_cost_protection.py`: **59/59**.
- `tests/test_ai_cost_protection_postgres.py`: **11/11** nad PostgreSQL 17, sa doslovnim SQL-om migracija 107/108 i kroz ceo HTTP tok.
- Mutacije: **16/16 ubijeno**: 11 ranijih (M5 prilagođen novom namirenju) i 5 novih (M12 rezervacija bez multiplikatora, M13 izjava bez dejstva, M14 ostatak se ne vraća, M15 nepoznat ishod zadržava sve, M16 prvo namirenje ponovo broji upotrebu).

**Regresija:**
- Ciljane naplatne i bezbednosne svite (38 fajlova, uključujući `test_strategija_routes`, `test_multi_agent`, `test_usage_multiplier`, `test_beta_gate_credit_race_postgres`, `test_wave9_*`, `test_phantom_ai_charges`): **795 passed**.
- Svite koje dotiču `digital_twin`: **142 passed**.
- Cela svita, zaključan redosled (`-p no:randomly`), bez `tests/e2e`, Python 3.13: **13.430 passed, 14 failed, 337 skipped**.
  - Svih 14 padova postoji i na `main` `aaea99a4` (osnovni skup ima 25), a **novih padova nema**. Od toga su 2 `test_rc_cold_start` (provera commit izvora), a ostali su postojeći padovi okruženja.
  - 11 padova koji postoje samo na `main` (`test_tier_config`, `test_business_groups`, `test_feature_type`, `test_product_intelligence`) ovde prolaze. Grana ne menja te module, pa je to razlika okruženja između dva merenja (INFERRED), ne zasluga ispravke.

**Preostalo:** produkcijske vrednosti `credit_multiplier` mogle su biti menjane kroz Admin konzolu (UNKNOWN). Nova funkcija sa multiplikatorom većim od 1 i rutom koja naplaćuje ×1 bez izjave rezervisaće registarsku cenu. To je konzervativno: nalog bez te cene dobija 402 pre poziva, a višak se vraća. Ruta tada treba da dobije `ocekivani_multiplikator`.

### Dnevni limit `ai_osnovna_obrada` — opcije za izričitu odluku

Teorijski najgori slučaj je limit × $3 (granica operacije), a realni napad limit × ≈ $0,30 (jedan veliki gpt-4o poziv po operaciji). Oba su INFERRED. Legitiman obim nije izmeren (UNKNOWN).

| Limit dnevno | Realan napad po nalogu dnevno | Teorijski maksimum | Rizik za legitiman rad |
|---:|---:|---:|---|
| 300 (u migraciji) | ≈ $90 | $900 | najmanji |
| 100 | ≈ $30 | $300 | intake veći od ≈ 50–70 dokumenata dnevno, plus pozadina, može biti odbijen (ASSUMED) |
| 50 | ≈ $15 | $150 | veći uvoz predmeta u jednom danu verovatno udara u limit |

Sa granicom operacije od $1 (§3), teorijski maksimum se deli sa 3. Hard limit projekta ($50) ograničava zbir svih naloga bez obzira na izbor. Preporuka je **100 za zatvoren pilot**, uz pregled linija `operacija zatvorena … feature=ai_osnovna_obrada` posle 7 dana. Ipak, **ovo je odluka osnivača**.

## Klasifikacija

- **Spremno za pregled:** PR #66 sa P0 ispravkom multiplikatora, migracija 146 i ovaj izveštaj.
- **Nije spremno za produkciju** dok se ne završe akcije osnivača 1–3. Javna registracija ne treba da se otvara dok se ne završi akcija 4.
