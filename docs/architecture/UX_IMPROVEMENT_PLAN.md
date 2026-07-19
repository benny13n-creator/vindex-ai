# Vindex AI — UX Improvement Plan (2026-07-19)

Faza 2 — direktan nastavak `UX_CURRENT_STATE_REPORT.md`. Svaki nalaz ispod
je izveden iz te analize i rangiran po Severity Matrix-u (Sekcija 16 tog
izveštaja) i founderovim eksplicitnim odlukama. Redosled unutar svake
klase je redosled rada, ne slučajan.

**Pravilo pre implementacije (Faza 3):** ni jedna stavka se ne dira dok
ovaj plan nije pregledan i eksplicitno odobren, ista disciplina kao kod
Case Genome Reliability Patch-a. Opseg Faze 3 kad počne: layout/
navigacija/IA/mikrointerakcije/tekst/vizuelna hijerarhija. Bez backend/API
izmena osim gde je dole eksplicitno navedeno da je minimalna backend
promena neophodna (označeno). Bez novih funkcija/AI modula.

---

## KRITIČNO (P0) — raditi prvo, sve 4 stavke

### 1. Genome Verification Layer nevidljiv

- **Problem:** Backend računa `_verifikacija.odluka`
  (`approve`/`approve_with_warning`/`require_review`) plus `hard_flags`/
  `soft_flags` za svaki Genome, ali `_caseDnaRender` (`vindex.js:16621`)
  to polje nikad ne čita niti prikazuje.
- **Uzrok:** Verification Layer je izgrađen u Fazi 1.3 (backend-only
  zadatak po tadašnjem obimu) — frontend prikaz nikad nije bio deo tog
  zadatka i niko ga posle nije dodao.
- **Posledica:** Sloj čija je jedina svrha upozorenje na nepouzdanost AI
  procene je potpuno nem prema korisniku. Advokat ne može da razlikuje
  "AI je siguran" od "AI je sam sebe označio kao sumnjiv".
- **Rešenje (revidirano posle founderovog pregleda 2026-07-19 — NIJE
  badge, nego mini-narativ):** Founder eksplicitno: samo zelena oznaka je
  preslabo — korisnik mora da razume PROCES, ne samo ZAKLJUČAK: "AI je
  analizirao predmet → AI je proverio sopstvene zaključke → [siguran je /
  nije siguran] → ovde traži tvoju pažnju." Rešenje: mala "AI Provera"
  kartica na Case Genome panelu, odmah pored `snaga_predmeta_procent`
  prikaza, sa dva reda teksta umesto jedne ikonice:
  - Red 1 (uvek isti, gradi proces): "AI je analizirao predmet i proverio
    sopstvenu procenu."
  - Red 2 (zavisi od `_verifikacija.odluka`): za `approve` — "✓ Nema
    upozorenja."; za `approve_with_warning`/`require_review` — "⚠
    Pronađeno [N] upozorenje(a) — pogledajte pre oslanjanja na ovu
    procenu.", sa proširivom listom `hard_flags`/`soft_flags` u
    jednostavnom jeziku (ne sirov backend tekst).
  Ako `_verifikacija` polje ne postoji (stariji Genome zapisi pre Faze
  1.3), ne prikazivati ništa — ne izmišljati status za podatke koji ga
  nemaju.
- **Uticaj:** Najveći u celom izveštaju — direktno zatvara jaz između
  uloženog inženjerskog rada (Faza 1.3, Reliability Patch) i onoga što
  korisnik stvarno vidi.
- **Procena vremena:** 0.5–1 dan (čisto frontend, polje već stiže u API
  odgovoru, nema backend izmene).
- **Rizik:** Nizak — read-only prikaz postojećeg polja, ne menja logiku
  odlučivanja niti snimanje Genome-a.

### 2. Onboarding korak 1 — pogrešno dugme

- **Problem:** `onboardingStep(1)` (`vindex.js:15196-15197`) klikće
  `document.querySelector('.crm-add-btn')`, koji pogađa dugme "⚠
  Konflikt" umesto "+ Novi klijent".
- **Uzrok:** Oba dugmeta dele klasu `crm-add-btn`
  (`index.html:1870,1872`); "Konflikt" dugme je prvo u DOM redosledu, pa
  ga `querySelector` (vraća prvi match) pogađa umesto namenjenog dugmeta.
- **Posledica:** Prvi vođeni klik novog korisnika u celoj aplikaciji
  otvara pogrešnu funkciju (proveru konflikta interesa umesto forme za
  novog klijenta).
