# Vindex AI — UX Simplification Audit (2026-07-20)

**Status: ANALIZA. Nijedna linija koda nije menjana ovim dokumentom.**
Implementacija bilo čega odavde čeka da se CONTRACT 01 ručni prolaz
završi (founderova odluka, 2026-07-20) — ovo je urađeno po masterprompt
zahtevu za "sveobuhvatnu strategiju", eksplicitno kao analiza-samo, ne
kao sledeći sprint.

**Odnos prema postojećim UX dokumentima:** ovo NIJE prvi UX audit —
`UX_CURRENT_STATE_REPORT.md` i `UX_IMPROVEMENT_PLAN.md` (2026-07-19)
su već identifikovali i (delimično) rešili konkretne probleme (npr.
Genome Verification Layer nevidljivost — VIDI niže, potvrđeno da je
implementirano). Ovaj dokument je ŠIRI po obimu (cela platforma, ne
samo onboarding/Genome) i koristi masterprompt 8-pitanja rubriku po
komponenti. Gde se preklapa sa starim dokumentima, to je eksplicitno
označeno — ne ponavlja se kao "nov" nalaz.

**Metodologija:** svaki nalaz je citiran na file:line iz stvarnog koda
(`index.html`, `static/vindex.js`, `static/vindex.css`, `api.py`,
relevantni routeri). Dubina provere NIJE ista za sve stranice —
Dashboard, Pregled predmeta i Genome su pročitani u dubinu (svaka
renderujuća funkcija, red po red); Dokumenti, Klijenti, Rokovi, AI
analiza, Finansije i Modali su strukturno uzorkovani (header/sekcije/
dugmad, ne svaka linija). Gde je dubina uzorkovana, to piše eksplicitno
uz nalaz — ne predstavlja se uzorak kao kompletna provera.

**Obavezna ograda (masterprompt + founderova ranija pravila u ovoj
sesiji):** tamna tema, boje brenda i arhitektura ostaju. Nijedan predlog
ispod ne uvodi novu AI funkciju, agenta, modul ili stranicu. Svaki
predlog je uklanjanje, spajanje, premeštanje ili pojednostavljenje
postojećeg.

---

## Executive Summary — 5 najvažnijih nalaza

1. **Dashboard (Pregled dana) ima ČETIRI nezavisna AI-narativna widgeta
   koja delom ponavljaju iste brojeve** — Health Index, AI Command
   Center Intel Briefing, Jutarnji brifing, Chief Intelligence Officer.
   Ovo je isti obrazac kao G-027 (višestruki izvori za isti koncept),
   samo na nivou celog ekrana, ne jednog polja. **BLOCKER-nivo nalaz.**
