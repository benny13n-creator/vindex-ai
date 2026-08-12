# FAZA 2 — FORENSIC CLEANUP: REMOVE / KEEP / MERGE / REWIRE

**Polazno:** `c6369d35` · 5161 passed
**Završno:** **5178 passed / 1 skipped / 0 failed**, `no:randomly` i `seed=11`

Lanac čuvanja primenjen na **34 kandidata** (3 funkcije + 31 mrtva DOM
referenca), u četiri sloja: statičke reference → tačna atribucija funkcije
(brace-matching) → dostižnost do `index.html` → **runtime** (instrumentiran
`getElementById` kroz 12 tabova, 12 podtabova i 9 modala).

---

# ZBIRNO

```
REMOVED     3 funkcije + 1 modal + 5 DOM ID-jeva   (1 zatvoreno ostrvo)
REWIRED     1                                      („Štampaj")
KEPT        2 funkcije + 2 modala                   (qiOtvori, bulkOtvori)
MERGED      0
UNRESOLVED  4
```

**`UNRESOLVED > 0` ⇒ FAZA 2 NIJE ZATVORENA.** Četiri stavke traže odluku
vlasnika, ne dodatnu forenziku — dokazi su kompletni, nedostaje proizvodni sud.

---

# TABELA PRESUDA

## Funkcije

| Kandidat | Static | Dynamic | Runtime | Alternate caller | Verdict | Dokaz |
|---|---|---|---|---|---|---|
| `pred_openNewModal` | 0 | 0 (`niska`: 0) | ❌ nikad pozvan | ❌ | **REMOVE** | zatvoreno ostrvo: `open→close→kreiraj` + modal 384-416; nijedna referenca spolja |
| `qiOtvori` | 1 (`index.html:601`) | 0 | ❌ | ⚠ dugme trajno `display:none`, prazno, ništa ga ne otkriva | **KEEP** | modal `#qi-overlay` je **kompletan**: 6 dugmadi, 4 polja |
| `bulkOtvori` | 1 (`index.html:602`) | 0 | ❌ | ⚠ isto | **KEEP** | modal `#bulk-overlay`: 4 dugmeta, 1 polje |

### Zašto `qiOtvori`/`bulkOtvori` nisu obrisani

Ovo je razlog zbog kog Faza 2 nije nazvana „REMOVE sprint".

Dugmad su `<button …></button>` — **bez teksta**, `style="display:none;"`, i
**ništa u `vindex.js` ih nikad ne otkriva** (2 pojave ukupno, obe u `index.html`).
Po svakom površnom kriterijumu izgledaju mrtvo.

Ali iza njih stoje **potpuno implementirani i ispravni modali**. To je **mrtva
ulazna tačka, ne mrtva funkcija.** Brisanje bi uklonilo radeću funkcionalnost
(brzo kreiranje predmeta i uvoz iz CSV-a) i predstavljalo bi to kao čišćenje
koda.

Test `test_keep_funkcija_i_njen_modal_su_ocuvani` sada to **zaključava**;
mutacija koja briše `qiOtvori` obara test.

## DOM reference — 31 mrtva, po grupama

### Grupa A — ostaci obrisane landing stranice → **REMOVE (kod), odloženo**

23 reference. `landing.html` je obrisan u Website sprintu (`f1865d4b`), ali su
njegove init rutine ostale u `vindex.js`.

| ID-jevi | Vlasnik | Runtime | Verdict |
|---|---|---|---|
| `hero`, `nav`, `ni`, `tog` | `<TOP-LEVEL>`, `focusInput`, `toggleAnnual` | traži se, uvek `null` | REMOVE |
| `p1`, `p2`, `pp1`, `pp2` | `_setPrices` | traži se, uvek `null` | REMOVE |
| `demo`, `demoConf`, `demoTxt` | `<TOP-LEVEL>` (demo typewriter) | 1 od 3 traženo | REMOVE |
| `hamburger`, `mobile-menu` | `toggleMenu` | nikad | REMOVE |
| `sphereCanvas`, `sphereWrap`, `para-canvas` | `<TOP-LEVEL>` (pozadinske animacije) | delimično | REMOVE |
| `srp-content`, `srp-typing` | `<TOP-LEVEL>` | traži se, uvek `null` | REMOVE |
| `modBody`, `modLabel`, `modShowcase`, `modTabs` | `<TOP-LEVEL>` | 1 od 4 | REMOVE |
| `vx-topbar-settings-btn` | `<TOP-LEVEL>` | 2×, uvek `null` | REMOVE |
| `aic3-btn`, `aic3-q`, `aic3-result` | `aic3_submit` (nedostižna) | nikad | REMOVE |

