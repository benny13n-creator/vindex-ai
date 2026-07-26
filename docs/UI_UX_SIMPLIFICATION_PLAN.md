# Vindex AI — UI/UX Simplification Plan: Radni Tok po Fazama Predmeta (2026-07-26)

**Status:** Plan/predlog, **nula izmena koda**. Isti standard kao tri
prethodna UX dokumenta ove sesije (`VINDEX_UX_SIMPLIFICATION_AUDIT_2026-07-20.md`,
`VINDEX_AI_UX_SIMPLIFICATION_STRATEGY.md`,
`VINDEX_UI_UX_USABILITY_ANALYSIS_2026-07-25.md`) — ovaj se ne ponavlja,
fokusira se isključivo na "modulnu tablu" (tool-selection dashboard) koju
zahtev traži.

**Korekcija premise pre bilo čega drugog:** komponenta koju zahtev opisuje
konkretno postoji na **`index.html:1136-1249`**, `id="pred-pane-strategija"`
("Pregled predmeta → Strategija" pod-tab), CSS klasa `.strat-feature-card`
(`static/vindex.css:5698-5712`), 8 stvarnih alata definisanih u
`STRAT_MODULI` (`static/vindex.js:3193-3253`). "Draft Engine" i "Pravni
osnov" iz zahteva **nisu deo ove komponente** — žive u potpuno odvojenim
top-level tabovima (`routers/drafting.py`'s nacrti/podnesci UI, i AI
Intelligence hub-ov "zakon" mod). Ovo je važno jer određuje šta se realno
može reorganizovati u OVOJ komponenti bez šireg refaktora — v. §1.4.

---

## 0. Zatečeno stanje (dokazi)

### 0.1 Osam stvarnih alata (STRAT_MODULI, `vindex.js:3193-3253`)

| Ključ | Naziv u UI-ju | Trenutna kategorija na kartici |
|---|---|---|
| `red_team` | Analiza crvenog tima | "Analiza i procena" |
| `sudija` | Sudija — procena ishoda | "Simulacija suda" |
| `sudija_v2` | Simulacija sudskog postupka | "Simulacija suda" |
| `litigation` | Simulacija parničnog postupka | "Simulacija suda" |
| `witness` | Analiza svedoka | "Dokumenti i svedoci" |
| `revizor` | Revizija dokumenta | "Dokumenti i svedoci" |
| `due_diligence` | Analiza rizika | "Dokumenti i svedoci" |
| `court_predictor` | Predikcija ishoda | (nije na kartici — samo u pill-row-u, v. 0.3) |

Plus 3 kartice van `STRAT_MODULI` u istom gridu: **Hearing Command Center**
(`rokovi` subtab), **Outcome Intelligence** (kancelarijska statistika),
**Digital Twin** (3-scenario simulacija).

### 0.2 Postojeća kategorizacija ne prati životni ciklus predmeta

Trenutne sekcije (`index.html:1137,1150,1179,1207,1219`) su: "Analiza i
procena" (1 kartica), "Simulacija suda" (3), "Dokumenti i svedoci" (3,
uključujući Reviziju dokumenta koja logički pripada RANOJ fazi, ne istoj
grupi kao Analiza svedoka), "Priprema za ročište" (1), "Inteligencija
kancelarije" (2). Ovo je flat skrolujuća lista labela, ne tabovi — cela
lista se scroll-uje odjednom.

### 0.3 Skriven, neočigledan navigacioni skok

