# MIR001 FINAL CLOSURE REPORT

**Datum:** 2026-10-22 · **Grana:** `night/miroslav-recovery` (lokalno; NIJE pushovana) · **Osnova:** `origin/main` = produkcija `f33dcce8` · **Kandidat:** `ea1bfba5` + commit ovog izveštaja (C4) · **0 iza / 21 ispred** `origin/main`.
Push, merge, deploy, migracije, promene tajni, Cron i NS007 aktivacija **nisu rađeni niti su odobreni**. Miroslav nije kontaktiran. Svi podaci su sintetički; produkcija je samo ČITANA, isključivo GET (C1 i C4 procena: tip, status, oznake, akter i nazivi fajlova — bez teksta predmeta).

## Konačni status: **READY_FOR_FOUNDER_RELEASE_REVIEW**
Sve četiri korektivne kapije (GATE-C0…C3) su PASS kod nezavisnog reviewera (C1–C3 tek posle 1–2 FAIL prolaza; svi nalazi ispravljeni ili obelodanjeni). Ovo **nije** `PRODUCTION_READY` niti `REAL_USER_ACCEPTED`. Jedan pod-kriterijum C3 je izričito **FAIL** (v. tabelu) — odluka osnivača da li je oznaka-za-proveru dovoljna za kontrolisan pilot.

## Tabela

| Requirement | Scenario | Evidence | Level | PASS/FAIL/BLOCKED | Remaining risk |
|---|---|---|---|---|---|
| C1 — zatvaranje radnje proverljivo (MIR-01/05) | brisanje relevantnog dokumenta (DOK-08) → rok-radnja zatvorena sa `IZVOR_POVUCEN`, izvorom, događajem; audit `prethodno`; nepovezan dokument → ništa; nedokaziva veza → `open` + `dokaz.zadrzano`; replay idempotentan; B ne menja radnje A | `tests/test_mir001_c1_zatvaranje_radnji.py` 10/10; mutacije 10/10; C4 E2E seg. 09–11; produkcija (read-only): izmereno, brojevi lokalno, van javnog repoa; većina otvorenih radnji bez polja veze | ISOLATED (+ read-only prod brojevi) | **PASS** | 70 otvorenih prod radnji bez polja veze: brisanje izvora ih zadržava do sledećeg opšteg događaja; istorijska zatvaranja ostaju bez razloga (bez backfill-a); odluka o trajnom zadržavanju |
| C2 — ekstrakcija iz celog dokumenta (MIR-01) | činjenica iza 4.500. znaka → tvrdnja sa izvorom; Genome je vidi kroz katalog; > 23.000 znakova → `potpuno: False`; pad/prekid prozora → nepročitan; 2 dokumenta protivreče; bez duplikata; OCR nepromenjen | `tests/test_mir001_c2_ceo_dokument.py` 10/10; mutacije 12/12; **stvaran gpt-4o-mini**, gust sintetički dok. 16.082 zn., priznanje u 4. prozoru: stari upit 0/5, novi **5/5 tvrdnja i 5/5 locirana**, 99/100 činjenica locirano, 1/100 pogrešan datum (lokator ga ne locira); C4 E2E seg. 02–04 | ISOLATED + stvaran model (k/5, 1 sintetički dokument) | **PASS** | > 23.000 zn. delimično (zabeleženo); 20 tvrdnji/dok. (odbacivanje zabeleženo, kod gustog 14–20); Genome katalog 60 → PARTIAL češće; trošak ≈ 3× ulaz / 4–5× izlaz po dugom dokumentu; stari dokumenti nisu ponovo čitani |
| C3a — nacrt ne traži / ne protivi se već odlučenom (MIR-03) | Golden Case: sud je u DOK-07 prihvatio dopunu veštačenja; zadatak: izjašnjenje na DOK-05/06 | stvaran gpt-4o, **slepo čitanje** (`mir001_c3_model/SLEPE_OZNAKE.md`): pre 10/15 → posle **0/40**; DOK-07 naveden 40/40; `tests/test_mir001_c3_procesno_stanje.py` 9/9; mutacije 15/15; C4 E2E seg. 06–08 | ISOLATED + stvaran model (k/N, 1 slučaj) | **PASS** | jedan sintetički slučaj, jedna vrsta odluke; odluke prepoznate obrascem |
| C3b — nacrt ne iznosi samouverenu tvrdnju suprotnu odluci (MIR-03) | isto | slepo: „naložena mera nije potrebna“ pre 11/15 → posle **20/40**; provera posle modela označava na mestu **18/20**, 2 neoznačena (+9 graničnih) | ISOLATED + stvaran model | **FAIL** (ublaženo oznakom, ne sprečeno) | advokat mora pročitati svaku oznaku i napomenu; promašaji provere i istekao rok (G1) neotkriveni |
| C3c — negativni scenario (bez odluke) | DOK-07 obrisan rutom | bez bloka, bez oznake; stvaran gpt-4o 5/5 normalno argumentuje, 0/5 izmišlja odluku | ISOLATED + stvaran model | **PASS** | greške izvora u istom skupu (izmišljeno mesto, nalaz pripisan tuženom) |
| C4 — jedan E2E: dug dokument + ranija odluka + brisanje izvora | `tests/test_mir001_c4_e2e.py` (isti proces, baza, korisnik, predmet) | **12/12 segmenata, 2 uzastopna pokretanja** | ISOLATED | **PASS** | zamenjeni: pozivi modela, Pinecone, Supabase i prijava (baza u memoriji), atomski RPC brisanja (Python zamena, ne SQL funkcije 131/133/137), dozvole i naplata, `audit.log_action`, ocena kvaliteta nacrta, `asyncio.create_task` u savetniku — stvarna baza i SQL RPC brisanja nisu u ovom toku |
| Regresija (uz 14 izmenjenih postojećih testova — spisak i razlozi u ledger-u C4) | pun Python paket (izolovan PG) + V2 frontend | **16 failed / 11.836 passed / 318 skipped**: 15 = identičan nasleđeni skup osnove + 1 prolazni Playwright timeout (`Page.goto`, sam 3/3, fajl 5/5); V2 frontend **51/51** skripti (3 uz lokalni `serve.mjs`, kao TASK-10) | LOCAL | **PASS** (0 novih padova) | — |
| Bojanovi tokovi | Smart Intake → predmet → OCR → klasifikacija → hronologija → rokovi/podsetnici → radnje → AI pregled | svi testovi tog lanca u punom paketu prolaze (osb002 solo tok, ns005 t11/t14, smart_intake*, rokovi*, hronologija, podsetnici) | LOCAL | **PASS** (tok radi) — ponašanje IZMENJENO u: klasifikaciji, rokovima, radnjama, AI pregledu (Genome, savetnici), pregledu nacrta, autonomiji — v. „Izmene Bojanovog toka“ | izmene su namerne; Bojan ih nije video |
| MIR-04 korporativni rad | — | TASK-09 inventar | — | **BLOCKED_REQUIREMENTS_DETAIL** | čeka pitanje Miroslavu |
| MIR-05 autonomija u produkciji | NS007 | migracija 136, tajna, Cron, budžet — nije ništa urađeno | — | **BLOCKED_AUTHORITY** | — |
| LIVE (prijavljen tok u produkciji) | — | — | — | **NOT_RUN** | nema QA naloga |
| REAL_USER_ACCEPTED | — | — | — | **NOT_RUN** | — |

