# Vindex AI — Trust Layer Beta Freeze (2026-07-19)

Zatvara seriju rada koja je počela sa `UX_CURRENT_STATE_REPORT.md` i
prošla kroz dva persona-simulaciona testa, `TRUST_LAYER_IMPLEMENTATION_
PLAN.md`, i tri runde implementacije. Ovaj dokument je founderova
konačna odluka o obimu za prvi pilot — ne tehnički izveštaj, nego
zapisan trenutak odluke, u istom duhu kao `VINDEX_AI_PILOT_SUCCESS_
FRAMEWORK_v1.0.md`.

---

## 1. Trust Layer status pred betu

| Modul | Status |
|---|---|
| Case Genome objašnjivost (ZAŠTO X%, Osnov labele za kontradikcije/dokazi) | ✅ spremno |
| Verification Layer (AI Provera narativ) | ✅ spremno |
| Evidence osnov (DOK-XX vidljiv kao izvor) | ✅ spremno |
| AI ograničenja (na čemu se analiza zasniva + šta nedostaje) | ✅ spremno |
| Sigurnost procene (Najslabija tačka) | ✅ spremno |
| Smart Intake confidence | ⚠ čeka objedinjavanje Intake arhitekture |

Svih pet "✅" stavki je live na `main`, komitovano i push-ovano
(`97446ba`, `329144f`, `1aa071c`). Poslednja stavka postoji, testirana
je, ali živi na `feature/new-predmet-chooser` grani — namerno ne
merge-ovana, videti Deo 2.

---

## 2. Strateški nalaz — ovo nije UX problem, nego arhitektonski dug

Tokom pokušaja da se Smart Intake confidence prikaz prenese na stari CRM
wizard, otkriveno je (kod-verifikovano, ne pretpostavka): stari wizard
(`intakeOtvori`, `routers/dokument.py` + `routers/intake.py`) i Smart
Intake (`smartIntakeOtvori`, `shared/intake_documents.py`,
`intake_jobs`/`extracted_entities` tabele) su **dve potpuno odvojene
generacije sistema**, ne jedan sistem sa dve UI varijante:

| | V1 — stari CRM wizard | V2 — Smart Intake |
|---|---|---|
| Ekstrakcija | GPT-4o-mini, sinhrono, bez joba | Job-based worker, asinhrono |
| Confidence | Ne postoji u šemi | `classification_confidence`, `entity_confidence`, po polju |
| Audit/review queue | Ne postoji | `intake_review_queue`, threshold-based |
| Trust Layer kompatibilnost | Nema šta da se prikaže — podatak ne postoji | Puna podrška |

**Ovo je dobra vest, ne loša.** Ne treba uložiti energiju da V1 "izgleda"
kao V2 (dodavanje lažnog/izvedenog confidence-a na stari wizard bi bilo
tačno ono što je ceo Trust Layer rad pokušao da izbegne — vidi Pravilo
5, "bolje bez izvora nego lažni izvor", isto važi za confidence).
Umesto toga, prava odluka je bihevioralna, ne tehnička: **da li V2
treba potpuno da zameni V1** — i ta odluka ne sme se doneti interno,
nego na osnovu pilot signala.

---

## 3. Founderova odluka za beta freeze (2026-07-19)

- ✅ `main` ostaje kakav jeste — ne merge-ovati `feature/new-predmet-chooser`
  samo zbog confidence-a.
- ✅ Ne dodavati backend confidence u stari wizard (izbegnuta lažna
  preciznost).
- ✅ Genome Trust Layer je dovoljan za prvi pilot.
- ✅ Pozvati 3-5 advokata, posmatrati prvi kontakt sa sistemom (Silent
  Test, `feedback_post_p0_mindset_shift`).
- 📌 Otvorena stratešku stavku (Deo 5) umesto tehničkog rešenja.

**Nema više koda pre bete.** Ovo je eksplicitan freeze — sledeći kod
koji se piše za Vindex AI dolazi POSLE pilot feedback-a, ne pre.

---

## 4. Beta ulazni scenario (za founder-a, ne ceo proizvod)

Za prvi pilot ne prodaje se ceo Vindex AI — prodaje se jedna konkretna
stvar:

> "Pogledajte kako AI analizira predmet i pronađite gde greši."

Predložen tok za svakog od 3-5 advokata (admin/founder prisutan, ne
advokat sam — ovo je vođena demonstracija + posmatranje, ne samostalan
Silent Test u punom smislu, ali služi istoj svrsi u manjem obimu):

1. Zajedno se otvara prvi predmet (stvaran ili anonimizovan realan
   slučaj advokata, ne sintetički primer).
2. Dokument se otpremi.
3. AI obrada (advokat posmatra da li zna da nešto radi u pozadini).
4. Case Genome se prikaže.
5. Advokat ocenjuje, naglas ili napismeno:
   - Da li razume rezultat?
   - Da li mu veruje?
   - Gde sumnja?

Ovo su tačno tri pitanja koja Trust Layer v1 pokušava da omogući
pošten odgovor na — ne "da li je AI dobar", nego "da li advokat zna
KADA da mu veruje".

---

## 5. Backlog — otvoreno, ne odlučeno

### Unified Intake Trust Layer

> Nakon beta validacije odlučiti da li stari CRM wizard ostaje ili se
> migrira na Smart Intake pipeline.

Status: čeka pilot signal. Ne raditi pre toga — ovo je tačno Rule A/
Evidence Matrix primenjeno na arhitektonsku odluku, ne samo na
funkcije.

### Strateška stavka (post-pilot, veći rez)

> Smart Intake kao jedinstveni entry point Vindex AI sistema.

Dugoročni cilj artikulisan od foundera: jedan Intake Engine (dokument
ili podaci → predmet → Case Operating System), ne "stari wizard + Smart
Intake + treći način" koji bi ugrozio konzistentnost. Ovo NIJE odluka
doneta danas — ovo je zapisan pravac koji čeka da 3-5 advokata iz pilota
pokažu da li V2 treba da postane jedini ulaz. Vezano za
`NOVI_PREDMET_CHOOSER_ANALYSIS.md` otvorena pitanja (onboarding
usklađivanje, "zapamti izbor" mehanizam) — ta pitanja postaju relevantna
tek ako se ova stavka aktivira.

---

## 6. Zaključak

Pre nekoliko nedelja: "Imamo puno funkcija, ali ne znamo da li korisnik
veruje sistemu." Sada: "Imamo trust arhitekturu, ali jedan stari ulaz je
zaobilazi." Ovo je zdraviji problem — jasno omeđen, dokumentovan, i
zavisi od stvarnog signala, ne od još jedne interne iteracije.

Sledeći potez nije kod. Sledeći potez je poziv 3-5 advokata i pošten
odgovor na jedno pitanje: **"Ovo mi štedi vreme i mogu da mu verujem"**
— da ili ne, od ljudi koji nikad nisu videli kod.

Veza: [[project_ux_audit_2026-07-19]], [[project_pilot_success_framework]],
[[feedback_post_p0_mindset_shift]], `NOVI_PREDMET_CHOOSER_ANALYSIS.md`,
`TRUST_LAYER_IMPLEMENTATION_PLAN.md`
