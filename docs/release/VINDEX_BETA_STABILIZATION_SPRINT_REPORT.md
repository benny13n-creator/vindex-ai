# VINDEX — Beta Stabilization Sprint — završni izveštaj (15.10.2026)

**Osnova:** `origin/main` = `3ab9343e` (provereno pre i posle sprinta; nepromenjen).
**Verdikt:** `PARTIAL_WITH_EXPLICIT_HOLDS` — tri ispravke spremne za pregled osnivača (PR #37, #38, dopunjen #36) uz PR #35; QA-02B, QA-04, QA-01 i opcioni UX zadatak su HOLD sa razlogom.
Ništa nije spojeno, ništa nije pušteno, nema migracija, nema upisa u produkciju, produkcioni QA predmet nije diran.

## 1. Pregled

| Task | Status | Uzrok | Promenjeni fajlovi | Testovi | Nezavisni pregled | Rizik | PR |
|---|---|---|---|---|---|---|---|
| 01 QA-05 JPG/PNG prikačivanje | ISPRAVLJENO | `UploadedDocChunk.source_format` = `pdf/docx/txt`; Smart Intake i `api.py` šalju `jpg/jpeg/png` → ValidationError posle OCR-a (Smart Intake 0/1, `api.py` 500) | `uploaded_doc/schema.py` (+test) | 37 + 2 (Tesseract, CI); bez ispravke 18 pada; ceo paket 19 = `main` | GO WITH NOTES (nalaz ispravljen) | nizak | #37 |
| 02A QA-02 klasifikacija | ISPRAVLJENO | heuristika: prva vrsta iz liste sa ključnom reči bilo gde u 400 znakova; „TUŽBE“ nije ključna reč | `shared/intake_classify.py` (+test) | 35 novih + postojeći; 553/3 = `main` | GO WITH NOTES (preporuka ugrađena) | nizak–srednji (v. §4) | #38 |
| 02B ljudska ispravka vrste | HOLD | Evidence Vault i „Reklasifikuj“ prepisuju `tip_dokaza`; nema mesta za poreklo ljudske odluke | — | — | — | — | odluka |
| 03 QA-03 PR #36 dopuna | ISPRAVLJENO | `VxNazivi` direktno korišćen → bez `nazivi.js` ekrani pucaju; vrsta predmeta/uloga sirove | `index.html`, `nazivi.js`, `app.js`, `law-brain.js`, `analiza-predmeta.js` (+testovi) | e2e 53/53; 17 Playwright paketa 0 FAIL; akteri/vrste 7/7 | GO WITH NOTES (preporuke ugrađene) | nizak | #36 (`62fc2625`) |
| 04 QA-04 Genome protivrečnost | HOLD (dokazano otvoreno) | sadržaj protivrečnosti i `tezina` daje model; deterministička provera postoji samo za reference | — | — | — | srednji | — |
| 05 QA-01 rokovi | HOLD (odluka) | v. §5 | — | — | — | — | — |
| 06 UX „Nov klijent u kartoteci“ | HOLD (predlog) | dugme bez okvira, vidljivo tek posle „Poveži klijenta“; tastatura već radi (`<button>`) | — | — | — | — | — |
| 07 Integracija / CI | URAĐENO | — | ovaj izveštaj | v. §6 | — | — | — |

## 2. Diff, reprodukcija i dokazi po PR-u

### 2.1 PR #37 — fotografija (base `3ab9343e`, head `08990674`)
- **Pre:** `chunk_document(..., source_format="jpg")` → `1 validation error for UploadedDocChunk` (isti tekst kao produkcija); kroz stvarne rute: finalize 0/1, posao `completed`, `predmet_id` postavljen, `assimilation_complete=false`, `finalizing_at=NULL` — tačno produkciono stanje.
- **Posle:** upload → OCR → pregled → finalize → tačno jedan `predmet_dokumenti` red (`source_intake_job_id`, `content_sha256` = heš teksta, tekst sa ćirilicom, `status=indeksirano`), posao `assimilation_complete=true`.
- Nastavak starog posla **bez ponovnog otpremanja**: u postojeći predmet i u nov predmet (jedan predmet, jedan dokument, jedna audit radnja `document_assimilated`, nijedan događaj dvaput).
- Ponovljen finalize: `already_finalized`, ništa novo (dokumenti, predmeti, događaji, audit). Paralelni finalize (stvarne niti, barijere): jedan dokument, gubitnik 409/503.
- Greška baze → `NIJE_PRIKACENO`, `ok:false`; ponovni pokušaj prolazi. Nepotpun/pao vektorski upis → dokument `sacuvano`, nikad `indeksirano`.
- Isti sadržaj u drugom predmetu → ne povezuje se automatski. Dva korisnika → svaki svoj predmet i namespace; tuđ posao → 404.
- TIFF preimenovan u .jpg, lažni PNG, GIF → odbijeni pri otpremanju, bez posla. Memorijske zaštite (`extract_image`) netaknute.
- `api.py` otpremanje fotografije u predmet sada stiže do vektorskog upisa (pre: izuzetak).
- Pregled: svi formati koji stižu do `chunk_document` su malim slovima i u novom skupu; `source_format` se nizvodno koristi samo kao oznaka u Pinecone metapodacima. Mutacije (samo jpg, jpg+jpeg, bez txt, bilo koji string) uhvaćene.

### 2.2 PR #38 — klasifikacija (head `7588fce4`)
- **Pre:** PREDLOG TUŽBE → `contract`; ODGOVOR NA TUŽBU koji pominje „TUŽBA“ → `lawsuit`; ZAPISNIK/POTVRDA sa „UGOVOR br.“ → `contract`; UGOVOR koji pominje TUŽBA → `lawsuit`.
- **Posle:** lawsuit / response / None (model) / contract; ćirilica, latinica, bez dijakritika, genitiv „TUŽBE“, razmaknut naslov, redni broj i navodnici.
- Kroz stvaran worker (digitalni PDF): `intake_documents.document_type`, `classification_method` i pouzdanost (0.85 heuristika / model) zadržani.
- Pregled na 79 zaglavlja: 24 ispravljeno, 23 isto tačno, 18 isto pogrešno kao ranije, 11 → model umesto heuristike (naslov malim slovima), 3 nova lažna pozitiva (§4).

### 2.3 PR #36 — dopuna (`adc0d79f` + `62fc2625`, bez force push-a)
- **Pre (mutacija bez rezerve):** sa 404 za `nazivi.js` lista dokumenata, predmet, hronologija, analiza, znanje i prijem ostaju prazni (8 provera pada).
- **Posle:** rezerva u `index.html` bez ijednog prevoda: „„contract“ (srpski naziv nije učitan)“, akter kako je upisan; 0 JS grešaka; podaci identični.
- Vrsta predmeta: `opsti` → „Opšti“, `parnicno` → „Parnični“, `radni` → „Radni“; tekst advokata doslovno; šifra sa „_“ van rečnika → „Nepoznata vrsta predmeta (oznaka …)“.
- Uloga koju backend odbaci (`uloga_neispravna`) → „uloga iz analize nije prepoznata“ (ranije pogrešno „uloga nije navedena“).
- `tests/test_qa03_nazivi_akteri.py`: svih 10 internih potpisa `akter` iz backend-a ima srpski naziv; nijedan ne tvrdi potvrdu; AI ostaje AI; šablon nije AI; ljudski potpisi (Advokat, „Automatski — ZPP lanac“, ime advokata) doslovno.
- Rezerva se uključuje i za delimičan stariji rečnik (bez novih funkcija) — e2e proverava. Šifre `gradjansko`, `izvrsenje` (šabloni prijema) i `clio_import` (uvoz) imaju naziv; test vezuje `nov-predmet.js::KLJUC` za rečnik vrsta.
- Pregled: rezerva dokazana za 404, HTML umesto JS i JS sintaksnu grešku; CSP dozvoljava inline skriptu; nijedan postojeći test je ne zabranjuje. Mutacije (bez rezerve, pogrešna vrsta, „potvrdio“ u nazivu aktera, AI izbačen iz naziva) uhvaćene. **GO WITH NOTES.**
- Prva verzija pravila „mala slova = šifra“ oborila je `live-law-brain` (vrednost `radni` iz starog /app) — pravilo suženo na šifru sa „_“; test sada očekuje „Radni“.

## 3. Testovi (stvarni rezultati)
- Python, ceo paket na grani PR #37: **19 failed / 10.657 passed** — skup padova identičan baznoj liniji `main`.
- Python intake skup na grani PR #38: 553 passed, 3 failed (`test_coi_intake_convergence::test_t8_*[trio]`, isto na `main`: trio nije instaliran lokalno).
- Playwright na PR #36 (`adc0d79f`; posle `62fc2625` ponovljeni nazivi 53, law-brain 45, matter 56, analiza 43, brand 335, verify 98): live-matter 56, live-prijem 53, prijem-pracenje 29, analiza 43, rad-predmeta 44, danas 53, isolation 25, matters 64, verify 98, brand-identity 335, pregled-zivi 30, radna-lista 25, prijem-carobnjak 37, prijem-oporavak 18, rok-odluka 75, law-brain 45, nazivi 51 — **0 FAIL**. Pregledač dodatno: session-contract 33, live-nov-predmet 41.
- Stvaran Tesseract za JPG/PNG: **nije izvršen lokalno** (2 testa preskočena); izvršava ga CI posao „Production Runtime Parity“ ako se doda u njegovu listu (v. §7).

## 4. Preostali rizici
- **PR #38:** red velikim slovima koji počinje ključnom reči PRE pravog naslova (memorandum „RAČUN: 205-…“, „REŠENJE Iv 55/24“ pre ŽALBE) daje pogrešnu vrstu sa 0.85. Ublaženo: 0.85 < prag 0.90 → uvek pregled advokata. Naslovi malim slovima idu modelu (trošak, ne pogrešan tip). OCR koji meša pisma u stop-reči (latinično „A“ u „ЗAПИСНИК“) nije pokriven.
- **PR #37:** stvaran OCR fotografije je dokazan samo sintetički (OCR zamenjen na granici); produkcioni fajl 05 NIJE ponovo testiran. Ako upis `original_filename` izostane, sufiks pada na `.pdf` (stari dug).
- **PR #36:** u režimu bez rečnika akter se prikazuje kako je upisan (npr. „Template (AI)“) — isto kao pre PR-a. Nepoznata vrsta predmeta bez „_“ (npr. tekst advokata) prikazuje se doslovno, bez napomene. `/v2/preview` (mutable keš) nije proveren u produkciji.
- **PR #35:** v. §6.

## 5. HOLD paketi za odluku osnivača

### 5.1 QA-02B — ljudska ispravka vrste dokumenta
Dokazano ponašanje:
1. U prijemu se vrsta čuva u `intake_documents.document_type` (engleski skup); postoji ispravka samo za izdvojena polja (`/entities/{id}/correct`), ne za vrstu.
2. Na finalize se upisuje `predmet_dokumenti.tip_dokaza = document_type`.
3. Ako klasifikacija NIJE nesigurna, događaj `NEW_EVIDENCE_REGISTERED` pokreće Evidence Vault (`routers/evidence.py::klasifikuj_i_sacuvaj`), koji **prepisuje** `tip_dokaza` srpskom vrstom iz modela. Isto radi ručno „Reklasifikuj“.
4. Heuristika daje 0.85 < 0.90 → dokument je „nesiguran“ → Evidence Vault se preskače i engleska vrsta ostaje trajno (to je razlog trajnog `contract` u beti).
5. Ne postoji kolona koja kaže da je vrstu izabrao čovek; zato bi svaka ručna ispravka bila tiho pregažena sledećom AI klasifikacijom.

Najmanji bezbedan mehanizam (predlog, nije implementiran): kolona porekla vrste (`tip_dokaza_izvor` = `ai|covek`, ko, kada) + pravilo da Evidence Vault/Reklasifikuj ne prepisuje vrstu sa poreklom `covek` + audit radnja `tip_dokaza_ispravljen`. **Traži migraciju → HOLD.** Odluka: da li odobravate migraciju i pravilo „ljudska vrsta je konačna dok je čovek ne promeni“.

### 5.2 QA-04 — Case Genome protivrečnost
- Put: Genome prompt (`routers/case_dna.py`) → model vraća `kontradikcije[]` sa `claim_refs`, `relation_type`, `tezina` → `claim_ids` se razrešavaju kroz katalog tvrdnji (fail-closed: nepoznata/tuđa/duplirana referenca → odbačeno; traže se ≥ 2 različite tvrdnje ovog predmeta) → V2 materijalizacija.
- „Kritična“ = `tezina` modela; nepoznata vrednost → `kriticna` namerno (`shared/contradiction_identity.py::normalize_tezina`).
- OPEN → „više se ne opaža“ kad je novi refresh ne vidi; UI to razlikuje od „razrešena“ (`STANJE_K`). Kartica nosi oznaku „Analiza (AI)“ i izvor svake tvrdnje.
- Lažna protivrečnost iz bete (dve tvrdnje dokumenta 01: „Ugovor o isporuci opreme“ / „Isporuka 12 monitora“) prolazi sve determinističke provere — to su dve stvarne, različite tvrdnje. Da li se kose, odlučuje model. **Nije reprodukovano bez stvarnog poziva modela; nema uske determinističke ispravke.** Zabrana protivrečnosti unutar jednog dokumenta bi bila pogrešna.
- Predlog acceptance testa: korpus sintetičkih parova (neutralne tvrdnje istog dokumenta / stvarni sukob iznosa i datuma) kroz stvaran prompt, N ponavljanja; meri se stopa lažnih „kritičnih“. Predlog pravila za odluku: AI protivrečnost se prikazuje kao „traži vaš pregled“ dok je advokat ne potvrdi, a „kritična“ samo kada su obe tvrdnje vezane za konkretan citat. Odluka osnivača.

### 5.3 QA-01 — semantika rokova (samo specifikacija)
Dokazano (sintetički predmet `QA-TEST-20261015`, read-only metapodaci):
- Pipeline (AI) je iz opisa predmeta (470 znakova) upisao 3 `vrsta=rok` kandidata (15.08 kritičan, 01.09 kritičan, 24.08 važan); važnost daje model (`services/case_pipeline.py`).
- Smart Intake je iz ugovora dodao 15.08 „Rok iz dokumenta (ugovor)“ sa fiksnom važnošću „važan“ (`routers/smart_intake.py::_rok_iz_dokumenta`); duplikat se prepoznaje samo za isti izvorni fajl + datum + naziv (N03-FD2), ne po datumu.
- Odbijanje osnivača je zapisano kao `ManualCorrectionApplied rok_odluka` i ostaje u istoriji.

Najmanje pravilo (predlog):
1. Svaki kandidat nosi **vrstu datuma**: `datum_dogadjaja` (npr. isporuka 24.08), `ugovorna_obaveza` (isporuka do 15.08), `procesni_rok` (zakon/sud), `interna_radnja` (advokat). Model predlaže, advokat potvrđuje; bez potvrde nijedna nije obaveza.
2. Važnost AI kandidata se ne prikazuje kao „kritičan“ dok ne postoji izvor (zakonski osnov ili citat); do tada „nije procenjeno“.
3. Dva izvora za istu obavezu se **povezuju kao dokaz**, ne spajaju: spajanje samo odlukom advokata; isti datum nikad nije dovoljan.
4. Odbijen kandidat se ne obnavlja automatski iz drugog izvora sa istim datumom; novi izvor pravi nov kandidat koji pokazuje da je raniji odbijen.

Primeri: 15.08 iz opisa i 15.08 iz ugovora → jedna `ugovorna_obaveza` sa dva izvora (ako advokat poveže); 24.08 → `datum_dogadjaja`; 01.09 → `datum_dogadjaja` relevantan za tvrdnju, ne rok.
Negativni slučajevi: dve nezavisne obaveze istog datuma (isporuka i plaćanje 15.08) ne smeju se spojiti; procesni rok iz dostavnice ne sme dobiti važnost „važan“ fiksno bez izvora.
Rizici: pogrešna vrsta „datum_dogadjaja“ za stvarni procesni rok → propušten rok (zato bez potvrde ostaje vidljiv kao kandidat); previše kandidata → zamor.
**Odluka koja se traži:** (a) odobravate li 4 vrste datuma, (b) zabranu automatske važnosti „kritičan“ bez izvora, (c) povezivanje izvora bez spajanja. Bez izmene 78 istorijskih zapisa i bez novih podsetnika.

### 5.4 Opcioni UX
„Nov klijent u kartoteci“ je `<button>` (tastatura radi), ali bez okvira i vidljiv tek u panelu „Poveži klijenta“. Predlog: postojeća varijanta `text-btn--line` (okvir, isti stil kao „Poveži klijenta“). Odluka o izgledu → HOLD; nije mešano u PR #36.

## 6. Integracija i CI
| PR | base | head | CI | Padovi naspram `main` |
|---|---|---|---|---|
| #35 forenzika identiteta | `3ab9343e` | `6da18ded` | Test Suite ✗, Runtime Parity ✗, Security ✓ | pytest 3.11/3.13: 174 = isti ID-jevi kao `main`; Parity 195 = isti ID-jevi |
| #36 srpski nazivi | `3ab9343e` | `62fc2625` | ranije `54a07e14`: isto kao #35; nov head čeka CI | isto kao `main` (za `54a07e14`) |
| #37 fotografija | `3ab9343e` | `08990674` | čeka CI | lokalno ceo paket = `main` |
| #38 klasifikacija | `3ab9343e` | `7588fce4` | čeka CI | lokalno intake skup = `main` |

`main` (`3ab9343e`) sam ima crven Test Suite i Runtime Parity (174/195 padova, pre ovog sprinta); ovaj sprint ih ne menja.
PR #35: kriterijumi ispunjeni (31 test, mutacije ubijene, ceo paket = `main`, pregled GO WITH NOTES) → preporuka za pregled osnivača kao zaseban kandidat.

Preklapanja: #36 (frontend), #37 (`uploaded_doc/schema.py`), #38 (`shared/intake_classify.py`), #35 (`services/event_bus.py`) ne dele nijedan fajl → spajanje bez konflikata.

## 7. Predlog redosleda i rollback
1. **#37** (P0, jedan red koda). Posle deploy-a, ručno: ponovo „Prikači“ na postojećem QA poslu za fajl 05 (nastavlja bez ponovnog otpremanja) → očekivano 1/1, dokument u predmetu, `assimilation_complete=true`.
2. **#38** — nova klasifikacija važi samo za NOVE dokumente; stari zapisi ostaju.
3. **#36** — samo prikaz.
4. **#35** — forenzika identiteta.
Rollback: svaki PR je nezavisan revert jednog merge commit-a; nijedan nema migraciju ni promenu podataka. Revert #37 vraća grešku 0/1 za fotografije (podaci ostaju ispravni). Revert #38 vraća staru heuristiku. Revert #36 vraća engleske oznake.
Preporuka pre #37: dodati `tests/test_qa05_slika_finalize.py` u listu OCR testova posla „Production Runtime Parity“ da stvaran Tesseract izvrši JPG/PNG tok (izmena workflow-a nije rađena bez odobrenja).

## 8. Uslovi za nastavak ručnog beta testa
- Posle deploy-a #37: fajl 05 kroz postojeći posao (bez novog upload-a); zatim nov JPG i PNG sa telefona.
- Posle #38: ponovo otpremiti 02 (predlog tužbe), 04 (zapisnik), 05 (potvrda) u NOV test predmet; očekivano: tužba / model (ne `contract`) / model.
- Posle #36: dosije, hronologija, analiza, prijem i Znanje bez engleskih oznaka; hard refresh.
- Rokovi i Genome protivrečnosti ostaju pod HOLD; u beti ih tretirati kao AI predloge.
