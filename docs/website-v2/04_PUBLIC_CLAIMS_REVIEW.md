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

## E. Završna remedijacija istinitosti (2026-10-20, posle direktive osnivača)

Pravilo: dokazan problem → najmanja ispravka → ciljani dokaz. Menjani su samo sporni segmenti; dizajn, stranice, katalog i registar od 67 funkcija nisu dirani. Svaka stavka ispod ima test u `tests/test_website_v2_remediacija.py`, koji je pre ispravke pao (RED), a posle prošao (GREEN).

### E.1 Ispravljene javne tvrdnje

| # | Dokument | Original | Problem | Dokaz | Nova formulacija | Preostalo ograničenje |
|---|---|---|---|---|---|---|
| P-01 | `/privacy` | „Backup: Dnevni automatski backup sa 30-dnevnim rokom čuvanja“; red „Backup — 30 dana (rolling)“ | aktivni Supabase plan je Free i nema automatske backup-e | Supabase Dashboard (osnivač, direktiva §4.A) | „aktivni plan baze (Supabase Free) ne uključuje automatske backup-e. Vindex trenutno nema potvrđen sistem automatskog backup-a i ne obećava rok oporavka podataka.“ | stvaran rizik gubitka podataka ostaje; to je poslovna odluka, ne tekst |
| P-02 | `/security` §6, §11, §14.3; §3 | tabela backup-a (dnevno/30 dana, PITR 7 dana, S3 versioning 90 dana), RTO 4 h / RPO 24 h, „Backup baze 30 dana“, „backup kopije… max 30 dana“, „AES-256 … backupi“ | isto kao P-01; PITR i S3 versioning nisu potvrđeni | isto | §6 je jedna rečenica: plan ne uključuje automatske backup-e ni PITR; Vindex ne objavljuje frekvenciju, rok, RPO ni RTO. Redovi u §11 i §14.3 kažu da backup ne postoji. | `docs/security/DISASTER_RECOVERY_PLAN.md` (interni) i dalje navodi ciljeve RPO/RTO kao *policy target*; nije javan |
| P-03 | `/dpa` Aneks B; `/security` §5.2 i §9; `/privacy` (OpenAI, Pinecone); `/ai-disclosure` | „✓ DPA potpisan“, „✓ SCC potpisan“, „SCC su potpisani“, „Ugovor: EU SCC“, „SAD — EU SCC garancije“, „primenjuju se sledeće zaštitne mere: … SCC“ | nijedan potpisan DPA ni SCC nije predočen | pretraga repozitorijuma i dokumentacije: nema ugovora | status „Nije potvrđeno“; „zaključenje standardnih ugovornih klauzula (SCC) … nije potvrđeno“; u DPA: SCC je *predviđeni* mehanizam, zaključenje nije potvrđeno | **odluka/dokaz osnivača (F.2)**; ugovorne obaveze DPA nisu menjane |
| P-04 | `/privacy`, `/security` §4, `/bezbednosni-list` | „RLS — svaki korisnik pristupa isključivo sopstvenim podacima na nivou baze“; „čak i direktan DB pristup ne može da vrati tuđe podatke“; „greška u aplikativnom kodu ne može izložiti tuđe podatke“; „Svaki red u svakoj tabeli sadrži user_id“ | backend koristi servisni ključ koji zaobilazi RLS | `docs/security/PUBLIC_SECURITY_CLAIMS.md` Lista B (SEC-004); registar J02 | granicu sprovodi provera na serveru pri svakom zahtevu; servisni ključ ne podleže RLS-u; RLS ne štiti od greške u serverskom kodu | — |
| P-05 | `/bezbednosni-list`, `/security` §3, `/privacy`, `/dpa` | „Dokumenti klijenata se enkriptuju AES-256-GCM na nivou aplikacije“; „AES-256 (Supabase)“ bez obuhvata | fajlovi iz klijentskog portala (`portal-uploads`) se ne šifruju; izdvojeni tekst nije šifrovan | `docs/security/CLIENT_PORTAL_UPLOAD_FORENSICS.md`; `routers/client_portal.py`; registar J05 | šifruju se (AES-256-GCM) originalni fajlovi koje advokat otpremi u predmet (otpremanje, prijem dokumenata, trezor klijenta) i JMBG/pasoš/PIB; izuzeti: izdvojeni tekst i fajlovi iz klijentskog portala. Šifrovanje u mirovanju na nivou baze pripisano je pružaocu, „prema njegovoj dokumentaciji“. | šifrovanje portala nije ispravljeno (van obima) |
| P-06 | `/bezbednosni-list` | „Lozinke se čuvaju isključivo kao Argon2id heš“ | Argon2id nema nijedno pozivno mesto; lozinke drži Supabase Auth | `security/crypto.py` (SEC-023); Lista B | „Lozinkama za prijavu upravlja Supabase Auth; aplikacioni server ih ne čuva.“ | — |
| P-07 | `/bezbednosni-list` | JMBG/pasoš/PIB „na nivou baze podataka“ | šifruje se na nivou aplikacije pre upisa | `klijenti/router.py`, `security/crypto.py` | „na nivou aplikacije, pre upisa u bazu“ | — |
| P-08 | `/privacy` | „Zaposleni Pružaoca usluge nemaju pristup sadržaju predmeta“; „operativni pristup … uz obavezno evidentiranje u audit logu“ | administrator ima tehnički pristup preko konzola pružalaca; taj pristup ne beleži audit aplikacije | servisni ključ / Supabase konzola | tehnički pristup ima ovlašćeni administrator; koristi se samo za incident ili kritičnu grešku; ne beleži ga audit log aplikacije | — |
| P-09 | `/privacy`, `/dpa`, `/security` §7.1 | „Sve kritične operacije se beleže“; „Audit logging svih pristupa podacima“; „Svaki pristup production bazi … se beleži“ | audit postoji samo za određene operacije | `klijenti/router.py` (VIEW_CONFIDENTIAL), `routers/data_export.py`, `routers/gdpr.py` | „određene osetljive operacije (uvid u šifrovane identifikatore klijenta, potpun izvoz podataka, brisanje naloga)“ | — |
| P-10 | `/dpa` | „Redovni bezbednosni pregledi i penetracioni testovi“ | penetracioni test ne postoji (`/security` §9: „U planu“) | registar J08 | „Interni bezbednosni pregledi izvornog koda“ | — |
| P-11 | `/dpa`, `/security` §2.1 | „Dvofaktorska autentifikacija (opciono)“; „Opciona 2FA putem Supabase TOTP“ | 2FA ne postoji ni u legacy ni u V2 interfejsu | grep `mfa/totp` u `static/vindex.js`, `frontend-v2-ng/src`, backend: 0 | uklonjeno | — |
| P-12 | `/security` §9 | GDPR „Usklađen“, ZZPL „Usklađen“ | nezavisna ocena ne postoji; DPA/SCC nepotvrđeni (zabranjena tvrdnja „Potpuno GDPR usklađeno“) | Lista B | „Nije nezavisno ocenjeno“ | — |
| P-13 | `/security` §1 | API server „Render.com (EU)“ (a `/privacy` kaže „SAD“) | region nije potvrđen; dokumenti protivreče | `render.yaml` bez regiona | „Render.com“ | region servera nije javno naveden |
| P-14 | `/privacy`, `/beta` | Politika ne opisuje beta prijavu | forma prikuplja 5 polja bez obaveštenja | `routers/waitlist.py` | novi odeljak `#beta-prijava`: podaci, svrha, pravni osnov, primaoci, čuvanje, prava i kanal; `/beta` linkuje na njega | pravni osnov je **predlog** (F.3); čuvanje opisuje stvarno stanje (bez automatskog brisanja) |
| P-15 | `/beta` (frontend), greška 5xx | „Prijava nije sačuvana zbog greške na serveru“ | posle prekida veze sa bazom upis je mogao uspeti, pa tvrdnja o sigurnom neuspehu nije tačna | `site/sajt.js` | „Server nije potvrdio prijavu (kod). … ponovno slanje je bezbedno.“ | — |

