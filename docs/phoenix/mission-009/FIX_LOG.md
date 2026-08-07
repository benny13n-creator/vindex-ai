# Mission 009 — Fix Log

### Fix 1 — `routers/court_predictor.py::argument_reputation` (closes `LIVINGSYS-DEBT-047`)
```python
_grounded_argumenti: set[str] = set()
...
for arg in payload.argumenti[:5]:
    ...
    if odluke:
        _grounded_argumenti.add(arg)
        ...

# after parsing rezultat:
for _a in (rezultat.get("argumenti_analiza") or []):
    if not isinstance(_a, dict):
        continue
    _a["rag_grounded"] = (_a.get("argument") or "").strip() in _grounded_argumenti
    ...
```
`static/vindex.js`'s Argument Reputation card renderer:
```js
+ (a.rag_grounded === false ? '<div ...>⚠ procena bez direktne potvrde iz sudske prakse</div>' : '')
```

### Fix 2 — `routers/drafting.py::_critique_and_refine_draft` (closes `LIVINGSYS-DEBT-015`)
```python
async def _critique_and_refine_draft(nacrt: str, kontekst: str, tip: str, log_id: str) -> tuple[str, bool]:
    try:
        ...
        if not ima_problema:
            return nacrt, True
        ispravljen = (kritika.get("ispravljen_tekst") or "").strip()
        if not ispravljen:
            logger.warning(...)
            return nacrt, False
        ...
        return ispravljen, True
    except Exception as exc:
        ...
        return nacrt, False
```
Call site:
```python
nacrt, critique_applied = await _critique_and_refine_draft(nacrt, kontekst, req.tip, log_id)
...
return {..., "critique_applied": critique_applied}
```
`static/index.html`: new conditional banner `#podnesak-preview-critique-warn`.
`static/vindex.js`: toggles it via `d.critique_applied === false`.

### Fix 3 — `static/sw.js`
`CACHE_NAME` bumped `"vindex-v101"` → `"vindex-v102"` (this mission touched `vindex.js`/
`index.html`). `tests/test_iron_lawyer_frontend_fixes.py`'s pinned-literal assertion updated.

## Reuse discipline

Fix 1 reuses the exact retrieval already performed for the first 5 arguments — no new query.
Fix 2 reuses the function's existing 3 return points, only widening the return type — no new
control flow. Zero migrations, zero new algorithms.
