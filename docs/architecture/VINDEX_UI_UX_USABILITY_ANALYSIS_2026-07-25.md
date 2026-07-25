# Vindex AI — UI/UX & Usability Analiza (Maksimalna Jednostavnost za Advokate)

**Datum:** 2026-07-25
**Obim:** `index.html` (4679 linija), `static/vindex.js` (21823 linije),
`static/vindex.css` (9423 linije). Analiza, nula izmena koda.
**Fokus:** Vindex AI koriste advokati bez naprednog IT znanja — svaki
tehnički izraz, generička poruka o grešci ili premala dugmad direktno
poskupljuje korišćenje aplikacije za tu ciljnu grupu.

Ova analiza se **nadovezuje** na tri postojeća dokumenta i namerno ih ne
ponavlja:
- `VINDEX_UX_SIMPLIFICATION_AUDIT_2026-07-20.md` (ekran-po-ekran audit)
- `VINDEX_AI_UX_SIMPLIFICATION_STRATEGY.md` (Top 10, nova IA, 10 pravila)
- `VINDEX_UX_IMPLEMENTATION_GAP_REPORT_v1.0.md` (status: 0% realizacije)

Sekcija 1 ispod zato **citira** te nalaze umesto da ih ponovo izvodi.
Sekcije 2–4 su **nova teritorija** — terminologija, statusi
obrade/greške i mobilna pristupačnost nisu bili fokus prethodna tri
dokumenta.

---

## 1. Kognitivno opterećenje i Vizuelna Hijerarhija (Clutter Check)

**Već dijagnostikovano, i dalje nerešeno (0% realizacije, potvrđeno u
Gap Report-u).** Najvažniji nalazi koji direktno odgovaraju na pitanje:

- **Dashboard ima 4 nezavisna AI-narativna izvora** za isto "šta se
  danas dešava" (Health Index, AI Command Center Intel Briefing,
  Jutarnji brifing, Chief Intelligence Officer) — korisnik ne zna koji
  je "pravi" odgovor. Primarna akcija se gubi među 4 podjednako
  istaknuta widgeta. `vindex.js:1158,1262,1625,16543`.
- **"Sledeća akcija" ima 4 nekomunicirajuća sistema** (Cockpit/Matter
  Intelligence/Case Ready Score/`workflow.py`) — najozbiljniji
  pojedinačni nalaz jer krši osnovno obećanje "sistem vodi mene".
- **Sidebar: 13 stavki na desktop-u naspram 5 na mobilnom** — mobilna
  verzija je već ispravno pojednostavljena, desktop nikad usklađen.
- **Pozitivan kontraprimer koji već postoji u kodu:** Case Genome panel
  (`_caseDnaRender`, `vindex.js:16685-17048`) — sažetak na vrhu,
  detalji iza klika, jedan trust-signal red. Ovo je dokaz da tim zna
  rešenje; pitanje je samo primene na ostale ekrane.

Ne ponavljam predloge rešenja — v. Top 10 listu i Implementation
Roadmap u `VINDEX_AI_UX_SIMPLIFICATION_STRATEGY.md`. Za primarni
CTA specifično: trenutno stanje na Dashboard-u i Pregled predmeta
nema JEDNO istaknuto dugme već 3-4 podjednako vizuelno teška bloka —
ovo je isti nalaz kao gore, ne novi.

---

## 2. Terminologija i AI Transparentnost

**Nalaz: tehnički žargon curi u tačno one ekrane gde je najskuplje —
prodajne/konverzione (cenovnik, PRO upgrade) i svakodnevne AI odgovore
koje advokat gleda desetine puta dnevno.**

### 2.1 "RAG" bukvalno prikazan korisniku (4 lokacije, sve van dev/admin konteksta)

| Lokacija | Trenutni tekst | Kontekst |
|---|---|---|
| `vindex.js:6892` | `<span class="rag-verified">✓ RAG</span>` | **Bedž koji se prikazuje na SVAKOM visoko-pouzdanom AI odgovoru** — advokat ga vidi desetine puta dnevno, bez ikakvog objašnjenja šta "RAG" znači |
| `vindex.js:6773` | `lbl:'📖 Citat zakona [RAG]'` | Bedž tipa odgovora u AI chat-u |
| `vindex.js:7947` | `'RAG pretraga sudske prakse i zakona'` | Feature bullet na **cenovniku** (Basic plan) — potencijalni kupac ovo čita PRE nego što se registruje |
| `index.html:183` | `'RAG pretraga kroz 30.365 pravnih izvora pri generisanju'` | Bullet u **PRO upgrade modalu** — najkonverzivniji ekran u aplikaciji |

