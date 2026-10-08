# Vindex — mapa zavisnosti sposobnosti

**Misija:** CAPABILITY RECOVERY FORENSICS 001 · **Osnova:** `origin/main` `51164c92` · **Datum:** 2026-10-08
**Prateći fajlovi:** `VINDEX_CAPABILITY_CENSUS.csv` (131 sposobnost, sve rute pokrivene), `VINDEX_V2_RECOVERY_STRATEGY.md`

Ovaj dokument ne menja ništa u proizvodu. Opisuje šta od čega zavisi, da bi se V2 vraćao redom koji ne lomi ništa.

---

## 0. Kako je dokaz prikupljen (hijerarhija dokaza)

| Nivo | Izvor | Težina |
|---|---|---|
| PROVEN | `import api` sa lažnim env-om i blokiranom mrežom → stvarna lista `app.routes` (640 ruta, 115 modula); neautentifikovane TestClient probe nad svakom rutom (Supabase lažiran da baci izuzetak, bez mreže); `git log` nad celom istorijom | najjača |
| INFERRED | statičko traženje putanja u frontend kodu (`frontend-v2-ng/src`, `v2/`, `index.html` + `static/vindex.js`); poklapanje regex-a za tabele/upise/spoljne servise u telu handlera | srednja |
| ASSUMED | izveštaji u repou, memorija projekta, stari sajt | samo trag |
| UNKNOWN | produkciona šema baze, Render cron poslovi, Render build mod (Docker/native), stvarni korisnički saobraćaj | nije proveravano: misija ne sme u produkciju |

**Ispravka u toku rada.** Statičko traženje je prvo pokazalo 12 ruta sa V2 NG pozivaocem. Ručna provera `frontend-v2-ng/src/api.js` pokazuje da V2 NG ima **samo GET**, i to **tačno 3 rute**:
- `GET /api/predmeti`
- `GET /api/predmeti/{id}`
- `GET /api/predmeti/{id}/dokumenti/{dok_id}/preview`

Ostalih 9 su bili lažni pogoci: isti tekst putanje, drugi HTTP metod. Obrnuto, statičko traženje promašuje putanje sa promenljivim segmentom akcije (`/api/rokovi/${id}/${putanja}`). Posebna provera je našla 2 takve rute i preraspodelila ih: `POST /api/rokovi/{id}/potvrdi` → `/app-v2`; `POST /klijenti/{id}/komunikacija` → legacy (INFERRED). Svi brojevi ispod su ispravljeni.

---

## 1. Popis ruta (A–E)

629 API ruta (bez `/docs`, `/openapi.json` i mount tačaka):

| Klasa | Značenje | Broj | Napomena |
|---|---|---|---|
| A | ima V2 pozivaoca | **129** | **3** → V2 NG (`/app`, primarni za sve); **126** → `/app-v2` (vidi ga samo nosilac `v2_pristup`, tj. founder 1/17) |
| B | samo legacy pozivalac | **230** | `index.html` + `static/vindex.js`; posle cutovera dostupno samo na nelinkovanom `/app-legacy` |
| C | bez ikakvog pozivaoca u frontendu | **270** | uključuje i ispravne neaplikacijske rute: cron, webhook, admin, javne stranice, `/v1` API |
| D | kod postoji, ruta nije registrovana | **0** | svaki `routers/*.py` je uključen kroz `include_router` (114 poziva) |
| E | uklonjeno iz koda | 8 fajlova u celoj istoriji | vidi §6 |

**Šta stvarno vidi običan korisnik danas:** posle NS004 cutovera `/app` je V2 NG i nudi 3 GET rute. Sve ostalo (oko 356 ruta iz klasa A i B) postoji, radi u kodu i auth je fail-closed, ali je do njega moguće doći samo:
- ručnim kucanjem `/app-legacy` (nelinkovan), ili
- ako je korisnik founder (`/app-v2`).

## 2. Granica bezbednosti (probe bez tokena)

| Grupa | Rezultat |
|---|---|
| GET rute | 236 → 401; 37 → 200, svi namerno javni: sajt, status, šifarnici (`/api/courts`, `/zastarelost/tipovi`, `/api/rokovi/*tipovi*`, `/api/agents/lista`, `/api/viber/status`, `/sms/status`) |
| Debug rute | `/test-pinecone`, `/test-zdi`, `/api/debug`, `/api/rag-test`, `/api/diagnose` → **404** (gejtovano); `/api/test-pitanje` traži `ADMIN_DEBUG_KEY` |
| Rute koje pišu | 293 → 401, 8 → 403 (cron tajne), 15 → 422 |
| Tih 15 sa 422, statički provereno | auth pre tela (`klijenti` preko `_auth_from_request`); `X-Api-Key` (`/api/bot/ask`); API ključ (`/v1/*`); javni deterministički kalkulatori (`/zastarelost/*`, `/rokovi/ics-export`); javni po dizajnu (`/api/register`, `/api/check-email`, `/waitlist/prijava`) |
| Webhooks | `/viber/webhook` → 200; `/v1/webhook/clio|imanage` → 503 (nisu konfigurisani) |