Dokumenti nose oznaku „ispravke činjenica 2026-10-20“ uz postojeću verziju. Nijedna obaveza iz DPA ili Uslova nije dodata ni uklonjena, osim dve netačne stavke na listi mera (P-10, P-11) i statusa ugovora (P-03).

### E.2 Beta prijava (P0-B)

| Pitanje | Pre | Posle | Dokaz |
|---|---|---|---|
| Otkrivanje stanja adrese | tri poruke: nova / „Već ste na listi“ / „Vaš nalog je već aktivan“ | jedna: `{"ok": true, "poruka": "Prijava je evidentirana."}` za svaki ishod, iste dužine | `test_poznata_adresa_dobija_isti_odgovor_kao_nova[pending/contacted/active]`, `test_odgovor_ne_sadrzi_reci_o_nalogu_ili_listi` |
| Džoker u adresi | `ilike` → `a_b@x` pogađa `axb@x`; nova prijava se ne čuva | `eq` nad sačuvanim malim slovima | `test_dzoker_u_adresi_ne_pogadja_tudju_prijavu` |
| Istovremene prijave | drugi upis → `23505` → HTTP 500 | 23505 = isti neutralan odgovor; 1 red, 1 obaveštenje | `test_dve_istovremene_prijave_iste_adrese` (barijera garantuje da oba čitanja prođu pre upisa) |
| Nedostupna baza | 5xx | 5xx, nikad `ok:true`, nema obaveštenja | `test_nedostupna_baza_nije_uspeh[citanje/upis]` |
| Lični podaci u logu | ime i adresa u `logger.info` | log bez ličnih podataka | čitanje koda |
| Zloupotreba | globalni `SlowAPIMiddleware`, 60/h po klijentu | nepromenjeno (već efektivno; nije dodat dupli limit) | `test_globalni_limit_stize_do_forme…`: 61. zahtev → 429 JSON, odbijeni ne upisuju |