## Rešena ograničenja (ovaj sprint)
- **LIM-MIR-03-1** (klasifikator vidi 1.500 znakova, ≤ 5 činjenica) → prozori do ≈ 23.000 znakova, ≤ 20 činjenica, eksplicitno stanje čitanja (C2).
- **TASK-07 ogr. 4** (zatvorena radnja nema razlog) → razlog, izvor, događaj na redu i u auditu, sa prethodnim stanjem (C1).
- **DEBT-MIR-06-1** (3–4/5 nacrta predlaže već odlučeno) → izričit zahtev/protivljenje 0/40 (C3a); samouverena tvrdnja i dalje 20/40, označena 18/20 (C3b — NIJE rešeno do kraja).
- Genome je tiho skraćivao dokument > 4.500 znakova → eksplicitna oznaka „TEKST SKRAĆEN“.

## Izmene Bojanovog toka (tok radi; ponašanje se menja)
- *Klasifikacija* (C2): novi dokumenti se čitaju celi (prozori, ≤ 6 poziva, ≤ 20 tvrdnji, nov upit, `_ekstrakcija`).
- *Rokovi* (TASK-07): rok iz obrisanog dokumenta se ne nudi na potvrdu (`/api/rokovi/kandidati` `izvor_povucen`, Danas bez „Potvrdi“).
- *Radnje* (TASK-07 + C1): legacy grana protivrečnosti isključena za predmete sa V2; protivrečnost iz obrisanog dokumenta se preskače; brisanje izvora zatvara samo radnje sa dokazivom vezom, uz razlog (`dokaz.zatvaranje` / `zadrzano`); `SourceInvalidated` bez izvora i brisanje ročišta bez `dokaz.rociste_id` ne zatvaraju radnju.
- *AI pregled — Genome* (TASK-03 + C2): sporne tačke se ne zatvaraju kad model nije video sve tvrdnje; do 60 tvrdnji u katalogu; zaglavlje „TEKST SKRAĆEN“.
- *AI pregled — savetnici* (TASK-04/05 + C3): ceo spis (do 12 dok.) i sporne tačke u kontekstu, današnji datum, bez „Snaga predmeta %“; parnična strategija sa procesnim stanjem; nacrt sa blokom procesnog stanja i oznakama protivrečnosti.
- *Pregled nacrta* (TASK-06): nacrt savetnika iz spisa ide na staging; odobren `nacrt_iz_spisa` se NIKAD ne indeksira u bazu znanja.
- *Autonomija* (TASK-08): `CASE_CHANGE_BRIEF` registrovan u NS007 (u produkciji ne radi bez migracije 136 i Cron-a).

