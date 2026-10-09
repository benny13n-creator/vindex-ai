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

---

## TASK 3 — USKA ULAZNA TAČKA RASPOREĐIVAČA

**PROBLEM.** Autonomni rad ne sme da zavisi od `/api/cron/daily` (šalje mejlove/Viber, briše, eskalira — Task 0 J),
ni od njegovog ne-atomskog heartbeat-a.

**FALSIFIKACIJA.** (1) Da dnevni cron poziva novu rutu preko HTTP-a? Zabranjeno direktivom i nepotrebno. (2) Da se
koristi postojeći `BRIEFING_CRON_SECRET`? Odbačeno: ista tajna bi okidala ceo dnevni dispečer; posebna tajna znači da
procurela tajna okidača autonomije ne daje pristup brisanjima i slanju mejlova. (3) Da pozivalac zadaje prozor ili
korisnika? Odbačeno: prozor računa server (UTC sat), telo se ne čita.

**ODLUKA / IMPLEMENTACIJA.**
- `POST /api/cron/autonomy` (`routers/autonomy.py`): `X-Autonomy-Secret` == `AUTONOMY_CRON_SECRET`
  (`hmac.compare_digest`); tajna nepodešena ili kraća od 32 znaka = zatvoreno; nepodešena, pogrešna, nedostajuća →
  bajt-identičan 401. Tok: zauzmi prozor `auto:YYYY-MM-DDTHH` → `run_autonomy_cycle` → završi ciklus. Zauzimanje
  nedostupno → 503 (radnik se ne poziva); pad radnika → 500 + ciklus FAILED; upis završetka neuspeo →
  `COMPLETED_UNRECORDED` (rad je već trajno upisan po stavkama, ciklus ostaje vidljivo RUNNING, ne krade se).
- Kanonski radnik ostaje `workers/background_agents.py`. Registar je SADA JEDAN SPISAK MODULA (`_agent_modules`):
  `_agent_registry()` (dnevni cron, legacy preporuke) bira module sa `run` — rezultat identičan kao pre;
  `_work_agents()` bira module sa `planiraj` + `izvrsi`. Nema drugog registra.
- `run_autonomy_cycle`: plan (0 poziva modela) → upis (jedan okidač = jedan red; nova verzija zastareva staru;
  poništen okidač zastareva QUEUED/READY) → zauzimanje kroz `autonomy_claim_work_item` → izvršilac → rezultat samo
  za vlasnika zakupa. `NeuspehPosla` (u `services/autonomy.py`) = FAILED, bez ponavljanja; drugi izuzetak =
  prolazno (zakup ističe, ograničeno sa `max_attempts`). Bilo koji ishod zauzimanja osim CLAIMED, uključujući grešku
  baze → izvršilac se NE poziva.
- Dnevni cron i dalje zove `run_background_agents` (legacy preporuke) — dva toka ne dele poslove, pa nema
  dvostrukog izvršavanja istog rada.

**RUTE.** Nova: `POST /api/cron/autonomy` (mašina-mašini). Nijedna postojeća nije menjana.

**TESTOVI.** 14/14 novih + postojeći `test_background_agents`, `test_cron_daily_dispatcher`,
`test_cron_daily_failclosed_auth` (ukupno 53 passed).

**MUTACIJE (11/11 ubijeno).** S1 nepodešena tajna = otvoreno; S2 obično/prefiks poređenje; S3 drugačiji 401 kad nije
podešeno (orakl); S4 drugi poziv istog prozora radi; S5 greška zauzimanja prozora → ipak radi; S6 pad radnika bez
FAILED ciklusa; S7 greška zauzimanja posla → izvršava se; S8 iscrpljen budžet → izvršava se; S9 `NeuspehPosla` kao
prolazan; S10 agent trajnog rada ulazi u dnevni cron; S11 poništen okidač se ne zastareva.

**OGRANIČENJE.** Prozor je UTC sat (najviše 24 ciklusa dnevno, bez obzira na broj okidanja); konačnu kadencu
određuje founder (Task 4 plan).

**SLEDEĆA KAPIJA.** Task 4 — klijent okidača i plan za Render (bez postavljanja).

---

## TASK 4 — KLIJENT OKIDAČA + PLAN ZA RENDER (NIJE POSTAVLJENO)

**PROBLEM.** Produkcioni raspoređivač treba da okine ciklus bez dupliranja Vindex runtime-a i tajni u drugi servis.

