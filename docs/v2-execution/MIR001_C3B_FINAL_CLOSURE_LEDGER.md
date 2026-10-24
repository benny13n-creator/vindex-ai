# MIR001 C3b FINAL CLOSURE — kontrolisan sudski nacrt (ledger)

Zadatak osnivača: „MIR001 C3b FINAL CLOSURE — CONTROLLED LEGAL DRAFTING — ONE BOUNDED IMPLEMENTATION“ (2026-10-24).
Pristup: **AI RADNI PREDLOG → IZRIČITO USVAJANJE ADVOKATA → DOKUMENT ZA SUD.** Jedan ograničen pokušaj; ishod je
`C3B_CONTROLLED_DRAFTING_READY` ili `C3B_AUTOMATED_COURT_DRAFTING_DISABLED`.

Prethodni ledger: `MIR001_C3B_STRUCTURAL_LEDGER.md` (GATE-03 `C3B_FAIL`, `strukturalno/t03/GATE03_RECENZIJA.md`).
Dijagnoza GATE-03 se ovde ne otvara ponovo.

## TASK-00 — zamrzavanje neuspele arhitekture

**Početno stanje (provereno):**
- grana `night/miroslav-recovery`, HEAD `81bd7684`;
- radno stablo čisto;
- `origin/main` = `f33dcce8` (`git ls-remote`);
- grana je 41 commit ispred `origin/main`, 0 iza.

**Popis C3b commitova (`c4cf8008`..`81bd7684`) i odluka:**

| Commit(i) | Šta je | Odluka |
|---|---|---|
| `c4cf8008`, `72dc01a4`, `544f778f`, `caa997c4`, `900643de`..`81bd7684` | reprodukcije, slepa merenja, harness, ledger | **zadržano** (dokaz) |
| `589cd4f0` → `b93cd739` | pravila procesnog stanja u uputstvu modelu → selektivno vraćeno posle GATE-03 FAIL | već izolovano |
| `744911fa`..`41c52c00` | `shared/procesno_stanje`: identitet dokumenta, doslovan izvod (sha + pomeraj, `potvrdi_izvod`), tumačenje nikad `VERIFIED` | **zadržano** (serverska činjenica o izvoru, ne o pravu) |
| `18a235a6` (deo) | JSON razdvajanje teksta modela i napomena, serverska `GRANICA`, DOCX samo iz SAČUVANOG teksta (`POST /api/staging/{id}/docx`, vlasnik), zabrana granice u slobodnom izvozu | **zadržano** |
| `3b3d7f77` (deo) | obrada pre naplate (502 bez naplate i bez upisa), `/run-parallel` ne pravi nacrt iz spisa | **zadržano** |
| `18a235a6`, `3b3d7f77`, `7b2ac201`, `6b4aa0c9`, `398bedd6`, `78301e71` (kapija) | `shared/nacrt_za_sud.zastiti`: leksički detektori, pravilo predmeta, polaritet, čuvari `[IZOSTAVLJENO I-n]` | **povučeno iz toka** |

Kapija je povučena zbog dokaza iz GATE-03: ista heuristika i propušta i briše. Potvrđeni M1/M2/M5/M7 su prošli kroz
nju, a P4 suzbijanje je zabeleženo u 9/10 scenarija. Modul i njegovi čisti testovi ostaju kao dokaz tog merenja.
Funkciju više ne poziva nijedna ruta.

**`_RE_SAMO_OZNAKA`** (`routers/multi_agent.py`):
- Koristi ga samo `_protivreci_odlukama`, oznaka `[PROVERITI PROCESNO STANJE]` iz C3.
- Rutu nacrta je `18a235a6` prestala da poziva; `grep` pokazuje da `_protivreci_odlukama` i `_oznaci_protivrecnosti`
  danas pozivaju samo testovi.
- Zato ne utiče ni na uklanjanje ni na propuštanje ijedne tvrdnje u bilo kom toku, i nije semantička kontrola.
- Izmena nije potrebna; ostaje sa testovima C3 kao istorija.

**Izmena (najmanja):**
- `shared/nacrt_za_sud.predlog`: tekst modela ostaje CEO.
  - Server samo neutrališe svoje natpise i oznaku `[[PS-nn]]` zamenjuje doslovnim izvodom. To je prikaz izvora koji je
    izabrao model, a ne potvrda.
  - Nepostojeća oznaka ostaje vidljiva.
- `POST /api/agents/run` (nacrt iz spisa) poziva `predlog` umesto `zastiti`.
  - Odgovor nosi `predlog_teksta` i `status_teksta: "AI_RADNI_PREDLOG"`. `tekst_za_sud` i
    `izostavljeno_iz_teksta_za_sud` više ne postoje.
  - Interne napomene i dalje nose procesno stanje, šta nije utvrđeno, napomene AI i proveru citata. Odeljak
    „IZOSTAVLJENO“ je nestao, jer se ništa ne briše.
- `POST /api/staging/{id}/docx` za `tip = nacrt_iz_spisa` → **409** („AI radni predlog se ne izvozi kao dokument za
  sud“).
  - Važi i za ranije sačuvane i ranije „odobrene“ nacrte iz spisa: oni se ne označavaju retroaktivno kao usvojeni.
- Zatvoren je samo izvoz **sa pregleda** (`POST /api/staging/{id}/docx`). GATE-00 N1: opšti izvoz
  `POST /api/nacrti/export/docx` i dalje prima bilo koji tekst iz pregledača. Odbija samo tekst sa granicom, pa
  advokat može da izveze ceo AI predlog (iz `predlog_teksta` ili posle uklanjanja granice). TASK-02 mora da veže ili
  zatvori i taj put za nacrt iz spisa.

**Testovi rute** (izmenjeni, jer su merili povučenu kapiju):
- `test_mir001_c3b_nacrt_za_sud`: 2 testa (predlog je ceo, DOCX 409 i posle „odobri“; pad obrade bez naplate).
- `test_mir001_c3_procesno_stanje`: 4 testa.
- `test_mir001_c4_e2e`: segmenti 07–08.
- `test_mir001_t10_ceo_tok`: segment 08.
- `test_mir001_t06_nacrt_iz_spisa`: 1 provera.
- Čisti testovi kapije su ostali nepromenjeni.

