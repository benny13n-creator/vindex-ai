# FAZA 6.4 — PROVENANCE CONTRACT FORENSIC REPORT

## 1. Executive Summary

`predmet_hronologija.izvor` je uveden kao **cetvrta, nezavisna semanticka osa**.
Migracija 127 je **napisana i NIJE pokrenuta** (nema DDL kanala — pokrece je
vlasnik). Svih **16 pisaca** eksplicitno salje kanonsku provenijenciju. Kapija
`sme_pokrenuti_obavezu` vise **ne cita `akter`** — cita `izvor`, i to kao **belu
listu**: sve sto nije u njoj (ukljucujuci `None`, odsutan kljuc i nepoznatu
vrednost) trazi ljudsku potvrdu.

Mutacije **13/13 KILLED**. Regresija **1421 prosla, 0 novih padova**
(8 `[trio]` padova dokazano pre-postojecih na cistom HEAD-u).

## 2. Pre-Migration Environment
0 GPT poziva · 0 email/SMS · 0 push/deploy · 0 novih produkcionih redova ·
fixture netaknut · migracija NIJE izvrsena.

## 3. Starting SHA
```
HEAD pre sprinta  fadd7026      origin/main = production  044c5310
```
Baseline brojevi identicni FAZI 6.3: `23 / 44 / 55 / 26 / 31 / 12`.

## 4. Schema Before
```
akter, created_at, datum, datum_iso, dogadjaj, dokument_id,
dokument_naziv, id, predmet_id, user_id, vaznost      -- `izvor` NE POSTOJI
```

## 5. Canonical Provenance Contract
```sql
izvor TEXT NOT NULL
  CHECK (izvor IN ('AI_AUTONOMOUS','AI_ASSISTED','HUMAN_DIRECT',
                   'DETERMINISTIC','SYSTEM','LEGACY_UNKNOWN'))
-- BEZ DEFAULT-a
```
Sifarnik u kodu: `shared/rokovi.py::IZVOR_DOZVOLJENI`.

## 6. Migration Sequence (`migrations/127_hronologija_izvor_provenance.sql`)
```
1  ADD COLUMN izvor TEXT              (nullable, bez default-a — privremeno)
2  UPDATE ... SET izvor='LEGACY_UNKNOWN' WHERE izvor IS NULL   (backfill)
3  ADD CONSTRAINT ..._izvor_check                              (CHECK)
4  ALTER COLUMN izvor SET NOT NULL
5  ALTER COLUMN izvor DROP DEFAULT     (brava protiv buduceg "pomocnog" default-a)
```
NOT NULL pre backfill-a bi pao na 55 postojecih redova — zato ovaj redosled.
Testovi `test_redosled_je_backfill_pa_not_null` i `test_NEMA_DEFAULT_a` to cuvaju.

**OBAVEZAN REDOSLED PRIMENE: migracija PRVO, deploy koda POSLE.** Obrnuto obara
svaki upis u hronologiju (kolona ne postoji). Zapisano i u zaglavlju migracije.

## 7–8. Backfill Strategy i Counts
Svih **55 → `LEGACY_UNKNOWN`**, bez izuzetka i bez heuristike.

Razmatrano i **odbaceno**: klasifikovati `akter IN ('Genome (AI)','Pipeline (AI)')`
kao `AI_AUTONOMOUS`. Odbaceno jer bi i to bila heuristika **nad `akter`** — tacno
onim poljem cija je nepouzdanost i dovela do ove migracije.

```
pre backfill-a:  55 redova bez provenijencije
posle:            0 bez provenijencije,  55 LEGACY_UNKNOWN
HUMAN_DIRECT:     0     (izricito: legacy NIJE ljudski)
```
Ocekivano stanje posle pokretanja; provera upitom iz zaglavlja migracije.

## 9. All 16 Writer Updates

| # | Writer | Fajl | `izvor` |
|---|---|---|---|
| 1 | W-UPLOAD | `api.py` | `AI_AUTONOMOUS` |
| 2 | W-GENOME | `routers/case_dna.py` | `AI_AUTONOMOUS` |
| 3 | W-PIPELINE | `services/case_pipeline.py` | `AI_AUTONOMOUS` |
| 4 | W-SMARTINTAKE | `routers/smart_intake.py` | `AI_AUTONOMOUS` |
| 5 | W-CONFIRMLINKS | `api.py` | `AI_ASSISTED` |
| 6 | W-COPILOT | `routers/copilot.py` | `AI_ASSISTED` |
| 7 | W-INTAKE-ROK | `routers/intake.py` | `AI_ASSISTED` |
| 8 | W-ROCISTE | `routers/rocista.py` | `HUMAN_DIRECT` |
| 9 | W-UGOVOR | `routers/ugovor_zastupanja.py` | `HUMAN_DIRECT` |
| 10 | W-CLOSE | `routers/predmeti_close.py` | `HUMAN_DIRECT` |
| 11 | W-INTAKE-TPL1 | `routers/intake.py` | `DETERMINISTIC` |
| 12 | W-INTAKE-TPL2 | `routers/intake.py` | `DETERMINISTIC` |
| 13 | W-ROKOVILANAC | `routers/rokovi_lanac.py` | `DETERMINISTIC` |
| 14 | W-EVOLUTION | `services/case_evolution.py` | `SYSTEM` |
| 15 | W-LEARNING | `routers/learning.py` | `SYSTEM` |
| 16 | W-ONBOARDING | `routers/onboarding.py` | `SYSTEM` |

