# FRI001 — dokazi za zaključan kandidat V2 solo beta izdanja

Oznake: **P** dokazano · **I** zaključeno · **A** pretpostavljeno · **U** nepoznato.

## 1. Tačno stanje (P, `git fetch` + GitHub API, 2026-10-11)
| Ref | SHA |
|---|---|
| Produkcija `origin/main` | `80c3902be2e06654490972a027a391dbf667dbb4` |
| `origin/release/v2-rc1` | `036854c0824b5aaf3d5ae49abf0a2cd8cbbcf54e` |
| PR #12 (ONS001) | `ad028bdef3b3454607a613cb93186aebd93867bb` |
| PR #13 (OSB002) | `8901a249a59836d33bd53b8d42025b3fced72d9e` |
| PR #14 (OSB003) | `db37af55c42145caa232fc37158a4eb37057ff0a` |
| PR #15 (FRG001) | `df5feb3619ff8286c9e689f134ba2da5ac4926c1` |
| **Kandidat (kod)** `release/v2-solo-final-candidate` | `c7b809f10501ae30c649ebf8b75169e8b286d86d` |
| Draft PR #16 → `main` | https://github.com/benny13n-creator/vindex-ai/pull/16 |

Završni commit ove grane dodaje samo ova dva dokumenta (v. §9 za dokaz da kod nije menjan).

## 2. Istorija izdanja (Task 1) — P
```
main 80c3902b ──93 (5 merge)──► rc1 036854c0 ──3──► #12 ad028bde ──5──► #13 8901a249 ──11──► #14 db37af55 ──4──► #15 df5feb36 ──2──► kandidat c7b809f1
```
- Svaki korak je strogi predak sledećeg (`merge-base --is-ancestor`). Merge-baza `main..#15` je `80c3902b`. `main` nema commita kojih nema u #15.
- Nijedan commit sa RC1, #12, #13 ili #14 ne nedostaje u #15 (0 / 0 / 0 / 0).
- Sve povezane grane imaju 0 commita i 0 patch-neekvivalentnih izmena van #15:
  - `hotfix/rh001-memory-acl`, `hotfix/v2-primary-asset-coherency`;
  - `rh001-ns006/7/8`, `ns006/7/8`.
