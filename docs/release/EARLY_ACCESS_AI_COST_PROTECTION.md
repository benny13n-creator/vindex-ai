# Early Access — Faza A: AI zaštita troška

**Grana:** `feature/ai-cost-protection` (od `main` = `aaea99a4`)
**Status:** `AI_COST_PROTECTION_READY_FOR_REVIEW` — spajanje, puštanje i promene OpenAI podešavanja čekaju odluku osnivača.
**Oznake:** PROVEN = izmereno testom ili čitanjem koda u ovom radu; INFERRED = zaključak iz dokaza; ASSUMED = pretpostavka; UNKNOWN = nije vidljivo odavde.

## 1. Problem (A1)

`UsageService.consume()` je projektovan da se zove **posle** AI poziva. Docstring kaže: „generiši AI odgovor, pa consume“. Nalog bez kredita zato izvršava plaćen AI poziv, pa tek onda dobije 402. Trošak nastaje, a korisnik ga ne plaća.

**Statički inventar ruta koje dosežu provajdera** (AST, aproksimacija po imenu funkcije, `scratchpad/cost/inventar.py`):

| Klasa | Broj ruta |
|---|---:|
| naplata POSLE AI poziva | 55 |
| bez ikakve naplate/rezervacije | 23 |
| naplata PRE AI poziva | 3 |
| **ukupno** | **81** |

Inventar je donja granica jer ne vidi `to_thread(fn)` i pozadinske zadatke. Zato zaštita nije po rutama, nego na jedinoj tački kroz koju prolazi svaki OpenAI poziv.

**Runtime dokaz, PROVEN.** Ruta je produkciona (`POST /api/style/profil/gradi`, `api.app`). U oba stabla važe isti lažni provajder na HTTP transportu i ista lažna baza:

| Slučaj | `main` `aaea99a4` | grana |
|---|---|---|
| 0 kredita | **1 HTTP zahtev ka provajderu**, odgovor 500 „Interna greška“ | **0 zahteva**, 402 `NO_CREDITS` |
| 20 paralelnih, stanje 5, cena 1 | **9 zahteva**, 5 plaćenih | **5 zahteva**, 5 plaćenih |

## 2. Rešenje (A2)

Nema novog sistema prava, nove tabele ni nove cene. Ovaj modul samo primenjuje postojeće odluke:

- **Ko i za koju funkciju:** `PermissionService.require(feature)` posle uspešne autorizacije veže operaciju za nalog iz verifikovanog tokena.
- **Cena i limiti:** čitaju se iz `feature_registry`.
- **Rezervacija:** ide kroz `UsageService`, istim algoritmom kao `consume()`:
  - cooldown;
  - dnevni i mesečni limit;
  - atomični `increment_feature_usage` (migracija 108);
  - atomični `deduct_n_credits` (migracija 107).

  Razlika je što rezervacija radi **STROGO**: svaka greška baze odbija poziv.
- **Brana** (`shared/ai_budget.py`) je ugrađena u postojeće SEC-003 wrappere (`shared/ai_client.py`): chat, embeddings, Whisper/TTS. Uz to postoji i SDK `_build_request` hook, koji se izvršava jednom po HTTP pokušaju, uključujući SDK-ove interne retry-je.
- **Operacija** je jedan HTTP zahtev ili jedan pozadinski posao (Smart Intake job, događaj event bus-a). Pre PRVOG poziva provajdera rezerviše se osnovna cena funkcije. Kasniji `consume()` u ruti postaje **namirenje**: naplaćuje razliku do stvarne cene (multiplikator) ili vraća višak. Upotreba se ne broji dva puta i nema druge naplate.
- **Kraj operacije:**
  - Rezervacija koju ruta nije namirila vraća se, isto ponašanje kao pre brane.
  - Izuzetak je nepoznat ishod (timeout ili prekid veze): tada se rezervacija **zadržava** i beleži sa `[AI_BUDZET_RECONCILE]`.
