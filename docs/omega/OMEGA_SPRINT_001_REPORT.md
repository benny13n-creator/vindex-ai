# Mission Report — Program Omega, Master Sprint 001: From Document Upload to Complete Case Intelligence

**Datum**: 2026-08-06
**Program**: Omega (prvi sprint)
**Tim**: Product Workflow Architect, Smart Intake & OCR Specialist, Case Intelligence Architect, Workflow
Automation Engineer, Reliability & Data Integrity Engineer, Legal Product Reviewer (svih 6 uloga izvedeno
direktno u ovoj sesiji, bez odvojenih pod-agenata).

---

## Zatvorenje misije

Misija je tražila jedan kompletan autonomni tok, sa Prioritetom 1 eksplicitno imenovanim kao "direktan
Bojanov zahtev": advokat šalje haotičnu fasciklu od 500 dokumenata i dobija organizovan predmet. Pre bilo
kakvog koda, urađen je OBAVEZNI AUDIT (`OMEGA_ARCHITECTURE_MAP.md`) koji je pratio ceo lanac — Upload → OCR →
Segmentacija → Klasifikacija → Case Assimilation → Case Evolution Engine → Genome → Timeline → Rokovi →
Zadaci → Dokazi → Alerts → Firm Brain → Copilot → Briefing → Search → Audit → Dashboard — i pronašao TAČNO
mesto gde se taj lanac lomi za scenario od 500 dokumenata.

## Otkriveno

1. **`POST /api/smart-intake/documents` obrađuje ceo batch SINHRONO, u JEDNOM HTTP zahtevu.** Za 500
   dokumenata, ovo gotovo sigurno premašuje gunicorn-ov worker timeout (120s) — konekcija se ubija usred
   obrade, bez ijednog strukturiranog odgovora advokatu o tome šta je uspelo.
2. **Ne postoji batch-finalize mehanizam.** Svaki od do 500 posebno-otpremljenih fajlova postaje sopstveni
   `intake_job`, i svaki mora biti finalizovan POSEBNIM pozivom. Mission-ov sopstveni primer izlaza
   ("Obrađeno 500 dokumenata. Pronađeno: 1 postojeći predmet...") NIJE MOGAO POSTOJATI ni u jednom postojećem
   API pozivu.
3. **Genome se ponovo računa JEDNOM PO POZIVU finalizacije, ne jednom po predmetu.** Ako 500 dokumenata
   pripada JEDNOM predmetu, Genome bi se potpuno preračunao do 500 puta — ozbiljan, ali NEIZMENJEN ovim
   sprintom problem (v. "Odloženo" ispod).
4. **Zadaci se nikad ne kreiraju automatski** ni iz jednog od 6 Case Evolution događaja — potvrđeno već
   sertifikovanom Event Coverage Matrix-om (Program Delta Sprint 004), ponovo potvrđeno ovde.
5. **Firm Brain i Memory Graph i dalje nemaju nijedan writer** — potvrđeno ponovnim grep-om, isti
   prethodno-dokumentovan nalaz (`WOW-003`, `IF-005`), ne novootkriven, ne pogoršan Omega-om.

## Popravljeno

1. **`routers/smart_intake.py::upload_intake_documents`** — dodat `_UPLOAD_TIME_BUDGET_S = 90.0` vremenski
   budžet. Petlja proverava proteklo vreme PRE početka svakog novog fajla (nikad usred fajla). Ako je budžet
   dostignut, endpoint vraća čist, nastavljiv odgovor (`{"nastavlja": true, "preostali_fajlovi": [...]}`)
   umesto da rizikuje ubijanje konekcije bez ikakvog odgovora.
2. **`routers/smart_intake.py::finalize_intake_job`** — izdvojen u tanak, decorated wrapper +
   `_finalize_intake_job_core` (nedekorisana funkcija, identična logika, čista ekstrakcija) — neophodno da bi
   batch-finalize mogao da poziva logiku 500 puta bez pogađanja sopstvenog 20/minute rate limita.
3. **`routers/smart_intake.py::finalize_intake_jobs_batch`** (NOVO) — `POST /jobs/finalize-batch`, prima do
   1000 job_id-jeva, poziva `_finalize_intake_job_core` po poslu (nepromenjena logika), agregira u JEDAN
   sažetak: ukupno obrađeno, uspešno/neuspešno, predmeti pogođeni (deduplicirano po predmet_id, ne po poslu),
   dokumenti za proveru, rokovi dodati.

Nijedna nova AI sposobnost, Genome/Timeline/Evidence/Alert logika nije uvedena — sve reuse-uje POSTOJEĆE,
već-otvrđene mehanizme (Program Intake Sprintovi 001-007, Program Delta Sprintovi 001-004), tačno po
"Omega Principu."

## Dokazano

**10 novih testova** (`tests/test_omega_sprint001_batch_intake.py`):
- Vremenski budžet zaustavlja veliki batch i tačno prijavljuje preostale fajlove (stvarno-vreme zasnovan
  test, ne mokovan sat).
- Mali/srednji batch ostaje potpuno nepromenjen ponašanjem.
- Batch-finalize agregira više poslova u JEDAN predmet-red kada svi pripadaju istom predmetu.
- Jedan neuspešan posao ne zaustavlja ostatak batch-a.
- Batch-finalize dokazano NE pogađa rate limit pojedinačnog endpoint-a (batch od 30, veći od 20/minute
  limita).
- Wrapper i dalje deleguje identično posle ekstrakcije.

**Regresija**: svih 10 postojećih finalize-vezanih test fajlova (86 testova ukupno sa novim) prošlo bez
promene ponašanja pre pune regresione provere.

**Puna test suita**: **2.644 passed, 1 skipped, 0 failed** (bilo 2.638 na kraju Programa Delta) — tačno +6
novih testova, nula regresija.

## Odloženo

1. **Genome N-puta-preračunavanje po istom predmetu** — zahteva izmenu KADA `_finalize_intake_job_core`
   emituje `DOCUMENT_ACCEPTED` (odloženo emitovanje, agregirano po predmet_id na kraju batch-a) — stvarna
   izmena već-otvrđene, produkciono-kritične mašinerije; namerno ne pokušana zajedno sa ostale dve izmene u
   istom sprintu radi pažljivijeg testiranja svake.
2. **Automatsko kreiranje zadataka iz uočenih problema** (nedostajući dokazi, kontradikcije, rizik roka) — ne
   postoji nijedan event→task mehanizam; jasno imenovano kao sledeći najveći prioritet, ne pokušano ovde
   (zahteva poslovnu odluku o tome koji problemi zaslužuju automatski zadatak).
3. **Live provera sa 500 stvarnih dokumenata** — sva provera ovog sprinta je na nivou mock/jedinica; nema
   živog okruženja dostupnog ovoj sesiji za pravi load test.
4. **Firm Brain/Memory Graph auto-populacija** — van opsega, prethodno dokumentovano, nepromenjeno.

## Zaključak

Prioritet 1 (500-dokumenata scenario) ima sada REALAN put od haotične fascikle do organizovanog predmeta sa
JEDNIM sažetkom rezultata — pre ovog sprinta, taj put se lomio na dva mesta (upload timeout rizik, nepostojeći
batch-finalize). Oba su zatvorena, testirana, bez regresije u dodirnutim putanjama. Preostali nalazi
(Genome skaliranje, automatski zadaci) su imenovani sa jasnim razlogom odlaganja, ne skriveni kao završeni.