**Regresije:**
- 7 fajlova C3/C3b/T06/T10/C4 (OCR, `-p no:randomly`): **268 passed**.
- Širi skup od 87 fajlova (spisak u scratchpadu, `fc_siri.txt`):
  - na `81bd7684` (worktree) i na radnom stablu isto: **1.204 passed, 137 skipped, 9 errors**;
  - skup padova je identičan;
  - 9 errors su greške postavke `caplog` zbog pokretanja sa `-p no:logging`; ponavlja se bez tog prekidača u TASK-04.

**GATE-00 — nezavisni recenzent: PASS, bez blokera.**
- Recenzent je sam proverio:
  - popis i podelu commitova;
  - da `zastiti` više nije u toku;
  - 409 za nacrt iz spisa;
  - `_RE_SAMO_OZNAKA`: koristi ga samo `_protivreci_odlukama`, a nju pozivaju samo testovi;
  - očuvanost ranije validiranog rada.
- Testovi: 268 passed.
- Mutacije:
  - uklonjen 409 → 4 testa padaju;
  - `zastiti` vraćena u rutu → 7 testova pada.
- Napomene (prenete u sledeće zadatke):
  - **N1:** opšti izvoz `/api/nacrti/export/docx` je i dalje otvoren za tekst predloga. Ledger je ispravljen; zatvara
    ga TASK-02. Test `t06` koji izvozi sa `tip: nacrt_iz_spisa` se prepravlja tada.
  - **N2:** `services/law_brain.py` prikazuje odobren nacrt iz spisa kao `LAWYER_VERIFIED_ARTIFACT` (znanje
    kancelarije), sa celim tekstom. To je stanje od ranije; rešava TASK-01/02.
  - **N3:** uslov `not iz_spisa` pri odobravanju nije zaštićen testom (prag 0.5 i `side_effect=AssertionError` koji
    ruta proguta). Popravlja se testom u TASK-01.
  - **N4:** V2 frontend nudi DOCX za nacrt iz spisa i pogrešno objašnjava 409 → TASK-02.
  - **N5:** zaostala terminologija „tekst za sud“ i „kapija“ u komentarima i porukama; mrtav
    `_procesno_stanje_za_nacrt` i grana `_protiv_odluka`. JSON ključ modela `tekst_za_sud` ostaje nepromenjen da bi
    generisanje bilo isto kao u izmerenom GATE-03, a komentari se ispravljaju u TASK-01.

## TASK-01 — najmanji ugovor izričitog usvajanja

**Početno ponašanje (posle TASK-00, provereno čitanjem koda i testovima):**
- `staging_memory` ima samo „izmeni → odobri/odbij“ nad jednim tekstom.
- „Odobri“ za nacrt iz spisa je označavao AI tekst kao „odobren radni nacrt“, bez ikakvog koraka provere procesnih
  informacija.
- `services/law_brain.py` je takav red prikazivao kao `LAWYER_VERIFIED_ARTIFACT`, uz interne napomene (GATE-00 N2).
- Postojeće „approve“ zato **nije** usvajanje.

**Ugovor** (`shared/usvajanje_nacrta.py`; rute u `routers/drafting.py`; bez nove šeme):

Migracija nije potrebna: `staging_memory.tip` je tekst, a zapis ide u `quality_detail` (jsonb, migracija 088).

1. **AI radni predlog** (`tip = nacrt_iz_spisa`):
   - Pri izradi server beleži snimak `quality_detail.predlog`:
     - stavke, odnosno pasuse, sa `sha256` i oznakama dokumenata koje stavka pominje;
     - dokumente spisa sa identitetom (`dokument_id`) i stanjem čitanja;
     - osam procesnih tačaka sa **kandidatima**: doslovni izvodi iz `procesno_stanje`, a vrsta i akter su samo
       kandidati;
     - šta nije utvrđeno.
   - Predlog je **nepromenljiv**: `PATCH` vraća 409, `approve` vraća 409, DOCX vraća 409.
   - Ništa u snimku nije „potvrđeno“, a odluka ne postoji.
2. **Dokument za sud** (`tip = dokument_za_sud`), poseban red:
   - `POST /api/staging/{predlog}/dokument-za-sud` pravi dokument sa **praznim** tekstom.
     - Ponovljen zahtev vraća istu verziju na čekanju. Kod paralelnog duplog zahteva posle upisa ostaje jedna
       (najranija); suvišna, netaknuta verzija se briše. Nema jedinstvenog ograničenja u šemi, pa u retkom slučaju
       istog trenutka upisa mogu ostati dve verzije na čekanju (GATE-01 N5).
     - Posle odobrenja pravi novu verziju sa istim tekstom, **bez odobrenja i bez odluka o tačkama**.
   - `POST /api/staging/{dok}/stavka {stavka, odluka: USVOJENO|ODBACENO}`:
     - server dodaje tekst stavke **iz snimka**, po id-u i sha256; tekst iz pregledača ne prihvata;
     - ponovljena ista odluka ne menja ništa;
     - usvojena stavka se ne odbacuje naknadno, već se uklanja izmenom teksta.
   - `PATCH /api/staging/{dok}/tekst`: advokat piše i ispravlja tekst. Zapis usvajanja ostaje, a izmena važi samo
     nad pročitanim tekstom.
   - `POST /api/staging/{dok}/procesne-tacke`:
     - advokatova odluka o svakoj od 8 tačaka: osnovni zahtev, dodatni zahtev, povlačenje ili izmena, odluke suda,
       nalog, uplata, rok, nedostajući ili nečitljiv dokument;
     - moguće odluke: `POTVRDJENO`, `ISPRAVLJENO`, `NEPOZNATO`, `NIJE_PRIMENLJIVO`;
     - uz potvrdu ili ispravku ide advokatov opis; izvori nisu obavezni, ali ako su navedeni, moraju biti dokumenti
       spisa (GATE-01 N8);
     - sistem ih nikad ne popunjava, a „nepoznato“ je dozvoljena i sačuvana neizvesnost.
