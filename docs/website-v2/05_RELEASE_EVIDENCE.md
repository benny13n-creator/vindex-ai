# 05 — Dokaz za izdanje i plan provere posle puštanja (Website V2)

- Osnova: `origin/main` = produkcija `77733e11` (2026-10-20).
- Grana: `website/v2-master`.
- Ništa nije spojeno ni pušteno. Spajanje čeka vizuelno i sadržajno odobrenje osnivača.

## 1. Šta je isporučeno

**Javne stranice:**

| Ruta | Sadržaj |
|---|---|
| `/` | Početna |
| `/kako-radi` | Koraci rada |
| `/funkcionalnosti` | Katalog: 49 javnih stavki iz registra, filter po tekstu i statusu |
| `/za-advokate` | Primeri toka rada |
| `/razvoj` | Funkcije u razvoju (dve, sa odlukom) |
| `/bezbednost` | Pristup, AI kontrola, šifrovanje, evidencija, pravni dokumenti |
| `/beta` | Prijava za beta testiranje (jedina forma) |

**Preusmerenja (301):**
- `/sposobnosti` → `/funkcionalnosti`
- `/platforma` → `/kako-radi`
- `/kontakt` → `/beta`
- `/web3`, `/vizija`, `/tehnologija` → `/`

**Pre-auth ulaz:** `#vx-landing` na `/app-legacy` (kuda V2 `/app` šalje neprijavljenog korisnika).
- Novi tekst i V2 izgled, u obe legacy teme.
- Početni tekst modala prijave odgovara režimu prijave.
- Legacy plutajuće kontrole su skrivene samo dok je ulaz prikazan.
- Logika prijave, sesije i preusmeravanja nije menjana.

**Nisu menjani:**
- unutrašnja V2 aplikacija (`frontend-v2-ng/src`);
- `/api/*`;
- prijava i sesija;
- pravne stranice;
- backend prijave za beta (`routers/waitlist.py`);
- migracije, cene i krediti.

## 2. Izmenjeni fajlovi

| Fajl | Izmena |
|---|---|
| `site/funkcije.json` | **nov**. Jedini izvor istine: 67 stavki, statusi, dokazi, javni tekst. |
| `site/_izvor/*.html` | **novi**. Tekst sedam stranica. |
| `site/*.html` | generisano (`scripts/gradi_sajt.py`). `index.html` je zamenjen. |
| `site/sajt.css`, `site/sajt.js` | **novi**. Stil po V2 tokenima, pod `.sajt`; filter kataloga i forma. |
| `site/snimci/*.webp` | **novi**. 6 snimaka stvarnih V2 ekrana sa izmišljenim podacima (25–64 KB). |
| `scripts/gradi_sajt.py`, `scripts/snimci_webp.py` | **novi**. Gradnja sajta i matrice; konverzija snimaka. |
| `frontend-v2-ng/tests/diagnostics/site-snimci.mjs` | **nov** alat. Snima V2 ekrane nad lokalnim fixture-om. |
| `api.py` | 6 ruta stranica, novi spisak preusmerenja, `/v2/site/sajt.css`, `/v2/site/sajt.js`, mount `/v2/site/snimci`, sitemap. |
| `index.html` | `#vx-landing` zamenjen, početni tekst modala prijave, linkovi na V2 fontove. |
| `static/vindex.css` | blok `.vxp` (tamna i svetla tema) i skrivanje plutajućih kontrola pre prijave. |
| `static/sw.js` | `CACHE_NAME` v156 → v157 (pravilo: menja se legacy frontend). |
| `tests/test_website_public.py` | ugovori prošireni na 7 stranica; nov §9 (sadržaj ↔ registar) i §10 (pre-auth). |
| `frontend-v2-ng/tests/site-e2e.mjs` | pregledač: 7 stranica × 6 širina, tastatura, mobilni meni, pokret, katalog, 6 ishoda forme, pre-auth u obe teme. |
| `.gitignore` | `site/snimci-izvor/` (PNG izvor snimaka). |
| `docs/website-v2/01…05`, `docs/website-v2/snimci/` | dokumentacija i snimci za pregled. |

## 3. Testovi (lokalno, 2026-10-20)

| Paket | Rezultat |
|---|---|
| `tests/test_website_public.py` | **216 passed** |
| `node frontend-v2-ng/tests/site-e2e.mjs` (stvaran `api.py`, Chromium) | **355/355 PASS** |
| `tests/test_v2_ng_primary.py` (V2 `/app`, `/app-legacy`, povratak na V2) | **33 passed** |
| 50 pytest fajlova koji čitaju `index.html`, `vindex.css`, `sw.js` ili pre-auth (uklj. font test FAZA1) | grana i `origin/main` imaju isti skup padova: 3 u `test_faza1_pristupacnost.py`, poznati i van obima (NS4 §13). **0 novih padova.** |
| `python scripts/gradi_sajt.py --provera` | 0 (generisano = sačuvano) |

