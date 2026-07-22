# Vindex 2.1 — Architecture Roadmap (ADR)

**Poslednje ažuriranje: 2026-07-19.** Ovo je centralni, živ dokument
koji zamenjuje potrebu da se ponovo prolazi kroz `OPERATING_SYSTEM_
CONNECTIVITY_AUDIT.md`, `OPERATING_SYSTEM_CONNECTIVITY_AUDIT_V2.md`,
`OPERATING_SYSTEM_ROADMAP.md`, `TRUST_LAYER_IMPLEMENTATION_PLAN.md`,
`TRUST_LAYER_BETA_FREEZE_2026-07-19.md`, `KNOWN_RELIABILITY_RISKS.md`,
i `NOVI_PREDMET_CHOOSER_ANALYSIS.md` da bi se rekonstruisalo šta je već
odlučeno. Ti dokumenti ostaju kao dubinski dokaz iza svake odluke ovde
— ovaj dokument je INDEKS ODLUKA, ne zamena za njihov detalj.

**Dopuna (2026-07-19):** `VINDEX_INTEGRATION_MASTER_PLAN.md` je šesti
dokument u nizu — USTAV PROCESA (kako se rad organizuje po tokovima, ne
modulima; Definition of Done po toku; obavezno end-to-end testiranje).
Taj dokument je otkrio D21/D22 ispod, prvi put registrovane ovde.

**Druga dopuna (2026-07-19):** `VINDEX_OPERATING_SYSTEM_CONTRACTS.md`
je sedmi dokument — UGOVOR (precizna specifikacija po toku: trigger/
event/servisi/podaci/UI/audit/test, plus matematički izračunata
Integration Coverage po toku — 67%/10%/29%/40%, ponderisan agregat 32%).
Taj dokument je otkrio D23/D24 ispod.

**Pravilo održavanja:** kad pilot feedback stigne, ažurira se OVAJ
dokument (status promena, nova odluka dodata) — ne pišu se novi
paralelni audit dokumenti za iste teme. Ako se otvori potpuno nova tema
(ne produbljivanje postojeće), novi audit dokument je opravdan, ali
njegov zaključak treba da se svede u red ovde.

**STATUS PROMENJEN (2026-07-19, isti dan):** "Deferred (posle beta
feedback-a)" u ovom dokumentu se sada čita kao "čeka red u Fazi A
Internal Integration Sprint" (`VINDEX_OPERATIONAL_GAP_REGISTER.md`),
ne "čeka pasivno da freeze prestane". Beta Freeze u starom obliku
("nema koda dok ne stigne pilot feedback") je zamenjen — implementacija
je u toku, ograničena na zatvaranje G-stavki, bez novih funkcija.

**Status legenda:**
- **Accepted** — odluka doneta, spremna za implementaciju čim freeze
  dozvoli (ili već implementirana).
- **Deferred (posle beta feedback-a)** — dizajn jasan, effort/rizik
  procenjen, čeka samo da Beta Freeze prestane.
- **Blocked (zavisi od pilota/druge odluke)** — ne može se pouzdano
  dizajnirati ili prioritizovati bez dodatnog ulaza (pilot podaci, ili
  druga odluka u ovoj listi mora prvo pasti).
- **Rejected** — eksplicitno odlučeno da se NE radi, sa razlogom.

---

## Trenutni okvir (ne menja se ovom listom)

**BETA FREEZE JE NA SNAZI** (`TRUST_LAYER_BETA_FREEZE_2026-07-19.md`).
Main grana ide u pilot kakva jeste. Nijedna stavka označena "Deferred"
ili "Blocked" ispod se ne implementira dok founder eksplicitno ne
potvrdi da je pilot feedback stigao. Ovaj dokument ne menja tu odluku —
organizuje šta čeka na redu KAD freeze prestane.

---

## Faza 1 — Pouzdan ulaz

### D1. Preciznija klasifikacija procesnih akata

- **Kontekst:** Evidence Vault (`routers/evidence.py`) klasifikuje
  tužbu/žalbu/odgovor na tužbu SVE kao `podnesak`, presudu/rešenje OBA
  kao `sudska_odluka` — nedovoljno granularno za ZPP rok-pravila koja
  se razlikuju po tačnom tipu akta. (`OPERATING_SYSTEM_CONNECTIVITY_
  AUDIT_V2.md`, Faza 3.)