3. **Odobrenje** (`POST /api/staging/{dok}/approve {sha256, rev}`) odobrava tačno određen tekst i odluke. Uslovi:
   - sha odgovara sačuvanom tekstu, a `rev` reviziji zapisa usvajanja koju je advokat video;
   - svaki upis u dokument za sud (stavka, tačke, PATCH, odobrenje) je uslovan na status na čekanju, isti tekst i
     istu reviziju (`quality_detail.usvajanje_rev`). Paralelan upis daje 409, nikad tiho izgubljenu odluku
     (GATE-01 B1);
   - svih 8 tačaka je odlučeno;
   - nema serverskog natpisa ni nerazrešenog mesta (`[PROVERITI`, `[IZOSTAVLJENO`, `[[PS-`, granica);
   - nema **doslovne AI stavke koja nije usvojena** (≥ 60 znakova). To je **zamka za grešku, ne bezbednosni dokaz**
     (GATE-01 N1): tekst koji advokat sam unese kroz PATCH, uključujući neznatno izmenjenu AI stavku, server beleži
     kao advokatov tekst. Ruta ne može da zna ko je šta otkucao. Granica se oslanja na to da AI tekst stiže samo
     usvajanjem ili advokatovim unosom, nikad automatski.
   - Stari klijent bez sha dobija 409.
   - Nema promocije ni upisa u bazu znanja; zapis je `usvajanje.odobreno {sha256, by, at}`.
4. **DOCX** (`POST /api/staging/{dok}/docx`):
   - samo odobren dokument čiji tekst ima tačno odobreni sha;
   - bez automatskog naslova i bez podnožja „Generisano … Vindex AI“ (`_nacrt_to_docx(za_sud=True)`; drugi izvozi
     nepromenjeni);
   - zaglavlje kancelarije (podaci korisnika) ostaje.
   - Opšti izvoz `/api/nacrti/export/docx` sa `tip` nacrt iz spisa ili dokument za sud vraća 409 (GATE-00 N1).
5. **Granica nije semantička:**
   - Server ne tvrdi da je usvojena tvrdnja tačna; prikaz nosi `provera_izvora: NIJE_IZVRSENA_SERVEROM`.
   - Ne postoji detektor reči: provere su identitet, sha, potpunost odluka, serverski natpisi i doslovna neusvojena
     stavka.
6. **Ostalo:**
   - `law_brain` za oba tipa: `AI_WORK_PRODUCT` (nikad `LAWYER_VERIFIED_ARTIFACT`), loza `LAWYER_ADOPTED` za
     odobren dokument, izvod bez internih napomena.
   - Ponovni upis odbija oba tipa.
   - Svaka radnja ima audit zapis (`dokument_za_sud_*`).
   - Komentari rute više ne govore o „kapiji“ (GATE-00 N5).

**Postojeći nacrti:**
- Nacrt iz spisa bez snimka (izrađen pre ovog toka) ne može da dobije dokument za sud: 409, „izradite novi predlog“.
- Ranije „odobren“ nacrt iz spisa se ne izvozi.
- Ništa se ne označava retroaktivno.

**Testovi:**
- Novi fajl `tests/test_mir001_c3b_usvajanje.py` (13) i pomoćnik `tests/c3b_usvajanje_pomoc.py`.
- Adversarijalno: izvod u stavci je **doslovan iz DOK-07** („Sud prihvata predlog za dopunu vestacenja.“), a tumačenje
  je suprotno („sud odbio … nije potrebna“). Test pokazuje:
  - stavka ostaje AI predlog;
  - dokument za sud je prazan dok se ne usvoji;
  - prepisana mimo usvajanja blokira odobrenje;
  - izričito usvojena prolazi samo kao zapis „usvojio advokat“, bez ijednog `VERIFIED`.
- Ostali testovi:
  - tačke obavezne i nikad unapred popunjene;
  - odbacivanje ne briše drugo;
  - izmena posle odobrenja ne nasleđuje odobrenje (verzija 2, a v1 se i dalje izvozi tačno);
  - DOCX = odobren tekst, bez naslova i podnožja;
  - podmetnut tekst u bazi daje 409;
  - tuđ korisnik dobija 404 na svakoj ruti;
  - poreklo (tip, sha snimka, predlog bez snimka);
  - usvajanje ne naplaćuje, ne zove model i ne ide u znanje;
  - uslovna izmena odbija zastareo tekst.
- T06, C4 (segment 08) i T10 (segment 08) sada idu kroz usvajanje do DOCX-a.
- GATE-00 N3 je popravljen: promocija se broji, umesto da se oslanja na `side_effect` koji ruta proguta.

**Mutacije izvršioca (1. krug):** 17/17 ubijeno (`scratchpad/fc_mut01.py`, binarno vraćanje).

**GATE-01, 1. prolaz — nezavisni recenzent: FAIL (jedan uzak bloker).**
- Potvrđeno da drži:
  - adversarijalni slučaj (autentičan izvod uz pogrešno tumačenje nikad nije potvrđen niti automatski prenet);
  - legacy `/approve` bez tela;
  - `/run-parallel`, `/pipeline`, Law Brain, promocija i ponovni upis;
  - 8 tačaka i sha;
  - verzija posle odobrenja;
  - podmetnut tekst daje DOCX 409;
  - tuđ korisnik dobija 404;
  - bez nove šeme.
  - Recenzentove mutacije: ubijeno je 7 od 10 preživelih kandidata; za preostale vidi N6 i N7.
- **B1 (bloker):** trka. Odobrenje je upisivalo ceo `quality_detail` iz pročitanog snimka. Paralelna odluka o tački
  (tekst nepromenjen) je zato tiho nestajala, a odobren zapis je tvrdio odluku koju je advokat već zamenio.
- Napomene:
  - **N1:** provera doslovne AI stavke je leksička zamka za grešku, a ne dokaz. Proba je pokazala da AI stavke bez
    završne tačke kroz PATCH prolaze.
  - **N2:** RLS iz 088 (`FOR ALL` za vlasnika) uz javni anon ključ verovatno dozvoljava vlasniku direktan upis u
    `staging_memory` mimo ruta, uključujući `status` i `quality_detail.usvajanje.odobreno`.
  - **N3:** odbačen predlog se i dalje usvajao.
  - **N4:** odobren dokument za sud je mogao da se odbije.
  - **N5:** dupli paralelni POST je pravio dve verzije.
  - **N6:** X8 (Law Brain izvod) i X1 (predmet u poreklu) nisu imali test.
  - **N8:** „izvor mora biti dokument spisa“ je bilo preoštro rečeno.
  - **N9:** DOCX prikazuje markdown (`#`, `**`); sadržaj ostaje.
  - **N10:** opšti izvozi blokiraju po `tip` koji šalje klijent. Opšti izvoz teksta sa `tip=""` daje DOCX sa
    naslovom i podnožjem sistema, a ne odobren dokument. Nijedan frontend to ne radi.
  - **N11:** `_ponovni_upis_moguc` za dokument za sud; poruka u `law-brain.js` (TASK-02).

