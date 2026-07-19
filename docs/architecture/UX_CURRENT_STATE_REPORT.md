# Vindex AI — UX Current State Report (2026-07-19)

**Metodologija:** ova analiza je urađena ISKLJUČIVO na osnovu čitanja stvarnog
koda — `index.html` (4663 linije), `static/vindex.js` (21823 linije, 771
funkcija, 297 fetch poziva), `static/vindex.css` (9405 linija), i relevantnih
backend ruta gde je trebalo potvrditi šta API stvarno vraća. Nijedan raniji
dokument iz ove sesije (Architecture Bible, Product Philosophy, 90-Day Plan)
nije korišćen kao izvor — svaka tvrdnja ispod je citirana na file:line ili
eksplicitno označena kao neverifikovana ako kod nije dao siguran odgovor.

Ovo je snimak stanja, ne trajan zaključak — kod se menja, ponovo verifikovati
pre oslanjanja na stare brojeve.

---

## Najkritičniji nalazi (ako se čita samo ovo)

1. **Genome Verification Layer (`_verifikacija`, `hard_flags`, `require_review`) ima NULA pojava u frontendu** — potvrđeno grep-om preko `static/vindex.js` i `index.html`. Backend eksplicitno računa da li AI treba da sumnja u sopstveni rezultat; ta procena nikad ne stiže do advokata na ekranu. Videti Sekciju 11.
2. **Prvi vođeni korak u onboardingu je pokvaren** — `onboardingStep(1)` klikće na pogrešno dugme (`.crm-add-btn` selector pogađa "⚠ Konflikt" umesto "+ Novi klijent") zbog duplirane CSS klase. Prvi utisak novog korisnika je bug. Videti Sekcije 1 i 15.
3. **Bogatiji, već napisan 7-koračni onboarding sistem postoji u kodu ali je namerno ugašen** (`onboard_show()` je prazna funkcija, komentar u kodu: "deaktivirano"). Jeftina popravka u odnosu na pisanje novog. Videti Sekcije 5 i 15.
4. **Glasovna komanda je potpuno implementirana ali nevidljiva** — dugme trajno `display:none`, dostupno samo preko Alt+V prečice koja nigde nije napisana u UI-ju. Videti Sekcije 4 i 5.
5. **3-minutni "tihi" timeout kod Strategy job polling-a** — kad posao ne završi u 180s, dugme se otključa bez ijedne poruke korisniku; izgleda kao da se ništa nije desilo. Nigde u kodu ne postoji `AbortController`/klijentski timeout za sinhrone AI pozive. Videti Sekciju 13.

---

## 1. Kompletan User Journey

**Ulazak u aplikaciju.** Auth modal (login/registracija) je prvo što nov
korisnik vidi — nema landing/marketing sadržaja unutar same SPA. Posle
prijave, `onboardingCheck()` (`vindex.js:15153`) proverava `localStorage`
ključ `vx_onboarded_<uid>` i, ako korisnik nema taj ključ i nalog mu je
mlađi od 7 dana, prikazuje `#onboarding-overlay` (`index.html:2304`).

**Onboarding overlay — tri koraka, jedan pokvaren.** Nudi tri stavke:
"Dodajte prvog klijenta", "Otvorite prvi predmet", "Postavite pravno
pitanje" (`index.html:2320-2360`), svaka poziva `onboardingStep(1|2|3)`
(`vindex.js:15190-15209`). Koraci 2 i 3 rade ispravno (otvaraju Intake
Wizard, odnosno fokusiraju pitanje polje). **Korak 1 je pokvaren:**
`onboardingStep(1)` prebaci na Klijenti tab pa posle 400ms uradi
`document.querySelector('.crm-add-btn').click()` (`vindex.js:15196-15197`).
Pravo dugme "+ Novi klijent" nosi klasu `vx-btn vx-btn-primary`, NE
`crm-add-btn` (`index.html:1872`) — tu klasu prvo nosi dugme "⚠ Konflikt"
(`index.html:1870`, `crmCheckKonfliktOtvori()`), pa `querySelector` (vraća
PRVI match) otvara proveru konflikta interesa umesto forme za novog
klijenta. **Verifikovan bug u prvom vođenom koraku koji nov korisnik vidi.**

**Postoji drugi, bogatiji, potpuno mrtav onboarding sistem.**
`vindex.js:18529-18565` definiše `_onboardSteps` — 7-koračni wizard sa
naslovima/tekstom/dots navigacijom (`onboard_render`, `onboard_next`,
`onboard_prev`). `onboard_show()` je eksplicitno prazna funkcija sa
komentarom u kodu: *"deaktivirano — onboardingCheck() je jedini onboarding
flow"* (`vindex.js:18567`). Potpuno napisan, funkcionalan UI blok koji se
nikad ne prikazuje nijednom korisniku.

**Kreiranje klijenta.** `crmOtvoriFormu()` (`vindex.js:4689`) otvara modal;
lista se učitava kroz `ucitajKlijente()` (`vindex.js:4386`), automatski pri
ulasku na Klijenti tab.

**Kreiranje predmeta i unos dokumenata.** Dva paralelna puta: (a)
`pred_kreiraj` — brzi ručni modal (`vindex.js:11977-12003`), (b) Intake
Wizard — CRM+upload+AI ekstrakcija u jednom toku. Posle uploada
(`pred_upload_doc`, `vindex.js:18606-18690`) korisnik vidi spinner i grešku
ako upload padne, ali **nema signal da se u pozadini pokreće Genome
regeneracija** (GPT ekstrakcija + Verification Layer, 15-90s prozor bez
povratne informacije) — korisnik mora ručno da klikne refresh na Case
Genome panelu da vidi da li se nešto promenilo.

**Predmet detalj.** Genome panel (`_caseDnaRender`, `vindex.js:16621`) se
automatski prikazuje kad podaci postoje, bez potrebe za ekstra klikom —
jedini deo toka koji se ponaša vizuelno "autonomno".

