# FAZA 1 — RE-AUDIT KRITIČNIH KONTROLA

**Polazno:** `ac1d70e2` · 5069 passed
**Završno:** **5144 passed / 1 skipped / 0 failed**, `no:randomly` i `seed=11`
**Metod:** merenje u pravom Chromium-u nad pravim `index.html`, devet dimenzija
po kontroli. Nula pretpostavki iz izvora.

---

# 0. GLAVNI NALAZ — P0F-001 NIJE BIO ZATVOREN

**Prijavio sam ga kao zatvoren. Nije bio.** Ovo je najvažnija stavka izveštaja i
stoji prva.

## Šta sam pogrešio

Prvu popravku sam merio **samo na visini ekrana 860px**. Re-audit na realnim
visinama telefona:

| Ekran | `#mic-qi` na vrhu skrola |
|---|---|
| 375×860 | 49/49 ✓ |
| 390×860 · 412×860 | 49/49 ✓ |
| **375×740** | **21/49 — presreće `#vx-mobile-fab`** |
| **390×667 · 412×667** | **0/35 — presreće `#vx-mobile-fab`** |

Kompozer se na nižem ekranu pomera naniže i njegov vrh ponovo ulazi u pojas
plutajućih dugmadi. Poravnanje mikrofona uz vrh kompozera nije moglo to da
spreči — **vertikalno razdvajanje ne može da važi kad položaj zavisi od visine
ekrana.**

## Druga greška — merio sam pogrešan element

U prethodnom izveštaju sam tvrdio: *„panel se ne skroluje
(`scrollHeight 795 < clientHeight 804`), pa `padding-bottom` ne pomera sadržaj"*.

**Netačno.** Merio sam `.vx-body`. Stvarni skrol kontejner je
**`.vx-panels-wrap`** — `overflow-y: auto`, `scrollHeight 1147` vs
`clientHeight 726`, dakle **421px skrola**.

Ista greška u izboru elementa dala je i pogrešan zaključak o `#exec-btn`
(„ispod preloma, dostupno skrolovanjem" — slučajno tačno, ali iz pogrešnog
razloga).

## Popravka — vodoravno razdvajanje

`#mic-qi` je vezan za **desnu** ivicu kompozera. Dokle god je i „Novi predmet"
desno, sudar se vraća na svakoj dovoljno niskoj visini.

Zato plutajuća dugmad idu u **levu kolonu**:

```
#vx-mobile-fab   right:18 bottom:76  →  left:18 bottom:68     (Novi predmet)
#vx-voice-fab    bottom:72           →  bottom:130            (Vindex Live)
#feedback-fab    bottom:134          →  bottom:192            (povratna informacija)
```

Redosled odozdo nagore prati važnost: primarna radnja je najniža, dakle
najlakše dohvatljiva palcem. Desna ivica ostaje slobodna za kontrole sadržaja.

Rezultat na svih **12** kombinacija (375/390/412 × 667/740/800/860): nijedna
tačka mete mikrofona ne pripada plutajućem dugmetu, ni na vrhu ni na dnu skrola.

## Prvobitna popravka je uklonjena jer ništa nije radila

`.mic-input-wrap { align-items: flex-start }` je posle pomeranja FAB-a postala
suvišna — **mutacija je to dokazala**: test prolazi i bez nje. Uklonjena.
Držati pravilo koje ne radi ništa je isti razred greške koji ovaj program lovi.

---

# 1. PRECIZIRAN KRITERIJUM — DVA RAZREDA PRESRETANJA

Re-audit je iznudio razliku koju prva verzija testa nije pravila:

| Presretač | Status | Zašto |
|---|---|---|
| **Plutajuće dugme** (`#vx-mobile-fab`, `#vx-voice-fab`, `#feedback-fab`, `#pred-fab`) | **UVEK KVAR** | ne pomera se sa sadržajem; korisnik nema način da sazna da mu neko drugi uzima dodir, a pritisak izvršava tuđu radnju |
| **Fiksna donja traka** (`#vx-mobile-nav`) | **nije kvar sam po sebi** | sadržaj legitimno skroluje ispod nje — tako radi svaka mobilna aplikacija |

