# FRG001 — dokazi: integritet događaja dokumenta i vezivanje zakona za član

**Grana:** `feature/vindex-frg001-final-release-gates` · **Draft PR #15** → `feature/vindex-osb003-release-breaker` (PR #14)
**Početni SHA:** `db37af55` (vrh PR #14, potvrđen nepromenjen) · **Produkcija:** `80c3902` (nedirnuta)
Oznake: **P** dokazano · **I** zaključeno · **A** pretpostavljeno · **U** nepoznato.

---

## Task A — BETA-DEF-004: dokument → događaj

### A1. Granica (P, iz koda)
| Pitanje | Odgovor |
|---|---|
| Red koji označava prihvaćen dokument | `predmet_dokumenti` (insert u `_finalize_intake_job_core`); posao je „prikačen“ kad `intake_jobs.predmet_id` + `assimilation_complete` |
| Znak završene klasifikacije | `predmet_dokumenti.klasifikovan_at` (čuvar idempotencije u `case_evolution._consequence_evidence_classify`) |
| Ko piše događaj | ista funkcija, odvojenim pozivom `services/event_bus.py::emit_durable` → outbox `events` |
| Transakcija dokument+događaj | **ne postoji** — dva zasebna PostgREST poziva; atomski RPC postoji samo za status posla (`complete_intake_job`) |
| Ključevi idempotencije | `content_sha256` po korisniku (dokument); `claim_intake_finalize` (`finalizing_at`, 120 s); `(event_id, consequence_name)` UNIQUE; `klasifikovan_at` |
| Retry / dead-letter | `DispatchLoop` (3 s) → `dispatch_pending_events`; do `MAX_DISPATCH_ATTEMPTS = 5`, zatim dead-letter oznaka |
| Događaj pre ili posle HTTP odgovora | pre — u istom zahtevu, posle upisa dokumenta |
| Postojeći oporavak (pre FRG001) | nijedan za ovaj slučaj: nema sweep-a; brzi izlaz (`predmet_id` + `assimilation_complete`) zauvek preskače posao; ručno „Klasifikuj“ postoji samo u starom UI-ju |

### A2. Reprodukcija (P)
`tests/test_frg001_dogadjaj_dokumenta.py::test_pad_upisa_dogadjaja_nije_lazno_zavrsen_i_ponovni_pokusaj_dovrsava` na **starom** kodu pada: finalize vraća **200**, posao je prikačen, dokument postoji, `predmet_dokazi == []` i posle ponovnog pokušaja. Isto stanje je u OSB003 opisao `test_beta_def_004_*`.

**Prateći kvar nađen tokom rada (P):** `emit_durable(event_id=...)` je zvao `insert(..., ignore_duplicates=True)`. Pravi klijent supabase-py **2.28.3** (zakucan u `requirements.txt`) `insert()` nema taj argument, pa poziv diže `TypeError` pre ikakvog mrežnog zahteva. Dokazano na pravom `create_client` bez mreže (`tests/test_frg001_emit_durable_pravi_klijent.py`: stari kod → `TypeError`). Fake-ovi (ns006, S6) su argument prihvatali i to sakrili.
- **Posledica u produkciji (I):** `main` ima isti kod. COI događaj `NEW_CLIENT_LINKED` iz Smart Intake-a koristi `event_id`, pa se svaki upis 3× sruši i odgovor kaže `COI_FAILED`. COI provera iz Smart Intake-a se, dakle, ne zakazuje. Produkcioni logovi nisu čitani (U).

### A3. Opcije
| Opcija | Ishod |
|---|---|
| A — postojeći oporavak dovoljan | **OBORENO**: brzi izlaz čini ponovni pokušaj no-op-om; nema reconciler-a; V2 nema ručnu akciju |
| B — minimalna ispravka u postojećem putu | **IZABRANO** (bez migracije, bez nove pozadinske komponente) |
| C — postojeći reconciler | nije potreban; nov sweep bi bio nov zakazan proces (traži odobrenje) |
| D — NO-GO | ne važi posle ispravke; ostaci su ispod |

### Ispravka (`2248d832`, `a5813350`)
1. Ako obavezni događaj (`NEW_EVIDENCE_REGISTERED`, `DOCUMENT_ACCEPTED`) nije upisan: posao se **ne** obeležava kao prikačen, zauzeće se oslobađa (CAS na `finalizing_at`) i odgovor je **503**. V2 (`api.js`) 5xx tretira kao `ishodNepoznat` → „Ishod nije poznat… proverite pre ponovnog pokušaja“, a dugme „Prikači“ ostaje jer `job.predmet_id` nije upisan.
2. Nastavak (postojeći `source_intake_job_id` / `content_sha256`, isti predmet): postojeći neklasifikovan dokument ponovo dobija `NEW_EVIDENCE_REGISTERED`; `DOCUMENT_ACCEPTED` se ponavlja pri nastavku.
3. Stabilan identitet: `uuid5(dokument)` i `uuid5(posao)` → ponovni upis istog događaja je no-op.
4. `emit_durable`: `upsert(on_conflict="id", ignore_duplicates=True)` = `ON CONFLICT (id) DO NOTHING`; bez `event_id` je i dalje običan `insert`.
5. Fake `ns006` i S6 fake sada imaju potpis pravog klijenta. Lint BLK-2.1 broji i `upsert` pisce.

### A4. Adversarijalna matrica (P, stvarne rute + IntakeWorker + dispečer)
| Slučaj | Test | Rezultat |
|---|---|---|
| Prekid procesa odmah posle upisa dokumenta | `test_prekid_procesa_posle_upisa_dokumenta_pa_nastavak` | posao neprikačen; brz pokušaj 409; posle 120 s nastavak dovršava, 1 dokument, 1 događaj, tvrdnje postoje |
| Upis događaja padne | `test_pad_upisa_dogadjaja_nije_lazno_zavrsen_i_ponovni_pokusaj_dovrsava` | 503, posao neprikačen, zauzeće slobodno; ponovni pokušaj dovršava |
| Pad samo `DOCUMENT_ACCEPTED` | `test_pad_samo_document_accepted_*` | 503; nastavak bez drugog događaja dokaza; Genome osvežen |
| Identičan zahtev ponovljen | `test_identican_zahtev_i_dupla_isporuka_ne_dupliraju_nista` | `already_finalized`, ništa novo |
| Dupla isporuka događaja | isti | broj događaja, tvrdnji i dokumenata nepromenjen |
| Ponovni upis istog događaja | `test_ponovni_upis_istog_dogadjaja_je_no_op` | nema novog reda |
| Događaj postoji, posledica padne | `test_dogadjaj_postoji_ali_posledica_padne_*` | nije lažno završeno; dispečer dovršava |
| Dve istovremene finalizacije | `test_istovremena_finalizacija_drugi_poziv_409_bez_upisa` | 409, bez upisa |
| Ubacivanje događaja od drugog korisnika | `test_tudj_korisnik_ne_moze_*` | 404; B ne izaziva nijedan događaj za A-in dokument; isti sadržaj kod B je zaseban |
| Referenca na drugi predmet | `test_nastavak_ostaje_u_predmetu_gde_je_dokument_upisan` | dokument i događaji ostaju u predmetu gde je dokument upisan |
| Baza pada i tokom oporavka | `test_baza_pada_i_tokom_oporavka_*` | 2× 503, stanje nepotpuno i oporavljivo, zatim uspeh |
| Zapisi nastali pre ispravke | `test_zapis_pre_ispravke_nije_automatski_oporavljen_ali_je_vidljiv` | **nema automatskog oporavka**; V2 analiza prikazuje „nije klasifikovan“ |
| Audit | `document_assimilated` se ne ponavlja pri nastavku (grana duplikata ne loguje) | (P iz koda + testova sprint006) |

**Mutacije (P):** 4/4 uhvaćene — bez ponovnog emitovanja (4 pada), bez 503 (5), bez stabilnog ID-ja (3), bez nastavka DOCUMENT_ACCEPTED (4). Na starom kodu: 9/11 FRG001 testova pada; prepisan `lz002` test pada.

### Ostaci Task A (nisu zatvoreni ovim PR-om)
- **Prekid procesa** između dva upisa: oporavak je **ručni** (ponovno „Prikači“ posle ≤120 s; ili ponovo otpremiti isti fajl, jer isti sadržaj vraća isti posao — P na API nivou, OSB002). Stanje je vidljivo: posao nije prikačen, a dokument je u analizi „nije klasifikovan“. Automatski oporavak bi tražio nov zakazan proces (odobrenje).
- **Zapisi pre ispravke:** nema automatskog oporavka. Produkcija (`80c3902`) još pokreće kod pre OSB002, koji pri finalizaciji upisuje `klasifikovan_at`, pa V2 Smart Intake dokumenti u produkciji verovatno **nemaju tvrdnje, a izgledaju klasifikovano** (I; OSB002 je izbrojao 3 takva dokumenta). Ručni put je „Reklasifikuj“ u starom UI-ju (troši kredit).
- **Stari upload (`api.py`)** je i dalje fail-soft; stari UI dokument prikazuje kao „neklasifikovan“ uz dugme „Klasifikuj“ (ručno). Nije menjano.
- **Dead-letter posle 5 pokušaja posledice:** postojeće ponašanje, vidljivo u metrikama (migracija 129). Nije menjano.
- **Promena ponašanja posle deploy-a:** COI iz Smart Intake-a će prvi put stvarno biti zakazan, pa se mogu pojaviti COI upozorenja.

**Task A: PASS** — nema tihog trajnog nepotpunog dokumenta na putu V2 Smart Intake; oporavak je deterministički (ručno pokretan) i dokazan.

---

## Task B — zakon + član

### B1. Ugovor (P, iz koda)
- Čuvar: `main.py::_proveri_halucinaciju`. Pozivaoci: `_parsiraj_strukturni_odgovor` (pitanja) i `ask_nacrt` (nacrti). Oba dobijaju izvore u formatu `ZAKON: <law>\nČLAN: <article>` iz `retrieve.py::_formatiraj_match` (Pinecone metapodaci; svi izlazi pravnog izvora prolaze kroz tu funkciju).
- Odgovor prikazuje citate pod „PRAVNI OSNOV [ISKLJUČIVO VERIFIKOVANO IZ KONTEKSTA]“, dakle prolaz čuvara **jeste** tvrdnja o proveri.
- Neproveren citat: retry sa MEDIUM modelom, zatim postojeća blokada **samo pravnog dela** (`_format_halucination_block`; činjenice iz dokumenta ostaju).
- Statusnu liniju računa backend iz retrieval-a (`_izracunaj_statusnu_potvrdu`), nikad iz modela.

### B2. Reprodukcija (P)
Na starom kodu čuvar prihvata:
- „član 201 Zakona o oglednom postupku“ kada je 201 samo u izvoru drugog zakona;
- svaki citat zakona čiji izvor nije dostavljen (ako se broj nađe bilo gde);
- **svaki ćirilični citat** (regex ga nije video, pa ni „члан 9999“ nije proveren);
- svaki odgovor koji sadrži marker „nije dostupno“ (tekst modela je gasio proveru).

12 FRG001 testova pada na starom `main.py`.

### B3. Šta se proverava
| Nivo | Da li se proverava |
|---|---|
| `SOURCE_MATCHED` | **da** — citat imenuje zakon, a identitet se poklapa sa zaglavljem izvora |
| `ARTICLE_PRESENT` | **da** — član postoji u izvoru TOG zakona; za citat bez naziva zakona: broj negde u kontekstu (stari nivo) |
| `VERSION_VALIDATED` | **ne** — sistem nema proveru verzije ni datuma važenja; nigde se ne tvrdi (`version_validated: False`) |
| `LEGAL_CORRECTNESS` | **ne** |

### B4. Ispravka (`b5b9d5a8`)
- Identitet izvora: zaglavlje retrieval-a, kanonizovano kroz postojeći `_ZAKON_KODOVI` (kod ↔ vrednost u korpusu) i pune nazive iz `SL_GLASNIK_MAP`. Jedini nov podatak je alias `krivični zakonik ↔ kz`, jer korpus KZ beleži kao „KZ“.
- Citirani zakon: samo zakon naveden **neposredno** uz citat (posle, ili pre, npr. „ZOO čl. 5“), uz padeže, ćirilicu, `čl.`, stav/tačka/`2)`. Tematski `LAW_HINTS` se **ne** koristi.
- Odbija se:
  - pogrešan par zakon/član;
  - član koji nije u izvoru tog zakona;
  - zakon čiji izvor nije dostavljen;
  - imenovan, ali neprepoznat propis;
  - član označen kao brisan.
- Citat bez naziva zakona („člana 5 ovog zakona“, „člana 5 Zakona,“) ostaje na starom nivou.
- ZOO izuzetak šablona važi samo za ZOO ili za citat bez zakona.
- Marker modela gasi proveru samo kad odgovor ne citira nijedan član.
- Bez LLM poziva, bez nove ingestije, bez izmene retrieval-a.

### B5. Obavezni testovi (`tests/test_frg001_zakon_clan_vezivanje.py`, 30 prolazi — P)
1 tačan zakon + član → SOURCE_MATCHED · 2 nepostojeći član → odbijen · 3 pogrešan zakon sa brojem iz drugog → odbijen · 4 bez identiteta izvora → nema proverenog autoriteta · 5 padeži → prepoznati · 6 ćirilica → prepoznata · 7 skraćenica (ZOO, ZR, KZ↔Krivični zakonik) → prepoznata · 8 verzija → nikad validirana · 9 bez autoriteta → neizvesnost ostaje (STATUS_ERR) · 10 tekst modela ne menja identitet (marker, lažno zaglavlje u odgovoru).

Dodatno: brisan član, isti broj u dva zakona, ZOO izuzetak, stvaran pozivalac `_parsiraj_strukturni_odgovor`, 7 realnih formulacija bez lažne blokade („Ustava RS“, „ZR-a“, „tač. 2)“, Sl. glasnik u zagradi).