- `hotfix/rh001-memory-acl` je već u produkciji (`main` je merge PR #11).
- **RH002** (`rh002/final-closure`, lokalna grana dokaza): jedini commit je prenet u #15 kao `2a944c44`. Dokumenti su identični, a test se razlikuje u 1 liniji, jer koristi `ns008_fake` umesto `ns005_harness`.
- **Sadržaj ispravki, ne samo istorija:** obrnuti patch svake ključne ispravke primenjuje se čisto na kandidat:

| Grupa | Commit(i) |
|---|---|
| RH001/RH002 | `af5392a1`, `5713bd9d` |
| ONS001 | `ae1897a1` |
| OSB002 | `c148d342` |
| OSB003 | `db5255d2`, `0709728d`, `9994b976`, `b8ac7935` |
| FRG001 | `2248d832`, `a5813350`, `b5b9d5a8` |
| ostalo | `bcdda274` |

  Tri patch-a se ne primenjuju obrnuto. Sva tri je kasniji commit namerno nadogradio, a novi sadržaj je prisutan:
  - `2248d832/event_bus` → `a5813350`;
  - `1c188ea3/main.py` → `b5b9d5a8` (padeži su sačuvani);
  - `bcdda274/package.json` → kasnije skripte.
- Revert commita u opsegu nema.

**Matrica izmena po koraku (fajlovi):**

| Korak | Fajlova | Glavne oblasti |
|---|---|---|
| main→rc1 | 151 | 78 tests, 18 frontend-v2-ng, 11 services, 10 shared, 9 routers, 2 migrations, requirements |
| rc1→#12 | 6 | routers, services, tests, docs |
| #12→#13 | 9 | routers, frontend-v2-ng, tests, docs |
| #13→#14 | 22 | main.py, routers, shared, frontend-v2-ng, .github, .gitleaksignore, tests |
| #14→#15 | 19 | main.py, routers, services, tests |
| #15→kandidat | 5 | `routers/intake.py`, `services/case_evolution.py`, 3 test fajla |
| **main→kandidat** | 197 | ukupni opseg izdanja |

Izvan koda u opsegu:
- `migrations/135` (u produkciji primenjena 2026-10-09);
- `migrations/136` (fajl postoji, **nije primenjen**, nije potreban; v. §6);
- `pypdf` 6.15.0 → 6.19.0;
- `scripts/trigger_autonomy_cycle.py` i `workers/background_agents.py` (NS007, neaktivno).

`git diff --check main..kandidat`: samo razmaci na kraju dva reda u `NS008_OVERNIGHT_EVIDENCE.md`.

## 3. Kandidat (Task 2) — P
`main` je predak #15, pa je najmanji metod koji čuva istoriju **fast-forward**: kandidat je kreiran na `df5feb36` (stablo `9a6a7dcf` = stablo PR #15, isti commit). Bez cherry-pick-a i merge commita. Na to idu 2 FRI001 commita (§4). Postojeće grane i PR-ovi nisu menjani.

## 4. COI lanac (Task 3)
**Lanac (P, kod):**
- Smart Intake finalize **starog čarobnjaka** (`static/vindex.js:22363` šalje `klijent_strana`) → `NEW_CLIENT_LINKED`. Stabilan `event_id` po poslu, 3 pokušaja; odgovor nosi `coi_status`: `PENDING`, `FAILED` ili `NOT_APPLICABLE`.
- → `dispatch_pending_events` (do 5 pokušaja, zatim dead-letter) → `case_evolution._consequence_conflict_check`. Ledger `(event_id, consequence_name)` sprečava dvostruko izvršenje.
- → `routers/intake._run_conflict_check`, isključivo nad podacima **istog** `user_id`.
- → `proactive_alerts` (`tip=sukob_interesa`).
- → advokat ga vidi samo u starom UI-ju: brifing predmeta (AI kontekst) i jutarnji brifing (samo `hitna`).
- **V2 prikačivanje ne šalje `klijent_strana`**, pa je uvek `COI_NOT_APPLICABLE` i događaj ne nastaje (P, test 0).
- Jedini emiter `NEW_CLIENT_LINKED` je ovaj finalize.
- Do FRG001 se događaj u produkciji nije upisivao (`TypeError`), pa je sve ovo novo aktivno ponašanje posle deploy-a.

**Nađeno i ispravljeno (`207757e6`, P):**
1. **Sukob predmeta sa samim sobom.** Finalize poveže klijenta i stranke u novi predmet pre provere, pa je svaki finalize sa klijentom pravio „Već postoji klijent sličnog imena … u predmetu <isti predmet>“. Ispravka: `_run_conflict_check(iskljuci_predmet_id=…)`. Podrazumevano je `None`, pa je HTTP provera pre otvaranja predmeta nepromenjena.
2. **Mečer predstavljen kao pravna ocena.** Upozorenje je preuzimalo „Postoji BLOKIRAJUCI sukob… Ne možete zastupati…“. Sada glasi „Mogući (blokirajući) sukob interesa — potrebna provera“ i „automatsko podudaranje imena, nije pravna ocena“. `urgentnost` je ista.
3. **Duplo upozorenje posle delimičnog rezultata.** Upozorenje upisano, prekid pre beleženja posledice, pa ponovna obrada. Sada se isto nepročitano upozorenje za isti predmet ne upisuje ponovo (obrazac postojećih audit posledica).

**Testovi (`tests/test_fri001_coi_lanac.py`, 12, stvarne rute + IntakeWorker + dispečer + stvarna provera):**

| # | Scenario | Dokaz |
|---|---|---|
| 0 | V2 put | `COI_NOT_APPLICABLE`, bez događaja |
| 1 | nema sukoba | odgovor `COI_PENDING` (nije „čisto“); posledica `completed`; 0 upozorenja (ranije: 1, o samom sebi) |
| 2, 13 | mogući sukob, lažno pozitivan | 1 upozorenje, „mogući … potrebna provera“, bez „ne možete zastupati“; vidljivo preko `/api/briefing/alerts` za tačnog advokata |
| 3 | provera ne može da se izvrši | događaj nije isporučen, posledica nije `completed`, 0 upozorenja; posle oporavka se izvrši |
| 4 | nema imena stranke | `COI_NOT_APPLICABLE`, bez događaja |
| 5, 14 | upisan, a neisporučen; zakasneli rezultat | upozorenje stiže pri kasnijem dispečovanju |
| 6, 7 | replay; dupli upis | 1 događaj, 1 upozorenje |
| 8 | istovremena obrada | 1 posledica, 1 upozorenje |
| 9 | pad posle delimičnog rezultata | 1 upozorenje (ranije 2) |
| 10, 11 | tuđi klijenti/predmeti; drugi korisnik | B-ovi podaci ne ulaze u A-inu proveru niti u upozorenja; B ne vidi A-ina; tuđ posao 404 |
| 12 | više sličnih imena | oba kandidata u istom upozorenju, nijedan izabran |
| — | spoljna pravna radnja | posledica piše samo u dozvoljene interne tabele; bez email/SMS/podnesaka/autonomije |

Mutacije: 3/3 uhvaćene. Postojećih 30 COI fajlova: 447 prolazi; padaju samo 3 `[trio]` (nema modula `trio`), isto i na polaznoj grani.

**Ostaci (bez ispravke, odluka B):**
- **COI koji trajno ne uspe** (5 pokušaja, dead-letter) advokatu se ne javlja nigde. Nije predstavljen kao „čisto“, ali je nevidljiv (P).
- `coi_status` iz odgovora ne prikazuje nijedan UI (P).
- U V2 se COI upozorenja ne prikazuju (P). Za solo betu na V2 to znači da COI iz Smart Intake-a nije deo V2 toka.
- Stara HTTP provera (čarobnjak „ime prvo“, već u produkciji) i dalje prikazuje „Ne možete zastupati… (čl. 42 Zakona o advokaturi)“ za podudaranje imena. Navod zakona nije proveren ovim sistemom.

## 5. Oporavak dokumenta i čuvar citata (Task 4) — P na kandidatu
- FRG001 testovi (dokument 11, pravi klijent 2, zakon+član 30), OSB003 autoritet 12, `guard_v2` 8, novi `test_fri001_kandidat_ugovori.py` 2: **65 prolazi, exit 0**.
- Novo izmereno:
  - pad pa ponovni pokušaj **ne naplaćuje ništa više** od čistog prolaza (finalize i automatska klasifikacija ne naplaćuju);
  - prihvaćen dokument i njegove tvrdnje ostaju bajt-isti posle identičnog zahteva, istog fajla (isti posao), istog teksta u drugom fajlu (nov posao → `vec_obradjen_preskocen`) i replay-a.
- Dedup posla je po **bajtovima**: isti tekst u drugom fajlu je nov posao, ali dokument se ne duplira.
- Nepotpuni zapisi nastali **pre** ovog izdanja ne mogu se pouzdano prepoznati iz koda. Stari Smart Intake je upisivao `klasifikovan_at` bez tvrdnji, pa izgledaju klasifikovano. Status je **U**. Destruktivna popravka nije pravljena.
- FRG001 `main.py` diff ne menja nijedno JSON polje odgovora. Menja se samo tekst `razlog` (prikazuje se skraćen; niko ga ne parsira; P, grep).

## 6. Bezbednost i regresija (Task 5)
- **Lokalno (P):** 347 fajlova, seme `12345`, JUnit, kandidat / PR #15 / `main`.

  | Grana | Padovi | Prošlo |
  |---|---|---|
  | kandidat | 13 | 5387 |
  | PR #15 | 14 | 5372 |
  | `main` (281 zajednički fajl) | 12 | 4723 |

  - Jedina razlika po identitetu su Playwright UI testovi (`id01`, kontrast). Padali su naizmenično na kandidatu i na PR #15 dok su tri pokretanja išla paralelno. Izolovano, na kandidatu prolaze **9/9 dva puta zaredom**. Kandidat nema nijednu izmenu u UI kodu u odnosu na PR #15. Klasifikacija: nestabilnost pod opterećenjem.
  - Preostali padovi su isti na sve tri strane: `[trio]` (nema modula), `rc_cold_start`, `ca_trust_boundary::M19`, `phoenix_013`.
- Pokriveno:
  - izolacija korisnika, predmeta i klijenata; RH001/RH002 memorija kancelarije;
  - graf (čitanje i pisanje); izolacija konteksta AI razgovora; Law Brain dozvole;
  - ograničenja kancelarije i opoziv delegacije; JWT algoritmi i ključevi (OSB003);
  - isključena autonomija; 404 pre migracije 136 (ONS001/OSB003).
- **Autonomija (P, kod):** ciklus se pokreće samo POST-om sa `AUTONOMY_CRON_SECRET`; bez tajne se odbija, a tabela 136 ne postoji. Registar starih dnevnih agenata je i dalje `court_portal_watcher` + `precedents_radar`: `hearing_prep` nema `run`, pa ne ulazi.
- **Tajne (P):** gitleaks 8.30.1 sa konfiguracijom repoa:
  - opseg `main..kandidat`: 0 nalaza;
  - cela istorija: 0 nalaza;
  - sintetički AWS ključ (pozitivna kontrola): 1 nalaz, exit 1 (vrednost nije ispisana).
- **JWT (P/I):** CVE-2026-85394 (python-jose 3.5.0), bez zakrpe.
  - Svaki `decode` dozvoljava tačno jedan algoritam; produkcioni JWKS je ES256 sa `alg`.
  - 0 falsifikata u 4 varijante JWKS-a (OSB003).
  - pip-audit prolazi samo zbog postojećeg, **neodobrenog** izuzetka; izuzetak nije menjan.
  - Preporuka: prihvatiti rizik na 90 dana, sa uslovima iz OSB003.

## 7. Proizvod (Task 6)
- **Pregledač:** CI V2 NG na SHA kandidata pokreće sve `e2e:*` (uključujući `solo-tok` 23 provere i `pre136`) u pravom Chromium-u nad pravim FastAPI-jem. Rezultat je u §8.
- **Nov korisnik:** nema lažnog „Vindex je pripremio“; autonomija bez aktivnih kontrola (OSB003 testovi u regresiji, P).
- **Nepotpuno prikačivanje:**
  - API vraća 5xx i posao ostaje neprikačen (P);
  - V2 to prikazuje kao „Ishod nije poznat… proverite“ i ponovo nudi „Prikači“ (I, iz `api.js`/`prijem-predmeta.js`; nije zaseban e2e).
- **Tim:** V2 ne nudi saradnju; stare timske rute su pod postojećom autorizacijom (OSB002, 58 ruta, u regresiji) i nisu uklonjene.

## 8. CI, Docker, rollback (Task 7)
**CI na tačnom SHA kandidata `c7b809f1` (P).** Poređenje po zaglavljima padova (puna imena) sa `main` `80c3902b` i sa PR #15 (`b5b9d5a8`, isto stablo kao `df5feb36` bez dokumenata).

| Posao | `main` | PR #15 | Kandidat | Novi padovi |
|---|---|---|---|---|
| Test Suite, Python 3.11 | 175 f / 7877 p | 175 / 8587 | 175 / 8601 | **0** (i prema `main` i prema #15) |
| Test Suite, Python 3.13 | 175 / 7877 | 175 / 8587 | 175 / 8601 | **0** |
| Prod. Python 3.11: import + full suite | 197 / 7337 | 197 / 8050 | 197 / 8064 | **0** |
| Byte-compile (3.11) | ok | ok | ok | — |
| **Docker**: build prod. slike + boot + OCR u slici (`srp+srp_latn+eng`, 21/21 reči) | ok | ok | ok | — |
| V2 NG: frontend suite (Chromium), preview ugovor, Docker gate | — | ok | ok | — |
| **Pregledač**: svih 9 `e2e:*` nad pravim FastAPI-jem; `e2e:solo-tok` **23/23 PASS**, `e2e:pre136` PASS | — | ok | ok | — |
| Security: gitleaks 8.30.1 („no leaks found“), sast, semgrep, pip-audit („No known vulnerabilities, 3 ignored“) | — | ok | ok | — |

- **Napomena:** padovi Test Suite i produkcionog Python-a su istorijski (isti identiteti na `main`), pa CI **nije potpuno zelen**.
- pip-audit prolazi samo zbog izuzetaka; izuzetak CVE-2026-85394 je u opseg izdanja ušao u NS006/RC1 i **nije odobren**.
- Run ID-jevi:
  - kandidat: 38166903442 (tests), 38166903441 (prod/Docker), 38166969521 (V2 NG), 38166903455 (security);
  - `main`: 38166971436, 38166973722.


**Rollback (P/I):**
- Tehnički: `80c3902b` je `origin/main`, nepromenjen; redeploy tog commita na Renderu (I; potvrda u dashboard-u). Migracija nema.
- V2 kao `/app` uključuje se samo promenljivom `VINDEX_V2_NG_PRIMARY_ENABLED` (podrazumevano isključena, globalna). Gašenje je uklanjanje promenljive i restart, bez promene koda. Asseti su adresirani po buildu (NS005.1).
- **Kad rollback nije čist (traži ručnu proveru):**
  - Neisporučeni `NewClientLinked` događaji iz novog koda: stari kod bi ih obradio **starom** posledicom, sa sukobom predmeta sa samim sobom i formulacijom „Ne možete zastupati“. Pre rollback-a proveriti `events` gde je `event_type='NewClientLinked' AND dispatched_at IS NULL`.
  - Poslovi koje je novi kod ostavio neprikačene (503) stari kod može ponovo finalizovati, ali bez ponovnog događaja. Takav dokument tada trajno ostaje bez tvrdnji (stari kvar).
  - Novi Smart Intake dokumenti koji su dobili tvrdnje ostaju ispravni. Posle rollback-a novi dokumenti se vraćaju na stari kvar (bez tvrdnji).
  - Već kreirana COI upozorenja ostaju (bezopasno).
- **Kriterijumi za rollback:**
  - 5xx na `/api/smart-intake/*/finalize` iznad uobičajenog;
  - rast stope `HALUCINACIJA v2.0` koji blokira normalne odgovore;
  - bilo kakav dokaz curenja između korisnika.

## 9. Integritet
`git diff --stat c7b809f1 <završni>` sadrži samo dva FRI001 dokumenta. Bez merge-a, deploy-a, migracija, Cron-a, produkcionih upisa, izmena promenljivih i izmena JWT izuzetka. Postojeće grane i PR-ovi nisu menjani.
