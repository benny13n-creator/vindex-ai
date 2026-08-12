# P0 REMEDIATION — IZVEŠTAJ

**Polazno stanje:** `bc55d0c8` · 4989 passed / 1 skipped
**Završno stanje:** 5054 passed / 1 skipped / **0 failed**, deterministički na
redosledima `no:randomly`, `seed=3`, `seed=7`, `seed=11`
**Format:** pre fix → koren → minimalni fix → nov test → mutacija → runtime provera

Šest stavki. Pet ih je bilo naručeno; šesta je nađena pri radu i teža je od svih.

---

# 0. BLOKIRAJUĆA PROVERA PRE IZMENA — `analyze_predmet`

Tražena je pre P0 rada, urađena bez ijedne izmene koda.

```
glasovna komanda „analiziraj"
  → routers/voice.py:308            vraća akciju `analyze_predmet`
  → static/vindex.js:16912          case 'analyze_predmet'
  → static/vindex.js:19508          agent_run()
  → POST /api/agents/run
  → routers/multi_agent.py:394      PermissionService.require("multi_agent")
  → routers/multi_agent.py:662      UsageService.consume(uid, email, "multi_agent")
```

**Ishod: scenario C — 🟢 druga operacija, potpuno gejtovana.**

Nije isti orkestrator kao `stratOrkestratorPokreni`: druga ruta, drugi ključ
funkcije (`multi_agent` vs `strategija`), sopstvena naplata. Glas **ne**
zaobilazi ni dozvolu ni kredite. Trag zatvoren.

---

# P0-0 — `static/vindex.js` JE PUCAO PRI UČITAVANJU

**Nije bio na listi. Nađen je zato što su moji testovi za P0-1 pali iz razloga
koji nisam mogao da objasnim.**

### Pre fix
Čist Chromium, `index.html`, nula stubova:
```
PAGE ERRORS: ['kalendarLoad is not defined']
  _iStep               -> undefined
  _INTAKE_STEP_LABELS  -> undefined
  _genomeDnaCache      -> undefined
  kalendarLoad         -> undefined
```

### Koren
Program Omega, Sprint 005 (2026-08-06) uklonio je `function kalendarLoad()` kao
zasenčen mrtav kod. Definicija je nestala, ali je ostao red koji je taj
identifikator **čitao**:

```javascript
var _kalendarLoad_orig = kalendarLoad;   // vindex.js:14212 → ReferenceError
```

Greška na najvišem nivou skripte zaustavlja izvršavanje **celog ostatka fajla**:
**9.469 od 23.681 reda**. Nikad se nisu izvršile 79 top-level `var` dodela i 4
`addEventListener` registracije. `kalendarLoad` sam nikad nije dobio vrednost,
pa je `vindex.js:2036` (`if (t==='kal') kalendarLoad()`) pucao na svako otvaranje
Kalendara.

**Zašto ga nijedan audit nije video:** deklaracije funkcija se podižu, pa je
posle pada svaka funkcija i dalje *postojala*. Zato su sva tri statička agenta
nezavisno prijavila „0 mrtvih rukovalaca" — i bila u pravu po svojoj definiciji.
Kvar postoji isključivo u izvršavanju.

### Fix
`_kalendarLoad_orig` je bio dodeljen jednom i **nikad pročitan**. Uklonjen;
`kalendarLoad` postao ispravna `var` deklaracija.

### Test · mutacija · provera
`tests/test_p0_script_executes.py` — 6 testova: `pageerror` mora biti prazan;
četiri globala iz donjeg dela fajla moraju biti inicijalizovana (pozitivna
potvrda da je izvršavanje **stiglo** dokle treba, ne samo da nije puklo);
statička brava nad obrascem „čitaj pa zameni".
**Mutacija: 6/6 pada.** Runtime: `PAGE ERRORS: NEMA`.

---

# P0-1 — ADVOKAT NIJE VIDEO DA MU ORIGINAL NIJE SAČUVAN

### Pre fix
`#pred-procena-result`: **0 pojava** u `index.html`, **2** u `vindex.js`
(`:20048`, `:20148`). Uklonjen u `010082aa` zajedno sa panelom
`#pred-pane-ai-analiza`; `pred_upload_doc()` je nastavio da piše u njega, a
`if (resEl)` je sve gutao bez ijedne poruke.