2. **Sidebar ima 13 top-level stavki**, dok mobilna navigacija (već u
   kodu) ispravno svodi na 5. Desktop nikad nije usklađen sa tim
   principom — poznat, ranije odložen nalaz ("Beta Readiness sprint —
   sidebar reduction opet preskočen").
3. **"Dokumenti" top-level tab nema sopstveni sadržaj** — dve kartice
   koje samo preusmeravaju na Predmeti / Analiza dokumenta. Cela stavka
   u navigaciji postoji da bi preusmerila negde drugde.
4. **Pregled predmeta ima tri preklapajuća skor-widgeta** (već
   dijagnostikovano kao G-027 tokom ove sesije — deo je REŠEN kodom,
   deo — vizuelna konsolidacija — čeka Sprint 2) + 4 administrativne
   sekcije nabijene u glavni scroll.
5. **Genome panel je već prošao kroz sličnu disciplinu** (P0.3
   self-review, 2026-07-19) — "PREGLED" sažetak na vrhu, collapsible
   detalji, jedan red za AI Trust signal. **Ovo je pozitivan primer,
   vredan kopiranja na Dashboard, ne problem.**

---

## 1. Navigacija (Sidebar/Topbar)

**Dubina provere:** strukturna (kompletan spisak tabova, ne svaka
pod-stavka).

### Problemi
13 top-level tabova u desktop sidebar-u (`index.html:444-506`): Pregled
dana, Predmeti, Klijenti, Rokovi, Vindex Intelligence, Sudska praksa,
Dokumenti, Šabloni dokumenata, Zadatci, Finansije, Kancelarija,
Portfolio kancelarije, Podešavanja. Mobilna navigacija (`index.html:
4247-4263`) već svodi ovo na 5: Početna, Predmeti, Rokovi, Klijenti,
Više opcija.

### Zašto je problem
Masterprompt mentalni model: advokat razmišlja "Koji predmet? → Šta se
desilo? → Šta treba da uradim?" — ne bira među 13 imenovanih modula.
13 stavki premašuje uobičajenu granicu za jednim pogledom prepoznatljivu
navigaciju (7±2 stavki, standardno IA pravilo). Mobilna verzija DOKAZUJE
da tim već zna ispravan broj (5) — desktop prosto nikad nije usklađen.

### Ozbiljnost
**High.** Ne blokira funkciju, ali je prva stvar koju svaki korisnik
vidi na svakoj poseti, svaki dan.

### Predlog rešenja
Grupisati 13 stavki u nekoliko klastera sa jasnom hijerarhijom (npr.
primarno vidljivo: Danas, Predmeti, Klijenti, Rokovi; sekundarno iza
grupe "Alati"/"Kancelarija": Vindex Intelligence, Sudska praksa,
Šabloni, Zadatci; treće iza "Kancelarija": Finansije, Kancelarija,
Portfolio, Podešavanja) — isti princip koji mobilna navigacija već
primenjuje sa "Više opcija". Ne predlažem konkretan raspored ovde (to
je dizajn odluka za Sprint, ne za audit) — samo utvrđujem da broj mora
pasti sa 13 na jednocifren broj primarno vidljivih stavki.

### Zašto je novo rešenje bolje
Manje odluka po pogledu (masterprompt pitanje 8), dosledno sa već
postojećim mobilnim obrascem — ne izmišlja se nova IA, kopira se
postojeća koja već radi.

### Implementaciona složenost
Srednja — čisto frontend (HTML struktura + CSS + `setTab()` logika za
grupe), ali dotiče SVAKU stranicu (navigacija je svuda vidljiva),
zahteva pažljivo regresiono testiranje.

### Backend izmene
Nema.

### Uticaj na postojeću logiku
Nizak rizik ako se ruta/`setTab(id)` pozivi ne menjaju (samo vizuelno
grupisanje) — visok rizik ako se menjaju ID-jevi tabova (mnogo koda
poziva `setTab(el,'x')` direktno).

**Napomena:** ovo je POZNAT, prethodno identifikovan nalaz (memorija
"Beta Readiness sprint" — "sidebar reduction opet preskočen", dva puta
odloženo). Treći put da se pojavljuje isti nalaz je samo po sebi signal
da zaslužuje red u sledećem UI sprintu, ne treći nezavisni audit.

---

## 2. Dashboard (Pregled dana)

**Dubina provere:** duboka — `dash_load()`, `_dashRender()`,
`_ccBrifingHtml()`, `_healthIndexRender()`, `loadBriefing()`,
`_cioRender()`, `kcConstellationInit()` pročitani u celosti
(`static/vindex.js:999-2026`, `16543-16700+`).

### Problemi

**2.1 — Četiri nezavisna AI-narativna widgeta na jednom ekranu, sa
preklapajućim brojevima:**
1. **Health Index** (`_healthIndexRender`, `vindex.js:1158`) — "Zdravlje
   kancelarije danas" score/100 + grade + component breakdown + "Chief
   Partner — Direktiva za danas" TEKST (ili alerts, ili "sve pod
   kontrolom").
2. **AI Command Center Intel Briefing** (`_ccBrifingHtml`, `vindex.js:
   1262`) — sopstveni pozdrav + "Analizirao sam X predmeta, otkrio
   sam..." tekst, 4-stat traka (Rizika/Promena/Hitnih rokova/Ročišta
   danas), lista "Otkriveno" (do 7 stavki), "Prioritet danas" kartica,
   + async "Duboka analiza" ispod.
3. **Jutarnji brifing** (`loadBriefing`/`_renderBriefing`, `vindex.js:
   1625-1666`) — TREĆI odvojen AI tekst (`d.ai_briefing`) + SVOJA 4-stat
   traka (Hitnih rokova/Ročišta danas/Aktivnih predmeta/Rokova 7 dana).