- **Founder:** ne plaća kredite, ali važe ista ograničenja modela, ulaza, izlaza i operacije, kao i projektni limit.
- **Cron i admin dijagnostika:** sistemska operacija posle provere tajne, bez kredita, sa širim ali konačnim granicama, u projektnom limitu.
- **Realtime glas:** sirov WebSocket, mimo SDK-a. Rezervacija `voice` se radi pre veze, a sesija se prekida posle `VINDEX_AI_REALTIME_MAX_SEKUNDI` (600).
- **Progutano odbijanje:** 849 `except Exception` mesta u `routers/` pretvara odbijanje u 500. Postojeća 5xx granica u `api.py` i middleware brane tada vraćaju stvarni razlog (402/429/503). Trošak je zaštićen u oba slučaja.

### Invarijante

Sve invarijante su **PROVEN**. Svaki dokaz je test u `tests/test_ai_cost_protection.py`, osim gde je naveden drugi fajl.

| Invarijanta | Mehanizam | Dokaz |
|---|---|---|
| Nema plaćenog AI poziva pre rezervacije | brana u wrapperima + `_build_request` hook | `test_0_kredita…`, `test_sinhroni_klijent…`, `test_negejtovan_sdk_resurs…` |
| Atomično, bez trke | `deduct_n_credits` / `increment_feature_usage` u bazi | `test_20_paralelnih…` + `test_ai_cost_protection_postgres.py` (stvarni SQL, 20 niti) |
| Nema duple naplate iste idempotentne operacije | postojeći `IdempotencyMiddleware` + jedna rezervacija po operaciji | `test_dupli_zahtev…`, `test_ugnezdeni_podpozivi…`, `test_pre_deduct_ruta…` |
| Pad baze blokira AI | strogi režim (`strogo=True`) | `test_pad_baze_pri_rezervaciji_blokira` ×3, `test_pad_dnevnog_brojaca…` |
| Tuđi nalog/tenant ne troši tuđ budžet | identitet samo iz tokena; drugi kontekst u operaciji se odbija | `test_tudji_kontekst…`, `test_tudji_token…` |
| Retry-ji i podpozivi se broje | `_build_request` hook | `test_timeout…` (3 HTTP pokušaja = 3 u operaciji), `test_granica_pokusaja…` |
| Ograničenja modela i izlaza | lista dozvoljenih modela, `max_tokens` podrazumevano/najviše 8.000, `n=1` | `test_promena_modela…`, `test_prevelik_kontekst_i_izlaz…`, `test_izlaz_bez_granice…` |
| Stvarna upotreba se beleži ili je označena kao nedostupna | tokeni iz `usage` odgovora → `feature_usage_log.tokens_*`; bez `usage` → `stvarno_nedostupno` | `test_namirenje_multiplikatora…` |
| Nepoznat ishod se ne vraća tiho | zadržavanje + `[AI_BUDZET_RECONCILE]` | `test_timeout…`, `test_izgubljen_odgovor_baze…` |
| Founder/pozadina ne zaobilaze projektni limit | projektni limit pre svakog poziva | `test_projektni_limit_vazi_i_za_foundera`, `test_sistemska_operacija…`, `test_pozadinski_…` |
| Legitimni tokovi ostaju | namirenje umesto druge naplate; nenamirena rezervacija se vraća | `test_produkciona_ruta_sa_kreditom…`, `test_ruta_bez_naplate…`, `test_namirenje_multiplikatora…` |

**Mutacije:** 10 od 10 mutacija je ubijeno. Mutirani su async wrapper, rezervacija, strogi brojač, brojač pokušaja, namirenje, provera identiteta, zadržavanje nepoznatog ishoda, `PermissionService` vezivanje, lista modela i projektni limit.

## 3. Provajder (A3)

**Šta OpenAI podržava (PROVEN iz dokumentacije):**
- Hard limit na nivou projekta postoji samo uz uključen prekidač **Enforce a hard limit**. Bez njega postoje samo upozorenja.
- Kad se limit dostigne, odgovor je 429 `project_spend_limit_exceeded`. Primena nije trenutna, pa potrošnja može malo da pređe limit.
- Limit važi samo za saobraćaj naplaćen tom projektu.
- Projekat može da ograniči dozvoljene modele (allowlist).

