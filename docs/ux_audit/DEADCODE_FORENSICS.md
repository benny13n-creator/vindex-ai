# DEAD-CODE FORENSICS

**Polazno:** `f6ace9f7` · 5195 passed
**Završno:** **5208 passed / 1 skipped / 0 failed**, `no:randomly` i `seed=11`
**Mandat:** samo pronaći i dokazati mrtav kod. Nula refaktora, nula optimizacije,
nula arhitektonskih izmena. **`F2-001` nije dirnut.**

---

# ZBIRNO

```
Pregledano     816 funkcija · 1.029 HTML ID-jeva · 1.664 CSS klasa
REMOVE          2   (dokaz na sva četiri nivoa + mutacija)
KEEP            7   (2 lažno mrtva + 5 funkcija bez vrata)
DEFER          18   (13 → nov zapis F2-002; 5 → postojeći F2-001)
Ne-kategorija  62 HTML ID-jeva + 426 CSS klasa — v. §5
```

**Detektor je na 22 provere dao 2 lažna pozitiva.** Oba bi bila regresija.
To je najvredniji rezultat prolaza — vredniji od dva uklonjena reda.

---

# 1. REMOVE — dokaz na sva četiri nivoa

| Kandidat | Static | DOM | Runtime | Mutacija | Verdict |
|---|---|---|---|---|---|
| `_analizaSwitchTab` | 0 poziva, 0 niski, 0 `window[]` | 0 u `index.html` | nikad pozvana | vraćanje → **2 pala** | **REMOVE** |
| `docTplGetAktivniIdx` | 1 pojava imena u repou (sopstvena definicija) | 0 | nikad pozvana | isto | **REMOVE** |

`_analizaSwitchTab` je tražila `.t-tab` čiji `onclick` sadrži `'n'`/`'t'`. Ti
tabovi su zamenjeni sistemom modova; njena poslednja dva pozivaoca prevedena su
na `openAITool()` u Fazi 2.1 — **ovaj prolaz je uklonio ono što je prethodni
osirotio**.

`docTplGetAktivniIdx` je trolinijski getter bez korisničke semantike.

Posle uklanjanja: `node --check` prolazi, **nula JS grešaka pri učitavanju**,
nula preostalih referenci (provereno nad izvorom **bez komentara**),
`analizaGenerisiNacrt` i `docTplIzaberi` i dalje postoje.

---

# 2. KEEP — dva lažno mrtva kandidata

Ovo je razlog zbog kog `grep` ne sme da bude poslednja reč.

## `crmPokreniKonfliktNovi` — dostupna pod DRUGIM imenom

```javascript
vindex.js:19455   window.crmPokreniKonflikt = crmPokreniKonfliktNovi;
index.html:2092   crmPokreniKonflikt()
```

Nula poziva pod sopstvenim imenom. Detektor koji traži ime funkcije ovo ne vidi.
Brisanje bi uklonilo **proveru sukoba interesa**.

## `_sud_dropdown_hide` — prosleđuje se, ne poziva

```
index.html:3024   setTimeout(_sud_dropdown_hide, 200)
```

Provera koja traži `ime(` ovo ne vidi. Provera koja traži samo ime — vidi.
Zato detektor mora meriti **oba oblika**.

---

# 3. KEEP — pet funkcija bez vrata (Pravilo 9)

Nemaju nijednog pozivaoca — ali su **kompletne korisničke funkcije**, ne
pomoćni kod:

| Funkcija | Šta je | Dokaz da nije ljuska |
|---|---|---|
| `crmObrisi` | brisanje klijenta | **zove API** (`fetch`) |
| `crmUredi` | izmena klijenta | **zove API**, puni 11 polja |
| `copyToMarkdown` | kopiranje analize kao Markdown | 33 reda, javlja korisniku |
| `sazimiZaKlijenta` | sažetak za klijenta | 26 redova, javlja korisniku |
| `aicOtvoriPredmet` | otvaranje predmeta iz AI konteksta | javlja korisniku |

**Brisanje bi uklonilo sposobnost i predstavilo to kao čišćenje koda.**
Da im se daju vrata je proizvodna odluka — ne odluka o brisanju.

Zaključano testom; mutacija koja briše `crmUredi` obara ga.

---

# 4. DEFER

## F2-002 (nov zapis) — 13 pomoćnih funkcija bez pozivaoca

`_applyPismo` · `_sud_clear` · `_vx2_stub_start` · `_vxPdIsLocked` ·
`checkTrialStatus` · `copyZakljucak` · `pred_exportHronologija` · `showIzvor` ·
`tabsScroll` · `vxChartLine` · `vxFieldClearError` · `vxFieldSetError`

