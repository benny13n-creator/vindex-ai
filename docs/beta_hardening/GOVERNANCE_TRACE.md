# GOVERNANCE / AUDIT / PROVENANCE TRACE

**Program:** BETA-HARDENING-001, Agent 2
**Baseline commit:** `6fb4a99f`
**Datum:** 2026-08-13
**Obim:** AI izvršna putanja — `pozivalac → governance → odluka → provajder → response firewall → audit → provenance`
**Metod:** statička analiza (AST merenja, priloženi skriptovi opisani u §9) + **runtime eksperimenti** (§2, §3, §4)
**Izmene produkcionog koda:** nula. Ovaj dokument je jedini artefakt.

---

## 0. Sažetak — šta lanac stvarno garantuje

| Karika | Stanje | Dokaz |
|---|---|---|
| Ulazni guard (`prompt_guard.analyze`) | **RADI** — poziv provajderu se ne izvrši | §2, scenario (c): `provajder pozvan puta = 0` |
| Odluka guard-a → trajan trag | **NE POSTOJI NA KAPIJI** | §2 (c): 0 provenance, 0 audit zapisa; §5.2 |
| Provajder → response firewall | **RADI** na SDK putanji | §2 (b): pozivalac dobio `ResponseBlocked` |
| Firewall odluka → audit | **RADI za BLOCK/ESCALATE**, ali kroz `create_task`/`spawn` best-effort | §5.1 |
| AI poziv → provenance red | **RADI**, ali sadržaj reda zavisi od migracije 089 | §6, **GT-001** |
| Jedan `correlation_id` kroz sve slojeve | **RADI na HTTP putanji**, **PUCA van nje** | §2 (a) vs (d), **GT-004** |

**Jedna rečenica:** kapija stoji i stvarno blokira; ono što ne stoji je **dokaz** — trag koji spaja odluku, poziv i posledicu je uslovljen jednom nepotvrđenom migracijom i tiho degradira bez ijednog signala.

---

## 1. Koliko sistema upravljanja imamo — JEDAN

Mandat je tražio odgovor na pitanje da li `shared/ai_fabric.py::AIGateway` predstavlja drugi, paralelni sistem upravljanja uz SDK zakrpu.

**Odgovor: NE. Postoji tačno jedan živ sistem — SDK zakrpa.**

Mereno:

```
grep -rn "from shared.ai_fabric|from shared import ai_fabric|import ai_fabric" --include=*.py .
→ 3 pogotka, SVA TRI u tests/
```

`shared/ai_fabric.py` (672 linije, `AIGateway`, 3 adaptera, registry, `_govern_request`, telemetrija, shadow mode) ima **nula produkcionih pozivalaca**. `tests/test_ai_fabric_governance.py:104-113` to drži kao ugovor — test pada ako se pojavi pozivalac.

Pridruženo, i bitno jer se navodi kao dokaz u `docs/website/VINDEX_AI_PUBLIC_CLAIMS.md`:

- `shared/ai_fabric.py:534-537` uvozi `security.prompt_guard.sanitize_prompt`.
- U `security/prompt_guard.py` postoje: `analyze`, `wrap_for_ai`, `truncate_safe`, `_normalize`, `_analyze_base64_payloads`, `_extra_heuristics`, `_short_hash`. **`sanitize_prompt` ne postoji.**
- Dakle taj `try` uvek digne `ImportError`, a `except ImportError: pass` ga proguta. Sadržajna sanitizacija u `_govern_request` je **no-op**. (Već zabeleženo u `docs/beta_war/BETA_HARDENING_WAVE_8.md:64-70`; ovde potvrđeno nezavisno.)

**Kanonska kapija je `shared/ai_client.py::_patch_prompt_guard()`**, pozvana iz `api.py:28`, pre svih router importa. Runtime potvrda u svežem procesu (§2):

```
governance_status: {'attempted': True, 'active': True, 'ai_blocked': False, ...}
Completions.create._vindex_guarded = True
```

### 1.1 Ali postoje TRI putanje koje kapiju zaobilaze

Ovo nisu paralelni sistemi upravljanja — to su **rupe sa kompenzacijom samo na strani provenance-a**:

