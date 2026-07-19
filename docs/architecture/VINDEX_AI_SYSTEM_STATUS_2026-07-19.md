# Vindex AI — Analiza celokupnog sistema (2026-07-19)

Snimak stanja na ovaj datum, ne trajan zaključak — sledeći put kad se ovo
pita, treba ponovo verifikovati protiv živog koda/baze, ne citirati ovaj
dokument kao večitu istinu (ista disciplina kao svi ostali dokumenti u
`docs/architecture/`).

Odgovor na tri konkretna pitanja, redom.

---

## 1. Da li je platforma kompletno autonomna?

**Ne. I to namerno, po dizajnu, ne kao privremeno ograničenje.**

Ovo pitanje ima dve odvojene dimenzije koje se ne smeju mešati:

### Operativna automatizacija (koliko pipeline-a radi bez klika)

**Delimično, i sada merljivo poštenije nego ranije.** Kad dokument stigne u
predmet, sledeće se dešava BEZ ljudske intervencije: OCR/parsing → GPT-4o
ekstrakcija → Case Genome se računa (uključujući sada backend-računat
snaga_predmeta_procent, ne GPT-ovo samoprijavljeno) → Genome Verification
Layer proverava (dokazi_rang protiv stvarnih dokumenata, brojevi članova
zakona, interna konzistentnost) → GenomeUpdated event ide u durable outbox
→ audit_immutable red se upisuje (ko/kada/zašto/agent/pre-posle) → Evidence
Vault klasifikuje dokument i upisuje ključne činjenice (OVO je od danas
stvarno живо, posle ispravke migracija 016/074).

**Gde se lanac i dalje prekida, potvrđeno u Reality Validation izveštaju:**
Smart Intake ne kreira predmet automatski iz završenog posla — advokat
mora eksplicitno da klikne "finalize" (kod sam to priznaje u komentaru).
CRM wizard (stariji put) nema OCR pipeline uopšte. Nijedan modul osim
Case Genome-a ne reaguje automatski na promenu drugog modula — Strategy,
Firm DNA, Digital Twin i dalje se pozivaju posebno, ne kroz event bus.

### Odluka-autonomija (da li sistem donosi pravne odluke bez advokata)

**Eksplicitno i namerno NE, ovo je definisan identitet proizvoda, ne
tehnički nedostatak koji treba popraviti.** `VINDEX_AI_PRODUCT_PHILOSOPHY_
v1.0.md` Deo 4: "AI pomaže advokatu" znači izvlači/procenjuje/računa/
predlaže, advokat donosi konačnu odluku. `require_review` je STATUS na
sačuvanom Genome-u, nikad blokada snimanja — ovo je arhitektonska odluka
potvrđena u svakoj fazi razvoja Verification Layer-a, ne privremeno
ograničenje koje čeka da se ukine. Nijedna trenutna arhitektonska odluka
ne planira autonomnu akciju sa pravnom/finansijskom posledicom (podnošenje
podneska, prihvatanje poravnanja, zatvaranje predmeta) bez ljudskog
pregleda.

**Zaključak:** ako "kompletno autonomna" znači "radi sve samo bez ijednog
klika", odgovor je ne, i deo tog razmaka (Smart Intake finalize) je
namerno ostavljen tako dok se ne izmeri da li advokati uopšte to žele
(Faza 2.1 instrumentacija upravo to meri, rezultati još ne postoje). Ako
"kompletno autonomna" znači "donosi pravne odluke bez čoveka", odgovor je
ne, i to se neće promeniti bez fundamentalne promene filozofije proizvoda
koju niko nije predložio.

---

## 2. Koji je stadijum trenutno?

Sintetizovano kroz sve slojeve koji postoje (Bible → 90-Day Plan → Pilot
Framework → Product Philosophy):

