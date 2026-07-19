# Vindex AI — Founder Playbook za prezentaciju advokatima (2026-07-19)

**Metodološka napomena:** svaka tvrdnja u ovom dokumentu je verifikovana
direktno u kodu na `main` grani na dan pisanja — frontend tokovi
(`index.html`, `static/vindex.js`), backend endpoint-i (`routers/*.py`).
Gde nešto nije moglo da se potvrdi bez ručnog testiranja u browseru, to
je eksplicitno označeno "PROVERI PRE DEMOA" — nemoj to tretirati kao
sigurno dok sam ne probaš. Ovaj dokument NIJE tehnička dokumentacija —
piši ga kao vodič za sebe, ne kao specifikaciju za programera.

**Trenutno stanje repozitorijuma (bitno za demo):** `main` grana ide u
pilot sa **starim CRM wizard-om kao jedinim putem za kreiranje predmeta**
(`intakeOtvori()`) — "Smart Intake" upload-first tok i "Novi predmet"
chooser ekran postoje ali su namerno NE-merge-ovani (žive na
`feature/new-predmet-chooser` grani), po tvojoj odluci iz
`TRUST_LAYER_BETA_FREEZE_2026-07-19.md`. Ovaj Playbook opisuje ono što
je STVARNO živo za tvoje bета korisnike, ne ono što postoji u kodu na
drugoj grani.

---

# FAZA 1 — Rekonstrukcija proizvoda

## Glavni tok korisnika (potvrđen kodom, `main` grana)

```
START
 ↓
Registracija / Login
 ↓
(nov korisnik, prvih 7 dana) Onboarding overlay — 3 vođena koraka
 ↓
Kreiranje klijenta (CRM)
 ↓
Kreiranje predmeta — Intake Wizard (5 koraka)
 ↓
Upload dokumenta
 ↓
AI obrada (pozadinski, Case Genome regeneracija)
 ↓
Case Genome prikaz
 ↓
[opciono, paralelno, ne linearno] Rokovi · Evidence · Strategy · Naplata
 ↓
Status predmeta na Kanban tabli (Inicijalna procena → ... → Završen)
```

### Korak: Onboarding overlay (samo za nove naloge, prvih 7 dana)

- **Šta korisnik vidi:** overlay preko celog ekrana sa tri konkretne
  stavke: "Dodajte prvog klijenta", "Otvorite prvi predmet", "Postavite
  pravno pitanje".
- **Vrednost:** jasno "počni ovde" umesto praznog dashboard-a.
- **Backend proces:** nijedan — čisto UI vođenje.
- **AI modul:** nijedan.
- **Šta korisnik treba da razume:** ovo su tri NEZAVISNE prečice, ne
  strogi redosled — može ih preskočiti i sam istraživati.

### Korak: Kreiranje klijenta

- **Šta korisnik vidi:** Klijenti tab → "+ Novi klijent" → forma (ime,
  prezime, firma, email, telefon, JMBG, PIB, adresa, pravni osnov
  obrade podataka za GDPR).
- **Vrednost:** centralizovana evidencija klijenata sa GDPR poljem
  ugrađenim od početka, ne naknadno dodatim.
- **Backend proces:** `POST /klijenti`, upis u bazu, bez AI poziva.
- **AI modul:** nijedan.
- **Šta korisnik treba da razume:** samo ime je obavezno — ostatak
  polja može popuniti kasnije, forma ga ne blokira.

### Korak: Kreiranje predmeta — Intake Wizard

- **Šta korisnik vidi:** 5-koračni wizard (`intakeOtvori()`): Klijent →
  Opis problema → Dokumenti → Analiza → Predlog.
- **Vrednost:** GPT-4o-mini izvlači osnovne podatke (naziv predmeta,
  vrsta spora, protivna strana, vrednost spora, prvi rok, potrebni
  dokumenti) iz opisa problema i (opciono) otpremljenih dokumenata —
  umesto ručnog kucanja svakog polja.