**ODLUKA.** `scripts/trigger_autonomy_cycle.py`: samo stdlib, URL i tajna iz okruženja, jedan POST bez tela, timeout,
izlaz ≠ 0 za sve osim 2xx, ispis samo statusa/prozora/run_id/brojeva. Tajna se ne šalje preko običnog HTTP-a osim ka
localhost-u; URL sa korisnikom/lozinkom se odbija. Nema baze, modela ni poslovne logike.
`docs/v2-recovery/NS007_RENDER_CRON_PLAN.md`: kandidat arhitektura (jedan lagan Render Cron Job → uska ruta),
preduslovi redom, kadenca kao OPCIJE (founder odlučuje), isključivanje. Označeno NIJE POSTAVLJENO.

**TESTOVI.** 12/12 — skripta kao pravi proces protiv lokalnog HTTP servera: uspeh, SKIPPED, 401/500/503, isteklo
vreme, nepostojeći server, 5 konfiguracionih grešaka bez ijednog zahteva; tajna nikad u izlazu.

**MUTACIJE (5/5 ubijeno).** K1 ispis celog tela; K2 ne-2xx kao uspeh; K3 http ka udaljenom hostu; K4 tajna u poruci
greške; K5 bez timeout-a.

**PRODUKCIJA.** Ništa nije postavljeno. Render nije diran.

**SLEDEĆA KAPIJA.** Task 5 — budžet autonomije zatvoren pri grešci.

---

## TASK 5 — BUDŽET AUTONOMIJE ZATVOREN PRI GREŠCI

**EVIDENCIJA (PROVEN, Task 0).** Legacy agenti: čitanje budžeta fail-open (`workers/background_agents.py:159`), budžet
broji POKRETANJA agenta a ne pozive modela, upis potrošnje ide POSLE izvršenja.

**ODLUKA.**
- Izvor istine o trošku autonomnog rada je SAMA STAVKA (`budget_units`, `reserved_day`), rezervisana u
  `autonomy_claim_work_item` PRE poziva modela, pod bravom po organizaciji (Task 1–2). `usage_events` (feature
  `autonomy`) je samo računovodstvo POSLE trajnog upisa rezultata — nije osnov odluke, pa njegov pad ne može ni da
  otvori potrošnju ni da ponovi rad.
- Jedinica budžeta = jedno izvršenje plaćenog posla (jedan poziv modela po izvršiocu, Task 8/10). Budžet je po
  organizaciji (`kancelarija:{id}` ili `solo:{uid}`) i zajednički za sve vrste plaćenog rada; resetuje se po UTC
  danu. Besplatan (deterministički) rad ne troši budžet.
- Fail-closed putanje: baza nedostupna pri zauzimanju → posao nije zauzet → izvršilac se ne poziva; nepoznat ili
  neispravan limit (`AUTONOMY_BUDGET_PER_ORG_DAILY`) → BUDGET_UNKNOWN; iscrpljen → posao ostaje QUEUED.
- Legacy fail-open budžet pozadinskih agenata NIJE menjan (direktiva cilja nov autonomni trošak) — zabeleženo kao dug.

**TESTOVI.** 6/6 (nivo radnika) + SQL pod konkurencijom iz Task 1–2: **10 plaćenih, budžet 3 → model pozvan tačno 3
puta**, 7 ostaje QUEUED; isti dan 0 novih; sledeći dan nova trojka; budžet zajednički za kancelariju i vrste rada;
besplatan rad radi pri budžetu 0 i ne knjiži se; **baza budžeta nedostupna → 0 poziva modela**; **pad `usage_events`
posle završenog rada → proizvod ostaje READY, ne pokreće se ponovo, neuspeh se broji**; knjiženje bez sadržaja
(samo `work_item_id`, `run_id`, `attempt`).

**MUTACIJE (4/4 ubijeno + D2/D6/D10/D11 iz Task 1–2).** B1 knjiži i besplatan rad; B2 neuspeh knjiženja vraća posao
u red; B3 neuspeh knjiženja prijavljen kao uspeh; B4 budžet se ne resetuje po danu.

**SLEDEĆA KAPIJA.** Task 6 — deterministički planer.

---

## TASK 6–7 — DETERMINISTIČKI PLANER + PODOBNOST ZA PRIPREMU ROČIŠTA