Ceo lanac potvrđen s kraja na kraj:
```
POST /api/predmeti/{id}/upload  (api.py:4859)
  → "original_preserved": bool(_original_storage_path)   (api.py:5608)
  → vindex.js:20110  if (d.original_preserved === false) → warnHtml
  → vindex.js:20124  if (resEl) resEl.innerHTML = …      → resEl === null
  → korisnik vidi POTPUN USPEH
```

Tiho su nestajali: AI procena dokumenta, sve poruke o grešci, kartica za
auto-povezivanje, i **⚠ „Originalni fajl nije sačuvan u trezoru"** — nalaz
**F7/F20 iz Final Beta Gate-a**, napisan, merge-ovan i nikad prikaziv.

### Zašto ga postojeći test nije uhvatio
`tests/test_iron_lawyer_frontend_fixes.py:245`:
```python
assert "if (d.original_preserved === false) {" in VINDEX_JS
```
Niska u izvoru. Prolazila je sve vreme dok je funkcija bila nedostupna.

### Fix
Kontejner vraćen — ali **ne** u stari panel, nego u `#pred-pane-dokumenti`,
odmah ispod `#pred-upload-error`. Zona, učitavanje i greška su tri preostala
brata ovog toka i korisnik posle uploada gleda upravo u njih.

### Test · mutacija · provera
`tests/test_p0_upload_disclosure.py` — 5 testova. Pravi Chromium, pravi
`index.html`, prava `pred_upload_doc()`, do panela se ide **aplikacijinom
navigacijom** (`updateAuthUI` → `setTab` → `pred_subtabSwitch`), a meri se
`innerText` — dakle tekst stvarno iscrtan na ekranu.

