# ZADATAK 015 — WAVE 1 · GATE V1 — IZVEŠTAJ

Datum: 2026-09-05 · Base: `1201cee5` (produkcija) · **Clean HEAD: `f3174535`**
Grana: `v2-wave1` · Migracije: **0** · Push: **nije izvršen** · Legacy `/app`: **netaknut**

---

## 1. GIT / BASE IDENTITET

```
produkcija (/api/version)  1201cee56f8ba174b95bb349f99515cc18ec25b5   identity_proven=true
origin/main                1201cee56f8ba174b95bb349f99515cc18ec25b5   ← isto
base novog worktree-a      1201cee5                                    ✓
legacy visual diff od base 0 fajlova
worktree pri startu        0 izmena
```

Glavni development worktree (`legal-agent`, `cf33ab9b`, 15 ahead / 5 behind, sa
10 odbačenih UI commitova i vašim artefaktima) **nije dirnut**: bez `rebase`,
`reset`, `stash`, `clean`, `checkout` i `merge`.

## 2. IZOLOVANI WORKTREE

```
putanja : ../vindex-v2-wt
grana   : v2-wave1  (nova, od TAČNO 1201cee5)
```

## 3. FAJLOVI — 26 novih, 2 izmenjena

```
NOVO
  index-v2.html                          36
  v2/boot.js                             95     v2/app.js                      15
  v2/platform/{http,auth,router,          362    (6 modula)
               lifecycle,errors,log}.js
  v2/domain/{predmeti,labels}.js         122
  v2/shell/shell.js                       70
  v2/features/predmeti/{api,state,view}   371
  v2/styles/*.css                        614    (7 fajlova)
  tests/test_z015_v2_{rute,sw_izolacija,domen}.py

IZMENJENO
  api.py         +111   tri nove rute, nijedna postojeća nije dirnuta
  static/sw.js    +20/-1  V2 bypass + CACHE_NAME v148 → v149
```

**Nula izmena** u: `index.html`, `static/vindex.js`, `static/vindex.css`,
`shared/*`, `routers/*`, `migrations/*`.

## 4. ARHITEKTURA RUTA

| ruta | ponašanje |
|---|---|
| `/app-v2` | minimalan V2 dokument (1 631 B) |
| `/app-v2/{putanja}` | **isti** dokument — ruter je na klijentu (History API) |
| `/v2/@{token}/{putanja}` | V2 asset, `immutable`, `max-age=31536000`, `nosniff` |
| `/app` | **nepromenjeno** |

Klijentski ruter: `/app-v2` se kanonski razrešava na `/app-v2/predmeti` bez
ponovnog učitavanja dokumenta; nepoznata child putanja se takođe razrešava na
Predmete. Deep link i osvežavanje rade jer server servira isti dokument.

Izmereno: `/app-v2` → `/app-v2/predmeti`, **0 ponovnih učitavanja dokumenta**,
`popstate` ne izaziva novi API poziv.

## 5. AUTH BOOT

```
1 dokument (bez poslovnog sadržaja)
2 sesija
3 nema sesije      -> kanonska prijava (/app)
4 /api/plan/status -> kanonski izvor prava
5 v2_pristup?
6 tek tada montiranje aplikacije
7 tek tada prvi poslovni poziv
```

Sesija se čita iz **istog skladišta koje legacy supabase-js već piše**
(`sb-<ref>-auth-token`), bez SDK-a: `window.supabase` je globalna promenljiva
koju V2 ne sme da nasledi. Ko je prijavljen na `/app`, prijavljen je i na
`/app-v2`. Ako se konvencija ključa ikad promeni, sesija se ne nađe i korisnik
ide na prijavu — fail-closed, nikad tihi prolaz.

## 6. `v2_pristup` KAPIJA — izmereno, ne tvrđeno

Mereno tako što je preusmerenje na legacy blokirano, pa se vidi **šta je V2
stvarno uradio pre nego što je otišao**:

| nalog | `/api/plan/status` | `/api/predmeti` | ishod | curi „v2_pristup/rollout/403" |
|---|---|---|---|---|
| neprijavljen | **0** | **0** | → `/app` | ne |
| prijavljen, bez dodele | 1 | **0** | → `/app` | ne |
| founder (ima dodelu) | 1 | 1 | aplikacija | ne |

Neprijavljen ne dodirne čak ni izvor prava. Nalog bez dodele dobije **nula**
poslovnih poziva. Korisniku se ne prikazuje ni naziv kapije, ni broj statusa,
ni „uskoro" stranica — samo kanonsko preusmerenje na proizvod koji koristi.

Frontend nije bezbednosna granica: kad bi neko obrisao ovu proveru u
pretraživaču, dobio bi ekran bez podataka, ne podatke.

## 7. SERVICE WORKER — P1 ZATVOREN

Kvar: SW ima scope `/`, presreće i `/app-v2`, a njegova navigaciona grana pri
padu mreže radi `caches.match("/offline")` → legacy `index.html`. Korisnik bi
video **stari Vindex pod V2 adresom** — pogrešan proizvod, ne prazan ekran.

Najmanja bezbedna korekcija: `/app-v2`, `/app-v2/*` i `/v2/*` izlaze iz SW-a
**pre svake grane koja poziva `respondWith`**. Bez `respondWith`, bez keša.

Izmereno u pregledaču, sa **stvarno registrovanim** SW-om (`vindex-v149`,
kontroliše stranicu, `/offline` potvrđeno u kešu):

```
offline  fetch("/app-v2")        -> mrežna greška   (legacy dokument: NE)
offline  fetch("/v2/@x/boot.js") -> mrežna greška
offline  fetch("/app")           -> 200, 411 202 B legacy app-shell  ← NEPROMENJENO
online   navigacija /app-v2      -> V2 se učitava, 20 redova, "vindex.js" u dokumentu: NE
```

V2 **ne registruje** SW (online-only u Wave 1); samo traži `update()` već
instaliranog legacy SW-a, da stara verzija bez bypass-a ne ostane aktivna.

## 8. VERZIONISANI ASSETI

Verzija je **u putanji** (`/v2/@<token>/...`), pa asset sme `immutable` keš od
godinu dana: nova verzija = nova putanja. Legacy `?v=` model radi suprotno i
namerno se ne ponavlja.

```
produkcija  token = dokazan commit identitet (isti izvor kao /api/version)
razvoj      token = "dev-" + hash stabla (putanja + veličina + mtime)
```

Izmereno: 21/21 asseta 200; `Cache-Control: public, max-age=31536000, immutable`;
`X-Content-Type-Options: nosniff`; `../api.py`, `../../.env`, `/etc/passwd` → **404**;
stara verzija se i dalje servira (to je poenta immutable modela).

## 9. VIZUELNA IMPLEMENTACIJA

Puna širina scene, editorial mera samo za sadržaj. Crna scena = ljuska, papir
scena = registar. Bez kartica, bez senki, bez zaobljenja, bez bočne trake,
bez hero-a i bez slogana. Prvi sadržaj ekrana je **registar**.

| odluka | vrednost | zašto |
|---|---|---|
| crna | `#12110F` | neutralna, nije čista crna (ustav §6 P-2/P-3) |
| papir | `#F6F3ED` | topla, nije čista bela (P-4) |
| brend | `#6E1B22` oxblood | koristi se **samo** za prsten fokusa i oznaku aktivnog odeljka |
| separator | jedna vlasasta linija | ustav §7 S-3 |
| serif | Source Serif 4 | znak „Vindex" i naslov „Predmeti" — ne slogan |
| sans | Source Sans 3 | ceo operativni UI |
| mono | JetBrains Mono | broj predmeta i datum — vrednosti koje se porede/prepisuju |

Legacy pisma (Cormorant Garamond, Plus Jakarta Sans) **nisu** u V2 — test to
čuva. Status nosi reč, boja je samo pojačava; kategorija (`vrsta`) je verzal
bez ispune i okvira — dve uloge, ne sedam tretmana (Wave 2 lock W2-L3).

