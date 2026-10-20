# 04 — Adversarijalni pregled javnih tvrdnji (Website V2)

Za svaku značajnu tvrdnju postavljeno je osam pitanja:

1. Kod postoji?
2. UI ga poziva?
3. Radi u trenutnom V2 toku?
4. Zavisi od paketa, dozvole ili konfiguracije?
5. Menja li ograničenje značenje rečenice?
6. Dokaz u produkciji ili samo lokalno?
7. Odobren plan?
8. Može li korisnik pogrešno da razume obećanje?

Rečenica koja ne prođe se preformuliše ili uklanja. Za postizanje tačnosti tvrdnje nije implementirana nijedna nova funkcija.

Nivo dokaza:
- **P** — produkcija, čitanje 2026-10-20;
- **CI** — automatski test na istom kodu;
- **K** — čitanje koda.

## A. Tvrdnje koje je pregled oborio ili suzio (ispravljeno pre predaje)

| # | Prvobitna rečenica | Šta je obara | Ishod |
|---|---|---|---|
| R-1 | „Vindex ne računa procesne rokove“ (`/kako-radi`, D01) | `routers/rokovi_lanac.py` i `POST /api/rokovi/procesni` (`routers/zastarelost.py`) računaju lanac procesnih rokova (legacy) | uklonjeno. Nova stavka D10 (LEGACY_ONLY, nije javna dok se ne proveri tačnost pravila). Tekst: „Predloženi rok potiče iz pročitanog dokumenta“. |
| R-2 | „Nalozi se otvaraju pojedinačno… nalog se ne otvara automatski“ (`/beta`, J01) | `POST /api/register` odmah pravi potvrđen nalog sa 15 kredita (K; ruta postoji u produkciji) | `/beta` sada kaže da prijava ne otvara nalog, a da se nalog može otvoriti i samostalno. J01 dopunjen. |
| R-3 | „Aplikacija se razvija i testira sa ograničenim brojem naloga“ (`/`) | isto (R-2); broj naloga nije ograničen | „Aplikacija se razvija i testira.“ |
| R-4 | „obrada je opisana u Politici privatnosti“ (`/beta`) | `privacy.html` ne pominje prijave za beta ni listu čekanja | uklonjeno. Navodi se samo šta se čuva i zašto. Nalaz L-01. |
| R-5 | Natpisi snimaka bez „izmišljeni podaci“ (`/`, `/kako-radi`) | test `test_svaki_snimak_je_oznacen_kao_demonstracioni` je pao | svaki natpis nosi „Demonstracioni prikaz“ i „Podaci su izmišljeni.“ |
| R-6 | Poruka uspeha beta forme iz servera („Vaš nalog je već aktivan“) | otkriva stanje naloga za proizvoljnu adresu (W-01) | sajt prikazuje sopstven neutralan tekst za svaki `ok:true` |

## B. Pregled po rizičnim oblastima

| Oblast | Tvrdnja na sajtu | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 — rizik pogrešnog razumevanja i odgovor |
|---|---|---|---|---|---|---|---|---|---|
| Pravni izvori i citati | Odgovor navodi propise; nepostojeći član se odbija; bez izvora se kaže (E01) | da | da | da | `ai_pravna_pitanja` (basic); krediti | da: obuhvat baze | CI (verify:live-pitanje), produkcioni korpus nije meren ovim radom | — | „Navodi izvore“ bi se moglo shvatiti kao potpunost; zato „Baza propisa nije potpuna i ne zamenjuje službena glasila“. Broj zakona i brzina se ne navode. |
| Savetnici | Status provere citata uz svaki odgovor (E02) | da | da | da | `multi_agent` (professional) | da | CI | — | Niz „Od istraživanja do nacrta“ je isključen (E03) i ne pominje se. |
| Rokovi | Predloženi rok čeka potvrdu; potvrda nije provera tačnosti (D01) | da | da | da | `rokovi` (basic) | da | CI + izolovani PG (VCR002 B9) | — | Sajt izričito kaže da Vindex danas ne šalje podsetnike (C-09). |
| Podsetnici | samo `/razvoj`, K02 „Nije dostupno“ | kod da | ne (V2) | ne | — | — | P: `email-cron` 2026-10-20 = failure; 0 profila | B10 / VCR002: BLOCKED_AUTHORITY | Ne pojavljuje se kao dostupno nigde (test `test_nijedna_neobjavljiva_funkcija_nije_na_sajtu`). |
| NS4 znanje kancelarije | Iskustvo samo iz vašeg rada; nova kancelarija počinje praznim prikazom (G01, G02) | da | da | da | `firm_memory` (professional) | da | P: migracije 138–140 primenjene; tabele imaju 0 redova; CI pravi PostgreSQL | — | Nigde se ne tvrdi da je Vindex „učio“ iz predmeta niti da je vrednost potvrđena. Registar beleži: „vrednost nije empirijski potvrđena“. |
| AI rezultati | AI analiza je uvek označena; nije procena ishoda (C01, C05) | da | da | da | `case_dna` (professional) | da | CI | — | Procena šanse u procentima (C07) je odbačena i ne pominje se. |
| Elektronske fakture | Nacrt fakture nije izdata faktura i ne prijavljuje se u SEF (I03) | da | da | da | `finansije` | da | P: 0 faktura, 0 SEF podešavanja | — | SEF (I05) = UNVERIFIED, ne pominje se kao mogućnost. |
| Pristup | Server vraća samo predmete naloga (J02) | da | da | da | — | da: servisni ključ | CI (live-isolation, e2e:fastapi) | — | Sajt ne tvrdi da je „baza“ granica (test zabranjuje „na nivou baze“). |
| Šifrovanje | Originali iz prijema i tri polja klijenta (J05, J06) | da | — | — | — | da: izdvojeni tekst nije šifrovan | K | — | „AES-256 svih podataka“ je uklonjeno. Za ostalo se kaže da važi zaštita pružaoca infrastrukture, koju ovaj rad nije nezavisno proverio. |
| Roadmap | Samo K01, K02 | — | — | ne | — | — | — | K01: VCR001 R3 (aktivacija traži odluku); K02: A018 B10 | Bez datuma; obe „Nije dostupno“; ostalo izričito nije plan. |
| Prijava za beta | Jedna forma, poštene poruke za uspeh, grešku servera, validaciju i prekid veze | da | da | — | — | — | CI e2e (6 ishoda); P: 0 prijava, tok nikad korišćen u produkciji | — | Posle puštanja treba jedna kontrolisana prijava osnivača kao smoke (plan u `05_RELEASE_EVIDENCE.md`). |
| Snimci | Stvarni V2 ekrani, izmišljeni podaci | da | — | — | — | — | izvedeni iz koda na `77733e11` | — | Nema AI odgovora, presuda, OCR rezultata ni stvarnih klijenata. Svaki snimak je označen. |

