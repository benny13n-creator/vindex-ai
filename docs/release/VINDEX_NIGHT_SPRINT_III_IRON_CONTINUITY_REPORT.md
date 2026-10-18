# VINDEX — NIGHT SPRINT III „OPERATION IRON CONTINUITY“ — završni izveštaj

Datum: 2026-10-17 · Grana: `night/iron-continuity-ns3` (samo lokalno) · Baseline: `469085b6` (= `origin/main` = produkcija)
Detaljni zapis po misiji: `docs/release/VINDEX_NIGHT_SPRINT_III_LEDGER.md`.

**Konačna presuda: `LOCAL_IRON_CONTINUITY_COMPLETE_RELEASE_HOLD`**

Svih 16 misija je završeno sa dokazom. Status svake misije je jedan od: ispravljeno, dokazano ispravno ili dokazan kvar odložen uz obrazloženje.

Ništa nije pushovano, spojeno ni pušteno. Izdanje čeka odluku osnivača (HOLD).

---

## A. Stanje repozitorijuma

| Stavka | Vrednost |
|---|---|
| Baseline | `469085b6a2a4a92b4ddfd929a5d88433743c66cc`. Na kraju sprinta isti je `origin/main` (`git ls-remote`), a isti je i produkcijski `/api/version` (`commit_source=RENDER_GIT_COMMIT`). |
| Commitova misija | 13 (N01–N06, N08, N10–N13, N15, N16), plus završni commit sa ledgerom i ovim izveštajem |
| Izmenjeni fajlovi | 38 fajlova, +1615 / −31 linija (do `05b5c22b`) |
| Produkcioni kod | `api.py`, `routers/{case_dna,copilot_ambient,email_notif,gdpr,intelligence_timeline,rokovi_lanac,search,smart_intake,whatsapp_notif}.py`, `templates/podnesci.py`, `uploaded_doc/extractor.py`, `static/vindex.js`, `static/sw.js` (v155) |
| CI / zavisnosti | `.github/workflows/tests.yml`, `.github/workflows/production-runtime.yml`, novi `requirements-dev.txt` |
| Migracije | **nema** |
| Push / PR / deploy | **nema** |

## B. Matrica 16 misija

| # | Tema | Status | Commit |
|---|---|---|---|
| N01 | Mrežna izolacija testova (kanarinac + plugin) | FIXED_VERIFIED | `63bb7bfa` |
| N02 | CI baseline: pytest-asyncio, git istorija, bu001 | FIXED_VERIFIED (lokalno; udaljeni CI NOT_RUN) | `d24b1b5a` |
| N03 | Dnevni cron: ugnežđen neuspeh prijavljen kao „ok“ | FIXED_VERIFIED | `4beaa97f` |
| N04 | Deaktivacija email podsetnika bez provere odgovora | FIXED_VERIFIED. Duplikat po danu je DEFECT_PROVEN_DEFERRED. | `b2053a2c` |
| N05 | Smart Intake prijavljuje „klijent dodat“ i kad veza nije upisana | FIXED_VERIFIED | `104a8e56` |
| N06 | Neispravan PDF daje 500 umesto jasne poruke | FIXED_VERIFIED | `69b90002` |
| N07 | (istraga) | NO_CHANGE_NEEDED_PROVEN | — |
| N08 | Finalize kad original nedostaje | NO_CHANGE_NEEDED_PROVEN (+ test) | `0cf7779f` |
| N09 | (istraga) | NO_CHANGE_NEEDED_PROVEN | — |
| N10 | Ručno uneti rok i potvrda advokata | NO_CHANGE_NEEDED_PROVEN. Ispravljeni runbook i zastareo komentar. | `d342c94d` |
| N11 | Hronologija: rok bez stanja odluke | FIXED_VERIFIED | `bcddb89f` |
| N12 | Pretraga vraća predmete u brisanju (tombstone) | FIXED_VERIFIED | `6f0856be` |
| N13 | Prazna vrednost briše oznaku [POPUNITI] u nacrtu | FIXED_VERIFIED | `bb0e266a` |
| N14 | V2 pregledač (189/189 u browseru) | NO_CHANGE_NEEDED_PROVEN | — |
| N15 | `maybe_single()` → None → 500 (5 mesta) | FIXED_VERIFIED. Ostalih 60 kandidata je samo inventarisano. | `a42fd95a` |
| N16 | M05 vektori siročad: arhitektonska odluka | DEFECT_PROVEN_DEFERRED (samo dokument) | `05b5c22b` |