**Naplata — neverifikovano.** `naplata` pod-tab nema eksplicitan lazy-load
poziv u `pred_subtabSwitch` listi (svih 8 lazy-load grana pobrojano,
`naplata` odsutan, `vindex.js:10039-10047`). Nije potvrđeno da li se
sadržaj popunjava na drugi način — treba ručno testirati pre pilota, ne
tvrdim da je ovo bug bez potvrde.

---

## 2. Information Architecture

**Trenutna hijerarhija:**

- **13 glavnih tabova u sidebar-u** (`#t-tabs-el`, `index.html:441-511`):
  Pregled dana (h), Predmeti (p), Klijenti (k), Kalendar (kal), Digitalna
  imovina (aiws), Strategija (s), Dokumenti (dok), Document Templates
  (doctpl — otvara modal, ne tab), Zadaci (zadaci-g), Finansije (fin),
  Kancelarija (kanc), Poslovanje/KPI (pi), Podešavanja (settings). Plus 2
  skrivena tab-dugmeta bez vidljivog teksta: `tab-btn-notif` (notifikacije)
  i drugi `tab-btn-pi` (duplikat ulaza za isti "pi" tab — videti Sekciju 6).
- **Detalj predmeta** ima sopstvenu navigaciju od **13 validnih panela**
  (`pred_subtabSwitch`, `vindex.js:9996-10053`): `pregled, dokumenti,
  strategija, rokovi, naplata, komunikacija, saradnja, timeline, agenti,
  graf, zadaci, profitabilnost, workflow`. 4 sekundarna panela
  (`komunikacija, saradnja, graf, profitabilnost`) sakrivena su iza "Više
  ▾" dropdown-a (`vindex.js:10012`), nisu direktno vidljiva.
- **Legacy mapiranje potvrđuje raniju reorganizaciju:** `ccc→pregled`,
  `ai-analiza→agenti`, `dokazi→agenti`, `timeline→rokovi`
  (`vindex.js:9998-10002`) — bar 4 stara imena panela se tiho preusmeravaju
  na naslednike.
- **49 modalnih blokova** direktno u `index.html`, plus dinamički građeni
  modali u JS-u, bez jedne konzistentne konvencije imenovanja (20+
  različitih `open*/close*` funkcija specifičnih po modalu).
- **Global Search / Command Palette** (Ctrl/Cmd+K) postoji i **dobro je
  označen** — ikona + tekst + tooltip u gornjoj traci. Redak primer dobre
  discoverability prakse.
- **`tab-dok` (Dokumenti) je funkcionalno prazan tab** — statički HTML
  pokazuje samo 2 navigacione kartice koje preusmeravaju na Predmeti ili
  Analizu dokumenta (`index.html:3252-3277`, komentar u samom HTML-u:
  "Svi otpremljeni dokumenti su organizovani unutar predmeta..."). Zauzima
  stalno mesto u sidebar-u za nešto što nije samostalna funkcija.

**Predložena idealna hijerarhija — samo gde postoji konkretno imenovan problem:**

1. `tab-dok` ne treba da bude samostalan sidebar tab ako nema sopstveni
   sadržaj — ukloniti ili jasno označiti kao prečicu, ne dupliranu ulaznu
   tačku.