- **Rešenje:** Dodati jedinstven `id="crm-novi-klijent-btn"` direktno na
  "+ Novi klijent" dugme (`index.html:1872`) i promeniti
  `onboardingStep(1)` da cilja taj ID umesto generičke klase. "Konflikt"
  dugme zadržava svoju klasu nepromenjeno.
- **Uticaj:** Kritičan za prvi utisak, ali izolovan i tačno lociran opseg.
- **Procena vremena:** 15–30 minuta.
- **Rizik:** Vrlo nizak — jedan selector fix, nema uticaja na druge tokove.

### 3. Nema signala da Genome radi u pozadini posle uploada

- **Problem:** Posle uspešnog uploada dokumenta korisnik vidi samo
  potvrdu uploada — nema signala da pozadinska Genome regeneracija (OCR +
  GPT ekstrakcija + Verification Layer, 15–90s) uopšte postoji ili je u
  toku.
- **Uzrok:** `pred_upload_doc` (`vindex.js:18606-18690`) upravlja samo
  upload-spinnerom; pozadinski `_run_genome_background` proces na
  backendu nema odgovarajući frontend prateći UI.
- **Posledica:** Direktno određuje ishod "Time to WOW" analize
  (izveštaj, Sekcija 17) — korisnik koji ne zna da treba ručno da osveži
  Case Genome panel ili nikad ne vidi WOW trenutak, ili ga vidi tek posle
  proizvoljno dugog, neizmerenog kašnjenja.
- **Rešenje:** Posle potvrde uploada prikazati inline poruku na Genome
  panelu ("AI analiza u toku — obično 15–90s") i automatski pokušati
  re-fetch Genome-a u fiksnim intervalima (npr. 20s/40s/60s) dok se ne
  detektuje nova verzija ili ne prođe razuman gornji limit (npr. 2 min), a
  da korisnik ne mora ručno da klikne refresh. Očistiti interval čim
  korisnik napusti taj ekran, da se izbegnu nepotrebni pozivi u pozadini.
- **Uticaj:** Direktno popravlja najveći pojedinačni nalaz iz Time-to-WOW
  analize — razlika između "2-4 minuta, odličan rezultat" i "možda nikad"
  zavisi tačno od ove stavke.
- **Procena vremena:** ~1 dan (polling logika + UI stanje na Genome
  panelu).
- **Rizik:** Nizak-srednji — pažljivo očistiti interval na promenu taba,
  inače nepotrebni pozivi nastavljaju u pozadini.

### 4. Strategy — 3-minutni tihi timeout

- **Problem:** `strat_job_poll` (`vindex.js:3600-3618`) ima hard limit od
  180s; kad istekne bez `'done'`/`'error'` statusa, dugme se tiho otključa
  bez ikakve poruke korisniku.
- **Uzrok:** Petlja za praćenje posla nema fallback granu za slučaj
  isteka vremena — samo za uspeh i eksplicitnu grešku.
- **Posledica:** Izgleda kao da se sistem pokvario tačno u trenutku
  najvećeg očekivanja vrednosti od AI-ja — najgori mogući trenutak za
  gubitak poverenja.
