# FAZA 6.6.1 — INCIDENT RECOVERY + SAFE PROVENANCE ROLLOUT

## 0. Ispravka moje preporuke iz FAZE 6.6

U 6.6 sam preporucio **`DROP NOT NULL` kao prvi korak**. Mandat 6.6.1 je trazio
da tu tezu aktivno oborim — i **oborena je**.

`DROP NOT NULL` je **losiji** plan. Dokaz je u §5.

## 1. Baseline (§1)
```
HEAD lokalno   3039332a       origin/main = production   044c5310
produkcija     044c5310       (potvrdjeno /api/version i /health)
workers 1 · pid 7 · render.yaml NE postoji u repou (config je u dashboard-u)
git status nad kodom: cisto (jedini novi fajl je test iz ove faze)
```

## 2. Stvarno stanje seme — read-only, tri merenja (§4)
```
kolona `izvor` postoji
55 redova · svih 55 = LEGACY_UNKNOWN · NULL: 0
najnoviji red 2026-09-02T06:36:46 (fixture iz FAZE 6.1) — NIJEDAN red posle migracije

INSERT bez `izvor`              -> 23502   NOT NULL radi
INSERT sa izvor='NEPOSTOJECA'   -> 23514   CHECK radi
INSERT sa izvor='SYSTEM'        -> 23503   pada tek na FK  <-- KLJUC
```

Treci nalaz je presudan: **red sa validnim `izvor` prolazi sve provere kolone**
i pada tek zato sto moj probni `predmet_id` ne postoji. Dakle
**NOVI KOD + TRENUTNA SEMA = RADI.** Nikakav DDL nije potreban.

## 3. Tri pojma koja se ne smeju spajati (§2)

| Pojam | Stanje |
|---|---|
| **Production availability** | 🟡 **latentno**, ne aktivno. Nijedan red nije nastao posle migracije — nema saobracaja koji pogadja pisce. Prvi upload/refresh ce pasti. |
| **Data integrity** | 🟢 **nista nije izgubljeno do sada.** 55 redova netaknuto, 0 NULL, 0 anomalija. |
| **Provenance integrity** | 🟢 **ocuvana** — i to bas zato sto `NOT NULL` drzi. Nijedan red bez provenijencije ne moze nastati. |

