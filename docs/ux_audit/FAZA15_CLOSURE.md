# FAZA 1.5 — INTERACTION CLOSURE

**Polazno:** `45e45edb` · 5144 passed
**Završno:** **5161 passed / 1 skipped / 0 failed**, `no:randomly` i `seed=11`

Od sada nijedan nalaz nije „zatvoren" bez pune matrice. Reč *zatvoreno* znači
tačno ovo i ništa manje:

```
reprodukcija pre → popravka → granični uslovi → mutacija → regresija → runtime
```

---

# CLOSURE MATRIX

| | R-001 | R-002 | R-003 | R-004 |
|---|---|---|---|---|
| **Nalaz** | „Pomoć & podrška" bez ijednog rukovaoca | „Otpremi dokument" nedostupno tastaturom | polje za upit bez pristupačnog imena | potvrda uspeha bez ishoda |
| **Reprodukcija pre** | `onclick` = ∅, slušalac = ∅ (6 pogodaka u repou, svih 6 CSS) | `<div onclick>` bez `role`/`tabindex`; 0 zaustavljanja `Tab`-om | `#qi` samo `placeholder`; ime u ARIA stablu prazno | `getSupabase()` → `null` ⇒ upis preskočen, poruka „✓ Prijavljeno" ipak prikazana |
| **Popravka** | vezano za **postojeće** odredište `#pomoc-section` | `role="button"` + `tabindex="0"` + ime | `for="qi"` na **postojeću vidljivu** labelu | uspeh uslovljen stvarnim upisom |
| **Granični uslovi** | miš · `Enter` · ime u ARIA stablu · odredište iscrtano | `Enter` · `Space` · miš · tačno **jednom** | ime iz ARIA stabla, ne atributa; bez dvostrukog izvora | nema klijenta · baza odbila upis · dve nezavisne prijave · bez JS grešaka |
| **Mutacija** | uklonjen `onclick` → **3 pala** | uklonjeni `role`/`tabindex` → **4 pala** | uklonjen `for` → **2 pala** | vraćena bezuslovna potvrda → **3 pala** |
| **Regresija** | 5161 / 0 failed | 5161 / 0 failed | 5161 / 0 failed | 5161 / 0 failed |
| **Runtime** | ✓ klik i `Enter` otvaraju Podešavanja + sekciju | ✓ izbor fajla otvoren tačno jednom | ✓ ARIA ime = „Vaše pravno pitanje:" | ✓ upis u `reported_errors` sa sva 4 polja |
| **Status** | **CLOSED** | **CLOSED** | **CLOSED** | **CLOSED** |

---

# R-001 — VEZANO, NE IZMIŠLJENO

Nova funkcija podrške **nije napravljena**. Kanonsko odredište je već postojalo:

```
#pomoc-section   (index.html:3746, unutar Podešavanja)
  ├── FAQ            → pomocFaqToggle()
  └── forma podrške  → pomocPosalji() → POST /api/support/poruka
```

Do njega **nije vodila nijedna kontrola** — moglo se stići samo ručnim
otvaranjem Podešavanja i skrolovanjem. Sidebar sada vodi tačno tamo:
`setTab(settings)` pa `scrollIntoView` na sekciju.

Nula novih ruta, nula novih tabela, nula nove terminologije.

**Zašto nije bila opcija ostaviti je mrtvu:** CSS joj je davao `cursor:pointer`
i hover. To je lažna affordance — kontrola koja izgleda živa a ne radi ništa uči
korisnika da dugmad u ovoj aplikaciji ne rade.

---

# R-002 — I OTKRIVEN DUPLIKAT U MOJOJ SOPSTVENOJ POPRAVCI

Zona za otpremanje je dobila `role="button"`, `tabindex="0"` i pristupačno ime.

**Ali test je odmah pao — i to je najvredniji trenutak ovog sprinta.**

Test ne pita „da li se izbor fajla otvorio" nego **koliko puta**. Odgovor je bio
**dva**.

Uzrok: u Fazi 1.5 sam napisao generički aktivator za `[role="button"], [role="tab"]`
— a `vindex.js:483` **već** ima aktivator za `[role="button"][tabindex]`, iz
Iron Lawyer sprinta. Dva rukovaoca, dva klika, dva otvaranja izbora fajla.

Provereno da nije reč o pregledaču: čist `<div role="button" tabindex="0">` na
praznoj stranici, bez našeg koda, daje **0** klikova na `Enter` i `Space`.
Chromium ih ne aktivira sam. Dupliranje je bilo isključivo naše.

Popravka: moj rukovalac je sužen na **`role="tab"`** — jedino što postojeći ne
pokriva (glavna navigacija iz P0-4). Za sve što se predstavlja kao dugme
dovoljno je dodati `role` i `tabindex`; aktivacija već postoji.

> Pravilo 3 kaže da `onclick` nije dokaz da interakcija radi.
> Ovo dodaje: **ni „radi" nije dovoljno — mora da radi tačno jednom.**

---

# R-003 — POSTOJEĆA LABELA, BEZ DUPLIRANJA

