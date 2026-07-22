# Vindex AI — Operational Gap Register

**2026-07-19.** Osmi i poslednji planski dokument u ovoj seriji. Ovo
NIJE analiza — ovo je operativna radna lista. Founderova formulacija:
posle ovog dokumenta, rad se prati kao "zatvaram G-003", ne "radim D6".

**STATUS PROMENJEN (2026-07-19, isti dan):** stari "Beta Freeze" (nema
koda dok ne stigne pilot feedback) je ZAMENJEN sa **Faza A — Internal
Integration Sprint**. Cilj: zatvoriti pilot-kritične G-stavke, dokazati
kroz Verified Coverage, TEK ONDA pozvati beta korisnike — ne čekati
pasivno. Kod SME da se menja sada, ali isključivo za zatvaranje G-stavki
iz ovog registra — bez novih funkcija, bez UX promena, bez novih AI
modula (founderova eksplicitna ograda za Fazu A).

**Pilot-kritični filter (prvi korak Faze A, urađen 2026-07-19):**
stvaran pilot scenario (`TRUST_LAYER_BETA_FREEZE_2026-07-19.md`, Deo 4
— otvori predmet→upload→AI obrada→Genome→advokat ocenjuje) mapira se
**isključivo na CONTRACT 01 (Upload tužbe)**. Nijedan G-004 do G-025
(Tok 2/3/4) nije na kritičnoj putanji ZA OVAJ KONKRETAN pilot scenario
— vredni su, ali ne blokiraju start. G-001/G-002/G-003 (Tok 1) su
takođe NE-blokirajući za scenario (Tok 1 kritični koraci su već ✅ u
kodu) — pravi nedostatak nije bio kod, nego DOKAZ. **Prva akcija Faze A
zato nije bila zatvaranje G-001, nego pisanje i pokretanje stvarnog E2E
testa za CONTRACT 01** (`scripts/contract01_e2e_verify.py`) — rezultat:
sva 3 kritična koraka PROŠLA (klasifikacija, Evidence Vault, Genome
regeneracija sa ispravno funkcionalnim Verification Layer-om), potvrđeno
protiv produkcijske baze. Detalji u `VINDEX_OPERATING_SYSTEM_
CONTRACTS.md` CONTRACT 01 sekciji.

**Kolone:** ID | Tok | Prekid | Uzrok | Rešenje (D-broj u
`VINDEX_2_1_ARCHITECTURE_ROADMAP.md`) | Status.

Svaki red je izveden iz `VINDEX_OPERATING_SYSTEM_CONTRACTS.md` Deo B —
dubok dokaz (file:line) za svaki red je tamo, ne ponovljen ovde.