**Ispravke posle 1. prolaza (samo TASK-01):**
- **B1:**
  - revizija `quality_detail.usvajanje_rev` (počinje od 0 i raste sa svakim upisom);
  - `_uslovno_azuriraj_dokument` i PATCH dokumenta za sud su uslovni na `quality_detail->>usvajanje_rev`;
  - odobrenje traži `{sha256, rev}`, dakle tačno ono što je advokat video.
- **N3:** `_predlog_dokumenta` odbija odbačen predlog.
- **N4:** `reject` za odobren dokument za sud vraća 409.
- **N5:** posle upisa ostaje najranija verzija na čekanju, a suvišna netaknuta se briše.
- **N11:** `_ponovni_upis_moguc` isključuje dokument za sud.
- Ledger: N1, N5 i N8 su preformulisani.
- **N2 (RLS) nije ispravljen:** to je migracija, dakle odluka osnivača.
  - Do tada tvrdnja „server kontroliše odobrenje“ važi za rute aplikacije i za audit zapis.
  - Audit je i dalje najbolji pokušaj (`create_task`).
  - Direktan upis vlasnika svojim JWT-om u svoj red nije zatvoren.
  - Ovo ide u preostala ograničenja (TASK-04).
- Novi testovi:
  - trka odobrenja i tačke;
  - trka PATCH-a i tačke;
  - zastarela revizija;
  - zaključan odbačen predlog i odobren dokument;
  - predmet u poreklu;
  - dupli zahtev daje jednu verziju;
  - Law Brain izvod bez napomena;
  - uslovni upis sa revizijom.
- Mutacije ispravki: **8/8 ubijeno** (`scratchpad/fc_mut01b.py`). Mutacija „PATCH bez revizije“ je preživela u prvom
  pokretanju, pa je dodat test trke PATCH-a.
- Testovi (11 fajlova iz brief-a, OCR): **279 passed** pre testa trke PATCH-a, a onda je dodat i on.

**GATE-01, 2. prolaz — isti recenzent: PASS.**
- Testovi: 280 passed.
- Probe:
  - R1, ponovljen P2 (paralelna ispravka tačke): approve 409, ispravka ostaje;
  - R2 (paralelni reject): approve 409;
  - R4: N4 ne menja druge tipove, a N3 drži;
  - R5 (`rev` nedostaje, je string ili je zastareo): 409;
  - R6: dedupe ne briše pogrešan red.
- Mutacije:
  - Y1 i Y4: ubijene;
  - Y2 (PATCH ne podiže rev): ekvivalentna u efektu, jer PATCH menja tekst, a svi upisi su uslovljeni i tekstom;
  - Y3 (dedupe briše izabrani red): test-gap.
- Revizija se ne može zaobići.
- Napomene:
  - **N-a:** trka odbijanja i odobrenja; odbijanje je upisivalo bez uslova `pending`.
  - **N-b:** filter `->>` u UPDATE nad `staging_memory` nije proveren uživo. Isti obrazac je u produkciji
    (`routers/evidence.py`), a ako ga PostgREST odbije, rute padaju zatvoreno.
  - **N-c:** nijedan test nije proveravao koji red dedupe briše.
- Zatvoreno posle PASS-a, u obuhvatu TASK-01:
  - **N-a:** odbijanje dokumenta za sud je uslovno na `pending`, inače 409. Novi test simulira trku.
  - **N-c:** test proverava da ostaje radni red sa sadržajem.
  - Obe mutacije su ubijene (`scratchpad/fc_mut01c.py`, 2/2).
- Testovi posle toga: **281 passed** (11 fajlova, OCR).
- `rev` dokazuje stanje koje je klijent poslao, ne šta je čovek pročitao. To važi za svaki potpis u aplikaciji.

## TASK-02 — kontrolisan sastav dokumenta za sud (V2)

**Početno ponašanje:**
- V2 kartica Nacrt je otvarala nacrt iz spisa kao jedan tekst sa dugmadima Sačuvaj, Odobri i DOCX nad AI tekstom.
- Posle TASK-01 server ta dugmad odbija (409), a ekran poruku 409 objašnjava pogrešno, preko „[IZOSTAVLJENO …]“
  (GATE-00 N4).
- Savetnik je prikazivao nacrt pod naslovom „Savetnik: Pisanje podnesaka“.

**Izmena** (`frontend-v2-ng/index.html`, `src/nacrt-predmeta.js`, `src/agenti-predmeta.js`, `src/app.css`; bez
redizajna i bez novog dashboard-a):
- Otvoren AI predlog ili dokument za sud prikazuje **tri dela sa naslovima koji kažu razliku rečima**:
  1. „AI predlog — samo za pregled. Ovaj tekst NE ide u dokument za sud.“ Svaka stavka ima:
     - tekst;
     - „Izvori koje navodi AI (nisu provereni)“, gde se dokument otvara iz same stavke
       (`/api/predmeti/{id}/dokumenti/{dok}/preview`);
     - stanje rečima („Nije odlučeno — nije u dokumentu za sud“, „Usvojeno u dokument za sud“, „Ne usvajam — ne
       ulazi u dokument za sud“);
     - dugmad „Proverio sam — usvajam u dokument za sud“ i „Ne usvajam“.
     - „Usvoji sve“ ne postoji. Interne napomene su sklopljene i označene kao interne.
  2. „Procesne informacije — vaša provera pre odobrenja“: 8 tačaka.
     - Uz svaku su doslovni izvodi („značenje nije utvrđeno“) i izbor potvrđujem, ispravljam, nepoznato ili nije
       primenljivo, plus advokatov opis.
     - Ništa nije unapred izabrano.
  3. „Tekst koji će biti izvezen u dokument za sud“: tekst dokumenta za sud, sa dugmadima Sačuvaj i Odobri.
     - Prikazan je spisak razloga koji sprečavaju odobrenje.
     - Posle odobrenja tekst je zaključan; nude se „Preuzmi odobren dokument (.docx)“ i „Nova verzija (bez
       odobrenja)“.
     - Poruka glasi „Usvajanje je vaša odluka — sistem nije proverio da su tvrdnje tačne“.