Iznad polja već stoji vidljivo `Vaše pravno pitanje:`. Dodato je `for="qi"` —
ista labela je sada i programska.

Namerno **nije** dodat `aria-label`: dva izvora imena za istu kontrolu znače da
čitač ekrana izgovara jedno, a korisnik vidi drugo. Test to izričito zabranjuje.

Merenje ide kroz **ARIA stablo** (`Locator.aria_snapshot()`), ne kroz atribute.
`page.accessibility` u ovoj verziji Playwright-a ne postoji; `aria_snapshot` je
isti izvor — ono što pregledač izlaže pomoćnim tehnologijama.

---

# R-004 — BIO JE `UNVERIFIED`, ISPOSTAVIO SE KAO `BROKEN`

Runtime provera je potvrdila da dugme radi kako izgleda:

```
pre odgovora        0 traka
posle odgovora      1 traka, ime „Prijavi netačan odgovor"
klik                „✓ Prijavljeno — hvala", onemogućeno, klasa `sent`
                    POST /api/feedback
dve prijave         nezavisne — jedna ne zaključava drugu
JS greške           nema
```

**Ali `reported_errors` upis se nije desio, a potvrda je ipak prikazana.**

Trag kroz oba sloja:

| Sloj | Šta čuva |
|---|---|
| `POST /api/feedback` (`routers/drafting.py:796`) | po NO-STORAGE politici **samo heš pitanja i tip** — bez teksta. Poziv je `fetch(...).catch(function(){})`, a backend vraća `{"status":"ok"}` i kad upis padne |
| `reported_errors` (Supabase klijent u pregledaču) | **jedini** trag stvarnog sadržaja: `original_prompt`, `ai_response` |

Kod je glasio `var sb = getSupabase(); if (sb) { …insert… }`, a poruka o uspehu
se postavljala **bezuslovno** ispod. Kad `window.supabase` još nije učitan,
`getSupabase()` vraća `null`, upis se tiho preskoči — i advokat dobija potvrdu
za prijavu koje nigde nema.

**To je isti razred kao P0-1: ekran uspeha bez ishoda — i to na najvrednijem
signalu koji ova aplikacija ima.**

Popravka koristi `_waitSupa()`, koji **već postoji u istom fajlu** upravo za taj
slučaj (6 drugih poziva ga koriste), i uslovljava potvrdu:

* nema klijenta → `⚠ Nije poslato — pokušajte ponovo`, dugme ostaje aktivno
* baza odbila upis → isto (Supabase JS ne baca izuzetak, grešku vraća u objektu)
* upis prošao → potvrda kao i pre

---

# ŠTA JE OSTALO — I ZAŠTO NIJE KVAR

Re-audit posle popravki javlja tri stavke; nijedna nije otvoren nalaz:

| Stavka | Objašnjenje |
|---|---|
| „Prijavi netačan odgovor: ne postoji u DOM-u" | ograničenje statičkog harness-a — traka se crta uz odgovor. Sada pokrivena runtime testovima (R-004) |
| „Pretraži pravnu bazu: 390px jezgro 0%" | fiksna donja traka na vrhu skrola; dokazano da se skrolom razrešava (12/12 na dnu, 49/49) |
| „Polje za pravni upit: nema pristupačno ime" | ograničenje harness-a — proverava `aria-label`/`title`/tekst, a ime `<textarea>` dolazi iz povezane `<label>`. ARIA stablo daje „Vaše pravno pitanje:" |

**P0F-002 ostaje `DEFERRED / VERIFIED / OUT-OF-SCOPE`.** Nije mešan sa R-001/R-002
— to su različiti razredi: P0F-002 je poznat mobilni layout problem, R-001/R-002
su bile kontrole koje ne rade odnosno nisu dohvatljive.

---

# STANJE

```
index.html          role/tabindex/ime na 2 kontrole, `for="qi"` na 1 labelu
static/vindex.js    pomocOtvori(), rukovalac sužen na role="tab", R-004 popravka
static/vindex.css   :focus-visible za 2 custom kontrole
static/sw.js        v129 → v130
tests/              +1 fajl (17 testova)

Testovi:  5144 → 5161 passed / 1 skipped / 0 failed
Redosled: no:randomly · seed=11
```

**REMOVE lista je i dalje zaključana.** Faza 2 sada može da počne — R-001…R-004
su zatvoreni po punoj matrici, a re-audit je čist.

---

# OSMO PRAVILO

> **Radnja mora da se izvrši tačno jednom.**

„Kontrola radi" i „kontrola radi jednom" nisu ista tvrdnja. Test koji proverava
*da li se nešto desilo* prolazi i kad se desilo dvaput — a dvostruko izvršavanje
je u pravnoj aplikaciji zaseban razred kvara (dupli predmet, dupla naplata,
dupla prijava).

Ovo pravilo je uhvatilo duplikat **u popravci napisanoj u istom sprintu**, pola
sata posle pravila 6 koje kaže da se poznat kvar ne sme izgubiti. Brojanje je
jeftino i nalazi ono što provera postojanja ne može.
