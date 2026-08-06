# Mission Report — Program Omega, Sprint 004: Unified Legal Workspace

**Datum**: 2026-08-06
**Program**: Omega (četvrti sprint)
**Tim**: Product Workflow Architect (lead), Data Ownership Engineer, Systems Integration Engineer,
Frontend Reality Auditor, Product Reality Reviewer (svih 5 uloga izvedeno direktno u ovoj sesiji).

---

## Zatvorenje misije

Misija je tražila JEDAN kanonski operativni centar rada — ne novu funkciju, ne novi dashboard, ne novu
AI mogućnost, već jedan odgovor na "šta advokat vidi kada otvori Vindex AI." Pre koda, FAZA 1
forenzički pregled (`docs/omega/WORKSPACE_SURFACE_REGISTRY.md`) je otkrio da je stvarno stanje veće
nego što je pretpostavljeno na početku: home page (`dash_load()`, `static/vindex.js:1206`) VEĆ
kombinuje **6 nezavisno izgrađenih površina** (Command Center, Morning Briefing, Case Commander, CIO
Daily, Notifications, Health Index) u jednom prikazu, svaka sa sopstvenim učitavanjem, sopstvenim
pragovima i — pronađeno je — **najmanje 5 nezavisnih skala prioriteta** i **3 odvojene tabele
alertova**. Sprint 003-ov deterministički `case_actions` — arhitektonski najispravnija površina —
imao je NULA frontend referenci.

## Otkriveno

1. **Home page je već pokušaj "jednog centra," samo kompozicijom, ne konsolidacijom** — 6 nezavisnih
   poziva, ne 1. Ovo NIJE zadatak "izgraditi nešto novo" — to je zadatak "od 6+ postojećih glasova,
   odabrati/spojiti u JEDAN," tačno kako misija kaže.
2. **2 nove površine pronađene, van Sprint 003-ovog originalnog registra**: CIO Daily
   (`routers/cio.py`, `cio_preporuka` — "JEDNA konkretna akcija — danas," konceptualno najbliža
   Action Engine-u od svih GPT površina) i Notification Engine (`routers/notifications.py`, sopstvena
   `notifications` tabela, treća nezavisna alert-tabela, 16-tipova taksonomija).
3. **`GET /api/zadaci/moji`** (lični unakrsni-predmet pregled zadataka) — potvrđeno nula frontend
   referenci, isti obrazac kao `case_actions` Worklist.
4. **Ispravka Sprint 003-ovog sopstvenog nalaza**: `proactive_alerts` NIJE write-only kako je
   pretpostavljeno — čita ga 4 modula, uključujući Morning Briefing.
5. **Stvaran, ranije nikad testiran bag pronađen u Sprint 003-ovom sopstvenom kodu**:
   `_consequence_refresh_case_actions` je pisao `closed_at`/`updated_at` kao string literal `"now()"`
   (sa zagradama) — PostgreSQL-ov `timestamptz` parser dokumentuje samo `'now'` (bez zagrada) kao
   specijalnu vrednost. Nijedan Sprint 003 test ovo nije uhvatio jer svi koriste mokovan Supabase klijent
   koji ne validira tipove. Ovaj sprint je prvi put kada nešto STVARNO filtrira po `closed_at`
   (Workspace-ov "Završeno nedavno" bucket) — što bi ovaj bag prvi put učinilo vidljivim.

## Popravljeno

1. **`routers/workspace.py`** (NOVO) — `GET /api/workspace`, kanonski agregacioni endpoint. Piše
   NIŠTA — čisto čitanje iz 3 već-postojeća, već-vlasnička izvora: `case_actions` (Sprint 003),
   `zadaci` (status='ceka'), `intake_jobs` (status='awaiting_review'). 6 bucket-a: Danas, Kritično,
   Predstojeće, Za pregled, Na čekanju, Završeno nedavno — svaki sourced na stvarnu, već-postojeću
   kolonu (vidi `docs/omega/CANONICAL_WORKSPACE_SPEC.md`).
2. **`services/case_evolution.py::_consequence_refresh_case_actions`** — `"now()"` string literal
   zamenjen stvarnim izračunatim ISO-8601 timestamp-om. Bez ovoga, Workspace-ov "Završeno nedavno"
   bucket ne bi radio pouzdano.
3. **Dokumentacione (bez promene ponašanja) ispravke** — `routers/case_commander.py`,
   `routers/cio.py`, `routers/morning_briefing.py`, `routers/zadaci.py::moji_zadaci`: svaki dobija
   docstring koji eksplicitno imenuje Workspace kao kanonski pogled, a sebe kao "postaje podmodul"
   (Case Commander-ova stara sopstvena tvrdnja "srce platforme" je sada činjenično netačna, ispravljena).
4. **`api.py`** — `workspace_router` registrovan.

Nijedna GPT komponenta nije menjana (ponašanje 4 live, naplativa modula — Command Center, Morning
Briefing, Case Commander, CIO — potpuno nepromenjeno). Nijedna nova tabela, nijedna nova migracija.

## Dokazano

**16 novih testova** kroz 2 fajla:

`tests/test_omega_sprint004_workspace.py` (10 testova) — bucket-ovanje, sortiranje, prevod
prioriteta, prazno stanje, isključenje low/informational akcija.

`tests/test_omega_sprint004_case_to_workspace_flow.py` (6 testova) — svih 6 misijom traženih
scenarija, korišćenjem JEDNOG generičkog in-memory fake-a deljenog između `_consequence_refresh_
case_actions` (write strana) i `get_workspace` (read strana) — dokazuje da je pisanje kroz STVARNU
produkcionu putanju odmah vidljivo kroz STVARNU produkcionu read putanju, bez ičega između:

| Scenario | Test | Rezultat |
|---|---|---|
| 1. Novi dokument | `test_new_document_finding_flows_to_workspace_with_no_manual_refresh` | ✅ Nalaz se pojavljuje bez ručnog osvežavanja |
| 2. Nova kontradikcija | `test_new_contradiction_produces_a_new_workspace_action` | ✅ Nova akcija odmah vidljiva |
| 3. Rok produžen | `test_deadline_extended_moves_action_from_critical_to_predstojece_in_workspace` | ✅ ISTA akcija, novi bucket, bez duplikata |
| 4. Akcija završena | `test_resolved_action_disappears_from_active_workspace_and_appears_in_completed` | ✅ Nestaje iz aktivnog rada, pojavljuje se u Završeno-nedavno sa STVARNIM timestamp-om |
| 5. Restart sistema | `test_restart_produces_identical_workspace_output` | ✅ Identičan izlaz, bez duplikata |
| 6. 500 dokumenata | `test_500_documents_one_case_workspace_shows_only_what_matters` | ✅ Samo 2 stvarna signala prikazana, ne šum |

**Regresija**: 0 — 124 postojeća testa (Sprint 001-003 + Delta certification + dashboard/zadaci) ponovo
pokrenuta, sve prolaze nepromenjeno. Puna test suita: **2.688 passed, 1 skipped, 0 failed** (bilo 2.672
na kraju Sprinta 3) — tačno +16 novih testova, nula regresija.

## Faza 6 — Forenzička sertifikacija

Pokušaj da se dokaže drugi izvor istine, po sopstvenom pravilu misije ("ako postoji, nije završeno"):

**Unutar deterministic, verifiable "operational action" domena** (šta se automatski otvara/zatvara kao
posledica stanja predmeta): **SERTIFIKOVANO.** Nijedan drugi modul ne piše u `case_actions`. Nijedan
drugi endpoint ne računa ekvivalentnu, proverljivu, sourced listu akcija. `GET /api/workspace` je jedini
agregator, i sam ne piše ništa. Dokazano testovima, ne samo arhitektonski implicirano.

**Na širem, "šta advokat vidi kada otvori platformu" nivou**: **NIJE sertifikovano — pošteno, ne
prećutno.** Command Center, Morning Briefing, Case Commander i CIO Daily i dalje nezavisno postoje i
nezavisno računaju sopstvenu verziju "šta je važno." Njihove sopstvene odgovornosti su formalno
demotovane (Responsibility Matrix, "postaje podmodul") i njihovi docstring-ovi više ne tvrde da su
kanonski — ali njihov KOD i dalje radi, nepromenjen, i frontend ih i dalje prikazuje na home page-u.
Drugi izvori istine i dalje postoje na frontendu. Ovo je imenovano (`OMEGA-012`), ne skriveno.

## Odloženo

1. **`OMEGA-010`** — 3 nezavisne alert/notifikacione tabele (`proactive_alerts`, `notifications`,
   `case_actions`) nikad pomirene.
2. **`OMEGA-011`** — najmanje 5 nezavisnih skala prioriteta platform-wide; samo 2 (case_actions/zadaci)
   prevedene za Workspace, ne sve.
3. **`OMEGA-012`** — **najvažniji preostali nalaz**: `/api/workspace` (i Sprint 003-ov Worklist pre
   njega) imaju nula frontend referenci. Arhitektonski tačan odgovor postoji i testiran je, ali advokat
   ga ne vidi dok home page ne bude ožičen da ga čita. Namerno NIJE pokušano ovaj sprint (rizik
   slepog diranja legacy `static/vindex.js` bez live-browser provere) — isti obrazac kao Smart Intake-
   ov frontend gap, koji je čekao 3 sesije pre eksplicitne autorizacije.
4. **`OMEGA-013`** — 9 drugih mesta u repou i dalje pišu `"now()"` string literal; samo Sprint 003-ovo
   sopstveno mesto popravljeno ovaj sprint.
5. **`ai_analiziraj_predmet` vs `case_actions` preklapanje** (deo `OMEGA-008`) — i dalje nedirnuto,
   isti razlog kao Sprint 003.

## Zaključak

Definition of Done, stavka po stavka: (1) postoji tačno jedan kanonski operativni pogled za advokata —
**delimično**: `/api/workspace` JESTE taj pogled, arhitektonski i test-dokazano, ali nije jedini koji
POSTOJI (4 druge površine i dalje rade, samo demotovane) ✅/⚠️; (2) svaki prikaz ima jasno definisanu
ulogu ili je uklonjen — **ispunjeno**: svih 12 površina ima firm odluku (Responsibility Matrix), nijedna
ostavljena nedefinisana ✅; (3) ne postoje paralelni izvori istine za dnevni rad — **NIJE u potpunosti
ispunjeno**, pošteno rečeno u Fazi 6 iznad, imenovano kao `OMEGA-012` ⚠️; (4) sve promene na predmetu
automatski završavaju u Workspace-u — **dokazano** testovima za svih 6 scenarija ✅; (5) advokat može
otvoriti platformu i odmah videti šta zahteva pažnju — **backend deo ispunjen, frontend deo nije**,
najveći preostali gap ⚠️.

Ovaj sprint nije lažno tvrdio potpunu pobedu. Otkrio je da je problem veći nego što je pretpostavljeno
(6 površina, ne 5; 3 tabele alertova, ne 1), doneo je čvrste odluke za svih 12 pronađenih površina,
izgradio i testirao kanonski backend sloj bez ijedne regresije, i imenovao — jasno, ne prećutno —
tačno šta nedostaje da bi advokat STVARNO video jedan operativni centar umesto šest. Sledeći, poslednji
korak nije arhitektonski — to je jedna eksplicitna odluka: da li i kada se home page ožičava da čita
`/api/workspace`.
