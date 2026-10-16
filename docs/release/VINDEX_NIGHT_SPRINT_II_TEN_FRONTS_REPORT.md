# VINDEX — Night Sprint II · Operation Ten Fronts — stvarni rezultati

**Završni status: `LOCAL_TEN_FRONTS_COMPLETE_RELEASE_HOLD`**

Sve izvršene misije su zatvorene sa dokazom. Lokalni rad je završen. Ništa nije pushovano, spojeno ni pušteno, i nijedna produkciona promena nije napravljena. Za puštanje je potrebno posebno odobrenje.

## A. Izvršni rezime

Od 10 primarnih misija:
- **8 je otklonilo stvarne, reprodukovane defekte**: M01, M02, M03, M04, M05, M06, M09 i M10.
- **2 su dokazale da je postojeći kod već ispravan** i zatvorene su bez izmene koda: M07 i M08.
- Rezerva **R01** je procenjena i takođe je već ispravna. Nije uračunata kao ispravka.
- Blokiranih i neuspelih misija nema.

Svaki popravljen defekt ima RED test na kodu pre izmene, GREEN posle izmene i najmanje jednu mutaciju koja dokazuje da test hvata vraćanje greške.

Koliko je Vindex bolji nego na početku sprinta (lokalno, do spajanja):
- Dnevni dispečer više ne prijavljuje neuspele ni nepotvrđene email podsetnike kao uspeh.
- Email podešavanja više ne vraćaju 500 korisniku bez profila.
- Advokat u starom UI-ju nalazi timske komentare kroz globalnu pretragu.
- Delimična pretraga (više od 200 predmeta) se otvoreno označava.
- Neuspeo upis dokumenta više ne ostavlja njegove vektore dostupne pretrazi, a vektori postojećeg istog dokumenta se ne diraju.
- Neuspeh AI klasifikacije na dokumentu sa ljudskom vrstom sada ima trajan trag.
- Istek čekanja na Genome više ne izgleda kao normalno stanje.
- Ekran „Šalje se na“ i probni email koriste stvarnog primaoca podsetnika.

## B. Stanje repozitorijuma

| | SHA |
|---|---|
| Produkciona baza (`origin/main`, produkcija `/api/version`) | `d2f8d7d94bd328dde21711b9728e7e970ed0e881` |
| Nasleđeni alerts sprint (nije deo ovog sprinta; 7 commita) | `59cdb9a6` → `40d98288` |
| Night Sprint II commiti (10) | `e945ff8b`, `a0a00e19`, `277435d4`, `30e39d6f`, `cddf2c9f`, `f7106674`, `9bb13bf8` (samo test), `b4cc5b10` (samo test), `0a2cff7b`, `662df513` (+ commit ovog izveštaja i ledger-a) |
| Kombinovani lokalni HEAD | grana `night/canonical-ten-fronts`, worktree `C:/vindex-qa/ten-fronts`, bez upstream-a |

Pre izveštaja je radni prostor bio čist. Alerts worktree (`40d98288`, 0 izmena) i `int-beta` (2 nekomitovana dijagnostička testa iz ranije) nisu dirani.

## C. Matrica misija