**Ograničenje zaštite od zloupotrebe (otvoreno, ne blokira):** ključ limita je krajnja leva vrednost `X-Forwarded-For` (`shared/rate.py::_get_real_ip`), koju klijent može sam da postavi. Lokalno izmereno: 61 zahtev sa različitim `X-Forwarded-For` → 61 × 200. Da li produkcioni lanac (Cloudflare → Render) prosleđuje zaglavlje klijenta, nije provereno, jer bi provera zahtevala zloupotrebu produkcije. Ovo važi za sve rute platforme, ne samo za formu. Bez Redis-a brojači su po procesu. Pošto odgovor više ne otkriva stanje adrese, zaobilaženje limita ne daje nabrajanje adresa. Ostaje mogućnost masovnog upisa različitih adresa (red u bazi + obaveštenje). Ispravka je odluka o pouzdanom zaglavlju (npr. `CF-Connecting-IP`) za ceo limiter; to je izmena van ovog obima.

**Konzistentnost:** prvo pokretanje testa istovremenih prijava (sa kašnjenjem umesto barijere) bilo je **lažno zeleno**: mutacija M10 (uklonjeno hvatanje 23505) je preživela, jer je prvi upis stizao pre drugog čitanja. Test je promenjen na barijeru, posle čega je M10 uhvaćena. Mutacije: M10 uhvaćena, M11 (`ilike` vraćen) uhvaćena, M12 (status u odgovoru) uhvaćena.

### E.3 Status nalaza iz odeljka C

| ID | Status posle remedijacije |
|---|---|
| S-01 | **zatvoren** za backup, DPA/SCC, RLS, šifrovanje, Argon2id, audit, pen test, 2FA, „usklađen“ (E.1). Otvoren samo za pravni identitet (F.1). |
| W-01 | **zatvoren** (E.2) |
| W-02 | limit: **dokumentovan**, efektivan po klijentu, uz ograničenje `X-Forwarded-For`. Saglasnost: ne uvodi se, jer predloženi osnov nije saglasnost (F.3). |
| L-01 | **zatvoren** tekstom (P-14); pravni osnov čeka potvrdu (F.3) |
| E-01 | **delimično**: `vindex.ai` ima MX zapise (Fastmail), `vindex.rs` nema MX. Da li osnivač prima poštu na `privacy@vindex.ai` nije potvrđeno (F.4). |
| R-01, T-01, O-01, D-01 | nepromenjeno (van obima direktive) |

## F. Jedan konsolidovan zahtev osnivaču (FOUNDER LEGAL IDENTITY CONFIRMATION REQUIRED)

Ovo su jedine činjenice koje agent ne sme da izmisli. Sve ostalo je završeno i ne zavisi od njih.

| # | Dokument i sporna tvrdnja | Zašto je neophodno | Šta je završeno bez toga | Šta ne sme biti objavljeno dok je UNKNOWN |
|---|---|---|---|---|
| **F.1** | `/privacy` („Rukovalac … je: Vindex d.o.o., Beograd“), `/terms` („pravni odnos između Vindex d.o.o. …“), `/dpa` („Obrađivač: Vindex d.o.o.“), `/security` §12, `/bezbednosni-list` podnožje, modal uslova u `index.html` | Rukovalac i ugovorna strana moraju biti stvarno lice. U repozitorijumu nema dokaza da „Vindex d.o.o.“ postoji (nema PIB-a, MB-a ni izvoda iz APR-a). | sve ispravke E.1/E.2 | spajanje ovog PR-a kao „zatvoreno“; tekst ostaje nepromenjen, jer agent ne izmišlja firmu i ne briše ime. **Treba:** tačan pravni naziv, sedište, MB i PIB, ili potvrda da operater nije registrovano pravno lice (tada: ime i prezime operatera / preduzetnika i adresa). |
| **F.2** | `/dpa` Aneks B i odeljak o prenosu, `/privacy`, `/security` §5.2/§9, `/ai-disclosure`: status DPA i SCC sa Supabase, OpenAI, Pinecone i Render | Tvrdnja „potpisan“ zahteva ugovor. | tekst sada kaže „Nije potvrđeno“, što je tačno | ništa dodatno: tekst je već bezbedan. Ako postoje prihvaćeni DPA (npr. kroz podešavanja naloga dobavljača), dostavite ih i status se menja u „Zaključen (datum)“. |
| **F.3** | `/privacy#beta-prijava`, „Pravni osnov: preduzimanje radnji na vaš zahtev pre zaključenja ugovora (čl. 12 st. 1 tač. 2 ZZPL; čl. 6 st. 1 tač. b GDPR)“; čuvanje: „automatsko brisanje ne postoji; prijava se čuva dok je ne obrišemo na vaš zahtev“ | Pravni osnov i rok čuvanja određuje rukovalac, ne agent. **Ovo je predlog AI pregleda, nije pravno mišljenje.** | tekst opisuje stvarno ponašanje sistema | potvrdite ili zamenite ove dve rečenice. Ako želite rok (npr. brisanje N meseci posle kraja beta perioda), to je nova operativna obaveza bez automatske podrške u kodu. |
| **F.4** | `privacy@vindex.ai` (Politika, DPA, Bezbednosni list, AI Disclosure) kao kanal za ostvarivanje prava; `legal@`, `security@`, `support@vindex.ai` | Kanal za prava mora stvarno primati poštu. DNS: `vindex.ai` MX → messagingengine.com (Fastmail); `vindex.rs` nema MX. | — | potvrda da `privacy@vindex.ai` stiže u sanduče koje čitate (jedna probna poruka). U suprotnom treba navesti adresu koja radi. |
| **F.5** | `/privacy` „Izmene … uz pisano obaveštenje Korisnika najmanje 14 dana unapred“ | Ove ispravke menjaju tekst Politike. Većinom su to ispravke netačnih činjenica (bez novih obaveza za korisnika), uz novi odeljak o beta prijavi. | — | odluka da li postojeće korisnike obaveštavate pre objavljivanja. Predlog: ispravke činjenica ne smatrati izmenom koja zahteva rok od 14 dana; o tome odlučuje osnivač. |