Zbir: **8 funkcionalnih ispravki** (N03, N04, N05, N06, N11, N12, N13, N15) + **2 poboljšanja infrastrukture/testova** (N01, N02) = 10 FIXED_VERIFIED; **5 potvrđenih postojećih ponašanja** (N07, N08, N09, N10, N14); **1 arhitektonski dokument M05** (N16, nije implementiran). Odložen je i deo N04 (duplikat po danu).

## C. Stvarne ispravke (šta je bilo pokvareno → šta sada radi)

1. **N03.** Kada interni poziv za onboarding ili nedeljni pregled ima `greske > 0` ili nevažeći rezultat, dnevni cron je ranije ipak beležio „ok“. Sada `_poslato_greske_status` vraća „greska“ za svaki rezultat koji nije dokazano čist.
2. **N04.** Dugme „Deaktiviraj“ za email podsetnike je pokazivalo uspeh i kad server odbije zahtev. Sada se proverava `r.ok` i prikazuje se crvena poruka sa razlogom.
3. **N05.** Smart Intake je vraćao `klijent_dodat: true` i kada upis u `predmet_klijenti` nije uspeo. Sada je vrednost `true` samo posle stvarnog upisa.
4. **N06.** Oštećen ili lažan PDF je izazivao pypdf izuzetak koji je Smart Intake worker tretirao kao privremenu grešku: posao je ponavljan do 5 puta (~7,5 min) i završavao sirovim engleskim tekstom. Sada je to trajno odbijanje sa porukom „nije PDF“ (`DocumentSafetyLimitExceeded`, postojeći terminalni put).
5. **N11.** Hronologija je prikazivala rok bez stanja potvrde. Sada svaki rok nosi `stanje_odluke` i oznaku, iz istog izvora kao V2 Danas. Ako izvor ne odgovori, stanje je UNKNOWN i ta degradacija se prijavljuje (fail-closed).
6. **N12.** Globalna pretraga je vraćala predmete čije je brisanje započeto i njihove dokumente. Sada ih filtrira. Ako čitanje tombstone-a ne uspe, rezultati vezani za predmet se izostavljaju i označavaju kao nepotpuni.
7. **N13.** Kada model vrati `""`, `null` ili razmake, nacrt je ostajao prazan na tom mestu („Tužilac: ,“). Sada ostaje vidljiva oznaka `[… — POPUNITI]`.
8. **N15.** Pet ruta (GDPR izvoz, WhatsApp pretplata, provera vlasništva u copilot/podnesak, Case DNA, lanac rokova) davalo je 500 za nepostojeći red. Sada daju predviđeno prazno stanje ili 404. Nijedna provera vlasništva nije oslabljena.
9. **N01/N02.** Testovi i CI:
   - kanarinac dokazuje nula spoljnih mrežnih pokušaja u cron i notifikacionim testovima;
   - `requirements-dev.txt` dodaje pytest-asyncio za 143 async testa;
   - `fetch-depth: 0` za testove git istorije;
   - ispravljen bu001.

Za svaku ispravku postoji test koji pada na staroj verziji koda (mutacija ili pokretanje na baseline-u), kako je navedeno u ledgeru.

## D. Dokazano ispravno, bez izmene koda

- **N07, N09.** Ponašanje je potvrđeno testom ili čitanjem izvora (vidi ledger).
- **N08.** Finalize bez originala se ponaša ispravno. Raniji „crveni“ rezultat bio je greška mog test-okruženja: unutrašnji patch je pregazio spoljni. Dodat je namenski test.
- **N10.** Ručno unet rok takođe traži potvrdu advokata pre akcije, klijenta ili izvoza (`shared/rokovi.py::sme_pristupiti`). Pogrešna je bila moja N04 dokumentacija, ne kod; ispravljena je.
- **N14.** V2 tokovi: 189/189 provera u pravom browseru.

## E. Odloženo, sa dokazom

