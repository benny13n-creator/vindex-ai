# VCR002 — knjiga zadataka

Grana `program/vcr002-beta-operational-closure`, osnova `main` = produkcija `b36235a3` (PR #19).
Dokazi VCR001 se ne ponavljaju; referenca: `VCR001_TASK_LEDGER.md`, `VCR001_R1_GATE.md`, `VCR001_R2_GATE.md`.
Nivoi dokaza: LOCAL · ISOLATED · BROWSER_INTEGRATION · LIVE · REAL_USER_ACCEPTED.

---

## T00 — Stvarnost izdanja i osnovica posle spajanja — `PASS_LIVE`

- **Početni SHA:** `b36235a3`.
- **Problem:** posle spajanja PR #19 nije bilo utvrđeno šta tačno radi u produkciji ni koji testovi padaju.
- **Šta je provereno:**
  - `origin/main` = `b36235a3` (Merge PR #19). Izveštaj OPERATION LIVE nije spojen, kao što je i bilo namereno.
  - Produkcija: `GET https://vindex.rs/health` → `"commit":"b36235a"`, `redis:true`, `workers:1`.
  - `/app` → 200, asseti `/v2/app/@b36235a/…`.
  - VCR001 moduli se serviraju (200): `agenti-predmeta.js`, `nacrt-predmeta.js`, `zadaci-predmeta.js`, `zastarelost-kalkulator.js`, `dokaz-unos.js`.
  - `/app-legacy` → 200.
- **Minimalni ugovor ruta (bez prijave):**

  | Ruta | Odgovor |
  |---|---|
  | `GET /api/predmeti` | 401 |
  | `GET /api/workspace` | 401 („Prijava je obavezna…“) |
  | `GET /api/staging/x` | 401 |
  | `POST /email-notif/send-reminders` bez ključa | 403 „Restricted to founder or valid cron key.“ |
  | `POST /api/cron/autonomy` bez ključa | 401 |

- **CI na `b36235a3`, poređenje identiteta palih testova sa `6ad0b13a`:**

  | Workflow | Rezultat | Padovi | Novo | Nestalo |
  |---|---|---|---|---|
  | Security Checks (run 38213977242) | success | — | — | — |
  | Test Suite 3.11 / 3.13 (run 38213977142) | failure | 174 / 174, prethodno 175 / 175 | **0** | `test_ca_trust_boundary.py::test_M19_dokaz_prezivljava_granu_sa_predmetom` (ispravljen u VCR001 T04) |
  | Production Runtime Parity (run 38213977151) | failure | pun paket 196 (8162 passed) | **0** | M19 |

  - Production Runtime Parity: byte-compile i Docker build/boot su zeleni.
  - Prividna razlika „test_wave7_failure_matri…“ je skraćena linija u logu. Parametrizovani skup je identičan sa obe strane.
- **Bezbednosni izuzeci:** JWT CVE-2026-85394 je prihvaćen do 2027-01-09 (JRC001, CI kontrola roka) i nije proširen.
- **Kritični putevi koji ostaju nedokazani:**
  - prijavljeni tok u produkciji (T01);
  - OCR na produkcionom serveru (T02);
  - podsetnici (T04);
  - autonomija (migracija 136 nije primenjena; T09).
- **Izmenjeni fajlovi:** samo dokumentacija.
- **Status:** `PASS_LIVE` (javni ugovor i identitet izdanja). Prijavljeni deo pripada T01.

## T01 — Prijavljena produkciona QA sesija — `BLOCKED_AUTHENTICATION`

- **Šta je provereno:**
  - U ovom izvršnom okruženju nema QA kredencijala: ni promenljive okruženja, ni lokalnog `.env` ključa, ni sačuvanog pregledača.
  - TinyFish profil nije dostupan ovoj sesiji, a poslednji put je zatečen odjavljen.
- **Šta namerno NIJE urađeno** (direktiva):
  - nova registracija;
  - pravljenje naloga preko Supabase SQL-a;
  - preuzimanje tuđe sesije;
  - izmišljanje lozinke.
- **Za otključavanje:** osnivač dostavlja kanal za QA nalog: e-pošta + lozinka u lokalnoj promenljivoj okruženja (npr. `VX_QA_EMAIL` / `VX_QA_PASSWORD`, nikad u repo-u) ili prijavljen profil pregledača. Posle toga se izvršavaju koraci 1–7 iz direktive.
- **Status:** `BLOCKED_AUTHENTICATION`. Nezavisni zadaci se nastavljaju.

## T02 — OCR i Smart Intake na kontrolisanom korpusu — `PASS_ISOLATED` (živo: `BLOCKED_AUTHENTICATION`)

- **Problem:** OCR na stvarnom produkcionom putu otpremanja nikad nije nezavisno dokazan.
- **Izvor istine (nepromenjen):**
  - `routers/smart_intake.py` (otpremanje, pregled, prikačivanje);
  - `shared/intake_worker.py`;
  - `uploaded_doc/extractor.py` (Tesseract po strani, VCR001 T01);
  - migracije 073 / 092 / 095.
- **Postojeći dokazi (ne ponavljaju se):** NS005 Gate B matrica A/B/B2/C/D/E/F i NS005 T14:
  - skeniran PDF → pregled;
  - izolacija A/B;
  - dedupe;
  - odbijen pregled;
  - nečitljiv sken;
  - nepodržan format;
  - idempotentno prikačivanje;
  - ćirilica kroz worker.
- **Dodato:** `tests/test_vcr002_t02_ocr_korpus.py` (11 testova). Svi su sintetički, a imena i brojevi su izmišljeni:

  | # | Slučaj | Ugovor |
  |---|---|---|
  | A | digitalni PDF (latinica) | tačni redovi u `tekst_sadrzaj`, `ocr_koriscen=false` |
  | D | DOCX | poznat pasus doslovno u tekstu dokumenta predmeta |
  | C | mešovit PDF (digitalna latinica + rasterizovan ćirilični sken) kroz **stvaran worker** do prikačenog dokumenta | `ocr_koriscen=true`; digitalni red doslovno; ćirilica ≥ 75 % reči sa srpskim paketom (OCR tolerancija); bez paketa skenirana strana nije tiho izostavljena; ponovno čitanje ne pravi novo stanje |
  | — | isto ime, različit sadržaj | dva posla i dva dokumenta |
  | — | > 25 MB | odbijeno, bez posla i bez skladišta |
  | — | oštećen PDF | nikad `completed`, bez entiteta i bez dokumenta |
  | — | prolazna greška baze **posle ekstrakcije** | posao je vraćen u red (`attempts=1`); posle ponovnog pokušaja tačno jedan `intake_documents`; entiteti nisu udvostručeni |
  | — | greška baze **pri prikačivanju** | nije uspeh (5xx bez sirove greške baze); do isteka zauzeća iskren 409 i nijedan dokument; posle isteka tačno jedan dokument |
  | — | ponovljeno prikačivanje bez ključa | jedan dokument, jedan vektorski upis |
  | — | prikačivanje u tuđ predmet | 403/404, bez traga |
  | — | mreža | nijedan spoljni pokušaj |

- **Rezultati:**
  - Lokalno (bez Tesseract-a): `10 passed, 11 skipped` (zajedno sa NS005 T14). Preskočen je samo test C, jer traži stvaran OCR.
  - Test je dodat u oba CI OCR koraka `production-runtime.yml`:
    - runner sa `tesseract-ocr`;
    - **produkciona Docker slika** sa `VINDEX_REQUIRE_OCR=1 VINDEX_EXPECT_SRP=1`, gde je nedostatak OCR-a pad.
- **Negativna kontrola (mutacije, binarni režim):**
  - M1 (limit ×4): UHVAĆENA.
  - M2 (pad workera obeležen kao završen): UHVAĆENA.
  - M3 (zauzeće bez prozora zastarelosti): neodlučna, jer lažni RPC tumači `0` kao podrazumevanih 120 s. Nije prijavljena kao dokaz.
- **Uočeno ograničenje `LIM-T02-1`:**
  - Šta se dešava: posle neočekivane greške baze tokom prikačivanja, zauzeće (`finalizing_at`, migracija 092) se ne oslobađa. Ponovni pokušaj zato oko 120 s dobija 409 „Finalizacija je već u toku… za par sekundi“.
  - Integritet je očuvan: nema lažnog uspeha i nema duplikata, a test to dokazuje.
  - Problem je poruka: „par sekundi“ ne odgovara stvarnih ~2 minuta.
  - Zašto nije menjano: ispravka traži zahvat u funkciju od oko 1.300 linija, izvan ovog zadatka. Predlog je poseban mali zadatak (CAS oslobađanje zauzeća u `except` grani).
- **Živo:** zavisi od T01 (`BLOCKED_AUTHENTICATION`). Postupak za živu proveru je u `VCR002_RELEASE_HANDOFF.md` §8.
- **Status:** `PASS_ISOLATED`. LIVE: `BLOCKED_AUTHENTICATION`.

## T03 — Bojanov tok sa više dokumenata — `PASS_ISOLATED` + jedna ispravka integriteta (živo: `BLOCKED_AUTHENTICATION`)

- **Početni SHA:** `514d0f24`.
- **Scenario** (izmišljen): Zlatibor Fiktivić protiv Primer Gradnja DOO, P 4711/2026, tri dokumenta:
  - Tužba: rešenje uručeno 17.03.2025;
  - Dostavnica: uručeno 25.03.2025 — namerna protivrečnost;
  - Zapisnik: rok za izjašnjenje za 14 dana.

  Nedostaje ugovor o radu.
- **Šta prolazi stvarnim putem** (`tests/test_vcr002_t03_visedokumentni_predmet.py`):
  - Smart Intake rute;
  - intake worker i pypdf;
  - kanonski pisac tvrdnji;
  - Case Evolution dispečer;
  - osvežavanje Genome-a (zamenjen je samo model; on vraća SAMO oznake `DOK-NN` i `CLAIM-NNN` iz stvarnog prompta, a server ih razrešava);
  - sinhronizacija rokova;
  - Case Actions;
  - lanac odluka o roku;
  - pravno pitanje i istorija;
  - brisanje dokumenta.
- **Ispravka `FIX-T03-1`** (problem → reprodukcija → ispravka):
  - **Problem:** obrisan dokument je ostajao merodavan. `predmet_dokazi.dokument_id` je `ON DELETE SET NULL` (016), pa su AI tvrdnje obrisanog dokumenta ostajale aktivne bez izvora. Nastavljale su da ulaze:
    - u Genome (`EVIDENCE VAULT … CLAIM-001: Rok za izjasnjenje…`);
    - u kontekst pravnog pitanja kao „Utvrđene činjenice“;
    - u Analizu.
  - **Ispravka** (`api.py::predmet_dokument_obrisi`):
    - pre atomskog brisanja se pročitaju tvrdnje tog dokumenta koje je napisao sistem: `izvor_tvrdnje='ai_klasifikacija'`, ili zastarele tvrdnje pronađene u tekstu (`nacin_pronalaska` egzaktan/normalizovan);
    - posle potvrđenog brisanja te tvrdnje dobijaju `deleted_at` (meko brisanje, isti mehanizam kao `delete_dokaz`);
    - **advokatove tvrdnje (`covek`) se ne diraju**;
    - broj povučenih tvrdnji ide u odgovor i u nepromenljivi audit (`tvrdnje_povucene`).
  - **Bez migracije.**
  - **Ostatak rizika:** pad procesa između brisanja reda i povlačenja ostavlja tvrdnje kao ranije. To nije gore od zatečenog stanja, a greška se beleži u logu kao `error`.
- **Rezultati:**
  - `7 passed`.
  - Mutacije M1 (bez povlačenja), M2 (povlači i advokatove) i M3 (čitanje posle gubitka veze): **sve 3 UHVAĆENE**.
  - Regresija: postojeći testovi brisanja (NS001 FAZA 2, Wave 2 2D) 35/35. Šira grupa (brisanje, dokazi, evidence, OSB002/003, VCR001, NS006, FRG001, Wave 2): **484 passed, 1 skipped**.

| Zahtev | Dokaz | Status |
|---|---|---|
| **B6** više dokumenata u jednom predmetu | 3 dokumenta, 3 stabilna identiteta, jedan predmet; svaka tvrdnja nosi svoj `dokument_id`; nema „preskakanja“ | `PASS_ISOLATED` |
| **B8** hronologija sa izvorom | `genome-v2` hronologija: oba datuma uručenja → tačan `dokument_id` | `PASS_ISOLATED` |
| **B9** rok potvrđuje advokat | rok iz Zapisnika: `AI_AUTONOMOUS`, `dokument_id` = Zapisnik, akcija „čeka vašu potvrdu“; posle ponovnog osvežavanja i dalje 1 rok i 1 akcija; potvrda je trajna i zatvara akciju; B ne može da odluči o tuđem roku | `PASS_ISOLATED` |
| **B11** akcije iz nalaza u dokumentu | `PLANIRATI_ROKOVE` sa `hronologija_id` + `dokument_id` | `PASS_ISOLATED` |
| **B12** Genome sa identitetom izvora | protivrečnost razrešena u dva STVARNA reda tvrdnji iz dva različita dokumenta; `CLAIM-NNN` nije sačuvan kao identitet; poslednje osvežavanje vidi sve dokumente; posle brisanja ne vidi obrisan | `PASS_ISOLATED` |
| pravno pitanje u predmetu | kontekst nosi tvrdnje sva tri dokumenta, u granici poverenja; B ne dobija kontekst; istorija upisana jednom, vlasniku | `PASS_ISOLATED` |
| **B13** sintetički | ceo lanac iznad | `PASS_ISOLATED` |
| **B13** stvaran pilot | nema pilot predmeta ni prijavljene sesije | `BLOCKED_AUTHORITY` (pilot) / `BLOCKED_AUTHENTICATION` |

- **Zapažanje `OBS-T03-1`** (nije menjano):
  - Kontekst pravnog pitanja prikazuje obe protivrečne AI tvrdnje kao „Utvrđene činjenice … snaga=jaka“, bez oznake protivrečnosti.
  - Advokat to ne vidi, jer je reč o promptu modela. Ipak, „utvrđene“ je preširoka reč za AI izvod.
  - Promena teksta prompta je promena ponašanja proizvoda, pa je predložena kao posebna odluka, ne tiha izmena.
- **Zapažanje `OBS-T03-2`:**
  - Rok iz obrisanog dokumenta ostaje u hronologiji bez izvora (126: „čuva istorijski događaj“, namerno).
  - Ostaje **NEPOTVRĐEN**, pa nikad ne postaje operativna obaveza. Test to proverava.

## T04 — B10: postojeći podsetnici za rokove — `PASS_IMPLEMENTED` (kod) / `BLOCKED_AUTHORITY` (tajna i isporuka)

- **Početni SHA:** `4a51a2c8`.
- **Nema drugog planera.** Ostaju postojeći `email-cron.yml` → `POST /email-notif/send-reminders` → `routers/email_notif.py::posalji_podsetnike`.

### Faza A — dijagnoza (bez otkrivanja tajni)

- `email-cron.yml`: `state=active`, raspored `0 8 * * *`.
  - Stvarna pokretanja kasne oko 6 h (GitHub raspored).
  - Poslednjih 6 dana: **6/6 failure**, run 38147295244 (2026-10-11): `HTTP 403 {"detail":"Restricted to founder or valid cron key."}`.
- Zaglavlje je ispravno od Wave 4: `X-Cron-Key: ***`. Maskirana vrednost znači da je tajna **neprazna**.
- GitHub tajna `CRON_TOKEN` postoji (izmenjena 2026-06-20).
- Server (`_require_cron_or_founder`) prihvata samo `X-Cron-Key == CRON_SECRET` (Render) ili osnivačev JWT.
- **Zaključak:** na Render-u `CRON_SECRET` nije postavljen ili se razlikuje od `CRON_TOKEN`. Ova sesija ne vidi nijednu od te dve vrednosti, pa se dalje ne može razlikovati. Nijedna tajna nije čitana niti menjana.
- **Nov nalaz — `FIX-T04-3`** (SMS posao lažno prijavljuje uspeh):
  - `sms-cron.yml` prijavljuje **success** svaki dan (6/6), a server odgovara `401 „Vaša sesija je istekla“` (run 38144992944).
  - Uzrok: `/sms/send-reminders` prima samo osnivačev JWT, a goli `curl` nema proveru statusa.
  - Ispravka: posao sada pada na odgovor koji nije 2xx (isti obrazac kao email posao).
  - SMS ruta **nije** proširena na cron ključ, jer bi to uključilo slanje SMS-a stvarnim korisnicima; to je odluka osnivača.
  - Napomena: planirani poslovi se izvršavaju sa `main`-a, pa ispravka deluje tek posle spajanja.

### Faza B — pravna bezbednost rokova (kapija postoji: `shared/rokovi.sme_pokrenuti_obavezu` + `shared/rok_potvrda`, lanac `audit_immutable`)

Dokazano kroz **stvarnu kapiju** (bez zamene `_potvrdjeni_ids`):

| Rok | Šalje se? |
|---|---|
| nepotvrđen AI rok | ne |
| odbijen | ne |
| potvrđen pa odbijen (poslednja odluka pobeđuje) | ne |
| potvrđen | da |
| pad čitanja lanca odluka | ništa se ne šalje (fail-closed) |

- Već pokriveno ranije (B10/FAZA 6.x, nepromenjeno): isključena preferenca, neaktivan profil, arhiviran predmet, pad rezervacije.
- **`FIX-T04-2`:** predmet **u brisanju** (`brisanje_zapoceto`, BETA-DEL-001) je slao podsetnik. Sada je isključen, isto kao `api.py::_je_u_brisanju`. Ako kolona ne postoji, upit pada na stari oblik.
- **Primalac:** isključivo vlasnik profila (`profiles.email` po `user_id`).
- **Odjava:** svaki email nosi „Odjavi se“ (`make_unsub_url`).
- **Vremenska zona:** `date.today()` na Render-u (UTC). Rokovi su datumi, a pokretanje je oko 08:00–15:00 UTC, isti datum kao u Beogradu.

### Faza C — idempotencija

- **`FIX-T04-1`** (podsetnik se gubio):
  - **Problem:** dva potvrđena roka istog dana u istom predmetu pravila su dva identična reda rezervacije u jednom INSERT-u. UNIQUE(user, predmet, datum, dan) iz 021 obara ceo iskaz (23505). Kod je to čitao kao „već rezervisano drugim procesom“, pa podsetnik **nikad nije poslat**, a izveštaj je tvrdio `preskoceno=1`.
  - Postojeći test to nije video, jer njegova lažna baza nije proveravala jedinstvenost unutar jednog upisa.
  - **Ispravka:** jedna rezervacija po predmetu. Email i dalje navodi sve rokove.
- Ponovljen cron posle toga ne šalje ponovo (dokazano).
- **Ugovor ostaje:** najviše jedan pokušaj slanja (at-most-once), ne tačno jedna isporuka. Pad SMTP-a posle rezervacije je `neisporuceno` i traži ručnu proveru (B10, nepromenjeno).

### Faza D — stvarna isporuka: `BLOCKED_AUTHORITY`

- Nema ovlašćenja za tajne, nema odobrenog test primaoca i nema prijavljene QA sesije.
- Uputstvo za osnivača: `VCR002_RELEASE_HANDOFF.md` §6.

### Rezultati

- `tests/test_vcr002_t04_podsetnici.py`: 10 testova.
- Mutacije M1 (rezervacija po roku), M2 (bez provere predmeta u brisanju), M3 (kapija propušta sve): **sve 3 UHVAĆENE**.
- Regresija podsetnika (B10, Wave 4 auth, LZ001, Living System, nedeljni pregled, svi FAZA 6.x): **368 passed**.

## T05 — Paralelni savetnici: bezbednost — `PASS_IMPLEMENTED` (ISOLATED)

- **Početni SHA:** `ed6e1431`.
- **Problem:** `POST /api/agents/run-parallel` je bio slabiji od `/run` (VCR001 T06):

  | # | Razlika |
  |---|---|
  | P1 | nijedan rezultat nije imao proveru citata |
  | P2 | tuđ ili nepostojeći predmet je tiho postajao „opšti“ kontekst, bez oznake |
  | P3 | poseban, siromašniji kontekst: bez dokumenata, bez Genome-a, a opis bez granice poverenja |
  | P4 | sirov tekst greške provajdera (`str(exc)[:80]`) išao je klijentu |
  | P5 | budžet se nije proveravao pre plaćenih poziva modela; nedovoljno kredita je značilo n plaćenih poziva pa 402 i bačene odgovore |
  | P6 | isti savetnik izabran 3 puta se plaćao 3 puta |
  | P7 | objekat u listi `agenti` je davao 500; zadatak nije imao granicu |
  | P8 | prazan odgovor modela se plaćao kao uspeh |

- **Ispravke** (`routers/multi_agent.py`):
  - **Jedan izvor konteksta:** `_kontekst_predmeta(supa, uid, predmet_id)` je mehanički izvučen iz `/run` i koriste ga oba puta. Proverava vlasništvo, uključuje dokumente (T3 granica) i Genome sažetak.
  - **Opis predmeta je sada podatak, ne naredba:** pakuje se u granicu `BELESKA_PREDMETA` (i za `/run`).
  - **Pretraga i provera citata:**
    - pretraga se radi po zadatku (kao `/run`), a ti izvori su osnov kanonskog čuvara citata za **svaki** rezultat;
    - rezultat nosi `stanje` USPEH/NEUSPEH;
    - greška je generička: „Savetnik trenutno nije dostupan. Ništa nije naplaćeno za ovog savetnika.“
  - **Odgovor:** `kontekst_predmeta` (None/True/False), `uspesnih`, `neuspesnih`, `naplaceno_savetnika`.
  - **Naplata i ulaz:**
    - duplikati savetnika se uklanjaju, uz očuvan redosled;
    - provera budžeta (`krediti × n`) radi se PRE poziva modela (402);
    - naplata ostaje po isporučenom odgovoru (SOA2-001), a prazan odgovor je NEUSPEH;
    - `ParalelnaReq`: `task` 1–8000 znakova, `agenti: list[str]` (najviše 12) → 422.
- **Nalaz u VCR001 kodu — `FIX-T05-1`** (ispravljeno, važi i za `/run`):
  - **Problem:** `_proveri_citate_agenta` je `EXEMPT_FRAMEWORK` (npr. čl. 154 ZOO, izuzet od čuvara halucinacija) brojao kao proveren. V2 je advokatu pisao „Svi citirani članovi potvrđeni su u izvorima iz pravne baze“ i kad baza nije vratila **nijedan** izvor.
  - **Ispravka:** izuzet član je potvrđen samo ako ga dostavljeni izvor tog zakona sadrži. U suprotnom je neproveren, uz razlog „opšte poznat član — nije potvrđen u dostavljenom izvoru“.
- **Adversarijalni skup** (`tests/test_vcr002_t05_paralelni_savetnici.py`, 22 testa):
  - Vlasništvo: tuđ predmet, nepostojeći predmet, istovremeni zahtevi A i B.
  - Ubačena uputstva: napad iz dokumenta i iz opisa ostaje unutar granice.
  - Citati:
    - nepostojeći član → NEPROVERENI;
    - bez rezultata pretrage i pri padu pretrage nema PROVERENI;
    - dokument predmeta nije izvor za zakon;
    - regresija za izuzet član na `/run`.
  - Delimičan neuspeh: 1 od 3 pada (2 naplaćena, bez sirove greške); svi padaju (0 naplaćeno); prazan odgovor.
  - Budžet i ulaz: nedovoljno kredita (402 pre ijednog poziva); dupli savetnik; 5 pogrešnih ulaza → 422 bez poziva; nepoznati savetnici.
  - Mreža: nijedan spoljni pokušaj.
- **Rezultati:**
  - 22/22.
  - Postojeći testovi savetnika (VCR001 T06, `test_multi_agent`, CELINA 3): 33/33.
  - **Mutacije M1–M8 (vlasništvo, provera citata, izuzet = proveren, sirova greška, duplikati, budžet, naplata po pokušaju, opis bez granice): 8/8 UHVAĆENE.**
- **Nije u ovom zadatku:** V2 dugme za paralelni rad (T07).

## T06 — Integritet niza savetnika (pipeline) — `PASS_IMPLEMENTED` (ISOLATED)

- **Početni SHA:** `86fa7e5e`.
- **Tok** (provereno čitanjem i testom): zadatak → korak 1 (`run_agent`: kontekst predmeta, pretraga, čuvar citata, naplata) → izlaz → korak 2 … → odgovor.
- **Problemi:**

  | # | Problem |
  |---|---|
  | Q1 | izlaz prethodnog savetnika je ulazio u sledeći korak kao golo „PRETHODNI KORAK“, pa je uputstvo koje je model upisao u izlaz moglo da upravlja sledećim |
  | Q2 | rezultat niza **nije nosio proveru citata** ni po koraku, ni za završni odgovor |
  | Q3 | jedina zaštita od ponavljanja bio je keš procesa (15 min); ne važi preko radnika ni restarta |
  | Q4 | sirova greška (`str(exc)[:120]`) išla je klijentu |
  | Q5 | budžet za ceo niz se nije proveravao, pa je korak 3 mogao da padne na 402 posle dva plaćena koraka |
  | Q6 | ulaz bez tipa i granica |

- **Ispravke:**
  - **`_zadatak_koraka`:** izlaz prethodnog koraka ulazi samo u granici poverenja. Nova oznaka u `security/prompt_guard.py`: `IZVOR_AI_KORAK = "IZLAZ_PRETHODNOG_SAVETNIKA"`, uz napomenu da to nije proverena činjenica i da njegovi citati nisu potvrđeni.
  - **Citati:**
    - svaki korak nosi svoju `provera_citata`, `stanje` i `naplacen`;
    - `provera_citata_zavrsnog` je isključivo provera poslednjeg isporučenog odgovora, nikad nasleđena iz ranijeg koraka;
    - `potreban_pregled_advokata: true`; `kontekst_predmeta`; `naplaceno_koraka`.
  - **Trajna idempotencija:** dodata ruta `POST /api/agents/(run|run-parallel|pipeline)` u `shared/idempotency.py::ZASTICENE_RUTE`. To je postojeći okvir migracije 134 (`v2_mutation_idempotency`, primenjena u produkciji). **Bez nove tabele i bez migracije.** V2 već šalje `Idempotency-Key` za svaku radnju.
  - **Greške, budžet, ulaz:**
    - greška je generička (`_GRESKA_KORAKA`);
    - provera budžeta (`krediti × broj koraka`) radi se pre prvog poziva;
    - `PipelineReq`: `opis` 1–8000, `pipeline: list[str]` 1–12, `idempotency_key` ≤ 128.

### Deklarisana garancija idempotencije

| Slučaj | Ponašanje | Dokaz |
|---|---|---|
| ponovljen HTTP zahtev, isti ključ, isto telo | sačuvan odgovor (`idempotent-replayed: true`); model i naplata se NE ponavljaju, ni posle brisanja keša procesa | test |
| istovremen zahtev, isti ključ (prvi u toku) | 409 `IDEMPOTENCY_IN_PROGRESS`, ruta se ne izvršava | test |
| isti ključ, drugo telo | 409 `IDEMPOTENCY_CONFLICT` | test |
| više radnika / instanci | PRIMARNI KLJUČ (user_id, ključ) u bazi | migracija 134 + NS005 A2 testovi |
| timeout klijenta posle plaćenog koraka, ponovljen zahtev sa istim ključem | dok traje: 409; posle završetka: sačuvan odgovor, bez nove naplate | ugovor middleware-a (NS005 A2) |
| restart radnika usred niza | red ostaje IN_PROGRESS, pa isti ključ dobija 409 trajno (fail-closed). Nova radnja advokata (novi ključ) izvršava ponovo i **ponovo naplaćuje** već plaćene korake prekinutog izvršenja. Ovo je **deklarisano ograničenje** (`LIM-T06-1`), ne garancija | ugovor middleware-a |
| namerno ponovno pokretanje (nov ključ) | izvršava se i naplaćuje | test |
| ključ drugog korisnika | ne deli odgovor | test |
| pozivalac bez zaglavlja (V1) | kao pre: samo keš procesa, `iz_kesa` | nepromenjeno |

- **Rezultati:**
  - `tests/test_vcr002_t06_niz_savetnika.py`: 19/19 (tri koraka, nasleđivanje provere, prenesena halucinacija, tuđ predmet, pad 2. koraka, pad 1. koraka, neočekivan izuzetak, budžet, 5 pogrešnih ulaza, 5 idempotencija, mreža).
  - Regresija (idempotencija NS005 A2, savetnici VCR001/T05, `test_multi_agent`): 124 passed, 9 skipped (PostgreSQL).
  - **Mutacije M1–M6 (izlaz bez granice, završni nasleđuje prvi, ruta van zaštite, bez budžeta, sirova greška, neuspeh kao naplaćen): 6/6 UHVAĆENE** (M5 posle dodatog testa za neočekivan izuzetak).
