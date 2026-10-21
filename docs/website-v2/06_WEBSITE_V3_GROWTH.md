# 06 — Website V3: rast, pozicioniranje i prijava problema (2026-10-21)

**Mandat osnivača:** „Website V3 / Growth Experience Sprint“.
**Grana:** `website/v3-growth`, od `main` = produkcija `fe03aaec` (PR #48 spojen).

Oznake dokaza:
- **PROVEN** — izmereno testom ili čitanjem produkcije;
- **INFERRED** — sledi iz koda ili pravnih dokumenata;
- **UNKNOWN** — nije proverljivo iz ovog okruženja.

## 1. Šta je promenjeno

| Površina | Ranije | Sada |
|---|---|---|
| Početna | tehnički opis, beta status, „Šta Vindex danas radi“, poziv na `/razvoj` | Hero „Od dokumenata do jasnih odluka.“, šest razlika u odnosu na AI čet, četiri istaknute funkcije (problem → šta Vindex radi → korist, stvaran snimak), tok rada sa linijom napretka, deset sektora, zaštita ukratko, završni poziv |
| Poziv na akciju | „Prijavite se za beta testiranje“, „Beta pristup“ | „Prijavi se za rani pristup“ (zaglavlje, mobilni meni, sve stranice); ruta `/beta` i `POST /waitlist/prijava` su nepromenjeni |
| `/razvoj` | javna stranica sa planovima (K01, K02) | 301 → `/funkcionalnosti`; uklonjen iz menija, podnožja, sitemap-a i generatora; planovi ostaju samo u `site/funkcije.json` i internoj matrici 02 |
| `/funkcionalnosti` | katalog po tehničkim oblastima sa statusnim oznakama, legendom i filterom po statusu | sedam grupa po poslu (organizuj → razumi → poveži → istraži → pripremi → deluj → zaštita); bez statusnih oznaka; granica funkcije ostaje u celosti uz funkciju; funkcija dostupna samo u klasičnom interfejsu to i kaže; pretraga po tekstu |
| `/bezbednost` | tri mreže mehanizama | sedam pitanja korisnika (pristup, čuvanje, AI, dokumenti, izvoz, brisanje, uloge), tabela dobavljača, pošteno poređenje sa opštim AI asistentom, „Šta je dobro da znate“ (bez sertifikacije, bez backup-a, evidencija nije potpuna) |
| `/beta` | „Prijava za beta testiranje“ | „Prijavi se za rani pristup Vindexu“; svrha i dalje glasi „uključivanje u beta testiranje“ (isto kao u Politici privatnosti, `#beta-prijava`) |
| V2 aplikacija | nema ulaza za prijavu problema (legacy ga ima) | stalno dugme dole desno → dijalog „Prijavi problem ili pošalji predlog“ (samo prijavljen korisnik, LIVE) |
| `POST /api/support/poruka` | uvek `ok:true` i „Odgovorićemo u roku od 24h“; neuspeo upis tiho progutan (`logger.debug`) | `ok:true` samo ako je poruka sačuvana ili predata SMTP-u; inače 503; odgovor kaže `sacuvano`, `obavesteno` i `broj`; zaglavlje emaila bez prelaza reda; ruta je u `shared/idempotency.py` |
| `GET /api/support/admin/lista` | — | osnivač vidi poslednjih 200 prijava (`FOUNDER_EMAILS`) |
| `/security`, `/bezbednosni-list` | „samouslužno dugme … nije izloženo / u pripremi“ | dugme „Obriši nalog“ postoji u Podešavanjima (`index.html:3472`, `obrisiNalogSelfService`); tekst usklađen sa kodom |

Pokret:
- ulaz hero dela, otkrivanje odeljaka pri skrolovanju (IntersectionObserver), hover kartica i sektora, strelica na pozivu, linija toka rada;
- samo CSS i postojeći `sajt.js`, bez biblioteka;
- bez JS-a i uz `prefers-reduced-motion` sve je odmah vidljivo (e2e „pokret“).

## 2. Dokaz za svaku tvrdnju početne

| Tvrdnja | Izvor u registru / kodu |
|---|---|
| kontekst predmeta, pitanje u kontekstu predmeta | A06, E01 |
| podatak vezan za dokument, protivrečnosti uz oba izvora | C02, C03, B04 |
| izvori uz odgovor, član koji ne postoji se odbija | E01 |
| rok, podaci, vrsta, nacrt važe tek posle odluke | J03, D01, B03, F02 |
| šta se promenilo, pažnja, sledeći korak | C04 |
| interni stavovi, odobreni nacrti, iskustvo | E05, G01, G02 |
| prijem više dokumenata, OCR ćirilica/latinica, pouzdanost | B01, B02, B04 |
| Danas: radna lista, 30 dana, nepotpuna lista označena | D03, D04 |
| samo predmeti naloga | J02 |

Nema procenata, ušteda vremena, broja korisnika, preporuka ni sertifikata. To čuvaju `tests/test_website_public.py` (ZABRANJENO, procenti, socijalna potvrda) i `tests/test_website_v3_rast.py`.

## 3. Prijava problema — ishod isporuke

| Stavka | Status |
|---|---|
| Tabela `support_tickets` postoji u produkciji (čitanje, 2026-10-21: 2 reda) | PROVEN |
| Upis prijave → broj prijave korisniku | PROVEN lokalno (pytest), produkcija posle deploya |
| SMTP u produkciji (`EMAIL_SMTP_*` na Render-u) | **UNKNOWN**: nema pristupa Render okruženju. Ako SMTP nije podešen, prijava se i dalje trajno čuva i korisnik dobija broj, a osnivač je vidi preko `/api/support/admin/lista` ili Supabase-a. Email obaveštenje tada ne stiže, i to se nigde ne tvrdi. |
| `FOUNDER_EMAILS` sadrži `benny13.n@gmail.com` | INFERRED (lokalni `.env`; produkcijska vrednost nije čitana) |

Poverljivost: dijalog šalje samo `kategorija`, `poruka` i `kontekst`. `kontekst` je naziv ekrana bez ID-a (`#/predmet/<id>/…` → „Predmet“). Bez snimka, bez sadržaja predmeta. Korisniku piše šta se šalje i da ne unosi podatke klijenata.

## 4. Adversarijalni prolaz

| # | Pitanje | Nalaz |
|---|---|---|
| 1 | Reklamira li početna nešto čega nema? | Ne. Svaka tvrdnja ima stavku registra (§2). „Brže do polazne tačke“ je uklonjena jer nije merena. |
| 2 | Sektori i sertifikacija ili spremnost? | Samo advokati su „Za ovo je Vindex napravljen“; ostali su „Moguća primena“, uz rečenicu da nema posebnih funkcija, odobrenja ni potvrde regulatora (test). |
| 3 | Roadmap preko stare rute ili asseta? | `/razvoj` → 301; nazivi K01/K02 nisu ni na jednoj stranici ni u `sajt.js`/`sajt.css`; `funkcije.json` nije serviran (404). **Ograničenje: repozitorijum `benny13n-creator/vindex-ai` je JAVAN**, pa su `site/funkcije.json`, `docs/website-v2/02_…` i istorija commitova sa planovima vidljivi na GitHub-u. Istorija nije menjana. |
| 4 | Poređenje sa ChatGPT-om? | Kaže šta opšti asistent ume (fajlovi, kontekst projekata). Ne tvrdi da je Vindex bezbedniji. Navodi da Vindex koristi OpenAI preko API-ja. |
| 5 | Bezbednosna tvrdnja protivna kodu? | Pronađena i ispravljena: `/security` i `/bezbednosni-list` su tvrdili da samouslužno brisanje ne postoji. |
| 6 | Pravni dokument krije činjenicu? | Ne. Politika privatnosti nije menjana; `/bezbednost` ponavlja servisni ključ, bez backup-a, SCC nije potvrđen, Pinecone segmenti. |
| 7 | Lažan uspeh widgeta? | Ruta je ispravljena (503 kada ništa nije sačuvano). UI: uspeh samo uz `ok:true`; 5xx, prekid, 401 i 429 imaju istinite poruke (e2e). |
| 8 | Curenje tuđih podataka? | Identitet je iz tokena; telo sa `user_id`/`email` se ignoriše (test); widget ne šalje ID predmeta. |
| 9 | Spam ili HTML? | 5/h po klijentu (postojeći limiter); HTML se escapuje; zaglavlje bez prelaza reda (test); ponovljen klik se pokriva idempotentnošću. Limiter po klijentu je zaobilazan lažnim `X-Forwarded-For` (poznato, cela platforma), ali ruta traži prijavu. |
| 10 | Pokret i čitljivost? | `prefers-reduced-motion` gasi sve; bez JS-a je sve vidljivo; e2e meri preliv, kontrast ≥ 4,5:1 i ciljeve ≥ 40 px na šest širina. |
| 11 | Zašto Vindex? | Prvi ekran: kategorija, korist, razlika (izvor i potvrda), jedan poziv i stvaran ekran. |
| 12 | Dodirnuta beta-kritična funkcija? | Ne. Izmene su sajt, ruta podrške, jedan red u listi idempotentnosti, novi V2 modul i dva reda u `app.js` (LIVE grana). |

## 5. Preostale nepoznanice

1. **SMTP u produkciji** (UNKNOWN). Prijava radi i bez njega (trajni upis), ali email osnivaču stiže samo ako je SMTP podešen. Provera posle deploya: jedna stvarna prijava iz aplikacije sa osnivačevog naloga.
2. **Javni repozitorijum** izlaže interne planove (§4, tačka 3). Rešenje je odluka osnivača (privatni repozitorijum), ne izmena koda.
3. Lokacija baze „EU (Frankfurt)“ preuzeta je iz Politike privatnosti (INFERRED), nije nezavisno merena.

## 6. CI ispravke na prvom HEAD-u (`584f1ed1`)

- **Security Checks:** 4 nova CVE-a u `pypdf 6.19.0` (CVE-2026-113792…113795, objavljeni posle poslednjeg zelenog CI-ja; nisu posledica ovog PR-a). `pypdf==6.20.1` je najmanja verzija sa ispravkama. 1050 lokalnih testova vezanih za PDF daju isti rezultat sa starom i novom verzijom; lokalni `pip-audit` je čist uz postojeće izuzetke. Novih izuzetaka nema.
- **Test Suite / Parity:** `test_bu007…::test_W5` je tražio svesnu proveru nove privilegovane rute `GET /api/support/admin/lista`. Ruta čita identitet samo iz `get_current_user` (verifikovan token) i poredi `user.get("email")` sa `FOUNDER_EMAILS`, bez ulaza iz tela ili upita. Broj je zato podignut sa 62 na 63, uz obrazloženje u testu. To je bio jedini pad u 11.676 testova.


## 7. Novi logo (odluka osnivača 2026-10-21)

- Logo A2 („Heritage Crest“) je izdvojen 1:1 iz slike osnivača (`scripts/brand/izdvoji_logo.py`); uklonjena je samo papirna pozadina. Prethodna precrtana verzija je odbijena i uklonjena.
- Svetla verzija: originalne boje. Tamna verzija: iste linije, V i slova u boji kosti, stub i lovor u zlatu.
- Zamenjeno: zaglavlje sajta, V2 gornja traka (obe teme), stara aplikacija (javna strana, bočna i mobilna traka), portal za klijente, stranica statusa, favicon i PWA ikone (`*-v4.png`), manifest, `sw.js` v162.
- Izvorni logo je 357×305 px, pa se prikazuje samo umanjen (najviše 48 px visine), da se pikseli ne vide.
- **Security Checks na `f74309bf`:** novi CVE-2026-113786 u `pypdf 6.20.1` (objavljen posle prethodnog zelenog CI-ja). `pypdf==6.21.1`; 1049 lokalnih testova vezanih za PDF/OCR/prijem prolazi, lokalni `pip-audit` čist uz postojeće izuzetke.