- Staro polje i dugmad nad AI tekstom se za ova dva tipa ne nude.
- Stari nacrt iz spisa bez snimka se prikazuje samo za čitanje, uz objašnjenje, bez izvoza.
- Lista nacrta piše rečima: „AI predlog — za pregled, ne izvozi se“ i „dokument za sud — čeka vaše odobrenje / odobren“.
- Savetnik za nacrt iz spisa ima naslov „AI radni predlog — samo za pregled, ne ide u dokument za sud (usvajanje:
  kartica Nacrt)“.
- **DOCX:**
  - samo `POST /api/staging/{dok}/docx` (TASK-01);
  - bez naslova „NACRT IZ SPISA (SAVETNIK)“ i bez podnožja „Generisano … Vindex AI“;
  - generički izvoznik je nepromenjen za sve druge tokove (parametar `za_sud` važi samo za dokument za sud).

**Test okruženje:**
- `tests/osb003_solo_server.py` dobija:
  - podrazumevane vrednosti kolona `staging_memory` iz migracije 088, jer baza u memoriji ih nije znala;
  - zamenu modela uz `VX_NACRT_C3B=1` (autentičan izvod iz DOK-07 uz pogrešno tumačenje);
  - u `stanje`: sažetak nacrta (tip, status, sha256, zapis usvajanja) bez sadržaja.

**Dokaz:**
- `frontend-v2-ng/tests/live-c3b-usvajanje-e2e.mjs`: **32/32**. To je pravi `api.app` nad bazom koja upisuje, Golden
  Case kroz stvaran prijem i OCR, a svaki korak je proveren u UI-ju i u bazi.
  - Predlog: 1 poziv modela, 1 naplata.
  - Ekran:
    - tri dela;
    - pogrešna stavka uz autentičan izvod je prikazana kao AI predlog sa „nisu provereni“;
    - 8 tačaka bez izbora;
    - izvor se otvara.
  - Usvajanje:
    - prazan dokument se ne odobrava;
    - 3 stavke su usvojene, pogrešna je odbijena, upozorenje AI je neodlučeno;
    - dokument sadrži samo usvojeno, a AI predlog je nepromenjen (sha).
  - Advokatov tekst; bez tačaka nema odobrenja; 8 odluka (ODLUKE_SUDA = ISPRAVLJENO).
  - Odobrenje i DOCX:
    - odobren je tačno tekst sa ekrana (sha);
    - **DOCX pročitan iz preuzetog fajla** (python-docx): pasusi = odobren tekst red po red, bez naslova, bez
      podnožja, bez internih napomena.
  - Reload daje isto stanje. Nova verzija je na čekanju, bez odobrenja i odluka, a v1 ostaje odobrena.
  - Ostalo:
    - drugi korisnik dobija 404;
    - AI predlog i opšti izvoz daju 409;
    - usvajanje ne zove model i ne naplaćuje;
    - 0 spoljnih veza, bez JS grešaka i bez 5xx.
- Snimak: `mir001_c3b_model/final_closure/t02_odobren_dokument_za_sud.png`.
- Susedni frontend testovi:
  - `live-nacrt` 54/54 (blok „D.docx“ je prepravljen na „D.predlog“: stari nacrt samo za čitanje, bez izvoza,
    izmene i odobrenja);
  - `live-agenti` 52/52;
  - `live-savetnici-e2e` 16/16;
  - `live-law-brain` 45/45;
  - `live-mir001-spis-e2e` 17/17.
- Python:
  - asset, preview i primary, website, niz i usvajanje: 158 passed (`test_website_v3_rast` traži `OPENAI_API_KEY`
    u okruženju pri samostalnom pokretanju, kao i ranije);
  - 11 fajlova TASK-01: 281 passed.
- Napomena: kandidati procesnih tačaka prikazuju sirove nazive vrsta (`stranka_predlaze`) uz „kasnije“. To je
  kozmetika; reči su dobijene iz procesnog stanja servera.

**GATE-02, 1. prolaz — nezavisni recenzent: FAIL (jedan uzak bloker na ekranu).**
- Potvrđeno da drži:
  - E2E 32/32, uz proveru da zaista meri ono što tvrdi (DOCX iz fajla, sha ekrana jednak sha odobrenja, predlog
    nepromenjen);
  - `za_sud` se koristi samo na jednom mestu;
  - razlika nije samo bojom;
  - dvostruki klik je bezbedan;
  - nesačuvan tekst se pre odobrenja čuva;
  - prepisana neusvojena stavka je blokirana;
  - stari nacrt je samo za čitanje;
  - nigde se ne tvrdi da je AI tvrdnja proverena.
- **B1:** „Odobri“ je čuvalo samo tekst. Promenjen, a nesačuvan izbor procesne tačke je ponovno crtanje tiho
  vraćalo, pa je odobren zapis tvrdio odluku koju advokat nije doneo, uz poruku „odobren“.
- Napomene:
  - **N1:** tekst ukucan pre nastanka dokumenta za sud je prvo usvajanje tiho prepisivalo.
  - **N2:** čuvanje teksta i usvajanje su brisali nesačuvane izbore tačaka.
  - **N3:** mutacija M1 je preživela E2E.
  - **N4:** kasan odgovor drugog predloga mogao je da se upiše u otvoren predlog (pronađeno čitanjem koda).
  - **N5:** „Odbij“ iz liste pozivalo je stari prikaz.
  - **N6:** oznaka „tačno ovaj tekst“, a izvoz pretvara `#` i `**`.

**Ispravke posle 1. prolaza** (`src/nacrt-predmeta.js`, `index.html`):
- **B1:** odobrenje se zaustavlja pre servera ako se bilo koja tačka na ekranu razlikuje od sačuvane („odobrava se
  samo ono što je sačuvano“).