Uz to je potrebno i **odobrenje za javno objavljivanje** ovog teksta (direktiva §11.5). Merge se ne radi bez njega.

## G. Night Sprint V — završna istinitost i bezbednost (2026-10-21)

Osnivač je potvrdio: **Vindex AI je naziv proizvoda i brenda; Benjamin Nađ je osnivač; registrovano pravno lice „Vindex d.o.o.“ ne postoji.** Privatni poslovni status osnivača se ne objavljuje.

### G.1 Ispravke

| # | Dokument | Original | Problem | Dokaz | Nova formulacija | Preostalo |
|---|---|---|---|---|---|---|
| N-01 | `/privacy`, `/terms`, `/dpa`, `/security` §12, modal uslova i privatnosti u `index.html` (`/app-legacy`) | „Vindex d.o.o.“ kao rukovalac, pružalac i obrađivač; „Beograd, Republika Srbija“; „Sedište: Srbija“ | pravno lice ne postoji | izjava osnivača (Night Sprint V §5.1) | „Benjamin Nađ, osnivač Vindex AI“; mesto i sedište uklonjeni (nisu potvrđeni) | da je osnivač rukovalac i ugovorna strana, sledi iz toga što drugog lica nema; **potvrda osnivača tražena u §H** |
| N-02 | `/bezbednosni-list` podnožje | „Vindex d.o.o. · Srbija“ | isto | isto | „Vindex AI“ (brend u podnožju, ne ugovorna strana) | — |
| N-03 | `/privacy` (Pinecone), red čuvanja | „Numeričke vektorske reprezentacije … — ne originalni tekst … nisu … pogodni za rekonstrukciju“; „Embeddings — dok je nalog aktivan“ | `uploaded_doc/ingest.py:165` upisuje `"text": text_stored` (do 40.000 znakova) u metapodatke; `routers/batch_ingest.py:96` takođe (sudske odluke) | kod | vektori **i tekstualni segmenti** dokumenta; originalni fajl se ne šalje; segmenti nisu dodatno šifrovani; „Poseban rok nije utvrđen; brisanje naloga ih ne briše“ | lokacija „SAD (us-east-1)“ i „izolovano po korisniku“ nisu menjani (nisu deo nalaza) |
| N-04 | `/security` §5.3, §14.3 | „Čuvaju se isključivo matematički vektori, ne originalni tekst“; „dok su predmeti aktivni … prati status predmeta“ | isto; brisanje nije dokazano | isto | tekstualni segmenti se čuvaju kao metapodatak; „Zadržavaju se; brisanje naloga ih ne briše — poseban rok nije utvrđen“ | — |

Nijedan javni tekst ne navodi privatni status osnivača, ne tvrdi da je pravno lice „registrovano“ i ne navodi MB, PIB ni sedište.

### G.2 Beta forma

- **HTML obaveštenje:** ime, adresa, kancelarija, telefon i poruka ulazili su u HTML e-poruku bez escapovanja. Sada su escapovani (`html.escape`), a naslov nema prelaz reda. Test je uhvatio i stvaran kvar sopstvene ispravke: lokalna promenljiva `html` prekrivala je istoimeni modul, pa se obaveštenje ne bi poslalo. Ispravljeno je preko `import html as _html`.
- **Zloupotreba (G11):** ključ limita po klijentu je krajnja leva vrednost `X-Forwarded-For`, koju klijent sam bira. Lokalno je dokazano da se zaobilazi promenljivim zaglavljem. Produkcioni proxy lanac nije ispitan, jer bi ispitivanje zahtevalo masovne zahteve prema produkciji; neautorizovane rute sa niskim limitom ne služe kao sonda, jer prijava odbija zahtev pre brojanja.
  - Zato ruta sada ima **ukupnu granicu koja ne zavisi od zaglavlja: 20 na sat i 100 na dan za sve klijente**, plus 10 na sat po klijentu.
  - Brojač je u Redis-u; produkcija `/health` prijavljuje `"redis": true` i `"workers": 1`.
  - Lažni upisi su time ograničeni na najviše 100 dnevno, umesto da budu neograničeni.
  - Cena: kada je granica dostignuta, i legitimna prijava dobija 429, a sajt kaže „Server nije potvrdio prijavu (429). Pokušajte ponovo kasnije“. Do sada je tabela `waitlist` u produkciji imala 0 redova.
  - Globalni limiter (sve ostale rute) nije menjan.

### G.3 Pillow