| Putanja | Prompt guard | Response firewall | Provenance |
|---|---|---|---|
| `services/voice_orchestrator.py` — sirov WSS ka OpenAI Realtime | NE | NE | DA, ručno (`:143-189`) — **samo red „sesija je postojala", bez ijednog reda o sadržaju razgovora** |
| `app/services/retrieve.py::_cohere_rerank` — Cohere SDK | NE | NE | DA, ručno (`:564-628`); grana je podrazumevano isključena (`_cohere_dozvoljen`, tri uslova) |
| `shared/ai_fabric.py` | no-op (v. gore) | NE | ne dolazi do izvršenja — 0 pozivalaca |

Prve dve su izričito imenovane u ugovoru `security/response_firewall.py:27-35`. To je pošteno prijavljeno, ne skriveno.

---

## 2. RUNTIME DOKAZ — ceo lanac kroz zakrpljeni `Completions.create`

Eksperiment presreće **sink** provenance-a (`security.ai_forensics.log_provenance_from_wrapper`) i **audit odluke** firewall-a (`security.response_firewall._audit_odluku`), i zamenjuje `shared.ai_client._orig_create` lažnim odgovorom. Nijedan mrežni poziv se ne dešava. Baza se ne dira.

### (a) Srećan put — HTTP zahtev, sa `case_context`

```
request correlation_id : 67e871ca-e606-4b59-8489-598db52d5588
provenance.correlation : 67e871ca-...  ISTI: True
fw_audit.correlation   : 67e871ca-...  ISTI: True
provenance.user_id     : korisnik-1 | fw_audit.user_id: korisnik-1
provenance.predmet_id  : P-42 | document_id: D-7
provenance.status      : success | fw odluka: ALLOW
provenance.retrieval_query        : None
provenance.retrieved_context_ids  : []
```

**Lanac je potpun i povezan istim ID-em.** Ovo je stvarno dobra vest i treba je tako i zvati.

### (b) Firewall vraća BLOCK

```
pozivalac je dobio : ResponseBlocked
fw odluka          : BLOCK ['sadržaj je prazan string']
provenance zapisa  : 1
provenance.status  : success   ← odgovor NIJE stigao korisniku
```

**Nalaz GT-006.** `_capture_chat_provenance` se zove **pre** `_enforce_response` (`shared/ai_client.py:741-742`). Provenance red tvrdi `status="success"` za poziv koji je pozivalac dobio kao izuzetak. Redovi jesu spojivi preko `correlation_id`-a, ali svaki direktan upit tipa „koliko je AI poziva uspelo" daje netačan broj naviše.

### (c) Ulazni guard odbija

```
analyze().blocked = True  score = 1.0
ishod poziva          : PromptInjectionBlocked
provajder pozvan puta : 0        ← poziv se NIJE desio
provenance zapisa     : 0
fw audit zapisa       : 0
```

**Bezbednosna tvrdnja je POTVRĐENA** (nijedan token nije otišao provajderu).
**Tvrdnja o dokazivosti je OBORENA** — v. **GT-002**.

### (d) Pozadinski posao — bez HTTP zahteva

```
fw odluka  : ESCALATE ['correlation_id nedostaje', 'user_id nedostaje']
prov corr  : 5d4336d0-7b5c-470e-8555-b9b70b07e1da
fw corr    : None
ISTI?      : False
```

**Nalaz GT-004 — korelacioni ID se razilazi UNUTAR JEDNOG ISTOG POZIVA.**

Uzrok je asimetrija koja se vidi na dve linije istog fajla:

- `shared/ai_client.py:452` — `correlation_id=ctx.get("correlation_id") or _prov.new_correlation_id()` → **kuje nov ID**
- `shared/ai_client.py:692` (`_enforce_response`) — `cid = _ctx.get("correlation_id")` → **ostaje `None`**

Posledica na svakoj AI putanji bez HTTP zahteva: firewall audit red nosi `correlation_id = NULL`, provenance red nosi svež UUID koji nigde drugde ne postoji. Dva reda o istom pozivu ne mogu se spojiti ni jedan sa drugim ni sa bilo čim uzvodno.

---

## 3. RUNTIME DOKAZ — da li `correlation_id` preživi `asyncio.to_thread`?

**DA. Preživi.** Mereno, ne pretpostavljeno:

```
ROOT correlation_id = 76fac191-9eb7-49db-afa6-33305601851b
  A_to_thread             = ISTI
  B_case_root             = ISTI      (unutar case_context)
  B_case_to_thread        = ISTI      (case_context + to_thread)
  C_bg_spawn              = ISTI      (shared/bg.py::spawn → create_task)
  D_asyncio_run_u_niti    = ISTI      (asyncio.run() unutar to_thread worker niti)
  D_grana                 = 'nema loop-a → asyncio.run'
  E_raw_threadpool        = None      ← ThreadPoolExecutor.submit BEZ copy_context
  F_run_in_executor       = None      ← loop.run_in_executor BEZ copy_context
```