| Sloj | Status |
|---|---|
| Arhitektura (Bible v1.0) | Track 1 stavke iz Deo X u velikoj meri završene: Event Bus → Genome wiring, Audit Trail, Verification Layer v1, Genome Strength Calibration, Legal Citation v2. Track 2 (Fact Graph, State Machine, rollback, cross-module wiring) i dalje čeka dokaz, namerno. |
| Pouzdanost (90-Day Plan) | Faza 1 (1.1–1.3) završena i verifikovana pre/posle na regresionom skupu. Faza 2 (2.1 instrumentacija + 2.2 tehnički dug) završena. Faza 3 (data ingestion reliability) NIJE započeta — korpus je i dalje dokumentovano nestabilan (Pinecone write-cap, većina izvora neuspešno ingestovano). |
| Evidence Vault | Danas prvi put stvarno radi u produkciji — migracije 016 i 074 su bile 100%/delimično neprimenjene otkad su napisane, oba SQL bug-a nađena i ispravljena tek danas, `klasifikuj_i_sacuvaj` sada otporniji na delimičan neuspeh. |
| Pilot (Pilot Success Framework) | **Nije počeo.** Framework, Evidence Matrix, Emergency Rule postoje kao pravila — nijedna od 3+5+10 kancelarija još nije uključena. Deo 2 Reality Validation (5-10 stvarnih anonimizovanih predmeta) čeka founder-ove dokumente, harness je gotov. |
| Identitet (Product Philosophy) | **Draft.** Najvažnije pitanje u dokumentu (Deo 4, "AI pomaže" vs "AI odlučuje" granica) je predlog, ne potvrđena odluka — čeka founder-ovu eksplicitnu potvrdu (Deo 8). |
| Bezbednost/Enterprise (Bible Deo VII) | Najzreliji deo sistema, iznenađujuće za veličinu projekta — security, GDPR, enkripcija, error tracking su realni, verifikovani u kodu. Slabe tačke: nema keširanja nigde, audit log je rascepkan po modulima (iako Genome sada IMA svoj audit trail preko event bus-a). |

**Kratko: sistem je prošao kroz Engineering → Architecture → Reliability →
Evaluation → Evidence fazu (memorija `project_strategic_direction`), i
sada je na samoj granici između "Evidence faze" i "Pilot faze" — pravila
za pilot su napisana, infrastruktura za merenje postoji, ali stvaran pilot
sa stvarnim advokatima još nije pokrenut.** To je sledeći, ne tehnički,
korak — i to je već zapisano u memoriji kao founder-ov sopstveni zadatak,
ne nešto što čeka na kod.

---

## 3. Ima li prostora za poboljšanje?

**Da, i lista je poštena — ne izmišljena da bi dokument delovao
kompletnije.** Podeljeno po Rule A/B/C iz Bible-a i Evidence Matrix-u iz
Pilot Framework-a:

### Poznato, dokumentovano, namerno odloženo (čeka dokaz, Rule A)

- **Tačnost pravnih citata** — Legal Citation v2 hvata očigledno nemoguće
  brojeve članova, ne potvrđuje da tačan broj stvarno postoji. Founder je
  eksplicitno rekao da ovo ostaje privremeno rešenje dok ne postoji
  pouzdan pravni korpus — nije greška, jeste otvoren rad.
- **Kompresija snaga_predmeta kategorije** — posle Genome Strength
  Calibration patch-a, procenat sada stvarno varira (35–80% na test
  skupu), ali kategorija (jaka/srednja/slaba) se i dalje grupiše oko
  "srednja" zbog umerenih iznosa faktora. Dokumentovano u Reliability
  Patch izveštaju kao poznato ograničenje, ne popravljeno.
- **Heatmap anchoring** — isti prompt-anchoring bug kao
  snaga_predmeta_procent (bukvalni brojčani primeri u system promptu),
  nađen slučajno tokom Reality Validation-a, NIJE popravljen jer nije bio
  u odobrenom obimu te zakrpe. Čeka svoju odluku.
- **Cross-file `_d`/`_safe` unifikacija** (matter_intel.py ↔ learning.py)
  — namerno izdvojeno iz Faze 2.2 jer nije striktno behavior-preserving.
- **`_INTEL_SYSTEM` mrtav kod** u matter_intel.py — leftover iz perioda
  kad je taj modul pozivao GPT, sada nekorišćen.

### Sledeći prirodan korak nije tehnički — poslovni je

- **Pravi pilot** (Pilot Success Framework Faza 1: 3 kancelarije, cilj je
  otkriti greške, ne prodaja) — nije pokrenut.
- **Deo 2 Reality Validation** (5-10 stvarnih anonimizovanih predmeta,
  isti harness kao sintetički batch) — čeka founder-ove dokumente.
- **LEC popunjavanje** (150-200 anotiranih dokumenata) — i dalje prazno,
  isto stanje kao 2026-07-15.
- **Product Philosophy Deo 8** — četiri konkretna pitanja čekaju
  founder-ovu potvrdu pre nego što dokument prestane da bude nacrt.

### Track 3, eksplicitno ne sada

- **Deterministic Intelligence Framework** — širiti "LLM predlaže, backend
  računa" obrazac (dokazan na snaga_predmeta_procent) na druge brojeve u
  sistemu (confidence, priority, urgency) — imenovano, namerno odloženo.

**Ono što NIJE na listi, namerno:** nova arhitektura, novi moduli, pravni
graf, autonomni agenti. Ne zato što nisu zanimljivi, nego zato što ništa
od toga trenutno ne prolazi Evidence Matrix (≥2 boda) niti The One
Sentence Test iz Product Philosophy Deo 7.
