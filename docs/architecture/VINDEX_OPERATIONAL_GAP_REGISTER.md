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
| G-001 | Upload tužbe | `PredmetKreiran` se ne emituje | Event nikad pozvan iz `routers/intake.py` | D3 | Open |
| G-002 | Upload tužbe | `run_case_pipeline()` se ne pokreće za standardni put | Zavisi od G-001 | D9 | Open |
| G-003 | Upload tužbe | Audit ne beleži kreiranje predmeta/upload dokumenta | `predmet_create`/`dokument_upload` nikad pozvani | D22 | Open |
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
| G-026 | Arhitektonski (frontend) | `#t-credits-row` (credit panel vidljivost) povremeno se prikazuje na tabovima gde ne treba (npr. Rokovi), otkriveno ručnim prolazom CONTRACT 01 | Tri nezavisna pisca istog `style.display` — `updateAuthUI()` (bezuslovno, bez provere `activeTab`), `setTab()`, `aiwsSetMode()`; `updateAuthUI()` se poziva iz async Supabase `onAuthStateChange` callback-a koji može razrešiti posle navigacije i prepisati `setTab()`-ovo sakrivanje. Isti obrazac kao D21/D23 (kršenje "jedan poslovni koncept = jedan izvor istine"), sada na frontend UI-state, ne na podacima. | D20.1 (princip; nema poseban D-broj) | Open, **ne blokira CONTRACT 01** |
| G-027 | Arhitektonski (poslovna logika, Pregled predmeta) | Matter Intelligence Bar i Cockpit su nezavisno računali "procesni rizik" za isti predmet | Ekstrahovano u `services/risk_engine.py::calculate_procesni_rizik` — jedini deterministički izvor istine. `routers/matter_intel.py` ga poziva (ponašanje nepromenjeno). `api.py` `/workspace` endpoint ga poziva PRE GPT poziva; Cockpit-ov prompt (`_COCKPIT_SYSTEM`) više ne pita GPT za nivo — dobija ga kao dat kontekst i vraća samo `rizik_objasnjenje` (faktori_plus/minus). | D20.1 + **AR-01 (novo, formalizovano ovom stavkom)** | **CLOSED (2026-07-20)** |
| G-028 | Bug, otkriven usput tokom G-027 popravke | Matter Intel/risk engine `nedostajuci_dokazi` uvek vraća pun spisak očekivanih dokumenata bez obzira na stvarne upload-ove | `predmet_dokumenti` upiti (i u starom `matter_intel.py` i u novom `workspace` endpoint-u) selektuju `naziv_fajla,status` — NIKAD `tip_dokaza` — pa je `postojeci_tipovi` uvek prazan skup. Objašnjava zašto je u G-027 uzorku `nedostajuci_count` bio konstantno 2 za svih 16 predmeta bez obzira na broj/tip dokumenata. | — (nema D-broj, čist bug) | Open, **needs verification da li je select namerno ovakav ili previd**, ne blokira ništa |
| G-029 | AR-01 (novo pravilo) povreda, otkriven usput tokom G-027 popravke | Cockpit `sledeca_akcija.prioritet` ("hitan/normalan/odložen") i dalje GPT sam bira, isti obrazac kao rizik pre popravke | `api.py` `_COCKPIT_SYSTEM` i dalje traži od GPT-a da vrati `prioritet` kao slobodan izbor, bez determinističkog izvora ispod | AR-01 | Open, **nije proveravano empirijski kao G-027 (nema dokaz da se prioritet stvarno razlikuje po pozivima) — proveriti pre popravke, ista disciplina kao G-027** |

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
Detalji u `VINDEX_OPERATING_SYSTEM_CONTRACTS.md` CONTRACT 01.
