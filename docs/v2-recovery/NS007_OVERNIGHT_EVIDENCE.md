# NS007 — WHILE YOU SLEEP — OVERNIGHT EVIDENCE

Grana `feature/vindex-v2-ns007-while-you-sleep`, napravljena iz TAČNO `dac1f6dd` (NS006 zamrznut).
Provereno pre grananja: `origin/main` = `99d2c6b9`, `origin/feature/vindex-v2-ns006-living-matter` = `dac1f6dd` — bez
pomeranja. Radna kopija: `C:\vindex-ns007`. Migracija 135 je već primenjena (founder) i ne pokreće se ponovo.

Klasifikacija: **PROVEN** (izmereno/pročitano u kodu) · **INFERRED** (zaključeno) · **ASSUMED** · **UNKNOWN**.

---

## TASK 0 — FORENZIČKA MAPA AUTONOMIJE

**PROBLEM.** Pre bilo kakve arhitekture: šta danas postoji za autonomni rad, ko je vlasnik, šta košta, šta izlazi
napolje i šta se desi kad se pozove `/api/cron/daily`.

### A. Mapa raspoređivača (PROVEN)

| Okidač | Gde | Šta poziva | Napomena |
|---|---|---|---|
| `POST /api/cron/daily` | `api.py:1936` | 13+ modula (v. J) | spoljni okidač (Render/cron-job.org) — konfiguracija NIJE u repou |
| GitHub Actions `email-cron.yml` | `0 8 * * *` | `routers/email_notif.py` (header `X-Cron-Key`) | samo mejl podsetnici |
| GitHub Actions `sms-cron.yml` | raspored | SMS ruta | samo SMS |
| `POST /api/portal-monitoring/cron-proveri` | `routers/portal_monitoring.py:540` | portal.sud.rs provera | poziva se i iz dnevnog crona |
| Event Bus `DispatchLoop` | `services/event_bus.py` | Case Evolution posledice | nije raspoređivač rada, već dostava događaja |

**Ne postoji namenski raspoređivač autonomnog rada** (PROVEN: pretraga `render.yaml`, `.github/workflows/*`, svih
`/api/cron/*` ruta).

### B. Registar agenata (PROVEN)

`workers/background_agents.py::_agent_registry` — TAČNO 2 agenta:
`court_portal_watcher` (`services/agent_tasks/court_portal_watcher.py`) i `precedents_radar`
(`services/agent_tasks/precedents_radar.py`). Jedina javna ulazna tačka: `run_background_agents(run_id)`, jedini
pozivalac: `api.py:2286` (Modul 10 dnevnog crona, `timeout=600`). Ne postoji drugi registar.

### C. Životni ciklus preporuke (PROVEN)

`agent_recommendations` (082): `pending → accepted | rejected`, `UNIQUE(user_id, dedup_key)`, RLS SELECT/UPDATE
vlastitih redova, INSERT samo service-role. Pregled: `routers/agent_notifications.py` (GET lista, POST accept/reject).
Accept/reject **samo menja status** — nema efekta. Nema stanja izvršavanja, zauzimanja, ponavljanja, greške ni
izvora. `CHECK (agent_type IN ('court_portal_watcher','precedents_radar'))` — zatvoren skup.

### D. Mehanizmi radnog proizvoda / staging-a (PROVEN)