- **Backend proces:** `POST /api/dokument/analiza` (po fajlu, ako su
  dokumenti otpremljeni u ovom koraku) → `POST /api/intake/ekstrakcija`
  (GPT-4o-mini) → `POST /api/intake/kreiraj` (kreira predmet + povezuje
  klijenta + dodaje prvi rok ako je prepoznat).
- **AI modul:** GPT-4o-mini ekstrakcija (`routers/intake.py`) — **ovo je
  STARIJI, jednostavniji AI modul od onog koji pokreće Case Genome**,
  bitna razlika za FAZU 7.
- **Šta korisnik treba da razume:** ovaj korak NEMA nikakav "confidence"
  ili "pouzdanost" signal — GPT samo predlaže, korisnik uvek može da
  ispravi svako polje pre potvrde. Nemoj obećavati preciznost koju ovaj
  konkretan korak ne prikazuje (videti FAZU 7).

### Korak: Upload dokumenta (unutar već otvorenog predmeta)

- **Šta korisnik vidi:** upload zonu u Dokumenti pod-tabu, spinner
  tokom otpremanja, zatim potvrdu i (posle par sekundi) status "AI
  analiza u toku" ispod dugmeta za osvežavanje procene.
- **Vrednost:** dokument se automatski klasifikuje (Evidence Vault) i
  Case Genome se sam osvežava u pozadini — korisnik ne mora ručno da
  pokrene ništa.
- **Backend proces:** `POST /api/predmeti/{id}/upload` → paralelno: (a)
  Evidence Vault klasifikacija (`klasifikuj_i_sacuvaj`, GPT-4o-mini,
  ~5-10s), (b) Case Genome regeneracija u pozadini (`_run_genome_background`,
  GPT-4o, ~15-90s, sačekuje 3s da klasifikacija upiše tip dokumenta).
- **AI modul:** dva odvojena — Evidence Vault klasifikator i Case Genome
  ekstraktor. Rade nezavisno, mogu se završiti u različito vreme.
- **Šta korisnik treba da razume:** samo digitalni PDF/DOCX (ne skenirane
  slike) — skenirani dokument vraća grešku sa jasnom porukom. Limit
  veličine fajla je 10MB na ovom putu.

### Korak: Case Genome prikaz

- **Šta korisnik vidi:** automatski prikazan panel čim se otvori predmet
  koji ima analizu — "PREGLED" sažetak na vrhu (Status/Najveća snaga/
  Najveća slabost/Sledeća akcija), AI Provera red, "Na osnovu/Nedostaje"
  red, zatim "Detaljna analiza →" toggle sa 9+ sekcija.
- **Vrednost:** brza orijentacija u predmetu bez ponovnog čitanja celog
  spisa. Detaljna verzija ove sekcije je FAZA 4.
- **Backend proces:** `GET /api/predmeti/{id}/case-dna` (čitanje već
  izračunatog Genome-a) ili `POST .../case-dna/refresh` (ručno osvežavanje).
- **AI modul:** GPT-4o (Case Genome ekstraktor) + deterministički backend
  izračun (Verification Layer, Genome Strength Calibration — objašnjeno
  u FAZI 4).
- **Šta korisnik treba da razume:** ovo NIJE gotov pravni dokument —
  ovo je polazna tačka za sopstvenu analizu, sa vidljivim tragom zašto
  je sistem došao do svakog zaključka.

### Korak: Rokovi / Evidence / Strategy / Naplata (paralelni pod-tabovi, ne linearni)

Sve četiri žive kao pod-tabovi unutar predmeta, dostupne bilo kojim
redosledom posle Genome-a. Detaljno objašnjeno u FAZI 4/5.

