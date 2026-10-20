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
8. `/sw.js` sadrži `vindex-v157`.
9. Keš:
   - `Cache-Control: public, max-age=300` na stranicama;
   - posle najviše 5 minuta `/` ne sme vraćati stari naslov „Vindex — predmeti, rokovi i spisi…“.
10. Prijava osnivača, jednom: pošalje kontrolnu prijavu sa svoje adrese na `/beta`. Proverava se:
    - prikazana je poruka „Prijava je evidentirana…“;
    - red je u tabeli `waitlist` (čitanje).

    Ovo je jedini upis u produkciju i radi ga osnivač, ne agent.
11. Konzola pregledača na `/` i `/beta`: 0 grešaka. Mreža: nijedan spoljni zahtev.

**Povratak:** revert commita spajanja → AutoDeploy. Bez migracija, pa nema ni povratka šeme.
