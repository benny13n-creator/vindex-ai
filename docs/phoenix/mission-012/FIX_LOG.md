# Mission 012 — Fix Log

### Fix 1 — `shared/usage.py` (closes `LIVINGSYS-DEBT-012` TOCTOU sub-item)
```python
async def _claim_cooldown_atomic(user_id: str, feature: str, cooldown: float) -> bool:
    # atomic UPDATE ... WHERE updated_at < cutoff; falls back to INSERT
    # (duplicate-key = lost the race) reusing UNIQUE(user_id, feature_key, dan)
    ...

# in UsageService.consume():
if cooldown:
    claimed = await _claim_cooldown_atomic(user_id, feature, cooldown)
    if not claimed:
        elapsed = await _seconds_since_last_call(user_id, feature)  # message only
        raise HTTPException(429, detail={"code": "COOLDOWN", ...})
```

### Fix 2 — `api.py` (closes `LIVINGSYS-DEBT-021`)
```python
def _validate_hronologija_datum_iso(datum_iso, predmet_id: str) -> Optional[str]: ...
def _insert_hronologija_rows(rows: list, predmet_id: str) -> int: ...

# in predmet_upload_auto_analyze:
datum_iso = _validate_hronologija_datum_iso(ev.get("datum_iso"), predmet_id)
...
hron_count = _insert_hronologija_rows(rows, predmet_id)
```

### Fix 3 — `routers/case_dna.py` (closes `LIVINGSYS-DEBT-045`)
```python
_genome_refresh_done_event: dict = {}
_GENOME_COALESCE_WAIT_TIMEOUT = 120.0  # module-level: patchable in tests

async def _run_genome_background(predmet_id, uid, stari_procent=None, trigger="upload_trigger"):
    if predmet_id in _genome_refresh_inflight:
        _genome_refresh_rerun.add(predmet_id)
        _done_event = _genome_refresh_done_event.get(predmet_id)
        if _done_event is not None:
            try:
                await asyncio.wait_for(_done_event.wait(), timeout=_GENOME_COALESCE_WAIT_TIMEOUT)
            except asyncio.TimeoutError:
                logger.warning("[GENOME] coalesced caller timed out ... predmet=%s", predmet_id)
        return
    _genome_refresh_inflight.add(predmet_id)
    _my_event = asyncio.Event()
    _genome_refresh_done_event[predmet_id] = _my_event
    try:
        while True:
            ...
    finally:
        _genome_refresh_inflight.discard(predmet_id)
        _genome_refresh_rerun.discard(predmet_id)
        _genome_refresh_done_event.pop(predmet_id, None)
        _my_event.set()
```
The `asyncio.wait_for` bound was added after this mission's own full-suite run caught a real
deadlock risk from an initially-unbounded wait — see `TEST_RESULTS.md`'s incident note.

### Fix 4 — `routers/cio.py::cio_run` (closes `LIVINGSYS-DEBT-046`)
```python
_claim_window_seconds = 5
_stale_cutoff_iso = (now - timedelta(seconds=_claim_window_seconds)).isoformat()
claimed = False
try:
    _upd = await asyncio.to_thread(lambda: supa.table("cio_dnevni_izvestaj").update(
        {"created_at": now.isoformat()}
    ).eq("user_id", uid).eq("datum", danes_iso).lt("created_at", _stale_cutoff_iso).execute())
    if _upd and _upd.data:
        claimed = True
except Exception: ...
if not claimed:
    try:
        await asyncio.to_thread(lambda: supa.table("cio_dnevni_izvestaj").insert({...}).execute())
        claimed = True
    except Exception as _claim_exc:
        if "duplicate key" not in str(_claim_exc).lower() and "unique" not in str(_claim_exc).lower():
            claimed = True
if not claimed:
    return {...}  # loser: no charge, no overwrite
if izvestaj.get("predmeta_analizirano"):
    await UsageService.consume(...)
```

## Reuse discipline

Fix 1 and Fix 4 reuse existing UNIQUE constraints (migrations 064 and 050, respectively) and the
exact retry-on-conflict idiom already proven in `billing.py`/`smart_intake.py`. Fix 3 reuses
`asyncio.Event`, the stdlib primitive for this pattern. Fix 2 reuses `date.fromisoformat` and the
established "fail safe, drop the bad piece" philosophy. Zero migrations, zero new algorithms.