`pillow` 12.3.0 → 13.0.0, jedina objavljena verzija sa ispravkama za 8 CVE-ova (`requires_python >=3.11`; postoje točkovi za cp311 i cp313).
- Napomene o izdanju (nekompatibilne izmene: I-mode PNG, `get_child_images`, `Image._show`, `ImageCms.product_*`, `ExifTags.IFD.Makernote`): nijednu Vindex ne koristi (grep).
- Lokalno, u izolovanom venv-u (Python 3.13), isti skup od 91 test-fajla vezanog za slike i OCR daje isti rezultat sa 12.3.0 i 13.0.0: 2278 prošlo, 3 ista poznata lokalna pada (`test_faza1_pristupacnost`).
- Lokalni `pip-audit -r requirements.txt` sa postojeća dva izuzetka: „No known vulnerabilities found“.
- Python 3.11, Docker build i OCR u produkcionoj slici (Tesseract, Poppler, srpski paketi) dokazuje CI (05 §9).

### G.4 Mutacije

| ID | Mutacija | Rezultat |
|---|---|---|
| M13 | uklonjena ukupna granica | uhvaćena (`test_lazni_x_forwarded_for_ne_zaobilazi_ukupnu_granicu`) |
| M14 | vraćeno sirovo ime u HTML | uhvaćena (`test_obavestenje_escapuje_unos_sa_forme`) |
| M15 | vraćeno „ne originalni tekst“ | uhvaćena |
| M16 | vraćeno „Vindex d.o.o.“ u Uslove | uhvaćena |

## H. Release gate — šta samo osnivač može da zatvori

Kod je završen; ovo su jedine preostale nepoznanice. Ne objavljuju se dok nisu razrešene.

| # | Činjenica | Zašto blokira | Dokaz koji nedostaje | Šta je urađeno do tada |
|---|---|---|---|---|
| H.1 | **`privacy@vindex.ai` radi i domen je Vindexov** | Kanal za prava lica mora primati poštu. `vindex.ai` je registrovan 2023-01-10, tri godine pre prvog commita projekta (2026-03-29); vlasnik je sakriven (Withheld for Privacy, registrar Namecheap). MX zapisi vode na Fastmail. `vindex.rs` nema MX. | jedna probna poruka na `privacy@vindex.ai` koju je osnivač primio, ili druga adresa koju osnivač stvarno čita | ništa nije izmišljeno; adresa nije menjana |
| H.2 | **Osnivač je rukovalac podataka i ugovorna strana** | Nema pravnog lica, pa je jedino stvarno lice osnivač. To je pravna kvalifikacija, ne izmišljen podatak; potvrditi je može samo on. | jedna rečenica potvrde | tekst već kaže „Benjamin Nađ, osnivač Vindex AI“ |
| H.3 | **Pravni osnov i rok čuvanja beta prijava** | Predloženi predugovorni osnov (ZZPL čl. 12 st. 1 tač. 2) nije potvrđen, a „do brisanja na zahtev“ nije rok. | odluka; predlog: „osnov: radnje na zahtev lica pre zaključenja ugovora; rok: prijava se briše 12 meseci posle prijema ako nalog nije otvoren“. Brisanje vrši administrator ručno, jer automatsko ne postoji. | tekst u grani je predlog i nije objavljen |
| H.4 | **Obaveštenje 14 dana pre izmene Politike** | Politika obećava korisnicima pisano obaveštenje 14 dana unapred. U produkciji postoji **141 profil** (čitanje, 2026-10-21). | odluka: (a) obavestiti i objaviti posle 14 dana, ili (b) objaviti odmah, jer većina izmena ispravlja netačne bezbednosne tvrdnje i ne uvodi nove obaveze, uz istovremeno obaveštenje | — |

Redosled ako osnivač izabere (b): merge → deploy → isti dan e-poruka korisnicima sa spiskom ispravki iz §E i §G. Netačne tvrdnje (backup, potpisani ugovori, RLS, Pinecone, „Vindex d.o.o.“) i dalje stoje u produkciji dok se ovo ne spoji.


## I. Final Closure (2026-10-21) — odgovori osnivača i šta iz njih sledi

Osnivač je u mandatu „Final Closure Night Sprint“ potvrdio sledeće:
- rukovalac je za sopstvene podatke Vindexa (H.2 zatvoren);
- jedini domen koji poseduje je `vindex.rs`, a `vindex.ai` **nije njegov**;
- preporučeni osnov za beta prijavu je legitimni interes, a rok čuvanja šest meseci.

### I.1 Kontakt (A1)

| Činjenica | Dokaz | Status |
|---|---|---|
| Javne adrese `privacy@`, `legal@`, `security@`, `support@` i `kontakt@vindex.ai` su na tuđem domenu | izjava osnivača; `vindex.ai` registrovan 2023-01-10, sa sakrivenim vlasnikom i MX zapisom ka Fastmail-u | PROVEN (izjava) |
| U produkciji (`77733e1`) korisnici zahteve iz oblasti privatnosti i povratne informacije (legacy `mailto:kontakt@vindex.ai`) šalju na domen trećeg lica | `static/vindex.js`, `privacy.html`, `routers/gdpr.py` i ostali na `origin/main` | PROVEN |
| `vindex.rs` ima NS kod Cloudflare-a (`abby`/`jose.ns.cloudflare.com`) i **nema MX zapis** (2026-10-21, upit preko 8.8.8.8 vraća samo SOA) | `nslookup -type=MX vindex.rs 8.8.8.8` | PROVEN |
| `privacy@vindex.rs` i `kontakt@vindex.rs` mogu da prime poštu | — | **FAIL: adrese ne postoje, jer bez MX zapisa pošta na domen ne može da se isporuči** |