| Misija | Početna tvrdnja | Stvarni nalaz | Status | Testovi (novi) | Commit |
|---|---|---|---|---|---|
| M01 | Dispečer upisuje „ok“ i kad email ima grešku | PROVEN: konstanta `"ok"`, bez +1 greške; 12 RED | ACCEPTED_VERIFIED | 20 | `e945ff8b` |
| M02 | UI prikazuje lažno „nije konfigurisan“ | Lažno upozorenje NIJE reprodukovano u runtime-u. Stvarni defekt: `maybe_single()` vraća None → **500** za svakog korisnika bez profila; 5 RED | ACCEPTED_VERIFIED | 8 (3 izvršavaju stvarnu UI funkciju u Node-u) | `a0a00e19` |
| M03 | Komentari nisu u pretrazi | PROVEN; granica vidljivosti preuzeta iz `komentari.py`; 7 RED | ACCEPTED_VERIFIED | 14 | `277435d4` |
| M04 | Prećutno skraćivanje pretrage | PROVEN za više od 200 predmeta (hronologija, beleške, komentari), bez `nepotpuno`; 9 RED | ACCEPTED_VERIFIED | 14 | `30e39d6f` |
| M05 | Sirotni vektori posle neuspelog upisa | PROVEN na stvarnom endpointu; dodatno otkriveno da isti sadržaj u istom predmetu deli ID-jeve vektora | ACCEPTED_VERIFIED | 15 | `cddf2c9f` |
| M06 | Pozadinski neuspesi samo u logu | Većinom ZASTARELO (outbox + verify-or-raise). Preostao defekt: AI neuspeh na dokumentu sa ljudskom vrstom nema trajan trag; 2 RED | ACCEPTED_VERIFIED | 4 | `f7106674` |
| M07 | Genome refresh bez prekida posle provere vlasnika | Kod je VEĆ bezbedan: `.single()` diže izuzetak, a `except` izlazi pre bilo kakve posledice | NO_CHANGE_NEEDED_PROVEN | 5 | `9bb13bf8` (test) |
| M08 | Genome zastareo posle izmene predmeta | Premisa ne važi: Genome ulaz su samo dokumenti i tvrdnje, ne izmenjiva polja | NO_CHANGE_NEEDED_PROVEN | 4 | `b4cc5b10` (test) |
| M09 | Istek watcher-a izgleda kao normalno stanje | PROVEN (stari UI); 2 RED | ACCEPTED_VERIFIED | 6 | `0a2cff7b` |
| M10 | Primalac podsetnika nedosledan | PROVEN; pravilo već postoji (VCR002: `profiles.email`), primenjeno je na oznaku i probni email; 4 RED | ACCEPTED_VERIFIED | 9 | `662df513` |
| R01 (rezerva) | Kontekst korisnika se gubi kroz `to_thread` | Već ispravljeno u S2-3, dokazano izvršavanjem; nije komitovano | NO_CHANGE_NEEDED_PROVEN | — | — |

## D. Stvarni inženjerski učinak

- **Nezavisno otklonjenih defekata: 8.**
- **Već ispravnih komponenti potvrđenih dokazom: 2 primarne + 1 rezerva.**
- **Blokiranih: 0.**
- **Novih regresionih testova: 99** u 10 novih fajlova (20+8+14+14+15+4+5+4+6+9).
- **Novih padova: 0.** Unija ciljane regresije u 88 fajlova: 1.474 prolaza, 3 pada, 2 preskočena.
  - Sva 3 pada su `test_faza1_pristupacnost` i padaju identično na `40d98288`, potvrđeno u netaknutom alerts worktree-u.
  - Preskočena su 2 `test_qa05_slika_finalize`, jer lokalno nema Tesseract-a.
- **Lokalnih commita: 10** (8 ispravki + 2 samo-test) + 1 za izveštaj i ledger.
- **Izmenjene produkcione putanje:** `api.py` (dispečer, upload), `routers/email_notif.py`, `routers/search.py`, `services/case_evolution.py`, `shared/vector_deletion.py`, `static/vindex.js`, `index.html`, `static/sw.js` (v152→v154), `frontend-v2-ng/src/pretraga.js`.

## E. Adversarial nalazi (pokušaji da se rad obori)

1. **Mutacije.** Svaka izmena ima bar jednu mutaciju koju test hvata. Tri mutacije su pri prvom pokušaju **preživele ili se nisu izvršile**, pa su ispravljene i ponovljene:
   - M04: `>=` mutacija nije primenjena, jer Windows Python ne vidi MSYS `/tmp`. Odbačena i ponovljena.
   - M05: mutacija „široki prefiks“ nije primenjena zbog CRLF-a. Odbačena i ponovljena.
   - M10: mutacija oznake je preživela. Dodat je test za granu sa postojećim profilom.
2. **M05 bezbednost brisanja.** Naivno brisanje po prefiksu bi obrisalo vektore postojećeg dokumenta istog sadržaja, jer su ID-jevi deterministički. Zato se briše samo ako nijedan red ne nosi isti identitet, uz post-proveru za trku.
3. **Nalaz u postojećem harness-u (M01).** `test_cron_daily_dispatcher` ne zamenjuje tri `reap_*` modula, pa pri svakom pokretanju pokušava **stvaran mrežni poziv**. Postojeći fajl nije menjan; moj test ih zamenjuje.
4. **Nalaz u grupnom pokretanju (M05).** Dva postojeća testa grane „insert pao“ pokušala su stvaran Pinecone poziv, jer je čišćenje novi saradnik. Dodata im je zamena indeksa; tvrdnje su nepromenjene.
5. **Klasa defekta (nije menjano, van scope-a).** Postoji 66 poziva `maybe_single().execute()`. Svaki koji čita `.data` bez provere `None` vraća 500 za 0 redova. Primeri: M02 (ispravljeno), a `komentari.py` za tuđi predmet vraća 500 umesto 403 (i dalje fail-closed).
6. **Odbačene istorijske tvrdnje.**
   - M02 lažno upozorenje: nije reprodukovano.
   - M06 „samo log“: većinom zastarelo.
   - M07: već bezbedno.
   - M08: premisa ne važi.
   - R01: već ispravljeno.