**Negativne kontrole.** Svaka je izvedena pa vraćena. Uhvaćeno je 9/9.

| # | Mutacija | Šta je palo |
|---|---|---|
| M1 | „847 zakona“ vraćeno u pre-auth | `test_pre_auth_ulaz_nema_zastarelih_tvrdnji` |
| M2 | status u registru promenjen bez ponovne gradnje | `test_generisane_stranice_su_uskladjene_sa_izvorom` |
| M3 | podsetnici (D07) označeni kao javni | `test_registar_je_potpun_i_dosledan` |
| M4 | ograničenje obrisano iz generisane stranice | katalog i usklađenost |
| M5 | plan označen „Uskoro“ | `test_razvoj_prikazuje_samo_odobrene_planove_kao_nedostupne` |
| M6 | snimak bez oznake demonstracionog prikaza | `test_svaki_snimak_je_oznacen_kao_demonstracioni` |
| M7 | „AES-256“ na `/bezbednost` | `test_nema_zabranjenih_tvrdnji` |
| M8 | vraćen stari početni naslov modala | `test_pre_auth_ulaz_cuva_ugovor_prijave_i_vodi_na_beta` |
| M9 | forma prikazuje uspeh za svaki odgovor | e2e: 3 ishoda (500, 422, stvaran backend bez baze) |

Tokom rada testovi su pronašli i četiri stvarna propusta, koja su ispravljena:
- natpisi snimaka bez „izmišljeni podaci“;
- legacy mobilna navigacija vidljiva pre prijave;
- `hidden` dugme vidljivo zbog CSS-a;
- komentar u legacy HTML-u sa oznakom V2, koji je obarao 12 testova `/app` ugovora.

## 4. CI

Vidi PR (statusi se dopunjuju posle pokretanja).

## 5. Snimci za pregled

U `docs/website-v2/snimci/`:
- svaka stranica desktop (`*-1440`) i mobilni (`*-390`), cela visina;
- pre-auth tamna, svetla, mobilni i otvoren modal;
- šest ishoda beta forme;
- poređenje pre i posle: `uporedno-pre-auth-1440`, `uporedno-pocetna-1440`, `pre-*`, `posle-*`.

## 6. Puštanje (tek posle odobrenja osnivača)

Spajanje PR-a → Render AutoDeploy. Bez ručnog deploy-a i bez migracija.

## 7. Provera posle puštanja (samo čitanje, osim jedne prijave)

1. `/health` → `commit` = SHA spajanja.
2. `GET` 200 i očekivan `<title>`: `/`, `/kako-radi`, `/funkcionalnosti`, `/za-advokate`, `/razvoj`, `/bezbednost`, `/beta`.
3. 301 sa tačnom lokacijom: `/sposobnosti`, `/platforma`, `/kontakt`, `/web3`, `/vizija`, `/tehnologija`.
4. 200: `/v2/site/sajt.css?v=…`, `/v2/site/sajt.js?v=…`, `/v2/site/snimci/registar.webp`, `/privacy`, `/terms`, `/dpa`, `/ai-disclosure`, `/status`, `/security`, `/bezbednosni-list`.
5. `/sitemap.xml` sadrži 7 stranica; `/robots.txt` i dalje sadrži `Disallow: /api/`.
6. `/app` = V2 (naslov „Aktivni predmeti · Vindex“).
7. `/app-legacy?posle=app` bez sesije prikazuje „Prijava u Vindex“, bez „847“.
8. `/sw.js` sadrži `vindex-v159`.
9. Keš:
   - `Cache-Control: public, max-age=300` na stranicama;
   - posle najviše 5 minuta `/` ne sme vraćati stari naslov „Vindex — predmeti, rokovi i spisi…“.
10. Prijava osnivača, jednom: pošalje kontrolnu prijavu sa svoje adrese na `/beta`. Proverava se:
    - prikazana je poruka „Prijava je evidentirana…“;
    - red je u tabeli `waitlist` (čitanje).

    Ovo je jedini upis u produkciju i radi ga osnivač, ne agent.
11. Konzola pregledača na `/` i `/beta`: 0 grešaka. Mreža: nijedan spoljni zahtev.

**Povratak:** revert commita spajanja → AutoDeploy. Bez migracija, pa nema ni povratka šeme.