**Zaključak:** nijedna ruta koja čita ili piše podatke korisnika nije pronađena otvorena bez autentifikacije. Ovo **ne dokazuje** izolaciju između tenant-a (vlasnik A čita predmet B). Ta provera mora da se uradi po talasu, sa dva naloga (vidi strategiju, „TENANT-SAFE").

## 3. Graf zavisnosti po sposobnostima

```
                       ┌───────────────────────── AUTH / PLAN / ROLLOUT (CAP-167, CAP-106) ─────────────────────────┐
                       │                                                                                             │
   CAP-001 Registar ──► CAP-002 Detalj ──► CAP-003 Čitač teksta                                                       │
        │                    │                                                                                       │
        │                    ├─► CAP-006 Beleške/istorija ─► CAP-007 Hronologija ─► CAP-008 Workspace agregat        │
        │                    ├─► CAP-012 Download/brisanje dok.                                                      │
        │                    ├─► CAP-030/031 Klijenti ─► CAP-032 Sukob interesa ─► CAP-188 potvrda veza             │
        │                    └─► CAP-074 Ročišta ─► CAP-075 Kalendar                                                 │
        │                                                                                                            │
   CAP-004 Nov predmet ◄── CAP-020 Smart Intake ◄── CAP-011 OCR (BLOKER) ◄── tesseract u runtime-u (UNKNOWN)          │
                               │       ▲                                                                             │
                               │       └── shared/intake_worker.py + services/event_bus.py (startup petlje)          │
                               ├─► CAP-010 Upload + auto-analiza ─► CAP-070 Kandidati rokova ─► potvrdi/odbij (samo /app-v2)    │
                               │                                         └─► CAP-076 Email podsetnici (CRON PADA)   │
                               └─► CAP-120 Case Genome ─► CAP-121 Matter intel, CAP-123 Dokazi, CAP-126 Case actions │
                                                              └─► CAP-110 Strategija, CAP-111 Predictor, CAP-112 Twin │
   CAP-040 Pravno pitanje (Pinecone zakoni + citation guard) ─► CAP-060 Nacrt ─► CAP-061 Staging (ljudska kapija)      │
          └─► CAP-042 Praksa                                     └─► CAP-062 Šabloni, CAP-063 DOCX                    │
   CAP-130 Zatvaranje + ishod ─► CAP-113 Outcome Intelligence ("Office Intelligence") ─► CAP-114 Slični predmeti       │
   CAP-171 /api/cron/daily (Render cron UNKNOWN) ─► CAP-141 Pozadinski agenti ─► agent-notifications (NEMA UI)         │
                                                 └─► CAP-082 Portal sudova                                           │
   CAP-091 Tim kancelarije ─► CAP-092 Saradnja ─► CAP-093 Komentari, CAP-094 Zadaci                                  │
   CAP-100 Naplata ─► CAP-101 Izveštaji/recurring ─► CAP-102 SEF (nedokazano) ─► CAP-099 Profitabilnost               │
                       └─────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Kritični čvorovi.** Kada su pokvareni, ruše sve što zavisi od njih:

| Čvor | Šta pada ako ne radi | Stanje |
|---|---|---|
| CAP-011 OCR | Smart Intake za skenirane dokumente, upload skeniranog PDF-a, tvrdnja sajta „sistem sam pročita sliku" | kod REAL; jedini test pao kada je pokrenut sa tesseractom; produkcija **nikad** proverena |
| CAP-171 dnevni cron | pozadinski agenti, portal sudova, deo brifinga, sidrenje audit lanca | endpoint postoji i fail-closed je; da li ga Render poziva: **UNKNOWN** |
| `.github/workflows/email-cron.yml` | CAP-076 email podsetnici za rokove | **pada svakog dana** (`X-Cron-Key` se ne poklapa); BLK-3 |
| CAP-070 potvrdi rok | rok koji sistem nađe obični korisnik danas ne može da potvrdi | potvrdi/odbij postoje samo u founder-only `/app-v2` (`v2/features/rokovi/odluka.js`); legacy nema ekran za kandidate |
| CAP-120 Case Genome | svi AI moduli predmeta koji čitaju jedan opis | deployovano (A-serija); u V2 NG nije prikazano |
| Pinecone namespace | CAP-040, CAP-042, CAP-065 playbook | radi u legacy; izolacija playbook namespace-a po korisniku mora se dokazati pre V2 |

## 4. Radnici i automatizacija

| Mehanizam | Gde | Okidač | Stanje |
|---|---|---|---|
| `_warm_connections` | `api.py` startup | pokretanje procesa | PROVEN (kod) |
| Smart Intake worker (claim/process/complete/fail/reap) | `shared/intake_worker.py` | startup petlja | PROVEN (kod); memorija kaže da su Phase 0+1A proverene uživo |
| Event bus dispatch | `services/event_bus.py` | startup petlja | PROVEN (kod) |
| Gašenje pozadinskih poslova | `shared/bg.py` | shutdown | PROVEN (kod) |
| Dnevni orkestrator | `POST /api/cron/daily` (`X-Cron-Secret`, idempotentan 60 min) → `workers/background_agents.py` (budžet 40/org/dan, 600 s) | Render cron po docstring-u, 07:00 UTC | **UNKNOWN**: postojanje crona nije dokazano |
| Pozadinski agenti | `services/agent_tasks/court_portal_watcher.py`, `precedents_radar.py` | dnevni orkestrator | INFERRED |
| Email podsetnici | `.github/workflows/email-cron.yml` → `/email-notif/send-reminders` | GitHub schedule 08:00 | **PADA** |
| SMS podsetnici | `.github/workflows/sms-cron.yml` | GitHub schedule 07:00 | zeleno (isporuka korisniku nije proverena) |
| Jutarnji brifing / noćna inteligencija | `/api/briefing/cron`, `/api/briefing/nightly-intelligence` (403 bez tajne) | pozivalac UNKNOWN | UNKNOWN |
| Praćenje promena zakona | `/api/zakon-monitoring/cron` (403) | pozivalac UNKNOWN | UNKNOWN |
| Čišćenje dokumenata | `/api/dokument/cleanup` (503 bez tajne) | pozivalac UNKNOWN | UNKNOWN |

## 5. Baza i migracije

- **Repo:** 124 SQL migracije, koje sa `CREATE TABLE` prave 146 tabela.
- **Kod:** referencira 156 tabela. Za 135 od njih postoji `CREATE` u migracijama.
- **Tabele koje kod koristi, a nemaju `CREATE` u repou (21)**, status `UNKNOWN` (iz repoa):
  - `predmeti`, `klijenti`, `predmet_dokumenti`, `predmet_hronologija`, `predmet_istorija`, `predmet_beleske`, `predmet_klijenti`, `predmet_komentari`;
  - `audit_log`, `feedback`, `user_credits`, `ai_cache`, `ai_sessions`, `api_costs`;
  - `case_profitability`, `events_outbox_metrics`, `intake_queue_metrics`, `klijenti_dokumenti`, `ratio_decidendi`, `user_activity_profile`;
  - `t` (lažni pogodak regex-a).
- **Zašto je to važno:** jezgro šeme (predmeti, dokumenti, klijenti) napravljeno je ručno u Supabase-u pre ere migracija. Postojanje u produkciji je *indirektno* PROVEN: NS003/NS004 smoke je pročitao predmete i dokumente. Tačan oblik kolona nije PROVEN iz repoa.
- **Tabele iz migracija koje kod nikad ne koristi (≈7 stvarnih):**
  - `impact_metrics`, `korisnik_plan`, `korisnik_usage`, `plan_limits`, `predmet_issue_labels`, `reported_errors`, `uploaded_documents`: status `MIGRATION_FILE_ONLY` ili `SUPERSEDED`;
  - `vindex_memory`: `REMOVED` (njen router je obrisan u `ff8c75db`);
  - `bi`, `if`, `iznad`: lažni pogoci regex-a.
- **Produkciona šema:** nije čitana (zabranjeno u ovoj misiji). Svaki talas koji dodaje upis mora prvo da potvrdi kolone u produkciji, i to radi founder. **Nikakav SQL se ne šalje iz ove misije.**

| Status | Primeri |
|---|---|
| CURRENT_SCHEMA_PROVEN (indirektno, kroz live smoke) | `predmeti`, `predmet_dokumenti`, `klijenti` (polja koja V2 NG čita) |
| MIGRATION_FILE_ONLY | `agent_recommendations` (082), `reasoning_*` (076: memorija kaže „čeka pokretanje"), `style_profili`, `simulator_partije`, `memory_entries`, `twin_simulacije` |
| SUPERSEDED | `uploaded_documents` (zamenjeno sa `predmet_dokumenti` / `intake_documents`), `korisnik_plan` / `plan_limits` (zamenjeno Feature Registry-jem i `rollout_flags`) |
| REMOVED | `vindex_memory` |
| UNKNOWN | sve tabele iz liste od 21 iznad, osim polja koja je smoke dokazao |

## 6. Šta je zaista uklonjeno (cela istorija, samo kodni direktorijumi)

| Fajl | Commit | Razlog | Klasa |
|---|---|---|---|
| `routers/vindex_memory.py` | `ff8c75db` | „tabela nikad live" | HISTORICAL_CODE_REMOVED |
| `routers/marketing_agent.py`, `services/content_generator.py`, `shared/social_connectors.py` | `9f1c9623` | revert marketing agenta | INTENTIONALLY_RETIRED |
| `app/services/multi_query_rag.py` | — | mrtav kod, 0 importa | SUPERSEDED |
| `app/services/audit_log.py` | `a5f4eeb8` | duplikat logike | SUPERSEDED |
| `shared/features.py` | — | zamenjen Feature Registry v2 | SUPERSEDED |
| `security/data_classification.py` | `966e0e77` | uklonjeno | SUPERSEDED |
| `landing.html` + 9 `site/*.html` | `d329add1` (NS004) | novi sajt; stare putanje vraćaju 301 | SUPERSEDED |

**Sve grane su spojene u `main`.** `website-rebuild-001` sadrži samo statičke prototipove (`prototype/vindex-next-app/*.html`). Nijedna sposobnost ne živi samo na nekoj grani.

## 7. Duplikati (jedan koncept, više vlasnika)

Prema principu Core Consolidation („1 koncept = 1 vlasnik = 1 algoritam = 1 istina"):

| Koncept | Implementacije | Preporučeni vlasnik |
|---|---|---|
| Prijem predmeta | `routers/smart_intake.py` · `routers/intake.py` · `klijenti/intake-wizard` | **smart_intake**; iz `intake` zadržati samo `bulk-import` ako nema ekvivalent |
| Sukob interesa | `/api/conflict-check` · `/klijenti/check-conflict` · `/api/intake/conflict-check` | `routers/conflict_check.py` (COI dokazano fail-closed) |
| Uvoz klijenata | `/klijenti/import-csv` · `routers/import_klijenti.py` | `/klijenti/import-csv` (ima V2 pozivaoca) |
| Memorija i učenje | `firm_memory` · `learning` · `memory_graph` · `knowledge_hygiene` · `knowledge_transfer` · `knowledge_base` · `interni` · `corrections` · `confidence_audit` | **interni stavovi + ishod pri zatvaranju**; ostalo REDESIGN ili RETIRE |
| Spoljne integracije | `routers/integracije.py` (`/v1`, `/api/webhooks`) · `routers/integrations.py` · `/api-kljucevi` + `/v1/query` (`routers/export.py`) | jedan modul; odlazni webhook tek posle SSRF provere |
| Jutarnji pregled | `morning_briefing` · `cio` · `case_commander/jutarnji` · `dashboard/command-center` | **morning_briefing** (`/app-v2` „Danas" ga već koristi) |
| Priprema ročišta | `hearing_cc` · `predictor/hearing-prep` | `hearing_cc` |
| Graf predmeta | `evidence_graph` · `knowledge_graph` | jedan (ili nijedan; nema dokaz korisničke vrednosti) |
| Jedna AI preporuka | `case_intelligence` · `case_commander` · `/api/predmeti/{id}/ai-preporuka` · `/api/procena` · `copilot` | Case Genome + `case_actions` kao jedini izvor sledećeg koraka |
| Pravno pitanje po oblasti | `routers/oblasti.py` · intent ruter u `/api/pitanje` | `/api/pitanje` |
| Ugovor o zastupanju | `ugovor_zastupanja` · `doc_templates` | `doc_templates` |
| Rokovi iz teksta | `rok_odluka` · `rokovi/guardian` · `/api/dokument/rokovi` | `rok_odluka` (ljudska odluka, FAZA 6.5) |
| **Dva V2 frontenda** | `/app-v2` (`v2/`, 125 ruta, founder) · `frontend-v2-ng` (`/app`, 3 rute) | **V2 NG je primarni.** Iz `/app-v2` se uzimaju *ugovori sa backendom* (api.js po feature-u), ne vizuelni sloj |