**Trenutna konfiguracija je UNKNOWN.** Iz ove sesije nema pristupa OpenAI nalogu ni Render okruženju. Nepoznato je:
- da li produkcija koristi zaseban projekat;
- da li je hard limit uključen;
- da li je postavljen `AZURE_OPENAI_*`. Ako jeste, sav saobraćaj ide na Azure, a OpenAI projektni limit ga **ne pokriva**.

Zato šire puštanje ostaje **BLOKIRANO** dok osnivač ne potvrdi korake iz §8.

**Ključevi i provajderi u kodu (PROVEN, statički):**
- `OPENAI_API_KEY` (122 mesta), uključujući Realtime WebSocket.
- `AZURE_OPENAI_*` (redirect za ceo proces).
- `COHERE_API_KEY`: podrazumevano isključen. Uključuje se samo uz `VINDEX_COHERE_RERANK`. Ako se uključi, ide **mimo brane**.
- `ANTHROPIC_API_KEY` u `shared/ai_fabric.py`: nedostižan, jer `ai_fabric` ima 0 produkcionih pozivalaca, a `anthropic` nije u `requirements.txt`.

## 4. Telemetrija (A4)

- **`public.api_costs`:** ne postoji u pregledanoj šemi. `shared/cost.py::log_cost_to_db` u nju piše tiho bezuspešno, pa se ne koristi kao dokaz.
- **`ai_forensics`** (provenance): stvarni `token_usage_input/output` po pozivu iz odgovora provajdera. Upisi su fail-soft i asinhroni. To je **telemetrija, ne obračun**.
- **`feature_usage_log.estimated_cost_usd`:** statična procena iz registra po funkciji. **NIJE stvarni trošak** i ne koristi se kao takav.
- **Novo:**
  - Namirenje upisuje stvarne tokene operacije u `feature_usage_log.tokens_prompt/tokens_completion`.
  - Projektni brojač u procesu se puni stvarnim tokenima × cenovnik iz `shared/cost.py`. To je procena cene nad stvarnim tokenima.
  - Ako odgovor nema `usage`, ishod se beleži kao „NEDOSTUPNO“.
- **Autoritativan stvarni trošak** postoji samo na OpenAI-u (Usage/Costs po projektu). Iz aplikacije to je UNKNOWN.
- **Projektni brojač u procesu nije trajan:** restart ga nulira. Trajna granica je hard limit OpenAI projekta.

## 5. Zloupotreba i probni period (A5)

| Pitanje | Nalaz | Status |
|---|---|---|
| Ponovljena registracija | `/api/register` pravi nalog sa `email_confirm=True` (bez potvrde email-a); 5/min po IP-u; blokira samo poznate privremene domene. Svaki nov email = 15 kredita + besplatne funkcije sa sopstvenim dnevnim limitom. | PROVEN (kod); **materijalni rizik**, rešenje je odluka proizvoda |
| Jednokratna početna dodela | Trigger `on_auth_user_created_credits` + `_sb_ensure_credits_row(ignore_duplicates)` + auto-heal samo kad red ne postoji | PROVEN (kod + `test_ponovljena_registracija…`) |
| Obnova kredita kroz oporavak profila | Nijedna putanja u aplikaciji ne briše `user_credits`; postojeći red 0 ostaje 0 | PROVEN (grep + test) |
| 30-dnevni probni period | `_setup_trial` upisuje `plan='trial'`, `trial_kraj` — čita ga SAMO `GET /api/auth/trial/status`. `effective_tier` ga ne gleda. **Probni period se nigde ne sprovodi.** | PROVEN |
| Istek pristupa | Posle `trial_kraj` nalog ostaje `basic` sa preostalim kreditima; nema mesečnog punjenja kredita u kodu (poruka „sačekajte mesečni reset“ nema mehanizam iza sebe) | PROVEN (grep) |
| Pristup podacima posle iscrpljenih kredita | Krediti gejtuju samo AI; CRUD rute ne čitaju kredite | PROVEN (kod) |
| Founder izuzetak | `FOUNDER_EMAILS` iz env; sada ograničen granicama i projektnim limitom | PROVEN |
| Ručna dodela/opoziv | Nema rute u aplikaciji: `subscription_type`, `rollout_flags`, `user_credits` se menjaju direktno u bazi, bez audit traga u aplikaciji | PROVEN (grep); prepreka za B3 |

