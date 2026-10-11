# V2 SOLO BETA: paket za odluku o izdanju

- **Datum:** 2026-10-11
- **Opseg:** solo advokat. Timske funkcije ostaju u kodu, ali se ne oglašavaju.
- **Oznake:** **P** = PROVEN (izmereno), **I** = INFERRED (zaključeno iz koda), **A** = ASSUMED, **U** = UNKNOWN.

## 1. Kandidat
| | SHA |
|---|---|
| Produkcija danas | `80c3902be2e06654490972a027a391dbf667dbb4` (P: `/health`) |
| RC1 | `036854c0824b5aaf3d5ae49abf0a2cd8cbbcf54e` |
| **Kandidat (kod)** | `ae1897a1588ac99bb7063f6c6838392df0067521`, Draft PR #12 → `release/v2-rc1` |
| Vrh PR #12 | ovaj dokument i ONS001 dokazi su samo docs commitovi iznad `ae1897a1` |

PR #12 sadrži samo dokumentovanu ispravku pre migracije 136 (P: diff `036854c0..ae1897a1` = `routers/autonomy.py`, `services/law_brain_promocija.py`, 1 test). Ništa nije spojeno.

## 2. Solo tok: matrica sposobnosti
Ključ: **Browser** = V2 NG CI skup (Chromium, fixture na 127.0.0.1). **Backend** = Python testovi nad stvarnim rutama i lažnom bazom. **Prod** = dokaz u produkciji.

| Korak | V2 putanja | Browser | Backend | Prod | Status |
|---|---|---|---|---|---|
| Registracija | V1 prijava (`/api/register`); V2 je nema | — | — | **P** (RH002 FINAL: sintetički nalozi) | radi |
| Prijava | V1 prijava → V2 most sesije | `verify:live-session`, `verify:session-contract` | — | **P** (password grant, RH002) | radi |
| Klijent | kartica Klijenti predmeta + sukob interesa | `verify:live-klijenti` | `test_ns005_t4_klijenti_coi` | **P** (klijent kroz API, RH002) | radi |
| Predmet | Nov predmet, registar, detalj | `verify:live-nov-predmet`, `live-matters`, `e2e:primary` (stvaran api.py) | `test_ns005_t2_nov_predmet` | **P** (predmet kroz API, RH002) | radi |
| Smart Intake / dokument | Prijem dokumenata | `verify:live-prijem` | `test_ns005_t14_smart_intake`, `test_ns005_b_ocr` | OCR u produkcionoj slici: **P u CI** ("OCR proof inside the production image" = success); živi OCR u produkciji: **U** | radi u CI-ju; produkcija neizmerena |
| Dokazi | Dokumenti/dokazi predmeta | `e2e:primary` (kartica Dokumenti), browser dokaz §4 | `test_ns006_t2/t4` | U | radi (CI) |
| Living Matter | Analiza, Pregled | `verify:live-analiza`, `live-pregled-zivi`, `e2e:demo-ns006` | `test_ns006_t3/t5/t6/t7/t14` | U | radi (CI) |
| Case Actions | Radna lista, Rad na predmetu | `verify:live-radna-lista`, `live-rad-predmeta` | `test_ns006_t8` | U | radi (CI) |
| Pravno pitanje / Law Brain | Pravno pitanje, Znanje | `verify:live-pitanje`, `live-law-brain`, `live-znanje`, `e2e:demo-ns008` | `test_ns005_t6`, `test_ns008_*`, `test_rh001_law_brain_authority` | U (kvalitet odgovora na stvarnom korpusu nije meren u ovom sprintu) | radi (CI) |
| Nacrt podneska | Nacrt + overa + DOCX | `verify:live-nacrt` | `test_ns005_t8_nacrti` | U | radi (CI) |
| Autonomna priprema | — | browser dokaz §4 | ONS001 T1 | **P**: tabele 136 ne postoje | **isključeno** (`NIJE_UKLJUCENO`), ne tvrdi ništa |

V2 NG CI na kandidatu: **38/38 skupova PASS** (run 38090010235), a i RC1 osnovica je zelena (38090034266).

**Van solo opsega:** poziv kolege, uloge i delegacija. V2 nema dugme za poziv (I: `frontend-v2-ng/src` ne poziva `/api/kancelarija/pozovi`); poziv postoji samo u legacy `/app-legacy`. BETA-DEF-001 i BETA-DEF-002 ostaju otvoreni i ne oglašavaju se.