**Rokovi pod-tab sadrži DVE odvojene stvari, bitno ih ne mešati u
razgovoru:**
1. Redovna evidencija ročišta/rokova (ručni unos).
2. "Lanac ZPP rokova" — kolapsibilna sekcija, **manuelan alat**:
   korisnik bira tip procesnog akta (npr. "Dostava presude prvostepenog
   suda") i unosi datum, sistem **deterministički** (ne AI, pravilo iz
   ZPP-a — npr. "Rok za žalbu: ZPP čl. 374 st. 1, 15 dana") izračunava
   sve rokove koji iz toga proizilaze. **Ovo NIJE automatski pokrenuto
   otpremanjem dokumenta** — korisnik mora ručno da unese tip akta i
   datum. Ako u demou kažeš "rokovi se računaju automatski", budi
   precizan: automatski se računa REZULTAT kad uneseš datum, ne
   pokretanje same kalkulacije.

**Naplata pod-tab — ⚠ PROVERI PRE DEMOA.** Za razliku od Rokovi/
Evidence/Zadaci/Profitabilnost pod-tabova, koji imaju eksplicitan
lazy-load poziv kad se otvore (`pred_subtabSwitch`,
`static/vindex.js:10095-10102`), za `naplata` **nije nađen nijedan
odgovarajući poziv u kodu**. Ovo ne znači da je sigurno pokvareno — može
biti da se popunjava na drugi način — ali ovo NIJE potvrđeno kao radno u
ovoj analizi. **Otvori predmet sa bar jednom fakturom i proveri lično
pre nego što ovo pokažeš advokatu.**

### Korak: Zatvaranje predmeta

**ISPRAVKA (2026-07-19, nakon `OPERATING_SYSTEM_CONNECTIVITY_AUDIT.md`):**
prethodna verzija ovog dokumenta je tvrdila da ne postoji poseban
"Zatvori predmet" proces — to je bilo netačno, ispravljeno posle
dubljeg audita.

- **Šta korisnik vidi:** namenski "Zatvori predmet" tok
  (`routers/predmeti_close.py`, `PATCH /api/predmeti/{id}/zatvori`) sa
  strukturisanim ishodom — pobeda/poraz/nagodba/odustajanje/odbačena/
  ostalo. Povezano dugme u UI ("Potvrdi zatvaranje",
  `pred_zatvoriPredmet()`).
- **Vrednost:** ishod predmeta se beleži strukturisano, ne kao slobodan
  tekst — korisno za buduću statistiku uspešnosti.
- **Backend proces:** upisuje hronologija zapis o zatvaranju i anonimni
  benchmark doprinos.
- **AI modul:** nijedan — čisto strukturiran unos.
- **Šta korisnik treba da razume:** ovo je pravi, namenski proces, ne
  samo Kanban prevlačenje. Kanban tabla (opisana ispod) postoji
  ODVOJENO kao vizuelni pregled faza predmeta — može se koristiti
  paralelno, ali formalno zatvaranje ide kroz ovaj namenski tok.

### Korak: Status predmeta (Kanban)

- **Šta korisnik vidi:** opciona Kanban tabla (prekidač lista/kanban) sa
  5 faza: Inicijalna procena → Priprema → Aktivan postupak → Čeka odluku
  → Završen.
- **Vrednost:** vizuelan pregled celog portfolija predmeta po fazi, ne
  samo pojedinačnog predmeta.
- **Backend proces:** drag-and-drop menja status polje predmeta (`POST
  /api/predmeti/bulk` za grupne akcije, ili pojedinačna izmena statusa).
  **Napomena:** promena statusa na "Završen" ovde NE pokreće formalni
  zatvaranje-tok iznad — to su dva nezavisna mehanizma.
- **AI modul:** nijedan — čisto ručno upravljanje.
- **Šta korisnik treba da razume:** za brz pregled portfolija koristi
  Kanban; za formalno zatvaranje sa ishodom koristi namenski
  "Zatvori predmet" tok opisan iznad.

---

# FAZA 2 — Founder demo scenario (30-45 minuta)

## 1. Šta prvo pokazujem?

Dashboard (Pregled dana) — 30 sekundi, samo da advokat vidi da ovo
liči na profesionalan alat, ne na chatbot. Ne zadržavaj se — odmah idi
na predmet.

## 2. Šta nikako ne pokazujem odmah?

- Podešavanja/Settings ekran (najgušći, najkompleksniji ekran u celoj
  aplikaciji — 131 klikabilnih elemenata, potvrđeno u ranijem UX audit-u).