Objašnjenje: `asyncio.to_thread` interno radi `contextvars.copy_context()` i izvršava funkciju u toj kopiji. `asyncio.create_task` isto kopira kontekst. Golo `ThreadPoolExecutor.submit` i `loop.run_in_executor` **ne kopiraju ništa**.

**Operativna posledica:**
- `loop.run_in_executor` — **0 pojava** u produkcionom kodu. Nema rizika odatle.
- `asyncio.to_thread` — 1.532 pojave, sve bezbedne.
- Golo `ThreadPoolExecutor.submit` — **ovde je rupa**, v. **GT-005**.

Grana `D` je vredna posebne pažnje: kada sinhroni SDK poziv radi u `to_thread` worker niti, `_capture_chat_provenance` ne nalazi event loop i pada na `asyncio.run(coro)` (`shared/ai_client.py:477`). Kontekst preživi — ali upis provenance-a tu postaje **blokirajući mrežni poziv u deljenoj executor niti**, umesto fire-and-forget. To nije korektnost, nego propusnost; navedeno kao dug, ne kao blokada bete.

---

## 4. RUNTIME DOKAZ — koliko ruta postavlja korelacioni kontekst

### 4.1 Osnovni `correlation_id`: 611 / 611 HTTP ruta = **100 %**

Nije po ruti — postavlja ga **globalni HTTP middleware**:

```python
# api.py:1027-1051
@app.middleware("http")
async def correlation_id_middleware(request, call_next):
    cid = set_request_context(correlation_id=request.headers.get("X-Correlation-ID"))
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = cid
    return response
```

Repo ima **tačno jednu** `FastAPI()` instancu (`api.py:564`) i 119 `include_router` poziva na njoj — nema drugog app-a koji bi zaobišao middleware.

Da middleware stvarno propušta contextvar kroz Starlette `BaseHTTPMiddleware` (što nije samo po sebi razumljivo — `call_next` startuje downstream u zasebnom anyio tasku) provereno je runtime-om, na verzijama koje repo stvarno koristi:

```
fastapi 0.135.3 | starlette 1.3.1
/async    handler_cid='TEST-CID-123'  header='TEST-CID-123'  POKLAPA=True
/sync     handler_cid='TEST-CID-123'  header='TEST-CID-123'  POKLAPA=True   (sync ruta → threadpool)
/thread   handler_cid='TEST-CID-123'  header='TEST-CID-123'  POKLAPA=True   (to_thread u ruti)
/ws       handler_cid=None
```

### 4.2 WebSocket: 0 / 1 ruta — **GT-010**

`@app.middleware("http")` se po definiciji ne izvršava za `scope["type"] == "websocket"`. Runtime to potvrđuje gore. Jedina WS ruta je `routers/voice_realtime.py:140::voice_realtime_ws`, tj. glasovni asistent — putanja koja i inače zaobilazi i prompt guard i firewall (§1.1). Njena provenance funkcija (`voice_orchestrator.py:161`) zato uvek pada na `_prov.new_correlation_id()` i kuje **siroče ID** po sesiji.

### 4.3 Kontekst predmeta (`predmet_id`/`document_id`/`module`/`operation`): 31 / 611 = **5,1 %**

To je jedini sloj koji zahteva ručno ožičenje, i on je tanak.

AST merenje po ruti (dekorator → telo funkcije sadrži `case_context`):

| Fajl | Ruta sa `case_context()` |
|---|---|
| `routers/strategija.py` | 9 |
| `routers/court_predictor.py` | 7 |
| `routers/drafting.py` | 3 |
| `routers/digital_twin.py` | 2 |
| `routers/hearing_cc.py` | 2 |
| `api.py`, `case_dna.py`, `case_intelligence.py`, `cross_doc.py`, `dokument.py`, `evidence_graph.py`, `matter_intel.py`, `zadaci.py` | po 1 |
| **UKUPNO** | **31** |

Postojeći repo skript `scripts/audit_binding_metric.py` meri isto sa druge strane i slaže se:

```
Provider call sites (AST):        84
case_context(...) declarations:   39
  WITH subject (predmet/document): 36  across 12 modules
  WITHOUT subject:                  3
```