- **N2:** ponovno crtanje zadržava nesačuvane izbore i označava ih „Nesačuvana izmena“.
- **N1:** tekst je nesačuvan i dok dokument za sud još ne postoji, pa usvajanje i tačke traže da se prvo sačuva.
- **N4:** posle svakog čekanja proverava se da je otvoren isti predlog (`isti(pid)`).
- **N5:** odluka iz liste o otvorenom predlogu ili dokumentu ponovo čita stanje sa servera.
- **N6:** oznake opisuju osnovno formatiranje.
- E2E dobija 4 provere:
  - usvajanje uz nesačuvan tekst pre nastanka dokumenta;
  - nesačuvan izbor preživljava čuvanje teksta;
  - odobrenje sa nesačuvanom tačkom je zaustavljeno;
  - B1 posle sačuvanih 8 tačaka: baza ostaje na čekanju, a NEPOZNATO ostaje NEPOZNATO.
- Rezultat: **36/36**.
- Mutacije (`scratchpad/fc_mut02.py`, nad E2E): **4/4 ubijene** (M1, B1, N2, N1). `live-nacrt` 54/54.

**GATE-02, 2. prolaz — FAIL (dva nova uska blokera, oba uvedena ispravkom N2).**
- Ispravke iz 1. prolaza drže. Recenzentovi napadi A1, A1b, A4a, A5, A5a, A5b i A5c prolaze.
- **B2:** lažna „Nesačuvana izmena“ posle uspešnog čuvanja. Ekran je poredio opis doslovno, a server ga skraćuje
  (`.strip()`), pa jedan Enter na kraju opisa trajno blokira odobrenje.
- **B3:** posle „Nova verzija“ ekran je zadržavao odluke iz odobrene v1 kao nesačuvane izbore. Jedan klik na „Sačuvaj
  odluke“ bi ih upisao u v2 bez nove odluke. Baza je ostala ispravna, a greška je samo na ovom putu.
- Napomene:
  - **N-a:** zaštite N4 i N5 nemaju test (X3 i X5 preživljavaju).
  - **N-b:** opis bez odluke se tiho ne čuva; sačuvana odluka se ne može vratiti na prazno.
  - **N-c:** unakrsni upis između dva predloga nije potvrđen uživo.

**Ispravke posle 2. prolaza:**
- **B2:** poređenje kao server (skraćen opis); izbor bez odluke nije nesačuvana izmena.
- **B3:** nesačuvani izbori se zadržavaju samo za isti dokument za sud (`crtanoZa`) ili pri prelazu „nema dokumenta →
  nastao dokument“.
- **N-b:**
  - opis bez odluke se ne čuva tiho, već poruka traži odluku;
  - sačuvana odluka se ne može vratiti na „— izaberite —“, jer server nema brisanje odluke.
- **N-a:**
  - X5 sada ima test: „Odbij“ iz liste za otvorenu verziju 2 osvežava ekran sa servera.
  - X3 (`isti(pid)`) i dalje nema test. Drugi AI predlog u istom predmetu se ne može napraviti u lažnom serveru:
    ponovljen upis u roku zaštite od duplikata (`_STAGING_RETRY_WINDOW_SECONDS`) se preskače. Zaštita je zato
    utvrđena samo čitanjem koda; to ide u preostala ograničenja.
- E2E: **40/40**. Nove provere:
  - opis sa novim redom na kraju;
  - ekran nove verzije bez izbora;
  - odbijanje v2 iz liste;
  - baza: v2 odbijena, v1 odobrena.
- Mutacije (`scratchpad/fc_mut02b.py`): **7/7 ubijene** (M1, B1, N2, N1, B2, B3, X5). `live-nacrt` 54/54.

**GATE-02, 3. prolaz — isti recenzent: PASS (bez blokera).**
- Ponovljeni napadi:
  - A9 (ranije B2) i A12 (ranije B3) su zatvoreni;
  - A1–A5c drže;
  - nove probe prolaze: prelaz bez dokumenta preko „Usvajam“, onemogućena prazna opcija, promenjen samo opis
    sačuvane tačke, samo razmaci, zaključane tačke posle odobrenja, opis bez odluke.
- Rezultati: E2E 40/40, `live-nacrt` 54/54, recenzentovi napadi 23/23, 14/14 i 17/17.
- Mutacije:
  - Y1 i Y2: ubijene;
  - Y3, Y4, Y5 i Y6: kod se ponaša ispravno, ali ih E2E nije držao. Najvažnija je Y6, izmena samo opisa, iste klase
    kao prvobitni B1.
- Napomene:
  - N3: `isti()` bez testa (ograničenje lažnog servera);
  - N4: `#` i `**` u DOCX-u; oznake to sada kažu.
- **Zatvoreno posle PASS-a (samo testovi, bez promene koda):** E2E dobija provere za
  - Y3: izbor preživljava nastanak dokumenta;
  - Y4: prazna opcija onemogućena;
  - Y5: opis bez odluke se ne čuva tiho;
  - Y6: izmena samo opisa zaustavlja odobrenje, a baza zadržava stari opis.
  - Rezultat: **44/44**. Mutacije (`scratchpad/fc_mut02c.py`): **4/4 ubijene**.
- Dokaz: `mir001_c3b_model/final_closure/t02_live_e2e.txt` (44/44) i `t02_odobren_dokument_za_sud.png`.

## TASK-03 — adversarijalni gejt dokaza (granica prenosa)

**Prethodna registracija:** `mir001_c3b_model/final_closure/t03/PREREGISTRACIJA.md`, commit `6f9b584b` pre merenja i
pre ijednog novog poziva modela. Odstupanja su u `t03/ODSTUPANJA.md` (7, nijedno ne menja merila). Kod koji se meri:
`dee9d8b0`.

**Deo A — 100 snimljenih SIROVIH izlaza gpt-4o iz GATE-03 i 10 sa ubačenom netačnom tvrdnjom (A2), kroz NOVU rutu:**
- Harness `t03/t03_fc.py`, režim `replay`; rezultati u `t03/replay/` i `t03/zbir_replay.json`.
- 110/110: ruta 200, AI predlog sa snimkom. Mehanički advokat je usvojio 1.229 stavki i odbacio 80 (citati koje su
  slepi označivači GATE-03 označili kao materijalne, „⚠“, `NE POSTOJI]]`).
