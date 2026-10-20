# 03 — Odobren tekst sajta i registar tvrdnji (Website V2)

## Gde je konačan tekst

Konačan tekst svake stranice je doslovno u izvornim fajlovima. Server ih šalje posle gradnje skriptom `scripts/gradi_sajt.py`:

| Stranica | Izvor teksta | Generisano |
|---|---|---|
| `/` | `site/_izvor/index.html` | `site/index.html` |
| `/kako-radi` | `site/_izvor/kako-radi.html` | `site/kako-radi.html` |
| `/funkcionalnosti` | `site/_izvor/funkcionalnosti.html` + katalog iz `site/funkcije.json` | `site/funkcionalnosti.html` |
| `/za-advokate` | `site/_izvor/za-advokate.html` | `site/za-advokate.html` |
| `/razvoj` | `site/_izvor/razvoj.html` + planovi iz `site/funkcije.json` | `site/razvoj.html` |
| `/bezbednost` | `site/_izvor/bezbednost.html` | `site/bezbednost.html` |
| `/beta` | `site/_izvor/beta.html` + poruke ishoda u `site/sajt.js` | `site/beta.html` |
| pre-auth ulaz | `index.html` (`#vx-landing.vxp`) | — |

Svaka stavka kataloga i razvoja dolazi doslovno iz polja `javni_opis` u registru `site/funkcije.json`. Pravilo (test `test_katalog_prikazuje_tacno_javne_funkcije_sa_tacnim_statusom`): stavka na sajtu = stavka u registru, sa istim statusom i istim tekstom. Ograničenje je deo teksta i ne može da se izgubi.

**Jezik i ton:** srpski, latinica, dijakritici. Svaka funkcionalna rečenica opisuje radnju, rezultat ili granicu. Nema slogana i nema obećanja budućih funkcija kao postojećih.

## Registar tvrdnji izvan kataloga

Status `ALLOWED` znači da tvrdnja ima oslonac u registru (ID funkcije) ili u kodu i da je prošla proveru iz `04_PUBLIC_CLAIMS_REVIEW.md`.

| ID | Stranica | Tvrdnja (suština) | Oslonac | Status |
|---|---|---|---|---|
| C-01 | `/` hero | „Predmeti, dokumenti, rokovi i pravni rad na jednom mestu.“ | A01, B05, D03, E01: sve četiri oblasti postoje u istoj V2 aplikaciji | ALLOWED (opis, ne „sve na jednom mestu“) |
| C-02 | `/` hero | „Sistem priprema informacije i predloge; advokat proverava izvore, odlučuje i potvrđuje radnje.“ | J03, D01, F02, B04 | ALLOWED |
| C-03 | `/` tok | Šest koraka sa nosiocem: vi otvarate / Vindex čita / čeka pregled / čeka potvrdu / AI predlaže / vi odlučujete | A02–A04, B01–B04, D01, E01, F01–F02 | ALLOWED. Nijedan korak nije predstavljen kao automatski ako to nije. |
| C-04 | `/` oblasti | Šest oblasti po tri stavke | podskup kataloga (A, B, C, D, E/F, I/H) | ALLOWED |
| C-05 | `/` kontrola | Poreklo stavke; izvor uz odgovor i odbijanje nepostojećeg člana; potvrda advokata; greška se ne skriva; samo vaši predmeti; znanje bez prečica | J03, E01, D01, J04, J02, G02 | ALLOWED |
| C-06 | `/` beta | „Funkcije su proverene automatskim testovima nad izmišljenim podacima; sistematsko iskustvo iz rada advokata na stvarnim predmetima tek se prikuplja.“ | VCR002 (nijedan zahtev nema nivo REAL_USER_ACCEPTED); NS4 tabele prazne | ALLOWED |
| C-07 | `/`, `/kako-radi` | Snimci su stvarni V2 ekrani sa izmišljenim podacima | `frontend-v2-ng/tests/diagnostics/site-snimci.mjs` | ALLOWED, uz oznaku „Demonstracioni prikaz“ |
| C-08 | `/kako-radi` k2 | Čitanje skenova OCR-om za ćirilicu i latinicu; `.doc` nije podržan | B01, B02 | ALLOWED |
| C-09 | `/kako-radi` k4 | „Vindex danas ne šalje podsetnike.“ | D07 (zakazani posao pada, 2026-10-20) | ALLOWED (granica) |
| C-10 | `/kako-radi` k4 | Kalkulator zastarelosti ne računa prekid ni zastoj | D06 | ALLOWED |
| C-11 | `/kako-radi` k5, `/bezbednost` | Odgovor izrađuje jezički model spoljnog dobavljača | E01; `/ai-disclosure` | ALLOWED |
| C-12 | `/kako-radi` k6 | Nacrt se preuzima kao Word dokument; ništa se ne šalje sudu ni klijentu | F01–F03 | ALLOWED |
| C-13 | `/kako-radi` k7 | Nacrt fakture nije izdata faktura i ne prijavljuje se u sistem e-faktura | I03; I05 (SEF nije potvrđen) | ALLOWED (granica) |
| C-14 | `/za-advokate` | Osam primera toka rada, označenih kao „primeri toka rada sa izmišljenim okolnostima“ | ID-jevi navedeni u „Gde:“ svakog primera | ALLOWED |
| C-15 | `/bezbednost` | Nema nezavisne bezbednosne sertifikacije niti spoljnog ispitivanja prodora | J08 | ALLOWED (granica) |
| C-16 | `/bezbednost` | Granicu pristupa sprovodi server; backend koristi privilegovan servisni ključ | J02 | ALLOWED |
| C-17 | `/bezbednost` | Originalni fajlovi iz prijema šifrovani na aplikacionom serveru; izdvojeni tekst nije | J05 (`routers/smart_intake.py::_encrypt`) | ALLOWED |
| C-18 | `/bezbednost` | JMBG, broj pasoša i PIB šifrovani; po njima se ne pretražuje | J06 (`klijenti/router.py:288–292`) | ALLOWED |
| C-19 | `/bezbednost` | Veza koristi HTTPS | produkcija: `strict-transport-security` | ALLOWED |
| C-20 | `/bezbednost` | Promene predmeta i odluke o rokovima beleže se kao događaji; nije potpun revizorski trag | C04, D01 | ALLOWED |
| C-21 | `/beta` | Prijava je zahtev za kontakt i ne otvara nalog; nalog se može otvoriti i sam (Registracija) sa ograničenim brojem kredita | `routers/waitlist.py`; `api.py::register` | ALLOWED |
| C-22 | `/beta` | „Potvrda se ne šalje e-poštom. Rok za odgovor ne obećavamo.“ | `routers/waitlist.py` šalje samo osnivaču | ALLOWED |
| C-23 | `/beta` ishod | Uspeh samo za `200` + `ok:true`; neutralan tekst „Prijava je evidentirana…“ bez stanja naloga | `site/sajt.js`; e2e „beta“ | ALLOWED |
| C-24 | `/razvoj` | Samo funkcije sa važećom odlukom (K01, K02), bez datuma, obe „Nije dostupno“ | registar | ALLOWED |
| C-25 | pre-auth | „Prijava u Vindex“, „Prijavite se svojim Vindex nalogom…“, link na `/beta` | J01 | ALLOWED |
| C-26 | podnožje | „Vindex ne zamenjuje profesionalno rasuđivanje advokata.“ | `terms.html` | ALLOWED |