## Preostala ograničenja (sažetak; pun spisak u ledger-u C1–C3)
- C1: radnje bez polja veze (većina otvorenih u produkciji) se pri brisanju izvora zadržavaju; zatvaraju se odloženo sledećim opštim događajem uz `posle_zadrzavanja`; čuva se samo poslednje zadržavanje; motor rizika može otvoriti novu radnju pored zadržane.
- C2: delimično čitanje > 23.000 znakova; 20 tvrdnji/dok.; Genome katalog 60; model može pogrešno pripisati podatak (lokator hvata); `reklasifikuj` duplira tvrdnje (zato NE preporučujemo ponovno čitanje starih dokumenata bez odluke); upit važi za sve dokumente (vrsta merena na 7 kratkih sintetičkih: identično).
- C3: (B) 20/40 nacrta, provera je leksička (2 promašaja + poznati obrasci koje ne vidi, implicitan zahtev „odluka na osnovu postojećeg nalaza“, ponovni predlog već prihvaćenog); **istekao rok (G1) niko ne proverava**; ponovljeno povlačenje; datum ročišta izostaje; DEBT-MIR-06-2 (nalaz veštaka kao „utvrđen“); samo `/api/agents/run` drafting.
- Raniji dugovi MIR001 (ledger TASK-10) ostaju osim gore rešenih.
- Sve mereno na JEDNOM sintetičkom predmetu; pouzdanost nad stvarnim spisima je UNKNOWN.

## Migracije potrebne za puštanje
**Nijedna** za ovu granu (`git diff f33dcce8..HEAD -- migrations/` prazno). NS007 aktivacija (ako se odobri) traži migraciju 136 — van ovog puštanja.

## Mogući uticaj na produkcione podatke
- Bez izmene šeme. Novi kod upisuje nove ključeve u postojeće JSONB kolone: `case_actions.dokaz.zatvaranje` / `zadrzano`, `predmet_dokumenti.ai_tags._ekstrakcija` — stari kod ih ignoriše.
- Radnje: brisanje izvora više ne zatvara radnje bez dokazive veze (većina otvorenih danas); istorijska zatvaranja ostaju bez razloga.
- Dokumenti: samo NOVO otpremljeni čitaju se celi (više tvrdnji, ≤ 6 poziva gpt-4o-mini po dugom dokumentu); postojeći ostaju kakvi jesu.
- Genome: češće PARTIAL (više tvrdnji naspram granice 60) — eksplicitno.
- Nacrti savetnika `drafting` sa predmetom: blok procesnog stanja (+≈ 250 tokena) i oznake `[PROVERITI PROCESNO STANJE: …]` u tekstu.
- NS007: `case_change_brief` je registrovan, ali ciklus autonomije u produkciji NE radi (nema migracije 136 ni Cron-a).
- **Masovno zatvaranje pri prvom usklađivanju posle puštanja (TASK-07 ogr. 9):** na predmetima sa V2 spornim tačkama otvorene LEGACY radnje protivrečnosti i radnje roka čiji je dokument već obrisan zatvoriće se pri prvom usklađivanju, sa opštim razlogom `CINJENICA_VISE_NE_VAZI`. **Izmereno read-only 2026-10-22 (`MIR001_C4_PROD_PROCENA.py`): 0** — (a) protivrečnosti: 3 otvorene, 0 legacy, 0 legacy na predmetu sa V2 (2 predmeta sa V2 spornim tačkama); (b) radnje pregleda roka (`PLANIRATI_ROKOVE`, izvor hronologija): 4 otvorene, 0 ispunjava pravilo `izvor_povucen` — meriti ponovo neposredno pre puštanja.