## F. Očuvanje invarijanti

- **Izolacija između kancelarija:**
  - M03 koristi istu granicu kao čitanje komentara; tuđi komentar i anomalija se ne nalaze; mutacija „bez filtera“ pada.
  - M05 proverava vlasništvo, briše samo u sopstvenom namespace-u i prefiksu.
  - M10 nikad ne čita tuđi profil.
- **Autorizacija:** nijedna provera nije oslabljena. Tajne i autorizacija `/api/cron/daily` su nepromenjene; M07 je dokazao postojeću granicu.
- **Poverljivost:** nijedna vrednost tajne ni email adresa u logovima (testovi to proveravaju). `smtp_ok` je samo bool.
- **Audit:** M06 koristi postojeći `audit_immutable`, bez nove šeme i bez novog tipa događaja.
- **Pravna pouzdanost:**
  - Nepotvrđen AI rok i dalje ne šalje podsetnik.
  - Isporuka se ne tvrdi.
  - Delimična pretraga i istek se kažu otvoreno.
- **Pozadinski poslovi:** nijedno novo ponavljanje, nijedan novi posao. Dispečer ne ponavlja email modul; M09 ne pokreće novo osvežavanje; M06 ne reklasifikuje.
- **QA-02:** uslovni upis vrste je nepromenjen. M06 je potvrdio da ljudska vrsta i oznaka ostaju.

## G. Poznata ograničenja

- Sve je LOCAL_TEST_ONLY:
  - stvarni Pinecone, SMTP, PostgREST i Supabase nisu pozivani;
  - Playwright nije pokretan za ⌘K paletu, poruke pretrage ni Genome hint.
- M03 i M09 važe za stari UI (`/app-legacy`). V2 nema prikaz komentara ni Genome watcher; V2 nije menjan sem teksta u M04.
- M05: ostaje rizik trke sa istovremenim uspešnim upload-om istog sadržaja. Taj slučaj se otkriva (VERIFICATION_FAILED + ERROR „potrebna reindeksacija“), ali se ne sprečava.
- M06: trag je trajan (`result_ref` u posledici i auditu), ali nijedan ekran ga ne prikazuje.
- M10: da li se kod stvarnih korisnika `profiles.email` razlikuje od adrese za prijavu: UNKNOWN.
- Da li Render Cron poziva `/api/cron/daily`: UNKNOWN.
- Rezerve R02–R04 nisu procenjene.

## H. Predaja za puštanje

- **Grana:** `night/canonical-ten-fronts` sadrži nasleđeni alerts rad (`40d98288`) **i** ovaj sprint. Treba je pregledati i spojiti kao celinu, posle alerts grane ili zajedno sa njom.
- **Očekivani konflikti sa drugim granama:**
  - `static/sw.js` (`CACHE_NAME` v154): svaka druga frontend grana koja povećava broj će se sukobiti, kao ranije v151.
  - `routers/email_notif.py` i `api.py`: alerts i ovaj sprint ih menjaju redom na istoj liniji istorije, pa međusobno nema konflikta.
- **Migracije:** nema.
- **Nove tajne i env promenljive:** nema.

## I. Odluke osnivača (samo stvarno potrebne)

1. **Puštanje.** Da li se kombinovana grana šalje u Draft PR → `main` radi CI poređenja po imenima testova? Traži novo odobrenje za push.
2. **Klasa `maybe_single()` → 500.** Da li se otvara zasebna misija za 66 poziva? Ovaj sprint ju je samo dokumentovao.

## J. Preporuka

Kombinovana lokalna grana je **podobna za nezavisan release review** (Draft PR + CI poređenje po imenima testova). **To nije odobrenje za produkciju.** Podsetnici i dalje zahtevaju korake iz runbook-a alerts sprinta (ključ, SMTP, opt-in) pre bilo kakve tvrdnje o isporuci.

Detaljan dokaz po misiji: `docs/release/VINDEX_TEN_FRONTS_EVIDENCE_LEDGER.md`.
