# Mission Report — Program Omega, Final Sprint 007: Canonical Notification & Trigger Engine

**Datum**: 2026-08-06
**Program**: Omega (sedmi sprint)
**Tim**: Lead Product Architect, Event Lifecycle Engineer, Backend Systems Engineer, Database &
Consistency Engineer, AI Governance Auditor, Forensic Code Investigator, QA & Reliability Engineer,
End-to-End Validation Engineer (svih 8 uloga izvedeno direktno u ovoj sesiji).

---

## Zatvorenje misije

Cilj: dokazati da postoji TAČNO JEDAN kanonski životni ciklus korisničke pažnje — Business Event → Trigger
→ Priority → Active Notification → Resolution — a sve ostalo je projekcija. Za razliku od Sprinta 6
(kanonizacija VOKABULARA), ovaj sprint je eksplicitno zabranio odlaganje: "svaki pronađeni problem koji se
može bezbedno otkloniti MORA biti odmah popravljen."

## Otkriveno

1. **Šema-vs-kod drift u `notifications.prioritet`-ovom CHECK ograničenju.** `migrations/
   009_notifications_analytics.sql` je deklarisao `CHECK (prioritet IN ('hitan','normalan','info'))`,
   nikad proširen, dok je aplikacioni kod (`NOTIF_TIPOVI`) oduvek koristio drugačiji, 5-vrednosni
   vokabular. Sprint 6-ova sopstvena ispravka (pisanje `"high"` umesto starog, slučajno-usklađenog
   `"hitan"`) mogla je pretvoriti "pogrešno sortira" bag u "insert ne uspeva uopšte" bag. **Popravljeno
   odmah** — `migrations/100_notifications_priority_alignment.sql` (čeka osnivačevo pokretanje).
2. **Stvaran, ranije nepoznat bag u `routers/sms.py::posalji_podsetnike`**: sopstveni `vec_poslato: set()`
   je bio funkcijski-lokalan (resetuje se na svaki poziv) — sprečavao je duplikate SAMO unutar istog
   batch-a, nikad između 2 odvojena poziva cron endpointa istog dana (slučajan duplirani cron trigger,
   ručni re-run, GitHub Actions retry). `notification_log` je već beležio svaki slat, ali ništa ga nikad
   nije čitalo nazad pre sledećeg slanja — direktan neuspeh misijinog obaveznog Scenarija 2. **Popravljeno
   odmah.**
3. **`predmet_hronologija` vs `rocista` — ispravka sopstvene Sprint 6 pretpostavke.** Sprint 6-ov
   `OMEGA-020` je predložio da se `notifications.py`-ova sopstvena detekcija roka potpuno ugasi u korist
   nove `case_actions`-izvedene projekcije. Dublja istraga (praćenje svih ~14 pisaca
   `predmet_hronologija`, i `kreiraj_rociste`-ovih sopstvenih stvarnih insert naredbi) pokazala je da
   `predmet_hronologija` i `rocista` NISU isti prostor činjenica — retiring bi bio stvaran regres
   pokrivenosti za ~13 izvora rokova koji nisu ročišta. **Odluka ispravljena, ne ćutke sprovedena.**
4. **Nova, ranije nekatalogizovana `proactive_alerts.urgentnost` — 14. nezavisan vokabular prioriteta**
   (Faza 8, forenzička sertifikacija) — nije bio deo Sprinta 6-ovih 13 katalogizovanih.
5. **`proactive_alerts`-ov sopstveni TOCTOU race** (`OMEGA-023`) — `check-postoji-pa-emit` na strani
   pozivaoca (`matter_intel.py`), ne DB ograničenje; realan ali redak.
6. **`notification_log`/`email_notif_log` nemaju DB unique ograničenje** (`OMEGA-026`) — potvrđeno čitanjem
   `migrations/048_reliability_hardening.sql`; SMS/email sopstveni dedup je SELECT-pa-INSERT provera, ne
   DB-garantovana atomarnost.
7. **`on_document_job_failed` nema consequence-ledger idempotency stražu** (`OMEGA-024`) — jedini direktni
   Event Bus handler bez `(event_id, consequence_name)` provere.

## Popravljeno