## 3. Timska arhitektura je očuvana (solo radi bez nje)
- **Nijedan fajl obrisan** (P: `git diff --name-status 80c3902b..ae1897a1`, 0 × `D`).
- `routers/kancelarija.py`, `shared/rbac.py`, `routers/enterprise.py`, `routers/saradnja.py`, `shared/memorija_vidljivost.py`, `routers/firm_memory.py`, `routers/memory_graph.py` i `shared/deps.py` su **identični** produkciji (P). Semantika uloga je nepromenjena.
- `shared/rag_acl.py`: jedina izmena **sužava** pristup, jer delegat ne vidi predmet u brisanju (P, pregled diff-a).
- **Bez implicitne delegacije:** delegacija nastaje samo kroz `POST /api/enterprise/predmet/delegiraj` (vlasnik predmeta, cilj mora biti član iste kancelarije) (I). Solo korisnik nema kancelariju, pa delegacija nije moguća. Produkcija: 0 članova kancelarija, 0 delegacija (P, read-only zbir).
- **Bez kancelarijskog pristupa za solo:** memorija kancelarije zahteva kancelariju (`_fetch_firm_memory_context` vraća `None` bez nje) (I). ACL skup S1 prolazi (P).
- Nema novog feature flag-a.

## 4. Browser dokaz: isključena autonomija (P)
Pravi `api.py` i pravi V2 `/app` u Chromium-u. Harness je repo `tests/v2_ng_e2e_harness.py` uz omotač van repoa:
1. tabele 136 vraćaju PGRST205;
2. ista lažna autentifikacija za `shared.deps.get_current_user`;
3. verno `.not_.in_`.

Rezultat: `node pre136-browser.mjs` → exit 0, **17/17 PASS**:
- `/api/workspace` → 200, `vindex_je_pripremio_stanje = NIJE_UKLJUCENO` (simulacija potvrđena zapisom PGRST205);
- blok „Vindex je pripremio“ nije prikazan, a nigde nema tvrdnje o pripremljenom radu;
- nema vidljive akcije autonomnog rada;
- navigacija radi: Danas, Predmeti (12 stvarnih), detalj predmeta, Dokumenti, povratak na Danas;
- 0 upisa i 0 RPC (nema naplate, nema ciklusa); 0 poziva `/api/cron/*` i `/api/autonomy/work-items/{id}*`; samo GET; 0 spoljnih veza; 0 JS grešaka.

**Kontrola osetljivosti:** isti test sa backend-om koji vraća jednu spremnu stavku → exit 1, 13/17. Pada tačno na „blok nije prikazan“, „nema tvrdnje“, „povratak na Danas“ i stanju API-ja. Provera „nema akcije“ prolazi i u kontroli, jer su akcije u detalju rada, ne na Danas, pa je ta provera slaba.

Ograničenje: ovo je dokaz iz scratchpad skripte, nije u repou ni u CI-ju.

## 5. Ključni testovi na `8d521ae6` (kod = `ae1897a1`)
Lokalno: `timeout 900`, `--randomly-seed=12345`, ishod iz JUnit XML-a.

| Grupa | Exit | Rezultat |
|---|---|---|
| S1 ACL (RH001/RH002 legacy memorija, graf, delegacija/opoziv ACL, chat, JWT) | 0 | 121 passed |
| S2 ONS001 pre-migracija + NS007 granice | 0 | 42 passed |
| S3 solo tok (predmet, beleška, klijent/COI, ročišta, pitanje, nacrt, NS006 dokazi/Genome/kontradikcije/spremnost/Case Actions/API/tenant matrica) | 0 | 151 passed |
| S4 Smart Intake / OCR otkazi | 0 | 61 passed, **12 skipped** (nema Tesseract-a lokalno: 9 × `test_ns005_t14`, 1 × `test_b3`, 2 kolekcije) |
| S5 Law Brain autoritet / ACL / trovanje / opoziv / API | 0 | 190 passed |

**CI** (ONS001 runovi na `ae1897a1` vs `main`, po ID-ju testa):
- pytest 3.11/3.13: 0 novih padova;
- ceo skup na produkcionom Python-u 3.11: 0 novih padova;
- Docker build i boot: 17 passed;
- OCR proof u produkcionoj slici i py311: success;
- V2 NG 38/38;
- sast/semgrep: success;
- pip-audit: success samo zahvaljujući izuzetku (§6);
- gitleaks: failure zbog skeniranja cele istorije (876 starih `theme_token` nalaza, svi na `main`-u, 0 u diff-u).

**Osnovica od 175/197 padova postoji i na produkciji**, uključujući `test_b3_ocr_bez_laznog_uspeha::test_o2` („OCR alat postoji ali nije izvršen“) u py311 paritetu. Nije sakrivena i nije menjana.