**PROBLEM.** Legacy `precedents_radar` svaki dan prolazi kroz SVE aktivne predmete sa Genome-om i za svaki zove model
(Task 0 F). Autonomni rad mora da nastaje samo iz stvarnog okidača, sa razlogom, bez modela u odlučivanju.

**EVIDENCIJA (PROVEN).** Ročišta: `rocista` (005), `status ∈ {zakazano, odrzano, odlozeno, otkazano}`, `datum DATE`,
`vreme TIME`. Završni statusi predmeta: `shared/constants.TERMINALNI_STATUSI_PREDMETA = (zatvoren, arhiviran,
odbijen)` (legacy agenti koriste samo prva dva — dug, ne menja se ovde). Tombstone brisanja: `predmeti.
brisanje_zapoceto` (114), čitan kao u `shared/rag_acl.py`. „Danas" u Case Actions / Workspace = `date.today()`.

**ODLUKA.**
- Planer je deo agenta (`planiraj`), radnik samo upisuje: plan → upis → zastarevanje (Task 3). 0 poziva modela.
- HEARING_PREP (`services/agent_tasks/hearing_prep.py::planiraj`): posao SAMO ako je ročište `zakazano` u prozoru
  [danas, danas + `AUTONOMY_HEARING_WINDOW_DAYS`] (podrazumevano 1 = danas i sutra, opseg 0–7, neispravno = 1),
  predmet istog korisnika, nije završen, nije u brisanju, ima Genome (verzija ≥ 1). Bez razloga nema posla:
  `reason` = „Ročište sutra (11.10.2026. u 09:30, Osnovni sud u Beogradu) — priprema po analizi predmeta v3.";
  preskočeni se broje po razlogu.
- Ključ = `HEARING_PREP:{ročište}:{verzija ročišta = sha256(datum|vreme|sud|sudnica)}:g{Genome verzija}`; promena
  ročišta ili analize = nov posao, stari QUEUED/READY → SUPERSEDED (ne briše se).
- Poništavanje: za svaku pripremu u QUEUED/READY planer proverava da li njeno ročište još važi (otkazano, odloženo,
  održano, obrisano, pomereno van prozora, predmet zatvoren/u brisanju) → SUPERSEDED, izvršilac se ne poziva.
