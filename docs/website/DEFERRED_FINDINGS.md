# VINDEX AI — ODLOŽENI NALAZI (Phase B)

Nalazi uočeni **usput** tokom izrade blueprint-a. Phase B nije forenzički sprint,
pa nijedan nije istraživan dalje niti popravljan.

Podela je po jednom pitanju: **da li blokira tačnu javnu tvrdnju ili start sajta?**

---

# A. BLOKIRA START — traži odluku vlasnika pre objave

| # | Nalaz | Zašto blokira |
|---|---|---|
| **A1** | **Tri domena u opticaju:** `vindex.rs` (landing), `vindex-ai.com` (canonical u `pricing.html`), `vindex.ai` (adrese e-pošte na pravnim stranicama) | Ulazi u `canonical`, OG oznake i `sitemap.xml` **svake** stranice. Pogrešan izbor se posle teško ispravlja u indeksu. |
| **A2** | **Pravni identitet firme ne postoji u repou** — pravno lice, adresa, PIB, matični broj | Podnožje i stranica `/kontakt` ne mogu se napisati. Phase A ga vodi kao `UNKNOWN`. |
| **A3** | **Broj zakona u korpusu: `18` vs `847`** — landing tvrdi jedno, pre-auth ekran drugo | Najmanje jedan je netačan. **Nijedan broj ne ide na sajt do merenja korpusa.** |
| **A4** | **SMTP se tiho preskače** ako env nije podešen (`routers/waitlist.py:91-93`, samo `logger.warning`) | Korisnik dobija `200`, red uđe u bazu, **vlasnik ne dobija nijedno obaveštenje**. Ceo Beta tok bi bio tih. Traži proveru produkcionog okruženja. |

---

# B. UTIČE NA TVRDNJU — rešeno slabijom formulacijom, ne popravkom

| # | Nalaz | Kako je zaobiđeno |
|---|---|---|
| **B1** | Memorija kancelarije se pretražuje **samo** pri auto-analizi unosa dokumenta; `/api/pitanje` je ne dira. 14 od 15 ruta institucionalnog učenja nema pozivaoca | Tvrdnja „Vindex uči iz svih predmeta" **odbačena**. Sajt nema sekciju „Kancelarijsko znanje" kao stranicu. |
| **B2** | Ograničenje AI verdikta postoji **samo** u orkestratoru strategije; `/strategija/sudija`, `/sudija-v2`, `/litigation` vraćaju slobodan tekst, a promptovi traže „USVAJA / ODBIJA" | „AI nikad ne presuđuje" **zabranjeno**. Koristi se uža formulacija o brojevima koje računa program. |
| **B3** | 207 RLS politika je za backend mrtvo slovo — aplikacija se povezuje service ključem | „Zaštićeno na nivou baze" **zabranjeno**. Dozvoljeno: „razdvojeno po nalogu, pokriveno testovima". |
| **B4** | `predmet_id` nikad ne stiže do rute za nacrt, pa je memorija nacrta u praksi prazna | Nije tvrđeno na sajtu. |
| **B5** | Streaming odgovor (`api.py:3220`) ne emituje `izvori`; frontend ga ne koristi | Nije tvrđeno. Rizik ostaje ako neko sutra prebaci ćaskanje na streaming. |

---

# C. HIGIJENA JAVNIH POVRŠINA — u obimu izrade sajta

| # | Nalaz | Postupak |
|---|---|---|
| **C1** | **`static/vindex.js.bak` (876 KB) je javno servirana** preko `/static` mount-a — stara verzija cele aplikacije, bez autentifikacije | `.gitignore` je pokriven u Wave 11, ali fajl i dalje stoji u radnom stablu. **Obrisati pri izradi sajta.** |
| **C2** | **`static/Vindex-AI-Bezbednosni-List.pdf` (94 KB) nije linkovan ni sa jedne stranice** | Postaje sekundarni CTA — dokument postoji, samo do njega niko ne stiže. |
| **C3** | **`static/status.html` nosi zabranjene ikone** (`⚖️⚡🤖🗄️🔍⚙️`, linije 46/62/96), kao i favicon aplikacije (`index.html:16`). Nijedan test to ne hvata | Van obima Phase B *(dira aplikaciju)*. Prijavljeno; odluka vlasnika. |
| **C4** | **`static/security.html` je dostupan i kao `/security` i kao `/static/security.html`**, sa različitim `Cache-Control`, oba indeksibilna | Novi sajt ide u `site/`, koji nije montiran — obrazac se ne ponavlja. |
| **C5** | **`robots.txt` nema `Sitemap:`** | Dodaje se sa novim stranicama. |
| **C6** | **`manifest.json:59-73` deklariše snimke ekrana koji ne postoje** | Van obima; prijavljeno. |

---

# D. VAN OBIMA SAJTA — čista evidencija

| # | Nalaz |
|---|---|
| **D1** | `/waitlist/prijava` **nema `@limiter.limit`** — oslanja se na podrazumevanih `60/hour` po IP-u, in-memory po radniku. Javan, bez auth, bez CAPTCHA i bez CSRF. |
| **D2** | **Nema `try/except` oko Supabase `insert`-a** (`waitlist.py:163-171`) → pad baze daje `500`, a prijava se gubi bez rezervnog zapisa. |
| **D3** | **Tabela `waitlist` nema kolonu za trag saglasnosti (GDPR).** Saglasnost može stajati kao tekst iznad dugmeta, ali se ne čuva. Čuvanje bi tražilo izmenu šeme. |
| **D4** | **Kontakt poruke ulaze u istu tabelu `waitlist`** kao Beta prijave; razlikuje ih samo prefiks `[KONTAKT]`/`[BETA]` u polju `poruka`. |
| **D5** | **`WaitlistPrijava` ne podiže `extra="forbid"`** → svako dodatno polje se pošalje, vrati `200 OK` i **nestane bez traga**. Zato Founding Partner nije polje u obrascu. |
| **D6** | **`focus-visible` ima 0 pojava u celom `static/vindex.css`** — problem nije lokalan za landing, pokriva ceo frontend. |
| **D7** | **Graf dokaza je mrtav zbog URL-enkodiranog imena:** frontend zove `/api/evidence-graph/generi%C5%A1i`, backend sluša `/generisi`. Test koristi ispravan put pa nikad nije pao. |
| **D8** | **Ne postoji nijedna ruta za brisanje dokumenta iz predmeta.** |
| **D9** | **`/api/pitanje` pretražuje vektorski prostor `firm_*` u koji nijedan upis u repou ne piše.** |
| **D10** | **`.doc` je dozvoljen na ulazu, ali ga ekstraktor ne ume.** |
| **D11** | **`secret-scan` CI job je već crven** zbog istorijskog nalaza (`dc29b764`) — boja CI-ja se ne sme koristiti kao signal pri izradi sajta. |

---

# PRAVILO KOJE JE OVDE PRIMENJENO

Nijedan nalaz iz ovog dokumenta nije popravljen u Phase B.

Za nalaze iz grupe **B** primenjena je jedina dozvoljena reakcija: **tvrdnja je
oslabljena ili odbačena**, proizvod nije menjan.

Grupa **A** ulazi u finalni izveštaj kao otvorene odluke; grupa **C** se rešava
u Phase C zajedno sa izradom stranica; grupa **D** ostaje evidencija.