- `staging_memory` (088): **nacrt čeka potvrdu advokata pre ulaska u Pinecone** (zaštita od „toksičnog učenja").
  Stanja `pending/approved/rejected`, `confidence_score` iz Quality Gate-a, `pinecone_indexed`. Jedini pisac:
  `routers/drafting.py::_stage_draft_for_review`. Odgovornost je **promocija u memoriju znanja**, NE izvršavanje rada.
- `agent_recommendations.payload`: `court_portal_watcher` u payload stavlja i nacrt žalbe (`generate_draft`) —
  polu-radni-proizvod bez izvora, bez stanja kvaliteta, bez veze na verziju Genome-a.
- `routers/hearing_cc.py` (`POST /api/rociste/command-center`): sinhrona priprema za ročište na zahtev advokata;
  rezultat se NE čuva (vraća se u odgovoru).

### E. Spoljni efekti (PROVEN, pretraga koda)

| Izvor | Efekat |
|---|---|
| `routers/morning_briefing.py:639` | SMTP slanje mejla |
| `routers/portal_monitoring.py:99, 210` | HTTP ka portal.sud.rs (čitanje) + **Viber poruka** korisniku |
| `routers/email_notif.py` (moduli 6–8 dnevnog crona) | mejl podsetnici, onboarding, nedeljni sažetak |
| `services/agent_tasks/*` | **nema** spoljnog slanja; pišu samo `agent_recommendations` |
| `routers/hearing_cc.py` | nema spoljnog efekta osim poziva modela |

### F. Granice AI troška (PROVEN)

- Pozadinski agenti: budžet `AGENT_BUDGET_PER_ORG_DAILY=40` **pokretanja agenta po organizaciji dnevno**, brojano iz
  `usage_events(feature='background_agents')`. **Broji pokretanja, ne pozive modela**: jedno pokretanje
  `precedents_radar` = do 20 predmeta × 5 odluka = **do 100 poziva `gpt-4o-mini`** (+ RAG pretraga), i to za SVAKI
  aktivan predmet sa Genome-om, SVAKI dan, bez obzira na to da li se išta promenilo.
- `court_portal_watcher`: po promeni na portalu do 1 `generate_draft` poziv.
- Hearing Command Center: `gpt-4o`, 4000 tokena, 3 kredita (`UsageService.consume` POSLE poziva modela).
- Neuspeh klasifikacije u `precedents_radar` → tiho `"neutralno"` (gubi se signal i trošak je već nastao).

### G. Revizioni trag (PROVEN)

`shared/audit_immutable.py::log_action` — jedini vlasnik nepromenjivog traga; beleži SAMO akcije iz
`AUDITABLE_ACTIONS` (ostale tiho preskače), vraća `None` kad upis ne uspe („nikad ne blokira"). Pozadinski agenti
upisuju `AGENT_AUTONOMOUS_EXECUTION` POSLE izvršenja; greška upisa se loguje na `debug` nivou.

### H. Ponavljanje i deduplikacija (PROVEN)

- `agent_recommendations`: `UNIQUE(user_id, dedup_key)` — ali skup posao (RAG + klasifikacija) se izvršava PRE
  pokušaja upisa, pa duplikat ne štedi trošak, samo sprečava dupli red.
- `shared/idempotency.py` (NS005 A2): trajna idempotentnost HTTP mutacija (`v2_mutation_idempotency`, PK zauzimanje,
  IN_PROGRESS se nikad ne oslobađa istekom) — za korisničke POST-ove, ne za pozadinske poslove.
- Case Evolution: `case_evolution_consequences UNIQUE(event_id, consequence_name)`.
- Pozadinski agenti: **nema zauzimanja, nema zakupa, nema retry-ja**; greška → `greske += 1`, sledeći pokušaj tek
  sutradan.

### I. Granice zakupaca (PROVEN)

Agenti dobijaju `user_id` iz `predmeti.user_id` (service-role čitanje); `precedents_radar` čita predmete
`.eq("user_id", user_id)`. Budžet je po organizaciji (`kancelarija:{id}` ili `solo:{uid}`). Pregled preporuka:
`.eq("user_id", user["user_id"])`, tuđa → 404.

### J. Šta se izvrši kad se pozove `/api/cron/daily` (PROVEN, `api.py:1936–2370`)

1 workflow eskalacije · 2 zakon monitoring (samo ponedeljkom) · 3 brisanje memorije (`memory_entries` DELETE) ·
4 portal.sud.rs (HTTP + Viber) · 5 workflow eskalacije (DRUGI PUT) · 6 mejl podsetnici · 7 onboarding mejlovi ·
8 nedeljni sažetak · 9 retention cleanup (brisanje) · 9a reaper pipeline događaja · 9a2 reaper ročišta ·
9b reaper faktura · 10 pozadinski agenti (600 s) · heartbeat `chain_anchors` + `cron_runs`.

### Eksplicitne potvrde / opovrgavanja

| Tvrdnja | Ishod |
|---|---|
| pozadinski agenti prave preporuke, ne završene radne proizvode | **POTVRĐENO** (jedini izuzetak: nacrt žalbe u payload-u `court_portal_watcher`, bez izvora i bez životnog ciklusa rada) |
| čitanje budžeta je fail-open | **POTVRĐENO** — `workers/background_agents.py:159`: „fail-open na budžet proveru" |
| u repou ne postoji namenski raspoređivač autonomije | **POTVRĐENO** |
| dnevni cron je preširok za čest okidač autonomije | **POTVRĐENO** — šalje mejlove/Viber, briše podatke, radi eskalacije; čest poziv bi umnožio sve to |
| `staging_memory` ima užu odgovornost | **POTVRĐENO** — promocija nacrta u memoriju znanja posle potvrde advokata |
| heartbeat dnevnog crona nije atomsko zauzimanje | **POTVRĐENO** — provera je SELECT na početku, upis (`upsert`) tek na KRAJU; dva istovremena poziva oba prolaze; greška čitanja → `except: pass` (fail-open) |

### Dodatni nalazi bitni za dizajn

1. Hearing Command Center NIJE bezbedan za autonomni rad u postojećem obliku: kontekst predmeta je fail-soft (nastavlja
   bez kanonskog konteksta), sistemski prompt sam navodi članove zakona (model proizvodi autoritet), vraća
   `hearing_score` 0–100, kredit se troši POSLE poziva. → Task 8 odluka.
2. Workspace (`routers/workspace.py`) ne prikazuje preporuke agenata ni `staging_memory` — radni proizvodi danas
   nemaju mesto u operativnom pregledu.
3. Lokalno je instaliran PostgreSQL 17.9 (`C:\Program Files\PostgreSQL\17\bin`) → atomsko zauzimanje se može
   dokazati na PRAVOM Postgres-u (izolovan klaster u scratchpad-u, bez veze sa produkcijom).

**FAJLOVI.** Samo ovaj dokument. Nijedan produkcioni fajl.

**SLEDEĆA KAPIJA.** Task 1 — trajni ugovor autonomije.

---

## TASK 1–2 — TRAJNI UGOVOR AUTONOMIJE + ATOMSKO ZAUZIMANJE CIKLUSA

**PROBLEM.** Nijedna postojeća tabela nema pun ugovor (identitet posla, zakup, ponavljanje, rezultat, pregled,
poreklo, vlasništvo, deduplikacija, greška/dead-letter) — Task 0. Heartbeat dnevnog crona nije atomsko zauzimanje.

**FALSIFIKACIJA.** (1) Proširiti `agent_recommendations`? Odbačeno: zatvoren `CHECK agent_type`, nema stanja
izvršavanja, a ona ostaje legacy površina preporuka. (2) `staging_memory`? Odbačeno: druga odgovornost (promocija u
memoriju znanja). (3) Budžet brojati iz `usage_events`? Odbačeno: upis ide POSLE poziva modela (TOCTOU) i nema
atomske rezervacije. (4) Zauzimanje ciklusa SELECT-pa-INSERT? Odbačeno (isti kvar kao heartbeat).

**ODLUKA / ŠEMA — migracija `136_autonomy_work_items.sql` (KREIRANA, NIJE primenjena na produkciji).**
- `autonomy_cycles`: `window_key UNIQUE`; zauzimanje = INSERT; RUNNING ciklus se nikad ne otima (zastareo je
  vidljiv: `claimed_at` bez `finished_at`); oporavak prekinutog rada je na nivou posla.
- `autonomy_work_items`: `UNIQUE(user_id, dedupe_key)`; stanja QUEUED / RUNNING / READY_FOR_REVIEW / ACCEPTED /
  REJECTED / FAILED / DEAD_LETTER / SUPERSEDED — nijedno više; `reason` (ZAŠTO) obavezan; `source_refs` = samo
  identifikatori; ograničenja: RUNNING ima zakup, READY/ACCEPTED/REJECTED imaju proizvod, pregled ima ko/kada,
  plaćena rezervacija ima dan; veličina sadržaja ograničena.
- `autonomy_claim_work_item(id, owner, lease, limit)`: zaključavanje reda → zakup samo za QUEUED ili RUNNING sa
  ISTEKLIM zakupom → iscrpljeni pokušaji = DEAD_LETTER → za PLAĆEN posao savetodavna brava po organizaciji, prebrojavanje
  dnevnih jedinica i rezervacija PRE modela; `NULL` limit = BUDGET_UNKNOWN (nije „neograničeno").
- RLS: korisnik SELECT samo svoje; nikakav INSERT/UPDATE/DELETE i nikakvo izvršavanje funkcije za
  `authenticated`/`anon`; ciklusi nevidljivi korisnicima.
- Brisanje predmeta: `ON DELETE CASCADE` — ista politika kao 082 i kanonsko brisanje predmeta (P15); revizioni trag
  ostaje u `audit_immutable`. Testovi brisanja predmeta: 91/91 sa 136 prisutnom.

**GRANICA KOJA SE NE MOŽE ZATVORITI (iskreno).** Tačno-jednom izvršavanje modela nije moguće: radnik može da padne
posle naplate, a pre upisa. Granica: svaki pokušaj rezerviše jedinicu, plaćen posao ima podrazumevano
`max_attempts = 2` → jedan logički posao košta najviše 2 izvršenja, zatim DEAD_LETTER (vidljivo). Rezultat i
READY_FOR_REVIEW se upisuju u JEDNOJ naredbi, samo za vlasnika zakupa — nema stanja „sačuvano, a nije spremno".

**IMPLEMENTACIJA.** `services/autonomy.py` — jedini vlasnik životnog ciklusa (upis kandidata, zauzimanje ciklusa i
posla, upis rezultata, neuspeh, zastarevanje). Nije registar agenata ni raspoređivač.

**TESTOVI.**
- PRAVI PostgreSQL 17.9 (izolovan lokalni klaster, sveža baza po testu, migracija iz repoa) — 10/10:
  ponovljiva migracija; **20 istovremenih zauzimanja prozora → tačno 1 pobednik, 19× 23505**; **20 istovremenih
  zauzimanja istog posla → tačno 1 CLAIMED**; isti okidač → 1 posao (drugi korisnik ima svoj); **10 istovremenih
  plaćenih poslova, budžet 3 → tačno 3 CLAIMED, 7 ostaje QUEUED**; budžet po organizaciji, besplatan posao ne troši,
  nepoznat limit zatvara; zakup: važeći se ne otima, istekao se preuzima, iscrpljen → DEAD_LETTER sa najviše 2
  rezervacije; rezultat upisuje samo vlasnik; RLS i prava (uključujući direktnu proveru prava izvršavanja);
  brisanje predmeta.
- Paritet lažne baze i PostgreSQL-a (isti scenario, 11 koraka, svih 6 ishoda) — 1/1. Paritet je odmah otkrio
  razliku u MOM Python sloju (`limit=None` je značio „podrazumevano", pa nepoznat limit nije mogao da stigne do
  baze) — ispravljeno.
- Servisni sloj nad lažnom bazom — 6/6.

**MUTACIJE (17/17 ubijeno).** SQL nad pravim Postgres-om: D1 bez `FOR UPDATE`, D2 bez brave budžeta (TOCTOU), D3
prozor bez UNIQUE, D4 bez granice pokušaja, D5 otimanje važećeg zakupa, D6 nepoznat limit = neograničeno, D7 RLS
svi vide sve, D8 korisnik sme da poziva zauzimanje (prvo PREŽIVELA — druga brava je nedostatak UPDATE prava; dodata
direktna provera prava), D9 bez dedupe ključa, D10 besplatan troši, D11 budžet globalan. Emulacija/servis: E1, E2,
E3 — paritet ih hvata.

**OGRANIČENJE.** Testovi na pravom Postgres-u traže `VX_TEST_PG_DSN`; bez njega se PRESKAČU (CI ih trenutno ne
pokreće). Supabase specifičnosti (PostgREST, stvarne uloge) su emulirane minimalnim okruženjem.

**SLEDEĆA KAPIJA.** Task 3 — uska ulazna tačka raspoređivača.