## C. Nalazi za odluku osnivača (nisu menjani ovim radom)

| ID | Nalaz | Dokaz | Uticaj na javnu tačnost | Najmanja odluka |
|---|---|---|---|---|
| **S-01** | `/security` i `/bezbednosni-list` sadrže tvrdnje koje ovaj rad nije potvrdio. Primeri: „U mirovanju AES-256 — Supabase PostgreSQL, Storage, backupi“; „Dokumenti klijenata se enkriptuju AES-256-GCM na nivou aplikacije“ (tačno samo za prijem); odeljak „Sertifikati i usklađenost“; „RBAC, RLS“ u DPA. | GET produkcije; čitanje koda | Sajt ih više ne linkuje iz navigacije. Stranice ostaju dostupne (mandat: pravne stranice netaknute) i u sitemap-u. | pravna i bezbednosna revizija ta dva dokumenta i DPA, ili odluka da se uklone iz sitemap-a |
| **W-01** | `POST /waitlist/prijava` za postojeću adresu vraća „Vaš nalog je već aktivan“ ili „Već ste na listi“, pa svako može da proveri stanje proizvoljne adrese. | `routers/waitlist.py` | Sajt to ne prikazuje, ali API odgovara. | jedna neutralna poruka u backend-u (mala izmena, van obima ovog rada) |
| **W-02** | Ruta prijave nema sopstveno ograničenje broja zahteva i ne beleži saglasnost. | `routers/waitlist.py` | — | limiter + odluka o pravnom osnovu obrade prijava |
| **L-01** | Politika privatnosti ne pominje prijave za beta testiranje. | `privacy.html` | Sajt ne tvrdi da je ova obrada opisana. | dopuna politike privatnosti |
| **R-01** | Samostalna registracija je otvorena (15 kredita, bez potvrde adrese), dok je proizvod u „kontrolisanom“ beta testiranju. | `api.py::register` | Sajt to kaže tačno (C-21). | da li registracija ostaje otvorena |
| **E-01** | Pravni dokumenti navode adrese `@vindex.ai` (privacy, legal, security, support). Isporuka na te adrese nije proverena. | grep pravnih stranica | Sajt ne navodi kontakt adresu; jedini kontakt je forma. | potvrda da adrese primaju poštu |
| **T-01** | Kanonska pravila navode Source Sans 3 i JetBrains Mono, a V2 koristi IBM Plex Sans. | `tokens.css` | Sajt prati V2. | potvrda tipografije |
| **O-01** | Legacy `/sw.js` bez mreže može prikazati keširanu stariju javnu stranicu ili legacy `/offline`. | `static/sw.js` | samo bez mreže; postojeće ponašanje | nijedna (prihvaćen rizik) ili isključenje javnih ruta iz SW-a |
| **D-01** | Modal registracije (legacy) i dalje kaže „15 besplatnih upita odmah po registraciji“ i „Bez automatske naplate“. Tačno po kodu (15 kredita, naplata ne postoji), ali je komercijalna formulacija. | `index.html` | nije deo sajta | potvrda da tekst ostaje |

## D. Šta ovaj pregled NE tvrdi

- Prijavljena produkcija nije proverena funkciju po funkciju: nema QA naloga u produkciji. Statusi „Dostupno“ počivaju na CI/E2E dokazima nad istim kodom i na produkcionim čitanjima gde su navedena.
- Nijedna funkcija nije potvrđena radom stvarnih advokata na stvarnim predmetima (VCR002: nijedan zahtev nema nivo REAL_USER_ACCEPTED).