- Veza: `case_action_id` = otvorena Case Action `PRIPREMITI_PODNESAK` za isto ročište (dodatak, ne uslov).
- Budžet: ključ organizacije iz postojećeg `_resolve_orgs_batched` (kancelarija ili solo).
- Kolona tombstone-a nedostaje → ista bezbedna grana kao `rag_acl` (tombstone se bez nje ne može upisati); SVAKA
  druga greška čitanja propagira (planer pada vidljivo, nikad „nema posla").

**TESTOVI.** 25/25: kandidat sa razlogom, ključem, vezom na Case Action i budžetom; kancelarija kao budžet; 8
nepodobnih slučajeva (van prozora ×2, zatvoren/odbijen/arhiviran, u brisanju, bez Genome-a, ročište A uz predmet
B); odloženo/otkazano/održano; eksplicitan podesiv prozor; **100 aktivnih predmeta sa 2 ročišta → tačno 2 kandidata,
0 poziva modela**; promena ročišta → nov posao + SUPERSEDED; nova verzija Genome-a → nova priprema, ista → nijedna;
otkazano/odloženo/zatvoren/obrisano posle upisa → posao koji čeka se NE izvršava; ročište pomereno 30 dana → poništen;
kolona tombstone-a nedostaje; greška čitanja predmeta propagira; jednokratna greška (ne kolona) ne skida filter.

**MUTACIJE (11/11 ubijeno).** H1 bez statusa ročišta; H2 bez provere vlasnika; H3 bez filtera završenog; H4 legacy
lista bez `odbijen`; H5 bez tombstone-a; H6 bez Genome uslova (generička priprema); H7 ključ bez verzije ročišta; H8
ključ bez verzije Genome-a; H9 bez poništavanja; H10 fallback na svaku grešku (prvo PREŽIVELA — dodat test
jednokratne greške); H11 prozor bez gornje granice (prvo PREŽIVELA — dodat test pomerenog ročišta).

**OGRANIČENJE.** „Danas" je datum servera (`date.today()`, na Render-u UTC) — isto kao Case Actions i Workspace; oko
ponoći po beogradskom vremenu prozor kasni do 2 sata. Agent se registruje u Task 8 (kad dobije izvršioca).

**SLEDEĆA KAPIJA.** Task 8 — izvršilac pripreme ročišta.

---

## TASK 8 — IZVRŠILAC PRIPREME ZA ROČIŠTE

**EVIDENCIJA (PROVEN, Task 0).** Postojeći Hearing Command Center (`routers/hearing_cc.py`) NIJE bezbedan za
autonomni rad: kanonski kontekst je fail-soft (nastavlja bez njega), sistemski prompt sam navodi članove zakona (model
proizvodi autoritet bez provere izvora), vraća `hearing_score` 0–100, kredit se troši posle poziva.

**ODLUKA.** Ne pravi se drugi „hearing intelligence" motor i HCC se ne poziva. Izvršilac
(`services/agent_tasks/hearing_prep.py::izvrsi`) sastavlja pripremu iz POSTOJEĆEG kanonskog ugovora živog predmeta
(NS006 `ucitaj_zivi_predmet` + `sastavi_zivi_predmet`: poreklo i izvor svake stavke) i dodaje JEDAN uzak poziv modela.
- Kapije PRE modela, redom: ročište postoji za (ročište, predmet, korisnik) → i dalje `zakazano` i nije prošlo →
  nepromenjeno od planiranja (verzija u ključu) → predmet dostupan vlasniku (404 = konačno, 503 = prolazno) → aktivan i
  nije u brisanju → SVI izvori konteksta pročitani (inače prolazno, bez proizvoda) → verzija Genome-a ista →
  zakup i dalje naš (budžet je rezervisan pri zauzimanju).
- Proizvod (`schema hp-1`): ročište (iz baze, `SOURCE_FACT`), predmet, determinističke dimenzije spremnosti, ključne
  činjenice SAMO `SOURCE_FACT`/`HUMAN_CONFIRMED` sa dokumentom i stranom, aktivne protivrečnosti sa učesnicima,
  otvorene radnje, nedostajući dokazi. Naslov i sažetak su deterministički.
- AI deo: model dobija samo te stavke sa id-jevima (tekst = podatak, ne uputstvo); vraća pitanja i beleške; zadržava se
  samo stavka sa važećom referencom, bez citata propisa/odluke i bez predviđanja ishoda (ostale se broje u
  `odbaceno`); oznaka `AI_ANALYSIS` + napomena „nije utvrđena činjenica ni pravni izvor". `max_retries=0`: jedna
  rezervacija = jedan poziv. Pad modela → priprema iz baze se čuva (`DETERMINISTIC`), bez ponovnog poziva.
  Poziv ide kroz `case_context(predmet_id, module_name="autonomy.hearing_prep")` (postojeća AI proveniencija i
  zaštita prompta).
- Agent registrovan u JEDINI spisak modula; nema `run`, pa ne ulazi u dnevni cron.

**TESTOVI.** 15/15 nad realističnim predmetom (ročište sutra): jedan poziv; ročište tačno iz baze; reference svih
izvora postoje u bazi; prompt bez tuđeg predmeta; izmišljena referenca / citat (čl., Rev …/…) / predviđanje
(„verovatnoća uspeha") / stavka bez reference se odbacuju; sve odbačeno → bez AI dela; pad modela → priprema iz baze
bez ponovnog poziva; 5 konačnih kapija (otkazano, pomereno, zatvoren predmet, nova verzija Genome-a, ročište
obrisano), ročište A u predmetu B, predmet više nije vlasnikov → FAILED bez modela; nepročitan izvor / izgubljen
zakup → bez modela i bez proizvoda; nijedan spoljni efekat (upisi samo u tabele autonomnog rada i računovodstvo).
Ukupno NS007 + legacy agenti/cron: 130 passed.

**MUTACIJE (14/14 ubijeno).** X1 status ročišta; X2 promena ročišta; X3 ročište bez vezivanja za predmet/korisnika;
X4 zatvoren predmet; X5 degradiran kontekst prolazi (fail-soft kao HCC); X6 verzija Genome-a; X7 zakup pre modela;
X8 citati; X9 predviđanje; X10 nepoznate reference; X11 AI činjenice kao ključne; X12 pad modela = ponovni poziv; X13
AI_PREPARED bez AI dela; X14 404 kao prolazno (prvo PREŽIVELA — dodat test promenjenog vlasništva).

**OGRANIČENJE.** Model nije meren na kvalitet (zamenjen); filter citata je obrazac, ne potpuna provera — zato se
autoritet uopšte ne traži od modela. Podrazumevani model `gpt-4o-mini` (`AUTONOMY_HEARING_MODEL`).

**SLEDEĆA KAPIJA.** Task 9 — Precedents Radar.

---

## TASK 9–10 — PRECEDENTS RADAR → UTEMELJENA ANALIZA UTICAJA (PRECEDENT_IMPACT)

**MAPA (PROVEN, `services/agent_tasks/precedents_radar.py`).** Izvor: `retrieve_sudska_praksa` (Pinecone
`sudska_praksa`, Cohere rerank) + `process_praksa_chunks` (prag + dedup po broju odluke). Relevantnost: `gpt-4o-mini`
klasifikacija podupire/osporava/neutralno (neuspeh → tiho „neutralno"). Vlasništvo: `predmeti.eq(user_id)`.
Deduplikacija: `precedent:{predmet}:{broj}` u `agent_recommendations` (POSLE skupe pretrage i klasifikacije).
Identitet odluke: `decision_number` iz metapodataka; kad ga nema, `process_praksa_chunks` daje `_unk_{id}`.
Izlaz: SAMO preporuka. Legacy `run` NIJE menjan.

**NALAZ.** `routers/praksa._fetch_decision_chunks` (dohvat odluke po identitetu, koristi ga poređenje odluka) je za
NEDOSTUPAN Pinecone vraćao isto što i za NEPOSTOJEĆU odluku („nije pronađena"). Dodat opcioni `raise_on_error`
(isti obrazac kao `retrieve._direktan_fetch_clana`): nedostupno → `RetrievalUnavailable`; podrazumevano ponašanje
postojećih pozivalaca nepromenjeno (test). Nema druge implementacije dohvata.

**ODLUKA.** Isti agent (jedan modul, jedan registar) dobija `planiraj`/`izvrsi` za PRECEDENT_IMPACT.
- Planer (0 poziva modela): preporuka ovog agenta `pending`/`accepted`, ≤ 14 dana; predmet istog korisnika, aktivan,
  nije u brisanju, sa Genome-om; broj odluke ispravan (ne `_unk_`, sadrži broj i „/"); odnos podupire/osporava sa
  obrazloženjem; ODLUKA POSTOJI u korpusu i sud se poklapa. Korpus nedostupan → bez posla u ovom ciklusu (bez tvrdnje
  da odluka ne postoji). Izmišljena odluka → nikad. Ključ `PRECEDENT_IMPACT:{predmet}:{odluka}:g{Genome}`; već
  planiran ključ se ne proverava ponovo (ni Pinecone upit).
- Izvršilac (jedan poziv): preporuka i dalje važi i vlasnikova je → identitet odluke isti → predmet dostupan, aktivan,
  kontekst kompletan, ista verzija Genome-a → IZVOR PONOVO PROVEREN (nestao → FAILED; nedostupan → prolazno) →
  postoje sporna pitanja predmeta (inače FAILED — bez generičke analize) → zakup naš. Model dobija tekst odluke i
  sporna pitanja sa id-jevima. Prikazuje se: identitet odluke iz korpusa (`SOURCE_FACT`, `provereno`), zašto je
  relevantna (procena Radar-a, `AI_ANALYSIS`), uticaji SAMO uz DOSLOVAN izvod iz odluke (provereno poređenjem
  teksta), pitanja za pregled, „razmotriti argument" samo kad postoji potkrepljen uticaj. Odbacuje se: izmišljen
  izvod, nepoznata referenca, drugi propisi/odluke, procenti, „sud će…", „predmet je dobijen/izgubljen".
  Klasifikacija u prilog/protiv bez potkrepljenog uticaja → „nije utvrđeno". Pad modela → proizvod sa proverenim
  izvorom bez AI dela, bez ponovnog poziva.

**TESTOVI.** 25/25 (+ postojeći praksa testovi zeleni): proverena preporuka → 1 kandidat bez modela; 8 nepodobnih
(izmišljena odluka, sud se ne poklapa, odbačena, neutralno, bez obrazloženja, `_unk_`, broj bez broja, tuđ predmet);
zatvoren predmet; korpus nedostupan pa vraćen; **ista odluka dva dana zaredom → 1 posao, 1 poziv, 0 novih
Pinecone upita**; nova verzija Genome-a → nova analiza; fetch razlikuje nedostupno/nepostojeće, a podrazumevano
ponašanje ostaje; pun proizvod sa izvodom; 6 vrsta izmišljanja odbačeno; klasifikacija bez potkrepljenja; 5 kapija
posle planiranja (izvor nestao, korpus nedostupan, preporuka odbačena, predmet zatvoren, nova verzija); ponovljen
ciklus; pad modela; bez spornih pitanja nema generičke analize.

**MUTACIJE (15/15 ubijeno).** P1 bez provere izvora u planeru; P2 nedostupno = nepostojeće; P3 sud se ne poredi; P4
`_unk_` prihvaćen; P5 neutralno prihvaćeno; P6 bez vlasnika preporuke; P7 ključ bez Genome-a; P8 izvršilac bez ponovne
provere; P9 uticaj bez izvoda; P10 procenti/predviđanje; P11 klasifikacija bez potkrepljenja (prvo PREŽIVELA — dodat
test); P12 odbačena preporuka važi; P13 nedostupno = konačno; P14 generička analiza; P15 ponovna provera planiranog.

**OGRANIČENJE.** Provera izvoda je doslovna (posle normalizacije razmaka i velikih slova) — parafraza se ne prihvata.
Legacy radar i dalje troši model za sve aktivne predmete u dnevnom cronu (nepromenjeno, dug iz Task 0).

**SLEDEĆA KAPIJA.** Task 11 (opciono) — sažetak promene predmeta.

---

## TASK 11 — SAŽETAK PROMENE PREDMETA (OPCIONO) — NAMERNO PRESKOČENO

**ODLUKA.** Direktiva: „ako ne donosi dodatnu vrednost korisniku — PRESKOČI". NS006 Pregled već prikazuje tačno te
determinističke promene između verzija Genome-a („Šta se promenilo", `GET genome-v2/promene`), uz radnje i pažnju.
Isti sadržaj kao radni proizvod bi dupliralo Pregled i punilo red za pregled bez nove odluke za advokata. Vrsta
`CASE_CHANGE_BRIEF` ostaje dozvoljena u šemi (136) za budući slučaj sa stvarnom vrednošću; nijedan kod je ne pravi.

---

## TASK 12 — API PREGLEDA AUTONOMNOG RADA

**ODLUKA / RUTE (`routers/autonomy.py`).** `GET /api/autonomy/work-items` (status — podrazumevano
READY_FOR_REVIEW, matter_id, work_type, limit 1–100; lista bez sadržaja), `GET /api/autonomy/work-items/{id}` (pun
proizvod: sadržaj, izvori, razlog), `POST …/{id}/accept`, `POST …/{id}/reject` (opciono `{"razlog"}` ≤ 1000).
- Sve sa `get_current_user`, svi upiti `.eq("user_id", uid)`; tuđ, nepostojeći i neispravan id → bajt-identičan 404;
  naziv predmeta se čita samo iz vlasnikovih predmeta.
- Prihvati/odbaci = SAMO odluka o pregledu: uslovni prelaz `READY_FOR_REVIEW → ACCEPTED/REJECTED` sa `resolved_at`,
  `reviewed_by`, `review_note`. Ne šalje, ne podnosi, ne piše mejl, ne promoviše u memoriju znanja, ne izvršava i ne
  zatvara Case Action. Nije na pregledu (već rešeno, zastarelo, neuspelo) → 409.
- Mutacije dodate u NS005 trajnu idempotentnost (`shared/idempotency.ZASTICENE_RUTE`): isti `Idempotency-Key` → jedan
  prelaz i sačuvan odgovor; i bez ključa uslov u bazi daje jedan prelaz.

**TESTOVI.** 7/7 + NS005 idempotentnost zelena: lista samo svoje + filteri + 400 za neispravne + 401; detalj i
identičan 404 bez curenja; prihvatanje bez upisa u druge tabele, drugi put 409; odbijanje sa razlogom, predugačak
razlog 422; tuđ rad 404 i nepromenjen, zastareo 409; mrežno ponavljanje = 1 prelaz; oštećen red ne otkriva naziv
tuđeg predmeta.

**MUTACIJE (8/8 ubijeno).** V1 lista bez vlasnika; V2 detalj bez vlasnika; V3 prelaz bez uslova READY; V4 neispravan
id kao 400 (orakl); V5 prihvatanje zatvara Case Action; V6 nazivi bez vlasnika (prvo PREŽIVELA — dodat test oštećenog
reda); V7 lista nosi sadržaj; V8 ruta van idempotentnosti.

**SLEDEĆA KAPIJA.** Task 13 — kompatibilnost sa `agent_recommendations`.
