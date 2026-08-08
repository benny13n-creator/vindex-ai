# Mission 014 — Fix Log

### `routers/cio.py::_generiši_cio_izvestaj`
```python
_count_task = asyncio.create_task(asyncio.to_thread(
    lambda: supa.table("predmeti").select("id", count="exact")
        .eq("user_id", uid).in_("status", ["aktivan", "u_toku", "pending"])
        .limit(1).execute()
))
pred_r = await asyncio.to_thread(lambda: supa.table("predmeti").select(...)....execute())  # unchanged, fail-hard
predmeti_raw = pred_r.data or []
try:
    count_r = await _count_task
    total_aktivnih_u_bazi = count_r.count if isinstance(count_r.count, int) else len(predmeti_raw)
except Exception as _count_exc:
    logger.warning("[CIO] count upit neuspešan (nastavljam bez truncated signala): %s", _count_exc)
    total_aktivnih_u_bazi = len(predmeti_raw)
portfolio_truncated = total_aktivnih_u_bazi > len(predmeti_raw)
```
Both return paths (`if not portfolio: return {...}` and the main return) gained
`"ukupno_u_bazi": total_aktivnih_u_bazi, "truncated": portfolio_truncated` inside
`portfolio_zdravlje`.

### `static/vindex.js::_cioRender`
```js
if (pg.truncated) html += '<span ... title="Prikazano '+pg.ukupno_aktivnih+' od ukupno '+pg.ukupno_u_bazi+' aktivnih predmeta (najstariji nisu prikazani)."> · prikazano '+pg.ukupno_aktivnih+'/'+pg.ukupno_u_bazi+'</span>';
```

### `static/sw.js`
`CACHE_NAME` bumped `"vindex-v104"` → `"vindex-v105"`.

## Reuse discipline

The count query reuses the same `.select("id", count="exact").limit(1)` idiom already
established elsewhere in this codebase (`admin_dashboard.py`, `case_dna.py`, `corrections.py`).
The fail-soft/fail-hard split reuses the exact "core data vs. disclosure metadata" distinction
already applied in Mission 013. Zero new algorithms, zero migrations. The cap and ordering
themselves are untouched — this is a pure disclosure addition.