Nijedan ne koristi fallback ni izvodjenje iz `akter` — svaki nosi kanonsku
konstantu `_IZVOR.IZVOR_*` iz jednog vlasnika (`shared/rokovi.py`).

## 10. Writer Coverage
`test_svaki_pisac_dodeljuje_izvor` broji kanonske dodele po fajlu i trazi tacno
ocekivani broj; `test_ukupan_broj_pisaca_je_16` sabira na 16.

Ne broje se `.insert(` pozivi: `api.py` gradi red kroz `rows.append({...})`, a
`rokovi_lanac.py` kroz `records = [...]` — tekstualno uparivanje bi merilo
**oblik koda** umesto ugovora. Broj kanonskih dodela je direktan dokaz i pada cim
neko doda 17. pisca bez provenijencije.

## 11. `akter` / `izvor` Separation
```
akter    KO je izvrsio radnju (stranka u dogadjaju)
izvor    KAKO je sadrzaj nastao
potvrda  DA LI je covek odobrio izvrsivu upotrebu   (audit_immutable)
vaznost  KOLIKO je dogadjaj vazan
```
`test_akter_NE_UTICE_na_odluku` proverava 6 razlicitih `akter` vrednosti uz istu
`izvor` klasu — ishod mora biti identican. `test_akter_koji_izgleda_kao_ai_ne_
blokira_ljudski_red` pokriva obrnut smer (`akter='Genome (AI)'` + `HUMAN_DIRECT`
→ ALLOW): `akter` ne sme ni da propusti ni da blokira.

## 12. Gate Migration
```python
if red.get("izvor") in IZVOR_SME_BEZ_POTVRDE:   # AI_ASSISTED, HUMAN_DIRECT,
    return True                                 # DETERMINISTIC, SYSTEM
# sve ostalo trazi potvrdu
```
**BELA lista, ne crna.** Crna bi svaku buducu, jos neuvedenu klasu tiho
propustila. `None`, odsutan kljuc i nepoznata vrednost → DENY.

Svih **7 gejtovanih upita** (email ×3, SMS ×2, notifikacije ×2) sada dovlace
`izvor`; nijedan vise ne dovlaci `akter` kao poreklo.

**Provenijencija NIJE ovlascenje.** `AI_ASSISTED`/`HUMAN_DIRECT`/`DETERMINISTIC`/
`SYSTEM` prolaze ovu kapiju, ali se time NE tvrdi da su potvrdjeni — samo da im
sadrzaj nije proizveo model bez ljudskih ociju.

## 13. Legacy Safety
`LEGACY_UNKNOWN` je u `IZVOR_TRAZI_POTVRDU` → **NO ACTION** bez potvrde.
Automatski potvrdjenih legacy redova: **0**. Backfill ne upisuje nijednu potvrdu.

## 14–15. No-Default / Invalid-Value Enforcement
`test_NEMA_DEFAULT_a` odbija i `SET DEFAULT` i `ADD COLUMN ... DEFAULT`, i trazi
eksplicitan `DROP DEFAULT`. `test_check_pokriva_tacno_sest_vrednosti` pada i ako
se doda sedma vrednost i ako se izostavi jedna.

Baza je primarna brava: bez `izvor` → **23502**, nepoznata vrednost → **23514**.

## 16. Action Safety Matrix (§18)
```
A  AI_AUTONOMOUS  + kritičan + nepotvrdjen -> NO ACTION
B  AI_AUTONOMOUS  + važan    + nepotvrdjen -> NO ACTION
C  AI_ASSISTED    + kritičan + nepotvrdjen -> prolazi provenijenciju,
                                              ali NIJE implicitno potvrdjen
D  HUMAN_DIRECT   + kritičan               -> postojeci behavior
E  LEGACY_UNKNOWN + nepotvrdjen            -> NO ACTION
F  email UKLJUCEN + AI_AUTONOMOUS nepotvrdjen -> NO SEND
G  email UKLJUCEN + AI_AUTONOMOUS POTVRDJEN   -> salje (kontrolni par)
```
`test_vaznost_ne_utice_na_kapiju` dokazuje da `vaznost` nije ovlascenje.