- Digitalna imovina/Compliance modul (nepovezano sa tipičnim građanskim/
  privrednim sporom, samo zbunjuje na prvom sastanku).
- Sve 8 Strategy modula odjednom — pokaži JEDAN (FAZA 5).
- Bilo šta PRO-gejtovano pre nego što advokat vidi besplatnu vrednost.

## 3. Koji predmet koristim za demonstraciju?

**Realan, ali NE stvaran klijentski predmet** (poverljivost) — koristi
anonimizovan ili sintetički slučaj sa realnom kompleksnošću: privredni
ili radni spor sa 3-5 dokumenata, bar jednom blagom kontradikcijom
između dokumenata (da Case Genome ima šta da otkrije), ne trivijalan
slučaj bez ičega spornog.

## 4. Koji dokument uploadujem?

**Digitalni PDF, izvezen iz Word-a ili originalno digitalan — NIKAD
skeniran/fotografisan dokument.** Skenirani PDF vraća grešku
("Skenirani PDF — uploadujte digitalni PDF") — ako se ovo desi na
demou, izgleda kao da sistem ne radi, a zapravo samo poštuje jasno
ograničenje. Testiraj upload UNAPRED, ne prvi put pred advokatom.

## 5. Kada pričam o AI?

Tek POSLE upload-a, dok se Genome računa u pozadini (15-90s prozor).
Ovo je prirodan trenutak: "Dok sistem čita dokument, da vam objasnim
šta tačno radi" (FAZA 3, 60-sekundni objašnjenje).

## 6. Kada pokazujem Case Genome?

Odmah kad se pojavi (automatski, bez dodatnog klika). Prvo PREGLED
sažetak na vrhu — NE otvaraj "Detaljna analiza" odmah, pusti advokata
da prvo apsorbuje 4 reda sažetka.

## 7. Kada pokazujem Strategy?

Tek posle Case Genome-a, i tek ako advokat pokaže interesovanje za
"šta dalje" — ne guraj ga kao sledeći obavezan korak. Pokaži TAČNO
JEDAN modul (preporuka: "Analiza crvenog tima" — najintuitivniji
koncept za advokata, "sistem napada moj predmet kao protivnik").

## 8. Kada pokazujem Timeline/Rokovi?

Samo ako advokat pita o rokovima, ili ako želiš da demonstriraš ZPP
lanac rokova kao poseban, impresivan trenutak — ali samo posle ručnog
testa da tačno znaš koji tip akta/datum daje čist, tačan rezultat.

## 9. Koje rečenice koristim?

- Ne: "AI će vam reći da li ćete dobiti predmet."
- Da: "Sistem vam pokazuje na čemu se procena zasniva — vi odlučujete
  da li se slažete."
- Ne: "Ovo je 94% tačno."
- Da: "Sistem vam govori i kada NIJE siguran — to je namerno, ne
  slabost."

### Za svaki ekran:

**Ekran: Case Genome PREGLED**
- Founder kaže: "Ovo je prva stvar koju vidite kad otvorite predmet —
  status, najjača tačka, najslabija tačka, i šta sledeće da uradite.
  Sve ostalo je iza ovog dugmeta ako želite detalje."
- Advokat vidi: 4 reda teksta, ne zid podataka.
- Glavna poruka: "Ne morate da čitate sve da biste znali gde da počnete."

**Ekran: AI Provera red**
- Founder kaže: "Sistem je sam proverio sopstvenu procenu — evo šta je
  proverio i da li je nešto sumnjivo."
- Advokat vidi: "✓ AI provera: nema upozorenja" ili konkretnu listu
  upozorenja na klik.
- Glavna poruka: "Sistem vam kaže kad da mu ne verujete, ne samo kad
  da mu verujete."

**Ekran: Strategy — Analiza crvenog tima**
- Founder kaže: "Ovo simulira kako bi protivnička strana napala vaš
  predmet — koristite ga da se pripremite, ne kao gotov odgovor."