U grani su sve kontakt adrese zamenjene:
- **`privacy@vindex.rs`**: zaštita podataka, prava lica, DPA, beta prijava;
- **`kontakt@vindex.rs`**: Uslovi, podrška, bezbednosni incidenti, povratne informacije iz aplikacije, serverske poruke.

Zamena obuhvata 13 fajlova: pravne stranice, `index.html`, `static/vindex.js`, `static/status.html`, `routers/gdpr.py`, `routers/drafting.py`, `routers/data_export.py` i `scripts/dr_runbook.py`.
- `ics_export.py` zadržava `@vindex.ai` kao UID kalendarskog događaja. To nije adresa, a promena bi korisnicima duplirala događaje.
- „DPO kontakt“ u `/security` je promenjen u „Kontakt za zaštitu podataka“, jer lice za zaštitu podataka nije imenovano.

**FOUNDER ACTION: CONFIGURE AND VERIFY PRIVACY CONTACT ON VINDEX.RS**
1. Cloudflare → `vindex.rs` → Email → Email Routing → Enable. Cloudflare sam dodaje MX i SPF zapise.
2. Destination address: inbox koji osnivač čita; potvrditi link koji Cloudflare pošalje.
3. Routing rules: `privacy@vindex.rs` i `kontakt@vindex.rs` → taj inbox.
4. Iz drugog naloga poslati poruku na obe adrese i potvrditi da su stigle.
5. Odgovoriti na jednu od njih. Email Routing samo prima poštu: odgovor odlazi sa adrese inboxa, što je dovoljno za prijem i odgovor na zahteve.

Agent posle toga sam proverava MX zapis. Prijem poruke potvrđuje samo osnivač.

### I.2 Rukovalac i obrađivač (A2)

- Politika privatnosti: Benjamin Nađ je rukovalac **samo za podatke koje Vindex obrađuje u sopstvene svrhe**: nalog, beta prijave, komunikaciju i tehničke evidencije.
- Za podatke o klijentima, strankama i drugim licima u predmetima rukovalac je advokat ili kancelarija, a Vindex je obrađivač (čl. 45 ZZPL; čl. 28 GDPR). Odnos uređuje DPA, koji stupa na snagu potpisivanjem.
- Ovo samo usklađuje Politiku sa DPA, objavljenim od 2026-07-05 („Klijent (Rukovalac)“, „Obrađivač (Vindex AI)“), i sa definicijom rukovaoca kao lica koje određuje svrhu obrade (čl. 4 ZZPL).
- Iz DPA uklonjena je rečenica „Za poslovne korisnike sa godišnjom pretplatom DPA je standardni aneks“, jer pretplata ne postoji.
- **Usko pravno pitanje, ne blokira sajt:** da li je ijedan DPA zaista potpisan (UNKNOWN). Bez potpisanog DPA, obrada stvarnih podataka klijenata nema ugovor koji traži čl. 45 st. 3 ZZPL. Zato je REAL-DATA beta NO-GO (§J).

### I.3 Beta prijava: procena legitimnog interesa (A3)

| # | Pitanje | Odgovor |
|---|---|---|
| 1 | Konkretan i zakonit interes? | Da: razmotriti zahtev koji je lice samo poslalo i odgovoriti na njega. |
| 2 | Neophodno? | Da: bez imena i adrese nema odgovora. Telefon, kancelarija i poruka su neobavezni. |
| 3 | Manji obim podataka? | Obavezno je samo ime i adresa; ostalo je dobrovoljno. Manje od toga onemogućava kontakt. |
| 4 | Razumno očekivanje? | Da: lice popunjava formu „prijava za beta testiranje“, a stranica i Politika kažu šta se čuva i zašto. |
| 5 | Uticaj na prava? | Nizak: kontakt podaci profesionalca, bez posebnih kategorija, bez profilisanja i bez automatskog odlučivanja. Pristup ima samo administrator. |
| 6 | Prigovor? | Na `privacy@vindex.rs`. Prijava se posle prigovora briše (čl. 37 ZZPL). |
| 7 | Posebne kategorije, dodatni rizik? | Ne traže se. Slobodno polje „poruka“ može da sadrži bilo šta; ublaženo je rokom čuvanja i pristupom samo administratora. Kopija stiže e-poštom osnivaču, pa se i ona briše po roku. |
| 8 | Mere ograničenja | Rok od šest meseci; nema marketinga ni newslettera; nema sekundarne svrhe; ograničenje 10/h po klijentu i 20/h i 100/dan ukupno; neutralan odgovor bez otkrivanja postoji li adresa. |

**Zaključak (INFERRED, nije pravno mišljenje):** legitimni interes (čl. 12 st. 1 tač. 6 ZZPL; čl. 6 st. 1 tač. f GDPR) je odgovarajući osnov. Interes ne preteže nad pravima lica jer je obrada mala, očekivana i ograničena rokom. Raniji predlog „predugovorne radnje“ (tač. 2) je zamenjen; prijava nije nužno korak ka ugovoru.