- 110/110 je odobreno i izvezeno. **Povreda K1–K7: 0.**
  - **K4:** nijedan deo sirovog izlaza modela ne nedostaje u predlogu. Kapija je ranije brisala, a sada ništa ne
    nestaje.
  - **A2:** ubačena „uplata i odbijanje“ je u 10/10 slučajeva AI predlog, a u 0/10 je u dokumentu.
- **Provera harness-a** (`scratchpad/fc_mut03.py`): 6 pokvarenih servera nad A2, i svih 6 je uhvaćeno.
  - X1: dokument kreće od celog predloga;
  - X2: DOCX sa naslovom i podnožjem;
  - X3: odbačena stavka se dodaje;
  - X4: PATCH predloga dozvoljen (test pada);
  - X5: kapija vraćena (brisanje);
  - X6: tiho skraćena usvojena stavka.

**Deo B — 10 stvarnih poziva gpt-4o (po jedan po scenariju) kroz novu rutu:**
- Svih 10: 200, 1 poziv i 1 naplata, ceo predlog (K4); rezultati u `t03/gen/`.
- **B1, nezavisan advokat** (zaseban agent; vidi samo spis i ono što proizvod prikazuje):
  - usvojio je 112 stavki, a odbio 4: 2× „uključujući 600.000“ i 2× upozorenje AI;
  - ispravio je stavke zamenama: odluka suda prećutana ili pogrešna, iznos, `[PROVERITI …]`;
  - odlučio je o svih 8 tačaka u 10/10 predmeta.
  - Odluke su primenjene kroz stvarne rute (`t03/primeni/`, `t03/zbir_primeni.json`): **10/10 odobreno i izvezeno,
    povreda K1–K7: 0, sve zamene primenjene.**
- **B2, slepi ocenjivač AI predloga (Q):** M1 3/10, M2 2/10, M5 7/10, M7 4/10, M8 6/10, M3 i M4 0; K 10/10; Q prosek
  2,8 (medijana 3).
  - Ponavljaju se iste greške kao u GATE-03: „4.200.000 uključuje 600.000“, prećutana odluka suda, prećutan dopis o
    uplati, i sistemski tekst u AI predlogu (`[PROVERITI`, „⚠“).
  - **AI kvalitet nije popravljen i to se ne tvrdi.**
- **B3, drugi slepi ocenjivač dokumenata za sud (K i korisnost):** M1–M5, M7 i M8 su **0/10**; neprazan i koherentan
  **10/10**; Q prosek **3,4** (medijana 3).
  - Ocene 3 su date za tačne tekstove koji ćute o otvorenom pitanju (uplata) ili nemaju deo o stanju postupka.
  - Granica ocene: u N2 je ocenjivač kasniju odluku suda (odbija, 10.09.) čitao kao da zamenjuje raniju (prihvata,
    15.07.). Drugi ocenjivač bi to mogao videti kao protivrečno (M7).

**R — regresije** (`t03/regresije/`):
- Širi skup od 87 fajlova:
  - `81bd7684`: 1.213 passed, 137 skipped, **0 failed**;
  - HEAD, sa `test_mir001_c3b_usvajanje.py`: 1.232 passed, 137 skipped, **0 failed**.
- Browser: `live-c3b-usvajanje-e2e` 44/44, `live-nacrt` 54/54, `live-agenti` 52/52, `live-savetnici-e2e` 16/16,
  `live-law-brain` 45/45, `live-mir001-spis-e2e` 17/17.

**K8 — negativni testovi iz zadatka osnivača i gde ih drži automatika:**

| # | zahtev | testovi |
|---|---|---|
| 1 | AI tvrdnja ne postaje potvrđena | `test_snimak_predloga_nista_nije_potvrdjeno_ni_popunjeno`, `test_adversarijalno_…`, deo A/B K7, E2E `2.ekran` |
| 2 | ne prelazi neprimetno u dokument | `test_bez_usvajanja_i_odobrenja_nema_dokumenta_za_sud`, deo A K1/K5, A2, E2E `3.prazno`, `4.usvajanje` |
| 3 | korisnik vidi izvor i status | E2E `2.ekran` (izvori „nisu provereni“, dokument se otvara, stanje rečima), `test_snimak_…` |
| 4 | može da odbaci ili ispravi | E2E `4.usvajanje`, `5.tacke`; B1 zamene; `test_odbacivanje_…` |
| 5 | odbacivanje ne briše drugo | `test_odbacivanje_ne_brise_drugi_sadrzaj_…`, deo A K3, A2 |
| 6 | nijedan interni naslov u DOCX-u | `test_docx_je_tacno_odobren_tekst_bez_naslova_i_podnozja_sistema`, deo A/B K2, E2E `7.docx` |
| 7 | neodobren se ne predstavlja kao odobren | `test_bez_usvajanja_…`, deo A K4 (predlog: approve/PATCH/DOCX 409), legacy approve bez tela 409, `test_poreklo_…` (bez snimka 409) |
| 8 | izmena posle odobrenja ne nasleđuje odobrenje | `test_odbacivanje_…_izmena_posle_odobrenja_…`, `test_odbacen_predlog_i_odobren_dokument_su_zakljucani`, E2E `8.verzija` |
| 9 | neovlašćen korisnik | `test_tudj_korisnik_ne_vidi_ne_usvaja_ne_odobrava_ne_izvozi`, E2E `9.izolacija`, T06 |
| 10 | ponavljanje bez duple naplate i verzija | `test_usvajanje_ne_naplacuje_…`, `test_dupli_zahtev_…`, dvostruki approve, `test_odobrenje_trazi_reviziju_…`, trke, E2E `9.trosak` |

**Merilo U:** B1 je dao neprazan dokument u 10/10 (prag ≥ 9/10), B3 ocenjuje K = DA u 10/10 (prag ≥ 9/10), medijana Q
je 3 (prag ≥ 3) → **ispunjeno**.

**Predlog izvršioca (presuda je na recenzentu):** K1–K8: 0 povreda; U ispunjen; R bez novih padova → **PASS**.

Ograničenja:
- B1, B2 i B3 su instance istog modela, a ne ljudi.
- Mehanički advokat dela A odbacuje samo ono što su GATE-03 označivači označili, pa je usvajao i rečenice koje je
  kapija ranije brisala i koje niko nije ocenio. Zato deo A meri granicu, a ne sadržaj.