## 10. UGOVOR `/api/predmeti`

```
GET /api/predmeti?view=summary&limit=50&offset=0&q=

odgovor: { predmeti[], ukupno, limit, offset }
kolone : brisanje_zapoceto, broj_predmeta, created_at, id, naziv, status, tip, updated_at
         8 kolona umesto 17 na legacy putanji;  case_dna: NIJE u payload-u
```

`id` prelazi jer ga ruter i backend trebaju, ali **nije deo vidljivog modela** —
mereno: **0 UUID-eva** u vidljivom tekstu, nema `case_dna`, `storage_path`,
`user_id` ni `namespace`.

## 11. PRETRAGA I STRANIČENJE

**Pretraga** — registarska, ne globalna. Server `q`, debounce 300 ms, `AbortController`
+ broj generacije protiv zastarelog odgovora, jasno poništavanje, radi sa tastature.

```
4 znaka ukucana brzo   -> 1 poziv (ne 4)
q u pozivu             DA        view=summary zadržan   DA
prazan rezultat        „Nema predmeta za ovu pretragu."
„Poništi"              20 predmeta natrag
spor 1. + brz 2. upit  konačno 0 redova — stari odgovor NIJE pregazio novi
```

**Straničenje** — stvarni server `limit`/`offset`, bez klijentske paginacije.
Izmereno nad stvarnim podacima sa prisilnom stranom od 5:

```
strana 1  1–5 od 20    prethodna onemogućena
strana 2  6–10 od 20
strana 3  11–15 od 20
strana 4  16–20 od 20  sledeća onemogućena
fokus posle promene strane -> v2-reg-sadrzaj
```

Integritet meren **po identitetu, ne po nazivu**: 20 prikupljenih, **20
jedinstvenih ID-eva, 0 duplikata, 0 preskočenih**, redosled identičan u 3
uzastopna poziva.

> **Ispravka sopstvenog merenja.** Prvi prolaz je po nazivima prijavio „9
> duplikata". Bilo je netačno: stvarni podaci imaju 11 različitih naziva na 20
> zapisa (7 naziva se ponavlja). Nalaz nije prijavljen kao bag jer nije bio bag.

Klijent **usvaja `limit`/`offset` iz odgovora**. `/api/predmeti` skraćuje limit
na `[1,500]`; da klijent zadrži traženu vrednost, sledeći offset bi se računao
po strani koja nikad nije stigla i straničenje bi **preskakalo zapise**. Ovo je
pravi bag koji je nađen i zatvoren tokom Gate-a.

## 12. RESPONSIVE

| viewport | horizontalno prelivanje | tekst < 11 px | visina reda | redova u prvom ekranu |
|---|---|---|---|---|
| 1440×900 | **0** | **0** | 56 px | 11 |
| 1024×768 | **0** | **0** | 56 px | 8 |
| 390×844 | **0** | **0** | 74 px (prelama) | 7 |
| 360×800 | **0** | **0** | 74 px | 7 |