### I.4 Čuvanje i postupak brisanja (A4, A5)

- **Čitanje, 2026-10-21:** tabela `waitlist` u produkciji ima **0 redova**. Nijedan postojeći zapis nije pogođen niti obrisan.
- **Pravilo (operativno, nije zakonski rok):**
  - nerešena prijava se briše najkasnije šest meseci od prijema;
  - posle otvaranja naloga briše se najkasnije za 30 dana;
  - briše se i ranije kod povlačenja, prigovora ili zahteva za brisanje.
- **Ko i kada:** osnivač, najmanje jednom u 30 dana (podsetnik u sopstvenom kalendaru).
- **Kako:**
  1. Supabase → Table Editor → `waitlist`.
  2. Izdvojiti redove gde je `created_at` stariji od **pet** meseci, ili `status = 'active'`. Prag od pet meseci, uz pregled svakih 30 dana, garantuje brisanje pre šest meseci.
  3. Za svaki red proveriti da li je u toku razgovor koji se odnosi baš na beta pristup. Ako jeste i lice to očekuje, red se zadržava do sledećeg pregleda, ali najviše do roka.
  4. Obrisati redove (Delete rows) i iz inboxa obrisati e-poruke „Vindex AI: nova prijava od …“ za iste osobe.
  5. U privatnu evidenciju (ne u repo i ne u bazu) upisati samo datum pregleda i broj obrisanih redova, bez imena i adresa.
- Automatsko brisanje se ne obećava. Cron, migracija i nova tabela nisu dodati, jer ručni postupak pouzdano pokriva sadašnji obim (0 redova, najviše 100 dnevno).
- Brisanje reda iz `waitlist` ne dira nalog. Nalog je u `auth.users` i `profiles`, a ne u ovoj tabeli.

### I.5 Rok od 14 dana (Faza B)

Klauzula u Politici glasi: „Pružalac usluge može izmeniti ovu Politiku uz pisano obaveštenje Korisnika najmanje 14 dana unapred.“ U Uslovima je ista obaveza („najmanje 14 dana pre primene izmena“). Nijedna klauzula nije uklonjena niti oslabljena; to proverava test `test_ispravke_su_vidljivo_oznacene`.

| Izmena | Klasa | Obrazloženje |
|---|---|---|
| backup, šifrovanje, RLS i servisni ključ, administrativni pristup, audit, Argon2id, 2FA, pen test | FACTUAL CORRECTION | obrada je i ranije bila takva; tekst ju je pogrešno opisivao |
| SCC/DPA „potpisani“ → „nije potvrđeno“ | FACTUAL CORRECTION | isto |
| Pinecone čuva tekstualne segmente | FACTUAL CORRECTION | `uploaded_doc/ingest.py:165` |
| „Vindex d.o.o.“ → Benjamin Nađ, osnivač Vindex AI | FACTUAL CORRECTION | subjekt ne postoji; ugovorna strana je uvek bilo isto lice |
| kontakt `@vindex.ai` → `@vindex.rs` | FACTUAL CORRECTION | stara adresa nije pružaočeva |
| rukovalac/obrađivač za podatke klijenata | FACTUAL CORRECTION | usklađeno sa DPA koji važi od 2026-07-05 i sa čl. 4 ZZPL; prava korisnika se ne smanjuju |
| odeljak o beta prijavi (osnov, rok, prigovor) | nova informacija, ne izmena postojećeg odnosa | važi za nove prijave; postojećih prijava nema (0 redova); nijednom korisniku se ništa ne menja |
| Uslovi: „naplata nije uvedena“; odeljak o pretplati važi tek uz naplatu | FACTUAL CORRECTION | cenovnik i naplata ne postoje (`api.py`: `/pricing` uklonjen, `STRIPE_URL` prazan); niko nije platio |

Nijedna izmena nije MATERIAL CHANGE ni UNCERTAIN LEGAL EFFECT. Zato se ispravke objavljuju odmah, a ne posle 14 dana:
- one ne menjaju obradu niti obaveze, već istinito opisuju postojeće stanje;
- odlaganje bi značilo svesno objavljivanje netačnih informacija još 14 dana (čl. 5 i čl. 23 ZZPL). Uključujući i to da korisnici zahteve šalju na tuđi domen.

Klauzula o 14 dana štiti od nepovoljnih budućih izmena, a ispravka ne može „stupiti na snagu kasnije“ jer je stvarno stanje već takvo. (INFERRED; nije pravno mišljenje.)

Uslovi ispunjenja:
- Datum je vidljiv („Ispravke od 2026-10-21“ na `/privacy` i `/terms`).
- Prethodna verzija je sačuvana: produkcioni tekst je na `77733e11` (`git show 77733e11:privacy.html` itd.) i dostavlja se na zahtev, kako Politika i kaže.
- **Pisano obaveštenje istog dana:** nacrt je u I.7. Šalje ga osnivač, ne agent.