| Provereno | Ishod |
|---|---|
| `original_preserved: false` → upozorenje na ekranu | ✓ vidljivo, `offsetParent ≠ null`, visina > 0 |
| `original_preserved: true` → nema lažnog upozorenja | ✓ i kontejner **nije prazan** (inače „nema upozorenja" ne dokazuje ništa) |
| AI procena dokumenta stiže do ekrana | ✓ |
| negativna kontrola: kontejner uklonjen u toku testa | ✓ merenje prestaje da vidi upozorenje |

**Mutacija (kontejner uklonjen iz `index.html`): 4/5 pada.** Peti je negativna
kontrola koja i sama uklanja kontejner — očekivano prolazi.

---

# P0-2 — `#feedback-fab` NEDOSTUPAN NA SVIM ŠIRINAMA

### Pre fix
49/49 tačaka blokirano na svih 7 merenih širina. Na desktopu ga je pokrivao
`#vx-voice-fab` (z **9990** vs **7000**), na mobilnom `#vx-mobile-nav` (z 9999).

### Koren — dva sloja, oba moja iz Dashboard Polish sprinta

**1. Pozicija je stajala INLINE u `index.html:214`**, pa je nijedna provera koja
gleda `static/vindex.css` nije mogla videti. Komentar koji sam tada ostavio
(`vindex.css:3625`) tvrdi da je desni ugao slobodan „provereno u ovom fajlu" —
provera je bila iskrena i slepa.

Gore od toga: `id` i `style` su bili u **različitim redovima**, pa ga ni pretraga
`index.html` po redu nije nalazila. Popis `position:fixed` elemenata koji sam
pokrenuo na početku ovog sprinta ga je iz tog razloga propustio.

**2. `@media (max-width: 768px)` je zadržao `left: 18px`.** Kad su zadati i
`left` i `right` uz fiksnu širinu, **`left` pobeđuje** — pa je na telefonu i
dalje važila stara pozicija. Moj tadašnji test je tvrdio `"right" in blok` i
prolazio nad deklaracijom koja ne odlučuje.

### Fix
Sve pozicije plutajućih dugmadi izmeštene u **jedan blok** u `static/vindex.css`,
sa zabranom vraćanja pozicionih osobina u inline stil. Niz složen vertikalno,
svaka širina ostavlja mobilnu navigaciju slobodnom.

**Ispravka u toku rada:** prva verzija je oba dugmeta prebacila desno i napravila
**nov** sudar sa `#vx-mobile-fab` („Novi predmet", `bottom:76px; right:18px`).
Invariant je to prijavio odmah (`#vx-voice-fab` 0% jezgra). Ispostavilo se da
`left` na mobilnom **nije bio zaostatak nego namera** — leva strana je vraćena,
promenjen je samo odmak odozdo.

### Nov invariant, ne nova koordinata
`tests/test_p0_hit_area_invariant.py` — **41 test**. Ne čita nijedan CSS.
Za svaku vidljivu kontrolu uzima `getBoundingClientRect()` i preko
`document.elementFromPoint` pita **ko stvarno prima klik**, na 9 širina
(1920/1440/1366/1280/1024/768/412/390/375).

Mere se dve stvari, jer jedan broj ne izražava obe polovine pravila:
* **jezgro** — središnjih 70% pravougaonika; tu ništa ne sme presretati klik.
  (70% jer kod okruglog dugmeta uglovi pravougaonika padaju van oblika — prva
  verzija je zbog toga prijavljivala lažnih 6%.)
* **pun pravougaonik** — služi samo da uhvati potpuno izgubljenu kontrolu.

Beleži se i **da li je presretač i sam interaktivan** — „preklopio ga je
kontejner" i „pojelo ga je drugo dugme" nisu isti nalaz.

**Mutacija (`#feedback-fab` vraćen na `bottom:18px`): 10 testova pada.**

---

# P0-3 — ČAROBNJAK NOVI PREDMET NEUPOTREBLJIV NA TELEFONU

### Pre fix
`#intake-btn-next` `[23, 786, 345, 44]` ceo ispod `#vx-mobile-nav`
`[0, 784, 390, 60]`. Panel z **2101**, navigacija z **9999**. Na 390px se
čarobnjak nije mogao odvesti dalje od koraka 1.

### Koren
Aplikacija **već ima** konvenciju „modal iznad trake" — `#mob-more-sheet` 10001,
`#dok-preview-overlay` 10001. Intake je bio jedini izuzetak, na 2100/2101.

### Fix
`.intake-overlay` → 10004, `.intake-panel` → 10005 (iznad navigacije 9999,
ispod glasovnog modala 10010). `#intake-tpl-overlay` podignut 10000 → 10006 jer
se otvara **iz** čarobnjaka i mora ostati iznad njegovog panela.

### Test · mutacija
Provereno na **375 / 390 / 412 / 768 / 1366 / 1920**, kako je traženo: dugme
vidljivo, 100% jezgra prima klik, i **zasebno** — panel je z-index iznad
navigacije (uzrok, ne posledica).
**Mutacija (z-index vraćen na 2100/2101): 8 testova pada.**

### Uz put popravljeno — isti razred, nađen invariantom
`.vx-panels-wrap > div` je imao donji odmak **10px** uz traku od **60px**, pa je
svaka kontrola na dnu pane-a završavala ispod trake. Izmereno na 390px:
`#exec-btn` („Pretraži pravnu bazu", 233×44) primao je **0 od 49** tačaka klika.
Uzrok: `padding-bottom: 68px !important` iz bloka za 768px poništava kasniji
`padding: 0 !important` u bloku za 640px.

---

# P0-4 — GLAVNA NAVIGACIJA NEDOSTUPNA TASTATUROM

### Pre fix
15 stavki, sve `<div class="t-tab" onclick=…>` bez `role` i `tabindex`.
`grep -c tabindex index.html` = **0**. 60 pritisaka `Tab` → **0** zaustavljanja.
Korisnik bez miša nije mogao da pređe ni na jedan ekran.

### Fix — postojeći obrazac, ne nova arhitektura
Primenjen obrazac koji već stoji u istom fajlu na `index.html:1163`
(`role="tablist"` / `role="tab"` / `aria-selected`):

1. `role="tab"`, `tabindex="0"`, `aria-selected` na svih 15; kontejner
   `role="tablist"`
2. `setTab()` održava `aria-selected` (inače čitač ekrana izgovara tab koji više
   nije otvoren)
3. **delegirani `keydown`** — `<div tabindex="0">` prima fokus ali **ne**
   aktivira `onclick` na `Enter`/`Space`; to radi samo `<button>`. Bez ovoga bi
   „dodali smo tabindex" bila tačna izjava i nedovoljna popravka. `Space` se
   sprečava u `keydown` da stranica ne odskroluje.
4. `.t-tab:focus-visible` sa `!important` na kraju fajla — jer `.t-tab` nosi
   `outline: none !important` iz vremena kad tabovi nisu ni bili fokusabilni.
   To je bila **zamka**: čim dobiju `tabindex`, primaju fokus bez ikakvog traga.

Tabovi **nisu** pretvoreni u `<button>`: `.t-tab` nosi 6 CSS pravila sa
`!important` pisanih za `div`, pa bi promena oznake bila veći zahvat od same
pristupačnosti.

### Test · mutacija
`tests/test_p0_keyboard_nav.py` — 9 testova: `Tab` stiže do svake stavke ·
`Shift+Tab` vraća · `Enter` i `Space` **stvarno otvaraju ekran** (meri se da je
panel prikazan, ne da je rukovalac pozvan) · `Space` ne skroluje · fokusiran tab
ima izračunat `outline ≠ none` pod stvarnim `:focus-visible` · `role`/
`aria-selected` prate otvoren ekran · kontejner je `tablist`.

**Tri odvojene mutacije, jer popravka ima tri dela:**

| Mutacija | Pada |
|---|---|
| uklonjen `tabindex` | 5 |
| uklonjen `keydown` rukovalac | 3 |
| uklonjen `:focus-visible` prsten | 1 |

---

# P0-5 — `/generiši` vs `/generisi`

### Pre fix
`vindex.js` je slao `POST /api/evidence-graph/generi%C5%A1i`; backend sluša
`/generisi` (`evidence_graph.py:178`). Zahtev je padao na `GET /{predmet_id}` →
**405**. Oba dugmeta za graf dokaza mrtva.

### Šta je provereno pre izmene
* **Kanonska ruta:** `/generisi`. U `evidence_graph.py` postoje tačno tri rute i
  nijedna nema dijakritiku.
* **Drugi pozivaoci:** dva mesta zovu evidence-graph; drugo (`GET`) je ispravno.
* **Je li jedini pokvaren `fetch`:** da, jedan od 303.
* **Ima li sistemske greške u kodiranju:** ne u frontendu. Od 618 ruta **tačno
  jedna** sadrži naše slovo — `/api/ugovor-zastupanja/generiši`
  (`ugovor_zastupanja.py:283`). Dva susedna modula donela su **suprotnu odluku**
  o dijakritici; frontend je oba pozvao istim oblikom i tačno jedan promašio.

### Fix
Frontend usklađen sa kanonskom rutom. `ugovor-zastupanja` **nije diran** — radi,
i menjanje žive rute je veći rizik od nesklada.

### Test klase, ne slučaja
`tests/test_p0_frontend_routes.py` — iz `vindex.js` se vade **sve** nepromenljive
`fetch` putanje i porede sa stvarnom tabelom ruta FastAPI aplikacije.

Dva puta sam morao da popravim **merenje**, ne kod:
* prva verzija je hvatala statičke prefikse dinamičkih URL-ova
  (`'/api/zadaci/' + id`) i prijavila **47 lažnih** nepostojećih ruta;
* poređenje je moralo da ide nad **dekodiranim** oblikom, jer su `%C5%A1` i `š`
  ista putanja.

Uključena je i negativna kontrola nad samim vađenjem (ako se obrazac pokvari,
ostali testovi bi „prošli" nad praznim skupom).

**Mutacija (vraćen `%C5%A1`): 2 testa padaju.**

---

# ŠTA JE NAĐENO USPUT, A NIJE POPRAVLJENO

## P0F-001 — `#mic-qi` prekriven dugmetom „Novi predmet"

`#vx-mobile-fab` pluta preko mikrofona za diktiranje u polju za pravni upit:
na **375px potpuno**, na 390px 48%. Dodir namenjen diktatu pokreće kreiranje
predmeta.

**Nije popravljeno** jer popravka traži pomeranje mobilnog FAB-a ili prelom
polja za upit — dakle izmenu mobilnog rasporeda, ne jednu poziciju. To je izvan
pet naručenih stavki i izvan pravila „minimalni patch".

**Nije ni prećutano.** Upisan je u `_EVIDENTIRANI_KVAROVI` u
`tests/test_p0_hit_area_invariant.py`, uz dve brave koje sprečavaju da zapis
postane tiho gašenje testa:
* `test_evidentirani_kvarovi_se_i_dalje_reprodukuju` — kvar **mora** i dalje da
  postoji; čim ga neko popravi, test pada i tera brisanje zapisa;
* `test_evidencija_je_kratka_i_obrazlozena` — najviše 3 stavke, svaka sa
  obrazloženjem.

Opšti invariant izuzima **isključivo** taj jedan `id`; svaka nova kontrola u
istom stanju i dalje obara test.

---

# ZATEČENI KVAR IZOLACIJE TESTOVA

Pod `seed=11` je pao `test_case_dna_events.py::test_emit_genome_event_…`
(`assert 6 == 36`, vrednost `'corr-9'`). **Sam prolazi.**

Koren: `shared/ai_provenance.py` drži `_request_ctx`/`_case_ctx` kao
`ContextVar`-ove koje `set_request_context()` postavlja **bez vraćanja** — što je
namerno u produkciji (svaki HTTP zahtev ima svoj kontekst), ali u testovima svi
dele isti kontekst procesa. `conftest.py` to nije čistio.

Moje izmene ne diraju nijedan backend fajl (`git diff --stat HEAD -- shared/
routers/ api.py` je prazan). Novi testovi su samo promenili raspored i **otkrili**
curenje koje je već postojalo.

Rešen razred, ne slučaj: autouse `_izolovan_ai_kontekst` u `tests/conftest.py`,
po uzoru na postojeći `_izolovan_rate_limiter` iz Wave 11.

---

# DVA TESTA ISPRAVLJENA, NIJEDAN OSLABLJEN

| Test | Bio | Sada |
|---|---|---|
| `test_iron_lawyer_frontend_fixes.py::test_portfolio_kancelarije_nav_gated_to_founders` | tražio `id="tab-btn-pi-nav" style="display:none;"` kao **jednu nisku** — dakle atribute jedan do drugog; pao kad je P0-4 između njih ubacio `role`/`tabindex` | traži **svojstvo**: oznaka tog taba mora nositi `display:none` |
| `test_dashboard_polish.py::test_voice_dugme_ostaje_dostupno_na_uskim_ekranima` | `assert "right" in blok` — prolazilo i za `right: auto`, i prolazilo dok je isti selektor u drugom bloku držao `left: 18px` | traži `bottom ≥ 60px` (visina donje trake); poruka više ne tvrdi da dugme „treba desno" — na mobilnom je levo namerno |

Obe ispravke su **mutacijom potvrđene** da i dalje hvataju svoj izvorni kvar.

---

# STANJE

```
index.html         +18 redova   (kontejner rezultata, ARIA na 15 tabova, z-index)
static/vindex.js   +38 redova   (P0-0 fix, aria-selected, keydown, ruta)
static/vindex.css  +64 reda     (niz FAB-ova, intake z-index, focus-visible, odmak)
static/sw.js       v126 → v127
tests/             +4 nova fajla (61 test), 1 nov fixture, 2 ispravljena testa

Testovi:  4989 → 5054 passed / 1 skipped / 0 failed
Redosled: no:randomly · seed=3 · seed=7 · seed=11  — sva četiri zelena
Worktree: CLEAN
```

**REMOVE lista je i dalje zaključana.** `pred_openNewModal`, `qiOtvori`,
`bulkOtvori` i 31 mrtav DOM ID nisu dirnuti — čekaju traženu forenziku
`dead ID → referenca → runtime → dinamička injekcija → odredište → presuda`.

---

# ŠTA OVAJ SPRINT KAŽE

Šest kvarova, jedan oblik: **ugovor između dva sloja promenjen s jedne strane,
druga strana nije ni pukla ni prijavila.**

Vlasnikova nova definicija je se pokazala tačnom na najskuplji način. „Nula
mrtvih dugmadi" je bilo tačno po definiciji „`onclick` pokazuje na postojeću
funkciju" — i istovremeno je `vindex.js` pucao pri učitavanju, gaseći 9.469
redova, a tri nezavisna agenta to nisu videla jer se **deklaracije funkcija
podižu**. Kvar koji izgleda kao uspeh je skuplji od kvara koji baci grešku.

Tri predložene CI kapije iz `CANONICAL_INVENTORY.md` §7 sada postoje kao testovi:
`getElementById` ↔ DOM · `fetch` ↔ tabela ruta · geometrija svih fiksnih slojeva
odjednom. Četvrtu je dodao ovaj sprint: **stranica ne sme da baci nijednu JS
grešku pri učitavanju.**