| Nalaz | Dokaz | Zašto nije ispravljeno |
|---|---|---|
| **M05 / kontraprimer 0.** Dva dokumenta istog sadržaja u istom predmetu dele identitet vektora, pa brisanje jednog briše vektore i drugog. | `scratchpad/ns3/n16_deljeni_identitet_demo.py`: DELETED 3, drugom ostaje 0/3 | Menja identitet vektora i ponašanje brisanja; to je arhitektonska odluka. Predlog: `docs/architecture/VINDEX_M05_ORPHAN_VECTOR_DECISION.md` |
| Brisanje predmeta ostavlja vektore siročad | isti dokument | isto |
| Upload ruta ne proverava tombstone | isti dokument | isto |
| N04: provera duplikata po danu preskače rok drugog predmeta istog dana | `scratchpad/ns3/n04_demo_dup_po_danu.py` | Menja semantiku slanja podsetnika, a slanje podsetnika je u produkciji ionako blokirano (403) |
| 60 preostalih `maybe_single` kandidata | `VINDEX_NS3_N15_MAYBE_SINGLE_INVENTAR.md` | Samo inventar; svaki kandidat traži posebnu procenu |

## F. Testovi

- Novi testovi: `tests/test_ns3_n01…n15_*.py` (10 fajlova).
- Prilagođene lažne baze: `tests/_schema_fake.py` i `tests/ns005_harness.py` dobijaju `not_` kao property, kao u postgrest-py.
- **Pun lokalni suite.** Uslovi: Windows, Python 3.13, zaključan redosled (`-p no:randomly`), mrtav proxy.

| | failed | passed | skipped |
|---|---|---|---|
| Baseline `469085b6` | 19 | 11153 | 227 |
| Grana `05b5c22b` | 16 | 11292 | 227 |

- Poređenje po ID-u testa: **0 novih padova** i **3 popravljena** (bu001).
- Preostalih 16 padova postoji i na baseline-u. Svi su uzrokovani okruženjem ili su već poznati:
  - 8 `[trio]` (trio nije instaliran);
  - 4 testa minimalne veličine fonta (`faza1`);
  - `ns003` heš fixture-a;
  - `phoenix013`;
  - 2 `rc_cold_start`.
- Ciljani suite koji je ceo zelen ne znači da je ceo repozitorijum zelen. Repozitorijum lokalno nije zelen (16 padova sa baseline-a).

## G. CI baseline

- Udaljeni CI je imao 174 pada na `469085b6`, u klasterima: async 143, git istorija, bu001, psycopg, opcioni SDK-ovi, font, phoenix013, r7.
- N02 cilja klastere async, git istorija i bu001.
- **Udaljeni CI za ovu granu je NOT_RUN**, jer push nije dozvoljen. Smanjenje broja padova u CI-ju je dokazano samo lokalno, kao očekivanje, a ne kao CI rezultat.

## H. Bezbednost i pravna tačnost

- RLS i autorizacija nisu oslabljeni. U N15 nedostajući red vlasništva i dalje vodi u 404, nikad u dozvolu.
- N11 i N12 su fail-closed: kada izvor ne odgovori, rezultat je UNKNOWN ili se izostavlja, nikad „potvrđeno“ ili „prikazano“.
- U testovima nema pravih dokumenata klijenata ni pravih tokena. U logove ne ulazi sadržaj dokumenata.
- Mrežna izolacija:
  - kanarinac (N01) beleži 0 pokušaja;
  - u punom suite-u je bio aktivan mrtav proxy i postojeća brana iz `conftest.py`;
  - deny-all plugin nije globalno učitan, i to je namerno i dokumentovano.
- Produkcija je samo čitana (GET `/api/version`). Nije bilo upisa, slanja email-a ili SMS-a, cron-a ni migracija.
- Uspešno parsiranje se nigde ne tretira kao pravna izvesnost. N13 upravo čuva vidljivu oznaku za nepoznatu činjenicu.

## I. Kontinuitet proizvoda: koji pravni tokovi su sada pouzdaniji