**Konkretan, verifikovan nalaz:** klik na BILO KOJU `.strat-feature-card`
poziva `pred_openStrat(modul)` (`vindex.js:10386-10392`), koji poziva
`openAITool('t')` (`vindex.js:2456-2467`) — a ta funkcija radi
`setTab(aiwsBtn, 'aiws')`, prebacujući korisnika **na potpuno drugi
top-level tab** ("Vindex Intelligence"), gde tek onda živi stvarni
pill-row (`.strat-btn`, `index.html:2982-2990`) i tekst-unos za taj alat.
Korisnik bira alat na jednom mestu, a stvarno ga koristi na drugom —
razdvojeno skrivenim JS pozivom, ne vizuelno očiglednom navigacijom
(nema breadcrumb-a, nema animacije prelaska, izgleda kao da se "cela
aplikacija promenila"). Ovo je **konkretan uzrok** zašto konsolidacija u
jedan mesto (v. §3) ima realnu vrednost, ne samo kozmetičku.

### 0.4 Nema vizuelne razlike po tipu alata

`static/vindex.css:5698-5712` — SVAKA `.strat-feature-card` koristi
identičan `border: 1px solid rgba(255,255,255,.07)` bez obzira da li je
alat analitika (Red Team), pisanje (Revizor) ili simulacija (Sudija).
`.pro-badge` (zlatna) je jedina vizuelna varijacija, i ona označava CENU,
ne TIP alata.

### 0.5 Opis je uvek vidljiv, uvek pun tekst

`.sfc-desc` (`vindex.css:5710`) nema `hover`/`:not(:hover)` skrivanje —
svih 8+ opisa (30-90 karaktera svaki) renderuje se odjednom, uvek. Za
korisnika koji skrola kroz listu, ovo je i tražena "gustina teksta" iz
zahteva.

---

## 1. Predlog: Radni Tok po Fazama (Workflow Buckets)

### 1.1 Mapiranje na STVARNE alate

| Faza | Alati (STRAT_MODULI ključ) | Napomena |
|---|---|---|
| **FAZA 1: INTAKE & ANALIZA** | `due_diligence` (Analiza rizika), `revizor` (Revizija dokumenta) | Smart Intake **NIJE** ovde — v. §1.4 |
| **FAZA 2: STRATEGIJA & SVEDOCI** | `red_team` (Crveni tim), `witness` (Analiza svedoka) | Tačno kako zahtev traži |
| **FAZA 3: IZRAĐIVANJE NACRTA** | *(nema STRAT_MODULI alata ovde)* | Draft Engine/Pravni osnov nisu deo ove komponente — v. §1.4 |
| **FAZA 4: SIMULACIJA SUDA** | `sudija`, `sudija_v2`, `litigation`, `court_predictor`, Digital Twin, Hearing Command Center | `litigation`/`court_predictor`/Twin/Hearing nisu eksplicitno pomenuti u zahtevu — dodati ovde po istoj logici ("šta će se desiti na sudu"), obrazloženo ispod |

**Obrazloženje sudijske odluke za nepomenute alate:** `litigation`
("Simulator parnice" — % uspeha, preporuka tužba/odbrana/nagodba) i
`court_predictor` ("Predikcija ishoda" — statistička %) su suštinski isti
tip pitanja kao `sudija`/`sudija_v2` — razlika je metod (debate-simulacija
vs. statistička procena), ne faza predmeta. Digital Twin (3-scenario
simulacija razvoja) i Hearing Command Center (borbeni brifing pred
ročište) su takođe "šta će se desiti / kako se pripremiti za sud" —
prirodno pripadaju Fazi 4, ne novoj petoj kategoriji.

**Outcome Intelligence (kancelarijska statistika) namerno IZOSTAVLJENA iz
sve 4 faze** — nije korak u životnom ciklusu JEDNOG predmeta, već
cross-case kancelarijska analitika. Predlog: zadržati kao zasebnu,
uvek-vidljivu sekciju ISPOD 4 faze taba (ne u njima), kao što je i danas
pozicionirana poslednja u listi.

### 1.2 FAZA 3 je praznina u ovoj komponenti — dve opcije

Zahtev eksplicitno traži "FAZA 3: IZRAĐIVANJE NACRTA (Draft Engine, Pravni
osnov)" ali nijedan od ta dva alata ne živi u `STRAT_MODULI`/
`.strat-feature-card` gridu danas. Dve legitimne opcije, founder bira:

- **Opcija A (minimalan rizik):** Faza 3 tab u ovoj komponenti sadrži
  SAMO jednu "prečicu" karticu — "Otvori Nacrti/Podnesci →" koja radi
  `setTab(..., 'n')` (isti obrazac kao postojeći `openAITool` skok, samo
  eksplicitno imenovan i vizuelno najavljen, ne skriven). Nula promena u
  `routers/drafting.py` ili nacrt UI-ju.
- **Opcija B (veći zahvat, prava konsolidacija):** stvarno preseliti
  nacrt-generisanje UI (tip-selektor, opis-textarea, dugme) UNUTAR ove
  komponente kao četvrti tab, pozivajući postojeće `/api/nacrt`/
  `/api/podnesak` endpointe iz novog mesta. Ovo bi prvi put učinilo da
  "4 faze" bude STVARNO jedno mesto, ne 3 mesta + 1 prečica. Zahteva
  poseban frontend rad (nova tab-panel markup, prebacivanje postojeće
  `podnesak-tip`/`podnesak-opis` logike) — nije obuhvaćeno ovim planom,
  navedeno kao Sprint 2 kandidat ako founder odluči za Opciju B.

Preporuka: **Opcija A za prvi prolaz** — dobija se tražena 4-faze
struktura odmah, bez rizika po postojeći, već testiran nacrt-generisanje
tok.