- `isti()` (kasni odgovor drugog predloga) nema test.
- RLS iz 088 (GATE-01 N2) nije zatvoren.

**GATE-03 — nezavisni recenzent: PASS (bez blokera).**
- Prethodna registracija prethodi merenju (13:11:54, a prvi izlazi su iz 13:19).
- Recenzent je ponovio deo A sa sadašnjim harness-om: 110/110 identično.
- Nezavisan zbir, bez `zbir_fc.py`, za svih 120: odobren tekst je znak po znak spoj usvojenih stavki uz zamene.
  Nijedna rečenica (≥ 20 znakova) iz 80 odbačenih stavki nije u DOCX-u, a ubačena tvrdnja nije ni u jednom od 10.
- Slepoća B1–B3 je proverena (paketi bajt-identični, bez ključeva).
- Sopstveno čitanje svih 10 DOCX-a: nijedna materijalna greška ne potiče iz neusvojenog teksta ni iz sistema.
- Negativni testovi: 19/19 uz OCR, E2E 44/44, širi skup 1.213 passed i 0 failed.
- Mutacije:
  - X3, X6, Y2, Y3 i Y4 su uhvaćene;
  - **Y1 (delimično procurela odbačena stavka) nije bila uhvaćena** proverom K1, rupa u merenju koja je zatvorena
    (vidi dole).
- Korisnost: nijedan od zabranjenih načina nije korišćen.

Napomene recenzenta:
1. K1 i serverski čuvar traže celu stavku kao podniz. Ovo je **zatvoreno u harness-u kao K1b** (odstupanje #8;
   ponovljeno 120/120, Y1 je sada uhvaćena). Serverski čuvar ostaje zamka za grešku, ne dokaz (GATE-01 N1).
2. AI rezervisana mesta kojih nema na spisku (npr. „[POTREBNO JE DOSTAVITI POTPIS …]“, `replay/N4_02`) prolaze ako ih
   advokat usvoji. To je kvalitet AI, ne povreda K.
3. **Odluka osnivača:** izvodi koje umeće server, oblika „(DOK-07, zapisnik … 15.07.2026.: „…“)“, nose internu
   numeraciju DOK-nn i tekst bez dijakritika. Ulaze u sudski DOCX kad ih advokat usvoji; ima ih u 74 od 120 DOCX-a.
   Advokat ih vidi pre usvajanja, a B3 ih nije označio kao sistemski tekst.
4. Opšti izvoz `/api/nacrti/export/docx` izvozi tekst koji klijent pošalje (ručno kopiran AI predlog), van
   zaštićenog toka i bez oznake odobrenja.
5. B1–B3 su isti model, a izolacija je samo po uputstvu.
6. Procesne tačke se ne porede sa tekstom (namerno, nema leksičke kapije).
7. `isti()` bez testa, RLS iz 088, deo A meri granicu, a ne sadržaj.

**Ishod TASK-03 / GATE-03: PASS.**
- Granica prenosa je proverena na 120 stvarnih izlaza i 10 ubačenih netačnih tvrdnji, bez povrede.
- Proizvod ostaje koristan (10/10 neprazan i koherentan, medijana Q 3, M = 0 u dokumentima za sud).
- Nema nove regresije.
- AI CONTENT QUALITY je i dalje slab (B2: M1 3/10, M5 7/10, Q 2,8) i prijavljen je odvojeno.

## TASK-04 — završno zatvaranje proizvoda

Nema nove funkcionalnosti; kod nije menjan.
- Završni izveštaj: `MIR001_C3B_FINAL_CLOSURE_REPORT.md`.
- Read-only plan za produkciju, kontrolisani QA i povratak: `mir001_c3b_model/final_closure/t04/PRODUKCIJA_I_QA.md`.
- **Pun skup testova** (`t04/pun_skup.txt`): `81bd7684` daje 23 failed i 12.024 passed, a HEAD `c6d67252` daje 23
  failed i 12.043 passed. **Skup padova je identičan**; svi su postojeći padovi okruženja.
- **Migracije:** nema (`git diff f33dcce8 HEAD -- migrations` je prazan). Nema infrastrukturnih izmena ni aktivacije
  NS007.

**GATE-04, 1. prolaz — FAIL (bloker samo u dokumentu).**
- **B1:** plan povratka nije obuhvatao **odobrene** dokumente za sud. Stari kod (`f33dcce8`) bi ih preko „Ponovi upis“
  (`_ponovni_upis_moguc`, RPC 140) uneo u bazu znanja ako je ocena ≥ 0,85, a ocenu dokument dobija pri izmeni teksta.
- Napomene:
  - **N1–N3, N7:** ograničenja koja su bila samo u ledger-u nisu bila u izveštaju (opšti izvoz i `/app-legacy`,
    `isti()`, deo A, izolacija B1–B3, NS007 `case_change_brief`, trošak ponovljene izrade).
  - **N4:** zastarela poruka 409 u `docx()`.
  - **N5:** osnova regresije za raniji MIR001 rad.
  - **N6:** mrtva grana `iz_spisa`.
- Recenzent je već tada ocenio presudu A kao suštinski opravdanu.
- **Ispravke** (samo dokumenti): plan povratka i §9 obuhvataju obe grupe redova, uz obaveznu odluku osnivača; §8 je
  dopunjen svim ograničenjima; §7 navodi osnovu regresije i dokaze za raniji rad.

**GATE-04, 2. prolaz — isti recenzent: PASS.** Recenzent potvrđuje presudu A.
- Preostala napomena: lanac dokaza za pun paket prema produkciji nije neprekidan posle `18a235a6`. Ako osnivač želi
  jedan dokaz za ceo raspon, pre puštanja treba ponoviti pun paket na `f33dcce8` i uporediti ga sa HEAD-om.

**KONAČNA PRESUDA SPRINTA: `C3B_CONTROLLED_DRAFTING_READY`.** To je spremnost za osnivačev release review ograničenog,
ljudski kontrolisanog izrađivanja nacrta. NIJE `REAL_USER_ACCEPTED`. AI tvrdnje nisu proverene; kvalitet AI predloga
je i dalje slab i prijavljen je odvojeno. Ništa nije pushovano, spojeno ni pušteno.