Svi imaju **nula dostižnosti do `index.html`** i nula pojava kao niska.

**Nisu uklonjeni u ovom sprintu — i to je namerno.** Brisanje 23 reference znači
uklanjanje ~8 funkcija i nekoliko blokova koda na najvišem nivou. Posle
`kalendarLoad` incidenta — gde je uklanjanje „zasenčenog mrtvog koda" ostavilo
red koji ga čita i oborilo 9.469 redova — takva operacija zaslužuje sopstveni
prolaz sa mutacijom po funkciji. **UNRESOLVED-1.**

### Grupa B — živa putanja, nedostaje element → **REWIRE**

| ID | Vlasnik | Dostižnost | Verdict | Ishod |
|---|---|---|---|---|
| `pred-pane-ccc` | `pred_print` | ✓ `index.html:769` „Štampaj" | **REWIRE — URAĐENO** | cilj → `#pred-pane-pregled` |
| `pred-novi-btn` | `analizaSacuvajUPredmet` | ✓ `index.html` | **UNRESOLVED-2** | oba rezervna selektora pogađaju **0** elemenata |
| `tip-podneska` | `voice_doAction` ← `voice_execute` ← `voice_start` | ✓ preko glasa | **UNRESOLVED-3** | traži proizvodnu odluku o glasovnom toku |

### Grupa C — nedostižna funkcija

| ID | Vlasnik | Verdict |
|---|---|---|
| `pred-cinjenice` | `pred_submitProcena` (0 pozivalaca) | REMOVE, uz Grupu A |
| `tab-n` | referenca u `analizaGenerisiNacrt` | **UNRESOLVED-4** — PRO-gejtovan tab `n` je uklonjen iz DOM-a, ali `setTab` ga i dalje pominje |

---

# ŠTA JE IZVRŠENO

## REMOVE — ostrvo `pred_openNewModal`

Uklonjeni `pred_openNewModal`, `pred_closeNewModal`, `pred_kreiraj` i modal
`#pred-new-modal` (`index.html` 384-416) sa 5 ID-jeva.

Dokaz zatvorenosti ostrva — **ništa spolja nije doticalo nijedan deo**:

```
pred_openNewModal    index.html: 0   vindex.js: 0   kao niska: 0
pred_closeNewModal   pozivan iskljucivo iz samog modala
pred_kreiraj         pozivan iskljucivo iz samog modala
runtime              nikad pozvan tokom prolaza kroz 12 tabova,
                     12 podtabova i 9 modala
```

Funkcionalno je bio i zastareo: slao je na `POST /api/predmeti` **bez** vezivanja
klijenta, roka i dokumenata — posao koji Intake čarobnjak radi kompletno.

Posle uklanjanja: `node --check` prolazi, **nula JS grešaka pri učitavanju**,
nula preostalih poziva ka uklonjenim imenima (provereno nad izvorom **bez
komentara** — inače obrazloženje uklanjanja izgleda kao kod).

## REWIRE — „Štampaj" više ne štampa prazan papir

`pred_print()` je sakrivao sve panele, pa pokušavao da otkrije `#pred-pane-ccc`.
Kontejner ne postoji, `if (ccc)` je preskočio otkrivanje, i `window.print()` je
štampao stranicu na kojoj je **sve sakriveno**.

**Naslednik nije biran procenom — deklarisan je u samom kodu:**

```javascript
// pred_subtabSwitch, vindex.js:10367
var _legacyMap = { ccc:'pregled', 'ai-analiza':'agenti', dokazi:'agenti', timeline:'rokovi' };
```

Cilj je `#pred-pane-pregled`. Test čita `_legacyMap` i pada ako se mapa promeni
a štampa ne — dakle veza ostaje živa, ne zamrznuta u testu.

