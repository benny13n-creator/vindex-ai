# Miroslav — lokalna integracija, 7. novembar 2026.

Osnovica `da50b0203a90e9d9dbc9226e7492e4c303c61500` potvrđena na lokalnom main, origin/main i GitHub main (drift 0). Source i S08 su imali čisto radno stablo na početku. Odvojena grana `codex/miroslav-integration`. GitHub PR #69 `59669958b695330f9b66fcbb90b410579a5232ed`; PR #72 `3e8bed16b2eac72174823e3b9801163b11fc4808`. Identitet integrisanog commita i rezultati konačnog izvršenja su u predaji.

## Matrica zahteva

| Zahtev | Korisnički ishod | Stanje i dokaz | Preostali gap |
| --- | --- | --- | --- |
| MIR-01 | Prijem spisa, kontinuitet i povlačenje izvora | PROVEN / LOCAL_TEST za sintetičke scenarije; S02 ispravljen | OCR, S08 i prihvatanje korisnika |
| MIR-02 | Strategija iz spisa sa dokazivim procesnim stanjem | PROVEN / LOCAL_TEST za ugovor tri rute i čl. 371; odvojeni P10 red/green | UNKNOWN za sadržaj stvarnog modela; nasleđena pogrešna referenca na čl. 368 ZPP |
| MIR-03 | Radni nacrt, ljudsko usvajanje, odobrenje, DOCX | PROVEN / LOCAL_TEST nad digitalnim spisom; promena izvora čuva snimak i odobrenje tačnog teksta | Automatska provera izvora nije deo ugovora; korisnički test |
| MIR-04 | Korporativne radnje iz validiranog procesa | UNKNOWN; nema potvrđena tri scenarija | Potreban konkretan unos od Miroslava |
| MIR-05 | Kontrolisane radnje i priprema nakon promene | STATIC: postojeće NS007 komponente i lokalni testovi | Odvojena autorizacija aktivacije, S08 i prihvatanje korisnika |

## S01–S10

| Sprint | Ishod | Granica |
| --- | --- | --- |
| S01 | CLOSED | Izvor zahteva je founder input u MIR001_TASK_LEDGER.md i trenutni mandat; transkript nije utvrđen |
| S02 | FIXED_LOCAL | N-13/N-15 su radnje tužioca zapisane u sudskom dokumentu. DOK-08 nosi navod veštaka o osam dana i datum dopune; autoritativni početak i istek nisu utvrđeni |
| S03 | BLOCKED_SPECIFIC | Tesseract nedostupan; digitalni dokument i granice delimičnog čitanja mogu se dokazati odvojeno |
| S04 | RELEASE_PENDING | Kontinuitet i povlačenje izvora imaju lokalne provere; konkurentna potvrda ostaje S08 kapija |
| S05 | FIXED_LOCAL | MIR002_CONTRACT_READY_LOCAL; stvarni izlaz modela UNKNOWN |
| S06 | BLOCKED_SPECIFIC | HOLD_AI_QUALITY_UNKNOWN; četiri ista deterministička slučaja, bez autorizovanih plaćenih poziva |
| S07 | CLOSED | PROVEN / LOCAL_TEST digitalni spis, eksplicitno usvajanje i DOCX; izvor promenjen između predloga i odobrenja, sačuvani snimak nije izmenjen |
| S08 | BLOCKED_SPECIFIC | S08_REQUIRES_MINIMAL_FIX; 148 izostavljena; vidi odvojeni paket |
| S09 | RELEASE_PENDING | READY_FOR_SEPARATE_ACTIVATION_APPROVAL samo za dokazani lokalni ugovor; aktivacija zahteva zasebnu odluku |
| S10 | BLOCKED_SPECIFIC | Potrebna tri scenarija iz postojećeg ručnog procesa i stvarno korisničko prihvatanje |

## Implementacija i dokazi

