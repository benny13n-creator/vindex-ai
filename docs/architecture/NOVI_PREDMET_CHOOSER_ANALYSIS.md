# "Novi predmet chooser" — analiza pre merge-a (2026-07-19)

Founderov zahtev: ova funkcionalnost je tri puta blokirala čist commit
kao neplanirana, nekomitovana grana koda. Umesto da se dalje zaobilazi,
premeštena je na `feature/new-predmet-chooser` branch i ovde je analiza
koju je founder tražio PRE bilo kakvog merge-a u `main`. Ovo je analiza,
ne preporuka za ili protiv — odluka o merge-u ostaje founderova.

**Šta je fizički premešteno:** ceo "Novi predmet chooser" +
"Smart Intake — Iz dokumenta" modal (`novPredmetOtvori`, `_npChoiceCard`,
`npChooserClose/Manual/Smart`, `smartIntakeOtvori`, `_siRenderResult` i
prateće funkcije, `static/vindex.js`) — kod je postojao nekomitovan u
working tree-u od pre početka ove UX audit sesije, sa komentarom u
samom kodu datiranim "Founder direktiva (2026-06-16)". Ovom prilikom je
i dovršen (T1.1/T1.2, Trust Layer v1 — confidence prikaz u
`_siRenderResult`) jer je tekstualno neodvojiv od ostatka bloka.

---

## 1. Šta rešava?

Kad korisnik klikne "+ Novi predmet", umesto direktnog ulaska u stari
CRM wizard (`intakeOtvori`), prvo bira između dve opcije: "Iz dokumenta"
(upload-first, Smart Intake — AI ekstrakcija) i "Ručni unos" (postojeći
wizard). Rešava konkretan, već dokumentovan problem: stari CRM wizard
nema OCR/AI-ekstrakcioni pipeline uopšte (potvrđeno u
`VINDEX_AI_SYSTEM_STATUS_2026-07-19.md`: "CRM wizard (stariji put) nema
OCR pipeline uopšte"). Bez ovog chooser-a, Smart Intake AI-prvi put
postoji u kodu ali nije otkriv — korisnik mora znati da uopšte postoji
da bi ga pronašao.

## 2. Da li UX test potvrđuje potrebu?

**Ne direktno — i ovo treba jasno reći, ne zamagliti.** Ni
`SENIOR_LAWYER_SIMULATION_REPORT.md` ni
`SENIOR_PARTNER_BUYER_SIMULATION_REPORT.md` nisu testirali ovaj chooser
ekran, jer kod NIJE bio komitovan/deployovan kad su ta dva testa rađena
— oba su testirala postojeći (committed) tok, koji ide direktno u stari
wizard.

**Posredan dokaz postoji, direktan ne.** Oba testa su kritikovala
odsustvo brzog, AI-prvog puta za kreiranje predmeta (prva simulacija:
"Smart Intake Wizard 'gotov' a onda traži DODATNI eksplicitni 'finalize'
klik" — kritika POSTOJEĆEG Smart Intake toka, ne ovog chooser-a
specifično). Ovo znači: problem koji chooser pokušava da reši
(otkrivenost AI-prvog puta) je stvaran po ranijim nalazima — ali NE
postoji dokaz da je BAŠ OVO REŠENJE (dodatan izbor-ekran) najbolji način
da se taj problem reši, niti da je testirano na pravim korisnicima. Po
Evidence Matrix pravilu (`project_pilot_success_framework`), ovo je
trenutno ispod praga za potvrđenu potrebu — kandidat je za testiranje
kod prvih beta korisnika (Silent Test), ne za merge na osnovu unutrašnje
pretpostavke da je dobra ideja.

## 3. Da li menja onboarding?

**Da, i trenutno NEDOSLEDNO — konkretan nalaz, ne pretpostavka.**
Proverio sam direktno u kodu: `onboardingStep(2)` (vođeni onboarding
korak "Otvorite prvi predmet", `vindex.js:15260-15261`) i dalje poziva
`intakeOtvori()` DIREKTNO, zaobilazeći chooser potpuno. Ovo znači: nov
korisnik u onboardingu nikad ne vidi chooser (uvek ide pravo u stari
wizard), dok isti korisnik posle onboardinga, klikom na "+ Novi predmet"
na dashboard-u, ODJEDNOM vidi chooser koji ranije nije postojao u istom
toku. Ovo je nekonzistentnost koju treba rešiti PRE merge-a, ne posle —
ili uskladiti onboarding da i on koristi chooser, ili eksplicitno
odlučiti da onboarding namerno zadržava stari put (i ako da, zabeležiti
zašto, ne ostaviti kao previd).

## 4. Da li povećava ili smanjuje kognitivni teret?

**Povećava za jedan klik, za SVAKOG korisnika, bez izuzetka.** Proverio
sam — ne postoji mehanizam koji pamti prethodni izbor korisnika
(nijedan `localStorage` poziv vezan za chooser). Ovo znači: iskusan
korisnik koji je 50 puta izabrao "Ručni unos" i dalje mora da vidi i
klikne kroz chooser ekran 51. put. Za NOVE korisnike, chooser je
verovatno neto pozitivan (jasno objašnjava dve opcije pre nego što se
obavežu na jednu) — ali za POVRATNE korisnike je čist dodatni korak bez
vrednosti. Ovo je isti tip trade-off-a koji je UX audit već identifikovao
kod Smart Intake wizard-a samog (dvostruko potvrđivanje) — dodaje
korak za jasnoću početnicima po ceni trenja za redovne korisnike.

---

## Otvorena pitanja pre merge-a (ne odluke, pitanja za foundera)

1. Da li onboarding treba ažurirati da koristi isti chooser (uskladiti
   iskustvo), ili namerno zadržati stari wizard u onboardingu kao
   poznatiji prvi korak?
2. Da li dodati "zapamti moj izbor" (localStorage) da se izbegne
   ponovljeni klik za redovne korisnike?
3. Da li ovo ide u beta kao deo trenutne runde, ili čeka posle prvih
   Silent Test nalaza (po Evidence Matrix pravilu — problem koji rešava
   je dokumentovan, rešenje samo nije testirano)?

**Status:** kod postoji, funkcionalan, komitovan na ovaj feature branch
(ne na `main`). Merge čeka founderovu odluku po pitanjima iznad.