Za orijentaciju: 83–89 `chat.completions.create` pozivnih mesta u 66 fajlova, 82 funkcije koje ih direktno sadrže.

---

## 5. Audit — gde se stvarno piše i gde ne

### 5.1 Kanonski zapisi

Postoje **dva** trajna traga, i to je namerno:

1. **`shared/audit_immutable.py::log_action` / `log_action_sync`** — append-only hash-lanac (`audit_immutable`), migracija 081 sa `UNIQUE(prev_hash)`. Akcija mora biti u `AUDITABLE_ACTIONS`, inače `log_action` **tiho vrati `None`**.
2. **`security/ai_forensics.py::log_provenance_from_wrapper`** — tabela `ai_forensics` (§6).

Kroz ledger prolaze ove AI-relevantne akcije (mereno brojanje produkcionih pozivalaca, izuzimajući samu allowlistu):

| Akcija | Pozivalaca | Napomena |
|---|---|---|
| `court_predictor_analiza` | 7 | |
| `ai_analiza_complete` | 4 | |
| `dokument_pitanje` | 3 | |
| `strategija_generisana` | 2 | |
| `copilot_analiza_predmeta`, `zadaci_ai_analiza_complete`, `briefing_generisan`, `drafting_generisan`, `drafting_nacrt`, `drafting_analiza`, `evidence_klasifikacija`, `dokument_ai_analiza_complete`, `copilot_pravno_pitanje`, `reasoning_graph_generated` | po 1 | |
| `ai_response_firewall_decision` | 1 (`response_firewall.py:286`) | samo BLOCK/ESCALATE, nikad ALLOW |
| `ai_fabric_call` | 1 (`ai_fabric.py:653`) | **mrtav put** — 0 pozivalaca modula |
| `injection_attempt_blocked` | 3 (`api.py:912`, `:3239`, `:3423`) | v. GT-002 |
| **`ai_kompletna_analiza_complete`** | **0** | registrovana akcija bez ijednog producenta |

### 5.2 GT-002 (VISOK) — odluka ulaznog guard-a nema trag NA KAPIJI

Runtime (§2c) pokazuje: kada `_guarded_create` digne `PromptInjectionBlocked`, kapija upiše **`logger.warning` i ništa više**. Nijedan audit red, nijedan provenance red.

Trag postoji samo ako izuzetak **iscuri sve do** `api.py:891::global_exception_handler`, koji ga onda upiše kao `injection_attempt_blocked` sa `user_id="unknown"` (SDK-nivo zakrpa ne poznaje autentifikovani identitet).

Koliko često izuzetak ne iscuri — AST merenje:

```
Funkcija koje direktno sadrže chat.completions.create : 82
Poziva tih funkcija ukupno                             : 205
  unutar try/except Exception (odluka se guta)         : 78  (38 %)
```

Najgušće: `main.py` (9), `app/services/retrieve.py` (8), `routers/copilot.py` (7), `routers/praksa.py` (4), `routers/style_checker.py` (3), `services/case_pipeline.py` (3).

Konkretan, pročitan primer — `main.py:3957-3968` (`_map_analiziraj_batch`): `except Exception` → `logger.warning` → prazan doprinos batch-a. Pokušaj injekcije u dokumentu koji se analizira Map-Reduce putanjom **ne ostavlja nijedan trajan zapis nigde**.

Dve rute (`api.py:3232`, `api.py:3416`) ovo rešavaju ispravno — zovu `analyze()` eksplicitno **pre** naplate i pišu `injection_attempt_blocked` sa stvarnim `user_id`-em. To je tačan obrazac; problem je što važi za 2 od 611 ruta.

### 5.3 GT-003 (VISOK) — 70 audit upisa ide kroz golo `asyncio.create_task`

```
asyncio.create_task( u produkciji                    : 140
  od toga log_action / _imm_log / _audit             :  70
Pozivnih mesta koja koriste shared/bg.py::spawn      :  20
```

`shared/bg.py` postoji upravo zato što golo `create_task` ima dva defekta: (1) event loop drži samo slabu referencu, pa task može biti pokupljen GC-om usred izvršavanja, (2) niko ne čita `task.exception()`, pa je svaki pad tih. Shutdown handler (`api.py:884-889`) drenira **samo** taskove registrovane kroz `spawn`.

S3-1 je ovaj obrazac popravio **unutar `ai_client.py`** (provenance upis ide kroz `_spawn_bg`), ali **ne i u ruterima**. Rezultat: provenance red je zaštićen, a **audit red o istom pozivu nije**. Pogođeni su, između ostalog:

- `api.py:3238` i `api.py:3422` — **`injection_attempt_blocked`**, tj. baš bezbednosni zapis
- `routers/strategija.py:173` — `strategija_generisana`
- `routers/copilot.py:497, 260, 712, 825, 887, 995, 1274`
- `routers/court_predictor.py:437` i 6 drugih mesta

Na Render-u svaki redeploy šalje SIGTERM; ovih 70 taskova se prekida bez milosti.

### 5.4 GT-008 (SREDNJI) — audit samo na srećnom putu

Dva pročitana, reprezentativna obrasca:

**(a) `routers/copilot.py:470-500`** — GPT poziv je u `try`; `except` grana vraća `{"odgovor": "Greška pri generisanju analize."}` i **ne piše nikakav audit**. `log_action("copilot_analiza_predmeta")` stoji tek posle `try` bloka. „AI operacija je pokušana i pala" nema trajan zapis.

**(b) `routers/court_predictor.py:425-443`** — `log_action("court_predictor_analiza")` stoji **u istom `try` bloku** kao `supa.table("predictor_analize").insert(...)`, sa `except Exception: pass`. Ako padne DB upis analize, audit se preskače zajedno sa njim, iako je AI poziv stvarno izvršen i naplaćen (`UsageService.consume` je nekoliko linija niže).

### 5.5 Redosled upisa

Audit odluke firewall-a piše se **pre** dizanja `ResponseBlocked` (`response_firewall.py:349-359`) — to je ispravno i namerno: neuspeh upisa ne može da pretvori BLOCK u prolaz.

Provenance se piše **posle** povratka provajdera, i za uspeh i za grešku (`ai_client.py:736-742`, `:767-773`) — dakle nije „samo srećan put". Jedina greška u tome je pogrešan `status` kod BLOCK-a (GT-006).

---

## 6. Provenance — gde se stvarno upisuje

Jedina tačka upisa: **`security/ai_forensics.py::log_provenance_from_wrapper` → tabela `ai_forensics`**.

Produkcioni producenti (4, svi kroz isti sink):

| Producent | Operacije |
|---|---|
| `shared/ai_client.py::_capture_chat_provenance` | `Completions.create`, `AsyncCompletions.create` |
| `shared/ai_client.py::_capture_embedding_provenance` | `Embeddings.create`, `AsyncEmbeddings.create`, **i sve audio operacije** (`Transcriptions.create`, `Speech.create` + async parnjaci) |
| `app/services/retrieve.py::_uknjizi_cohere_provenance` | `cohere_rerank` |
| `services/voice_orchestrator.py::_uknjizi_voice_sesiju_provenance` | `voice_realtime_session` |

### 6.1 GT-001 (KRITIČNO) — ceo lanac visi o migraciji 089, i tiho puca

`log_provenance_from_wrapper` prvo pokušava „širok" INSERT sa svim kolonama. Ako Postgres odgovori greškom tipa „kolona ne postoji", pada na **uski, legacy skup** (`ai_forensics.py:298-302`):

```python
_legacy_keys = {
    "user_id", "endpoint", "model", "prompt_hash", "started_at",
    "latency_ms", "response_hash", "tokens_prompt", "tokens_completion",
    "prompt_version",
}
```

**U tom skupu NEMA `correlation_id`. Nema ni `predmet_id`, ni `document_id`, ni `status`, ni `error_message`, ni `module_name`, ni `operation_name`, ni `tenant_id`.**

Drugim rečima: ako migracija `089_ai_provenance_extension.sql` nije primenjena na produkciji, **join ključ koji ceo ovaj dokument prati fizički ne postoji ni u jednom provenance redu**, a aplikacija se ponaša kao da postoji.

Status migracije 089 = **UNKNOWN**. Bez pristupa produkcionoj bazi (`SUPABASE_DB_URL` je i dalje neisporučen, v. `project_night_shift_2026_08_02`) ovo se ne može utvrditi iz repoa. Repo sam sebe upozorava na isto mesto:

- `docs/architecture/ATLAS_AI_PROVENANCE_REPORT.md:164` — „Migration 089 (drafted, not applied…)"
- `docs/website/VINDEX_WEBSITE_CLAIMS_REGISTRY.md:171` — javna tvrdnja „za svaki AI poziv beleži se i u okviru kog predmeta je pokrenut" je `PARTIALLY_VERIFIED`, sa ogradom da zavisi od 089