## Uklonjeno i čime je zamenjeno

| Ranije (gde) | Zašto je uklonjeno | Sada |
|---|---|---|
| „847 zakona Srbije pretraženo za manje od 10 sekundi“ (pre-auth) | Broj korpusa i brzina nisu izmereni u produkciji | E01: „Baza propisa nije potpuna i ne zamenjuje službena glasila“ |
| „Automatska obaveštenja 7, 2 i 1 dan pre isteka. Sistem prati rokove umesto vas.“ (pre-auth) | Zakazani posao pada sa 403; isporuka nikad nije posmatrana | K02 na `/razvoj` kao „nije dostupno“; C-09 |
| „Poverljivi podaci zaštićeni AES-256“ (pre-auth) | Šifrovanje pokriva samo originale iz prijema i tri polja klijenta | C-17, C-18 sa granicom |
| „Beta · Ograničen broj mesta“, „Besplatno tokom beta faze“ (pre-auth) | Broj mesta ne postoji; cena nije predmet sajta | izostavljeno |
| „Pravo na dohvat ruke.“, „Pravni Operativni Sistem — Republika Srbija“, „Analiza koja radi umesto vas“ (pre-auth) | Slogan; „radi umesto vas“ protivreči ljudskoj kontroli | „Prijava u Vindex“ + jedna rečenica |
| „Dobrodošli. 15 besplatnih upita.“ / „Registracija je potpuno besplatna…“ kao POČETNI tekst modala (i u režimu prijave) | Režim prijave prikazivao je tekst registracije | početni tekst = tekst režima prijave iz `setAuthMode('login')`; tekst režima registracije nije menjan (činjenice o kreditima) |
| Jednostranični sajt sa devet koraka (NS004/NS005) | Mandat traži višestranični sajt i potpun katalog | 7 stranica + katalog iz registra |
| Linkovi na `/security` i `/bezbednosni-list` u podnožju | Sadrže tvrdnje koje ovaj rad nije potvrdio (S-01) | podnožje linkuje `/privacy`, `/terms`, `/dpa`, `/ai-disclosure`, `/status`; `/bezbednost` opisuje proverene mehanizme |

## Strukturisani podaci

JSON-LD nije dodat. Ne postoji proveren podatak o pravnom licu (test `test_nema_izmisljenog_pravnog_lica`), a ocena, recenzija ni broj korisnika se ne objavljuju. OpenGraph i Twitter metapodaci koriste naslov, opis i demonstracioni snimak registra.