- Advokat vidi: strukturiran tekst sa identifikovanim slabostima.
- Glavna poruka: "AI predlaže, vi odlučujete šta da uradite sa tim."

---

# FAZA 3 — Vindex AI za 60 sekundi

> "Vindex AI nije zamena za advokata — to je alat koji radi ono što
> inače radi mlađi saradnik dok pripremate predmet: čita dokumente,
> pravi prvi nacrt procene, i kaže vam gde da obratite pažnju. Vi
> ostajete taj koji donosi svaku pravnu odluku — sistem nikad ne šalje
> ništa sudu niti stranci bez vaše potvrde.
>
> Njegova uloga je da vam uštedi vreme na prvom čitanju spisa i da vam
> pokaže slabe tačke predmeta pre nego što ih protivnik nađe. Pomaže kod
> orijentacije u obimnim predmetima, pripreme za ročište, i praćenja
> procesnih rokova.
>
> Ono što ga razlikuje od chatbot-a je da svaki zaključak ima trag nazad
> do dokumenta koji ga potkrepljuje — i da vam eksplicitno kaže kad nije
> siguran, umesto da glumi da zna sve."

Bez marketing fraza, bez "revolucionaran", bez "najpametniji" — ako
advokat pita dalje, produbi kroz FAZU 4.

---

# FAZA 4 — Case Genome Deep Walkthrough

## Šta je Case Genome?

Živi digitalni model predmeta koji se automatski gradi i osvežava iz
otpremljenih dokumenata — GPT-4o čita sve dokumente predmeta zajedno
(ne jedan po jedan izolovano) i vraća strukturiranu procenu: snagu
predmeta, ključne faktore, rangiranu evidenciju, najslabiju tačku,
strateški plan, šta nedostaje.

## Zašto postoji?

Da advokat (ili partner koji proverava rad mlađeg kolege) ne mora da
ponovo čita ceo spis da bi se orijentisao — dobija sažetak sa tragom
nazad do izvora, ne samo gotov zaključak.

## Kako advokat treba da ga koristi?

Kao POLAZNU tačku, ne kao gotov proizvod. Pravilo koje treba
naglasiti advokatu direktno: "Proverite svaki zaključak pre nego što ga
iznesete pred sudom ili klijentom — ovo vam štedi vreme na prvom čitanju,
ne zamenjuje vašu pravnu analizu."

## Koje sekcije su najvažnije? Šta pokazati prvo, šta preskočiti?

**Pokazati prvo (uvek vidljivo, van "Detaljna analiza"):**
1. PREGLED (Status/Najveća snaga/Najveća slabost/Sledeća akcija)
2. AI Provera red
3. "Na osnovu / Nedostaje" red

**Pokazati ako advokat traži detalje (iza toggle-a):**
- "ZAŠTO X%" — konkretni faktori sa objašnjenjem, najbolje za "pokaži
  mi zašto" pitanje.
- Rangirana evidencija — koji dokazi su najjači, sa "Osnov: DOK-XX".
- Najslabija tačka — crveni alert box sa preporukom.

**Preskočiti u prvom demou (previše detalja za 30-45 min sastanak):**
- Genome Heat Map (6 dimenzija) — koristno, ali sekundarno.
- Plan postupanja (War Plan) — bolje pokazati kroz Strategy module.
- Kontradikcije, ako ih trenutni demo predmet nema.

## Verification Layer

Deterministička provera (ne novi AI poziv) koja proverava da li se
Genome-ovi zaključci slažu sami sa sobom — da li referencirani dokazi
stvarno postoje, da li se procenat snage slaže sa faktorima, da li
brojevi članova zakona deluju realno. Rezultat: "AI provera: nema
upozorenja" ili konkretna lista šta treba proveriti. **Ovo je savetodavno,
nikad ne blokira snimanje Genome-a** — čak i kad nešto flaguje, Genome
se ipak sačuva, samo sa upozorenjem.

## AI ograničenja

