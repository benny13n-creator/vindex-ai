# FAZA 6.6 — ROLLOUT SAFETY GATE

# 🔴 STOP — BASELINE NIJE OCEKIVAN. AKTIVAN PRODUKCIONI KVAR.

## 1. Sta je zateceno

Mandat kaze: *„Migration 127: NIJE IZVRSENA."*

**Izvrsena je.** Dokaz sa zive baze, tri nezavisna merenja:

```
1. kolona `izvor` POSTOJI u predmet_hronologija
2. svih 55 redova ima izvor = 'LEGACY_UNKNOWN'   (tacno backfill iz 127)
3. probni INSERT bez `izvor` -> SQLSTATE 23502
   "null value in column \"izvor\" ... violates not-null constraint"
```

Dakle `NOT NULL` je **aktivan i primenjuje se**.

## 2. Zasto je to kvar, a ne uspeh

```
produkcija radi commit  044c5310   (potvrdjeno zivo preko /api/version)
lokalni HEAD            3039332a   (NIJE pushovan)
```

Kod koji je **pusten u produkciji** (`044c5310`) upisuje `izvor` u **0 od 16**
pisaca `predmet_hronologija`. Provereno `git show 044c5310:<fajl>` za svih 16.
(`services/case_evolution.py` ima 4 pogotka na `"izvor"`, ali su to nepovezani
kljucevi u `case_actions.dokaz` JSON-u, ne hronologija.)

Kod koji **zna** da upise `izvor` je lokalni `3039332a` — i on nije deployovan.

**Posledica: svaki upis u `predmet_hronologija` u produkciji trenutno pada sa
23502.**

## 3. Obim — sta advokat vidi

Od 16 pisaca, **5 pada glasno** (korisnik dobija gresku) a **10 tiho gubi
podatak** (izuzetak se hvata i loguje):

| Pisac | Sta se desava |
|---|---|
| W-CONFIRMLINKS (`api.py`) | 🔴 glasno — potvrda veza puca |
| W-INTAKE-ROK (`intake.py`) | 🔴 glasno |
| W-ROKOVILANAC (`rokovi_lanac.py`) | 🔴 glasno — ZPP lanac vraca 503 |
| W-UGOVOR (`ugovor_zastupanja.py`) | 🔴 glasno |
| W-EVOLUTION (`case_evolution.py`) | 🔴 glasno — posledica na sabirnici puca |
| **W-GENOME** (`case_dna.py`) | ⚠️ **TIHO** — rok iz dokumenta nestaje bez traga |
| **W-UPLOAD** (`api.py`) | ⚠️ **TIHO** — cela hronologija iz uploada nestaje |
| **W-SMARTINTAKE** | ⚠️ **TIHO** |
| W-COPILOT, W-PIPELINE, W-CLOSE, W-LEARNING, W-ONBOARDING, W-INTAKE-TPL1/2 | ⚠️ TIHO |
| W-ROCISTE | ⚪ oblik koda nije jednoznacan iz statickog citanja |

Tiho gubljenje je gore od glasnog pada: advokat uploaduje dokument, sistem kaze
da je sve u redu, a nijedan rok ne udje u hronologiju.

## 4. Zasto se ovo desilo — odgovor na PART II

Ovo **jeste** odgovor na pitanje o redosledu, samo dobijen skupo:

| Scenario | Ishod |
|---|---|
| **A. migracija prvo, stari kod jos radi** | 🔴 **ovo se desilo** — svaki upis pada 23502 |
| **B. novi kod prvo, migracija posle** | 🔴 takodje pada — kolona ne postoji, PostgREST odbija upit |
| **C. expand → deploy → backfill → contract** | 🟢 jedini bezbedan |

Migracija 127 je napisana kao **jedan atomski skript** (`ADD → backfill → CHECK
→ NOT NULL`). To je ispravno kao *finalno stanje*, ali **nije bezbedno kao
jedan korak** dok stari kod jos radi: izmedju zavrsetka migracije i deploy-a
koda postoji prozor u kome sve pada. Taj prozor je sada otvoren.

**Ugovor se NE menja.** Finalna sema ostaje `NOT NULL + CHECK + BEZ DEFAULT-a`.
Menja se samo redosled primene.

## 5. Sta NIJE resenje

Izricito odbaceno, po §3 mandata:
`DEFAULT` na `izvor` · trigger koji popunjava provenijenciju · izvodjenje iz
`akter` · „ako nema izvor → HUMAN_DIRECT" · `LEGACY_UNKNOWN` kao runtime default
za nove upise · try/except koji guta 23502.

Svako od toga bi vratilo tacno onu klasu greske koju su faze 6.1–6.5 zatvarale.

## 6. Dve opcije — obe su tvoje, ja ne izvrsavam nijednu

### Opcija 1 — vrati `NOT NULL` (najbrze, minimalno)
```sql
ALTER TABLE public.predmet_hronologija ALTER COLUMN izvor DROP NOT NULL;
```
Produkcija odmah ponovo pise rokove. Kolona, `CHECK` i backfill **ostaju**.
Ovo NIJE workaround nego **korak „expand"** koji je trebalo da dodje pre
deploy-a koda. `NOT NULL` se vraca posle deploy-a (korak „contract").

Rizik: dok je `NOT NULL` iskljucen, novi redovi mogu nastati bez provenijencije.
Oni se posle prepoznaju kao `izvor IS NULL` i mogu se popuniti pre nego sto se
`NOT NULL` vrati.

### Opcija 2 — deployuj kod koji pise `izvor`
Push 7 commita (`27a4dd87` … `3039332a`) i deploy. Time prestaje 23502.

**Ali:** isti deploy aktivira i celu granicu iz faza 6.2–6.5. Posledica koju sam
vec dvaput izgovorio: **svi postojeci rokovi su `LEGACY_UNKNOWN`, dakle
nepotvrdjeni**, pa email, SMS, Viber, WhatsApp, kalendar i klijentski portal za
njih **cute** dok ih ne potvrdis. Rute za potvrdu postoje
(`/api/rokovi/kandidati`, `/potvrdi`, `/odbij`), **ekran ne postoji.**

### Preporuka
**Prvo Opcija 1** — zaustavi tiho gubljenje rokova odmah, jednim ALTER-om.
Zatim mirno: deploy koda → provera → vracanje `NOT NULL`. Opcija 2 sama resava
23502, ali u istom trenutku gasi sve podsetnike, sto je velika promena da bi se
radila pod pritiskom.

## 7. Sta NIJE uradjeno u ovoj fazi

Po PART I („ako baseline nije ocekivan: STOP") zaustavio sam se pre analize
rollout scenarija u punom obimu i pre definisanja UI ugovora.

**0 izmena koda · 0 DDL · 0 push · 0 deploy · 0 novih produkcionih redova.**
Migracija 127 nije menjana. Jedini trag koji sam ostavio je probni INSERT koji
je **odbijen** (23502) — dakle nijedan red nije nastao.

PART IV–VI (ugovor za UI potvrde) ostaju nedirnuti i cekaju resenje ovog kvara —
nema smisla definisati ekran dok osnovni upis pada.

## 8. VERDICT

# 🔴 RED — BLOCKED

Ne zato sto rollout order nije dokaziv — nego zato sto je **vec izvrsen
pogresnim redosledom i produkcija je u kvaru**.

```
HEAD 3039332a · origin/main = production 044c5310 · NIJE pushovano
migracija 127: IZVRSENA (suprotno premisi mandata)
predmet_hronologija: 55 redova, svi LEGACY_UNKNOWN, NOT NULL aktivan
```
