# VINDEX AI — Architecture Bible v1.0

Status: živ dokument. Svaka tvrdnja o kodu ovde je verifikovana na 2026-07-18 —
proveri file:line pre nego što na osnovu njih doneseš odluku, jer se kod menja
brže od ovog dokumenta. Kad neki deo zastari, ispravi ga umesto da ga ignorišeš.

Svrha: ovo je ustav sistema, ne prompt i ne blog. Svaka rečenica ovde mora da
odgovori na pitanje "kako ovo utiče na kvalitet proizvoda?" — ako ne odgovara,
briše se. Ovaj dokument ne prodaje Vindex. Opisuje ga tačno onakvog kakav jeste,
i onoga u šta sme da preraste.

---

## DEO I — Vision, Mission, Philosophy

**Vision.** Vindex AI je srpski i regionalni operativni sistem za advokatske
kancelarije — platforma bez koje kancelarija ne može da funkcioniše, ne još
jedan AI alat pored deset drugih koje advokat otvara.

**Mission.** Sistem ne odgovara na pitanja. Sistem vodi predmet. Advokat
usmerava; sistem izvršava, prati, upozorava i uči.

**Core Philosophy — četiri pravila koja se ne pregovaraju:**

1. **Daily habit > WOW feature.** Pre svakog predloga za novu funkciju: "Da li
   ovo otvara Vindex svako jutro, ili je samo demo?" (`project_strategic_direction`)
2. **Rule A — proizvod ide za dokazom.** Svaka nova korisnički vidljiva funkcija
   mora da odgovori na jedan od četiri izvora: LEC, Hall of Shame, Office
   Accuracy Dashboard, ili stvaran korisnik/pilot. Bez dokaza — bez izgradnje.
3. **Rule B — arhitektura sme unapred, pod uslovima.** Infrastrukturna promena
   sme da se radi bez direktnog korisničkog dokaza AKO: (1) ne menja javni API,
   (2) ne menja UX, (3) poboljšava održavanje ili skalabilnost, (4) ne uvodi
   kompleksnost bez jasne koristi. Ne sme uvesti špekulativno *proizvodno*
   ponašanje — čim to uradi, vraća se na Rule A.
4. **Rule C — svaka veća arhitektonska promena mora imati brojku pre i posle.**
   Pre početka: koja metrika, bazna vrednost, ciljana vrednost, kako se meri.
   Posle: da li je cilj postignut, otvoreno rečeno. Bez ovoga, "impresivno
   zvuči" nije isto što i "proizvod je bolji".

**Anti-patterns — stvari koje se aktivno izbegavaju:**

- Arhitektura radi arhitekture ("zvuči enterprise" nije razlog da nešto postoji).
- Dupliranje stanja istog predmeta u dva sistema (npr. Firm DNA danas živi
  odvojeno od Genome-a — ovo je dug, ne uzor, vidi Deo III).