**Zašto je ovo najozbiljniji nalaz:** degradacija je potpuno nema. Uski fallback ne loguje ništa (`ai_forensics.py:318-321`); tek totalan neuspeh oba pokušaja daje `logger.debug` (`:322-323`) — nivo koji se na produkciji ne emituje. Ne postoji nijedan health-check, readiness sonda ni test koji bi razlikovao „provenance radi" od „provenance upisuje redove bez korelacije". `api.py:1698` izlaže `governance_status()` (stanje **zakrpe**), ali ništa ne izlaže stanje **šeme**. `routers/admin_dashboard.py:275` broji `ai_forensics_24h` — broj redova, ne njihovu upotrebljivost.

### 6.2 GT-011 — `retrieval_query` ide kao sirov tekst, ali producenta nema

Provera ranije poznatog nalaza. Da, `ai_forensics.py:288` upisuje `"retrieval_query": retrieval_query` **bez heširanja** — za razliku od `system_prompt_hash`/`user_prompt_hash`/`output_hash`, koji svi prolaze kroz `sha256_text`. Dizajn kolone dozvoljava sirov korisnički tekst u forenzičkoj tabeli.

**Ali u praksi je polje mrtvo.** Merenje producenata `case_context(...)` argumenata:

| Polje | Produkcionih producenata | Potrošača |
|---|---|---|
| `retrieval_query` | **0** | 2 (oba u `ai_client.py`) |
| `retrieved_context_ids` | **0** | 1 |
| `parent_event_id` | **0** | 3 |
| `knowledge_sources` | 6 | 2 |

Runtime potvrda (§2a): `provenance.retrieval_query : None`, `retrieved_context_ids : []`.

Zaključak: **rizik curenja sirovog upita je latentan, ne aktivan.** Prvi pozivalac koji doda `case_context(retrieval_query=...)` ga aktivira. Istovremeno, RAG provenance — koji dokument je stvarno ušao u odgovor — **ne postoji**, što je već zavedeno kao `PROGBETA-002` u `.vindex_ai_team/MISSION_BOARD.md:462`.

---

## 7. GT-005 (VISOK) — dva `ThreadPoolExecutor` pool-a bez `copy_context`

Iz §3: golo `ThreadPoolExecutor.submit` **ne prenosi contextvars**. Repo to zna — `app/services/retrieve.py:1861-1871` nosi eksplicitan komentar (S2-4) i popravku na 4 mesta:

```
app/services/retrieve.py:1870, 1871, 1904, 1911   ← contextvars.copy_context().run
```

To su **jedina 4 mesta u celom repou**. Dva pool-a koja izvršavaju AI pozive su ostala nepokrivena:

### (a) `app/services/retrieve.py:1685-1729` — `_jedan_retrieval_krug`, 12 niti

```python
executor = ThreadPoolExecutor(max_workers=12)
...
fjobs.append(executor.submit(_semanticka_pretraga, term, 3, "zakon o digitalnoj imovini"))
```

`_semanticka_pretraga` (`:891-904`) zove `_ugradi_query` (`:716-722`) → `embed_query` → **`Embeddings.create`** → `_capture_embedding_provenance`. Do 14 submit-ova po jednom RAG upitu, u zavisnosti od okidača ekspanzije. Svi provenance redovi iz njih nose `user_id=None`, `predmet_id=None`, i **svež siroče `correlation_id`** (jer `ai_client.py:511` kuje nov ID kad ga u kontekstu nema).

Ovo je najprometnija AI putanja u proizvodu.

### (b) `main.py:4080-4090` — `_ask_analiza_v2_map_reduce`, 4 niti

```python
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {executor.submit(_map_analiziraj_batch, batch, ...): i ...}
```

`_map_analiziraj_batch` (`:3934-3983`) zove `_pozovi_openai` → **`chat.completions.create`**. Svaki MAP batch analize dugačkog dokumenta (>12.000 znakova) je AI poziv bez identiteta.

Dodatna posledica na obe putanje: `_enforce_response` vidi `correlation_id=None` i `user_id=None`, pa **svaki takav odgovor dobija verdikt ESCALATE**. Degradacija koja je uvek uključena nije signal — to je isti kvar koji je Wave 9 (C3) već jednom popravio na drugom mestu (`ai_client.py:676-685`), sada reprodukovan preko granice niti.

---

## 8. Ostali nalazi

