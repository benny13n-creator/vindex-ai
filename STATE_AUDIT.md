# STATE_AUDIT.md — automatski generisano, ne rucno pisano

Generisano: 2026-07-19 07:56 UTC — pokretanjem `python scripts/audit_state.py`.
Ovo NIJE narativ. Svaka linija ispod je provera naspram zive baze ili koda,
ne pretpostavka o tome sta bi trebalo da bude live.

## Migracije — CREATE TABLE naspram zive baze

1/41 migracija ima bar jednu tabelu koja NIJE live:

- `058_briefing_saradnja_memory_webhooks.sql` — nedostaje: vindex_memory

## Ruteri — registrovan naspram stvarno pozvan

Provereno 104 registrovanih rutera (api.py `include_router`).

**14 registrovan(a) bez i jednog pronadjenog pozivaoca** (heuristika — vidi scripts/audit_routers.py za detalje/ogranicenja):

- `routers.auto_discovery`
- `routers.case_intelligence`
- `routers.gdpr`
- `routers.import_klijenti`
- `routers.knowledge_hygiene`
- `routers.knowledge_transfer`
- `routers.oblasti`
- `routers.onboarding`
- `routers.region`
- `routers.status_page`
- `routers.strategy_simulator`
- `routers.style_checker`
- `routers.ugovor_zastupanja`
- `routers.whatsapp_notif`

Moguce spoljni (webhook/cron, ne ocekuju interni poziv): `routers.integrations`, `routers.viber`