- **Status: Blocked (zavisi od D2 i pilota).** Ovo je preduslov za D6/
  D7, ne samostalna poboljšica — nema smisla graditi pre nego što se
  zna da će se rok-automatizacija (Faza 3 ovog dokumenta) stvarno
  praviti.

### D2. Pouzdano hvatanje datuma dostave/prijema

- **Kontekst:** većina ZPP rokova počinje datumom DOSTAVE, ne datumom
  dokumenta — sistem danas ne hvata ovaj datum pouzdano nigde u
  pipeline-u. Označeno kao temeljniji blok od D1.
- **Status: Blocked (zavisi od pilota).** Najveći dizajn-rizik u celoj
  listi — pogrešan datum dostave čini ceo downstream rok-lanac
  netačnim bez obzira koliko je ostatak sistema dobar. Treba founder-
  ova odluka o pristupu (da li se datum dostave traži eksplicitno od
  advokata kao obavezno polje pri uploadu, ili se pokušava ekstrakcija
  sa vrlo visokim pragom pouzdanosti) PRE dizajna.

---

## Faza 2 — Događaj

### D3. Emitovati `PREDMET_KREIRAN` iz standardnog intake puta

- **Kontekst:** event i njegov handler (`on_predmet_kreiran` →
  `run_case_pipeline()`) već postoje i rade — samo se nikad ne pozivaju
  za jedini live put kreiranja predmeta. (`OPERATING_SYSTEM_ROADMAP.md`,
  Top 5 #1.)
- **Status: Deferred (posle beta feedback-a).** Nizak effort, nizak-
  srednji rizik, dizajn kompletan — spreman za implementaciju čim
  freeze prestane, bez dodatnih odluka potrebnih.

### D4. Definisati i emitovati "Dokument klasifikovan" event

- **Kontekst:** ne postoji odgovarajući `EventType` danas — trebalo bi
  da postoji da bi Faza 3 (D6) imala signal na koji reaguje.
- **Status: Blocked (zavisi od D1).** Nema smisla emitovati event čija
  je jedina svrha da trigeruje rok-logiku koja ne može pouzdano da
  radi dok D1 nije rešeno.

### D5. Aktivirati `RokKritican`/`HealthScorePromenjen` evente

- **Kontekst:** oba imaju izgrađene, funkcionalne handlere
  (`proactive_alerts` kreiranje, upozorenje na nizak health score) koji
  čekaju evente koji se nikad ne emituju.
- **Status: Deferred (posle beta feedback-a).** Nizak effort — hendleri
  su gotovi, samo treba pronaći ispravna mesta za `emit()` poziv
  (verovatno u rok-related i Genome-related kodu). Nezavisno od D1-D2.

### D25 (novo, `VINDEX_OPERATIONAL_GAP_REGISTER.md`). Emitovati `ROCISTE_ZAKAZANO`

- **Kontekst:** definisan u enum-u, nema registrovan handler niti se
  emituje — isti obrazac kao D3/D5, otkriven odvojeno pri izradi
  CONTRACT 03 (Dodavanje ročišta).
- **Status: Deferred (posle beta feedback-a).** Nizak effort, nezavisno
  od ostalih D-stavki.

---

## Faza 3 — Deterministički motor

### D6. Povezati ZPP rok-katalog sa klasifikacijom dokumenta, uz obaveznu advokatovu potvrdu

- **Kontekst:** deterministički katalog (`routers/rokovi_lanac.py`) već
  postoji i tačan je — nedostaje samo triger iz klasifikacije. Dizajn
  već postoji (`OPERATING_SYSTEM_ROADMAP.md`, Task 3): AI predlaže tip
  roka, sistem izračuna tačan datum, advokat MORA potvrditi pre nego
  što rok postane obavezujući.
- **Status: Blocked (zavisi od D1, D2, D4).** Ne implementirati pre sva
  tri preduslova, inače nosi realan rizik uverljivo pogrešnog roka.

### D7. Materijalizacija Genome `rokovi_kriticni[]` u stvarne rokove

- **Kontekst:** Genome ekstrahuje kritične rokove iz teksta dokumenata,
  ali podatak ostaje zarobljen u JSON koloni, nikad ne postaje
  actionable stavka u Rokovi tabu.
- **Status: Blocked (zavisi od D2).** Isti rizik profil kao D6 — datum
  mora biti pouzdan pre nego što se pretvori u obavezujući rok, čak i
  uz potvrda-korak.

### D8. Surface-ovati Deadline Guardian u UI

- **Kontekst:** `routers/zastarelost.py::guardian_scan/guardian` je
  potpuno izgrađen (skenira sve rokove 30 dana unapred, generiše
  akcioni plan unazad od roka), nula UI referenci bilo gde.
- **Status: Deferred (posle beta feedback-a).** Nezavisno od D1/D2/D6 —
  Guardian radi nad ROKOVIMA KOJI VEĆ POSTOJE u sistemu (bilo koji
  izvor), ne zavisi od nove klasifikacije. Čist frontend rad, nizak
  rizik, može ići prvo od cele Faze 3.

### D9. Aktivirati `run_case_pipeline()` za standardni intake put

- **Kontekst:** direktna posledica D3 (event emitovan → handler ga
  automatski pokreće) — nabrojano odvojeno jer nosi sopstveni rizik
  (dodatni GPT troškovi po predmetu, treba meriti).
- **Status: Deferred (posle beta feedback-a), zavisi tehnički od D3
  ali se meri nezavisno.**

### D21. Jedinstven izvor istine za rokove (novo, `VINDEX_INTEGRATION_MASTER_PLAN.md`)

- **Kontekst:** reorganizacija po tokovima (ne modulima) otkrila je
  TRI paralelna, nesinhronizovana "rok" koncepta: `predmet_hronologija`
  (piše ZPP lanac/follow-up/GPT ekstrakcija), `rokovi` tabela (čita je
  Guardian + 6 drugih modula, nijedan pisac nađen), `zadaci.rok_datum`
  (sopstveni rok pojedinačnog zadatka, potpuno nezavisan).
- **Status: Blocked (zavisi od D2, prethodi D6/D7/D8 sadržajno).** Pre
  nego što se ijedna veza iz D6-D9 implementira sa STVARNIM sadržajem,
  mora se odlučiti koji izvor postaje jedini — arhitektonska odluka,
  ne detalj, utiče na redosled cele Faze 3.

### D22. Core audit trail akcije (formalizovano iz Roadmap-a)

- **Kontekst:** od 24 dozvoljene akcije u `AUDITABLE_ACTIONS`, samo 3
  se stvarno pozivaju. `predmet_create`, `dokument_upload`,
  `klijent_create`, `login_success/failed` nikad ne ostavljaju trag,
  uprkos GDPR referenci u kodu. Dodatno potvrđeno u Integration Master
  Plan-u: `audit_immutable` tabelu **ništa nikad ne čita nazad**
  (0 poziva van `log_action` definicije) — čak i kad bi se popunila,
  nema Analytics/dashboard koji bi je iskoristio.
- **Status: Blocked — kandidat za HITAN izuzetak od Beta Freeze-a,
  isti razlog kao D10/D11** (compliance rizik postoji nezavisno od
  pilot signala, ne nova funkcionalnost). Founderova odluka.

### D23. Usklađivanje predloženog "predmet kao mašina stanja" sa postojećim Kanban statusom (novo, `VINDEX_OPERATING_SYSTEM_CONTRACTS.md`)

- **Kontekst:** predložen 13-stanja lifecycle (Kreiran→...→Arhiviran)
  za predmet je mnogo granularniji od postojećeg Kanban `_KANBAN_FAZE`
  (5 faza) i ne poklapa se 1:1. Uvođenje novog statusa BEZ usklađivanja
  bi stvorilo ČETVRTI paralelni "status predmeta" izvor istine (uz
  Kanban, uz Genome `genome_kompletnost`, uz D21 rok-koncepte) — isti
  tip problema kao D21.
- **Status: Blocked (zavisi od pilota + arhitektonske odluke).** Ne
  implementirati pre nego što se eksplicitno odluči: da li novi
  lifecycle ZAMENJUJE Kanban, da li se Kanban IZVODI iz lifecycle-a, ili
  ostaju namerno odvojeni sa jasnom podelom svrhe.

### D24. Ne postoji `EventType` ni koncept za zatvaranje/pravosnažnost predmeta

- **Kontekst:** za razliku od ostalih "nedostajućih" eventova (koji BAR
  postoje kao definicija u enum-u), za "predmet zatvoren"/"predmet
  postao pravosnažan" ne postoji čak ni definicija.
- **Status: Blocked (zavisi od D23).** Definisati tek kad se odluči
  kako se ovo stanje uopšte modeluje.

---

## Faza 4 — Operativni sistem

### D10. Rešiti notification cron isporuku (email/whatsapp/morning briefing)

- **Kontekst:** sva tri sistema su ispravno izgrađena, ali zahtevaju
  eksterni cron poziv koji `Procfile` ne definiše. Landing stranica
  (`index.html:4067`) JAVNO obećava "Sistem prati rokove umesto vas" —
  ovo obećanje je verovatno trenutno neispunjeno u produkciji.
- **Status: Blocked — ALI preporučujem founderu da razmotri hitan
  izuzetak od Beta Freeze-a za OVU STAVKU specifično**, jer nije "nova
  funkcionalnost" nego provera/popravka VEĆ DATOG javnog obećanja.
  Razlika je bitna: Freeze je smišljen da spreči nove interne iteracije
  pre pilot signala, ne da ostavi neispunjeno spoljno obećanje da stoji
  dok traje pilot. Konačna odluka o izuzetku je founderova — ovde je
  samo eksplicitno flagovano da se ne izgubi u listi.

### D11. Proveriti/ukloniti 3 "unlock" modal obećanja bez potvrđenog odredišta

- **Kontekst:** Knowledge Transfer/Firm DNA/Intelligence Engine
  (15/20/30 predmeta) — nijedno nema potvrđen realan UI pane.
- **Status: Blocked — ista preporuka kao D10** (moguć hitan izuzetak,
  founderova odluka), iz istog razloga: postojeće obećanje, ne nova
  funkcija.

### D12. AI Output → System Action — task-predlog iz Genome nalaza

- **Kontekst:** Genome `nedostaje`/`najslabija_tacka` se prikazuju ali
  nikad ne kreiraju task, čak ni kao predlog. Advokat mora ručno da
  prenese svaki nalaz u Zadaci tab ako želi podsetnik.
- **Status: Deferred (posle beta feedback-a).** Dizajn: sistem PREDLAŽE
  task, advokat potvrđuje/odbija — ista granica kao D6 (nikad automatski
  izvršena akcija bez potvrde).

### D13. Konsolidacija 4 fragmentirana "sledeći koraci" sistema

- **Kontekst:** Genome sinteza, `matter_intel.py`, `case_intelligence.py`,
  `workflow.py` — nijedan ne zna za ostale, mogu davati različite
  preporuke bez objašnjenja zašto se razlikuju.
- **Status: Deferred (posle beta feedback-a), niži prioritet (P2).**
  Vredi prvo videti da li pilot advokati uopšte primete nekonzistentnost
  pre nego što se ulaže u konsolidaciju.

### D14. Kanban "Završen" → opciona finalna faktura/checklist

- **Kontekst:** promena statusa na "Završen" je danas potpuno inertna
  — ne trigeruje finalnu fakturu niti arhiviranje.
- **Status: Deferred (posle beta feedback-a), niži prioritet (P2).**

---

## Faza 5 — Case Genome Integration Sync (dodato 2026-07-22)

Poreklo: `CASE_GENOME_FULL_INTEGRATION_COMPLETION` masterprompt (2026-07-22)
tretiran ne kao dozvola za refaktoring, nego kao checklist za preostale
integracione gapove — founderova eksplicitna odluka istog dana: "Izvuci
iz masterprompta samo one stavke koje predstavljaju integraciju
postojećih komponenti, bez proširenja funkcionalnosti i bez kršenja
D20." Sve četiri stavke ispod su POVEZIVANJE postojećeg koda — nijedna
ne dodaje nov event tip, nov AI agent, niti menja poslovnu logiku.
Masterprompt-ove stavke koje BI kršile D20 (Faza 6 Learning Loop,
Faza 3 "blokiraj invalid Genome" kao promena poslovne logike) su
eksplicitno IZOSTAVLJENE ovde, ne tiho zaboravljene — vidi napomenu na
kraju ove sekcije.

### D26 (novo, `VINDEX_OPERATIONAL_GAP_REGISTER.md` G-031). `health_index.py` čita nepostojeća Genome polja

- **Kontekst:** `routers/health_index.py:272` — `genome.get("ishod") or
  genome.get("preporucena_akcija", "")`. Nijedno od ta dva polja ne
  postoji u Genome šemi (`routers/case_dna.py:39-115`) — izraz uvek
  vraća `""`, tiho lomi "ishod zatvorenog predmeta" signal koji Health
  Index pokušava da izračuna (`health_index.py:252-289`).
- **Status: Closed (commit `aae1c54`/`ac667a9`, 2026-07-22).** Stvaran
  izvor istine je `predmet_hronologija`, ne Genome — Genome nikad nije
  ni imao ovaj koncept u šemi. Fix reuse-uje postojeći parser iz
  `routers/predmeti_close.py::get_predmet_ishod`. Founderov review
  otkrio dodatni edge case (reopen→reclose, `datum` je korisnički
  zadato polje, ne pouzdan sort ključ) — ispravljeno da koristi
  `created_at`. Verification: Unit verified (3 testa,
  `tests/test_health_index_weak_signals.py`), Production E2E: Not
  required (deterministički read-path, nema event/pipeline/audit/AI
  stranu — founderova eksplicitna ocena).

### D27 (novo, G-032). `require_review` verifikacija nema potrošača

- **Kontekst:** `shared/genome_validator.py::verify_genome()` računa
  `odluka: require_review` kad se nađe hard-flag, upisuje se u audit
  metadata (`services/event_bus.py::on_genome_updated`), ali ništa ne
  reaguje na tu vrednost — nema alert, nema notifikaciju.
- **Status: Closed (commit `9ed7679`, 2026-07-22).** Rešenje reuse-uje
  POSTOJEĆI `proactive_alerts` mehanizam (isti obrazac kao
  `genome_change` alert u `routers/case_dna.py`) — nula novog eventa,
  nula novog AI-ja. Alert nastaje SAMO na prelaz u `require_review`
  (dedup preko poređenja starog/novog `_verifikacija.odluka`), ne na
  svaki refresh dok isti problem traje. Verification: Unit + Integration
  verified (`tests/test_case_dna_verifikacija_alert.py`, 4 testa —
  false→true/true→true/true→false→true životni ciklus). Production E2E:
  Not required (deterministička integracija, nema AI/event/side-effect
  promene — founderova eksplicitna ocena, ista kategorija kao D26).

### D28 (novo, G-033). Strategy Simulator nema audit trag niti genome_version referencu

- **Kontekst:** `routers/strategy_simulator.py` — potvrđeno grep-om,
  nula poziva `log_action`/`audit_immutable` u celom fajlu. Genome
  verzija (`_g.get('verzija',1)`) se koristi samo inline u GPT prompt
  tekstu (`strategy_simulator.py:230`), nikad se ne upisuje na
  `simulator_partije` red za kasniju sledljivost.
- **Status: Accepted, PRIORITET 3 (posle D27).** `ai_analiza_complete`
  je već u `AUDITABLE_ACTIONS` allowlist-i, nikad pozvan iz ovog fajla
  — isti obrazac kao D22 (aktiviranje postojeće, nekorišćene akcije).
  `genome_verzija` kolona na `simulator_partije` je šema-dopuna, ne
  nova poslovna logika.

### D29 (novo, G-034). Genome risk signali naspram `risk_engine.py` — analiza, NE odluka

- **Kontekst:** `services/risk_engine.py::calculate_procesni_rizik`
  (deterministički izvor rizika posle G-027 fix-a) ima nula referenci
  na `case_dna`/genome — potvrđeno grep-om. Genome nezavisno računa
  sopstvene rizik-signale (`najslabija_tacka.kriticnost`,
  `snaga_predmeta_procent`). Isti oblik obrasca kao G-027 (Cockpit vs.
  Matter Intel "procesni rizik").
- **Status: Blocked — čeka empirijsku analizu, NE Accepted za
  implementaciju.** Founderovo eksplicitno pravilo (isto kao G-027,
  2026-07-22): "izgleda kao duplikat" ≠ "dokazano duplikat". Sledeći
  korak je skript analogan `scripts/g027_risk_validation.py` koji
  poredi Genome i Risk Engine signale na realnom uzorku predmeta —
  TEK POSLE toga sledi odluka (spoji/razlikuj/ne diraj), ne pre.

**Eksplicitno IZOSTAVLJENO iz ove sekcije (masterprompt stavke koje
zadiru u D20 teritoriju, ne tiho zaboravljene):** Faza 6 (Learning Loop
konekcija — `learning_engine`/`confidence_calibrator`/`lessons_learned`
dobijaju ulaze koji MENJAJU buduće ponašanje sistema, čak i u
"defanzivnom" obliku koji masterprompt predlaže); Faza 3 (Genome
Validation kao HARD BLOKADA umesto trenutnog advisory-only dizajna —
ovo bi bila promena poslovne logike, ne povezivanje postojećeg koda,
`shared/genome_validator.py`'s sopstveni dizajn dokument eksplicitno
kaže "require_review je status, ne blokada"). Oba čekaju zasebnu,
eksplicitnu founderovu odluku pre nego što se uopšte razmatraju —
nisu deo D26-D29 rada.

---

## Meta-odluke — Trust Layer i arhitektonske granice

### D15. Smart Intake confidence prikaz (T1.1/T1.2)

- **Kontekst:** implementirano i testirano (`_siConfidenceLabel`,
  `_siRenderResult`), ali fizički živi na `feature/new-predmet-chooser`
  grani jer je tekstualno neodvojivo od tog bloka koda.
- **Status: Accepted (implementirano), Blocked na merge.** Sama
  implementacija je gotova posao — čeka D16 (chooser merge odluku), ne
  sopstveni dizajn rad.

### D16. "Novi predmet chooser" merge u main

- **Kontekst:** puna analiza već postoji (`NOVI_PREDMET_CHOOSER_
  ANALYSIS.md`) — šta rešava (potvrđeno), UX test potvrda (NE
  direktno), onboarding uticaj (menja ga, trenutno nedosledno),
  kognitivni teret (raste za 1 klik, nema "zapamti izbor").
- **Status: Blocked (zavisi od pilota).** Eksplicitno izabrano da se NE
  merge-uje samo zbog D15 vrednosti (founderova odluka, `TRUST_LAYER_
  BETA_FREEZE_2026-07-19.md`) — čeka pilot signal o tome da li Smart
  Intake treba da postane primarni ulaz (videti D18).

### D17. Evidence Vault ↔ Case Genome tvrdnja-dokaz povezivanje (P1.3)

- **Kontekst:** dva paralelna, nekomunicirajuća sistema dokaza. Ovo NIJE
  previd — `shared/genome_validator.py:15-21` eksplicitno dokumentuje
  da je provenance provera "procenjena i odložena" zbog rizika lažnih
  pozitiva (Faza 1.3 dizajn odluka).
- **Status: Deferred (posle beta feedback-a) — NE Rejected.** Founder
  je eksplicitno rekao "posle stvarnih predmeta", ne "nikad". Vredi
  ponovo razmotriti SA pilot podacima, ne pre.

### D18. Strateška stavka: Smart Intake kao jedinstveni entry point sistema

- **Kontekst:** veći, dugoročan arhitektonski rez — jedan Intake Engine
  umesto "stari wizard + Smart Intake + potencijalno treći način".
- **Status: Blocked (zavisi od pilota).** Eksplicitno zapisan pravac,
  ne odluka doneta danas (`TRUST_LAYER_BETA_FREEZE_2026-07-19.md`,
  Backlog). Ne raditi ništa dok 3-5 pilot advokata ne pokažu da li V2
  (Smart Intake) treba da zameni V1 (stari wizard).

### D19. `verify_genome()` edge case — tiho "odobreno" ako sve podprovere padnu

- **Kontekst:** `KNOWN_RELIABILITY_RISKS.md` — niska verovatnoća,
  visok uticaj na poverenje ako se materijalizuje.
- **Status: Deferred (posle beta feedback-a), niži prioritet.** Nema
  dokaz da se ovo ikad realno desilo — prati se, ne hitno.

### D20. Arhitektonske granice — eksplicitno Rejected, ne "još nije urađeno"

Ovo NISU praznine koje čekaju implementaciju — ovo su svesno donete
granice, ponovljene kroz sve audite ove sesije:

- **Automatsko pokretanje Strategy modula** na osnovu novog dokaza/
  Genome promene — **Rejected.** Strategy generiše argumentaciju koja
  zahteva advokatovu nameru; automatsko pokretanje bi bilo AI koji
  "odlučuje" da li je vreme za novu strategiju, ne AI koji pomaže.
- **Novi AI agenti/modeli** za bilo koju stavku u ovoj listi —
  **Rejected.** Svaka stavka D1-D14 koristi POSTOJEĆU infrastrukturu.
- **Nova event arhitektura** — **Rejected.** 12 `EventType` vrednosti
  već postoji, 11 čeka povezivanje ili gašenje — ne dodavati 13.
  (Izuzetak: D4, jedan nov event tip za "dokument klasifikovan", jer
  taj koncept stvarno ne postoji u trenutnom enum-u — ovo je dodavanje
  NEDOSTAJUĆE karike u postojeći sistem, ne nova arhitektura.)
- **Nov Case Pipeline / nov Deadline sistem** — **Rejected.** Oba već
  postoje (`case_pipeline.py`, `zastarelost.py`) i rade — D9/D8 su
  povezivanje, ne građenje.
- **Bilo koja automatska akcija sa pravnom/finansijskom posledicom bez
  advokatove potvrde** (rok, faktura, podnesak) — **Rejected, trajno.**
  Ovo je Product Philosophy Deo 4 granica, ne privremeno ograničenje —
  ponovljena eksplicitno u D6/D7/D12 dizajnu ("advokat potvrđuje ili
  menja predlog", direktan citat iz korisnikovog Faza 4 predloga).

### D20.1 (novo, trajna arhitektonska smernica). Jedan poslovni koncept = jedan izvor istine

Founderova formulacija, direktan citat: *"Ako postoje dva: problem.
Ako postoje tri: ozbiljan problem. Ako postoje četiri: arhitektonski
dug koji će se stalno vraćati."* D21 (tri paralelna rok-koncepta) i D23
(lifecycle status naspram Kanban statusa) su dva NEZAVISNA otkrića istog
obrasca — dovoljno da se ovaj obrazac formalizuje kao STALNO PRAVILO za
evaluaciju svakog budućeg predloga, ne samo za rokove/status:

- **Jedan izvor istine za rokove** (D21 — trenutno tri: `predmet_
  hronologija`, `rokovi` tabela, `zadaci.rok_datum` — nerešeno).
- **Jedan izvor istine za status predmeta** (D23 — trenutno najmanje
  dva: Kanban `_KANBAN_FAZE`, plus predloženi lifecycle status ako se
  usvoji bez usklađivanja — nerešeno).
- **Jedan izvor istine za životni ciklus predmeta** (deo D23/D24
  diskusije — Case Genome `genome_kompletnost` je TREĆI kandidat koji
  delimično preklapa "koliko je predmet zreo/spreman").
- **Jedan izvor istine za događaje** (event bus `events` tabela — ovo
  već JESTE jedinstveno, `services/event_bus.py`, nema paralelnih
  event-log sistema pronađenih — pozitivan primer da se pravilo može
  ispoštovati).

**Praktična primena za svaki budući predlog:** pre nego što se doda
NOVO polje/tabela/status koje opisuje nešto što sistem već negde prati
(rok, status, prioritet, "spremnost"), prvo proveriti da li već postoji
izvor istine za taj koncept. Ako postoji — novi mehanizam mora biti
PROJEKCIJA tog izvora (izveden prikaz), ne zasebna evidencija. Ako
provera pokaže DVA ili više postojećih izvora za isti koncept — to je
samo po sebi nalaz vredan D-broja u ovom registru, pre nego što se
razmišlja o trećem.

### AR-01 (novo, trajno arhitektonsko pravilo, 2026-07-20). LLM nikad ne određuje poslovno stanje

Otkriveno kroz G-027 (Matter Intelligence i Cockpit su nezavisno
računali "procesni rizik" — empirijski potvrđeno 16/16 predmeta, GPT je
vraćao "srednji" bez ikakve varijanse dok je deterministička formula
ispravno pratila stvarne podatke). Founderova formulacija, direktan
citat:

> "LLM nikada ne određuje poslovno stanje sistema. LLM može da: objasni,
> sumira, predloži, napiše, upozori. Ali ne određuje: rizik, status,
> rok, kompletiranost, prioritet. To određuje deterministički sloj."

Ovo NIJE D-stavka sa statusom (Accepted/Deferred/Blocked) — kao ni
D20.1, ovo je STALNO pravilo za evaluaciju svakog budućeg predloga koji
uključuje LLM izlaz:

- **Sme:** objašnjenje ("zašto je rizik visok"), sažetak, predlog
  sledećeg koraka kao TEKST, upozorenje, nacrt dokumenta.
- **Ne sme:** da bude JEDINI izvor za rizik, status, rok, spremnost/
  kompletiranost, prioritet — ta polja moraju imati deterministički
  izračunat izvor istine; LLM ih najviše INTERPRETIRA već izračunatu
  vrednost, nikad je ne izmišlja iznova.
- Isti princip kao Trust Layer (izvori/citati) i Deterministic
  Intelligence Framework ([[project_deterministic_intelligence_framework]])
  — G-027 je treći nezavisan nalaz istog obrasca, sada eksplicitno
  imenovan kao opšte pravilo umesto da se otkriva iznova po polju.

**Poznati preostali slučajevi koji krše AR-01 (otkriveni usput tokom
G-027 popravke, NE popravljeni — zasebne stavke, van obima te popravke):**
- Cockpit `sledeca_akcija.prioritet` ("hitan/normalan/odložen") — GPT i
  dalje sam bira prioritet. Isti obrazac kao procena_rizika je bila,
  nije još adresiran.
- Case Genome i drugi moduli koji vraćaju "prioritet"/"hitnost" polja
  direktno iz GPT odgovora — nije sistematski popisano, vredi budući
  audit ako se AR-01 primenjuje šire od ovog jednog fixa.

**Praktična primena:** svaki budući predlog koji dodaje polje sa GPT
kao jedinim izvorom za rizik/status/rok/spremnost/prioritet treba
odbiti u toj formi — tražiti deterministički sloj ispod, LLM samo iznad
njega kao objašnjenje.

---

## Redosled kad Beta Freeze prestane (predlog, ne konačna odluka)

1. **Prvo, nezavisno od pilot signala:** D10, D11 (proveriti/popraviti
   javna obećanja) — ako founder prihvati preporuku o hitnom izuzetku.
2. **Odmah posle prvog pilot feedback ciklusa:** D3, D5, D8, D9 (nizak
   rizik, dizajn gotov, ne zavise jedni od drugih).
3. **Zahteva founderovu eksplicitnu dizajn-odluku pre početka:** D1, D2
   (Faza 1 preduslovi za sve što sledi u rok-automatizaciji).
4. **Tek posle D1+D2:** D4, D6, D7 (rok-automatizacija lanac).
5. **Niži prioritet, kad ima vremena:** D12, D13, D14, D19.
6. **Veće, strateške odluke — čekaju pun pilot ciklus, ne prvi
   feedback:** D16, D17, D18.

---

## Kako se ovaj dokument održava

Kad pilot feedback stigne: (a) ažurirati status svake stavke koja se
menja (npr. Blocked→Deferred kad se D1/D2 dizajn-odluka donese,
Deferred→Accepted kad se implementacija odobri), (b) dodati nove D#
stavke ako pilot otkrije nešto što nijedan dosadašnji audit nije
predvideo, (c) NE pisati novi paralelni "Connectivity Audit V3" za
iste teme — ažurirati ovaj dokument direktno. Duboki dokazi ostaju u
postojećim audit fajlovima (linkovani na vrhu), ovaj dokument je uvek
trenutni presek ODLUKA, ne ponovljena analiza.
