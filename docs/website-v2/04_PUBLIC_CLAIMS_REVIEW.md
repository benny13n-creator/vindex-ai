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
