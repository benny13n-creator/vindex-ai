# Mission 004 — Fix Log

### Fix 1 — `routers/case_commander.py::commander_jutarnji` (closes `LIVINGSYS-DEBT-006`)
```python
claimed = True
try:
    await asyncio.to_thread(
        lambda: supa.table("commander_jutarnji").insert({
            "user_id": uid, "datum": danas, "brifing": {},
        }).execute()
    )
except Exception as _claim_exc:
    if "duplicate key" not in str(_claim_exc).lower() and "unique" not in str(_claim_exc).lower():
        logger.warning(...)
    else:
        claimed = False
...
if not claimed:
    return brifing  # own fresh result, not charged/cached
if n > 0:
    await UsageService.consume(...)
```

### Fix 2 — `routers/drafting.py::nacrt` (closes `LIVINGSYS-DEBT-002`)
```python
_ok = isinstance(rezultat, dict) and rezultat.get("status") == "success" and rezultat.get("data")
if _ok:
    preostalo = await UsageService.consume(...)
    ...
else:
    preostalo = await UsageService.balance(...)
```

### Fix 3 — `routers/drafting.py::podnesak` (closes `LIVINGSYS-DEBT-027`)
```python
if entiteti:
    await UsageService.consume(...)
else:
    logger.warning("Podnesak: naplata preskočena, ekstrakcija entiteta potpuno neuspešna [q=%s]", log_id)
```

## Reuse discipline

Fix 1 reuses CIO `/daily`'s own claim idiom (simplified for a table with no staleness window).
Fix 2 reuses `analiza()`'s own success-gated charging idiom verbatim. Zero new algorithms.
