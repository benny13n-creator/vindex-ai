# Mission 003 — Fix Log

### Fix 1 — `routers/firm_memory.py` (closes `LIVINGSYS-DEBT-008`)
5 call sites: `.order("vaznost")` → `.order("vaznost", desc=True)` (lines feeding `/pretrazi`,
`/kontekst-za-ai`, `/sudija/{ime}`, `/klijent/{ime}`, `/sve`).

### Fix 2 — `routers/memory_graph.py` (closes `LIVINGSYS-DEBT-052`)
```python
from shared.kancelarija_utils import get_kancelarija_id as _get_firma_id
```
Local `async def _get_firma_id(supa, uid)` definition removed (was byte-identical to the
canonical helper).

### Fix 3 — `shared/semantic_registry.py` (closes `LIVINGSYS-DEBT-017`)
```python
PROBABILITY = ConceptOwnership(
    concept="probability",
    owner=None,
    ...
    truth_contract_ref="#probability-successoutcome",
)
ALL_CONCEPTS: tuple[ConceptOwnership, ...] = (
    RISK, READINESS, STRENGTH, PRIORITY, RECOMMENDATION, HEALTH_FIRM, HEALTH_PER_CASE,
    PROBABILITY, CONFIDENCE, WEB3_COMPLIANCE_SCORES,
)
```

### Fix 4 — `services/risk_engine.py` (closes `LIVINGSYS-DEBT-055`)
```python
logger = logging.getLogger("vindex.risk_engine")
...
except Exception as _e:
    logger.warning(
        "[RISK_ENGINE] rociste sa nevalidnim datumom preskočen u proračunu rizika (id=%s, datum=%r): %s",
        r.get("id"), r.get("datum"), _e,
    )
```

## Reuse discipline

Fix 2 reuses the exact consolidation pattern already established 2026-07-26. Fix 3 reuses the
exact `ConceptOwnership` dataclass shape already used by all 9 pre-existing entries. Zero new
algorithms, zero new migrations.