- **Rokovi.** Hronologija pokazuje da li je rok potvrđen (N11). Cron više ne prikriva neuspeh (N03).
- **Prijem dokumenata.** Lažni PDF daje jasnu poruku (N06), a veza klijent–predmet se ne prijavljuje lažno (N05).
- **Nacrti podnesaka.** Nepoznate činjenice ostaju označene (N13).
- **Brisanje predmeta.** Predmet u brisanju ne izlazi u pretrazi (N12). Vektori su i dalje otvoreni (M05).
- **GDPR izvoz i Case DNA.** Ne padaju za korisnike bez opcionog reda (N15).
- **Podsetnici.** Deaktivacija je iskrena (N04). Samo slanje i dalje ne radi u produkciji (403, CRON_TOKEN ≠ CRON_SECRET).

## J. M05: odluka (nije implementirano)

Dokument `docs/architecture/VINDEX_M05_ORPHAN_VECTOR_DECISION.md` preporučuje:
- **Faza 1 (C0+C1+C2):** bez migracije i bez promene identiteta. Brisanje dokumenta ne briše vektor dok bilo koji drugi živ red deli isti identitet; uz to idu provera tombstone-a pri uploadu i kontrolisano čišćenje siročadi.
- **Faza 2 (opciono):** Opcija A, identitet po redu dokumenta.

Ništa od ovoga nije implementirano. Raniji M05 pokušaj je vraćen (`e58c967f`), jer je bio destruktivan pod konkurentnim radom.

## K. Akcije osnivača

1. Pregledati granu `night/iron-continuity-ns3` i odlučiti o push-u i Draft PR-u. Tek tada se pokreće udaljeni CI.
2. Odlučiti o M05 Fazi 1 (preporuka dokumenta).
3. Podsetnici: uskladiti `CRON_TOKEN` i `CRON_SECRET` na Renderu (email cron dobija 403 u produkciji). Zatim odlučiti o duplikatu po danu (N04).
4. Odlučiti da li se Smart Intake poslovi iz dead-letter reda ponovo obrađuju kada se isti fajl ponovo učita.
5. Odobriti posebnu misiju za 60 preostalih `maybe_single` kandidata.

## L. Novi rizici otkriveni u sprintu

| Rizik | Status |
|---|---|
| Kontraprimer 0 (deljeni identitet vektora) | PROVEN, nije ispravljeno |
| Vektori siročad posle brisanja predmeta | PROVEN |
| Upload bez provere tombstone-a | PROVEN |
| Duplikat podsetnika po danu (drugi predmet) | PROVEN, odloženo |
| Prozor duplikata markera u koraku 3 pipeline-a | INFERRED (nije dokazano) |
| Poređenje boja u hronologiji bez dijakritika nikad ne pogađa | Zabeleženo |
| from-template ruta guta neuspeh veze | Zabeleženo |
| Dead-letter Smart Intake poslovi se ne obnavljaju ponovnim uploadom | Odluka |

## M. Preporuka za izdanje

**RELEASE HOLD.** Grana je kvalifikovana za nezavisan pregled PR-a:
- svaka ispravka ima test;
- pun lokalni suite nema novih padova u odnosu na baseline;
- nema migracija;
- nema slabljenja bezbednosti.

Pre spajanja je potrebno:
1. odluka osnivača o push-u;
2. udaljeni CI uporediv po ID-u testa sa 174 pada sa baseline-a;
3. ručna provera N04 (vindex.js) i N11 u browseru posle deploy-a.

Ovo nije oznaka spremnosti za produkciju; to je preporuka za pregled.

## N. Handoff gejtovi (dodato pri pripremi Draft PR-a)

### Klasifikacija tri nova rizika (izvor + izvršen dokaz na OBA stabla)

| Rizik | Izvor | Dokaz | Klasa |
|---|---|---|---|
| 1. Brisanje deljenih vektora između identičnih dokumenata | `shared/vector_deletion.py` (identitet `prefiks_dokumenta(predmet_id, content_sha256)`); fajl **nije menjan** na grani | demo na `469085b6` i na grani: `DELETED 3`, drugom dokumentu ostaje 0/3 | **EXISTING BASELINE DEFECT** |
| 2. Upload paralelan sa brisanjem predmeta | `api.py::predmet_upload_auto_analyze` bira `select("id,naziv,tip")` bez `brisanje_zapoceto` — baseline `api.py:5987`, grana `api.py:6005` (identičan red) | čitanje izvora na oba stabla | **EXISTING BASELINE DEFECT** |
| 3. Isti dan: podsetnik drugog predmeta se ne šalje | `routers/email_notif.py` (grana menja samo komentar) | demo na oba stabla: drugo pokretanje `poslato 0, preskoceno 0` — i nije prijavljeno kao preskočeno | **EXISTING BASELINE DEFECT** |