Moja formulacija iz 6.6 („svaki upis u produkciji trenutno pada") je **tacna kao
tvrdnja o ponasanju**, ali sam je predstavio kao aktivno krvarenje. Nije: kvar je
**latentan** dok neko ne uploaduje dokument ili ne pokrene refresh. Ispravljam.

## 4. Incident map — 16 pisaca (§3, source inspection nad `044c5310`)

Svih 13 fajlova provereno `git show 044c5310:<fajl>`: **0 dodela `izvor`**.
Lokalni `3039332a`: **16/16 dodela**, svaka kanonska konstanta iz sifarnika.

| Pisac | Prod salje `izvor` | Ponasanje pri 23502 | Korisnik vidi | Gubitak |
|---|---|---|---|---|
| W-CONFIRMLINKS `api.py` | ne | proverava rezultat, dize | 🔴 da | ne |
| W-INTAKE-ROK | ne | dize | 🔴 da | ne |
| W-ROKOVILANAC | ne | `raise RuntimeError` → 503 | 🔴 da | ne |
| W-UGOVOR | ne | dize | 🔴 da | ne |
| W-EVOLUTION | ne | `raise` — posledica na sabirnici puca | 🔴 da | ne |
| **W-GENOME** | ne | `except` + `logger.warning` | ⚠️ **ne** | **da** |
| **W-UPLOAD** | ne | per-row `except`, log | ⚠️ **ne** | **da** |
| **W-SMARTINTAKE** | ne | `except` | ⚠️ **ne** | **da** |
| W-COPILOT | ne | vraca `uspeh: False` uz poruku | 🟡 delimicno | da |
| W-PIPELINE, W-CLOSE, W-LEARNING, W-ONBOARDING, W-INTAKE-TPL1/2 | ne | `except` + log | ⚠️ ne | da |
| W-ROCISTE | ne | oblik nije jednoznacan iz statickog citanja | ⚪ | ⚪ |

**5 glasno · 10 tiho · 1 nejasno.** Tiho je opasnije: advokat uploaduje dokument,
dobije potvrdu, a nijedan rok ne udje u hronologiju.

## 5. Zasto `DROP NOT NULL` NIJE resenje (§5, §1-A vs §1-B)

| | Plan „DROP NOT NULL prvo" | Plan „samo deploy" |
|---|---|---|
| DDL koraka | **2** (drop + kasnije restore) | **0** |
| Prozor u kome stari kod uspesno pise | **postoji** | ne postoji |
| Sta stari kod upise u tom prozoru | **red sa `izvor IS NULL`** | nista |
| Provenance integrity tokom prozora | 🔴 **narusena** | 🟢 ocuvana |
| Potreban drugi backfill posle | **da** (svi NULL redovi) | ne |
| Ako deploy padne | ostajemo sa nullable semom i NULL redovima | ostajemo tacno gde smo sad |
| Mesovit prozor | stara instanca **kvari podatke** | stara instanca **samo ne pise** |

Odgovori na §5 pitanja 1–9 za `DROP NOT NULL`: prozor traje **od DDL-a do kraja
deploya** (minuti, ne sekunde — Render gradi image); u njemu se mogu pozvati
**svih 16** pisaca; **mogu** nastati NULL redovi; prozor se **ne moze** pouzdano
ograniciti bez zaustavljanja servisa; ako deploy padne prozor ostaje otvoren
neograniceno; NULL redovi bi se prepoznavali kao `izvor IS NULL`, ali bi trebalo
**odluciti kojom klasom ih popuniti** — a to je tacno pogadjanje koje je ceo
program zabranio.

**Zakljucak: uklanjanje `NOT NULL` bi resilo incident tako sto bi otvorilo bas
onu rupu koju je incident sprecio.** Odbaceno.

## 6. Mixed-version analiza (§11)

`render.yaml` ne postoji u repou, pa **ne mogu dokazati** kako tacno Render
zamenjuje instance. Po §11 to i **ne pretpostavljam**. Umesto toga dokazujem da
je ishod isti u svakom slucaju:

```
stara instanca + trenutna sema  ->  23502            (identicno danasnjem stanju)
nova  instanca + trenutna sema  ->  upis prolazi
```

Nema kombinacije u kojoj stari kod upise **neispravan** red — on ne moze upisati
**nikakav**. Zato je mesovit prozor **monoton**: svaka zamenjena instanca je
strogo poboljsanje, a nijedna ne kvari podatke.

To je razlika izmedju ovog plana i svakog expand/contract plana, i razlog zasto
ovde expand/contract **nije potreban**: ekspanzija je vec izvrsena (migracijom),
samo pogresnim redosledom u odnosu na kod.

## 7. IZABRANI PLAN — jedan korak

### PLAN B — DEPLOY ONLY (bez DDL-a)

1. **Precondition**
   - schema: `izvor` postoji, `NOT NULL`, `CHECK` nad 6 vrednosti, bez DEFAULT-a — **vec ispunjeno**
   - 55 legacy redova = `LEGACY_UNKNOWN` — **vec ispunjeno**, ne dira se
   - `git status` cist, testovi zeleni

2. **DB promena** — **NIJEDNA.** Nema ALTER-a, nema migracije, nema backfill-a.

3. **Application SHA** — `3039332a` (7 commita: `27a4dd87`, `5ab3990d`,
   `fadd7026`, `aa986192`, `773213e2`, `702e6bd0`, `3039332a`)

4. **Redosled** — `git push origin main` → Render build → health check → zamena.

5. **Mixed-version rizik** — 🟢 monoton, v. §6.

6. **Rollback** — `git revert` ili redeploy `044c5310`. Vraca se **tacno
   danasnje stanje** (23502), ne gore. **Sema se ne dira, pa nema sta da se
   vraca.** Nijedan podatak se ne gubi: redovi upisani novim kodom imaju validan
   `izvor` i ostaju validni i pod starim kodom (koji ih samo cita).

7. **Verifikacija posle deploya**
   ```sql
   SELECT izvor, count(*) FROM predmet_hronologija GROUP BY izvor;
   SELECT count(*) FROM predmet_hronologija WHERE izvor IS NULL;   -- mora biti 0
   ```
   ```
   GET /api/version              -> commit_short = 3039332
   GET /api/rokovi/kandidati     -> 200, stanje_odluke = UNCONFIRMED
   ```
   Zatim jedan stvaran upis (upload ili refresh) i provera da je red nastao sa
   ocekivanim `izvor`.

8. **Success criteria** — 0 novih `23502` u logu · novi redovi nose kanonski
   `izvor` · `izvor IS NULL` = 0 · autorizaciona granica nepromenjena.

9. **Contract step** — **nema ga.** Finalni ugovor je vec na snazi.

10. **Dokaz da ugovor ostaje nepromenjen** — `test_migracija_i_dalje_nosi_finalni_ugovor`
    i `test_migracija_nije_menjana_posle_faze_64` (migracija je bajt-identicna
    verziji iz `aa986192`).

## 8. Sta se menja za korisnika istog trenutka (mora se znati pre odobrenja)

Deploy aktivira i granicu iz faza 6.2–6.5:

- svih 55 rokova je `LEGACY_UNKNOWN` = **nepotvrdjeno**;
- zato **email, SMS, Viber, WhatsApp, kalendar i klijentski portal za njih cute**
  dok ih advokat ne potvrdi;
- rute za potvrdu postoje (`/api/rokovi/kandidati`, `/potvrdi`, `/odbij`),
  **ekran ne postoji**.

Ublazavanje: danas ionako nista ne salje — `korisnik_email_notif` = **0 profila**,
`email_notif_log` = **0 redova**. Dakle deploy ne gasi nista sto trenutno radi.

## 9. Legacy podaci (§7)
55 redova ostaje `LEGACY_UNKNOWN`. Ne prevode se u `HUMAN_DIRECT`, ne
klasifikuju se heuristikom, ne brisu se. Potvrda ostaje odvojena odluka.

## 10. Testovi
```
tests/test_faza661_rollout_compatibility.py (nov)   51 prosla
regresija: 950 prosla, 1 preskocen, 2 palo
```
Oba pada su **pre-postojeci `[trio]`** (`test_prg_night_register`), dokazani na
cistom HEAD-u jos u FAZI 6.4. **0 novih.** Nijedan assert nije oslabljen.

## 11. VERDICT

# 🟢 GREEN — SAFE ROLLOUT PLAN PROVEN

| Uslov | |
|---|---|
| incident precizno karakterisan | 🟢 latentan, ne aktivan; 5 glasno / 10 tiho |
| nema nepoznatog mehanizma gubitka | 🟢 0 NULL, 0 novih redova, 0 anomalija |
| novi kod kompatibilan sa produkcionom semom | 🟢 dokazano zivo (23503 tek na FK) |
| deployment order dokazan | 🟢 jedan korak, bez DDL-a |
| mixed-version rizik resen | 🟢 monoton, bez pretpostavki o Renderu |
| finalni schema contract ocuvan | 🟢 migracija bajt-identicna, ugovor netaknut |
| authorization boundary netaknut | 🟢 6.2–6.5 regresija zelena |
| nema fallback-a | 🟢 0 pogodaka na zabranjene obrasce |
| nema provenance ambiguity | 🟢 16/16 kanonskih dodela |

## 12. STOP

**Nista nije izvrseno.** Bez ALTER-a, bez migracije, bez push-a, bez deploya.

Za odobrenje je potrebna jedna recenica od tebe:

> „Pushuj i deployuj `3039332a`."

Ako zelis da prvo vidis ekran za potvrdu (da rokovi ne budu nemi posle deploya),
reci to umesto — tada prvo gradim UI, pa deploy ide zajedno.
