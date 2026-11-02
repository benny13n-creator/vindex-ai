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

**Minimalna ispravka:** migracija ostaje kakva jeste. Posle pokretanja, osnivač u Admin Feature Console postavlja `dnevni_limit` za Early Access na **100**. To pokriva ≈ 50–70 dokumenata u Smart Intake-u plus pozadinsku obradu (ASSUMED). Realan najgori slučaj time pada na ≈ $30 po nalogu dnevno. Vrednost se menja bez deploy-a.

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
| Multiplikator > 1 | Rezerviše se osnovna cena. Razlika se namiruje posle poziva. Nalog koji nema razliku dobija 402 **posle** izvršenog rada, pa razlika ostaje neplaćena. | PROVEN (kod, test `test_namirenje_multiplikatora…`) |
| Ruta pukne posle uspešnog AI poziva | Nenamirena rezervacija se vraća, a provajder je rad naplatio. Isto ponašanje kao na `main`. | PROVEN (kod `zatvori`) |
| Timeout ili prekid veze (nepoznat ishod) | Rezervacija se zadržava, uz log `[AI_BUDZET_RECONCILE]`. | PROVEN (test) |
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
3. **Supabase:** pokrenuti `migrations/146_ai_osnovna_obrada.sql` i upit za proveru. U Admin konzoli postaviti `ai_osnovna_obrada.dnevni_limit = 100`.
4. **Odluka:** potvrda email-a i Supabase SMTP pre javne registracije (§9).
5. Tek posle 1–3: spojiti PR #66 i izvršiti smoke test iz §8.

## Klasifikacija

- **Spremno za pregled:** PR #66 (kod, testovi, CI 11/11), migracija 146, ovaj izveštaj.
- **Nije spremno za produkciju** dok se ne završe akcije osnivača 1–3. Javna registracija ne treba da se otvara dok se ne završi akcija 4.