Da ovo ne bi bilo spuštanje kriterijuma, drugi razred je vezan za **obavezu koja
se posebno dokazuje**: kontrola mora biti **100% dostupna kad se doskroluje**.

Izmereno na svih 12 kombinacija, na dnu skrola:

```
mic-qi 49/49 · qi 49/49 · exec-btn 49/49     (svih 12, bez izuzetka)
```

Bez tog para tvrdnji bi prva bila prazna.

---

# 2. DEVET DIMENZIJA — REZULTAT PO KONTROLI

`postoji → izvršavanje → rukovalac → tastatura → geometrija 1440 → geometrija
390 → API` (odredište i duplikat provereni u izvoru)

| Grupa | Kontrola | Post | Vidljiv | Rukovalac | Tastatura | Jezgro 1440 | Jezgro 390 | API |
|---|---|---|---|---|---|---|---|---|
| Glas | Vindex Live (FAB) | ✓ | ✓ | `function` | ✓ | 100% | 100% | — |
| Glas | Govori (gornja traka) | ✓ | ✓ | inline izraz | ✓ | 100% | — | — |
| Glas | Diktat u polju za upit | ✓ | ✓ | `function` | ✓ | 100% | 100% | — |
| Podrška | Povratna informacija | ✓ | ✓ | `function` | ✓ | 100% | 100% | — |
| Podrška | **Pomoć & podrška** | ✓ | ✓ | **NEMA** | **NE** | 100% | — | — |
| Podrška | Prijavi netačan odgovor | dinamički | — | — | — | — | — | — |
| Navigacija | Pregled dana · Predmeti · Klijenti · Vindex Intelligence · Podešavanja | ✓ | ✓ | `function` | ✓ | 100% | — | — |
| Navigacija | Mobilna navigacija | ✓ | mobilni | kontejner | — | — | 100% | — |
| Radnje | Novi predmet (čarobnjak) | ✓ | ✓ | `function` | ✓ | 100% | 100% | — |
| Radnje | Iz dokumenta (Smart Intake) | ✓ | ✓ | `function` | ✓ | 100% | 100% | — |
| Radnje | Novi predmet (mobilni FAB) | ✓ | mobilni | `function` | ✓ | — | 100% | — |
| Radnje | **Otpremi dokument** | ✓ | ✓ | `function` | **NE** | — | — | — |
| Radnje | Pretraži pravnu bazu | ✓ | ✓ | `function` | ✓ | 100% | 100%¹ | ✓ |
| Radnje | **Polje za pravni upit** | ✓ | ✓ | — | ✓ | 100% | 100% | — |
| Tok | Dalje (čarobnjak) | ✓ | ✓ | `function` | ✓ | 100% | 100% | — |
| Tok | Rezultat uploada | ✓ | uslovno | kontejner | — | — | — | — |
| Tok | Greška uploada | ✓ | uslovno | kontejner | — | — | — | — |

¹ posle doskrolovanja; na vrhu skrola je iza donje trake, v. §1.

**Nula JS grešaka pri učitavanju** na obe širine — P0-0 popravka drži.
**Nula `fetch` poziva ka nepostojećoj ruti** među proverenim kontrolama
(581 registrovana ruta).

---

# 3. NALAZI KOJI OSTAJU OTVORENI

## R-001 — „Pomoć & podrška" je i dalje mrtva

`index.html:533` · `<div class="vx-foot-row vx-sidebar-help">` · **nema
`onclick`, nema slušaoca** (6 pogodaka u repou, svih 6 su CSS). Nije dostupna
tastaturom jer nije ni kontrola. CSS joj daje `cursor:pointer` i hover, pa
izgleda živo.

Ovo je `B-007` iz kanonskog inventara. **Nije regresija — nikad nije ni radila.**
Popravka je proizvodna odluka (šta to dugme treba da otvori), ne tehnička.