- S02 menja samo oracle i testove koji ga koriste. Negativni test pre korekcije je dobio `['SUD', 'SUD']` za N-13/N-15. U testu posledica datum je izričito vrednost koju predlaže stub, nezavisna od oracle-a. Sintetički tekst je očuvan.
- Pre korekcije red iz stvarnog intake sistemskog prompta navodio je tri godine. Čl. 371 daje deset godina ako zakon ne odredi drugi rok. [Vrhovni sud Rev2 122/2026](https://www.vrh.sud.rs/sr-lat/rev2-1222026-312141-312155-319312)
- Prenet je samo MIR002 kod i potrebni testovi iz #69. `/pipeline` koristi `run_agent`, pa posebna implementacija nije potrebna. Budžet izvoda i prioritet upozorenja ostaju iz #69. Pravilo roka traži merodavan sudski izvor i dokaz početnog događaja. Model, broj poziva, naplata i osnovni sistemski promptovi ostalih agenata su očuvani.
- Odvojeni P10 reviewer je reprodukovao curenje teksta dokumenta B sa pogrešno pridruženim ID-em predmeta A. Stari test je gledao samo procesni blok. Dva čitanja dokumenata sada traže i vlasnika, a negativni test proverava ceo prompt i evidenciju izvora.
- PROVEN / STATIC: referenca na čl. 368 u zaključanom susednom intake pravilu je nasleđena. Opšte pravilo o žalbi na prvostepenu presudu je u čl. 367 ZPP i računa se od dostavljanja prepisa, uz izuzetke. Ovo ostaje konkretna release kapija izvan odobrene izmene čl. 371. [Zvanični ZPP](https://pravno-informacioni-sistem.rs/SlGlasnikPortal/eli/rep/sgrs/skupstina/zakon/2011/72/2/reg)
- S06 eksperiment pokrenuo je P04, P05, P06 i P09 bez teksta na istom kodu i spisu, jednom bez i jednom sa tri F4 pravila, dodata samo u memoriji. Deterministički kontekst ostaje uporediv; kvalitet odgovora nije meren. #72 je izostavljen.
- S07 promena teksta DOK-07 posle generisanja proverena je i odvojenim reviewerom i dodatim regresionim testom. Neusvojen predlog ne prolazi odobrenje ili DOCX. Odobreni tekst i DOCX odgovaraju eksplicitno usvojenom i sačuvanom tekstu. Provera trenutnog izvora ostaje označena kao neizvršena.

## Matrica izvršenja

| Komanda ili proba | Okruženje | Dokaz |
| --- | --- | --- |
| `git ls-remote origin refs/heads/main refs/pull/69/head refs/pull/72/head` | GitHub read-only | Sva tri refa potvrđena |
| Uvezi intake prompt i proveri 10 godina na osnovici | LOCAL_TEST | RED, stvarno 3 god. |
| Oracle N-13/N-15 na osnovici | LOCAL_TEST | RED, oba statusa SUD |
| P10 test sa proverom kompletnog prompta pre korekcije | LOCAL_TEST, odvojeni reviewer | RED, tekst curi izvan procesnog bloka |
| `python -B -m pytest tests/test_migration_147_p0_privilegije_postgres.py` | ISOLATED_POSTGRES 17.9, key-value DSN | 56 provera, uključujući RLS/RPC, mutacije REVOKE/GRANT i konkurentni worker |
| `python -B -m pytest tests/test_mir001_c3b_usvajanje.py::test_promena_izvora_izmedju_predloga_i_odobrenja -q -p no:cacheprovider` | LOCAL_TEST, digitalni spis, stub modela | 1 PASS |
| `python -m pytest tests/test_s08_postgres_concurrency.py tests/test_s08_withdrawn_source.py -q` | Odvojeni S08 commit, ISOLATED_POSTGRES | 22 PASS, dodatne adversarijalne probe oborile gate |
| `python -B -m pytest tests/ -q -rfEs -p no:cacheprovider --tb=short` | Integrisani SHA, sintetičko okruženje, loopback PG, bez Tesseract-a | Konačni zbir i neuspele provere navedeni u predaji |

## MIR-04 acceptance obrazac

Miroslav popunjava odvojeno **scenario 1**, **scenario 2** i **scenario 3** iz svog stvarnog procesa. Za svaki scenario upisuje šest polja. Nijedan scenario nije unapred pretpostavljen.

| Scenario | Ulazni dokument ili događaj | Današnja ručna radnja | Očekivani rezultat | Obavezna kontrola ili odobrenje | Učestalost | Kriterijum prihvatanja |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | | | | | | |
| 2 | | | | | | |
| 3 | | | | | | |

## Kontrolisani beta handoff

Koristi samo sintetički P 9901/2026. U kontrolisanom okruženju unesi DOK-01–07, zabeleži stanje čitanja svakog dokumenta, proveri izvore protivrečnosti K-01/K-02 i pokreni parničnu strategiju. Proveri da nepoznat početak roka ostane nepoznat. Generiši nacrt, proveri izvode, usvoji samo odabrane stavke i izvezi odobren tekst u DOCX. Dodaj DOK-08, uporedi strategiju i radnje, zatim povuci jedan izvor i proveri posledice. Zabeleži prihvaćeno/odbijeno po koraku, datum, tester i konkretan primer. Ovaj handoff je skripta za budući test; REAL_USER_ACCEPTED je UNKNOWN.

## Odluka

`CODE_READY` za lokalni S02 i deterministički MIR002 opseg. `RELEASE_PENDING_CI_OR_APPROVAL` i konkretne kapije: S08 hash/privilege korekcija, zaključana ZPP referenca, OCR i sadržinsko merenje, CI, odobrenje i korisnički test. `CONTROLLED_BETA_READY` i `FULL_MIROSLAV_REQUIREMENTS_ACCEPTED` nisu dokazani. Nema push-a, merge-a, deploy-a, produkcionih promena ili NS007 aktivacije.
