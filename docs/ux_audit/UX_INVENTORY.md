# UX INVENTAR — svi interaktivni elementi Vindex AI `/app`

> **Tip dokumenta:** forenzički inventar (audit). **Nijedan fajl aplikacije nije menjan.**
> **Izvori:** `index.html` (4.832 linije) i `static/vindex.js` (23.681 linija).
> **Datum:** 2026-08-12 · **Uloga:** UX Cartographer

## 1. Metod i granice

Inventar je napravljen mašinskim izvlačenjem svih HTML čvorova koji su:

- `<button>`, `<a>`, `<input>`, `<select>`, `<textarea>`,
- bilo koji element sa `onclick` / `onchange` / `oninput` / `onkeydown` / `onkeyup` / `onsubmit` / `ondblclick`,
- bilo koji element sa `role="button"` ili `contenteditable="true"`.

Obuhvaćen je i HTML koji `static/vindex.js` sastavlja u vreme izvršavanja (`innerHTML`, `html += '<button…'`) — takvi elementi su ravnopravni i nose oznaku funkcije koja ih crta.

**Šta ovaj inventar NE tvrdi:**

- Ne tvrdi da element radi ono što mu ime kaže — samo da rukovalac postoji i da je globalno dostupan.
- Ne pokriva elemente koje crtaju spoljne biblioteke (Chart.js platna, Lucide ikone).
- Ne pokriva `client_portal.html`, `privacy.html`, `terms.html`, `static/*.html` — to nije `/app`.
- Za elemente vezane preko `addEventListener` (delegirani rukovaoci) vidi §6.

## 2. Statistika

| Metrika | Vrednost |
|---|---|
| **Ukupno interaktivnih elemenata** | **1014** |
| — statički, iz `index.html` | 781 |
| — dinamički, iz `static/vindex.js` | 233 |
| Elemenata bez ijedne labele | 72 |
| Različitih imena rukovalaca (funkcija) u `onclick`-ovima | 445 |
| Rukovalaca koji NE postoje | 0 (v. §5) |

### 2.1 Raspodela po vrsti

| Vrsta | Broj |
|---|---|
| dugme | 512 |
| polje | 241 |
| dugme (div) | 143 |
| tab | 37 |
| dugme (span) | 28 |
| link | 26 |
| stavka menija | 20 |
| FAB | 4 |
| dugme (tr) | 2 |
| dugme (td) | 1 |

### 2.2 Raspodela po lokaciji

| Lokacija | Broj |
|---|---|
| tab AI radni prostor (`tab-aiws`) | 126 |
| tab Podešavanja (`tab-settings`) | 91 |
| kartica predmeta (dinamički) | 60 |
| kartica predmeta → pan Pregled | 53 |
| dashboard (dinamički) | 37 |
| razno / pomoćni paneli (dinamički) | 35 |
| modal `si-overlay` (Novi predmet iz dokumenta) | 34 |
| modal `intake-overlay` (Intake Wizard) | 26 |
| kartica predmeta → pan AI Analiza | 25 |
| modal `auth-modal` (prijava/registracija) | 23 |
| kartica predmeta → pan Strategija | 23 |
| modal `crm-overlay` (klijent) | 21 |
| administracija (dinamički) | 20 |
| naplata / fakture (dinamički) | 18 |
| bočna traka (glavna navigacija) | 17 |
| kartica predmeta → pan Naplata | 17 |
| tab Klijenti (`tab-k`) | 17 |
| kartica predmeta — zaglavlje, tajmer, podtabovi | 16 |
| modal Intake / Novi predmet iz dokumenta (dinamički) | 16 |
| mobilno — 'Više' bottom sheet | 15 |
| modal `ugovor-modal` (ugovor o zastupanju) | 14 |
| gornja traka | 14 |
| tab Sudska praksa (`tab-s`) | 14 |
| kartica Predmeti — lista/kanban | 13 |
| modal `rociste-overlay` (ročište) | 13 |
| Digitalna imovina / moduli (dinamički) | 13 |
| kartica predmeta → pan Rokovi | 12 |
| modal `tos-overlay` (uslovi korišćenja) | 12 |
| modal `settings-modal` (podaci kancelarije) | 11 |
| modal `feedback-modal` | 10 |
| tab Kancelarija (`tab-kanc`) | 10 |
| tab Kalendar/Rokovi (`tab-kal`) | 10 |
| overlay `cmdk-overlay` (komandna paleta) | 10 |
| modal `doctpl-overlay` (šabloni dokumenata) | 9 |
| tab Finansije (`tab-fin`) | 9 |
| kancelarija / poslovna inteligencija (dinamički) | 9 |
| overlay `wl-overlay` (lista čekanja) | 8 |
| plutajuće — `pred-fab` (brze akcije u predmetu) | 7 |
| sudska praksa / pretraga (dinamički) | 7 |
| modal `pred-new-modal` (brzi novi predmet) | 6 |
| kartica predmeta → pan Dokumenti | 6 |
| kartica predmeta → pan Komunikacija | 6 |
| kartica predmeta → pan Zadaci | 6 |
| modal `crm-conflict-overlay` (provera sukoba) | 6 |
| landing stranica | 6 |
| mobilno — donja navigacija | 6 |
| modal `vx-voice-modal-overlay` (Vindex Live) | 6 |
| overlay `vx2-qa-overlay` (Brze akcije) | 5 |
| kartica predmeta → pan Profitabilnost | 5 |
| modal `crm-csv-overlay` (CSV uvoz) | 5 |
| notifikacije (dinamički) | 5 |
| modal `progressive disclosure` (otključavanje) | 4 |
| modal `vx-dialog-overlay` (zamena za alert/confirm) | 4 |
| tab Klijenti (dinamički) | 4 |
| modal `pro-upgrade-modal` | 3 |
| kartica predmeta → pan Saradnja | 3 |
| modal `data-residency-overlay` | 3 |
| dinamički (vindex.js) — nesvrstano | 3 |
| komandna paleta (dinamički) | 3 |
| modal `paywall-modal` | 2 |
| modal `pro-modal` (cenovnik / planovi) | 2 |
| kartica predmeta → pan Graf znanja | 2 |
| tab Dokumenti (`tab-dok`) | 2 |
| modal `compare-modal` (poređenje verzija) | 2 |
| mobilno — panel notifikacija | 2 |
| modal `android-install-modal` | 2 |
| kalendar (dinamički) | 2 |
| plutajuće (FAB feedback) | 1 |
| kartica predmeta → pan Workflow | 1 |
| tab Zadaci (`tab-zadaci-g`) | 1 |
| tab Poslovna inteligencija (`tab-pi`) | 1 |
| plutajuće — FAB Vindex Live (glas) | 1 |
| modal `voice-modal` (STARI glasovni modal) | 1 |
| modal `ios-install-modal` | 1 |
| šabloni dokumenata (dinamički) | 1 |

## 3. Puni inventar

### modal `auth-modal` (prijava/registracija) — 23 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-001 | `button.modal-close` | &#x2715; | dugme | `onclick="closeModal()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-002 | `#auth-login-tab` | Prijava | tab | `onclick="setAuthMode('login')"` | izvršava `setAuthMode()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-003 | `#auth-reg-tab` | Registracija | tab | `onclick="setAuthMode('register')"` | izvršava `setAuthMode()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-004 | `#login-email` | placeholder: Email adresa | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Email adresa | vidljiv samo dok je taj modal/overlay otvoren |
| UI-005 | `#login-password` | placeholder: Lozinka | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Lozinka | vidljiv samo dok je taj modal/overlay otvoren |
| UI-006 | `button.pw-eye` | aria-label: Prikaži/sakrij lozinku | dugme | `onclick="togglePw('login-password',this)"` | prikazuje ili sakriva deo ekrana | vidljiv samo dok je taj modal/overlay otvoren |
| UI-007 | `a` (index.html:86) | Zaboravili ste lozinku? | link | `onclick="setAuthMode('forgot')"` | izvršava `setAuthMode()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-008 | `#login-btn` | Prijavite se | dugme | `onclick="doLogin()"` | prijava/registracija/nalog | vidljiv samo dok je taj modal/overlay otvoren |
| UI-009 | `#reg-name` | placeholder: Ime i prezime | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Ime i prezime | vidljiv samo dok je taj modal/overlay otvoren |
| UI-010 | `#reg-email` | placeholder: Email adresa | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Email adresa | vidljiv samo dok je taj modal/overlay otvoren |
| UI-011 | `#reg-password` | placeholder: Lozinka | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Lozinka | vidljiv samo dok je taj modal/overlay otvoren |
| UI-012 | `button.pw-eye` | aria-label: Prikaži/sakrij lozinku | dugme | `onclick="togglePw('reg-password',this)"` | prikazuje ili sakriva deo ekrana | vidljiv samo dok je taj modal/overlay otvoren |
| UI-013 | `#reg-confirm-password` | placeholder: Potvrdi lozinku | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Potvrdi lozinku | vidljiv samo dok je taj modal/overlay otvoren |
| UI-014 | `button.pw-eye` | aria-label: Prikaži/sakrij lozinku | dugme | `onclick="togglePw('reg-confirm-password',this)"` | prikazuje ili sakriva deo ekrana | vidljiv samo dok je taj modal/overlay otvoren |
| UI-015 | `#reg-btn` | Registruj se | dugme | `onclick="doRegister()"` | prijava/registracija/nalog | vidljiv samo dok je taj modal/overlay otvoren |
| UI-016 | `#forgot-email` | placeholder: Email adresa | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Email adresa | vidljiv samo dok je taj modal/overlay otvoren |
| UI-017 | `#forgot-btn` | Pošalji reset link | dugme | `onclick="doForgotPassword()"` | izvršava `doForgotPassword()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-018 | `a.auth-back-link` | ← Nazad na prijavu | link | `onclick="setAuthMode('login')"` | izvršava `setAuthMode()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-019 | `#reset-password` | placeholder: Nova lozinka (min. 8 karaktera) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Nova lozinka (min. 8 karaktera) | vidljiv samo dok je taj modal/overlay otvoren |
| UI-020 | `button.pw-eye` | aria-label: Prikaži/sakrij lozinku | dugme | `onclick="togglePw('reset-password',this)"` | prikazuje ili sakriva deo ekrana | vidljiv samo dok je taj modal/overlay otvoren |
| UI-021 | `#reset-password2` | placeholder: Potvrdite novu lozinku | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Potvrdite novu lozinku | vidljiv samo dok je taj modal/overlay otvoren |
| UI-022 | `button.pw-eye` | aria-label: Prikaži/sakrij lozinku | dugme | `onclick="togglePw('reset-password2',this)"` | prikazuje ili sakriva deo ekrana | vidljiv samo dok je taj modal/overlay otvoren |
| UI-023 | `#reset-btn` | Sačuvaj novu lozinku | dugme | `onclick="doResetPassword()"` | izvršava `doResetPassword()` | vidljiv samo dok je taj modal/overlay otvoren |

### modal `paywall-modal` — 2 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-024 | `button.modal-close` | &#x2715; | dugme | `onclick="closePaywall()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-025 | `button.modal-btn` | Pretplatite se -> | dugme | `onclick="openSubscription()"` | otvara prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |

### modal `pro-upgrade-modal` — 3 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-026 | `#pro-upgrade-modal` | &#x2715; PRO Vindex AI PRO Otključajte VindexAI PRO Modul za podneske dostupan je isključi | dugme (div) | `onclick="if(event.target===this)closeProUpgradeModal()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-027 | `button.modal-close` | &#x2715; | dugme | `onclick="closeProUpgradeModal()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-028 | `button.modal-btn.pro-upgrade-cta` | Pogledajte planove i cene -> | dugme | `onclick="closeProUpgradeModal();openProModal();"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |

### overlay `vx2-qa-overlay` (Brze akcije) — 5 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-029 | `#vx2-qa-overlay` | Novi predmet Novi klijent Baza znanja Pokreni analizu | dugme (div) | `onclick="if(event.target===this)vxCoreCloseQA()"` | izvršava `vxCoreCloseQA()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-030 | `button.vx2-qa-item` | Novi predmet | dugme | `onclick="vxCoreCloseQA();intakeOtvori()"` | izvršava `vxCoreCloseQA()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-031 | `button.vx2-qa-item` | Novi klijent | dugme | `onclick="vxCoreCloseQA();setTab(document.getElementById('tab-btn-k'),'k');setTimeout(crmOtvoriFormu,250)"` | izvršava `vxCoreCloseQA()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-032 | `button.vx2-qa-item` | Baza znanja | dugme | `onclick="vxCoreCloseQA();setTab(document.getElementById('tab-btn-dok'),'dok')"` | izvršava `vxCoreCloseQA()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-033 | `button.vx2-qa-item` | Pokreni analizu | dugme | `onclick="vxCoreCloseQA();openAITool('q')"` | izvršava `vxCoreCloseQA()` | vidljiv samo dok je taj modal/overlay otvoren |

### plutajuće (FAB feedback) — 1 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-034 | `#feedback-fab` | 💬 | FAB | `onclick="feedbackOpen()"` | otvara prozor/panel | ne |

### modal `feedback-modal` — 10 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-035 | `#feedback-modal` | &#x2715; Pošaljite feedback ★ ★ ★ ★ ★ 📷 Uhvati snimak ekrana ✓ Snimljeno Pošaljite | dugme (div) | `onclick="if(event.target===this)feedbackClose()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-036 | `button.modal-close` | &#x2715; | dugme | `onclick="feedbackClose()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-037 | `span.feedback-star` | ★ | dugme (span) | `onclick="feedbackSetRating(1)"` | pomoć/podrška i povratna informacija | vidljiv samo dok je taj modal/overlay otvoren |
| UI-038 | `span.feedback-star` | ★ | dugme (span) | `onclick="feedbackSetRating(2)"` | pomoć/podrška i povratna informacija | vidljiv samo dok je taj modal/overlay otvoren |
| UI-039 | `span.feedback-star` | ★ | dugme (span) | `onclick="feedbackSetRating(3)"` | pomoć/podrška i povratna informacija | vidljiv samo dok je taj modal/overlay otvoren |
| UI-040 | `span.feedback-star` | ★ | dugme (span) | `onclick="feedbackSetRating(4)"` | pomoć/podrška i povratna informacija | vidljiv samo dok je taj modal/overlay otvoren |
| UI-041 | `span.feedback-star` | ★ | dugme (span) | `onclick="feedbackSetRating(5)"` | pomoć/podrška i povratna informacija | vidljiv samo dok je taj modal/overlay otvoren |
| UI-042 | `#feedback-opis` | placeholder: Šta ste primetili? Šta bismo mogli da poboljšamo? | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Šta ste primetili? Šta bismo mogli da poboljšamo? | vidljiv samo dok je taj modal/overlay otvoren |
| UI-043 | `#feedback-screenshot-btn` | 📷 Uhvati snimak ekrana | dugme | `onclick="feedbackCaptureScreenshot()"` | pomoć/podrška i povratna informacija | vidljiv samo dok je taj modal/overlay otvoren |
| UI-044 | `#feedback-submit-btn` | Pošaljite | dugme | `onclick="feedbackSubmit()"` | pomoć/podrška i povratna informacija | vidljiv samo dok je taj modal/overlay otvoren |

### modal `pro-modal` (cenovnik / planovi) — 2 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-045 | `#pro-modal` | &#x2715; Odaberite plan za vašu kancelariju Bez skrivenih troškova. Otkazivanje u bilo kom | dugme (div) | `onclick="if(event.target===this)closeProModal()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-046 | `button.modal-close` | &#x2715; | dugme | `onclick="closeProModal()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |

### modal `ugovor-modal` (ugovor o zastupanju) — 14 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-047 | `#ugovor-modal` | &#x2715; Ugovor o zastupanju Popunite podatke — ugovor se generiše automatski Ime i prezim | dugme (div) | `onclick="if(event.target===this)ugovor_closeModal()"` | zatvara otvoreni prozor/panel | `display:none` na samom elementu; vidljiv samo dok je taj modal/overlay otvoren |
| UI-048 | `button` (index.html:308) | &#x2715; | dugme | `onclick="ugovor_closeModal()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-049 | `#uz-klijent-ime` | placeholder: Petar Petrović | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Petar Petrović | vidljiv samo dok je taj modal/overlay otvoren |
| UI-050 | `#uz-klijent-adresa` | placeholder: Ul. Knez Mihailova 1, Beograd | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Ul. Knez Mihailova 1, Beograd | vidljiv samo dok je taj modal/overlay otvoren |
| UI-051 | `#uz-klijent-firma` | placeholder: Kompanija d.o.o. | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Kompanija d.o.o. | vidljiv samo dok je taj modal/overlay otvoren |
| UI-052 | `#uz-advokat-ime` | placeholder: Marko Marković | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Marko Marković | vidljiv samo dok je taj modal/overlay otvoren |
| UI-053 | `#uz-advokat-adresa` | placeholder: Ul. Terazije 10, Beograd | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Ul. Terazije 10, Beograd | vidljiv samo dok je taj modal/overlay otvoren |
| UI-054 | `#uz-predmet-opis` | placeholder: Naknada štete iz saobraćajne nezgode od 12.03.2026 | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Naknada štete iz saobraćajne nezgode od 12.03.2026 | vidljiv samo dok je taj modal/overlay otvoren |
| UI-055 | `#uz-oblast` | vizuelna `<label>` iznad (bez `for=`): Oblast prava | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Oblast prava | vidljiv samo dok je taj modal/overlay otvoren |
| UI-056 | `#uz-nagrada-tip` | vizuelna `<label>` iznad (bez `for=`): Naknada | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Naknada | vidljiv samo dok je taj modal/overlay otvoren |
| UI-057 | `#uz-nagrada-iznos` | placeholder: 50.000 RSD ili po dogovoru | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: 50.000 RSD ili po dogovoru | vidljiv samo dok je taj modal/overlay otvoren |
| UI-058 | `#uz-datum` | vizuelna `<label>` iznad (bez `for=`): Datum zaključenja | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Datum zaključenja | vidljiv samo dok je taj modal/overlay otvoren |
| UI-059 | `#uz-btn` | Generiši i sačuvaj | dugme | `onclick="ugovor_generiši(true)"` | izrada nacrta/podneska | vidljiv samo dok je taj modal/overlay otvoren |
| UI-060 | `button` (index.html:373) | Samo prikaži | dugme | `onclick="ugovor_generiši(false)"` | izrada nacrta/podneska | vidljiv samo dok je taj modal/overlay otvoren |

### modal `pred-new-modal` (brzi novi predmet) — 6 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-061 | `#pred-new-modal` | &#x2715; Novi predmet Unesite osnovne informacije. Detalje možete dodati naknadno. Naziv p | dugme (div) | `onclick="if(event.target===this)pred_closeNewModal()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-062 | `button.modal-close` | &#x2715; | dugme | `onclick="pred_closeNewModal()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-063 | `#pred-new-naziv` | placeholder: Npr. Tužba za naknadu štete | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Npr. Tužba za naknadu štete | vidljiv samo dok je taj modal/overlay otvoren |
| UI-064 | `#pred-new-tip` | vizuelna `<label>` iznad (bez `for=`): Tip postupka | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Tip postupka | vidljiv samo dok je taj modal/overlay otvoren |
| UI-065 | `#pred-new-opis` | placeholder: Kratki opis predmeta... | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Kratki opis predmeta... | vidljiv samo dok je taj modal/overlay otvoren |
| UI-066 | `button.modal-btn` | Kreiraj predmet | dugme | `onclick="pred_kreiraj()"` | izvršava `pred_kreiraj()` | vidljiv samo dok je taj modal/overlay otvoren |

### modal `progressive disclosure` (otključavanje) — 4 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-067 | `#vx-unlock-overlay` | Nova mogućnost otključana Isprobaj odmah → Zatvori automatski se zatvara za 8 sekundi | dugme (div) | `onclick="_vxPdCloseModal()"` | izvršava `_vxPdCloseModal()` | `display:none` na samom elementu; vidljiv samo dok je taj modal/overlay otvoren |
| UI-068 | `#vx-unlock-modal` | Nova mogućnost otključana Isprobaj odmah → Zatvori automatski se zatvara za 8 sekundi | dugme (div) | `onclick="event.stopPropagation()"` | upravlja tajmerom/naplatom vremena | vidljiv samo dok je taj modal/overlay otvoren |
| UI-069 | `button` (index.html:421) | Isprobaj odmah → | dugme | `onclick="_vxPdCloseModal()"` | izvršava `_vxPdCloseModal()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-070 | `button` (index.html:422) | Zatvori | dugme | `onclick="_vxPdCloseModal()"` | izvršava `_vxPdCloseModal()` | vidljiv samo dok je taj modal/overlay otvoren |

### bočna traka (glavna navigacija) — 17 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-071 | `#tab-btn-h` | Pregled dana | tab | `onclick="setTab(this,'h')"` | prebacuje korisnika na drugi ekran/tab | ne |
| UI-072 | `#tab-btn-p` | Predmeti | tab | `onclick="setTab(this,'p')"` | prebacuje korisnika na drugi ekran/tab | ne |
| UI-073 | `#tab-btn-k` | Klijenti | tab | `onclick="setTab(this,'k')"` | prebacuje korisnika na drugi ekran/tab | ne |
| UI-074 | `#tab-btn-kal` | Rokovi | tab | `onclick="setTab(this,'kal');setTimeout(function(){if(typeof kalSetView==='function')kalSetView('list');},120)"` | prebacuje korisnika na drugi ekran/tab | ne |
| UI-075 | `#tab-btn-aiws` | Vindex Intelligence | tab | `onclick="setTab(this,'aiws')"` | prebacuje korisnika na drugi ekran/tab | ne |
| UI-076 | `#tab-btn-s` | Sudska praksa | tab | `onclick="setTab(this,'s')"` | prebacuje korisnika na drugi ekran/tab | ne |
| UI-077 | `#tab-btn-dok` | Dokumenti | tab | `onclick="setTab(this,'dok')"` | prebacuje korisnika na drugi ekran/tab | ne |
| UI-078 | `#tab-btn-doctpl` | Šabloni dokumenata | tab | `onclick="docTplOpen()"` | otvara prozor/panel | ne |
| UI-079 | `#tab-btn-zadaci-g` | Zadatci | tab | `onclick="setTab(this,'zadaci-g')"` | prebacuje korisnika na drugi ekran/tab | ne |
| UI-080 | `#tab-btn-fin` | Finansije | tab | `onclick="setTab(this,'fin')"` | prebacuje korisnika na drugi ekran/tab | ne |
| UI-081 | `#tab-btn-kanc` | Kancelarija | tab | `onclick="setTab(this,'kanc')"` | prebacuje korisnika na drugi ekran/tab | ne |
| UI-082 | `#tab-btn-pi-nav` | Portfolio kancelarije | tab | `onclick="setTab(document.getElementById('tab-btn-pi'),'pi')"` | prebacuje korisnika na drugi ekran/tab | `display:none` na samom elementu |
| UI-083 | `#tab-btn-settings` | Podešavanja | tab | `onclick="setTab(this,'settings')"` | prebacuje korisnika na drugi ekran/tab | ne |
| UI-084 | `#tab-btn-notif` | (bez labele) | tab | `onclick="notif_toggleDropdown()"` | notifikacije | skriven tab (`vx-hidden-tab`) |
| UI-085 | `#tab-btn-pi` | (bez labele) | tab | `onclick="setTab(this,'pi')"` | prebacuje korisnika na drugi ekran/tab | skriven tab (`vx-hidden-tab`) |
| UI-086 | `div.vx-foot-row` | Svetla tema | dugme (div) | `onclick="toggleLightTheme()"` | prikazuje ili sakriva deo ekrana | ne |
| UI-087 | `div.vx-foot-row` | Pozovite kolegu | dugme (div) | `onclick="wl_open()"` | otvara prozor/panel | ne |

### gornja traka — 14 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-088 | `div.vx-global-search` | ⌕ Pretraži predmete, klijente, dokumente, zadatke... ⌘K | dugme (div) | `onclick="cmdkOpen()"` | otvara prozor/panel | ne |
| UI-089 | `#mi-overlay` | (bez labele) | dugme (div) | `onclick="mesecniIzvestajZatvori()"` | zatvara otvoreni prozor/panel | `display:none` na samom elementu |
| UI-090 | `#mi-mesec-sel` | (bez labele) | polje | `onchange="mesecniIzvestajUcitaj()"` | korisnik unosi/bira vrednost — polje bez opisa | ne |
| UI-091 | `button` (index.html:560) | ✕ | dugme | `onclick="mesecniIzvestajZatvori()"` | zatvara otvoreni prozor/panel | ne |
| UI-092 | `#vx-mic-btn` | Govori | dugme | `onclick="typeof voiceStart==='function' ? voiceStart() : showToast('Glasovne komande rade u Chrome/Edge pregledaču','info')"` | glasovna interakcija | ne |
| UI-093 | `#notif-bell` | title: Obaveštenja | dugme (div) | `onclick="notif_toggleDropdown()"` | notifikacije | ne |
| UI-094 | `#pwa-install-btn` | Instaliraj | dugme | `onclick="pwaInstall()"` | instalacija aplikacije | `display:none` na samom elementu |
| UI-095 | `button.vx-btn-new` | + Novi predmet | dugme | `onclick="intakeOtvori()"` | otvara prozor/panel | ne |
| UI-096 | `button.vx-btn-new` | + Iz dokumenta | dugme | `onclick="siOtvori()"` | otvara prozor/panel | ne |
| UI-097 | `#voice-cmd-btn` | title: Glasovna komanda (Alt+V) | dugme | `onclick="voice_start()"` | glasovna interakcija | `display:none` na samom elementu |
| UI-098 | `#btn-hitan-hidden` | title: Brzo kreiranje predmeta | dugme | `onclick="qiOtvori()"` | otvara prozor/panel | `display:none` na samom elementu |
| UI-099 | `#btn-csv-hidden` | title: Uvezi iz CSV | dugme | `onclick="bulkOtvori()"` | otvara prozor/panel | `display:none` na samom elementu |
| UI-100 | `button.settings-btn.vx-topbar-settings` | title: Podešavanja | dugme | `onclick="openSettings()"` | otvara prozor/panel | `display:none` na samom elementu |
| UI-101 | `#vx-back-btn` | Nazad | dugme | `onclick="vxGoBack()"` | izvršava `vxGoBack()` | ne |

### kartica Predmeti — lista/kanban — 13 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-102 | `button.pred-new-btn` | Otvori novi predmet | dugme | `onclick="intakeOtvori()"` | otvara prozor/panel | ne |
| UI-103 | `button.pred-new-btn` | Otpremi dokumenta | dugme | `onclick="siOtvori()"` | otvara prozor/panel | ne |
| UI-104 | `button.vx-pill.pred-sort-btn.is-active` | Svi | dugme | `onclick="pred_setSort('svi')"` | izvršava `pred_setSort()` | ne |
| UI-105 | `button.vx-pill.pred-sort-btn` | Prioritet | dugme | `onclick="pred_setSort('prioritet')"` | izvršava `pred_setSort()` | ne |
| UI-106 | `button.vx-pill.pred-sort-btn` | ⚠ Rizik | dugme | `onclick="pred_setSort('rizik')"` | izvršava `pred_setSort()` | ne |
| UI-107 | `button.vx-pill.pred-sort-btn` | Rokovi | dugme | `onclick="pred_setSort('rokovi')"` | izvršava `pred_setSort()` | ne |
| UI-108 | `#pred-firma-toggle` | Firma | dugme | `onclick="predFirmaToggle()"` | prikazuje ili sakriva deo ekrana | `display:none` na samom elementu |
| UI-109 | `button.vx-btn.vx-btn-secondary` | Arhivuj | dugme | `onclick="pred_bulkAkcija('arhiviranje')"` | izvršava `pred_bulkAkcija()` | ne |
| UI-110 | `button.vx-btn.vx-btn-ghost` | Aktiviraj | dugme | `onclick="pred_bulkAkcija('aktiviranje')"` | izvršava `pred_bulkAkcija()` | ne |
| UI-111 | `button.vx-btn.vx-btn-ghost` | ✕ | dugme | `onclick="pred_bulkOtkaziOznacavanje()"` | izvršava `pred_bulkOtkaziOznacavanje()` | ne |
| UI-112 | `#kanban-view-btn-lista` | ≡ Lista | dugme | `onclick="kanban_setView('lista')"` | izvršava `kanban_setView()` | ne |
| UI-113 | `#kanban-view-btn-kanban` | ⬛ Kanban | dugme | `onclick="kanban_setView('kanban')"` | izvršava `kanban_setView()` | ne |
| UI-114 | `button` (index.html:695) | ▶ Suprotne strane | dugme | `onclick="opposing_toggle()"` | prikazuje ili sakriva deo ekrana | ne |

### kartica predmeta — zaglavlje, tajmer, podtabovi — 16 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-115 | `#pred-timer-start-btn` | ▶ Start | dugme | `onclick="timer_start()"` | upravlja tajmerom/naplatom vremena | vidljiv samo kad je predmet otvoren |
| UI-116 | `#pred-timer-stop-btn` | ■ Stop + Sačuvaj | dugme | `onclick="timer_stop()"` | upravlja tajmerom/naplatom vremena | `display:none` na samom elementu; vidljiv samo kad je predmet otvoren |
| UI-117 | `button` (index.html:728) | ✕ | dugme | `onclick="timer_discard()"` | upravlja tajmerom/naplatom vremena | vidljiv samo kad je predmet otvoren |
| UI-118 | `#tab-pregled-btn` | Pregled | tab | `onclick="pred_subtabSwitch('pregled',this)"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo kad je predmet otvoren |
| UI-119 | `button.pred-subtab-btn.pred-tab-primary` | Dokumenti | tab | `onclick="pred_subtabSwitch('dokumenti',this)"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo kad je predmet otvoren |
| UI-120 | `#tab-ai-btn` | AI Analiza | tab | `onclick="pred_subtabSwitch('agenti',this)"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo kad je predmet otvoren |
| UI-121 | `#tab-rokovi-btn` | Rokovi | tab | `onclick="pred_subtabSwitch('rokovi',this)"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo kad je predmet otvoren |
| UI-122 | `#tab-zadaci-btn` | Zadaci | tab | `onclick="pred_subtabSwitch('zadaci',this)"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo kad je predmet otvoren |
| UI-123 | `#tab-workflow-btn` | Workflow | tab | `onclick="pred_subtabSwitch('workflow',this)"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo kad je predmet otvoren |
| UI-124 | `#tab-strategija-btn` | Strategija | tab | `onclick="pred_subtabSwitch('strategija',this)"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo kad je predmet otvoren |
| UI-125 | `#tab-naplata-btn` | Naplata | tab | `onclick="pred_subtabSwitch('naplata',this)"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo kad je predmet otvoren |
| UI-126 | `#pred-more-btn` | ⋯ Više | tab | `onclick="pred_more_toggle(event)"` | prikazuje ili sakriva deo ekrana | vidljiv samo kad je predmet otvoren |
| UI-127 | `button` (index.html:746) | Komunikacija | dugme | `onclick="pred_more_select('komunikacija')"` | izvršava `pred_more_select()` | vidljiv samo kad je predmet otvoren |
| UI-128 | `button` (index.html:747) | Saradnja | dugme | `onclick="pred_more_select('saradnja')"` | izvršava `pred_more_select()` | vidljiv samo kad je predmet otvoren |
| UI-129 | `button` (index.html:748) | Mapa veza | dugme | `onclick="pred_more_select('graf')"` | izvršava `pred_more_select()` | vidljiv samo kad je predmet otvoren |
| UI-130 | `button` (index.html:749) | Profitabilnost | dugme | `onclick="pred_more_select('profitabilnost')"` | izvršava `pred_more_select()` | vidljiv samo kad je predmet otvoren |

### kartica predmeta → pan Pregled — 53 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-131 | `button.vx-btn.vx-btn-ghost` | ↺ | dugme | `onclick="ccc_load()"` | izvršava `ccc_load()` | vidljiv samo kad je predmet otvoren |
| UI-132 | `button.vx-btn.vx-btn-ghost` | Štampaj | dugme | `onclick="pred_print()"` | izvršava `pred_print()` | vidljiv samo kad je predmet otvoren |
| UI-133 | `#pred-pdf-export-btn` | PDF | dugme | `onclick="predmetPdfExport(this)"` | izvozi/preuzima dokument | vidljiv samo kad je predmet otvoren |
| UI-134 | `#ccc-zatvori-btn` | ✕ Zatvori | dugme | `onclick="pred_zatvoriOtvori()"` | zatvara otvoreni prozor/panel | `display:none` na samom elementu; vidljiv samo kad je predmet otvoren |
| UI-135 | `button` (index.html:782) | Analiziraj | dugme | `onclick="this.textContent='Pokrećem...';this.disabled=true;pred_launchKompletnaAnaliza();var _b=this;setTimeout(function(){_b.textContent='Analiziraj';_b.di…"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |
| UI-136 | `#pred-s-tuzilac` | — | dugme (span) | `onclick="_predInlineEdit('pred-s-tuzilac','tuzilac','text')"` | izvršava `_predInlineEdit()` | vidljiv samo kad je predmet otvoren |
| UI-137 | `#pred-s-tuzeni` | — | dugme (span) | `onclick="_predInlineEdit('pred-s-tuzeni','tuzeni','text')"` | izvršava `_predInlineEdit()` | vidljiv samo kad je predmet otvoren |
| UI-138 | `#pred-s-oblast` | — | dugme (span) | `onclick="_predInlineEdit('pred-s-oblast','tip','oblast-select')"` | izvršava `_predInlineEdit()` | vidljiv samo kad je predmet otvoren |
| UI-139 | `#pred-s-rizik` | — | dugme (span) | `onclick="_predInlineEdit('pred-s-rizik','rizik','rizik-select')"` | izvršava `_predInlineEdit()` | vidljiv samo kad je predmet otvoren |
| UI-140 | `#pred-s-vrednost` | — | dugme (span) | `onclick="_predInlineEdit('pred-s-vrednost','vrednost_spora','text')"` | izvršava `_predInlineEdit()` | vidljiv samo kad je predmet otvoren |
| UI-141 | `button.vx-btn.vx-btn-ghost` | title: Kopiraj sažetak | dugme | `onclick="pckCopySazetak(this)"` | kopira tekst u ostavu | vidljiv samo kad je predmet otvoren |
| UI-142 | `button` (index.html:869) | ↺ | dugme | `onclick="matter_intel_load()"` | izvršava `matter_intel_load()` | vidljiv samo kad je predmet otvoren |
| UI-143 | `#pred-crs-run-btn` | ↻ Analiziraj | dugme | `onclick="pred_runPipeline()"` | izvršava `pred_runPipeline()` | vidljiv samo kad je predmet otvoren |
| UI-144 | `#pred-beleska-input` | placeholder: Nova beleška... | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Nova beleška... | vidljiv samo kad je predmet otvoren |
| UI-145 | `#mic-pred-beleska-input` | title: Glasovni unos | dugme | `onclick="micToggle('pred-beleska-input')"` | glasovna interakcija | vidljiv samo kad je predmet otvoren |
| UI-146 | `button` (index.html:938) | Dodaj | dugme | `onclick="pred_dodajBelesku()"` | izvršava `pred_dodajBelesku()` | vidljiv samo kad je predmet otvoren |
| UI-147 | `#pred-zatvori-ishod` | vizuelna `<label>` iznad (bez `for=`): Ishod | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Ishod | vidljiv samo kad je predmet otvoren |
| UI-148 | `#pred-zatvori-zakljucak` | placeholder: Kratak zaključak i pouka iz predmeta... | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Kratak zaključak i pouka iz predmeta... | vidljiv samo kad je predmet otvoren |
| UI-149 | `input` (index.html:962) | vizuelna `<label>` iznad (bez `for=`): Presudni faktori — pomaže Vindex Intelligence da uči (opciono) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Presudni faktori — pomaže Vindex Intelligence da uči (opciono) | vidljiv samo kad je predmet otvoren |
| UI-150 | `input` (index.html:963) | vizuelna `<label>` iznad (bez `for=`): Veštačenje | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Veštačenje | vidljiv samo kad je predmet otvoren |
| UI-151 | `input` (index.html:964) | vizuelna `<label>` iznad (bez `for=`): Svedoci | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Svedoci | vidljiv samo kad je predmet otvoren |
| UI-152 | `input` (index.html:965) | vizuelna `<label>` iznad (bez `for=`): Zastarelost | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Zastarelost | vidljiv samo kad je predmet otvoren |
| UI-153 | `input` (index.html:966) | vizuelna `<label>` iznad (bez `for=`): Procesna greška | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Procesna greška | vidljiv samo kad je predmet otvoren |
| UI-154 | `input` (index.html:967) | vizuelna `<label>` iznad (bez `for=`): Novi dokaz | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Novi dokaz | vidljiv samo kad je predmet otvoren |
| UI-155 | `input` (index.html:968) | vizuelna `<label>` iznad (bez `for=`): Sporazum | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Sporazum | vidljiv samo kad je predmet otvoren |
| UI-156 | `input` (index.html:969) | vizuelna `<label>` iznad (bez `for=`): Sudska praksa | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Sudska praksa | vidljiv samo kad je predmet otvoren |
| UI-157 | `input` (index.html:970) | vizuelna `<label>` iznad (bez `for=`): Pisana komunikacija | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Pisana komunikacija | vidljiv samo kad je predmet otvoren |
| UI-158 | `#pred-zatvori-trajanje` | placeholder: Trajanje (meseci) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Trajanje (meseci) | vidljiv samo kad je predmet otvoren |
| UI-159 | `#pred-zatvori-vrednost` | placeholder: Vrednost spora (RSD) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Vrednost spora (RSD) | vidljiv samo kad je predmet otvoren |
| UI-160 | `#pred-zatvori-btn` | Potvrdi zatvaranje | dugme | `onclick="pred_zatvoriPredmet()"` | zatvara otvoreni prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-161 | `button` (index.html:979) | Odustani | dugme | `onclick="pred_zatvoriCancel()"` | zatvara otvoreni prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-162 | `#pred-zatvori-trigger` | ✕ Zatvori predmet | dugme | `onclick="pred_zatvoriOtvori()"` | zatvara otvoreni prozor/panel | `display:none` na samom elementu; vidljiv samo kad je predmet otvoren |
| UI-163 | `#pred-rokovi-toggle-btn` | + Generiši lanac | dugme | `onclick="pred_rokokiToggle()"` | rokovi i ročišta | vidljiv samo kad je predmet otvoren |
| UI-164 | `#pred-rokovi-tip` | vizuelna `<label>` iznad (bez `for=`): Procesni akt | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Procesni akt | vidljiv samo kad je predmet otvoren |
| UI-165 | `#pred-rokovi-datum` | vizuelna `<label>` iznad (bez `for=`): Datum dostave | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Datum dostave | vidljiv samo kad je predmet otvoren |
| UI-166 | `#pred-rokovi-btn` | Generiši i sačuvaj | dugme | `onclick="pred_rokokiGeneriši(true)"` | rokovi i ročišta | vidljiv samo kad je predmet otvoren |
| UI-167 | `button` (index.html:1007) | Samo prikaži | dugme | `onclick="pred_rokokiGeneriši(false)"` | rokovi i ročišta | vidljiv samo kad je predmet otvoren |
| UI-168 | `button` (index.html:1008) | ✕ | dugme | `onclick="pred_rokokiOtvoriFormu(false)"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-169 | `button` (index.html:1019) | + Generiši ugovor | dugme | `onclick="ugovor_openModal()"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-170 | `#portal-toggle-btn` | + Generiši link | dugme | `onclick="portal_toggleForm()"` | prikazuje ili sakriva deo ekrana | vidljiv samo kad je predmet otvoren |
| UI-171 | `#portal-email` | placeholder: klijent@email.com | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: klijent@email.com | vidljiv samo kad je predmet otvoren |
| UI-172 | `#portal-days` | vizuelna `<label>` iznad (bez `for=`): Valjanost linka | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Valjanost linka | vidljiv samo kad je predmet otvoren |
| UI-173 | `#portal-gen-btn` | Generiši link | dugme | `onclick="portal_generateLink()"` | klijentski portal / portal suda | vidljiv samo kad je predmet otvoren |
| UI-174 | `button` (index.html:1043) | ✕ | dugme | `onclick="portal_toggleForm()"` | prikazuje ili sakriva deo ekrana | vidljiv samo kad je predmet otvoren |
| UI-175 | `button` (index.html:1050) | Kopiraj | dugme | `onclick="portal_copyLink()"` | kopira tekst u ostavu | vidljiv samo kad je predmet otvoren |
| UI-176 | `button` (index.html:1051) | ✕ Zatvori | dugme | `onclick="portal_toggleForm()"` | prikazuje ili sakriva deo ekrana | vidljiv samo kad je predmet otvoren |
| UI-177 | `button` (index.html:1059) | ↻ Osveži | dugme | `onclick="portal_loadUploads()"` | otprema dokument | vidljiv samo kad je predmet otvoren |
| UI-178 | `button.vx-rad-tool-btn` | Istraživanje zakona | dugme | `onclick="openAITool('q')"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-179 | `button.vx-rad-tool-btn` | Sudska praksa | dugme | `onclick="openAITool('s')"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-180 | `button.vx-rad-tool-btn` | Nacrti podnesaka | dugme | `onclick="openAITool('n')"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-181 | `button.vx-rad-tool-btn` | Analiza dokumenta | dugme | `onclick="openAITool('a')"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-182 | `button.vx-rad-tool-btn` | Šabloni | dugme | `onclick="docTplOpen()"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-183 | `button.vx-rad-tool-btn` | PDF Izveštaj | dugme | `onclick="predmetPdfExport()"` | izvozi/preuzima dokument | vidljiv samo kad je predmet otvoren |

### kartica predmeta → pan Dokumenti — 6 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-184 | `#pred-upload-input` | (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | polje | `onchange="pred_upload_doc(this.files[0])"` | korisnik unosi/bira vrednost — (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | `display:none` na samom elementu; vidljiv samo kad je predmet otvoren |
| UI-185 | `#pred-upload-zone` | Prevucite dokument ili kliknite za upload PDF, DOCX — do 10MB | dugme (div) | `onclick="pred_upload_trigger()"` | otprema dokument | vidljiv samo kad je predmet otvoren |
| UI-186 | `div.crossdoc-hd` | Cross-doc analiza — poređenje dokumenata 0 odabrano ▼ | dugme (div) | `onclick="crossdoc_toggleSection(this)"` | prikazuje ili sakriva deo ekrana | vidljiv samo kad je predmet otvoren |
| UI-187 | `#crossdoc-pitanje` | placeholder: npr. Da li postoje kontradikcije između ovih dokumenata? | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: npr. Da li postoje kontradikcije između ovih dokumenata? | vidljiv samo kad je predmet otvoren |
| UI-188 | `#mic-crossdoc-pitanje` | title: Glasovni unos | dugme | `onclick="micToggle('crossdoc-pitanje')"` | glasovna interakcija | vidljiv samo kad je predmet otvoren |
| UI-189 | `button.vx-btn.vx-btn-primary` | Analiziraj konflikte | dugme | `onclick="crossdoc_analiziraj()"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |

### kartica predmeta → pan Strategija — 23 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-190 | `#strat-plan-info` | pogledajte planove → | dugme (span) | `onclick="openProModal()"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-191 | `div.vx-insight-panel.vx-insight-hero` | ◆ Preporučeno PRO Kompletna analiza predmeta Sveobuhvatna pravna analiza u jednom izveštaj | dugme (div) | `onclick="pred_launchKompletnaAnaliza()"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |
| UI-192 | `button.vx-phase-tab.active` | 1 Intake & Analiza | tab | `onclick="predStratPhaseSwitch('1',this)"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |
| UI-193 | `button.vx-phase-tab` | 2 Strategija & Svedoci | tab | `onclick="predStratPhaseSwitch('2',this)"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |
| UI-194 | `button.vx-phase-tab` | 3 Izrada Nacrta | tab | `onclick="predStratPhaseSwitch('3',this)"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |
| UI-195 | `button.vx-phase-tab` | 4 Simulacija Suda | tab | `onclick="predStratPhaseSwitch('4',this)"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |
| UI-196 | `div.strat-feature-card` | Revizija dokumenta PRO Sistem čita vaš podnesak ili ugovor i daje konkretne sugestije za p | dugme (div) | `onclick="pred_openStrat('revizor')"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-197 | `div.strat-feature-card` | Analiza rizika PRO Sistemska provera pravnih rizika pre preuzimanja, investicije ili ulaga | dugme (div) | `onclick="pred_openStrat('due_diligence')"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-198 | `div.strat-feature-card` | Analiza crvenog tima PRO Sistem preuzima ulogu protivničkog advokata i napada vašu argumen | dugme (div) | `onclick="pred_openStrat('red_team')"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-199 | `div.strat-feature-card` | Analiza svedoka PRO Analizira iskaze svedoka, otkriva kontradikcije, predlaže pitanja za u | dugme (div) | `onclick="pred_openStrat('witness')"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-200 | `div.strat-feature-card` | Otvori Nacrti & Podnesci Generisanje tužbi, žalbi, ugovora i drugih podnesaka na osnovu pr | dugme (div) | `onclick="pred_openDraftEngine()"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-201 | `div.strat-feature-card` | Sudija — procena ishoda PRO Simulira sudijsku odluku na osnovu vaših argumenata, dokaza i  | dugme (div) | `onclick="pred_openStrat('sudija')"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-202 | `div.strat-feature-card` | Simulacija sudskog postupka PRO Detaljna simulacija celog postupka: pitanja suda, argument | dugme (div) | `onclick="pred_openStrat('sudija_v2')"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-203 | `div.strat-feature-card` | Simulacija parničnog postupka PRO Kompletna simulacija od tužbe do presude — identifikuje  | dugme (div) | `onclick="pred_openStrat('litigation')"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-204 | `div.strat-feature-card` | Predikcija ishoda PRO Statistička procena šansi za uspeh (%) na osnovu srpske sudske praks | dugme (div) | `onclick="pred_openStrat('court_predictor')"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-205 | `div.strat-feature-card` | Hearing Command Center PRO Borbeni brifing pred ročište: teret dokazivanja, nedostajući do | dugme (div) | `onclick="pred_subtabSwitch('rokovi')"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo kad je predmet otvoren |
| UI-206 | `#twin-card` | Digital Twin — simulacija razvoja PRO AI simulira 3 scenarija razvoja predmeta (optimistič | dugme (div) | `onclick="twinPanelShow()"` | prikazuje ili sakriva deo ekrana | vidljiv samo kad je predmet otvoren |
| UI-207 | `#outcome-intel-card` | Analiza uspeha kancelarije PRO Statistika svih zatvorenih predmeta vaše kancelarije — koji | dugme (div) | `onclick="outcome_intel_panel_show()"` | prikazuje ili sakriva deo ekrana | vidljiv samo kad je predmet otvoren |
| UI-208 | `button` (index.html:1282) | ✕ | dugme | `onclick="document.getElementById('outcome-intel-panel').style.display='none';"` | izvršava `document.getElementById()` | vidljiv samo kad je predmet otvoren |
| UI-209 | `#twin-simuliraj-btn` | Pokreni simulaciju (3 kredita) | dugme | `onclick="twinSimulirajPokreni()"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |
| UI-210 | `button` (index.html:1297) | ✕ | dugme | `onclick="document.getElementById('twin-panel').style.display='none';"` | izvršava `document.getElementById()` | vidljiv samo kad je predmet otvoren |
| UI-211 | `#twin-hipoteza-input` | placeholder: npr. Da smo prihvatili nagodbu od 500.000 RSD... | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: npr. Da smo prihvatili nagodbu od 500.000 RSD... | vidljiv samo kad je predmet otvoren |
| UI-212 | `button.vx-btn.vx-btn-secondary` | Analiziraj | dugme | `onclick="twinStaAkoPokreni()"` | izvršava `twinStaAkoPokreni()` | vidljiv samo kad je predmet otvoren |

### kartica predmeta → pan Rokovi — 12 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-213 | `button.vx-btn.vx-btn-secondary` | + Zakaži | dugme | `onclick="rocisteOtvoriFormu(activePredmetId)"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-214 | `button` (index.html:1327) | ZPP Lanac rokova ▼ | dugme | `onclick="lanac_toggleSection(this)"` | prikazuje ili sakriva deo ekrana | vidljiv samo kad je predmet otvoren |
| UI-215 | `#lanac-tip` | (bez labele — prva opcija: „-- Tip procesnog akta --“) | polje | `onchange="lanac_tipChange()"` | korisnik unosi/bira vrednost — (bez labele — prva opcija: „-- Tip procesnog akta --“) | vidljiv samo kad je predmet otvoren |
| UI-216 | `#lanac-datum` | title: Datum prijema/dostave akta | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — title: Datum prijema/dostave akta | vidljiv samo kad je predmet otvoren |
| UI-217 | `button.vx-btn.vx-btn-secondary` | Izračunaj | dugme | `onclick="lanac_kalkulisi()"` | rokovi i ročišta | vidljiv samo kad je predmet otvoren |
| UI-218 | `#hcc-datum` | placeholder: Datum ročišta | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Datum ročišta | vidljiv samo kad je predmet otvoren |
| UI-219 | `#hcc-tip` | (bez labele — prva opcija: „Parničan (ZPP)“) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — (bez labele — prva opcija: „Parničan (ZPP)“) | vidljiv samo kad je predmet otvoren |
| UI-220 | `#hcc-btn` | Generiši pripremu za ročište (3 kredita) | dugme | `onclick="hccGeneriši()"` | izvršava `hccGeneriši()` | vidljiv samo kad je predmet otvoren |
| UI-221 | `#portal-section-btn` | Praćenje na portal.sud.rs NOVO ▼ | dugme | `onclick="portalToggleSection(this)"` | prikazuje ili sakriva deo ekrana | vidljiv samo kad je predmet otvoren |
| UI-222 | `#portal-broj` | placeholder: npr. P 123/2024 | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: npr. P 123/2024 | vidljiv samo kad je predmet otvoren |
| UI-223 | `#portal-sud` | placeholder: Naziv suda | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Naziv suda | vidljiv samo kad je predmet otvoren |
| UI-224 | `button` (index.html:1384) | + Dodaj na praćenje | dugme | `onclick="portalDodajPraceni()"` | klijentski portal / portal suda | vidljiv samo kad je predmet otvoren |

### kartica predmeta → pan Naplata — 17 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-225 | `#billing-timer-btn` | ▶ Start tajmer | dugme | `onclick="billing_timerToggle()"` | upravlja tajmerom/naplatom vremena | vidljiv samo kad je predmet otvoren |
| UI-226 | `#billing-tip` | (bez labele — prva opcija: „Po tarifi (AKS)“) | polje | `onchange="billing_tipChange()"` | korisnik unosi/bira vrednost — (bez labele — prva opcija: „Po tarifi (AKS)“) | vidljiv samo kad je predmet otvoren |
| UI-227 | `#billing-tarifa-sel` | (bez labele — prva opcija: „-- Tarifna stavka --“) | polje | `onchange="billing_tarifaChange()"` | korisnik unosi/bira vrednost — (bez labele — prva opcija: „-- Tarifna stavka --“) | vidljiv samo kad je predmet otvoren |
| UI-228 | `#billing-opis` | placeholder: Opis radnje... | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Opis radnje... | vidljiv samo kad je predmet otvoren |
| UI-229 | `#billing-iznos` | placeholder: RSD | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: RSD | vidljiv samo kad je predmet otvoren |
| UI-230 | `button.vx-btn.vx-btn-secondary` | + Dodaj | dugme | `onclick="billing_addEntry()"` | naplata i fakturisanje | vidljiv samo kad je predmet otvoren |
| UI-231 | `button` (index.html:1442) | Ponavljajuće fakture ▼ | dugme | `onclick="billing_toggleRecurring(this)"` | naplata i fakturisanje | vidljiv samo kad je predmet otvoren |
| UI-232 | `#rec-naziv` | placeholder: Naziv šablona... | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Naziv šablona... | vidljiv samo kad je predmet otvoren |
| UI-233 | `#rec-ucestalost` | (bez labele — prva opcija: „Mesečno“) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — (bez labele — prva opcija: „Mesečno“) | vidljiv samo kad je predmet otvoren |
| UI-234 | `#rec-iznos` | placeholder: Iznos RSD | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Iznos RSD | vidljiv samo kad je predmet otvoren |
| UI-235 | `#rec-opis` | placeholder: Opis usluge... | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Opis usluge... | vidljiv samo kad je predmet otvoren |
| UI-236 | `#rec-datum` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | vidljiv samo kad je predmet otvoren |
| UI-237 | `#rec-pdv` | placeholder: PDV % | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: PDV % | vidljiv samo kad je predmet otvoren |
| UI-238 | `button.vx-btn.vx-btn-secondary` | Sačuvaj šablon | dugme | `onclick="billing_saveRecurring()"` | čuva unete podatke | vidljiv samo kad je predmet otvoren |
| UI-239 | `button.vx-btn.vx-btn-ghost` | Otkaži | dugme | `onclick="document.getElementById('recurring-form').style.display='none'"` | izvršava `document.getElementById()` | vidljiv samo kad je predmet otvoren |
| UI-240 | `#btn-new-recurring` | + Nov šablon | dugme | `onclick="billing_showRecurringForm()"` | naplata i fakturisanje | vidljiv samo kad je predmet otvoren |
| UI-241 | `a` (index.html:1475) | Finansije → | link | `onclick="setTab(document.getElementById('tab-btn-fin'),'fin')"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo kad je predmet otvoren |

### kartica predmeta → pan Komunikacija — 6 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-242 | `#pred-copilot-input` | placeholder: Napiši pitanje ili komandu… npr. Dodaj rok — ročište 20. jula | polje | `onkeydown="if((event.ctrlKey\|\|event.metaKey)&&event.key==='Enter'){pred_copilotSubmit();}"` | korisnik unosi/bira vrednost — placeholder: Napiši pitanje ili komandu… npr. Dodaj rok — ročište 20. jula | vidljiv samo kad je predmet otvoren |
| UI-243 | `#mic-pred-copilot-input` | title: Glasovni unos | dugme | `onclick="micToggle('pred-copilot-input')"` | glasovna interakcija | vidljiv samo kad je predmet otvoren |
| UI-244 | `button` (index.html:1489) | Pošalji | dugme | `onclick="pred_copilotSubmit()"` | izvršava `pred_copilotSubmit()` | vidljiv samo kad je predmet otvoren |
| UI-245 | `#pred-kom-input` | placeholder: Dodaj komentar... | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Dodaj komentar... | vidljiv samo kad je predmet otvoren |
| UI-246 | `button.kom-submit` | Pošalji | dugme | `onclick="dodajKomentar()"` | izvršava `dodajKomentar()` | vidljiv samo kad je predmet otvoren |
| UI-247 | `div` (index.html:1501) | Hearing Command Center premešten u tab Rokovi → | dugme (div) | `onclick="pred_subtabSwitch('rokovi')"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo kad je predmet otvoren |

### kartica predmeta → pan Saradnja — 3 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-248 | `#saradnja-email` | placeholder: Email adresa kolege... | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Email adresa kolege... | vidljiv samo kad je predmet otvoren |
| UI-249 | `#saradnja-uloga` | (bez labele — prva opcija: „Čitanje — samo pregled“) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — (bez labele — prva opcija: „Čitanje — samo pregled“) | vidljiv samo kad je predmet otvoren |
| UI-250 | `button` (index.html:1522) | + Dodaj saradnika | dugme | `onclick="saradnja_dodaj()"` | saradnja i kancelarija | vidljiv samo kad je predmet otvoren |

### kartica predmeta → pan Graf znanja — 2 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-251 | `button` (index.html:1551) | ↺ Osveži graf | dugme | `onclick="kg_load()"` | izvršava `kg_load()` | vidljiv samo kad je predmet otvoren |
| UI-252 | `button` (index.html:1575) | ✕ | dugme | `onclick="document.getElementById('kg-detail-panel').style.display='none'"` | izvršava `document.getElementById()` | vidljiv samo kad je predmet otvoren |

### kartica predmeta → pan AI Analiza — 25 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-253 | `#agent-launch-all-btn` | Pokreni kompletnu analizu | dugme | `onclick="this.textContent='Analiziram...';this.disabled=true;pred_launchKompletnaAnaliza();var _b=this;setTimeout(function(){_b.textContent='Pokreni komplet…"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |
| UI-254 | `#case-dna-refresh-btn` | Generiši / osveži procenu predmeta | dugme | `onclick="_voice_refresh_case_dna(activePredmetId);return false;"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |
| UI-255 | `#intel-briefing-btn` | AI Briefing — sledeći korak | dugme | `onclick="_intelBriefingLoad(activePredmetId);return false;"` | izvršava `_intelBriefingLoad()` | vidljiv samo kad je predmet otvoren |
| UI-256 | `#winning-brief-btn` | Winning Strategy Brief — sve uvide na jednom mestu | dugme | `onclick="_winningBriefLoad(activePredmetId);return false;"` | izvršava `_winningBriefLoad()` | vidljiv samo kad je predmet otvoren |
| UI-257 | `div.agent-card` | Prijem predmeta Analizira sve informacije o predmetu i daje pregled slučaja | dugme (div) | `onclick="agent_select('intake',this)"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |
| UI-258 | `div.agent-card` | Istraživanje zakona Pronalazi relevantne zakone i presude za vaš slučaj | dugme (div) | `onclick="agent_select('research',this)"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |
| UI-259 | `div.agent-card` | Pisanje podnesaka Pomaže u pisanju tužbi, žalbi i pravnih dokumenata | dugme (div) | `onclick="agent_select('drafting',this)"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |
| UI-260 | `div.agent-card` | Slabe tačke odbrane Napada vašu argumentaciju i otkriva slabosti pre suđenja | dugme (div) | `onclick="agent_select('litigation',this)"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |
| UI-261 | `div.agent-card` | Saveti o naplati Pomaže pri određivanju naknade i tumačenju AKS tarife | dugme (div) | `onclick="agent_select('billing',this)"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |
| UI-262 | `div.agent-card` | Rokovi i termini Prati procesne rokove, rokove za žalbu i ključne termine | dugme (div) | `onclick="agent_select('deadline',this)"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |
| UI-263 | `#btn-autofill-agenti` | ↺ Iz predmeta | dugme | `onclick="_predAutoFill('agent-task-input',true)"` | izvršava `_predAutoFill()` | `display:none` na samom elementu; vidljiv samo kad je predmet otvoren |
| UI-264 | `#agent-task-input` | placeholder: Opišite šta trebate... (ili izaberite analizu levo, pa unesite zadatak) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Opišite šta trebate... (ili izaberite analizu levo, pa unesite zadatak) | vidljiv samo kad je predmet otvoren |
| UI-265 | `button.vx-btn.vx-btn-primary` | ▶ Pokreni | dugme | `onclick="agent_run()"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |
| UI-266 | `button.vx-btn.vx-btn-ghost` | Kopiraj | dugme | `onclick="agent_copy()"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |
| UI-267 | `button.vx-btn.vx-btn-ghost` | + Novo | dugme | `onclick="agent_novo()"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |
| UI-268 | `#agent-para-btn` | Pokreni tri analize | dugme | `onclick="agent_run_parallel()"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |
| UI-269 | `a` (index.html:1710) | Rokovi → | link | `onclick="pred_subtabSwitch('rokovi')"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo kad je predmet otvoren |
| UI-270 | `button` (index.html:1720) | ↺ Osveži | dugme | `onclick="evidence_load()"` | izvršava `evidence_load()` | vidljiv samo kad je predmet otvoren |
| UI-271 | `button` (index.html:1727) | + Dodaj dokaz | dugme | `onclick="evidence_addDokaz()"` | izvršava `evidence_addDokaz()` | vidljiv samo kad je predmet otvoren |
| UI-272 | `button.pred-ai-tool-btn` | Analiza dokumenta | dugme | `onclick="openAITool('a')"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-273 | `button.pred-ai-tool-btn` | Sudska praksa | dugme | `onclick="openAITool('s')"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-274 | `button.pred-ai-tool-btn` | Istraživanje zakona | dugme | `onclick="openAITool('q')"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-275 | `button.pred-ai-tool-btn` | Nacrti i podnesci | dugme | `onclick="openAITool('n')"` | otvara prozor/panel | vidljiv samo kad je predmet otvoren |
| UI-276 | `#crossdoc-tool-btn` | Poređenje dokumenata | dugme | `onclick="openCrossDoc()"` | otvara prozor/panel | `display:none` na samom elementu; vidljiv samo kad je predmet otvoren |
| UI-277 | `#brain-load-btn` | Potraži slične predmete | dugme | `onclick="brain_load()"` | izvršava `brain_load()` | vidljiv samo kad je predmet otvoren |

### kartica predmeta → pan Zadaci — 6 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-278 | `button.vx-btn.vx-btn-secondary` | AI analiza | dugme | `onclick="zadaci_ai_analize()"` | pokreće AI analizu | vidljiv samo kad je predmet otvoren |
| UI-279 | `button.vx-btn.vx-btn-ghost` | ↺ | dugme | `onclick="zadaci_load(activePredmetId)"` | zadaci | vidljiv samo kad je predmet otvoren |
| UI-280 | `#zadaci-naziv` | placeholder: Naziv zadatka... | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Naziv zadatka... | vidljiv samo kad je predmet otvoren |
| UI-281 | `#zadaci-prioritet` | (bez labele — prva opcija: „Normalan prioritet“) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — (bez labele — prva opcija: „Normalan prioritet“) | vidljiv samo kad je predmet otvoren |
| UI-282 | `#zadaci-rok` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | vidljiv samo kad je predmet otvoren |
| UI-283 | `button.vx-btn.vx-btn-primary` | + Dodaj | dugme | `onclick="zadaci_kreiraj()"` | zadaci | vidljiv samo kad je predmet otvoren |

### kartica predmeta → pan Workflow — 1 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-284 | `button.vx-btn.vx-btn-ghost` | ↺ | dugme | `onclick="workflow_load(activePredmetId)"` | izvršava `workflow_load()` | vidljiv samo kad je predmet otvoren |

### kartica predmeta → pan Profitabilnost — 5 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-285 | `button` (index.html:1818) | ↺ | dugme | `onclick="profitabilnost_load(activePredmetId)"` | izvršava `profitabilnost_load()` | vidljiv samo kad je predmet otvoren |
| UI-286 | `#profit-opt-in` | (bez labele) | polje | `onchange="profitabilnost_toggleOptIn(this)"` | korisnik unosi/bira vrednost — polje bez opisa | vidljiv samo kad je predmet otvoren |
| UI-287 | `#api-kljuc-naziv` | placeholder: Naziv ključa (npr. Moja integracija) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Naziv ključa (npr. Moja integracija) | vidljiv samo kad je predmet otvoren |
| UI-288 | `button` (index.html:1870) | + Novi ključ | dugme | `onclick="kreirajApiKljuc()"` | izvršava `kreirajApiKljuc()` | vidljiv samo kad je predmet otvoren |
| UI-289 | `#push-btn` | Uključi podsetnik za rokove | dugme | `onclick="subscribePush()"` | izvršava `subscribePush()` | vidljiv samo kad je predmet otvoren |

### tab Sudska praksa (`tab-s`) — 14 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-290 | `button.t-tool-back` | ← Pravni alati | dugme | `onclick="setTab(document.getElementById('tab-btn-alati'),'alati')"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo dok je taj tab aktivan |
| UI-291 | `#praksa-query` | placeholder: Pretraga (npr. otkaz ugovora o radu) — ostavite prazno za sve odluke | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Pretraga (npr. otkaz ugovora o radu) — ostavite prazno za sve odluke | vidljiv samo dok je taj tab aktivan |
| UI-292 | `#praksa-matter` | (bez labele — prva opcija: „Sva pravna oblast“) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — (bez labele — prva opcija: „Sva pravna oblast“) | vidljiv samo dok je taj tab aktivan |
| UI-293 | `#praksa-court` | (bez labele — prva opcija: „Svi sudovi“) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — (bez labele — prva opcija: „Svi sudovi“) | vidljiv samo dok je taj tab aktivan |
| UI-294 | `#praksa-year-from` | placeholder: Od god. | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Od god. | vidljiv samo dok je taj tab aktivan |
| UI-295 | `#praksa-year-to` | placeholder: Do god. | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Do god. | vidljiv samo dok je taj tab aktivan |
| UI-296 | `#praksa-search-btn` | Pretraži sudsku praksu | dugme | `onclick="praksa_search()"` | pokreće pretragu/upit | vidljiv samo dok je taj tab aktivan |
| UI-297 | `#praksa-grupisano-btn` | Za/Protiv | dugme | `onclick="praksa_load_grupisano()"` | izvršava `praksa_load_grupisano()` | vidljiv samo dok je taj tab aktivan |
| UI-298 | `button` (index.html:1907) | Resetuj | dugme | `onclick="praksa_reset_filters()"` | prijava/registracija/nalog | vidljiv samo dok je taj tab aktivan |
| UI-299 | `#praksa-ratio-filter` | placeholder: Filtriraj po pravnom stavu... | polje | `oninput="praksa_ratio_filter_update()"` | korisnik unosi/bira vrednost — placeholder: Filtriraj po pravnom stavu... | `display:none` na samom elementu; vidljiv samo dok je taj tab aktivan |
| UI-300 | `#manual-a` | placeholder: npr. Uzp 51/2024 | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: npr. Uzp 51/2024 | vidljiv samo dok je taj tab aktivan |
| UI-301 | `#manual-b` | placeholder: npr. Rev 123/2023 | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: npr. Rev 123/2023 | vidljiv samo dok je taj tab aktivan |
| UI-302 | `button` (index.html:1917) | Uporedi | dugme | `onclick="startManualCompare()"` | upravlja tajmerom/naplatom vremena | vidljiv samo dok je taj tab aktivan |
| UI-303 | `#praksa-load-more` | Učitaj još odluka | dugme | `onclick="praksa_load_more()"` | izvršava `praksa_load_more()` | `display:none` na samom elementu; vidljiv samo dok je taj tab aktivan |

### tab Klijenti (`tab-k`) — 17 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-304 | `button.crm-add-btn` | ⚠ Konflikt | dugme | `onclick="crmCheckKonfliktOtvori()"` | otvara prozor/panel | vidljiv samo dok je taj tab aktivan |
| UI-305 | `button.crm-add-btn` | CSV | dugme | `onclick="crmCsvImportOtvori()"` | otvara prozor/panel | vidljiv samo dok je taj tab aktivan |
| UI-306 | `#crm-novi-klijent-btn` | + Novi klijent | dugme | `onclick="crmOtvoriFormu()"` | otvara prozor/panel | vidljiv samo dok je taj tab aktivan |
| UI-307 | `#crm-search-input` | placeholder: Pretraži po imenu... | polje | `onkeydown="if(event.key==='Enter')crm_pretrazi()"` | korisnik unosi/bira vrednost — placeholder: Pretraži po imenu... | vidljiv samo dok je taj tab aktivan |
| UI-308 | `button.crm-search-btn` | Traži | dugme | `onclick="crm_pretrazi()"` | pokreće pretragu/upit | vidljiv samo dok je taj tab aktivan |
| UI-309 | `button.crm-back-btn` | ← Nazad | dugme | `onclick="crmZatvoriProfil()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj tab aktivan |
| UI-310 | `button.crm-add-btn` | Uredi | dugme | `onclick="crmOtvoriFormu(crmAktivniId)"` | otvara prozor/panel | vidljiv samo dok je taj tab aktivan |
| UI-311 | `#crm-pt-podaci` | Podaci | tab | `onclick="crmProfilTab('podaci')"` | rad sa klijentima | vidljiv samo dok je taj tab aktivan |
| UI-312 | `#crm-pt-aktivni` | Aktivni predmeti | tab | `onclick="crmProfilTab('aktivni')"` | rad sa klijentima | vidljiv samo dok je taj tab aktivan |
| UI-313 | `#crm-pt-zavrseni` | Završeni | tab | `onclick="crmProfilTab('zavrseni')"` | rad sa klijentima | vidljiv samo dok je taj tab aktivan |
| UI-314 | `#crm-pt-timeline` | Hronologija | tab | `onclick="crmProfilTab('timeline')"` | rad sa klijentima | vidljiv samo dok je taj tab aktivan |
| UI-315 | `#crm-pt-dokumenti` | Dokumenti | tab | `onclick="crmProfilTab('dokumenti')"` | rad sa klijentima | vidljiv samo dok je taj tab aktivan |
| UI-316 | `#crm-pt-komunikacija` | Komunikacija | tab | `onclick="crmProfilTab('komunikacija')"` | rad sa klijentima | vidljiv samo dok je taj tab aktivan |
| UI-317 | `#crm-tarifa-input` | placeholder: Globalna satnica | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Globalna satnica | vidljiv samo dok je taj tab aktivan |
| UI-318 | `button.crm-tarifa-save-btn` | Sačuvaj | dugme | `onclick="crmSacuvajTarifu()"` | čuva unete podatke | vidljiv samo dok je taj tab aktivan |
| UI-319 | `#crm-tarifa-rm-btn` | Ukloni | dugme | `onclick="crmUkloniTarifu()"` | rad sa klijentima | vidljiv samo dok je taj tab aktivan |
| UI-320 | `#crm-reveal-btn` | Prikaži poverljive podatke | dugme | `onclick="crmOtkrijPoverljivo()"` | rad sa klijentima | vidljiv samo dok je taj tab aktivan |

### modal `crm-overlay` (klijent) — 21 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-321 | `#crm-overlay` | Novi klijent ✕ Tip klijenta Fizičko lice Pravno lice Osnovni podaci Ime * Prezime Matični  | dugme (div) | `onclick="if(event.target===this)crmConfirmClose()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-322 | `div.crm-panel` | Novi klijent ✕ Tip klijenta Fizičko lice Pravno lice Osnovni podaci Ime * Prezime Matični  | dugme (div) | `onclick="event.stopPropagation()"` | upravlja tajmerom/naplatom vremena | vidljiv samo dok je taj modal/overlay otvoren |
| UI-323 | `button.crm-panel-close` | ✕ | dugme | `onclick="crmConfirmClose()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-324 | `#crm-edit-id` | (skriveno polje — nema vidljivu labelu) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — (skriveno polje — nema vidljivu labelu) | vidljiv samo dok je taj modal/overlay otvoren |
| UI-325 | `#crm-tip-fiz` | Fizičko lice | dugme | `onclick="crmSetTip('fizicko_lice')"` | rad sa klijentima | vidljiv samo dok je taj modal/overlay otvoren |
| UI-326 | `#crm-tip-prav` | Pravno lice | dugme | `onclick="crmSetTip('pravno_lice')"` | rad sa klijentima | vidljiv samo dok je taj modal/overlay otvoren |
| UI-327 | `#crm-f-ime` | placeholder: Ime (ili naziv firme) | polje | `oninput="crmMarkDirty()"` | korisnik unosi/bira vrednost — placeholder: Ime (ili naziv firme) | vidljiv samo dok je taj modal/overlay otvoren |
| UI-328 | `#crm-f-prezime` | placeholder: Prezime | polje | `oninput="crmMarkDirty()"` | korisnik unosi/bira vrednost — placeholder: Prezime | vidljiv samo dok je taj modal/overlay otvoren |
| UI-329 | `#crm-f-mb` | placeholder: npr. 12345678 | polje | `oninput="crmMarkDirty()"` | korisnik unosi/bira vrednost — placeholder: npr. 12345678 | vidljiv samo dok je taj modal/overlay otvoren |
| UI-330 | `#crm-apr-btn` | Popuni iz APR | dugme | `onclick="crmAprAutofill()"` | rad sa klijentima | vidljiv samo dok je taj modal/overlay otvoren |
| UI-331 | `#crm-f-firma` | placeholder: Naziv firme | polje | `oninput="crmMarkDirty()"` | korisnik unosi/bira vrednost — placeholder: Naziv firme | vidljiv samo dok je taj modal/overlay otvoren |
| UI-332 | `#crm-f-email` | placeholder: email@primer.rs | polje | `oninput="crmMarkDirty()"` | korisnik unosi/bira vrednost — placeholder: email@primer.rs | vidljiv samo dok je taj modal/overlay otvoren |
| UI-333 | `#crm-f-telefon` | placeholder: +381 ... | polje | `oninput="crmMarkDirty()"` | korisnik unosi/bira vrednost — placeholder: +381 ... | vidljiv samo dok je taj modal/overlay otvoren |
| UI-334 | `#crm-f-jmbg` | placeholder: 13 cifara | polje | `oninput="crmMarkDirty();crmValidateJmbg(this)"` | korisnik unosi/bira vrednost — placeholder: 13 cifara | vidljiv samo dok je taj modal/overlay otvoren |
| UI-335 | `#crm-f-pasos` | placeholder: Broj pasoša | polje | `oninput="crmMarkDirty()"` | korisnik unosi/bira vrednost — placeholder: Broj pasoša | vidljiv samo dok je taj modal/overlay otvoren |
| UI-336 | `#crm-f-pib` | placeholder: PIB firme | polje | `oninput="crmMarkDirty()"` | korisnik unosi/bira vrednost — placeholder: PIB firme | vidljiv samo dok je taj modal/overlay otvoren |
| UI-337 | `#crm-f-adresa` | placeholder: Ulica i broj, grad | polje | `oninput="crmMarkDirty()"` | korisnik unosi/bira vrednost — placeholder: Ulica i broj, grad | vidljiv samo dok je taj modal/overlay otvoren |
| UI-338 | `#crm-f-osnov` | (bez labele — prva opcija: „Legitimni interes“) | polje | `onchange="crmMarkDirty()"` | korisnik unosi/bira vrednost — (bez labele — prva opcija: „Legitimni interes“) | vidljiv samo dok je taj modal/overlay otvoren |
| UI-339 | `#crm-f-napomena` | placeholder: Interna napomena... | polje | `oninput="crmMarkDirty()"` | korisnik unosi/bira vrednost — placeholder: Interna napomena... | vidljiv samo dok je taj modal/overlay otvoren |
| UI-340 | `button.crm-cancel-btn` | Otkaži | dugme | `onclick="crmConfirmClose()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-341 | `button.crm-save-btn` | Sačuvaj klijenta | dugme | `onclick="crmSacuvaj()"` | čuva unete podatke | vidljiv samo dok je taj modal/overlay otvoren |

### modal `crm-conflict-overlay` (provera sukoba) — 6 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-342 | `#crm-conflict-overlay` | ⚠ Provjera sukoba interesa Ime * Prezime Firma Proveri Zatvori | dugme (div) | `onclick="if(event.target===this)crmZatvoriKonflikt()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-343 | `#cf-ime` | placeholder: Ime | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Ime | vidljiv samo dok je taj modal/overlay otvoren |
| UI-344 | `#cf-prezime` | placeholder: Prezime | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Prezime | vidljiv samo dok je taj modal/overlay otvoren |
| UI-345 | `#cf-firma` | placeholder: Naziv firme | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Naziv firme | vidljiv samo dok je taj modal/overlay otvoren |
| UI-346 | `button.crm-save-btn` | Proveri | dugme | `onclick="crmPokreniKonflikt()"` | rad sa klijentima | vidljiv samo dok je taj modal/overlay otvoren |
| UI-347 | `button.crm-cancel-btn` | Zatvori | dugme | `onclick="crmZatvoriKonflikt()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |

### modal `crm-csv-overlay` (CSV uvoz) — 5 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-348 | `#crm-csv-overlay` | ⬆ Import klijenata iz CSV CSV mora imati header red sa kolonama: ime, prezime, firma, emai | dugme (div) | `onclick="if(event.target===this)crmCsvImportZatvori()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-349 | `#crm-csv-drop` | Kliknite ili prevucite CSV fajl ovde | dugme (div) | `onclick="document.getElementById('crm-csv-file').click()"` | izvršava `document.getElementById()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-350 | `#crm-csv-file` | (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | polje | `onchange="crmCsvFileSelected(this)"` | korisnik unosi/bira vrednost — (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | `display:none` na samom elementu; vidljiv samo dok je taj modal/overlay otvoren |
| UI-351 | `#crm-csv-btn` | Uvezi klijente | dugme | `onclick="crmCsvPosalji()"` | rad sa klijentima | vidljiv samo dok je taj modal/overlay otvoren |
| UI-352 | `button.crm-cancel-btn` | Zatvori | dugme | `onclick="crmCsvImportZatvori()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |

### modal `intake-overlay` (Intake Wizard) — 26 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-353 | `#intake-overlay` | Novi predmet — Intake Wiza | dugme (div) | `onclick="if(event.target===this)intakeConfirmClose()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-354 | `div.intake-panel` | Novi predmet — Intake Wizard <button class="intake-panel-close" onclick="in | dugme (div) | `onclick="event.stopPropagation()"` | upravlja tajmerom/naplatom vremena | vidljiv samo dok je taj modal/overlay otvoren |
| UI-355 | `button.intake-panel-close` | ✕ | dugme | `onclick="intakeConfirmClose()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-356 | `button` (index.html:2156) | Iz šablona | dugme | `onclick="intakeTemplateOpen()"` | otvara prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-357 | `#intake-klijent-search` | placeholder: Pretraži po imenu ili firmi... | polje | `oninput="intakeKlijentSearch(this.value)"` | korisnik unosi/bira vrednost — placeholder: Pretraži po imenu ili firmi... | vidljiv samo dok je taj modal/overlay otvoren |
| UI-358 | `button.intake-back-btn` | + Dodaj novog klijenta | dugme | `onclick="intakeNoviKlijentOpen()"` | otvara prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-359 | `#intake-opis` | placeholder: Npr: Klijent je dobio otkaz bez otkaznog roka i traženog obrazloženja. Radni odnos traj | polje | `oninput="intakeOpisChange()"` | korisnik unosi/bira vrednost — placeholder: Npr: Klijent je dobio otkaz bez otkaznog roka i traženog obrazloženja. Radni odnos traj | vidljiv samo dok je taj modal/overlay otvoren |
| UI-360 | `#intake-upload-zone` | Prevucite PDF/DOCX ili kliknite za upload Maks. 10MB — rezultati se koriste za bolji predl | dugme (div) | `onclick="document.getElementById('intake-file-input').click()"` | izvršava `document.getElementById()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-361 | `#intake-file-input` | (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | polje | `onchange="intakeUploadFile(this.files[0])"` | korisnik unosi/bira vrednost — (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | `display:none` na samom elementu; vidljiv samo dok je taj modal/overlay otvoren |
| UI-362 | `#intake-f-naziv` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | vidljiv samo dok je taj modal/overlay otvoren |
| UI-363 | `#intake-f-tip` | (bez labele — prva opcija: „Opšti“) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — (bez labele — prva opcija: „Opšti“) | vidljiv samo dok je taj modal/overlay otvoren |
| UI-364 | `#intake-f-opis` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | vidljiv samo dok je taj modal/overlay otvoren |
| UI-365 | `#intake-f-protivna` | placeholder: Npr. AD Beograd d.o.o. | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Npr. AD Beograd d.o.o. | vidljiv samo dok je taj modal/overlay otvoren |
| UI-366 | `#intake-f-vrsta` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | vidljiv samo dok je taj modal/overlay otvoren |
| UI-367 | `#intake-f-vrednost` | placeholder: Npr. 500000 RSD | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Npr. 500000 RSD | vidljiv samo dok je taj modal/overlay otvoren |
| UI-368 | `#intake-f-rok` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | vidljiv samo dok je taj modal/overlay otvoren |
| UI-369 | `#intake-f-rok-opis` | placeholder: Npr. Rok za tužbu, zastarelost | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Npr. Rok za tužbu, zastarelost | vidljiv samo dok je taj modal/overlay otvoren |
| UI-370 | `div` (index.html:2237) | Billing podešavanje (opciono) ▼ | dugme (div) | `onclick="intakeBillingToggle()"` | kreiranje novog predmeta | vidljiv samo dok je taj modal/overlay otvoren |
| UI-371 | `input` (index.html:2245) | uz kontrolu (`<label>` omotač): Fiksni honorar | polje | `onchange="intakeBillingTipChange()"` | korisnik unosi/bira vrednost — uz kontrolu (`<label>` omotač): Fiksni honorar | vidljiv samo dok je taj modal/overlay otvoren |
| UI-372 | `input` (index.html:2248) | uz kontrolu (`<label>` omotač): Po satu (tajmer startuje odmah) | polje | `onchange="intakeBillingTipChange()"` | korisnik unosi/bira vrednost — uz kontrolu (`<label>` omotač): Po satu (tajmer startuje odmah) | vidljiv samo dok je taj modal/overlay otvoren |
| UI-373 | `input` (index.html:2251) | uz kontrolu (`<label>` omotač): AKS tarifa | polje | `onchange="intakeBillingTipChange()"` | korisnik unosi/bira vrednost — uz kontrolu (`<label>` omotač): AKS tarifa | vidljiv samo dok je taj modal/overlay otvoren |
| UI-374 | `#intake-billing-iznos` | placeholder: Iznos u RSD | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Iznos u RSD | vidljiv samo dok je taj modal/overlay otvoren |
| UI-375 | `#intake-billing-aks` | vizuelna `<label>` iznad (bez `for=`): AKS tarifa | polje | `onchange="intakeBillingAksIznos()"` | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): AKS tarifa | vidljiv samo dok je taj modal/overlay otvoren |
| UI-376 | `button` (index.html:2293) | Otvori predmet → | dugme | `onclick="intakePipelineDone()"` | kreiranje novog predmeta | vidljiv samo dok je taj modal/overlay otvoren |
| UI-377 | `#intake-btn-back` | ← Nazad | dugme | `onclick="intakeBack()"` | kreiranje novog predmeta | `display:none` na samom elementu; vidljiv samo dok je taj modal/overlay otvoren |
| UI-378 | `#intake-btn-next` | Dalje → | dugme | `onclick="intakeNext()"` | kreiranje novog predmeta | vidljiv samo dok je taj modal/overlay otvoren |

### modal `si-overlay` (Novi predmet iz dokumenta) — 34 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-379 | `#si-overlay` | Novi predmet — iz dokumenta ✕ Korak 1 / 3 — Otpremanje Otpremite dokumenta predmeta Prevuc | dugme (div) | `onclick="if(event.target===this)siConfirmClose()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-380 | `div.intake-panel` | Novi predmet — iz dokumenta ✕ Korak 1 / 3 — Otpremanje Otpremite dokumenta predmeta Prevuc | dugme (div) | `onclick="event.stopPropagation()"` | upravlja tajmerom/naplatom vremena | vidljiv samo dok je taj modal/overlay otvoren |
| UI-381 | `button.intake-panel-close` | ✕ | dugme | `onclick="siConfirmClose()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-382 | `#si-upload-zone` | Prevucite PDF, DOCX, TXT ili fotografije (JPG/PNG), ili kliknite za upload Više fajlova od | dugme (div) | `onclick="document.getElementById('si-file-input').click()"` | izvršava `document.getElementById()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-383 | `#si-file-input` | (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | polje | `onchange="siFilesSelected(this.files)"` | korisnik unosi/bira vrednost — (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | `display:none` na samom elementu; vidljiv samo dok je taj modal/overlay otvoren |
| UI-384 | `#si-btn-back` | ← Nazad | dugme | `onclick="siBack()"` | kreiranje novog predmeta | `display:none` na samom elementu; vidljiv samo dok je taj modal/overlay otvoren |
| UI-385 | `#si-btn-next` | Dalje → | dugme | `onclick="siNext()"` | kreiranje novog predmeta | vidljiv samo dok je taj modal/overlay otvoren |
| UI-386 | `#qi-overlay` | Hitan predmet ✕ Brzo kreiranje bez analize — popunite minimum podataka. Klijent * Naziv pr | dugme (div) | `onclick="if(event.target===this)qiZatvori()"` | zatvara otvoreni prozor/panel | `display:none` na samom elementu; vidljiv samo dok je taj modal/overlay otvoren |
| UI-387 | `div` (index.html:2356) | Hitan predmet ✕ Brzo kreiranje bez analize — popunite minimum podataka. Klijent * Naziv pr | dugme (div) | `onclick="event.stopPropagation()"` | upravlja tajmerom/naplatom vremena | vidljiv samo dok je taj modal/overlay otvoren |
| UI-388 | `button` (index.html:2359) | ✕ | dugme | `onclick="qiZatvori()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-389 | `#qi-klijent-search` | placeholder: Pretraži po imenu... | polje | `oninput="qiKlijentSearch(this.value)"` | korisnik unosi/bira vrednost — placeholder: Pretraži po imenu... | vidljiv samo dok je taj modal/overlay otvoren |
| UI-390 | `#qi-naziv` | placeholder: Npr. Radni spor — Jovanović vs. Firma | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Npr. Radni spor — Jovanović vs. Firma | vidljiv samo dok je taj modal/overlay otvoren |
| UI-391 | `#qi-tip` | (bez labele — prva opcija: „Opšti“) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — (bez labele — prva opcija: „Opšti“) | vidljiv samo dok je taj modal/overlay otvoren |
| UI-392 | `#qi-btn` | Kreiraj predmet → | dugme | `onclick="qiKreiraj()"` | izvršava `qiKreiraj()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-393 | `#bulk-overlay` | Uvezi predmete iz CSV-a ✕ Prihvatamo .csv fajl sa sledećim kolonama: ime, prezime, firma,  | dugme (div) | `onclick="if(event.target===this)bulkZatvori()"` | zatvara otvoreni prozor/panel | `display:none` na samom elementu; vidljiv samo dok je taj modal/overlay otvoren |
| UI-394 | `div` (index.html:2385) | Uvezi predmete iz CSV-a ✕ Prihvatamo .csv fajl sa sledećim kolonama: ime, prezime, firma,  | dugme (div) | `onclick="event.stopPropagation()"` | upravlja tajmerom/naplatom vremena | vidljiv samo dok je taj modal/overlay otvoren |
| UI-395 | `button` (index.html:2388) | ✕ | dugme | `onclick="bulkZatvori()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-396 | `#bulk-upload-zone` | Kliknite ili prevucite CSV fajl Maks. 500 redova | dugme (div) | `onclick="document.getElementById('bulk-file-input').click()"` | izvršava `document.getElementById()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-397 | `#bulk-file-input` | (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | polje | `onchange="bulkParseFile(this.files[0])"` | korisnik unosi/bira vrednost — (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | `display:none` na samom elementu; vidljiv samo dok je taj modal/overlay otvoren |
| UI-398 | `button` (index.html:2408) | ← Novi fajl | dugme | `onclick="bulkResetUpload()"` | otprema dokument | vidljiv samo dok je taj modal/overlay otvoren |
| UI-399 | `button` (index.html:2421) | Zatvori | dugme | `onclick="bulkZatvori()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-400 | `#bulk-import-btn` | Uvezi sve | dugme | `onclick="bulkImportuj()"` | izvršava `bulkImportuj()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-401 | `div` (index.html:2429) | Vindex AI Pravni operativni sistem Dobrodošli! Spremni ste za rad. Pratite tri koraka i Vi | dugme (div) | `onclick="event.stopPropagation()"` | upravlja tajmerom/naplatom vremena | vidljiv samo dok je taj modal/overlay otvoren |
| UI-402 | `#ob-step-1` | Dodajte prvog klijenta Ime, kontakt, tip — 30 sekundi | dugme (div) | `onclick="onboardingStep(1)"` | izvršava `onboardingStep()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-403 | `#ob-step-2` | Otvorite prvi predmet Intake Wizard — automatska ekstrakcija podataka | dugme (div) | `onclick="onboardingStep(2)"` | izvršava `onboardingStep()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-404 | `#ob-step-3` | Postavite pravno pitanje 847 zakona RS + 12.604 presuda — odgovor za &lt;10 sek | dugme (div) | `onclick="onboardingStep(3)"` | izvršava `onboardingStep()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-405 | `button` (index.html:2495) | Preskoči za sada | dugme | `onclick="onboardingDismiss()"` | izvršava `onboardingDismiss()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-406 | `button` (index.html:2496) | Počnimo → | dugme | `onclick="onboardingStep(1)"` | izvršava `onboardingStep()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-407 | `#intake-tpl-overlay` | Šabloni predmeta ✕ Izaberite šablon — predmet se kreira sa predefinisanom hronologijom i p | dugme (div) | `onclick="if(event.target===this)intakeTemplateClose()"` | zatvara otvoreni prozor/panel | `display:none` na samom elementu; vidljiv samo dok je taj modal/overlay otvoren |
| UI-408 | `div` (index.html:2503) | Šabloni predmeta ✕ Izaberite šablon — predmet se kreira sa predefinisanom hronologijom i p | dugme (div) | `onclick="event.stopPropagation()"` | upravlja tajmerom/naplatom vremena | vidljiv samo dok je taj modal/overlay otvoren |
| UI-409 | `button` (index.html:2506) | ✕ | dugme | `onclick="intakeTemplateClose()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-410 | `#dok-preview-overlay` | ✕ Učitavam dokument... Tekst dokumenta nije dostupan — dokument je možda istekao (čuva se  | dugme (div) | `onclick="if(event.target===this)dokPreviewClose()"` | zatvara otvoreni prozor/panel | `display:none` na samom elementu; vidljiv samo dok je taj modal/overlay otvoren |
| UI-411 | `div` (index.html:2515) | ✕ Učitavam dokument... Tekst dokumenta nije dostupan — dokument je možda istekao (čuva se  | dugme (div) | `onclick="event.stopPropagation()"` | upravlja tajmerom/naplatom vremena | vidljiv samo dok je taj modal/overlay otvoren |
| UI-412 | `button` (index.html:2524) | ✕ | dugme | `onclick="dokPreviewClose()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |

### modal `doctpl-overlay` (šabloni dokumenata) — 9 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-413 | `#doctpl-overlay` | Šabloni dokumenata Generiši pravni akt automatski — tužbe, ugovori, punomoćja ✕ ⌕ Esc Saču | dugme (div) | `onclick="if(event.target===this)docTplClose()"` | zatvara otvoreni prozor/panel | `display:none` na samom elementu; vidljiv samo dok je taj modal/overlay otvoren |
| UI-414 | `div.vx-modal.vx-modal-palette` | Šabloni dokumenata Generiši pravni akt automatski — tužbe, ugovori, punomoćja ✕ ⌕ Esc Saču | dugme (div) | `onclick="event.stopPropagation()"` | upravlja tajmerom/naplatom vremena | vidljiv samo dok je taj modal/overlay otvoren |
| UI-415 | `button` (index.html:2547) | ✕ | dugme | `onclick="docTplClose()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-416 | `#doctpl-search` | placeholder: Pretraži šablone… | polje | `oninput="docTplFilter(this.value)"` + `onkeydown="if(event.key==='Escape')docTplClose()"` | korisnik unosi/bira vrednost — placeholder: Pretraži šablone… | vidljiv samo dok je taj modal/overlay otvoren |
| UI-417 | `#doctpl-predmet-id` | vizuelna `<label>` iznad (bez `for=`): Sačuvaj uz predmet (opciono) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Sačuvaj uz predmet (opciono) | vidljiv samo dok je taj modal/overlay otvoren |
| UI-418 | `#doctpl-gen-btn` | Generiši dokument | dugme | `onclick="docTplGeneriši()"` | izvršava `docTplGeneriši()` | `display:none` na samom elementu; vidljiv samo dok je taj modal/overlay otvoren |
| UI-419 | `button.vx-btn.vx-btn-ghost` | Kopiraj | dugme | `onclick="docTplKopiraj()"` | kopira tekst u ostavu | vidljiv samo dok je taj modal/overlay otvoren |
| UI-420 | `button.vx-btn.vx-btn-ghost` | Sačuvaj uz predmet | dugme | `onclick="docTplSacuvaj()"` | čuva unete podatke | vidljiv samo dok je taj modal/overlay otvoren |
| UI-421 | `#doctpl-result-txt` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | vidljiv samo dok je taj modal/overlay otvoren |

### tab Zadaci (`tab-zadaci-g`) — 1 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-422 | `button.vx-btn.vx-btn-ghost` | ↺ | dugme | `onclick="zadaci_g_load()"` | zadaci | vidljiv samo dok je taj tab aktivan |

### tab Finansije (`tab-fin`) — 9 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-423 | `button.vx-btn.vx-btn-secondary` | Mesečni izveštaj | dugme | `onclick="mesecniIzvestajOtvori()"` | otvara prozor/panel | vidljiv samo dok je taj tab aktivan |
| UI-424 | `button.vx-btn.vx-btn-ghost` | ↺ | dugme | `onclick="finLoad()"` | izvršava `finLoad()` | vidljiv samo dok je taj tab aktivan |
| UI-425 | `button.vx-btn.vx-btn-ghost` | ↻ | dugme | `onclick="billingDugovanjaLoad()"` | naplata i fakturisanje | vidljiv samo dok je taj tab aktivan |
| UI-426 | `button` (index.html:2651) | Detaljni izveštaji ▼ | dugme | `onclick="billing_toggleReports(this)"` | naplata i fakturisanje | vidljiv samo dok je taj tab aktivan |
| UI-427 | `button.billing-report-btn` | Godišnji | dugme | `onclick="billing_openReport('godisnji')"` | otvara prozor/panel | vidljiv samo dok je taj tab aktivan |
| UI-428 | `button.billing-report-btn` | ⏱ Starele stavke | dugme | `onclick="billing_openReport('zastarele')"` | otvara prozor/panel | vidljiv samo dok je taj tab aktivan |
| UI-429 | `button.billing-report-btn` | Po tipu predmeta | dugme | `onclick="billing_openReport('po-tipu')"` | otvara prozor/panel | vidljiv samo dok je taj tab aktivan |
| UI-430 | `button.billing-report-btn` | Po klijentu | dugme | `onclick="billing_openReport('po-klijentu')"` | otvara prozor/panel | vidljiv samo dok je taj tab aktivan |
| UI-431 | `button.billing-report-btn` | ⬇ Preuzmi CSV | dugme | `onclick="billing_csvDownload()"` | izvozi/preuzima dokument | vidljiv samo dok je taj tab aktivan |

### tab Kancelarija (`tab-kanc`) — 10 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-432 | `button.vx-btn.vx-btn-ghost` | ↺ | dugme | `onclick="kancelarijaLoad()"` | saradnja i kancelarija | vidljiv samo dok je taj tab aktivan |
| UI-433 | `#kancelarija-new-naziv` | placeholder: Naziv kancelarije | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Naziv kancelarije | vidljiv samo dok je taj tab aktivan |
| UI-434 | `button.settings-btn` | Kreiraj | dugme | `onclick="kancelarijaKreiraj()"` | saradnja i kancelarija | vidljiv samo dok je taj tab aktivan |
| UI-435 | `button.settings-btn` | Prihvati pozivnicu | dugme | `onclick="kancPrihvati()"` | saradnja i kancelarija | vidljiv samo dok je taj tab aktivan |
| UI-436 | `button.settings-btn` | Odbij | dugme | `onclick="kancOdbij()"` | saradnja i kancelarija | vidljiv samo dok je taj tab aktivan |
| UI-437 | `button.settings-btn` | Preimenuj | dugme | `onclick="kancRename()"` | saradnja i kancelarija | vidljiv samo dok je taj tab aktivan |
| UI-438 | `#kancelarija-invite-email` | placeholder: email@kancelarija.rs | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: email@kancelarija.rs | vidljiv samo dok je taj tab aktivan |
| UI-439 | `#kancelarija-invite-uloga` | (bez labele — prva opcija: „Partner“) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — (bez labele — prva opcija: „Partner“) | vidljiv samo dok je taj tab aktivan |
| UI-440 | `button.settings-btn` | Pošalji | dugme | `onclick="kancPozovi()"` | saradnja i kancelarija | vidljiv samo dok je taj tab aktivan |
| UI-441 | `button.settings-btn` | Napusti firmu | dugme | `onclick="kancOstavi()"` | saradnja i kancelarija | vidljiv samo dok je taj tab aktivan |

### tab Kalendar/Rokovi (`tab-kal`) — 10 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-442 | `#kal-view-grid-btn` | Mesec | dugme | `onclick="kalSetView('grid')"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo dok je taj tab aktivan |
| UI-443 | `#kal-view-list-btn` | Lista | dugme | `onclick="kalSetView('list')"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo dok je taj tab aktivan |
| UI-444 | `button.kal-ics-btn` | ⬇ .ics | dugme | `onclick="kalendarIcsExport()"` | izvozi/preuzima dokument | vidljiv samo dok je taj tab aktivan |
| UI-445 | `button.kal-ics-btn` | Google | dugme | `onclick="kalendarGoogleExport()"` | izvozi/preuzima dokument | vidljiv samo dok je taj tab aktivan |
| UI-446 | `button.kal-ics-btn` | Outlook | dugme | `onclick="kalendarOutlookExport()"` | izvozi/preuzima dokument | vidljiv samo dok je taj tab aktivan |
| UI-447 | `button.kal-dodaj-btn` | + Ročište | dugme | `onclick="rocisteOtvoriFormu()"` | otvara prozor/panel | vidljiv samo dok je taj tab aktivan |
| UI-448 | `button` (index.html:2790) | ‹ | dugme | `onclick="kalMesecPrev()"` | rokovi i ročišta | vidljiv samo dok je taj tab aktivan |
| UI-449 | `button` (index.html:2792) | › | dugme | `onclick="kalMesecNext()"` | rokovi i ročišta | vidljiv samo dok je taj tab aktivan |
| UI-450 | `button` (index.html:2793) | Danas | dugme | `onclick="kalMesecToday()"` | rokovi i ročišta | vidljiv samo dok je taj tab aktivan |
| UI-451 | `button` (index.html:2799) | ✕ | dugme | `onclick="document.getElementById('kal-day-detail').style.display='none';"` | izvršava `document.getElementById()` | vidljiv samo dok je taj tab aktivan |

### tab Poslovna inteligencija (`tab-pi`) — 1 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-452 | `button.pi-reload-btn` | Osveži | dugme | `onclick="piLoad()"` | izvršava `piLoad()` | vidljiv samo dok je taj tab aktivan |

### tab AI radni prostor (`tab-aiws`) — 126 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-453 | `button.vx-pill.is-active` | Istraživanje zakona | dugme | `onclick="aiwsSetMode('zakon',this)"` | izvršava `aiwsSetMode()` | vidljiv samo dok je taj tab aktivan |
| UI-454 | `button.vx-pill` | Analiza dokumenta | dugme | `onclick="aiwsSetMode('analiza',this)"` | izvršava `aiwsSetMode()` | vidljiv samo dok je taj tab aktivan |
| UI-455 | `button.vx-pill` | Nacrti podnesaka | dugme | `onclick="aiwsSetMode('nacrti',this)"` | izvršava `aiwsSetMode()` | vidljiv samo dok je taj tab aktivan |
| UI-456 | `button.vx-pill` | Strategija | dugme | `onclick="aiwsSetMode('strategija',this)"` | izvršava `aiwsSetMode()` | vidljiv samo dok je taj tab aktivan |
| UI-457 | `button.vx-pill` | Pravne oblasti | dugme | `onclick="aiwsSetMode('oblasti',this)"` | izvršava `aiwsSetMode()` | vidljiv samo dok je taj tab aktivan |
| UI-458 | `button.vx-pill` | Litigation Intelligence | dugme | `onclick="aiwsSetMode('litigation',this)"` | izvršava `aiwsSetMode()` | vidljiv samo dok je taj tab aktivan |
| UI-459 | `#aiws-pill-dim` | Vindex AI - Digitalna imovina & usklađenost | dugme | `onclick="aiwsSetMode('digitalna_imovina',this)"` | izvršava `aiwsSetMode()` | `display:none` na samom elementu; vidljiv samo dok je taj tab aktivan |
| UI-460 | `span.t-chip` | Nematerijalna šteta | dugme (span) | `onclick="fillQ('Naknada nematerijalne štete')"` | izvršava `fillQ()` | vidljiv samo dok je taj tab aktivan |
| UI-461 | `span.t-chip` | Otkaz radnog odnosa | dugme (span) | `onclick="fillQ('Uslovi za otkaz ugovora o radu')"` | izvršava `fillQ()` | vidljiv samo dok je taj tab aktivan |
| UI-462 | `span.t-chip` | Razvod i starateljstvo | dugme (span) | `onclick="fillQ('Razvod braka i starateljstvo nad detetom')"` | izvršava `fillQ()` | vidljiv samo dok je taj tab aktivan |
| UI-463 | `span.t-chip` | Zastarelost | dugme (span) | `onclick="fillQ('Zastarelost potraživanja naknade štete')"` | izvršava `fillQ()` | vidljiv samo dok je taj tab aktivan |
| UI-464 | `#qi` | placeholder: Npr. Koji su uslovi za naknadu nematerijalne štete? | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Npr. Koji su uslovi za naknadu nematerijalne štete? | vidljiv samo dok je taj tab aktivan |
| UI-465 | `#mic-qi` | title: Glasovni unos — kliknite da diktirate (sr-RS) | dugme | `onclick="micToggle('qi')"` | glasovna interakcija | vidljiv samo dok je taj tab aktivan |
| UI-466 | `#interni-naslov` | placeholder: Naslov stava (npr. 'Tumačenje čl. 179 ZR — otpremnina') | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Naslov stava (npr. 'Tumačenje čl. 179 ZR — otpremnina') | vidljiv samo dok je taj tab aktivan |
| UI-467 | `#interni-tekst` | placeholder: Tekst internog pravnog stava ili argumenta... | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Tekst internog pravnog stava ili argumenta... | vidljiv samo dok je taj tab aktivan |
| UI-468 | `button.interni-submit-btn` | + Dodaj stav | dugme | `onclick="dodajInterniStav()"` | izvršava `dodajInterniStav()` | vidljiv samo dok je taj tab aktivan |
| UI-469 | `#interni-upit` | placeholder: Pretražite interne stavove... | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Pretražite interne stavove... | vidljiv samo dok je taj tab aktivan |
| UI-470 | `button.interni-search-btn` | Pretraži | dugme | `onclick="pretraziInterneStavove()"` | pokreće pretragu/upit | vidljiv samo dok je taj tab aktivan |
| UI-471 | `button.btn-danger-small.interni-del-btn` | Obriši sve stavove | dugme | `onclick="obrisiSveInterneStavove()"` | briše stavku | vidljiv samo dok je taj tab aktivan |
| UI-472 | `button.strat-btn.active` | Krivično pravo | dugme | `onclick="oblastiIzaberiOblast('krivicno',this)"` | izvršava `oblastiIzaberiOblast()` | vidljiv samo dok je taj tab aktivan |
| UI-473 | `button.strat-btn` | Privredno pravo | dugme | `onclick="oblastiIzaberiOblast('privredno',this)"` | izvršava `oblastiIzaberiOblast()` | vidljiv samo dok je taj tab aktivan |
| UI-474 | `button.strat-btn` | Radno pravo | dugme | `onclick="oblastiIzaberiOblast('radno',this)"` | izvršava `oblastiIzaberiOblast()` | vidljiv samo dok je taj tab aktivan |
| UI-475 | `#ob-tekst` | placeholder: npr. Koja je kazna za krađu? Koji su uslovi za uslovnu osudu? | polje | `oninput="document.getElementById('ob-chars').textContent=this.value.length"` | korisnik unosi/bira vrednost — placeholder: npr. Koja je kazna za krađu? Koji su uslovi za uslovnu osudu? | vidljiv samo dok je taj tab aktivan |
| UI-476 | `#ob-submit-btn` | Postavi pitanje | dugme | `onclick="oblastiPokreni()"` | izvršava `oblastiPokreni()` | vidljiv samo dok je taj tab aktivan |
| UI-477 | `button.web3-copy-btn` | Kopiraj | dugme | `onclick="oblastiKopiraj()"` | kopira tekst u ostavu | vidljiv samo dok je taj tab aktivan |
| UI-478 | `#doc-upload-input` | (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | polje | `onchange="doc_upload_file(this.files[0])"` | korisnik unosi/bira vrednost — (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | `display:none` na samom elementu; vidljiv samo dok je taj tab aktivan |
| UI-479 | `#doc-upload-zone` | Prevucite ugovor ovde ili kliknite za odabir Podržani formati: PDF, DOCX (do 25MB) | dugme (div) | `onclick="doc_upload_trigger()"` | otprema dokument | vidljiv samo dok je taj tab aktivan |
| UI-480 | `button.doc-remove-btn` | ✕ Ukloni | dugme | `onclick="doc_clear_session()"` | izvršava `doc_clear_session()` | vidljiv samo dok je taj tab aktivan |
| UI-481 | `#aq` | placeholder: Npr. Da li postoji rizik od raskida ugovora? | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Npr. Da li postoji rizik od raskida ugovora? | vidljiv samo dok je taj tab aktivan |
| UI-482 | `#aitxt` | vizuelna `<label>` iznad (bez `for=`): Postavite pitanje o ovom dokumentu: | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Postavite pitanje o ovom dokumentu: | `display:none` na samom elementu; vidljiv samo dok je taj tab aktivan |
| UI-483 | `#rok-datum-doc` | placeholder: DD.MM.YYYY | polje | `oninput="doc_rokovi_recalc()"` | korisnik unosi/bira vrednost — placeholder: DD.MM.YYYY | vidljiv samo dok je taj tab aktivan |
| UI-484 | `button.rokovi-btn` | Prikaži rokove | dugme | `onclick="doc_prikaži_rokove(this)"` | rokovi i ročišta | vidljiv samo dok je taj tab aktivan |
| UI-485 | `#btn-ics-all` | Izvezi sve rokove (.ics) | dugme | `onclick="sviRokoviUKalendar()"` | rokovi i ročišta | `display:none` na samom elementu; vidljiv samo dok je taj tab aktivan |
| UI-486 | `#forensic-audit-btn` | Forenzička analiza dokumenta | dugme | `onclick="doc_forensic_audit()"` | izvršava `doc_forensic_audit()` | vidljiv samo dok je taj tab aktivan |
| UI-487 | `button.zast-toggle` | ⏳ Kalkulator zastarelosti | dugme | `onclick="zastToggle(this)"` | prikazuje ili sakriva deo ekrana | vidljiv samo dok je taj tab aktivan |
| UI-488 | `#zast-tip` | vizuelna `<label>` iznad (bez `for=`): Tip potraživanja | polje | `onchange="zastTipChange(this)"` | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Tip potraživanja | vidljiv samo dok je taj tab aktivan |
| UI-489 | `#zast-datum` | placeholder: 01.01.2024 | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: 01.01.2024 | vidljiv samo dok je taj tab aktivan |
| UI-490 | `button.zast-btn` | Izračunaj | dugme | `onclick="kalkulisiZastarelost()"` | rokovi i ročišta | vidljiv samo dok je taj tab aktivan |
| UI-491 | `#podnesak-tip` | (skriveno polje — nema vidljivu labelu) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — (skriveno polje — nema vidljivu labelu) | vidljiv samo dok je taj tab aktivan |
| UI-492 | `button.podnesak-option.selected` | Tužba za naknadu štete | dugme | `onclick="_selectPodnesakOption('tuzba_naknada_stete')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-493 | `button.podnesak-option` | Tužba — radni spor | dugme | `onclick="_selectPodnesakOption('tuzba_radni_spor')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-494 | `button.podnesak-option` | Tužba za razvod braka | dugme | `onclick="_selectPodnesakOption('tuzba_razvod')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-495 | `button.podnesak-option` | Žalba na presudu (parnica) | dugme | `onclick="_selectPodnesakOption('zalba_parnicna')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-496 | `button.podnesak-option` | Žalba na presudu (nacrt) | dugme | `onclick="_selectPodnesakOption('zalba_na_presudu')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-497 | `button.podnesak-option` | Žalba na rešenje | dugme | `onclick="_selectPodnesakOption('zalba_na_resenje')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-498 | `button.podnesak-option` | Odgovor na tužbu | dugme | `onclick="_selectPodnesakOption('odgovor_na_tuzbu')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-499 | `button.podnesak-option` | Prigovor na platni nalog | dugme | `onclick="_selectPodnesakOption('prigovor_platni_nalog')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-500 | `button.podnesak-option` | Prigovor na rešenje o izvršenju | dugme | `onclick="_selectPodnesakOption('prigovor_izvrsenje')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-501 | `button.podnesak-option` | Predlog za privremenu meru | dugme | `onclick="_selectPodnesakOption('predlog_privremena_mera')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-502 | `button.podnesak-option` | Predlog za izvršenje | dugme | `onclick="_selectPodnesakOption('predlog_izvrsenje')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-503 | `button.podnesak-option` | Urgencija sudu | dugme | `onclick="_selectPodnesakOption('urgencija_sudu')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-504 | `button.podnesak-option` | Krivična prijava | dugme | `onclick="_selectPodnesakOption('krivicna_prijava')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-505 | `button.podnesak-option` | Žalba na presudu (krivična) | dugme | `onclick="_selectPodnesakOption('zalba_krivicna')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-506 | `button.podnesak-option` | Opomena pre tužbe | dugme | `onclick="_selectPodnesakOption('opomena_duznik')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-507 | `button.podnesak-option` | Zahtev zaposlenog poslodavcu | dugme | `onclick="_selectPodnesakOption('zahtev_poslodavcu')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-508 | `button.podnesak-option` | Obaveštenje o otkazu ugovora | dugme | `onclick="_selectPodnesakOption('obaveštenje_o_otkazu')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-509 | `button.podnesak-option` | Ugovor o radu — neodređeno vreme | dugme | `onclick="_selectPodnesakOption('ugovor_neodredjeno')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-510 | `button.podnesak-option` | Ugovor o radu — određeno vreme | dugme | `onclick="_selectPodnesakOption('ugovor_odredjeno')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-511 | `button.podnesak-option` | Aneks ugovora o radu | dugme | `onclick="_selectPodnesakOption('aneks')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-512 | `button.podnesak-option` | Sporazumni raskid radnog odnosa | dugme | `onclick="_selectPodnesakOption('sporazumni_raskid')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-513 | `button.podnesak-option` | Ugovor o kupoprodaji | dugme | `onclick="_selectPodnesakOption('ugovor_kupoprodaja')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-514 | `button.podnesak-option` | Ugovor o zakupu nepokretnosti | dugme | `onclick="_selectPodnesakOption('ugovor_zakup')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-515 | `button.podnesak-option` | Punomoćje | dugme | `onclick="_selectPodnesakOption('punomocje')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-516 | `#podnesak-sud-input` | placeholder: Pretražite sud ili ukucajte naziv... | polje | `oninput="_sud_filter(this.value)"` | korisnik unosi/bira vrednost — placeholder: Pretražite sud ili ukucajte naziv... | vidljiv samo dok je taj tab aktivan |
| UI-517 | `#podnesak-sud-naziv` | vizuelna `<label>` iznad (bez `for=`): Sud: | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Sud: | vidljiv samo dok je taj tab aktivan |
| UI-518 | `#podnesak-sud-adresa` | vizuelna `<label>` iznad (bez `for=`): Sud: | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Sud: | vidljiv samo dok je taj tab aktivan |
| UI-519 | `#btn-autofill-podnesak` | ↺ Iz predmeta | dugme | `onclick="_predAutoFill('podnesak-opis',true)"` | izvršava `_predAutoFill()` | `display:none` na samom elementu; vidljiv samo dok je taj tab aktivan |
| UI-520 | `#podnesak-opis` | placeholder: Npr. Tužilac Petar Petrović, ul. Vojvode Mišića 5, Beograd traži naknadu štete od tužen | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Npr. Tužilac Petar Petrović, ul. Vojvode Mišića 5, Beograd traži naknadu štete od tužen | vidljiv samo dok je taj tab aktivan |
| UI-521 | `#mic-podnesak-opis` | title: Glasovni unos — diktirajte opis slučaja (sr-RS) | dugme | `onclick="micToggle('podnesak-opis')"` | glasovna interakcija | vidljiv samo dok je taj tab aktivan |
| UI-522 | `span.podnesak-chip` | Tužba — saobraćajna nezgoda | dugme (span) | `onclick="fillPodnesakPrimer('tuzba')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-523 | `span.podnesak-chip` | Žalba — odbijen zahtev | dugme (span) | `onclick="fillPodnesakPrimer('zalba')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-524 | `span.podnesak-chip` | Izvršenje — neplaćen dug | dugme (span) | `onclick="fillPodnesakPrimer('izvrsenje')"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-525 | `#playbook-file-input` | (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | polje | `onchange="playbookUploadFajlove(this.files)"` | korisnik unosi/bira vrednost — (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | `display:none` na samom elementu; vidljiv samo dok je taj tab aktivan |
| UI-526 | `div` (index.html:3074) | Prevucite fajlove ovde ili kliknite za izbor PDF, DOCX, TXT — max 2MB po fajlu | dugme (div) | `onclick="document.getElementById('playbook-file-input').click()"` | izvršava `document.getElementById()` | vidljiv samo dok je taj tab aktivan |
| UI-527 | `button.playbook-akcija-btn` | Osveži | dugme | `onclick="ucitajPlaybookStatus()"` | izvršava `ucitajPlaybookStatus()` | vidljiv samo dok je taj tab aktivan |
| UI-528 | `button.btn-danger-small` | Obriši sve | dugme | `onclick="obrisiSvPlaybook()"` | briše stavku | vidljiv samo dok je taj tab aktivan |
| UI-529 | `button.strat-btn.active` | Crveni tim | dugme | `onclick="stratIzaberiModul('red_team',this)"` | pokreće AI analizu | vidljiv samo dok je taj tab aktivan |
| UI-530 | `button.strat-btn` | Simulator parnice | dugme | `onclick="stratIzaberiModul('litigation',this)"` | pokreće AI analizu | vidljiv samo dok je taj tab aktivan |
| UI-531 | `button.strat-btn` | Procena ishoda | dugme | `onclick="stratIzaberiModul('sudija',this)"` | pokreće AI analizu | vidljiv samo dok je taj tab aktivan |
| UI-532 | `button.strat-btn` | Analiza rizika | dugme | `onclick="stratIzaberiModul('due_diligence',this)"` | pokreće AI analizu | vidljiv samo dok je taj tab aktivan |
| UI-533 | `button.strat-btn` | Pravni Revizor | dugme | `onclick="stratIzaberiModul('revizor',this)"` | pokreće AI analizu | vidljiv samo dok je taj tab aktivan |
| UI-534 | `button.strat-btn` | Analizator svedoka | dugme | `onclick="stratIzaberiModul('witness',this)"` | pokreće AI analizu | vidljiv samo dok je taj tab aktivan |
| UI-535 | `button.strat-btn` | Sudija v2 — Debata | dugme | `onclick="stratIzaberiModul('sudija_v2',this)"` | pokreće AI analizu | vidljiv samo dok je taj tab aktivan |
| UI-536 | `button.strat-btn` | Predikcija ishoda | dugme | `onclick="stratIzaberiModul('court_predictor',this)"` | pokreće AI analizu | vidljiv samo dok je taj tab aktivan |
| UI-537 | `#btn-autofill-strat` | ↺ Iz predmeta | dugme | `onclick="_predAutoFill('strat-tekst',true)"` | izvršava `_predAutoFill()` | `display:none` na samom elementu; vidljiv samo dok je taj tab aktivan |
| UI-538 | `#strat-tip-postupka` | vizuelna `<label>` iznad (bez `for=`): Tip postupka | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): Tip postupka | vidljiv samo dok je taj tab aktivan |
| UI-539 | `#strat-tekst` | placeholder: Unesite detaljan opis predmeta ili tekst dokumenta... | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Unesite detaljan opis predmeta ili tekst dokumenta... | vidljiv samo dok je taj tab aktivan |
| UI-540 | `#strat-submit-btn` | Pokreni analizu | dugme | `onclick="stratPokreni()"` | pokreće AI analizu | vidljiv samo dok je taj tab aktivan |
| UI-541 | `#strat-ork-btn` | Pokreni kompletnu analizu (6 kredita) | dugme | `onclick="stratOrkestratorPokreni()"` | pokreće AI analizu | vidljiv samo dok je taj tab aktivan |
| UI-542 | `button.btn-word` | Word | dugme | `onclick="exportujKaoWord(document.getElementById('strat-rezultat-naslov').textContent,document.getElementById('strat-rezultat-body').innerText,'strategija')"` | izvozi/preuzima dokument | vidljiv samo dok je taj tab aktivan |
| UI-543 | `button.strat-copy-btn` | Kopiraj | dugme | `onclick="stratKopiraj()"` | pokreće AI analizu | vidljiv samo dok je taj tab aktivan |
| UI-544 | `#lit-brain-load-btn` | Potraži slične predmete | dugme | `onclick="litIntelBrainLoad()"` | izvršava `litIntelBrainLoad()` | vidljiv samo dok je taj tab aktivan |
| UI-545 | `#lit-outcome-load-btn` | Prikaži trendove | dugme | `onclick="litIntelOutcomeShow()"` | prikazuje ili sakriva deo ekrana | vidljiv samo dok je taj tab aktivan |
| UI-546 | `#strat-judge-sud` | placeholder: Naziv suda (obavezno) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Naziv suda (obavezno) | vidljiv samo dok je taj tab aktivan |
| UI-547 | `#strat-judge-ime` | placeholder: Ime sudije (opciono) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Ime sudije (opciono) | vidljiv samo dok je taj tab aktivan |
| UI-548 | `button` (index.html:3183) | Profiliši | dugme | `onclick="stratJudgeProfile()"` | pokreće AI analizu | vidljiv samo dok je taj tab aktivan |
| UI-549 | `#strat-opponent-naziv` | placeholder: Naziv protivničke strane (obavezno) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Naziv protivničke strane (obavezno) | vidljiv samo dok je taj tab aktivan |
| UI-550 | `#strat-opponent-adv` | placeholder: Advokat / kancelarija (opciono) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Advokat / kancelarija (opciono) | vidljiv samo dok je taj tab aktivan |
| UI-551 | `button` (index.html:3195) | Analiziraj | dugme | `onclick="stratOpponentIntel()"` | pokreće AI analizu | vidljiv samo dok je taj tab aktivan |
| UI-552 | `button` (index.html:3202) | → Istraživanje zakona i argumentacija | dugme | `onclick="aiwsSetMode('zakon', document.querySelector('#aiws-modes .vx-pill[data-mode=zakon]'))"` | izvršava `aiwsSetMode()` | vidljiv samo dok je taj tab aktivan |
| UI-553 | `button` (index.html:3203) | → Puna pretraga sudske prakse | dugme | `onclick="setTab(document.getElementById('tab-btn-s'),'s')"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo dok je taj tab aktivan |
| UI-554 | `#dim-hero-input` | placeholder: Postavite pitanje o ZDI, MiCA ili regulativi digitalne imovine… | polje | `onkeydown="if(event.key==='Enter')dimHeroAnaliziraj()"` | korisnik unosi/bira vrednost — placeholder: Postavite pitanje o ZDI, MiCA ili regulativi digitalne imovine… | vidljiv samo dok je taj tab aktivan |
| UI-555 | `button.vx-btn.vx-btn-primary` | Analiziraj | dugme | `onclick="dimHeroAnaliziraj()"` | pokreće AI analizu | vidljiv samo dok je taj tab aktivan |
| UI-556 | `button.vx-btn.vx-btn-ghost` | Otvori | dugme | `onclick="dimOpenCard('due_diligence')"` | digitalna imovina / usklađenost | vidljiv samo dok je taj tab aktivan |
| UI-557 | `button.vx-btn.vx-btn-ghost` | Otvori | dugme | `onclick="dimOpenCard('regulatorna')"` | digitalna imovina / usklađenost | vidljiv samo dok je taj tab aktivan |
| UI-558 | `button.vx-btn.vx-btn-ghost` | Otvori | dugme | `onclick="dimOpenCard('wallet')"` | digitalna imovina / usklađenost | vidljiv samo dok je taj tab aktivan |
| UI-559 | `button.vx-btn.vx-btn-ghost` | Otvori | dugme | `onclick="dimOpenCard('sof')"` | digitalna imovina / usklađenost | vidljiv samo dok je taj tab aktivan |
| UI-560 | `button.strat-btn` | AI analiza projekta | dugme | `onclick="dimOpenModul('whitepaper_check')"` | digitalna imovina / usklađenost | vidljiv samo dok je taj tab aktivan |
| UI-561 | `button.strat-btn` | AML/KYC revizija | dugme | `onclick="dimOpenModul('aml_audit')"` | digitalna imovina / usklađenost | vidljiv samo dok je taj tab aktivan |
| UI-562 | `button.strat-btn` | Pametni ugovori | dugme | `onclick="dimOpenModul('smart_contract')"` | digitalna imovina / usklađenost | vidljiv samo dok je taj tab aktivan |
| UI-563 | `button.strat-btn` | Exchange Reporting Simulator | dugme | `onclick="dimOpenModul('reporting_simulator')"` | digitalna imovina / usklađenost | vidljiv samo dok je taj tab aktivan |
| UI-564 | `button.t-tool-back` | ← Vindex AI - Digitalna imovina & usklađenost | dugme | `onclick="dimBackToOverview()"` | digitalna imovina / usklađenost | vidljiv samo dok je taj tab aktivan |
| UI-565 | `#web3-tekst` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | vidljiv samo dok je taj tab aktivan |
| UI-566 | `#web3-submit-btn` | Analiziraj | dugme | `onclick="web3Pokreni()"` | digitalna imovina / usklađenost | vidljiv samo dok je taj tab aktivan |
| UI-567 | `button.web3-copy-btn` | Kopiraj | dugme | `onclick="web3Kopiraj()"` | kopira tekst u ostavu | vidljiv samo dok je taj tab aktivan |
| UI-568 | `#web3-jurisdikcije-btn` | Prikaži listu jurisdikcija | dugme | `onclick="web3JurisdikcijeLoad()"` | digitalna imovina / usklađenost | vidljiv samo dok je taj tab aktivan |
| UI-569 | `#web3-ofac-adrese` | placeholder: 0x...&#10;1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: 0x...&#10;1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa | vidljiv samo dok je taj tab aktivan |
| UI-570 | `#web3-ofac-btn` | Proveri adrese | dugme | `onclick="web3OfacProveri()"` | digitalna imovina / usklađenost | vidljiv samo dok je taj tab aktivan |
| UI-571 | `#web3-wallet-adresa` | placeholder: 0x... | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: 0x... | vidljiv samo dok je taj tab aktivan |
| UI-572 | `#web3-wallet-btn` | Proveri novčanik | dugme | `onclick="web3WalletProvenance()"` | digitalna imovina / usklađenost | vidljiv samo dok je taj tab aktivan |
| UI-573 | `#web3-dossier-opis` | placeholder: Npr: Imam KYC verifikaciju na Binance i Kraken nalozima... | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Npr: Imam KYC verifikaciju na Binance i Kraken nalozima... | vidljiv samo dok je taj tab aktivan |
| UI-574 | `#web3-dossier-carf` | placeholder: Ostavite prazno za opšti pregled obaveza izveštavanja. | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Ostavite prazno za opšti pregled obaveza izveštavanja. | vidljiv samo dok je taj tab aktivan |
| UI-575 | `#web3-dossier-wallet` | placeholder: 0x... (ostavite prazno da preskočite) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: 0x... (ostavite prazno da preskočite) | vidljiv samo dok je taj tab aktivan |
| UI-576 | `#web3-dossier-btn` | Generiši dossier (PDF, 2 kredita) | dugme | `onclick="web3DossierGeneriraj()"` | digitalna imovina / usklađenost | vidljiv samo dok je taj tab aktivan |
| UI-577 | `#web3-csv-fajl` | vizuelna `<label>` iznad (bez `for=`): CSV fajl | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — vizuelna `<label>` iznad (bez `for=`): CSV fajl | vidljiv samo dok je taj tab aktivan |
| UI-578 | `#web3-csv-btn` | Analiziraj CSV | dugme | `onclick="web3CsvUvoz()"` | digitalna imovina / usklađenost | vidljiv samo dok je taj tab aktivan |

### tab Dokumenti (`tab-dok`) — 2 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-579 | `div.dok-nav-card` | Predmeti Dokumenti unutar predmeta | dugme (div) | `onclick="setTab(document.getElementById('tab-btn-p'),'p')"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo dok je taj tab aktivan |
| UI-580 | `div.dok-nav-card` | Analiza dokumenta analiza novog dokumenta | dugme (div) | `onclick="openAITool('a')"` | otvara prozor/panel | vidljiv samo dok je taj tab aktivan |

### tab Podešavanja (`tab-settings`) — 91 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-581 | `#settings-display-name-input` | placeholder: npr. Benny | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: npr. Benny | vidljiv samo dok je taj tab aktivan |
| UI-582 | `button.settings-btn` | Sačuvaj | dugme | `onclick="saveDisplayName()"` | čuva unete podatke | vidljiv samo dok je taj tab aktivan |
| UI-583 | `button.settings-btn` | Upravljaj | dugme | `onclick="openSubscription()"` | otvara prozor/panel | vidljiv samo dok je taj tab aktivan |
| UI-584 | `button.settings-btn` | Resetuj | dugme | `onclick="doForgotPasswordFromSettings()"` | izvršava `doForgotPasswordFromSettings()` | vidljiv samo dok je taj tab aktivan |
| UI-585 | `button.settings-btn` | Detalji | dugme | `onclick="dataResidencyOpen()"` | otvara prozor/panel | vidljiv samo dok je taj tab aktivan |
| UI-586 | `#export-btn` | Preuzmi ZIP | dugme | `onclick="exportSviPodaci()"` | izvozi/preuzima dokument | vidljiv samo dok je taj tab aktivan |
| UI-587 | `#delete-account-btn` | Obriši nalog | dugme | `onclick="obrisiNalogSelfService()"` | briše stavku | vidljiv samo dok je taj tab aktivan |
| UI-588 | `a` (index.html:3496) | Otvori | link | `href="/security"` | vodi na /security | vidljiv samo dok je taj tab aktivan |
| UI-589 | `button.settings-btn` | Otvori | dugme | (nema inline rukovaoca) | nema definisano dejstvo (nema rukovaoca) | vidljiv samo dok je taj tab aktivan |
| UI-590 | `a` (index.html:3503) | Preuzmi | link | `href="/dpa"` | vodi na /dpa | vidljiv samo dok je taj tab aktivan |
| UI-591 | `button.settings-btn` | Preuzmi | dugme | (nema inline rukovaoca) | nema definisano dejstvo (nema rukovaoca) | vidljiv samo dok je taj tab aktivan |
| UI-592 | `a` (index.html:3510) | Otvori | link | `href="/status"` | vodi na /status | vidljiv samo dok je taj tab aktivan |
| UI-593 | `button.settings-btn` | Otvori | dugme | (nema inline rukovaoca) | nema definisano dejstvo (nema rukovaoca) | vidljiv samo dok je taj tab aktivan |
| UI-594 | `button.settings-btn` | ↻ Osveži | dugme | `onclick="planLoad()"` | nadogradnja plana / naplata pretplate | vidljiv samo dok je taj tab aktivan |
| UI-595 | `button.settings-btn` | ⬆ Upgrade plan | dugme | `onclick="openProModal()"` | otvara prozor/panel | vidljiv samo dok je taj tab aktivan |
| UI-596 | `button.settings-btn` | ↻ Osveži | dugme | `onclick="confidenceAuditLoad()"` | izvršava `confidenceAuditLoad()` | vidljiv samo dok je taj tab aktivan |
| UI-597 | `a.settings-btn` | Politika privatnosti | link | `href="/privacy"` | vodi na /privacy | vidljiv samo dok je taj tab aktivan |
| UI-598 | `a.settings-btn` | Uslovi korišćenja | link | `href="/terms"` | vodi na /terms | vidljiv samo dok je taj tab aktivan |
| UI-599 | `div.settings-row` | Advokatska kancelarija Tim, pozivnice, uloge — sada u tabu Kancelarija → | dugme (div) | `onclick="setTab(document.getElementById('tab-btn-kanc'),'kanc')"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo dok je taj tab aktivan |
| UI-600 | `div.settings-row` | Naplata i dugovanja Fakture, izveštaji, neplaćena dugovanja — sada u tabu Finansije → | dugme (div) | `onclick="setTab(document.getElementById('tab-btn-fin'),'fin')"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo dok je taj tab aktivan |
| UI-601 | `#sef-pib` | placeholder: 123456789 | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: 123456789 | vidljiv samo dok je taj tab aktivan |
| UI-602 | `#sef-naziv` | placeholder: Advokat Petrović | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Advokat Petrović | vidljiv samo dok je taj tab aktivan |
| UI-603 | `#sef-adresa` | placeholder: Knez Mihailova 10 | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Knez Mihailova 10 | vidljiv samo dok je taj tab aktivan |
| UI-604 | `#sef-mesto` | placeholder: Beograd | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Beograd | vidljiv samo dok je taj tab aktivan |
| UI-605 | `#sef-apikey` | placeholder: Novi API ključ (ostavite prazno da ne menjate) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Novi API ključ (ostavite prazno da ne menjate) | vidljiv samo dok je taj tab aktivan |
| UI-606 | `#sef-save-btn` | Sačuvaj SEF | dugme | `onclick="sef_saveSettings()"` | čuva unete podatke | vidljiv samo dok je taj tab aktivan |
| UI-607 | `#sms-telefon-input` | placeholder: +381601234567 ili 0601234567 | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: +381601234567 ili 0601234567 | vidljiv samo dok je taj tab aktivan |
| UI-608 | `#sms-whatsapp-chk` | uz kontrolu (`<label>` omotač): WhatsApp | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — uz kontrolu (`<label>` omotač): WhatsApp | vidljiv samo dok je taj tab aktivan |
| UI-609 | `button.settings-btn` | Sačuvaj broj | dugme | `onclick="sms_sacuvaj()"` | čuva unete podatke | vidljiv samo dok je taj tab aktivan |
| UI-610 | `#sms-test-btn` | Pošalji test | dugme | `onclick="sms_testSms()"` | izvršava `sms_testSms()` | `display:none` na samom elementu; vidljiv samo dok je taj tab aktivan |
| UI-611 | `#sms-deaktivir-btn` | Deaktiviraj | dugme | `onclick="sms_deaktiviraj()"` | izvršava `sms_deaktiviraj()` | `display:none` na samom elementu; vidljiv samo dok je taj tab aktivan |
| UI-612 | `#en-dan-7` | uz kontrolu (`<label>` omotač): 7 dana pre | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — uz kontrolu (`<label>` omotač): 7 dana pre | vidljiv samo dok je taj tab aktivan |
| UI-613 | `#en-dan-3` | uz kontrolu (`<label>` omotač): 3 dana pre | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — uz kontrolu (`<label>` omotač): 3 dana pre | vidljiv samo dok je taj tab aktivan |
| UI-614 | `#en-dan-1` | uz kontrolu (`<label>` omotač): 1 dan pre (dan uoči roka) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — uz kontrolu (`<label>` omotač): 1 dan pre (dan uoči roka) | vidljiv samo dok je taj tab aktivan |
| UI-615 | `#en-nedeljni` | uz kontrolu (`<label>` omotač): Nedeljni sažetak (ponedeljak ujutru — rokovi, ročišta, naplata) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — uz kontrolu (`<label>` omotač): Nedeljni sažetak (ponedeljak ujutru — rokovi, ročišta, naplata) | vidljiv samo dok je taj tab aktivan |
| UI-616 | `#en-save-btn` | Aktiviraj | dugme | `onclick="emailNotifSacuvaj()"` | čuva unete podatke | vidljiv samo dok je taj tab aktivan |
| UI-617 | `#en-test-btn` | Pošalji test | dugme | `onclick="emailNotifTest()"` | notifikacije | `display:none` na samom elementu; vidljiv samo dok je taj tab aktivan |
| UI-618 | `#en-deaktiv-btn` | Deaktiviraj | dugme | `onclick="emailNotifDeaktivaj()"` | notifikacije | `display:none` na samom elementu; vidljiv samo dok je taj tab aktivan |
| UI-619 | `button` (index.html:3708) | kopuj | dugme | `onclick="integr_copy('analyze')"` | kopira tekst u ostavu | vidljiv samo dok je taj tab aktivan |
| UI-620 | `button` (index.html:3717) | kopuj | dugme | `onclick="integr_copy('clio')"` | kopira tekst u ostavu | vidljiv samo dok je taj tab aktivan |
| UI-621 | `button` (index.html:3722) | kopuj | dugme | `onclick="integr_copy('imanage')"` | kopira tekst u ostavu | vidljiv samo dok je taj tab aktivan |
| UI-622 | `div.pomoc-faq-q` | Koliko je tačan AI? ▸ | dugme (div) | `onclick="pomocFaqToggle(0)"` | pomoć/podrška i povratna informacija | vidljiv samo dok je taj tab aktivan |
| UI-623 | `div.pomoc-faq-q` | Kako da uploadujem dokument? ▸ | dugme (div) | `onclick="pomocFaqToggle(1)"` | pomoć/podrška i povratna informacija | vidljiv samo dok je taj tab aktivan |
| UI-624 | `div.pomoc-faq-q` | Kako da dodam novog klijenta? ▸ | dugme (div) | `onclick="pomocFaqToggle(2)"` | pomoć/podrška i povratna informacija | vidljiv samo dok je taj tab aktivan |
| UI-625 | `div.pomoc-faq-q` | Koja sudska praksa je dostupna? ▸ | dugme (div) | `onclick="pomocFaqToggle(3)"` | pomoć/podrška i povratna informacija | vidljiv samo dok je taj tab aktivan |
| UI-626 | `div.pomoc-faq-q` | Da li su moji podaci bezbedni? ▸ | dugme (div) | `onclick="pomocFaqToggle(4)"` | pomoć/podrška i povratna informacija | vidljiv samo dok je taj tab aktivan |
| UI-627 | `a` (index.html:3783) | Politiku privatnosti | link | `href="/privacy"` | vodi na /privacy | vidljiv samo dok je taj tab aktivan |
| UI-628 | `div.pomoc-faq-q` | Kako da promenim ili otkazhem pretplatu? ▸ | dugme (div) | `onclick="pomocFaqToggle(5)"` | pomoć/podrška i povratna informacija | vidljiv samo dok je taj tab aktivan |
| UI-629 | `#pomoc-kategorija` | (bez labele — prva opcija: „Tehnički problem“) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — (bez labele — prva opcija: „Tehnički problem“) | vidljiv samo dok je taj tab aktivan |
| UI-630 | `#pomoc-poruka` | placeholder: Opišite problem ili pišite nam šta mislite... | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Opišite problem ili pišite nam šta mislite... | vidljiv samo dok je taj tab aktivan |
| UI-631 | `#pomoc-send-btn` | Pošalji poruku | dugme | `onclick="pomocPosalji()"` | pomoć/podrška i povratna informacija | vidljiv samo dok je taj tab aktivan |
| UI-632 | `button.settings-btn` | Odjavi se | dugme | `onclick="doLogout ? doLogout() : null"` | prijava/registracija/nalog | vidljiv samo dok je taj tab aktivan |
| UI-633 | `#corpus-discover-btn` | Traži nove biltene | dugme | `onclick="corpusDiscoverRun()"` | administrativna radnja | vidljiv samo dok je taj tab aktivan |
| UI-634 | `button.settings-btn` | Lista otkrivenih | dugme | `onclick="corpusListDiscovered()"` | administrativna radnja | vidljiv samo dok je taj tab aktivan |
| UI-635 | `#law-list-btn` | Lista | dugme | `onclick="lawListLoad()"` | administrativna radnja | vidljiv samo dok je taj tab aktivan |
| UI-636 | `#law-naziv-input` | placeholder: Naziv zakona (npr. Zakon o privrednim društvima) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Naziv zakona (npr. Zakon o privrednim društvima) | vidljiv samo dok je taj tab aktivan |
| UI-637 | `#law-sl-glasnik-input` | placeholder: Sl. glasnik RS (npr. 36/2011, 99/2011...) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Sl. glasnik RS (npr. 36/2011, 99/2011...) | vidljiv samo dok je taj tab aktivan |
| UI-638 | `#law-pdf-input` | (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | vidljiv samo dok je taj tab aktivan |
| UI-639 | `#law-upload-btn` | ⬆ Upload | dugme | `onclick="lawUploadRun()"` | otprema dokument | vidljiv samo dok je taj tab aktivan |
| UI-640 | `button.settings-btn` | ↻ Osveži sve | dugme | `onclick="adminOpsLoad()"` | administrativna radnja | vidljiv samo dok je taj tab aktivan |
| UI-641 | `button.settings-btn` | ↻ | dugme | `onclick="adminNotifLoad()"` | notifikacije | vidljiv samo dok je taj tab aktivan |
| UI-642 | `#notif-filter-channel` | (bez labele — prva opcija: „Svi kanali“) | polje | `onchange="adminNotifLoad()"` | korisnik unosi/bira vrednost — (bez labele — prva opcija: „Svi kanali“) | vidljiv samo dok je taj tab aktivan |
| UI-643 | `#notif-filter-status` | (bez labele — prva opcija: „Svi statusi“) | polje | `onchange="adminNotifLoad()"` | korisnik unosi/bira vrednost — (bez labele — prva opcija: „Svi statusi“) | vidljiv samo dok je taj tab aktivan |
| UI-644 | `#beta-add-email` | placeholder: email@firma.rs | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: email@firma.rs | vidljiv samo dok je taj tab aktivan |
| UI-645 | `button.settings-btn` | + Dodaj | dugme | `onclick="adminBetaAdd()"` | administrativna radnja | vidljiv samo dok je taj tab aktivan |
| UI-646 | `button.settings-btn` | ↻ | dugme | `onclick="adminPineconeLoad()"` | administrativna radnja | vidljiv samo dok je taj tab aktivan |
| UI-647 | `button.settings-btn` | ↻ | dugme | `onclick="adminFeatureRegistryLoad()"` | administrativna radnja | vidljiv samo dok je taj tab aktivan |
| UI-648 | `#fr-filter-kategorija` | (bez labele — prva opcija: „Sve kategorije“) | polje | `onchange="adminFeatureRegistryRender()"` | korisnik unosi/bira vrednost — (bez labele — prva opcija: „Sve kategorije“) | vidljiv samo dok je taj tab aktivan |
| UI-649 | `#fr-filter-search` | placeholder: Pretraži po nazivu... | polje | `oninput="adminFeatureRegistryRender()"` | korisnik unosi/bira vrednost — placeholder: Pretraži po nazivu... | vidljiv samo dok je taj tab aktivan |
| UI-650 | `#analytics-period` | (bez labele — prva opcija: „7 dana“) | polje | `onchange="analyticsLoad()"` | korisnik unosi/bira vrednost — (bez labele — prva opcija: „7 dana“) | vidljiv samo dok je taj tab aktivan |
| UI-651 | `button.settings-btn` | ↻ | dugme | `onclick="analyticsLoad()"` | izvršava `analyticsLoad()` | vidljiv samo dok je taj tab aktivan |
| UI-652 | `#wl-admin-refresh-btn` | ↻ Osveži | dugme | `onclick="wl_admin_load()"` | administrativna radnja | vidljiv samo dok je taj tab aktivan |
| UI-653 | `#exec-btn` | Pretraži pravnu bazu | dugme | `onclick="execQuery()"` | pokreće pretragu/upit | vidljiv samo dok je taj tab aktivan |
| UI-654 | `#cyr-toggle` | uz kontrolu (`<label>` omotač): Ћирилица | polje | `onchange="toggleCyrillic()"` | korisnik unosi/bira vrednost — uz kontrolu (`<label>` omotač): Ћирилица | vidljiv samo dok je taj tab aktivan |
| UI-655 | `button.analiza-wf-btn` | Sačuvaj u predmet | dugme | `onclick="analizaSacuvajUPredmet()"` | čuva unete podatke | vidljiv samo dok je taj tab aktivan |
| UI-656 | `button.analiza-wf-btn` | Generiši nacrt tužbe | dugme | `onclick="analizaGenerisiNacrt()"` | pokreće AI analizu | vidljiv samo dok je taj tab aktivan |
| UI-657 | `button.analiza-wf-btn` | Pošalji u Strategiju | dugme | `onclick="analizaDodajUStrategiju()"` | pokreće AI analizu | vidljiv samo dok je taj tab aktivan |
| UI-658 | `button.analiza-wf-btn` | Kopiraj analizu | dugme | `onclick="analizaKopiraj(this)"` | pokreće AI analizu | vidljiv samo dok je taj tab aktivan |
| UI-659 | `button.analiza-wf-btn` | Izvezi Word | dugme | `onclick="exportujKaoWord('Analiza predmeta', document.getElementById('rb').innerText, 'analiza')"` | izvozi/preuzima dokument | vidljiv samo dok je taj tab aktivan |
| UI-660 | `#podnesak-preview-body` | title: Kliknite za direktno uređivanje teksta | polje | `oninput="window._podnesakEdited=true;"` | nema definisano dejstvo (nema rukovaoca) | vidljiv samo dok je taj tab aktivan |
| UI-661 | `#podnesak-pdf-btn` | Preuzmi PDF | dugme | `onclick="exportPDF(_lastRawText, this)"` | izvozi/preuzima dokument | vidljiv samo dok je taj tab aktivan |
| UI-662 | `#podnesak-copy-btn` | Kopiraj tekst | dugme | `onclick="copyPodnesak(this)"` | kopira tekst u ostavu | vidljiv samo dok je taj tab aktivan |
| UI-663 | `button.podnesak-preview-btn.btn-word` | Word | dugme | `onclick="exportujKaoWord('Nacrt dokumenta',_lastRawText,'nacrt')"` | izvozi/preuzima dokument | vidljiv samo dok je taj tab aktivan |
| UI-664 | `#nacrt-docx-btn` | ⬇ DOCX | dugme | `onclick="nacrtExportDocx()"` | izvozi/preuzima dokument | vidljiv samo dok je taj tab aktivan |
| UI-665 | `button.podnesak-preview-btn.podnesak-preview-edit` | Uredi / Follow-up | dugme | `onclick="editPodnesak()"` | izrada nacrta/podneska | vidljiv samo dok je taj tab aktivan |
| UI-666 | `button.podnesak-preview-btn` | ↺ Regeneriši | dugme | `onclick="regenerisiPodnesak(this)"` | kreiranje novog predmeta | vidljiv samo dok je taj tab aktivan |
| UI-667 | `#portal-file-input` | (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | polje | `onchange="portal_fileSelected(this)"` | korisnik unosi/bira vrednost — (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | `display:none` na samom elementu; vidljiv samo dok je taj tab aktivan |
| UI-668 | `#portal-file-drop` | Kliknite ili prevucite fajl ovde PDF, DOCX, JPG, PNG · maks 10 MB | dugme (div) | `onclick="document.getElementById('portal-file-input').click()"` | izvršava `document.getElementById()` | vidljiv samo dok je taj tab aktivan |
| UI-669 | `button` (index.html:4110) | ✕ | dugme | `onclick="portal_fileOtkazi()"` | klijentski portal / portal suda | vidljiv samo dok je taj tab aktivan |
| UI-670 | `#portal-napomena` | placeholder: Napomena advokatu (opciono)... | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Napomena advokatu (opciono)... | vidljiv samo dok je taj tab aktivan |
| UI-671 | `#portal-upload-btn` | ⬆ Pošalji dokument | dugme | `onclick="portal_uploadFajl()"` | otprema dokument | vidljiv samo dok je taj tab aktivan |

### overlay `wl-overlay` (lista čekanja) — 8 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-672 | `#wl-overlay` | &#x2715; Early Access Pridružite se Vindex AI Prijavite se za rani pristup. Javićemo vam s | dugme (div) | `onclick="if(event.target===this)wl_close()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-673 | `button.wl-close` | &#x2715; | dugme | `onclick="wl_close()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-674 | `#wl-ime` | placeholder: Marko Marković | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Marko Marković | vidljiv samo dok je taj modal/overlay otvoren |
| UI-675 | `#wl-firma` | placeholder: AK Marković | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: AK Marković | vidljiv samo dok je taj modal/overlay otvoren |
| UI-676 | `#wl-email` | placeholder: marko@kancelarija.rs | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: marko@kancelarija.rs | vidljiv samo dok je taj modal/overlay otvoren |
| UI-677 | `#wl-telefon` | placeholder: +381 60 123 4567 | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: +381 60 123 4567 | vidljiv samo dok je taj modal/overlay otvoren |
| UI-678 | `#wl-poruka` | placeholder: Npr. istraživanje zakona, upravljanje predmetima... | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Npr. istraživanje zakona, upravljanje predmetima... | vidljiv samo dok je taj modal/overlay otvoren |
| UI-679 | `#wl-submit-btn` | Prijavite se za rani pristup | dugme | `onclick="wl_submit()"` | izvršava `wl_submit()` | vidljiv samo dok je taj modal/overlay otvoren |

### landing stranica — 6 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-680 | `a.vx-land-logo` | Vindex AI | link | `href="#"` | nema definisano dejstvo (nema rukovaoca) | samo neprijavljenim korisnicima (landing) |
| UI-681 | `#nav-cta-btn` | Prijavite se -> | link | `onclick="openModal();return false;"` | otvara prozor/panel | samo neprijavljenim korisnicima (landing) |
| UI-682 | `button.vx-land-btn-primary` | Zatražite rani pristup -> | dugme | `onclick="wl_open()"` | otvara prozor/panel | samo neprijavljenim korisnicima (landing) |
| UI-683 | `button.vx-land-btn-secondary` | Već imam nalog | dugme | `onclick="openModal()"` | otvara prozor/panel | samo neprijavljenim korisnicima (landing) |
| UI-684 | `a` (index.html:4223) | Politika privatnosti | link | `href="/privacy"` | vodi na /privacy | samo neprijavljenim korisnicima (landing) |
| UI-685 | `a` (index.html:4225) | Uslovi korišćenja | link | `href="/terms"` | vodi na /terms | samo neprijavljenim korisnicima (landing) |

### overlay `cmdk-overlay` (komandna paleta) — 10 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-686 | `#cmdk-overlay` | ⌕ Esc Sve Predmeti Klijenti Rokovi Zadaci Dokumenti Naplata ↑↓ navigacija Enter otvori Esc | dugme (div) | `onclick="if(event.target===this)cmdkClose()"` | zatvara otvoreni prozor/panel | `display:none` na samom elementu; vidljiv samo dok je taj modal/overlay otvoren |
| UI-687 | `div.vx-modal.vx-modal-palette` | ⌕ Esc Sve Predmeti Klijenti Rokovi Zadaci Dokumenti Naplata ↑↓ navigacija Enter otvori Esc | dugme (div) | `onclick="event.stopPropagation()"` | upravlja tajmerom/naplatom vremena | vidljiv samo dok je taj modal/overlay otvoren |
| UI-688 | `#cmdk-input` | placeholder: Pretraži predmete, klijente, dokumente, zadatke, naplatu... | polje | `oninput="cmdkQuery(this.value)"` | korisnik unosi/bira vrednost — placeholder: Pretraži predmete, klijente, dokumente, zadatke, naplatu... | vidljiv samo dok je taj modal/overlay otvoren |
| UI-689 | `button.vx-pill.is-active` | Sve | dugme | `onclick="cmdkSetFilter(this)"` | komandna paleta | vidljiv samo dok je taj modal/overlay otvoren |
| UI-690 | `button.vx-pill` | Predmeti | dugme | `onclick="cmdkSetFilter(this)"` | komandna paleta | vidljiv samo dok je taj modal/overlay otvoren |
| UI-691 | `button.vx-pill` | Klijenti | dugme | `onclick="cmdkSetFilter(this)"` | komandna paleta | vidljiv samo dok je taj modal/overlay otvoren |
| UI-692 | `button.vx-pill` | Rokovi | dugme | `onclick="cmdkSetFilter(this)"` | komandna paleta | vidljiv samo dok je taj modal/overlay otvoren |
| UI-693 | `button.vx-pill` | Zadaci | dugme | `onclick="cmdkSetFilter(this)"` | komandna paleta | vidljiv samo dok je taj modal/overlay otvoren |
| UI-694 | `button.vx-pill` | Dokumenti | dugme | `onclick="cmdkSetFilter(this)"` | komandna paleta | vidljiv samo dok je taj modal/overlay otvoren |
| UI-695 | `button.vx-pill` | Naplata | dugme | `onclick="cmdkSetFilter(this)"` | komandna paleta | vidljiv samo dok je taj modal/overlay otvoren |

### modal `settings-modal` (podaci kancelarije) — 11 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-696 | `#settings-modal` | &#x2715; Podešavanja kancelarije Ovi podaci se prikazuju na PDF izveštajima. Čuvaju se lok | dugme (div) | `onclick="if(event.target===this)closeSettings()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-697 | `button.modal-close` | &#x2715; | dugme | `onclick="closeSettings()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-698 | `#s-naziv` | placeholder: npr. Adv. kancelarija Petrović | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: npr. Adv. kancelarija Petrović | vidljiv samo dok je taj modal/overlay otvoren |
| UI-699 | `#s-adresa` | placeholder: Ulica i broj, Grad | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Ulica i broj, Grad | vidljiv samo dok je taj modal/overlay otvoren |
| UI-700 | `#s-pib` | placeholder: 123456789 | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: 123456789 | vidljiv samo dok je taj modal/overlay otvoren |
| UI-701 | `#s-kontakt` | placeholder: advokat@kancelarija.rs | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: advokat@kancelarija.rs | vidljiv samo dok je taj modal/overlay otvoren |
| UI-702 | `button.settings-save-btn` | Sačuvaj podešavanja | dugme | `onclick="saveSettings()"` | čuva unete podatke | vidljiv samo dok je taj modal/overlay otvoren |
| UI-703 | `#s-satnica` | placeholder: 7500 (AKS default) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: 7500 (AKS default) | vidljiv samo dok je taj modal/overlay otvoren |
| UI-704 | `button.settings-save-btn` | Sačuvaj | dugme | `onclick="tarife_saveSatnica()"` | čuva unete podatke | vidljiv samo dok je taj modal/overlay otvoren |
| UI-705 | `#btn-clear-compare` | Poništi | dugme | `onclick="clearCompare()"` | izvršava `clearCompare()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-706 | `#btn-start-compare` | Uporedi odabrane | dugme | `onclick="startCompare()"` | upravlja tajmerom/naplatom vremena | vidljiv samo dok je taj modal/overlay otvoren |

### modal `compare-modal` (poređenje verzija) — 2 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-707 | `button.vx-modal-close` | &#x2715; | dugme | `onclick="closeCompareModal()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-708 | `button` (index.html:4339) | Zatvori | dugme | `onclick="closeCompareModal()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |

### modal `rociste-overlay` (ročište) — 13 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-709 | `#rociste-overlay` | Novo ročište ✕ Predmet * Sud * Datum * Vreme (opciono) Sudnica (opciono) Broj predmeta sud | dugme (div) | `onclick="rocisteZatvoriFormu()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-710 | `div.crm-panel` | Novo ročište ✕ Predmet * Sud * Datum * Vreme (opciono) Sudnica (opciono) Broj predmeta sud | dugme (div) | `onclick="event.stopPropagation()"` | upravlja tajmerom/naplatom vremena | vidljiv samo dok je taj modal/overlay otvoren |
| UI-711 | `button.crm-panel-close` | ✕ | dugme | `onclick="rocisteZatvoriFormu()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-712 | `#rociste-edit-id` | (skriveno polje — nema vidljivu labelu) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — (skriveno polje — nema vidljivu labelu) | vidljiv samo dok je taj modal/overlay otvoren |
| UI-713 | `#rociste-predmet-id` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | vidljiv samo dok je taj modal/overlay otvoren |
| UI-714 | `#rociste-sud` | placeholder: Npr. Viši sud u Beogradu | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Npr. Viši sud u Beogradu | vidljiv samo dok je taj modal/overlay otvoren |
| UI-715 | `#rociste-datum` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | vidljiv samo dok je taj modal/overlay otvoren |
| UI-716 | `#rociste-vreme` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | vidljiv samo dok je taj modal/overlay otvoren |
| UI-717 | `#rociste-sudnica` | placeholder: Npr. Sudnica 4 | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Npr. Sudnica 4 | vidljiv samo dok je taj modal/overlay otvoren |
| UI-718 | `#rociste-broj` | placeholder: Npr. P-123/2025 | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Npr. P-123/2025 | vidljiv samo dok je taj modal/overlay otvoren |
| UI-719 | `#rociste-napomena` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | vidljiv samo dok je taj modal/overlay otvoren |
| UI-720 | `button.crm-save-btn` | Sačuvaj | dugme | `onclick="rocisteSnimi()"` | rokovi i ročišta | vidljiv samo dok je taj modal/overlay otvoren |
| UI-721 | `button.crm-cancel-btn` | Otkaži | dugme | `onclick="rocisteZatvoriFormu()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |

### mobilno — donja navigacija — 6 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-722 | `#mob-btn-h` | Početna | stavka menija | `onclick="mobileNavGo('h')"` | prebacuje korisnika na drugi ekran/tab | samo na mobilnom prikazu |
| UI-723 | `#mob-btn-p` | Predmeti | stavka menija | `onclick="mobileNavGo('p')"` | prebacuje korisnika na drugi ekran/tab | samo na mobilnom prikazu |
| UI-724 | `#mob-btn-kal` | Rokovi | stavka menija | `onclick="mobileNavGo('kal')"` | prebacuje korisnika na drugi ekran/tab | samo na mobilnom prikazu |
| UI-725 | `#mob-btn-k` | Klijenti | stavka menija | `onclick="mobileNavGo('k')"` | prebacuje korisnika na drugi ekran/tab | samo na mobilnom prikazu |
| UI-726 | `#mob-btn-mob-more` | Više | stavka menija | `onclick="mobileMoreOtvori()"` | otvara prozor/panel | samo na mobilnom prikazu |
| UI-727 | `#vx-mobile-fab` | title: Novi predmet | FAB | `onclick="intakeOtvori()"` | otvara prozor/panel | samo na mobilnom prikazu |

### plutajuće — FAB Vindex Live (glas) — 1 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-728 | `#vx-voice-fab` | title: Vindex Live — glasovna komanda | FAB | `onclick="vxLiveOpen()"` | otvara prozor/panel | ne |

### modal `vx-voice-modal-overlay` (Vindex Live) — 6 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-729 | `#vx-voice-modal-overlay` | &#x2715; Povezujem... Da, potvrdi Otkaži Završi razgovor Vindex Live sluša samo dok je ova | dugme (div) | `onclick="if(event.target===this) vxLiveClose()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-730 | `button.modal-close` | &#x2715; | dugme | `onclick="vxLiveClose()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-731 | `button.modal-btn.vx-voice-confirm-yes` | Da, potvrdi | dugme | `onclick="vxLiveConfirm(true)"` | glasovna interakcija | vidljiv samo dok je taj modal/overlay otvoren |
| UI-732 | `button.strat-btn.vx-voice-confirm-no` | Otkaži | dugme | `onclick="vxLiveConfirm(false)"` | glasovna interakcija | vidljiv samo dok je taj modal/overlay otvoren |
| UI-733 | `#vx-voice-stop-btn` | Završi razgovor | dugme | `onclick="vxLiveClose()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-734 | `#mob-more-overlay` | (bez labele) | dugme (div) | `onclick="mobileMoreZatvori()"` | zatvara otvoreni prozor/panel | `display:none` na samom elementu; vidljiv samo dok je taj modal/overlay otvoren |

### mobilno — 'Više' bottom sheet — 15 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-735 | `button.mob-more-btn` | Istraži zakon | stavka menija | `onclick="mobileMoreGo('aiws')"` | prebacuje korisnika na drugi ekran/tab | samo na mobilnom prikazu |
| UI-736 | `button.mob-more-btn` | Sud. praksa | stavka menija | `onclick="mobileMoreGo('s')"` | prebacuje korisnika na drugi ekran/tab | samo na mobilnom prikazu |
| UI-737 | `button.mob-more-btn` | Analiza dok. | stavka menija | `onclick="mobileMoreGo('a')"` | prebacuje korisnika na drugi ekran/tab | samo na mobilnom prikazu |
| UI-738 | `button.mob-more-btn` | Podnesci | stavka menija | `onclick="mobileMoreGo('n')"` | prebacuje korisnika na drugi ekran/tab | samo na mobilnom prikazu |
| UI-739 | `button.mob-more-btn` | Strategija | stavka menija | `onclick="mobileMoreGo('t')"` | prebacuje korisnika na drugi ekran/tab | samo na mobilnom prikazu |
| UI-740 | `button.mob-more-btn` | Šabloni | stavka menija | `onclick="mobileMoreZatvori();docTplOpen();"` | zatvara otvoreni prozor/panel | samo na mobilnom prikazu |
| UI-741 | `button.mob-more-btn` | Baza znanja | stavka menija | `onclick="mobileMoreGo('dok')"` | prebacuje korisnika na drugi ekran/tab | samo na mobilnom prikazu |
| UI-742 | `button.mob-more-btn` | Finansije | stavka menija | `onclick="mobileMoreGo('fin')"` | prebacuje korisnika na drugi ekran/tab | samo na mobilnom prikazu |
| UI-743 | `button.mob-more-btn` | Kancelarija | stavka menija | `onclick="mobileMoreGo('kanc')"` | prebacuje korisnika na drugi ekran/tab | samo na mobilnom prikazu |
| UI-744 | `button.mob-more-btn` | Portfolio | stavka menija | `onclick="mobileMoreGo('pi')"` | prebacuje korisnika na drugi ekran/tab | samo na mobilnom prikazu |
| UI-745 | `button.mob-more-btn` | + Klijent | stavka menija | `onclick="mobileMoreZatvori();crmOtvoriFormu();"` | zatvara otvoreni prozor/panel | samo na mobilnom prikazu |
| UI-746 | `button.mob-more-btn` | Izveštaj | stavka menija | `onclick="mobileMoreZatvori();mesecniIzvestajOtvori();"` | zatvara otvoreni prozor/panel | samo na mobilnom prikazu |
| UI-747 | `#mob-more-notif-btn` | Notifikacije | stavka menija | `onclick="mobileMoreZatvori();notif_toggleDropdown();"` | zatvara otvoreni prozor/panel | samo na mobilnom prikazu |
| UI-748 | `button.mob-more-btn` | Podešavanja | stavka menija | `onclick="mobileMoreGo('settings')"` | prebacuje korisnika na drugi ekran/tab | samo na mobilnom prikazu |
| UI-749 | `#mob-more-install-btn` | Instaliraj | stavka menija | `onclick="mobileMoreZatvori();pwaInstall();"` | zatvara otvoreni prozor/panel | `display:none` na samom elementu; samo na mobilnom prikazu |

### modal `voice-modal` (STARI glasovni modal) — 1 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-750 | `button` (index.html:4535) | ✕ Otkaži | dugme | `onclick="voice_stop()"` | glasovna interakcija | vidljiv samo dok je taj modal/overlay otvoren |

### plutajuće — `pred-fab` (brze akcije u predmetu) — 7 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-751 | `button` (index.html:4545) | Dodaj dokument | dugme | `onclick="pred_fab_close();pred_subtabSwitch('dokumenti')"` | zatvara otvoreni prozor/panel | ne |
| UI-752 | `button` (index.html:4546) | Dodaj rok | dugme | `onclick="pred_fab_close();pred_subtabSwitch('rokovi')"` | zatvara otvoreni prozor/panel | ne |
| UI-753 | `button` (index.html:4547) | Zakaži ročište | dugme | `onclick="pred_fab_close();rocisteOtvoriFormu(activePredmetId)"` | zatvara otvoreni prozor/panel | ne |
| UI-754 | `button` (index.html:4548) | Unesi naplatu | dugme | `onclick="pred_fab_close();pred_subtabSwitch('naplata')"` | zatvara otvoreni prozor/panel | ne |
| UI-755 | `button` (index.html:4549) | Dodaj belešku | dugme | `onclick="pred_fab_close();if(activePredmetId){pred_subtabSwitch('rokovi');}"` | zatvara otvoreni prozor/panel | ne |
| UI-756 | `button` (index.html:4550) | ⏱ Pokreni tajmer | dugme | `onclick="pred_fab_close();if(!_billingPredmetId)_billingPredmetId=activePredmetId;if(typeof billing_timerToggle==='function')billing_timerToggle();"` | zatvara otvoreni prozor/panel | ne |
| UI-757 | `#pred-fab-btn` | title: Brze akcije — dodaj dokument, rok, naplatu | FAB | `onclick="pred_fab_toggle()"` | prikazuje ili sakriva deo ekrana | ne |

### modal `ios-install-modal` — 1 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-758 | `button` (index.html:4564) | ✕ | dugme | `onclick="document.getElementById('ios-install-modal').style.display='none'"` | izvršava `document.getElementById()` | vidljiv samo dok je taj modal/overlay otvoren |

### mobilno — panel notifikacija — 2 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-759 | `#mob-notif-overlay` | (bez labele) | dugme (div) | `onclick="mobNotifZatvori()"` | zatvara otvoreni prozor/panel | `display:none` na samom elementu; samo na mobilnom prikazu |
| UI-760 | `button` (index.html:4589) | ✕ | dugme | `onclick="mobNotifZatvori()"` | zatvara otvoreni prozor/panel | samo na mobilnom prikazu |

### modal `android-install-modal` — 2 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-761 | `#android-install-modal` | Instaliraj Vindex AI ✕ Dodajte Vindex AI na početni ekran putem Chrome menija: 1 Tapnite t | dugme (div) | `onclick="if(event.target===this)this.style.display='none'"` | izvršava `if()` | `display:none` na samom elementu; vidljiv samo dok je taj modal/overlay otvoren |
| UI-762 | `button` (index.html:4599) | ✕ | dugme | `onclick="document.getElementById('android-install-modal').style.display='none'"` | izvršava `document.getElementById()` | vidljiv samo dok je taj modal/overlay otvoren |

### modal `vx-dialog-overlay` (zamena za alert/confirm) — 4 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-763 | `#vx-dialog-overlay` | Odustani OK | dugme (div) | `onclick="if(event.target===this)_vxDlgCancel()"` | zatvara otvoreni prozor/panel | `display:none` na samom elementu; vidljiv samo dok je taj modal/overlay otvoren |
| UI-764 | `#vx-dialog-input` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | `display:none` na samom elementu; vidljiv samo dok je taj modal/overlay otvoren |
| UI-765 | `#vx-dialog-cancel` | Odustani | dugme | `onclick="_vxDlgCancel()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |
| UI-766 | `#vx-dialog-ok` | OK | dugme | (nema inline rukovaoca) | nema definisano dejstvo (nema rukovaoca) | vidljiv samo dok je taj modal/overlay otvoren |

### modal `tos-overlay` (uslovi korišćenja) — 12 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-767 | `#tos-tab-tos` | Uslovi | dugme | `onclick="tosTab('tos')"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo dok je taj modal/overlay otvoren |
| UI-768 | `#tos-tab-privacy` | Privatnost | dugme | `onclick="tosTab('privacy')"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo dok je taj modal/overlay otvoren |
| UI-769 | `#tos-tab-ai` | AI Obrada | dugme | `onclick="tosTab('ai')"` | prebacuje korisnika na drugi ekran/tab | vidljiv samo dok je taj modal/overlay otvoren |
| UI-770 | `a` (index.html:4681) | Puni tekst Uslova korišćenja → | link | `href="/terms"` | vodi na /terms | vidljiv samo dok je taj modal/overlay otvoren |
| UI-771 | `a` (index.html:4730) | Puna Politika privatnosti → | link | `href="/privacy"` | vodi na /privacy | vidljiv samo dok je taj modal/overlay otvoren |
| UI-772 | `a` (index.html:4768) | Puni AI Disclosure dokument → | link | `href="/ai-disclosure"` | vodi na /ai-disclosure | vidljiv samo dok je taj modal/overlay otvoren |
| UI-773 | `a` (index.html:4768) | DPA za poslovne korisnike → | link | `href="/dpa"` | vodi na /dpa | vidljiv samo dok je taj modal/overlay otvoren |
| UI-774 | `#tos-confirm-chk` | uz kontrolu (`<label>` omotač): Potvrđujem da sam pročitao/la Uslove korišćenja i Politiku privatnos | polje | `onchange="tosChkChange()"` | korisnik unosi/bira vrednost — uz kontrolu (`<label>` omotač): Potvrđujem da sam pročitao/la Uslove korišćenja i Politiku privatnos | vidljiv samo dok je taj modal/overlay otvoren |
| UI-775 | `a` (index.html:4777) | Uslove korišćenja | link | `href="/terms"` | vodi na /terms | vidljiv samo dok je taj modal/overlay otvoren |
| UI-776 | `a` (index.html:4777) | Politiku privatnosti | link | `href="/privacy"` | vodi na /privacy | vidljiv samo dok je taj modal/overlay otvoren |
| UI-777 | `button` (index.html:4780) | Odjavi se | dugme | `onclick="tosDecline()"` | izvršava `tosDecline()` | vidljiv samo dok je taj modal/overlay otvoren |
| UI-778 | `#tos-accept-btn` | Prihvatam ✓ | dugme | `onclick="tosAccept()"` | izvršava `tosAccept()` | vidljiv samo dok je taj modal/overlay otvoren |

### modal `data-residency-overlay` — 3 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-779 | `#data-residency-overlay` | Zaštita podataka klijenata ✕ Supabase — Predmeti i klijenti Lokacija: Frankfurt, Nemačka ( | dugme (div) | `onclick="dataResidencyClose()"` | zatvara otvoreni prozor/panel | `display:none` na samom elementu; vidljiv samo dok je taj modal/overlay otvoren |
| UI-780 | `div` (index.html:4791) | Zaštita podataka klijenata ✕ Supabase — Predmeti i klijenti Lokacija: Frankfurt, Nemačka ( | dugme (div) | `onclick="event.stopPropagation()"` | upravlja tajmerom/naplatom vremena | vidljiv samo dok je taj modal/overlay otvoren |
| UI-781 | `button` (index.html:4794) | ✕ | dugme | `onclick="dataResidencyClose()"` | zatvara otvoreni prozor/panel | vidljiv samo dok je taj modal/overlay otvoren |

### dashboard (dinamički) — 37 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-784 | `span` (vindex.js:1307) | Pokušaj ponovo | dugme (span) | `onclick="dash_load()"` | izvršava `dash_load()` | crta se dinamički iz `dash_load()` |
| UI-785 | `button` (vindex.js:1369) | title: Osveži | dugme | `onclick="_healthIndexLoad(null,true)"` | izvršava `_healthIndexLoad()` | crta se dinamički iz `_healthIndexRender()` |
| UI-786 | `span.kc-panel-hd-cta` | Vidi sve → | dugme (span) | `onclick="setTab(document.getElementById(\'tab-btn-p\'),\'p\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_kcPanelAktivni()` |
| UI-787 | `div.kc-panel-row` | aria-label: Otvori predmet '+escHtml(p.naziv\|\|'')+' | dugme (div) | `onclick="_dashGoToPredmet(\''+escHtml(p.id)+'\')"` | izvršava `_dashGoToPredmet()` | crta se dinamički iz `_kcPanelAktivni()` |
| UI-788 | `div.kc-panel-expand` | Još <vrednost> <vrednost> ▾ | dugme (div) | `onclick="setTab(document.getElementById(\'tab-btn-p\'),\'p\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_kcPanelAktivni()` |
| UI-789 | `span.kc-panel-hd-cta` | Vidi sve → | dugme (span) | `onclick="setTab(document.getElementById(\'tab-btn-p\'),\'p\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_kcPanelAktivnosti()` |
| UI-790 | `button.kc-qa-btn` | (dinamički tekst — labela zavisi od podataka) | dugme | `onclick="intakeOtvori()"` | otvara prozor/panel | crta se dinamički iz `_dashRender()` |
| UI-791 | `button.kc-qa-btn` | (dinamički tekst — labela zavisi od podataka) | dugme | `onclick="setTab(document.getElementById(\'tab-btn-k\'),\'k\');setTimeout(crmOtvoriFormu,250)"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_dashRender()` |
| UI-792 | `button.kc-qa-btn` | (dinamički tekst — labela zavisi od podataka) | dugme | `onclick="openAITool(\'a\')"` | otvara prozor/panel | crta se dinamički iz `_dashRender()` |
| UI-793 | `button.kc-qa-btn` | (dinamički tekst — labela zavisi od podataka) | dugme | `onclick="setTab(document.getElementById(\'tab-btn-alati\'),\'alati\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_dashRender()` |
| UI-794 | `div.kc-sphere-quad.clickable` | <vrednost> <vrednost> Aktivnih predmeta | dugme (div) | `onclick="setTab(document.getElementById(\'tab-btn-p\'),\'p\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_dashRender()` |
| UI-795 | `div.kc-sphere-quad.clickable` | 0?' warn':'')+'"><vrednost> 0?' warn':'')+'"><vrednost> Hitnih rokova | dugme (div) | `onclick="setTab(document.getElementById(\'tab-btn-kal\'),\'kal\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_dashRender()` |
| UI-796 | `div.kc-inbox-row` | (dinamički tekst — labela zavisi od podataka) | dugme (div) | `onclick="_dashGoToPredmet(\''+escHtml(item.predmet_id)+'\')"` | izvršava `_dashGoToPredmet()` | crta se dinamički iz `_dashRender()` |
| UI-860 | `#vx-tts-play-btn` | Pročitaj | dugme | `onclick="vx_tts_toggle()"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `_feedbackBar()` |
| UI-861 | `button.feedback-btn` | Generiši nacrt | dugme | `onclick="_generateDraftFromQA()"` | izrada nacrta/podneska | crta se dinamički iz `_feedbackBar()` |
| UI-862 | `#fb-btn` | Prijavi netačan odgovor | dugme | `onclick="sendFeedback(this,\''+p+'\',\''+o+'\')"` | pomoć/podrška i povratna informacija | crta se dinamički iz `_feedbackBar()` |
| UI-889 | `div` (vindex.js:11376) | (dinamički tekst — labela zavisi od podataka) | dugme (div) | `onclick="pred_select(\''+h.predmet_id+'\')"` | izvršava `pred_select()` | crta se dinamički iz `portfolio_render()` |
| UI-949 | `span` (vindex.js:17678) | Pokušaj ponovo | dugme (span) | `onclick="_cioLoad(null,true)"` | izvršava `_cioLoad()` | crta se dinamički iz `_cioLoad()` |
| UI-950 | `button` (vindex.js:17701) | Osvezi | dugme | `onclick="_cioLoad(null,true)"` | izvršava `_cioLoad()` | crta se dinamički iz `_cioRender()` |
| UI-951 | `div` (vindex.js:17748) | (dinamički tekst — labela zavisi od podataka) | dugme (div) | `onclick="_dashGoToPredmet(\''+escHtml(nr.predmet_id\|\|'')+'\')"` | izvršava `_dashGoToPredmet()` | crta se dinamički iz `_cioRender()` |
| UI-952 | `div` (vindex.js:17759) | (dinamički tekst — labela zavisi od podataka) | dugme (div) | `onclick="_dashGoToPredmet(\''+escHtml(zp.predmet_id\|\|'')+'\')"` | izvršava `_dashGoToPredmet()` | crta se dinamički iz `_cioRender()` |
| UI-953 | `div` (vindex.js:17770) | (dinamički tekst — labela zavisi od podataka) | dugme (div) | `onclick="_dashGoToPredmet(\''+escHtml(kr.predmet_id\|\|'')+'\')"` | izvršava `_dashGoToPredmet()` | crta se dinamički iz `_cioRender()` |
| UI-954 | `div` (vindex.js:17785) | (dinamički tekst — labela zavisi od podataka) | dugme (div) | `onclick="_dashGoToPredmet(\''+escHtml(nk.predmet_id\|\|'')+'\')"` | izvršava `_dashGoToPredmet()` | crta se dinamički iz `_cioRender()` |
| UI-955 | `div` (vindex.js:17794) | (dinamički tekst — labela zavisi od podataka) | dugme (div) | `onclick="_dashGoToPredmet(\''+escHtml(ss.predmet_id\|\|'')+'\')"` | izvršava `_dashGoToPredmet()` | crta se dinamički iz `_cioRender()` |
| UI-956 | `div` (vindex.js:17803) | (dinamički tekst — labela zavisi od podataka) | dugme (div) | `onclick="_dashGoToPredmet(\''+escHtml(sp.predmet_id\|\|'')+'\')"` | izvršava `_dashGoToPredmet()` | crta se dinamički iz `_cioRender()` |
| UI-965 | `button.itl-filter-btn'.+.(isActive` | (dinamički tekst — labela zavisi od podataka) | dugme | `onclick="_itlFilter_set(this,\'' + t + '\')"` | izvršava `_itlFilter_set()` | crta se dinamički iz `_itlRender()` |
| UI-968 | `button.smart-chip.'+c.cls+'` | (dinamički tekst — labela zavisi od podataka) | dugme | `onclick="'+c.action+'"` | nema definisano dejstvo (nema rukovaoca) | crta se dinamički iz `_ccc_render()` |
| UI-969 | `button` (vindex.js:19152) | Otvori trezor dokaza → | dugme | `onclick="pred_subtabSwitch(\'dokazi\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_ccc_render()` |
| UI-970 | `button` (vindex.js:19164) | Otvori Naplatu → | dugme | `onclick="pred_subtabSwitch(\'naplata\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_ccc_render()` |
| UI-971 | `button` (vindex.js:19173) | Svi rokovi → | dugme | `onclick="pred_subtabSwitch(\'rokovi\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_ccc_render()` |
| UI-972 | `button` (vindex.js:19178) | Puna hronologija → | dugme | `onclick="pred_subtabSwitch(\'timeline\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_ccc_render()` |
| UI-973 | `button.smart-chip.chip-blue` | Analiza | dugme | `onclick="pred_subtabSwitch(\'ai-analiza\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_ccc_render()` |
| UI-974 | `button.smart-chip` | Strategija | dugme | `onclick="pred_subtabSwitch(\'strategija\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_ccc_render()` |
| UI-975 | `button.smart-chip` | Savetnici | dugme | `onclick="pred_subtabSwitch(\'agenti\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_ccc_render()` |
| UI-976 | `button.smart-chip` | Dokumenti | dugme | `onclick="pred_subtabSwitch(\'dokumenti\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_ccc_render()` |
| UI-977 | `button.smart-chip` | Tajmer | dugme | `onclick="if(typeof billing_timerToggle===\'function\'){if(!_billingPredmetId)_billingPredmetId=activePredmetId;billing_timerToggle();}"` | upravlja tajmerom/naplatom vremena | crta se dinamički iz `_ccc_render()` |
| UI-978 | `button.smart-chip` | Mapa veza | dugme | `onclick="pred_subtabSwitch(\'graf\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_ccc_render()` |

### kartica predmeta (dinamički) — 60 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-819 | `#strat-battle-report-btn` | Generiši Battle Report — kompletna priprema za ročište (3 kredita) | dugme | `onclick="stratBattleReport()"` | pokreće AI analizu | crta se dinamički iz `stratPokreni()` |
| UI-820 | `#strat-confidence-btn` | Proveri pouzdanost predikcije (1 kredit) | dugme | `onclick="stratConfidenceCheck()"` | pokreće AI analizu | crta se dinamički iz `stratPokreni()` |
| UI-821 | `#strat-judge-sud` | placeholder: Sud (npr. Prvi osnovni sud Beograd) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Sud (npr. Prvi osnovni sud Beograd) | crta se dinamički iz `stratPokreni()` |
| UI-822 | `#strat-judge-ime` | placeholder: Ime sudije (opciono) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Ime sudije (opciono) | crta se dinamički iz `stratPokreni()` |
| UI-823 | `button.vx-btn.vx-btn-secondary` | Profil sudije (2 kredita) | dugme | `onclick="stratJudgeProfile()"` | pokreće AI analizu | crta se dinamički iz `stratPokreni()` |
| UI-824 | `#strat-opponent-naziv` | placeholder: Naziv protivničke strane | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Naziv protivničke strane | crta se dinamički iz `stratPokreni()` |
| UI-825 | `#strat-opponent-adv` | placeholder: Advokatska kancelarija (opciono) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Advokatska kancelarija (opciono) | crta se dinamički iz `stratPokreni()` |
| UI-826 | `button.vx-btn.vx-btn-secondary` | Obaveštajni profil protivnika (2 kredita) | dugme | `onclick="stratOpponentIntel()"` | pokreće AI analizu | crta se dinamički iz `stratPokreni()` |
| UI-827 | `#strat-argrep-lista` | placeholder: Argumenti koje planirate da koristite — po jedan u redu | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Argumenti koje planirate da koristite — po jedan u redu | crta se dinamički iz `stratPokreni()` |
| UI-828 | `button.vx-btn.vx-btn-secondary` | Proveri reputaciju argumenata (2 kredita) | dugme | `onclick="stratArgumentReputation()"` | pokreće AI analizu | crta se dinamički iz `stratPokreni()` |
| UI-864 | `button` (vindex.js:8190) | 79€/mes samostalno | dugme | `onclick="event.stopPropagation();pricing_kontakt(\'digitalna_imovina_standalone\')"` | upravlja tajmerom/naplatom vremena | crta se dinamički iz `pgRenderCard()` |
| UI-865 | `button` (vindex.js:8191) | 39€/mes dodatak | dugme | `onclick="event.stopPropagation();pricing_kontakt(\'digitalna_imovina_addon\')"` | upravlja tajmerom/naplatom vremena | crta se dinamički iz `pgRenderCard()` |
| UI-866 | `button` (vindex.js:8224) | <vrednost> funkcija → | dugme | `onclick="pgToggleExpand(this)"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `pgRenderCard()` |
| UI-872 | `button.btn-ics` | ics | dugme | `onclick="dodajUKalendar(\'' + naslov + '\',\'' + rok.konkretan_datum_iso + '\',\'' + opisIcs + '\')"` | rokovi i ročišta | crta se dinamički iz `_rok_build_card()` |
| UI-873 | `button.btn-ics` | Google | dugme | `onclick="otvoriGoogleKalendar(\'' + naslov + '\',\'' + rok.konkretan_datum_iso + '\',\'' + opisIcs + '\')"` | otvara prozor/panel | crta se dinamički iz `_rok_build_card()` |
| UI-874 | `button.btn-ics` | Outlook | dugme | `onclick="otvoriOutlookKalendar(\'' + naslov + '\',\'' + rok.konkretan_datum_iso + '\',\'' + opisIcs + '\')"` | otvara prozor/panel | crta se dinamički iz `_rok_build_card()` |
| UI-878 | `button.vx-error-retry-btn` | Pokušaj ponovo | dugme | `onclick="pred_load()"` | izvršava `pred_load()` | crta se dinamički iz `_predListError()` |
| UI-879 | `button.vx-btn.vx-btn-secondary` | Kreiraj prvi predmet | dugme | `onclick="intakeOtvori()"` | otvara prozor/panel | crta se dinamički iz `pred_renderList()` |
| UI-880 | `#'+p.id+'` | (bez labele) | dugme (tr) | `onclick="pred_select(\''+p.id+'\')"` | izvršava `pred_select()` | crta se dinamički iz `pred_renderList()` |
| UI-881 | `td` (vindex.js:10067) | (bez labele) | dugme (td) | `onclick="event.stopPropagation()"` | upravlja tajmerom/naplatom vremena | crta se dinamički iz `pred_renderList()` |
| UI-882 | `input.pred-chk` | (bez labele) | polje | `onclick="pred_toggleOznaci(\''+p.id+'\')"` | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `pred_renderList()` |
| UI-883 | `div.kanban-card` | <vrednost> <vrednost> '; if | dugme (div) | `onclick="kanban_openPredmet(\''+_htmlEsc(p.id)+'\')"` | otvara prozor/panel | crta se dinamički iz `kanban_render()` |
| UI-884 | `div` (vindex.js:10910) | Otkriven je kritičan rok (možda već prošao) — proverite Rokovi tab → | dugme (div) | `onclick="pred_subtabSwitch(\'rokovi\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `pred_renderCockpit()` |
| UI-885 | `button` (vindex.js:11059) | title: Ukloni saradnika | dugme | `onclick="saradnja_ukloni(\''+escHtml(s.saradnik_user_id)+'\',\''+escHtml(predmetId)+'\',this)"` | saradnja i kancelarija | crta se dinamički iz `saradnja_renderLista()` |
| UI-886 | `#conf-kl-'+i+'` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `pred_renderConfirmCard()` |
| UI-887 | `#conf-rok-0` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `pred_renderConfirmCard()` |
| UI-888 | `button` (vindex.js:11298) | Potvrdi i poveži | dugme | `onclick="pred_confirmLinks('+kIds+','+rData+')"` | izvršava `pred_confirmLinks()` | crta se dinamički iz `pred_renderConfirmCard()` |
| UI-895 | `button.lanac-save-btn` | Sačuvaj u hronologiju predmeta → | dugme | `onclick="lanac_sacuvaj(\''+escHtml(tipVal)+'\',\''+escHtml(datumVal)+'\',this)"` | čuva unete podatke | crta se dinamički iz `lanac_renderResult()` |
| UI-897 | `#cdrow-' + escHtml(dok.id \|\| '') + '` | <vrednost> <vrednost> <vrednost> <vrednost> KB | dugme (div) | `onclick="dokUcitajZaAnalizu(\'' + escHtml(_ns) + '\',\'' + escHtml(dok.naziv_fajla \|\| '') + '\',\'' + escHtml(_kb + '') + '\',\'' + escHtml(dok.id \|\| '') + …"` | pokreće AI analizu | crta se dinamički iz `pred_loadDetail()` |
| UI-898 | `button.vx-btn.vx-btn-ghost` | title: Pogledaj sadržaj | dugme | `onclick="event.stopPropagation();dokPreviewOpen(\'' + escHtml(dok.id \|\| '') + '\',\'' + escHtml(dok.naziv_fajla \|\| '') + '\',\'' + escHtml(_kb + '') + '\')"` | upravlja tajmerom/naplatom vremena | crta se dinamički iz `pred_loadDetail()` |
| UI-899 | `input.pred-dok-item-cb` | title: Označi za cross-doc analizu | polje | `onclick="event.stopPropagation()"` + `onchange="crossdoc_toggleDok(this)"` | korisnik unosi/bira vrednost — title: Označi za cross-doc analizu | crta se dinamički iz `pred_loadDetail()` |
| UI-918 | `button` (vindex.js:13504) | Opozovi | dugme | `onclick="portal_revokeToken(\''+escHtml(t.id)+'\')"` | klijentski portal / portal suda | crta se dinamički iz `portal_loadTokens()` |
| UI-919 | `a` (vindex.js:13557) | Preuzmi | link | `href="'+u.download_url+'"` | vodi na '+u.download_url+' | crta se dinamički iz `portal_loadUploads()` |
| UI-920 | `button` (vindex.js:13558) | Pregledano | dugme | `onclick="portal_oznacPregledano(\''+escHtml(u.id)+'\')"` | klijentski portal / portal suda | crta se dinamički iz `portal_loadUploads()` |
| UI-921 | `button` (vindex.js:13559) | (dinamički tekst — labela zavisi od podataka) | dugme | `onclick="portal_obrisiUpload(\''+escHtml(u.id)+'\')"` | briše stavku | crta se dinamički iz `portal_loadUploads()` |
| UI-957 | `span` (vindex.js:17886) | kada je ažurirano? → | dugme (span) | `onclick="_genomHistoryOpen(\''+escHtml(predmetId\|\|'')+'\')"` | otvara prozor/panel | crta se dinamički iz `_caseDnaRender()` |
| UI-958 | `#genom-detalji-toggle-'+escHtml(predmetId\|\|'')+'` | (dinamički tekst — labela zavisi od podataka) | dugme | `onclick="_genomDetaljiToggle(\''+escHtml(predmetId\|\|'')+'\')"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `_caseDnaRender()` |
| UI-959 | `#genom-verif-toggle-'+escHtml(predmetId\|\|'')+'` | AI provera: <vrednost> <vrednost> — pogledajte pre oslanjanja na ovu procenu (prikaži) | dugme (div) | `onclick="_genomVerifToggle(\''+escHtml(predmetId\|\|'')+'\')"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `_caseDnaRender()` |
| UI-960 | `button` (vindex.js:17975) | istorija | dugme | `onclick="_genomHistoryOpen(\''+escHtml(predmetId\|\|'')+'\')"` | otvara prozor/panel | crta se dinamički iz `_caseDnaRender()` |
| UI-961 | `span.vx-clamp-2` | title: Klikni za pun tekst | dugme (span) | `onclick="this.classList.toggle(\'vx-clamp-2\')"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `_caseDnaRender()` |
| UI-962 | `div` (vindex.js:18013) | <vrednost> <vrednost>% | dugme (div) | `onclick="_genomHeatmapDrill(\''+escHtml(predmetId\|\|'')+'\',\''+k+'\')"` | izvršava `_genomHeatmapDrill()` | crta se dinamički iz `_caseDnaRender()` |
| UI-963 | `span.vx-clamp-2` | title: Klikni za pun tekst | dugme (span) | `onclick="this.classList.toggle(\'vx-clamp-2\')"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `_caseDnaRender()` |
| UI-964 | `span.vx-clamp-2` | title: Klikni za pun tekst | dugme (span) | `onclick="this.classList.toggle(\'vx-clamp-2\')"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `_caseDnaRender()` |
| UI-966 | `button` (vindex.js:18782) | title: Ponovo pokreni AI klasifikaciju ovog dokumenta | dugme | `onclick="evidence_reklasifikuj(\'' + doc.id + '\')"` | izvršava `evidence_reklasifikuj()` | crta se dinamički iz `evidence_load()` |
| UI-967 | `button` (vindex.js:18806) | (dinamički tekst — labela zavisi od podataka) | dugme | `onclick="evidence_deleteDokaz(\'' + dz.id + '\')"` | briše stavku | crta se dinamički iz `evidence_load()` |
| UI-979 | `div.procena-section-hdr'+extraCls+'` | <vrednost> <vrednost> ▾ | dugme (div) | `onclick="this.nextElementSibling.classList.toggle(\'open\')"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `pred_renderProcena()` |
| UI-980 | `div.procena-section-hdr'+extraCls+'` | <vrednost> <vrednost> ▾ | dugme (div) | `onclick="this.nextElementSibling.classList.toggle(\'open\')"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `pred_renderPresuda()` |
| UI-997 | `button.vx-btn.vx-btn-ghost` | Ponovo otvori predmet | dugme | `onclick="pred_reopen(\'' + _htmlEsc(predmetData.id \|\| activePredmetId) + '\')"` | izvršava `pred_reopen()` | crta se dinamički iz `pred_zatvoriRenderSection()` |
| UI-998 | `div` (vindex.js:22441) | <vrednost> ✕ <vrednost> Analiza kancelarije — tip: <vrednost> | dugme (div) | `onclick="if(event.target===this)this.remove()"` | briše stavku | crta se dinamički iz `_outcome_feedback_show()` |
| UI-999 | `button` (vindex.js:22443) | (dinamički tekst — labela zavisi od podataka) | dugme | `onclick="this.closest(\'[style*=fixed]\').remove()"` | izvršava `this.closest()` | crta se dinamički iz `_outcome_feedback_show()` |
| UI-1003 | `button` (vindex.js:22652) | Štampaj / PDF | dugme | `onclick="window.print()"` | izvršava `window.print()` | crta se dinamički iz `ugovor_stampaj()` |
| UI-1004 | `button.eg-gen-btn` | Generisi graf | dugme | `onclick="evidenceGraph_generiši(_egPredmetId)"` | izvršava `evidenceGraph_generiši()` | crta se dinamički iz `evidenceGraph_load()` |
| UI-1007 | `button.vx-kb-move-btn` | (dinamički tekst — labela zavisi od podataka) | dugme | `onclick="zadaci_setStatus(\'' + escHtml(z.id) + '\',\'' + _ZADACI_KOLONE[idx-1].status + '\',' + (opts.isGlobal ? 'true' : 'false') + ')"` | zadaci | crta se dinamički iz `_zadaciCardHtml()` |
| UI-1008 | `button.vx-kb-move-btn` | (dinamički tekst — labela zavisi od podataka) | dugme | `onclick="zadaci_setStatus(\'' + escHtml(z.id) + '\',\'' + _ZADACI_KOLONE[idx+1].status + '\',' + (opts.isGlobal ? 'true' : 'false') + ')"` | zadaci | crta se dinamički iz `_zadaciCardHtml()` |
| UI-1009 | `button.vx-kb-move-btn` | title: Obriši | dugme | `onclick="zadaci_obrisi(\'' + escHtml(z.id) + '\',' + (opts.isGlobal ? 'true' : 'false') + ')"` | briše stavku | crta se dinamički iz `_zadaciCardHtml()` |
| UI-1010 | `div.vx-card` | (dinamički tekst — labela zavisi od podataka) | dugme (div) | `onclick="workflow_pokreni(\'' + t.id + '\',\'' + escHtml(t.naziv).replace(/'/g,"` | izvršava `workflow_pokreni()` | crta se dinamički iz `_workflowUcitajPredloske()` |
| UI-1011 | `button.vx-btn.vx-btn-primary` | Završi korak | dugme | `onclick="workflow_zavrsiKorak(\'' + k.id + '\')"` | kreiranje novog predmeta | crta se dinamički iz `_workflowRenderKoraci()` |
| UI-1012 | `a` (vindex.js:23399) | (dinamički tekst — labela zavisi od podataka) | link | `onclick="_workflowGoToPredmet(\'' + k.predmet_id + '\')"` | izvršava `_workflowGoToPredmet()` | crta se dinamički iz `workflow_eskalacije_load()` |
| UI-1013 | `button` (vindex.js:23621) | Proveri | dugme | `onclick="portalManualUpdate(\'' + p.id + '\',this)"` | klijentski portal / portal suda | crta se dinamički iz `portalUcitajListu()` |
| UI-1014 | `button` (vindex.js:23622) | Ukloni | dugme | `onclick="portalUkloni(\'' + p.id + '\')"` | klijentski portal / portal suda | crta se dinamički iz `portalUcitajListu()` |

### tab Klijenti (dinamički) — 4 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-832 | `tr.vx-grid-row` | (bez labele) | dugme (tr) | `onclick="crmOtvoriProfil(\''+_htmlEsc(k.id)+'\')"` | otvara prozor/panel | crta se dinamički iz `ucitajKlijente()` |
| UI-833 | `#crm-twin-analiziraj-btn` | (dinamički tekst — labela zavisi od podataka) | dugme | `onclick="crmAnaliziranjeTwin(\'' + klijentId + '\')"` | pokreće AI analizu | crta se dinamički iz `_crmRenderTwin()` |
| UI-834 | `a.crm-btn-edit` | Preuzmi | link | `href="/klijenti/'+_htmlEsc(klijentId)+'/dokumenti/'+_htmlEsc(doc.id)+'/download"` | vodi na /klijenti/'+_htmlEsc(klijentId)+'/dokumenti/'+_htmlEsc(doc.id)+'/download | crta se dinamički iz `crmUcitajDokumente()` |
| UI-996 | `div.intake-klijent-result` | <vrednost> <vrednost> ' : '') | dugme (div) | `onclick="qiKlijentIzaberi(\''+k.id+'\',\''+escHtml(name)+'\')"` | rad sa klijentima | crta se dinamički iz `qiKlijentSearch()` |

### modal Intake / Novi predmet iz dokumenta (dinamički) — 16 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-941 | `div` (vindex.js:15426) | (dinamički tekst — labela zavisi od podataka) | dugme (div) | `onclick="intakeTemplateIzaberi(\''+_htmlEsc(t.id)+'\',\''+_htmlEsc(t.naziv)+'\')"` | kreiranje novog predmeta | crta se dinamički iz `_intakeRenderTpl()` |
| UI-981 | `button` (vindex.js:20709) | Kreiraj prvi predmet | dugme | `onclick="intakeOtvori()"` | otvara prozor/panel | crta se dinamički iz `intakeHistoryLoad()` |
| UI-982 | `div` (vindex.js:20719) | (dinamički tekst — labela zavisi od podataka) | dugme (div) | `onclick="intakeHistOtvoriPredmet(\''+escHtml(it.id)+'\')"` | otvara prozor/panel | crta se dinamički iz `intakeHistoryLoad()` |
| UI-983 | `div.intake-klijent-result'.+.(k.id` | <vrednost> <vrednost> ' : '') | dugme (div) | `onclick="intakeKlijentSelect(\'' + k.id + '\',\'' + (name.replace(/'/g,"` | rad sa klijentima | crta se dinamički iz `intakeKlijentSearch()` |
| UI-984 | `button.intake-file-rm` | title: Ukloni fajl | dugme | `onclick="intakeRemoveFile(' + i + ')"` | kreiranje novog predmeta | crta se dinamički iz `_intakeRenderFileList()` |
| UI-985 | `span` (vindex.js:21548) | (dinamički tekst — labela zavisi od podataka) | dugme (span) | `onclick="siRemoveFile(' + idx + ')"` | kreiranje novog predmeta | crta se dinamički iz `_siRenderFilesList()` |
| UI-986 | `#si-f-naziv` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `_siRenderReview()` |
| UI-987 | `input` (vindex.js:21727) | (bez labele) | polje | `onchange="_siKlijentStrana=\'plaintiff\'"` | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `_siRenderReview()` |
| UI-988 | `input` (vindex.js:21729) | (bez labele) | polje | `onchange="_siKlijentStrana=\'defendant\'"` | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `_siRenderReview()` |
| UI-989 | `input` (vindex.js:21731) | (bez labele) | polje | `onchange="_siKlijentStrana=null"` | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `_siRenderReview()` |
| UI-990 | `#si-f-klijent` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `_siRenderReview()` |
| UI-991 | `#si-ent-' + escHtml(ent.entity_id) + '` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `_siRenderReview()` |
| UI-992 | `button` (vindex.js:21755) | Sačuvaj | dugme | `onclick="siCorrectEntity(\'' + escHtml(ent.entity_id) + '\')"` | kreiranje novog predmeta | crta se dinamički iz `_siRenderReview()` |
| UI-993 | `button.intake-next-btn` | Nastavi na predmet → | dugme | `onclick="siGoToPredmet(\'' + predmetId + '\')"` | kreiranje novog predmeta | crta se dinamički iz `_siShowRecap()` |
| UI-994 | `button` (vindex.js:21993) | Odobri | dugme | `onclick="stagingApprove(\'' + escHtml(s.id) + '\')"` | izvršava `stagingApprove()` | crta se dinamički iz `_stagingRender()` |
| UI-995 | `button` (vindex.js:21994) | Odbij | dugme | `onclick="stagingReject(\'' + escHtml(s.id) + '\')"` | izvršava `stagingReject()` | crta se dinamički iz `_stagingRender()` |

### naplata / fakture (dinamički) — 18 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-814 | `div` (vindex.js:2526) | <vrednost> <vrednost> <vrednost> stavk | dugme (div) | `onclick="pred_select(\''+g.predmet_id+'\')"` | izvršava `pred_select()` | crta se dinamički iz `billingDugovanjaLoad()` |
| UI-858 | `button.tarife-reset-btn` | x21BA | dugme | `onclick="tarife_resetStavka(\''+s.sifra+'\')"` | naplata i fakturisanje | crta se dinamički iz `tarife_renderStavke()` |
| UI-859 | `input.tarife-stavka-iznos` | placeholder: '+s.aks_iznos+' | polje | `onchange="tarife_saveStavka(\''+s.sifra+'\', this.value)"` | korisnik unosi/bira vrednost — placeholder: '+s.aks_iznos+' | crta se dinamički iz `tarife_renderStavke()` |
| UI-900 | `button.billing-del-btn` | title: Obriši | dugme | `onclick="billing_deleteEntry(\''+e.id+'\')"` | briše stavku | crta se dinamički iz `billing_loadEntries()` |
| UI-901 | `button.billing-faktura-btn` | Generiši fakturu (<vrednost> stavki · <vrednost> RSD) | dugme | `onclick="billing_generateFakturaPanel()"` | naplata i fakturisanje | crta se dinamički iz `billing_loadEntries()` |
| UI-902 | `#bf-klijent` | placeholder: Naziv klijenta * | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Naziv klijenta * | crta se dinamički iz `billing_generateFakturaPanel()` |
| UI-903 | `#bf-adresa` | placeholder: Adresa klijenta (opciono) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: Adresa klijenta (opciono) | crta se dinamički iz `billing_generateFakturaPanel()` |
| UI-904 | `#bf-pib` | placeholder: PIB | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: PIB | crta se dinamički iz `billing_generateFakturaPanel()` |
| UI-905 | `#bf-pdv` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `billing_generateFakturaPanel()` |
| UI-906 | `button.billing-faktura-btn` | Kreiraj fakturu | dugme | `onclick="billing_doGenerateFaktura()"` | naplata i fakturisanje | crta se dinamički iz `billing_generateFakturaPanel()` |
| UI-907 | `button` (vindex.js:13079) | Otkaži | dugme | `onclick="billing_loadEntries()"` | naplata i fakturisanje | crta se dinamički iz `billing_generateFakturaPanel()` |
| UI-908 | `a` (vindex.js:13111) | Preuzmi PDF | link | `href="'+pdfUrl+'"` | vodi na '+pdfUrl+' | crta se dinamički iz `billing_doGenerateFaktura()` |
| UI-909 | `button` (vindex.js:13112) | Email | dugme | `onclick="billing_sendEmail(\''+escHtml(fakt.id)+'\')"` | naplata i fakturisanje | crta se dinamički iz `billing_doGenerateFaktura()` |
| UI-910 | `button` (vindex.js:13113) | SEF | dugme | `onclick="sef_posalji(\''+escHtml(fakt.id)+'\')"` | izvršava `sef_posalji()` | crta se dinamički iz `billing_doGenerateFaktura()` |
| UI-911 | `button` (vindex.js:13114) | XML | dugme | `onclick="sef_preuzmiXml(\''+escHtml(fakt.id)+'\')"` | izvozi/preuzima dokument | crta se dinamički iz `billing_doGenerateFaktura()` |
| UI-912 | `button` (vindex.js:13115) | SEF log | dugme | `onclick="sef_prikaziLog(\''+escHtml(fakt.id)+'\')"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `billing_doGenerateFaktura()` |
| UI-913 | `button` (vindex.js:13158) | Generiši | dugme | `onclick="billing_generiši(\''+escHtml(t.id)+'\')"` | naplata i fakturisanje | crta se dinamički iz `billing_loadRecurring()` |
| UI-914 | `button` (vindex.js:13159) | title: '+(t.aktivan?'Deaktiviraj':'Aktiviraj')+' | dugme | `onclick="billing_deactivateRecurring(\''+escHtml(t.id)+'\','+t.aktivan+')"` | naplata i fakturisanje | crta se dinamički iz `billing_loadRecurring()` |

### sudska praksa / pretraga (dinamički) — 7 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-844 | `div` (vindex.js:6242) | (dinamički tekst — labela zavisi od podataka) | dugme (div) | `onclick="_sud_select(' + JSON.stringify(s.naziv) + ',' + JSON.stringify(s.adresa) + ')"` | izvršava `_sud_select()` | crta se dinamički iz `_sud_filter()` |
| UI-845 | `a.glasnik-link` | 1 | link | `href="https://www.pravno-informacioni-sistem.rs/"` | vodi na https://www.pravno-informacioni-sistem.rs/ | crta se dinamički iz `_linkGlasnik()` |
| UI-863 | `button` (vindex.js:8141) | (dinamički tekst — labela zavisi od podataka) | dugme | `onclick="pricing_kontakt(\'' + t.id + '\')"` | izvršava `pricing_kontakt()` | crta se dinamički iz `ptRenderCard()` |
| UI-867 | `#praksa-expand-btn-' + idx + '` | Prikaži odluku | dugme | `onclick="praksa_expand_decision(' + idx + ')"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `praksa_render_card()` |
| UI-868 | `button` (vindex.js:8392) | Kopiraj citiranje | dugme | `onclick="praksa_copy_citation(\'' + jsDn + '\',\'' + dateStr + '\',\'' + jsCourt + '\')"` | kopira tekst u ostavu | crta se dinamički iz `praksa_render_card()` |
| UI-869 | `input.compare-check` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `praksa_render_card()` |
| UI-870 | `div.pg-group-header.'.+` | <vrednost> <vrednost> <vrednost> odluka ▾ | dugme (div) | `onclick="var el=document.getElementById(\'' + gid + '\');el.style.display=el.style.display===\'none\'?\'block\':\'none\';"` | izvršava `document.getElementById()` | crta se dinamički iz `praksa_render_grupisano()` |

### administracija (dinamički) — 20 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-871 | `div.fa-legacy-toggle` | Plain-text rezime (kompatibilnost) | dugme (div) | `onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display===\'none\'?\'block\':\'none\'"` | nema definisano dejstvo (nema rukovaoca) | crta se dinamički iz `renderForenzickiAudit()` |
| UI-924 | `#fr-plan-' + key + '` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `adminFeatureRegistryRender()` |
| UI-925 | `#fr-addon-' + key + '` | placeholder: — | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: — | crta se dinamički iz `adminFeatureRegistryRender()` |
| UI-926 | `#fr-krediti-' + key + '` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `adminFeatureRegistryRender()` |
| UI-927 | `#fr-dnevni-' + key + '` | placeholder: ∞ | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: ∞ | crta se dinamički iz `adminFeatureRegistryRender()` |
| UI-928 | `#fr-mesecni-' + key + '` | placeholder: ∞ | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: ∞ | crta se dinamički iz `adminFeatureRegistryRender()` |
| UI-929 | `button.vx-btn.vx-btn-ghost` | (dinamički tekst — labela zavisi od podataka) | dugme | `onclick="adminFeatureRegistryToggle(\'' + key + '\')"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `adminFeatureRegistryRender()` |
| UI-930 | `button.settings-btn` | Sačuvaj | dugme | `onclick="adminFeatureRegistrySave(\'' + key + '\')"` | čuva unete podatke | crta se dinamički iz `adminFeatureRegistryRender()` |
| UI-931 | `button.vx-btn.vx-btn-ghost` | Više ▾ | dugme | `onclick="adminFeatureRegistryToggleMore(\'' + key + '\')"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `adminFeatureRegistryRender()` |
| UI-932 | `#fr-cooldown-' + key + '` | placeholder: — | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: — | crta se dinamički iz `adminFeatureRegistryRender()` |
| UI-933 | `#fr-priority-' + key + '` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `adminFeatureRegistryRender()` |
| UI-934 | `#fr-status-' + key + '` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `adminFeatureRegistryRender()` |
| UI-935 | `#fr-visible-' + key + '` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `adminFeatureRegistryRender()` |
| UI-936 | `#fr-version-' + key + '` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `adminFeatureRegistryRender()` |
| UI-937 | `#fr-cost-' + key + '` | placeholder: — | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — placeholder: — | crta se dinamički iz `adminFeatureRegistryRender()` |
| UI-938 | `button.vx-btn.vx-btn-ghost` | Istorija izmena | dugme | `onclick="adminFeatureRegistryHistory(\'' + key + '\')"` | administrativna radnja | crta se dinamički iz `adminFeatureRegistryRender()` |
| UI-939 | `button` (vindex.js:15007) | Retry | dugme | `onclick="adminNotifRetry(\'' + n.id + '\',this)"` | notifikacije | crta se dinamički iz `adminNotifLoad()` |
| UI-940 | `button` (vindex.js:15220) | (dinamički tekst — labela zavisi od podataka) | dugme | `onclick="lawDelete(\''+z.id+'\',\''+_htmlEsc(z.naziv)+'\')"` | briše stavku | crta se dinamički iz `lawListLoad()` |
| UI-945 | `a` (vindex.js:15940) | (dinamički tekst — labela zavisi od podataka) | link | `href="mailto:' + escHtml(p.email) + '"` | vodi na mailto:' + escHtml(p.email) + ' | crta se dinamički iz `_wl_admin_render()` |
| UI-946 | `select` (vindex.js:15945) | (bez labele) | polje | `onchange="wl_admin_set_status(\'' + p.id + '\', this.value)"` | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `_wl_admin_render()` |

### notifikacije (dinamički) — 5 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-890 | `button.vx-btn.vx-btn-ghost` | title: Osveži | dugme | `onclick="notif_load()"` | notifikacije | crta se dinamički iz `notif_render()` |
| UI-891 | `button.vx-btn.vx-btn-ghost` | Označi sve | dugme | `onclick="notif_markAllRead()"` | notifikacije | crta se dinamički iz `notif_render()` |
| UI-892 | `div.vx-notif-item` | (dinamički tekst — labela zavisi od podataka) | dugme (div) | `onclick="notif_click(this,\''+escHtml(n.id)+'\',\''+escHtml(n.predmet_id\|\|'')+'\')"` | notifikacije | crta se dinamički iz `notif_render()` |
| UI-893 | `button` (vindex.js:11610) | Označi sve | dugme | `onclick="notif_markAllRead()"` | notifikacije | crta se dinamički iz `mobNotifOtvori()` |
| UI-894 | `div.vx-notif-item` | (dinamički tekst — labela zavisi od podataka) | dugme (div) | `onclick="notif_click(this,\''+escHtml(n.id)+'\',\''+escHtml(n.predmet_id\|\|'')+'\')"` | notifikacije | crta se dinamički iz `mobNotifOtvori()` |

### kalendar (dinamički) — 2 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-922 | `button.kal-ev-del` | title: Obriši | dugme | `onclick="event.stopPropagation();rocisteObrisi(\'' + _kalEsc(det.id) + '\')"` | upravlja tajmerom/naplatom vremena | crta se dinamički iz `_kalendarRender()` |
| UI-923 | `div.kal-grid-cell'.+.hasCls` | <vrednost> '; evs.slice(0, 3).forEach(function(e) { var col = e.tip === 'ro | dugme (div) | `onclick="kalDayClick(\'' + iso + '\')"` | rokovi i ročišta | crta se dinamički iz `_kalRenderGrid()` |

### komandna paleta (dinamički) — 3 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-915 | `div.gs-item` | (dinamički tekst — labela zavisi od podataka) | dugme (div) | `onclick="cmdkClose();(function(){'+_askAi.action+'})()"` | zatvara otvoreni prozor/panel | crta se dinamički iz `cmdkRender()` |
| UI-916 | `div.gs-item` | (dinamički tekst — labela zavisi od podataka) | dugme (div) | `onclick="cmdkClose();(function(){'+a.action+'})()"` | zatvara otvoreni prozor/panel | crta se dinamički iz `cmdkRender()` |
| UI-917 | `div.gs-item` | <vrednost> <vrednost> <vrednost> ' : '') | dugme (div) | `onclick="cmdkSelect('+i+')"` | komandna paleta | crta se dinamički iz `cmdkRender()` |

### Digitalna imovina / moduli (dinamički) — 13 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-810 | `button.strat-btn` | (dinamički tekst — labela zavisi od podataka) | dugme | `onclick="web3IzaberiModul(\'' + m + '\',this)"` | digitalna imovina / usklađenost | crta se dinamički iz `_dimEnterLevel2()` |
| UI-811 | `button.settings-btn` | Otvori modul | dugme | `onclick="' + (typeof _dimOpenModul === 'function' ? '_dimOpenModul()' : '') + '"` | digitalna imovina / usklađenost | crta se dinamički iz `dimModuleCardRender()` |
| UI-812 | `button.settings-btn` | Zatražite aktivaciju — 39€/mes | dugme | `onclick="pricing_kontakt(\'digitalna_imovina_addon\')"` | izvršava `pricing_kontakt()` | crta se dinamički iz `dimModuleCardRender()` |
| UI-813 | `button.settings-btn` | Pogledajte cene — od 39€/mes | dugme | `onclick="openProModal()"` | otvara prozor/panel | crta se dinamički iz `dimModuleCardRender()` |
| UI-835 | `div.sc-section-head.sc-collapsible` | Administrativna ovlašćenja <vrednost> ▾ | dugme (div) | `onclick="scToggle(this)"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `web3RenderSmartContract()` |
| UI-836 | `div.sc-section-head.sc-collapsible` | Analiza centralizacije <vrednost> ▾ | dugme (div) | `onclick="scToggle(this)"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `web3RenderSmartContract()` |
| UI-837 | `div.sc-section-head.sc-collapsible` | Ključne radnje ▾ | dugme (div) | `onclick="scToggle(this)"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `web3RenderSmartContract()` |
| UI-838 | `div.sc-section-head.sc-collapsible` | Pravni indikatori ▾ | dugme (div) | `onclick="scToggle(this)"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `web3RenderSmartContract()` |
| UI-839 | `div.sc-section-head.sc-collapsible` | AML/KYC <vrednost> ▾ | dugme (div) | `onclick="scToggle(this)"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `web3RenderSmartContract()` |
| UI-840 | `div.sc-section-head.sc-collapsible` | Klasifikacija tokena ▾ | dugme (div) | `onclick="scToggle(this)"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `web3RenderSmartContract()` |
| UI-841 | `div.sc-section-head.sc-collapsible` | Regulatorna relevantnost ▾ | dugme (div) | `onclick="scToggle(this)"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `web3RenderSmartContract()` |
| UI-842 | `div.sc-section-head.sc-collapsible` | Off-chain zavisnosti (<vrednost>) ▸ | dugme (div) | `onclick="scToggle(this)"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `web3RenderSmartContract()` |
| UI-843 | `div.sc-section-head.sc-collapsible` | Limitacije analize ▸ | dugme (div) | `onclick="scToggle(this)"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `web3RenderSmartContract()` |

### kancelarija / poslovna inteligencija (dinamički) — 9 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-797 | `span` (vindex.js:1774) | Pokušaj ponovo | dugme (span) | `onclick="wsLoad()"` | izvršava `wsLoad()` | crta se dinamički iz `wsLoad()` |
| UI-798 | `div.kc-inbox-row` | <vrednost> <vrednost> · <vrednost> | dugme (div) | `onclick="'+clickAttr+'"` | nema definisano dejstvo (nema rukovaoca) | crta se dinamički iz `_wsRender()` |
| UI-799 | `div.kc-panel-expand` | Još <vrednost> <vrednost> ▾ | dugme (div) | `onclick="setTab(document.getElementById(\'tab-btn-p\'),\'p\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_wsRender()` |
| UI-815 | `select` (vindex.js:2767) | (bez labele) | polje | `onchange="kancPromeniUlogu(\''+c.id+'\',this.value)"` | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `_kancRenderClanovi()` |
| UI-816 | `button` (vindex.js:2769) | Suspenduj | dugme | `onclick="kancSuspenduj(\''+c.id+'\',\''+c.email+'\')"` | saradnja i kancelarija | crta se dinamički iz `_kancRenderClanovi()` |
| UI-817 | `button` (vindex.js:2771) | Reaktiviraj | dugme | `onclick="kancReaktiviraj(\''+c.id+'\',\''+c.email+'\')"` | saradnja i kancelarija | crta se dinamički iz `_kancRenderClanovi()` |
| UI-818 | `button` (vindex.js:2773) | (dinamički tekst — labela zavisi od podataka) | dugme | `onclick="kancUkloni(\''+c.id+'\',\''+c.email+'\')"` | saradnja i kancelarija | crta se dinamički iz `_kancRenderClanovi()` |
| UI-947 | `button.pi-ftab'+(i===_piFunnelIdx?'.active':'')+'` | (dinamički tekst — labela zavisi od podataka) | tab | `onclick="_piSelectFunnel('+i+')"` | izvršava `_piSelectFunnel()` | crta se dinamički iz `_piRenderFunnels()` |
| UI-948 | `select.pi-period-sel` | (bez labele) | polje | `onchange="piReloadFeatures(this.value)"` | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `piLoad()` |

### šabloni dokumenata (dinamički) — 1 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-942 | `#doctpl-item-'+i+'` | (dinamički tekst — labela zavisi od podataka) | dugme (div) | `onclick="docTplIzaberi('+i+')"` | izvršava `docTplIzaberi()` | crta se dinamički iz `_doctplRenderLista()` |

### razno / pomoćni paneli (dinamički) — 35 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-782 | `button` (vindex.js:480) | a real-world pattern in this codebase, // not something worth rewriting wholesale this spr | dugme | (nema inline rukovaoca) | nema definisano dejstvo (nema rukovaoca) | crta se dinamički iz `wl_submit()` |
| UI-783 | `button.vx-error-retry-btn` | Pokušaj ponovo | dugme | (nema inline rukovaoca) | nema definisano dejstvo (nema rukovaoca) | crta se dinamički iz `showUserError()` |
| UI-800 | `div.vx2-sat.vx2-sat-n` | <vrednost> rokova | dugme (div) | `onclick="setTab(document.getElementById(\'tab-btn-kal\'),\'kal\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_vx2_stub_start()` |
| UI-801 | `div.vx2-sat.vx2-sat-e` | <vrednost> predmeta | dugme (div) | `onclick="setTab(document.getElementById(\'tab-btn-p\'),\'p\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_vx2_stub_start()` |
| UI-802 | `div.vx2-sat.vx2-sat-w` | klijenti | dugme (div) | `onclick="setTab(document.getElementById(\'tab-btn-k\'),\'k\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_vx2_stub_start()` |
| UI-803 | `div.vx2-sphere` | VINDEX CORE | dugme (div) | `onclick="vxCoreQuickActions()"` | izvršava `vxCoreQuickActions()` | crta se dinamički iz `_vx2_stub_start()` |
| UI-804 | `div.vx2-panel'+(predWarn?'.has-warn':'')+.'` | Predmeti <vrednost> <vrednost> aktivna | dugme (div) | `onclick="setTab(document.getElementById(\'tab-btn-p\'),\'p\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_vx2_stub_start()` |
| UI-805 | `div.vx2-panel` | Klijenti — Baza klijenata kancelarije Otvori → | dugme (div) | `onclick="setTab(document.getElementById(\'tab-btn-k\'),\'k\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_vx2_stub_start()` |
| UI-806 | `div.vx2-panel'+(rokWarn?'.has-warn':'')+.'` | Rokovi <vrednost> <vrednost> ove ned. | dugme (div) | `onclick="setTab(document.getElementById(\'tab-btn-kal\'),\'kal\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_vx2_stub_start()` |
| UI-807 | `div.vx2-panel` | Centar alata 847 zakona RS Istraži zakon ☐ Analiziraj d | dugme (div) | `onclick="setTab(document.getElementById(\'tab-btn-alati\'),\'alati\')"` | prebacuje korisnika na drugi ekran/tab | crta se dinamički iz `_vx2_stub_start()` |
| UI-808 | `button.vx2-panel-ai-btn` | Istraži zakon | dugme | `onclick="event.stopPropagation();openAITool(\'q\')"` | upravlja tajmerom/naplatom vremena | crta se dinamički iz `_vx2_stub_start()` |
| UI-809 | `button.vx2-panel-ai-btn` | Analiziraj dokument | dugme | `onclick="event.stopPropagation();openAITool(\'a\')"` | upravlja tajmerom/naplatom vremena | crta se dinamički iz `_vx2_stub_start()` |
| UI-829 | `button.btn-danger-small` | Opozovi | dugme | `onclick="opoziviApiKljuc(\'' + k.id + '\')"` | izvršava `opoziviApiKljuc()` | crta se dinamički iz `ucitajApiKljuceve()` |
| UI-830 | `button.btn-word` | Kopiraj | dugme | `onclick="navigator.clipboard.writeText(\'' + data.kljuc + '\');showToast(\'Ključ kopiran\')"` | izvršava `navigator.clipboard.writeText()` | crta se dinamički iz `kreirajApiKljuc()` |
| UI-831 | `button.kom-btn-del` | Obriši | dugme | `onclick="obrisiKomentar(\''+_htmlEsc(k.id)+'\')"` | briše stavku | crta se dinamički iz `ucitajKomentare()` |
| UI-846 | `button.citat-toggle` | Prikaži ceo tekst ▼ | dugme | `onclick="toggleCitat(\'' + uid + '\',this)"` | prikazuje ili sakriva deo ekrana | crta se dinamički iz `formatResponse()` |
| UI-847 | `button.resp-action-btn` | Kopiraj citat | dugme | `onclick="copyToClipboard(decodeURIComponent(\'' +citatEnc+ '\'),this)"` | kopira tekst u ostavu | crta se dinamički iz `formatResponse()` |
| UI-848 | `button.resp-action-btn` | Izvor: <vrednost> | dugme | `onclick="copyToClipboard(decodeURIComponent(\'' +osnovEnc+ '\'),this)"` | kopira tekst u ostavu | crta se dinamički iz `formatResponse()` |
| UI-849 | `button.resp-action-btn` | Sačuvaj PDF | dugme | `onclick="exportPDF(decodeURIComponent(\'' +fullEnc+ '\'),this)"` | izvozi/preuzima dokument | crta se dinamički iz `formatResponse()` |
| UI-850 | `button.resp-action-btn.btn-word` | Word | dugme | `onclick="exportujKaoWord(\'Pravno istraživanje\',_lastRawText,\'istrazivanje\')"` | izvozi/preuzima dokument | crta se dinamički iz `formatResponse()` |
| UI-851 | `#followUpBtn_'+Date.now()+'` | Follow-up | dugme | `onclick="startFollowUp(this)"` | upravlja tajmerom/naplatom vremena | crta se dinamički iz `formatResponse()` |
| UI-852 | `button` (vindex.js:7162) | Email — formalni, sa pozdravom | dugme | (nema inline rukovaoca) | nema definisano dejstvo (nema rukovaoca) | crta se dinamički iz `sazimiZaKlijenta()` |
| UI-853 | `button` (vindex.js:7163) | Viber — kratak, neformalan (3-4 rečenice) | dugme | (nema inline rukovaoca) | nema definisano dejstvo (nema rukovaoca) | crta se dinamički iz `sazimiZaKlijenta()` |
| UI-854 | `button` (vindex.js:7164) | Pisano obaveštenje — zvanično pismo | dugme | (nema inline rukovaoca) | nema definisano dejstvo (nema rukovaoca) | crta se dinamički iz `sazimiZaKlijenta()` |
| UI-855 | `button` (vindex.js:7166) | Odustani | dugme | `onclick="this.closest(\'[style*=fixed]\').remove()"` | izvršava `this.closest()` | crta se dinamički iz `sazimiZaKlijenta()` |
| UI-856 | `button` (vindex.js:7199) | Kopiraj tekst | dugme | `onclick="navigator.clipboard.writeText(' + JSON.stringify(sazetak) + ').then(function(){this.textContent=\'✓ Kopirano!\';}.bind(this))"` | izvršava `navigator.clipboard.writeText()` | crta se dinamički iz `_doSazmi()` |
| UI-857 | `button` (vindex.js:7200) | Zatvori | dugme | `onclick="this.closest(\'[style*=fixed]\').remove()"` | izvršava `this.closest()` | crta se dinamički iz `_doSazmi()` |
| UI-875 | `button.btn-ics` | ics | dugme | `onclick="dodajUKalendar(\'' + _zastNaslov + '\',\'' + d.datum_zastarelosti_iso + '\',\'' + _zastOsnov + '\')"` | rokovi i ročišta | crta se dinamički iz `kalkulisiZastarelost()` |
| UI-876 | `button.btn-ics` | Google | dugme | `onclick="otvoriGoogleKalendar(\'' + _zastNaslov + '\',\'' + d.datum_zastarelosti_iso + '\',\'' + _zastOsnov + '\')"` | otvara prozor/panel | crta se dinamički iz `kalkulisiZastarelost()` |
| UI-877 | `button.btn-ics` | Outlook | dugme | `onclick="otvoriOutlookKalendar(\'' + _zastNaslov + '\',\'' + d.datum_zastarelosti_iso + '\',\'' + _zastOsnov + '\')"` | otvara prozor/panel | crta se dinamički iz `kalkulisiZastarelost()` |
| UI-1000 | `button` (vindex.js:22625) | x2715 | dugme | `onclick="document.getElementById(\'ugovor-result-modal\').remove()"` | izvršava `document.getElementById()` | crta se dinamički iz `overlay.onclick()` |
| UI-1001 | `#uz-copy-btn` | Kopiraj tekst | dugme | `onclick="ugovor_kopiraj()"` | kopira tekst u ostavu | crta se dinamički iz `overlay.onclick()` |
| UI-1002 | `button` (vindex.js:22632) | Štampaj / PDF | dugme | `onclick="ugovor_stampaj()"` | izrada nacrta/podneska | crta se dinamički iz `overlay.onclick()` |
| UI-1005 | `button.eg-regen-btn` | x21BA; Regenerisi | dugme | `onclick="evidenceGraph_generiši(_egPredmetId)"` | izvršava `evidenceGraph_generiši()` | crta se dinamički iz `overlay.onclick()` |
| UI-1006 | `button.eg-close-btn` | x2715 | dugme | `onclick="document.getElementById(\'eg-modal\').remove()"` | izvršava `document.getElementById()` | crta se dinamički iz `overlay.onclick()` |

### dinamički (vindex.js) — nesvrstano — 3 elemenata

| ID | Selektor | Labela | Vrsta | Rukovalac | Namena | Uslovno prikazan? |
|---|---|---|---|---|---|---|
| UI-896 | `button.vx-btn.vx-btn-secondary` | <vrednost> → | dugme | `onclick="'+_akcijaDef.fn+'"` | nema definisano dejstvo (nema rukovaoca) | crta se dinamički iz `copilot_renderResponse()` |
| UI-943 | `#dtf-'+f+'` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `fieldsEl.innerHTML()` |
| UI-944 | `#dtf-'+f+'` | (bez labele) | polje | (bez inline rukovaoca — vrednost se čita iz JS-a) | korisnik unosi/bira vrednost — polje bez opisa | crta se dinamički iz `fieldsEl.innerHTML()` |

## 4. Grupisanje po funkciji

Grupisanje je *ulaz za agenta koji traži duplikate* — ovde se ne donosi zaključak da je nešto duplikat.

| Funkcionalna grupa | Broj elemenata |
|---|---|
| Polja za unos (forme) | 185 |
| Navigacija (tabovi i ekrani) | 110 |
| Lista predmeta i rad na predmetu | 65 |
| Izrada dokumenata i nacrta | 54 |
| AI analiza i procena predmeta | 52 |
| Kreiranje novog predmeta (Intake) | 48 |
| Tehničke kontrole (zaustavi klik, zatvori panel, okini skriveno polje) | 47 |
| Klijenti (CRM) | 44 |
| Naplata, tajmer i finansije | 35 |
| Rokovi, ročišta i kalendar | 33 |
| Pretraga i pravni upiti | 21 |
| Ostalo / nesvrstano | 20 |
| Spoljni i pomoćni linkovi | 20 |
| Komandna paleta / brze akcije | 19 |
| Digitalna imovina / usklađenost | 19 |
| Nalog i prijava | 18 |
| Pomoć, podrška i povratna informacija | 18 |
| Glasovna interakcija | 16 |
| Dashboard i poslovna inteligencija | 16 |
| Saradnja i kancelarija | 16 |
| Plan, pretplata i krediti | 14 |
| Notifikacije | 14 |
| Podešavanja i integracije | 14 |
| Dokumenti i otpremanje | 14 |
| Izvoz, štampa i poređenje | 14 |
| Portali (klijentski / portal suda) | 14 |
| Bez rukovaoca (statički / vezan iz JS-a) | 14 |
| Zadaci i workflow | 12 |
| Administracija | 11 |
| Pravni pristanak (uslovi, privatnost, rezidentnost podataka) | 9 |
| Zatvaranje prozora i dijalozi | 7 |
| Lista čekanja / rani pristup | 7 |
| Graf znanja i dokazi | 7 |
| Onboarding | 5 |
| Instalacija aplikacije (PWA) | 1 |
| Prikaži/sakrij (razvijanje panela) | 1 |

### Polja za unos (forme) (185)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-004 | placeholder: Email adresa | modal `auth-modal` (prijava/registracija) | `—` |
| UI-005 | placeholder: Lozinka | modal `auth-modal` (prijava/registracija) | `—` |
| UI-009 | placeholder: Ime i prezime | modal `auth-modal` (prijava/registracija) | `—` |
| UI-010 | placeholder: Email adresa | modal `auth-modal` (prijava/registracija) | `—` |
| UI-011 | placeholder: Lozinka | modal `auth-modal` (prijava/registracija) | `—` |
| UI-013 | placeholder: Potvrdi lozinku | modal `auth-modal` (prijava/registracija) | `—` |
| UI-016 | placeholder: Email adresa | modal `auth-modal` (prijava/registracija) | `—` |
| UI-019 | placeholder: Nova lozinka (min. 8 karaktera) | modal `auth-modal` (prijava/registracija) | `—` |
| UI-021 | placeholder: Potvrdite novu lozinku | modal `auth-modal` (prijava/registracija) | `—` |
| UI-042 | placeholder: Šta ste primetili? Šta bismo mogli da poboljšamo? | modal `feedback-modal` | `—` |
| UI-049 | placeholder: Petar Petrović | modal `ugovor-modal` (ugovor o zastupanju) | `—` |
| UI-050 | placeholder: Ul. Knez Mihailova 1, Beograd | modal `ugovor-modal` (ugovor o zastupanju) | `—` |
| UI-051 | placeholder: Kompanija d.o.o. | modal `ugovor-modal` (ugovor o zastupanju) | `—` |
| UI-052 | placeholder: Marko Marković | modal `ugovor-modal` (ugovor o zastupanju) | `—` |
| UI-053 | placeholder: Ul. Terazije 10, Beograd | modal `ugovor-modal` (ugovor o zastupanju) | `—` |
| UI-054 | placeholder: Naknada štete iz saobraćajne nezgode od 12.03.2026 | modal `ugovor-modal` (ugovor o zastupanju) | `—` |
| UI-055 | vizuelna `<label>` iznad (bez `for=`): Oblast prava | modal `ugovor-modal` (ugovor o zastupanju) | `—` |
| UI-056 | vizuelna `<label>` iznad (bez `for=`): Naknada | modal `ugovor-modal` (ugovor o zastupanju) | `—` |
| UI-057 | placeholder: 50.000 RSD ili po dogovoru | modal `ugovor-modal` (ugovor o zastupanju) | `—` |
| UI-058 | vizuelna `<label>` iznad (bez `for=`): Datum zaključenja | modal `ugovor-modal` (ugovor o zastupanju) | `—` |
| UI-063 | placeholder: Npr. Tužba za naknadu štete | modal `pred-new-modal` (brzi novi predmet) | `—` |
| UI-064 | vizuelna `<label>` iznad (bez `for=`): Tip postupka | modal `pred-new-modal` (brzi novi predmet) | `—` |
| UI-065 | placeholder: Kratki opis predmeta... | modal `pred-new-modal` (brzi novi predmet) | `—` |
| UI-144 | placeholder: Nova beleška... | kartica predmeta → pan Pregled | `—` |
| UI-147 | vizuelna `<label>` iznad (bez `for=`): Ishod | kartica predmeta → pan Pregled | `—` |
| UI-148 | placeholder: Kratak zaključak i pouka iz predmeta... | kartica predmeta → pan Pregled | `—` |
| UI-149 | vizuelna `<label>` iznad (bez `for=`): Presudni faktori — pomaže Vindex Intelligence da uči (opciono) | kartica predmeta → pan Pregled | `—` |
| UI-150 | vizuelna `<label>` iznad (bez `for=`): Veštačenje | kartica predmeta → pan Pregled | `—` |
| UI-151 | vizuelna `<label>` iznad (bez `for=`): Svedoci | kartica predmeta → pan Pregled | `—` |
| UI-152 | vizuelna `<label>` iznad (bez `for=`): Zastarelost | kartica predmeta → pan Pregled | `—` |
| UI-153 | vizuelna `<label>` iznad (bez `for=`): Procesna greška | kartica predmeta → pan Pregled | `—` |
| UI-154 | vizuelna `<label>` iznad (bez `for=`): Novi dokaz | kartica predmeta → pan Pregled | `—` |
| UI-155 | vizuelna `<label>` iznad (bez `for=`): Sporazum | kartica predmeta → pan Pregled | `—` |
| UI-156 | vizuelna `<label>` iznad (bez `for=`): Sudska praksa | kartica predmeta → pan Pregled | `—` |
| UI-157 | vizuelna `<label>` iznad (bez `for=`): Pisana komunikacija | kartica predmeta → pan Pregled | `—` |
| UI-158 | placeholder: Trajanje (meseci) | kartica predmeta → pan Pregled | `—` |
| UI-159 | placeholder: Vrednost spora (RSD) | kartica predmeta → pan Pregled | `—` |
| UI-164 | vizuelna `<label>` iznad (bez `for=`): Procesni akt | kartica predmeta → pan Pregled | `—` |
| UI-165 | vizuelna `<label>` iznad (bez `for=`): Datum dostave | kartica predmeta → pan Pregled | `—` |
| UI-171 | placeholder: klijent@email.com | kartica predmeta → pan Pregled | `—` |
| UI-172 | vizuelna `<label>` iznad (bez `for=`): Valjanost linka | kartica predmeta → pan Pregled | `—` |
| UI-187 | placeholder: npr. Da li postoje kontradikcije između ovih dokumenata? | kartica predmeta → pan Dokumenti | `—` |
| UI-211 | placeholder: npr. Da smo prihvatili nagodbu od 500.000 RSD... | kartica predmeta → pan Strategija | `—` |
| UI-216 | title: Datum prijema/dostave akta | kartica predmeta → pan Rokovi | `—` |
| UI-218 | placeholder: Datum ročišta | kartica predmeta → pan Rokovi | `—` |
| UI-219 | (bez labele — prva opcija: „Parničan (ZPP)“) | kartica predmeta → pan Rokovi | `—` |
| UI-222 | placeholder: npr. P 123/2024 | kartica predmeta → pan Rokovi | `—` |
| UI-223 | placeholder: Naziv suda | kartica predmeta → pan Rokovi | `—` |
| UI-228 | placeholder: Opis radnje... | kartica predmeta → pan Naplata | `—` |
| UI-229 | placeholder: RSD | kartica predmeta → pan Naplata | `—` |
| UI-232 | placeholder: Naziv šablona... | kartica predmeta → pan Naplata | `—` |
| UI-233 | (bez labele — prva opcija: „Mesečno“) | kartica predmeta → pan Naplata | `—` |
| UI-234 | placeholder: Iznos RSD | kartica predmeta → pan Naplata | `—` |
| UI-235 | placeholder: Opis usluge... | kartica predmeta → pan Naplata | `—` |
| UI-236 | (bez labele) | kartica predmeta → pan Naplata | `—` |
| UI-237 | placeholder: PDV % | kartica predmeta → pan Naplata | `—` |
| UI-245 | placeholder: Dodaj komentar... | kartica predmeta → pan Komunikacija | `—` |
| UI-248 | placeholder: Email adresa kolege... | kartica predmeta → pan Saradnja | `—` |
| UI-249 | (bez labele — prva opcija: „Čitanje — samo pregled“) | kartica predmeta → pan Saradnja | `—` |
| UI-264 | placeholder: Opišite šta trebate... (ili izaberite analizu levo, pa unesite zadatak) | kartica predmeta → pan AI Analiza | `—` |
| UI-280 | placeholder: Naziv zadatka... | kartica predmeta → pan Zadaci | `—` |
| UI-281 | (bez labele — prva opcija: „Normalan prioritet“) | kartica predmeta → pan Zadaci | `—` |
| UI-282 | (bez labele) | kartica predmeta → pan Zadaci | `—` |
| UI-287 | placeholder: Naziv ključa (npr. Moja integracija) | kartica predmeta → pan Profitabilnost | `—` |
| UI-291 | placeholder: Pretraga (npr. otkaz ugovora o radu) — ostavite prazno za sve odluke | tab Sudska praksa (`tab-s`) | `—` |
| UI-292 | (bez labele — prva opcija: „Sva pravna oblast“) | tab Sudska praksa (`tab-s`) | `—` |
| UI-293 | (bez labele — prva opcija: „Svi sudovi“) | tab Sudska praksa (`tab-s`) | `—` |
| UI-294 | placeholder: Od god. | tab Sudska praksa (`tab-s`) | `—` |
| UI-295 | placeholder: Do god. | tab Sudska praksa (`tab-s`) | `—` |
| UI-300 | placeholder: npr. Uzp 51/2024 | tab Sudska praksa (`tab-s`) | `—` |
| UI-301 | placeholder: npr. Rev 123/2023 | tab Sudska praksa (`tab-s`) | `—` |
| UI-317 | placeholder: Globalna satnica | tab Klijenti (`tab-k`) | `—` |
| UI-324 | (skriveno polje — nema vidljivu labelu) | modal `crm-overlay` (klijent) | `—` |
| UI-343 | placeholder: Ime | modal `crm-conflict-overlay` (provera sukoba) | `—` |
| UI-344 | placeholder: Prezime | modal `crm-conflict-overlay` (provera sukoba) | `—` |
| UI-345 | placeholder: Naziv firme | modal `crm-conflict-overlay` (provera sukoba) | `—` |
| UI-362 | (bez labele) | modal `intake-overlay` (Intake Wizard) | `—` |
| UI-363 | (bez labele — prva opcija: „Opšti“) | modal `intake-overlay` (Intake Wizard) | `—` |
| UI-364 | (bez labele) | modal `intake-overlay` (Intake Wizard) | `—` |
| UI-365 | placeholder: Npr. AD Beograd d.o.o. | modal `intake-overlay` (Intake Wizard) | `—` |
| UI-366 | (bez labele) | modal `intake-overlay` (Intake Wizard) | `—` |
| UI-367 | placeholder: Npr. 500000 RSD | modal `intake-overlay` (Intake Wizard) | `—` |
| UI-368 | (bez labele) | modal `intake-overlay` (Intake Wizard) | `—` |
| UI-369 | placeholder: Npr. Rok za tužbu, zastarelost | modal `intake-overlay` (Intake Wizard) | `—` |
| UI-374 | placeholder: Iznos u RSD | modal `intake-overlay` (Intake Wizard) | `—` |
| UI-390 | placeholder: Npr. Radni spor — Jovanović vs. Firma | modal `si-overlay` (Novi predmet iz dokumenta) | `—` |
| UI-391 | (bez labele — prva opcija: „Opšti“) | modal `si-overlay` (Novi predmet iz dokumenta) | `—` |
| UI-417 | vizuelna `<label>` iznad (bez `for=`): Sačuvaj uz predmet (opciono) | modal `doctpl-overlay` (šabloni dokumenata) | `—` |
| UI-421 | (bez labele) | modal `doctpl-overlay` (šabloni dokumenata) | `—` |
| UI-433 | placeholder: Naziv kancelarije | tab Kancelarija (`tab-kanc`) | `—` |
| UI-438 | placeholder: email@kancelarija.rs | tab Kancelarija (`tab-kanc`) | `—` |
| UI-439 | (bez labele — prva opcija: „Partner“) | tab Kancelarija (`tab-kanc`) | `—` |
| UI-464 | placeholder: Npr. Koji su uslovi za naknadu nematerijalne štete? | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-466 | placeholder: Naslov stava (npr. 'Tumačenje čl. 179 ZR — otpremnina') | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-467 | placeholder: Tekst internog pravnog stava ili argumenta... | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-469 | placeholder: Pretražite interne stavove... | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-481 | placeholder: Npr. Da li postoji rizik od raskida ugovora? | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-482 | vizuelna `<label>` iznad (bez `for=`): Postavite pitanje o ovom dokumentu: | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-489 | placeholder: 01.01.2024 | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-491 | (skriveno polje — nema vidljivu labelu) | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-517 | vizuelna `<label>` iznad (bez `for=`): Sud: | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-518 | vizuelna `<label>` iznad (bez `for=`): Sud: | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-520 | placeholder: Npr. Tužilac Petar Petrović, ul. Vojvode Mišića 5, Beograd traži naknadu štete od tužen | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-538 | vizuelna `<label>` iznad (bez `for=`): Tip postupka | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-539 | placeholder: Unesite detaljan opis predmeta ili tekst dokumenta... | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-546 | placeholder: Naziv suda (obavezno) | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-547 | placeholder: Ime sudije (opciono) | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-549 | placeholder: Naziv protivničke strane (obavezno) | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-550 | placeholder: Advokat / kancelarija (opciono) | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-565 | (bez labele) | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-569 | placeholder: 0x...&#10;1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-571 | placeholder: 0x... | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-573 | placeholder: Npr: Imam KYC verifikaciju na Binance i Kraken nalozima... | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-574 | placeholder: Ostavite prazno za opšti pregled obaveza izveštavanja. | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-575 | placeholder: 0x... (ostavite prazno da preskočite) | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-577 | vizuelna `<label>` iznad (bez `for=`): CSV fajl | tab AI radni prostor (`tab-aiws`) | `—` |
| UI-581 | placeholder: npr. Benny | tab Podešavanja (`tab-settings`) | `—` |
| UI-601 | placeholder: 123456789 | tab Podešavanja (`tab-settings`) | `—` |
| UI-602 | placeholder: Advokat Petrović | tab Podešavanja (`tab-settings`) | `—` |
| UI-603 | placeholder: Knez Mihailova 10 | tab Podešavanja (`tab-settings`) | `—` |
| UI-604 | placeholder: Beograd | tab Podešavanja (`tab-settings`) | `—` |
| UI-605 | placeholder: Novi API ključ (ostavite prazno da ne menjate) | tab Podešavanja (`tab-settings`) | `—` |
| UI-607 | placeholder: +381601234567 ili 0601234567 | tab Podešavanja (`tab-settings`) | `—` |
| UI-608 | uz kontrolu (`<label>` omotač): WhatsApp | tab Podešavanja (`tab-settings`) | `—` |
| UI-612 | uz kontrolu (`<label>` omotač): 7 dana pre | tab Podešavanja (`tab-settings`) | `—` |
| UI-613 | uz kontrolu (`<label>` omotač): 3 dana pre | tab Podešavanja (`tab-settings`) | `—` |
| UI-614 | uz kontrolu (`<label>` omotač): 1 dan pre (dan uoči roka) | tab Podešavanja (`tab-settings`) | `—` |
| UI-615 | uz kontrolu (`<label>` omotač): Nedeljni sažetak (ponedeljak ujutru — rokovi, ročišta, naplata) | tab Podešavanja (`tab-settings`) | `—` |
| UI-629 | (bez labele — prva opcija: „Tehnički problem“) | tab Podešavanja (`tab-settings`) | `—` |
| UI-630 | placeholder: Opišite problem ili pišite nam šta mislite... | tab Podešavanja (`tab-settings`) | `—` |
| UI-636 | placeholder: Naziv zakona (npr. Zakon o privrednim društvima) | tab Podešavanja (`tab-settings`) | `—` |
| UI-637 | placeholder: Sl. glasnik RS (npr. 36/2011, 99/2011...) | tab Podešavanja (`tab-settings`) | `—` |
| UI-638 | (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | tab Podešavanja (`tab-settings`) | `—` |
| UI-644 | placeholder: email@firma.rs | tab Podešavanja (`tab-settings`) | `—` |
| UI-670 | placeholder: Napomena advokatu (opciono)... | tab Podešavanja (`tab-settings`) | `—` |
| UI-674 | placeholder: Marko Marković | overlay `wl-overlay` (lista čekanja) | `—` |
| UI-675 | placeholder: AK Marković | overlay `wl-overlay` (lista čekanja) | `—` |
| UI-676 | placeholder: marko@kancelarija.rs | overlay `wl-overlay` (lista čekanja) | `—` |
| UI-677 | placeholder: +381 60 123 4567 | overlay `wl-overlay` (lista čekanja) | `—` |
| UI-678 | placeholder: Npr. istraživanje zakona, upravljanje predmetima... | overlay `wl-overlay` (lista čekanja) | `—` |
| UI-698 | placeholder: npr. Adv. kancelarija Petrović | modal `settings-modal` (podaci kancelarije) | `—` |
| UI-699 | placeholder: Ulica i broj, Grad | modal `settings-modal` (podaci kancelarije) | `—` |
| UI-700 | placeholder: 123456789 | modal `settings-modal` (podaci kancelarije) | `—` |
| UI-701 | placeholder: advokat@kancelarija.rs | modal `settings-modal` (podaci kancelarije) | `—` |
| UI-703 | placeholder: 7500 (AKS default) | modal `settings-modal` (podaci kancelarije) | `—` |
| UI-712 | (skriveno polje — nema vidljivu labelu) | modal `rociste-overlay` (ročište) | `—` |
| UI-713 | (bez labele) | modal `rociste-overlay` (ročište) | `—` |
| UI-714 | placeholder: Npr. Viši sud u Beogradu | modal `rociste-overlay` (ročište) | `—` |
| UI-715 | (bez labele) | modal `rociste-overlay` (ročište) | `—` |
| UI-716 | (bez labele) | modal `rociste-overlay` (ročište) | `—` |
| UI-717 | placeholder: Npr. Sudnica 4 | modal `rociste-overlay` (ročište) | `—` |
| UI-718 | placeholder: Npr. P-123/2025 | modal `rociste-overlay` (ročište) | `—` |
| UI-719 | (bez labele) | modal `rociste-overlay` (ročište) | `—` |
| UI-764 | (bez labele) | modal `vx-dialog-overlay` (zamena za alert/confirm) | `—` |
| UI-821 | placeholder: Sud (npr. Prvi osnovni sud Beograd) | kartica predmeta (dinamički) | `—` |
| UI-822 | placeholder: Ime sudije (opciono) | kartica predmeta (dinamički) | `—` |
| UI-824 | placeholder: Naziv protivničke strane | kartica predmeta (dinamički) | `—` |
| UI-825 | placeholder: Advokatska kancelarija (opciono) | kartica predmeta (dinamički) | `—` |
| UI-827 | placeholder: Argumenti koje planirate da koristite — po jedan u redu | kartica predmeta (dinamički) | `—` |
| UI-869 | (bez labele) | sudska praksa / pretraga (dinamički) | `—` |
| UI-886 | (bez labele) | kartica predmeta (dinamički) | `—` |
| UI-887 | (bez labele) | kartica predmeta (dinamički) | `—` |
| UI-902 | placeholder: Naziv klijenta * | naplata / fakture (dinamički) | `—` |
| UI-903 | placeholder: Adresa klijenta (opciono) | naplata / fakture (dinamički) | `—` |
| UI-904 | placeholder: PIB | naplata / fakture (dinamički) | `—` |
| UI-905 | (bez labele) | naplata / fakture (dinamički) | `—` |
| UI-924 | (bez labele) | administracija (dinamički) | `—` |
| UI-925 | placeholder: — | administracija (dinamički) | `—` |
| UI-926 | (bez labele) | administracija (dinamički) | `—` |
| UI-927 | placeholder: ∞ | administracija (dinamički) | `—` |
| UI-928 | placeholder: ∞ | administracija (dinamički) | `—` |
| UI-932 | placeholder: — | administracija (dinamički) | `—` |
| UI-933 | (bez labele) | administracija (dinamički) | `—` |
| UI-934 | (bez labele) | administracija (dinamički) | `—` |
| UI-935 | (bez labele) | administracija (dinamički) | `—` |
| UI-936 | (bez labele) | administracija (dinamički) | `—` |
| UI-937 | placeholder: — | administracija (dinamički) | `—` |
| UI-943 | (bez labele) | dinamički (vindex.js) — nesvrstano | `—` |
| UI-944 | (bez labele) | dinamički (vindex.js) — nesvrstano | `—` |
| UI-986 | (bez labele) | modal Intake / Novi predmet iz dokumenta (dinamički) | `—` |
| UI-987 | (bez labele) | modal Intake / Novi predmet iz dokumenta (dinamički) | `—` |
| UI-988 | (bez labele) | modal Intake / Novi predmet iz dokumenta (dinamički) | `—` |
| UI-989 | (bez labele) | modal Intake / Novi predmet iz dokumenta (dinamički) | `—` |
| UI-990 | (bez labele) | modal Intake / Novi predmet iz dokumenta (dinamički) | `—` |
| UI-991 | (bez labele) | modal Intake / Novi predmet iz dokumenta (dinamički) | `—` |

### Navigacija (tabovi i ekrani) (110)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-071 | Pregled dana | bočna traka (glavna navigacija) | `setTab` |
| UI-072 | Predmeti | bočna traka (glavna navigacija) | `setTab` |
| UI-073 | Klijenti | bočna traka (glavna navigacija) | `setTab` |
| UI-074 | Rokovi | bočna traka (glavna navigacija) | `setTab` |
| UI-075 | Vindex Intelligence | bočna traka (glavna navigacija) | `setTab` |
| UI-076 | Sudska praksa | bočna traka (glavna navigacija) | `setTab` |
| UI-077 | Dokumenti | bočna traka (glavna navigacija) | `setTab` |
| UI-079 | Zadatci | bočna traka (glavna navigacija) | `setTab` |
| UI-080 | Finansije | bočna traka (glavna navigacija) | `setTab` |
| UI-081 | Kancelarija | bočna traka (glavna navigacija) | `setTab` |
| UI-082 | Portfolio kancelarije | bočna traka (glavna navigacija) | `setTab` |
| UI-083 | Podešavanja | bočna traka (glavna navigacija) | `setTab` |
| UI-085 | (bez labele) | bočna traka (glavna navigacija) | `setTab` |
| UI-101 | Nazad | gornja traka | `vxGoBack` |
| UI-118 | Pregled | kartica predmeta — zaglavlje, tajmer, podtabovi | `pred_subtabSwitch` |
| UI-119 | Dokumenti | kartica predmeta — zaglavlje, tajmer, podtabovi | `pred_subtabSwitch` |
| UI-120 | AI Analiza | kartica predmeta — zaglavlje, tajmer, podtabovi | `pred_subtabSwitch` |
| UI-121 | Rokovi | kartica predmeta — zaglavlje, tajmer, podtabovi | `pred_subtabSwitch` |
| UI-122 | Zadaci | kartica predmeta — zaglavlje, tajmer, podtabovi | `pred_subtabSwitch` |
| UI-123 | Workflow | kartica predmeta — zaglavlje, tajmer, podtabovi | `pred_subtabSwitch` |
| UI-124 | Strategija | kartica predmeta — zaglavlje, tajmer, podtabovi | `pred_subtabSwitch` |
| UI-125 | Naplata | kartica predmeta — zaglavlje, tajmer, podtabovi | `pred_subtabSwitch` |
| UI-178 | Istraživanje zakona | kartica predmeta → pan Pregled | `openAITool` |
| UI-179 | Sudska praksa | kartica predmeta → pan Pregled | `openAITool` |
| UI-180 | Nacrti podnesaka | kartica predmeta → pan Pregled | `openAITool` |
| UI-181 | Analiza dokumenta | kartica predmeta → pan Pregled | `openAITool` |
| UI-192 | 1 Intake & Analiza | kartica predmeta → pan Strategija | `predStratPhaseSwitch` |
| UI-193 | 2 Strategija & Svedoci | kartica predmeta → pan Strategija | `predStratPhaseSwitch` |
| UI-194 | 3 Izrada Nacrta | kartica predmeta → pan Strategija | `predStratPhaseSwitch` |
| UI-195 | 4 Simulacija Suda | kartica predmeta → pan Strategija | `predStratPhaseSwitch` |
| UI-205 | Hearing Command Center PRO Borbeni brifing pred ročište: teret dokazivanja, nedostajući do | kartica predmeta → pan Strategija | `pred_subtabSwitch` |
| UI-241 | Finansije → | kartica predmeta → pan Naplata | `setTab` |
| UI-247 | Hearing Command Center premešten u tab Rokovi → | kartica predmeta → pan Komunikacija | `pred_subtabSwitch` |
| UI-269 | Rokovi → | kartica predmeta → pan AI Analiza | `pred_subtabSwitch` |
| UI-272 | Analiza dokumenta | kartica predmeta → pan AI Analiza | `openAITool` |
| UI-273 | Sudska praksa | kartica predmeta → pan AI Analiza | `openAITool` |
| UI-274 | Istraživanje zakona | kartica predmeta → pan AI Analiza | `openAITool` |
| UI-275 | Nacrti i podnesci | kartica predmeta → pan AI Analiza | `openAITool` |
| UI-290 | ← Pravni alati | tab Sudska praksa (`tab-s`) | `setTab` |
| UI-442 | Mesec | tab Kalendar/Rokovi (`tab-kal`) | `kalSetView` |
| UI-443 | Lista | tab Kalendar/Rokovi (`tab-kal`) | `kalSetView` |
| UI-453 | Istraživanje zakona | tab AI radni prostor (`tab-aiws`) | `aiwsSetMode` |
| UI-454 | Analiza dokumenta | tab AI radni prostor (`tab-aiws`) | `aiwsSetMode` |
| UI-455 | Nacrti podnesaka | tab AI radni prostor (`tab-aiws`) | `aiwsSetMode` |
| UI-456 | Strategija | tab AI radni prostor (`tab-aiws`) | `aiwsSetMode` |
| UI-457 | Pravne oblasti | tab AI radni prostor (`tab-aiws`) | `aiwsSetMode` |
| UI-458 | Litigation Intelligence | tab AI radni prostor (`tab-aiws`) | `aiwsSetMode` |
| UI-459 | Vindex AI - Digitalna imovina & usklađenost | tab AI radni prostor (`tab-aiws`) | `aiwsSetMode` |
| UI-552 | → Istraživanje zakona i argumentacija | tab AI radni prostor (`tab-aiws`) | `aiwsSetMode` |
| UI-553 | → Puna pretraga sudske prakse | tab AI radni prostor (`tab-aiws`) | `setTab` |
| UI-579 | Predmeti Dokumenti unutar predmeta | tab Dokumenti (`tab-dok`) | `setTab` |
| UI-580 | Analiza dokumenta analiza novog dokumenta | tab Dokumenti (`tab-dok`) | `openAITool` |
| UI-599 | Advokatska kancelarija Tim, pozivnice, uloge — sada u tabu Kancelarija → | tab Podešavanja (`tab-settings`) | `setTab` |
| UI-600 | Naplata i dugovanja Fakture, izveštaji, neplaćena dugovanja — sada u tabu Finansije → | tab Podešavanja (`tab-settings`) | `setTab` |
| UI-722 | Početna | mobilno — donja navigacija | `mobileNavGo` |
| UI-723 | Predmeti | mobilno — donja navigacija | `mobileNavGo` |
| UI-724 | Rokovi | mobilno — donja navigacija | `mobileNavGo` |
| UI-725 | Klijenti | mobilno — donja navigacija | `mobileNavGo` |
| UI-726 | Više | mobilno — donja navigacija | `mobileMoreOtvori` |
| UI-734 | (bez labele) | modal `vx-voice-modal-overlay` (Vindex Live) | `mobileMoreZatvori` |
| UI-735 | Istraži zakon | mobilno — 'Više' bottom sheet | `mobileMoreGo` |
| UI-736 | Sud. praksa | mobilno — 'Više' bottom sheet | `mobileMoreGo` |
| UI-737 | Analiza dok. | mobilno — 'Više' bottom sheet | `mobileMoreGo` |
| UI-738 | Podnesci | mobilno — 'Više' bottom sheet | `mobileMoreGo` |
| UI-739 | Strategija | mobilno — 'Više' bottom sheet | `mobileMoreGo` |
| UI-740 | Šabloni | mobilno — 'Više' bottom sheet | `mobileMoreZatvori` |
| UI-741 | Baza znanja | mobilno — 'Više' bottom sheet | `mobileMoreGo` |
| UI-742 | Finansije | mobilno — 'Više' bottom sheet | `mobileMoreGo` |
| UI-743 | Kancelarija | mobilno — 'Više' bottom sheet | `mobileMoreGo` |
| UI-744 | Portfolio | mobilno — 'Više' bottom sheet | `mobileMoreGo` |
| UI-745 | + Klijent | mobilno — 'Više' bottom sheet | `mobileMoreZatvori` |
| UI-746 | Izveštaj | mobilno — 'Više' bottom sheet | `mobileMoreZatvori` |
| UI-747 | Notifikacije | mobilno — 'Više' bottom sheet | `mobileMoreZatvori` |
| UI-748 | Podešavanja | mobilno — 'Više' bottom sheet | `mobileMoreGo` |
| UI-749 | Instaliraj | mobilno — 'Više' bottom sheet | `mobileMoreZatvori` |
| UI-786 | Vidi sve → | dashboard (dinamički) | `setTab` |
| UI-788 | Još <vrednost> <vrednost> ▾ | dashboard (dinamički) | `setTab` |
| UI-789 | Vidi sve → | dashboard (dinamički) | `setTab` |
| UI-791 | (dinamički tekst — labela zavisi od podataka) | dashboard (dinamički) | `setTab` |
| UI-792 | (dinamički tekst — labela zavisi od podataka) | dashboard (dinamički) | `openAITool` |
| UI-793 | (dinamički tekst — labela zavisi od podataka) | dashboard (dinamički) | `setTab` |
| UI-794 | <vrednost> <vrednost> Aktivnih predmeta | dashboard (dinamički) | `setTab` |
| UI-795 | 0?' warn':'')+'"><vrednost> 0?' warn':'')+'"><vrednost> Hitnih rokova | dashboard (dinamički) | `setTab` |
| UI-799 | Još <vrednost> <vrednost> ▾ | kancelarija / poslovna inteligencija (dinamički) | `setTab` |
| UI-800 | <vrednost> rokova | razno / pomoćni paneli (dinamički) | `setTab` |
| UI-801 | <vrednost> predmeta | razno / pomoćni paneli (dinamički) | `setTab` |
| UI-802 | klijenti | razno / pomoćni paneli (dinamički) | `setTab` |
| UI-804 | Predmeti <vrednost> <vrednost> aktivna | razno / pomoćni paneli (dinamički) | `setTab` |
| UI-805 | Klijenti — Baza klijenata kancelarije Otvori → | razno / pomoćni paneli (dinamički) | `setTab` |
| UI-806 | Rokovi <vrednost> <vrednost> ove ned. | razno / pomoćni paneli (dinamički) | `setTab` |
| UI-807 | Centar alata 847 zakona RS Istraži zakon ☐ Analiziraj d | razno / pomoćni paneli (dinamički) | `setTab` |
| UI-835 | Administrativna ovlašćenja <vrednost> ▾ | Digitalna imovina / moduli (dinamički) | `scToggle` |
| UI-836 | Analiza centralizacije <vrednost> ▾ | Digitalna imovina / moduli (dinamički) | `scToggle` |
| UI-837 | Ključne radnje ▾ | Digitalna imovina / moduli (dinamički) | `scToggle` |
| UI-838 | Pravni indikatori ▾ | Digitalna imovina / moduli (dinamički) | `scToggle` |
| UI-839 | AML/KYC <vrednost> ▾ | Digitalna imovina / moduli (dinamički) | `scToggle` |
| UI-840 | Klasifikacija tokena ▾ | Digitalna imovina / moduli (dinamički) | `scToggle` |
| UI-841 | Regulatorna relevantnost ▾ | Digitalna imovina / moduli (dinamički) | `scToggle` |
| UI-842 | Off-chain zavisnosti (<vrednost>) ▸ | Digitalna imovina / moduli (dinamički) | `scToggle` |
| UI-843 | Limitacije analize ▸ | Digitalna imovina / moduli (dinamički) | `scToggle` |
| UI-884 | Otkriven je kritičan rok (možda već prošao) — proverite Rokovi tab → | kartica predmeta (dinamički) | `pred_subtabSwitch` |
| UI-969 | Otvori trezor dokaza → | dashboard (dinamički) | `pred_subtabSwitch` |
| UI-970 | Otvori Naplatu → | dashboard (dinamički) | `pred_subtabSwitch` |
| UI-971 | Svi rokovi → | dashboard (dinamički) | `pred_subtabSwitch` |
| UI-972 | Puna hronologija → | dashboard (dinamički) | `pred_subtabSwitch` |
| UI-973 | Analiza | dashboard (dinamički) | `pred_subtabSwitch` |
| UI-974 | Strategija | dashboard (dinamički) | `pred_subtabSwitch` |
| UI-975 | Savetnici | dashboard (dinamički) | `pred_subtabSwitch` |
| UI-976 | Dokumenti | dashboard (dinamički) | `pred_subtabSwitch` |
| UI-978 | Mapa veza | dashboard (dinamički) | `pred_subtabSwitch` |

### Lista predmeta i rad na predmetu (65)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-089 | (bez labele) | gornja traka | `mesecniIzvestajZatvori` |
| UI-090 | (bez labele) | gornja traka | `mesecniIzvestajUcitaj` |
| UI-091 | ✕ | gornja traka | `mesecniIzvestajZatvori` |
| UI-104 | Svi | kartica Predmeti — lista/kanban | `pred_setSort` |
| UI-105 | Prioritet | kartica Predmeti — lista/kanban | `pred_setSort` |
| UI-106 | ⚠ Rizik | kartica Predmeti — lista/kanban | `pred_setSort` |
| UI-107 | Rokovi | kartica Predmeti — lista/kanban | `pred_setSort` |
| UI-108 | Firma | kartica Predmeti — lista/kanban | `predFirmaToggle` |
| UI-109 | Arhivuj | kartica Predmeti — lista/kanban | `pred_bulkAkcija` |
| UI-110 | Aktiviraj | kartica Predmeti — lista/kanban | `pred_bulkAkcija` |
| UI-111 | ✕ | kartica Predmeti — lista/kanban | `pred_bulkOtkaziOznacavanje` |
| UI-112 | ≡ Lista | kartica Predmeti — lista/kanban | `kanban_setView` |
| UI-113 | ⬛ Kanban | kartica Predmeti — lista/kanban | `kanban_setView` |
| UI-114 | ▶ Suprotne strane | kartica Predmeti — lista/kanban | `opposing_toggle` |
| UI-126 | ⋯ Više | kartica predmeta — zaglavlje, tajmer, podtabovi | `pred_more_toggle` |
| UI-127 | Komunikacija | kartica predmeta — zaglavlje, tajmer, podtabovi | `pred_more_select` |
| UI-128 | Saradnja | kartica predmeta — zaglavlje, tajmer, podtabovi | `pred_more_select` |
| UI-129 | Mapa veza | kartica predmeta — zaglavlje, tajmer, podtabovi | `pred_more_select` |
| UI-130 | Profitabilnost | kartica predmeta — zaglavlje, tajmer, podtabovi | `pred_more_select` |
| UI-132 | Štampaj | kartica predmeta → pan Pregled | `pred_print` |
| UI-134 | ✕ Zatvori | kartica predmeta → pan Pregled | `pred_zatvoriOtvori` |
| UI-135 | Analiziraj | kartica predmeta → pan Pregled | `pred_launchKompletnaAnaliza` |
| UI-136 | — | kartica predmeta → pan Pregled | `_predInlineEdit` |
| UI-137 | — | kartica predmeta → pan Pregled | `_predInlineEdit` |
| UI-138 | — | kartica predmeta → pan Pregled | `_predInlineEdit` |
| UI-139 | — | kartica predmeta → pan Pregled | `_predInlineEdit` |
| UI-140 | — | kartica predmeta → pan Pregled | `_predInlineEdit` |
| UI-146 | Dodaj | kartica predmeta → pan Pregled | `pred_dodajBelesku` |
| UI-160 | Potvrdi zatvaranje | kartica predmeta → pan Pregled | `pred_zatvoriPredmet` |
| UI-161 | Odustani | kartica predmeta → pan Pregled | `pred_zatvoriCancel` |
| UI-162 | ✕ Zatvori predmet | kartica predmeta → pan Pregled | `pred_zatvoriOtvori` |
| UI-184 | (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | kartica predmeta → pan Dokumenti | `pred_upload_doc` |
| UI-185 | Prevucite dokument ili kliknite za upload PDF, DOCX — do 10MB | kartica predmeta → pan Dokumenti | `pred_upload_trigger` |
| UI-191 | ◆ Preporučeno PRO Kompletna analiza predmeta Sveobuhvatna pravna analiza u jednom izveštaj | kartica predmeta → pan Strategija | `pred_launchKompletnaAnaliza` |
| UI-196 | Revizija dokumenta PRO Sistem čita vaš podnesak ili ugovor i daje konkretne sugestije za p | kartica predmeta → pan Strategija | `pred_openStrat` |
| UI-197 | Analiza rizika PRO Sistemska provera pravnih rizika pre preuzimanja, investicije ili ulaga | kartica predmeta → pan Strategija | `pred_openStrat` |
| UI-198 | Analiza crvenog tima PRO Sistem preuzima ulogu protivničkog advokata i napada vašu argumen | kartica predmeta → pan Strategija | `pred_openStrat` |
| UI-199 | Analiza svedoka PRO Analizira iskaze svedoka, otkriva kontradikcije, predlaže pitanja za u | kartica predmeta → pan Strategija | `pred_openStrat` |
| UI-200 | Otvori Nacrti & Podnesci Generisanje tužbi, žalbi, ugovora i drugih podnesaka na osnovu pr | kartica predmeta → pan Strategija | `pred_openDraftEngine` |
| UI-201 | Sudija — procena ishoda PRO Simulira sudijsku odluku na osnovu vaših argumenata, dokaza i  | kartica predmeta → pan Strategija | `pred_openStrat` |
| UI-202 | Simulacija sudskog postupka PRO Detaljna simulacija celog postupka: pitanja suda, argument | kartica predmeta → pan Strategija | `pred_openStrat` |
| UI-203 | Simulacija parničnog postupka PRO Kompletna simulacija od tužbe do presude — identifikuje  | kartica predmeta → pan Strategija | `pred_openStrat` |
| UI-204 | Predikcija ishoda PRO Statistička procena šansi za uspeh (%) na osnovu srpske sudske praks | kartica predmeta → pan Strategija | `pred_openStrat` |
| UI-242 | placeholder: Napiši pitanje ili komandu… npr. Dodaj rok — ročište 20. jula | kartica predmeta → pan Komunikacija | `pred_copilotSubmit` |
| UI-244 | Pošalji | kartica predmeta → pan Komunikacija | `pred_copilotSubmit` |
| UI-253 | Pokreni kompletnu analizu | kartica predmeta → pan AI Analiza | `pred_launchKompletnaAnaliza` |
| UI-263 | ↺ Iz predmeta | kartica predmeta → pan AI Analiza | `_predAutoFill` |
| UI-423 | Mesečni izveštaj | tab Finansije (`tab-fin`) | `mesecniIzvestajOtvori` |
| UI-519 | ↺ Iz predmeta | tab AI radni prostor (`tab-aiws`) | `_predAutoFill` |
| UI-537 | ↺ Iz predmeta | tab AI radni prostor (`tab-aiws`) | `_predAutoFill` |
| UI-751 | Dodaj dokument | plutajuće — `pred-fab` (brze akcije u predmetu) | `pred_fab_close` |
| UI-752 | Dodaj rok | plutajuće — `pred-fab` (brze akcije u predmetu) | `pred_fab_close` |
| UI-753 | Zakaži ročište | plutajuće — `pred-fab` (brze akcije u predmetu) | `pred_fab_close` |
| UI-754 | Unesi naplatu | plutajuće — `pred-fab` (brze akcije u predmetu) | `pred_fab_close` |
| UI-755 | Dodaj belešku | plutajuće — `pred-fab` (brze akcije u predmetu) | `pred_fab_close` |
| UI-756 | ⏱ Pokreni tajmer | plutajuće — `pred-fab` (brze akcije u predmetu) | `pred_fab_close` |
| UI-757 | title: Brze akcije — dodaj dokument, rok, naplatu | plutajuće — `pred-fab` (brze akcije u predmetu) | `pred_fab_toggle` |
| UI-814 | <vrednost> <vrednost> <vrednost> stavk | naplata / fakture (dinamički) | `pred_select` |
| UI-878 | Pokušaj ponovo | kartica predmeta (dinamički) | `pred_load` |
| UI-880 | (bez labele) | kartica predmeta (dinamički) | `pred_select` |
| UI-882 | (bez labele) | kartica predmeta (dinamički) | `pred_toggleOznaci` |
| UI-883 | <vrednost> <vrednost> '; if | kartica predmeta (dinamički) | `kanban_openPredmet` |
| UI-888 | Potvrdi i poveži | kartica predmeta (dinamički) | `pred_confirmLinks` |
| UI-889 | (dinamički tekst — labela zavisi od podataka) | dashboard (dinamički) | `pred_select` |
| UI-997 | Ponovo otvori predmet | kartica predmeta (dinamički) | `pred_reopen` |

### Izrada dokumenata i nacrta (54)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-047 | &#x2715; Ugovor o zastupanju Popunite podatke — ugovor se generiše automatski Ime i prezim | modal `ugovor-modal` (ugovor o zastupanju) | `ugovor_closeModal` |
| UI-048 | &#x2715; | modal `ugovor-modal` (ugovor o zastupanju) | `ugovor_closeModal` |
| UI-059 | Generiši i sačuvaj | modal `ugovor-modal` (ugovor o zastupanju) | `ugovor_generiši` |
| UI-060 | Samo prikaži | modal `ugovor-modal` (ugovor o zastupanju) | `ugovor_generiši` |
| UI-078 | Šabloni dokumenata | bočna traka (glavna navigacija) | `docTplOpen` |
| UI-169 | + Generiši ugovor | kartica predmeta → pan Pregled | `ugovor_openModal` |
| UI-182 | Šabloni | kartica predmeta → pan Pregled | `docTplOpen` |
| UI-186 | Cross-doc analiza — poređenje dokumenata 0 odabrano ▼ | kartica predmeta → pan Dokumenti | `crossdoc_toggleSection` |
| UI-189 | Analiziraj konflikte | kartica predmeta → pan Dokumenti | `crossdoc_analiziraj` |
| UI-276 | Poređenje dokumenata | kartica predmeta → pan AI Analiza | `openCrossDoc` |
| UI-410 | ✕ Učitavam dokument... Tekst dokumenta nije dostupan — dokument je možda istekao (čuva se  | modal `si-overlay` (Novi predmet iz dokumenta) | `dokPreviewClose` |
| UI-412 | ✕ | modal `si-overlay` (Novi predmet iz dokumenta) | `dokPreviewClose` |
| UI-413 | Šabloni dokumenata Generiši pravni akt automatski — tužbe, ugovori, punomoćja ✕ ⌕ Esc Saču | modal `doctpl-overlay` (šabloni dokumenata) | `docTplClose` |
| UI-415 | ✕ | modal `doctpl-overlay` (šabloni dokumenata) | `docTplClose` |
| UI-416 | placeholder: Pretraži šablone… | modal `doctpl-overlay` (šabloni dokumenata) | `docTplFilter` |
| UI-418 | Generiši dokument | modal `doctpl-overlay` (šabloni dokumenata) | `docTplGeneriši` |
| UI-419 | Kopiraj | modal `doctpl-overlay` (šabloni dokumenata) | `docTplKopiraj` |
| UI-420 | Sačuvaj uz predmet | modal `doctpl-overlay` (šabloni dokumenata) | `docTplSacuvaj` |
| UI-478 | (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | tab AI radni prostor (`tab-aiws`) | `doc_upload_file` |
| UI-479 | Prevucite ugovor ovde ili kliknite za odabir Podržani formati: PDF, DOCX (do 25MB) | tab AI radni prostor (`tab-aiws`) | `doc_upload_trigger` |
| UI-480 | ✕ Ukloni | tab AI radni prostor (`tab-aiws`) | `doc_clear_session` |
| UI-483 | placeholder: DD.MM.YYYY | tab AI radni prostor (`tab-aiws`) | `doc_rokovi_recalc` |
| UI-484 | Prikaži rokove | tab AI radni prostor (`tab-aiws`) | `doc_prikaži_rokove` |
| UI-486 | Forenzička analiza dokumenta | tab AI radni prostor (`tab-aiws`) | `doc_forensic_audit` |
| UI-492 | Tužba za naknadu štete | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-493 | Tužba — radni spor | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-494 | Tužba za razvod braka | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-495 | Žalba na presudu (parnica) | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-496 | Žalba na presudu (nacrt) | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-497 | Žalba na rešenje | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-498 | Odgovor na tužbu | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-499 | Prigovor na platni nalog | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-500 | Prigovor na rešenje o izvršenju | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-501 | Predlog za privremenu meru | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-502 | Predlog za izvršenje | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-503 | Urgencija sudu | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-504 | Krivična prijava | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-505 | Žalba na presudu (krivična) | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-506 | Opomena pre tužbe | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-507 | Zahtev zaposlenog poslodavcu | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-508 | Obaveštenje o otkazu ugovora | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-509 | Ugovor o radu — neodređeno vreme | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-510 | Ugovor o radu — određeno vreme | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-511 | Aneks ugovora o radu | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-512 | Sporazumni raskid radnog odnosa | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-513 | Ugovor o kupoprodaji | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-514 | Ugovor o zakupu nepokretnosti | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-515 | Punomoćje | tab AI radni prostor (`tab-aiws`) | `_selectPodnesakOption` |
| UI-662 | Kopiraj tekst | tab Podešavanja (`tab-settings`) | `copyPodnesak` |
| UI-664 | ⬇ DOCX | tab Podešavanja (`tab-settings`) | `nacrtExportDocx` |
| UI-861 | Generiši nacrt | dashboard (dinamički) | `_generateDraftFromQA` |
| UI-942 | (dinamički tekst — labela zavisi od podataka) | šabloni dokumenata (dinamički) | `docTplIzaberi` |
| UI-1001 | Kopiraj tekst | razno / pomoćni paneli (dinamički) | `ugovor_kopiraj` |
| UI-1002 | Štampaj / PDF | razno / pomoćni paneli (dinamički) | `ugovor_stampaj` |

### AI analiza i procena predmeta (52)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-142 | ↺ | kartica predmeta → pan Pregled | `matter_intel_load` |
| UI-143 | ↻ Analiziraj | kartica predmeta → pan Pregled | `pred_runPipeline` |
| UI-206 | Digital Twin — simulacija razvoja PRO AI simulira 3 scenarija razvoja predmeta (optimistič | kartica predmeta → pan Strategija | `twinPanelShow` |
| UI-207 | Analiza uspeha kancelarije PRO Statistika svih zatvorenih predmeta vaše kancelarije — koji | kartica predmeta → pan Strategija | `outcome_intel_panel_show` |
| UI-209 | Pokreni simulaciju (3 kredita) | kartica predmeta → pan Strategija | `twinSimulirajPokreni` |
| UI-212 | Analiziraj | kartica predmeta → pan Strategija | `twinStaAkoPokreni` |
| UI-255 | AI Briefing — sledeći korak | kartica predmeta → pan AI Analiza | `_intelBriefingLoad` |
| UI-256 | Winning Strategy Brief — sve uvide na jednom mestu | kartica predmeta → pan AI Analiza | `_winningBriefLoad` |
| UI-257 | Prijem predmeta Analizira sve informacije o predmetu i daje pregled slučaja | kartica predmeta → pan AI Analiza | `agent_select` |
| UI-258 | Istraživanje zakona Pronalazi relevantne zakone i presude za vaš slučaj | kartica predmeta → pan AI Analiza | `agent_select` |
| UI-259 | Pisanje podnesaka Pomaže u pisanju tužbi, žalbi i pravnih dokumenata | kartica predmeta → pan AI Analiza | `agent_select` |
| UI-260 | Slabe tačke odbrane Napada vašu argumentaciju i otkriva slabosti pre suđenja | kartica predmeta → pan AI Analiza | `agent_select` |
| UI-261 | Saveti o naplati Pomaže pri određivanju naknade i tumačenju AKS tarife | kartica predmeta → pan AI Analiza | `agent_select` |
| UI-262 | Rokovi i termini Prati procesne rokove, rokove za žalbu i ključne termine | kartica predmeta → pan AI Analiza | `agent_select` |
| UI-265 | ▶ Pokreni | kartica predmeta → pan AI Analiza | `agent_run` |
| UI-266 | Kopiraj | kartica predmeta → pan AI Analiza | `agent_copy` |
| UI-267 | + Novo | kartica predmeta → pan AI Analiza | `agent_novo` |
| UI-268 | Pokreni tri analize | kartica predmeta → pan AI Analiza | `agent_run_parallel` |
| UI-277 | Potraži slične predmete | kartica predmeta → pan AI Analiza | `brain_load` |
| UI-529 | Crveni tim | tab AI radni prostor (`tab-aiws`) | `stratIzaberiModul` |
| UI-530 | Simulator parnice | tab AI radni prostor (`tab-aiws`) | `stratIzaberiModul` |
| UI-531 | Procena ishoda | tab AI radni prostor (`tab-aiws`) | `stratIzaberiModul` |
| UI-532 | Analiza rizika | tab AI radni prostor (`tab-aiws`) | `stratIzaberiModul` |
| UI-533 | Pravni Revizor | tab AI radni prostor (`tab-aiws`) | `stratIzaberiModul` |
| UI-534 | Analizator svedoka | tab AI radni prostor (`tab-aiws`) | `stratIzaberiModul` |
| UI-535 | Sudija v2 — Debata | tab AI radni prostor (`tab-aiws`) | `stratIzaberiModul` |
| UI-536 | Predikcija ishoda | tab AI radni prostor (`tab-aiws`) | `stratIzaberiModul` |
| UI-540 | Pokreni analizu | tab AI radni prostor (`tab-aiws`) | `stratPokreni` |
| UI-541 | Pokreni kompletnu analizu (6 kredita) | tab AI radni prostor (`tab-aiws`) | `stratOrkestratorPokreni` |
| UI-543 | Kopiraj | tab AI radni prostor (`tab-aiws`) | `stratKopiraj` |
| UI-544 | Potraži slične predmete | tab AI radni prostor (`tab-aiws`) | `litIntelBrainLoad` |
| UI-548 | Profiliši | tab AI radni prostor (`tab-aiws`) | `stratJudgeProfile` |
| UI-551 | Analiziraj | tab AI radni prostor (`tab-aiws`) | `stratOpponentIntel` |
| UI-596 | ↻ Osveži | tab Podešavanja (`tab-settings`) | `confidenceAuditLoad` |
| UI-655 | Sačuvaj u predmet | tab Podešavanja (`tab-settings`) | `analizaSacuvajUPredmet` |
| UI-656 | Generiši nacrt tužbe | tab Podešavanja (`tab-settings`) | `analizaGenerisiNacrt` |
| UI-657 | Pošalji u Strategiju | tab Podešavanja (`tab-settings`) | `analizaDodajUStrategiju` |
| UI-658 | Kopiraj analizu | tab Podešavanja (`tab-settings`) | `analizaKopiraj` |
| UI-819 | Generiši Battle Report — kompletna priprema za ročište (3 kredita) | kartica predmeta (dinamički) | `stratBattleReport` |
| UI-820 | Proveri pouzdanost predikcije (1 kredit) | kartica predmeta (dinamički) | `stratConfidenceCheck` |
| UI-823 | Profil sudije (2 kredita) | kartica predmeta (dinamički) | `stratJudgeProfile` |
| UI-826 | Obaveštajni profil protivnika (2 kredita) | kartica predmeta (dinamički) | `stratOpponentIntel` |
| UI-828 | Proveri reputaciju argumenata (2 kredita) | kartica predmeta (dinamički) | `stratArgumentReputation` |
| UI-866 | <vrednost> funkcija → | kartica predmeta (dinamički) | `pgToggleExpand` |
| UI-949 | Pokušaj ponovo | dashboard (dinamički) | `_cioLoad` |
| UI-950 | Osvezi | dashboard (dinamički) | `_cioLoad` |
| UI-957 | kada je ažurirano? → | kartica predmeta (dinamički) | `_genomHistoryOpen` |
| UI-958 | (dinamički tekst — labela zavisi od podataka) | kartica predmeta (dinamički) | `_genomDetaljiToggle` |
| UI-959 | AI provera: <vrednost> <vrednost> — pogledajte pre oslanjanja na ovu procenu (prikaži) | kartica predmeta (dinamički) | `_genomVerifToggle` |
| UI-960 | istorija | kartica predmeta (dinamički) | `_genomHistoryOpen` |
| UI-962 | <vrednost> <vrednost>% | kartica predmeta (dinamički) | `_genomHeatmapDrill` |
| UI-965 | (dinamički tekst — labela zavisi od podataka) | dashboard (dinamički) | `_itlFilter_set` |

### Kreiranje novog predmeta (Intake) (48)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-061 | &#x2715; Novi predmet Unesite osnovne informacije. Detalje možete dodati naknadno. Naziv p | modal `pred-new-modal` (brzi novi predmet) | `pred_closeNewModal` |
| UI-062 | &#x2715; | modal `pred-new-modal` (brzi novi predmet) | `pred_closeNewModal` |
| UI-066 | Kreiraj predmet | modal `pred-new-modal` (brzi novi predmet) | `pred_kreiraj` |
| UI-095 | + Novi predmet | gornja traka | `intakeOtvori` |
| UI-096 | + Iz dokumenta | gornja traka | `siOtvori` |
| UI-098 | title: Brzo kreiranje predmeta | gornja traka | `qiOtvori` |
| UI-102 | Otvori novi predmet | kartica Predmeti — lista/kanban | `intakeOtvori` |
| UI-103 | Otpremi dokumenta | kartica Predmeti — lista/kanban | `siOtvori` |
| UI-353 | Novi predmet — Intake Wiza | modal `intake-overlay` (Intake Wizard) | `intakeConfirmClose` |
| UI-355 | ✕ | modal `intake-overlay` (Intake Wizard) | `intakeConfirmClose` |
| UI-356 | Iz šablona | modal `intake-overlay` (Intake Wizard) | `intakeTemplateOpen` |
| UI-357 | placeholder: Pretraži po imenu ili firmi... | modal `intake-overlay` (Intake Wizard) | `intakeKlijentSearch` |
| UI-358 | + Dodaj novog klijenta | modal `intake-overlay` (Intake Wizard) | `intakeNoviKlijentOpen` |
| UI-359 | placeholder: Npr: Klijent je dobio otkaz bez otkaznog roka i traženog obrazloženja. Radni odnos traj | modal `intake-overlay` (Intake Wizard) | `intakeOpisChange` |
| UI-361 | (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | modal `intake-overlay` (Intake Wizard) | `intakeUploadFile` |
| UI-370 | Billing podešavanje (opciono) ▼ | modal `intake-overlay` (Intake Wizard) | `intakeBillingToggle` |
| UI-371 | uz kontrolu (`<label>` omotač): Fiksni honorar | modal `intake-overlay` (Intake Wizard) | `intakeBillingTipChange` |
| UI-372 | uz kontrolu (`<label>` omotač): Po satu (tajmer startuje odmah) | modal `intake-overlay` (Intake Wizard) | `intakeBillingTipChange` |
| UI-373 | uz kontrolu (`<label>` omotač): AKS tarifa | modal `intake-overlay` (Intake Wizard) | `intakeBillingTipChange` |
| UI-375 | vizuelna `<label>` iznad (bez `for=`): AKS tarifa | modal `intake-overlay` (Intake Wizard) | `intakeBillingAksIznos` |
| UI-376 | Otvori predmet → | modal `intake-overlay` (Intake Wizard) | `intakePipelineDone` |
| UI-377 | ← Nazad | modal `intake-overlay` (Intake Wizard) | `intakeBack` |
| UI-378 | Dalje → | modal `intake-overlay` (Intake Wizard) | `intakeNext` |
| UI-379 | Novi predmet — iz dokumenta ✕ Korak 1 / 3 — Otpremanje Otpremite dokumenta predmeta Prevuc | modal `si-overlay` (Novi predmet iz dokumenta) | `siConfirmClose` |
| UI-381 | ✕ | modal `si-overlay` (Novi predmet iz dokumenta) | `siConfirmClose` |
| UI-383 | (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | modal `si-overlay` (Novi predmet iz dokumenta) | `siFilesSelected` |
| UI-384 | ← Nazad | modal `si-overlay` (Novi predmet iz dokumenta) | `siBack` |
| UI-385 | Dalje → | modal `si-overlay` (Novi predmet iz dokumenta) | `siNext` |
| UI-386 | Hitan predmet ✕ Brzo kreiranje bez analize — popunite minimum podataka. Klijent * Naziv pr | modal `si-overlay` (Novi predmet iz dokumenta) | `qiZatvori` |
| UI-388 | ✕ | modal `si-overlay` (Novi predmet iz dokumenta) | `qiZatvori` |
| UI-389 | placeholder: Pretraži po imenu... | modal `si-overlay` (Novi predmet iz dokumenta) | `qiKlijentSearch` |
| UI-392 | Kreiraj predmet → | modal `si-overlay` (Novi predmet iz dokumenta) | `qiKreiraj` |
| UI-407 | Šabloni predmeta ✕ Izaberite šablon — predmet se kreira sa predefinisanom hronologijom i p | modal `si-overlay` (Novi predmet iz dokumenta) | `intakeTemplateClose` |
| UI-409 | ✕ | modal `si-overlay` (Novi predmet iz dokumenta) | `intakeTemplateClose` |
| UI-727 | title: Novi predmet | mobilno — donja navigacija | `intakeOtvori` |
| UI-790 | (dinamički tekst — labela zavisi od podataka) | dashboard (dinamički) | `intakeOtvori` |
| UI-879 | Kreiraj prvi predmet | kartica predmeta (dinamički) | `intakeOtvori` |
| UI-941 | (dinamički tekst — labela zavisi od podataka) | modal Intake / Novi predmet iz dokumenta (dinamički) | `intakeTemplateIzaberi` |
| UI-981 | Kreiraj prvi predmet | modal Intake / Novi predmet iz dokumenta (dinamički) | `intakeOtvori` |
| UI-982 | (dinamički tekst — labela zavisi od podataka) | modal Intake / Novi predmet iz dokumenta (dinamički) | `intakeHistOtvoriPredmet` |
| UI-983 | <vrednost> <vrednost> ' : '') | modal Intake / Novi predmet iz dokumenta (dinamički) | `intakeKlijentSelect` |
| UI-984 | title: Ukloni fajl | modal Intake / Novi predmet iz dokumenta (dinamički) | `intakeRemoveFile` |
| UI-985 | (dinamički tekst — labela zavisi od podataka) | modal Intake / Novi predmet iz dokumenta (dinamički) | `siRemoveFile` |
| UI-992 | Sačuvaj | modal Intake / Novi predmet iz dokumenta (dinamički) | `siCorrectEntity` |
| UI-993 | Nastavi na predmet → | modal Intake / Novi predmet iz dokumenta (dinamički) | `siGoToPredmet` |
| UI-994 | Odobri | modal Intake / Novi predmet iz dokumenta (dinamički) | `stagingApprove` |
| UI-995 | Odbij | modal Intake / Novi predmet iz dokumenta (dinamički) | `stagingReject` |
| UI-996 | <vrednost> <vrednost> ' : '') | tab Klijenti (dinamički) | `qiKlijentIzaberi` |

### Tehničke kontrole (zaustavi klik, zatvori panel, okini skriveno polje) (47)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-068 | Nova mogućnost otključana Isprobaj odmah → Zatvori automatski se zatvara za 8 sekundi | modal `progressive disclosure` (otključavanje) | `event.stopPropagation` |
| UI-208 | ✕ | kartica predmeta → pan Strategija | `document.getElementById` |
| UI-210 | ✕ | kartica predmeta → pan Strategija | `document.getElementById` |
| UI-239 | Otkaži | kartica predmeta → pan Naplata | `document.getElementById` |
| UI-252 | ✕ | kartica predmeta → pan Graf znanja | `document.getElementById` |
| UI-322 | Novi klijent ✕ Tip klijenta Fizičko lice Pravno lice Osnovni podaci Ime * Prezime Matični  | modal `crm-overlay` (klijent) | `event.stopPropagation` |
| UI-349 | Kliknite ili prevucite CSV fajl ovde | modal `crm-csv-overlay` (CSV uvoz) | `document.getElementById` |
| UI-354 | Novi predmet — Intake Wizard <button class="intake-panel-close" onclick="in | modal `intake-overlay` (Intake Wizard) | `event.stopPropagation` |
| UI-360 | Prevucite PDF/DOCX ili kliknite za upload Maks. 10MB — rezultati se koriste za bolji predl | modal `intake-overlay` (Intake Wizard) | `document.getElementById` |
| UI-380 | Novi predmet — iz dokumenta ✕ Korak 1 / 3 — Otpremanje Otpremite dokumenta predmeta Prevuc | modal `si-overlay` (Novi predmet iz dokumenta) | `event.stopPropagation` |
| UI-382 | Prevucite PDF, DOCX, TXT ili fotografije (JPG/PNG), ili kliknite za upload Više fajlova od | modal `si-overlay` (Novi predmet iz dokumenta) | `document.getElementById` |
| UI-387 | Hitan predmet ✕ Brzo kreiranje bez analize — popunite minimum podataka. Klijent * Naziv pr | modal `si-overlay` (Novi predmet iz dokumenta) | `event.stopPropagation` |
| UI-394 | Uvezi predmete iz CSV-a ✕ Prihvatamo .csv fajl sa sledećim kolonama: ime, prezime, firma,  | modal `si-overlay` (Novi predmet iz dokumenta) | `event.stopPropagation` |
| UI-396 | Kliknite ili prevucite CSV fajl Maks. 500 redova | modal `si-overlay` (Novi predmet iz dokumenta) | `document.getElementById` |
| UI-401 | Vindex AI Pravni operativni sistem Dobrodošli! Spremni ste za rad. Pratite tri koraka i Vi | modal `si-overlay` (Novi predmet iz dokumenta) | `event.stopPropagation` |
| UI-408 | Šabloni predmeta ✕ Izaberite šablon — predmet se kreira sa predefinisanom hronologijom i p | modal `si-overlay` (Novi predmet iz dokumenta) | `event.stopPropagation` |
| UI-411 | ✕ Učitavam dokument... Tekst dokumenta nije dostupan — dokument je možda istekao (čuva se  | modal `si-overlay` (Novi predmet iz dokumenta) | `event.stopPropagation` |
| UI-414 | Šabloni dokumenata Generiši pravni akt automatski — tužbe, ugovori, punomoćja ✕ ⌕ Esc Saču | modal `doctpl-overlay` (šabloni dokumenata) | `event.stopPropagation` |
| UI-451 | ✕ | tab Kalendar/Rokovi (`tab-kal`) | `document.getElementById` |
| UI-475 | placeholder: npr. Koja je kazna za krađu? Koji su uslovi za uslovnu osudu? | tab AI radni prostor (`tab-aiws`) | `document.getElementById` |
| UI-526 | Prevucite fajlove ovde ili kliknite za izbor PDF, DOCX, TXT — max 2MB po fajlu | tab AI radni prostor (`tab-aiws`) | `document.getElementById` |
| UI-668 | Kliknite ili prevucite fajl ovde PDF, DOCX, JPG, PNG · maks 10 MB | tab Podešavanja (`tab-settings`) | `document.getElementById` |
| UI-687 | ⌕ Esc Sve Predmeti Klijenti Rokovi Zadaci Dokumenti Naplata ↑↓ navigacija Enter otvori Esc | overlay `cmdk-overlay` (komandna paleta) | `event.stopPropagation` |
| UI-710 | Novo ročište ✕ Predmet * Sud * Datum * Vreme (opciono) Sudnica (opciono) Broj predmeta sud | modal `rociste-overlay` (ročište) | `event.stopPropagation` |
| UI-758 | ✕ | modal `ios-install-modal` | `document.getElementById` |
| UI-762 | ✕ | modal `android-install-modal` | `document.getElementById` |
| UI-780 | Zaštita podataka klijenata ✕ Supabase — Predmeti i klijenti Lokacija: Frankfurt, Nemačka ( | modal `data-residency-overlay` | `event.stopPropagation` |
| UI-808 | Istraži zakon | razno / pomoćni paneli (dinamički) | `event.stopPropagation` |
| UI-809 | Analiziraj dokument | razno / pomoćni paneli (dinamički) | `event.stopPropagation` |
| UI-855 | Odustani | razno / pomoćni paneli (dinamički) | `this.closest` |
| UI-857 | Zatvori | razno / pomoćni paneli (dinamički) | `this.closest` |
| UI-864 | 79€/mes samostalno | kartica predmeta (dinamički) | `event.stopPropagation` |
| UI-865 | 39€/mes dodatak | kartica predmeta (dinamički) | `event.stopPropagation` |
| UI-870 | <vrednost> <vrednost> <vrednost> odluka ▾ | sudska praksa / pretraga (dinamički) | `document.getElementById` |
| UI-881 | (bez labele) | kartica predmeta (dinamički) | `event.stopPropagation` |
| UI-898 | title: Pogledaj sadržaj | kartica predmeta (dinamički) | `event.stopPropagation` |
| UI-899 | title: Označi za cross-doc analizu | kartica predmeta (dinamički) | `event.stopPropagation` |
| UI-922 | title: Obriši | kalendar (dinamički) | `event.stopPropagation` |
| UI-961 | title: Klikni za pun tekst | kartica predmeta (dinamički) | `this.classList.toggle` |
| UI-963 | title: Klikni za pun tekst | kartica predmeta (dinamički) | `this.classList.toggle` |
| UI-964 | title: Klikni za pun tekst | kartica predmeta (dinamički) | `this.classList.toggle` |
| UI-979 | <vrednost> <vrednost> ▾ | kartica predmeta (dinamički) | `this.nextElementSibling.classList.toggle` |
| UI-980 | <vrednost> <vrednost> ▾ | kartica predmeta (dinamički) | `this.nextElementSibling.classList.toggle` |
| UI-998 | <vrednost> ✕ <vrednost> Analiza kancelarije — tip: <vrednost> | kartica predmeta (dinamički) | `this.remove` |
| UI-999 | (dinamički tekst — labela zavisi od podataka) | kartica predmeta (dinamički) | `this.closest` |
| UI-1000 | x2715 | razno / pomoćni paneli (dinamički) | `document.getElementById` |
| UI-1006 | x2715 | razno / pomoćni paneli (dinamički) | `document.getElementById` |

### Klijenti (CRM) (44)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-304 | ⚠ Konflikt | tab Klijenti (`tab-k`) | `crmCheckKonfliktOtvori` |
| UI-305 | CSV | tab Klijenti (`tab-k`) | `crmCsvImportOtvori` |
| UI-306 | + Novi klijent | tab Klijenti (`tab-k`) | `crmOtvoriFormu` |
| UI-307 | placeholder: Pretraži po imenu... | tab Klijenti (`tab-k`) | `crm_pretrazi` |
| UI-308 | Traži | tab Klijenti (`tab-k`) | `crm_pretrazi` |
| UI-309 | ← Nazad | tab Klijenti (`tab-k`) | `crmZatvoriProfil` |
| UI-310 | Uredi | tab Klijenti (`tab-k`) | `crmOtvoriFormu` |
| UI-311 | Podaci | tab Klijenti (`tab-k`) | `crmProfilTab` |
| UI-312 | Aktivni predmeti | tab Klijenti (`tab-k`) | `crmProfilTab` |
| UI-313 | Završeni | tab Klijenti (`tab-k`) | `crmProfilTab` |
| UI-314 | Hronologija | tab Klijenti (`tab-k`) | `crmProfilTab` |
| UI-315 | Dokumenti | tab Klijenti (`tab-k`) | `crmProfilTab` |
| UI-316 | Komunikacija | tab Klijenti (`tab-k`) | `crmProfilTab` |
| UI-318 | Sačuvaj | tab Klijenti (`tab-k`) | `crmSacuvajTarifu` |
| UI-319 | Ukloni | tab Klijenti (`tab-k`) | `crmUkloniTarifu` |
| UI-320 | Prikaži poverljive podatke | tab Klijenti (`tab-k`) | `crmOtkrijPoverljivo` |
| UI-321 | Novi klijent ✕ Tip klijenta Fizičko lice Pravno lice Osnovni podaci Ime * Prezime Matični  | modal `crm-overlay` (klijent) | `crmConfirmClose` |
| UI-323 | ✕ | modal `crm-overlay` (klijent) | `crmConfirmClose` |
| UI-325 | Fizičko lice | modal `crm-overlay` (klijent) | `crmSetTip` |
| UI-326 | Pravno lice | modal `crm-overlay` (klijent) | `crmSetTip` |
| UI-327 | placeholder: Ime (ili naziv firme) | modal `crm-overlay` (klijent) | `crmMarkDirty` |
| UI-328 | placeholder: Prezime | modal `crm-overlay` (klijent) | `crmMarkDirty` |
| UI-329 | placeholder: npr. 12345678 | modal `crm-overlay` (klijent) | `crmMarkDirty` |
| UI-330 | Popuni iz APR | modal `crm-overlay` (klijent) | `crmAprAutofill` |
| UI-331 | placeholder: Naziv firme | modal `crm-overlay` (klijent) | `crmMarkDirty` |
| UI-332 | placeholder: email@primer.rs | modal `crm-overlay` (klijent) | `crmMarkDirty` |
| UI-333 | placeholder: +381 ... | modal `crm-overlay` (klijent) | `crmMarkDirty` |
| UI-334 | placeholder: 13 cifara | modal `crm-overlay` (klijent) | `crmMarkDirty` |
| UI-335 | placeholder: Broj pasoša | modal `crm-overlay` (klijent) | `crmMarkDirty` |
| UI-336 | placeholder: PIB firme | modal `crm-overlay` (klijent) | `crmMarkDirty` |
| UI-337 | placeholder: Ulica i broj, grad | modal `crm-overlay` (klijent) | `crmMarkDirty` |
| UI-338 | (bez labele — prva opcija: „Legitimni interes“) | modal `crm-overlay` (klijent) | `crmMarkDirty` |
| UI-339 | placeholder: Interna napomena... | modal `crm-overlay` (klijent) | `crmMarkDirty` |
| UI-340 | Otkaži | modal `crm-overlay` (klijent) | `crmConfirmClose` |
| UI-341 | Sačuvaj klijenta | modal `crm-overlay` (klijent) | `crmSacuvaj` |
| UI-342 | ⚠ Provjera sukoba interesa Ime * Prezime Firma Proveri Zatvori | modal `crm-conflict-overlay` (provera sukoba) | `crmZatvoriKonflikt` |
| UI-346 | Proveri | modal `crm-conflict-overlay` (provera sukoba) | `crmPokreniKonflikt` |
| UI-347 | Zatvori | modal `crm-conflict-overlay` (provera sukoba) | `crmZatvoriKonflikt` |
| UI-348 | ⬆ Import klijenata iz CSV CSV mora imati header red sa kolonama: ime, prezime, firma, emai | modal `crm-csv-overlay` (CSV uvoz) | `crmCsvImportZatvori` |
| UI-350 | (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | modal `crm-csv-overlay` (CSV uvoz) | `crmCsvFileSelected` |
| UI-351 | Uvezi klijente | modal `crm-csv-overlay` (CSV uvoz) | `crmCsvPosalji` |
| UI-352 | Zatvori | modal `crm-csv-overlay` (CSV uvoz) | `crmCsvImportZatvori` |
| UI-832 | (bez labele) | tab Klijenti (dinamički) | `crmOtvoriProfil` |
| UI-833 | (dinamički tekst — labela zavisi od podataka) | tab Klijenti (dinamički) | `crmAnaliziranjeTwin` |

### Naplata, tajmer i finansije (35)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-115 | ▶ Start | kartica predmeta — zaglavlje, tajmer, podtabovi | `timer_start` |
| UI-116 | ■ Stop + Sačuvaj | kartica predmeta — zaglavlje, tajmer, podtabovi | `timer_stop` |
| UI-117 | ✕ | kartica predmeta — zaglavlje, tajmer, podtabovi | `timer_discard` |
| UI-225 | ▶ Start tajmer | kartica predmeta → pan Naplata | `billing_timerToggle` |
| UI-226 | (bez labele — prva opcija: „Po tarifi (AKS)“) | kartica predmeta → pan Naplata | `billing_tipChange` |
| UI-227 | (bez labele — prva opcija: „-- Tarifna stavka --“) | kartica predmeta → pan Naplata | `billing_tarifaChange` |
| UI-230 | + Dodaj | kartica predmeta → pan Naplata | `billing_addEntry` |
| UI-231 | Ponavljajuće fakture ▼ | kartica predmeta → pan Naplata | `billing_toggleRecurring` |
| UI-238 | Sačuvaj šablon | kartica predmeta → pan Naplata | `billing_saveRecurring` |
| UI-240 | + Nov šablon | kartica predmeta → pan Naplata | `billing_showRecurringForm` |
| UI-285 | ↺ | kartica predmeta → pan Profitabilnost | `profitabilnost_load` |
| UI-286 | (bez labele) | kartica predmeta → pan Profitabilnost | `profitabilnost_toggleOptIn` |
| UI-424 | ↺ | tab Finansije (`tab-fin`) | `finLoad` |
| UI-425 | ↻ | tab Finansije (`tab-fin`) | `billingDugovanjaLoad` |
| UI-426 | Detaljni izveštaji ▼ | tab Finansije (`tab-fin`) | `billing_toggleReports` |
| UI-427 | Godišnji | tab Finansije (`tab-fin`) | `billing_openReport` |
| UI-428 | ⏱ Starele stavke | tab Finansije (`tab-fin`) | `billing_openReport` |
| UI-429 | Po tipu predmeta | tab Finansije (`tab-fin`) | `billing_openReport` |
| UI-430 | Po klijentu | tab Finansije (`tab-fin`) | `billing_openReport` |
| UI-431 | ⬇ Preuzmi CSV | tab Finansije (`tab-fin`) | `billing_csvDownload` |
| UI-606 | Sačuvaj SEF | tab Podešavanja (`tab-settings`) | `sef_saveSettings` |
| UI-704 | Sačuvaj | modal `settings-modal` (podaci kancelarije) | `tarife_saveSatnica` |
| UI-858 | x21BA | naplata / fakture (dinamički) | `tarife_resetStavka` |
| UI-859 | placeholder: '+s.aks_iznos+' | naplata / fakture (dinamički) | `tarife_saveStavka` |
| UI-900 | title: Obriši | naplata / fakture (dinamički) | `billing_deleteEntry` |
| UI-901 | Generiši fakturu (<vrednost> stavki · <vrednost> RSD) | naplata / fakture (dinamički) | `billing_generateFakturaPanel` |
| UI-906 | Kreiraj fakturu | naplata / fakture (dinamički) | `billing_doGenerateFaktura` |
| UI-907 | Otkaži | naplata / fakture (dinamički) | `billing_loadEntries` |
| UI-909 | Email | naplata / fakture (dinamički) | `billing_sendEmail` |
| UI-910 | SEF | naplata / fakture (dinamički) | `sef_posalji` |
| UI-911 | XML | naplata / fakture (dinamički) | `sef_preuzmiXml` |
| UI-912 | SEF log | naplata / fakture (dinamički) | `sef_prikaziLog` |
| UI-913 | Generiši | naplata / fakture (dinamički) | `billing_generiši` |
| UI-914 | title: '+(t.aktivan?'Deaktiviraj':'Aktiviraj')+' | naplata / fakture (dinamički) | `billing_deactivateRecurring` |
| UI-977 | Tajmer | dashboard (dinamički) | `billing_timerToggle` |

### Rokovi, ročišta i kalendar (33)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-163 | + Generiši lanac | kartica predmeta → pan Pregled | `pred_rokokiToggle` |
| UI-166 | Generiši i sačuvaj | kartica predmeta → pan Pregled | `pred_rokokiGeneriši` |
| UI-167 | Samo prikaži | kartica predmeta → pan Pregled | `pred_rokokiGeneriši` |
| UI-168 | ✕ | kartica predmeta → pan Pregled | `pred_rokokiOtvoriFormu` |
| UI-213 | + Zakaži | kartica predmeta → pan Rokovi | `rocisteOtvoriFormu` |
| UI-214 | ZPP Lanac rokova ▼ | kartica predmeta → pan Rokovi | `lanac_toggleSection` |
| UI-215 | (bez labele — prva opcija: „-- Tip procesnog akta --“) | kartica predmeta → pan Rokovi | `lanac_tipChange` |
| UI-217 | Izračunaj | kartica predmeta → pan Rokovi | `lanac_kalkulisi` |
| UI-220 | Generiši pripremu za ročište (3 kredita) | kartica predmeta → pan Rokovi | `hccGeneriši` |
| UI-444 | ⬇ .ics | tab Kalendar/Rokovi (`tab-kal`) | `kalendarIcsExport` |
| UI-445 | Google | tab Kalendar/Rokovi (`tab-kal`) | `kalendarGoogleExport` |
| UI-446 | Outlook | tab Kalendar/Rokovi (`tab-kal`) | `kalendarOutlookExport` |
| UI-447 | + Ročište | tab Kalendar/Rokovi (`tab-kal`) | `rocisteOtvoriFormu` |
| UI-448 | ‹ | tab Kalendar/Rokovi (`tab-kal`) | `kalMesecPrev` |
| UI-449 | › | tab Kalendar/Rokovi (`tab-kal`) | `kalMesecNext` |
| UI-450 | Danas | tab Kalendar/Rokovi (`tab-kal`) | `kalMesecToday` |
| UI-485 | Izvezi sve rokove (.ics) | tab AI radni prostor (`tab-aiws`) | `sviRokoviUKalendar` |
| UI-487 | ⏳ Kalkulator zastarelosti | tab AI radni prostor (`tab-aiws`) | `zastToggle` |
| UI-488 | vizuelna `<label>` iznad (bez `for=`): Tip potraživanja | tab AI radni prostor (`tab-aiws`) | `zastTipChange` |
| UI-490 | Izračunaj | tab AI radni prostor (`tab-aiws`) | `kalkulisiZastarelost` |
| UI-709 | Novo ročište ✕ Predmet * Sud * Datum * Vreme (opciono) Sudnica (opciono) Broj predmeta sud | modal `rociste-overlay` (ročište) | `rocisteZatvoriFormu` |
| UI-711 | ✕ | modal `rociste-overlay` (ročište) | `rocisteZatvoriFormu` |
| UI-720 | Sačuvaj | modal `rociste-overlay` (ročište) | `rocisteSnimi` |
| UI-721 | Otkaži | modal `rociste-overlay` (ročište) | `rocisteZatvoriFormu` |
| UI-851 | Follow-up | razno / pomoćni paneli (dinamički) | `startFollowUp` |
| UI-872 | ics | kartica predmeta (dinamički) | `dodajUKalendar` |
| UI-873 | Google | kartica predmeta (dinamički) | `otvoriGoogleKalendar` |
| UI-874 | Outlook | kartica predmeta (dinamički) | `otvoriOutlookKalendar` |
| UI-875 | ics | razno / pomoćni paneli (dinamički) | `dodajUKalendar` |
| UI-876 | Google | razno / pomoćni paneli (dinamički) | `otvoriGoogleKalendar` |
| UI-877 | Outlook | razno / pomoćni paneli (dinamički) | `otvoriOutlookKalendar` |
| UI-895 | Sačuvaj u hronologiju predmeta → | kartica predmeta (dinamički) | `lanac_sacuvaj` |
| UI-923 | <vrednost> '; evs.slice(0, 3).forEach(function(e) { var col = e.tip === 'ro | kalendar (dinamički) | `kalDayClick` |

### Pretraga i pravni upiti (21)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-296 | Pretraži sudsku praksu | tab Sudska praksa (`tab-s`) | `praksa_search` |
| UI-297 | Za/Protiv | tab Sudska praksa (`tab-s`) | `praksa_load_grupisano` |
| UI-298 | Resetuj | tab Sudska praksa (`tab-s`) | `praksa_reset_filters` |
| UI-299 | placeholder: Filtriraj po pravnom stavu... | tab Sudska praksa (`tab-s`) | `praksa_ratio_filter_update` |
| UI-303 | Učitaj još odluka | tab Sudska praksa (`tab-s`) | `praksa_load_more` |
| UI-460 | Nematerijalna šteta | tab AI radni prostor (`tab-aiws`) | `fillQ` |
| UI-461 | Otkaz radnog odnosa | tab AI radni prostor (`tab-aiws`) | `fillQ` |
| UI-462 | Razvod i starateljstvo | tab AI radni prostor (`tab-aiws`) | `fillQ` |
| UI-463 | Zastarelost | tab AI radni prostor (`tab-aiws`) | `fillQ` |
| UI-470 | Pretraži | tab AI radni prostor (`tab-aiws`) | `pretraziInterneStavove` |
| UI-472 | Krivično pravo | tab AI radni prostor (`tab-aiws`) | `oblastiIzaberiOblast` |
| UI-473 | Privredno pravo | tab AI radni prostor (`tab-aiws`) | `oblastiIzaberiOblast` |
| UI-474 | Radno pravo | tab AI radni prostor (`tab-aiws`) | `oblastiIzaberiOblast` |
| UI-476 | Postavi pitanje | tab AI radni prostor (`tab-aiws`) | `oblastiPokreni` |
| UI-477 | Kopiraj | tab AI radni prostor (`tab-aiws`) | `oblastiKopiraj` |
| UI-516 | placeholder: Pretražite sud ili ukucajte naziv... | tab AI radni prostor (`tab-aiws`) | `_sud_filter` |
| UI-653 | Pretraži pravnu bazu | tab Podešavanja (`tab-settings`) | `execQuery` |
| UI-844 | (dinamički tekst — labela zavisi od podataka) | sudska praksa / pretraga (dinamički) | `_sud_select` |
| UI-846 | Prikaži ceo tekst ▼ | razno / pomoćni paneli (dinamički) | `toggleCitat` |
| UI-867 | Prikaži odluku | sudska praksa / pretraga (dinamički) | `praksa_expand_decision` |
| UI-868 | Kopiraj citiranje | sudska praksa / pretraga (dinamički) | `praksa_copy_citation` |

### Ostalo / nesvrstano (20)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-522 | Tužba — saobraćajna nezgoda | tab AI radni prostor (`tab-aiws`) | `fillPodnesakPrimer` |
| UI-523 | Žalba — odbijen zahtev | tab AI radni prostor (`tab-aiws`) | `fillPodnesakPrimer` |
| UI-524 | Izvršenje — neplaćen dug | tab AI radni prostor (`tab-aiws`) | `fillPodnesakPrimer` |
| UI-527 | Osveži | tab AI radni prostor (`tab-aiws`) | `ucitajPlaybookStatus` |
| UI-528 | Obriši sve | tab AI radni prostor (`tab-aiws`) | `obrisiSvPlaybook` |
| UI-545 | Prikaži trendove | tab AI radni prostor (`tab-aiws`) | `litIntelOutcomeShow` |
| UI-619 | kopuj | tab Podešavanja (`tab-settings`) | `integr_copy` |
| UI-620 | kopuj | tab Podešavanja (`tab-settings`) | `integr_copy` |
| UI-621 | kopuj | tab Podešavanja (`tab-settings`) | `integr_copy` |
| UI-665 | Uredi / Follow-up | tab Podešavanja (`tab-settings`) | `editPodnesak` |
| UI-666 | ↺ Regeneriši | tab Podešavanja (`tab-settings`) | `regenerisiPodnesak` |
| UI-702 | Sačuvaj podešavanja | modal `settings-modal` (podaci kancelarije) | `saveSettings` |
| UI-761 | Instaliraj Vindex AI ✕ Dodajte Vindex AI na početni ekran putem Chrome menija: 1 Tapnite t | modal `android-install-modal` | `if` |
| UI-811 | Otvori modul | Digitalna imovina / moduli (dinamički) | `_dimOpenModul` |
| UI-829 | Opozovi | razno / pomoćni paneli (dinamički) | `opoziviApiKljuc` |
| UI-830 | Kopiraj | razno / pomoćni paneli (dinamički) | `navigator.clipboard.writeText` |
| UI-831 | Obriši | razno / pomoćni paneli (dinamički) | `obrisiKomentar` |
| UI-856 | Kopiraj tekst | razno / pomoćni paneli (dinamički) | `navigator.clipboard.writeText` |
| UI-897 | <vrednost> <vrednost> <vrednost> <vrednost> KB | kartica predmeta (dinamički) | `dokUcitajZaAnalizu` |
| UI-1003 | Štampaj / PDF | kartica predmeta (dinamički) | `window.print` |

### Spoljni i pomoćni linkovi (20)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-588 | Otvori | tab Podešavanja (`tab-settings`) | `—` |
| UI-590 | Preuzmi | tab Podešavanja (`tab-settings`) | `—` |
| UI-592 | Otvori | tab Podešavanja (`tab-settings`) | `—` |
| UI-597 | Politika privatnosti | tab Podešavanja (`tab-settings`) | `—` |
| UI-598 | Uslovi korišćenja | tab Podešavanja (`tab-settings`) | `—` |
| UI-627 | Politiku privatnosti | tab Podešavanja (`tab-settings`) | `—` |
| UI-680 | Vindex AI | landing stranica | `—` |
| UI-684 | Politika privatnosti | landing stranica | `—` |
| UI-685 | Uslovi korišćenja | landing stranica | `—` |
| UI-770 | Puni tekst Uslova korišćenja → | modal `tos-overlay` (uslovi korišćenja) | `—` |
| UI-771 | Puna Politika privatnosti → | modal `tos-overlay` (uslovi korišćenja) | `—` |
| UI-772 | Puni AI Disclosure dokument → | modal `tos-overlay` (uslovi korišćenja) | `—` |
| UI-773 | DPA za poslovne korisnike → | modal `tos-overlay` (uslovi korišćenja) | `—` |
| UI-775 | Uslove korišćenja | modal `tos-overlay` (uslovi korišćenja) | `—` |
| UI-776 | Politiku privatnosti | modal `tos-overlay` (uslovi korišćenja) | `—` |
| UI-834 | Preuzmi | tab Klijenti (dinamički) | `—` |
| UI-845 | 1 | sudska praksa / pretraga (dinamički) | `—` |
| UI-908 | Preuzmi PDF | naplata / fakture (dinamički) | `—` |
| UI-919 | Preuzmi | kartica predmeta (dinamički) | `—` |
| UI-945 | (dinamički tekst — labela zavisi od podataka) | administracija (dinamički) | `—` |

### Komandna paleta / brze akcije (19)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-029 | Novi predmet Novi klijent Baza znanja Pokreni analizu | overlay `vx2-qa-overlay` (Brze akcije) | `vxCoreCloseQA` |
| UI-030 | Novi predmet | overlay `vx2-qa-overlay` (Brze akcije) | `vxCoreCloseQA` |
| UI-031 | Novi klijent | overlay `vx2-qa-overlay` (Brze akcije) | `vxCoreCloseQA` |
| UI-032 | Baza znanja | overlay `vx2-qa-overlay` (Brze akcije) | `vxCoreCloseQA` |
| UI-033 | Pokreni analizu | overlay `vx2-qa-overlay` (Brze akcije) | `vxCoreCloseQA` |
| UI-088 | ⌕ Pretraži predmete, klijente, dokumente, zadatke... ⌘K | gornja traka | `cmdkOpen` |
| UI-686 | ⌕ Esc Sve Predmeti Klijenti Rokovi Zadaci Dokumenti Naplata ↑↓ navigacija Enter otvori Esc | overlay `cmdk-overlay` (komandna paleta) | `cmdkClose` |
| UI-688 | placeholder: Pretraži predmete, klijente, dokumente, zadatke, naplatu... | overlay `cmdk-overlay` (komandna paleta) | `cmdkQuery` |
| UI-689 | Sve | overlay `cmdk-overlay` (komandna paleta) | `cmdkSetFilter` |
| UI-690 | Predmeti | overlay `cmdk-overlay` (komandna paleta) | `cmdkSetFilter` |
| UI-691 | Klijenti | overlay `cmdk-overlay` (komandna paleta) | `cmdkSetFilter` |
| UI-692 | Rokovi | overlay `cmdk-overlay` (komandna paleta) | `cmdkSetFilter` |
| UI-693 | Zadaci | overlay `cmdk-overlay` (komandna paleta) | `cmdkSetFilter` |
| UI-694 | Dokumenti | overlay `cmdk-overlay` (komandna paleta) | `cmdkSetFilter` |
| UI-695 | Naplata | overlay `cmdk-overlay` (komandna paleta) | `cmdkSetFilter` |
| UI-803 | VINDEX CORE | razno / pomoćni paneli (dinamički) | `vxCoreQuickActions` |
| UI-915 | (dinamički tekst — labela zavisi od podataka) | komandna paleta (dinamički) | `cmdkClose` |
| UI-916 | (dinamički tekst — labela zavisi od podataka) | komandna paleta (dinamički) | `cmdkClose` |
| UI-917 | <vrednost> <vrednost> <vrednost> ' : '') | komandna paleta (dinamički) | `cmdkSelect` |

### Digitalna imovina / usklađenost (19)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-554 | placeholder: Postavite pitanje o ZDI, MiCA ili regulativi digitalne imovine… | tab AI radni prostor (`tab-aiws`) | `dimHeroAnaliziraj` |
| UI-555 | Analiziraj | tab AI radni prostor (`tab-aiws`) | `dimHeroAnaliziraj` |
| UI-556 | Otvori | tab AI radni prostor (`tab-aiws`) | `dimOpenCard` |
| UI-557 | Otvori | tab AI radni prostor (`tab-aiws`) | `dimOpenCard` |
| UI-558 | Otvori | tab AI radni prostor (`tab-aiws`) | `dimOpenCard` |
| UI-559 | Otvori | tab AI radni prostor (`tab-aiws`) | `dimOpenCard` |
| UI-560 | AI analiza projekta | tab AI radni prostor (`tab-aiws`) | `dimOpenModul` |
| UI-561 | AML/KYC revizija | tab AI radni prostor (`tab-aiws`) | `dimOpenModul` |
| UI-562 | Pametni ugovori | tab AI radni prostor (`tab-aiws`) | `dimOpenModul` |
| UI-563 | Exchange Reporting Simulator | tab AI radni prostor (`tab-aiws`) | `dimOpenModul` |
| UI-564 | ← Vindex AI - Digitalna imovina & usklađenost | tab AI radni prostor (`tab-aiws`) | `dimBackToOverview` |
| UI-566 | Analiziraj | tab AI radni prostor (`tab-aiws`) | `web3Pokreni` |
| UI-567 | Kopiraj | tab AI radni prostor (`tab-aiws`) | `web3Kopiraj` |
| UI-568 | Prikaži listu jurisdikcija | tab AI radni prostor (`tab-aiws`) | `web3JurisdikcijeLoad` |
| UI-570 | Proveri adrese | tab AI radni prostor (`tab-aiws`) | `web3OfacProveri` |
| UI-572 | Proveri novčanik | tab AI radni prostor (`tab-aiws`) | `web3WalletProvenance` |
| UI-576 | Generiši dossier (PDF, 2 kredita) | tab AI radni prostor (`tab-aiws`) | `web3DossierGeneriraj` |
| UI-578 | Analiziraj CSV | tab AI radni prostor (`tab-aiws`) | `web3CsvUvoz` |
| UI-810 | (dinamički tekst — labela zavisi od podataka) | Digitalna imovina / moduli (dinamički) | `web3IzaberiModul` |

### Nalog i prijava (18)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-001 | &#x2715; | modal `auth-modal` (prijava/registracija) | `closeModal` |
| UI-002 | Prijava | modal `auth-modal` (prijava/registracija) | `setAuthMode` |
| UI-003 | Registracija | modal `auth-modal` (prijava/registracija) | `setAuthMode` |
| UI-006 | aria-label: Prikaži/sakrij lozinku | modal `auth-modal` (prijava/registracija) | `togglePw` |
| UI-007 | Zaboravili ste lozinku? | modal `auth-modal` (prijava/registracija) | `setAuthMode` |
| UI-008 | Prijavite se | modal `auth-modal` (prijava/registracija) | `doLogin` |
| UI-012 | aria-label: Prikaži/sakrij lozinku | modal `auth-modal` (prijava/registracija) | `togglePw` |
| UI-014 | aria-label: Prikaži/sakrij lozinku | modal `auth-modal` (prijava/registracija) | `togglePw` |
| UI-015 | Registruj se | modal `auth-modal` (prijava/registracija) | `doRegister` |
| UI-017 | Pošalji reset link | modal `auth-modal` (prijava/registracija) | `doForgotPassword` |
| UI-018 | ← Nazad na prijavu | modal `auth-modal` (prijava/registracija) | `setAuthMode` |
| UI-020 | aria-label: Prikaži/sakrij lozinku | modal `auth-modal` (prijava/registracija) | `togglePw` |
| UI-022 | aria-label: Prikaži/sakrij lozinku | modal `auth-modal` (prijava/registracija) | `togglePw` |
| UI-023 | Sačuvaj novu lozinku | modal `auth-modal` (prijava/registracija) | `doResetPassword` |
| UI-584 | Resetuj | tab Podešavanja (`tab-settings`) | `doForgotPasswordFromSettings` |
| UI-632 | Odjavi se | tab Podešavanja (`tab-settings`) | `doLogout` |
| UI-681 | Prijavite se -> | landing stranica | `openModal` |
| UI-683 | Već imam nalog | landing stranica | `openModal` |

### Pomoć, podrška i povratna informacija (18)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-034 | 💬 | plutajuće (FAB feedback) | `feedbackOpen` |
| UI-035 | &#x2715; Pošaljite feedback ★ ★ ★ ★ ★ 📷 Uhvati snimak ekrana ✓ Snimljeno Pošaljite | modal `feedback-modal` | `feedbackClose` |
| UI-036 | &#x2715; | modal `feedback-modal` | `feedbackClose` |
| UI-037 | ★ | modal `feedback-modal` | `feedbackSetRating` |
| UI-038 | ★ | modal `feedback-modal` | `feedbackSetRating` |
| UI-039 | ★ | modal `feedback-modal` | `feedbackSetRating` |
| UI-040 | ★ | modal `feedback-modal` | `feedbackSetRating` |
| UI-041 | ★ | modal `feedback-modal` | `feedbackSetRating` |
| UI-043 | 📷 Uhvati snimak ekrana | modal `feedback-modal` | `feedbackCaptureScreenshot` |
| UI-044 | Pošaljite | modal `feedback-modal` | `feedbackSubmit` |
| UI-622 | Koliko je tačan AI? ▸ | tab Podešavanja (`tab-settings`) | `pomocFaqToggle` |
| UI-623 | Kako da uploadujem dokument? ▸ | tab Podešavanja (`tab-settings`) | `pomocFaqToggle` |
| UI-624 | Kako da dodam novog klijenta? ▸ | tab Podešavanja (`tab-settings`) | `pomocFaqToggle` |
| UI-625 | Koja sudska praksa je dostupna? ▸ | tab Podešavanja (`tab-settings`) | `pomocFaqToggle` |
| UI-626 | Da li su moji podaci bezbedni? ▸ | tab Podešavanja (`tab-settings`) | `pomocFaqToggle` |
| UI-628 | Kako da promenim ili otkazhem pretplatu? ▸ | tab Podešavanja (`tab-settings`) | `pomocFaqToggle` |
| UI-631 | Pošalji poruku | tab Podešavanja (`tab-settings`) | `pomocPosalji` |
| UI-862 | Prijavi netačan odgovor | dashboard (dinamički) | `sendFeedback` |

### Glasovna interakcija (16)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-092 | Govori | gornja traka | `voiceStart` |
| UI-097 | title: Glasovna komanda (Alt+V) | gornja traka | `voice_start` |
| UI-145 | title: Glasovni unos | kartica predmeta → pan Pregled | `micToggle` |
| UI-188 | title: Glasovni unos | kartica predmeta → pan Dokumenti | `micToggle` |
| UI-243 | title: Glasovni unos | kartica predmeta → pan Komunikacija | `micToggle` |
| UI-254 | Generiši / osveži procenu predmeta | kartica predmeta → pan AI Analiza | `_voice_refresh_case_dna` |
| UI-465 | title: Glasovni unos — kliknite da diktirate (sr-RS) | tab AI radni prostor (`tab-aiws`) | `micToggle` |
| UI-521 | title: Glasovni unos — diktirajte opis slučaja (sr-RS) | tab AI radni prostor (`tab-aiws`) | `micToggle` |
| UI-728 | title: Vindex Live — glasovna komanda | plutajuće — FAB Vindex Live (glas) | `vxLiveOpen` |
| UI-729 | &#x2715; Povezujem... Da, potvrdi Otkaži Završi razgovor Vindex Live sluša samo dok je ova | modal `vx-voice-modal-overlay` (Vindex Live) | `vxLiveClose` |
| UI-730 | &#x2715; | modal `vx-voice-modal-overlay` (Vindex Live) | `vxLiveClose` |
| UI-731 | Da, potvrdi | modal `vx-voice-modal-overlay` (Vindex Live) | `vxLiveConfirm` |
| UI-732 | Otkaži | modal `vx-voice-modal-overlay` (Vindex Live) | `vxLiveConfirm` |
| UI-733 | Završi razgovor | modal `vx-voice-modal-overlay` (Vindex Live) | `vxLiveClose` |
| UI-750 | ✕ Otkaži | modal `voice-modal` (STARI glasovni modal) | `voice_stop` |
| UI-860 | Pročitaj | dashboard (dinamički) | `vx_tts_toggle` |

### Dashboard i poslovna inteligencija (16)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-131 | ↺ | kartica predmeta → pan Pregled | `ccc_load` |
| UI-452 | Osveži | tab Poslovna inteligencija (`tab-pi`) | `piLoad` |
| UI-650 | (bez labele — prva opcija: „7 dana“) | tab Podešavanja (`tab-settings`) | `analyticsLoad` |
| UI-651 | ↻ | tab Podešavanja (`tab-settings`) | `analyticsLoad` |
| UI-784 | Pokušaj ponovo | dashboard (dinamički) | `dash_load` |
| UI-785 | title: Osveži | dashboard (dinamički) | `_healthIndexLoad` |
| UI-787 | aria-label: Otvori predmet '+escHtml(p.naziv\|\|'')+' | dashboard (dinamički) | `_dashGoToPredmet` |
| UI-796 | (dinamički tekst — labela zavisi od podataka) | dashboard (dinamički) | `_dashGoToPredmet` |
| UI-947 | (dinamički tekst — labela zavisi od podataka) | kancelarija / poslovna inteligencija (dinamički) | `_piSelectFunnel` |
| UI-948 | (bez labele) | kancelarija / poslovna inteligencija (dinamički) | `piReloadFeatures` |
| UI-951 | (dinamički tekst — labela zavisi od podataka) | dashboard (dinamički) | `_dashGoToPredmet` |
| UI-952 | (dinamički tekst — labela zavisi od podataka) | dashboard (dinamički) | `_dashGoToPredmet` |
| UI-953 | (dinamički tekst — labela zavisi od podataka) | dashboard (dinamički) | `_dashGoToPredmet` |
| UI-954 | (dinamički tekst — labela zavisi od podataka) | dashboard (dinamički) | `_dashGoToPredmet` |
| UI-955 | (dinamički tekst — labela zavisi od podataka) | dashboard (dinamički) | `_dashGoToPredmet` |
| UI-956 | (dinamički tekst — labela zavisi od podataka) | dashboard (dinamički) | `_dashGoToPredmet` |

### Saradnja i kancelarija (16)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-246 | Pošalji | kartica predmeta → pan Komunikacija | `dodajKomentar` |
| UI-250 | + Dodaj saradnika | kartica predmeta → pan Saradnja | `saradnja_dodaj` |
| UI-432 | ↺ | tab Kancelarija (`tab-kanc`) | `kancelarijaLoad` |
| UI-434 | Kreiraj | tab Kancelarija (`tab-kanc`) | `kancelarijaKreiraj` |
| UI-435 | Prihvati pozivnicu | tab Kancelarija (`tab-kanc`) | `kancPrihvati` |
| UI-436 | Odbij | tab Kancelarija (`tab-kanc`) | `kancOdbij` |
| UI-437 | Preimenuj | tab Kancelarija (`tab-kanc`) | `kancRename` |
| UI-440 | Pošalji | tab Kancelarija (`tab-kanc`) | `kancPozovi` |
| UI-441 | Napusti firmu | tab Kancelarija (`tab-kanc`) | `kancOstavi` |
| UI-468 | + Dodaj stav | tab AI radni prostor (`tab-aiws`) | `dodajInterniStav` |
| UI-471 | Obriši sve stavove | tab AI radni prostor (`tab-aiws`) | `obrisiSveInterneStavove` |
| UI-815 | (bez labele) | kancelarija / poslovna inteligencija (dinamički) | `kancPromeniUlogu` |
| UI-816 | Suspenduj | kancelarija / poslovna inteligencija (dinamički) | `kancSuspenduj` |
| UI-817 | Reaktiviraj | kancelarija / poslovna inteligencija (dinamički) | `kancReaktiviraj` |
| UI-818 | (dinamički tekst — labela zavisi od podataka) | kancelarija / poslovna inteligencija (dinamički) | `kancUkloni` |
| UI-885 | title: Ukloni saradnika | kartica predmeta (dinamički) | `saradnja_ukloni` |

### Plan, pretplata i krediti (14)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-024 | &#x2715; | modal `paywall-modal` | `closePaywall` |
| UI-025 | Pretplatite se -> | modal `paywall-modal` | `openSubscription` |
| UI-026 | &#x2715; PRO Vindex AI PRO Otključajte VindexAI PRO Modul za podneske dostupan je isključi | modal `pro-upgrade-modal` | `closeProUpgradeModal` |
| UI-027 | &#x2715; | modal `pro-upgrade-modal` | `closeProUpgradeModal` |
| UI-028 | Pogledajte planove i cene -> | modal `pro-upgrade-modal` | `closeProUpgradeModal` |
| UI-045 | &#x2715; Odaberite plan za vašu kancelariju Bez skrivenih troškova. Otkazivanje u bilo kom | modal `pro-modal` (cenovnik / planovi) | `closeProModal` |
| UI-046 | &#x2715; | modal `pro-modal` (cenovnik / planovi) | `closeProModal` |
| UI-190 | pogledajte planove → | kartica predmeta → pan Strategija | `openProModal` |
| UI-583 | Upravljaj | tab Podešavanja (`tab-settings`) | `openSubscription` |
| UI-594 | ↻ Osveži | tab Podešavanja (`tab-settings`) | `planLoad` |
| UI-595 | ⬆ Upgrade plan | tab Podešavanja (`tab-settings`) | `openProModal` |
| UI-812 | Zatražite aktivaciju — 39€/mes | Digitalna imovina / moduli (dinamički) | `pricing_kontakt` |
| UI-813 | Pogledajte cene — od 39€/mes | Digitalna imovina / moduli (dinamički) | `openProModal` |
| UI-863 | (dinamički tekst — labela zavisi od podataka) | sudska praksa / pretraga (dinamički) | `pricing_kontakt` |

### Notifikacije (14)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-084 | (bez labele) | bočna traka (glavna navigacija) | `notif_toggleDropdown` |
| UI-093 | title: Obaveštenja | gornja traka | `notif_toggleDropdown` |
| UI-289 | Uključi podsetnik za rokove | kartica predmeta → pan Profitabilnost | `subscribePush` |
| UI-641 | ↻ | tab Podešavanja (`tab-settings`) | `adminNotifLoad` |
| UI-642 | (bez labele — prva opcija: „Svi kanali“) | tab Podešavanja (`tab-settings`) | `adminNotifLoad` |
| UI-643 | (bez labele — prva opcija: „Svi statusi“) | tab Podešavanja (`tab-settings`) | `adminNotifLoad` |
| UI-759 | (bez labele) | mobilno — panel notifikacija | `mobNotifZatvori` |
| UI-760 | ✕ | mobilno — panel notifikacija | `mobNotifZatvori` |
| UI-890 | title: Osveži | notifikacije (dinamički) | `notif_load` |
| UI-891 | Označi sve | notifikacije (dinamički) | `notif_markAllRead` |
| UI-892 | (dinamički tekst — labela zavisi od podataka) | notifikacije (dinamički) | `notif_click` |
| UI-893 | Označi sve | notifikacije (dinamički) | `notif_markAllRead` |
| UI-894 | (dinamički tekst — labela zavisi od podataka) | notifikacije (dinamički) | `notif_click` |
| UI-939 | Retry | administracija (dinamički) | `adminNotifRetry` |

### Podešavanja i integracije (14)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-086 | Svetla tema | bočna traka (glavna navigacija) | `toggleLightTheme` |
| UI-100 | title: Podešavanja | gornja traka | `openSettings` |
| UI-288 | + Novi ključ | kartica predmeta → pan Profitabilnost | `kreirajApiKljuc` |
| UI-582 | Sačuvaj | tab Podešavanja (`tab-settings`) | `saveDisplayName` |
| UI-586 | Preuzmi ZIP | tab Podešavanja (`tab-settings`) | `exportSviPodaci` |
| UI-587 | Obriši nalog | tab Podešavanja (`tab-settings`) | `obrisiNalogSelfService` |
| UI-609 | Sačuvaj broj | tab Podešavanja (`tab-settings`) | `sms_sacuvaj` |
| UI-610 | Pošalji test | tab Podešavanja (`tab-settings`) | `sms_testSms` |
| UI-611 | Deaktiviraj | tab Podešavanja (`tab-settings`) | `sms_deaktiviraj` |
| UI-616 | Aktiviraj | tab Podešavanja (`tab-settings`) | `emailNotifSacuvaj` |
| UI-617 | Pošalji test | tab Podešavanja (`tab-settings`) | `emailNotifTest` |
| UI-618 | Deaktiviraj | tab Podešavanja (`tab-settings`) | `emailNotifDeaktivaj` |
| UI-696 | &#x2715; Podešavanja kancelarije Ovi podaci se prikazuju na PDF izveštajima. Čuvaju se lok | modal `settings-modal` (podaci kancelarije) | `closeSettings` |
| UI-697 | &#x2715; | modal `settings-modal` (podaci kancelarije) | `closeSettings` |

### Dokumenti i otpremanje (14)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-099 | title: Uvezi iz CSV | gornja traka | `bulkOtvori` |
| UI-177 | ↻ Osveži | kartica predmeta → pan Pregled | `portal_loadUploads` |
| UI-393 | Uvezi predmete iz CSV-a ✕ Prihvatamo .csv fajl sa sledećim kolonama: ime, prezime, firma,  | modal `si-overlay` (Novi predmet iz dokumenta) | `bulkZatvori` |
| UI-395 | ✕ | modal `si-overlay` (Novi predmet iz dokumenta) | `bulkZatvori` |
| UI-397 | (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | modal `si-overlay` (Novi predmet iz dokumenta) | `bulkParseFile` |
| UI-398 | ← Novi fajl | modal `si-overlay` (Novi predmet iz dokumenta) | `bulkResetUpload` |
| UI-399 | Zatvori | modal `si-overlay` (Novi predmet iz dokumenta) | `bulkZatvori` |
| UI-400 | Uvezi sve | modal `si-overlay` (Novi predmet iz dokumenta) | `bulkImportuj` |
| UI-525 | (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | tab AI radni prostor (`tab-aiws`) | `playbookUploadFajlove` |
| UI-633 | Traži nove biltene | tab Podešavanja (`tab-settings`) | `corpusDiscoverRun` |
| UI-635 | Lista | tab Podešavanja (`tab-settings`) | `lawListLoad` |
| UI-639 | ⬆ Upload | tab Podešavanja (`tab-settings`) | `lawUploadRun` |
| UI-921 | (dinamički tekst — labela zavisi od podataka) | kartica predmeta (dinamički) | `portal_obrisiUpload` |
| UI-940 | (dinamički tekst — labela zavisi od podataka) | administracija (dinamički) | `lawDelete` |

### Izvoz, štampa i poređenje (14)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-133 | PDF | kartica predmeta → pan Pregled | `predmetPdfExport` |
| UI-141 | title: Kopiraj sažetak | kartica predmeta → pan Pregled | `pckCopySazetak` |
| UI-183 | PDF Izveštaj | kartica predmeta → pan Pregled | `predmetPdfExport` |
| UI-302 | Uporedi | tab Sudska praksa (`tab-s`) | `startManualCompare` |
| UI-542 | Word | tab AI radni prostor (`tab-aiws`) | `exportujKaoWord` |
| UI-659 | Izvezi Word | tab Podešavanja (`tab-settings`) | `exportujKaoWord` |
| UI-661 | Preuzmi PDF | tab Podešavanja (`tab-settings`) | `exportPDF` |
| UI-663 | Word | tab Podešavanja (`tab-settings`) | `exportujKaoWord` |
| UI-705 | Poništi | modal `settings-modal` (podaci kancelarije) | `clearCompare` |
| UI-706 | Uporedi odabrane | modal `settings-modal` (podaci kancelarije) | `startCompare` |
| UI-847 | Kopiraj citat | razno / pomoćni paneli (dinamički) | `copyToClipboard` |
| UI-848 | Izvor: <vrednost> | razno / pomoćni paneli (dinamički) | `copyToClipboard` |
| UI-849 | Sačuvaj PDF | razno / pomoćni paneli (dinamički) | `exportPDF` |
| UI-850 | Word | razno / pomoćni paneli (dinamički) | `exportujKaoWord` |

### Portali (klijentski / portal suda) (14)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-170 | + Generiši link | kartica predmeta → pan Pregled | `portal_toggleForm` |
| UI-173 | Generiši link | kartica predmeta → pan Pregled | `portal_generateLink` |
| UI-174 | ✕ | kartica predmeta → pan Pregled | `portal_toggleForm` |
| UI-175 | Kopiraj | kartica predmeta → pan Pregled | `portal_copyLink` |
| UI-176 | ✕ Zatvori | kartica predmeta → pan Pregled | `portal_toggleForm` |
| UI-221 | Praćenje na portal.sud.rs NOVO ▼ | kartica predmeta → pan Rokovi | `portalToggleSection` |
| UI-224 | + Dodaj na praćenje | kartica predmeta → pan Rokovi | `portalDodajPraceni` |
| UI-667 | (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) | tab Podešavanja (`tab-settings`) | `portal_fileSelected` |
| UI-669 | ✕ | tab Podešavanja (`tab-settings`) | `portal_fileOtkazi` |
| UI-671 | ⬆ Pošalji dokument | tab Podešavanja (`tab-settings`) | `portal_uploadFajl` |
| UI-918 | Opozovi | kartica predmeta (dinamički) | `portal_revokeToken` |
| UI-920 | Pregledano | kartica predmeta (dinamički) | `portal_oznacPregledano` |
| UI-1013 | Proveri | kartica predmeta (dinamički) | `portalManualUpdate` |
| UI-1014 | Ukloni | kartica predmeta (dinamički) | `portalUkloni` |

### Bez rukovaoca (statički / vezan iz JS-a) (14)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-589 | Otvori | tab Podešavanja (`tab-settings`) | `—` |
| UI-591 | Preuzmi | tab Podešavanja (`tab-settings`) | `—` |
| UI-593 | Otvori | tab Podešavanja (`tab-settings`) | `—` |
| UI-660 | title: Kliknite za direktno uređivanje teksta | tab Podešavanja (`tab-settings`) | `—` |
| UI-766 | OK | modal `vx-dialog-overlay` (zamena za alert/confirm) | `—` |
| UI-782 | a real-world pattern in this codebase, // not something worth rewriting wholesale this spr | razno / pomoćni paneli (dinamički) | `—` |
| UI-783 | Pokušaj ponovo | razno / pomoćni paneli (dinamički) | `—` |
| UI-798 | <vrednost> <vrednost> · <vrednost> | kancelarija / poslovna inteligencija (dinamički) | `—` |
| UI-852 | Email — formalni, sa pozdravom | razno / pomoćni paneli (dinamički) | `—` |
| UI-853 | Viber — kratak, neformalan (3-4 rečenice) | razno / pomoćni paneli (dinamički) | `—` |
| UI-854 | Pisano obaveštenje — zvanično pismo | razno / pomoćni paneli (dinamički) | `—` |
| UI-871 | Plain-text rezime (kompatibilnost) | administracija (dinamički) | `—` |
| UI-896 | <vrednost> → | dinamički (vindex.js) — nesvrstano | `—` |
| UI-968 | (dinamički tekst — labela zavisi od podataka) | dashboard (dinamički) | `—` |

### Zadaci i workflow (12)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-278 | AI analiza | kartica predmeta → pan Zadaci | `zadaci_ai_analize` |
| UI-279 | ↺ | kartica predmeta → pan Zadaci | `zadaci_load` |
| UI-283 | + Dodaj | kartica predmeta → pan Zadaci | `zadaci_kreiraj` |
| UI-284 | ↺ | kartica predmeta → pan Workflow | `workflow_load` |
| UI-422 | ↺ | tab Zadaci (`tab-zadaci-g`) | `zadaci_g_load` |
| UI-797 | Pokušaj ponovo | kancelarija / poslovna inteligencija (dinamički) | `wsLoad` |
| UI-1007 | (dinamički tekst — labela zavisi od podataka) | kartica predmeta (dinamički) | `zadaci_setStatus` |
| UI-1008 | (dinamički tekst — labela zavisi od podataka) | kartica predmeta (dinamički) | `zadaci_setStatus` |
| UI-1009 | title: Obriši | kartica predmeta (dinamički) | `zadaci_obrisi` |
| UI-1010 | (dinamički tekst — labela zavisi od podataka) | kartica predmeta (dinamički) | `workflow_pokreni` |
| UI-1011 | Završi korak | kartica predmeta (dinamički) | `workflow_zavrsiKorak` |
| UI-1012 | (dinamički tekst — labela zavisi od podataka) | kartica predmeta (dinamički) | `_workflowGoToPredmet` |

### Administracija (11)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-634 | Lista otkrivenih | tab Podešavanja (`tab-settings`) | `corpusListDiscovered` |
| UI-640 | ↻ Osveži sve | tab Podešavanja (`tab-settings`) | `adminOpsLoad` |
| UI-645 | + Dodaj | tab Podešavanja (`tab-settings`) | `adminBetaAdd` |
| UI-646 | ↻ | tab Podešavanja (`tab-settings`) | `adminPineconeLoad` |
| UI-647 | ↻ | tab Podešavanja (`tab-settings`) | `adminFeatureRegistryLoad` |
| UI-648 | (bez labele — prva opcija: „Sve kategorije“) | tab Podešavanja (`tab-settings`) | `adminFeatureRegistryRender` |
| UI-649 | placeholder: Pretraži po nazivu... | tab Podešavanja (`tab-settings`) | `adminFeatureRegistryRender` |
| UI-929 | (dinamički tekst — labela zavisi od podataka) | administracija (dinamički) | `adminFeatureRegistryToggle` |
| UI-930 | Sačuvaj | administracija (dinamički) | `adminFeatureRegistrySave` |
| UI-931 | Više ▾ | administracija (dinamički) | `adminFeatureRegistryToggleMore` |
| UI-938 | Istorija izmena | administracija (dinamički) | `adminFeatureRegistryHistory` |

### Pravni pristanak (uslovi, privatnost, rezidentnost podataka) (9)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-585 | Detalji | tab Podešavanja (`tab-settings`) | `dataResidencyOpen` |
| UI-767 | Uslovi | modal `tos-overlay` (uslovi korišćenja) | `tosTab` |
| UI-768 | Privatnost | modal `tos-overlay` (uslovi korišćenja) | `tosTab` |
| UI-769 | AI Obrada | modal `tos-overlay` (uslovi korišćenja) | `tosTab` |
| UI-774 | uz kontrolu (`<label>` omotač): Potvrđujem da sam pročitao/la Uslove korišćenja i Politiku privatnos | modal `tos-overlay` (uslovi korišćenja) | `tosChkChange` |
| UI-777 | Odjavi se | modal `tos-overlay` (uslovi korišćenja) | `tosDecline` |
| UI-778 | Prihvatam ✓ | modal `tos-overlay` (uslovi korišćenja) | `tosAccept` |
| UI-779 | Zaštita podataka klijenata ✕ Supabase — Predmeti i klijenti Lokacija: Frankfurt, Nemačka ( | modal `data-residency-overlay` | `dataResidencyClose` |
| UI-781 | ✕ | modal `data-residency-overlay` | `dataResidencyClose` |

### Zatvaranje prozora i dijalozi (7)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-067 | Nova mogućnost otključana Isprobaj odmah → Zatvori automatski se zatvara za 8 sekundi | modal `progressive disclosure` (otključavanje) | `_vxPdCloseModal` |
| UI-069 | Isprobaj odmah → | modal `progressive disclosure` (otključavanje) | `_vxPdCloseModal` |
| UI-070 | Zatvori | modal `progressive disclosure` (otključavanje) | `_vxPdCloseModal` |
| UI-707 | &#x2715; | modal `compare-modal` (poređenje verzija) | `closeCompareModal` |
| UI-708 | Zatvori | modal `compare-modal` (poređenje verzija) | `closeCompareModal` |
| UI-763 | Odustani OK | modal `vx-dialog-overlay` (zamena za alert/confirm) | `_vxDlgCancel` |
| UI-765 | Odustani | modal `vx-dialog-overlay` (zamena za alert/confirm) | `_vxDlgCancel` |

### Lista čekanja / rani pristup (7)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-087 | Pozovite kolegu | bočna traka (glavna navigacija) | `wl_open` |
| UI-652 | ↻ Osveži | tab Podešavanja (`tab-settings`) | `wl_admin_load` |
| UI-672 | &#x2715; Early Access Pridružite se Vindex AI Prijavite se za rani pristup. Javićemo vam s | overlay `wl-overlay` (lista čekanja) | `wl_close` |
| UI-673 | &#x2715; | overlay `wl-overlay` (lista čekanja) | `wl_close` |
| UI-679 | Prijavite se za rani pristup | overlay `wl-overlay` (lista čekanja) | `wl_submit` |
| UI-682 | Zatražite rani pristup -> | landing stranica | `wl_open` |
| UI-946 | (bez labele) | administracija (dinamički) | `wl_admin_set_status` |

### Graf znanja i dokazi (7)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-251 | ↺ Osveži graf | kartica predmeta → pan Graf znanja | `kg_load` |
| UI-270 | ↺ Osveži | kartica predmeta → pan AI Analiza | `evidence_load` |
| UI-271 | + Dodaj dokaz | kartica predmeta → pan AI Analiza | `evidence_addDokaz` |
| UI-966 | title: Ponovo pokreni AI klasifikaciju ovog dokumenta | kartica predmeta (dinamički) | `evidence_reklasifikuj` |
| UI-967 | (dinamički tekst — labela zavisi od podataka) | kartica predmeta (dinamički) | `evidence_deleteDokaz` |
| UI-1004 | Generisi graf | kartica predmeta (dinamički) | `evidenceGraph_generiši` |
| UI-1005 | x21BA; Regenerisi | razno / pomoćni paneli (dinamički) | `evidenceGraph_generiši` |

### Onboarding (5)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-402 | Dodajte prvog klijenta Ime, kontakt, tip — 30 sekundi | modal `si-overlay` (Novi predmet iz dokumenta) | `onboardingStep` |
| UI-403 | Otvorite prvi predmet Intake Wizard — automatska ekstrakcija podataka | modal `si-overlay` (Novi predmet iz dokumenta) | `onboardingStep` |
| UI-404 | Postavite pravno pitanje 847 zakona RS + 12.604 presuda — odgovor za &lt;10 sek | modal `si-overlay` (Novi predmet iz dokumenta) | `onboardingStep` |
| UI-405 | Preskoči za sada | modal `si-overlay` (Novi predmet iz dokumenta) | `onboardingDismiss` |
| UI-406 | Počnimo → | modal `si-overlay` (Novi predmet iz dokumenta) | `onboardingStep` |

### Instalacija aplikacije (PWA) (1)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-094 | Instaliraj | gornja traka | `pwaInstall` |

### Prikaži/sakrij (razvijanje panela) (1)

| ID | Labela | Lokacija | Rukovalac (prvi poziv) |
|---|---|---|---|
| UI-654 | uz kontrolu (`<label>` omotač): Ћирилица | tab Podešavanja (`tab-settings`) | `toggleCyrillic` |

## 5. Elementi čiji rukovalac NE POSTOJI

Provereno je svih **445** različitih imena funkcija koja se pozivaju iz inline atributa (`onclick`, `onchange`, `oninput`, `onkeydown`, `onkeyup`, `onsubmit`, `ondblclick`), i u `index.html` i u dinamičkom HTML-u iz `static/vindex.js`.

**Rezultat: 0 elemenata sa nepostojećim rukovaocem.**

Način provere (da nalaz bude proverljiv, a ne tvrdnja):

1. Za svako ime iz rukovaoca traženo je `function <ime>(`, `window.<ime> =`, ili `var/let/const <ime> = function|(...)=>` u `static/vindex.js` + `index.html`.
2. Za imena sa tačkom (`X.Y()`) traženo je `X.Y =` ili poznati DOM/ugrađeni metod.
3. Dodatno je provereno da definicija nije zarobljena u ugnježdenom opsegu:
   - sve definicije rukovalaca su na koloni 0 (globalni opseg) — 0 izuzetaka;
   - nijedan rukovalac nije definisan **samo** unutar nekog od 16 IIFE blokova u `vindex.js` — 0 izuzetaka.

Raspodela načina definisanja:

| Način definisanja | Broj imena |
|---|---|
| `function ime(...)` — globalna funkcija | 427 |
| ugrađeni DOM/JS metod (npr. `event.stopPropagation`) | 13 |
| nije razrešeno automatski (v. napomenu ispod) | 2 |
| `window.ime = ...` | 2 |
| `const/let/var ime = function...` | 1 |

**Napomena o 2 stavke označene kao „nije razrešeno automatski“** — obe su lažni alarm i ručno su provereni:

| Ime | Zašto nije pravi nalaz |
|---|---|
| `function` | Ključna reč iz ugrađene anonimne funkcije unutar `onclick` (npr. `setTimeout(function(){...},120)` na `#tab-btn-kal`) — nije poziv funkcije. |
| `window.print` | Ugrađena funkcija pregledača, `static/vindex.js:22652` („Štampaj / PDF“). |

### 5.1 Zamka koja je zamalo dala lažan nalaz — imena funkcija sa našim slovima

Prva verzija ove provere koristila je obrazac `[A-Za-z_$][A-Za-z0-9_$]*` za ime funkcije, pa je **preskočila 7 rukovalaca čije ime sadrži `š`, `ć` ili `ž`**. Da to nije uočeno, izveštaj bi te elemente prikazao kao „bez rukovaoca“. Obrazac je proširen na Unicode i sve su ručno proverene:

| Ime funkcije | Postoji? | Gde se koristi |
|---|---|---|
| `pred_rokokiGeneriši` | da (1 definicija) | `#pred-rokovi-btn` — „Generiši i sačuvaj“ i „Samo prikaži“ |
| `ugovor_generiši` | da (1 definicija) | `#uz-btn` — ugovor o zastupanju |
| `hccGeneriši` | da (1 definicija) | `#hcc-btn` — priprema za ročište |
| `docTplGeneriši` | da (1 definicija) | `#doctpl-gen-btn` — generisanje dokumenta iz šablona |
| `doc_prikaži_rokove` | da (1 definicija) | dugme „Prikaži rokove“ u analizi dokumenta |
| `billing_generiši` | da (1 definicija) | dinamičko dugme u naplati (`static/vindex.js`) |
| `evidenceGraph_generiši` | da (1 definicija) | dugme „Generisi graf“ (`static/vindex.js`) |

**Zaključak: nijedan od njih nije mrtvo dugme.** Nalaz se beleži kao metodološko upozorenje za ostale agente — svaka automatska provera nad ovom bazom koda mora da podržava naša slova u imenima funkcija.

## 6. Interaktivnost vezana preko `addEventListener` (nije u tabeli iznad)

Ovi rukovaoci nisu inline atributi pa nemaju svoj `UI-` broj, ali menjaju ponašanje elemenata koji su u inventaru.
Najvažniji su dva **delegirana** rukovaoca — jedan klik na roditelja pokriva sve redove u listi:

| Fajl:linija | Element | Događaj | Uloga |
|---|---|---|---|
| `static/vindex.js:8284` | `#pred-list` | `click` | delegirani klik na red liste predmeta |
| `static/vindex.js:8288` | `#pred-istorija-list` | `click` | delegirani klik na stavku istorije predmeta |
| `static/vindex.js:8274` | `#auth-modal` | `click` | zatvara modal klikom na pozadinu |
| `static/vindex.js:8275` | `#paywall-modal` | `click` | zatvara modal klikom na pozadinu |
| `static/vindex.js:8276` | `#pro-modal` | `click` | zatvara modal klikom na pozadinu |
| `static/vindex.js:5215` | `.pred-subtab-nav` | `scroll` | ažurira indikator „ima još tabova desno“ |
| `static/vindex.js:9556-9558` | zona za prevlačenje fajlova | `dragover`/`dragleave`/`drop` | otpremanje dokumenta prevlačenjem |
| `static/vindex.js:12206-12207` | inline polje za izmenu | `blur`/`keydown` | čuva vrednost pri izlasku ili Enter-u |
| `static/vindex.js:12790` | kartice u showcase-u | `click` | prebacivanje kartica |
| `static/vindex.js:19823-19894` | SVG graf znanja | `mouseenter`/`mousemove`/`click`/`wheel`/`mousedown`/`dblclick` | zumiranje, pomeranje i izbor čvora |
| `static/vindex.js:14608` | traka tabova | `scroll` | strelice za skrol tabova |
| `static/vindex.js:7168-7202` | privremeni modali koje pravi JS | `click` | zatvaranje klikom na pozadinu |
| `static/vindex.js:22985` | dinamički generisan element | `click` | v. kod na toj liniji |
| `static/vindex.js:537` | dugme „ponovi“ u poruci o grešci | `click` | ponavlja neuspelu radnju |

**Nije provereno:** da li svi ovi elementi zaista postoje u trenutku vezivanja rukovaoca — to je van opsega inventara. Status: `UNVERIFIED`.

## 7. Elementi bez ijedne labele

Kriterijum: nema vidljivog teksta, nema `title`, nema `aria-label`, nema `placeholder`, nema `<label>` omotač niti `<label>` neposredno iznad.

**Ukupno: 72.**

| ID | Selektor | Lokacija | Vrsta | Rukovalac / uloga |
|---|---|---|---|---|
| UI-084 | `#tab-btn-notif` | bočna traka (glavna navigacija) | tab | `notif_toggleDropdown()` |
| UI-085 | `#tab-btn-pi` | bočna traka (glavna navigacija) | tab | `setTab()` |
| UI-089 | `#mi-overlay` | gornja traka | dugme (div) | `mesecniIzvestajZatvori()` |
| UI-090 | `#mi-mesec-sel` | gornja traka | polje | `mesecniIzvestajUcitaj()` |
| UI-184 | `#pred-upload-input` | kartica predmeta → pan Dokumenti | polje | `pred_upload_doc()` |
| UI-215 | `#lanac-tip` | kartica predmeta → pan Rokovi | polje | `lanac_tipChange()` |
| UI-219 | `#hcc-tip` | kartica predmeta → pan Rokovi | polje | (bez labele — prva opcija: „Parničan (ZPP)“) |
| UI-226 | `#billing-tip` | kartica predmeta → pan Naplata | polje | `billing_tipChange()` |
| UI-227 | `#billing-tarifa-sel` | kartica predmeta → pan Naplata | polje | `billing_tarifaChange()` |
| UI-233 | `#rec-ucestalost` | kartica predmeta → pan Naplata | polje | (bez labele — prva opcija: „Mesečno“) |
| UI-236 | `#rec-datum` | kartica predmeta → pan Naplata | polje | (bez labele) |
| UI-249 | `#saradnja-uloga` | kartica predmeta → pan Saradnja | polje | (bez labele — prva opcija: „Čitanje — samo pregled“) |
| UI-281 | `#zadaci-prioritet` | kartica predmeta → pan Zadaci | polje | (bez labele — prva opcija: „Normalan prioritet“) |
| UI-282 | `#zadaci-rok` | kartica predmeta → pan Zadaci | polje | (bez labele) |
| UI-286 | `#profit-opt-in` | kartica predmeta → pan Profitabilnost | polje | `profitabilnost_toggleOptIn()` |
| UI-292 | `#praksa-matter` | tab Sudska praksa (`tab-s`) | polje | (bez labele — prva opcija: „Sva pravna oblast“) |
| UI-293 | `#praksa-court` | tab Sudska praksa (`tab-s`) | polje | (bez labele — prva opcija: „Svi sudovi“) |
| UI-338 | `#crm-f-osnov` | modal `crm-overlay` (klijent) | polje | `crmMarkDirty()` |
| UI-350 | `#crm-csv-file` | modal `crm-csv-overlay` (CSV uvoz) | polje | `crmCsvFileSelected()` |
| UI-361 | `#intake-file-input` | modal `intake-overlay` (Intake Wizard) | polje | `intakeUploadFile()` |
| UI-362 | `#intake-f-naziv` | modal `intake-overlay` (Intake Wizard) | polje | (bez labele) |
| UI-363 | `#intake-f-tip` | modal `intake-overlay` (Intake Wizard) | polje | (bez labele — prva opcija: „Opšti“) |
| UI-364 | `#intake-f-opis` | modal `intake-overlay` (Intake Wizard) | polje | (bez labele) |
| UI-366 | `#intake-f-vrsta` | modal `intake-overlay` (Intake Wizard) | polje | (bez labele) |
| UI-368 | `#intake-f-rok` | modal `intake-overlay` (Intake Wizard) | polje | (bez labele) |
| UI-383 | `#si-file-input` | modal `si-overlay` (Novi predmet iz dokumenta) | polje | `siFilesSelected()` |
| UI-391 | `#qi-tip` | modal `si-overlay` (Novi predmet iz dokumenta) | polje | (bez labele — prva opcija: „Opšti“) |
| UI-397 | `#bulk-file-input` | modal `si-overlay` (Novi predmet iz dokumenta) | polje | `bulkParseFile()` |
| UI-421 | `#doctpl-result-txt` | modal `doctpl-overlay` (šabloni dokumenata) | polje | (bez labele) |
| UI-439 | `#kancelarija-invite-uloga` | tab Kancelarija (`tab-kanc`) | polje | (bez labele — prva opcija: „Partner“) |
| UI-478 | `#doc-upload-input` | tab AI radni prostor (`tab-aiws`) | polje | `doc_upload_file()` |
| UI-525 | `#playbook-file-input` | tab AI radni prostor (`tab-aiws`) | polje | `playbookUploadFajlove()` |
| UI-565 | `#web3-tekst` | tab AI radni prostor (`tab-aiws`) | polje | (bez labele) |
| UI-629 | `#pomoc-kategorija` | tab Podešavanja (`tab-settings`) | polje | (bez labele — prva opcija: „Tehnički problem“) |
| UI-638 | `#law-pdf-input` | tab Podešavanja (`tab-settings`) | polje | (bez labele — skriveno `input[type=file]`, pokreće ga vidljivo dugme) |
| UI-642 | `#notif-filter-channel` | tab Podešavanja (`tab-settings`) | polje | `adminNotifLoad()` |
| UI-643 | `#notif-filter-status` | tab Podešavanja (`tab-settings`) | polje | `adminNotifLoad()` |
| UI-648 | `#fr-filter-kategorija` | tab Podešavanja (`tab-settings`) | polje | `adminFeatureRegistryRender()` |
| UI-650 | `#analytics-period` | tab Podešavanja (`tab-settings`) | polje | `analyticsLoad()` |
| UI-667 | `#portal-file-input` | tab Podešavanja (`tab-settings`) | polje | `portal_fileSelected()` |
| UI-713 | `#rociste-predmet-id` | modal `rociste-overlay` (ročište) | polje | (bez labele) |
| UI-715 | `#rociste-datum` | modal `rociste-overlay` (ročište) | polje | (bez labele) |
| UI-716 | `#rociste-vreme` | modal `rociste-overlay` (ročište) | polje | (bez labele) |
| UI-719 | `#rociste-napomena` | modal `rociste-overlay` (ročište) | polje | (bez labele) |
| UI-734 | `#mob-more-overlay` | modal `vx-voice-modal-overlay` (Vindex Live) | dugme (div) | `mobileMoreZatvori()` |
| UI-759 | `#mob-notif-overlay` | mobilno — panel notifikacija | dugme (div) | `mobNotifZatvori()` |
| UI-764 | `#vx-dialog-input` | modal `vx-dialog-overlay` (zamena za alert/confirm) | polje | (bez labele) |
| UI-815 | `select` (vindex.js:2767) | kancelarija / poslovna inteligencija (dinamički) | polje | `kancPromeniUlogu()` |
| UI-832 | `tr.vx-grid-row` | tab Klijenti (dinamički) | dugme (tr) | `crmOtvoriProfil()` |
| UI-869 | `input.compare-check` | sudska praksa / pretraga (dinamički) | polje | (bez labele) |
| UI-880 | `#'+p.id+'` | kartica predmeta (dinamički) | dugme (tr) | `pred_select()` |
| UI-881 | `td` (vindex.js:10067) | kartica predmeta (dinamički) | dugme (td) | `event.stopPropagation()` |
| UI-882 | `input.pred-chk` | kartica predmeta (dinamički) | polje | `pred_toggleOznaci()` |
| UI-886 | `#conf-kl-'+i+'` | kartica predmeta (dinamički) | polje | (bez labele) |
| UI-887 | `#conf-rok-0` | kartica predmeta (dinamički) | polje | (bez labele) |
| UI-905 | `#bf-pdv` | naplata / fakture (dinamički) | polje | (bez labele) |
| UI-924 | `#fr-plan-' + key + '` | administracija (dinamički) | polje | (bez labele) |
| UI-926 | `#fr-krediti-' + key + '` | administracija (dinamički) | polje | (bez labele) |
| UI-933 | `#fr-priority-' + key + '` | administracija (dinamički) | polje | (bez labele) |
| UI-934 | `#fr-status-' + key + '` | administracija (dinamički) | polje | (bez labele) |
| UI-935 | `#fr-visible-' + key + '` | administracija (dinamički) | polje | (bez labele) |
| UI-936 | `#fr-version-' + key + '` | administracija (dinamički) | polje | (bez labele) |
| UI-943 | `#dtf-'+f+'` | dinamički (vindex.js) — nesvrstano | polje | (bez labele) |
| UI-944 | `#dtf-'+f+'` | dinamički (vindex.js) — nesvrstano | polje | (bez labele) |
| UI-946 | `select` (vindex.js:15945) | administracija (dinamički) | polje | `wl_admin_set_status()` |
| UI-948 | `select.pi-period-sel` | kancelarija / poslovna inteligencija (dinamički) | polje | `piReloadFeatures()` |
| UI-986 | `#si-f-naziv` | modal Intake / Novi predmet iz dokumenta (dinamički) | polje | (bez labele) |
| UI-987 | `input` (vindex.js:21727) | modal Intake / Novi predmet iz dokumenta (dinamički) | polje | (bez labele) |
| UI-988 | `input` (vindex.js:21729) | modal Intake / Novi predmet iz dokumenta (dinamički) | polje | (bez labele) |
| UI-989 | `input` (vindex.js:21731) | modal Intake / Novi predmet iz dokumenta (dinamički) | polje | (bez labele) |
| UI-990 | `#si-f-klijent` | modal Intake / Novi predmet iz dokumenta (dinamički) | polje | (bez labele) |
| UI-991 | `#si-ent-' + escHtml(ent.entity_id) + '` | modal Intake / Novi predmet iz dokumenta (dinamički) | polje | (bez labele) |

### 7.1 Dodatna napomena — labela postoji ali je dinamička (39)

Ovi elementi imaju tekst, ali se on sastavlja iz podataka u vreme izvršavanja, pa se iz koda ne može pročitati statična labela. **Ovo nije nalaz o nedostatku labele** — samo ograničenje statičke analize.

| ID | Selektor | Lokacija | Rukovalac |
|---|---|---|---|
| UI-790 | `button.kc-qa-btn` | dashboard (dinamički) | `intakeOtvori` |
| UI-791 | `button.kc-qa-btn` | dashboard (dinamički) | `setTab` |
| UI-792 | `button.kc-qa-btn` | dashboard (dinamički) | `openAITool` |
| UI-793 | `button.kc-qa-btn` | dashboard (dinamički) | `setTab` |
| UI-796 | `div.kc-inbox-row` | dashboard (dinamički) | `_dashGoToPredmet` |
| UI-810 | `button.strat-btn` | Digitalna imovina / moduli (dinamički) | `web3IzaberiModul` |
| UI-818 | `button` (vindex.js:2773) | kancelarija / poslovna inteligencija (dinamički) | `kancUkloni` |
| UI-833 | `#crm-twin-analiziraj-btn` | tab Klijenti (dinamički) | `crmAnaliziranjeTwin` |
| UI-844 | `div` (vindex.js:6242) | sudska praksa / pretraga (dinamički) | `_sud_select` |
| UI-863 | `button` (vindex.js:8141) | sudska praksa / pretraga (dinamički) | `pricing_kontakt` |
| UI-889 | `div` (vindex.js:11376) | dashboard (dinamički) | `pred_select` |
| UI-892 | `div.vx-notif-item` | notifikacije (dinamički) | `notif_click` |
| UI-894 | `div.vx-notif-item` | notifikacije (dinamički) | `notif_click` |
| UI-915 | `div.gs-item` | komandna paleta (dinamički) | `cmdkClose` |
| UI-916 | `div.gs-item` | komandna paleta (dinamički) | `cmdkClose` |
| UI-921 | `button` (vindex.js:13559) | kartica predmeta (dinamički) | `portal_obrisiUpload` |
| UI-929 | `button.vx-btn.vx-btn-ghost` | administracija (dinamički) | `adminFeatureRegistryToggle` |
| UI-940 | `button` (vindex.js:15220) | administracija (dinamički) | `lawDelete` |
| UI-941 | `div` (vindex.js:15426) | modal Intake / Novi predmet iz dokumenta (dinamički) | `intakeTemplateIzaberi` |
| UI-942 | `#doctpl-item-'+i+'` | šabloni dokumenata (dinamički) | `docTplIzaberi` |
| UI-945 | `a` (vindex.js:15940) | administracija (dinamički) | `—` |
| UI-947 | `button.pi-ftab'+(i===_piFunnelIdx?'.active':'')+'` | kancelarija / poslovna inteligencija (dinamički) | `_piSelectFunnel` |
| UI-951 | `div` (vindex.js:17748) | dashboard (dinamički) | `_dashGoToPredmet` |
| UI-952 | `div` (vindex.js:17759) | dashboard (dinamički) | `_dashGoToPredmet` |
| UI-953 | `div` (vindex.js:17770) | dashboard (dinamički) | `_dashGoToPredmet` |
| UI-954 | `div` (vindex.js:17785) | dashboard (dinamički) | `_dashGoToPredmet` |
| UI-955 | `div` (vindex.js:17794) | dashboard (dinamički) | `_dashGoToPredmet` |
| UI-956 | `div` (vindex.js:17803) | dashboard (dinamički) | `_dashGoToPredmet` |
| UI-958 | `#genom-detalji-toggle-'+escHtml(predmetId\|\|'')+'` | kartica predmeta (dinamički) | `_genomDetaljiToggle` |
| UI-965 | `button.itl-filter-btn'.+.(isActive` | dashboard (dinamički) | `_itlFilter_set` |
| UI-967 | `button` (vindex.js:18806) | kartica predmeta (dinamički) | `evidence_deleteDokaz` |
| UI-968 | `button.smart-chip.'+c.cls+'` | dashboard (dinamički) | `—` |
| UI-982 | `div` (vindex.js:20719) | modal Intake / Novi predmet iz dokumenta (dinamički) | `intakeHistOtvoriPredmet` |
| UI-985 | `span` (vindex.js:21548) | modal Intake / Novi predmet iz dokumenta (dinamički) | `siRemoveFile` |
| UI-999 | `button` (vindex.js:22443) | kartica predmeta (dinamički) | `this.closest` |
| UI-1007 | `button.vx-kb-move-btn` | kartica predmeta (dinamički) | `zadaci_setStatus` |
| UI-1008 | `button.vx-kb-move-btn` | kartica predmeta (dinamički) | `zadaci_setStatus` |
| UI-1010 | `div.vx-card` | kartica predmeta (dinamički) | `workflow_pokreni` |
| UI-1012 | `a` (vindex.js:23399) | kartica predmeta (dinamički) | `_workflowGoToPredmet` |

### 7.2 Skrivena polja (3)

Nisu vidljiva korisniku pa im labela nije potrebna; navedena su radi potpunosti.

| ID | Selektor | Lokacija |
|---|---|---|
| UI-324 | `#crm-edit-id` | modal `crm-overlay` (klijent) |
| UI-491 | `#podnesak-tip` | tab AI radni prostor (`tab-aiws`) |
| UI-712 | `#rociste-edit-id` | modal `rociste-overlay` (ročište) |

## 8. Šta nije bilo moguće utvrditi (`UNVERIFIED`)

| Pitanje | Status | Razlog |
|---|---|---|
| Da li se gejtovanje po tarifi (Basic/PRO) radi u HTML-u | `UNVERIFIED` | U `index.html` nema nijednog `data-tier`, `data-feature`, `pro-only` ni `locked` markera. Zaključavanje se očigledno radi iz JS-a u vreme izvršavanja, ali koji tačno elementi i pod kojim uslovom — nije čitljivo iz statičkog koda. |
| Da li se svaki element zaista prikaže korisniku | `UNVERIFIED` | Vidljivost zavisi od stanja aplikacije (aktivan tab, otvoren predmet, uloga, podaci sa servera). Kolona „Uslovno prikazan?“ navodi samo uslov koji se vidi iz koda. |
| Da li rukovalac radi ispravno | `UNVERIFIED` | Provereno je samo da funkcija **postoji i da je globalno dostupna**. Ponašanje nije izvršavano. |
| Elementi koje crtaju spoljne biblioteke (Chart.js, Lucide) | `UNVERIFIED` | Nisu u HTML izvoru; nastaju u pregledaču. |
| Da li svi `addEventListener` ciljevi postoje kad se rukovalac vezuje | `UNVERIFIED` | Zahtevalo bi pokretanje aplikacije. |
| Tačna lokacija za 3 dinamičkih elemenata svrstanih kao „nesvrstano“ | `UNVERIFIED` | Funkcija koja ih crta ne pripada jasno nijednom ekranu. |

---

*Kraj inventara. Nijedan fajl aplikacije nije menjan tokom izrade ovog dokumenta.*