**Mutacije (P):** 6/6 uhvaćene — uklonjeno vezivanje (28 padova), bez ćirilice (1), marker gasi proveru (1), identitet iz teksta modela (1), bez brisanog člana (1), nepoznat zakon prolazi (4).

### Ograničenja Task B
- „članovima 179 i 180 Zakona o radu“: proverava se samo prvi broj, na starom nivou (postojeće ograničenje).
- **Strože nego ranije (I, uticaj U):** citat zakona koji je samo u korisnikovom dokumentu, a ne u indeksiranom izvoru, i netačan naziv (npr. „Zakona o krivičnom postupku“ umesto „Zakonika“) sada se blokiraju. Stopa blokada u produkciji je nepoznata; posle deploy-a pratiti log `HALUCINACIJA v2.0`.
- Identitet zavisi od metapodatka `law` u korpusu (A). Zakon čija vrednost nije u registrima prepoznaje se samo kao tačan naziv iz zaglavlja.

**Task B: PASS** — pogrešno uparen zakon/član ne može da prođe kao proveren u testiranom cevovodu citata.

---

## Regresija i CI
- **Lokalno (P):** 184 povezana fajla (Smart Intake, finalize, event bus, Case Evolution, Genome, Case Actions, čuvar citata, Law Brain, RH001/RH002 ACL, JWT, tim/delegacija, OSB002/OSB003), seme `12345`, JUnit, poređenje po identitetu testa naspram `db37af55`: **0 novih padova**; 3060 prema 3019 prošlih. Isti stari pad postoji na obe strane (`test_ca_trust_boundary::test_M19_*`), a jedan fajl na obe strane traži `OPENAI_API_KEY` pri učitavanju.
- 20 privremenih padova je usput razrešeno, svaki iz poznatog uzroka:
  - harness bez izlaza za događaje (`emit_durable` je išao na pravu mrežu, ranije tiho) → `AsyncMock`;
  - 2 testa starog fail-soft ugovora → prevedena na novi ugovor;
  - 3 testa sa izmišljenim formatom konteksta ili sa fake-om koji prihvata nepostojeći argument → ispravljena.