## 17. Production Data Integrity
```
predmeti 23 · predmet_dokumenti 44 · predmet_hronologija 55 · case_actions 31
kolona `izvor` u produkciji: NE POSTOJI  (migracija nije pokrenuta — ocekivano)
```

## 18. Fixture Integrity
Fixture `fb6f7ebd` / dokument `0ab218de` i sva tri roka netaknuti.

## 19. Regression Results
```
ciljani podskup:  1421 prosla,  6 palo
   od toga PRE-POSTOJECE [trio]: 5
   moje:                          1  -> popravljeno, sada prolazi
finalna provera 9 kljucnih fajlova: 162 prosla
mutacije: 13/13 KILLED
```
Baseline na cistom HEAD-u: **8 `[trio]` padova** (`test_prg_night_register` 5,
`test_coi_intake_convergence` 3). **Nula novih padova.**

## 20. Known Limitations
1. **Migracija NIJE pokrenuta.** Do tada `izvor` ne postoji, pa bi deploy koda
   oborio svaki upis u hronologiju. Redosled je obavezan.
2. Posle deploy-a **svih 55 postojecih rokova prestaje da bude izvrsivo** dok ih
   covek ne potvrdi (`LEGACY_UNKNOWN`). To je namerna posledica odluke iz §0,
   ne regresija.
3. **Nema rute ni UI za potvrdu** (`potvrdi_rok`/`odbij_rok` postoje kao
   funkcije) — dok je nema, `AI_AUTONOMOUS` i `LEGACY_UNKNOWN` su trajno
   neizvrsivi.
4. Fixture-i u 6 postojecih test fajlova su dopunjeni sa `"izvor"` da ostanu
   verni semi; njihovi ugovori nisu menjani.

## 21. Out-of-Scope Findings (prijavljeno, NIJE dirano)
1. `W-UPLOAD` prihvata `vaznost` **direktno iz LLM-a** (§19) — model sam sebi
   dodeljuje najvisi prioritet. Kapija to sada neutralise, ali izvor stoji.
2. `intake.py:1042` upisuje `akter="Template (AI)"` a sadrzaj je **staticki
   katalog** — pogresna oznaka.
3. **Nema UPDATE/DELETE putanje** za rok (§20) — ne moze se ispraviti ni povuci.
4. `predmet_genome_history` uvek kasni jednu verziju (upisuje STARI genome).

## 22. Files Changed
```
migrations/127_hronologija_izvor_provenance.sql   (nov)
shared/rokovi.py                                  +76 -1
api.py · routers/{case_dna,copilot,email_notif,intake,learning,notifications,
  onboarding,predmeti_close,rocista,rokovi_lanac,smart_intake,sms,
  ugovor_zastupanja}.py · services/{case_evolution,case_pipeline}.py
tests/  test_faza64_provenance_contract.py (nov) + 8 azuriranih
                                    ukupno 25 fajlova, +268 / -142
```
`git diff --check`: cisto.

## 23. Files Not Changed
Genome prompt i extraction schema · `predmeti.case_dna` · V2 (`issue_v2`,
`contradiction_identity`, `v2_*`) · `shared/rok_potvrda.py` · `audit_immutable`
sifarnik · UI (`index.html`, `static/vindex.js`) · Dockerfile · Procfile ·
`.github/workflows/` · fixture podaci · produkciona sema.

## 24. Local Commits
`27a4dd87` (6.2) · `5ab3990d` (6.2.1) · `fadd7026` (6.3) · **ovaj (6.4)**.
`origin/main` = `044c5310`. **Nista nije pushovano.**

## 25. FINAL VERDICT

🟡 **BLOCKED — ugovor je kompletan, migracija ceka vlasnika**

Sve inzenjerski dokazivo je ispunjeno: `NOT NULL` + `CHECK` + **bez DEFAULT-a**,
svih 16 pisaca salje provenijenciju, backfill je determinististican bez
heuristike, `akter` se vise ne cita kao poreklo, kapija je bela lista, potvrda
ostaje odvojena osa, 13/13 mutacija ubijeno, 0 novih padova.

GREEN nije opravdan jer **finalno stanje seme nije dokazano** — nema DDL kanala,
pa migracija 127 nije pokrenuta. Mandat §26 trazi da schema contract POSTOJI, a
on trenutno postoji samo kao datoteka. Dokaz iz introspekcije (§6) moguc je tek
posle pokretanja.

**Potrebne su dve tvoje radnje, ovim redom:**
1. pokreni `migrations/127_hronologija_izvor_provenance.sql` u Supabase SQL editoru;
2. tek onda odobri push/deploy koda.

Obrnut redosled obara svaki upis u `predmet_hronologija`.