## R-002 — „Otpremi dokument" nedostupno tastaturom

`index.html:1086` · `#pred-upload-zone` je `<div onclick="pred_upload_trigger()">`
bez `role` i `tabindex`. Otpremanje dokumenta je **osnovna radnja** — advokat
bez miša do nje ne može.

Isti razred kao P0-4 (glavna navigacija), i ista popravka: `role="button"` +
`tabindex="0"` + rukovalac za `Enter`/`Space`. **Nije urađeno** jer izlazi iz
scope-a re-audita — re-audit meri, ne popravlja.

## R-003 — `#qi` nema pristupačno ime

Polje za pravni upit ima samo `placeholder`. Čitač ekrana ne izgovara čemu polje
služi. Deo šireg nalaza iz `ACCESSIBILITY_REPORT.md` (175 od 203 polja).

## R-004 — „Prijavi netačan odgovor" se ne može statički proveriti

Ne postoji u `index.html`; crta se iz `vindex.js` posle AI odgovora. Njegovo
ponašanje **nije ovim re-auditom dokazano** — traži scenario sa stvarnim
rezultatom analize. `UNVERIFIED`, ne „ispravno".

---

# 4. P0F-002 — I DALJE ODLOŽEN, I DALJE ZAKLJUČAN

Plutajuća dugmad su pomerena naviše (voice 130, feedback 192), ali i dalje padaju
preko uglova polja `#qi`. Registar to potvrđuje izvršno:
`test_odlozeni_kvar_se_i_dalje_reprodukuje[P0F-002]` **prolazi** — dakle kvar
postoji, zapis je istinit.

Status ostaje `DEFERRED / VERIFIED / OUT-OF-SCOPE`. Uslov zatvaranja nepromenjen:
rezervisana geometrija za plutajuća dugmad.

---

# 5. ŠTA JE ZAKLJUČANO TESTOVIMA

```
tests/test_p0f001_mobile_collision.py   84 testa  (3 širine × 4 visine × 7)
tests/test_deferred_defects.py           6 testova (registar + brave)
```

## Mutacije

| Mutacija | Ishod |
|---|---|
| „Novi predmet" vraćen **desno** | **16 od 84 palo** |
| uklonjena popravka mikrofona (`align-items`) | **84 prošlo** → dokaz da je bila suvišna |
| obe uklonjene (potpuno staro stanje) | **16 palo** |
| P0F-002 „popravljen" (oba FAB-a sklonjena) | **brava registra pala** — zapis ne može da nadživi popravku |

Druga mutacija je najkorisnija: pokazala je da jedno od dva pravila ne radi
ništa, pa je uklonjeno.

---

# 6. STANJE

```
static/vindex.css   3 pozicije premeštene, 1 suvišno pravilo uklonjeno
static/sw.js        v128 → v129
tests/              +1 fajl (registar odloženih), matrica visina u P0F-001

Testovi:  5069 → 5144 passed / 1 skipped / 0 failed
Redosled: no:randomly · seed=11
```

**REMOVE lista je i dalje zaključana.** Faza 2 se ne otvara dok R-001 i R-002 ne
dobiju odluku — jer su oba u istoj porodici pitanja („kontrola postoji, ali
ne radi / nije dohvatljiva") kao i kandidati za brisanje.

---

# 7. ŠTA OVAJ RE-AUDIT KAŽE

Sedmo pravilo, izvedeno iz sopstvene greške:

> **Jedan uslov merenja nije dokaz.** Jedna visina ekrana, jedan položaj skrola,
> jedan element kao „skrol kontejner" — svako od toga je proizvelo pogrešan
> zaključak u prethodnom sprintu.

Prvih šest pravila su govorila *šta* meriti. Ovo govori *koliko puta*. Test koji
meri na jednoj tački prostora stanja daje tačan rezultat za tu tačku i lažnu
sigurnost za sve ostale — što je tačno ono što se desilo sa P0F-001.