Grana ne dodaje nijedan poziv brisanja vektora niti Pinecone operaciju (`git diff` produkcionog koda: 0 pogodaka za pinecone/delete/vector).

### Izolacija CI-ja (gejt 4)

- Python sloj: brana u `tests/conftest.py` (`getaddrinfo`) nepromenjena; CI env koristi samo lažne vrednosti (`fake.supabase.co`, `sk-fake`).
- Jedini test koji izvršava workflow korak sa produkcionim URL-om je `tests/test_alerts_email_cron_contract.py` (`https://vindex.rs/email-notif/send-reminders`). Do sada ga je štitio jedan sloj (lažni `curl` + proba).
- **Dodat drugi, nezavisan sloj:** okruženje koraka dobija `HTTP(S)_PROXY`/`ALL_PROXY` = `http://127.0.0.1:9` (mrtav port), `NO_PROXY` se briše.
- **Adversarijalni dokaz:** mutant bez lažnog `curl`-a i bez probe (tačno scenario PR #45), sa posmatračem na mestu mrtvog porta: pravi `curl` je poslao `CONNECT vindex.rs:443` **posmatraču, ne mreži**; test pada. U pravom testu taj zahtev ide na port 9 i odbija se lokalno. Mutant nad baseline-om NIJE pokrenut (išao bi u produkciju).
- Rezultat: `test_alerts_email_cron_contract.py` + kanarinac N01 = 40 passed.

---

## Samosertifikacija (20 pitanja)

1. Da li je išta pushovano, spojeno ili pušteno? **Ne.** `origin/main` i produkcija su i dalje `469085b6`.
2. Da li je ijedan produkcioni upis, SQL, Pinecone brisanje ili slanje email-a ili SMS-a izvršeno? **Ne.**
3. Da li su korišćeni pravi produkcioni tokeni u testovima? **Ne.** Ključ je lažan (`sk-test-dummy`).
4. Da li je ijedna mrežna brana oslabljena? **Ne.** Dodata je nova (N01); postojeća brana u `conftest.py` nije dirana.
5. Da li je oslabljen RLS ili autorizacija? **Ne.** U N15 je 500 postalo 404; testovi „tuđ“ i „nepostojeći“ predmet traže 404.
6. Da li je ijedna istraga prijavljena kao ispravka? **Ne.** N07, N08, N09, N10 i N14 su NO_CHANGE.
7. Da li svaka FIXED stavka ima test koji pada na starom kodu? **Da**, po ledgeru (mutacija ili baseline).
8. Da li je pun suite zelen? **Ne.** 16 padova, svi postoje i na baseline-u.
9. Da li postoje novi padovi u odnosu na baseline? **Ne** (poređenje po ID-u, zaključan redosled).
10. Da li je udaljeni CI potvrdio N02? **Ne.** NOT_RUN.
11. Da li je M05 implementiran? **Ne.** Postoji samo odluka.
12. Da li je N04 dokumentacija bila tačna? **Ne u prvoj verziji.** Ispravljena je u N10.
13. Da li je ijedan „crveni“ nalaz bio lažan? **Da**, N08, zbog greške harness-a. Prijavljeno je.
14. Da li je u testovima korišćen stvaran dokument klijenta? **Ne.** Sve je sintetičko.
15. Da li se loguje sadržaj dokumenata ili tajne? **Ne.**
16. Da li je dodata migracija? **Ne.**
17. Da li je `services/event_bus.py` menjan? **Ne.**
18. Da li je ijedna deljena grana resetovana, rebase-ovana ili stash-ovana? **Ne.**
19. Da li postoje nalazi koji su samo pretpostavka? **Da**, prozor markera u koraku 3. Označen je kao INFERRED.
20. Da li je presuda strožija od dokaza? **Ne.** COMPLETE znači da je svih 16 misija zatvoreno sa dokazom. RELEASE_HOLD znači da izdanje i dalje traži odluku osnivača i udaljeni CI.
