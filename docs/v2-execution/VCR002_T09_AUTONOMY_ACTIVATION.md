# VCR002 T09 — Autonomija A2/A3 (NS007): spremnost i paket za aktivaciju — `PASS_ISOLATED` / `BLOCKED_AUTHORITY`

**Osnova:** `b36235a3`. Kod autonomije je nepromenjen u VCR002: `git diff b36235a3..HEAD` nad `services/autonomy.py`, `routers/autonomy.py`, `workers/` i `migrations/` je prazan.

**Šta NIJE urađeno** (direktiva):
- migracija 136 na produkciji;
- Render Cron;
- tajne;
- plaćeno zakazivanje;
- probni ciklus na produkciji.

## Novi dokaz u odnosu na VCR001

VCR001 T08 je zabeležio `152 passed, 11 skipped`, uz netačnu napomenu „nema lokalnih PG binarnih fajlova“. PostgreSQL 17.9 postoji na mašini (`C:/Program Files/PostgreSQL/17/bin`).

U VCR002 je napravljen **izolovan, privremen klaster**:
- `initdb` u scratchpad-u;
- port 55432, samo `127.0.0.1`;
- korisnik `vx`, autentikacija `trust`;
- ničim nije povezan sa produkcijom.

Nad njim su pokrenuti svi NS007 testovi (`VX_TEST_PG_DSN=postgresql://vx@127.0.0.1:55432/postgres`):

**`163 passed, 0 skipped`** (82 s). Preskočenih više nema. Tih 11 testova sada radi nad **stvarnim PostgreSQL-om sa stvarnom migracijom 136**:

| Test | Šta dokazuje |
|---|---|
| `test_migracija_je_ponovljiva` | 136 se može primeniti dvaput bez greške |
| `test_20_istovremenih_zauzimanja_prozora_tacno_jedan_pobednik` | istovremeni pozivi planera → jedan ciklus po UTC prozoru |
| `test_20_istovremenih_zauzimanja_posla_tacno_jedan` | atomsko zauzimanje posla (`autonomy_claim_work_item`) |
| `test_isti_okidac_jedan_logicki_posao` | dupli rad: isti okidač = jedan logički posao |
| `test_10_istovremenih_placenih_budzet_3` | rezervacija budžeta pod konkurencijom: tačno 3 plaćena |
| `test_budzet_po_organizaciji_besplatan_ne_trosi_nepoznat_limit_zatvara` | budžet po organizaciji; nepoznat limit **zatvara** (fail-closed) |
| `test_zakup_pad_ponovno_zauzimanje_i_dead_letter` | istek zakupa, ponovno zauzimanje, iscrpljeni pokušaji → dead-letter |
| `test_rezultat_upisuje_samo_vlasnik_zakupa` | zastareo radnik ne može da prepiše rezultat |
| `test_rls_i_prava` | RLS i prava: `authenticated` nema EXECUTE na RPC ni INSERT/UPDATE |
| `test_brisanje_predmeta_brise_radne_proizvode` | brisanje predmeta briše radne proizvode |
| `test_lazna_baza_i_postgres_daju_iste_ishode` | lažna baza ostalih 152 testa daje iste ishode kao PostgreSQL |

**Ostali NS007 testovi** (bez PostgreSQL-a, i dalje zeleni):
- poništavanje izvora;
- nedostupan predmet;
- prelazi `READY_FOR_REVIEW`;
- prihvati/odbaci sa auditom;
- nema A5 spoljne radnje (radni proizvod nikad ne šalje, ne podnosi i ne menja predmet bez čoveka).

**Stanje u produkciji** (bez prijave, 2026-10-12): `POST /api/cron/autonomy` bez tajne → **401**. Ruta je zatvorena, što odgovara stanju bez `AUTONOMY_CRON_SECRET`. Tabele autonomije ne postoje (direktiva). V2 to iskreno prikazuje kao isključeno (`e2e:pre136`, zeleno u ovom programu).

## Paket za aktivaciju (odluka osnivača)

Tehnički postupak, kontrolna lista i opcije rasporeda su u `docs/v2-recovery/NS007_RENDER_CRON_PLAN.md`, i ovde se ne ponavljaju. Sažetak za odluku:

| Stavka | Šta | Ko |
|---|---|---|
| 1. Šema | primeniti `migrations/136_autonomy_work_items.sql` (pokrećete sami). Posle provere: 2 tabele + funkcija `autonomy_claim_work_item`; `authenticated` bez EXECUTE i bez INSERT/UPDATE (isto meri `test_rls_i_prava`) | osnivač |
| 2. Tajna | `AUTONOMY_CRON_SECRET` (≥ 32 znaka) na web servisu; kraća ili prazna drži rutu zatvorenom (401) | osnivač |
| 3. Budžet | `AUTONOMY_BUDGET_PER_ORG_DAILY`: podrazumevano 20 plaćenih izvršenja po organizaciji dnevno; neispravna vrednost = 0 plaćenih. Opcije: 5 (oprezan početak), 20 (podrazumevano) | osnivač |
| 4. Prvi ciklus | jedan ručni okidač (`scripts/trigger_autonomy_cycle.py`). Očekivano: 1 red `autonomy_cycles` COMPLETED; `autonomy_work_items` samo za stvarne okidače (ročišta u prozoru, provereni presedani) | osnivač |
| 5. Kadenca | A `0 3 * * *` (noću) · B `0 3,10 * * *` · C `0 6-17 * * 1-5`. Trošak ne zavisi od kadence, jer isti okidač = jedan posao | osnivač |
| 6. Render Cron | samo dve promenljive: URL + tajna; bez ključeva baze i modela | osnivač |

- **Prekidač za gašenje:** pauzirati Cron ili obrisati `AUTONOMY_CRON_SECRET` (ruta odmah vraća 401). Postojeći radni proizvodi ostaju za pregled.
- **Greške:**
  - pad baze pri zauzimanju = nijedan poziv modela (fail-closed);
  - pad izvršenja = ponovni pokušaj do iscrpljenja, pa dead-letter;
  - ciklus koji padne vraća 500 sa bezbednim poljima, a Render ga prijavljuje kao neuspeh.
- **Ograničenje oporavka:** posle pada procesa zakup ističe (`AUTONOMY_LEASE_SECONDS`, 300) i posao se ponovo zauzima. Plaćen poziv modela koji je bio u toku pre pada **nije vraćen**: najviše jedan dodatni poziv po posao.
- **Izloženost troškovima:** najviše `budžet × broj organizacija` plaćenih izvršenja dnevno. U solo beti je jedna organizacija po advokatu, pa je izloženost ≤ 20 izvršenja dnevno po aktivnom advokatu (ili ≤ 5 uz oprezan početak). Prati se kroz `usage_events(feature='autonomy')`.

**Kontrolna lista prihvatanja** (posle prve noći):
- [ ] `/api/cron/autonomy` bez tajne → 401;
- [ ] tačno 1 ciklus po prozoru;
- [ ] broj `usage_events(feature='autonomy')` jednak broju plaćenih izvršenja i ≤ budžeta;
- [ ] V2 Danas → „Vindex je pripremio“ prikazuje samo `READY_FOR_REVIEW`;
- [ ] prihvati/odbaci upisuje audit;
- [ ] nijedna spoljna radnja.

## Status

- **`PASS_ISOLATED`:** ceo NS007 paket, uključujući stvaran PostgreSQL.
- **`BLOCKED_AUTHORITY`:** stavke 1–6 iznad (migracija, tajna, budžet, prvi ciklus, kadenca, Cron).