4. **Chief Intelligence Officer** (`_cioLoad`/`_cioRender`, `vindex.js:
   16543-16600+`) — ČETVRTI AI glas, "portfolio zdravlje" (jakih/
   slabih/srednje predmeta) + `cio_preporuka` tekst.

Brojevi "hitnih rokova" i "ročišta danas" se prikazuju u NAJMANJE 3 od
4 widgeta (Health Index alerts, CC Intel stat traka, Jutarnji brifing
stat traka), plus PONOVO u 4-KPI redu (`vindex.js:1479-1484`), plus
PONOVO u dvokolonskom rasporedu ispod (`vindex.js:1553-1580`). Isti par
brojeva se pojavljuje na istom ekranu **do 5 puta**, svaki put drugom
vizuelnom težinom, i svaki put ga generiše DRUGI backend poziv
(`/api/dashboard/command-center`, `/api/firm/health-index`,
`/api/briefing/daily`, `/api/cio/daily`) — nema garancije da se
brojevi slažu (isti obrazac kao G-027, sad na 4 nezavisna izvora
umesto 2).

**2.2 — Globalna pretraga u topbar-u je vizuelno prisutna ali
funkcionalno mrtva:** `title="Globalna pretraga — dolazi uskoro"`
(`vindex.js:1467`) — element koji izgleda kao input polje, ne radi
ništa.

**2.3 — Dekorativna 3D "constellation" animacija** (`kcConstellationInit`,
`vindex.js:999-1107`+, rotirajuća sfera preko canvas-a sa orbitalnim
prstenovima) — nema informativnu funkciju, čisto vizuelni efekat.

**2.4 — "Pravni alati" 4 kartice na dnu** (`vindex.js:1598-1617`)
dupliraju ulaze koji već postoje u sidebar-u (Vindex Intelligence,
Sudska praksa) — isti alati, treći put ponuđeni na istom ekranu (posle
sidebar-a i posle "Vindex Intelligence" hub mod-svič-a).