**Postojeći nalozi (čitanje, agregat, bez ličnih podataka):**
- 141 nalog u `auth.users`;
- 130 adresa po obrascu testnog ili sintetičkog naloga (`test`, `qa`, `demo`, `e2e`, `vindex.rs` i slično);
- 11 ostalih: 2 sa prijavom u poslednjih 90 dana, 8 starijih, 1 nepotvrđena bez prijave.

Klasifikacija po obrascu je INFERRED. Konačan spisak primalaca utvrđuje osnivač u Supabase-u; spisak se ne čuva u repou.

### I.6 Predlog trajnog pravila (B4)

Predlog nije primenjen. Usvajanje bi menjalo samu klauzulu o 14 dana, pa bi i ono tražilo prethodno obaveštenje.

> Izmene ove Politike koje menjaju svrhu ili pravni osnov obrade, rokove čuvanja ili vaša prava objavljujemo i šaljemo vam e-poštom najmanje 14 dana pre primene. Ispravke netačnih ili zastarelih činjeničnih navoda, koje ne menjaju obradu, objavljujemo odmah, sa datumom i opisom ispravke, i o njima vas obaveštavamo e-poštom. Novu svrhu obrade ne započinjemo pre nego što vas o njoj obavestimo i, kada je to potrebno, pribavimo vaš pristanak. Izmene ne deluju unazad i ne umanjuju prava u vezi sa već prikupljenim podacima.

### I.7 Nacrt obaveštenja korisnicima (ne šalje se automatski)

> Naslov: Vindex AI — ispravke Politike privatnosti i Uslova korišćenja
>
> Poštovani,
>
> obaveštavamo vas da smo 2026-10-21 ispravili netačne navode u Politici privatnosti i Uslovima korišćenja. Način na koji Vindex obrađuje vaše podatke nije promenjen; tekstovi sada tačno opisuju stvarno stanje:
> - baza podataka trenutno nema automatske backup-e;
> - standardne ugovorne klauzule (SCC) sa dobavljačima u SAD nisu potvrđene;
> - u Pinecone-u se, uz vektore, čuvaju i tekstualni segmenti dokumenata;
> - opseg šifrovanja i kontrole pristupa opisan je tačno;
> - pružalac usluge je Benjamin Nađ, osnivač Vindex AI; naplata nije uvedena;
> - za podatke o vašim klijentima vi ste rukovalac, a Vindex obrađivač;
> - **nova adresa za zaštitu podataka je privacy@vindex.rs, a za ostala pitanja kontakt@vindex.rs. Ne koristite ranije adrese na domenu vindex.ai.**
>
> Ispravljeni tekstovi: https://vindex.rs/privacy i https://vindex.rs/terms. Prethodnu verziju možete dobiti na zahtev.
>
> Benjamin Nađ, osnivač Vindex AI

### I.8 Uslovi i naplata (Faza C)

| Provera | Rezultat |
|---|---|
| Naplata aktivna? | Ne: `STRIPE_URL = ''` (`static/vindex.js:124`); `routers/product_intelligence.py`: „Stripe nije integrisan“ |
| Plaćeni ugovori? | Nema dokaza da postoje; osnivač kaže da nema prihoda (INFERRED: nema ih) |
| Cenovnik na sajtu? | Ne: `/pricing` je uklonjen (`api.py`), a V2 sajt nema cena |
| Uslovi opisuju beta uslugu? | Do sada nisu („pretplatni model prema važećem cenovniku“); ispravljeno |

Odluka o ograničenju odgovornosti („iznos pretplate plaćen u 12 meseci“) i nadležnosti („Privredni sud u Beogradu“, iako je pružalac fizičko lice) je **usko pravno pitanje za kasniju proveru**. Ugovorni uslovi se ne menjaju bez pravne osnove, pa to ne blokira sajt.


## K. Founder contact override — 2026-10-21 (final release amendment)

Osnivač Benjamin Nađ izričito je potvrdio da je njegova **trenutna kontakt adresa** `benny13.n@gmail.com` i zahtevao da se Website V2 završi bez podešavanja `@vindex.rs` sandučića. Ova odluka zamenjuje prethodni nerešeni kontakt gate iz §I.1; **ne menja istorijski dokaz** da `vindex.rs` nema aktivne MX kontakte.

- Jedini javni kontakt za privatnost, pravna pitanja, korisničku podršku i prijavu problema do daljeg je `benny13.n@gmail.com`.
- U aktivnim tekstovima i porukama uklonjene su `privacy@vindex.rs`, `kontakt@vindex.rs` i `info@vindex.rs`. Nisu izmišljeni novi mailbox-i.
- PROVEN: osnivač je lično naveo adresu kao trenutni kontakt. UNKNOWN: nezavisni test prijema sa druge adrese nije obavljen ovde; ne tvrditi suprotno.
- Gmail adresa je svesni privremeni javni kontakt osnivača, ne dokaz da postoji registrovano pravno lice.
- Odredba o 14 dana i obaveza obaveštavanja pogođenih korisnika ostaju posebna odgovornost; samo ispravka kontakta nije pravni GO za sve izmene.
- Regression testovi proveravaju da nijedna aktivna kontakt površina ne upućuje na neaktivni `@vindex.rs` / tuđi `@vindex.ai` i da prikazuje potvrđeni Gmail.