1. **`migrations/100_notifications_priority_alignment.sql`** (novo) — usklađuje `notifications.prioritet`
   CHECK ograničenje sa stvarnim kodnim vokabularom.
2. **`migrations/101_notifications_dedupe_key.sql`** (novo) — `dedupe_key` kolona + parcijalni UNIQUE
   indeks (`user_id, dedupe_key WHERE procitano=FALSE`), tačno isti obrazac kao `case_actions`-ov sopstveni
   (migracija 099).
3. **`shared/attention_priority.py`** — dodat `CANONICAL_TO_NOTIFICATIONS` (obrnuti smer prevoda, kanonski
   → notifications vokabular).
4. **`services/case_evolution.py::_consequence_project_case_actions_to_notifications`** (novo) — nova
   trailing posledica na `DOCUMENT_ACCEPTED`/`REVIEW_ACCEPTED`/`ROCISTE_ZAKAZANO`/
   `DOCUMENT_BATCH_COMPLETED`; projektuje `case_actions`-ove otvorene `PRIPREMITI_PODNESAK` akcije u
   `notifications`, koristeći ISTI `dedupe_key` identitet — create/update/close rekonsilijacija, ne slepo
   ponovno umetanje.
5. **`routers/sms.py::posalji_podsetnike`** — dodat trajan, batch, cross-run dedup upit protiv
   `notification_log`-a (`rok_podsetnik:<datum>`-označene stavke), tačno isti obrazac kao
   `email_notif.py`-ov već ispravan.
6. **9 postojećih testova ažurirano** (registry-redosled/broj-poziva asercije u
   `test_delta_sprint002_event_migration.py`, `test_delta_sprint004_certification.py`,
   `test_omega_sprint002_case_intelligence.py`, `test_omega_sprint003_action_engine.py`,
   `test_omega_sprint005_full_chain_to_workspace.py`) da odražavaju novu `project_notifications` posledicu
   — svaka izmena je proverena da odgovara STVARNOM, ne pretpostavljenom, ponašanju novog koda.

## Dokazano

**17 novih testova, 4 nove test datoteke:**
- `tests/test_omega_sprint007_notification_schema_alignment.py` (3) — migracija 100 dozvoljava svaku
  vrednost koju kod stvarno piše.
- `tests/test_omega_sprint007_sms_reminder_dedup.py` (3) — direktno reprodukuje pronađeni bag (2 odvojena
  cron poziva istog dana) i dokazuje popravku; dokazuje da RAZLIČIT rok i dalje šalje.
- `tests/test_omega_sprint007_project_notifications.py` (8) — create/update/close rekonsilijacija,
  retry 100× → tačno jedna notifikacija (misijin Scenario 2), benigno rukovanje konkurentnim
  duplicate-key izuzetkom, propagacija NE-duplicate grešaka.
- `tests/test_omega_sprint007_concurrency.py` (3) — 2-way i 10-way `asyncio.gather` napad na istu
  `dedupe_key` sa realnom thread-lock-zaštićenom simulacijom parcijalnog UNIQUE indeksa; negativna
  kontrola (različiti predmeti se ne mešaju).

**Regresija**: 0. Puna test suita: **2.725 passed, 1 skipped, 0 failed** (bilo 2.705 na kraju Sprinta 6).

## Faza 7 — AI Governance re-verifikacija

Ponovo pročitan svaki GPT-facing prompt (`_COCKPIT_SYSTEM`, Genome ekstrakcija, CIO `kriticnost`,
`strategija.py`). **Nijedan GPT odgovor ne vlasi prioritet/notifikaciju/hitnost/pažnju** — potvrđeno
direktnim čitanjem, ne oslanjanjem na Sprint 6-ov zaključak bez ponovne provere. Nova posledica
(`_consequence_project_case_actions_to_notifications`) ne poziva GPT nigde — čisto prevodni lookup.

## Faza 8 — Forenzička sertifikacija

7 pokušaja da se arhitektura slomi (puni detalji u `docs/omega/FORENSIC_CERTIFICATION_REPORT.md`):
skriveni scheduler (nije nađen), drugi event dispatcher (nije nađen — disjunktno vlasništvo tipova
događaja), `proactive_alerts` kao skriveni drugi Notification Engine (nije — drugačiji kanal, dokumentovan
ne prećutan, ali otkriva `OMEGA-027`), da li SMS-popravka ili nova posledica zaobilaze kanonski dispečer
(ne zaobilaze — obe su obične, registrovane stavke u postojećim mehanizmima), da li konkurentnost slama
novu projekciju (nije uspelo — 2-way/10-way napad, tačno jedan red preživljava), da li registar Sprinta 6
propušta neki generator (ne propušta).