### Zašto su problemi
Direktno krši masterprompt pitanje 6 ("Da li postoji više izvora
istine? Ako postoji, označi kao kritičan problem") — ovde nije jedno
polje nego CEO EKRAN sastavljen od 4 nezavisna AI izvora koji svi
tvrde da sumiraju "stanje kancelarije danas". Advokat koji prvi put
otvori aplikaciju vidi 4 različita "glasa" (Chief Partner, Command
Center, Jutarnji brifing, CIO) koji mu potencijalno kažu blago
različite verzije iste stvari, plus lažnu pretragu, plus dekorativnu
animaciju bez svrhe. Ovo je najozbiljniji, najkonkretniji primer
"kontrolne table aviona" utiska u celoj platformi — gori nego
Pregled predmeta (koji ima 3 widgeta, ne 4, i bar prikazuje ISTI
predmet, ne 4 nezavisna izveštaja).

### Ozbiljnost
**BLOCKER** za "izgleda jednostavno" utisak — ovo je PRVI ekran posle
logina, svaki dan, za svakog korisnika. Ne blokira funkcionalnost (sve
tehnički radi), ali je najveći pojedinačni rizik za "ovo nije dovoljno
zrelo" percepciju iz cele platforme.

### Predlog rešenja
Pre bilo kakvog vizuelnog redizajna, primeniti G-027 disciplinu: prvo
empirijski utvrditi da li ova 4 izvora ikad daju kontradiktorne brojeve
za isti predmet/kancelariju (isti "dokaz pre promene" princip koji je
upravo primenjen na Cockpit/Matter Intel). Ako se slažu — spojiti u
JEDAN narativni blok sa jednim glasom, ostala tri briefing tela postaju
IZVOR PODATAKA za taj jedan prikaz, ne 4 odvojena vizuelna bloka (isti
obrazac kao G-027 rešenje: jedan izvor istine, više potrošača postaje
jedan potrošač). Ukloniti ili sakriti lažnu pretragu dok ne postoji
prava (title="dolazi uskoro" ne treba da zauzima prostor). Ukloniti
constellation animaciju (nula informativne vrednosti, nasuprot
masterprompt "ZABRANJENO — vizuelni efekti bez funkcionalne koristi").
"Pravni alati" kartice na dnu — ukloniti ili zameniti linkom ka
postojećem Vindex Intelligence hub-u umesto duplirane liste.

### Zašto je novo rešenje bolje
Jedan glas umesto četiri direktno smanjuje kognitivno opterećenje
(masterprompt pitanje 4) i broj odluka (pitanje 8) na prvom ekranu.
Manji broj sekcija = brže vreme do "šta treba da uradim danas".

### Implementaciona složenost
**Visoka.** Ovo nije kozmetička izmena — zahteva prvo backend odluku
(koji izvor postaje "master" narativ) pre bilo kakve UI konsolidacije,
isto kao G-027. Najveći pojedinačni UI zahvat identifikovan u ovom
audit-u.

### Backend izmene
Da — ako se odluči da 4 endpoint-a (`/api/dashboard/command-center`,
`/api/firm/health-index`, `/api/briefing/daily`, `/api/cio/daily`)
treba da dele jedan izvor "šta se danas dešava" umesto da svaki računa
nezavisno.

### Uticaj na postojeću logiku
Visok — sva 4 endpoint-a se trenutno pozivaju paralelno i nezavisno
(`Promise.all` u `dash_load()`); spajanje zahteva promenu u tome KAKO
se dashboard puni, ne samo kako izgleda.

**Preporuka za redosled:** ovo NE ide pre CONTRACT 01, i verovatno NE
ide ni u "mali Sprint 2" bez svoje empirijske provere — obim je
uporediv sa G-027, zaslužuje sopstveni G-broj i sopstvenu validaciju
pre implementacije, ne mešati sa manjim UI zahvatima.

---

## 3. Pregled predmeta

**Dubina provere:** duboka (već urađena u ovoj sesiji kroz G-027 rad,
`index.html:766-1054`).

### Problemi
Već dijagnostikovano u ovoj sesiji: **(a)** tri preklapajuća skor-
widgeta — Matter Intelligence Bar, Cockpit, Case Ready Score — čiji je
"procesni rizik" deo REŠEN kodom (G-027, `services/risk_engine.py`),
ali VIZUELNA konsolidacija (tri odvojena bloka i dalje postoje na
ekranu, samo se sada slažu u broju) nije urađena. **(b)** četiri
administrativne sekcije (Zatvori predmet, ZPP Rokovi generator, Ugovor
o zastupanju, Klijentski portal) nabijene u glavni scroll odmah posle
AI procena, iako se koriste retko.

### Zašto su problemi
Masterprompt pitanje 3 ("Da li komponenta pomaže korisniku UPRAVO
SADA?") — administrativne sekcije ne pomažu pri svakodnevnom otvaranju
predmeta, samo povremeno. Pitanje 6 (više izvora istine) — delimično
rešeno kodom, vizuelno još nije.

### Ozbiljnost
**High** — najvredniji nalaz po founderovoj sopstvenoj oceni iz ranije
u ovoj sesiji ("Pregled ekran šaren/haotičan").

### Predlog rešenja
(Već dogovoreno ranije u sesiji, ponavlja se ovde radi kompletnosti
dokumenta.) Vizuelno spojiti tri skor-prikaza u jedan (sada bezbedno
jer se brojevi slažu posle G-027). Premestiti Zatvori predmet/ZPP
Rokovi/Ugovor/Portal iza "Više alata" collapse-a ili u odgovarajuće
postojeće podsekcije (npr. ZPP Rokovi generator konceptualno pripada
Rokovi subtab-u, ne Pregled-u).

### Implementaciona složenost
Niska-srednja za premeštanje sekcija (čisto HTML reorganizacija);
srednja za spajanje tri widgeta (mora se odlučiti finalni vizuelni
oblik, ne samo ukloniti duplikate).

### Backend izmene
Nema (G-027 već obezbedio jedinstven broj; ovo je čisto prikaz).

### Uticaj na postojeću logiku
Nizak — HTML/CSS reorganizacija, JS funkcije koje pune ta polja
(`pred_renderCockpit`, `matter_intel_load`, `pred_renderCaseReadyScore`)
ne moraju da se menjaju, samo gde se njihov output prikazuje.

---

## 4. Genome i Trust Layer

**Dubina provere:** duboka — `_caseDnaRender` (`vindex.js:16685-16796`)
pročitano u celosti za "uvek vidljivi" deo; "detaljna" sekcija iza
collapse-a (9+ pod-sekcija, prema komentaru u kodu) NIJE pročitana red
po red (poštovan progressive-disclosure princip — ako je skriveno iza
klika, ne mora se auditovati istom strogošću kao uvek-vidljiv sadržaj).

### Nalaz — POZITIVAN primer, ne problem
Genome panel je već prošao kroz identičnu disciplinu koju ovaj audit
traži, dokumentovano u samom kodu (komentari referenciraju P0.3
self-review i `SENIOR_LAWYER_SIMULATION_REPORT.md`, 2026-07-19):
- **"PREGLED" sažetak na vrhu** — status/najveća snaga/najveća slabost/
  sledeća akcija, 4 reda maksimum, PRE 9+ detaljnih sekcija.
- **Toggle uvek renderovan** (naučeno iz sopstvenog bug-a: ako sažetak
  nema sadržaj, toggle mora postojati da se detalji uopšte mogu
  otvoriti).
- **Trust Layer ("AI Provera") konsolidovan u JEDAN red** — kod
  eksplicitno beleži da je RANIJA verzija imala dva stalna reda i da je
  to bio cognitive-load problem, ispravljen.
- **"Na osnovu / Nedostaje" sažeto na 2 reda max** — kod eksplicitno
  beleži samo-otkriven problem (treći "uvek vidljiv" blok) i njegovu
  ispravku.

### Zašto je ovo vredno pomena u audit-u
Masterprompt traži da se svaka komponenta oceni nemilosrdno — ali
nemilosrdna ocena Genome panela je "ovo već radi kako treba, i sadrži
dokaz da je tim već primenio tačno ovu disciplinu jednom." Vredi
navesti kao REFERENTNI OBRAZAC za Dashboard (Sekcija 2) i Pregled
predmeta (Sekcija 3) — isti pristup (sažetak-pa-detalji, jedan trust-
signal red, ne dupliraj sličan tekst) doslovno već postoji u kodu,
samo nije primenjen svuda.

### Ozbiljnost
Nema akcione stavke — **Low/None**, informativni nalaz.

### Predlog rešenja
Nema predloga izmene za Genome samu. Predlog za DRUGE sekcije: kopirati
ovaj obrazac (sažetak-pa-detalji, jedan trust red) na Dashboard.

---

## 5. Dokumenta

**Dubina provere:** strukturna (`index.html:3252-3281`).

### Problemi
Top-level "Dokumenti" tab (`tab-dok`) nema sopstveni sadržaj — samo
tekstualna napomena ("dokumenti su organizovani unutar predmeta") i
dve navigacione kartice koje preusmeravaju: jedna na Predmeti tab,
druga na Analiza dokumenta AI alat. Nijedna lista, nijedna tabela,
nijedna funkcija koja ne postoji već negde drugde.

### Zašto je problem
Masterprompt pitanje 1 direktno: "Zašto ova komponenta postoji? Ako ne
postoji jasan odgovor, predloži uklanjanje." Ovaj top-level tab nema
jasan odgovor — postoji samo da bi preusmerio na dva mesta koja već
imaju svoje sopstvene ulaze u navigaciji (Predmeti tab, Vindex
Intelligence → Analiza dokumenta mod). Zauzima jedno od 13 mesta u
sidebar-u (Sekcija 1) bez jedinstvene funkcije.

### Ozbiljnost
**Medium** — ne zbunjuje aktivno (poruka je jasna), ali je čisto
navigacioni šum koji doprinosi 13-stavki problemu iz Sekcije 1.

### Predlog rešenja
Ukloniti kao top-level sidebar stavku. Ako postoji potreba da se
korisnik "uputi" gde su dokumenti kad ih traži na pogrešnom mestu, to
je posao praznog stanja (empty state) UNUTAR Predmeti taba, ne
sopstveni nav item.

### Zašto je novo rešenje bolje
Jedna manje odluka u sidebar-u (masterprompt pitanje 7/8 — manje
klikova, manje odluka) bez gubitka funkcije — sve što ova stranica radi
već je dostupno drugde.

### Implementaciona složenost
Niska — ukloniti jedan `<div class="t-tab">` red iz navigacije i
`tab-dok` blok. Proveriti da li nešto drugo linkuje direktno na
`setTab(...,'dok')` pre uklanjanja (npr. onboarding, deep linkovi).

### Backend izmene
Nema.

### Uticaj na postojeću logiku
Nizak, uz uslov iz gornjeg reda (provera postojećih linkova ka ovom
tabu pre brisanja).

---

## 6. Klijenti

**Dubina provere:** strukturna (`index.html:1860-1914`).

### Problemi
Nijedan ozbiljan nalaz iz strukturne provere. Lista→Profil obrazac je
standardan CRM pattern; 6 profil podtabova (Podaci/Aktivni predmeti/
Završeni/Hronologija/Dokumenti/Komunikacija) je razuman broj za CRM
kontekst, ne prekoračuje uobičajenu granicu. Header akcije (Konflikt/
CSV/Novi klijent) su 3 dugmeta — u redu.

### Zašto/Ozbiljnost/Predlog
Nema akcione stavke iz ove (strukturne) provere. Za punu ocenu bila bi
potrebna dubinska provera profila i formi (van budžeta ovog prolaza) —
ako se u budućoj sesiji ukaže potreba, ovo je kandidat za dubinsku
proveru, ne za sada.

---

## 7. Rokovi

**Dubina provere:** strukturna za sam kalendar (`index.html:2647-2682`)
+ duboka za jedan već poznat bug (G-026, iz ove iste sesije).

### Problemi

**7.1 — Tri odvojena dugmeta za izvoz** (.ics / Google / Outlook,
`index.html:2658-2660`) u istom header redu — moglo bi biti jedan
"Izvezi ▾" meni sa tri opcije, manje vizuelnog šuma u header-u koji već
ima 4 akcije (izvoz×3 + "+ Ročište").

**7.2 — G-026 (već dijagnostikovano ovom sesijom, Open, nije popravljen):**
credit panel (`#t-credits-row`, "Preostalo upita") se povremeno pojavi
na Rokovi tabu gde ne treba — race condition između `updateAuthUI()` i
`setTab()`, upisano u `VINDEX_OPERATIONAL_GAP_REGISTER.md`. Navodim
ovde radi kompletnosti stranice-po-stranice pregleda, ne kao nov nalaz.

### Zašto su problemi
7.1: manji vizuelni šum (masterprompt pitanje 5, dupliraju istu
funkciju — "izvezi" — u tri dugmeta). 7.2: aktivan, dokumentovan bug
koji direktno krši "korisnik ne sme videti nešto što izgleda polomljeno"
princip.

### Ozbiljnost
7.1: **Low.** 7.2: **Medium/Friction** (već ocenjeno u ranijem delu ove
sesije kao "FRICTION/TRUST DAMAGE").

### Predlog rešenja
7.1: konsolidovati u jedan dropdown. 7.2: već ima predlog u Gap
Registru — sredi vlasništvo nad `#t-credits-row` vidljivošću (jedan
pisac, ne tri).

### Implementaciona složenost
7.1: niska. 7.2: srednja (opisano u G-026 zapisu).

### Backend izmene
Nema za obe.

### Uticaj na postojeću logiku
Nizak za obe.

---

## 8. AI analiza / Vindex Intelligence

**Dubina provere:** strukturna (`index.html:2699-2758`).

### Problemi
"Vindex Intelligence" hub nudi 7 mod-pilula pre nego što korisnik i
otkuca pitanje: Istraživanje zakona, Analiza dokumenta, Nacrti
podnesaka, Strategija, Pravne oblasti, Litigation Intelligence,
Digitalna imovina. Nazivi mešaju svakodnevni jezik ("Nacrti podnesaka")
sa AI/enterprise žargonom ("Litigation Intelligence").

### Zašto je problem
Direktno krši masterprompt "Mentalni model advokata" sekciju: "Ne
razmišlja: Koji AI modul? Koji agent?" — a ovaj ekran upravo to traži
kao prvi korak, sa 7 opcija. "Litigation Intelligence" posebno ne
odgovara mentalnom modelu advokata (nije termin koji advokat sam
koristi u glavi).

### Ozbiljnost
**Medium** — mod-svič obrazac (jedan shell, više modova) je sam po sebi
DOBRA arhitektonska odluka (izbegnuta dalja fragmentacija tabova, videti
napomenu u kodu na `vindex.js:2211-2216` o konsolidaciji bivših
samostalnih tabova) — problem je samo u broju/nazivima opcija u prvom
redu izbora, ne u konceptu.

### Predlog rešenja
Ne menjati arhitekturu (mod-svič ostaje, ispravna odluka). Preimenovati
"Litigation Intelligence" u jezik bliži advokatovom mentalnom modelu
(masterprompt eksplicitno traži da se prati redosled: "Koji dokument mi
treba" itd., ne enterprise-software imenovanje). Razmotriti da li svih
7 modova treba da bude vidljivo odjednom ili da se manje korišćeni
(prema Product Intelligence analytics, ako postoji taj podatak) sakriju
iza "Više".

### Implementaciona složenost
Niska za preimenovanje. Srednja ako se dodaje "Više" grupisanje (nova
UI logika, mada mali obim).

### Backend izmene
Nema.

### Uticaj na postojeću logiku
Nizak — nazivi pilula su string konstante, `aiwsSetMode()` logika se
ne menja.

---

## 9. Finansije

**Dubina provere:** strukturna (`index.html:2490-2541`).

### Problemi
Nijedan ozbiljan nalaz. Redosled (KPI → grafikon → dugovanja → fakture
→ collapsible "Detaljni izveštaji") je već primer dobre progressive-
disclosure prakse — 5 naprednih izveštaja je SAKRIVENO iza jednog
collapse dugmeta, ne nabijeno u glavni prikaz. Ovo je isti obrazac kao
Genome (Sekcija 4) — vredan pominjanja kao pozitivan primer.

### Zašto/Ozbiljnost/Predlog
Nema akcione stavke.

---

## 10. Modali, forme, tabele — opšti obrasci

**Dubina provere:** strukturna (brojanje i imenovanje, ne svaki
pojedinačni modal).

### Problemi
Najmanje 14 imenovanih modala u `index.html` (auth, paywall, pro-
upgrade, feedback, pro, ugovor, pred-new, vx-unlock, mi-modal, settings,
compare, voice, ios-install, android-install). Većina koristi
`class="modal-overlay"` ili `class="vx-modal-overlay"` — ali NEKI
(`voice-modal`, `ios-install-modal`, `android-install-modal`, `mi-modal`)
imaju ručno pisane inline `style="position:fixed;..."` bez deljene
klase, umesto da koriste postojeći zajednički modal obrazac.

### Zašto je problem
Masterprompt pitanje 5 ("Da li postoje dve komponente koje rešavaju
isti problem? Ako postoje, spoji ih.") — ovde nije dupliran SADRŽAJ
nego dupliran MEHANIZAM: isti vizuelni/funkcionalni koncept ("modal
overlay") ima najmanje 2 paralelne implementacije (deljena CSS klasa
naspram ručnog inline stila). Ovo je isti D20.1/AR-01 obrazac
("jedan koncept, jedan izvor") primenjen na CSS/komponente umesto na
podatke ili poslovnu logiku — treći nezavisan kontekst gde se taj
obrazac pojavljuje u ovoj sesiji.

### Ozbiljnost
**Low/Medium** — ne utiče vidljivo na korisnika ako su svi vizuelno
identični (nije provereno da li JESU identični — to bi zahtevalo
poređenje computed stilova, van obima ove provere), ali je održavanje
rizik: izmena zajedničkog modal ponašanja (npr. ESC-za-zatvaranje,
klik-van-za-zatvaranje) mora se raditi na više mesta ručno umesto na
jednom.

### Predlog rešenja
Ne predlažem konkretan refaktoring bez prethodne provere da li se ovi
modali vizuelno/funkcionalno zaista razlikuju namerno (npr. install
modal-i su specifični za PWA install-prompt kontekst i možda opravdano
drugačiji). Predlog: pre bilo kakve izmene, kratka provera (kao G-026/
G-027 stil) da li razlika nosi nameru ili je slučajna divergencija.

### Implementaciona složenost
Nepoznata dok se ne uradi ta provera — otuda predlog da se PRVO
proveri, ne popravlja.

### Backend izmene
Nema.

### Uticaj na postojeću logiku
Nepoznat bez provere.

---

## Sumarna tabela — sve stavke, rangirano

| # | Stranica | Nalaz | Ozbiljnost | CONTRACT veza |
|---|---|---|---|---|
| 2.1 | Dashboard | 4 nezavisna AI-narativna widgeta, preklapajući brojevi | **BLOCKER** (utisak) | Nijedan — čist UX/poverenje nalaz |
| 1 | Navigacija | 13 sidebar stavki naspram 5 na mobilnom | High | Nijedan — poznat, 2x odložen |
| 3 | Pregled predmeta | 3 skor-widgeta (delom rešeno G-027) + 4 admin sekcije | High | CONTRACT 01 (Pregled je deo Toka 1) |
| 5 | Dokumenta | top-level tab bez sopstvenog sadržaja | Medium | Nijedan |
| 8 | AI analiza | 7 mod-pilula, "Litigation Intelligence" žargon | Medium | Nijedan |
| 7.2 | Rokovi | G-026 credit panel bug (već upisan, Open) | Medium (Friction) | Nijedan |
| 10 | Modali | 2 paralelne implementacije istog mehanizma | Low/Medium | Nijedan |
| 7.1 | Rokovi | 3 izvoz dugmeta umesto 1 dropdown-a | Low | Nijedan |
| 4 | Genome | (pozitivan primer, nema akciju) | — | — |
| 6 | Klijenti | (bez nalaza iz strukturne provere) | — | — |
| 9 | Finansije | (pozitivan primer, nema akciju) | — | — |

**Napomena o CONTRACT-vezi (founderovo pravilo iz ove sesije):** samo
Sekcija 3 (Pregled predmeta) je direktno na CONTRACT 01 putanji.
Ostalo — uključujući najozbiljniji nalaz (Dashboard) — NIJE vezano ni
za jedan od 4 CONTRACT-a, što po founderovom sopstvenom pravilu
("ako UI izmena ne može da se poveže sa korakom u CONTRACT-u, verovatno
nije prioritet pre bete") znači da čeka posle bete, bez obzira na
ozbiljnost utiska koji pravi.

---

## Šta NIJE urađeno u ovom audit-u (transparentnost o obimu)

- Nijedna forma, tabela ili kartica nije provereno pojedinačno van onih
  navedenih gore — masterprompt traži "sve forme/sve tabele/sve
  kartice" ali to bi za aplikaciju ove veličine (21.823 linije
  `vindex.js`, 4.663 linije `index.html`) zahtevalo obim koji prevazilazi
  jedan prolaz; gornjih 10 sekcija pokriva stranice koje je masterprompt
  eksplicitno imenovao ("Posebno analiziraj").
- Detaljne (collapsed) sekcije Genome panela (9+ pod-sekcija iza
  toggle-a) nisu pročitane red po red — poštovan je princip da se
  sakriveni sadržaj ne mora auditovati istom strogošću kao uvek-vidljiv.
- Nije provereno da li `_dashRender` ima "mrtav kod" duplikat (Command
  Center panel funkcije na `vindex.js:1716-2026` sa `kc-panel-hd`
  strukturom deluju kao alternativna/starija implementacija dashboard-a
  koja MOŽDA nije više pozvana — nisam potvrdio ovo sa sigurnošću, samo
  ga navodim kao pitanje vredno provere u budućoj sesiji, ne kao
  potvrđen nalaz).

---

## Zaključak — sledeći korak

Ovo je analiza, po founderovoj odluci od 2026-07-20. Sledeći korak NIJE
implementacija ijedne stavke odavde. Sledeći korak je (nepromenjen
sprint plan): završiti CONTRACT 01 ručni prolaz. Kad se taj prolaz
završi, ova tabela postaje kandidatska lista za Sprint 2 — birajući
prvo stavke koje su na CONTRACT putanji (trenutno samo Sekcija 3), uz
napomenu da je Sekcija 2 (Dashboard) najozbiljniji nalaz cele platforme
i zaslužuje sopstvenu odluku o prioritetu nezavisno od CONTRACT-pravila,
jer utiče na utisak SVAKOG korisnika SVAKI dan, ne samo na CONTRACT 01
tok.