- **CI (P)** — ručno pokrenut (`workflow_dispatch`, workflow-i se automatski pokreću samo za PR-ove ka `main`) na FRG001 (`b5b9d5a8`) i na nepromenjenoj grani PR #14 (`db37af55`). Poređenje po zaglavljima padova (puna imena):

| Posao | `db37af55` | FRG001 `b5b9d5a8` | Novi padovi |
|---|---|---|---|
| Test Suite, Python 3.11 | 175 failed / 8544 passed | 175 failed / 8587 passed | **0** |
| Test Suite, Python 3.13 | 175 / 8544 | 175 / 8587 | **0** |
| Production Runtime: import + full suite (3.11) | 197 / 8007 | 197 / 8050 | **0** |
| Production Runtime: byte-compile | success | success | — |
| **Docker:** build produkcione slike + boot + OCR u slici (`srp+srp_latn+eng`) | success | success | — |
| Security Checks (gitleaks, sast, semgrep, pip-audit) | success | success | — |
| V2 NG (uklj. `e2e:solo-tok` u pregledaču) | success | success | — |

+43 prošla = tačno novi FRG001 testovi. Run ID-jevi: FRG001 38162298716 / 38162305618 / 38162318525 / 38162324523; baza 38162303052 / 38162309080 / 38162322036 / 38162327199.

## Bezbednost
Bez merge-a, deploy-a, migracija, Cron-a, produkcionih upisa, izmena JWT izuzetka i izmena produkcionih promenljivih. Postojeće PR grane nisu menjane (CI je samo pokrenut ručno na grani PR #14, radi poređenja).