### GT-007 (SREDNJI) — `ESCALATE` je izračunat, ali nema potrošača

Grep za `ESCALATE`/`degradacije` van `security/response_firewall.py` i van testova daje **nula potrošača**. Verdikt se izračuna, uloguje (`logger.info`), upiše u ledger — i odgovor ide dalje **nepromenjen**. Nema oznake u API odgovoru, nema signala u UI-ju, nema metrike koja bi ga podigla. Advokat koji dobije odgovor iz degradiranog poziva ne može to nikako da zna.

Ovo je tačan primer „governance odluke koja se izračuna ali ne utiče na izvršenje". Nije nužno pogrešno — ali tvrdnja „odgovor prolazi kroz izlaznu proveru" korisniku implicira posledicu koje na ESCALATE putanji nema.

### GT-012 (SREDNJI) — `ResponseBlocked` i `GovernanceUnavailable` nemaju nijednog produkcionog rukovaoca

```
grep -rn "ResponseBlocked|GovernanceUnavailable" --include=*.py . | grep -v tests | grep -v response_firewall.py | grep -v ai_client.py
→ samo scripts/rc_cold_start.py:136-137
```

`api.py:891::global_exception_handler` ima posebnu granu **samo** za `PromptInjectionBlocked`. `ResponseBlocked` i `GovernanceUnavailable` padaju u generičku granu → korisnik dobija poruku koja izgleda kao pad servera, a ne kao namerna bezbednosna odluka. Za `GovernanceUnavailable` je to posebno pogrešno: to je stanje „cela AI granica je zatvorena", tj. incident, a ne greška zahteva.

### GT-009 (INFO) — naplata i predmet

`shared/usage.py:313-336` pošteno dokumentuje: `case_context` vraća `_case_ctx` na staru vrednost pri izlasku iz `with` bloka, a **svi** pozivi `UsageService.consume` stoje **izvan** tog bloka. Wave 11 (G2) je to zatvorio eksplicitnim argumentom na 9 mesta u `strategija.py`. Trenutno stanje:

```
UsageService.consume( pozivnih mesta : 143
  sa eksplicitnim predmet_id=        :  13   (9 %)
```

Preostalih 130 poziva naplate vezuje se za predmet **samo tranzitivno**, preko `correlation_id`-a kroz `ai_forensics` — što je isti join koji GT-001 dovodi u pitanje.

### GT-013 (INFO) — višestruki provenance redovi po logičkom pozivu

`shared/llm_retry.py` je tenacity dekorator na pozivnim mestima, dakle **iznad** zakrpljene SDK metode. Svaki pokušaj ponavljanja proizvodi sopstveni provenance red i sopstveni firewall audit, sve sa istim `correlation_id`-em. To nije duplikacija u smislu greške, ali svaka analitika koja broji redove kao „broj AI poziva" preračunava. Nije nađen nijedan slučaj dvostrukog dispatch-a istog audit zapisa.

---

## 9. Ponovljivost