### 1.3 Predložena nova HTML struktura (zamenjuje flat listu, `index.html:1136-1249`)

```html
<div class="vx-phase-tabs" role="tablist">
  <button class="vx-phase-tab active" data-phase="1" onclick="predStratPhaseSwitch('1', this)">
    <span class="vx-phase-num">1</span> Intake & Analiza
  </button>
  <button class="vx-phase-tab" data-phase="2" onclick="predStratPhaseSwitch('2', this)">
    <span class="vx-phase-num">2</span> Strategija & Svedoci
  </button>
  <button class="vx-phase-tab" data-phase="3" onclick="predStratPhaseSwitch('3', this)">
    <span class="vx-phase-num">3</span> Izrada Nacrta
  </button>
  <button class="vx-phase-tab" data-phase="4" onclick="predStratPhaseSwitch('4', this)">
    <span class="vx-phase-num">4</span> Simulacija Suda
  </button>
</div>

<div class="vx-phase-panel" data-phase-panel="1">
  <!-- due_diligence, revizor kartice ovde -->
</div>
<div class="vx-phase-panel" data-phase-panel="2" style="display:none;">
  <!-- red_team, witness kartice ovde -->
</div>
<div class="vx-phase-panel" data-phase-panel="3" style="display:none;">
  <!-- Opcija A: 1 prečica-kartica ka Nacrti/Podnesci -->
</div>
<div class="vx-phase-panel" data-phase-panel="4" style="display:none;">
  <!-- sudija, sudija_v2, litigation, court_predictor, twin, hearing kartice ovde -->
</div>

<!-- Outcome Intelligence ostaje OVDE, van faza -->
```

`predStratPhaseSwitch(phase, btn)` — nova, mala JS funkcija (analogna
postojećoj `pred_subtabSwitch`/`oblastiIzaberiOblast` obrascu): toggle
`active` klase na `.vx-phase-tab`, toggle `display` na `.vx-phase-panel`.
Ovo ponovo koristi VEĆ POSTOJEĆI `.pred-subtab-btn` vizuelni jezik
(`vindex.css`, editovano ranije ove sesije za touch target 44px) umesto
izmišljanja novog tab stila — v. `.vx-phase-tab` predlog niže kao
izvedenicu te klase.

---

## 2. Smanjenje Kognitivnog Opterećenja (CSS predlog)

### 2.1 Opis na hover / expand, ne uvek vidljiv

```css
/* Trenutno: .sfc-desc uvek renderovan, 30-90 karaktera x 8+ kartica */

.strat-feature-card { position: relative; }
.sfc-desc {
  max-height: 0;
  overflow: hidden;
  opacity: 0;
  transition: max-height .18s ease, opacity .15s ease;
  font-size: .7rem; color: rgba(255,255,255,.42); line-height: 1.5;
}
.strat-feature-card:hover .sfc-desc,
.strat-feature-card:focus-within .sfc-desc {
  max-height: 4.5em;   /* ~3 reda */
  opacity: 1;
  margin-top: .18rem;
}
```

**Napomena o pristupačnosti:** `:hover`-only skrivanje bez `:focus-within`
bi isključilo tastaturu/screen-reader korisnike iz opisa — zato oba
selektora zajedno. Alternativa (robusnija na mobilnom, gde `:hover` ne
postoji čisto): mali "ⓘ" info-ikonica koja na klik/tap otvara opis u
malom popover-u, umesto oslanjanja na hover — preporučeno ZA MOBILNI
prikaz specifično (media query override).

### 2.2 Boja/border akcenat po TIPU alata (ne po fazi — ortogonalna dimenzija)

Taksonomija (3 tipa, dovoljno da se razlikuje bez šarenila):

| Tip | Alati | Akcenat |
|---|---|---|
| **Analitika** | Red Team, Analiza rizika, Analiza svedoka, Outcome Intel | Plava (`--vx-accent: #00d4ff`, već postojeći token) |
| **Simulacija** | Sudija, Sudija v2, Litigation, Predikcija ishoda, Digital Twin | Ljubičasta (`rgba(167,139,250,.5)` — već korišćena boja u GDPR/DPA sekcijama, npr. `index.html:4594`, ponovna upotreba postojeće boje, ne novi token) |
| **Pisanje/Revizija** | Revizija dokumenta, (budući Draft Engine ako Opcija B) | Zelenkasta (`rgba(74,222,128,.4)` — `#4ade80`, već pervazivno korišćena "pozitivan/dobar" boja u kodu, npr. `vindex.css:134,145`, ne novi token) |