## Plan kontrolisane produkcione E2E provere (NIJE izvršen — traži odluku i QA nalog)
0. PRVO, i ponovo posle deploy-a (pre/posle) — `MIR001_C4_PROD_PROCENA.py` i, read-only: broj otvorenih `case_actions` po tipu za SVE korisnike i broj otvorenih legacy radnji protivrečnosti na predmetima sa V2 — svaka razlika osim QA predmeta se objašnjava pre nastavka; broj `autonomy_work_items` tipa `CASE_CHANGE_BRIEF` mora ostati 0 (NS007 nije aktiviran); QA nalog mora imati `v2_pristup`.
1. Osnivač odobri puštanje i QA nalog (zaseban korisnik, nikad stvarni klijent).
2. Posle deploy-a: `/health` = SHA kandidata.
3. QA nalog: nov sintetički predmet → otpremi Golden Case (7 PDF + sken) i dug sintetički dokument (C4 `DUG`) → proveri u `genome-v2`: kasna tvrdnja postoji, `citanje.potpuno`.
4. `/api/agents/run` drafting nad predmetom → poruka nije vidljiva, ali odgovor nosi DOK-07 / oznake; nacrt na pregledu ima napomenu.
5. Otpremi DOK-08 → rok-radnja; obriši DOK-08 → `/api/case-actions/predmeti/{id}`: radnja zatvorena, `dokaz.zatvaranje.razlog = IZVOR_POVUCEN`.
6. Obriši ceo sintetički predmet; proveri da nema ostataka tvrdnji/radnji; QA nalog deaktivirati.
Nijedan korak ne dira stvarne korisnike; trošak: nekoliko poziva gpt-4o-mini i jedan gpt-4o.

## Plan povlačenja (rollback)
- Kod: Render rollback na `f33dcce8` (prethodni deploy) — bez migracije nema šta da se vraća u bazi.
- Podaci upisani novim kodom su kompatibilni unazad (dodatni JSONB ključevi, tekst nacrta). Posle povlačenja stari kod ponovo zatvara radnje bez razloga (stanje pre C1) i ponovo čita 1.500 znakova novih dokumenata.
- **Rizik 1 — staging:** stari kod (`_ponovni_upis_moguc`, `staging_ponovi_upis`) ne proverava `tip`; odobren `nacrt_iz_spisa` sa ocenom ≥ 0,85 mogao bi posle povlačenja kroz rutu ponovnog upisa da uđe u bazu znanja kancelarije (što TASK-06 zabranjuje). Pre povlačenja: read-only broj `staging_memory` sa `tip = nacrt_iz_spisa` i `status = approved`; ako je > 0 — ne povlačiti bez ručne zaštite tih redova (odluka osnivača).
- **Rizik 2 — radnje:** posle povlačenja stari kod usklađuje radnje po starim pravilima; radnje zatvorene ili zadržane novim kodom mogu se ponovo otvoriti ili zatvoriti bez razloga (korisnik vidi „treperenje“). Pre i posle povlačenja izmeriti broj otvorenih radnji po tipu.
- Sintetički QA predmet obrisati rutom brisanja predmeta.

## Odluke osnivača
1. Pregled i puštanje grane `night/miroslav-recovery` (21 commit od `f33dcce8`): push/PR/merge/deploy — **nije urađeno**.
2. **C3b**: da li je oznaka-za-proveru (18/20 označeno, 2 ne) prihvatljiva za kontrolisan pilot sa obaveznim pregledom advokata, ili se nacrt iz spisa ne pušta Miroslavu dok se (B) ne smanji.
3. C1: odloženo zatvaranje zadržanih radnji (preporuka) naspram trajnog zadržavanja (traži ručno zatvaranje u V2 — nova funkcionalnost).
4. C2: ponovna klasifikacija starih dokumenata — NE bez odluke (duplira tvrdnje); prihvatanje troška ≈ 3–5× po dugom dokumentu.
5. QA nalog za kontrolisanu produkcionu E2E proveru (plan gore).
6. Da li i kada Miroslav dobija pilot (sintetički ili anonimizovan spis) uz pisano upozorenje za C3b, G1 (istekao rok) i DEBT-MIR-06-2.
7. NS007 aktivacija — posle 1–6; MIR-04 pitanje Miroslavu (TASK-09).

## Tačni SHA-ovi
`origin/main` = produkcija: `f33dcce812c655807ee90f06f11a8f772c6bc6c3`
MIR001 (TASK-00…10): `c9ba6abb` `b58d604a` `5b3a56ba` `4b6c19aa` `b549b9fc` `d5c7a6c0` `d0862d00` `3c4ae1ea` `150feb7f` `c474e3b5` `0ae5fa4b` `6d51793a` `2a2312b2` `0aa47350` `1a74f85b` `cd83b789`
FINAL CLOSURE: C0 `645dc4fe` · C1 `a30de1b2` · C2 `3c8e1de8` · C3 `ea1bfba5a7e4059e7462d7c816762f9c44f79a24` · C4 = commit koji dodaje ovaj izveštaj (`git log -1 night/miroslav-recovery`).