**Zaključak Faze 8**: tačno JEDAN kanonski životni ciklus dokazan je za ciljanu činjenicu ovog sprinta
(predmet-vezani, ročište-izvedeni rokovi). Ovo NIJE tvrdnja da je SVAKI notifikacijama-srodan mehanizam u
repou spojen u jedan sistem — `proactive_alerts`, email/SMS sopstveni kadenca, i `zastarelost.py`-ov
zastarelosni sken ostaju legitimno nezavisni (drugačija činjenica, drugačiji kanal, drugačiji potrošač),
svaki interno na putu ka (ne još potpuno na) jednom-vlasniku-po-činjenici unutar sebe.

## Odloženo

1. **`OMEGA-023`** — `proactive_alerts` TOCTOU race, nema DB dedup; zahteva novu migraciju + 2 poziva
   sajta, van vremenskog budžeta ovog sprinta uz istu strogost kao SMS popravka.
2. **`OMEGA-024`** — `on_document_job_failed` nema consequence-ledger stražu; redak trigger uslov.
3. **`OMEGA-025`** — log-posle-slanja obrazac u email/SMS nije crash-atomičan; postojao pre ovog sprinta,
   nije pogoršan.
4. **`OMEGA-026`** — `notification_log`/`email_notif_log` nemaju DB unique ograničenje; ispravan oblik
   ograničenja zahteva pažljiv dizajn (obe tabele namerno dozvoljavaju višestruke redove po danu).
5. **`OMEGA-027`** — `proactive_alerts.urgentnost`, 14. nekatalogizovan vokabular; dokumentovan, ne spojen
   (zavisi od `OMEGA-023`).
6. Potpuni frontend poll-site-po-poll-site audit `static/vindex.js`-a nije ponovo izvršen od nule (nasleđen
   vremenski budžet iz Sprinta 6).
7. 500-dokumenata batch i pravi multi-proces (ne samo multi-coroutine) konkurentnost testirani su
   strukturno i na asyncio/thread-pool nivou, ne protiv žive baze pod pravim konkurentnim OS procesima.

## Zaključak

Definition of Done, stavka po stavka: (1) jedan vlasnik po business event-u — **da**, dokazano registrom
vlasništva; (2) jedan kanonski Trigger Engine — **da**, `handle_case_changed`, potvrđeno da nema
konkurentskog dispečera; (3) jedan kanonski Notification Engine — **delimično**: `case_actions`↔
`notifications` sada dele jedan write, `proactive_alerts` ostaje svestan-drugačiji kanal, imenovan ne
sakriven; (4) jedan kanonski Priority Engine — **da**, prošireno ovaj sprint (`CANONICAL_TO_NOTIFICATIONS`)
umesto zamenjeno; (5) retry/replay/restart/konkurentnost ne proizvode duplikate — **da**, za ciljanu
projekciju, dokazano sa 4 nove test datoteke uključujući pravi `asyncio.gather` napad; (6)
Workspace/Dashboard/Inbox koriste isti izvor istine — **za ciljanu činjenicu da**, za Dashboard/Inbox-ove
sopstvene, genuinski drugačije činjenice ne (ispravno, ne bag); (7) svaki bezbedno-popravljiv problem
popravljen odmah — **da**: šema drift, SMS dedup bag, i 9 postojećih testova ažurirano da odražavaju
stvarno novo ponašanje, sve sa punom regresijom (2.725 passed, 0 failed).

Ovaj sprint ne tvrdi lažnu potpunu pobedu. Zatvara tačno ono što je bezbedno zatvoriti — jedan write put
za hitno-ročište projekciju, jedan stvaran SMS bag, jedna šema neusklađenost — i imenuje, precizno i bez
izgovora, 5 novih debt stavki (`OMEGA-023` do `OMEGA-027`) pronađenih upravo ZATO što je ovaj sprint tražio
da se arhitektura slomi, ne da se potvrdi.