Svi runtime rezultati u ovom dokumentu proizvedeni su iz tri samostalna skripta (držani u scratchpad-u sesije, **ne** dodati u repo, u skladu sa mandatom „tačno jedan nov fajl"):

| Skript | Šta meri | §|
|---|---|---|
| `exp_ctxvar.py` | propagacija contextvar-a kroz `to_thread` / `case_context` / `bg.spawn` / `asyncio.run` u niti / golu nit / executor | §3 |
| `exp_middleware.py` | propagacija iz `@app.middleware("http")` u async / sync / to_thread / websocket rutu, na stvarnim verzijama FastAPI 0.135.3 + Starlette 1.3.1 | §4 |
| `exp_lanac.py` | ceo lanac kroz zakrpljeni `Completions.create`, sa presretnutim sink-ovima; scenariji (a)(b)(c)(d) | §2 |

AST merenja: brojanje ruta, brojanje `case_context` po ruti, brojanje AI pozivnih mesta unutar `try/except Exception`. Postojeći repo skript `scripts/audit_binding_metric.py` korišćen kao nezavisna kontrola i slaže se.

Regresiona osnova pre početka rada — zelena:

```
pytest tests/test_gov3_response_firewall.py tests/test_wave9_governance.py \
       tests/test_wave11_guard_and_provenance.py tests/test_gov2_runtime_interception.py \
       tests/test_ai_fabric_governance.py
→ 99 passed
```

Nijedan produkcioni fajl nije menjan. Nijedna baza nije dirana (`PYTEST_CURRENT_TEST` je bio postavljen, pa `_ledger_dozvoljen()` blokira upis u živi ledger; sink-ovi su ionako bili presretnuti).

---

## 10. Registar nalaza

| ID | Ozbiljnost | Nalaz | Dokaz |
|---|---|---|---|
| **GT-001** | **KRITIČNO** | Ceo korelacioni lanac zavisi od migracije 089; bez nje provenance redovi tiho gube `correlation_id`, `predmet_id`, `status`. Nula signala o degradaciji. | `ai_forensics.py:298-321`; status 089 = UNKNOWN |
| **GT-002** | VISOK | Odluka ulaznog guard-a nema trajan trag na kapiji; zavisi od izuzetka koji 38 % pozivalaca guta | §2c; AST 78/205 |
| **GT-003** | VISOK | 70 audit upisa (uklj. `injection_attempt_blocked`) ide kroz golo `asyncio.create_task` — GC-abilno, ne drenira se pri gašenju | grep; `shared/bg.py` docstring |
| **GT-004** | VISOK | `correlation_id` se razilazi unutar istog poziva na ne-HTTP putanjama: firewall `None`, provenance svež UUID | §2d; `ai_client.py:452` vs `:692` |
| **GT-005** | VISOK | 2 `ThreadPoolExecutor` pool-a koji izvršavaju AI pozive bez `copy_context` → provenance bez identiteta + trajni ESCALATE | `retrieve.py:1685`, `main.py:4080`; §3 |
| **GT-006** | SREDNJI | Provenance tvrdi `status="success"` za poziv koji je firewall blokirao | §2b |
| **GT-007** | SREDNJI | `ESCALATE` nema nijednog potrošača — odluka bez posledice | grep |
| **GT-008** | SREDNJI | Audit se piše samo na srećnom putu (`copilot.py:470-500`) ili deli `try` sa DB upisom (`court_predictor.py:425-443`) | čitanje izvora |
| **GT-010** | SREDNJI | WebSocket ruta (glasovni asistent) nema korelacioni kontekst — HTTP middleware se ne izvršava | §4.2 |
| **GT-012** | SREDNJI | `ResponseBlocked` / `GovernanceUnavailable` nemaju produkcionog rukovaoca → izgledaju kao pad servera | grep |
| **GT-009** | INFO | 13/143 poziva naplate vezuje predmet eksplicitno; ostalo tranzitivno preko GT-001 | grep |
| **GT-011** | INFO | `retrieval_query` bi ušao kao sirov tekst, ali ima 0 producenata; RAG provenance ne postoji | §6.2 |
| **GT-013** | INFO | `llm_retry` proizvodi N provenance redova po logičkom pozivu | `shared/llm_retry.py` |
| **GT-014** | INFO | Mrtvi elementi: `ai_kompletna_analiza_complete` (0 producenata), `ai_fabric_call` (0 pozivalaca modula), `sanitize_prompt` (ne postoji) | grep |

---

## 11. Šta stvarno ugrožava beta lansiranje

**GT-001.**

Sve ostalo su rupe u pokrivenosti koje se mere i popravljaju inkrementalno. GT-001 je drugačiji jer **poništava dokaznu vrednost svega ostalog, i to nevidljivo**. Ako 089 nije primenjena:

- svaki provenance red ima 10 kolona umesto 27, bez `correlation_id`
- „ko je pitao, o kom predmetu, i šta je model odgovorio" ne može se rekonstruisati
- javna tvrdnja iz `VINDEX_WEBSITE_CLAIMS_REGISTRY.md:171` je neistinita
- veza naplata → predmet (GT-009, 130 od 143 poziva) nestaje zajedno sa join ključem
- **ništa u aplikaciji to ne prijavljuje** — ni log na produkcionom nivou, ni health endpoint, ni test

Preporučen redosled (izvršenje nije deo ovog mandata):

1. Utvrditi stanje 089 na produkciji (traži `SUPABASE_DB_URL`, koji je u dugu od Black Swan-a).
2. Ako nije primenjena — primeniti je, ili do tada javno povući tvrdnju o vezivanju za predmet.
3. Nezavisno od (1): podići uski fallback sa tihog na `logger.error` i izložiti stanje šeme kroz isti endpoint koji već izlaže `governance_status()`. Tvrdnja o forenzičkoj sledljivosti koja se ne može proveriti spolja nije tvrdnja nego nada.