2. "Strategija" postoji na dva strukturno različita mesta (predmet
   pod-tab `strategija`, i globalni PRO-gated `aiws` mod "t" — potvrđeno u
   Sekciji 7 kao DVA različita puta, ne isti sadržaj) — razmotriti
   jedinstveno imenovanje koje razlikuje ova dva (npr. "Strategija
   predmeta" vs "Strategija — kompletna analiza").
3. Dupliran `tab-btn-pi` ulaz (`index.html:498` i `511`) — potvrditi da
   drugi ulaz stvarno služi svrsi pre nego što se ukloni.

---

## 3. Cognitive Load Analysis

Mereno direktnim brojanjem `onclick=`/`<button`/`<input`/`<select`
elemenata u HTML-u (za Dashboard, čiji je statički HTML gotovo prazan,
mereno je unutar JS render funkcije koja ga generiše):

| Ekran | Klikabilni elementi (mereno) | Cognitive load |
|---|---|---|
| Podešavanja (tab-settings) | 131 onclick, 110 button, 38 input, 6 select, 16 linkova — najgušći statički HTML u celoj aplikaciji (108.564 karaktera) | **Veoma visok (9/10)** |
| Dashboard (tab-h) | ~42 onclick + ~15 button generisano dinamički u `_dashRender` (172-linijska funkcija) + varijabilan broj kartica predmeta/rokova | **Visok (8/10)** — obim nije vidljiv iz statičkog HTML-a |
| Predmet detalj (tab-p, 13 pod-tabova) | 131 onclick, 103 button, 31 input, 10 select (116.665 karaktera) | **Visok (8/10)** — dvoslojna navigacija (glavni tab + pod-tab) pre pronalaska konkretne funkcije |
| Digitalna imovina (tab-aiws) | 95 onclick, 86 button, 18 input (49.425 karaktera) | **Visok (7/10)** |
| Klijenti (tab-k) | 69 onclick, 45 button, 33 input, 5 select (52.751 karaktera) | **Srednje visok (6/10)** |
| Kalendar (tab-kal) | 10 onclick, 10 button (3.977 karaktera) | **Nizak (3/10)** |
| Finansije (tab-fin) | 9 onclick, 9 button (3.874 karaktera) | **Nizak (3/10)** |
| Strategija (tab-s, globalni) | 6 onclick, 6 button, 6 input, 2 select (7.191 karaktera) | **Nizak (2/10)** — iznenađujuće malo za modul pozicioniran kao "pravna strategija i preporuke" |
| Dokumenti (tab-dok) | 2 onclick (oba vode na druge tabove) | **Trivijalan (1/10)** — nije funkcionalan ekran, videti Sekciju 2 |

**Ključan nalaz:** tri najgušća ekrana (Podešavanja, Predmet detalj,
Digitalna imovina) čine **59% celog `index.html` fajla** koncentrisano u
samo 3 od 13 glavnih tabova. Nov korisnik koji prvo uđe duboko u predmet ili
Podešavanja nailazi na nesrazmerno veliku gustinu opcija u odnosu na
ostatak aplikacije.

---

## 4. Feature Discoverability

| Funkcija | DA/NE | Zašto |
|---|---|---|
| Kreiranje novog predmeta | **DA** | Vidljivo dugme u Predmeti tabu |
| Case Genome refresh | **DA** | Vidljivo dugme unutar predmeta (`vindex.js:1550` okolina) |
| Global Search (Ctrl+K) | **DA** | Ikona + tekst + tooltip u gornjoj traci — najbolji primer u aplikaciji |
| Document Templates | **DA** | Direktan ulaz u sidebar-u |
| **Glasovna komanda (Voice)** | **NE** | Dugme `voice-cmd-btn` (`index.html:598`) ima `style="display:none;"` TRAJNO — nijedno mesto u 21823 linije JS-a to ne menja na vidljivo. Jedini način aktiviranja: **Alt+V**, prečica koja se nigde u vidljivom UI-ju ne pominje (nema tooltip, nema pomen u Podešavanjima). **Konkretan UX bug po definiciji iz zadatka.** |
| Notifikacije (zvono) | DA, ali indirektno | `tab-btn-notif` je "skriveni" tab bez teksta u sidebar-u, pristupa se preko zasebne zvono-ikone |
| Evidence Graph, Cross-Doc analiza | **Neverifikovano** | Nije pronađen direktan onclick poziv u statičkom `index.html` — moguće kontekstualno dostupno samo unutar dinamički renderovane sekcije predmeta; ne tvrdim konačan zaključak bez dodatne provere |

**Zaključak:** aplikacija uglavnom dobro označava glavne funkcije, ali
Voice Command je konkretan, potvrđen discoverability bug — potpuno
implementirana funkcionalnost bez ijednog vidljivog traga da postoji.

---

## 5. Dead Features

- **`voice-cmd-btn`** (`index.html:598`) — trajno `display:none`, nikad
  postavljeno na vidljivo. Funkcionalnost iza njega (`voice_start`,
  `voice_stop`, `voice_execute`, ceo sistem od `vindex.js:~15999`) je
  potpuno implementirana i radi preko Alt+V — granica između "mrtve
  funkcije" i "discoverability bug-a", pošto se tehnički može aktivirati.
- **`_onboardSteps` / `onboard_show()`** (`vindex.js:18529-18568`) —
  kompletan 7-koračni onboarding wizard sa napisanim tekstom, nikad
  dostižan iz bilo koje žive putanje. `onboard_show()` je prazna funkcija
  sa eksplicitnim komentarom "deaktivirano". Ovo je već napisan sadržaj
  koji trenutno ne donosi nikakvu vrednost.
- **`tab-dok` globalni tab** — graničan slučaj: nije "mrtav" u smislu da se
  ne renderuje (vidljiv je, klikabilan), ali njegova SVRHA (prikaz
  dokumenata) ne postoji — čisto preusmeravajući ekran (videti Sekciju 2).
- **`.vx-skeleton` CSS klasa** (`vindex.css:8924-8930`, shimmer animacija
  definisana) — **0 poziva u celom JS-u**. Mrtav CSS, namera je postojala,
  implementacija nije proširena na aplikaciju.

**Ograničenje metodologije:** nije rađen iscrpan automatizovan popis svih
771 funkcija tražeći one bez ijednog pozivnog mesta — gornje je nađeno
kroz ciljano istraživanje. Za potpunu listu bio bi potreban poseban skript.

---

## 6. Duplicate Actions

- **"Strategija" — predmet pod-tab naspram globalnog `aiws` PRO-gated
  moda.** Ovo je REŠENO pitanje (Sekcija 7 potvrđuje): to su **dva
  strukturno različita puta**, ne isti sadržaj — predmet pod-tab
  `strategija` je deo obične navigacije, dok je `aiws` mod "t" (otvoren
  preko `pred_openStrat`/`pred_launchKompletnaAnaliza`,
  `vindex.js:10226-10247`) PRO-gated. Korisnik koji traži "Strategiju" ima
  dva mesta sa istim imenom i različitim pristupnim pravima — nije bug, ali
  je strukturalna dvosmislenost vredna razjašnjenja u imenovanju (videti
  Sekciju 2, predlog #2).
- **Dupliran `tab-btn-pi` ulaz** (`index.html:498` i `511`) — isti ciljni
  tab (`pi`) ima dva odvojena HTML elementa koja ga otvaraju, jedan
  vidljiv, jedan `vx-hidden-tab`. Verifikovati da drugi ulaz ima stvarnu
  svrhu pre uklanjanja.
- **`_voice_refresh_case_dna` naziv funkcije** (`vindex.js:16445`) — poziva
  se i iz redovnog, uvek-vidljivog dugmeta "Generiši / osveži procenu
  predmeta" (`index.html:1550`), ne samo iz glasovne komande. Nije
  duplirana akcija (razumno ponovno korišćenje koda), ali je konfuzno
  imenovanje — sugeriše pripadnost voice sistemu kad nije.
- **FAB "Dodaj belešku"** navigira na Rokovi pod-tab umesto na formu za
  belešku (`index.html:4366-4432` opseg) — labela i akcija se ne poklapaju.

**Ograničenje:** temeljna detekcija duplikata zahtevala bi semantičko
upoređivanje efekta svih 297 fetch poziva, ne samo strukturne/navigacione
duplikate. Nije potvrđeno da li postoje dodatni semantički duplikati (npr.
dva različita puta za "dodavanje roka" — predmet-specifičan naspram
globalnog kalendara).

---

## 7. Navigation Graph

**Nivo 1 — glavni tabovi** (`setTab`, `vindex.js:2146-2209`), svaki sa
sopstvenom lazy-load funkcijom pozvanom samo pri ulasku (konzistentan
obrazac). Nav history se čuva (max 20), scroll pozicija po tabu se pamti.

**Nivo 2 — predmet pod-tabovi** (`pred_subtabSwitch`, 13 panela). Deep
linking radi (`history.replaceState` upisuje `#pane`).

**Nivo 3 — `aiws` interni mod sistem** (`aiwsSetMode`), sopstveni pod-nivo
navigacije sa pilulama, pamti se `_aiwsMode`.

**Tačan broj koraka po ciljnoj akciji** (od Dashboard-a kao početne tačke,
sintetizovano iz strukture gore):

| Cilj | Koraci | Detalj |
|---|---|---|
| Case Genome (pregled) | **2** | Predmeti → otvori predmet (panel se automatski prikazuje, bez ekstra klika) |
| Novi predmet | **2** | Predmeti tab → dugme "Novi predmet" (`pred_kreiraj` modal) |
| Klijent (kreiranje) | **2** | Klijenti tab → "+ Novi klijent" (u onboardingu ovaj klik trenutno pogađa pogrešno dugme, van onboardinga radi ispravno) |
| Upload (dokumenta) | **3** | Predmeti → otvori predmet → Dokumenti pod-tab → upload |
| Dokument (pregled) | **3** | isto kao upload put |
| Timeline / Rok (predmeta) | **3** | Predmeti → predmet → Rokovi pod-tab (legacy alias `timeline→rokovi`) |
| Rok (globalno, van predmeta) | **2** | Kalendar tab → forma |
| Strategija (predmet pod-tab) | **3** | Predmeti → predmet → Strategija pod-tab |
| Strategija (kompletna analiza, PRO) | **2, ali PRO-gated** | aiws tab → mod "t" (blokirano za ne-PRO korisnike, `openProUpgradeModal()`) |
| CRM (klijenti, pregled) | **1** | Klijenti tab direktno |
| Naplata | **3, neverifikovano** | Predmeti → predmet → Naplata pod-tab — lazy-load poziv nije potvrđen u kodu, videti Sekciju 1 |

Nijedna ciljna akcija ne prelazi 3 koraka osim gde je PRO-gate ili
neverifikovano ponašanje u pitanju — navigaciona dubina sama po sebi nije
problem ove aplikacije.

**Strukturne dvosmislenosti nađene u toku mapiranja grafa:**
- Legacy mapiranje (`ccc→pregled`, `ai-analiza→agenti`, `dokazi→agenti`,
  `timeline→rokovi`) potvrđuje da je predmet-detalj struktura prošla kroz
  najmanje jednu značajniju reorganizaciju — tiho i ispravno, bez vidljivog
  loma za korisnika.
- Dugme sa vidljivom labelom **"AI Analiza"** (`index.html:738`,
  `id="tab-ai-btn"`) otvara panel interno nazvan `agenti`, čiji lazy-load
  poziva `evidence_load()` — naziv dugmeta, ID i stvarni sadržaj koriste tri
  različita pojma za istu stvar. Verovatno bezopasno za korisnika (vidi
  samo labelu), ali vredi potvrditi da panel zaista prikazuje ono što naziv
  obećava.
- **Orphan putanja potvrđena:** `_onboardSteps`/`onboard_show()` sistem
  (Sekcija 5) — nedostižan iz bilo koje žive putanje.

---

## 8. Consistency Audit

**Boje.** Definisane CSS varijable postoje (`vindex.css:2717-2727`:
`--blue:#00d4ff`, `--danger`, `--warn`, `--emerald`), ali postoje **tri
odvojena skupa `:root` varijabli** (linije ~2189, ~2717, ~6169 — potonji
izgleda kao light-theme varijanta). Preko **30 različitih hardcoded hex
boja** korišćeno direktno umesto varijabli (`#f56565`, `#68d391`, `#ecc94b`,
`#f87171`, `#fb923c`, `#34d399`, `#a78bfa`, `#fbbf24`, `#ff6b6b` i dr.) —
sve izgledaju kao ad-hoc varijante istih semantičkih boja
(uspeh/greška/upozorenje) predstavljene različitim tačnim nijansama na
različitim mestima.

**Ikonice — pravilo "samo ✓ ✅ ⚠️" NIJE dosledno poštovano.** U
`vindex.js` nađeno: 📋(12), 🟡(8), 📖(8), 🔴(7), 🟢(5), 🔗(3), 🔒(3), ⛓(3),
⚖(3), 📚(2), 🎯(2), ⛔(2), ⚡(2), ❌(2), plus pojedinačni ⛔🚫🚨🚀🗑🔵🔑🔍🪙🛡.
Konkretni primeri: `vindex.js:6549,6551` (status dot indikatori),
`:5793,5836` (section headers), `:6696-6739` (AI response label liste).
`index.html` je čistiji (dominiraju ✕/✓/⚠/★, plus pojedinačni
🔑📷📤💬⚡).

**Border-radius.** Uglavnom dosledno — pravilo 2-4px poštovano u ~350 od
~360 slučajeva. **7 izuzetaka**, svi u "kc-" prefiksovanoj komponenti
(verovatno Kancelarija/Firm-DNA ekran): `vindex.js:970,977,989,991,1047`
(6-10px) — lokalizovano odstupanje, ne sistemsko.

**Loading state-ovi.** 297 fetch poziva, ali samo 6 CSS referenci na
"spinner" i 0 stvarnih poziva `.vx-skeleton` klase (definisana, nikad
korišćena — mrtav CSS, videti Sekciju 5).

**Toast.** Jedna centralna `showToast(msg, type, duration)` funkcija
(`vindex.js:470`) — dobra konzistentnost, jedna tačka za sve toast poruke.

**Confirmation.** 19 poziva na browser-native `confirm()`
(`vindex.js:3998,4230,4307,4371,4680` i dr.) — funkcionalno, ali native
browser dialog ne prati custom vizuelni identitet aplikacije.

**Keyboard.** Stvarna command palette (Ctrl/Cmd+K, `vindex.js:12849-12860`,
sa Arrow/Enter/Escape navigacijom), Alt+V za glas, Escape zatvara overlay —
pozitivan nalaz, namerna i dosledna keyboard podrška postoji.

**Responsive.** 78 `@media` upita, dominantno `max-width:640px` (36×) plus
nekoliko drugih breakpoint-ova (768/900/375/720/600/560/480px) — stilski
mešano pisanje, ali funkcionalno široka pokrivenost.

---

## 9. Micro UX

| Element | Stanje | Dokazi |
|---|---|---|
| Spinner | Delimično | 6 CSS referenci, nije potvrđena sistematska upotreba na svih 297 fetch poziva |
| Progress indicator (AI analize) | Postoji za async Strategy poslove (`_strat6ModuliHtml`, veštački interpoliran 0-95% iz `elapsedSec/90`) — **ne postoji za multi-agent (`agent_run`) ili upload analizu** | `vindex.js:3570-3586` naspram `:18096-18098`, `:18628` |
| Skeleton loading | Definisano, nekorišćeno | `.vx-skeleton` (`vindex.css:8924`), 0 poziva u JS-u |
| Tooltip | Postoji, umereno | 65× `title=` u `index.html`, 32× u `vindex.js` |
| Keyboard shortcut | Postoji, namerno | Ctrl/Cmd+K, Alt+V, Escape |
| Auto-focus | Postoji, delimično | 16× `.focus()` poziva |
| Auto-save | **Potpuno odsutno** | 0 rezultata za "autosave"/"auto-save" u celom fajlu |
| Undo | **Potpuno odsutno** | 0 rezultata za "undo" u celom fajlu |
| Confirmation pre destruktivnih akcija | Postoji, ali native dialog | 19× `confirm()`, ne custom stilizovan modal |

**Pošten zaključak:** realna investicija u keyboard/tooltip/confirmation UX
postoji, ali auto-save i undo nigde ne postoje — svaka izmena/brisanje je
konačna bez mreže sigurnosti osim browser `confirm()` dijaloga.

---

## 10. AI UX

**Da li korisnik vidi ŠTA AI radi — nekonzistentno između modula:**

- **Case Genome refresh** (`vindex.js:16445-16467`) — najbolje rešen
  slučaj: dugme se menja u `'Generišem procenu... (obično 15–20s)'` PLUS
  paralelan toast. Korisnik dobija i akciju i procenu vremena.
- **Strategy moduli** (`stratPokreni`, `vindex.js:3237-3266`) — generički
  `'⏳ [modul] u toku...'`, procena vremena tek posle prelaska u async (202)
  režim: `'Ovo može trajati 60-90 sekundi. Pratimo napredak...'`, sa
  progres barom i listom 6 modula (✓/⏳/○ po svakom) — eksplicitan prikaz
  šta je urađeno/u toku/tek dolazi.
- **Multi-agent** (`agent_run`, `vindex.js:18096-18098`;
  `agent_run_parallel`, `:18147`) — statičan generički tekst, **bez procene
  vremena, bez progres bara, bez koraka**.
- **Upload + analiza** (`pred_upload_doc`, `:18628`) — `'Analiziram
  predmet...'` sa spinnerom, bez procene trajanja.

**Da li korisnik vidi ZAŠTO traje toliko dugo?** Nigde — samo brojka
sekundi, nikad obrazloženje (npr. "OCR celog dokumenta", "6 uzastopnih GPT
poziva").

**Da li korisnik vidi šta AI ZNA/NE ZNA?** Nema eksplicitnog UI elementa
tipa "AI je pročitao ove dokumente". Jedini posredni signal je
`genome_kompletnost` badge i `'ŠTA NEDOSTAJE'` sekcija — ali to je AI-ova
procena nedostajućeg, ne izjava o pročitanom. Za standalone Strategy
module, korisnik ručno unosi tekst, ali kod nigde ne rekapitulira taj tekst
nazad pre slanja.

---

## 11. Trust Analysis

**Najkritičniji nalaz cele analize.** Grep potvrđuje: `_verifikacija`,
`verifikacija_odluka`, `hard_flags`, `soft_flags`, `require_review` — **nula
pojava** u `static/vindex.js` i `index.html`. Backend eksplicitno računa da
li Genome treba `approve` / `approve_with_warning` / `require_review`, ali
`_caseDnaRender` (`vindex.js:16621-16860`) tu odluku nigde ne čita niti
prikazuje. Advokat koji otvori Case Genome vidi snagu predmeta, faktore,
rangiranu evidenciju — **bez ikakvog vizuelnog signala da li je AI sam sebe
označio kao nesiguran u sopstveni rezultat.** Postoji sloj čija je jedina
svrha upozorenje na nepouzdanost, i on je nem prema korisniku.

**Šta korisnik STVARNO vidi kao signal poverenja:**

- `genome_kompletnost` badge (`vindex.js:16844`) — meri KOMPLETNOST ulaznih
  podataka, ne tačnost same AI procene, ali UI ih tretira vizuelno kao
  jednu stvar.
- `dokazi_rang` — zvezdice/skor + opcioni `d.razlog`, bez porekla skora.
- `najslabija_tacka` — crveni alert box prezentovan kao "činjenica"
  (`vindex.js:16729-16732`), bez indikatora da je ovo AI procena koja može
  biti pogrešna.
- **Multi-agent RAG badge** (`vindex.js:18118`) — JEDINO mesto u celom
  kodu sa eksplicitnim poreklom: `'📚 izvori iz baze'` sa tooltip-om
  "Odgovor koristi izvore iz pravne baze Vindex-a". Pozitivan izuzetak —
  ali `agent_run_parallel` (3 agenta istovremeno, `:18138-18197`) **nema
  ekvivalentan badge po agentu**, rezultat svakog se renderuje identično
  bez signala izvora.
- Standalone Strategy moduli — slobodan formatiran tekst, nema indikatora
  izvora ili pouzdanosti nigde.

**Zaključak:** postoji tačno JEDAN vidljiv mehanizam poverenja (RAG badge
kod pojedinačnog agenta) i JEDAN koji postoji na backendu ali je potpuno
nevidljiv (Verification Layer kod Case Genome-a — arhitektonski najvažniji
AI rezultat u sistemu). Advokat nema način da na ekranu razlikuje "AI je
siguran" od "AI je označio ovo kao sumnjivo".

---

## 12. Explainability

**Polja koja backend šalje i JESU renderovana:** `snaga_faktori[].opis`
(`'ZAŠTO X%'` sekcija, `vindex.js:16660-16668`), `dokazi_rang[].razlog`
(`:16705-16717`), `najslabija_tacka.preporuka` (`:16731-16732`). Sva tri
tražena polja SU prikazana — pozitivan nalaz.

**Ali sva tri su odsečena bez mogućnosti proširenja:** `.slice(0,70)`,
`.slice(0,60)` — ako je GPT-ovo objašnjenje duže od jedne rečenice, tiho je
odsečeno usred rečenice, bez "prikaži više" opcije nigde vidljive.

**Da li korisnik može da klikne do IZVORA?** Ne, nijednom.
- `'Izvori: [relevantni_zakoni]'` footer prikazuje imena zakona kao **plain
  text** — nema linka, nema poziva ka dokument pregledaču.
- `dokazi_rang` nema link ka konkretnom dokumentu/pasusu iz kog je dokaz
  izvučen.
- `najslabija_tacka.preporuka` nema referencu na dokument/presudu/član
  zakona koji je potkrepljuje.
- **`'PREPORUČENI SLEDEĆI KORACI'` sekcija je eksplicitno
  frontend-sintetizovana**, ne backend polje — komentar u kodu:
  *"nema posebnog polja u case_dna, ovo je izvedeno na frontendu"*
  (`vindex.js:16817-16818`). Korisnik ne može da zna da je ovo
  frontend-kompilacija a ne direktan AI izlaz — prikazano identično kao
  svaki drugi AI rezultat.

**Zaključak:** tražena polja SU vidljiva, ali "objašnjenje" postoji kao
odsečen tekst, ne kao trag koji vodi do proverljivog izvora.

---

## 13. Error Recovery

| Scenario | Šta korisnik STVARNO vidi |
|---|---|
| Upload — nečitljiv dokument (OCR neuspeh) | 422 → konkretna poruka: `'Dokument nije čitljiv. Pokušajte sa digitalnim PDF-om...'` (`vindex.js:8730-8731`). Drugi upload put (`pred_upload_doc`) daje generičniju `'Skenirani PDF — uploadujte digitalni PDF.'` (`:18638-18641`) — **dva različita nivoa detalja za istu grešku, zavisno od toga koji upload put je korišćen** |
| GPT/AI poziv padne | Case Genome: generički `showToast('Greška pri generisanju...', 'error')`, bez razloga/predloga. Strategy/multi-agent: sirova `'Greška: ' + e.message` — JS/HTTP poruka neprevedena na jezik korisnika (`vindex.js:3277, 18128, 18194`) |
| Upload ne uspeva (veličina/mreža) | **Dva različita limita veličine fajla u dva upload puta**: 25MB (`doc_upload_file`, `:8681`) naspram 10MB (`pred_upload_doc`, `:18623`) — korisnik ne može unapred da zna koji važi gde. Mrežni pad: specifična poruka `'Nema veze sa serverom.'` postoji u oba puta |
| Analiza traje 5+ minuta | `strat_job_poll` ima hard limit 180s (`vindex.js:3600-3618`) — **kad petlja istekne bez statusa 'done'/'error', dugme se tiho otključa BEZ ikakve poruke**. Ekran ostaje zamrznut na poslednjem prikazanom napretku, izgleda kao da se ništa nije desilo. **Nigde u fajlu ne postoji `AbortController` ili `signal:`** (potvrđeno grep-om) — sinhroni AI pozivi nemaju klijentski timeout uopšte |
| Internet nestane usred operacije | Pokriveno samo za upload; za AI analize svi `catch(e)` blokovi tretiraju mrežni prekid identično kao svaku drugu grešku — ista generička poruka, **nema retry dugmeta nigde** |
| Nepodržan format | Klijentska provera pre slanja u oba puta + server 415 kao dodatna provera — dobra pokrivenost ovog specifičnog slučaja |

**Opšti obrazac:** sistem dobro pokriva "poznate, očekivane" greške vezane
za upload — ali za greške NAKON što je AI poziv već krenuo, poruke
degradiraju na sirovu `e.message` ili tihi timeout bez poruke. Nijedan
pronađen `catch` blok ne nudi retry dugme.

---

## 14. Empty State Audit

| Ekran (0 stavki) | Stvarno stanje u kodu | CTA/struktura? |
|---|---|---|
| Predmeti | Tri različita oblika: `'Nema predmeta.'` (`:4557`, `:10157`), `'Nema predmeta koji zahtevaju hitnu pažnju'` (`:1515`, dashboard-specifično) | **NE** — plain tekst, bez ikone, bez CTA |
| Klijenti | Nije pronađen eksplicitan empty-state tekst unutar budžeta ove analize | Neverifikovano |
| Dokumenti | Dva oblika: `'Nema dokumenata. (Upload: advokat+)'` (`:4608`, CRM wizard) naspram `vxGridEmpty('pred-dok-lista', 'file-text', 'Nema dokumenata', 'Otpremite dokument iznad da počnete.')` (`:11709`, unutar predmeta) | **Delimično** — drugi primer koristi strukturisanu komponentu (ikona+naslov+podtekst), prvi ne |
| Rokovi | `'Nema rokova danas.'` (`:1761`, dashboard panel) | **NE** — plain tekst |
| Uplate/fakture | `'Nema faktura.'` (`:2738`), `'Nema faktura za ovaj period.'` (`:13376`) | **NE** — samo inline color styling |

**Ključan nalaz:** postoji JEDNA dobra, reusable empty-state komponenta
(`vxGridEmpty`, `:15471` — ikona+naslov+podtekst+implicitno uputstvo), ali
je korišćena **samo 5 puta u celoj aplikaciji**. Ostatak empty-state-ova su
ad-hoc plain-text divovi bez jasnog sledećeg koraka za korisnika.

---

## 15. Pilot Readiness

Direktna procena: advokat prvi put otvara sistem, bez pomoći, bez obuke,
15 minuta na raspolaganju.

**Kritično — blokira dobar prvi utisak:**
1. Onboarding korak 1 je pokvaren (Sekcija 1) — prvi vođeni klik otvara
   proveru konflikta interesa umesto forme za novog klijenta.
2. Nema signala da se Genome ažurira u pozadini posle uploada (15-90s
   prozor bez povratne informacije) — korisnik može zaključiti da AI
   analiza "ne radi", posebno rizično u fazi gde se poverenje tek gradi.

**Visok prioritet:**
3. Bogatiji 7-koračni onboarding postoji u kodu, ugašen (Sekcija 5) —
   jeftinija popravka od pisanja novog, ako se odluči da se koristi.
4. FAB "Dodaj belešku" vodi na pogrešan pod-tab.
5. Dvosmislenost "Strategija" koncepta (dva mesta, različito gejtovanje) —
   verovatno generiše pitanja podrške u pilot fazi.

**Srednji prioritet, treba proveriti pre pilota:**
6. `naplata` pod-tab bez potvrđenog lazy-load poziva — ručno testirati.
7. "AI Analiza" labela / `agenti` interno ime / `evidence_load()` sadržaj —
   potvrditi da panel prikazuje ono što naziv obećava.

**Šta NIJE problem, potvrđeno kodom:** deep-linking kroz pod-tabove radi,
scroll pozicija se čuva po tabu, legacy imena panela se tiho i ispravno
preusmeravaju, Case Genome panel se automatski prikazuje bez ekstra klika.

**Nije verifikovano u ovom opsegu:** sadržaj/validacija klijent-forme,
zaštita od duplikata klijenata, funkcionalno ponašanje na mobilnom uređaju
(CSS ima `min-height:44px` na dugmadima — dobar znak za touch, nije
funkcionalno testirano).

---

## 16. UX Severity Matrix (dodatak po zahtevu foundera, 2026-07-19)

Founder je posle prvog čitanja ovog izveštaja eksplicitno tražio da se
nalazi ne ostave kao ravna lista, nego da se rangiraju po
Impact/Frequency/Effort, jer to "mnogo bolji način odlučivanja" od
liste problema bez prioriteta. Skala ★ 1-5 za sva tri stuba (Effort: više
zvezdica = veći/skuplji rad). Priority je izveden iz kombinacije, ne
proizvoljno dodeljen. Gde je founder već dao eksplicitnu ocenu u razgovoru
(Genome Verification, onboarding bug, Voice, Strategy timeout), ta ocena
je ovde direktno preneta, ne ponovo izmišljena.

### P0 — uraditi odmah (visok impact, nizak/srednji effort)

| Problem | Impact | Frequency | Effort | Napomena |
|---|---|---|---|---|
| Genome Verification Layer nevidljiv (Sek. 11) | ★★★★★ | ★★★★★ | ★★ | Backend već računa `_verifikacija`/`hard_flags`/`require_review` — ovo je čisto pitanje prikaza već postojećeg polja, ne nove logike. Founder: "Mercedes ima ABS, vozač nema lampicu." |
| Onboarding korak 1 — pogrešno dugme (Sek. 1, 15) | ★★★★★ | ★★★★ (svaki nov korisnik) | ★ | Nije UX odluka — jedan pogrešan CSS selector (`.crm-add-btn` pogađa "Konflikt" umesto "Novi klijent"). Founder: "To nije UX. To je bug. Popravlja se odmah." |
| Nema signala da Genome radi u pozadini posle uploada (Sek. 1) | ★★★★ | ★★★★★ (svaki upload) | ★★ | Direktno određuje "Time to WOW" (Sekcija 17) — najveći pojedinačni uzrok da prvi utisak ispadne loš ili da se WOW trenutak nikad ne dogodi. |
| Strategy 3-min tihi timeout, nema poruke o napretku (Sek. 13) | ★★★★ | ★★★ | ★★ | Nije problem trajanja — problem je tišine. Founder: "Advokat misli 'sistem se pokvario', a možda AI normalno radi." Rešenje ne mora biti stvaran progres — dovoljne su faze ("Analiziram... Pronalazim praksu... Formiram strategiju...") da korisnik zna da sistem radi. |

### P1 — visok impact, veći effort ili čeka odluku pre rada

| Problem | Impact | Frequency | Effort | Napomena |
|---|---|---|---|---|
| 7-koračni onboarding ugašen (Sek. 5, 15) | Nepoznat dok se ne utvrdi ZAŠTO | — | ★ (samo istraga) | **Nije automatski fix.** Founder eksplicitno: prvo pitati zašto je ugašen — ako je namerno (zbunjivao korisnike), ne vraćati; ako je slučajno ostalo ugašeno, vratiti. Sledeći korak je istraga koda/istorije, ne implementacija. |
| Objašnjivost — odsečen tekst bez "prikaži više", nema linkova ka izvorima (Sek. 12) | ★★★★ (poverenje) | ★★★ | ★★★ | `.slice(0,70)` odseca GPT objašnjenje usred rečenice; izvori prikazani kao plain tekst bez linka na dokument. |
| Strategija dual-path zabuna — predmet pod-tab vs. globalni PRO mod (Sek. 2, 6) | ★★★ | ★★ | ★★ | Rešava se imenovanjem/UI razjašnjenjem, ne restrukturiranjem. |
| Dva različita file-size limita (25MB vs 10MB) na dva upload puta (Sek. 13) | ★★★ | ★★ | ★ | Uskladiti brojku — jeftina popravka. |

### P2 — srednji impact, umeren effort

| Problem | Impact | Frequency | Effort |
|---|---|---|---|
| FAB "Dodaj belešku" vodi na pogrešan pod-tab (Sek. 6) | ★★ | ★★ | ★ |
| Nema retry dugmadi nigde posle greške (Sek. 13) | ★★★ | ★★ | ★★★ |
| Empty state nekonzistentnost — `vxGridEmpty` korišćen samo 5x (Sek. 14) | ★★ | ★★★ | ★★ |
| Ikonice/boje nekonzistentne (15+ emoji tipova, 30+ hex boja) (Sek. 8) | ★★ | ★★★★ | ★★★ |
| `naplata` pod-tab lazy-load neverifikovan (Sek. 1, 7) | ★★★ (ako je stvarno bug) | ★ | ★ (prvo samo proveriti) |
| `tab-dok` prazan redirect-only ekran (Sek. 2) | ★★ | ★ | ★★ |

### P3 — ne dirati sada / backlog

| Problem | Impact | Frequency | Effort | Napomena |
|---|---|---|---|---|
| Voice dugme nevidljivo (Sek. 4, 5) | ★ | ★ | ★★★ | Founder eksplicitno: "Ako niko od beta korisnika ne traži voice, ostavio bih ga ugašenog. Nije P0, nije čak ni P1." |
| Auto-save/undo potpuno odsutno (Sek. 9) | ★★★ | ★★ | ★★★★★ | Impact nije nizak, ali effort je arhitekturna promena, ne UX popravka — flagovati za buduću raspravu, ne sada. |
| `.vx-skeleton` mrtav CSS (Sek. 5, 9) | ★ | ★ | ★★ | |
| Nema `AbortController`/klijentski timeout generalno (Sek. 13) | ★★ | ★★ | ★★★ | Delimično pokriveno P0 stavkom (Strategy timeout poruka) — šira verzija ovog problema čeka. |
| Dupliran `tab-btn-pi` ulaz (Sek. 6) | ★ | ★ | ★ | |

---

## 17. "Vreme do WOW efekta" — procena zasnovana na kodu (NIJE mereno)

Founder je tražio metriku: koliko vremena prođe od login-a do prvog trenutka
kad nov advokat vidi vrednost sistema ("WOW"), sa referentnim okvirom 15min
loše / 3min odlično / 45s fenomenalno.

**Bitna ograda pre brojki:** ovo NIJE izmerena telemetrija — u sistemu
trenutno ne postoji instrumentacija koja beleži `signup_at` /
`prvi_upload_at` / `prva_genome_poseta_at` po korisniku (ista disciplina
kao i ranije u ovoj sesiji — Rule C: ništa se ne tretira kao dokazano dok
nije izmereno). Brojke ispod su **procena zasnovana na koracima
navigacije izbrojanim u Sekciji 7 i na vremenima obrade koje sam kod
prijavljuje korisniku** (npr. `'obično 15–20s'` na Genome dugmetu,
`'60-90 sekundi'` na Strategy modulima). Ovo je hodanje kroz kod, ne
merenje stvarnih korisnika.

### Scenario A — "best case" (korisnik zna da ručno osveži Genome)

| Korak | Procena vremena | Izvor |
|---|---|---|
| Registracija/login | ~15-30s | standardna forma |
| Dodavanje prvog klijenta | ~30-45s | 2 koraka navigacije (Sek. 7) + popunjavanje forme |
| Kreiranje predmeta | ~20-40s | 2 koraka navigacije + forma |
| Upload dokumenta | ~15-30s | 3 koraka navigacije + izbor fajla + potvrda uploada |
| AI Genome generisanje (pozadina) | ~15-90s | kod sam prijavljuje ovaj opseg (`vindex.js:16445`) |
| Ručno osvežavanje + pregled Genome-a (WOW #1) | ~5s | korisnik MORA znati da klikne refresh |
| **Ukupno do prvog Genome WOW-a** | **~2-4 minuta** | u okviru founderovog "odlično" praga |

### Scenario B — realan slučaj prvog korisnika (bez signala, Sek. 1 nalaz)

Isti koraci, ali pošto **ne postoji nikakav signal da je pozadinska
obrada gotova** (potvrđeno u Sekciji 1 — korisnik mora ručno da klikne
refresh na Case Genome panelu bez ijedne naznake da treba to da uradi),
realan tok je:

- Korisnik uploaduje dokument, vidi potvrdu uploada, **ne zna da bilo šta
  drugo treba da uradi**.
- Ako slučajno ponovo otvori predmet ili klikne refresh iz radoznalosti
  (nakon što je već prešao na drugi zadatak) — WOW se dešava, ali sa
  neproizvoljno dugim, neizmerenim kašnjenjem (moglo bi biti 5, 10, 30+
  minuta, ili sledeća sesija).
- Ako korisnik ne zna da postoji Genome funkcija i nikad ne osveži ručno —
  **WOW trenutak se nikad ne dogodi**, iako je AI obrada odavno završena u
  pozadini.

**Zaključak: raspon je "2-4 minuta (dobro)" do "nikad" — i razlika između
ta dva ishoda zavisi od TAČNO JEDNOG nalaza (P0 stavka #3 u Sekciji 16),
ne od deset različitih problema.** Ovo je najjači argument za zašto je taj
nalaz P0: nije samo neprijatnost, on direktno određuje da li se WOW trenutak
uopšte dešava.

### Ako se ide dalje do Strategije (drugi, veći WOW kandidat)

Dodatnih ~60-180s, sa rizikom da founder-ov P0 nalaz #4 (tihi timeout na
180s) taj drugi WOW trenutak pretvori u utisak da se sistem zaglavio, tačno
u trenutku kad bi trebalo da ostavi najjači utisak.

### Preporuka za sledeći korak (ne uraditi sada, samo zapisati)

Prava brojka zahteva stvarnu instrumentaciju — isti obrazac koji je već
primenjen u Smart Intake Fazi 2.1 (`_compute_finalize_wait_s` u
`routers/smart_intake.py`). Tri timestamp-a bi bila dovoljna:
`prvi_upload_at`, `genome_prvi_put_prikazan_at`, razlika između njih po
korisniku. Ovo bi Rule C zahtev (izmeriti pre/posle) pretvorio iz procene
u stvaran broj — ali to je zaseban, mali instrumentacioni zadatak, ne dec
implementacije u Fazi 3.

---

## Napomena o obimu i ograničenjima

Ova analiza je rađena kroz 4 paralelna istraživačka toka zbog veličine
kodbaze (21823 linije JS, 9405 linija CSS, 4663 linije HTML) — svaki tok je
pokrivao određen skup sekcija. Gde je nešto označeno "neverifikovano", to
znači da kod nije dao dovoljno siguran odgovor u raspoloživom budžetu
istraživanja, ne da je zaključeno da problem ne postoji. Preporučuje se
ručna provera u browseru za sve stavke označene "neverifikovano" pre nego
što se tretiraju kao zatvorene.