## 8. Završna remedijacija istinitosti (2026-10-20)

Detalji tvrdnji, dokaza i zahteva osnivaču su u `04_PUBLIC_CLAIMS_REVIEW.md` §E–F.

### 8.1 Šta je bilo neispravno

- Javni pravni i bezbednosni dokumenti su obećavali backup koji aktivni plan nema. Tvrdili su i da su DPA/SCC potpisani, da RLS sam štiti podatke, šire šifrovanje od stvarnog, Argon2id za lozinke, 2FA, penetracione testove, audit svih pristupa i „GDPR usklađen“.
- `POST /waitlist/prijava` je otkrivao stanje proizvoljne adrese. Džoker `_` u adresi pogađao je tuđu prijavu. Istovremena prijava iste adrese davala je HTTP 500.
- Politika privatnosti nije opisivala beta prijavu.

### 8.2 Šta je izmenjeno (najmanje)

| Fajl | Izmena |
|---|---|
| `routers/waitlist.py` | jedan neutralan odgovor; `eq` umesto `ilike`; 23505 = isti odgovor bez drugog obaveštenja; log bez ličnih podataka |
| `site/sajt.js` | tekst greške 5xx ne tvrdi siguran neuspeh |
| `site/_izvor/beta.html` (+ generisane stranice: samo `?v=` heš i jedan link) | link na `/privacy#beta-prijava` |
| `privacy.html` | P-01, P-03, P-04, P-05, P-08, P-09, P-14 |
| `static/security.html` | P-02, P-03, P-04, P-05, P-09, P-11, P-12, P-13 |
| `static/bezbednosni-list.html` | P-04, P-05, P-06, P-07 |
| `static/dpa.html` | P-03, P-05, P-09, P-10, P-11 (ugovorne obaveze nisu menjane) |
| `static/ai-disclosure.html` | P-03 |
| `tests/test_website_v2_remediacija.py` (nov), `tests/test_website_public.py` (mock `ilike`→`eq`), `frontend-v2-ng/tests/site-e2e.mjs` (novi tekst 5xx) | testovi |

### 8.3 Šta je ostalo nedirnuto

Dizajn, 7 stranica, navigacija, katalog i `site/funkcije.json` (matrica 02 se nije promenila), pre-auth ekran, V2 aplikacija, auth/registracija, krediti, cene, rokovi, RLS i šema (bez migracije), `static/sw.js`, limiter i infrastruktura. `/terms` nije menjan (sadrži samo pravni identitet, F.1).

### 8.4 RED → GREEN (lokalno)

| Skup | Pre ispravke | Posle |
|---|---|---|
| `tests/test_website_v2_remediacija.py` | 24 pada / 5 prolaza | 30 prolaza |
| `test_website_public.py`, `test_website_v2_remediacija.py`, `test_v2_ng_primary.py`, `test_sec005_rate_limiting.py`, `test_wave10_rate_limiter_isolation.py`, `test_ocr001_status_rate_limit.py` (`--randomly-seed=1234`) | — | 317 prolaza, 1 preskočen |
| `test_api_security`, `test_gdpr_delete`, `test_n04_case_export_integrity`, `test_ns2b_export_audit_ordering`, `test_ns3_export_audit_fail_closed`, `test_security_p1_p2`, `test_xss_sanitization_sweep`, `test_sec009_pii_encryption`, `test_sec005_failopen_limiter` | — | 163 prolaza |
| `npm run e2e:site` (7 stranica × 6 širina, beta forma: 6 ishoda, pre-auth) | — | 355/355 |
| Mutacije M10–M12 (`routers/waitlist.py`) | — | 3/3 uhvaćene (M10 tek posle ispravke lažno zelenog testa, vidi 04 §E.2) |

### 8.5 CI, merge i deploy

CI rezultati za konačni HEAD, SHA spajanja i SHA na Renderu upisuju se u komentar PR #48, ne u novi commit na `main`. Tako se ne izaziva novi deploy.

### 8.6 Dopuna provere posle puštanja (uz §7)

12. `/privacy` sadrži odeljak `id="beta-prijava"` i rečenicu „ne uključuje automatske backup-e“; `/dpa` ne sadrži „DPA potpisan“; `/bezbednosni-list` ne sadrži „Argon2id“.
13. Jednak odgovor za poznatu i nepoznatu adresu u produkciji proverava se samo adresama koje je osnivač odobrio. Postupak: osnivač pošalje istu svoju adresu dva puta, a agent poredi oba odgovora; nijedna tuđa adresa se ne koristi.

## 9. Night Sprint V (2026-10-21)