`vindex.js:5013` dodatno: `'RAG-pretraga nad ingestovanim CARF... tekstom'`
— "ingestovanim" je inženjerski žargon (od "data ingestion") koji
nema pravni ekvivalent u srpskom govornom jeziku.

**Zašto je ovo najozbiljniji nalaz u celoj sekciji 2:** "RAG" (Retrieval-
Augmented Generation) je termin za AI inženjere. Advokat koji vidi
"✓ RAG" pored odgovora nema način da proceni da li je to dobra ili loša
stvar — bedž koji bi trebalo da GRADI poverenje (otuda "trust-badge"
klase u istom fajlu) umesto toga zbunjuje.

**Predlog zamene** (isti smisao, bez žargona):
- `✓ RAG` → `✓ Potvrđeno u bazi propisa` ili `✓ Izvor proveren`
- `[RAG]` bedž uz citat zakona → ukloniti potpuno (citat zakona sam po
  sebi već nosi informaciju, "[RAG]" ne dodaje ništa korisniku)
- `RAG pretraga sudske prakse i zakona` (cenovnik) → `Pretraga kroz celu
  bazu zakona i sudske prakse`
- `RAG pretraga kroz 30.365 pravnih izvora` (PRO modal) → `Pretraga kroz
  30.365 zakona, presuda i mišljenja pri svakom nacrtu`

### 2.2 Ostali žargon (niži prioritet, opravdaniji kontekst)

- `embeddings` (`index.html:4557,4663`) — pojavljuje se u **GDPR/DPA
  disclosure modalu** ("Gde i koliko dugo se podaci čuvaju"). Ovo je
  zakonski obavezan tehnički opis obrade podataka, ne svakodnevni UI —
  **ne preporučujem pojednostavljenje ovde**, tačnost je bitnija od
  pristupačnosti u pravno obavezujućem tekstu.
- `webhook` (`index.html:3601,3606`) — u sekciji **Integracije**
  (Clio/iManage povezivanje), ciljana na IT administratora firme, ne na
  advokata koji svakodnevno koristi aplikaciju. Prihvatljivo zadržati,
  eventualno dodati jednu rečenicu objašnjenja iznad polja.