**Zašto nisu uklonjene:** kod svake postoji čitanje po kom bi mogla biti
*izgubljena sposobnost*, a ne pomoćni kod — `checkTrialStatus` osvežava značku
probnog perioda, `_vxPdIsLocked` je predikat sistema postepenog otkrivanja,
`_vx2_stub_start` je 124 reda alternativnog prikaza kontrolne table.

Pravilo koje je važilo u ovom prolazu: **ako nema dovoljno dokaza → KEEP, ne
nagađati.** Da su uklonjene, to bi bila procena, ne dokaz.

## F2-001 (postojeći) — 5 funkcija se NE dira

`toggleMenu` · `focusInput` · `toggleAnnual` · `aic3_submit` ·
`pred_submitProcena`

Drže 23 landing reference iz `F2-001`. Detektor ih je prijavio, i **izričito su
izuzete** da ovaj prolaz ne bi „usput" preinačio odloženi zapis sa sopstvenim
uslovom zatvaranja.

---

# 5. DVE KATEGORIJE KOJE NISU DEAD-CODE

## 62 HTML ID-ja bez reference u JS-u i CSS-u

**Nije mrtav kod.** Dugme sa `onclick` je potpuno živo i kad mu `id` niko ne
čita — `id` je tu kao oznaka. Uklanjanje `id`-a je kozmetika sa nenultim rizikom
(test, `aria-labelledby`, selektor u budućem kodu) i **nula koristi za
korisnika**.

Prijavljeno kao nalaz merenja, ne kao kandidat za brisanje.

## 426 CSS klasa bez pojave u HTML-u/JS-u

Isti razred problema kao ID-jevi, plus dodatni slepi ugao: klase se sastavljaju
(`'aic3-' + tip`). Bez dokaza za svaku pojedinačno, ovo je spisak sumnji, ne
spisak mrtvog koda.

---

# 6. DETEKTOR JE MORAO DA SE POPRAVI TRI PUTA

Zapisano jer je poučnije od rezultata.

| Greška detektora | Posledica | Ispravka |
|---|---|---|
| brojao **komentare** kao kod | `#onboard-overlay` prijavljen kao živ, iako postoji samo u komentaru o svom uklanjanju | komentari se uklanjaju pre svake analize |
| nije video **sastavljene ID-jeve** (`'crm-pane-' + tab`) | 148 lažnih kandidata | prepoznavanje prefiksa → 148 → 63 |
| tražio samo `ime(` | promašio alias i prosleđivanje kao referencu | meri se i ime **bez zagrada** |

Peti put u ovom repou da provera izmeri komentar umesto koda. Ovog puta ju je
napravio detektor mrtvog koda — alat čija je jedina svrha da ne pogreši u tome.

---

# 7. USPUT NAĐEN FLAKY TEST — I POPRAVLJEN

Puna regresija je pala na
`test_product_intelligence.py::test_overview_dau_counts_todays_users`. Sam
prolazi.

Uzrok: `TODAY` se računa **pri importu** modula, a
`routers/product_intelligence.py:199` računa `date.today()` **u trenutku poziva**.
Puna regresija traje ~8 minuta; prolaz je počeo 2026-08-12 a završio se
2026-08-13, pa je test dobio događaje datirane „juče" i očekivao da se broje
kao današnji.

**Nije posledica ovog prolaza** — moje izmene ne diraju nijedan backend fajl
(`git diff --stat HEAD -- routers/ shared/ api.py` prazan). Ali flaky test ruši
verodostojnost celog zelenog stanja, pa je vreme zamrznuto za ceo modul: obe
strane sada koriste isti dan.

---

# 8. STANJE

```
static/vindex.js   −2 funkcije (7 redova koda, zamenjeno obrazlozenjem)
static/sw.js       v132 → v133
tests/             +1 fajl (13 testova), 1 test ucinjen deterministicnim

Testovi:  5195 → 5208 passed / 1 skipped / 0 failed
Redosled: no:randomly · seed=11
node --check       OK
JS greske          NEMA
```

Funkcija bez ijednog pozivaoca: **27 → 25** (prag u testu je izmerena vrednost).

---

# JEDANAESTO PRAVILO

> **Detektor mrtvog koda mora prvo da dokaže da nije slep.**

Na 22 provere dao je 2 lažna pozitiva — alias pod drugim imenom i referencu bez
zagrada. Da je izlaz uzet zdravo za gotovo, obrisali bismo proveru sukoba
interesa.

Zato svaki takav alat mora imati **negativnu kontrolu nad sobom**: uzmi nekoliko
funkcija za koje se ZNA da su žive i proveri da ih ne prijavljuje. Ako ih
prijavi, izlaz se ne čita — popravlja se alat.