Nalazi i zahtev osnivaču: `04_PUBLIC_CLAIMS_REVIEW.md` §G–H.

| Fajl | Izmena | Razlog |
|---|---|---|
| `requirements.txt` | `pillow==13.0.0` | 8 CVE-ova u 12.3.0 (Security Checks pao na `a7d161e7`) |
| `routers/waitlist.py` | escapovan HTML obaveštenja; naslov bez prelaza reda; 10/h po klijentu + 20/h i 100/dan ukupno | G11: limit po klijentu se zaobilazi `X-Forwarded-For`-om |
| `privacy.html`, `terms.html`, `static/dpa.html`, `static/security.html`, `static/bezbednosni-list.html`, `index.html` | „Vindex d.o.o.“ → „Benjamin Nađ, osnivač Vindex AI“ / „Vindex AI“; Pinecone tekstualni segmenti | pravno lice ne postoji; `uploaded_doc/ingest.py:165` |
| `static/sw.js` | `vindex-v157` → `vindex-v158` | menja se legacy `index.html` (pravilo projekta) |
| `tests/test_website_v2_remediacija.py` | limit, escapovanje, Pinecone, identitet | regresioni testovi; mutacije M13–M16 uhvaćene |

Nepromenjeno: dizajn, 7 stranica, katalog, `site/funkcije.json`, V2 aplikacija, auth, RLS, šema, globalni limiter.

**Lokalno:**
- `test_website_v2_remediacija.py` + `test_website_public.py`: 253 prolaza.
- Regresija:
  - testovi limitera i bezbednosti (12 fajlova, seme 1234): 437 prolaza i 1 preskočen;
  - `test_lambda001_beta_readiness_fixes`: 13 prolaza.
- `e2e:site`: 355/355.
- Pillow 13 (91 OCR/slika fajl): isti rezultat kao 12.3.0.
- `pip-audit`: čisto.

**CI na konačnom HEAD-u** i odluka GO/NO-GO: u komentaru PR #48.

## 10. Final Closure (2026-10-21)

Nalazi i odluke: `04_PUBLIC_CLAIMS_REVIEW.md` §I.

| Fajl | Izmena | Razlog |
|---|---|---|
| 13 fajlova (pravne stranice, `index.html`, `static/vindex.js`, `static/status.html`, `routers/gdpr.py`, `routers/drafting.py`, `routers/data_export.py`, `scripts/dr_runbook.py`) | `*@vindex.ai` → `privacy@vindex.rs` / `kontakt@vindex.rs` | `vindex.ai` nije domen osnivača |
| `privacy.html` | rukovalac/obrađivač; beta: legitimni interes, rok 6 meseci / 30 dana, prigovor, ručno brisanje; oznaka ispravki | A2–A4 |
| `terms.html` | „Naplata nije uvedena i cenovnik nije objavljen“; odeljak o pretplati važi tek uz naplatu | Faza C |
| `static/dpa.html`, `static/security.html` | bez „godišnje pretplate“; „DPO“ → „Kontakt za zaštitu podataka“ | ne postoje |
| `static/sw.js` | `vindex-v158` → `vindex-v159` | menjaju se legacy `index.html` i `vindex.js` |
| `tests/test_website_v2_remediacija.py` | 19 novih testova; mutacije M17–M21 uhvaćene | regresija |

Nepromenjeno: dizajn, 7 stranica, katalog, V2 aplikacija, auth, šema, limiter.

**Lokalno:**
- `test_website_v2_remediacija.py` + `test_website_public.py`: 272 prolaza.
- GDPR, drafting, export, SW i `lambda001` testovi: 280 prolaza, 1 preskočen.

**Mutacije:**
| ID | Mutacija | Uhvaćena |
|---|---|---|
| M17 | `kontakt@vindex.ai` vraćen u `vindex.js` | da |
| M18 | vraćen osnov iz tač. 2 | da |
| M19 | vraćen „važeći cenovnik“ | da |
| M20 | vraćen „DPO“ | da |
| M21 | rukovalac podataka klijenata je „Vindex“ | da |

**Produkcija (čitanje):** `waitlist` = 0 redova; `auth.users` = 141. `vindex.rs` nema MX zapis.

**Smoke posle deploya, dopuna §7/§8.6:**
- `/privacy` i `/terms` sadrže „Ispravke od 2026-10-21“ i `@vindex.rs`;
- nijedna od stranica `/privacy`, `/terms`, `/dpa`, `/security`, `/ai-disclosure`, `/bezbednosni-list`, `/status` i `/app-legacy` ne sadrži `@vindex.ai`;
- `/sw.js` sadrži `vindex-v159`.