```css
.strat-feature-card { border-left: 2px solid transparent; }
.strat-feature-card[data-tip="analitika"]  { border-left-color: rgba(0,212,255,.35); }
.strat-feature-card[data-tip="simulacija"] { border-left-color: rgba(167,139,250,.35); }
.strat-feature-card[data-tip="pisanje"]    { border-left-color: rgba(74,222,128,.35); }
```

Implementacija: dodati `data-tip="analitika|simulacija|pisanje"` atribut
na svaku `.strat-feature-card` u markupu (§1.3) — čisto deklarativno, bez
JS izmene. **Namerno SUBTILNO** (`border-left`, ne pozadina/glow) — u
skladu sa postojećim projektnim standardom "Bloomberg stil, bez glow-a"
(`[[feedback_no_generic_ui_bloomberg_style]]`).

### 2.3 Razmak (spacing) između sekcija

Trenutno: `margin-bottom:.85rem` inline na svakom `<div style="display:grid;gap:.45rem;...">`
wrapper-u (`index.html:1138,1151,1180`) — funkcioniše, ali inline stilovi
ponovljeni 5x. Predlog: konsolidovati u `.vx-phase-panel { display:grid;
gap:.5rem; }` na nivou panela (§1.3), ukloniti inline stilove — čisti
postojeći obrazac umesto dodavanja novog.

---

## 3. Glavna Akcija (Primary Action Hierarchy)

### 3.1 Zadržati postojeći hero, ojačati ga

`.vx-insight-panel` ("Kompletna analiza predmeta", `index.html:1128-1134`)
je VEĆ ispravno pozicioniran kao jedina hero akcija na vrhu — ovo NIJE
problem koji treba rešavati od nule, samo ojačati kontrast u odnosu na
kartice ispod (koje će sada biti u tabovima, dodatno vizuelno odvojene).
Predlog: dodati `border: 1px solid rgba(0,212,255,.25)` (blag akcenat,
already-established `--vx-accent`) na `.vx-insight-panel` da se jasnije
razdvoji od `.strat-feature-card` ispod, pošto će obe komponente sada
deliti isti vizuelni nivo (kartica sa ikonicom+tekstom) — danas ih boja
pozadine jedva razlikuje.

### 3.2 Tabovi umesto flat liste (v. §1.3)

Glavna promena traženog stava 3: 4 faze KAO TABOVI (ne kao skrolujuće
labele) direktno rešava "jasnu vizuelnu hijerarhiju" zahtev — korisnik
vidi 1 dominantno dugme (Kompletna analiza) na vrhu, ispod NJEGA 4 taba
(faze), i tek ispod izabranog taba 2-6 kartica te faze — umesto 8+
kartica odjednom u jednoj dugoj listi.

### 3.3 Rešiti (ili bar imenovati) skriveni navigacioni skok (§0.3)

Ako se implementira §1.2 Opcija A/kartice ostaju kao danas (klik →
`pred_openStrat` → skok na `aiws` tab): predlog da se korisniku PRVI PUT
jasno pokaže da će doći do promene ekrana — npr. kratka animacija/toast
("Otvaram: Analiza crvenog tima...") pre `setTab` poziva, umesto trenutnog
tihog, neobjašnjenog skoka. Minimalna izmena u `pred_openStrat`
(`vindex.js:10386`), ne zahteva noviju arhitekturu.

---

## 4. Sažetak — šta bi trebalo izmeniti (za budući implementacioni task)

| Fajl | Izmena | Rizik |
|---|---|---|
| `index.html:1136-1249` | Zameniti flat listu sa 4 `.vx-phase-panel` + `.vx-phase-tabs` (§1.3) | Nizak — čisto markup restrukturiranje, isti sadržaj kartica |
| `static/vindex.js` | Nova `predStratPhaseSwitch(phase, btn)` funkcija (analogna `pred_subtabSwitch`) | Nizak — nova, izolovana funkcija |
| `static/vindex.js:10386` | `pred_openStrat` — opciono najaviti skok na `aiws` tab (§3.3) | Nizak |
| `static/vindex.css` | `.vx-phase-tab`/`.vx-phase-panel` (novo, izvedeno iz `.pred-subtab-btn`), `.sfc-desc` hover-reveal (§2.1), `data-tip` border-left boje (§2.2) | Nizak — aditivno, ne menja postojeće klase |
| `index.html` (kartice) | Dodati `data-tip="analitika\|simulacija\|pisanje"` atribut na svaku od 11 kartica | Nizak — deklarativno |

**Nije uključeno u ovaj plan (zahteva posebnu founder odluku):** Opcija B
iz §1.2 (stvarno preseljenje Draft Engine UI-ja u ovu komponentu) — veći
zahvat, sopstveni sprint.
