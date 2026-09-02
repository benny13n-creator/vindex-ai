# FAZA 6.4.1 — PROVENANCE ↔ AUTHORIZATION ADVERSARIAL GATE

## 1. Baseline
```
HEAD         aa986192          (ocekivano aa986192)   OK
origin/main  044c5310          (ocekivano 044c5310)   OK
git status nad kodom/testovima/migracijama: CISTO
```
`git status` prijavljuje 121 stavku, ali su sve nepracene `data/` datoteke i
izvestaji iz ranijih faza — nijedan prati kod.

**0 izmena koda · 0 izmena testova · 0 DDL · 0 commit · 0 push · 0 deploy.**

## 2–3. Semantika (formalna provera)

| Atribut | Znacenje u kodu | Nosi li vise od jedne funkcije? |
|---|---|---|
| `akter` | EVENT ACTOR | ne — kapija ga vise ne cita (dokazano §7) |
| `izvor` | CONTENT PROVENANCE | **DA — v. RED-1** |
| potvrda (`audit_immutable`) | AUTHORIZATION | ne |
| `vaznost` | PRIORITY | ne — kapija je ne cita (dokazano §8) |
| `status` | ne postoji na `predmet_hronologija` | — |

**`SEMANTIC OVERLOAD` prijavljen na `izvor`.**

## 4. `sme_pokrenuti_obavezu` — execution trace

Telo bez docstringa i komentara:
```python
def sme_pokrenuti_obavezu(red, potvrdjeni_ids=None):
    if red.get("izvor") in IZVOR_SME_BEZ_POTVRDE:
        return True                       # <-- ALLOW iskljucivo na osnovu provenijencije
    rid = red.get("id")
    if not rid:
        return False
    return rid in (potvrdjeni_ids or set())
```

1. **Inputi koji odlucuju:** `red["izvor"]`, `red["id"]`, `potvrdjeni_ids`.
2. **Da li se `izvor` koristi kao authorization?** **DA.** Prva grana vraca
   `True` bez ijedne provere potvrde.
3. **Gde se proverava confirmation?** Samo u poslednjoj liniji — i to samo za
   klase koje NISU u beloj listi.
4. **Postoji li grana gde `izvor` sam daje ALLOW?** **DA — 4 od 6 klasa.**
5. **Odsustvo potvrde kao implicitno odobrenje?** **DA**, za te 4 klase.
6. **Fail-open?** Ne za nepoznato/odsutno (v. §12) — ali jeste za 4 imenovane klase.

## 5. Obligaciona matrica (mereno pozivanjem funkcije)

```
izvor            vaznost     UNCONFIRMED   CONFIRMED
AI_AUTONOMOUS    kritičan          DENY       ALLOW
AI_AUTONOMOUS    važan             DENY       ALLOW
AI_ASSISTED      kritičan         ALLOW       ALLOW     <- ocekivano NO ACTION
AI_ASSISTED      važan            ALLOW       ALLOW     <- ocekivano NO ACTION
HUMAN_DIRECT     kritičan         ALLOW       ALLOW     <- implicitna potvrda
HUMAN_DIRECT     važan            ALLOW       ALLOW     <- implicitna potvrda
DETERMINISTIC    kritičan         ALLOW       ALLOW     <- implicitna potvrda
DETERMINISTIC    važan            ALLOW       ALLOW     <- implicitna potvrda
SYSTEM           kritičan         ALLOW       ALLOW     <- implicitna potvrda
SYSTEM           važan            ALLOW       ALLOW     <- implicitna potvrda
LEGACY_UNKNOWN   kritičan          DENY       ALLOW
LEGACY_UNKNOWN   važan             DENY       ALLOW
```

## 6. Mutacije (konceptualno, bez izmene repozitorijuma)

| # | Napad | Ishod | Ocena |
|---|---|---|---|
| M1 | `AI_AUTONOMOUS → HUMAN_DIRECT`, bez potvrde | postaje ALLOW | 🔴 provenijencija sama daje ovlascenje |
| M2 | `LEGACY_UNKNOWN → DETERMINISTIC`, bez potvrde | postaje ALLOW | 🔴 |
| M3 | `AI_ASSISTED → HUMAN_DIRECT`, bez potvrde | oba vec ALLOW | 🔴 (obe klase vec prolaze) |
| M4 | `izvor = None` | DENY | 🟢 |
| M5 | kljuc `izvor` odsutan | DENY | 🟢 |
| M6 | `izvor = "FUTURE_AGENT"` | DENY | 🟢 |
| M7 | `kritičan` + `AI_AUTONOMOUS` + nepotvrdjen | DENY | 🟢 |
| M8 | `važan` + `AI_AUTONOMOUS` + nepotvrdjen | DENY | 🟢 |
| M9 | `HUMAN_DIRECT` + `kritičan` + nepotvrdjen | **ALLOW** | 🔴 |