- **Rešenje (revidiran tekst faza posle founderovog pregleda):** (a)
  Zameniti generički "u toku"/"Molimo sačekajte" tekst rotirajućim fazama
  koje opisuju ŠTA sistem konkretno radi, ne generičko čekanje:
  "Analiziram dokumente... → Upoređujem sudsku praksu... → Simuliram
  strategije... → Formiram preporuku...", promena na ~20-30s, bez potrebe
  da prati stvaran progres — bitno je da korisnik zna DA sistem radi i
  ŠTA otprilike radi, ne generička poruka čekanja. (b) Na isteku 180s
  prikazati eksplicitnu poruku ("Analiza traje duže nego obično. Sačekajte
  ili pokušajte ponovo.") umesto tihog vraćanja u prvobitno stanje.
- **Uticaj:** Visok — direktno adresira poverenje u tačno onom trenutku
  kad je AI najsporiji i korisnik najviše sumnja.
- **Procena vremena:** ~0.5 dana.
- **Rizik:** Nizak.

### 5. Objašnjivost — izvori i linkovi ka dokazu (podignuto sa P1 na P0 posle founderovog pregleda 2026-07-19)

- **Founderovo obrazloženje za podizanje prioriteta:** "Advokat ne veruje
  AI-u. Veruje članu zakona, presudi, dokazu. Ako klikom može da vidi
  'Ovo potiče odavde', dobio si poverenje." Ovo je isti princip poverenja
  kao stavka 1 (Verification), samo sa druge strane — stavka 1 pokazuje da
  je AI proverio sebe, stavka 5 pokazuje NA ČEMU se AI zasniva. Obe zajedno
  čine "poverenje" celinu, zato idu zajedno u P0.
- **Problem:** `snaga_faktori[].opis`, `dokazi_rang[].razlog`,
  `najslabija_tacka.preporuka` su sečeni na `.slice(0,60-70)` bez opcije
  proširenja; imena zakona u footeru su plain tekst bez linka ka
  dokumentu; `'PREPORUČENI SLEDEĆI KORACI'` je frontend-sintetizovan
  (`vindex.js:16817-16818`, komentar u kodu to potvrđuje) ali prikazan
  identično kao direktan AI izlaz.
- **Uzrok:** Slice limiti su verovatno postavljeni radi kompaktnosti
  panela pre nego što je bilo jasno koliko GPT objašnjenja realno mogu
  biti duga.
- **Posledica:** Advokat ne može da proveri OSNOV AI procene niti da vidi
  puno obrazloženje bez čitanja sirovih podataka; ne zna da je "sledeći
  koraci" sekcija frontend-kompilacija a ne AI izlaz.
- **Rešenje:** Ukloniti hard slice limite, zameniti CSS `line-clamp` sa
  "prikaži više" linkom gde je tekst stvarno dug. Imena zakona u footeru
  učiniti klikabilnim linkovima ka odgovarajućem dokumentu/pasusu ako
  postoji ruta za to (proveriti pre obećavanja — ako ne postoji gotova
  ruta, klikabilna veza ide u drugi krug, ali sam "prikaži više" tekst i
  dalje ide u ovoj rundi jer ne zavisi od toga). Dodati sitnu labelu
  "generisano na osnovu gornjih podataka" uz "sledeći koraci" sekciju da
  se razlikuje od direktnog AI izlaza.
- **Uticaj:** Visok za poverenje — direktno adresira founderov nalaz da
  advokat ne veruje AI zaključku samom po sebi, nego proverljivom izvoru.
- **Procena vremena:** 1-2 dana (linkovanje ka dokumentima zahteva
  proveru da li odgovarajuća ruta/ID već postoji u payload-u — tekstualni
  deo bez linkovanja može ići brže, ~0.5 dana).
- **Rizik:** Nizak za tekst/slice promene; srednji za linkovanje ka
  dokumentima ako ruta ne postoji već gotova.

---

## ZATVORENO BEZ AKCIJE

### 6. 7-koračni onboarding sistem (`_onboardSteps`/`onboard_show`)

- **Nalaz iz istrage (git istorija):** commit `7013284`
  (2026-06-20, "profesionalni first-user flow za sastanak 2026-06-23")
  potvrđuje da je gašenje bilo **namerno**, ne slučajno — stari 7-koračni
  carousel je eksplicitno zamenjen sadašnjim konsolidovanim 3-koračnim
  flow-om, sa ciljem da "smanji trenje" (citat iz commit poruke), uz
  direktnije vođenje ka akciji.
- **Odluka:** Po founderovom sopstvenom pravilu ("ako je ugašen da ne bi
  zbunjivao korisnike, ne vraćati") — **ne vraćati, nema dalje akcije.**
  Mrtav kod (`_onboardSteps`, `onboard_show`, `onboard_render`,
  `onboard_next`, `onboard_prev`) ostaje kandidat za brisanje u nekoj
  budućoj tehničkoj-dug rundi (Faza 2.2 stila), ali to nije UX prioritet i
  ne spada u obim ovog plana.

---

## VISOK (P1)

Founder je potvrdio da su obe preostale P1 stavke nižeg urgentnosti —
"može da sačeka" (dual-path naming) i "nije hitno" (file-size limit) —
zadržane u P1 ali bez pritiska da idu odmah posle P0.

### 7. Strategija — dual-path zabuna

- **Problem:** "Strategija" postoji na dva strukturno različita mesta —
  predmet pod-tab (`strategija`) i globalni PRO-gated `aiws` mod "t" — sa
  istim imenom i različitim pristupnim pravima.
- **Uzrok:** Organski razvoj dva odvojena modula tokom vremena, oba
  legitimna, ali bez razlikovanja u imenovanju.
- **Posledica:** Korisnik koji traži "Strategiju" nailazi na dva mesta sa
  istim imenom, jedno besplatno jedno PRO — verovatan izvor pitanja
  podrške u pilot fazi.
- **Rešenje:** Preimenovati jedno od dva (predlog: predmet pod-tab ostaje
  "Strategija", globalni PRO mod postaje "Strategija — kompletna analiza"
  ili slično jasno diferencirano ime). Čisto tekstualna izmena, bez
  strukturne promene.
- **Uticaj:** Srednji-visok — smanjuje trenje i pitanja podrške, ne
  utiče na funkcionalnost.
- **Procena vremena:** ~1 sat.
- **Rizik:** Vrlo nizak.

### 8. Dva različita file-size limita (25MB vs 10MB)

- **Problem:** `doc_upload_file` dozvoljava 25MB (`vindex.js:8681`),
  `pred_upload_doc` dozvoljava 10MB (`vindex.js:18623`) — korisnik ne
  može unapred da zna koji limit važi gde.
- **Uzrok:** Dva odvojena upload puta razvijena u različitim iteracijama
  bez usklađivanja konstante.
- **Posledica:** Upload koji prolazi na jednom mestu odbija se na
  drugom bez očiglednog razloga za korisnika.
- **Rešenje:** Uskladiti na jednu vrednost (predlog: 25MB svuda, pošto
  je to već dokazan limit na jednom putu; potvrditi da backend/storage
  sloj podržava tu veličinu na oba puta pre nego što se menja frontend
  limit).
- **Uticaj:** Srednji, niska frekvencija (samo veći dokumenti).
- **Procena vremena:** ~30 minuta frontend + potvrda backend limita.
- **Rizik:** Nizak, uz uslov da se prvo potvrdi da backend prihvata veći
  fajl na oba puta (ako ne, ovo je backend zadatak, ne UX).

---

## SREDNJI (P2)

### 9. FAB "Dodaj belešku" vodi na pogrešan pod-tab

- **Problem:** FAB dugme sa labelom "Dodaj belešku" navigira na Rokovi
  pod-tab umesto na formu za belešku.
- **Uzrok:** Verovatno leftover iz ranije verzije kad je FAB imao drugu
  funkciju.
- **Posledica:** Labela i akcija se ne poklapaju — konfuzno, ali ne
  blokira rad (korisnik i dalje može doći do beleške drugim putem).
- **Rešenje:** Ili promeniti FAB akciju da vodi na stvarnu formu za
  belešku, ili promeniti labelu da odgovara stvarnoj akciji (Rokovi).
- **Uticaj:** Nizak-srednji, retko primećeno ako korisnik ne koristi FAB.
- **Procena vremena:** ~30 minuta.
- **Rizik:** Vrlo nizak.

### 10. Nema retry dugmadi posle greške

- **Problem:** Nijedan pronađen `catch` blok za AI pozive nudi retry
  dugme — korisnik mora ručno da ponovi celu akciju od početka.
- **Uzrok:** Error handling pisan da prikaže poruku, ne da ponudi
  sledeći korak.
- **Posledica:** Dodatno trenje posle već neprijatnog trenutka (greška).
- **Rešenje:** Dodati "Pokušaj ponovo" dugme u standardni error-toast
  obrazac za AI pozive (Genome refresh, Strategy, multi-agent) koje
  ponovo poziva istu funkciju sa istim parametrima.
- **Uticaj:** Srednji, direktno smanjuje trenje posle grešaka.
- **Procena vremena:** ~1 dan (treba pokriti par različitih poziva).
- **Rizik:** Nizak.

### 11. Empty state nekonzistentnost

- **Problem:** `vxGridEmpty` (ikona+naslov+podtekst) postoji kao dobra
  reusable komponenta ali se koristi samo 5x; ostatak su ad-hoc
  plain-text divovi bez CTA.
- **Uzrok:** Komponenta dodata posle većine ekrana, nikad retroaktivno
  primenjena svuda.
- **Posledica:** Nekonzistentan doživljaj — neki prazni ekrani vode
  korisnika dalje, drugi samo kažu "nema ničega".
- **Rešenje:** Zameniti preostale plain-text empty state-ove (Predmeti,
  Rokovi, Fakture — nabrojano u izveštaju Sekcija 14) sa `vxGridEmpty`
  pozivima.
- **Uticaj:** Srednji, vidljivo pri svakom prvom korišćenju modula bez
  podataka.
- **Procena vremena:** ~1 dan za sve nabrojane lokacije.
- **Rizik:** Vrlo nizak — čista zamena postojeće komponente.

### 12. Ikonice/boje nekonzistentne

- **Problem:** 15+ emoji tipova van dozvoljenog skupa (✓/✅/⚠️), 30+
  hardcoded hex boja umesto CSS varijabli.
- **Uzrok:** Organski rast bez centralne provere pri svakom dodavanju.
- **Posledica:** Vizuelni identitet nedosledan, otežava buduće theming
  izmene (svaka hardcoded boja je mesto koje treba ručno naći i menjati).
- **Rešenje:** Postepena zamena — prvo hex boje sa najviše ponavljanja
  (uspeh/greška/upozorenje varijante) na postojeće CSS varijable; zatim
  emoji zamena gde je jednostavna (status dot-ovi, section headeri).
  Ovo je veći, mehanički zadatak — predlog da se radi u manjim
  serijama, ne odjednom.
- **Uticaj:** Nizak po pojedinačnom slučaju, ali visoka frekvencija
  (svuda vidljivo) čini kumulativni utisak nedoslednim.
- **Procena vremena:** 2-3 dana ukupno ako se radi u celini; može se
  deliti na manje serije.
- **Rizik:** Nizak, uz pažnju da se ne promeni semantika boje slučajno.

### 13. `naplata` pod-tab — verifikacija lazy-load-a

- **Problem:** Nije potvrđeno u kodu da `naplata` pod-tab ima
  odgovarajući lazy-load poziv (odsutan iz `pred_subtabSwitch` liste od 8
  grana).
- **Uzrok:** Nepoznat dok se ne testira ručno.
- **Posledica:** Ako je stvarno bug, korisnik otvara prazan naplata
  panel bez podataka.
- **Rešenje:** PRVI korak nije popravka nego ručna provera u browseru —
  otvoriti predmet sa fakturama, kliknuti Naplata pod-tab, potvrditi da
  li se podaci učitavaju. Tek ako se potvrdi da nedostaje, dodati
  odgovarajući lazy-load poziv.
- **Uticaj:** Potencijalno visok ako je bug potvrđen (finansijski podaci),
  ali nepoznat dok se ne proveri.
- **Procena vremena:** 15 minuta provere; ako je bug, ~30 minuta popravke.
- **Rizik:** Nizak.

### 14. `tab-dok` — prazan redirect-only ekran

- **Problem:** Globalni "Dokumenti" tab u sidebar-u nema sopstveni
  sadržaj — samo dve kartice koje preusmeravaju na druge tabove.
- **Uzrok:** Verovatno ostatak starije IA pre nego što su dokumenti
  konsolidovani unutar predmeta.
- **Posledica:** Zauzima stalno mesto u sidebar-u za nešto što nije
  samostalna funkcija — dodatna stavka za skeniranje pri svakoj
  navigaciji.
- **Rešenje:** Ukloniti iz sidebar-a ili jasno preoblikovati kao
  prečicu/search ulaz umesto punog taba (odluka o tačnom rešenju zavisi
  od toga da li postoji plan za budući samostalan sadržaj — pitanje za
  foundera pre implementacije, ne pretpostavljati).
- **Uticaj:** Nizak-srednji, smanjuje sidebar gustinu ako se ukloni.
- **Procena vremena:** ~1 sat.
- **Rizik:** Nizak, uz proveru da nijedan spoljni link ne cilja taj tab
  direktno.

---

## NIZAK (P3) — backlog, ne raditi u ovoj rundi

| Stavka | Zašto se ne radi sada |
|---|---|
| Voice dugme nevidljivo | Founder eksplicitno: ne dirati dok pilot ne pokaže stvarnu potražnju za glasovnom komandom. |
| Auto-save/undo odsutno | Impact nije nizak, ali effort je arhitekturna promena (★★★★★), ne UX popravka — flagovati za buduću, posebnu raspravu. |
| `.vx-skeleton` mrtav CSS | Kozmetički, nema vidljiv efekat na korisnika dok se ne aktivira upotreba. |
| Nema `AbortController` generalno (šira verzija od P0 #4) | P0 stavka #4 rešava najvažniji slučaj (Strategy); generalizacija na sve pozive nije hitna. |
| Dupliran `tab-btn-pi` ulaz | Nizak impact, treba prvo potvrditi da drugi ulaz nema skrivenu svrhu pre uklanjanja. |

---

## Redosled rada (predlog, ažurirano posle podizanja stavke 5 na P0)

1. **Nedelja 1:** svih 5 KRITIČNO (P0) stavki — ukupno ~4-5 dana rada
   (1: AI Provera narativ, 2: onboarding selector, 3: Genome background
   signal, 4: Strategy faze poruke, 5: Objašnjivost/izvori).
2. **Nedelja 2:** VISOK (P1) stavke — ukupno ~1.5 dana rada (7: naming,
   8: file-size limit) — obe potvrđene od foundera kao "može da sačeka".
3. **Nedelja 3+:** SREDNJI (P2) stavke, po prioritetu unutar klase,
   prvo one sa najnižim effort-om (9, 13, 14) pre onih sa najviše (12).
4. NIZAK (P3): ne planirati, čeka pilot signal ili posebnu odluku.

Nijedna stavka iz ovog plana ne uključuje promenu Product Philosophy,
Architecture Bible, backend logike odlučivanja, ili dodavanje novih AI
modula — u skladu sa ograničenjima Faze 3 iz originalnog zahteva.

---

## Faza 2.5 — Strateško usklađivanje i pre-implementacioni gejt (2026-07-19)

Posle founderovog pregleda ovog plana, dodata su tri strateška alata koja
nisu bila u originalnom zahtevu, plus jedan eksplicitan gejt koji mora
biti zadovoljen PRE nego što se napiše ijedna linija koda za P0 set.
Founder: "Ako taj odgovor nije potpuno jasan, dizajn još nije spreman za
implementaciju."

### A. Radni tok advokata — klik-mapa celog životnog ciklusa predmeta

Founder je tražio mapu celog toka (Klijent → Smart Intake → Predmet →
Genome → Timeline → Strategija → Dokumenti → Rokovi → Troškovi → Gotov
predmet), ne samo izolovane ciljne akcije kao u Sekciji 7 izveštaja.

| Prelaz | Klikova | Ocena (founderova skala: 1-2 odlično, 3 dobro, 5+ previše) | Izvor/napomena |
|---|---|---|---|
| (Start) → Klijent kreiran | 2 | Odlično | Klijenti tab → forma (potvrđeno, izveštaj Sek. 7) |
| Klijent → Smart Intake pokrenut | ~1-2 (PROCENA) | Odlično, ako je procena tačna | Nije direktno citirano u ovoj analizi — **preporučujem ručnu proveru** pre nego što se ovaj broj tretira kao potvrđen |
| Smart Intake koraci (unos podataka) | 5 koraka wizard-a | Nije "trenje" — ovo je očekivan rad (unos podataka), ne navigacioni overhead | `project_intake_wizard` memorija: 5-step wizard |
| Smart Intake → Predmet kreiran | 1, ali RUČAN i eksplicitan | Dobro, ali nije automatski | Potvrđeno u analizi: "Smart Intake ne kreira predmet automatski... advokat mora eksplicitno da klikne 'finalize'" |
| Predmet → Genome prikazan | **0** (auto-prikaz) | **Fenomenalno** | Potvrđeno, izveštaj Sek. 7 |
| Genome → Timeline (Rokovi) | 1 (pod-tab) | Odlično | Potvrđeno, izveštaj Sek. 7 |
| Timeline → Strategija | 1 (pod-tab) | Odlično | Iste sibling pod-tab trake |
| Strategija → Dokumenti | 1 (pod-tab) | Odlično | Iste sibling pod-tab trake |
| Dokumenti → Rokovi | 1 (pod-tab) | Odlično | Iste sibling pod-tab trake |
| Rokovi → Troškovi (Naplata) | 1 (pod-tab), **lazy-load neverifikovan** | Odlično po broju klikova, ali videti P2 stavku 13 | Ista pod-tab traka, ali sadržaj možda ne radi |
| Troškovi → Gotov predmet | **NIJE VERIFIKOVANO** | — | Nijedan tok za formalno zatvaranje predmeta nije pronađen u dosadašnjoj analizi — treba posebna provera pre nego što se bilo šta tvrdi |

**Ključan zaključak mape:** lateralno kretanje UNUTAR već otvorenog
predmeta je gotovo idealno (1 klik po pod-tabu, Genome čak 0). Sve
"trenje" u celom toku je koncentrisano na TRI tačke: (1) ulazak u Smart
Intake iz liste klijenata — neverifikovano, treba proveriti; (2) ručni
"finalize" klik da bi Intake uopšte postao Predmet — poznato i namerno,
[[project_smart_intake_architecture]] instrumentacija iz Faze 2.1 upravo
to meri; (3) nepoznato stanje "zatvaranja" predmeta na kraju toka. Ovo
znači da fokus na P0/P1 stavke (koje su sve UNUTAR predmeta) ne rešava
ova tri spoljna trenja — vredna posebne provere u sledećoj rundi, ne
dela ovog plana.

### B. Time To First Value (TTFV) — reframing "Time to WOW" analize

Founder je predložio precizniju skalu od one korišćene u izveštaju
(Sekcija 17): 15 min = izgubljen korisnik, 5 min = dobro, 2 min = veoma
dobro, ispod 1 min = ozbiljan proizvod.

Postojeća procena (izveštaj, Sekcija 17, i dalje PROCENA ne merenje):

- **Scenario A (korisnik ručno osveži Genome, zna da treba):** ~2-4
  minuta → pada u "veoma dobro" do granice "dobro" po founderovoj skali.
- **Scenario B (bez P0 stavke 3 — nema signala da AI radi):** neizmereno,
  potencijalno nikad → ekvivalent najgoreg ishoda na founderovoj skali
  ("izgubljen korisnik"), bez obzira na to koliko je Scenario A brz.

**Ovo je najjači argument za redosled rada:** implementacija P0 stavke 3
ne pomera TTFV sa "dobrog" na "boljeg" — ona pomera sistem sa "možda
nikad" na "pouzdano 2-4 minuta". P0 set kao celina (naročito stavke 1, 3,
5) je direktno ono što TTFV cilja treba da pogodi "veoma dobro" prag
pouzdano, ne povremeno.

### C. Cognitive Load Score — primenjeno na P0 ekrane

Metodologija (founderov predlog): za svaki ekran, 4 pitanja — (1) koliko
NOVIH informacija korisnik vidi, (2) koliko odluka mora da donese, (3)
koliko akcija može da izvrši, (4) da li je sledeći korak jasan (Da/Ne).

| Ekran (posle predloženih P0 izmena) | Nove informacije | Odluke | Akcije | Sledeći korak jasan? |
|---|---|---|---|---|
| Case Genome + AI Provera kartica (stavka 1) | 2 nova reda teksta + opciona lista upozorenja | 0-1 (da li da otvori detalje upozorenja) | 1 (proširi/skupi) | **Da** — ili "sve OK, nastavi" ili "evo šta da proveriš" |
| Onboarding korak 1, posle fix-a (stavka 2) | 0 novih (isti ekran, ispravan cilj) | 0 | 1 (klik na tačno dugme) | **Da** |
| Upload + background progress (stavka 3) | 1 (poruka statusa) | 0 | 0 (pasivno čekanje) | **Da** — "sistem radi, ne moraš ništa" |
| Strategy sa fazama (stavka 4) | 1 po fazi (rotira, ne akumulira) | 0 | 0-1 (opciono otkazivanje ako postoji) | **Da** — svaka faza sama po sebi je odgovor na "šta se sad dešava" |
| Genome objašnjivost + izvori (stavka 5) | Varira (proširiv tekst, ali skriven dok se ne traži) | 1 (da li da klikne na izvor) | 1-2 (proširi tekst, klikni izvor) | **Da**, uz uslov da link postoji — ako ne, ekran i dalje jasno kaže odakle tekst dolazi, samo bez klika |

**Zaključak:** svih 5 predloženih P0 rešenja drži cognitive load nisko
(0-2 nove odluke po ekranu) dok istovremeno odgovara na "šta se dešava"
pitanje — ovo je direktno posledica dizajna fokusiranog na PROCES/NARATIV
(founderov zahtev za stavku 1), ne dodavanja više UI elemenata.

### D. Gejt: "Šta korisnik treba da pomisli u prvih 5 sekundi?"

Ovo je eksplicitni uslov foundera pre pisanja koda. Odgovor za svaku od 5
P0 stavki:

1. **AI Provera (Genome Verification):** *"AI je pregledao moj predmet i
   sam proverio svoj rad — mogu na prvi pogled da vidim da li treba nešto
   posebno da proverim, ili mogu da nastavim s poverenjem."*
   → Dizajn implikacija: dva reda teksta, ne jedna ikonica — prvi red
   gradi da je AI RADIO proveru (proces), drugi red daje ZAKLJUČAK
   (status). Bez oba reda, ovaj odgovor nije potpun.

2. **Onboarding korak 1 (posle fix-a):** *"Ovo je dugme za dodavanje mog
   prvog klijenta — jasno mi je gde sam i šta radim."*
   → Dizajn implikacija: selector mora pogađati TAČNO dugme sa
   odgovarajućom labelom vidljivom u istom trenutku; nema dodatne UI
   promene potrebne, ovo je čisto bug fix.

3. **Upload + background progress:** *"Sistem je primio moj dokument i
   sada nešto radi s njim — ne moram ništa da radim, samo da sačekam, i
   videću kad bude gotovo."*
   → Dizajn implikacija: poruka mora eksplicitno reći DA se nešto dešava
   (ne samo "uspešno otpremljeno") I da će korisnik biti obavešten kad se
   završi (implicitno kroz auto-refresh iz rešenja stavke 3) — bez toga
   drugog dela, korisnik i dalje ne zna da li treba da nešto proveri.

4. **Strategy faze poruke:** *"AI trenutno radi nešto konkretno — nije
   zaglavljen, samo mu treba vremena za ovaj korak."*
   → Dizajn implikacija: fraze moraju biti KONKRETNE radnje ("Upoređujem
   sudsku praksu"), ne apstraktne ("Obrađujem") — apstraktna fraza ne bi
   prošla ovaj test, jer ne razlikuje "radi" od "zaglavljeno".

5. **Genome objašnjivost + izvori:** *"Ovo nije AI koji izmišlja — mogu
   da vidim tačno na čemu se ova procena zasniva."*
   → Dizajn implikacija: labela "generisano na osnovu gornjih podataka"
   i vidljiv (ne skriven) link/referenca ka izvoru su OBAVEZNI deo
   rešenja, ne opcioni dodatak — bez njih, "prikaži više" sam po sebi ne
   ispunjava ovaj test (samo pokazuje duži tekst, ne izvor).

**Zaključak gejta:** sva 5 P0 rešenja iz ovog plana, kako su trenutno
opisana (uključujući revizije iz Faze 2.5), imaju jasan i specifičan
odgovor na "prvih 5 sekundi" pitanje. Nijedno rešenje se ne oslanja na
generičku poruku ili samu vizuelnu oznaku bez konteksta. Gejt je
zadovoljen za P0 set — spreman za Fazu 3 implementaciju, pending
founderovo konačno odobrenje za početak koda.

### E. Pravilo 0 + "Šta uklanjamo?" — dodato posle founderovog "Da" (2026-07-19)

Founder je dao zeleno svetlo za P0 implementaciju uz dva nova stalna
pravila (upisana i u Product Philosophy Deo 5, principi 8 i 9): (1) UX
nije gotov dok korisnik ne mora da razmišlja/pogađa/pamti, (2) svaka nova
komponenta mora reći šta je uklonjeno ili pojednostavljeno, ne samo šta je
dodato.

| P0 stavka | Šta uklanjamo / ne dodajemo net-novo |
|---|---|
| 1. AI Provera narativ | Ne dodaje se odvojena nova kartica pored postojećeg `snaga_predmeta_procent` prikaza — dvoredni narativ ZAMENJUJE/proširuje postojeći header red na istom mestu, isti vizuelni prostor. |
| 2. Onboarding selector fix | Nema dodavanja UI elementa — čista izmena reference (ID umesto klase). Izuzeto iz Principa 8 jer ne dodaje ništa novo, ispravlja postojeće. |
| 3. Genome background signal | Poruka je tranzitna — čim je Genome gotov, status red nestaje potpuno, ne ostaje kao trajan dodatak ekranu. |
| 4. Strategy faze poruke | Rotirajuće faze ZAMENJUJU postojeći generički "u toku" tekst 1:1 na istom mestu, ne dodaju se pored njega. |
| 5. Explainability | Uklanja se veštačko ograničenje (`.slice(0,70)`) — ovo je uklanjanje ograničenja, ne dodavanje kompleksnosti. "Prikaži više" je podrazumevano skupljeno (ne dodaje vizuelnu težinu dok se ne zatraži). |

Svih 5 stavki prolazi Princip 8 test — nijedna ne dodaje trajnu vizuelnu
težinu bez da nešto zauzvrat pojednostavi, ukloni, ili nestane kad više
nije potrebno.

---

## Posle P0 — founderova preporuka (upisano radi budućeg pridržavanja)

Founder je eksplicitno preporučio: **posle P0, ne nastavljati odmah na
P1.** Umesto toga, zamrznuti UX i pozvati 3 beta korisnika na
neusmerenu, posmatranu upotrebu (bez objašnjavanja, bez pomoći, bez
prekidanja) — beležiti gde zastanu, gde pogrešno kliknu, šta traže, šta
ignorišu, šta ih oduševi. Ovo je founderov zadatak (rekrutovanje/
posmatranje beta korisnika), ne kod — ali je upisano ovde da se P1 ne
pokrene automatski posle P0 bez ove provere. Ista disciplina faznog
zaustavljanja kao svuda drugde u ovom projektu: ne nastavljati na
sledeći korak dok prethodni nije potvrđen stvarnim signalom, ne internom
pretpostavkom.