**Zaključak sekcije 2:** Problem nije rasprostranjen kroz celu
aplikaciju (dobra vest — ostatak interfejsa dosledno koristi pravne
termine: "Pretraga sudske prakse", "AI Analiza predmeta", "Pametan
uvid" se već koriste na drugim mestima). Problem je koncentrisan na **5
konkretnih string-ova**, svih 5 lako zamenjivih bez ikakvog rizika po
logiku aplikacije.

---

## 3. Statusi obrade i Povratne informacije (Loading & Error States)

### 3.1 Loading — postoji odličan obrazac, ali se ne koristi svuda

Kod već sadrži **primer-vredan pattern** za dugotrajne (60-90s)
AI poslove: `_strat6ModuliHtml()` / `_stratSingleModulHtml()`
(`vindex.js:3600-3639`). Progres bar, checklist koraka koji se pale
jedan po jedan, i **rotirajuće KONKRETNE fraze** ("Analiziram
dokumente...", "Upoređujem sudsku praksu...", "Simuliram
strategije...", "Formiram preporuku..."). Sam kod ima komentar koji
objašnjava founderovu nameru:

> `vindex.js:3620` — *"KONKRETNE radnje, ne generičko 'Molimo sačekajte'
> — founder: bitno je da korisnik zna DA sistem radi i ŠTA otprilike
> radi."*

Ovo je **tačno ispravan princip** i tačno ono što pitanje 3 traži. Isti
princip se dosledno primenjuje i na kraće operacije koje imaju
namenski spinner: `"Tražim rokove..."`, `"Analiziram predmet..."`,
`"Generisanje grafa u toku..."` (`vindex.js:9199,18945,20939`).

**Problem:** ovaj obrazac postoji samo za ~8 mesta u celom fajlu.
Za brze (3-5s) svakodnevne AI pozive van ovih par ekrana, nema dokaza
o standardizovanom "razmišljam" indikatoru — korisnik verovatno gleda
prazan/nepromenjen ekran dok čeka odgovor, isti rizik na koji pitanje 3
upozorava ("Da li postoji jasan, smirujući vizuelni indikator?").

### 3.2 Greške — sistemski problem, 90 pojava jedne bezvredne poruke

Pretraga `static/vindex.js` na tačan string pokazuje:

```
"Greška."          — generička, bez konteksta, bez uputstva
"Greška mreže."    — ne kaže da li da pokuša ponovo, da proveri internet, ili da kontaktira podršku
"Greška veze."
"Mrežna greška."
```

**90 pojava** ovih 4 varijante u `static/vindex.js` (potvrđeno grep
pretragom). Primeri konkretnih lokacija:

- `vindex.js:4643` — `alert('Greška.')` posle pokušaja prikaza
  poverljivih podataka klijenta
- `vindex.js:4802` — `alert('Greška pri čuvanju.')` — ne kaže korisniku
  da li je promena izgubljena i treba ponovo da unese podatke, ili
  samo da klikne opet
- `vindex.js:3018,3028,3061,9803,13101,13976` i desetine drugih —
  `errEl.textContent='Greška mreže.'` bez dugmeta "Pokušaj ponovo" i
  bez objašnjenja

Čak i u **najboljem** postojećem obrascu (§3.1, `strat_job_poll`,
`vindex.js:3662,3669`), greška se i dalje prikazuje kao
`'Greška: ' + e.message` — što znači da sirova JavaScript/mrežna
poruka (npr. `Failed to fetch`) može direktno da se prikaže advokatu.

**Zašto je ovo najveći pojedinačni nalaz u celoj analizi:** 90 pojava
znači da je ovo *jedini* obrazac za greške u celoj aplikaciji — nije
izuzetak, to je standard. Advokat koji naiđe na grešku dobija tekst
koji ne objašnjava ništa i ne nudi sledeći korak, tačno suprotno od
principa koji sam kod već primenjuje za loading stanja (§3.1).

---

## 4. Mobilna i Tablet Pristupačnost (Responsive & Font Sizes)

**Pozitivno:** baza je zdrava — `html { font-size: 16px; }`
(`vindex.css:2790-2792`), **75 media query breakpointa** znači da
responsive struktura postoji na širokoj skali ekrana, i kritična polja
za unos (chat input, tekst polja) su namerno fiksirana na `font-size:
16px !important` (`vindex.css:5956,6150`) — ovo je poznat trik da se
spreči automatski zoom na iOS-u kad korisnik dodirne polje, znak da je
neko već razmišljao o mobilnoj upotrebi.

**Problem 1 — sitan tekst je pravilo, ne izuzetak.** 95 pojava
`font-size` između `0.50rem` i `0.64rem` (8–10px pri baznih 16px) u
`vindex.css`, plus dosledno isti opseg u inline stilovima kroz
`index.html` (npr. `font-size:0.68rem`, `0.72rem`, `0.76rem` na
desetine mesta — vidljivo u Integracije, PRO modal, GDPR disclosure
sekcijama). Za ciljnu grupu koja uključuje starije advokate, 8-10px
tekst je ispod praga udobnog čitanja bez zumiranja, posebno na
telefonu.

**Problem 2 — dodirne mete ispod preporučenog minimuma.** Standardni
dugmad (`.strat-btn`, `.push-btn`) imaju `min-height: 36px`
(`vindex.css:721,760`). Apple HIG i Material Design preporučuju **44px**
kao minimum za pouzdan dodir bez promašaja — 36px je 8px ispod toga,
relevantno posebno za korisnike sa manje preciznom motorikom.
Izuzetak koji je URAĐEN ispravno: `.intake-back-btn` na mobilnom već
ima `min-height: 46px` (`vindex.css:7401`) — dokaz da tim zna
standard, samo nije primenjen dosledno na sve dugmad.

**Dark Mode kontrast:** aplikacija je isključivo tamna tema (nema
light mode toggle-a — potvrđeno projektnim standardom "Bloomberg
stil"). Većina teksta koristi `rgba(255,255,255,0.4)` do `0.5)` opacity
za sekundarni tekst (npr. poruke o greškama iz §3.2 — `color:
rgba(255,100,100,0.5)` za crvenu grešku na crnoj pozadini) — ovo je
niz kontrast za tekst koji nosi VAŽNU informaciju (greška), ne
dekorativni element. WCAG AA za mali tekst traži kontrast 4.5:1;
`rgba(255,100,100,0.5)` na `#010308` pozadini pada značajno ispod toga.

---

## 5. Top 5 Konkretnih (Hirurških) UX Poboljšanja

Kriterijum: **maksimalan uticaj na jednostavnost, minimalan rizik po
postojeću logiku** — svih 5 su promene teksta/CSS-a, nula promena u
poslovnoj logici ili backend pozivima.

### 1. Ukloniti "RAG" iz svih korisniku vidljivih ekrana (5 stringova)
`vindex.js:6892,6773,7947,5013`, `index.html:183` — zamena teksta po
tabeli iz §2.1. **Najveći uticaj po liniji promenjenog koda** u celoj
listi: bedž `✓ RAG` se prikazuje na svakom pouzdanom AI odgovoru,
dakle stotine puta dnevno po korisniku.

### 2. Jedan zajednički "human-error" helper umesto 90 raštrkanih `'Greška.'` poziva
Umesto pojedinačne zamene 90 mesta, uvesti jednu funkciju (npr.
`vxErrorToast(poruka, {retry: fn})`) koja: (a) piše konkretno šta nije
uspelo ("Nije moguće sačuvati klijenta"), (b) daje konkretan sledeći
korak ("Proverite internet konekciju i pokušajte ponovo"), (c) opciono
nudi dugme "Pokušaj ponovo". Zameniti postojeće pozive postepeno,
počev od najčešće korišćenih tokova (klijenti, čuvanje predmeta —
`vindex.js:4643,4802,4821`). Najveći sistemski dobitak u ovoj listi.

### 3. Podići `min-height` standardnih dugmadi sa 36px na 44px na mobilnom
Jedan CSS media-query blok (`vindex.css`, mobilni breakpoint) —
`.strat-btn`, `.push-btn` i slične klase. Nulti rizik (čisto vizuelno
uvećanje dodirne zone), meri se u minutima rada, direktno adresira
nalaz iz §4.

### 4. Proširiti postojeći "konkretna fraza" loading pattern na brze AI pozive
Iskoristiti već napisan `_stratSingleModulHtml`-stil (rotirajuće
konkretne fraze tipa "Proveravam zakon...", "Tražim presedan...") na
mestima gde trenutno AI poziv od 3-5s nema nikakav vizuelni indikator
napretka. Nije nova komponenta — samo primena postojeće na više mesta,
isti obrazac koji je Case Genome panel već dokazao da radi (§1).

### 5. Zameniti `'Greška: ' + e.message` sirove poruke ljudskim tekstom
Čak i u najboljem postojećem loading obrascu (`strat_job_poll`,
`vindex.js:3662,3669`) sirova JS/mrežna greška može procuriti direktno
na ekran. Mapirati poznate `e.message` vrednosti (`Failed to fetch`,
`NetworkError...`) na jednu rečenicu: "Veza sa serverom je prekinuta —
proverite internet i pokušajte ponovo." Mala izmena, zatvara poslednju
rupu u inače najbolje dizajniranom loading toku u aplikaciji.

---

## Sumarno

| Pitanje | Odgovor |
|---|---|
| 1. Clutter/CTA na Dashboard-u | Već dijagnostikovano, 0% rešeno — v. postojeća 3 dokumenta |
| 2. Tehnički žargon | Koncentrisan na 5 stringova ("RAG"), ali baš u najkonverzivnijim ekranima (cenovnik, PRO modal, chat bedž) |
| 3. Loading/Error stanja | Loading: odličan pattern postoji, primenjen na ~8 mesta. Greške: 90 pojava jedne bezvredne poruke — sistemski problem |
| 4. Mobilna pristupačnost | Struktura zdrava (16px baza, 75 breakpointa), ali 95 mesta sa 8-10px tekstom i dugmad 8px ispod preporučenog dodirnog minimuma |
| 5. Top 5 hirurških izmena | Sve 5 su tekst/CSS promene bez rizika po logiku — v. iznad |
