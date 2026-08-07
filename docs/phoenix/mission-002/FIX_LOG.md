# Mission 002 — Fix Log

### Fix 1 — `static/vindex.js::_predInlineEdit` + `api.py::update_predmet` (closes `LIVINGSYS-DEBT-007`)

Frontend now sends `if_updated_at` from the last-known cached value, handles `409` explicitly,
and refreshes its cache from the backend's newly-returned `updated_at` on success:
```javascript
var _knownUpdatedAt = (window._predFull && window._predFull.predmet && window._predFull.predmet.updated_at) || null;
if (_knownUpdatedAt) body.if_updated_at = _knownUpdatedAt;
...
if (r.status === 409) {
  showToast('Predmet je izmenjen u međuvremenu. Osvežite stranicu i pokušajte ponovo.', 'error');
  span.textContent = curText;
  return;
}
...
if (_rj && _rj.updated_at && window._predFull && window._predFull.predmet) {
  window._predFull.predmet.updated_at = _rj.updated_at;
  window._predFull.predmet[field] = val;
}
```
Backend additive change:
```python
_new_updated_at = (result.data[0].get("updated_at") if result.data else None)
return {"ok": True, "updated_at": _new_updated_at}
```

### Fix 2 — `routers/learning.py` (closes `LIVINGSYS-DEBT-033`)

```python
_close_res = await asyncio.to_thread(
    lambda: supa.table("predmeti")
        .update({"status": novi_status})
        .eq("id", req.predmet_id)
        .eq("user_id", uid)
        .neq("status", novi_status)
        .execute()
)
if _close_res.data:
    try:
        await asyncio.to_thread(
            lambda: supa.table("predmet_hronologija").insert({
                "predmet_id": req.predmet_id, "user_id": uid,
                "dogadjaj": f"Predmet zatvoren (ishod zabeležen: {req.ishod})",
                "datum_iso": date.today().isoformat(),
                "vaznost": "informativan", "akter": "Learning Engine",
            }).execute()
        )
    except Exception as _he:
        logger.warning("[LEARNING] hronologija upis greška (non-fatal): %s", _he)
else:
    logger.info("[LEARNING] predmet status update preskočen (već zatvoren ili konkurentna izmena): %s", req.predmet_id)
```

### Fix 3 — `routers/zadaci.py` + `static/vindex.js` (closes `LIVINGSYS-DEBT-034`)

`StatusUpdate` model:
```python
if_updated_at: Optional[str] = None
```
`azuriraj_status`:
```python
q = supa.table("zadaci").update(update_data).eq("id", zadatak_id) \
    .or_(f"dodeljen_uid.eq.{uid},kreirao_uid.eq.{uid}")
if payload.if_updated_at:
    q = q.eq("updated_at", payload.if_updated_at)
r = await asyncio.to_thread(lambda: q.execute())
if not (r.data or []):
    if payload.if_updated_at:
        exists = ...  # existence recheck, ignoring if_updated_at
        if not exists.data:
            raise HTTPException(404, ...)
        raise HTTPException(409, "Zadatak je izmenjen u međuvremenu...")
    raise HTTPException(404, ...)
```
Frontend cache + wiring:
```javascript
var _zadaciCacheById = {};
// populated in _zadaciRenderBoard:
zadaci.forEach(function(z){ if (z && z.id) _zadaciCacheById[z.id] = z; });
// used in zadaci_setStatus:
var _cached = _zadaciCacheById[id];
if (_cached && _cached.updated_at) _body.if_updated_at = _cached.updated_at;
```

## Reuse discipline

Fix 1 and Fix 3 both reuse the exact `if_updated_at` optimistic-concurrency shape
`api.py::update_predmet` already established. Fix 2 reuses the exact `.neq()` write-time guard
`predmeti_close.py` already established. Zero new algorithms, zero new migrations.
