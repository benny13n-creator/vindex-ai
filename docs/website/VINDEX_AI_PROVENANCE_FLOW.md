# VINDEX AI — VERIFIKACIJA TOKA POREKLA

Stanje: `922615c1`. Utvrđeno **iz koda**, bez pokretanja aplikacije.

---

## VERDICT

# 🟡 PARTIALLY PROVEN

**Korisnik može da postavi pitanje. Korisnik NE MOŽE da vidi poreklo odgovora.**

Element za prikaz izvora postoji, ali je **mrtav u UI-ju**.

---

## 1. IZVRŠNI NALAZ — dokaz iz tri linije koda

**`index.html:4025`**
```html
<div id="rag-source-info" style="display:none; font-size:.72rem; ..."></div>
```
Element je **prazan** i ima **hardkodovan `display:none`** već u HTML-u.

**`static/vindex.js:918`** → `_si.style.display='none'`
**`static/vindex.js:7538`** → `src.style.display = 'none'`

To su **jedine dve reference** na taj element u celom fajlu od 23.303 linije.

**Nijedno mesto mu ne postavlja sadržaj (`innerHTML`/`textContent`).
Nijedno mesto ne postavlja `display` na bilo šta osim `none`.**

Zaključak: element je **skriven pri rođenju, nikad popunjen, nikad otkriven**.

**STATUS = IMPLEMENTIRANO ALI NIKAD PRIKAZANO** — u praksi mrtav UI.
Isto važi za `rag-confidence-badge`, koji prati isti obrazac.

## 2. TOK PITANJA — postoji

| Korak | Dokaz |
|---|---|
| Korisnik pita | `POST /api/pitanje` (`api.py:2967`), stream varijanta `:3128` |
| Frontend | `static/vindex.js` (elementi `qi`, `aq`, `aitxt`, kontejner odgovora `rb`) |
| Odgovor se prikazuje | kontejner `rb` |

**Dakle: pitanje da, prikaz odgovora da, prikaz izvora ne.**

## 3. ŠTA NIJE VERIFIKOVANO

**Da li `/api/pitanje` u odgovoru vraća polja sa izvorima — UNVERIFIED.**

Nisam stigao da pročitam potpunu šemu odgovora tog endpointa. Ta činjenica menja klasifikaciju:

- Ako **vraća** izvore → `API-AVAILABLE / UI-MISSING` — nedostaje samo prikaz, backend je tu
- Ako **ne vraća** → `NOT PROVEN` — poreklo za AI odgovore ne postoji ni na backendu

**Ovo je sledeći korak, i mali je:** pročitati telo `api.py:2967` do `return`.

## 4. ISPRAVKA RANIJEG NALAZA

**`landing.html` POSTOJI** — 57 KB u korenu repozitorijuma, servira se na `/`
(`api.py:1478`). Moja ranija tvrdnja da marketinška strana ne postoji **bila je netačna**;
gledao sam samo `static/`, a strana je u korenu.

To menja preporuku iz prethodne misije: sajt se **ne gradi od nule** — postoji polazna tačka
koju treba pregledati pre nego što se odluči da li se prepravlja ili zamenjuje.

## 5. IZVODLJIVOST SNIMAKA — danas

| Snimak | Postoji | Korisnik pristupa | Traži sintetičke podatke | Bezbedno za sajt |
|---|---|---|---|---|
| A — strukturisan kontekst | verovatno | verovatno | DA | uz sintetiku |
| B — unos dokumenta | verovatno | verovatno | DA | uz sintetiku |
| **C — odgovor sa vidljivim izvorom** | **NE** | **NE** | — | **NEMOGUĆE DANAS** |
| D — otvaranje izvornog dokumenta | NE (zavisi od C) | NE | — | NEMOGUĆE DANAS |
| E — rok sa izvorom | UNVERIFIED | UNVERIFIED | DA | uz proveru |

## 6. HOD KROZ PROIZVOD

`unos → obrada → kontekst → pitanje → odgovor` — **izvodljivo**.
`→ izvor → izvorni dokument` — **NIJE izvodljivo**, lanac puca na prikazu izvora.

## 7. TRI KATEGORIJE, RAZDVOJENE

| Kategorija | Stanje |
|---|---|
| **Sposobnost proizvoda** | kontekst sa poreklom po polju postoji u `case_context.py` — dokazano |
| **Dostupno korisniku** | pitanje da, odgovor da, **poreklo ne** |
| **Prikazivo na sajtu** | kontekst i unos uz sintetiku; **poreklo ne** |

## 8. POSLEDICA PO SAJT

Centralna teza **„Vindex zna odakle zna"** je **tačna o sistemu** — poreklo postoji u
`case_context` i u `ai_provenance`. Ali **korisnik to danas ne vidi na ekranu**.

Sajt zato:
- **SME** da tvrdi da sistem beleži poreklo — to je odobrena tvrdnja, potkrepljena kodom
- **NE SME** da prikaže snimak ekrana sa vidljivim izvorom — takav ekran ne postoji
- **NE SME** da implicira da korisnik klikom stiže do izvornog dokumenta

**Hero mora ići na dijagram, ne na snimak** — dok se prikaz izvora ne uključi.

## 9. SINTETIČKI FIXTURE

**Nije kreiran.** Bez rešenog prikaza izvora, fixture bi omogućio snimke A i B, ali ne i C —
a C je jedini koji nosi centralnu tezu. Kreiranje fixtura ima smisla **posle** odluke iz
tačke 3.