Kompaktan red koji kaže na čemu se TAČNO zasniva analiza (broj
dokumenata, broj pronađenih činjenica, broj pravnih elemenata) i šta
NEDOSTAJE (npr. "odgovor druge strane", "sudska odluka") — čisto
brojanje postojećih podataka, ne nova AI procena. Ovo direktno odgovara
na pitanje koje svaki iskusan advokat postavlja: "na osnovu čega je ovo
rečeno, i šta AI nije ni video?"

## Osnov/evidence

Kontradikcije i rangirana evidencija sada eksplicitno pokazuju "Osnov:
DOK-XX" (koji dokument potkrepljuje tu tvrdnju). Ako lokacija nije
jasna iz teksta dokumenta, sistem NE izmišlja — polje ostaje prazno.
Ovo je namerna odluka, ne propust: "bolje bez izvora nego lažni izvor."

## Sigurnost procene

Kod "Najslabija tačka" — oznaka "Sigurnost procene: Visoka/Srednja/
Niska", izvedena iz opšte kompletnosti dokumentacije predmeta (ne nova
AI procena po tvrdnji). Ako je niska/srednja, dodatno piše "Potrebna
provera advokata" — eksplicitan signal da ovde treba više opreza.

## Najslabija tačka

Crveni alert box — najveći rizik u predmetu po AI proceni, sa
konkretnom preporukom akcije. Najbolji "hook" za demo — konkretno,
akciono, lako razumljivo bez tehničkog objašnjenja.

## Sledeći koraci

Sinteza iz najslabije tačke, kritičnih nedostajućih dokumenata, i
strateškog cilja — eksplicitno označena kao "generisano na osnovu
gornjih podataka" (frontend sinteza, ne direktan AI izlaz). Reci
advokatu ovu razliku ako pita — transparentnost gradi poverenje više
nego glačanje.

---

# FAZA 5 — Strategy Engine

## Kada se koristi?

Kad advokat priprema veći ili sporniji predmet za ročište/pregovore —
ne za rutinske, jednostavne predmete gde nema šta da se simulira.

## Koji problem rešava?

Posao koji inače radi mlađi saradnik satima: analiza predmeta iz
perspektive protivnika, simulacija ishoda suđenja, revizija dokumenta
pre podnošenja, analiza svedočenja za unakrsno ispitivanje.

## Koju vrednost daje advokatu?

Brzu, strukturiranu polaznu tačku za pripremu — 8 modula, svaki
fokusiran na drugačiji ugao (Crveni tim, Simulacija suda, Sudija,
Analiza rizika, Revizija dokumenta, Analiza svedoka, Debata, Predikcija
ishoda).

## Kako objasniti da AI ne donosi odluku nego pomaže?

"Ovi moduli vam daju argumente i procene — vi odlučujete koje da
koristite i kako da ih formulišete. Sistem nikad ne podnosi ništa u
vaše ime niti donosi konačnu preporuku bez vaše provere." Naglasiti:
"% verovatnoće uspeha" u Predikciji ishoda je STATISTIČKA procena, ne
garancija — reći to advokatu direktno, pre nego što on to pita
skeptično.

## Koje module pokazati prvom korisniku?

