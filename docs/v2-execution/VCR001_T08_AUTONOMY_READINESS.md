# VCR001 T08 — autonomija A2/A3 (NS007): spremnost — `PASS_ISOLATED` / aktivacija `BLOCKED_AUTHORITY`

## Odluka iz direktive
Aktivacija u produkciji (migracija 136, Render Cron, tajna) traži **zasebnu izričitu odluku osnivača**. Ništa od toga nije urađeno.

## Zatečeno stanje (P)
- **NS007 kod je u `main`** i u produkciji (`6ad0b13a`):
  - `services/autonomy.py`, `routers/autonomy.py` (`/api/cron/autonomy`), V2 „Vindex je pripremio“ (Danas, Pregled predmeta, `#/pripremljeno/<id>`).
- **Bez migracije 136 autonomija je ISKLJUČENA i to se istinito prikazuje** (`e2e:pre136`):
  - `GET /api/workspace` → `vindex_je_pripremio_stanje = NIJE_UKLJUCENO`, prazna lista;
  - blok „Vindex je pripremio“ nije prikazan;
  - `/api/autonomy/work-items/{id}` → 404;
  - nema akcija prihvati/odbaci.
  - Kontrola osetljivosti (`VX_E2E_AUTONOMIJA`) namerno pada kad je autonomija uključena — dokaz da test meri stanje.
- **VCR001 nije menjao autonomiju:** `git diff 6ad0b13a..HEAD` nad `services/autonomy*`, `routers/autonomy*`, `workers/` i `migrations/` je prazan.

## Dokazi na programskoj grani
| Dokaz | Rezultat | Nivo |
|---|---|---|
| svi NS007 testovi (`tests/test_ns007_*.py`) | **152 passed, 11 skipped** | LI |
| preskočeno | 11 testova na pravom PostgreSQL-u (`VX_TEST_PG_DSN`): u ovoj sesiji nema lokalnih PG binarnih fajlova; poslednji put zeleni u NS007 sesiji na istom kodu migracije 136 | — |
| `e2e:demo-ns007` (pripremljen rad, prihvati/odbaci, kroz V2) | zeleno (lokalno i u CI V2 NG) | BR |
| `e2e:pre136` (isključena autonomija + kontrola osetljivosti) | zeleno | BR |
| CI na R2 kandidatu | Test Suite 0 novih; Runtime 0 novih | CI |

## Preostali preduslovi za uključivanje (redom; sve je odluka osnivača)
Plan i kontrolna lista: `docs/v2-recovery/NS007_RENDER_CRON_PLAN.md`. Stanje stavki:

| # | Stavka | Stanje |
|---|---|---|
| 1 | NS006/NS007 kod u `main` | ✓ ispunjeno |
| 2 | Migracija `136_autonomy_work_items.sql` primenjena (osnivač je pokreće sam) | čeka osnivača |
| 3 | `AUTONOMY_CRON_SECRET` (≥ 32 znaka) na web servisu | čeka osnivača |
| 4 | opciono: `AUTONOMY_BUDGET_PER_ORG_DAILY` (20), `AUTONOMY_LEASE_SECONDS` (300) | odluka |
| 5 | deploy web servisa sa NS007 kodom | ✓ ispunjeno (produkcija `6ad0b13a`) |
| 6 | jedan ručni okidač (`scripts/trigger_autonomy_cycle.py`) i pregled `autonomy_cycles`/`autonomy_work_items` | posle 2–3 |
| 7 | izbor kadence (A/B/C), pa tek onda Render Cron Job | odluka osnivača |

**Isključivanje u svakom trenutku:** pauzirati Cron ili obrisati `AUTONOMY_CRON_SECRET` (ruta odmah vraća 401). Postojeći radni proizvodi ostaju dostupni za pregled.

## Šta T08 NE dokazuje
- Rad autonomije nad produkcionom bazom: nemoguće bez migracije 136 i bez odluke.
- Atomičnost RPC-a `autonomy_claim_work_item` na PostgreSQL-u u ovoj sesiji (PG testovi preskočeni; dokazani u NS007).