## 6. Regresija

POPUNJAVA SE POSLE MERENJA.

## 7. Preostali materijalni rizici

1. **Konfiguracija provajdera je UNKNOWN** (§3). Do potvrde nema trajne projektne granice. Brojač u procesu je drugi, netrajan sloj.
2. **Registracija bez potvrde email-a** omogućava neograničen broj naloga sa po 15 kredita. Projektni limit je jedina granica na nivou zbira.
3. **Migracija 146 mora biti pokrenuta PRE puštanja.** Bez nje brana odbija (fail-closed) Smart Intake obradu, obradu događaja i rute sa ručnom autentifikacijom.
4. **Promena ponašanja:** nalog sa 0 kredita više ne pokreće AI ni na plaćenoj funkciji koju ruta ne naplaćuje. Ranije je AI radio i trošak se nije naplaćivao. To je namera brane, ali je vidljivo korisniku.
5. **Odbijanje unutar rute koja vraća degradiran 200** (hvata izuzetak i vraća rezervni sadržaj) izgleda kao slabiji rezultat, ne kao poruka o kreditima. Trošak je i tada 0.
6. **Razlika multiplikatora posle AI poziva:** rezervacija oduzima osnovnu cenu, a razliku namiruje ruta posle poziva. Nalog koji pokriva osnovnu cenu, ali ne i punu, dobija 402 posle izvršenog poziva. Izloženost je ograničena granicama operacije (60 pokušaja, $3).
7. **Pad rute posle uspešnog AI poziva** vraća rezervaciju (isto kao ranije). Namerno izazvan pad daje besplatan rad, ograničen dnevnim brojačem, granicama operacije i projektnim limitom.
8. **Cohere** ide mimo brane ako se ikad uključi.
9. **Procene cene su konzervativne aproksimacije** (≈3 znaka po tokenu, cenovnik iz `shared/cost.py`), ne ugovorne cene.

## 8. Akcije osnivača

1. Pregledati Draft PR; spajanje = puštanje u produkciju.
2. **PRE puštanja:** pokrenuti `migrations/146_ai_osnovna_obrada.sql` u Supabase SQL Editor-u i proveriti ga upitom na dnu fajla.
3. Potvrditi u Render-u da `AZURE_OPENAI_KEY`/`AZURE_OPENAI_ENDPOINT` **nisu** postavljeni, ili odlučiti drugačije.
4. **OpenAI (samo uz izričito odobrenje):**
   - napraviti projekat „Vindex Early Access“;
   - postaviti Spend limit $50/mesec sa uključenim **Enforce a hard limit**;
   - postaviti upozorenja na $25 i $40;
   - u Model permissions dozvoliti `gpt-4o`, `gpt-4o-mini`, `gpt-4o-2024-08-06`, `text-embedding-3-small`, `text-embedding-3-large`, `whisper-1`, `tts-1` i, ako se glas koristi, `gpt-4o-realtime-preview`;
   - napraviti ključ projekta i postaviti ga kao `OPENAI_API_KEY` u Render-u.
5. Opciono podesiti env vrednosti (podrazumevane su predlog):
   - `VINDEX_AI_PROJEKAT_MESECNI_USD` (50);
   - `VINDEX_AI_MAX_USD_OPERACIJE` (3);
   - `VINDEX_AI_MAX_POKUSAJA_OPERACIJE` (60);
   - `VINDEX_AI_MAX_IZLAZ_TOKENA` (8000);
   - `VINDEX_AI_MAX_ULAZ_TOKENA` (100000);
   - `VINDEX_AI_REALTIME_MAX_SEKUNDI` (600).
6. Hitno vraćanje: `VINDEX_AI_BUDZET=off`. Ono vraća i staru rupu, pa je to odluka, ne podrazumevano stanje.
7. Odluka o registraciji (potvrda email-a) pre masovnog pridobijanja korisnika (faza B).
