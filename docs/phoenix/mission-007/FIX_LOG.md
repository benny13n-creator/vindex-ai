# Mission 007 — Fix Log

### Fix 1 — `services/case_evolution.py::_consequence_timeline_entry` (partial `LIVINGSYS-DEBT-011`)
```python
_dup_r = await asyncio.to_thread(
    lambda: supa.table("predmet_hronologija").select("id")
        .eq("predmet_id", predmet_id).eq("dogadjaj", opis)
        .gte("created_at", _iso_seconds_ago(_CONSEQUENCE_STALE_PENDING_SECONDS))
        .limit(1).execute()
)
if _dup_r.data:
    return str(_dup_r.data[0]["id"])
```

### Fix 2 — `services/case_evolution.py::CONSEQUENCE_REGISTRY` (closes `LIVINGSYS-DEBT-016`)
```python
EventType.NEW_EVIDENCE_REGISTERED: [
    ConsequenceDef(name="evidence_classification", executor=_consequence_evidence_classify),
    ConsequenceDef(name="refresh_case_actions", executor=_consequence_refresh_case_actions),
],
```

## Reuse discipline

Fix 1 reuses the exact "identical content, recent window" idiom already proven for
`LIVINGSYS-DEBT-043` (Mission 005), and the existing `_CONSEQUENCE_STALE_PENDING_SECONDS`
constant. Fix 2 reuses the exact `_consequence_refresh_case_actions` executor 3 other event
types already register unchanged. Zero new algorithms, zero migrations.