Na uskom ekranu red postaje vertikalniji ali **ostaje red** — naziv u prvoj
liniji, metapodatak u drugoj razdvojen tačkom. Nije galerija kartica. Nijedan
podatak nije sakriven zbog širine (izuzetak: e-adresa u ljusci ispod 400 px,
nalog ostaje dostupan preko „Nalog").

## 13. PRISTUPAČNOST

```
kontrast    32 iscrtana čvora mereno, 0 ispod praga; najniži koji prolazi 6,09:1 (prag 4,5)
fokus       prsten 2 px oxblood na kontrolama papir scene, 2 px svetli na crnoj sceni
tastatura   3× Tab -> polje pretrage -> kucanje filtrira (13 predmeta)
            Enter ne učitava dokument -> Tab -> „Poništi" -> Enter -> 20 predmeta
semantika   native <form role=search>, <label for>, <button>, <ul>/<li>, <h1>
            nevidljive labele po polju; zaglavlje kolona aria-hidden
0 inline rukovaoca · 0 div onclick · skip link · prefers-reduced-motion poštovan
```

Dve dokazane regresije starog vizuelnog HEAD-a (glasovno dugme na uskim
ekranima, WCAG AA kontrast) **nisu nasleđene** — V2 je pisan iz nule.

## 14. FULL-BLEED — HARD GATE

```
viewport    scena   x=0                x=w/2              x=w-1              jedinstvena
1440×900    crna    rgb(18,17,15)      isto               isto               DA   širina 1440/1440
            papir   rgb(246,243,237)   isto               isto               DA   širina 1440/1440
1024×768    crna / papir                                                     DA / DA
390×844     crna / papir                                                     DA / DA
360×800     crna / papir                                                     DA / DA
```

Nigde `crno-papir-crno` na istoj Y osi. Nema crnih margina oko papira, nema
kartice na kanvasu, nema centriranog okvira.

## 15. KONTAMINACIJA LEGACY-JEM — NULA

```
skripte na /app-v2   ['/v2/@<token>/boot.js']            ← jedan ES modul
stilovi              7 × /v2/@<token>/styles/*.css + fonts.googleapis.com
legacy asseta        0
legacy globali       [] (supabase, $, jQuery, _predmeti, currentSession, FontAwesome)
inline rukovaoca     0
"vindex.js" u dokumentu   NE
```

## 16. MREŽA I TEŽINA

```
zahteva pri čistom učitavanju : 29
   1 dokument · 21 V2 asset · 1 fonts CSS · 4 font fajla
   1 /api/plan/status · 1 /api/predmeti
ničeg drugog: bez workspace prefetch-a, bez case_dna, bez legacy asseta
DOM čvorova : 273
```

| | V2 | legacy `/app` |
|---|---:|---:|
| dokument | **1 631 B** | 417 995 B |
| JS | **35 129 B** (14 modula) | 1 282 565 B |
| CSS | **20 452 B** (7 fajlova) | 492 947 B |
| ukupno | **57 KB** | **2 193 KB** |

Oko **38× lakše**. 21 asset je posledica ES modula bez bundlera (owner-locked);
svi nose `immutable` keš, pa se plaćaju jednom.

## 17. TESTOVI

```
tests/test_z015_v2_rute.py            18 prošlo
tests/test_z015_v2_sw_izolacija.py    10 prošlo
tests/test_z015_v2_domen.py           23 prošlo   (izvršeni u Node-u, pravi moduli)
                                      51 / 0
```

### Mutacije — 10 konstruisano, 10 razrešeno

| # | mutacija | ishod |
|---|---|---|
| M1 | SW bypass „premešten" (samo preimenovan komentar) | preživela — **loša mutacija** |
| M1b | SW bypass **stvarno** premešten posle navigacione grane | **UBIJENA** (3 pada) |
| M2 | SW bypass uklonjen | UBIJENA |
| M3 | `CACHE_NAME` vraćen na v148 | UBIJENA |
| M4 | `ukupno` računato iz dužine strane | UBIJENA |
| M5 | nepoznat enum vraćen kao sirov ključ | UBIJENA |
| M6 | nova generacija ne prekida prethodnu | UBIJENA |
| M7 | V2 dokument učitava legacy runtime | UBIJENA |
| M8 | uklonjena **jedna** od dve zaštite putanje | preživela — ruta ostala bezbedna |
| M8c | uklonjene **obe** zaštite putanje | **UBIJENA** |
| M9 | legacy offline fallback obrisan | UBIJENA |
| M10 | V2 child ruta servira legacy dokument | UBIJENA |

M1 je bila moja greška u konstrukciji, ne rupa u testu. M8 pokazuje da su dve
zaštite putanje **međusobno redundantne** — test čuva svojstvo (nemoguć izlazak
iz `v2/`), a ne to koja provera ga obezbeđuje; uklanjanje obe test obara.

## 18. REGRESIJA

Puna suita na `v2-wave1`, i ista suita na clean foundation grani (`1201cee5`)
iz Z014.3 — isti tip worktree-a, ista masina, isti redosled.

```
clean foundation (1201cee5)   15 palo · 7633 proslo · 179 presk. · 766 s
v2-wave1        (f3174535)    15 palo · 7684 proslo · 179 presk. · 785 s
```

Masinska razlika skupova padova:

```
NOVO na v2-wave1 : nijedan
NESTALO          : nijedan
proslo           : 7633 -> 7684 = +51   (tacno broj novih testova)
```

**Regresija: nijedna.** Svih 15 padova postoji i na produkcionom SHA i vec je
diferencijalno razreseno u Z014.3: `ns003_protocol` i `rc_cold_start` r5/r7 su
artefakt sveze `git checkout` kopije (CRLF u fixture fajlu, citanje git stanja),
a `coi_intake_convergence`, `prg_night_register` i cetiri `faza1` testa padaju i
na goloj produkciji. Nijedan od njih ne dodiruje `v2/`.

Cetiri `faza1` testa mere legacy `static/vindex.css`, koji ovaj zadatak nije
dirnuo — pa se njihov ishod nije ni mogao promeniti.

---

## 19. COMMIT-OVI

```
1201cee5  (produkcija / base)
  └ 52a12d21  fix(sw): /app-v2 nikad ne dobija legacy app-shell
    └ 97105b3b  feat(v2): W1.0 + W1.1 -- prvi Vindex V2 na /app-v2
      └ f3174535  test(v2): rute, SW izolacija i domen Wave 1
```

W1.0 i W1.1 nisu razdvojeni jer bi W1.0 bez W1.1 bio slomljen međukorak:
`app.js` montira ekran Predmeti.

## 20. DEPLOYMENT

**NIJE IZVRŠEN PUSH.** Ovaj mandat u zaglavlju kaže `IMPLEMENTATION AUTHORIZED`
— ne `DEPLOYMENT`. Z014.4 je, za poređenje, izričito glasio
`IMPLEMENTATION / DEPLOYMENT AUTHORIZED` uz rečenicu „OWNER JE ODOBRIO PUSH".
§50 nalaže: ako prethodna autorizacija nije dovoljna prema repo pravilima —
STOP pre push-a, ne pretpostavljaj.

### PRE-PUSH SUMMARY

```
base SHA          1201cee56f8ba174b95bb349f99515cc18ec25b5
commit range      1201cee5 .. f3174535   (3 commita)
fajlova           26 novih, 2 izmenjena
migracija         0
legacy fajlova    1 izmenjen: static/sw.js (+20/-1) — bypass + CACHE_NAME
                  0 izmena u index.html / vindex.js / vindex.css
testovi           51 novih, 0 padova
rollback target   1201cee5
```

## 21. ŽIVI URL

Posle push-a: **`https://vindex-ai.onrender.com/app-v2`** — otvara se sa vašim
nalogom, koji jedini ima `v2_pristup`.

Sve u ovom izveštaju izmereno je na `http://127.0.0.1:8021/app-v2` uz **stvarni
produkcioni backend, stvarnu bazu i vaš stvarni nalog** — ne na mokovima. Ono
što push menja je adresa, ne ponašanje.

## 22. PREOSTALO U WAVE 1

| stavka | status |
|---|---|
| Otvaranje predmeta (Dosije) | **svesno izostavljeno** — red nije klikabilan, jer mrtav klik je gori od izostanka |
| „Nov predmet" | **svesno izostavljeno** — tok kreiranja nije autorizovan; nema mrtvog dugmeta |
| Danas / Znanje / Kancelarija / Usklađenost | nisu prikazani ni kao onemogućeni |
| V2 offline | van opsega — Wave 1 je online-only po nalogu |

## 23. NALAZI KOJE STE VI POZVANI DA ODLUČITE

1. **`/api/predmeti` sa `offset` van opsega vraća HTTP 500.** Zatečeno u Z014
   foundation-u, **živo u produkciji `1201cee5`**, nezavisno od `view=summary`:
   ```
   offset=0    -> 200
   offset=200  -> 500
   offset=2000 -> 500
   ```
   V2 korisnik to **ne može dostići svojim kontrolama** — „Sledeća" je
   onemogućena na poslednjoj strani (dokazano). Ali stara deep-link adresa ili
   registar koji se smanji tokom rada mogu. §43 nalaže da se evidentira, ne
   popravlja automatski, i tako je i urađeno.

2. **Push i auto-deploy** — čeka vašu reč (§20 gore).

3. **Lokalni `main` je i dalje razišao sa produkcijom** (15 ahead / 5 behind).
   Grana `v2-wave1` polazi od produkcije, pa se to ne tiče ovog rada — ali
   ostaje otvoreno pitanje šta sa 10 odbačenih UI commitova.

4. **Dokumenti Z008 / Z010C.1 / Z011 / Z012 / Z013 ne postoje u repou.**
   Pretraženo po imenu i po sadržaju — nema ih. Kao specifikacija je korišćen
   sam ovaj mandat (koji ključne odluke ponavlja doslovno) plus
   `VINDEX-VISUAL-CONSTITUTION-v1.0.md`, `D-01`, `D-02` i `DOC-08`, koji
   **jesu** u repou. Ako ta dokumenta postoje van repoa, vredi ih uneti pre
   Wave 2 — inače će svaki sledeći izvođač morati da ih rekonstruiše.

## 24. VERDIKT

# 🟡 GATE V1 IMPLEMENTED — SPECIFIC OWNER/DEPLOY ACTION REMAINS

Vindex V2 postoji, radi na stvarnim podacima i izmeren je po svih 20 kriterijuma
iz §48. Zuto je iz **tacno jednog** razloga: **push nije autorizovan ovim
mandatom**, pa vi jos ne mozete otvoriti `/app-v2` u pretrazivacu. Sve ostalo je
zeleno.

| # | kriterijum §48 | ishod |
|---|---|---|
| 1 | `/app-v2` stvarno postoji | ✓ |
| 2 | founder moze da udje | ✓ 20 stvarnih predmeta |
| 3 | nalog bez prava ne dobija V2 povrsinu | ✓ 0 poslovnih poziva |
| 4 | legacy `/app` netaknut | ✓ 0 izmena u `index.html`/`vindex.js`/`vindex.css` |
| 5 | legacy asseti nisu u V2 | ✓ 0 |
| 6 | Predmeti koriste stvarne podatke | ✓ |
| 7 | `view=summary` se koristi | ✓ 8 kolona, bez `case_dna` |
| 8 | stranicenje radi | ✓ 4 strane, 0 duplikata, 0 preskocenih |
| 9 | `q` radi | ✓ server, debounce, stale defense |
| 10 | nema mrtvog UI-ja | ✓ |
| 11 | nema hero/slogana | ✓ prvi sadrzaj je registar |
| 12 | nema card/dashboard/sidebar kontaminacije | ✓ |
| 13 | full-bleed test | ✓ 4/4 viewporta |
| 14 | srpska terminologija | ✓ |
| 15 | 1440/1024/390/360 bez prelivanja | ✓ |
| 16 | tastatura i fokus | ✓ |
| 17 | 0 fatalnih konzolnih gresaka | ✓ |
| 18 | SW ne moze vratiti legacy HTML pod `/app-v2` | ✓ dokazano offline |
| 19 | nijedan interni ID nije user-facing | ✓ 0 UUID-eva |
| 20 | **owner moze otvoriti URL i oceniti V2** | **ceka push** |

Kada kazete rec, push je jedna komanda i `/app-v2` je ziv na vasem nalogu.

**STOP.** Dosije, Hronologija, Spisi, globalna pretraga, upload i reader nisu
dirani i nece biti dok ne vidite Predmete.