1. **Analiza crvenog tima** (najintuitivniji koncept — "sistem me
   napada da vidim gde sam slab").
2. Ako ima vremena: **Revizija dokumenta** (konkretna, opipljiva
   vrednost — direktne sugestije za tekst).

Ne pokazuj "Kompletnu analizu" (6-modulni orkestrator) na prvom
sastanku — traje 60-90s i pokriva previše odjednom za uvodni demo.

**Napomena o kontekstu:** kad se modul otvara IZ predmeta (klik na
Strategy karticu unutar otvorenog predmeta), tekst polje se automatski
popunjava kontekstom predmeta — advokat ne mora ručno da opisuje slučaj
koji sistem već poznaje. Ovo je nedavno popravljeno (ranije je polje
bilo prazno uprkos tekstu koji je to obećavao) — vredi to i sam
proveriti pre demoa da se uveriš da radi kako očekuješ.

---

# FAZA 6 — "Kako koristiti Vindex AI — prvi beta korisnik"

## Prvi dan

Prijavite se, prođite kroz 3-koračni onboarding (klijent → predmet →
pitanje). Ne morate sve odmah — cilj prvog dana je samo da vidite gde
se stvari nalaze.

## Prvi predmet

Koristite STVARAN predmet, po mogućstvu jedan koji već dobro poznajete
— tako ćete najbrže primetiti da li se AI procena poklapa sa onim što
vi već znate. Ne testirajte prvo na najkomplikovanijem predmetu koji
imate.

## Prvi upload

Digitalni PDF ili DOCX, ne skenirana slika. Ako dobijete grešku
"Skenirani PDF" — to je poznato ograničenje, ne bug; pokušajte sa
digitalno izvezenim dokumentom.

## Kako čitati rezultate

1. Prvo pročitajte PREGLED (4 reda) — ne skrolujte odmah na detalje.
2. Pogledajte AI Provera red — ako piše "upozorenja", pogledajte ih pre
   nego što bilo šta drugo uradite.
3. Za svaku tvrdnju koju planirate da iskoristite, proverite "Osnov" —
   ako ga nema, to znači da sistem nije bio dovoljno siguran da navede
   izvor. Tretirajte tu tvrdnju sa više opreza.
4. Nikad ne iznosite AI zaključak pred sudom ili klijentom bez sopstvene
   provere.

## Gde prijaviti problem

[Founder popunjava — kanal za beta feedback, npr. direktan email/Viber/
WhatsApp kontakt, konkretan i ličan, ne opšti "support@" adresa za samo
5 beta korisnika.]

## Šta očekujemo od testera

Ne savršenstvo — iskrenost. Konkretno:
- Gde ste zastali i niste znali šta dalje?
- Gde ste pomislili "ovo AI sigurno nije tačno" — i jeste li proverili?
- Da li vam je bilo koja procena uštedela stvarno vreme na stvarnom
  predmetu?

---

# FAZA 7 — Ograničenja i iskrenost

## Šta Vindex AI danas radi odlično

- Automatski klasifikuje i rangira dokaze iz otpremljenih dokumenata
  (Evidence Vault).
- Daje brzu, strukturiranu orijentaciju u obimnom predmetu (Case
  Genome), sa konkretnim objašnjenjem za svaki faktor snage.
- Deterministički (ne AI-pogađanje) računa ZPP procesne rokove kad
  korisnik unese tip akta i datum — ovo je pravilo iz zakona, ne
  procena, pa je ovde pouzdanost suštinski drugačija (viša) nego kod
  ostalih AI procena.
- Sam proverava sopstvenu Case Genome procenu i eksplicitno signalizira
  kad nešto ne štima (Verification Layer), umesto da tiho ćuti.
- Nikad ne šalje ništa u ime advokata bez eksplicitne akcije — svaka AI
  procena je predlog, ne izvršena radnja.

## Šta još nije savršeno

- **Pravni korpus (baza zakona/sudske prakse)** koji hrani AI istraživanje
  i module poput Strategy-a nije potvrđeno kompletan za sve oblasti
  prakse — nema javno vidljivog dokaza pokrivenosti. Reci ovo direktno
  ako advokat pita "da li poznaje SVU sudsku praksu" — odgovor je
  pošteno "ne znamo tačno koliko je pokriveno, radimo na tome."
- **"Izvori" (relevantni zakoni) u Genome panelu nisu klikabilni** — samo
  imena zakona kao tekst, korisnik mora sam da potvrdi tačan član.
- **Genome Verification Layer ima poznatu, dokumentovanu graničnu manu**
  (`KNOWN_RELIABILITY_RISKS.md`) — u vrlo retkom slučaju da SVE
  provere istovremeno padnu, sistem bi mogao pogrešno prikazati "nema
  upozorenja". Nizak rizik, ali postoji, i namerno nije skriven.
- **Stari CRM wizard (jedini živi put za kreiranje predmeta na main
  grani) nema nikakav confidence/pouzdanost signal** — GPT ekstrakcija u
  ovom koraku samo predlaže vrednosti bez ikakve indikacije koliko je
  siguran. Advokat mora sam proveriti svako polje pre potvrde.
- **`naplata` pod-tab treba ručno proveriti pre demoa** (videti FAZU 1)
  — nije potvrđeno da se podaci pouzdano učitavaju.
- **"Sledeći koraci" sekcija u Genome-u je frontend sinteza**, ne
  direktan AI izlaz — transparentno označeno u UI-ju, ali vredi znati
  razliku ako te advokat pita.

## Gde AI može pogrešiti

- Kod nejasnih/kontradiktornih dokumenata — Verification Layer hvata
  neke, ne sve moguće greške.
- Kod pravnih oblasti sa slabijom pokrivenošću u internom korpusu
  (nepoznato tačno koje).
- Kod skeniranih/loše čitljivih dokumenata — OCR kvalitet direktno utiče
  na kvalitet ekstrakcije.

## Gde nema dovoljno podataka

- Predmeti sa manje od 3 dokumenta dobijaju nižu ocenu
  "genome_kompletnost" — sistem to sam priznaje, ne glumi sigurnost koju
  nema.
- Pravna oblast/jurisdikcija van glavnog fokusa (privredno/građansko/
  radno pravo) — manje testirano.

## Gde korisnik mora proveriti rezultat

Svuda gde se AI zaključak koristi za stvarnu odluku sa pravnom ili
finansijskom posledicom — bez izuzetka. Ovo nije oprez radi opreza, ovo
je eksplicitna filozofija proizvoda (Product Philosophy Deo 4): "AI
pomaže advokatu" znači izvlači/procenjuje/predlaže, advokat uvek donosi
konačnu odluku.

---

# FAZA 8 — Founder checklist pre sastanka

```
□ Znam objasniti proizvod (60-sekundni pitch iz FAZE 3, napamet, ne sa ekrana)
□ Znam napraviti klijenta i predmet BEZ zastajkivanja (probano unapred)
□ Znam upload dokument — testiran UNAPRED sa istim fajlom koji ću pokazati
□ Znam objasniti Genome — posebno PREGLED, AI Provera, i Sigurnost procene
□ Znam pokazati Strategy — konkretno "Analiza crvenog tima", testiran auto-kontekst
□ Znam objasniti ograničenja BEZ odbrambenog tona (FAZA 7 napamet)
□ Znam odgovoriti na "da li je ovo tačno" pitanje bez preterivanja u oba pravca
□ Proverio sam naplata pod-tab pre demoa (poznat otvoren rizik)
□ Imam pripremljen digitalni (ne skeniran) PDF dokument spreman za upload
□ Znam kako se predmet "zatvara" (namenski "Zatvori predmet" tok sa ishodom — ne samo Kanban)
```

## Najteža pitanja koja advokat može postaviti — pripremljeni odgovori

**"Da li je ovo tačno?"**
→ "Sistem vam pokazuje NA ČEMU se procena zasniva i KADA nije siguran —
   vaš posao je da proverite, ne da verujete slepo. To je i dizajnirano
   tako namerno."

**"Šta ako AI pogreši?"**
→ "AI nikad ne šalje ništa u vaše ime. Svaka procena je predlog koji vi
   pregledate. Ako pogreši, to je isto kao da je pripravnik pogrešio u
   nacrtu — vi ste poslednja provera, kao i uvek."

**"Da li poznaje svu sudsku praksu?"**
→ Pošteno: "Radimo na proširenju pravne baze — trenutno ne mogu da
   garantujem potpunu pokrivenost za svaku oblast. Zato je Verification
   Layer tu — kaže vam kad nešto nije potvrđeno."

**"Zašto stari wizard nema iste 'pametne' oznake kao Genome?"**
→ "To je stariji, jednostavniji deo sistema — radimo na tome da se svi
   delovi ujednače. Trenutno vam preporučujem da svako polje u tom
   koraku sami proverite pre potvrde."
