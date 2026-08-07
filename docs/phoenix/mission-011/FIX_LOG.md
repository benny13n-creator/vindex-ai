# Mission 011 — Fix Log

### Fix 1 — `routers/billing.py::faktura_create` (closes `LIVINGSYS-DEBT-054`)
```python
mismatched_predmet = [e["id"] for e in entries if e.get("predmet_id") != body.predmet_id]
if mismatched_predmet:
    raise HTTPException(status_code=400, detail="Neke od odabranih radnji ne pripadaju navedenom predmetu.")
```

### Fix 2 — new migration `migrations/106_phoenix_predmet_dokumenti_redni_broj_unique.sql`
```sql
CREATE UNIQUE INDEX IF NOT EXISTS predmet_dokumenti_predmet_redni_unique
    ON public.predmet_dokumenti (predmet_id, redni_broj);
```

### Fix 3 — `routers/smart_intake.py`'s finalize document loop (closes `LIVINGSYS-DEBT-044`)
```python
dok_ins = None
for _redni_attempt in range(3):
    _base_rn = {**_dok_row_base, "redni_broj": _sledeci_redni}
    # ... build the same 6 fallback variants from _base_rn ...
    _redni_conflict = False
    for extra in (variant_1, ..., variant_6):
        try:
            dok_ins = await asyncio.to_thread(lambda r=extra: supa.table("predmet_dokumenti").insert(r).execute())
            break
        except Exception as dok_exc:
            if ("23505" in str(dok_exc) or "duplicate key" in str(dok_exc).lower()) and "redni" in str(dok_exc).lower():
                _redni_conflict = True
                break
            logger.debug(...)
    _sledeci_redni += 1
    if dok_ins and dok_ins.data:
        break
    if not _redni_conflict:
        break
    logger.warning("[SMART_INTAKE] redni_broj konflikt (pokušaj %d/3) predmet=%s", _redni_attempt + 1, predmet_id)
    dok_ins = None
```

### Test corrections
- `tests/test_lambda008_certification.py` (2 tests): `entries_chain` mock rows gained
  `"predmet_id": "p1"` (matching the test's own `FakturaReq(predmet_id="p1", ...)`).
- `tests/test_blackswan_mission001.py` (1 test): same correction.

## Reuse discipline

Fix 1 reuses data already fetched in the same function (`entries`, no new query). Fix 3 reuses
`billing.py`'s own already-proven retry-on-conflict idiom and the existing 6-variant fallback
ladder structure, only adding a redni-specific conflict branch and an outer bounded retry. Zero
new algorithms.