- Izmišljanje moat-a koji ne postoji (vidi Deo II, poslednja sekcija).
- Marketinški jezik u promptovima, dokumentaciji ili kodu ("AI-powered
  revolutionary platform" tipa rečenice se bacaju, ne pišu).
- Mikroservis/tabela/agent koji ne rade ništa što već ne radi postojeći deo
  sistema — spajaju se ili brišu, bez sentimentalnosti.

---

## DEO II — Case Operating System

**Zašto postoji.** Predmet advokata danas živi rasut po Wordu, mejlu, sudskom
portalu, Excelu i sećanju. Case Operating System je pokušaj da se sve to svede
na jedan živi model predmeta (Case Genome, Deo III) koji svaki modul čita i
piše nazad — umesto da svaki modul ima svoju privatnu verziju istine.

**Šta realno rešava danas** (ne šta bi trebalo da reši — vidi Deo IV za gap):
strukturisano izvlačenje činjenica/dokaza/rizika iz dokumenata predmeta u jedan
JSON objekat, sa verzionisanjem i istorijom. To je stvarno, testirano, koristi
se. Ono što NE rešava još: da se ostatak sistema (Firm DNA, Red Team, Next
Action) automatski reaguje na promenu tog objekta — danas svaki modul i dalje
mora da bude pozvan posebno.

**Šta je feature, šta je arhitektonska prednost, šta je stvaran moat — ovo se
ne meša:**

| Kategorija | Primer | Da li je teško kopirati |
|---|---|---|
| **Feature** | Case Genome JSON ekstrakcija, evidence ranking, war plan generator | Ne. Bilo koji ozbiljan konkurent sa GPT-4o pristupom može da napravi sličan prompt za par nedelja. |
| **Arhitektonska prednost** | Multi-agent orkestracija, event-driven pipeline, versioning sistem | Delimično. Sporije se kopira jer zahteva inženjerski rad, ali nije nemoguće — dobar tim to može da postigne za nekoliko meseci. |
| **Stvaran moat** | Akumulirano znanje kancelarije kroz vreme (Firm DNA, lessons_learned), dokazana tačnost merena javno (LEC/Hall of Shame/Dashboard), trošak zamene kad je predmet firme već "unutra" godinama | Da. Ovo raste samo sa vremenom i stvarnom upotrebom — konkurent ne može da ga preskoči novcem ili boljim promptom, mora da čeka isto toliko vremena sa isto toliko korisnika. |

**Iskreno:** sama multi-agent arhitektura nije moat. Dobar konkurent može da
napravi sličan sistem. Ono što traje jeste kombinacija kvaliteta implementacije,
ugradnje u svakodnevni rad (trošak zamene raste), akumuliranog znanja koje
korisnici stvaraju, i izgrađenog poverenja da sistem daje proverljive rezultate.
Ne tvrdimo više od ovoga.

---

## DEO III — Case Genome

Puna specifikacija JSON strukture, lifecycle-a, endpoint-a i trenutnog gap-a
prema V3 viziji već postoji i ne duplira se ovde:
`docs/architecture/CASE_GENOME_GAP_ANALYSIS_2026-07-18.md` + memorija
`project_case_genome`. Sažetak stanja (2026-07-18):

- **Entity model** — implementiran (`routers/case_dna.py:32-125`, GPT-4o JSON
  schema): pravna teorija, stranke, dokazi, kontradikcije, rizici, strategija.
- **Lifecycle** — implementiran: create/refresh (`POST .../refresh`), read
  (`GET .../case-dna`), history (`GET .../history`), compare dva dokumenta
  (razlika od compare dve verzije Genome-a, koje ne postoji).
- **Versioning** — implementiran, više od očekivanog: auto-increment `verzija`,
  `predmet_genome_history` tabela, realni delta-diff (`_compute_delta`). Nema
  rollback/restore endpoint-a — istorija je read-only.
- **Event model** — NE postoji. Genome nikad ne emituje event
  (`services/event_bus.py` postoji i radi za drugu svrhu — vidi Deo IV — ali
  `case_dna.py` ga ne uvozi).
- **Impact propagation** — NE postoji, i trenutni dizajn radi suprotno: svaki
  refresh je pun re-generate celog JSON-a, ne inkrementalni update.
- **Learning** — Firm DNA (`learning.py:914-1172`) postoji i radi, ali živi kao
  odvojeno stanje, ne kroz Genome. Ovo je danas najveće kršenje "single source
  of truth" principa iz Dela I.
- **Digital Twin** — implementiran kao zaseban modul (`digital_twin.py`, 3
  scenarija + što-ako, `project_strategic_direction` #13), takođe ne čita/piše
  kroz Genome direktno.

**Šta ovo znači za dalji rad:** Genome nije "još jedan modul koji treba
proširiti" — on je jedini deo sistema koji već radi kao SST. Sledeći
arhitektonski koraci (Deo X) treba da povlače Firm DNA, Red Team i Digital Twin
KA Genome-u, ne da grade nove module pored njega.

---

## DEO IV — Autonomous Pipeline

Cilj vizije: klijent uploaduje dokument → sistem automatski izvrši niz koraka →
advokat dobija gotov predmet. Stvarno stanje (2026-07-18), stage po stage:

| # | Faza | Status | Dokaz |
|---|---|---|---|
| 1 | Intake ulaz | **Rascepkano — 3 odvojena sistema** | CRM wizard (`intake.py`, ručni unos), Smart Intake (`smart_intake.py:80`, async queue), batch_ingest (nevezano — korpus zakona, ne predmeti klijenata) |
| 2 | OCR/parsing | Automatizovano | `shared/intake_worker.py:128 _process → :236 _extract_text`, pozadinski poller pokrenut na boot-u |
| 3 | Klasifikacija/ekstrakcija | Automatizovano | `IntakeWorker._classify:241`, `_extract_entities:246` |
| 4 | Genome refresh | Automatizovano, 3 realna okidača | `api.py:3916` (upload), `rocista.py:155` (novo ročište), `smart_intake.py:544` (finalize) |
| 5 | Kreiranje predmeta iz Smart Intake joba | **Ručno** | `smart_intake.py:327-330` — komentar u kodu priznaje da je "automatsko kreiranje predmeta" obećanje koje UX još ne ispunjava; treba eksplicitan `POST /jobs/{id}/finalize` klik |
| 6 | Reakcija ostatka sistema na Genome promenu | **Ne postoji** | Nijedan modul (Strategy, Red Team, Firm DNA, Morning Briefing) ne sluša Genome update — svaki se poziva posebno ili radi na svom cron rasporedu |
| 7 | Morning Briefing / deadline alerts | Automatizovano, ali pull ne push | `morning_briefing.py:397`, eksterni cron (06:00 UTC), ne reaguje na događaje |

**Event Bus — dva mehanizma, nejednaka:**

- **In-memory pub/sub** (`services/event_bus.py:169-224`, `EventType` sa 8+
  vrednosti, 4 registrovana handler-a) — **mrtav kod**. Nula poziva `.publish()`
  ili `emit()` bilo gde u aplikaciji van samog fajla. Infrastruktura postoji,
  testirana je izolovano, ali je niko ne zove.
- **Durable outbox** (`dispatch_pending_events`, `DispatchLoop`, pokrenut u
  `api.py:785/798`) — ovaj deo JESTE živ, ali samo za `DOCUMENT_JOB_*` events iz
  Smart Intake lanca, upisane direktno SQL RPC-om, ne kroz Python `emit()`.

**Iskreno:** danas je autonomno oko 3-4 od ~8-10 konceptualnih faza. "Upload →
50+ automatskih koraka → gotov predmet" je aspiracija, ne stanje. Najveći
propust nije nedostatak infrastrukture (bus postoji) — nego što postojeći bus
niko ne koristi. Ovo je najjeftiniji Rule B kandidat u celom dokumentu: povezati
`case_dna.py` i `smart_intake.py` finalize korak na već postojeći event bus,
umesto graditi novi.

---

## DEO V — AI Architecture

**Iskreno pre svega:** ono što se danas zove "multi-agent sistem" nije
orkestracija u pravom smislu. To je 6 nezavisnih GPT-4o poziva (`multi_agent.py`
`_AGENTS`: intake, research, drafting, litigation, billing, deadline) iza
zajedničkog wrapper-a, plus `gpt-4o-mini` ruter koji bira agenta, plus
sekvencijalno ulančavanje (`run_pipeline`) bez validacije između koraka. Nema
deljenog kontrakta, nema kritičara, nema confidence gate-a. Deo V opisuje ovo
kao "N specijalizovanih prompt-ova + ruter", ne kao "multi-agent sistem" —
terminologija mora da bude tačna, jer netačna terminologija vodi u pogrešne
arhitektonske odluke kasnije.

**Agent Registry** — postoji, ali plitko: dict od 6 unosa
(`multi_agent.py:23-308`), svaki samo `{naziv, ikona, opis, system prompt}`.
Nema tipiziranog input/output kontrakta — ulaz je slobodan tekst, izlaz je
slobodan tekst. Jedino mesto u AI sloju sa realnim (prompt-enforced, ne
code-enforced) izlaznim kontraktom je `case_dna.py` sa
`response_format={"type":"json_object"}` i ručno pisanom šemom u promptu.

**Confidence & Uncertainty** — `matter_intel.py:277-442`, potpuno
rule-based (ne AI): 5 dimenzija (činjenična, procesna, pravna, protivnička,
finansijska), svaka 0-100 kroz determinističku logiku, semafor na 35/65.
Napomena za čišćenje: `_compute_next_action` (`:231-259`) ima docstring koji
tvrdi da GPT-4o-mini formuliše odluku, ali telo funkcije je čist if/elif —
zastareo komentar, sitan dug, lako se ispravlja.

**Critic Layer** — ne postoji za Genome. ALI: `analiza/validator.py` (352
linije, sa test pokrićem u `tests/test_hallucination_guard.py` i
`test_analiza_validator.py`) je realan, testiran, non-blocking hallucination
guard — samo za "analiza" (analizu dokumenata) funkciju, ne za Genome i ne za
multi_agent.py. Ovo je najbolji template za budući Critic Layer — Rule B posao
je proširiti postojeći validator na Genome, ne izmisliti novi od nule.

**Explainability** — `case_dna.py:74-77` `snaga_faktori` (faktor+uticaj+zašto)
je jedini strukturisani "zašto" izlaz u sistemu. Agent promptovi imaju
hardkodovana pravila protiv izmišljanja citata (prompt-level guardrail, ne
code-enforced provera).

**Learning** — `learning.py` (1195 linija) ima realnu dubinu: outcome
tracking, case_patterns, counterfactual log, lessons_learned sa decay-check,
firm_dna sa svojom verzijom istorije, performance/impact izveštaji. Gap:
lekcije su slobodan tekst na nivou predmeta/ishoda, nisu povezane nazad na
konkretan agent/prompt/Genome polje koje je dovelo do te lekcije.

**Evaluation** — LEC (`evaluation/lec/annotations.json`) i Hall of Shame
(`evaluation/hall_of_shame/incidents.json`) su oba prazna (`dokumenti: []`,
`incidenti: []`) — placeholder, ne podaci. Office Accuracy Dashboard
(`GET /api/smart-intake/admin/accuracy`) meri operativne KPI (OCR uspeh, stopa
ručnih ispravki, LLM fallback %) — NE ground-truth tačnost, i pošteno vraća
prazno stanje ispod praga uzorka umesto izmišljene brojke. Ovo je dobar obrazac
— treba ga zadržati kad se LEC popuni.

---

## DEO VI — Knowledge Architecture

**RAG core.** `text-embedding-3-large` svuda. Pinecone indeks `vindex-ai`.
Namespace-ovi su rascepkani, ne jedinstveni: `zakoni_rs` (zakoni, ciljni
namespace prema planiranoj migraciji), zaostali `default`/`__default__` i dalje
referenciran u kodu, `sudska_praksa` (sudska praksa), `kb_{user_id}` (lične
beleške po korisniku). Retrieval je čist top-k similarity po namespace-u — nema
reranking sloja, nema hybrid (BM25+vector) pretrage.

**Evidence Graph** (`evidence_graph.py`) — ispravka prethodne gap analize:
OVO SE ČUVA, ne generiše se svaki put iznova. Jedan GPT-4o poziv proizvodi
`nodes`/`edges` JSON (tipovi veze: `POMINJE|POTVRDJUJE|OSPORAVA|VEZUJE|
PRETHODI`), upisuje se u `evidence_grafovi` tabelu, čita se i dopunjuje
(`dodaj_cvor` samo dodaje u isti JSON blob). I dalje nije prava graf baza — nema
traversal, nema tipiziranu šemu na nivou baze, nema inkrementalni re-index — ali
jeste perzistentna struktura, ne efemerna.

**Fact Graph, Law Graph, Citation Graph** — ne postoje ni u kom obliku. Nema
veze između članova zakona međusobno ni između zakona i sudske prakse koja ih
citira — `zakoni_rs` i `sudska_praksa` su odvojeni ravni vektorski prostori bez
ukrštenih referenci.

**Stanje korpusa (2026-07-18).** `data/` sadrži ~20 tipova izvora (sudovi,
ombudsman, parlament, komisija za javne nabavke, ECHR...). Ovo NIJE gotov,
čist korpus — `data/ingest_all_log.txt` pokazuje samo 3 izvora uspešno ingest-
ovana, 12+ sa greškom. `data/ingest_sp_log.txt` (2026-07-13) pokazuje da je
ingestion udario u Pinecone-ov mesečni limit write-unit-a (5,000,000), HTTP 429,
delimičan neuspeh. Ovo je aktivan, delimično neuspeo scraping poduhvat — treba
tretirati kao takav u planiranju, ne kao "korpus je gotov, samo treba povezati".

**Iskreno:** jedina stvarna, perzistentna, upitna struktura sa tipiziranom
šemom je Evidence Graph — i to je i dalje flat JSON blob po predmetu, ne graf
baza. Sve ostalo nazvano "graf" u V3 viziji trenutno ne postoji ni u jednom
obliku.

---

## DEO VII — Enterprise Architecture

**Iskreno pre svega — ovo je najzrelji deo sistema, iznenađujuće za veličinu
projekta.** Security, GDPR, enkripcija i error tracking su stvarni, verifikovani
kod, ne samo dokumentovana namera.

**Security** — `shared/permissions.py` (PermissionService po feature-u),
rate-limit + anomaly detection middleware (`api.py:855-942`), CSP header +
report endpoint (`api.py:977-988`), 9 modula u `security/` (prompt_guard,
ai_forensics, data_classification, agent_isolation, anomaly_detection,
chain_anchor, sbom_check, compute_sri, crypto). Migracije 043/044 postoje u
repo-u; da li su pokrenute na produkcionoj bazi je DB stanje, ne repo stanje —
ne pretpostavljati, proveriti direktno pre oslanjanja na njih.

**GDPR** — `routers/gdpr.py`: export, brisanje naloga, unsubscribe sa
potpisanim tokenima. Nema retention/auto-expiry politike — samo on-demand.

**Audit trail** — NIJE jedinstven sloj, rascepkan je po modulima (admin_
dashboard, confidence_audit, data_export, dokument, gdpr, kancelarija,
saradnja, wallet_provenance, web3, intake_queue). **Case Genome nema audit-log
upis uopšte** — samo verzionu istoriju, ne immutable audit chain. Ovo je realan
gap za advokatsku platformu gde se "ko je šta i kada promenio" često traži.

**Enkripcija** — stvarna, na nivou aplikacije: `security/crypto.py`, AES-256-GCM
za JMBG/pasoš/PIB pre upisa u bazu, Argon2id za lozinke, postoji backfill
skripta za postojeće plaintext podatke.

**Keširanje** — NE postoji nigde u aplikaciji. Nula pogodaka za redis/lru_cache
u celom repo-u.

**Observability** — Sentry je stvarno inicijalizovan (`api.py:30-52`), javni
status endpoint sa DB/OpenAI/Pinecone health check-ovima
(`status_page.py:24-44`). Logovanje je ad-hoc `logger.info/warning` po modulu —
nema correlation ID, nema request tracing, nema strukturisano logovanje.

**Skalabilnost** — `intake_queue.py` koristi `SELECT...FOR UPDATE SKIP LOCKED`
za bezbedno claim-ovanje posla između više worker-a — ovo je stvarno dizajnirano
za horizontalno skaliranje, iako ništa u repo-u ne potvrđuje da je trenutno
deployed više od jednog worker-a. Nema concurrency-limit ni queue-depth throttle.

**Zaključak:** slabe tačke nisu izmišljene tvrdnje — to su realni propusti:
nema keširanja nigde, audit log je rascepkan (i Genome nije u njemu),
observability je Sentry + ad-hoc logovi bez tracing-a. Sve ostalo u ovom delu
je realna, ozbiljna infrastruktura.

---

## DEO VIII — UX Bible

Ovo NIJE ekran-po-ekran katalog u v1.0 — to bi zahtevalo pun frontend audit
(`static/vindex.js` je ogroman) i bilo bi lažna preciznost da se to ovde tvrdi
bez tog rada. Umesto toga, v1.0 kodifikuje pravila koja su već potvrđena kroz
ponovljenu korisničku ispravku (najjači signal koji postoji) i ostavlja
ekran-po-ekran katalog kao živi dodatak koji raste organski.

**Ikonografija** (`feedback_no_generic_icons`) — apsolutna zabrana generičkih
emoji u UI-ju (⚔️🧠⚖️🎯🏢🤝🔄⚡💡📊🚨 i slično). Dozvoljeno: ✓ ✅ ⚠️ kao
funkcionalni indikatori, neutralni simboli (▾ →), CSS obojene tačke, ili već
integrisan Lucide icon set. Founder je ovo ispravljao 3+ puta nakon regresija —
tretirati kao tvrdo pravilo, ne preporuku.

**Vizuelni jezik** (`feedback_no_generic_ui_bloomberg_style`) — referenca je
Bloomberg Terminal / Palantir Foundry, ne Linear/Stripe generic-SaaS izgled.
Potvrđeni tokeni: corner radius 2-4px (nikad 8px+ ili pill/999px), nula
glow/blur senki (samo 1px precizne akcent linije), flat/solid dugme fill
(#00d4ff cyan, nikad gradijent), JetBrains Mono monospace, kompaktan terminal-
gustina spacing-a, imenovane vanilla-JS komponente (VxExecutiveHeader,
VxInsightPanel, VxCaseTable, VxAgentCard, VxTimeline, VxKanban, VxDataGrid),
asimetričan layout — jedan hero po ekranu, ne uniformna kartica-grid.

**Jedan tvrd izuzetak:** `#tab-h` ("Pregled dana") dashboard ekran je
eksplicitno zaključan i isključen iz bilo koje globalne promene tokena.

---

## DEO IX — Coding Constitution

Izvedeno iz posmatranja 5 rutera (`case_dna.py`, `evidence.py`,
`matter_intel.py`, `strategija.py`, `learning.py`) — ovo su konvencije koje
VEĆ postoje dosledno, ne nove ideje.

1. **Oblik rutera** — `# -*- coding: utf-8 -*-` header, docstring na vrhu
   fajla koji nabraja endpoint-e, `router = APIRouter(prefix="/api/x",
   tags=["x"])`. Izuzetak: `strategija.py` nema `prefix`, putanje su hardkodovane
   po ruti — treba ispraviti kad se taj fajl sledeći put dira (Rule B: ne menja
   API, smanjuje kompleksnost).
2. **Auth pravilo** — `Depends(get_current_user)` za čitanje i jeftine
   operacije; `Depends(PermissionService.require(feature))` za sve što zove
   `UsageService.consume`. Bez izuzetaka u proverenih 5 fajlova — ovo je pravo
   pravilo, ne slučajnost.
3. **Supabase pristup** — 100% dosledno: svaki DB poziv je
   `await asyncio.to_thread(lambda: supa.table(...)...)`, čak i u pozadinskim
   task-ovima. Nezavisni upiti se batch-uju kroz `asyncio.gather(...,
   return_exceptions=True)`. Postoji pomoćna funkcija koja guta exception u `[]`
   — reimplementirana zasebno u `matter_intel.py` (`_d`) i `learning.py`
   (`_safe`/`_safe_one`). Kandidat za konsolidaciju u `shared/` (Rule B: čist
   refaktor, ne menja ponašanje).
4. **Error handling** — `HTTPException` za greške vidljive klijentu (404
   vlasništvo, 422 validacija); `logger.warning/exception` + graceful fallback
   za AI/DB greške koje ne moraju da obore request. Provera vlasništva
   (`.eq("user_id", uid)`) ide PRE svake izmene, bez izuzetka.
5. **Usage metering** — `UsageService.consume(...)` jednom po naplativoj akciji,
   posle uspeha, nikad pre. `strategija.py` ima ponovljen `multiplier=1`
   override (identičan komentar 6 puta) da spreči nasleđivanje 6x multiplier-a
   sa orkestrator endpoint-a — realan footgun koji se rešava zaobilaženjem
   umesto strukturnim fix-om. Kandidat za pravi fix, ne za novi zaobilazak broj 7.
6. **Izbor GPT modela** — bez fiksnog globalnog pravila, ali dosledna logika:
   `gpt-4o` za Genome-kritičnu ili finalnu korisničku analizu, `gpt-4o-mini` za
   jeftine/pozadinske/visoko-volumenske pozive. `response_format:
   json_object` svuda gde je izlaz strukturisan. Temperatura 0-0.2 skoro svuda.
7. **Versioning pattern** — `case_dna.py`-jev `verzija` + history tabela nije
   deljen kao pattern — `learning.py`-jev `firm_dna` nezavisno izmišlja istu
   ideju (`verzija`, `verzija_od`, `aktuelna` bool, `/history` endpoint).
   Dva odvojena rešenja za isti koncept. Kandidat za zajednički helper kad se
   sledeći modul bude versioning-ovao (Rule B).

**Kako izgleda dobar novi endpoint u ovom sistemu:** prati pravila 1-6 iznad
tačno onako kako ih `case_dna.py` prati danas. On je referentni fajl — kad je
nejasno kako nešto treba da izgleda, pogledaj njega prvo.

---

## DEO X — Roadmap

Roadmap ovde NIJE lista feature-a sa datumima — to bi bilo suprotno Rule A/B/C
iz Dela I. Umesto toga, svaka stavka je klasifikovana i, gde je Rule B, ima
skiciran uspeh-kriterijum (Rule C) koji treba precizirati pre početka rada.

**Track 1 — Rule B kandidati (infra, ne čeka dokaz, ali čeka Rule C metriku):**

| Stavka | Zašto je najniži rizik | Skica Rule C metrike |
|---|---|---|
| Event Bus → Genome wiring | Bus već postoji i radi za intake pipeline — ovo je "poveži cev", ne "sagradi cev" | Pre: 0 Genome event-a emitovano. Posle: X% Genome refresh-a producira event koji nešto realno konzumira (ne samo log) |
| `analiza/validator.py` → Genome/multi_agent | Testiran obrazac već postoji, samo nije primenjen šire | Pre: 0% Genome/agent izlaza prolazi kroz guard. Posle: definisati ciljani % i mereno smanjenje nepodržanih tvrdnji (isti oblik kao founder-ov primer u Rule C) |
| Konsolidacija `_d`/`_safe` helper-a, versioning pattern-a | Čist refaktor, nula rizika po API/UX | Pre/posle: broj nezavisnih implementacija istog obrasca (danas 2-3 → cilj 1) |
| `strategija.py` prefix fix | Kozmetički, uklanja nekonzistentnost | Nema potrebe za Rule C metrikom — trivijalno, radi se usput |

**Track 2 — Rule A čeka dokaz (ne radi se dok dokaz ne postoji):**

Critic Layer za Genome (širi od validator prenosa iznad — pravi confidence-gate
koji blokira save), Impact Propagation (inkrementalni update umesto punog
recompute-a), Fact/Law/Citation Graph, Genome State Machine, Version
restore/rollback, Internal Agent Registry sa tipiziranim kontraktima. Svi ovi
postaju aktivni tek kad LEC, Hall of Shame, Dashboard ili stvaran pilot pokažu
konkretan nalaz koji na njih upućuje — vidi
`docs/architecture/CASE_GENOME_GAP_ANALYSIS_2026-07-18.md` za pun spisak i
trenutni status dokaza (na 2026-07-18: sva četiri izvora prazna).

**Track 3 — preduslov za Track 2, i jedini stvarno hitan posao:**

Popuniti LEC sa 150-200 stvarno anotiranih dokumenata, pokrenuti 3-5 kancelarija
pilot na Smart Intake-u. Ovo nije tehnički posao — vlasnik zadatka je founder,
ne Claude Code (`project_strategic_direction`). Dok se ovo ne uradi, Track 2 se
ne pomera, bez obzira koliko "očigledno korisna" neka stavka izgledala.

**V4/V5 (enterprise nivo)** — ne definišu se konkretno u v1.0. Preuranjeno je
planirati keširanje, jedinstven audit sloj ili multi-worker skaliranje pre nego
što postoji realan signal (spor sistem, veliki dokazni trag koji nedostaje,
ili potvrđen deployment sa više worker-a) da su ti problemi stvarni, ne
hipotetički. Kad se signal pojavi, dodaje se ovde kao nova Track 1 stavka sa
svojom Rule C metrikom — ne unapred kao nagađanje.