M1/M2/M3/M9 nisu napadi na implementaciju — oni pokazuju da je **sam model**
takav da promena provenijencije menja ovlascenje.

## 7. `akter` separation proof — 🟢 CIST

- Telo kapije: `akter` se ne pojavljuje (samo u docstringu, istorijski).
- `je_ai_poreklo` i `AI_AKTERI`: **0 pozivaoca van `shared/rokovi.py` i testova.**
- Svih 7 gejtovanih upita dovlaci `izvor`; **nijedan vise ne dovlaci `akter`**.

## 8. `vaznost` separation proof — 🟢 CIST (uz ogradu)

Kapija ne cita `vaznost` (mereno: 0 pojava u telu). `vaznost` i dalje filtrira
KOJI redovi su kandidati (`.in_("vaznost", _ACTIONABLE_VAZNOST)`), ali odluku o
izvrsenju donosi kapija.

**Ograda:** na Viber putu (RED-2) kapije nema, pa tamo `vaznost="kritičan"`
**jeste** jedini uslov slanja — dakle LLM-dodeljen prioritet vodi direktno u
poruku. To je posledica RED-2, ne slabost `vaznost` semantike same po sebi.

## 9. Action paths — **8, ne 7**

| # | Put | Kanal | Gejt |
|---|---|---|---|
| 1–3 | `email_notif.py` (send-reminders, digest ×2) | email | 🟢 |
| 4–5 | `sms.py` (cron batch, digest) | SMS | 🟢 |
| 6–7 | `notifications.py` (nadolazeci, propusteni) | notifikacija | 🟢 |
| **8** | **`viber.py::_briefing_tekst` → `POST /api/viber/send-briefing`** | **Viber** | **🔴 NEMA** |