| ID | Tok | Prekid | Uzrok | Rešenje | Status |
|---|---|---|---|---|---|
| G-001 | Upload tužbe | `PredmetKreiran` se ne emituje | Event nikad pozvan iz standardnog "+ Novi predmet" puta (`api.py::kreiraj_predmet`, `POST /api/predmeti` — ne `routers/intake.py` kako je prvobitno navedeno; ispravljeno posle provere `static/vindex.js::pred_kreiraj()`) | D3 | **Closed + Verified** (commit `8f54f54`/`5bcc226`, produkcijski dokaz 2026-07-21, `CONTRACT_01_PRODUCTION_VERIFICATION.md`) |
| G-002 | Upload tužbe | `run_case_pipeline()` se ne pokreće za standardni put | Zavisi od G-001 | D9 | **Closed + Verified** (posledica G-001 fix-a — `on_predmet_kreiran` handler, već registrovan u `services/event_bus.py`, sada stvarno prima event i poziva `run_case_pipeline()`) |
| G-003 | Upload tužbe | Audit ne beleži kreiranje predmeta/upload dokumenta | `predmet_create`/`dokument_upload` nikad pozvani | D22 v1 | **Closed + Verified — samo predmet/document creation audit coverage, NE kompletan audit sistem** (commit `b84fd4b`/`bb4388b`, produkcijski dokaz 2026-07-21, `CONTRACT_01_PRODUCTION_VERIFICATION.md` Addendum). Tamper-evidence provera, retention politika, user attribution kroz SVE tokove (~19-21 od 24 `AUDITABLE_ACTIONS` i dalje nikad pozvano), export, compliance format — sve i dalje van obima, nije D22 v1 tvrdio da ih rešava |
| G-004 | Upload presude | Klasifikator ne razlikuje tužbu/žalbu/odgovor na tužbu | Sve u kategoriji `podnesak` | D1 | Open |
| G-005 | Upload presude | Klasifikator ne razlikuje presudu/rešenje | Sve u kategoriji `sudska_odluka` | D1 | Open |
| G-006 | Upload presude | Datum dostave/prijema se ne hvata pouzdano | Nema polje/logiku za ekstrakciju tog datuma specifično | D2 | Open |
| G-007 | Upload presude | Ne postoji event za "dokument klasifikovan kao procesni akt" | Nedostaje čak i definicija u enum-u | D4 | Open |
| G-008 | Upload presude | Klasifikacija se ne mapira na ZPP tip roka | Nema determinstičku vezu tip→`rokovi_lanac.py` ključ | D6 | Blocked na G-004/G-005/G-006 |
| G-009 | Upload presude | Nema koraka gde advokat potvrđuje predloženi rok | UI ne postoji | D6 | Blocked na G-008 |
| G-010 | Upload presude | Deadline Guardian ne registruje rok po predmetu | Nema UI/trigering | D8 | Open |
| G-011 | Upload presude | Nema jedinstven izvor istine za rok podatak | 3 paralelne tabele (`predmet_hronologija`/`rokovi`/`zadaci.rok_datum`) | D21 | **Blocker za G-008/G-009/G-010** |
| G-012 | Upload presude | Task se ne kreira iz predloženog roka | Nema veze između rok-lanca i `zadaci` tabele | D12 | Blocked na G-009 |
| G-013 | Upload presude | Notifikacija za rok se ne raspoređuje pouzdano | Cron isporuka neizvesna (`Procfile` samo `web`) | D10 | Open, **kandidat za hitan izuzetak** |
| G-014 | Upload presude | Audit ne beleži lanac odluka (predlog→potvrda→rok) | Nijedna akcija u ovom lancu nije u `AUDITABLE_ACTIONS` | D22 | Open |
| G-015 | Dodavanje ročišta | `RociscteZakazano` se ne emituje | Event nikad pozvan | D25 | Open |
| G-016 | Dodavanje ročišta | Ročište nije sinhronizovano sa jedinstvenim rok-izvorom | Isti uzrok kao G-011 | D21 | Blocked na D21 odluci |
| G-017 | Dodavanje ročišta | Guardian ne registruje datum ročišta | Isti uzrok kao G-010 | D8 | Open |
| G-018 | Dodavanje ročišta | Podsetnik pre ročišta se ne raspoređuje | Isti uzrok kao G-013 | D10 | Open |
| G-019 | Dodavanje ročišta | Audit za unos ročišta — **neprovereno**, ne potvrđeno kao gap | `rociste_add` prisustvo u `AUDITABLE_ACTIONS` nije provereno | D22 | **Needs verification pre Open/Closed** |
| G-020 | Zatvaranje predmeta | Ne postoji event za zatvaranje/pravosnažnost predmeta | Nedostaje čak i definicija | D24 | Open |
| G-021 | Zatvaranje predmeta | Style profile update trigering — **neprovereno** | Da li `_update_style_profile` reaguje na zatvaranje ili samo na 10+ korekcija nezavisno | — (istraživanje, ne D-broj) | **Needs verification** |
| G-022 | Zatvaranje predmeta | Firm-nivo statistika ažuriranje — **neprovereno** | Nije praćeno u ovoj sesiji | — (istraživanje) | **Needs verification** |
| G-023 | Zatvaranje predmeta | Audit za `predmet_close` — **neprovereno** | Prisustvo u `AUDITABLE_ACTIONS` nije potvrđeno | D22 | **Needs verification** |
| G-024 | Arhitektonski (svi tokovi) | Predloženi 13-stanja lifecycle nije usklađen sa Kanban statusom | Dva nezavisna "status predmeta" koncepta ako se lifecycle uvede bez odluke | D23 | **Blocker za bilo koju lifecycle implementaciju** |
| G-025 | Arhitektonski | "Žalba" i "Pravosnažno" nemaju definisan tok/ugovor | Van obima 4 postojeća CONTRACT-a | D24 | Open, čeka D23 |
| G-026 | Arhitektonski (frontend) | `#t-credits-row` (credit panel vidljivost) povremeno se prikazuje na tabovima gde ne treba (npr. Rokovi), otkriveno ručnim prolazom CONTRACT 01 | Tri nezavisna pisca istog `style.display` — `updateAuthUI()` (bezuslovno, bez provere `activeTab`), `setTab()`, `aiwsSetMode()`; `updateAuthUI()` se poziva iz async Supabase `onAuthStateChange` callback-a koji može razrešiti posle navigacije i prepisati `setTab()`-ovo sakrivanje. Isti obrazac kao D21/D23 (kršenje "jedan poslovni koncept = jedan izvor istine"), sada na frontend UI-state, ne na podacima. | D20.1 (princip; nema poseban D-broj) | **Status: Completed** (2026-07-22, commit `9acc4fc`). **Verification: Playwright behavioral test — identičan scenario pokrenut i protiv stare i nove verzije funkcija (3/5 FAILED na staroj, potvrđujući tačnu reprodukciju prijavljenog buga; 9/9 PASSED na novoj).** **Production: Not required.** **Reason: UI state architecture correction (ne "presentation consolidation" kao Top10 #3 — ovo je popravka ownership-a nad deljenim state-om, ne samo vizuelna izmena), nema backend/auth/billing logike.** Usput otkriven i popravljen povezan nalaz: `credRow.dataset.wasVisible` se čita na 2 mesta, nigde se ne postavlja (mrtav uslov) — uklonjen kao deo konsolidacije, ne kao odvojena izmena. **Menja ponašanje** (ne samo prikaz): credits red se sada STVARNO pokazuje na `s`/`aiws` tabovima, ne samo prestaje da se pogrešno pokazuje na drugim tabovima — eksplicitno prijavljeno, ne prećutano. |
| G-027 | Arhitektonski (poslovna logika, Pregled predmeta) | Matter Intelligence Bar i Cockpit su nezavisno računali "procesni rizik" za isti predmet | Ekstrahovano u `services/risk_engine.py::calculate_procesni_rizik` — jedini deterministički izvor istine. `routers/matter_intel.py` ga poziva (ponašanje nepromenjeno). `api.py` `/workspace` endpoint ga poziva PRE GPT poziva; Cockpit-ov prompt (`_COCKPIT_SYSTEM`) više ne pita GPT za nivo — dobija ga kao dat kontekst i vraća samo `rizik_objasnjenje` (faktori_plus/minus). | D20.1 + **AR-01 (novo, formalizovano ovom stavkom)** | **CLOSED (2026-07-20)** |
| G-028 | Bug, otkriven usput tokom G-027 popravke | Matter Intel/risk engine `nedostajuci_dokazi` uvek vraća pun spisak očekivanih dokumenata bez obzira na stvarne upload-ove | `predmet_dokumenti` upiti (i u starom `matter_intel.py` i u novom `workspace` endpoint-u) selektuju `naziv_fajla,status` — NIKAD `tip_dokaza` — pa je `postojeci_tipovi` uvek prazan skup. Objašnjava zašto je u G-027 uzorku `nedostajuci_count` bio konstantno 2 za svih 16 predmeta bez obzira na broj/tip dokumenata. | — (nema D-broj, čist bug) | Open, **needs verification da li je select namerno ovakav ili previd**, ne blokira ništa. **Dodatan nalaz (2026-07-22, Core Consolidation brutal-audit prolaz):** novi `services/case_pipeline.py::_step_risk_snapshot` (Sec 1.1) ISPRAVNO selektuje `tip_dokaza` — pisan nezavisno, bez namere da se G-028 dira. Ovo znači da ISTA `calculate_procesni_rizik()` funkcija sada daje RAZLIČIT `nedostajuci_dokazi` rezultat u zavisnosti od pozivaoca (case_pipeline ispravno, matter_intel/workspace i dalje pogrešno) — jači dokaz da je G-028 pravi bug, ne namerno ponašanje. I dalje nije popravljeno (van obima Core Consolidation Faze 1, koja se bavi vlasništvom algoritma, ne postojećim select-bug-ovima unutar njega) — flagovano ovde da se ne izgubi. |
| G-029 | AR-01 (novo pravilo) povreda, otkriven usput tokom G-027 popravke | Cockpit `sledeca_akcija.prioritet` ("hitan/normalan/odložen") i dalje GPT sam bira, isti obrazac kao rizik pre popravke | `api.py` `_COCKPIT_SYSTEM` i dalje traži od GPT-a da vrati `prioritet` kao slobodan izbor, bez determinističkog izvora ispod | AR-01 | **Closed (2026-07-22, commit `96a44ac`, deo Core Consolidation Sec 1.2).** Rešeno tako što je ceo `sledeca_akcija`/`prioritet` koncept UKLONJEN, ne popravljen — zamenjen determinističkim `otkriveni_problemi` (`services.risk_engine.identify_case_problems`). GPT u Cockpit-u ostaje samo za `ai_sazetak`/`rizik_objasnjenje`, nikad ne bira prioritet. Nije bilo potrebe za empirijskom validacijom kao G-027 pošto rešenje nije "preuzmi drugi izvor" nego "obriši GPT-odluku, prikaži determinističku analizu". |
| G-030 | Arhitektonski (poslovna logika, "sledeći korak") | ČETIRI nezavisna sistema predlažu "sledeću akciju" za isti predmet — Cockpit `sledeca_akcija`, Matter Intel `sledeca_radnja`, Case Ready Score `copilot_preporuka`, `workflow.py::sledeci_korak` — nijedan ne zna za ostale (poznato od `VINDEX_INTEGRATION_MASTER_PLAN.md` nalaza #7, sada prvi put ocenjeno kao P0 u `VINDEX_AI_UX_SIMPLIFICATION_STRATEGY.md`) | Isti obrazac kao G-027 pre popravke — organski rast, svaki sistem dodat u drugoj fazi razvoja, nikad konsolidovan | AR-01 + D20.1 | **Closed (2026-07-22, commit `96a44ac`, Core Consolidation Sec 1.2).** Founder je doneo arhitektonsku odluku direktno (princip "1 koncept = 1 vlasnik = 1 algoritam = 1 istina", `docs/architecture/VINDEX_CORE_CONSOLIDATION.md`), zaobilazeći G030_NEXT_ACTION_DECISION_MODEL.md-ov 4-kandidata okvir — odluka NIJE "koji od tri postojeća pobeđuje" (Opcija A/B/C) nego Opcija D primenjena ("nova orkestracija koristeći postojeće signale") ALI još radikalnije: sam koncept "sledeća akcija/predlog" je ukinut, zamenjen sa dva determinička izlaza (Administrativni status = Case Ready Score, Otkriveni problemi = `identify_case_problems`, zasnovano na Matter Intel-ovom već-determinističkom `_compute_next_action`, sada obrisanom i zamenjenom deljenom funkcijom). Cockpit i Case Ready Score-ova stara GPT polja obrisana. `workflow.py::sledeci_korak` ostaje netaknut (potvrđeno drugačiji koncept, van sukoba). Empirijska pred-validacija (20-predmeta A/B/C tabela iz protokola ispod) NIJE sprovedena — founder je svesno preskočio taj korak jer odluka nije birala pobednika među postojećim sistemima, nego ih sve zamenila novim, jednostavnijim konceptom; ista vrsta odluke kao "obriši i zameni" ne zahteva empirijsko poređenje triju stvari koje sve nestaju. |
| G-031 | Case Genome sinhronizacija (izvučeno iz `CASE_GENOME_FULL_INTEGRATION_COMPLETION` masterprompta, 2026-07-22) | `health_index.py:272` čita `genome.get("ishod")`/`genome.get("preporucena_akcija")` — nijedno polje ne postoji u Genome šemi | Uvek vraća `""` — tiho lomi signal "ishod zatvorenog predmeta" u Health Index-u | D26 | **Closed** (commit `aae1c54`/`ac667a9`) — **Verification: Unit verified. Production E2E: Not required (razlog: deterministički read-path, nema event/pipeline/audit/AI stranu — unit test daje istu informacionu vrednost kao produkcijski run, po founderovoj eksplicitnoj oceni 2026-07-22).** Stvaran izvor istine je `predmet_hronologija` (ne Genome), isti parser kao `routers/predmeti_close.py::get_predmet_ishod`; sortiranje po `created_at`, ne po korisnički-zadatom `datum`, posle review nalaza o mogućem reopen→reclose. 3 unit testa, 69/69 ukupno prolazi. |
| G-032 | Case Genome sinhronizacija (isti masterprompt) | `verify_genome()`-ov `require_review` ishod se računa i upisuje u audit metadata, ali ništa ne reaguje na njega (nema alert) | "Half-wired" sistem — validator → audit → ništa | D27 | **Closed** (commit `9ed7679`) — **Verification: Unit + Integration verified (povezuje dva postojeća podsistema — validator i `proactive_alerts` — ponašanje kroz više stanja: False→True/True→True/True→False/False→True potvrđeno testovima). Production E2E: Not required (deterministička integracija postojećeg izlaza u postojeću infrastrukturu, nema novih AI poziva, nema promene event lanca, nema novih spoljašnjih side-effect-ova).** Alert koristi STVARNE `hard_flags` razloge (do 5, ne izmišljen "confidence %" — eksplicitno test-om zabranjen regres). 4 unit testa, 1666/1666 ukupno prolazi. |
| G-033 | Case Genome sinhronizacija (isti masterprompt) | Strategy Simulator (`routers/strategy_simulator.py`) nema nijedan `log_action`/`audit_immutable` poziv, niti čuva koji `genome_verzija` je korišćen na `simulator_partije` redu | Za 6 meseci niko ne može odgovoriti "koji Genome je informisao ovu strategiju" | D28 | **Closed** (commit `c592464`) — **Verification: Unit + Integration verified (5 testova, `tests/test_strategy_simulator_audit.py` — snapshot vs. current-version race condition izbegnuta, audit samo na uspeh, response oblik nepromenjen, `sledeci_potez` namerno bez fabrikovane verzije). Production E2E: Not required. Reason: Passive observability enhancement. No business logic changes. Snapshot traceability verified.** `genome_verzija` NIJE nova kolona (izbegnuta migracija) — čuva se u postojećem `istorija` JSONB polju (`simulator_partije`) i audit metadata, ne zahteva šema promenu. 1671/1671 ukupno prolazi. |
| G-035 | Backlog (predloženo tokom G-033 review-a, 2026-07-22 — NE za implementaciju sada) | Ne postoji jedinstven pregled koje funkcije čitaju Genome i čuvaju `genome_version` za sledljivost, naspram onih koje ne čuvaju | Za 6 meseci bi se isto pitanje (G-031/G-032/G-033 tip) ručno ponovo istraživalo po modulu | — (backlog, bez D-broja dok se ne odobri) | **Backlog — "Traceability Coverage Matrix": tabela Feature × Reads Genome × Persists genome_version, po uzoru na G-030 Next Action matricu. Ne implementirati dok founder eksplicitno ne zatraži.** |
| G-034 | Case Genome sinhronizacija (isti masterprompt) | `services/risk_engine.py::calculate_procesni_rizik` ima nula referenci na Genome, iako Genome nezavisno računa sopstvene rizik-signale (`najslabija_tacka`, `snaga_predmeta_procent`) — isti oblik kao G-027 | Moguć "dva sistema, jedan koncept" duplikat — NIJE dokazano | D29 | **Resolved — Evidence insufficient. Decision: No implementation.** (`scripts/g034_risk_validation.py`, 2026-07-22, 19 predmeta/17 uporedivo). Zaključak C od 3 dozvoljena (A=isti koncept / B=povezane-ali-razlicite dimenzije / C=nedovoljno dokaza): 0 "Nizak" slucajeva u uzorku (hipoteza netestabilna na 2/3 opsega), "Visok" grupa verovatno sadrzi duplikate iz sintetickih test predmeta (6/13 identicnih vrednosti 65%/89), i 2 kontradiktorna outlier-a (`e0a54af1` 80%/Visok, `7faf7d8e` 75%/Visok). **Vredan arhitektonski signal (ne dokaz, ali smer):** 2 "Visok" predmeta nemaju NIKAKAV Genome podatak, sto znaci da `risk_engine` dolazi do "Visok" bez Genome ulaza uopste — podrzava Hipotezu A (risk_engine meri proceduralni rizik: rokovi/nedostajuci dokumenti/faza postupka; Genome meri snagu dokaza/argumentacije — RAZLICITI koncepti) naspram Hipoteze B (risk_engine bi trebalo da koristi Genome ali ne koristi). Ne zatvarati kao implementacioni zadatak dok se ne pojavi 100+ realnih (ne sintetickih) predmeta za ponovnu proveru. |

**Napomena uz G-030 (radni naziv "Next Action Source of Truth Audit",
2026-07-20, founderova tačna metodologija — zapisana ovde da se ne
izgubi/rekonstruiše u budućoj sesiji):**

Pre bilo kakve arhitektonske odluke (koji sistem postaje "master"),
napraviti tabelu za svaki od 4 sistema:

| Sistem | Šta predlaže | Na osnovu čega | Koliko često | Testirano? |
|---|---|---|---|---|
| Cockpit (`api.py` `_fetch_cockpit_ai`, `sledeca_akcija`) | | | | |
| Matter Intelligence (`matter_intel.py`, `_compute_next_action`, `sledeca_radnja`) | | | | |
| Case Ready Score (`services/case_pipeline.py`, `copilot_preporuka`) | | | | |
| `workflow.py::sledeci_korak` | | | | |

Zatim uzeti ~20 predmeta (mešano, ne slučajno): jednostavan predmet,
komplikovan predmet, nedostatak dokaza, blizu roka, završen predmet —
i za svaki proveriti da li 4 sistema **(A) govore isto, (B) dopunjuju
se, (C) sukobljavaju se**. Tek POSLE ove tabele razmatrati arhitekturu.

**Founderova hipoteza (EKSPLICITNO označena kao hipoteza, ne odluka):**
`workflow.py` (deterministički, operativni događaji — dokument
uploadovan → analiza završena → nedostaje dokaz → predlog) postaje
kostur ("Action Engine"), GPT sloj (Cockpit) objašnjava ZAŠTO, ne ŠTA.
Isti oblik rešenja kao G-027 (`Risk Engine → jedan rizik → AI
objašnjenje`), sada za "sledeću akciju". **Ne birati ovu hipotezu kao
odluku pre tabele/20-predmeta provere — ista greška koja je izbegnuta
pre G-027 ne sme se sada napraviti ovde.**

**Redosled rada, founderov korigovan roadmap (2026-07-20):**
1. CONTRACT 01 ručni prolaz (aktivan, nezavršen).
2. **Sprint 2A — Decision Architecture (G-030 audit → izbor izvora
   istine → uklanjanje paralelnih sistema). Ne UI.**
3. Sprint 2B — UX Simplification (Dashboard/Sidebar/Pregled/AI modovi,
   iz `VINDEX_AI_UX_SIMPLIFICATION_STRATEGY.md`).

Razlog za ovaj redosled, founderov citat: "Nema smisla dizajnirati
savršen ekran ako iza njega postoje četiri različita 'mozga'."
`VINDEX_AI_UX_SIMPLIFICATION_STRATEGY.md` Roadmap sekcija (Sprint 3)
je ZASTARELA u delu koji tretira "Sledeća akcija" konsolidaciju kao UI
zahvat posle Dashboard-a — G-030 mora ići PRE, ne posle, kao Sprint 2A.

**Napomena uz G-026:** `credRow.dataset.wasVisible` se čita na 2 mesta
(`static/vindex.js:2178`, `:2251`) ali se **nigde ne postavlja** — mrtav
uslov, znak nedovršenog refaktorisanja ove vidljivost-logike. Forenzika
je namerno zaustavljena na ovom jednom slučaju (founderov zahtev — dalja
istraga je nov posao, ne nastavak trenutnog). Ako se u budućoj sesiji
otvori "frontend state ownership" tema, prva sumnja treba biti da ovaj
obrazac (više funkcija piše isti DOM-vidljivost bez jednog vlasnika)
postoji i na drugim deljenim elementima van tab-kontejnera — nije
provereno, samo označeno kao verovatno.

**Empirijska validacija G-027 (2026-07-20)** — pre bilo kakve
implementacije, pokrenut je `scripts/g027_risk_validation.py`: real API
pozivi (in-process ASGI, isti harness obrazac kao CONTRACT01 E2E test)
na GET `/api/matter-intel/predmeti/{id}` i GET `/api/predmeti/{id}/workspace`
za svih 16 predmeta na founder nalogu (14 iz [KALIBRACIJA] batch-a
2026-07-18, 1 CONTRACT01 test predmet, 1 realan predmet bez dokumenata).
Sirovi rezultati: `vindex_scraper_output/g027_validation.json` (van repo-a).

| Distribucija | Vrednosti |
|---|---|
| Matter Risk (16 predmeta) | Visok ×15, Srednji ×1 |
| Cockpit Risk (16 predmeta) | srednji ×16 (**nula varijanse**) |
| Case Ready Score | 35 ×13, 20 ×2, 50 ×1 |

Četiri pitanja iz protokola:
1. **Koliko često se razlikuju?** 15/16 (93.75%) — jedino "poklapanje"
   (predmet `47dc4817`, Matter=Srednji/Cockpit=srednji) je slučajno, jer
   je Cockpit izlaz konstantan bez obzira na predmet.
2. **Sistematska ili slučajna razlika?** Sistematska, jednosmerna:
   Cockpit gotovo nikad ne odstupa od "srednji" (16/16), dok Matter
   prati stvarne razlike u `snaga_dokaza`/nedostajućim dokazima/
   kritičnim rokovima. Ovo NIJE šum — Cockpit trenutno ne nosi
   diskriminativan signal u ovom uzorku (dodatni nalaz, ne isto što i
   G-027 sam po sebi — vredi zaseban prompt/temperature pregled pre
   fixa, ne samo "preuzmi Matter-ov broj").
3. **Isti koncept ili različiti?** Nameravaju da budu isti (isti naziv,
   ista 3-stepena skala) — Case Ready Score potvrđeno NIJE deo ovog
   problema, varirao je nezavisno (checklist kompletnosti, ne rizik).
4. **Da li korisnik razume razliku?** Ne — isti naziv polja
   ("Procena rizika"/"Procesni rizik"), ista terminologija, čak i
   case-mismatch (veliko/malo slovo), bez ikakvog objašnjenja da su to
   dva odvojena izvora.

**Bitna ograda uzorka:** 15/16 predmeta dele poreklo (14 sintetički
KALIBRACIJA batch, sličnog stila; 1 test predmet) — nema širokog realnog
uzorka iz prakse. `snaga_dokaza = "Nema dokaza"` za 14/16 (Evidence
Vault prazan za KALIBRACIJA batch iako `predmet_dokumenti` ima 1-4 reda
po predmetu) — ovo objašnjava VISOKU Matter stopu (artefakt uzorka, ne
nužno reprezentativno), ali NE objašnjava Cockpit-ovu nultu varijansu —
čak i jedini predmet sa drugačijim `snaga_dokaza` (47dc4817, "Srednja")
je i dalje dobio "srednji" od Cockpit-a, isto kao ostatak. **Zaključak:
Scenario A potvrđen — isti koncept, dva nekomunicirajuća izvora —
implementacija čeka founderovu odluku.**

**ZATVORENO (2026-07-20)** — founder odobrio implementaciju sa izmenjenom
specifikacijom (ne "Cockpit preuzima Matter broj" nego "jedinstven
servis, oba su potrošači") i formalizovao AR-01 kao trajno pravilo.
G-item closure protokol:
1. **Diff:** novi `services/risk_engine.py` (ekstrakcija, ponašanje
   nepromenjeno); `routers/matter_intel.py` sada poziva servis umesto
   inline računa; `api.py` `/workspace` računa rizik PRE GPT poziva,
   `_COCKPIT_SYSTEM` prompt promenjen da GPT vraća `rizik_objasnjenje`
   (faktori_plus/minus) umesto `procena_rizika.nivo`; risk-history
   poređenje (Step 6b) sada čita iz determinističkog izvora.
2. **CONTRACT red:** CONTRACT 01 nepromenjen (Cockpit/Matter Intel nisu
   deo CONTRACT 01 kritične putanje) — ovo je Pregled predmeta UI
   kvalitet, ne Tok 1 blocking stavka.
3. **KPI:** Coverage/Critical Coverage brojevi nepromenjeni (G-027 nije
   bio na CONTRACT listi). Novi pokazatelj uveden ovom stavkom: Cockpit/
   Matter Risk slaganje 0/16 (0%) → 16/16 (100%) posle fixa.
4. **Testovi pokrenuti:** `scripts/g027_risk_validation.py` ponovo
   pokrenut posle izmene, real API pozivi (in-process ASGI, isto kao
   CONTRACT01 harness) na svih 16 predmeta founder naloga. Rezultat:
   Matter i Cockpit se slažu na 16/16 (100%, bilo 1/16 pre fixa i to
   slučajno). Ručni test u UI-ju NIJE urađen (čeka founderov sledeći
   ručni prolaz).
5. **G-stavke zatvorene:** G-027.
6. **Nove G-stavke otvorene usput (nisu tiho prećutane):** G-028
   (`tip_dokaza` select bug — needs verification), G-029 (Cockpit
   `sledeca_akcija.prioritet` — ista AR-01 povreda, neprovereno
   empirijski, van obima ove popravke).

---

## Kako se ovaj registar koristi

- **"Zatvaram G-003"** znači: implementiran je audit poziv za
  `predmet_create`+`dokument_upload`, red testiran E2E (CONTRACT 01
  test stavka), status menja na Closed, `VINDEX_OPERATING_SYSTEM_
  CONTRACTS.md` Coverage/Critical Coverage brojevi se preračunaju.
- **"Needs verification"** stavke (G-019, G-021, G-022, G-023) NISU
  potvrđeni gapovi — ne planirati implementaciju za njih dok se prvo ne
  potvrdi da li stvarno nedostaju. Provera dolazi pre popravke.
- **Blokeri** (G-011 blokira G-008/009/010; G-024 blokira svaku
  lifecycle implementaciju) — ne pokušavati zatvoriti blokiranu stavku
  pre blokera, bez obzira koliko izgleda jednostavno izolovano.
- Novi gap otkriven u budućoj implementaciji dobija sledeći slobodan
  G-broj (G-026+) — ne prepravlja se numeracija postojećih.

## Protokol zatvaranja G-stavke (2026-07-19, founderov zahtev — obavezan format)

Rad se od sada ne zadaje kao "implementiraj feature" — zadaje se kao
**"zatvori G-XXX"**. Kad je G-stavka zatvorena, izveštaj MORA sadržati
svih 6 elemenata, ne manje:

1. **Diff** — tačna izmena koda.
2. **Koji CONTRACT je promenjen** — koja tabela/red u
   `VINDEX_OPERATING_SYSTEM_CONTRACTS.md` Deo B se ažurira.
3. **Koji KPI se promenio** — novi Coverage/Critical Coverage/Verified
   Coverage brojevi, sa računicom (ne samo novi broj — stara i nova
   vrednost).
4. **Koji testovi su pokrenuti** — automatizovan test rezultat, ručni
   test opis, (kad primenjivo) pilot scenario status.
5. **Koje G-stavke su zatvorene** — može biti više od jedne ako je
   izmena rešila lančanu zavisnost.
6. **Potvrda da nisu otvorene nove G-stavke slučajno** — ili
   eksplicitna lista ako jesu (novi gap otkriven tokom rada je
   normalan i očekivan ishod, ne greška — ali mora biti prijavljen, ne
   prećutan).

Zatvaranje bez svih 6 elemenata se ne broji kao zatvaranje — status
ostaje Open dok izveštaj nije kompletan.

## Pravilo redosleda rada (founderov zahtev)

**Dok postoji Open G-stavka koja prekida OSNOVNI operativni tok** (bilo
koja stavka bez "Needs verification" oznake, u bilo kom od 4
CONTRACT-a) **, ne razvija se nijedna nova funkcija.** Redosled je:
zatvori prekid → dokaži da radi (Verified Coverage raste) → ažuriraj
KPI → tek onda sledeći prekid. Ovo ne znači da se nikad više ne dodaju
nove mogućnosti — znači da G-registar ima prioritet nad svakim novim
predlogom dok je bar jedna osnovna stavka Open. Redosled zatvaranja
prati zavisnosti već utvrđene u `VINDEX_2_1_ARCHITECTURE_ROADMAP.md`
Deo E (infrastruktura → semantička preciznost → povezivanje).

## Kad je ovaj registar "gotov"

Kad nema više Open/Blocked/Needs-verification stavki — u tom trenutku
(i tek tada) Integration Coverage u `VINDEX_OPERATING_SYSTEM_
CONTRACTS.md` dostiže 28/28, i Vindex AI prestaje da bude "kolekcija
modula" po definiciji iz `VINDEX_INTEGRATION_MASTER_PLAN.md`.

---

**Poslednja napomena, founderova, vredna ponavljanja ovde direktno:**
sledeći pravi pomak nije novi dokument. Sledeći pravi pomak je trenutak
kad prvi red u ovoj tabeli pređe iz Open u Closed. Ovaj registar se
ažurira posle svake implementacione runde (Faza A je u toku, ne čeka se
freeze) — ne piše se deveti planski dokument dok se bar par ovih redova
ne zatvori.

**Update 2026-07-19 (isti dan, prva akcija Faze A):** CONTRACT 01
kritični koraci (klasifikacija, Evidence Vault, Genome regeneracija)
DOBILI su automatizovan E2E dokaz (`scripts/contract01_e2e_verify.py`,
stvaran predmet u produkciji, sva 3 PASS). Ovo NE zatvara G-001/G-002/
G-003 (ti se odnose na infrastrukturu koja nije bila deo ovog testa) —
ali daje prvi realan Verified Coverage podatak od 0% polazne tačke.

**Update 2026-07-21 — G-001, G-002 zatvorene (kod), commit `8f54f54`:**
1. **Diff:** `api.py::kreiraj_predmet` (`POST /api/predmeti`) sada
   poziva `services.event_bus.emit(EventType.PREDMET_KREIRAN, ...)`
   posle uspešnog insert-a u `predmeti`. Nijedan nov event tip, nijedan
   nov handler — `on_predmet_kreiran` je već postojao i bio registrovan
   (`services/event_bus.py:98-107,198`), samo nikad nije bio pozvan za
   ovaj (jedini live) put.
2. **CONTRACT promenjen:** `VINDEX_OPERATING_SYSTEM_CONTRACTS.md`,
   CONTRACT 01, redovi "Koji event mora nastati" i "Koji servisi moraju
   biti pozvani".
3. **KPI:** namerno NIJE promenjen u ovoj rundi — videti napomenu u
   Contracts dokumentu ("Update 2026-07-21") zašto Verified Coverage
   ostaje netaknut dok se `contract01_e2e_verify.py` ne proširi da
   pokrije `POST /api/predmeti` konkretno.
4. **Testovi:** `pytest tests/test_intake_phase0.py` (22/22 prošlo,
   event bus mehanizam nepromenjen); `python -c "import ast; ..."`
   sintaksna provera; ručni import test za `services.event_bus`. **Nije**
   pokrenut novi E2E test protiv produkcije za ovu konkretnu izmenu.
5. **G-stavke zatvorene:** G-001 (D3), G-002 (D9, lančana posledica).
6. **Nove G-stavke:** nijedna otvorena slučajno. G-003 (audit za
   `predmet_create`/`dokument_upload`, D22) ostaje Open — namerno van
   obima ove izmene, nije dirano.
Detalji u `VINDEX_OPERATING_SYSTEM_CONTRACTS.md` CONTRACT 01.

**Update 2026-07-21 — G-001, G-002 VERIFIKOVANE produkcijski, commit
`5bcc226`:**
1. **Diff:** `scripts/contract01_e2e_verify.py` prošireno da stvarno
   proveri checks 4/5/7 (bili hardkodovani `False`) — poll na
   `predmet_istorija` za `[Pipeline]` sumarni red; ispravljen i UTF-8
   stdout bug na Windows konzoli koji je srušio prvi run POSLE svih
   supstantivnih provera.
2. **CONTRACT promenjen:** `VINDEX_OPERATING_SYSTEM_CONTRACTS.md`
   CONTRACT 01 (Integration/Critical/Verified Coverage + agregatni KPI);
   `VINDEX_INTEGRATION_MASTER_PLAN.md` Tok 1 DoD checkboxes.
3. **KPI:** Integration Coverage CONTRACT 01 4/6=67% → **6/6=100%**.
   Agregatni Coverage (4 ugovora) 9/28=32% → **11/28=39%**. Critical
   Coverage nepromenjen (7/14=50%, D3/D9 nisu bili u kritičnoj
   definiciji). Puna računica u Contracts dokumentu.
4. **Testovi:** `scripts/contract01_e2e_verify.py` pokrenut DVA PUTA
   protiv produkcije (predmet_id `b3f7eae5...` i `87b76dc2...`, oba
   `[E2E CONTRACT01] Test predmet 2026-07-21`) — svih 7 provera
   PASS/POZNATO kako je očekivano (1-5,7 PASS; 6/D22 FAIL/POZNATO,
   namerno van obima). Puni dokaz: `CONTRACT_01_PRODUCTION_
   VERIFICATION.md` (novi dokument).
5. **G-stavke zatvorene (sada VERIFIED, ne samo Closed-u-kodu):**
   G-001 (D3), G-002 (D9).
6. **Nove G-stavke:** nijedna. Jedan sitan test-harness bug nađen i
   popravljen (Windows cp1252 stdout, ne sistemski bug) — nije dobio
   G-broj jer nije production kod, samo test tooling.

**Update 2026-07-21 (isti dan) — G-003 zatvorena i VERIFIKOVANA
produkcijski, commit `b84fd4b`/`bb4388b` — D22 v1 SAMO, eksplicitno
ograničen obim:**
1. **Diff:** `api.py::kreiraj_predmet` i `api.py::predmet_upload_auto_
   analyze` sada zovu `shared.audit_immutable.log_action("predmet_
   create", ...)` / `log_action("dokument_upload", ...)`. Oba imena
   akcije već postoje u `AUDITABLE_ACTIONS`, nikad ranije pozvani —
   nijedna nova tabela/šema/event tip. `scripts/contract01_e2e_verify.py`
   check 6 prošireno da asertuje TAČNU akciju + korelaciju resursa
   (ne samo postojanje reda) — usput otkriven i popravljen bug:
   `audit_immutable.metadata` se vraća kao JSON string (snimljen preko
   `json.dumps()`), ne parsiran dict.
2. **CONTRACT promenjen:** `VINDEX_INTEGRATION_MASTER_PLAN.md` Tok 1,
   7. DoD stavka (Audit) — sada takođe zaokružena.
3. **KPI:** Integration Coverage CONTRACT 01 ostaje **6/6=100%** za
   originalnih 6 DoD stavki (namerno NIJE promenjen imenilac — D22 je
   7. stavka formalizovana POSLE originalnog brojanja, videti Master
   Plan). Agregatni KPI (9/28, 11/28) takođe namerno nepromenjen iz
   istog razloga — izbegava se prepravljanje imenioca unazad preko
   više dokumenata bez punog ponovnog računanja svih 4 ugovora.
4. **Testovi:** treći produkcijski run (`predmet_id ab37c832...`),
   svih 7 provera PASS (uključujući sada i #6). Puni dokaz:
   `CONTRACT_01_PRODUCTION_VERIFICATION.md` Addendum.
5. **G-stavke zatvorene:** G-003 (D22 v1).
6. **Nove G-stavke:** nijedna — ali eksplicitno NIJE zatvoreno (ostaju
   Open, van obima D22 v1, ne tvrditi suprotno u budućim sesijama):
   tamper-evidence provera (`verify_chain_integrity()` postoji,
   NIJE pozvana ovim testom), retention politika, user attribution kroz
   SVE tokove (~19-21 od 24 `AUDITABLE_ACTIONS` i dalje nikad pozvano —
   ovaj fix pokriva TAČNO 2 od njih), export audit traga, compliance
   format.

## G-034 ZATVOREN kao "Resolved — Evidence insufficient" (2026-07-22)

Poslednja stavka Case Genome integracione serije (G-031 do G-034,
izvučene iz `CASE_GENOME_FULL_INTEGRATION_COMPLETION` masterprompta).
Za razliku od G-031/G-032/G-033 (implementirano i verifikovano), G-034
je zatvoren BEZ implementacije — empirijska analiza
(`scripts/g034_risk_validation.py`) nije potvrdila hipotezu da Genome i
`risk_engine.py` mere isti koncept. Status namerno NIJE "Open" (to bi
sugerisalo da nešto čeka implementaciju) — **Status: Resolved, Decision:
No implementation, Reason: Insufficient evidence.** Ne otvarati ponovo
dok se ne pojavi 100+ realnih (ne sintetičkih) predmeta za noviju
proveru iste hipoteze.

**Founderova eksplicitna ocena metodologije:** "Da je Claude ili bilo ko
drugi želeo da 'ugura' implementaciju, mogao je vrlo lako napisati
'Postoji korelacija, predlažem spajanje.' Umesto toga, analiza je
ostala verna podacima." — zaključak C (nedovoljno dokaza) tretiran kao
**podjednako vredan ishod** kao A ili B, ne kao neuspeh analize.

**Founderova eksplicitna preporuka za sledeću sesiju, izneta posle
zatvaranja G-034:** dalje traženje skrivenih Case Genome integracionih
gapova NIJE preporučeno — ne zato što sigurno ne postoje, nego zato što
cena traženja raste dok verovatnoća novog G-031/G-032 nalaza opada.
**Case Genome se tretira kao arhitektonski konsolidovan u meri u kojoj
postoje dokazi.** Sledeći izvor saznanja o eventualnim novim
integracionim problemima su realni pilot predmeti, ne dalja statička
analiza koda.