## 6. Izjava za odluku o JWT izuzetku
> Odobravam izuzetak `CVE-2026-85394` (python-jose ≤3.5.0) u `security.yml` za V2 solo betu, pod uslovom da se ukloni čim upstream objavi zakrpljenu verziju ili čim se promeni ugovor verifikatora tokena. Osnova:
> - zakrpljena verzija ne postoji (PyPI 3.5.0 = najnovija);
> - napad traži da se javni ključ koristi kao HMAC tajna, a Vindex HS256 proverava isključivo tajnom, dok javni ključ koristi samo za ES256/RS256 uz jedan dozvoljen algoritam;
> - 78 pokušaja falsifikata na stvarnim verifikatorima: 0 prihvaćenih;
> - produkcioni JWKS je ES256 sa `alg`.
>
> Zamena biblioteke se planira posle bete.

Bez ove izjave: **NO-GO** (RC1 ne prolazi pip-audit).

## 7. Redosled puštanja
1. Osnivač daje izjavu iz §6.
2. Osnivač pregleda i spaja PR #12 → `release/v2-rc1`.
3. Otvaranje PR-a `release/v2-rc1` → `main`. Na tom PR-u gitleaks radi u PR režimu (samo novi commitovi): ishod **U**; trijaža po potrebi.
4. CI na tom PR-u bez novih padova u odnosu na `main` `80c3902b`.
5. Merge → Render deploy sa `main`-a (I/A: Render prati `main`).
6. **Bez migracija:** 135 je već primenjena (P), 136 nije potrebna za solo betu.
7. **Bez Cron-a** i bez `AUTONOMY_CRON_SECRET`.
8. `VINDEX_V2_NG_PRIMARY_ENABLED` ostaje kako jeste: produkcija već služi V2 na `/app` (P).

## 8. Smoke test posle deploy-a (izvršava ga osnivač ili ovlašćen nalog)
1. `/health` → `commit` = kratki SHA spojenog `main`-a; `/app` asseti `/v2/app/@<taj SHA>`.
2. Prijava sopstvenim nalogom → Danas se učitava, a blok „Vindex je pripremio“ se **ne** prikazuje.
3. `GET /api/autonomy/work-items` → `stanje: NIJE_UKLJUCENO`; `POST /api/cron/autonomy` bez tajne → 401.
4. Predmet → Pregled, Analiza, Dokumenti, Radna lista se otvaraju bez greške.
5. Prijem jednog skeniranog PDF-a (OCR) na testnom predmetu → tekst i stanje su vidljivi. Ovo je prva živa OCR provera (do sada **U**).
6. Pravno pitanje u predmetu → odgovor ili iskreno „nemam pouzdan odgovor“; troši 1 kredit.
7. **ACL:** ponoviti RH002 sintetički A/B paket (memorija, graf, delegacija) **samo uz izričito odobrenje**, jer pravi naloge u produkciji.

## 9. Povratak unazad (čuva poverljivost)
- **Render rollback na `80c3902` i ništa starije.** `80c3902` sadrži ACL hotfix (PR #11). Vraćanje na `99d2c6b9` ili ranije **ponovo otvara curenje memorije kancelarije**.
- Nema migracija za vraćanje (nijedna nije pokrenuta). Tabele 136 ne postoje, pa nema ni podataka autonomije.
- V2 asseti su adresirani po buildu (`/v2/app/@<sha>`), pa vraćanje servira stari build bez mešanja.
- Ako V2 treba ugasiti bez rollback-a koda: `VINDEX_V2_NG_PRIMARY_ENABLED` isključiti, i `/app` ponovo služi legacy. ACL hotfix je u backendu, pa važi i za legacy.

## 10. Preostali rizici
1. **Živi OCR u produkciji: U.** U CI-ju unutar produkcione slike prolazi; osnovica sadrži `test_o2` pad.
2. **Kvalitet pravnih odgovora** (pitanje, Law Brain) na stvarnom korpusu nije meren u ovom sprintu: U.
3. **Gitleaks na PR-u RC1→main: U.**
4. **Istorijska izloženost memorije pre `80c3902`: U** (RH002).
5. BETA-DEF-001 i BETA-DEF-002 su otvoreni; van solo opsega, dostižni samo iz legacy UI-ja ili API-ja.
6. Browser dokaz §4 nije u CI-ju.
7. **Šema produkcije odstupa od repoa** (uloge, statusi delegacije): to se tiče timskih funkcija, ne solo toka.

## 11. Preporuka
**GO za solo betu, uslovno:** (1) izjava iz §6, (2) PR #12 spojen u RC1, (3) PR RC1→main bez novih CI padova i sa trijažiranim gitleaks-om. Prvi smoke korak posle deploy-a je živi OCR (§8.5).

Bez uslova (1): **NO-GO**.