Provereni i **odbaceni** kao ne-izvrsivi: `api.py`, `ccc.py`, `search.py`,
`intake.py` (pogotci na „kanal" su komentari ili `include_router`),
`case_evolution.py` (pise `notifications` iz `case_actions`, ne iz hronologije).

`client_portal.py` cita hronologiju i prikazuje je **klijentu** — nije push, ali
jeste izlaganje nepotvrdjenog AI sadrzaja trecem licu (v. §15 RIZIK-1).

## 10. Migracija 127 — 🟢 UGOVOR ISPRAVAN (nije pokrenuta)

```
ADD COLUMN izvor TEXT            (bez DEFAULT-a)
UPDATE ... SET izvor='LEGACY_UNKNOWN' WHERE izvor IS NULL
ADD CONSTRAINT ..._izvor_check CHECK (6 vrednosti)
ALTER COLUMN izvor SET NOT NULL
ALTER COLUMN izvor DROP DEFAULT
```
`SET DEFAULT`: **False** · `DEFAULT` u `ADD COLUMN`: **False** ·
`CHECK` vrednosti: **tacno 6**.

## 11. Legacy proof — 🟢
Jedini `SET izvor` u migraciji je `'LEGACY_UNKNOWN'`, uslovljen samo
`WHERE izvor IS NULL`. Nijedna heuristika (`akter`, `dokument_naziv`, `vaznost`,
naziv dogadjaja, datum) se ne koristi.

## 12. Fail-closed za buducu vrednost — 🟢
```
izvor = "FUTURE_AGENT"  -> DENY
izvor = None            -> DENY
kljuc odsutan           -> DENY
izvor = ""              -> DENY
```
Bela lista (`in IZVOR_SME_BEZ_POTVRDE`) garantuje da sedma vrednost uvedena bez
izmene kapije **pada zatvoreno**. Ovo je jedina tacka gde je dizajn radio tacno
ono sto je namerano.

## 13. Kljucno arhitektonsko pitanje — **DA, postoji takav state**

> „Ovaj zapis je ljudskog porekla, zato je automatski odobren."

`izvor = HUMAN_DIRECT` → ALLOW bez ijedne potvrde. Isto za `DETERMINISTIC`,
`SYSTEM` i `AI_ASSISTED`. Per §13 → **RED**.

## 14. Testovi (nepromenjeni)
```
116 prosla, 0 palo
```
(`test_faza64_provenance_contract`, `test_faza621_provenance_boundary`,
`test_faza62_ai_observation_gate`, `test_faza62_gate_e2e_paths`,
`test_b10_reminder_claim`)

**Novih padova: 0. Pre-postojecih padova u ovom skupu: 0.**
Poznatih 8 `[trio]` padova (`test_prg_night_register`, `test_coi_intake_convergence`)
nije u ovom skupu i nije dirano.

## 15. Pronadjeni rizici

### 🔴 RED-1 — `izvor` sam daje ovlascenje za 4/6 klasa
`IZVOR_SME_BEZ_POTVRDE = (AI_ASSISTED, HUMAN_DIRECT, DETERMINISTIC, SYSTEM)`.
Ime konstante doslovno znaci „izvor sme bez potvrde" — provenijencija JESTE
autorizacija. Docstring iste funkcije tvrdi suprotno („PROVENIJENCIJA NIJE
OVLASCENJE... time se NE tvrdi da su potvrdjeni") dok kod vraca `True`.
**Dokumentacija i ponasanje su u protivrecnosti.**

Posteno razgranicenje: ovo NIJE skriveni bag — to je ugovor koji sam
implementirao u FAZI 6.4 pod tada zadatim pravilom („`AI_AUTONOMOUS` mora biti
gejtovan"). FAZA 6.4.1 §5 sada postavlja **strozi** ugovor: autorizacija je
zasebna odluka za SVE klase. Pod novim ugovorom kod je RED.

### 🔴 RED-2 — osmi izvrsivi put bez kapije (Viber)
`routers/viber.py:281` cita `predmet_hronologija` filtrirano po
`vaznost="kritičan"`, renderuje „Hitni rokovi (7 dana)" i salje kroz
`POST /api/viber/send-briefing`. **`izvor` se ne dovlaci, kapija se ne zove.**

Nepotvrdjen AI rok ide pravo u advokatov Viber. Moje ranije tvrdnje o „svih 7
izvrsivih putanja" (FAZA 6.2 §10, FAZA 6.4 §12) su bile **nepotpune** — popis
nikad nije obuhvatio Viber kanal.

### 🟡 RIZIK-1 — nepotvrdjen AI rok vidljiv klijentu
`routers/client_portal.py:434,452` prikazuje hronologiju u klijentskom portalu.
Nije push i nije obaveza, pa ne pada pod definiciju action gate-a — ali jeste
izlaganje neverifikovanog AI sadrzaja trecem licu. Prijavljeno, nedirano.

## 16. Out-of-scope nalazi (nedirano)
1. `W-UPLOAD` prihvata `vaznost` direktno iz LLM-a — model sam sebi dodeljuje
   prioritet. Na 7 gejtovanih putanja kapija to neutralise; **na Viber putu ne.**
2. `intake.py:1042` upisuje `akter="Template (AI)"` a sadrzaj je staticki katalog.
3. Nema UPDATE/DELETE putanje za rok.
4. `predmet_genome_history` uvek kasni jednu verziju.

## 17. VERDICT

# 🔴 BLOCKED

Provera po tackama iz §17:

| Kriterijum | Ishod |
|---|---|
| `PROVENANCE ≠ AUTHORIZATION` | 🔴 **NIJE** — 4/6 klasa prolazi na osnovu provenijencije |
| `AKTER ≠ PROVENANCE` | 🟢 dokazano |
| `VAZNOST ≠ AUTHORIZATION` | 🟢 u kapiji · 🔴 na Viber putu (nema kapije) |
| `UNKNOWN ≠ ALLOW` | 🟢 dokazano |
| `MISSING ≠ ALLOW` | 🟢 dokazano |
| `AI ≠ AUTO-AUTHORIZED` | 🔴 `AI_ASSISTED` je auto-autorizovan |
| `HUMAN_DIRECT ≠ IMPLICIT_CONFIRMATION` | 🔴 **jeste implicitna potvrda** |
| `DETERMINISTIC ≠ IMPLICIT_CONFIRMATION` | 🔴 jeste |
| `SYSTEM ≠ IMPLICIT_CONFIRMATION` | 🔴 jeste |
| `LEGACY_UNKNOWN = FAIL-CLOSED` | 🟢 dokazano |
| 0 authorization bypasses | 🔴 **1** (Viber) |
| 0 `akter`-based provenance decisions | 🟢 |
| 0 fail-open unknown states | 🟢 |
| 0 direct action bypasses | 🔴 **1** (Viber) |
| 0 semantic overload | 🔴 `izvor` nosi i provenijenciju i autorizaciju |

**MIGRACIJA 127 SE NE SME POKRENUTI.** Ne zato sto je sama pogresna — njen
ugovor je dokazano ispravan (§10) — nego zato sto bi njeno pokretanje ucvrstilo
model u kome `izvor` odlucuje o izvrsenju, a to je upravo klasa greske koju su
FAZE 6.1–6.3 razotkrile kod `akter` polja.

**Nista nije popravljeno, predlozeno kao workaround, niti commit-ovano.**
`origin/main` = `044c5310`. Cetiri lokalna commita i dalje cekaju.