---

# MUTACIJE

| Mutacija | Ishod |
|---|---|
| vraćen `#pred-pane-ccc` kao cilj štampe | **3 pala** |
| vraćena funkcija `pred_openNewModal` | **3 pala** |
| **obrisan `qiOtvori`** (lažni REMOVE) | **1 pao** — KEEP brava radi |

Treća je najvažnija: dokazuje da testovi ne samo da čuvaju ono što je uklonjeno,
nego i **sprečavaju brisanje onoga što ne sme da se obriše**.

---

# ISPRAVKA SOPSTVENOG MERENJA

Prva verzija runtime sonde prijavila je da **`setTab('doctpl')` pada** —
`TypeError: Cannot read properties of null`.

Provereno pre nego što je prijavljeno kao nalaz: `#tab-btn-doctpl` ima
`onclick="docTplOpen()"`, a **ne** `setTab(…,'doctpl')`. Poziv koji je pao
aplikacija nikad ne pravi — **izmislila ga je moja sonda.** Klik na stvarno
dugme ne baca ništa.

Sonda je prepravljena da klikće na stvarna dugmad umesto da sintetizuje pozive.
Posle toga: **nula JS grešaka** kroz ceo prolaz.

**Zapažanje koje ostaje** (nije nalaz, nije popravljano): `setTab` na
`vindex.js:2026` radi `document.getElementById('tab-'+t).style.display='block'`
**bez zaštite od `null`**. Danas nijedan živi poziv to ne pogađa. Da pogodi,
izuzetak bi prekinuo `setTab` **posle** skrivanja svih panela — korisnik bi
ostao na praznom ekranu.

---

# UNRESOLVED — ČETIRI, SVE ČEKAJU ODLUKU VLASNIKA

| # | Stavka | Šta je dokazano | Šta nedostaje |
|---|---|---|---|
| **1** | 23 landing reference (Grupa A) | nula dostižnosti, nula pojava kao niska, runtime potvrđuje | odluka da se izvede zaseban prolaz sa mutacijom **po funkciji** — ne masovno brisanje |
| **2** | `analizaSacuvajUPredmet` → `#pred-novi-btn` | dugme živo; `#pred-novi-btn` ne postoji; **oba** rezervna selektora (`[onclick*="predmetNovi"]`, `[onclick*="noviPredmet"]`) pogađaju **0** elemenata ⇒ klik posle prelaska na Predmete ne radi ništa | koje je kanonsko odredište danas — Intake čarobnjak (`intakeOtvori`) ili nešto drugo |
| **3** | `voice_doAction` → `#tip-podneska` | dostižno preko glasa (`voice_start`) | da li glasovni tok „podnesak" i dalje postoji kao proizvod |
| **4** | `tab-n` | PRO-gejtovan tab `n` uklonjen iz DOM-a, `setTab` ga i dalje pominje | da li se tab vraća ili se pominjanje uklanja |

**`qiOtvori` i `bulkOtvori` NISU u ovom spisku** — presuda je jasna (KEEP).
Otvoreno pitanje je samo da li im dati ulaznu tačku, a to ne blokira Fazu 2.

---

# STANJE

```
index.html          −33 reda (modal `#pred-new-modal`)
static/vindex.js    −3 funkcije, 1 REWIRE
static/sw.js        v130 → v131
tests/              +1 fajl (17 testova)

Testovi:  5161 → 5178 passed / 1 skipped / 0 failed
Redosled: no:randomly · seed=11
node --check static/vindex.js  OK
JS greške pri učitavanju       NEMA
```

---

# DEVETO PRAVILO

> **Mrtva ulazna tačka nije mrtva funkcija.**

`qiOtvori` ima nula stvarnih pozivalaca, dugme mu je prazno i trajno skriveno,
runtime ga nikad ne dodirne. Svaki dosadašnji kriterijum bi ga proglasio mrtvim
— a iza njega stoji kompletan, ispravan modal.

Zato presuda mora da razdvoji **dostupnost** od **postojanja funkcionalnosti**.
Prvo je UX pitanje (dati vrata), drugo je pitanje brisanja. Mešanje ta dva je
najbrži način da se obriše nešto što radi.
