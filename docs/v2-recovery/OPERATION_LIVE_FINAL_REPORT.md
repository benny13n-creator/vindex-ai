# OPERATION LIVE — završni izveštaj (2026-10-11)

Oznake: **P** dokazano · **I** zaključeno · **U** nepoznato.

## 1. Stanje produkcije
- **Adresa:** https://vindex.rs/app (isto: https://vindex-ai.onrender.com/app).
- **Može li se otvoriti:** da. `/app` je **V2** (build `@6ad0b13`), bez JS grešaka i bez 5xx (P, pravi Chromium nad produkcijom). Stari UI je na `/app-legacy`.
- **Prijava:** postojeći put radi do formulara: `/app` → „Prijavite se“ → `/app-legacy?posle=app` → „Već imam nalog“ → modal (email + lozinka). Posle prijave skripta vraća na `/app` (P do formulara; I za samu prijavu: nemam nalog, a lozinke nisam izmišljao ni čitao).
- **Produkcioni SHA:** `6ad0b13a2ccfeb8cc28094e7be4e2743bd8fab4f` (`/health`: `status ok`, `commit 6ad0b13`, `redis true`, `workers 1`) (P).
- **Render:** servis `vindex-ai` (Docker, `main`, AutoDeploy). Deploy je pokrenut automatski posle merge-a i nov commit je bio živ za oko 60 s. ID deploy-a ne vidim, jer nemam pristup Render API-ju (U); status potvrđuje `/health`. Prethodni živi commit je bio `9c6f863` (spojeni PR #16 i #17).

## 2. Šta je ispravljeno
| Fajl | Kvar | Commit | Regresija | Deploy |
|---|---|---|---|---|
| `routers/intake.py` | stara provera „ime prvo“ (`POST /api/intake/conflict-check`, prikazuje se u čarobnjaku `/app-legacy`) je za podudaranje imena pisala „Postoji BLOKIRAJUCI sukob… **Ne možete zastupati**… (čl. 42 Zakona o advokaturi)“. Sada: „**Mogući sukob interesa — potrebna provera**… nije pravna ocena“. Ozbiljnost i ugovor odgovora su isti | `4b51fbf2` → merge PR #18 `6ad0b13a` | `tests/test_live_coi_formulacija.py` (4), test formulacije pada na starom kodu | živ, `6ad0b13` (P) |

**CI PR #18 u odnosu na `main` `9c6f863`, po identitetu testa (P):**
- Test Suite 3.11 i 3.13: 175 = 175 nasleđenih, **0 novih**, +4 prošla.
- Produkcioni Python: 197 = 197, 0 novih.
- Docker build, boot i srpski OCR u slici (`srp+srp_latn+eng`): uspeh.
- Security (gitleaks, sast, semgrep, pip-audit i rok JWT izuzetka): zelen.

## 3. Šta je provereno
| Oblast | Rezultat |
|---|---|
| Javne rute, V2 asseti, kapija `/health` | **P** (produkcija) |
| Prijava (formular, preusmeravanje) | **P** do formulara; sama prijava **U** (nema test naloga) |
| Klijent → predmet → Smart Intake → dokument → dokazi → Genome → akcije → pitanje → nacrt (ceo solo tok) | **P u izolovanom okruženju**: CI `e2e:solo-tok` 23/23 na istom runtime kodu (FRI001, run 38166969521); u produkciji sa prijavom **U** |
| OCR (srpska ćirilica i latinica) | **P** u produkcionoj Docker slici (CI); živi upload **U** |
| Dokument: bez lažnog uspeha, oporavak, bez duplikata | **P** (lokalna regresija) |
| Citati: pogrešan zakon/član nije „proveren“ | **P** (lokalno) |
| COI: mogući a ne potvrđen sukob, neuspeh nije „čisto“, bez curenja | **P** (lokalno + CI) |
| ACL (RH001/RH002, vlasništvo predmeta i dokumenta) | **P** (lokalno) |
| JWT: 0 prihvaćenih falsifikata; rok izuzetka do 2027-01-09 | **P** (lokalno + CI korak) |
| Isključena autonomija (bez 136, bez Cron-a) | **P** (testovi); produkcija: rute traže prijavu (401) |

Lokalna ciljana regresija na grani ispravke: **326 passed, exit 0** (11 OCR preskočeno lokalno; pokriveno Docker-om u CI-ju).

## 4. Poznata ograničenja (materijalna za betu)
- U prvoj sekundi posle učitavanja `/app-legacy` stranica se još jednom sama učita, pa rani klik na „Već imam nalog“ ponekad ne otvori prijavu. Ponovni klik radi. Ovo je postojeće ponašanje starog UI-ja.
- V2 sopstvena COI provera (povezivanje klijenta) za fuzzy podudaranje u aktivnom predmetu i dalje piše „Sukob interesa u aktivnom predmetu“ i zaustavlja povezivanje. To je zaseban V2 tok i nije menjan.
- V2 dokumenti otpremljeni pre ovog izdanja verovatno nemaju dokaze (I). Ručno „Reklasifikuj“ u `/app-legacy`.
- Zakazani GitHub workflow „Email Podsetnici za rokove“ poslednji put nije uspeo (postojeće stanje, nije menjano).

## 5. Verdikt
**LIVE — READY FOR FOUNDER USE.** Aplikacija je javno dostupna na tačnom SHA, V2 je primarni interfejs, a put do prijave radi. Jedino što nisam mogao da izvedem sam je prijavljeni produkcioni prolaz, jer nemam nalog. Vaša prva prijava je taj test.

## 6. Prvi koraci za vas
1. Otvorite **https://vindex.rs/app**, kliknite „Prijavite se“, pa „Već imam nalog“, i prijavite se svojim postojećim nalogom (email + lozinka).
2. U V2: „Predmeti“ → napravite **probni** predmet, pa otpremite jedan kratak PDF bez pravih podataka klijenata i prikačite ga.
3. Posle 1–2 minuta otvorite predmet i pogledajte dokaze, analizu i akcije; zatim postavite jedno pitanje (troši kredit).

**Ograničenje:** u produkciju za sada unosite samo probne podatke, bez stvarnih poverljivih podataka klijenata, dok ne potvrdite da je prvi prolaz uredan.
