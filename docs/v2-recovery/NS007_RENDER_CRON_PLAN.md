# NS007 — PLAN RASPOREĐIVAČA AUTONOMNOG RADA (Render Cron)

> **STATUS: NIJE POSTAVLJENO. POTREBNO ODOBRENJE FOUNDERA.**
> Ništa iz ovog dokumenta nije urađeno na produkciji: nema Render servisa, nema env promenljivih, nema okidanja.
> Kadenca NIJE odluka ovog sprinta — dole su opcije, ne izbor.

## Arhitektura (kandidat)

```
Render Cron Job (lagan, bez Vindex koda i bez tajni baze/modela)
  └─ python scripts/trigger_autonomy_cycle.py
       └─ POST https://vindex.rs/api/cron/autonomy   (zaglavlje X-Autonomy-Secret)
            └─ atomsko zauzimanje UTC prozora (autonomy_cycles)
                 └─ workers/background_agents.run_autonomy_cycle  (u postojećem web servisu)
```

Cron servis zna SAMO dve stvari: URL i tajnu okidača. `OPENAI_API_KEY`, Supabase ključevi i ostale tajne
**ne idu** u cron servis — posao se izvršava u postojećem web servisu, koji ih već ima.

## Preduslovi pre uključivanja (redom)

1. NS006 PR #9 spojen; NS007 grana rebase/retarget na `main` (odluka foundera).
2. Migracija `136_autonomy_work_items.sql` primenjena (founder). Provera posle: tabele `autonomy_cycles`,
   `autonomy_work_items`, funkcija `autonomy_claim_work_item`; `has_function_privilege('authenticated', …)` = false.
3. Na web servisu (Render env): `AUTONOMY_CRON_SECRET` = nasumična vrednost od najmanje 32 znaka (npr.
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`). Kraća ili prazna = ruta ostaje zatvorena (401).
4. Opciono na web servisu: `AUTONOMY_BUDGET_PER_ORG_DAILY` (podrazumevano 20 plaćenih izvršenja po organizaciji
   dnevno; neispravna vrednost = nijedno plaćeno izvršenje), `AUTONOMY_LEASE_SECONDS` (300),
   `AUTONOMY_MAX_ITEMS_PER_CYCLE` (25), `AUTONOMY_ITEM_TIMEOUT_SECONDS` (120).
5. Deploy web servisa sa NS007 kodom.
6. Ručni probni poziv (jednom), pa pregled `autonomy_cycles` i `autonomy_work_items`.
7. TEK ONDA Render Cron Job.

## Render Cron Job (kandidat konfiguracija)

| Polje | Vrednost |
|---|---|
| Tip | Cron Job |
| Repo / grana | isti repo, `main` (posle spajanja) |
| Build | nije potreban (`echo ok`) — skripta je samo stdlib |
| Komanda | `python scripts/trigger_autonomy_cycle.py` |
| Env | `AUTONOMY_TRIGGER_URL=https://vindex.rs/api/cron/autonomy`, `AUTONOMY_CRON_SECRET=<ista vrednost kao na web servisu>`, opciono `AUTONOMY_TRIGGER_TIMEOUT=900` |
| Raspored | **odlučuje founder** (v. ispod) |

Izlaz skripte: 0 samo za 2xx (`COMPLETED`, `SKIPPED`, `COMPLETED_UNRECORDED`); 401/500/503/isteklo vreme ≠ 0 —
Render tada prijavljuje neuspešan run. Skripta ispisuje samo status, prozor, run_id i brojeve; tajnu nikad.

## Kadenca — opcije (NIJE ODLUČENO)

Prozor je UTC sat: više okidanja u istom satu = jedan ciklus (ostala dobijaju `SKIPPED`). Zato je satni raspored
gornja granica smislene učestalosti.

| Opcija | Raspored (cron, UTC) | Posledica |
|---|---|---|
| A — jednom noću | `0 3 * * *` | priprema je gotova pre radnog dana; promena tokom dana čeka sledeću noć |
| B — noću + pre podne | `0 3,10 * * *` | ročište zakazano ujutru dobija pripremu do podne |
| C — radnim satima | `0 6-17 * * 1-5` | najbrže; najviše ciklusa (trošak je i dalje ograničen budžetom po organizaciji) |

Trošak NE zavisi direktno od kadence: plaćen posao nastaje samo iz stvarnog okidača (ročište, provereni presedan), a
isti okidač = jedan posao bez obzira na broj ciklusa.

## Odnos prema `/api/cron/daily`

Dnevni cron ostaje NEPROMENJEN i i dalje pokreće legacy agente preporuka (Modul 10). Ne poziva `/api/cron/autonomy`
i ova ruta ne zavisi od njegovog heartbeat-a. Poznat dug dnevnog crona (ne-atomski heartbeat, Task 0) je zabeležen
posebno i NIJE menjan u NS007.

## Isključivanje

Ukloniti/pauzirati Render Cron Job, ili obrisati `AUTONOMY_CRON_SECRET` na web servisu (ruta odmah vraća 401).
Postojeći radni proizvodi ostaju dostupni za pregled.
